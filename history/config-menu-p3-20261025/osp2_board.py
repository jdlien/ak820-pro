"""The Win/Mac switch's sides kept as left, and Reset settings, on the board
(10-27). The switch is read as each side by HC_PROFILES' dev sub 0x42 (the
real switch stays where it is); Reset settings through the menu (op 27), as
a press would. On empty slots and an empty last record (the prep's).

1. A profile a side; each flip brings the other side back as it was left; a
   change on one side (its `*`) survives a flip there and back; a bounce
   changes nothing; ten flips; a side whose profile is deleted keeps nothing
   of its own, and the side with one comes back as left.
2. Reset settings: the confirm, a click: the defaults (Solid h36 s64 v191
   speed 102, screen 60, both lights 5, 24h:ss, Percent, Balanced), saved;
   the profile kept, neither side's, no last record; a flip after changes
   nothing.
Every pass timed (op 27 sub 10). Leaves the side as the real switch reads it
and the slots empty. Never enumerates HID."""
import json
import sys
import time

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
import ak820profiles as ap  # noqa: E402
import menu_p1a_board as g  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "osp2-board.json"
A, B, B2 = (1, 20), (4, 90), (4, 91)   # (effect id, screen)
DEFAULTS_LIVE = {2: 1, 3: 1, 4: 36, 5: 64, 6: 191, 7: 102, 8: 60, 9: 5, 10: 5, 11: 0, 12: 1, 13: 1}   # the live record's bytes
REST = 0.8
TOP, DEFAULTS = 1, 58
fails, log = [], []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    log.append({"ok": bool(ok), "what": what})
    if not ok:
        fails.append(what)


def side(h):
    return ap.geometry(h).side


def block(h):
    return ap.read_block(h, ap.geometry(h))   # page 0 shows a pending active byte


def nib(p, s):
    return (p >> 4 if s == "mac" else p) & 0xF


def look(h):
    r = ap.read_live(h)
    return r[3], r[8]


def set_look(h, lk):
    r = bytearray(ap.read_live(h))
    r[2], r[3], r[8] = 1, lk[0], lk[1]
    r[26] = ap.crc8(r[1:26])
    ap.apply_live(h, bytes(r))


def flip(h, s, rest=REST):
    r = ap.xfer(h, 0x42, [1 if s == "mac" else 0])
    check(r[5] == 0, f"0x42 to {s}: status {r[5]}")
    if rest:
        time.sleep(rest)


def save(h, slot):
    r = ap.xfer(h, 0x40, [slot])
    check(r[5] == 0, f"save slot {slot + 1}: status {r[5]}")
    return r[6] == 1


def last_state(h):
    return block(h)[2 + ap.LAST * ap.REC]


def tag(s):
    return ap.PS_LAST | (1 if s == "mac" else 0)


