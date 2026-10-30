#!/usr/bin/env python3
"""Back up and restore the AK820 Pro's settings profiles and live settings
across a flash, over raw HID (HC_PROFILES, P5a of
plans/SETTINGS-PROFILES-PLAN.md).

A flash erases the emulated EEPROM: the profile slots, and with them the
settings every flash used to reset (the screen level, the clock format, the
indicators, the battery readout, the power mode). This saves both before and
writes both back after. flash.sh runs it beside the keymap's backup, and the
live record is then its one authoritative RGB restore, in place of
ak820lighting.py's.

The command is [SET_VALUE 0x07, HEALTH_CHANNEL 0x13, HC_PROFILES 0x10, sub, ...]
(menu/profiles.c has the framing):
    0 read a 26 B page of the block
    1 begin a restore (a token; the board clears the block's magic)
    2 write a page, in order (the magic's byte is the board's, never the host's)
    3 commit (every page; each record valid; the board writes the magic last)
    4 read the live settings as a 27 B record
    5 apply a live record
    6 flush the deferred settings writes
    7 the geometry (P5d): slots, record and page sizes, pages, the magic, and
      (10-27) the side of the Win/Mac switch the profiles go by

The block: the magic, the active slot, then the records. P5a and P5b had
four slots (110 B, five pages, magic 0xA1) and answer 7 unhandled; P5d has
eight (218 B, nine pages, magic 0xA2). Since 10-27 (magic 0xA3, eight slots)
the active byte holds a slot for each side of the Win/Mac switch: bits 0-3
Windows', 4-7 the Mac's, 0xF none. Later that day (magic 0xA4) the block keeps
its eight records but seven are profiles: the eighth is the last record, the
other side's settings as it was left (state 0x10 | the side, a profile's
fields without the name). A backup of any restores onto any: four into eight
as the first four slots, eight into four only when slots 5-8 are empty; onto
0xA4 a profile in slot 8 moves to the first empty of 1-7 (refused when none
is); off 0xA4 the last record is dropped; one active slot into the pair as
both sides', the pair into one as Windows' (else the Mac's).

Since 10-28 the live record's battery-readout byte carries the menu's face in
bit 2 (set Small, clear Large; the readout in bits 0-1); profiles never carry
it. The backup keeps the bit as read and the restore sends it as kept. A
firmware from before the Font setting refuses a live record with the bit set
(its readout's range is 1-3), so the restore then sends it once more without
the bit: everything but the face, which that firmware doesn't have.

Since 10-30 the readout can be Icon only: bit 4 of the same byte, bits 0-1
clear, in the live record and in profiles alike. A firmware from before it
refuses that, so the restore sends the record (or the block) once more with
Percent in its place, and then, if it is refused again, without the face.

Usage:
    ak820profiles.py dump    [file]   # default ~/Documents/ak820pro-profiles.json
    ak820profiles.py restore [file] [--block-only | --live-only]
    ak820profiles.py show    [file]   # the board's, and the file's
    ak820profiles.py fits    [file]   # the backup fits a firmware of seven profiles (flash.sh, before it flashes)

Exit: 0 done; 2 the firmware has no HC_PROFILES (flash.sh then skips it, and
restores the lighting the old way); 3 (fits) the backup holds more profiles
than seven; 4 (restore) the live settings restored, the profiles not (the
reason printed); 1 anything else.

Opens the board through ak820health.open_device(), which never enumerates HID
on Windows (CLAUDE.md). Replies are matched on the channel, command and sub
(and the page or the token where the board echoes them), because Windows
delivers every process's reports to every open handle.
"""
import argparse
import json
import os
import random
import sys
import time

import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
from ak820health import open_device

SET_VALUE, HEALTH_CHANNEL, HC_PROFILES = 0x07, 0x13, 0x10
UNHANDLED = 0xFF                        # RTC_UNHANDLED, == VIA's id_unhandled
DEFAULT = os.path.expanduser("~/Documents/ak820pro-profiles.json")

