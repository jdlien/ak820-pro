"""Before the board passes on the keyboard on gremlin: the lighting as the
baselines had it (Drift h43 s255 v255 speed 255), and the slots empty (JD's
are stashed in the scratchpad). Since 0xA4 (10-27) an empty block is
restored whole, so the active byte and the last record go too. Never
enumerates HID."""
import sys
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
import ak820profiles as ap
from ak820health import open_device

h = open_device()
try:
    g = ap.geometry(h)
    print("geometry", g.slots, g.size, g.pages, hex(g.magic), g.side)
    live = bytearray(ap.read_live(h))
    live[3], live[4], live[5], live[6], live[7] = 12, 43, 255, 255, 255   # Drift, h43 s255 v255, speed 255
    live[2] = 1
    live[26] = ap.crc8(live[1:26])
    ap.apply_live(h, bytes(live))
    print("live:", ap.decode(ap.read_live(h)).get("lighting"))
    if g.magic == ap.MAGIC_V4:
        empty = bytes([g.magic, 0xFF]) + bytes(g.size - 2)
        ap.write_block(h, empty, g)
        if ap.read_block(h, g) != empty:
            raise SystemExit("the empty block didn't read back")
    else:
        for s in range(g.slots):
            r = ap.xfer(h, 0x41, [s])
            if r[5] != 0:
                raise SystemExit(f"dev delete of slot {s}: {r[5]}")
    print(ap.describe({"decoded": {"block": ap.decode_block(ap.read_block(h, g))}}))
finally:
    h.close()
