"""ak820profiles.py's block conversion between P5a/P5b's four slots and P5d's eight,
offline (no device): convert(), normalized(), decode_block(); since 10-28 the live
record's face: its decode, the backup's and the restore's pass-through, and the
retry without it onto an older firmware, against a fake board.

    venv-win/Scripts/python.exe scripts/profiles_host_test.py < /dev/null"""
import contextlib
import io
import json
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
import ak820profiles as ap

fails = 0
def check(c, what):
    global fails
    if not c:
        fails += 1
        print("FAIL", what)

def rec(h, name=b""):
    body = bytearray(25)
    body[0] = ap.PF_LIGHTING | ap.PF_LCD | (ap.PF_NAME if name else 0)
    body[1] = 1; body[2] = 3; body[3] = h; body[4] = 255; body[5] = 200; body[6] = 128; body[7] = 50
    body[13:13 + len(name)] = name
    return bytes([1]) + bytes(body) + bytes([ap.crc8(body)])

r0, r3 = rec(11), rec(22, b"Work")
check(ap.rec_ok(r0) and ap.rec_ok(r3), "records")
v1 = bytes([ap.MAGIC_V1, 3]) + r0 + bytes(27) * 2 + r3
check(len(v1) == 110 and ap.block_slots(v1) == 4, "v1 size")
g8, g4 = ap.Geometry(8, ap.MAGIC_V2), ap.Geometry(4, ap.MAGIC_V1)
check(g8.size == 218 and g8.pages == 9 and g4.size == 110 and g4.pages == 5, "geometry")
v2 = ap.convert(v1, g8)
check(len(v2) == 218 and v2[0] == ap.MAGIC_V2 and v2[1] == 3 and v2[2:2 + 4 * 27] == v1[2:], "4 into 8")
check(v2[2 + 4 * 27:] == bytes(4 * 27), "the four new slots empty")
check(ap.convert(v1, g4) == v1, "4 onto 4 unchanged")
check(ap.convert(v2, g4) == v1, "8 onto 4, slots 5-8 empty")
v2b = bytearray(v2); v2b[2 + 6 * 27:2 + 7 * 27] = rec(77)
try:
    ap.convert(bytes(v2b), g4)
    check(False, "8 onto 4 with slot 7 saved refused")
except SystemExit as e:
    check("slots 5-8" in str(e), "the refusal names the slots")
d = ap.decode_block(bytes(v2b))
check(d["formatted"] and len(d["slots"]) == 8 and d["active"] == 4 and d["slots"][6]["name"] == "Profile 7"
      and d["slots"][3]["name"] == "Work" and d["slots"][1] is None, "decode eight")
check(ap.decode_block(bytes([0, 0xFF]) + bytes(216)) == {"formatted": False}, "unformatted")
check(ap.decode_block(bytes([ap.MAGIC_V1]) + bytes(217)) == {"formatted": False}, "a v1 magic on eight slots")
n = bytearray(v2b); n[1] = 5
check(ap.normalized(bytes(n))[1] == 0xFF and ap.normalized(bytes(v2b))[1] == 3, "normalized")
n[1] = 6
check(ap.normalized(bytes(n))[1] == 6, "normalized keeps slot 7")

# 10-27: the active byte a side's (magic 0xA3): bits 0-3 Windows', 4-7 the Mac's.
g3 = ap.Geometry(8, ap.MAGIC_V3)
check(ap.SLOTS_OF[ap.MAGIC_V3] == 8 and ap.FORMAT_OF[ap.MAGIC_V3] == 3, "v3's slots and format")
v3 = ap.convert(bytes(v2b), g3)   # one active slot (4th) into both sides'
check(v3[0] == ap.MAGIC_V3 and v3[1] == 0x33 and v3[2:] == bytes(v2b)[2:], "v2 into v3: both sides the old slot")
check(ap.convert(v1, g3)[1] == 0x33 and len(ap.convert(v1, g3)) == 218, "v1 into v3")
none2 = bytearray(v2b); none2[1] = 0xFF
check(ap.convert(bytes(none2), g3)[1] == 0xFF, "none into none, none")
check(ap.convert(v3, g3) == v3, "v3 onto v3 unchanged")
p = bytearray(v3); p[1] = 0x6F   # Windows none, the Mac slot 7
check(ap.convert(bytes(p), g8)[1] == 6 and ap.convert(bytes(p), g8)[0] == ap.MAGIC_V2, "v3 into v2: the Mac's, Windows' none")
p[1] = 0x63
check(ap.convert(bytes(p), g8)[1] == 3, "v3 into v2: Windows' first")
p[1] = 0xFF
check(ap.convert(bytes(p), g8)[1] == 0xFF, "v3 into v2: none")
p[1] = 0x03                       # slots 1-4 hold 0 and 3 only
p[2 + 6 * 27] = 0                 # slot 7 empty again: 8 onto 4 allowed
c4 = ap.convert(bytes(p), g4)
check(c4[0] == ap.MAGIC_V1 and c4[1] == 3, "v3 onto four slots")
# normalized, each side's: slots 0, 3 and 6 saved in v2b (the board's commit, profiles_test.c's cases).
for a, want in ((0xF1, 0xFF), (0x1A, 0xFF), (0x03, 0x03), (0x6E, 0x6F), (0x9C, 0xFF), (0x36, 0x36)):
    q = bytearray(v3); q[1] = a
    check(ap.normalized(bytes(q))[1] == want, f"normalized v3 {a:#04x} -> {want:#04x}")