PAGE, REC, NAME = 26, 27, 12
MAGIC_V1, MAGIC_V2, MAGIC_V3, MAGIC_V4 = 0xA1, 0xA2, 0xA3, 0xA4
SLOTS_OF = {MAGIC_V1: 4, MAGIC_V2: 8, MAGIC_V3: 8, MAGIC_V4: 8}   # the block's records
USER_OF = {MAGIC_V1: 4, MAGIC_V2: 8, MAGIC_V3: 8, MAGIC_V4: 7}    # the profiles among them
FORMAT_OF = {MAGIC_V1: 1, MAGIC_V2: 2, MAGIC_V3: 3, MAGIC_V4: 4}  # a backup's "format"
PAIRED = (MAGIC_V3, MAGIC_V4)                                      # the active byte a side's
LAST, PS_LAST = 7, 0x10                                            # 0xA4's last record: its index, its state | the side
SIDES = {0: None, 1: "windows", 2: "mac"}                          # sub 7's [9]
PF_LIGHTING, PF_LCD, PF_LOCKS, PF_CHARGING, PF_CLOCK, PF_BVIEW, PF_NAME, PF_POWER = (1 << i for i in range(8))
PF_LIVE = 0xBF                          # the live record's fields (subs 4 and 5): the power mode, no name
BV_VIEW, BV_SMALL = 0x03, 0x04          # its readout byte (10-28): the readout, and the menu's face (set Small)
BV_REG = 0x08                           # the third face (10-28): set Regular, Terminus regular
BV_FACE = BV_SMALL | BV_REG
BV_ICON = 0x10                          # Icon only (10-30): bit 4, bits 0-1 clear
VIEWS = {1: "percent", 2: "hours", 3: "both", 4: "icon only"}
# What an older firmware refuses in the readout byte, newest first: the restore drops each in turn.
LIVE_FALLBACKS = ((BV_ICON, "Icon only (a firmware from before it): the live settings sent again with Percent"),
                  (BV_FACE, "the menu's face (a firmware from before the Font setting): "
                            "the live settings sent again without it"))
BLOCK_FALLBACKS = ((BV_ICON, "the profiles' Icon only (a firmware from before it): the profiles sent again with Percent"),
                   (BV_FACE, "the profiles' font (a firmware from before profiles carried it): "
                             "the profiles sent again without it"))
STATUS = {0: "ok", 1: "bad request", 2: "no such restore (token)", 3: "busy (a deep sleep's recovery, or a restore)",
          4: "invalid", 5: "write failed", 6: "incomplete (a page missing)", 7: "unknown record format",
          8: "ok, the effect skipped (this build lacks it)"}

# rgb_effects.c's stable ids (scripts/check_effect_ids.py's REFERENCE), for reading.
EFFECTS = {1: "Solid", 2: "Alphas/Mods", 3: "Breathing", 4: "Cycle All", 5: "Cycle L-R",
           6: "Cycle U-D", 7: "Chevron", 8: "Pinwheel", 9: "Jellybean", 10: "Heatmap", 11: "Rainfall", 12: "Drift"}
CLOCKS = ["24h:ss", "12h:ss", "off", "date", "24h", "12h"]   # enum display_clock_mode
POWER = ["Always on", "Balanced", "Power saver", "Lights out"]


class Unhandled(Exception):
    pass


def crc8(b):
    """CRC-8, polynomial 0x07, initial 0xFF, MSB first: profiles.c's."""
    c = 0xFF
    for x in b:
        c ^= x
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def rec_ok(r):
    return r[0] == 0x01 and r[26] == crc8(r[1:26])


class Geometry:
    """The board's block: P5d's answer to sub 7, or P5a's four slots; the
    switch's side (10-27; None before, or before its first reading)."""
    def __init__(self, slots, magic, side=None):
        self.slots, self.magic, self.side = slots, magic, side
        self.size = 2 + slots * REC
        self.pages = (self.size + PAGE - 1) // PAGE


