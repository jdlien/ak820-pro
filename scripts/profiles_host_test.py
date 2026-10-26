"""ak820profiles.py's block conversion between P5a/P5b's four slots and P5d's eight,
offline (no device): convert(), normalized(), decode_block().

    venv-win/Scripts/python.exe scripts/profiles_host_test.py < /dev/null"""
import os
import sys
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
print("host conversion:", "all checks passed" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
