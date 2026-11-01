# The key presser (docs/test-bench.md, "The key presser"): an RP2040 board, a
# QT Py RP2040 or a Pico, driving two PC817C optocouplers wired across two of
# the AK820's key switches, commanded from the Mac over USB serial by
# scripts/presser.py. Every closure and release is stamped here, on this
# board's clock, which is where the delivery chain starts
# (plans/ROW-ISR-PLAN.md, "The key-press rig"). Copy this and boot.py to the
# presser board's CIRCUITPY. It is NOT the power logger's QT Py
# (scripts/qtpy/), whose drive is not to be touched while a drain runs.
#
# Channels: A on A0 (GPIO29) and B on A1 (GPIO28) of a QT Py; GP26 and GP27
# on a Pico. A pin high lights the opto's LED through 330 ohm and the key
# reads pressed; low is released, the state at every start and after any
# error. The keyboard and this board share nothing but the opto's light.
#
# W lines go to witness.py, the waveform witness, when it is on the drive.
# Lines in over the data port (boot.py enables it), a reply out for each,
# fields comma-separated, times in microseconds on this board's clock:
#   V                        V,ak820-presser,1,<board>,<uid>,2
#   T                        T,<t>                   the clock, for the Mac's offset
#   S                        S,<t>,<A 0|1>,<B 0|1>,<presses A>,<presses B>
#   P,<ch>,<dwell_ms>[,<gap_ms>[,<n>]]
#                            K,<ch>,<i>,<t_close>,<t_open> after each release,
#                            then B,<ch>,<done>,<n>
#   H,<ch> / R,<ch>          hold / release: H,<ch>,<t> / R,<ch>,<t>
#   X                        stop a batch between presses: X,<done>
#   L,<0-255>                the idle light's green level: L,<level>
#   anything else            E,<reason>
# <ch> is A, B, 0 or 1. Dwell and gap are ms, 0.2 to 5000, read to 0.01 ms;
# the clock steps 1/32768 s (30.5 us) and the recorded dwell is the actual one,
# usually within 0.1 ms of the asked. A held key is released if the Mac keeps
# the port closed for over a second, so a dead script cannot leave a key down.
#
# The light: dim green idle (L sets it; 3 of 255 by default, about 1%), a
# brighter flick while a key is down, amber while one is held; a Pico's plain
# LED is simply on while a key is down.
import time

import board
import digitalio
import microcontroller
import supervisor
import usb_cdc

try:
    import witness   # the waveform witness, W commands (witness.py beside this file)
except Exception:   # no module on the drive, or one this board cannot run
    witness = None

supervisor.runtime.autoreload = False  # a write to CIRCUITPY must not cut a batch short

VERSION = 1
NAMES = ("A", "B")
PIN_NAMES = (("A0", "A1"), ("GP26", "GP27"))
DWELL_MIN_MS, DWELL_MAX_MS, N_MAX = 0.2, 5000.0, 100000
GAP_DEFAULT_MS = 40.0
LED_IDLE, LED_FLICK, LED_HELD = 3, 24, (10, 30, 0)   # green levels; held is GRB amber

pins = None
for names in PIN_NAMES:
    if all(hasattr(board, n) for n in names):
        pins = [digitalio.DigitalInOut(getattr(board, n)) for n in names]
        break
if pins is None:
    raise RuntimeError("no A0/A1 or GP26/GP27 on this board")
for p in pins:
    p.switch_to_output(value=False)   # released

held = [False, False]
presses = [0, 0]
idle_green = LED_IDLE
uid = "".join("%02x" % b for b in microcontroller.cpu.uid)

try:
    import neopixel_write
    if hasattr(board, "NEOPIXEL_POWER"):
        _px_power = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
        _px_power.switch_to_output(value=True)
    _px = digitalio.DigitalInOut(board.NEOPIXEL)
    _px.switch_to_output()

    def led(grb):
        neopixel_write.neopixel_write(_px, bytes(grb))
except (ImportError, AttributeError):
    _led = digitalio.DigitalInOut(board.LED)
    _led.switch_to_output()

    def led(grb):
        _led.value = grb[0] > idle_green


def led_idle():
    led(LED_HELD if any(held) else (idle_green, 0, 0))


ser = usb_cdc.data
if ser is None:
    raise RuntimeError("boot.py did not enable the data port")
ser.timeout = 0
ser.write_timeout = 0.2


def now():
    return time.monotonic_ns() // 1000


def send(s):
    try:
        ser.write((s + "\n").encode())
    except OSError:
        pass   # nobody listening


def wait_until(t_us):
    """Sleep most of the way (the supervisor services USB meanwhile), then
    busy-wait the last ~2.5 ms, since time.sleep rounds to a millisecond."""
    while True:
        rem = t_us - now()
        if rem <= 0:
            return
        if rem > 4000:
            time.sleep((rem - 2500) / 1e6)


