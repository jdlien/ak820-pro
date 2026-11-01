#!/usr/bin/env python3
"""The key presser, from the Mac (docs/test-bench.md, "The key presser"): an
RP2040 board running scripts/presser/code.py drives two PC817C optocouplers
wired across two of the keyboard's switches, A at (0,13) and B low on the
board, and stamps every closure and release on its own clock.

    venv/bin/python scripts/presser.py status
    venv/bin/python scripts/presser.py tap [A|B] [ms]          one press (default A, 40 ms)
    venv/bin/python scripts/presser.py hold A|B | release A|B
    venv/bin/python scripts/presser.py batch A|B DWELL GAP N [--csv <out>]   ms, ms, presses
    venv/bin/python scripts/presser.py sync                    the board's clock against the Mac's
    venv/bin/python scripts/presser.py led LEVEL               the idle light, 0-255 (default 3)
    venv/bin/python scripts/presser.py find                    which port, and the board's identity

`scripts/press` runs it from anywhere (`press tap`, `press hold B`).

In a script: `with Presser() as p:` then `p.press("A", 15)`, `p.batch("A", 15,
40, 1000, on_press=...)`, `p.hold("B")`, `p.release("B")`, `p.sync()`.
`p.key("A")` and `RelayKey()` (the old rig, relay 1 of the bench's USB relay)
share one small interface, `press(dwell_ms)` / `batch(dwell_ms, gap_ms, n)` /
`hold()` / `release()`, each press reported as (t_down, t_up, dwell_ms) on
the Mac's clock, so keydrop_test.py and relay_press_test.py take either.

The port: the board enumerates as pid.codes 0x1209:0x0001 "AK820 key presser"
(its boot.py), never as an Adafruit board, so the bench's power recorder
cannot take it for the logger's QT Py; of its two serial ports the one that
answers `V` is the data port. The protocol is in scripts/presser/code.py.

The clock: a press's stamps are on the board's clock (microseconds since its
reset). `sync()` measures the offset to the Mac's epoch by round trip, the
shortest of several, and reports the uncertainty (half that round trip) and,
against an earlier sync, the drift; keydrop_test.py prints both beside its
latencies, and differences inside the bound are not claimed.
"""
import argparse
import csv
import sys
import time
from collections import namedtuple

import serial
from serial.tools import list_ports

VID, PID, PRODUCT = 0x1209, 0x0001, "AK820 key presser"
CHANNELS = ("A", "B")
Press = namedtuple("Press", "ch i t_close_us t_open_us")   # the board's clock
Sync = namedtuple("Sync", "offset_s unc_s rtt_ms when")     # mac = offset_s + t_us / 1e6


class PresserError(Exception):
    pass


def channel(s):
    s = str(s).strip().upper()
    if s in CHANNELS:
        return s
    if s in ("0", "1"):
        return CHANNELS[int(s)]
    raise PresserError(f"channel must be A or B, not {s!r}")


def candidate_ports():
    return [p.device for p in list_ports.comports()
            if p.vid == VID and p.pid == PID and (p.product in (None, PRODUCT))]


def probe(device, wait_s=0.6):
    """The V line from a port, or None: the console port never answers."""
    try:
        with serial.Serial(device, 115200, timeout=0.1, exclusive=True) as s:
            s.reset_input_buffer()
            s.write(b"V\n")
            t_end = time.monotonic() + wait_s
            while time.monotonic() < t_end:
                line = s.readline().decode(errors="replace").strip()
                if line.startswith("V,ak820-presser,"):
                    return line
    except (serial.SerialException, OSError):
        pass
    return None


def find_port():
    """The data port of the presser, by probing; None if no board answers."""
    for dev in candidate_ports():
        if probe(dev):
            return dev
    return None


