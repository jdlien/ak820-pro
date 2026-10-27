"""The Win/Mac switch's profiles on the board (bf29a081). The switch is read
as each side by HC_PROFILES' dev sub 0x42 (the real switch stays where it
is): one slot saved a side; each flip loads the other side's lighting and
screen level once the switch has rested (~0.3 s), not before; a bounce back
loads nothing; a side that remembers none loads nothing; a Delete clears
its side; the pair in the block's active byte; the side in sub 7's [9];
every pass timed (op 27 sub 10). Leaves the side as the real switch reads
it and the slots empty. Refuses unless every slot is empty (the prep's).
Never enumerates HID."""
import json
import sys
import time

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
import ak820profiles as ap  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "osp-board.json"
A, B = (1, 20), (4, 90)   # Solid at 20%, Cycle All at 90%: (effect id, screen)
REST = 0.8
fails, log = [], []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    log.append({"ok": bool(ok), "what": what})
    if not ok:
        fails.append(what)


def side(h):
    return ap.geometry(h).side


def pair(h):
    """The active byte as the board will write it (page 0 shows a pending one)."""
    return ap.read_block(h, ap.geometry(h))[1]


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


def flip(h, s):
    r = ap.xfer(h, 0x42, [1 if s == "mac" else 0])
    check(r[5] == 0, f"0x42 to {s}: status {r[5]}")


def save(h, slot):
    r = ap.xfer(h, 0x40, [slot])
    check(r[5] == 0, f"save slot {slot + 1}: status {r[5]}")
    return r[6] == 1   # consolidated


def delete(h, slot):
    r = ap.xfer(h, 0x41, [slot])
    check(r[5] == 0, f"delete slot {slot + 1}: status {r[5]}")


def main():
    h = open_device()
    meas, cons, real = {}, False, None
    try:
        g = ap.geometry(h)
        real = g.side
        check(g.magic == ap.MAGIC_V3 and real in ("windows", "mac"), f"magic {g.magic:#x}, the switch on {real}")
        b = ap.read_block(h, g)
        if b[0] == g.magic and any(ap.rec_ok(b[2 + s * 27:29 + s * 27]) for s in range(g.slots)):
            sys.exit("refused: a slot is saved")
        x, y = real, ("mac" if real == "windows" else "windows")
        look0 = look(h)
        to_dash(h)
        xfer(h, 10, bytes([1]))   # every pass timed from here
        set_look(h, A)
        cons |= save(h, 0)
        p = pair(h)
        check(nib(p, x) == 0 and nib(p, y) == 0xF, f"slot 1 is {x}'s, {y} none: {p:#04x}")
        flip(h, y)
        time.sleep(REST)
        check(side(h) == y and look(h) == A, f"to {y}, which remembers none: nothing loaded {look(h)}")
        set_look(h, B)
        cons |= save(h, 1)
        p = pair(h)
        check(nib(p, x) == 0 and nib(p, y) == 1, f"slot 2 is {y}'s: {p:#04x}")
        flip(h, x)
        before = look(h)
        time.sleep(REST)
        check(before == B, f"to {x}: not loaded before the rest {before}")
        check(side(h) == x and look(h) == A, f"to {x}: slot 1 loaded {look(h)}")
        flip(h, y)
        time.sleep(REST)
        check(side(h) == y and look(h) == B, f"to {y}: slot 2 loaded {look(h)}")
        # A bounce back before the rest: the change since the load stays.
        set_look(h, (B[0], B[1] + 1))
        flip(h, x)
        flip(h, y)
        time.sleep(REST)
        check(side(h) == y and look(h) == (B[0], B[1] + 1), f"a bounce: nothing loaded {look(h)}")
        # Ten flips, one at a time: each loads.
        for i in range(10):
            s = x if i % 2 == 0 else y
            flip(h, s)
            time.sleep(REST)
            check(look(h) == (A if s == x else B), f"flip {i + 1} to {s}: {look(h)}")
        # A Delete clears its side: y's slot gone, a flip to y loads nothing.
        delete(h, 1)
        p = pair(h)
        check(nib(p, x) == 0 and nib(p, y) == 0xF, f"slot 2 deleted, {y} none: {p:#04x}")
        flip(h, x)
        time.sleep(REST)
        check(look(h) == A, f"to {x}: slot 1 {look(h)}")
        set_look(h, B)
        flip(h, y)
        time.sleep(REST)
        check(side(h) == y and look(h) == B, f"to {y}, none: nothing loaded {look(h)}")
        flip(h, x)
        time.sleep(REST)
        check(side(h) == x == real and look(h) == A, f"back to {x}, the real switch's: slot 1 {look(h)}")
        time.sleep(6)   # the pair's deferred write, after kb_eeconfig's settle
        meas = decode_meas(xfer(h, 10, bytes([0])))
        check(not meas["aliased"], "no pass of 340 ms or more")
        if cons:
            print(f"  a save consolidated: the longest pass {meas['pass_max_us']} us is allowed past 25 ms", flush=True)
        else:
            check(meas["pass_max_us"] < 25000, f"the longest pass {meas['pass_max_us']} us")
        print(f"  longest pass {meas['pass_max_us']} us, over 15 ms {meas['over15']}", flush=True)
        delete(h, 0)
        set_look(h, look0)
    finally:
        try:
            if real is not None and side(h) != real:
                flip(h, real)
                time.sleep(REST)
        finally:
            h.close()
            with open(OUT, "w") as f:
                json.dump({"log": log, "meas": meas, "consolidated": cons, "fails": fails}, f, indent=1)
    print("PASS" if not fails else f"FAILED: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