_buf = bytearray()


def read_lines():
    """The complete lines received so far, stripped; a line without a newline
    is kept until one arrives, or dropped at 200 bytes."""
    out = []
    n = ser.in_waiting
    if n:
        _buf.extend(ser.read(n))
        while True:
            i = bytes(_buf).find(b"\n")
            if i < 0:
                break
            line = bytes(_buf[:i]).decode("ascii", "replace").strip()
            del _buf[:i + 1]
            if line:
                out.append(line)
        if len(_buf) > 200:
            del _buf[:]
            send("E,line too long")
    return out


def press(ch, dwell_us):
    led((LED_FLICK, 0, 0))
    t0 = now()
    pins[ch].value = True
    wait_until(t0 + dwell_us)
    pins[ch].value = False
    t1 = now()
    presses[ch] += 1
    led_idle()
    return t0, t1


def stop_requested():
    """An X between presses stops the batch; anything else is refused."""
    stop = False
    for line in read_lines():
        if line.upper() == "X":
            stop = True
        else:
            send("E,busy")
    return stop


def batch(ch, dwell_us, gap_us, n):
    done = 0
    for i in range(n):
        t0, t1 = press(ch, dwell_us)
        done += 1
        send("K,%s,%d,%d,%d" % (NAMES[ch], i, t0, t1))
        if i + 1 < n:
            if stop_requested():
                break
            wait_until(t1 + gap_us)
    send("B,%s,%d,%d" % (NAMES[ch], done, n))


def channel(s):
    s = s.strip().upper()
    if s in NAMES:
        return NAMES.index(s)
    if s in ("0", "1"):
        return int(s)
    return None


def set_held(ch, on):
    pins[ch].value = on
    held[ch] = on
    led_idle()
    return now()


def handle(line):
    global idle_green
    f = [x.strip() for x in line.split(",")]
    c = f[0].upper()
    if c == "V":
        send("V,ak820-presser,%d,%s,%s,%d" % (VERSION, board.board_id, uid, len(pins)))
    elif c == "T":
        send("T,%d" % now())
    elif c == "S":
        send("S,%d,%d,%d,%d,%d" % (now(), pins[0].value, pins[1].value, presses[0], presses[1]))
    elif c == "P":
        ch = channel(f[1]) if len(f) >= 3 else None
        if ch is None:
            send("E,P needs a channel (A, B) and a dwell in ms")
            return
        try:
            dwell = float(f[2])
            gap = float(f[3]) if len(f) >= 4 and f[3] else GAP_DEFAULT_MS
            n = int(f[4]) if len(f) >= 5 and f[4] else 1
        except ValueError:
            send("E,P: dwell and gap are ms, n an integer")
            return
        if not DWELL_MIN_MS <= dwell <= DWELL_MAX_MS or not DWELL_MIN_MS <= gap <= DWELL_MAX_MS:
            send("E,dwell and gap must be %g to %g ms" % (DWELL_MIN_MS, DWELL_MAX_MS))
            return
        if not 1 <= n <= N_MAX:
            send("E,n must be 1 to %d" % N_MAX)
            return
        if held[ch]:
            send("E,%s is held" % NAMES[ch])
            return
        batch(ch, int(dwell * 1000), int(gap * 1000), n)
    elif c in ("H", "R"):
        ch = channel(f[1]) if len(f) >= 2 else None
        if ch is None:
            send("E,%s needs a channel (A, B)" % c)
            return
        if c == "H" and held[ch]:
            send("E,%s is already held" % NAMES[ch])
            return
        send("%s,%s,%d" % (c, NAMES[ch], set_held(ch, c == "H")))
    elif c == "X":
        send("X,0")   # nothing running: a batch answers this itself
    elif c == "L":
        try:
            level = int(f[1])
            if not 0 <= level <= 255:
                raise ValueError
        except (IndexError, ValueError):
            send("E,L needs 0 to 255")
            return
        idle_green = level
        led_idle()
        send("L,%d" % level)
    elif c == "W":
        if witness is None:
            send("E,no witness module on this board")
        else:
            witness.handle(f, send)
    else:
        send("E,unknown command %s" % line[:24])


def service(disconnected_since):
    """One pass: commands, then the held-key guard. Returns the guard's state."""
    for line in read_lines():
        handle(line)
    if any(held):
        if ser.connected:
            return None
        if disconnected_since is None:
            return now()
        if now() - disconnected_since > 1000000:
            for ch in range(len(pins)):
                if held[ch]:
                    set_held(ch, False)
            return None
        return disconnected_since
    return None


def main():
    led_idle()
    disconnected_since = None
    while True:
        disconnected_since = service(disconnected_since)
        time.sleep(0.002)


if __name__ == "__main__":
    main()
