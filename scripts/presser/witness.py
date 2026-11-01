# The waveform witness, a module of the key presser's board (scripts/presser/
# code.py imports it; plans/ROW-ISR-PLAN.md, "The key-press rig", item 4;
# docs/test-bench.md, "The waveform witness"). The RP2040's PIO samples up to
# four lines of the keyboard every PIO cycle, 125 million a second on a QT Py
# RP2040 (150 on a Pico 2), into RAM by DMA, and the capture goes to the Mac
# over the presser's data port as base64 lines. The Mac's scripts/witness.py
# arms it, stores the capture and reads the pulses out of it.
#
# The lines: four consecutive GPIOs, bit 0 first. On a QT Py RP2040 they are
# SDA (GPIO24), SCL (GPIO25), A3 (GPIO26) and A2 (GPIO27), which leaves A0 and
# A1 to the presser; on a Pico, GP2 to GP5. Each line comes from the keyboard
# through a 1 kOhm series resistor and the keyboard runs on its pack while
# the probe is attached (the plan: its rail is then 3.90 V, a tenth of a volt
# over the RP2040's pin rating, which the resistor and the pin's diode absorb
# at a fraction of a milliamp; on USB the rail is 4.5-4.8 V and the same
# resistor passes about a milliamp, so relay 2 stays off while the probe is
# on). Power this board before the keyboard's lines reach it. Nothing here
# drives a line: every pin is an input with no pull.
#
# Protocol, lines in over the data port and a reply out for each, as the
# presser's:
#   W,V              -> W,V,<version>,<lines>,<pin names>,<sys Hz>,<max words>,<rp2pio>
#   W,C,<n>,<hz>,<words>,<trig>,<wait ms>
#                    capture n lines (1, 2 or 4) at hz samples a second (0 or
#                    the system clock for the full rate; the actual rate is in
#                    the reply), words 32-bit words of samples (32/n samples a
#                    word), trig N (now), R<i> or F<i> (the rising or falling
#                    edge of line i, which starts the capture to one sample),
#                    giving the trigger wait ms to arrive.
#                    -> W,C,<actual hz>,<n>,<words>,<trig>,<stall>,<t_arm us>,<t_done us>
#                       then W,D,<base64> lines, then W,E,<bytes>,<crc32 or ->
#                    stall 1 means the RX FIFO overflowed during the capture
#                    (the samples are not continuous: lower the rate or the
#                    lines). An E line instead of W,C when the capture could
#                    not be made or the trigger never came (E,timeout).
#   W,P              -> W,P,<bits>: the four lines' levels now, bit 0 first,
#                    read once with digitalio (the probe's attachment check).
# The capture words: in_shift_right, so the first sample of a word is its
# low n bits, bit 0 the first line; the next sample the n bits above it.
import time

import board
import microcontroller

VERSION = 1
LINES = 4
# The first pin must be the named GPIO, since the PIO takes the next three by
# number, whatever the board calls them.
PIN_SETS = ((("SDA", "SCL", "A3", "A2"), "GPIO24"), (("GP2", "GP3", "GP4", "GP5"), "GPIO2"))
WAIT_MAX_MS = 20000
CHUNK_WORDS = 768                 # 3072 bytes, 4096 base64 characters a line

try:
    import array
    import binascii
    import rp2pio
    HAVE_PIO = True
except ImportError:
    HAVE_PIO = False

pin_names, first_pin = None, None
_mpin = getattr(microcontroller, "pin", None)
for names, gpio in PIN_SETS:
    if _mpin is not None and all(hasattr(board, n) for n in names) and hasattr(_mpin, gpio) \
            and getattr(board, names[0]) is getattr(_mpin, gpio):
        pin_names, first_pin = names, getattr(board, names[0])
        break

SYS_HZ = int(getattr(microcontroller.cpu, "frequency", 125000000))

# One buffer, the largest the heap gives at import, 32-bit words so the DMA
# moves whole FIFO words (a byte buffer would take one byte a word).
buf, max_words = None, 0
if HAVE_PIO and first_pin is not None:
    probe = array.array("I", bytes(8))
    if len(probe) == 2 and probe.itemsize == 4:
        for kb in (224, 192, 160, 128, 96, 64, 48, 32, 16):
            try:
                buf = array.array("I", bytes(kb * 1024))
                max_words = len(buf)
                break
            except MemoryError:
                buf = None
    del probe


def _crc(mv):
    if hasattr(binascii, "crc32"):
        return "%08x" % (binascii.crc32(mv) & 0xFFFFFFFF)
    return "-"


def _now():
    return time.monotonic_ns() // 1000


