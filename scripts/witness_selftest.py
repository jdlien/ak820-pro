#!/usr/bin/env python3
"""The witness's two ends against each other, with no hardware: the presser
board's scripts/presser/code.py and its witness.py run in-process under CPython
with stand-ins for CircuitPython's board, rp2pio and the rest, and
scripts/witness.py talks to them through an in-memory serial. The fake PIO
hands the board a synthetic sample stream, so the test proves the PIO
program's encodings, the word packing and its decode, the base64 transfer and
the CRC, the pulse and marker arithmetic, the error paths and the trigger
timeout; not the sampling itself (that needs the board and a signal: the
plan's qualification).

    venv/bin/python scripts/witness_selftest.py
"""
import binascii
import importlib.util
import os
import struct
import sys
import threading
import time
import types
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "presser"))   # code.py's `import witness`

SYS_HZ = 125_000_000


class Pipe:
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
            return bytes(self.q.popleft() for _ in range(min(n, len(self.q))))

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


class BoardSerial:
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


class MacSerial:
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


LEVELS_NOW = 0b0101


class Pin:
    def __init__(self, pin):
        self.pin, self.value = pin, None

    def switch_to_output(self, value=False):
        self.value = value

    def switch_to_input(self, pull=None):
        self.value = bool((LEVELS_NOW >> PINS.index(self.pin)) & 1)

    def deinit(self):
        pass


# The synthetic signal ------------------------------------------------------

def pack(samples_per_line, n):
    """samples_per_line: n lists of 0/1, equal length -> bytes as the PIO packs
    them (in_shift_right: the first sample in a word's low n bits)."""
    per = 32 // n
    total = len(samples_per_line[0])
    out = bytearray()
    for w0 in range(0, total, per):
        w = 0
        for k in range(per):
            if w0 + k >= total:
                break
            v = 0
            for i in range(n):
                v |= samples_per_line[i][w0 + k] << i
            w |= v << (k * n)
        out += struct.pack("<I", w)
    return bytes(out)


SLOT = 1600                         # samples at 31.25 MHz = 51.2 us


def four_line_pattern(total=16000):
    col = [1] * total            # active low: the LED's on-time is the low pulse
    row = [0] * total
    marker = [0] * total
    idle = [0] * total
    for k in range(total // SLOT):
        s = k * SLOT
        for j in range(10, 1510):      # not at the slot's first sample: a pulse there reads as cut
            row[s + j] = 1
        if k != 5:
            for j in range(7):
                col[s + 100 + j] = 0
    for j in range(3 * SLOT + 50, 6 * SLOT + 50):
        marker[j] = 1
    return [col, row, marker, idle]


def one_line_pattern(total=3200):
    col = [1] * total
    for s in (100, 1000, 2000):
        col[s] = 0                       # one-tick glitches
    for j in range(1500, 1526):
        col[j] = 0                       # a 26-sample pulse (208 ns at 125 MHz)
    return [col]


PATTERN = {"n": 4, "data": None, "hang": False, "stall": False}


class FakeStateMachine:
    made = []

    def __init__(self, program, frequency, **kw):
        self.program, self.kw = list(program), kw
        self.frequency = frequency
        self.reading = False
        self.rxstall = False
        self.view = None
        self.made.append(self)
        if "fifo_type" in kw:
            raise TypeError("fifo_type unsupported here: the fallback path")

    def stop(self):
        pass

    def clear_rxfifo(self):
        pass

    def background_read(self, once=None):
        self.view = once
        self.reading = True

    def restart(self):
        if PATTERN["hang"]:
            return
        data = PATTERN["data"]
        words = len(self.view)
        self.view[:] = memoryview(data)[:words * 4].cast("I")
        self.rxstall = PATTERN["stall"]
        self.reading = False

    def deinit(self):
        pass


written = []


def stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


SDA, SCL, A3, A2 = object(), object(), object(), object()
PINS = [SDA, SCL, A3, A2]
stub("board", A0="A0", A1="A1", SDA=SDA, SCL=SCL, A3=A3, A2=A2, NEOPIXEL="NEOPIXEL",
     NEOPIXEL_POWER="NEOPIXEL_POWER", board_id="selftest")
stub("digitalio", DigitalInOut=Pin)
stub("microcontroller", cpu=types.SimpleNamespace(uid=bytes(range(8)), frequency=SYS_HZ),
     pin=types.SimpleNamespace(GPIO24=SDA))
stub("supervisor", runtime=types.SimpleNamespace(autoreload=True))
stub("usb_cdc", data=BoardSerial())
stub("neopixel_write", neopixel_write=lambda pin, buf: written.append(bytes(buf)))
stub("rp2pio", StateMachine=FakeStateMachine)

spec = importlib.util.spec_from_file_location("presser_code", os.path.join(HERE, "presser", "code.py"))
code = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code)
import presser   # noqa: E402
# code.py imported the board's witness.py under the name "witness"; the Mac's
# scripts/witness.py is loaded under another name so the two never collide.
spec = importlib.util.spec_from_file_location("mac_witness", os.path.join(HERE, "witness.py"))
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)
check_board = code.witness is not None and hasattr(code.witness, "program")