class Presser:
    def __init__(self, port=None, timeout_s=2.0, transport=None):
        if transport is not None:   # presser_selftest.py: the board's code in-process
            self.port, self.s = "selftest", transport
        else:
            self.port = port or find_port()
            if not self.port:
                raise PresserError("no key presser answers (is the board on USB, with its boot.py "
                                   "and code.py? `presser.py find`)")
            self.s = serial.Serial(self.port, 115200, timeout=timeout_s, exclusive=True)
        self.s.reset_input_buffer()
        self.last_sync = None

    def close(self):
        self.s.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # The wire
    def _send(self, line):
        self.s.write((line + "\n").encode())

    def _line(self, timeout_s=None):
        if timeout_s is not None:
            old, self.s.timeout = self.s.timeout, timeout_s
        try:
            raw = self.s.readline()
        finally:
            if timeout_s is not None:
                self.s.timeout = old
        if not raw:
            raise PresserError("the presser did not answer")
        line = raw.decode(errors="replace").strip()
        if line.startswith("E,"):
            raise PresserError(line[2:])
        return line.split(",")

    def cmd(self, line, expect, timeout_s=None):
        self._send(line)
        f = self._line(timeout_s)
        if f[0] != expect:
            raise PresserError(f"expected {expect}, got {','.join(f)}")
        return f

    # Commands
    def version(self):
        f = self.cmd("V", "V")
        return {"protocol": int(f[2]), "board": f[3], "uid": f[4], "channels": int(f[5])}

    def clock_us(self):
        return int(self.cmd("T", "T")[1])

    def status(self):
        f = self.cmd("S", "S")
        return {"t_us": int(f[1]), "A": bool(int(f[2])), "B": bool(int(f[3])),
                "presses_A": int(f[4]), "presses_B": int(f[5])}

    def sync(self, n=7):
        """The board's clock against the Mac's, from the shortest of n round trips."""
        best = None
        for _ in range(n):
            t0 = time.time()
            t_us = self.clock_us()
            t1 = time.time()
            rtt = t1 - t0
            if best is None or rtt < best[0]:
                best = (rtt, (t0 + t1) / 2 - t_us / 1e6)
        self.last_sync = Sync(best[1], best[0] / 2, best[0] * 1000, time.time())
        return self.last_sync

    def mac_time(self, t_us):
        if self.last_sync is None:
            self.sync()
        return self.last_sync.offset_s + t_us / 1e6

    def press(self, ch, dwell_ms):
        return self.batch(ch, dwell_ms, 1.0, 1)[0]

    def batch(self, ch, dwell_ms, gap_ms, n, on_press=None, stop=None):
        """n presses timed on the board; each K line as it comes, through
        on_press(Press) if given; stop() true between presses ends it early."""
        ch = channel(ch)
        self._send(f"P,{ch},{dwell_ms:.2f},{gap_ms:.2f},{n}")
        out = []
        per_press_s = (dwell_ms + gap_ms) / 1000 + 2.0
        stopped = False
        while True:
            f = self._line(per_press_s)
            if f[0] == "K":
                p = Press(f[1], int(f[2]), int(f[3]), int(f[4]))
                out.append(p)
                if on_press:
                    on_press(p)
                if stop and not stopped and stop():
                    self._send("X")
                    stopped = True
            elif f[0] == "B":
                done, asked = int(f[2]), int(f[3])
                if done != len(out):
                    raise PresserError(f"the board counted {done} presses, this end {len(out)}")
                return out
            else:
                raise PresserError(f"unexpected {','.join(f)} during a batch")

    def hold(self, ch):
        return int(self.cmd(f"H,{channel(ch)}", "H")[2])

    def release(self, ch):
        return int(self.cmd(f"R,{channel(ch)}", "R")[2])

    def set_led(self, level):
        return int(self.cmd(f"L,{int(level)}", "L")[1])

    def key(self, ch):
        return PresserKey(self, ch)


class PresserKey:
    """One channel with the tests' key interface: times on the Mac's clock."""

    def __init__(self, presser, ch):
        self.p, self.ch = presser, channel(ch)
        self.name = f"presser {self.ch}"
        self.sync_start = self.p.sync()
        self.sync_end = None

    def _mac(self, press):
        return (self.p.mac_time(press.t_close_us), self.p.mac_time(press.t_open_us),
                (press.t_open_us - press.t_close_us) / 1000)

    def press(self, dwell_ms):
        return self._mac(self.p.press(self.ch, dwell_ms))

    def batch(self, dwell_ms, gap_ms, n, on_press=None):
        out = []
        for press in self.p.batch(self.ch, dwell_ms, gap_ms, n):
            r = self._mac(press)
            out.append(r)
            if on_press:
                on_press(r)
        return out

    def hold(self):
        self.p.hold(self.ch)

    def release(self):
        self.p.release(self.ch)

    def finish(self):
        """A second sync; the drift since the first bounds any latency claim."""
        self.sync_end = self.p.sync()
        return self.sync_end

    def clock_note(self):
        a, b = self.sync_start, self.sync_end
        note = f"clock offset ±{a.unc_s * 1000:.2f} ms at the start"
        if b:
            note += (f", ±{b.unc_s * 1000:.2f} at the end, drift {(b.offset_s - a.offset_s) * 1000:+.2f} ms"
                     f" over {b.when - a.when:.0f} s")
        return note

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.p.close()