# PIO encodings (the RP2040 datasheet, 3.4): IN pins,n is 0x4000 | n (n 32 ->
# 0); WAIT polarity pin index is 0x2000 | polarity << 7 | 1 << 5 | index.
def program(n, trig):
    """The instructions and the wrap: the trigger's two waits once, then IN
    forever. trig is 'N', 'R<i>' or 'F<i>'."""
    in_pins = 0x4000 | (n & 31)
    if trig == "N":
        return (in_pins,), 0
    i = int(trig[1:])
    if trig[0] == "R":
        return (0x2020 | i, 0x20A0 | i, in_pins), 2
    return (0x20A0 | i, 0x2020 | i, in_pins), 2


def parse_capture(f):
    """-> (n, hz, words, trig, wait_ms) or an error string."""
    try:
        n, hz, words, trig, wait_ms = int(f[2]), int(float(f[3])), int(f[4]), f[5].upper(), int(f[6])
    except (IndexError, ValueError):
        return "W,C needs lines, hz, words, trig, wait ms"
    if n not in (1, 2, 4):
        return "lines must be 1, 2 or 4"
    if hz < 0 or hz > SYS_HZ:
        return "hz must be 0 (the system clock) to %d" % SYS_HZ
    if not 1 <= words <= max_words:
        return "words must be 1 to %d" % max_words
    if trig != "N" and not (len(trig) == 2 and trig[0] in "RF" and trig[1] in "0123"):
        return "trig must be N, R0-R3 or F0-F3"
    if not 0 <= wait_ms <= WAIT_MAX_MS:
        return "wait must be 0 to %d ms" % WAIT_MAX_MS
    return n, hz or SYS_HZ, words, trig, wait_ms


def capture(n, hz, words, trig, wait_ms, send):
    """One capture, the reply lines through send(). The DMA is armed before
    the state machine restarts, so the first word of the capture is the first
    word the program pushes; a trigger wait that outlasts wait_ms ends it."""
    instr, wrap_target = program(n, trig)
    kw = dict(frequency=hz, first_in_pin=first_pin, in_pin_count=LINES,
              auto_push=True, push_threshold=32, in_shift_right=True,
              wrap_target=wrap_target, wrap=len(instr) - 1, user_interruptible=False)
    sm = None
    try:
        try:
            sm = rp2pio.StateMachine(array.array("H", instr), fifo_type="rx", **kw)
        except (TypeError, ValueError):
            sm = rp2pio.StateMachine(array.array("H", instr), **kw)
        sm.stop()
        sm.clear_rxfifo()
        view = memoryview(buf)[:words]
        sm.background_read(once=view)
        t_arm = _now()
        sm.restart()
        samples = words * (32 // n)
        deadline = t_arm + wait_ms * 1000 + (samples * 1000000) // sm.frequency + 500000
        while sm.reading:
            if _now() > deadline:
                sm.stop()
                send("E,timeout: %s after %d ms" % ("the trigger never came" if trig != "N" else "the DMA did not finish", wait_ms))
                return
            time.sleep(0.001)
        t_done = _now()
        sm.stop()
        stall = 1 if sm.rxstall else 0
        actual = sm.frequency
    except Exception as e:
        send("E,capture: %s" % e)
        return
    finally:
        if sm is not None:
            sm.deinit()
    send("W,C,%d,%d,%d,%s,%d,%d,%d" % (actual, n, words, trig, stall, t_arm, t_done))
    crc = 0
    for a in range(0, words, CHUNK_WORDS):
        chunk = memoryview(buf)[a:min(words, a + CHUNK_WORDS)]
        if hasattr(binascii, "crc32"):
            crc = binascii.crc32(chunk, crc)
        send("W,D," + binascii.b2a_base64(chunk).decode("ascii").strip())
    send("W,E,%d,%s" % (words * 4, ("%08x" % (crc & 0xFFFFFFFF)) if hasattr(binascii, "crc32") else "-"))


def levels():
    """The four lines read once as plain inputs: bit 0 the first."""
    import digitalio
    bits = 0
    for i, name in enumerate(pin_names):
        p = digitalio.DigitalInOut(getattr(board, name))
        try:
            p.switch_to_input()
            if p.value:
                bits |= 1 << i
        finally:
            p.deinit()
    return bits


def handle(f, send):
    """f: the comma-split fields of a W line (f[0] is 'W')."""
    sub = f[1].upper() if len(f) > 1 else ""
    if sub == "V":
        send("W,V,%d,%d,%s,%d,%d,%d" % (VERSION, LINES, "/".join(pin_names) if pin_names else "-",
                                       SYS_HZ, max_words, 1 if (HAVE_PIO and buf is not None) else 0))
    elif sub == "C":
        if not HAVE_PIO or buf is None:
            send("E,no witness on this board (rp2pio or the pins missing, or no memory for the buffer)")
            return
        r = parse_capture(f)
        if isinstance(r, str):
            send("E," + r)
            return
        capture(*r, send)
    elif sub == "P":
        if pin_names is None:
            send("E,no witness pins on this board")
            return
        send("W,P,%d" % levels())
    else:
        send("E,W needs V, C or P")
