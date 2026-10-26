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
import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
import ak820text       # the one safe opener; see open_device() below

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61          # QMK raw HID

# VIA command ids (quantum/via.h). Protocol version 0x000C on this firmware.
GET_PROTOCOL      = 0x01
GET_LAYER_COUNT   = 0x11
GET_BUFFER        = 0x12
SET_BUFFER        = 0x13
GET_ENCODER       = 0x14
SET_ENCODER       = 0x15
GET_MACRO_SIZE    = 0x0D
GET_MACRO_BUFFER  = 0x0E
SET_MACRO_BUFFER  = 0x0F

ROWS, COLS = 6, 15                        # keyboard.json matrix_pins
ENCODERS   = 1
CHUNK      = 28                           # 32-byte report minus the 4-byte header
DEFAULT    = os.path.expanduser("~/Documents/ak820pro-keymap.json")


def open_device():
    """Reuse ak820text's opener rather than enumerating here.

    ⚠️ `hid.enumerate()` opens EVERY HID device on the machine, which twice
    wedged the APC UPS attached to this one
    (`../jdrgb/docs/ups-wedge-incident.md`); that UPS is still attached, and
    this tool ran unguarded until 2026-09-27. ak820text's version is the fixed
    one -- cached path, exponential backoff and a mains-settle gate -- and
    `ak820lighting.py` already shares it. So this is the third caller of one
    safe opener rather than a third copy of the hazard (`plans/BACKLOG.md`).

    It matches the same way this did: on usage page/usage, because the board
    publishes several HID interfaces and only 0xFF60/0x61 is QMK raw HID.
    """
    return ak820text.open_device()


def xfer(h, payload, read_ms=500, overall_s=5.0):
    """One request/response round trip, correlated against the request.

    ⚠️ Windows delivers HID input reports to EVERY open handle (CLAUDE.md), so
    the daemon's now-playing echo (`07 12 04`, every ~3 s) lands here too. The
    first-byte check this had refused it -- "unexpected reply 0x07 to command
    0x12" -- which failed flash.sh's backup on 2026-10-19 with the daemon
    running. The command byte alone is not enough either: a GET_BUFFER reply
    for another process's offset is also 0x12. VIA echoes each request's
    header (command, then offset/size or layer/index/direction), so the reply
    must match the request's first four bytes, or all of a shorter one; other
    reports are discarded and the wait goes on. ak820lighting.py's xfer is the
    same idea.
    """
    want = bytes(payload[:4])
    h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))
    deadline = time.monotonic() + overall_s
    others = 0
    while time.monotonic() < deadline:
        r = h.read(32, read_ms)
        if not r:
            continue
        if bytes(r[:len(want)]) == want:
            return bytes(r)
        others += 1
    if others:
        raise SystemExit(
            f"no reply to {want.hex(' ').upper()} in {overall_s:g}s, "
            f"though {others} report(s) for other requests arrived.\n"
            "  Something else is talking to the board -- close usevia.app, or pause\n"
            "  the host agents (`ak820 status` shows them).")
    raise SystemExit(
        "no reply from the board.\n"
        "  The usual cause is BLUETOOTH MODE, not a busy interface -- raw HID\n"
        "  replies route through the active host driver, so set the dip switch\n"
        "  to `cable` and try again. (VIA holding the interface also does it.)")


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


def macro_size(h):
    r = xfer(h, [GET_MACRO_SIZE])
    return (r[1] << 8) | r[2]


def read_macros(h):
    """VIA's macro buffer, whole. Since the settings profiles (P5a,
    plans/SETTINGS-PROFILES-PLAN.md, "Macros") it's 127 B, not 237: the
    profiles took the EEPROM's top 110 B. So the backup carries it."""
    size, buf, off = macro_size(h), bytearray(), 0
    while off < size:
        n = min(CHUNK, size - off)
        r = xfer(h, [GET_MACRO_BUFFER, (off >> 8) & 0xFF, off & 0xFF, n])
        buf += r[4:4 + n]
        off += n
    return bytes(buf)


