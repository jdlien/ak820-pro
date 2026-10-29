#!/usr/bin/env python3
"""The art on Help's More info page (P1d; plans/CONFIG-MENU-P1-DESIGN.md,
"P1b, P1c, P1d"; plans/MENU-TEXT.md, "Help > More info"): writes
graphics/res/menu_art.h, and the mock-up's copy (plans/menu-mockup/menuart.hex).

    python scripts/gen_menu_art.py [--check] < /dev/null

- The bunny: the splash's (assets-src/mkbunny.py), made the same way, an
  area average of assets-src/bunny-source.png's alpha (the ink), cropped to
  the ink and scaled to 42 rows: 27 x 42, a byte a pixel, 0 none and 255
  full ink. The menu draws it white over black, the ink as a level of the
  colour, so the face and the inner ear read dark, as on the splash.
- The QR code: https://github.com/jdlien/ak820-pro, frozen. Byte mode,
  version 3 (29 x 29) at level M, the smallest version for 35 bytes at M,
  encoded here (no library: stdlib only, as every generator in scripts/),
  the mask the standard's penalty picks. 4 bytes a row, module 0 in bit 7,
  1 dark.

The mock-up's copy is one hex string: the bunny's bytes, then the QR's.

--check writes nothing and fails if a file on disk differs."""
import argparse
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "time-util-ak820pro", "assets"))
from mkraw import decode_png  # noqa: E402

SRC = os.path.join(ROOT, "assets-src", "bunny-source.png")
RES = os.path.join(ROOT, "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro", "graphics", "res")
OUT_H = os.path.join(RES, "menu_art.h")
OUT_MOCK = os.path.join(ROOT, "plans", "menu-mockup", "menuart.hex")

BUNNY_H = 42   # three of Small's rows (plans/CONFIG-MENU-PLAN.md: "27 x 42")
URL = "https://github.com/jdlien/ak820-pro"