def geometry(h):
    try:
        r = xfer(h, 7)
    except Unhandled:
        return Geometry(4, MAGIC_V1)    # P5a and P5b; a build without HC_PROFILES fails at the first read
    if r[5] != REC or r[7] != PAGE or SLOTS_OF.get(r[8]) != r[4] or Geometry(r[4], r[8]).pages != r[6]:
        raise SystemExit(f"the board's profile geometry is new to this tool: {r[4:9].hex()}")
    return Geometry(r[4], r[8], SIDES.get(r[9]))


def block_slots(block):
    """A block's slot count, from its size (an unformatted one's magic is 0)."""
    for n in SLOTS_OF.values():
        if len(block) == 2 + n * REC:
            return n
    raise SystemExit(f"a profile block of {len(block)} B is no known size")


def active_as(a, src, dst):
    """The active byte from magic src's encoding to dst's: one slot (0xA1,
    0xA2; 0xFF none) or the pair (0xA3, 0xA4, 10-27: bits 0-3 Windows', 4-7
    the Mac's, 0xF none). One slot becomes both sides'; the pair, Windows'
    slot, else the Mac's."""
    if (src in PAIRED) == (dst in PAIRED):
        return a
    if dst in PAIRED:
        s = a if a < 0xF else 0xF
        return s | s << 4
    for s in (a & 0xF, a >> 4):
        if s != 0xF:
            return s
    return 0xFF


def convert(block, g):
    """A backup's block for this board's geometry: four slots into eight as
    the first four; eight into four only when slots 5-8 are empty; onto 0xA4
    a profile in slot 8 moved to the first empty of 1-7, the active byte
    following it; off 0xA4 the last record dropped; the active byte in the
    board's encoding (active_as())."""
    n = block_slots(block)
    recs = [block[2 + s * REC:2 + (s + 1) * REC] for s in range(n)]
    if block[0] not in SLOTS_OF:
        recs = recs[:g.slots] + [bytes(REC)] * (g.slots - len(recs))
        return bytes([block[0], block[1]]) + b"".join(recs)
    src, a = block[0], block[1]
    if src == MAGIC_V4 and g.magic != MAGIC_V4:
        recs[LAST] = bytes(REC)                     # the last record: no older firmware reads one
    if n > g.slots:
        if any(r[0] != 0 for r in recs[g.slots:]):
            raise SystemExit(f"the backup holds profiles in slots {g.slots + 1}-{n}, which this firmware lacks -- "
                             "restore it onto a firmware with eight slots, or flash with --no-profiles")
        recs = recs[:g.slots]
    recs += [bytes(REC)] * (g.slots - len(recs))
    a = active_as(a, src, g.magic)
    if g.magic == MAGIC_V4 and src != MAGIC_V4 and recs[LAST][0] != 0:
        free = [s for s in range(LAST) if recs[s][0] == 0]
        if not free:
            raise SystemExit("the backup holds eight profiles; this firmware keeps seven (the eighth record is the "
                             "other side's settings) -- delete one first, or flash with --no-profiles")
        recs[free[0]], recs[LAST] = recs[LAST], bytes(REC)
        a = sum((free[0] if (a >> sh & 0xF) == LAST else a >> sh & 0xF) << sh for sh in (0, 4))
    return bytes([g.magic, a]) + b"".join(recs)


def normalized(block):
    """The block as the board's commit leaves it: an active slot that points
    at an empty slot, or past the profiles, reads none (0xFF; since 10-27
    each side's nibble, 0xF)."""
    b = bytearray(block)
    n = USER_OF.get(b[0], block_slots(block))

    def saved(s):
        return s < n and b[2 + s * REC] != 0

    if b[0] in PAIRED:
        b[1] = sum((s if saved(s) else 0xF) << sh for sh in (0, 4) for s in [b[1] >> sh & 0xF])
    elif not saved(b[1]):
        b[1] = 0xFF
    return bytes(b)


