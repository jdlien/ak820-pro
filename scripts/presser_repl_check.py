#!/usr/bin/env python3
"""The presser's contact check while its QT Py still runs the power logger
(docs/test-bench.md, "The key presser"; first passed 02:13 11-03).

Run it through `presser_repl_check.sh`, which pauses the daemon and the
logger's LaunchAgent, puts white's data line on, and undoes all three after.

- **No write to CIRCUITPY.** The pins are driven from the logger's own
  CircuitPython REPL: Ctrl-C stops its code.py, and Ctrl-D at the end
  restarts it. The INA228 keeps counting in hardware throughout, so the
  drain's charge count runs on (rows go missing for about 15 s).
- **Silent presses.** For the run, (0,13) and (3,14) are F19/F20 on both
  base layers, which macOS ignores. Whatever they held before goes back in
  `finally` (F19/F20 themselves since 02:16 11-03).
- **The evidence is white's own count** (`key_presses`, health page 2).
  So each pulse is one key or none, whatever the host does with it.
- **One channel at a time.** The idle pin stays an input, so a short between
  the channels shows as two presses.

As wired 11-03, A0 is the yellow channel on (3,14), PgDn, and A1 the blue on
(0,13), Delete. That is crossed against the plan's channel A at (0,13).
Since 11-14 A0's plug is out and (3,14) has a switch again, so A0 reads 0
of 5 until JD swaps the plug back.

    scripts/presser_repl_check.sh            # A0 and A1, five pulses each
    scripts/presser_repl_check.sh --scan     # every free header pin once
"""
import sys
import time

import serial
from serial.tools import list_ports

sys.path.insert(0, "hostagent")
import ak820health as hp  # noqa: E402
import ak820keymap as km  # noqa: E402

ADAFRUIT = 0x239A
POS = ((0, 13), (3, 14))
SILENT = {(0, 13): 0x6E, (3, 14): 0x6F}   # KC_F19, KC_F20
LABEL = {"A0": "yellow, (3,14) PgDn", "A1": "blue, (0,13) Delete"}
FREE = ["A0", "A1", "A2", "A3", "SDA", "SCL", "TX", "RX", "SCK", "MISO", "MOSI"]


def log(s):
    print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)


def main():
    scan = "--scan" in sys.argv
    seq = FREE if scan else ["A0"] * 5 + ["A1"] * 5
    port = next((p.device for p in list_ports.comports() if p.vid == ADAFRUIT), None)
    if port is None:
        raise SystemExit("no Adafruit board on USB: is the logger's QT Py plugged in?")
    h = km.open_device()

    def getkc(l, r, c):
        rep = km.xfer(h, [0x04, l, r, c])
        return rep[4] << 8 | rep[5]

    def setkc(l, r, c, kc):
        km.xfer(h, [0x05, l, r, c, kc >> 8, kc & 0xFF])

    def presses():
        return hp.read_stalls(h)["key_presses"]

    orig = {(l, r, c): getkc(l, r, c) for (r, c) in POS for l in (0, 2)}
    s = None
    try:
        for (l, r, c) in orig:
            setkc(l, r, c, SILENT[(r, c)])
        s = serial.Serial(port, 115200, timeout=0.1)

        def drain(t):
            end, buf = time.time() + t, b""
            while time.time() < end:
                buf += s.read(4096)
            return buf

        def repl(line, t=0.4):
            s.write(line.encode() + b"\r")
            o = drain(t)
            if b"Error" in o or b"Traceback" in o:
                raise SystemExit(f"REPL error on {line!r}: {o!r}")
            return o

        s.write(b"\x03"); time.sleep(0.3); s.write(b"\x03"); drain(0.8)
        s.write(b"\r"); out = drain(1.2)
        if b">>>" not in out:
            s.write(b"\r"); out += drain(1.5)
        if b">>>" not in out:
            raise SystemExit(f"no REPL prompt from {port}: {out[-200:]!r}")
        names = sorted(set(seq))
        repl("import board, digitalio, time")
        repl(f"pins = {{n: digitalio.DigitalInOut(getattr(board, n)) for n in {names!r}}}")
        repl("_ = [p.switch_to_input(pull=digitalio.Pull.DOWN) for p in pins.values()]")
        repl("exec('def pulse(k, ms):\\n p = pins[k]\\n p.switch_to_output(value=True)\\n"
             " time.sleep(ms / 1000)\\n p.value = False\\n p.switch_to_input(pull=digitalio.Pull.DOWN)\\n')")
        c0 = presses(); time.sleep(2.0); c1 = presses()
        log(f"idle 2 s: {c1 - c0:+d} (anything but 0 is a stuck or phantom key, or someone typing)")
        got = []
        for n in seq:
            before = presses()
            repl(f"pulse('{n}', 100)", t=0.5)
            time.sleep(0.4)
            got.append((n, presses() - before))
            log(f"{n} ({LABEL.get(n, 'not wired')}): {got[-1][1]:+d}")
        log("RESULT " + " ".join(f"{n}:{d:+d}" for n, d in got)
            + "  (1 = a press; 0 = none: the plug not seated, the opto's pins 3/4 reversed,"
              " or an open LED side; 2 = the channels joined)")
    finally:
        if s is not None:
            s.write(b"\x04"); time.sleep(0.5); s.close()
            log("QT Py soft-rebooted into its logger")
        for (l, r, c), kc in orig.items():
            setkc(l, r, c, kc)
        back = {k: getkc(*k) for k in orig}
        log("keymap restored" if back == orig else f"KEYMAP RESTORE MISMATCH: {back}")
        h.close()


if __name__ == "__main__":
    main()
