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
    7 the geometry (P5d): slots, record and page sizes, pages, the magic

The block: the magic, the active slot, then the records. P5a and P5b had
four slots (110 B, five pages, magic 0xA1) and answer 7 unhandled; P5d has
eight (218 B, nine pages, magic 0xA2). A backup of either restores onto
either: four into eight as the first four slots, eight into four only when
slots 5-8 are empty.

Usage:
    ak820profiles.py dump    [file]   # default ~/Documents/ak820pro-profiles.json
    ak820profiles.py restore [file] [--block-only | --live-only]
    ak820profiles.py show    [file]   # the board's, and the file's

Exit: 0 done; 2 the firmware has no HC_PROFILES (flash.sh then skips it, and
restores the lighting the old way); 1 anything else.

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
MAGIC_V1, MAGIC_V2 = 0xA1, 0xA2
SLOTS_OF = {MAGIC_V1: 4, MAGIC_V2: 8}
PF_LIGHTING, PF_LCD, PF_LOCKS, PF_CHARGING, PF_CLOCK, PF_BVIEW, PF_NAME, PF_POWER = (1 << i for i in range(8))
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
    """The board's block: P5d's answer to sub 7, or P5a's four slots."""
    def __init__(self, slots, magic):
        self.slots, self.magic = slots, magic
        self.size = 2 + slots * REC
        self.pages = (self.size + PAGE - 1) // PAGE


def geometry(h):
    try:
        r = xfer(h, 7)
    except Unhandled:
        return Geometry(4, MAGIC_V1)    # P5a and P5b; a build without HC_PROFILES fails at the first read
    if r[5] != REC or r[7] != PAGE or SLOTS_OF.get(r[8]) != r[4] or Geometry(r[4], r[8]).pages != r[6]:
        raise SystemExit(f"the board's profile geometry is new to this tool: {r[4:9].hex()}")
    return Geometry(r[4], r[8])


def block_slots(block):
    """A block's slot count, from its size (an unformatted one's magic is 0)."""
    for n in SLOTS_OF.values():
        if len(block) == 2 + n * REC:
            return n
    raise SystemExit(f"a profile block of {len(block)} B is no known size")


def convert(block, g):
    """A backup's block for this board's geometry: four slots into eight as
    the first four; eight into four only when slots 5-8 are empty."""
    n = block_slots(block)
    recs = [block[2 + s * REC:2 + (s + 1) * REC] for s in range(n)]
    if n > g.slots:
        if any(r[0] != 0 for r in recs[g.slots:]):
            raise SystemExit(f"the backup holds profiles in slots {g.slots + 1}-{n}, which this firmware lacks -- "
                             "restore it onto a firmware with eight slots, or flash with --no-profiles")
        recs = recs[:g.slots]
    recs += [bytes(REC)] * (g.slots - len(recs))
    magic = g.magic if block[0] in SLOTS_OF else block[0]
    return bytes([magic, block[1]]) + b"".join(recs)


def normalized(block):
    """The block as the board's commit leaves it: an active byte that points
    at an empty slot, or at none, reads 0xFF."""
    b = bytearray(block)
    a = b[1]
    if a >= block_slots(block) or b[2 + a * REC] == 0:
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


def write_block(h, block, g):
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
    if st != 0:
        raise SystemExit(f"restore refused at commit: {STATUS.get(st, st)} (the board's profiles read as empty)")


def apply_live(h, live):
    st = busy_retry(lambda: xfer(h, 5, live)[31], "apply")
    if st not in (0, 8):
        raise SystemExit(f"live settings refused: {STATUS.get(st, st)}")
    st = busy_retry(lambda: xfer(h, 6)[4], "flush")
    if st != 0:
        raise SystemExit(f"flush refused: {STATUS.get(st, st)}")
    return st


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
        d["battery"] = {1: "percent", 2: "hours", 3: "both"}.get(r[12], r[12])
    if f & PF_POWER:
        d["power"] = POWER[r[13]] if r[13] < len(POWER) else r[13]
    if f & PF_NAME:
        d["name"] = bytes(r[14:26]).split(b"\0")[0].decode("ascii", "replace")
    return d


