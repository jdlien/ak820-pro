#!/usr/bin/env python3
"""Send a notification to the AK820 Pro -- over the cable, or over BT/2.4G.

    ak820notify.py send "Claude" "finished"                 lights + 2 lines in the text band
    ak820notify.py send "Claude" "finished" --page --gif 1  full screen until a key is pressed
    ak820notify.py gif-upload 1 some.gif                    store a GIF in slot 1..5 (cable)
    ak820notify.py close [--if-open]                        close the page on the board
    ak820notify.py ambient 3 [--after 60]                   screensaver: slot's GIF after N s idle (off = none)
    ak820notify.py ask "Permission" "Bash" "git push" --permission
    ak820notify.py ask "Which?" --options "One|Two|Three" [--multi]
                   a question answered on the board: arrows move, Space ticks
                   (--multi), Enter answers, Esc cancels; other keys are
                   ignored. Prints allow | deny | cancel | choice:N |
                   multi:N,M | timeout | aborted (SIGTERM, see below)
    ak820notify.py stats                                    LED-channel decoder counters (cable)

LINUX ONLY. Two transports carry the same frame (layout in the firmware's
notify.c):

  raw HID   channel 0x14, when the board is on the cable. Instant. Found
            through /sys/class/hidraw -- never by enumerating HID, which on
            some machines wedges other devices (see CLAUDE.md).
  LED       over BT/2.4G the CH582F forwards only the host keyboard-LED
            report, so the frame goes as Num Lock / Scroll Lock toggles on
            the wireless receiver's LED class devices: Num = 0, Scroll = 1,
            one bit per change, sent twice. ~1.7 s for two short lines at the
            default 10 ms per bit (measured reliable down to 8 ms; 6 ms loses
            every frame). Only that one device's LEDs change -- the host's own
            lock state and other keyboards are untouched. Writing the LEDs
            needs hostagent/linux/70-ak820-notify.rules.

Picked automatically (raw HID if the cable is there), or forced with --via.

Answers come back as HID consumer usages (the only board-to-host path over
BT/2.4G besides keystrokes), read from the receiver's or the board's
"Consumer Control" input device -- media keys only, never typing. Reading it
needs the same udev rules.

Settings: ~/.config/ak820notify.conf, KEY=value lines. TIMEOUT=300 is how long
`ask` waits for an answer; AMBIENT_AFTER=60 is the screensaver delay the
Claude Code hook sets.
"""
import argparse
import glob
import os
import select
import signal
import struct
import sys
import time
import unicodedata

VID = "0c45"
PID_KB = "8009"          # the board itself (cable)
PID_DONGLE = "fdfd"      # its 2.4G receiver
SET_VALUE, NOTIFY_CHANNEL = 0x07, 0x14
NOTIFY_SHOW, NOTIFY_STATS, NOTIFY_BOOTLOADER = 0x01, 0x02, 0x03
NOTIFY_STAGE, NOTIFY_COMMIT = 0x05, 0x06

EFFECTS = {"solid": 0, "blink": 1, "breathe": 2, "sweep": 3}
COLORS = {"red": 0, "orange": 21, "yellow": 43, "green": 85, "cyan": 128,
          "blue": 170, "purple": 191, "magenta": 213}
TEXT_MAX = 44            # NOTIFY_TEXT_MAX in notify.c
GIF_BASE, GIF_STRIDE, GIF_SLOTS, GIF_MAXF = 0xD80000, 0x80000, 5, 15

HERE = os.path.dirname(os.path.abspath(__file__))
AK820CTL = os.path.join(HERE, "..", "time-util-ak820pro", "ak820ctl")
SEQ_FILE = os.path.expanduser("~/.cache/ak820notify.seq")
PAGE_STATE = os.path.expanduser("~/.cache/ak820notify.page")   # a page may be open
ASKS_DIR = os.path.expanduser("~/.cache/ak820notify.asks")      # one file per waiting ask: <pid> -> tag
SEND_LOCK = os.path.expanduser("~/.cache/ak820notify.lock")     # serialises every send
SLOTS_FILE = os.path.expanduser("~/.cache/ak820notify.slots")   # question slot -> pid
CONF = os.path.expanduser("~/.config/ak820notify.conf")

