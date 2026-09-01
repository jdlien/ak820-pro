#!/usr/bin/env python3
"""Back up and restore the AK820 Pro's VIA keymap over raw HID.

Flashing erases the emulated EEPROM, so every firmware update wipes the VIA
keymap. This dumps it before and restores it after, byte for byte.

It saves the RAW dynamic-keymap buffer rather than VIA's .layout.json, which
means no keycode-name table to keep in sync with QMK: whatever the board holds
is what comes back. VIA's own export stays useful as a portable, human-readable
copy -- this one is for round-tripping.

Usage:
    ak820keymap.py dump    [file]     # default: ~/Documents/ak820pro-keymap.json
    ak820keymap.py restore [file]
    ak820keymap.py show    [file]     # what a saved file contains

⚠️ REQUIRES WIRED MODE. Raw HID *replies* route through the active host driver
(tmk_core/protocol/host.c), so in BT/2.4G mode the answer goes over the air and
the read times out even with the cable plugged in. Set the dip switch to cable.
"""
import argparse, json, os, sys, time
import hid

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61          # QMK raw HID

# VIA command ids (quantum/via.h). Protocol version 0x000C on this firmware.
GET_PROTOCOL      = 0x01
GET_LAYER_COUNT   = 0x11
GET_BUFFER        = 0x12
SET_BUFFER        = 0x13
GET_ENCODER       = 0x14
SET_ENCODER       = 0x15

ROWS, COLS = 6, 15                        # keyboard.json matrix_pins
ENCODERS   = 1
CHUNK      = 28                           # 32-byte report minus the 4-byte header
DEFAULT    = os.path.expanduser("~/Documents/ak820pro-keymap.json")


def open_device():
    """Match on usage page/usage: the board publishes several HID interfaces
    and only 0xFF60/0x61 is QMK raw HID."""
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            return hid.Device(path=d["path"])
    raise SystemExit("raw HID interface not found "
                     "(is VIA holding it? close the usevia.app tab)")


def xfer(h, payload, timeout=1000):
    """One request/response round trip. The reply echoes the command byte."""
    h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))
    r = h.read(32, timeout)
    if not r:
        raise SystemExit(
            "no reply from the board.\n"
            "  The usual cause is BLUETOOTH MODE, not a busy interface -- raw HID\n"
            "  replies route through the active host driver, so set the dip switch\n"
            "  to `cable` and try again. (VIA holding the interface also does it.)")
    if r[0] != payload[0]:
        raise SystemExit(f"unexpected reply 0x{r[0]:02X} to command 0x{payload[0]:02X}")
    return bytes(r)


def read_keymap(h, layers):
    size = layers * ROWS * COLS * 2
    buf, off = bytearray(), 0
    while off < size:
        n = min(CHUNK, size - off)
        r = xfer(h, [GET_BUFFER, (off >> 8) & 0xFF, off & 0xFF, n])
        buf += r[4:4 + n]
        off += n
    return bytes(buf)


def write_keymap(h, data):
    off = 0
    while off < len(data):
        n = min(CHUNK, len(data) - off)
        xfer(h, [SET_BUFFER, (off >> 8) & 0xFF, off & 0xFF, n] + list(data[off:off + n]))
        off += n


def read_encoders(h, layers):
    """Encoders live outside the keymap buffer. Skipping them would silently
    drop the knob's per-layer mapping -- on this board that includes the
    LSA(KC_VOLD/U) fine-volume binding on the Mac layers."""
    out = []
    for layer in range(layers):
        row = []
        for idx in range(ENCODERS):
            pair = []
            for cw in (0, 1):
                r = xfer(h, [GET_ENCODER, layer, idx, cw])
                pair.append((r[4] << 8) | r[5])
            row.append(pair)
        out.append(row)
    return out


def write_encoders(h, enc):
    for layer, row in enumerate(enc):
        for idx, pair in enumerate(row):
            for cw, kc in enumerate(pair):
                xfer(h, [SET_ENCODER, layer, idx, cw, (kc >> 8) & 0xFF, kc & 0xFF])


def cmd_dump(path):
    h = open_device()
    try:
        proto  = xfer(h, [GET_PROTOCOL])
        layers = xfer(h, [GET_LAYER_COUNT])[1]
        km     = read_keymap(h, layers)
        enc    = read_encoders(h, layers)
    finally:
        h.close()

    if not any(km):
        raise SystemExit("refusing to save: the board returned an all-zero keymap "
                         "(KC_NO everywhere), which is not a keymap worth keeping.")

    doc = {
        "_comment": "Raw VIA dynamic-keymap buffer for the AJAZZ AK820 Pro. "
                    "Restore with ak820keymap.py restore.",
        "saved":            time.strftime("%Y-%m-%d %H:%M:%S"),
        "protocol":         (proto[1] << 8) | proto[2],
        "layers":           layers,
        "rows":             ROWS,
        "cols":             COLS,
        "keymap":           km.hex(),
        "encoders":         enc,
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)                 # never truncate a good backup on failure
    print(f"saved {len(km)} bytes, {layers} layers, {len(enc[0]) if enc else 0} encoder(s) -> {path}")


def cmd_restore(path):
    with open(path) as f:
        doc = json.load(f)
    km = bytes.fromhex(doc["keymap"])
    expect = doc["layers"] * doc["rows"] * doc["cols"] * 2
    if len(km) != expect:
        raise SystemExit(f"file is {len(km)} bytes, expected {expect} -- refusing")
    if (doc["rows"], doc["cols"]) != (ROWS, COLS):
        raise SystemExit(f"file is for a {doc['rows']}x{doc['cols']} matrix, "
                         f"this board is {ROWS}x{COLS} -- refusing")
    h = open_device()
    try:
        layers = xfer(h, [GET_LAYER_COUNT])[1]
        if layers != doc["layers"]:
            raise SystemExit(f"board has {layers} layers, file has {doc['layers']} -- refusing")
        write_keymap(h, km)
        if doc.get("encoders"):
            write_encoders(h, doc["encoders"])
    finally:
        h.close()
    print(f"restored {len(km)} bytes across {doc['layers']} layers from {path}")
    print("(VIA reads the keymap at connect -- reload the tab to see it)")


def cmd_show(path):
    with open(path) as f:
        doc = json.load(f)
    km = bytes.fromhex(doc["keymap"])
    print(f"saved    : {doc.get('saved','?')}")
    print(f"layers   : {doc['layers']}   matrix {doc['rows']}x{doc['cols']}   {len(km)} bytes")
    per = doc["rows"] * doc["cols"] * 2
    for l in range(doc["layers"]):
        chunk = km[l * per:(l + 1) * per]
        used = sum(1 for i in range(0, len(chunk), 2)
                   if (chunk[i] << 8 | chunk[i + 1]) not in (0x0000, 0x0001))
        print(f"  layer {l}: {used} keys assigned")
    for l, row in enumerate(doc.get("encoders", [])):
        for i, pair in enumerate(row):
            print(f"  layer {l} encoder {i}: ccw=0x{pair[0]:04X} cw=0x{pair[1]:04X}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["dump", "restore", "show"])
    ap.add_argument("file", nargs="?", default=DEFAULT)
    a = ap.parse_args()
    {"dump": cmd_dump, "restore": cmd_restore, "show": cmd_show}[a.action](a.file)


if __name__ == "__main__":
    main()