def macros_used(buf):
    """The bytes the macros use: to the last non-zero one, and its NUL. The
    buffer's last byte is QMK's validity flag (dynamic_keymap.h), not a macro."""
    n = len(buf[:-1].rstrip(b"\0")) if buf else 0
    return buf[:n + 1] if n else b""


def write_macros(h, used, size):
    """QMK's rule (dynamic_keymap.h): the last byte non-zero first, so a cut
    transfer leaves the macros disabled, then the contents, then the last
    byte zero. The rest of the buffer is written empty."""
    last = size - 1
    xfer(h, [SET_MACRO_BUFFER, (last >> 8) & 0xFF, last & 0xFF, 1, 0xFF])
    data, off = used + bytes(last - len(used)), 0
    while off < last:
        n = min(CHUNK, last - off)
        xfer(h, [SET_MACRO_BUFFER, (off >> 8) & 0xFF, off & 0xFF, n] + list(data[off:off + n]))
        off += n
    xfer(h, [SET_MACRO_BUFFER, (last >> 8) & 0xFF, last & 0xFF, 1, 0x00])


def cmd_dump(path):
    h = open_device()
    try:
        proto  = xfer(h, [GET_PROTOCOL])
        layers = xfer(h, [GET_LAYER_COUNT])[1]
        km     = read_keymap(h, layers)
        enc    = read_encoders(h, layers)
        macros = read_macros(h)
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
        "macros":           macros.hex(),
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)                 # never truncate a good backup on failure
    print(f"saved {len(km)} bytes, {layers} layers, {len(enc[0]) if enc else 0} encoder(s), "
          f"{len(macros_used(macros))} of {len(macros)} macro bytes used -> {path}")


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
        # The macros, checked before anything is written: a backup whose
        # macros don't fit this firmware's buffer (127 B since the profiles)
        # is refused whole, and the file kept for its owner to trim.
        used = macros_used(bytes.fromhex(doc["macros"])) if doc.get("macros") else b""
        msize = macro_size(h) if used else 0
        if used and len(used) > msize - 1:
            raise SystemExit(f"the backup's macros use {len(used)} bytes, and this firmware's macro buffer holds "
                             f"{msize - 1} -- refusing; trim them in {path} or in VIA, then restore")
        write_keymap(h, km)
        if doc.get("encoders"):
            write_encoders(h, doc["encoders"])
        # Read it all back: a write that did not land must not pass for one
        # (codex, Phase 2: flash.sh's `show` afterwards reads the FILE).
        back = read_keymap(h, layers)
        if back != km:
            bad = next(i for i in range(len(km)) if back[i] != km[i]) // 2
            raise SystemExit(f"read-back differs from {path} at keycode {bad} -- the restore did not land")
        if doc.get("encoders") and read_encoders(h, layers) != doc["encoders"]:
            raise SystemExit(f"encoder read-back differs from {path} -- the restore did not land")
        if used:
            write_macros(h, used, msize)
            back = read_macros(h)
            if back[:len(used)] != used or back[-1] != 0:
                raise SystemExit(f"macro read-back differs from {path} -- the restore did not land")
    finally:
        h.close()
    print(f"restored {len(km)} bytes across {doc['layers']} layers"
          f"{f', and {len(used)} macro bytes' if used else ''} from {path}, read back and verified")
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
    if "macros" in doc:
        m = bytes.fromhex(doc["macros"])
        print(f"macros   : {len(macros_used(m))} of {len(m)} bytes used")
    else:
        print("macros   : not in this backup (saved before the profiles' P5a)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["dump", "restore", "show"])
    ap.add_argument("file", nargs="?", default=DEFAULT)
    a = ap.parse_args()
    {"dump": cmd_dump, "restore": cmd_restore, "show": cmd_show}[a.action](a.file)


if __name__ == "__main__":
    main()