class RelayKey:
    """The old rig: relay 1 of the bench's USB relay across one key, timed by
    the Mac (its command times are the stamps; the contact follows within
    ~5 ms). Relay 2, the keyboard's 5 V, is never touched."""
    VID, PID = 0x16C0, 0x05DF

    def __init__(self):
        import hid
        devs = hid.enumerate(self.VID, self.PID)
        if len(devs) != 1:
            raise PresserError(f"expected one USB relay, found {len(devs)}")
        self.dev = hid.Device(path=devs[0]["path"])
        self.name = "relay 1"
        if self.state() & 1:
            raise PresserError("relay 1 is already on (the key is held): `relay off key` releases it")
        self.relay2 = self.state() & 2

    def state(self):
        return self.dev.get_feature_report(0, 9)[8]

    def _set(self, on):
        self.dev.send_feature_report(bytes([0, 0xFF if on else 0xFD, 1, 0, 0, 0, 0, 0, 0]))

    def press(self, dwell_ms):
        t0 = time.time()
        self._set(True)
        time.sleep(dwell_ms / 1000)
        self._set(False)
        t1 = time.time()
        return (t0, t1, (t1 - t0) * 1000)

    def batch(self, dwell_ms, gap_ms, n, on_press=None):
        out = []
        for i in range(n):
            r = self.press(dwell_ms)
            out.append(r)
            if on_press:
                on_press(r)
            if i + 1 < n:
                time.sleep(gap_ms / 1000)
        return out

    def hold(self):
        self._set(True)

    def release(self):
        self._set(False)

    def finish(self):
        return None

    def clock_note(self):
        s = self.state()
        return "the relay's command times" + (
            f"; ⚠️ relay state changed: relay 1 {'on' if s & 1 else 'off'}, relay 2 "
            f"{'on' if s & 2 else 'off'}" if s & 1 or (s & 2) != self.relay2 else "")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dev.close()


def open_key(presser_ch):
    """The tests' choice: a presser channel ("A"/"B") or, with None, relay 1."""
    return Presser().key(presser_ch) if presser_ch else RelayKey()


def main(argv):
    ap = argparse.ArgumentParser(description="the key presser")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["status", "tap", "hold", "release", "batch", "sync", "led", "find"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", default=None)
    ap.add_argument("--csv", default=None, help="batch: append each press's stamps here")
    a = ap.parse_args(argv)
    if a.cmd == "find":
        for dev in candidate_ports():
            v = probe(dev)
            print(f"{dev}: {v or 'no answer (the console port)'}")
        if not candidate_ports():
            sys.exit("no presser on USB (vid 1209, pid 0001)")
        return
    with Presser(a.port) as p:
        if a.cmd == "status":
            v, s = p.version(), p.status()
            print(f"{p.port}: {v['board']} uid {v['uid']}, protocol {v['protocol']}; "
                  f"A {'DOWN' if s['A'] else 'up'} ({s['presses_A']} presses), "
                  f"B {'DOWN' if s['B'] else 'up'} ({s['presses_B']} presses), "
                  f"clock {s['t_us'] / 1e6:.3f} s")
        elif a.cmd == "tap":
            ch = channel(a.args[0]) if a.args else "A"
            ms = float(a.args[1]) if len(a.args) > 1 else 40.0
            r = p.press(ch, ms)
            print(f"{ch} pressed {(r.t_open_us - r.t_close_us) / 1000:.2f} ms (asked {ms:g})")
        elif a.cmd in ("hold", "release"):
            if not a.args:
                sys.exit(f"{a.cmd} A|B")
            ch = channel(a.args[0])
            t = p.hold(ch) if a.cmd == "hold" else p.release(ch)
            print(f"{ch} {'held' if a.cmd == 'hold' else 'released'} at {t / 1e6:.3f} s")
        elif a.cmd == "batch":
            if len(a.args) != 4:
                sys.exit("batch A|B DWELL_MS GAP_MS N")
            ch, dwell, gap, n = channel(a.args[0]), float(a.args[1]), float(a.args[2]), int(a.args[3])
            s0 = p.sync()
            w = None
            if a.csv:
                f = open(a.csv, "a", newline="")
                w = csv.writer(f)
                if f.tell() == 0:
                    w.writerow(["ch", "i", "t_close_us", "t_open_us", "mac_close", "dwell_ms"])
            dwells = []

            def each(pr):
                dwells.append((pr.t_open_us - pr.t_close_us) / 1000)
                if w:
                    w.writerow([pr.ch, pr.i, pr.t_close_us, pr.t_open_us,
                                f"{p.mac_time(pr.t_close_us):.4f}", f"{dwells[-1]:.3f}"])

            out = p.batch(ch, dwell, gap, n, on_press=each)
            s1 = p.sync()
            print(f"{len(out)} presses on {ch}: dwell asked {dwell:g} ms, actual min {min(dwells):.2f} "
                  f"mean {sum(dwells) / len(dwells):.2f} max {max(dwells):.2f}; "
                  f"clock offset ±{s0.unc_s * 1000:.2f} ms, drift {(s1.offset_s - s0.offset_s) * 1000:+.2f} ms")
        elif a.cmd == "sync":
            s = p.sync()
            print(f"offset {s.offset_s:.6f} s (mac = offset + board_us/1e6), ±{s.unc_s * 1000:.2f} ms "
                  f"(round trip {s.rtt_ms:.2f} ms)")
        elif a.cmd == "led":
            if not a.args:
                sys.exit("led 0..255")
            print(f"idle light {p.set_led(int(a.args[0]))}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PresserError as e:
        sys.exit(str(e))
