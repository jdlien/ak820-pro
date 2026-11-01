#!/usr/bin/env python3
"""The presser's two ends against each other, with no hardware: the board's
scripts/presser/code.py runs in-process under CPython with stand-ins for
CircuitPython's board, digitalio, usb_cdc and the rest, and scripts/presser.py
talks to it through an in-memory serial. Proves the protocol agrees at both
ends, the timing loop, the held-key guard and the error paths; not the GPIO
or the real clock's step (those need the board: `presser.py tap` with an LED
and a resistor from A0 to GND, then the keyboard).

    venv/bin/python scripts/presser_selftest.py
"""
import importlib.util
import os
import sys
import threading
import time
import types
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class Pipe:
    """One direction of bytes with a condition variable."""

    def __init__(self):
        self.q = deque()
        self.cv = threading.Condition()

    def put(self, b):
        with self.cv:
            self.q.extend(b)
            self.cv.notify_all()

    def available(self):
        with self.cv:
            return len(self.q)

    def get(self, n):
        with self.cv:
            out = bytes(self.q.popleft() for _ in range(min(n, len(self.q))))
        return out

    def readline(self, timeout):
        end = time.monotonic() + timeout
        buf = bytearray()
        with self.cv:
            while True:
                while self.q and (not buf or buf[-1] != 10):
                    buf.append(self.q.popleft())
                if buf and buf[-1] == 10:
                    return bytes(buf)
                rem = end - time.monotonic()
                if rem <= 0:
                    return bytes(buf)
                self.cv.wait(rem)


to_board, to_mac = Pipe(), Pipe()


class BoardSerial:          # usb_cdc.data as code.py uses it
    timeout = 0
    write_timeout = 0
    connected = True

    @property
    def in_waiting(self):
        return to_board.available()

    def read(self, n):
        return to_board.get(n)

    def write(self, b):
        to_mac.put(b)


class MacSerial:            # the pyserial subset presser.Presser uses
    def __init__(self):
        self.timeout = 2.0

    def write(self, b):
        to_board.put(b)

    def readline(self):
        return to_mac.readline(self.timeout)

    def reset_input_buffer(self):
        to_mac.get(to_mac.available())

    def close(self):
        pass


class Pin:
    def __init__(self, name):
        self.name, self.value = name, None

    def switch_to_output(self, value=False):
        self.value = value


written = []


def stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


stub("board", A0="A0", A1="A1", NEOPIXEL="NEOPIXEL", NEOPIXEL_POWER="NEOPIXEL_POWER", board_id="selftest")
stub("digitalio", DigitalInOut=Pin)
stub("microcontroller", cpu=types.SimpleNamespace(uid=bytes(range(8))))
stub("supervisor", runtime=types.SimpleNamespace(autoreload=True))
stub("usb_cdc", data=BoardSerial())
stub("neopixel_write", neopixel_write=lambda pin, buf: written.append(bytes(buf)))

spec = importlib.util.spec_from_file_location("presser_code", os.path.join(HERE, "presser", "code.py"))
code = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code)
import presser  # noqa: E402

stop = threading.Event()


def board_loop():            # code.main(), minus the forever
    code.led_idle()
    state = None
    while not stop.is_set():
        state = code.service(state)
        time.sleep(0.001)


threading.Thread(target=board_loop, daemon=True).start()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


p = presser.Presser(transport=MacSerial())
v = p.version()
check(v == {"protocol": 1, "board": "selftest", "uid": "0001020304050607", "channels": 2}, f"version {v}")
s = p.status()
check(s["A"] is False and s["B"] is False and s["presses_A"] == 0, f"status {s}")
check(code.pins[0].value is False and code.pins[1].value is False, "both channels released at start")
check(written and written[-1] == bytes((3, 0, 0)), f"idle light GRB {written[-1] if written else None}")

r = p.press("A", 5)
d = (r.t_open_us - r.t_close_us) / 1000
check(r.ch == "A" and r.i == 0 and 4.5 <= d <= 7.0, f"one 5 ms press on A: {d:.2f} ms actual")
check(code.pins[0].value is False, "released after the press")
check(p.status()["presses_A"] == 1, "the board counted it")

t0 = time.monotonic()
out = p.batch("B", 3, 4, 5)
el = (time.monotonic() - t0) * 1000
check(len(out) == 5 and [x.i for x in out] == list(range(5)) and all(x.ch == "B" for x in out),
      f"a batch of 5 on B, {el:.0f} ms (5 x 3 + 4 x 4 = 31 asked)")
gaps = [(out[i + 1].t_close_us - out[i].t_open_us) / 1000 for i in range(4)]
check(all(3.8 <= g <= 6.5 for g in gaps), f"gaps {['%.2f' % g for g in gaps]} ms")

n_seen = []
out = p.batch("A", 2, 3, 50, on_press=lambda pr: n_seen.append(pr.i), stop=lambda: len(n_seen) >= 3)
check(3 <= len(out) <= 12 and len(n_seen) == len(out),
      f"stop() ended a 50-press batch after {len(out)} (a few presses' lag here, where the host is a thread)")

t = p.hold("B")
check(code.pins[1].value is True and code.held[1], f"hold B at {t} us")
check(written[-1] == bytes((10, 30, 0)), "amber while held")
try:
    p.press("B", 5)
    check(False, "a press on a held channel refused")
except presser.PresserError as e:
    check("held" in str(e), f"a press on a held channel refused: {e}")
p.release("B")
check(code.pins[1].value is False and not code.held[1], "release B")

for bad, why in (("P,C,5", "channel"), ("P,A,0.01", "dwell"), ("P,A,5,5,0", "n"), ("Q", "unknown"), ("L,300", "L")):
    try:
        p.cmd(bad, "?")
        check(False, f"{bad!r} refused")
    except presser.PresserError as e:
        check(True, f"{bad!r} refused: {e}")

check(p.set_led(1) == 1 and written[-1] == bytes((1, 0, 0)), "L,1 sets the idle light")

sy = p.sync()
expect = time.time() - time.monotonic_ns() / 1e9
check(abs(sy.offset_s - expect) < 0.05 and sy.unc_s < 0.05, f"sync offset within 50 ms of the truth, ±{sy.unc_s * 1000:.2f} ms")
k = p.key("A")
(t_down, t_up, dw), = k.batch(5, 1, 1)
check(abs(t_down - time.time()) < 1 and 4.5 <= dw <= 7, f"PresserKey gives Mac-clock stamps, dwell {dw:.2f}")
k.finish()
print("  note:", k.clock_note())

p.hold("A")
BoardSerial.connected = False
time.sleep(1.3)
check(code.pins[0].value is False and not code.held[0], "a held key released 1 s after the port closed")
BoardSerial.connected = True

stop.set()
print("FAILED" if fails else "all passed", f"({fails} failures)" if fails else "")
sys.exit(1 if fails else 0)