def xfer(h, sub, body=b"", echo=(), overall_s=3.0):
    """One request; the reply that answers it. `echo` lists the byte offsets
    (beyond 1-3) the board leaves as sent, which the match also checks."""
    req = bytes([SET_VALUE, HEALTH_CHANNEL, HC_PROFILES, sub]) + bytes(body)
    req += bytes(32 - len(req))
    h.write(bytes([0x00]) + req)
    deadline = time.monotonic() + overall_s
    while time.monotonic() < deadline:
        r = h.read(32, 500)
        if not r or len(r) < 32:
            continue
        r = bytes(r)
        if r[1:4] != req[1:4] or any(r[i] != req[i] for i in echo):
            continue                    # another process's report
        if r[0] == UNHANDLED:
            raise Unhandled()
        if r[0] == SET_VALUE:
            return r
    raise SystemExit(f"no reply to HC_PROFILES sub {sub} in {overall_s:g}s -- is something else "
                     "holding the board (usevia.app, a script)? `ak820 status` shows the agents.")


def busy_retry(fn, what):
    """A deep sleep's recovery refuses writes for a few passes: retry briefly."""
    for _ in range(10):
        st = fn()
        if st != 3:
            return st
        time.sleep(0.5)
    raise SystemExit(f"{what}: the board stayed busy")


def read_block(h, g):
    out = bytearray()
    for p in range(g.pages):
        r = xfer(h, 0, [p], echo=(4,))
        if r[5] != 0:
            raise SystemExit(f"read of page {p} refused: {STATUS.get(r[5], r[5])}")
        out += r[6:6 + min(PAGE, g.size - p * PAGE)]
    return bytes(out)


def read_live(h):
    r = xfer(h, 4)
    if r[31] != 0:
        raise SystemExit(f"live read refused: {STATUS.get(r[31], r[31])}")
    live = r[4:4 + REC]
    if not rec_ok(live):
        raise SystemExit("the board's live record failed its own crc -- refusing to save it")
    return live


def write_block(h, block, g, may_refuse=False):
    """The block, page by page, then the commit. may_refuse: a commit refused
    as out of range (4) is returned, not raised, for the caller's retry."""
    token = random.randint(1, 255)
    st = busy_retry(lambda: xfer(h, 1, [0, token], echo=(5,))[6], "begin")
    if st != 0:
        raise SystemExit(f"restore refused at begin: {STATUS.get(st, st)}")
    for p in range(g.pages):            # in order: P5d's board refuses a page past a gap
        data = block[p * PAGE:(p + 1) * PAGE]
        st = busy_retry(lambda: xfer(h, 2, bytes([p, token]) + data, echo=(4, 5))[6], f"page {p}")
        if st != 0:
            raise SystemExit(f"restore refused at page {p}: {STATUS.get(st, st)}")
    st = busy_retry(lambda: xfer(h, 3, [0, token], echo=(5,))[6], "commit")
    if st == 4 and may_refuse:
        return st
    if st != 0:
        raise SystemExit(f"restore refused at commit: {STATUS.get(st, st)} (the board's profiles read as empty)")


def bv_without(v, bits):
    """A readout byte with `bits` taken out: the face's (BV_FACE), and Icon
    only's (BV_ICON, 10-30), which goes as Percent."""
    if bits & BV_ICON and v & BV_ICON:
        v = (v & ~BV_ICON & 0xFF) | 1
    return v & ~(bits & BV_FACE) & 0xFF


def block_has(block, bits):
    """Whether any record in the block has any of `bits` in its readout byte."""
    return any(block[2 + s * REC] != 0 and block[2 + s * REC + 12] & bits for s in range(block_slots(block)))


def block_faces(block):
    """Whether any record in the block carries the menu's face (10-28)."""
    return block_has(block, BV_FACE)


def block_without(block, bits):
    """The block with `bits` taken out of every record's readout byte
    (bv_without), each crc taken again: for a firmware from before them, which
    refuses a record with them at the commit."""
    b = bytearray(block)
    for s in range(block_slots(block)):
        o = 2 + s * REC
        if b[o] != 0 and b[o + 12] & bits:
            b[o + 12] = bv_without(b[o + 12], bits)
            b[o + 26] = crc8(b[o + 1:o + 26])
    return bytes(b)


def block_without_faces(block):
    """The block with every record's face taken out (10-28)."""
    return block_without(block, BV_FACE)