KIND_SHOW, KIND_CLOSE, KIND_ASK, KIND_AMBIENT = 0, 1, 2, 3
ASK_PERM, ASK_MULTI = 4, 8          # bits 1-0: detail lines, bits 5-4: slot
CLOSE_SLOT = 0x80
ASK_SLOTS = 4
# Slot markers, sent by the board before every answer (see notify.c).
SLOT_MARK = {0x199: 0, 0x1A7: 1, 0x1AE: 2, 0x18E: 3}
# Answers: HID consumer usages (MSC_SCAN = 0x000C0000 | usage), see notify.c.
ANSWERS = {0x191: "allow", 0x1AB: "deny", 0x1BD: "cancel",
           0x1B6: "choice:1", 0x1B7: "choice:2", 0x1B8: "choice:3", 0x1BC: "choice:4"}


# --------------------------------------------------------------------- frame
def crc8(data):
    """CRC-8, poly 0x07, init 0 -- the firmware's crc8()."""
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def to_ascii(s):
    """The panel fonts are printable ASCII: fold accents, keep newlines."""
    out = []
    for ch in s:
        if ch == "\n" or 0x20 <= ord(ch) < 0x7F:
            out.append(ch)
        else:
            out.append(unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode() or "?")
    return "".join(out)


def build_frame(seq, effect, hue, dur_ds, text, page=False, gif=0, kind=KIND_SHOW):
    """[hdr][hue][dur][gif|flags][len][text...][crc] -- see notify.c."""
    t = to_ascii(text).encode()[:TEXT_MAX]
    hdr = (seq & 3) << 6 | (effect & 7) << 3 | (4 if page else 0) | (kind & 3)
    body = bytes([hdr, hue & 0xFF, dur_ds & 0xFF, gif & 0xFF, len(t)]) + t
    return body + bytes([crc8(body)])


def next_seq():
    """2-bit sequence number, persisted so consecutive runs never repeat one
    (the firmware drops a repeat within 15 s as the duplicate copy)."""
    try:
        s = (int(open(SEQ_FILE).read()) + 1) & 3
    except (OSError, ValueError):
        s = 0
    try:
        os.makedirs(os.path.dirname(SEQ_FILE), exist_ok=True)
        with open(SEQ_FILE, "w") as f:
            f.write(str(s))
    except OSError:
        pass
    return s


# ------------------------------------------------------------------- devices
def _usb_ids(sysdev):
    """Walk up sysfs from a class device to its USB device: (vid, pid)."""
    d = os.path.realpath(sysdev)
    while d != "/":
        v = os.path.join(d, "idVendor")
        if os.path.exists(v):
            return open(v).read().strip(), open(os.path.join(d, "idProduct")).read().strip()
        d = os.path.dirname(d)
    return None, None


def find_rawhid():
    """The board's QMK raw-HID node (usage page 0xFF60), or None."""
    for h in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        if _usb_ids(h + "/device") != (VID, PID_KB):
            continue
        with open(h + "/device/report_descriptor", "rb") as f:
            if f.read(3) == b"\x06\x60\xff":
                return "/dev/" + os.path.basename(h)
    return None


def rawhid_xfer(dev, payload, want_reply=True):
    """One 32-byte report out; the reply whose channel+command match ours.
    hidraw returns reports without a report id: [0] status, [1] channel, [2] cmd."""
    pkt = bytes(payload) + bytes(32 - len(payload))
    fd = os.open(dev, os.O_RDWR)
    try:
        os.write(fd, b"\x00" + pkt)
        if not want_reply:
            return None
        end = time.time() + 1.0
        while time.time() < end:
            if select.select([fd], [], [], 0.2)[0]:
                rep = os.read(fd, 64)
                if rep[1:3] == pkt[1:3]:
                    return rep
        raise TimeoutError("no raw-HID reply")
    finally:
        os.close(fd)