def decode_block(b):
    if SLOTS_OF.get(b[0]) != block_slots(b):
        return {"formatted": False}
    slots = []
    for s in range(block_slots(b)):
        r = b[2 + s * REC:2 + (s + 1) * REC]
        if r[0] == 0:
            slots.append(None)
        elif not rec_ok(r):
            slots.append("damaged")
        else:
            d = decode(r)
            d["name"] = d.get("name") or f"Profile {s + 1}"
            slots.append(d)
    a = b[1]
    return {"formatted": True, "active": a + 1 if a < len(slots) and isinstance(slots[a], dict) else None, "slots": slots}


def describe(doc):
    lines = []
    blk = doc.get("decoded", {}).get("block", {})
    if not blk.get("formatted"):
        lines.append("profiles: none saved")
    else:
        for i, s in enumerate(blk["slots"]):
            mark = "*" if blk.get("active") == i + 1 else " "
            if s is None:
                lines.append(f" {mark} slot {i + 1}: empty")
            elif s == "damaged":
                lines.append(f" {mark} slot {i + 1}: damaged (reads as empty)")
            else:
                l = s.get("lighting", {})
                lines.append(f" {mark} slot {i + 1}: {s['name']}: {l.get('effect')} h{l.get('hue')} s{l.get('sat')} "
                             f"v{l.get('val')}, screen {s.get('screen')}%, clock {s.get('clock')}")
    lv = doc.get("decoded", {}).get("live")
    if lv:
        l = lv.get("lighting", {})
        lines.append(f"live: {l.get('effect')} {'on' if l.get('on') else 'off'} h{l.get('hue')} s{l.get('sat')} "
                     f"v{l.get('val')} speed {l.get('speed')}, screen {lv.get('screen')}%, locks {lv.get('lock_lights')}, "
                     f"charging {lv.get('charging_light')}, clock {lv.get('clock')}, battery {lv.get('battery')}, "
                     f"power {lv.get('power')}")
    return "\n".join(lines)


def snapshot(h):
    g = geometry(h)
    block, live = read_block(h, g), read_live(h)
    return {
        "_comment": f"AK820 Pro settings profiles (the EEPROM's top {g.size} B, {g.slots} slots) and the live "
                    "settings, as HC_PROFILES reads them. Restore with ak820profiles.py restore.",
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": 1 if g.slots == 4 else 2,   # 2: P5d's eight slots
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
    if fmt not in (1, 2):
        raise SystemExit(f"{path} is format {fmt}; this tool reads 1 and 2")
    block, live = bytes.fromhex(doc["block"]), bytes.fromhex(doc["live"])
    if len(block) != 2 + (4 if fmt == 1 else 8) * REC or len(live) != REC or not rec_ok(live):
        raise SystemExit(f"{path} is malformed -- refusing")
    h = open_device()
    try:
        g = geometry(h)
        if not live_only:
            if SLOTS_OF.get(block[0]) == block_slots(block):
                want = convert(block, g)
                write_block(h, want, g)
                if read_block(h, g) != normalized(want):
                    raise SystemExit("the profiles' read-back differs from the backup -- the restore did not land")
                note = f" ({block_slots(block)} slots into {g.slots})" if block_slots(block) != g.slots else ""
                print(f"profiles restored and read back{note}")
            else:
                print("profiles: none in the backup, the board's left unformatted")
        if not block_only:
            st = apply_live(h, live)
            back = read_live(h)
            note = ", the effect skipped (this build lacks it)" if st == 8 else ""
            if back[1:26] != live[1:26] and st != 8:
                print("  note: the live settings read back differently -- the board clamped something:")
                print("  asked " + json.dumps(decode(live)))
                print("  got   " + json.dumps(decode(back)))
            print(f"live settings restored and flushed{note}")
        doc_now = {"decoded": {"block": decode_block(read_block(h, g)), "live": decode(read_live(h))}}
    finally:
        h.close()
    print(describe(doc_now))
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
    ap.add_argument("action", choices=["dump", "restore", "show"])
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
        return cmd_show(a.file)
    except Unhandled:
        print("this firmware has no HC_PROFILES (before P5a): profiles skipped")
        return 2


if __name__ == "__main__":
    sys.exit(main())
