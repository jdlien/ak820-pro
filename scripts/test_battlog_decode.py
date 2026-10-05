#!/usr/bin/env python3
"""Host decode tests for the battery log's v3, v4 and v5 replies
(plans/BATTERY-GAUGE-REFINE-PLAN.md, B: "Host decode tests on v3, v4 and v5
replies, each with its version byte"). Builds replies byte for byte as the
firmware's battery_log_read() lays them out, then runs ak820battery.py's own
dump_v3() over a fake device."""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
sys.modules.setdefault("hid", type(sys)("hid"))
sys.modules.setdefault("venv_bootstrap", type(sys)("venv_bootstrap"))
sys.modules.setdefault("ak820health", type(sys)("ak820health"))
sys.modules["ak820health"].open_device = None
import ak820battery as B

fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("  FAIL", msg)


def entry16(vdd=3901, vmin=3870, c5_sum=12345, c5_n=300, c5_min=40, c5_max=43, flags=0x41,
            flags_any=0x41, level=71, led=1000, bkl=5, ver=4):
    e = struct.pack("<HHHBBBBBBHB", vdd, vmin, c5_sum, c5_n & 0xFF, c5_min, c5_max, flags, flags_any,
                    level, led, bkl)
    return e + bytes([c5_n >> 8 if ver >= 4 else 0])


def reply(ver, count, idx, since, period, written, e):
    if ver >= 5:
        body = struct.pack("<BHHIH", ver, count, idx, since, written) + e
    else:
        body = struct.pack("<BHHIHH", ver, count, idx, since, period, written) + e
    r = bytes([B.SET_VALUE, B.HEALTH_CHANNEL, B.HC_BATTLOG]) + body
    assert len(r) == 32, (ver, len(r))
    return r


def run(ver, entries, period=600):
    """dump_v3 over a fake board holding `entries` (bytes each)."""
    def xfer(h, cmd, args=()):
        if cmd == B.HC_BATTCFG:
            out = bytearray(32)
            out[:3] = bytes([B.SET_VALUE, B.HEALTH_CHANNEL, B.HC_BATTCFG])
            out[10:12] = struct.pack("<H", period)
            return bytes(out)
        idx = args[0] | args[1] << 8
        return reply(ver, len(entries), idx, 5000, period, 77, entries[idx])
    B.xfer = xfer
    return B.dump_v3(None)


# v3: one-byte count (no high byte), whole-percent level.
rows, count, since, period, ver = run(3, [entry16(c5_n=230, level=71, ver=3)])
r = rows[0]
check(ver == 3 and period == 600, f"v3 header {ver} {period}")
check(r["c5_n"] == 230 and r["level"] == 71 and r["c5_mean"] == f"{12345 / 230:.2f}", f"v3 row {r}")
check("m" not in r, "v3 has no m")

# v4: the count's high byte, the level in 0.5 %.
rows, count, since, period, ver = run(4, [entry16(c5_n=300, level=71)])
r = rows[0]
check(ver == 4 and r["c5_n"] == 300 and r["level"] == "35.5", f"v4 row {r}")
check(r["pack_mv"] == f"{(12345 / 300 + B.FIT_OFFSET) / B.FIT_SLOPE * 1000:.0f}", f"v4 pack {r['pack_mv']}")

# v5: 18-byte entries, the period from HC_BATTCFG, m and chg.
e5 = entry16(c5_n=300, level=150) + bytes([152, 0x03 | 0x08 | 0x80])   # m 76.0 %, MODEL, LOST, saturated
e5b = entry16(c5_n=280, c5_max=100, level=198) + bytes([0xFF, 0x05 | 0x10 | 0x20 | 0x40])   # FULL, OVERRUN, handover, selfcheck
rows, count, since, period, ver = run(5, [e5, e5b], period=600)
check(ver == 5 and period == 600 and count == 2, f"v5 header {ver} {period} {count}")
a, b = rows
check(a["m"] == "76.0" and a["chg_state"] == "model" and a["chg_lost"] == 1 and a["c5_saturated"] == 1
      and a["chg_overrun"] == 0, f"v5 row a {a}")
check(b["m"] == "" and b["chg_state"] == "full" and b["chg_overrun"] == 1 and b["chg_handover"] == 1
      and b["chg_selfcheck"] == 1 and b["chg_lost"] == 0, f"v5 row b {b}")
check(b["pack_mv"] == "", "a report at 100 withholds pack_mv")
t0, t1 = a["time"], b["time"]
check(t0 != t1, "entries ten minutes apart")

# A v5 period that is not 600 s is the board's, never assumed.
rows, count, since, period, ver = run(5, [e5, e5b], period=300)
check(period == 300, f"v5 period from HC_BATTCFG: {period}")

print(f"{'FAIL' if fails else 'ok  '} battlog decode v3/v4/v5")
sys.exit(1 if fails else 0)
