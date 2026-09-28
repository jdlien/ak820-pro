#!/usr/bin/env python3
"""Read the AK820 Pro's battery state, its battery log, and the low-battery
thresholds over raw HID. See docs/battery.md and plans/BATTERY-GAUGE-PLAN.md.

Wire format (health channel 0x13, firmware hid_protocol.c / battery.c):
    HC_CONN    0x02  [.., .., 0x02] -> link state, then the battery at [12..31]
    HC_BATTLOG 0x0A  [.., .., 0x0A, idx u16] -> one page of the log
    HC_BATTCFG 0x0B  [.., .., 0x0B, op, warn u16, cut u16] -> thresholds

Three log formats exist:
    v1 (b35d8672b3)  no version byte; two 8-byte entries a page, one a minute
    v2 (36be68f16a)  version 2; one 12-byte entry, one a minute (never flashed)
    v3 (the gauge)   version 3; one 16-byte entry, the PERIOD IN THE REPLY
                     (10 min), every `5C` report in the period aggregated
v3 firmware says so in HC_CONN byte 31 (BATTERY_PROTO_VERSION); older firmware
leaves the host's own zero there. ⚠️ Never assume the period: a 10-minute log
read as one-minute entries is ten times too fast, and so is every dV/dt.

Opens the board through ak820health.open_device(), which calls hid_enumerate:
fine on macOS, but on Windows that opens every HID device on the machine (see
CLAUDE.md, "Never enumerate HID") -- do not run it there as it stands.

Needs the USB cable. The slider position does not matter for the read, but
moving the slider from BT to cable RESETS the board and loses the RAM log: to
keep a wireless session's log, plug in with the slider still on BT.

Usage:
    ak820battery.py                 battery state (HC_CONN)
    ak820battery.py log [out.csv]   dump the log (stdout without a file)
    ak820battery.py cfg [WARN CUT]  read, or set, the thresholds in mV (0 = off);
                                    PACK mV on v3 firmware, VDD mV before it
"""
import csv, sys, time
import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
from ak820health import open_device

SET_VALUE, HEALTH_CHANNEL = 0x07, 0x13
HC_CONN, HC_BATTLOG, HC_BATTCFG = 0x02, 0x0A, 0x0B
FLAGS_V2 = ["on_batt", "charging", "done", "rgb_on", "lights_cut", "slider_usb", "linked", "clamped"]
FLAGS_V3 = ["on_batt", "charging", "done", "rgb_on", "lights_cut", "slider_usb", "linked", "external"]
STATES = ["none", "battery", "charging", "full", "usb"]
BATT_PROTO_V3 = 3

# 5C = 114.22 * V - 361.04 (five meter points, 3.30-3.84 V, discharge). The
# firmware carries the same constants; change both together.
FIT_SLOPE, FIT_OFFSET = 114.22, 361.04


def u16(b, i):
    return b[i] | (b[i + 1] << 8)


def u32(b, i):
    return u16(b, i) | (u16(b, i + 2) << 16)


def xfer(h, cmd, args=()):
    args = list(args)
    h.write(bytes([0x00, SET_VALUE, HEALTH_CHANNEL, cmd] + args + [0x00] * (29 - len(args))))
    # Windows delivers every input report to every open handle, and other
    # processes (the host agents) talk on this channel too: take only a reply
    # to the command we sent.
    for _ in range(5):
        rep = h.read(32, 1000)
        if not rep:
            break
        if rep[0] == SET_VALUE and rep[1] == HEALTH_CHANNEL and rep[2] == cmd:
            return bytes(rep)
    sys.exit(f"no reply to 0x{cmd:02x}")


def flags_str(f, names):
    return " ".join(name for i, name in enumerate(names) if f & (1 << i)) or "-"


def log_format(r):
    """The log format a HC_CONN reply's firmware writes: 3, 2 or 1."""
    if r[31] == BATT_PROTO_V3:
        return 3
    return 2 if u16(r, 26) != 0 else 1