stop = threading.Event()


def board_loop():
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
check(check_board, "code.py imported the board's witness module")
check(p.version()["protocol"] == 1, "the presser still answers V with the witness aboard")
inf = witness.info(p)
check(inf["ready"] and inf["pins"] == "SDA/SCL/A3/A2" and inf["sys_hz"] == SYS_HZ and inf["max_words"] >= 4096,
      f"W,V: {inf}")
check(witness.levels(p) == LEVELS_NOW, "W,P reads the four lines")

# 1. Four lines at a quarter rate: the plan's hold-off picture.
lines4 = four_line_pattern()
PATTERN.update(n=4, data=pack(lines4, 4), hang=False, stall=False)
meta, raw = witness.capture(p, 4, SYS_HZ // 4, 2000, "N", 100)
check(meta["hz"] == SYS_HZ // 4 and meta["words"] == 2000 and meta["stall"] == 0 and meta["crc_checked"],
      f"W,C reply {meta}")
check(raw == PATTERN["data"], "the capture arrived intact through base64 and the CRC")
sm = FakeStateMachine.made[-1]
check(sm.program == [0x4004] and sm.kw["wrap_target"] == 0 and sm.kw["wrap"] == 0, f"untriggered program {sm.program}")
rep, trans, initial = witness.analyze(raw, meta, {}, marker=2, slot_us=51.2)
ns = 1e9 / meta["hz"]
l0, l1, l2, l3 = rep["line"]
check(l0["pulses"] == 9 and l0["width"]["min_samples"] == 7 and l0["width"]["max_samples"] == 7
      and abs(l0["width"]["median_ns"] - 7 * ns) < 0.01, f"column: 9 low pulses of 7 samples ({l0['width']})")
check(l0["periods_in_slots"] == {"1": 7, "2": 1} and l0["off_grid"] == 0, f"column periods in slots {l0['periods_in_slots']}")
check(abs(l0["longest_gap"]["ns"] - (2 * SLOT - 7) * ns) < 0.01 and l0["longest_gap"]["after_pulse"] == 4,
      f"the skipped slot is the longest gap: {l0['longest_gap']}")
check(l1["pulses"] == 10 and l1["width"]["min_samples"] == 1500 and not l1["cut_first"] and not l1["cut_last"],
      f"mux row: 10 high pulses of 1500 samples")
check(l2["pulses"] == 1 and l2["width"]["min_samples"] == 3 * SLOT, "marker: one interval of three slots")
check(l3["pulses"] == 0 and l3["transitions"] == 0, "the idle line is silent")
iv = rep["marker"]["intervals"]
check(len(iv) == 1 and abs(iv[0]["length_us"] - 3 * SLOT * ns / 1e3) < 0.001, f"marker interval {iv[0]['length_us']} us")
ins = iv[0]["inside"]
check(ins["0"]["pulses"] == 2 and ins["0"]["straddling"] == 0, f"column pulses inside the marker: {ins['0']}")
check(ins["1"]["pulses"] == 2 and ins["1"]["straddling"] == 2, f"mux-row pulses inside the marker: {ins['1']}")
check(abs(ins["0"]["first_after_start_us"] - 50 * ns / 1e3) < 0.001
      and abs(ins["0"]["first_pulse_after_us"] - 50 * ns / 1e3) < 0.001, "the column's offsets from the marker's edges")
edges = os.path.join(os.environ.get("TMPDIR", "/tmp"), "witness-selftest-edges.csv")
witness.write_edges(edges, trans, initial, meta["hz"])
check(sum(1 for _ in open(edges)) == 1 + 4 + sum(len(t) for t in trans), "the edges CSV has every transition")

# 2. One line at the full rate: the glitch test's one-sample pulses.
lines1 = one_line_pattern()
PATTERN.update(n=1, data=pack(lines1, 1))
meta, raw = witness.capture(p, 1, 0, 100, "R2", 50)
sm = FakeStateMachine.made[-1]
check(sm.program == [0x2022, 0x20A2, 0x4001] and sm.kw["wrap_target"] == 2 and sm.kw["wrap"] == 2,
      f"rising-edge trigger on line 2: {[hex(x) for x in sm.program]}")
check(meta["hz"] == SYS_HZ and meta["trig"] == "R2", f"full rate and the trigger echoed: {meta}")
rep, _, _ = witness.analyze(raw, meta, {0: 0})
l0 = rep["line"][0]
check(l0["pulses"] == 4 and l0["width"]["min_samples"] == 1 and l0["width"]["max_samples"] == 26
      and abs(l0["width"]["min_ns"] - 8.0) < 0.01 and abs(l0["width"]["max_ns"] - 208.0) < 0.01,
      f"one-tick glitches and a 208 ns pulse at 8 ns a sample: {l0['width']}")
meta, raw = witness.capture(p, 1, 0, 100, "F0", 50)
sm = FakeStateMachine.made[-1]
check(sm.program == [0x20A0, 0x2020, 0x4001], f"falling-edge trigger on line 0: {[hex(x) for x in sm.program]}")

# 3. Two lines, a stall reported, a truncated pulse at each end.
two = [[0] * 64, [1] * 64]
for j in range(40, 50):
    two[0][j] = 1
two[1][0:5] = [0] * 5
two[1][60:64] = [0] * 4
PATTERN.update(n=2, data=pack(two, 2), stall=True)
meta, raw = witness.capture(p, 2, SYS_HZ // 2, 4, "N", 10)
check(meta["stall"] == 1, "the FIFO stall flag comes through")
rep, _, _ = witness.analyze(raw, meta, {0: 1, 1: 0})
check(rep["stall"] == 1 and rep["line"][0]["pulses"] == 1 and rep["line"][0]["width"]["min_samples"] == 10,
      "two-line packing decodes")
check(rep["line"][1]["pulses"] == 0 and rep["line"][1]["cut_first"] and rep["line"][1]["cut_last"],
      "pulses cut by the capture's edges are counted apart, not as pulses")
PATTERN["stall"] = False

# 4. Errors and the timeout.
for bad in ("W,C,3,0,10,N,10", "W,C,1,0,0,N,10", "W,C,1,0,10,R9,10", "W,C,1,0,10,N,99999", "W,C,1,999999999,10,N,1", "W,Q"):
    try:
        p.cmd(bad, "W")
        check(False, f"{bad!r} refused")
    except presser.PresserError as e:
        check(True, f"{bad!r} refused: {e}")
PATTERN["hang"] = True
t0 = time.monotonic()
try:
    witness.capture(p, 1, 0, 10, "R1", 20)
    check(False, "a trigger that never comes times out")
except presser.PresserError as e:
    dt = time.monotonic() - t0
    check("timeout" in str(e) and 0.3 < dt < 2.0, f"a trigger that never comes times out: {e} after {dt:.2f} s")
PATTERN["hang"] = False
check(p.version()["protocol"] == 1, "the presser answers after the timeout")

stop.set()
print("FAILED" if fails else "all passed", f"({fails} failures)" if fails else "")
sys.exit(1 if fails else 0)