q = bytearray(v3); q[1] = 0x63
d3 = ap.decode_block(bytes(q))
check(d3["active"] == {"windows": 4, "mac": 7}, "decode v3's pair")
q[1] = 0xF3
check(ap.decode_block(bytes(q))["active"] == {"windows": 4, "mac": None}, "decode v3, the Mac none")
txt = ap.describe({"switch": "mac", "decoded": {"block": d3}})
check("the switch on the Mac" in txt and " W  slot 4" in txt and "  M slot 7" in txt, "describe's marks")
check(" *  slot 4" in ap.describe({"decoded": {"block": d}}), "describe, one slot")

# 10-27, later: magic 0xA4, seven profiles and the last record (the other side's settings as left).
g4v = ap.Geometry(8, ap.MAGIC_V4)
check(g4v.size == 218 and ap.USER_OF[ap.MAGIC_V4] == 7 and ap.FORMAT_OF[ap.MAGIC_V4] == 4, "v4's geometry")
v4 = ap.convert(v3, g4v)   # slots 1, 4 and 7 saved, slot 8 empty: only the magic changes
check(v4[0] == ap.MAGIC_V4 and v4[1:] == v3[1:], "v3 into v4: the records as they were")
check(ap.convert(bytes(v2b), g4v)[1] == 0x33 and ap.convert(bytes(v2b), g4v)[2:] == bytes(v2b)[2:], "v2 into v4")
# A profile in slot 8 moves to the first empty of 1-7, the active byte following it.
e = bytearray(v3); e[2 + 7 * 27:2 + 8 * 27] = rec(88, b"Eighth"); e[1] = 0x37   # the Mac on slot 8, Windows on 4
m = ap.convert(bytes(e), g4v)
check(m[2 + 1 * 27:2 + 2 * 27] == rec(88, b"Eighth") and m[2 + 7 * 27] == 0 and m[1] == 0x31,
      "slot 8's profile into slot 2, the Mac's nibble with it")
full = bytearray(e)
for s in range(8):
    full[2 + s * 27:2 + (s + 1) * 27] = rec(s + 1)
try:
    ap.convert(bytes(full), g4v)
    check(False, "eight profiles onto seven refused")
except SystemExit as x:
    check("seven" in str(x), "the refusal says seven")
# The last record: kept onto 0xA4, dropped off it.
def last_rec(side, h):
    body = bytearray(25)
    body[0] = 0x3F
    body[1] = 1; body[2] = 1; body[3] = h; body[4] = 64; body[5] = 191; body[6] = 102
    body[7] = 60; body[8] = 5; body[9] = 5; body[10] = 0; body[11] = 1
    return bytes([ap.PS_LAST | side]) + bytes(body) + bytes([ap.crc8(body)])
