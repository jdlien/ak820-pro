#!/usr/bin/env python3
"""Read the AK820 Pro's battery state, its once-a-minute battery log, and the
low-battery thresholds over raw HID. See docs/battery.md.

Wire format (health channel 0x13, firmware hid_protocol.c / battery.c):
    HC_CONN    0x02  [.., .., 0x02] -> link state, then the battery at [12..30]
    HC_BATTLOG 0x0A  [.., .., 0x0A, idx u16] -> one page of the log
    HC_BATTCFG 0x0B  [.., .., 0x0B, op, warn u16, cut u16] -> thresholds

Two log formats exist. v1 (firmware b35d8672b3) has no version byte and two
8-byte entries per page; v2 (36be68f16a onward) starts with a version byte (2)
and carries one 12-byte entry with the level estimate and the LED drive. The
reader tells them apart by HC_CONN: only v2 firmware reports a regulator
output at [26..27].

Opens the board through ak820health.open_device(), which calls hid_enumerate:
fine on macOS, but on Windows that opens every HID device on the machine (see
CLAUDE.md, "Never enumerate HID") -- do not run it there as it stands.

Needs the USB cable. The slider position does not matter for the read, but
moving the slider from BT to cable RESETS the board and loses the RAM log: to
keep a wireless session's log, plug in with the slider still on BT.

Usage:
    ak820battery.py                 battery state (HC_CONN)
    ak820battery.py log [out.csv]   dump the log (stdout without a file)
    ak820battery.py cfg [WARN CUT]  read, or set, the thresholds in mV (0 = off)
"""
import csv, sys, time
import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
from ak820health import open_device

SET_VALUE, HEALTH_CHANNEL = 0x07, 0x13
HC_CONN, HC_BATTLOG, HC_BATTCFG = 0x02, 0x0A, 0x0B
FLAGS = ["on_batt", "charging", "done", "rgb_on", "lights_cut", "slider_usb", "linked", "clamped"]
STATES = ["none", "battery", "charging", "full", "usb"]


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


def flags_str(f):
    return " ".join(name for i, name in enumerate(FLAGS) if f & (1 << i)) or "-"


def status(h):
    r = xfer(h, HC_CONN)
    age = r[22]
    print(f"vdd          {u16(r, 12)} mV  (raw {u16(r, 14)}, since boot {u16(r, 16)}..{u16(r, 18)} mV)")
    print(f"charger pins CHRG {'low (charging)' if not r[20] & 1 else 'high'}, "
          f"STDBY {'low' if not r[20] & 2 else 'high'}")
    print(f"module 5C    {r[5]}%  (min {r[21]}, last report {'never/stale' if age == 255 else f'{age} s ago'})")
    print(f"flags        {flags_str(r[23])}")
    clamp = u16(r, 26)
    if clamp:
        soc = u16(r, 24)
        state = STATES[r[30]] if r[30] < len(STATES) else r[30]
        print(f"estimate     {'unknown' if soc == 0xFFFF else f'{soc / 100:.2f} %'}  ({state})")
        print(f"regulator    {clamp} mV learned output")
        print(f"led drive    {u16(r, 28) / 10:.1f} % of maximum")
    return clamp != 0


def dump_log(h, out):
    v2 = status_quiet(h)
    rows = []
    first = xfer(h, HC_BATTLOG, [0, 0])
    if v2:
        if first[3] != 2:
            sys.exit(f"unexpected log format {first[3]}")
        count, since = u16(first, 4), u32(first, 8)
        newest = time.time() - since / 1000.0
        for n in range(count):
            r = first if n == 0 else xfer(h, HC_BATTLOG, [n & 0xFF, n >> 8])
            e = r[12:24]
            soc = u16(e, 4)
            row = {"time": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest - (count - 1 - n) * 60)),
                   "vdd_avg": u16(e, 0), "vdd_min": u16(e, 2),
                   "soc": "" if soc == 0xFFFF else f"{soc / 100:.2f}",
                   "led_pm": u16(e, 6), "module_pct": e[8], "rgb_val": e[10], "module_age_s": e[11]}
            row.update({name: (e[9] >> i) & 1 for i, name in enumerate(FLAGS)})
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
                row = {"time": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest - (count - 1 - n) * 60)),
                       "vdd_avg": u16(e, 0), "vdd_min": u16(e, 2),
                       "module_pct": e[4], "rgb_val": e[6], "module_age_s": e[7]}
                row.update({name: (e[5] >> i) & 1 for i, name in enumerate(FLAGS[:7])})
                rows.append(row)
    f = open(out, "w", newline="") if out else sys.stdout
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["time"])
    w.writeheader()
    w.writerows(rows)
    print(f"# {count} entries (log v{2 if v2 else 1}), newest {since / 1000:.0f} s ago", file=sys.stderr)


def status_quiet(h):
    return u16(xfer(h, HC_CONN), 26) != 0


def cfg(h, argv):
    if len(argv) == 2:
        w, c = int(argv[0]), int(argv[1])
        r = xfer(h, HC_BATTCFG, [1, w & 0xFF, w >> 8, c & 0xFF, c >> 8])
    else:
        r = xfer(h, HC_BATTCFG, [0])
    print(f"warn {u16(r, 4)} mV  cut {u16(r, 6)} mV  lights_cut {r[8]}  warned {r[9]}  "
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
