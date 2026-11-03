#!/usr/bin/env python3
"""Press white's keys through the logger's CircuitPython REPL: the presser
built on the logger's QT Py (docs/test-bench.md, "The key presser"), by the
method of presser_repl_check.py: Ctrl-C stops the logger's code.py, the opto
pins are driven from the REPL, Ctrl-D at the end restarts code.py. No write
to CIRCUITPY; the INA228 keeps counting in hardware (rows go missing from
power.csv for about 15 s a run; the REPL's soft reboots did not restart the
charge count, 11-03).

The logger's LaunchAgent holds the serial port: the script pauses it
(launchctl bootout) and puts it back in `finally`; --no-logger skips both.

As wired 11-03: A0 is the yellow channel on (3,14) PgDn, A1 the blue on
(0,13) Delete; both are F19/F20 on the base layers since 02:16 11-03, which
macOS ignores. The dwell is timed on the board's clock (CircuitPython's
time.monotonic_ns, ~1 ms resolution): the actual dwell is reported.

    presser_repl.py pulse A1 100              one press of A1, 100 ms
    presser_repl.py batch A1 50 25 100        50 presses of A1: 25 ms dwell, 100 ms gap
    presser_repl.py batch A1 50 25 100 --hold A0   the same with A0 held throughout (a cross-row chord)
    presser_repl.py hold A0 5000              A0 held for 5 s, then released
"""
import argparse
import os
import subprocess
import sys
import time

import serial
from serial.tools import list_ports

ADAFRUIT = 0x239A
PINS = ("A0", "A1")
LABEL = {"A0": "yellow, (3,14) PgDn/F20", "A1": "blue, (0,13) Delete/F19"}
PLG = "com.jdlien.ak820pro.powerlog"
PLG_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.jdlien.ak820pro.powerlog.plist")
POWER_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "history", "power-bench-2026-10-15", "power.csv")


def log(s):
    print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)