def rec_without(live, bits):
    """The live record with `bits` taken out of its readout byte (bv_without),
    the crc taken again over bytes 1-25."""
    r = bytearray(live)
    r[12] = bv_without(r[12], bits)
    r[26] = crc8(r[1:26])
    return bytes(r)


def without_face(live):
    """The live record with the menu's face taken out of its readout byte (10-28)."""
    return rec_without(live, BV_FACE)


def apply_live(h, live):
    """Sub 5, then the flush. Returns the apply's status and the record the
    board took: a firmware from before Icon only (10-30) refuses one with its
    bit, and one from before the Font setting (10-28) one with the face's bit
    set (and one from before Regular, bit 3), so that is sent once more
    without each, newest first."""
    st = busy_retry(lambda: xfer(h, 5, live)[31], "apply")
    for bits, what in LIVE_FALLBACKS:
        if st == 4 and live[12] & bits:
            live = rec_without(live, bits)
            print(f"  the board refused {what}")
            st = busy_retry(lambda: xfer(h, 5, live)[31], "apply")
    if st not in (0, 8):
        raise SystemExit(f"live settings refused: {STATUS.get(st, st)}")
    applied = st
    st = busy_retry(lambda: xfer(h, 6)[4], "flush")
    if st != 0:
        raise SystemExit(f"flush refused: {STATUS.get(st, st)}")
    return applied, live


# --- Reading a record ----------------------------------------------------------

def decode(r):
    f = r[1]
    d = {}
    if f & PF_LIGHTING:
        d["lighting"] = {"on": bool(r[2]), "effect": EFFECTS.get(r[3], f"id {r[3]}"), "effect_id": r[3],
                         "hue": r[4], "sat": r[5], "val": r[6], "speed": r[7]}
    if f & PF_LCD:
        d["screen"] = r[8]
    if f & PF_LOCKS:
        d["lock_lights"] = r[9]
    if f & PF_CHARGING:
        d["charging_light"] = r[10]
    if f & PF_CLOCK:
        d["clock"] = CLOCKS[r[11]] if r[11] < len(CLOCKS) else r[11]
    if f & PF_BVIEW:
        v = r[12]
        if not v & ~(BV_VIEW | BV_FACE | BV_ICON) and (v & BV_FACE) != BV_FACE and not (v & BV_ICON and v & BV_VIEW):
            d["font"] = "small" if v & BV_SMALL else "regular" if v & BV_REG else "large"   # 10-28: every record's
            v = 4 if v & BV_ICON else v & BV_VIEW                                           # 10-30: Icon only
        d["battery"] = VIEWS.get(v, v)
    if f & PF_POWER:
        d["power"] = POWER[r[13]] if r[13] < len(POWER) else r[13]
    if f & PF_NAME:
        d["name"] = bytes(r[14:26]).split(b"\0")[0].decode("ascii", "replace")
    return d


def decode_block(b):
    if SLOTS_OF.get(b[0]) != block_slots(b):
        return {"formatted": False}
    slots = []
    for s in range(USER_OF[b[0]]):
        r = b[2 + s * REC:2 + (s + 1) * REC]
        if r[0] == 0:
            slots.append(None)
        elif not rec_ok(r):
            slots.append("damaged")
        else:
            d = decode(r)
            d["name"] = d.get("name") or f"Profile {s + 1}"
            slots.append(d)
    def active(s):
        return s + 1 if s < len(slots) and isinstance(slots[s], dict) else None

    a = b[1]
    if b[0] not in PAIRED:
        return {"formatted": True, "active": active(a), "slots": slots}
    d = {"formatted": True, "active": {"windows": active(a & 0xF), "mac": active(a >> 4)}, "slots": slots}
    if b[0] == MAGIC_V4:   # 10-27: the last record, the other side's settings as left
        r = b[2 + LAST * REC:2 + (LAST + 1) * REC]
        if r[0] == 0:
            d["last"] = None
        elif r[0] & ~1 != PS_LAST or r[26] != crc8(r[1:26]):
            d["last"] = "damaged"
        else:
            d["last"] = dict(decode(r), side="mac" if r[0] & 1 else "windows")
    return d


