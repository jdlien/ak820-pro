#!/usr/bin/env python3
"""Send a notification to the AK820 Pro -- over the cable, or over BT/2.4G.

    ak820notify.py send "Claude" "finished"                 lights + 2 lines in the text band
    ak820notify.py send "Claude" "finished" --page --gif 1  full screen until a key is pressed
    ak820notify.py gif-upload 1 some.gif                    store a GIF in slot 1..5 (cable)
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
"""
import argparse
import glob
import os
import select
import sys
import time
import unicodedata

VID = "0c45"
PID_KB = "8009"          # the board itself (cable)
PID_DONGLE = "fdfd"      # its 2.4G receiver
SET_VALUE, NOTIFY_CHANNEL = 0x07, 0x14
NOTIFY_SHOW, NOTIFY_STATS, NOTIFY_BOOTLOADER = 0x01, 0x02, 0x03

EFFECTS = {"solid": 0, "blink": 1, "breathe": 2, "sweep": 3}
COLORS = {"red": 0, "orange": 21, "yellow": 43, "green": 85, "cyan": 128,
          "blue": 170, "purple": 191, "magenta": 213}
TEXT_MAX = 44            # NOTIFY_TEXT_MAX in notify.c
GIF_BASE, GIF_STRIDE, GIF_SLOTS, GIF_MAXF = 0xD80000, 0x80000, 5, 15

HERE = os.path.dirname(os.path.abspath(__file__))
AK820CTL = os.path.join(HERE, "..", "time-util-ak820pro", "ak820ctl")
SEQ_FILE = os.path.expanduser("~/.cache/ak820notify.seq")


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


def build_frame(seq, effect, hue, dur_ds, text, page=False, gif=0):
    """[hdr][hue][dur][gif][len][text...][crc] -- see notify.c."""
    t = to_ascii(text).encode()[:TEXT_MAX]
    hdr = (seq & 3) << 6 | (effect & 7) << 3 | (4 if page else 0)
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


def send_leds(frame, num_path, scr_path, bit_ms, repeats, gap_ms=500):
    """Toggle Num for a 0 and Scroll for a 1, MSB first. Every bit must be a
    CHANGE: the host only sends the LED report when it changes."""
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
        print(f"slot {a.slot}: {n} frames, {len(blob)} bytes -> 0x{addr:06X}")
        os.execv(AK820CTL, [AK820CTL, "flash", "write", hex(addr), out])

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

    hue = COLORS.get(a.color.lower())
    hue = int(a.color) if hue is None else hue
    dur = 255 if a.dur == "until" else min(254, round(float(a.dur) * 10))
    text = a.title + ("\n" + a.body if a.body else "")
    seq = next_seq()

    dev = find_rawhid() if a.via in ("auto", "usb") else None
    if dev:
        # One 32-byte report: 3 bytes of framing leave 29 for the frame.
        frame = build_frame(seq, EFFECTS[a.effect], hue, dur, text[:23], a.page, a.gif)
        rep = rawhid_xfer(dev, [SET_VALUE, NOTIFY_CHANNEL, NOTIFY_SHOW] + list(frame))
        if rep[0] != SET_VALUE:
            sys.exit("the board rejected the frame (firmware without notify?)")
        return
    if a.via == "usb":
        sys.exit("board not found on the cable")
    leds = find_leds() or sys.exit("no Num/Scroll LEDs for the receiver or the board")
    frame = build_frame(seq, EFFECTS[a.effect], hue, dur, text, a.page, a.gif)
    try:
        send_leds(frame, *leds, a.bit_ms, a.repeats)
    except PermissionError:
        sys.exit("cannot write the LEDs: install hostagent/linux/70-ak820-notify.rules")


if __name__ == "__main__":
    main()