class Repl:
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.1)

    def drain(self, t):
        end, buf = time.time() + t, b""
        while time.time() < end:
            buf += self.s.read(4096)
        return buf

    def cmd(self, line, t=0.4):
        self.s.write(line.encode() + b"\r")
        o = self.drain(t)
        if b"Error" in o or b"Traceback" in o:
            raise SystemExit(f"REPL error on {line!r}: {o!r}")
        return o

    def wait_for(self, marker, t):
        """Read until `marker` appears and the REPL's prompt follows it (the
        line complete), for up to t seconds."""
        end, buf = time.time() + t, b""
        while time.time() < end:
            buf += self.s.read(4096)
            i = buf.find(marker)
            if i >= 0 and b">>>" in buf[i:]:
                return buf
            if b"Traceback" in buf:
                raise SystemExit(f"REPL traceback: {buf!r}")
        raise SystemExit(f"no {marker!r} within {t:.0f} s: {buf[-300:]!r}")

    def enter(self):
        s = self.s
        s.write(b"\x03"); time.sleep(0.3); s.write(b"\x03"); self.drain(0.8)
        s.write(b"\r"); out = self.drain(1.2)
        if b">>>" not in out:
            s.write(b"\r"); out += self.drain(1.5)
        if b">>>" not in out:
            raise SystemExit(f"no REPL prompt: {out[-200:]!r}")
        self.cmd("import board, digitalio, time")
        self.cmd(f"pins = {{n: digitalio.DigitalInOut(getattr(board, n)) for n in {list(PINS)!r}}}")
        self.cmd("_ = [p.switch_to_input(pull=digitalio.Pull.DOWN) for p in pins.values()]")
        # The dwell on the board's clock; the pin back to an input (pull-down) after each press.
        self.cmd("exec('def pulse(k, ms):\\n p = pins[k]\\n t0 = time.monotonic_ns()\\n"
                 " p.switch_to_output(value=True)\\n"
                 " while time.monotonic_ns() - t0 < ms * 1000000:\\n  pass\\n"
                 " p.value = False\\n t1 = time.monotonic_ns()\\n"
                 " p.switch_to_input(pull=digitalio.Pull.DOWN)\\n return (t1 - t0) // 1000\\n')")
        self.cmd("exec('def batch(k, n, dwell, gap):\\n ds = []\\n t0 = time.monotonic_ns()\\n"
                 " for i in range(n):\\n  ds.append(pulse(k, dwell))\\n  time.sleep(gap / 1000)\\n"
                 " t1 = time.monotonic_ns()\\n"
                 " print(\"BATCH\", n, min(ds), max(ds), sum(ds) // n, (t1 - t0) // 1000000)\\n')")
        self.cmd("exec('def hold(k, v):\\n p = pins[k]\\n"
                 " p.switch_to_output(value=True) if v else p.switch_to_input(pull=digitalio.Pull.DOWN)\\n')")

    def leave(self):
        self.s.write(b"\x04"); time.sleep(0.5); self.s.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("op", choices=("pulse", "batch", "hold"))
    ap.add_argument("pin", choices=PINS)
    ap.add_argument("args", nargs="*", type=int)
    ap.add_argument("--hold", choices=PINS, help="a second channel held high throughout (a chord)")
    ap.add_argument("--no-logger", action="store_true", help="do not pause/resume the logger's LaunchAgent")
    a = ap.parse_args()
    if a.hold == a.pin:
        raise SystemExit("--hold must name the other channel")
    port = next((p.device for p in list_ports.comports() if p.vid == ADAFRUIT), None)
    if port is None:
        raise SystemExit("no Adafruit board on USB: is the logger's QT Py plugged in?")
    paused = False
    r = None
    try:
        if not a.no_logger:
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{PLG}"], capture_output=True)
            paused = True
            log("logger paused")
            time.sleep(1.0)
        r = Repl(port)
        r.enter()
        if a.hold:
            r.cmd(f"hold('{a.hold}', 1)")
            log(f"{a.hold} held ({LABEL[a.hold]})")
            time.sleep(0.3)
        if a.op == "pulse":
            ms = a.args[0] if a.args else 100
            out = r.cmd(f"print('DWELL', pulse('{a.pin}', {ms}))", t=ms / 1000 + 0.6)
            got = [l for l in out.decode(errors="replace").splitlines() if l.startswith("DWELL")]
            log(f"{a.pin} ({LABEL[a.pin]}): one press, asked {ms} ms, actual {got[0].split()[1] if got else '?'} us")
        elif a.op == "batch":
            n, dwell, gap = (a.args + [1, 25, 100])[:3]
            r.s.write(f"batch('{a.pin}', {n}, {dwell}, {gap})\r".encode())
            out = r.wait_for(b"BATCH", n * (dwell + gap) / 1000 + 5)
            line = [l for l in out.decode(errors="replace").splitlines() if l.startswith("BATCH")][0].split()
            log(f"{a.pin} ({LABEL[a.pin]}): {line[1]} presses, dwell asked {dwell} ms, actual "
                f"min {line[2]} max {line[3]} mean {line[4]} us, gap {gap} ms, total {line[5]} ms")
            print(f"BATCH pin={a.pin} n={line[1]} dwell_ms={dwell} dwell_min_us={line[2]} "
                  f"dwell_max_us={line[3]} dwell_mean_us={line[4]} gap_ms={gap} total_ms={line[5]}"
                  f"{' hold=' + a.hold if a.hold else ''}", flush=True)
        elif a.op == "hold":
            ms = a.args[0] if a.args else 1000
            r.cmd(f"hold('{a.pin}', 1)")
            log(f"{a.pin} held for {ms} ms")
            time.sleep(ms / 1000)
            r.cmd(f"hold('{a.pin}', 0)")
            log(f"{a.pin} released")
        if a.hold:
            r.cmd(f"hold('{a.hold}', 0)")
            log(f"{a.hold} released")
    finally:
        if r is not None:
            try:
                r.leave()
                log("QT Py soft-rebooted into its logger")
            except Exception as e:  # noqa: BLE001
                log(f"REPL close failed: {e}")
        if paused:
            subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", PLG_PLIST], capture_output=True)
            log("logger back")
            # The QT Py froze three times on 11-03 while the presser was built on it:
            # a new power.csv row within 60 s says the logger is back, not only its agent.
            n0 = os.path.getsize(POWER_CSV) if os.path.exists(POWER_CSV) else -1
            end = time.time() + 60
            while time.time() < end:
                time.sleep(2)
                if os.path.exists(POWER_CSV) and os.path.getsize(POWER_CSV) > n0:
                    log("logger logging again (a new power.csv row)")
                    break
            else:
                log("LOGGER NOT LOGGING: no new power.csv row in 60 s (the QT Py stuck? stop pressing)")
                sys.exit(3)


if __name__ == "__main__":
    main()