def describe(doc):
    lines = []
    blk = doc.get("decoded", {}).get("block", {})
    act = blk.get("active")
    if not blk.get("formatted"):
        lines.append("profiles: none saved")
    else:
        if isinstance(act, dict):
            side = {"windows": "Windows", "mac": "the Mac"}.get(doc.get("switch"))
            lines.append("profiles (W, M: the slot each side of the Win/Mac switch loads"
                         + (f"; the switch on {side}" if side else "") + "):")
        for i, s in enumerate(blk["slots"]):
            if isinstance(act, dict):
                mark = ("W" if act.get("windows") == i + 1 else " ") + ("M" if act.get("mac") == i + 1 else " ")
            else:
                mark = "* " if act == i + 1 else "  "
            if s is None:
                lines.append(f" {mark} slot {i + 1}: empty")
            elif s == "damaged":
                lines.append(f" {mark} slot {i + 1}: damaged (reads as empty)")
            else:
                l = s.get("lighting", {})
                lines.append(f" {mark} slot {i + 1}: {s['name']}: {l.get('effect')} h{l.get('hue')} s{l.get('sat')} "
                             f"v{l.get('val')}, screen {s.get('screen')}%, clock {s.get('clock')}")
        last = blk.get("last")
        if isinstance(last, dict):
            l = last.get("lighting", {})
            lines.append(f"    {'Windows' if last['side'] == 'windows' else 'the Mac'}'s settings as left: "
                         f"{l.get('effect')} h{l.get('hue')} s{l.get('sat')} v{l.get('val')}, screen "
                         f"{last.get('screen')}%, clock {last.get('clock')}")
        elif last == "damaged":
            lines.append("    the other side's settings as left: damaged (reads as none)")
    lv = doc.get("decoded", {}).get("live")
    if lv:
        l = lv.get("lighting", {})
        lines.append(f"live: {l.get('effect')} {'on' if l.get('on') else 'off'} h{l.get('hue')} s{l.get('sat')} "
                     f"v{l.get('val')} speed {l.get('speed')}, screen {lv.get('screen')}%, locks {lv.get('lock_lights')}, "
                     f"charging {lv.get('charging_light')}, clock {lv.get('clock')}, battery {lv.get('battery')}, "
                     + (f"font {lv['font']}, " if "font" in lv else "") + f"power {lv.get('power')}")
    return "\n".join(lines)


def snapshot(h):
    g = geometry(h)
    block, live = read_block(h, g), read_live(h)
    return {
        "_comment": f"AK820 Pro settings profiles (the EEPROM's top {g.size} B, {g.slots} slots) and the live "
                    "settings, as HC_PROFILES reads them. Restore with ak820profiles.py restore.",
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": FORMAT_OF[g.magic],   # 2: P5d's eight slots; 3: the active byte a side's; 4: seven and the last (10-27)
        "switch": g.side,
        "block": block.hex(),
        "live": live.hex(),
        "decoded": {"block": decode_block(block), "live": decode(live)},
    }


# --- The commands ----------------------------------------------------------------

def cmd_dump(path):
    h = open_device()
    try:
        doc = snapshot(h)
    finally:
        h.close()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)               # never truncate a good backup on failure
    print(f"profiles and live settings saved to {path}")
    print(describe(doc))
    return 0