def find_leds():
    """(num, scroll) brightness files of the receiver, else of the board."""
    for pid in (PID_DONGLE, PID_KB):
        for num in sorted(glob.glob("/sys/class/leds/input*::numlock")):
            scr = num.replace("::numlock", "::scrolllock")
            if _usb_ids(num + "/device") == (VID, pid) and os.path.exists(scr):
                return num + "/brightness", scr + "/brightness"
    return None


LAST_SEND = os.path.expanduser("~/.cache/ak820notify.last")
FRAME_GAP = 0.6   # s of silence between frames; the firmware ends a frame after 0.4


def _gap_wait():
    """Frames closer than the firmware's 400 ms gap merge into one oversized
    frame that fails the length check -- measured: back-to-back runs lost 4
    of 5. Wait out the gap since the previous send, from any process."""
    try:
        wait = os.path.getmtime(LAST_SEND) + FRAME_GAP - time.time()
        if 0 < wait <= FRAME_GAP:
            time.sleep(wait)
    except OSError:
        pass


def _gap_mark():
    try:
        os.makedirs(os.path.dirname(LAST_SEND), exist_ok=True)
        open(LAST_SEND, "w").close()
    except OSError:
        pass


def send_leds(frame, num_path, scr_path, bit_ms, repeats, gap_ms=FRAME_GAP * 1000):
    """Toggle Num for a 0 and Scroll for a 1, MSB first. Every bit must be a
    CHANGE: the host only sends the LED report when it changes."""
    _gap_wait()
    state = {p: int(open(p).read()) > 0 for p in (num_path, scr_path)}
    fds = {p: os.open(p, os.O_WRONLY) for p in state}
    try:
        for r in range(repeats):
            if r:
                time.sleep(gap_ms / 1000)   # > the firmware's 400 ms frame gap
            for byte in frame:
                for i in range(7, -1, -1):
                    p = scr_path if (byte >> i) & 1 else num_path
                    state[p] = not state[p]
                    os.write(fds[p], b"1" if state[p] else b"0")
                    time.sleep(bit_ms / 1000)
    finally:
        for fd in fds.values():
            os.close(fd)
        _gap_mark()


def find_consumer_events():
    """The board's and the receiver's "Consumer Control" evdev nodes."""
    out = []
    for n in glob.glob("/sys/class/input/input*/name"):
        try:
            name = open(n).read().strip()
        except OSError:
            continue
        d = os.path.dirname(n)
        if name.endswith("Consumer Control") and _usb_ids(d) in ((VID, PID_KB), (VID, PID_DONGLE)):
            out += ["/dev/input/" + os.path.basename(e) for e in glob.glob(d + "/event*")]
    return out


def _locked(path):
    """An exclusive fcntl lock on `path`, as a context manager."""
    import contextlib
    import fcntl

    @contextlib.contextmanager
    def cm():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    return cm()


def slot_take():
    """A free question slot (0-3), or None if all four are taken. Slots of
    dead processes free themselves."""
    with _locked(SLOTS_FILE + ".lock"):
        try:
            owners = {int(k): int(v) for k, v in (l.split() for l in open(SLOTS_FILE) if l.strip())}
        except (OSError, ValueError):
            owners = {}
        alive = {}
        for k, pid in owners.items():
            try:
                os.kill(pid, 0)
                alive[k] = pid
            except OSError:
                pass
        free = [k for k in range(ASK_SLOTS) if k not in alive]
        if not free:
            return None
        alive[free[0]] = os.getpid()
        with open(SLOTS_FILE, "w") as f:
            f.writelines(f"{k} {v}\n" for k, v in alive.items())
        return free[0]


def slot_release(slot):
    with _locked(SLOTS_FILE + ".lock"):
        try:
            lines = [l for l in open(SLOTS_FILE) if l.strip() and int(l.split()[0]) != slot]
            with open(SLOTS_FILE, "w") as f:
                f.writelines(lines)
        except (OSError, ValueError):
            pass


