#!/usr/bin/env python3
"""Record the bench power logger (scripts/qtpy/code.py on the QT Py RP2040,
docs/test-bench.md): the INA228 in series on the AK820 pack's + lead and the
MAX17048 across the pack, one row per second, timestamped by the Mac.

    venv/bin/python scripts/power_log.py --out <csv> [--detach] [--serial UID]

Columns: time, epoch, qt_ms (the QT Py's clock), vbus_mv (the pack, at the
INA228), vshunt_uv, current_ma (+ out of the pack, - into it), charge_mah (the
INA228's own count, gap-free between rows; it restarts at 0 only when the QT
Py loses power), temp_c (the INA228's die: the logger board, not the cell; from
10-15), vcell_mv, soc_pct and crate_pct_h (the MAX17048; empty until a pack
powers it).

The INA228 reads -0.064 mA (-0.97 uV) with the harness on and nothing
flowing (10-14); subtract it when the floor matters. The shunt is taken as
15 mohm (marked R015; Adafruit's driver default), unchecked against a known
load yet.

The QT Py repeats its H line every minute, and each one is checked. Until
10-15 it sent one, at start, and the check never ran: that line comes behind
CircuitPython's title-bar escape codes (seen 10-15), which are now stripped,
and it may also go out before the Mac opens the port. A D line of the wrong
length is reported (once a minute), not dropped silently.

Serial only, never HID: the QT Py's boot.py turns its HID off. The port is
found by USB ids, so it survives a replug onto another port. With --detach
it forks off (PPID 1), like trial_guard.py; its pid goes in <csv>.pid and
its notes (start, H and E lines, reconnects) in <csv>.log. During a drain
run it as a LaunchAgent instead (scripts/power_log_agent.sh): a detached
recorder started from a cmux shell still dies when cmux restarts.

One recorder at a time: it takes a lock on <csv> and opens the port
exclusive, since two would each read some of the QT Py's lines and
interleave them. A second one refuses.
"""
import argparse
import csv
import fcntl
import os
import re
import sys
import time

import serial
from serial.tools import list_ports

ADAFRUIT = 0x239A
FIELDS = ["time", "epoch", "qt_ms", "vbus_mv", "vshunt_uv", "current_ma", "charge_mah",
          "temp_c", "vcell_mv", "soc_pct", "crate_pct_h"]
CURRENT_LSB = 5e-6   # must match code.py; checked against its H line
# +1 with the pack on the INA228's Vin+ (the plan). The harness had them the
# other way round from 20:38 to ~20:59 10-15 (-1 then), until JD swapped the
# two + wires at the terminal block. The QT Py's D lines stay raw.
SHUNT_SIGN = 1
# CircuitPython's status bar: OSC title sequences, and the CSI clears around them
ESCAPES = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")
H_MUST = [f"current {CURRENT_LSB:g}A", "temp 7.8125mdegC"]  # what this parser assumes


def say(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def find_port(uid):
    for p in list_ports.comports():
        if p.vid == ADAFRUIT and (uid is None or p.serial_number == uid):
            return p.device
    return None


def conv(f):
    """A D line's fields (ms, vbus, vshunt, current, charge, temp, vcell, soc, crate)."""
    def scale(s, k, nd):
        return f"{int(s) * k:.{nd}f}" if s != "" else ""
    return [f[0], scale(f[1], 195.3125e-3, 3), scale(f[2], SHUNT_SIGN * 78.125e-3, 3),
            scale(f[3], SHUNT_SIGN * CURRENT_LSB * 1e3, 3),
            scale(f[4], SHUNT_SIGN * CURRENT_LSB / 3.6, 6),
            scale(f[5], 7.8125e-3, 2),
            scale(f[6], 78.125e-3, 3), scale(f[7], 1 / 256, 3), scale(f[8], 0.208, 3)]


def detach(note_path):
    if os.fork():
        time.sleep(0.3)
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    log = open(note_path, "a", buffering=1)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--serial", default=None, help="the QT Py's USB serial number (default: the first Adafruit board)")
    ap.add_argument("--detach", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    base = out[:-4] if out.endswith(".csv") else out
    new = not os.path.exists(out)
    if not new:
        with open(out, newline="") as f:
            have = next(csv.reader(f), None)
        if have != FIELDS:
            say(f"{out} has other columns ({have}); start a new file")
            sys.exit(1)
    lock = open(out, "a")   # held for the process's life, across detach's forks
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        say(f"another recorder is writing {out} (pid in {base}.pid); not starting")
        sys.exit(1)
    if a.detach:
        print(f"detaching; pid in {base}.pid, notes in {base}.log", flush=True)
        detach(base + ".log")
    with open(base + ".pid", "w") as f:
        f.write(f"{os.getpid()}\n")
    f = open(out, "a", newline="", buffering=1)
    w = csv.writer(f)
    if new:
        w.writerow(FIELDS)
    say(f"recording to {out}")

    while True:
        dev = find_port(a.serial)
        if not dev:
            time.sleep(2)
            continue
        try:
            s = serial.Serial(dev, 115200, timeout=5, exclusive=True)
            say(f"connected {dev}")
            header, bad, bad_said = None, 0, 0.0
            while True:
                line = ESCAPES.sub("", s.readline().decode(errors="replace")).strip()
                if not line:
                    continue
                kind, _, rest = line.partition(",")
                if kind == "D":
                    t = time.time()
                    fields = rest.split(",")
                    if len(fields) == len(FIELDS) - 2:
                        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)),
                                    f"{t:.2f}"] + conv(fields))
                    else:
                        bad += 1
                        if t - bad_said >= 60:
                            say(f"dropped {bad} D line(s) of {len(fields)} fields, not "
                                f"{len(FIELDS) - 2}: code.py and this script disagree: {line}")
                            bad, bad_said = 0, t
                elif kind == "H":
                    if rest != header:
                        say(f"header: {rest}")
                        header = rest
                    if not all(m in rest for m in H_MUST):
                        say(f"header lacks {[m for m in H_MUST if m not in rest]}: code.py "
                            "and this script disagree, the conversions are wrong; stopping")
                        sys.exit(1)
                elif kind == "E":
                    say(f"logger error: {rest}")
        except (serial.SerialException, OSError) as e:
            say(f"disconnected: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