def status(h):
    r = xfer(h, HC_CONN)
    fmt = log_format(r)
    age = r[22]
    age_s = "never/stale" if age == 255 else f"{age} s ago"
    if fmt == 3:
        f = r[23]
        supply = "battery" if f & 0x01 else "external (USB)" if f & 0x80 else "unknown"
        state = STATES[r[30]] if r[30] < len(STATES) else r[30]
        med, pk, lvl = r[21], u16(r, 26), u16(r, 24)
        print(f"supply       {supply}  ({state})")
        print(f"level        {'unknown' if lvl == 0xFFFF else f'{lvl / 10:.1f} %'}")
        if med == 0xFF:
            print("pack         no fresh 5C reports")
        else:
            bound = ">=" if med == 100 else "<=" if med == 0 else "  "
            print(f"pack         {bound}{pk} mV  (median 5C {med})")
        print(f"module 5C    last {r[5]}%, {age_s}")
        print(f"vdd          {u16(r, 12)} mV  (raw {u16(r, 14)}, since boot {u16(r, 16)}..{u16(r, 18)} mV)"
              "  -- the rail, not the pack")
        print(f"charger pins CHRG {'low (charging)' if not r[20] & 1 else 'high'}, "
              f"STDBY {'low' if not r[20] & 2 else 'high'}")
        print(f"led drive    {u16(r, 28) / 10:.1f} % of maximum")
        print(f"flags        {flags_str(f, FLAGS_V3)}")
        return fmt
    print(f"vdd          {u16(r, 12)} mV  (raw {u16(r, 14)}, since boot {u16(r, 16)}..{u16(r, 18)} mV)")
    print(f"charger pins CHRG {'low (charging)' if not r[20] & 1 else 'high'}, "
          f"STDBY {'low' if not r[20] & 2 else 'high'}")
    print(f"module 5C    {r[5]}%  (min {r[21]}, last report {age_s})")
    print(f"flags        {flags_str(r[23], FLAGS_V2)}")
    if fmt == 2:
        soc = u16(r, 24)
        state = STATES[r[30]] if r[30] < len(STATES) else r[30]
        print(f"estimate     {'unknown' if soc == 0xFFFF else f'{soc / 100:.2f} %'}  ({state})")
        print(f"regulator    {u16(r, 26)} mV learned output")
        print(f"led drive    {u16(r, 28) / 10:.1f} % of maximum")
    return fmt