w = bytearray(v4); w[2 + 7 * 27:2 + 8 * 27] = last_rec(1, 36); w[1] = 0x03
check(ap.convert(bytes(w), g4v) == bytes(w), "v4 onto v4 unchanged, the last record kept")
d3 = ap.convert(bytes(w), g8)
check(d3[0] == ap.MAGIC_V2 and d3[1] == 3 and d3[2 + 7 * 27:] == bytes(27), "v4 into v2: the last record dropped")
check(ap.convert(bytes(w), ap.Geometry(8, ap.MAGIC_V3))[2 + 7 * 27] == 0, "v4 into v3: dropped too")
for a, want in ((0x37, 0x3F), (0x76, 0xF6), (0x03, 0x03), (0xF7, 0xFF)):   # 7 is no profile on v4
    q = bytearray(w); q[1] = a
    check(ap.normalized(bytes(q))[1] == want, f"normalized v4 {a:#04x} -> {want:#04x}")
d4 = ap.decode_block(bytes(w))
check(len(d4["slots"]) == 7 and d4["active"] == {"windows": 4, "mac": 1} and d4["last"]["side"] == "mac" and
      d4["last"]["lighting"]["hue"] == 36 and d4["last"]["screen"] == 60, "decode v4: seven, and the last record")
q = bytearray(w); q[2 + 7 * 27 + 4] ^= 1
check(ap.decode_block(bytes(q))["last"] == "damaged", "a damaged last record")
check("the Mac's settings as left: Solid h36" in ap.describe({"decoded": {"block": d4}}), "describe's last line")

# 10-28, the Font setting: the live record's readout byte carries the menu's face in bit 2 (set Small). The
# decode shows the readout and the face apart, for the live record only; the backup and the restore pass the
# bit through; a firmware from before refuses it, and the restore sends the record once more without it.
def live_rec(bview, h=36):
    body = bytearray(25)
    body[0] = ap.PF_LIVE
    body[1] = 1; body[2] = 1; body[3] = h; body[4] = 64; body[5] = 191; body[6] = 102
    body[7] = 60; body[8] = 5; body[9] = 5; body[10] = 0; body[11] = bview; body[12] = 1
    return bytes([1]) + bytes(body) + bytes([ap.crc8(body)])

small, large = live_rec(2 | ap.BV_SMALL), live_rec(2)
check(ap.rec_ok(small) and ap.rec_ok(large), "live records")
ds, dl = ap.decode(small), ap.decode(large)
check(ds["battery"] == "hours" and ds["font"] == "small" and dl["battery"] == "hours" and dl["font"] == "large",
      "decode: the readout and the face apart")
check(ap.decode(live_rec(3 | ap.BV_SMALL))["battery"] == "both", "decode: both, in Small")
check(ap.decode(live_rec(0x0E))["battery"] == 0x0E and "font" not in ap.decode(live_rec(0x0E)),
      "decode: a garbage byte (both face bits) as it is, no face")
check(ap.decode(live_rec(0x1A))["battery"] == 0x1A and "font" not in ap.decode(live_rec(0x1A)),
      "decode: a garbage byte (bit 4) as it is, no face")
reg = live_rec(2 | ap.BV_REG)   # 10-28: the third face, Regular, in bit 3
dr = ap.decode(reg)
check(dr["battery"] == "hours" and dr["font"] == "regular", "decode: Regular's bit")
check(ap.without_face(reg) == large and ap.rec_ok(ap.without_face(reg)), "without_face: Regular's bit out too")
check("font" not in ap.decode(rec(11)) and ap.decode(last_rec(0, 36))["font"] == "large",
      "decode: the face wherever the readout is (10-28: every record's), none without it")
# 10-28: a block whose records carry the face, sent again without it onto a firmware from before.
fb = bytearray(ap.normalized(bytes([ap.MAGIC_V4, 0xFF]) + bytes(8 * 27)))
lr = bytearray(last_rec(0, 36)); lr[12] |= ap.BV_REG; lr[26] = ap.crc8(lr[1:26])
fb[2 + 7 * 27:2 + 8 * 27] = lr
check(ap.block_faces(bytes(fb)) and not ap.block_faces(ap.block_without_faces(bytes(fb))), "block_faces / without")
nb = ap.block_without_faces(bytes(fb))
check(nb[2 + 7 * 27 + 26] == ap.crc8(nb[2 + 7 * 27 + 1:2 + 7 * 27 + 26]) and nb[2 + 7 * 27 + 12] == 1 and nb[:2 + 7 * 27] == bytes(fb[:2 + 7 * 27]),
      "block_without_faces: the bits out, the crc taken again, the rest untouched")