def bunny():
    w, h, px = decode_png(SRC)
    alpha = [p[3] for p in px]
    ys = [i // w for i, a in enumerate(alpha) if a]
    xs = [i % w for i, a in enumerate(alpha) if a]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    sw, sh = x1 - x0, y1 - y0
    bw = max(1, round(sw * BUNNY_H / sh))
    out = []
    for dy in range(BUNNY_H):   # mkbunny.py's box filter, over the ink's box
        ya = y0 + dy * sh // BUNNY_H
        yb = max(ya + 1, y0 + (dy + 1) * sh // BUNNY_H)
        row = []
        for dx in range(bw):
            xa = x0 + dx * sw // bw
            xb = max(xa + 1, x0 + (dx + 1) * sw // bw)
            tot = sum(alpha[sy * w + sx] for sy in range(ya, yb) for sx in range(xa, xb))
            row.append(tot // ((yb - ya) * (xb - xa)))
        out.append(row)
    return bw, out


# --- QR, version 3-M, byte mode (ISO/IEC 18004) --------------------------------
VER, SIZE, DATA_CW, EC_CW = 3, 29, 44, 26   # 70 codewords, one block
ALIGN = (6, 22)                              # version 3's alignment centres
FMT_M = 0                                    # level M's format bits

EXP = [0] * 512
LOG = [0] * 256
_v = 1
for _i in range(255):
    EXP[_i] = _v
    LOG[_v] = _i
    _v <<= 1
    if _v & 0x100:
        _v ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gmul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def rs_ec(data, n):
    gen = [1]                                # (x - a^0)...(x - a^(n-1)), highest degree first
    for i in range(n):
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= c
            nxt[j + 1] ^= gmul(c, EXP[i])
        gen = nxt
    rem = [0] * n
    for d in data:
        f = d ^ rem[0]
        rem = rem[1:] + [0]
        for j in range(n):
            rem[j] ^= gmul(gen[j + 1], f)
    return rem


def codewords(text):
    b = text.encode("ascii")
    bits = [0, 1, 0, 0] + [(len(b) >> i) & 1 for i in range(7, -1, -1)]
    for c in b:
        bits += [(c >> i) & 1 for i in range(7, -1, -1)]
    cap = DATA_CW * 8
    if len(bits) > cap:
        sys.exit(f"{text!r} doesn't fit version {VER}-M")
    bits += [0] * min(4, cap - len(bits))    # the terminator
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0
    while len(data) < DATA_CW:
        data.append((0xEC, 0x11)[pad])
        pad ^= 1
    return data + rs_ec(data, EC_CW)


def function_map():
    m = [[None] * SIZE for _ in range(SIZE)]   # m[y][x]: True dark, False light, None data

    def finder(cy, cx):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                y, x = cy + dy, cx + dx
                if 0 <= y < SIZE and 0 <= x < SIZE:
                    d = max(abs(dy), abs(dx))
                    m[y][x] = d != 2 and d != 4
    finder(3, 3)
    finder(3, SIZE - 4)
    finder(SIZE - 4, 3)
    for i in range(8, SIZE - 8):              # the timing patterns
        m[6][i] = m[i][6] = i % 2 == 0
    for cy in ALIGN:
        for cx in ALIGN:
            if m[cy][cx] is not None:         # on a finder
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    m[cy + dy][cx + dx] = max(abs(dy), abs(dx)) != 1
    for y, x in format_cells(0):              # reserved; drawn with the mask
        m[y][x] = False
    m[SIZE - 8][8] = True                     # the dark module
    return m


def format_cells(_):
    """The 15 format bits' places, bit i at index i, both copies: (y, x)."""
    a = [(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)] + [(8, 14 - i) for i in range(9, 15)]
    b = [(8, SIZE - 1 - i) for i in range(8)] + [(SIZE - 15 + i, 8) for i in range(8, 15)]
    return a + b


def format_bits(mask):
    data = FMT_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


def place(fm, cw):
    m = [row[:] for row in fm]
    bits = [(c >> (7 - i)) & 1 for c in cw for i in range(8)]
    k = 0
    right = SIZE - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(SIZE):
            for j in range(2):
                x = right - j
                y = SIZE - 1 - vert if ((right + 1) & 2) == 0 else vert
                if fm[y][x] is None:
                    m[y][x] = bool(bits[k]) if k < len(bits) else False   # version 3's 7 remainder bits: light
                    k += 1
        right -= 2
    return m


def masked(fm, base, mask):
    m = [row[:] for row in base]
    for y in range(SIZE):
        for x in range(SIZE):
            if fm[y][x] is None and MASKS[mask](x, y):
                m[y][x] = not m[y][x]
    fb = format_bits(mask)
    for i, (y, x) in enumerate(format_cells(0)):
        m[y][x] = bool((fb >> (i % 15)) & 1)
    return m


def penalty(m):
    p = 0
    lines = [row for row in m] + [[m[y][x] for y in range(SIZE)] for x in range(SIZE)]
    for ln in lines:                          # N1: runs of five or more
        run = 1
        for i in range(1, SIZE + 1):
            if i < SIZE and ln[i] == ln[i - 1]:
                run += 1
            else:
                if run >= 5:
                    p += 3 + run - 5
                run = 1
    for y in range(SIZE - 1):                 # N2: 2 x 2 blocks
        for x in range(SIZE - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                p += 3
    pats = ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1])
    for ln in lines:                          # N3: the finder's 1:1:3:1:1 beside four light
        v = [int(c) for c in ln]
        for i in range(SIZE - 10):
            if v[i:i + 11] in pats:
                p += 40
    dark = sum(c for row in m for c in row)   # N4: the balance
    p += 10 * (abs(dark * 20 - SIZE * SIZE * 10) // (SIZE * SIZE))
    return p


def qr():
    fm = function_map()
    base = place(fm, codewords(URL))
    best = min(range(8), key=lambda k: penalty(masked(fm, base, k)))
    return best, masked(fm, base, best)


def render():
    bw, bun = bunny()
    mask, q = qr()
    rows = []
    for row in q:
        v = 0
        for x, d in enumerate(row):
            v |= int(d) << (31 - x)
        rows.append([(v >> s) & 0xFF for s in (24, 16, 8, 0)])
    h = ["// GENERATED by scripts/gen_menu_art.py -- do not edit.",
         "// Help's More info page (P1d): the bunny, the splash's art (assets-src/bunny-source.png) cropped to",
         f"// its ink and area-averaged to {bw} x {BUNNY_H}, a byte a pixel (0 none, 255 full ink); and the QR code",
         f"// to {URL}, version {VER}-M (mask {mask}), {SIZE} x {SIZE} modules,",
         "// 4 bytes a row, module 0 in bit 7, 1 dark.",
         "#pragma once",
         "#include <stdint.h>",
         "",
         f"#define MENU_BUNNY_W {bw}",
         f"#define MENU_BUNNY_H {BUNNY_H}",
         "static const uint8_t menu_bunny[MENU_BUNNY_H][MENU_BUNNY_W] = {"]
    for row in bun:
        h.append("    {" + ", ".join(f"{v}" for v in row) + "},")
    h += ["};",
          "",
          f"#define MENU_QR_N {SIZE}",
          f"#define MENU_QR_URL \"{URL}\"",
          "static const uint8_t menu_qr[MENU_QR_N][4] = {"]
    for r in rows:
        h.append("    {" + ", ".join(f"0x{v:02X}" for v in r) + "},")
    h.append("};")
    hexs = "".join(f"{v:02x}" for row in bun for v in row) + "".join(f"{v:02x}" for r in rows for v in r)
    return {OUT_H: "\n".join(h) + "\n", OUT_MOCK: hexs + "\n"}, (bw, mask, q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", action="store_true", help="print the QR's modules")
    a = ap.parse_args()
    files, (bw, mask, q) = render()
    if a.show:
        for row in q:
            print("".join("##" if d else "  " for d in row))
    bad = 0
    for path, text in files.items():
        old = open(path).read() if os.path.exists(path) else None
        if old == text:
            continue
        if a.check:
            print(f"{os.path.relpath(path, ROOT)} differs: run scripts/gen_menu_art.py")
            bad += 1
        else:
            open(path, "w").write(text)
            print(f"wrote {os.path.relpath(path, ROOT)}")
    print(f"the bunny {bw} x {BUNNY_H}; the QR {SIZE} x {SIZE}, mask {mask}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
