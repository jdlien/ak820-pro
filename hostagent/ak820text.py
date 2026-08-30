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

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61        # QMK raw HID
SET_VALUE, TEXT_CHANNEL, TEXT_SET, TEXT_CLEAR = 0x07, 0x12, 0x01, 0x02
MAXLEN = 12                              # 128px band / 10px glyph advance
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
    import hid
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            return hid.Device(path=d["path"])
    raise SystemExit("raw HID interface not found "
                     "(is VIA holding it? close the usevia.app tab)")


def send(payload):
    h = open_device()
    try:
        # QMK raw HID expects a 32-byte report; leading 0 is the report id.
        h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))
    finally:
        h.close()


def push(icon="none", text=""):
    """Reusable entry point for producer scripts (avoids a subprocess per
    update, which matters more on Windows). icon is a key of ICONS."""
    if not text and icon == "none":
        send([SET_VALUE, TEXT_CHANNEL, TEXT_CLEAR])
        return
    body = to_ascii(text)[:MAXLEN].encode("ascii", "replace")
    send([SET_VALUE, TEXT_CHANNEL, TEXT_SET, ICONS[icon]] + list(body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--icon", default="none", choices=list(ICONS))
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    if a.clear:
        send([SET_VALUE, TEXT_CHANNEL, TEXT_CLEAR])
        return
    push(a.icon, a.text)


if __name__ == "__main__":
    main()