def stamp(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def dump_v3(h):
    """Read every entry. The ring can take a new entry mid-dump, which shifts
    every index by one; the reply's written-count says so, and the dump is
    retried rather than silently duplicating or dropping a row."""
    for _ in range(3):
        first = xfer(h, HC_BATTLOG, [0, 0])
        if first[3] != 3:
            sys.exit(f"unexpected log format {first[3]}")
        count, since, period, written = u16(first, 4), u32(first, 8), u16(first, 12), u16(first, 14)
        newest = time.time() - since / 1000.0
        rows, torn = [], False
        for n in range(count):
            r = first if n == 0 else xfer(h, HC_BATTLOG, [n & 0xFF, n >> 8])
            if u16(r, 6) != n or u16(r, 14) != written:
                torn = True
                break
            e = r[16:32]
            c5_sum, c5_n, c5_min, c5_max = u16(e, 4), e[6], e[7], e[8]
            mean = c5_sum / c5_n if c5_n else None
            # Pack mV only when no report in the period sat on a clamp: a mean
            # that includes a clamped 100 or 0 is a mean of bounds.
            pack = "" if mean is None or c5_min == 0 or c5_max == 100 \
                else f"{(mean + FIT_OFFSET) / FIT_SLOPE * 1000:.0f}"
            row = {"time": stamp(newest - (count - 1 - n) * period),
                   "vdd_avg": u16(e, 0), "vdd_min": u16(e, 2),
                   "c5_mean": "" if mean is None else f"{mean:.2f}", "c5_n": c5_n,
                   "c5_min": "" if not c5_n else c5_min, "c5_max": "" if not c5_n else c5_max,
                   "pack_mv": pack, "level": "" if e[11] == 0xFF else e[11],
                   "led_pm": u16(e, 12), "bkl": e[14]}
            row.update({name: (e[9] >> i) & 1 for i, name in enumerate(FLAGS_V3)})
            row["flags_any"] = flags_str(e[10], FLAGS_V3)
            rows.append(row)
        if not torn:
            return rows, count, since, period
    sys.exit("the log kept moving under the dump; try again")


def dump_log(h, out):
    fmt = log_format(xfer(h, HC_CONN))
    rows = []
    if fmt == 3:
        rows, count, since, period = dump_v3(h)
    else:
        first = xfer(h, HC_BATTLOG, [0, 0])
        period = 60
        if fmt == 2:
            if first[3] != 2:
                sys.exit(f"unexpected log format {first[3]}")
            count, since = u16(first, 4), u32(first, 8)
            newest = time.time() - since / 1000.0
            for n in range(count):
                r = first if n == 0 else xfer(h, HC_BATTLOG, [n & 0xFF, n >> 8])
                e = r[12:24]
                soc = u16(e, 4)
                row = {"time": stamp(newest - (count - 1 - n) * period),
                       "vdd_avg": u16(e, 0), "vdd_min": u16(e, 2),
                       "soc": "" if soc == 0xFFFF else f"{soc / 100:.2f}",
                       "led_pm": u16(e, 6), "module_pct": e[8], "rgb_val": e[10], "module_age_s": e[11]}
                row.update({name: (e[9] >> i) & 1 for i, name in enumerate(FLAGS_V2)})
                rows.append(row)
        else:
            count, since = u16(first, 3), u32(first, 7)
            newest = time.time() - since / 1000.0
            for idx in range(0, count, 2):
                r = first if idx == 0 else xfer(h, HC_BATTLOG, [idx & 0xFF, idx >> 8])
                for k in range(2):
                    n = idx + k
                    if n >= count:
                        break
                    e = r[11 + 8 * k: 19 + 8 * k]
                    row = {"time": stamp(newest - (count - 1 - n) * period),
                           "vdd_avg": u16(e, 0), "vdd_min": u16(e, 2),
                           "module_pct": e[4], "rgb_val": e[6], "module_age_s": e[7]}
                    row.update({name: (e[5] >> i) & 1 for i, name in enumerate(FLAGS_V2[:7])})
                    rows.append(row)
    f = open(out, "w", newline="") if out else sys.stdout
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["time"])
    w.writeheader()
    w.writerows(rows)
    print(f"# {count} entries (log v{fmt}, one per {period} s), newest {since / 1000:.0f} s ago",
          file=sys.stderr)


def cfg(h, argv):
    fmt = log_format(xfer(h, HC_CONN))
    if len(argv) == 2:
        w, c = int(argv[0]), int(argv[1])
        r = xfer(h, HC_BATTCFG, [1, w & 0xFF, w >> 8, c & 0xFF, c >> 8])
    else:
        r = xfer(h, HC_BATTCFG, [0])
    on = "pack" if fmt == 3 else "VDD"
    print(f"warn {u16(r, 4)} mV  cut {u16(r, 6)} mV  ({on})  lights_cut {r[8]}  warned {r[9]}  "
          f"log period {u16(r, 10)} s  (RAM only: a reset restores the defaults)")


def main():
    h = open_device()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "log":
            dump_log(h, sys.argv[2] if len(sys.argv) > 2 else None)
        elif len(sys.argv) > 1 and sys.argv[1] == "cfg":
            cfg(h, sys.argv[2:])
        else:
            status(h)
    finally:
        h.close()


if __name__ == "__main__":
    main()
