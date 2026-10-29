#!/usr/bin/env python3
"""op 24's sleep slots on a dev build: the wake ring (0-7), the last stray's
snapshot (8, scripts/deep_cycles.py's decode) and, from gremlin/ds-phase
(27d1105d), slot 9: the sleep under way or the last one, kept through a reset; from
fcb7ae00, slot 10: slot 9 as this boot inherited it (magic DSL2).
Prints JSON; also the watchdog record via `ak820 health --json`."""
import json, os, subprocess, sys

R = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, os.path.join(R, "scripts"))
import deep_cycles as dc  # noqa: E402
import deep_sleep as ds  # noqa: E402

cm = ds.cm
REASONS = ds.REASONS


def slot(h, n):
    r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, 24, n] + [0] * 27)
    if len(r) < 32 or r[3] != 24:
        return None
    return bytes(r[4:32])


def u16(b, i): return int.from_bytes(b[i:i + 2], "little")
def u32(b, i): return int.from_bytes(b[i:i + 4], "little")


def read(h):
    out = {"ring": []}
    for n in range(8):
        b = slot(h, n)
        if b is None:
            continue
        out["wake_seq"] = u16(b, 26)
        e = {"seq": u16(b, 0), "reason": REASONS.get(b[2], b[2]), "flags": b[3], "counted": u32(b, 4),
             "p0": hex(u32(b, 8)), "p1": hex(u32(b, 12)), "p2": hex(u32(b, 16)), "ms": u32(b, 20), "strays": u16(b, 24)}
        if any(b[:26]):
            out["ring"].append(e)
    out["ring"].sort(key=lambda e: e["seq"])
    out["stray"] = dc.stray_diag(h)
    for n, key in ((9, "last"), (10, "inherited")):
        b = slot(h, n)
        if b is None:
            continue
        f = b[7]
        out[key] = {"magic_ok": u32(b, 0) == 0x44534C32, "seq": u16(b, 4), "reason": REASONS.get(b[6], b[6]),
                       "flags": hex(f), "clk_ceil": bool(f & 1), "pll_ceil": bool(f & 0x20), "slept": bool(f & 0x40),
                       "returned": bool(f & 0x80), "secs": u32(b, 8), "p0": hex(u32(b, 12)), "p1": hex(u32(b, 16)),
                       "p2": hex(u32(b, 20)), "strays": u16(b, 24), "from_boot_before" if n == 9 else "present": bool(b[26]),
                    "rstst": hex(b[27])}
    return out


def main():
    res = ds.with_dev(read)
    try:
        hj = json.loads(subprocess.run([ds.AK820, "health", "--json"], capture_output=True, text=True, timeout=15).stdout)
        res["watchdog_record"] = hj.get("watchdog_record", hj)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        res["watchdog_record"] = f"unread: {e}"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