txt = ap.describe({"decoded": {"live": ds}})
check("battery hours, font small, power Balanced" in txt, "describe's live line: " + txt)
check("font" not in ap.describe({"decoded": {"live": ap.decode(rec(11))}}), "describe: no face without one")
nf = ap.without_face(small)
check(nf == large and ap.rec_ok(nf), "without_face: the bit out, the crc taken again")


class FakeBoard:
    """HC_PROFILES' subs 0, 4, 5, 6 and 7 on an 0xA4 block, as a firmware answers them. `old`: one from before
    the Font setting, which refuses a record whose readout byte is out of 1-3 (bit 2 set) and never reports a face;
    `refuse`: a record it refuses whatever its face."""
    def __init__(self, live, old=False, refuse=False):
        self.live, self.old, self.refuse, self.sent, self.reply = live, old, refuse, [], None
        self.block = bytes([ap.MAGIC_V4, 0xFF]) + bytes(8 * ap.REC)

    def write(self, b):
        q = bytearray(b[1:])
        sub = q[3]
        if sub == 0:
            q[5] = 0
            page = self.block[q[4] * ap.PAGE:(q[4] + 1) * ap.PAGE]
            q[6:6 + len(page)] = page
        elif sub == 4:
            q[4:4 + ap.REC] = self.live
            q[31] = 0
        elif sub == 5:
            r = bytes(q[4:4 + ap.REC])
            self.sent.append(r)
            bad = not ap.rec_ok(r) or self.refuse or (self.old and not 1 <= r[12] <= 3)
            q[31] = 4 if bad else 0
            if not bad:
                self.live = r
        elif sub == 6:
            q[4] = 0
        elif sub == 7:
            q[4:10] = bytes([8, ap.REC, 9, ap.PAGE, ap.MAGIC_V4, 1])
        self.reply = bytes(q)

    def read(self, n, timeout_ms):
        r, self.reply = self.reply, None
        return r

    def close(self):
        pass


def quiet(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            res = fn(*a)
        except SystemExit as e:
            res = e
    return res, out.getvalue()

# The backup: the face as the board reports it, in the file's bytes and its decode.
doc, _ = quiet(ap.snapshot, FakeBoard(small))
check(doc["live"] == small.hex() and doc["decoded"]["live"]["font"] == "small", "the backup keeps the face")
# The restore onto this firmware: sent once, as kept.
b = FakeBoard(large)
(res, out) = quiet(ap.apply_live, b, small)
check(res == (0, small) and b.sent == [small] and b.live == small and "refused" not in out, "the restore passes the face")
# Onto an older firmware: refused with the bit, taken without it, said so; Large is sent once.
b = FakeBoard(large, old=True)
(res, out) = quiet(ap.apply_live, b, small)
check(res == (0, large) and b.sent == [small, large] and b.live == large and "sent again without it" in out,
      "an older firmware: once more without the face")
b = FakeBoard(large, old=True)   # 10-28: Regular's bit onto a firmware without it: the same retry
(res, out) = quiet(ap.apply_live, b, reg)
check(res == (0, large) and b.sent == [reg, large] and "sent again without it" in out, "an older firmware: Regular's bit out")
b = FakeBoard(small, old=True)
(res, out) = quiet(ap.apply_live, b, large)
check(res == (0, large) and b.sent == [large] and "refused" not in out, "an older firmware, Large: sent once")
# Refused for something else: with the bit, the one retry and then the refusal; without it, no retry.
b = FakeBoard(large, refuse=True)
(res, out) = quiet(ap.apply_live, b, small)
check(isinstance(res, SystemExit) and "refused" in str(res) and b.sent == [small, large], "a refusal after the retry")
b = FakeBoard(large, refuse=True)
(res, out) = quiet(ap.apply_live, b, large)
check(isinstance(res, SystemExit) and b.sent == [large], "no retry for a record without the face")
# The whole live restore onto an older firmware: done, and no "clamped" note for the face it can't hold.
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "p.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": 4, "block": bytes([ap.MAGIC_V4, 0xFF]).hex() + "00" * (8 * ap.REC),
                   "live": small.hex()}, f)
    for old, want in ((False, small), (True, large)):
        b = FakeBoard(live_rec(1), old=old)
        ap.open_device = lambda: b
        (res, out) = quiet(ap.cmd_restore, path, False, True)
        check(res == 0 and b.live == want and "clamped" not in out and "live settings restored" in out,
              f"cmd_restore --live-only, {'an older' if old else 'this'} firmware: {out}")

print("host conversion:", "all checks passed" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
