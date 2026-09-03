#!/usr/bin/env python3
"""Push a line of text + a transport icon to the AK820 Pro's LCD.

Wire format (one raw-HID report, no framing -- the whole payload fits):
    [0x07 SET_VALUE][0x12 TEXT_CHANNEL][0x01 TEXT_SET  ][icon][ascii...]
    [0x07 SET_VALUE][0x12 TEXT_CHANNEL][0x02 TEXT_CLEAR]

The firmware attaches no meaning to the text; this script decides what it says.
Platform-agnostic by design -- a Windows producer sends the same bytes.

Usage:
    ak820text.py "Some text" [--icon play|pause|stop|none]
    ak820text.py --clear
"""
import argparse, sys
import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
import hid

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61        # QMK raw HID
SET_VALUE, TEXT_CHANNEL, TEXT_SET, TEXT_CLEAR = 0x07, 0x12, 0x01, 0x02
TEXT_SET_LINE = 0x03
TEXT_PLAYBACK = 0x04                     # per-line set: [line][icon][ascii...]
# Per-line character budget, matching DISPLAY_TEXT_MAX_L0/L1 in the firmware.
# Only line 0 sits beside the transport icon, so it loses the 14px gutter:
# (128 - 14) / 6 = 19. Line 1 runs the full width: (128 - 2) / 6 = 21. The
# firmware clamps too -- this is here so the producer knows what will survive.
MAXLEN = {0: 19, 1: 21}
ICONS = {"none": 0, "play": 1, "pause": 2, "stop": 3}

# The atlases carry printable ASCII only. Transliterate the punctuation real
# track titles are full of, rather than letting the firmware substitute '?'.
SUBS = {"‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " "}


def to_ascii(s):
    for k, v in SUBS.items():
        s = s.replace(k, v)
    try:                                  # strip accents where possible
        import unicodedata
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    except Exception:
        pass
    return "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s)


def open_device():
    """The `hid` package (a QMK dependency) exposes hid.Device(path=...), not
    the hidapi-style hid.device()/open_path(). Match on usage page/usage rather
    than vid/pid alone -- the board publishes several HID interfaces and only
    0xFF60/0x61 is QMK's raw HID."""
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            return hid.Device(path=d["path"])
    raise SystemExit("raw HID interface not found "
                     "(is VIA holding it? close the usevia.app tab)")


def send(*payloads):
    """Write one or more reports through a SINGLE device open.

    Batching matters for more than efficiency. The firmware repaints the text
    band from its ~10 Hz housekeeping tick, so two reports that straddle a tick
    boundary produce TWO full-band clear-and-redraw cycles -- a visible double
    flash on every track change. Issued back to back through one open they are
    ~1 ms apart and always land in the same tick, so the band repaints once.
    """
    h = open_device()
    try:
        for payload in payloads:
            # QMK raw HID expects a 32-byte report; leading 0 is the report id.
            h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))
    finally:
        h.close()


def push_line(line, text, icon="none"):
    """Set one line of the two-line slot.

    Line 0 sits beside the transport icon (19 chars); line 1 runs the full
    width (21). The producer decides what goes where -- nowplaying-macos.sh
    puts the ARTIST on line 0 and the TITLE on line 1, so the title gets the
    two extra characters.

    A second line needs its own packet: 32 bytes leaves ~27 for ASCII after
    framing, and two lines would be 40. Torn updates are harmless --
    the lines are independently meaningful and the poll interval is 3 s."""
    send(_line_packet(line, text, icon))


def _line_packet(line, text, icon="none"):
    body = to_ascii(text)[:MAXLEN[line]].encode("ascii", "replace")
    return [SET_VALUE, TEXT_CHANNEL, TEXT_SET_LINE, line, ICONS[icon]] + list(body)


def push_playback(state, pos, dur):
    """Playback position, drawn in place of the clock while playing.

    state 0 hands the band back to the clock. Seconds are 16-bit big-endian --
    18.2 hours, past any track. The firmware advances pos itself once a second,
    so this only has to re-assert the truth every few seconds; that is what
    makes it read as a running timer instead of a value that jumps per poll.
    """
    pos = max(0, min(0xFFFF, int(pos)))
    dur = max(0, min(0xFFFF, int(dur)))
    send([SET_VALUE, TEXT_CHANNEL, TEXT_PLAYBACK, 1 if state else 0,
          pos >> 8, pos & 0xFF, dur >> 8, dur & 0xFF])


def push_both(line0, line1, icon="none"):
    """Both lines in one device open, so the band repaints once. See send()."""
    send(_line_packet(0, line0, icon), _line_packet(1, line1, icon))


def push(icon="none", text=""):
    """Reusable entry point for producer scripts (avoids a subprocess per
    update, which matters more on Windows). icon is a key of ICONS."""
    if not text and icon == "none":
        send([SET_VALUE, TEXT_CHANNEL, TEXT_CLEAR])
        return
    # TEXT_SET is line 0 in the firmware, so it carries line 0's budget.
    body = to_ascii(text)[:MAXLEN[0]].encode("ascii", "replace")
    send([SET_VALUE, TEXT_CHANNEL, TEXT_SET, ICONS[icon]] + list(body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--icon", default="none", choices=list(ICONS))
    ap.add_argument("--line", type=int, default=None,
                    help="0 = the line beside the transport icon, 1 = the "
                         "full-width line below it; omit for the legacy "
                         "single-line set")
    ap.add_argument("--line1", default=None,
                    help="text for line 1, sent WITH the positional text (line 0) "
                         "in one device open so the band repaints once")
    ap.add_argument("--playback", nargs=3, metavar=("STATE", "POS", "DUR"),
                    help="playback readout: STATE 1=playing 0=hand back to the "
                         "clock, POS and DUR in whole seconds")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    if a.clear:
        send([SET_VALUE, TEXT_CHANNEL, TEXT_CLEAR])
        return
    if a.playback:
        push_playback(int(a.playback[0]), float(a.playback[1]), float(a.playback[2]))
        return
    if a.line1 is not None:
        push_both(a.text, a.line1, a.icon)
    elif a.line is not None:
        push_line(a.line, a.text, a.icon)
    else:
        push(a.icon, a.text)


if __name__ == "__main__":
    # A busy interface is an ordinary, recoverable condition -- VIA has the
    # device, or another poller is mid-push -- and a poller retries in seconds.
    # Dumping a 15-line traceback per failure buried the ONE line that actually
    # diagnoses it (a stray second poller) under thousands of identical stacks.
    # One line, and the exit status still says it failed.
    try:
        main()
    except hid.HIDException as e:
        msg = str(e)
        if "already open" in msg:
            msg = "interface busy (VIA, or another poller is running)"
        print(f"ak820text: {msg}", file=sys.stderr)
        raise SystemExit(1)