def wait_answer(timeout, multi=False, slot=0):
    """Our slot's answer, from EV_MSC/MSC_SCAN: the board sends the slot's
    marker, then the answer. A multi-select arrives as the ticked choices
    followed by "allow" as the end marker."""
    fds = []
    for dev in find_consumer_events():
        try:
            fds.append(os.open(dev, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    if not fds:
        return "noreader"
    fmt = "llHHi"                      # struct input_event, 64-bit
    size = struct.calcsize(fmt)
    end = time.time() + timeout
    picked = []
    mine = False     # the last marker seen was ours
    marked = False   # any marker seen (firmware with the queue)
    try:
        while time.time() < end:
            for fd in select.select(fds, [], [], max(0.05, end - time.time()))[0]:
                try:
                    data = os.read(fd, size * 64)
                except BlockingIOError:
                    continue
                for off in range(0, len(data) - size + 1, size):
                    _, _, typ, code, val = struct.unpack_from(fmt, data, off)
                    if typ != 4 or code != 4 or (val >> 16) != 0x0C:   # EV_MSC, MSC_SCAN, consumer page
                        continue
                    u = val & 0xFFFF
                    if u in SLOT_MARK:
                        mine, marked = SLOT_MARK[u] == slot, True
                        continue
                    a = ANSWERS.get(u)
                    # Firmware without the queue sends no markers: slot 0 only.
                    if not a or not (mine or (not marked and slot == 0)):
                        continue
                    if multi and a.startswith("choice:"):
                        if a[7:] not in picked:
                            picked.append(a[7:])
                    elif multi and a == "allow":
                        return "multi:" + ",".join(picked)
                    else:
                        return a
        return "timeout"
    finally:
        for fd in fds:
            os.close(fd)


def send_frame(frame, via="auto", bit_ms=10.0, repeats=2):
    """Raw HID if the board is on the cable (staged for long frames), else the
    LEDs -- one send at a time across processes: interleaved frames on the LED
    channel corrupt each other. Only the send is locked, never a wait."""
    with _locked(SEND_LOCK):
        _send_frame(frame, via, bit_ms, repeats)


def _send_frame(frame, via, bit_ms, repeats):
    dev = find_rawhid() if via in ("auto", "usb") else None
    if dev:
        for off in range(0, len(frame), 27):   # [07 14 05 off n] + up to 27 bytes
            chunk = list(frame[off:off + 27])
            if rawhid_xfer(dev, [SET_VALUE, NOTIFY_CHANNEL, NOTIFY_STAGE, off, len(chunk)] + chunk)[0] != SET_VALUE:
                sys.exit("the board rejected the frame (firmware without notify?)")
        if rawhid_xfer(dev, [SET_VALUE, NOTIFY_CHANNEL, NOTIFY_COMMIT, len(frame)])[0] != SET_VALUE:
            sys.exit("the board rejected the frame (firmware without notify?)")
        return
    if via == "usb":
        sys.exit("board not found on the cable")
    leds = find_leds() or sys.exit("no Num/Scroll LEDs for the receiver or the board")
    try:
        send_leds(frame, *leds, bit_ms, repeats)
    except PermissionError:
        sys.exit("cannot write the LEDs: install hostagent/linux/70-ak820-notify.rules")


def page_state(is_open):
    try:
        if is_open:
            os.makedirs(os.path.dirname(PAGE_STATE), exist_ok=True)
            open(PAGE_STATE, "w").write(str(time.time()))
        elif os.path.exists(PAGE_STATE):
            os.remove(PAGE_STATE)
    except OSError:
        pass


def load_conf():
    c = {"TIMEOUT": "300"}
    try:
        for line in open(CONF):
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                c[k.strip().upper()] = v.strip()
    except OSError:
        pass
    return c


# ----------------------------------------------------------------------- gif
def gif_blob(path):
    """GIF -> slot image: "AKN1", frame count, 0xFF pad to 0x100, then 128x128
    RGB565 frames lo-byte-first (the DMA swaps pairs), 0x8000 apart. Letterboxed
    on black; more than 15 frames are evenly thinned."""
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        sys.exit("needs Pillow: run with ./venv/bin/python (qmk installs it)")
    frames = []
    for fr in ImageSequence.Iterator(Image.open(path)):
        f = fr.convert("RGBA")
        f = Image.alpha_composite(Image.new("RGBA", f.size, (0, 0, 0, 255)), f).convert("RGB")
        f.thumbnail((128, 128), Image.LANCZOS)
        canvas = Image.new("RGB", (128, 128), (0, 0, 0))
        canvas.paste(f, ((128 - f.width) // 2, (128 - f.height) // 2))
        px = bytearray()
        for r, g, b in canvas.getdata():
            v = (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
            px += bytes([v & 0xFF, v >> 8])
        frames.append(bytes(px) + bytes(0x8000 - len(px)))
    if len(frames) > GIF_MAXF:
        step = len(frames) / GIF_MAXF
        frames = [frames[int(i * step)] for i in range(GIF_MAXF)]
    hdr = b"AKN1" + bytes([len(frames)])
    return hdr + b"\xff" * (0x100 - len(hdr)) + b"".join(frames), len(frames)


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="show a notification")
    s.add_argument("title")
    s.add_argument("body", nargs="?", default="")
    s.add_argument("--color", default="blue", help="name (%s) or hue 0-255" % ", ".join(COLORS))
    s.add_argument("--effect", default="breathe", choices=list(EFFECTS))
    s.add_argument("--dur", default="4", help="seconds of light; 0 = none, 'until' = until dismissed")
    s.add_argument("--page", action="store_true", help="full screen until any key is pressed")
    s.add_argument("--gif", type=int, default=0, help="with --page: GIF slot 1-5 (0 = text)")
    s.add_argument("--via", choices=["auto", "usb", "leds"], default="auto")
    s.add_argument("--bit-ms", type=float, default=10.0, help="LED channel: pause per bit")
    s.add_argument("--repeats", type=int, default=2, help="LED channel: copies sent")
    g = sub.add_parser("gif-upload", help="store a GIF in a slot (cable)")
    g.add_argument("slot", type=int, choices=range(1, GIF_SLOTS + 1))
    g.add_argument("gif")
    am = sub.add_parser("ambient", help="set the screensaver")
    am.add_argument("slot", help="GIF slot 1-5, or off")
    am.add_argument("--after", type=int, default=60, help="seconds without a key press before it starts (1-255)")
    am.add_argument("--via", choices=["auto", "usb", "leds"], default="auto")
    cl = sub.add_parser("close", help="close the page on the board")
    cl.add_argument("--if-open", action="store_true", help="only if a page may be open")
    cl.add_argument("--via", choices=["auto", "usb", "leds"], default="auto")
    ak = sub.add_parser("ask", help="a question answered on the board")
    ak.add_argument("title")
    ak.add_argument("details", nargs="*", help="up to 2 detail lines")
    ak.add_argument("--options", default="", help="choices, |-separated (permission default: Allow|Deny)")
    ak.add_argument("--permission", action="store_true", help="option 1 = allow, option 2 = deny")
    ak.add_argument("--multi", action="store_true", help="checkboxes: Space ticks, Enter answers")
    ak.add_argument("--color", default="yellow")
    ak.add_argument("--effect", default="blink", choices=list(EFFECTS))
    ak.add_argument("--timeout", type=float, default=None, help="seconds (default: TIMEOUT in the conf)")
    ak.add_argument("--tag", default="", help="free text stored with the waiting ask (the hook: session + tool)")
    ak.add_argument("--via", choices=["auto", "usb", "leds"], default="auto")
    sub.add_parser("stats", help="LED-channel decoder counters (cable)")
    sub.add_parser("bootloader", help="reboot to the bootloader (firmware built with NOTIFY_RAW_BOOTLOADER)")
    a = ap.parse_args()

    if a.cmd == "gif-upload":
        blob, n = gif_blob(a.gif)
        out = os.path.expanduser(f"~/.cache/ak820notify-gif{a.slot}.bin")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(blob)
        addr = GIF_BASE + (a.slot - 1) * GIF_STRIDE
        print(f"slot {a.slot}: {n} frames, {len(blob)} bytes -> 0x{addr:06X}", flush=True)
        # Under the send lock: a hook's CLOSE on the same raw-HID interface in
        # the middle of the write interleaves the replies and spoils the slot
        # (seen: a CRC mismatch after a hook fired mid-upload).
        import subprocess
        with _locked(SEND_LOCK):
            sys.exit(subprocess.run([AK820CTL, "flash", "write", hex(addr), out]).returncode)

    if a.cmd in ("stats", "bootloader"):
        dev = find_rawhid() or sys.exit("board not found on the cable")
        if a.cmd == "bootloader":
            rawhid_xfer(dev, [SET_VALUE, NOTIFY_CHANNEL, NOTIFY_BOOTLOADER], want_reply=False)
            return
        rep = rawhid_xfer(dev, [SET_VALUE, NOTIFY_CHANNEL, NOTIFY_STATS])
        if rep[0] != SET_VALUE:
            sys.exit("this firmware has no notify channel")
        d = rep[3:23]
        u16 = lambda i: d[i] << 8 | d[i + 1]
        print(f"frames ok {u16(0)}  crc {u16(2)}  length {u16(4)}  both-flipped {u16(6)}  duplicates {u16(8)}")
        print(f"LED changes {int.from_bytes(d[10:14], 'big')}  last frame {u16(14)} bits in {u16(16)} ms"
              f"  min gap {u16(18)} ms")
        return

    if a.cmd == "ambient":
        slot = 0 if a.slot == "off" else int(a.slot)
        send_frame(build_frame(next_seq(), 0, 0, max(1, min(255, a.after)), "", gif=slot, kind=KIND_AMBIENT), a.via)
        return

    if a.cmd == "close":
        if a.if_open and not os.path.exists(PAGE_STATE):
            return
        page_state(False)
        send_frame(build_frame(next_seq(), 0, 0, 0, "", kind=KIND_CLOSE), a.via)
        return

    hue = COLORS.get(a.color.lower())
    hue = int(a.color) if hue is None else hue

    if a.cmd == "ask":
        slot = slot_take()
        if slot is None:
            print("busy")   # four questions already waiting: this one stays at the computer
            return
        details = [d for d in a.details if d][:2]
        opts = [o for o in (a.options or ("Allow|Deny" if a.permission else "")).split("|") if o]
        if len(opts) < (2 if a.permission else 1):
            sys.exit("--options: nothing to choose from")
        opts = opts[:2] if a.permission else opts[:4 - len(details)]
        flags = len(details) | (ASK_PERM if a.permission else 0) | (ASK_MULTI if a.multi else 0) | slot << 4
        frame = build_frame(next_seq(), EFFECTS[a.effect], hue, 255, "\n".join([a.title] + details + opts),
                            True, flags, kind=KIND_ASK)
        send_frame(frame, a.via)
        page_state(True)

        # Whoever deals with the question at the computer sends SIGTERM (the
        # Claude Code hook does): stop waiting and close the page now rather
        # than holding it up until the timeout.
        def _abort(*_):
            raise InterruptedError
        signal.signal(signal.SIGTERM, _abort)
        signal.signal(signal.SIGHUP, _abort)
        os.makedirs(ASKS_DIR, exist_ok=True)
        mine = os.path.join(ASKS_DIR, str(os.getpid()))
        with open(mine, "w") as f:
            f.write(a.tag + "\n")
        try:
            ans = wait_answer(a.timeout if a.timeout is not None else float(load_conf()["TIMEOUT"]), a.multi, slot)
        except InterruptedError:
            ans = "aborted"
        finally:
            try:
                os.remove(mine)
            except OSError:
                pass
        if ans in ("timeout", "noreader", "aborted"):   # withdraw just this question
            send_frame(build_frame(next_seq(), 0, 0, 0, "", gif=CLOSE_SLOT | slot << 4, kind=KIND_CLOSE), a.via)
        slot_release(slot)
        page_state(False)
        print(ans)
        return

    dur = 255 if a.dur == "until" else min(254, round(float(a.dur) * 10))
    text = a.title + ("\n" + a.body if a.body else "")
    seq = next_seq()
    if a.page:
        page_state(True)
    send_frame(build_frame(seq, EFFECTS[a.effect], hue, dur, text, a.page, a.gif), a.via, a.bit_ms, a.repeats)


if __name__ == "__main__":
    main()