def main():
    h = open_device()
    meas, cons, real = {}, False, None
    try:
        gm = ap.geometry(h)
        real = gm.side
        check(gm.magic == ap.MAGIC_V4 and real in ("windows", "mac"), f"magic {gm.magic:#x}, the switch on {real}")
        b = ap.read_block(h, gm)
        if b[0] == gm.magic and (any(ap.rec_ok(b[2 + s * 27:29 + s * 27]) for s in range(7)) or b[2 + 7 * 27]):
            sys.exit("refused: a slot or the last record is saved")
        x, y = real, ("mac" if real == "windows" else "windows")
        to_dash(h)
        xfer(h, 10, bytes([1]))   # every pass timed from here

        # 1. The sides.
        set_look(h, A)
        cons |= save(h, 0)
        flip(h, y)
        check(side(h) == y and look(h) == A, f"to {y}, no profile: what was there {look(h)}")
        check(last_state(h) == tag(x), f"{x}'s settings kept: {last_state(h):#x}")
        set_look(h, B)
        cons |= save(h, 1)
        p = block(h)[1]
        check(nib(p, x) == 0 and nib(p, y) == 1, f"a profile a side: {p:#04x}")
        flip(h, x)
        check(side(h) == x and look(h) == A and last_state(h) == tag(y), f"to {x}: as left {look(h)}")
        flip(h, y)
        check(look(h) == B and last_state(h) == tag(x), f"to {y}: as left {look(h)}")
        set_look(h, B2)   # a change on y, its `*`
        flip(h, x)
        check(look(h) == A, f"to {x}: {look(h)}")
        flip(h, y)
        check(look(h) == B2, f"to {y}: the change kept (JD: \"don't lose your settings\") {look(h)}")
        flip(h, x, rest=0)
        flip(h, y)
        check(side(h) == y and look(h) == B2, f"a bounce: nothing {look(h)}")
        for i in range(10):
            s = x if i % 2 == 0 else y
            flip(h, s)
            check(look(h) == (A if s == x else B2), f"flip {i + 1} to {s}: {look(h)}")
        # On y, its profile deleted: y keeps nothing of its own from here.
        r = ap.xfer(h, 0x41, [1])
        check(r[5] == 0, f"delete slot 2: {r[5]}")
        p = block(h)[1]
        check(nib(p, y) == 0xF and nib(p, x) == 0 and last_state(h) == tag(x), f"slot 2 deleted, {y} none: {p:#04x}")
        flip(h, x)
        check(look(h) == A and last_state(h) == 0, f"to {x}: as left, the copy used up {look(h)}")
        flip(h, y)
        check(look(h) == A and last_state(h) == tag(x), f"to {y}, none: what was there {look(h)}")
        flip(h, x)
        check(side(h) == x and look(h) == A, f"back to {x}: {look(h)}")

        # 2. Reset settings, through the menu.
        g.step(h, 11, b"", "open", g.SCR(TOP), 0)
        g.turn(h, g.R_DEFS, "to Reset settings", g.SCR(TOP), g.R_DEFS)
        g.click(h, "Reset settings", g.SCR(DEFAULTS), 0)
        g.click(h, "reset", g.SCR(DEFAULTS), 1)
        lv = ap.read_live(h)
        bad = {i: lv[i] for i, v in DEFAULTS_LIVE.items() if lv[i] != v}
        check(not bad and ap.rec_ok(lv), f"the defaults, live (bytes off: {bad})")
        bk = block(h)
        check(bk[1] == 0xFF and bk[2 + 7 * 27] == 0 and ap.rec_ok(bk[2:29]), f"no side's, no last record, slot 1 kept: "
                                                                           f"{bk[1]:#04x}")
        g.dwell(h, "the done page, 2 s", 2.0)
        g.click(h, "back", g.SCR(TOP), g.R_DEFS)
        g.step(h, 11, b"", "close", owner="dash")
        time.sleep(1.5)
        flip(h, y)
        flip(h, x)
        check(look(h) == (1, 60) and side(h) == x, f"flips after it change nothing: {look(h)}")
        time.sleep(6)   # the deferred writes
        bk = block(h)
        check(bk[1] == 0xFF, f"the active byte written as none: {bk[1]:#04x}")
        meas = decode_meas(xfer(h, 10, bytes([0])))
        check(not meas["aliased"], "no pass of 340 ms or more")
        print(f"  longest pass {meas['pass_max_us']} us, over 15 ms {meas['over15']}"
              f"{', a save consolidated' if cons else ''}", flush=True)
        r = ap.xfer(h, 0x41, [0])
        check(r[5] == 0, f"delete slot 1: {r[5]}")
    finally:
        try:
            if real is not None and side(h) != real:
                flip(h, real)
        finally:
            h.close()
            with open(OUT, "w") as f:
                json.dump({"log": log, "steps": g.log, "meas": meas, "consolidated": cons,
                           "fails": fails + g.fails}, f, indent=1)
    all_f = fails + g.fails
    print("PASS" if not all_f else f"FAILED: {len(all_f)} ({len(g.fails)} the menu steps')")
    return 1 if all_f else 0


if __name__ == "__main__":
    sys.exit(main())