def cmd_restore(path, block_only, live_only):
    if not os.path.exists(path):
        print(f"no profiles backup at {path} -- nothing to restore")
        return 0
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    fmt = doc.get("format")
    if fmt not in (1, 2, 3, 4):
        raise SystemExit(f"{path} is format {fmt}; this tool reads 1 to 4")
    block, live = bytes.fromhex(doc["block"]), bytes.fromhex(doc["live"])
    if len(block) != 2 + (4 if fmt == 1 else 8) * REC or len(live) != REC or not rec_ok(live):
        raise SystemExit(f"{path} is malformed -- refusing")
    h = open_device()
    block_err = None
    try:
        g = geometry(h)
        if not live_only:
            want = None
            if SLOTS_OF.get(block[0]) == block_slots(block):
                try:   # codex (10-27): a backup that won't fit leaves the live settings to restore all the same
                    want = convert(block, g)
                except SystemExit as e:
                    block_err = str(e)
                    print(f"profiles NOT restored: {block_err}")
            if want is not None:
                st = write_block(h, want, g, may_refuse=block_has(want, BV_ICON | BV_FACE))
                for bits, what in BLOCK_FALLBACKS:   # newest first, as apply_live's
                    if st == 4 and block_has(want, bits):
                        want = block_without(want, bits)
                        print(f"  the board refused {what}")
                        st = write_block(h, want, g, may_refuse=block_has(want, BV_ICON | BV_FACE))
                if st == 4:
                    raise SystemExit("restore refused at commit: invalid (the board's profiles read as empty)")
                if read_block(h, g) != normalized(want):
                    raise SystemExit("the profiles' read-back differs from the backup -- the restore did not land")
                note = f" ({block_slots(block)} slots into {g.slots})" if block_slots(block) != g.slots else ""
                print(f"profiles restored and read back{note}")
            elif block_err is None:
                print("profiles: none in the backup, the board's left unformatted")
        if not block_only:
            st, sent = apply_live(h, live)   # sent: without the face when an older firmware refused it
            back = read_live(h)
            note = ", the effect skipped (this build lacks it)" if st == 8 else ""
            if back[1:26] != sent[1:26] and st != 8:
                print("  note: the live settings read back differently -- the board clamped something:")
                print("  asked " + json.dumps(decode(sent)))
                print("  got   " + json.dumps(decode(back)))
            print(f"live settings restored and flushed{note}")
        doc_now = {"switch": g.side, "decoded": {"block": decode_block(read_block(h, g)), "live": decode(read_live(h))}}
    finally:
        h.close()
    print(describe(doc_now))
    if block_err:
        if block_only:   # codex (10-27): nothing restored, so not 4
            print(f"the profiles stay in {path}; nothing was restored")
            return 1
        print(f"the profiles stay in {path}; the live settings were restored")
        return 4
    return 0


def held(doc):
    """A backup's saved profiles: those whose record isn't empty."""
    block = bytes.fromhex(doc["block"])
    if SLOTS_OF.get(block[0]) != block_slots(block):
        return 0
    return sum(1 for s in range(USER_OF[block[0]]) if block[2 + s * REC] != 0)


def cmd_fits(path):
    """flash.sh's check before it flashes (codex, 10-27): a backup of eight
    profiles from a firmware before 0xA4 won't fit one of seven, and the
    flash would erase them with no way to restore."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    n = held(doc)
    if n > USER_OF[MAGIC_V4]:
        print(f"the backup holds {n} profiles; a firmware since 10-27 keeps {USER_OF[MAGIC_V4]} (the eighth record "
              "is the other side of the Win/Mac switch's settings)")
        return 3
    return 0


def cmd_show(path):
    h = open_device()
    try:
        doc = snapshot(h)
    finally:
        h.close()
    print("board:")
    print(describe(doc))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        same = saved.get("block") == doc["block"] and saved.get("live") == doc["live"]
        print(f"\nbackup ({saved.get('saved', '?')}, {'same' if same else 'DIFFERENT'}):")
        print(describe(saved))
    else:
        print(f"\nbackup: none at {path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["dump", "restore", "show", "fits"])
    ap.add_argument("file", nargs="?", default=DEFAULT)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--block-only", action="store_true", help="restore the profile slots, not the live settings")
    g.add_argument("--live-only", action="store_true", help="restore the live settings, not the profile slots")
    a = ap.parse_args()
    try:
        if a.action == "dump":
            return cmd_dump(a.file)
        if a.action == "restore":
            return cmd_restore(a.file, a.block_only, a.live_only)
        if a.action == "fits":
            return cmd_fits(a.file)
        return cmd_show(a.file)
    except Unhandled:
        print("this firmware has no HC_PROFILES (before P5a): profiles skipped")
        return 2


if __name__ == "__main__":
    sys.exit(main())
