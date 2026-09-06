#!/usr/bin/env python3
"""Back up and restore the board's RGB lighting across a flash.

⚠️ **Why this exists.** Flashing erases the emulated EEPROM, and `flash.sh`
already restores the VIA keymap — but nothing restored the lighting, so every
flash silently reverted the LEDs to `rgb_matrix.default` in `keyboard.json`.
That went unnoticed through all nine flashes of 2026-09-03 (see CLAUDE.md).
The advice since then has been "keep the default equal to your setup", which is
a rule a human has to remember; this is the version the machine does.

Wire format is **VIA's** custom-value protocol, not this project's. They share
one interface and are easy to confuse:

    ours   [0x07 SET_VALUE][channel 0x10-0x13][command][...]
    VIA's  [command id    ][channel 0-4      ][value id][...]

Our channel numbers were chosen above QMK's precisely so the two cannot
collide. `via.json` declares `menus: ["qmk_rgb_matrix"]`, so the values here are
QMK's stock ones on channel 3.

Usage:
    ak820lighting.py dump [path]      # read the board, write JSON
    ak820lighting.py restore [path]   # write JSON back to the board
    ak820lighting.py show [path]      # print what is on the board (and the file)
"""
import argparse, json, os, sys, time

import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing

# ⚠️ Reuse ak820text's opener rather than enumerating again. Its version is the
# FIXED one: cached path, exponential backoff and a mains-settle gate, added
# after `hid_enumerate` -- which opens every HID device on the machine -- twice
# wedged an APC UPS here (../jdrgb/docs/ups-wedge-incident.md). Importing it
# costs nothing and means there is one safe opener rather than three copies.
import ak820text

GET_VALUE = 0x08
SET_VALUE = 0x07
SAVE = 0x09
RGB_MATRIX_CHANNEL = 3

# QMK's stock `via_qmk_rgb_matrix_value` ids.
BRIGHTNESS, EFFECT, SPEED, COLOR = 1, 2, 3, 4

DEFAULT_PATH = os.path.expanduser("~/Documents/ak820pro-lighting.json")


def xfer(h, payload, read_ms=500, overall_s=5.0):
    """One VIA custom-value round trip, correlated against the command sent.

    ⚠️ `ak820keymap.py`'s `xfer` checks only the command id, which cannot work
    here: a brightness reply and an effect reply are both `0x08`, so the id
    alone does not say which question was answered. Measured 2026-09-05,
    Windows delivers HID input reports to **every open handle**, so another
    process's traffic genuinely does arrive mid-transaction -- the now-playing
    agent's `07 12 04` echo lands here every ~3 s. A foreign reply would
    otherwise be decoded as this one, so non-matching reports are discarded and
    the wait continues.

    ⚠️ The key is `payload[:3]` **or the whole payload if it is shorter**, and
    that bit is not decoration. `id_custom_save` is two bytes -- `[0x09,
    channel]`, no value id -- so a fixed three-byte key builds a 2-tuple and
    compares it against a 3-tuple, which can never be equal. That bug made
    every restore write its values correctly and then report failure on the
    commit.

    A read timing out is *not* "no reply": with other traffic on the handle a
    single read can expire while our answer is still coming. Only the overall
    deadline gives up, and it says which of the two it saw.
    """
    n = min(3, len(payload))
    want = tuple(payload[:n])
    h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))

    deadline = time.monotonic() + overall_s
    others = 0
    while time.monotonic() < deadline:
        r = h.read(32, read_ms)
        if not r:
            continue
        if tuple(r[:n]) == want:
            return bytes(r)
        others += 1

    if others:
        raise SystemExit(
            f"no reply to {' '.join(f'{b:02X}' for b in want)} in {overall_s:g}s, "
            f"though {others} report(s) for other requests arrived.\n"
            "  Something else is talking to the board -- close usevia.app, or pause\n"
            "  the host agents (hostagent/install-agents-windows.ps1 -Status).")
    raise SystemExit(
        "no reply from the board.\n"
        "  The usual cause is BLUETOOTH MODE, not a busy interface -- raw HID\n"
        "  replies route through the active host driver, so set the dip switch\n"
        "  to `cable` and try again. (VIA holding the interface also does it.)")


def get(h, value_id):
    return xfer(h, [GET_VALUE, RGB_MATRIX_CHANNEL, value_id])


def read_lighting(h):
    """-> dict, in the same field names `keyboard.json`'s rgb_matrix.default uses."""
    colour = get(h, COLOR)
    return {
        "animation_index": get(h, EFFECT)[3],
        "hue": colour[3],
        "sat": colour[4],
        "val": get(h, BRIGHTNESS)[3],
        "speed": get(h, SPEED)[3],
    }


def write_lighting(h, cfg):
    """Set every value, then commit.

    Order matters only in that the commit comes last. The firmware also
    auto-saves ~0.9 s after values stop moving (that settle is what the LED
    row-flash fix in BACKLOG.md was about), so the explicit save is belt and
    braces rather than the only thing persisting it.
    """
    xfer(h, [SET_VALUE, RGB_MATRIX_CHANNEL, EFFECT, cfg["animation_index"]])
    xfer(h, [SET_VALUE, RGB_MATRIX_CHANNEL, BRIGHTNESS, cfg["val"]])
    xfer(h, [SET_VALUE, RGB_MATRIX_CHANNEL, SPEED, cfg["speed"]])
    xfer(h, [SET_VALUE, RGB_MATRIX_CHANNEL, COLOR, cfg["hue"], cfg["sat"]])
    xfer(h, [SAVE, RGB_MATRIX_CHANNEL])


def describe(cfg):
    return ("effect {animation_index}, hue {hue}, sat {sat}, "
            "val {val}, speed {speed}").format(**cfg)


def cmd_dump(path):
    h = ak820text.open_device()
    try:
        cfg = read_lighting(h)
    finally:
        h.close()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"lighting saved to {path}")
    print(f"  {describe(cfg)}")
    return 0


def cmd_restore(path):
    if not os.path.exists(path):
        print(f"no lighting backup at {path} -- nothing to restore")
        return 0
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    h = ak820text.open_device()
    try:
        before = read_lighting(h)
        if before == cfg:
            print(f"lighting already matches the backup ({describe(cfg)})")
            return 0
        write_lighting(h, cfg)
        after = read_lighting(h)
    finally:
        h.close()

    print(f"lighting restored: {describe(after)}")
    if after != cfg:
        # ⚠️ Not an error. The firmware clamps some values, and an effect index
        # that no longer exists in this build lands somewhere else -- which is
        # exactly what a changed animation set does, since QMK renumbers every
        # effect after one that was enabled or disabled.
        print(f"  note: asked for {describe(cfg)}")
        print("  the board clamped or renumbered something -- check the LEDs.")
    return 0


def cmd_show(path):
    h = ak820text.open_device()
    try:
        cfg = read_lighting(h)
    finally:
        h.close()
    print(f"board : {describe(cfg)}")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        state = "same" if saved == cfg else "DIFFERENT"
        print(f"backup: {describe(saved)}   ({state})")
    else:
        print(f"backup: none at {path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="AK820 Pro RGB lighting backup/restore")
    ap.add_argument("action", choices=["dump", "restore", "show"])
    ap.add_argument("path", nargs="?", default=DEFAULT_PATH)
    a = ap.parse_args()
    return {"dump": cmd_dump, "restore": cmd_restore, "show": cmd_show}[a.action](a.path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
