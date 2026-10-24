#!/usr/bin/env python3
"""The configuration menu's 1-bit small face (plans/CONFIG-MENU-BUILD-PLAN.md,
"Generated files"): writes graphics/res/font_small_mono.h.

    python scripts/gen_mono_font.py [--check] < /dev/null

- The 95 ASCII glyphs come from the shipped atlas,
  assets-src/current/Iosevka-Medium-13.png, which holds Cozette (the name is
  deliberate: docs/fonts-assets.md). They are what the board's FONT_SMALL
  draws, so the menu's text is the debug page's, pixel for pixel.
- The atlas is checked against a fresh render of assets-src/cozette.bdf
  through mkbdfatlas.py's own placement (cell 6x14, baseline row 9, its
  xshift). A mismatch refuses: the atlas and the BDF have drifted.
- `‹ › • ▸ ✓` come from the BDF, placed the same way, at codes 0x80-0x84,
  and are checked against the mockup's EXTRA13 (plans/config-menu-mockup.html).
- 14 B a glyph, a byte a row, column 0 in bit 7.

--check writes nothing and fails if the header on disk differs."""
import argparse
import os
import re
import struct
import sys
import zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "assets-src"))
import mkbdfatlas  # noqa: E402

ATLAS = os.path.join(ROOT, "assets-src", "current", "Iosevka-Medium-13.png")
BDF = os.path.join(ROOT, "assets-src", "cozette.bdf")
MOCKUP = os.path.join(ROOT, "plans", "config-menu-mockup.html")
OUT = os.path.join(ROOT, "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro",
                   "graphics", "res", "font_small_mono.h")
CW, CH, BASELINE = 6, 14, 9
EXTRAS = [("‹", 0x2039), ("›", 0x203A), ("•", 0x2022), ("▸", 0x25B8), ("✓", 0x2713)]


def read_png(path):
    """-> (w, h, rows of (r, g, b)). 8-bit RGB or RGBA, non-interlaced."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"{path}: not a PNG")
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, = struct.unpack(">I", data[pos:pos + 4])
        t = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif t == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or ctype not in (2, 6) or interlace:
        sys.exit(f"{path}: want 8-bit RGB/RGBA, non-interlaced (got depth {depth}, type {ctype})")
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
            elif f != 0:
                sys.exit(f"{path}: filter {f}")
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = line
    return w, h, rows


def atlas_glyphs():
    w, h, px = read_png(ATLAS)
    n = mkbdfatlas.LAST - mkbdfatlas.FIRST + 1
    if (w, h) != (CW * n, CH):
        sys.exit(f"{ATLAS}: {w}x{h}, want {CW * n}x{CH}")
    out = []
    for g in range(n):
        if px[0][g * CW] != mkbdfatlas.MARKER:
            sys.exit(f"{ATLAS}: no marker at cell {g}")
        ink = set()
        for y in range(CH):
            for x in range(CW):
                r, gg, b = px[y][g * CW + x]
                if r > 200 and gg > 200 and b > 200:   # white is ink; the magenta marker isn't
                    ink.add((x, y))
        out.append(ink)
    return out


def bdf_cell(glyphs, cp, dx, name):
    if cp not in glyphs:
        sys.exit(f"{BDF}: no glyph for U+{cp:04X} ({name})")
    ink = set()
    for x0, y in mkbdfatlas.glyph_pixels(glyphs[cp], BASELINE):
        x = x0 + dx
        if not (0 <= x < CW and 0 <= y < CH):
            sys.exit(f"{name}: ink at ({x},{y}) falls outside the {CW}x{CH} cell")
        ink.add((x, y))
    return ink


def mockup_extras():
    m = re.search(r"const EXTRA13 = (\{[^}]*\})", open(MOCKUP, encoding="utf-8").read())
    if not m:
        sys.exit(f"{MOCKUP}: no EXTRA13")
    out = {}
    for ch, bits in re.findall(r'"(.)": "([01]{84})"', m.group(1)):
        out[ch] = {(i % CW, i // CW) for i, b in enumerate(bits) if b == "1"}
    return out


def rows_of(ink):
    return [sum(0x80 >> x for x in range(CW) if (x, y) in ink) for y in range(CH)]


def label(i):
    if i < 95:
        c = chr(0x20 + i)
        return "space" if c == " " else "'\\\\'" if c == "\\" else f"'{c}'"
    return EXTRAS[i - 95][0] + f" U+{EXTRAS[i - 95][1]:04X}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    glyphs = mkbdfatlas.parse_bdf(BDF)
    dx = mkbdfatlas.xshift(glyphs)
    atlas = atlas_glyphs()
    bad = []
    for i, ink in enumerate(atlas):
        want = bdf_cell(glyphs, 0x20 + i, dx, label(i)) - {(0, 0)}   # the marker hides (0, 0)
        if ink != want:
            bad.append(label(i))
    if bad:
        sys.exit("the atlas and the BDF disagree on: " + ", ".join(bad))
    if any((0, 0) in bdf_cell(glyphs, 0x20 + i, dx, label(i)) for i in range(95)):
        sys.exit("a glyph has ink under the atlas's marker")

    mock = mockup_extras()
    extras = []
    for ch, cp in EXTRAS:
        ink = bdf_cell(glyphs, cp, dx, ch)
        if mock.get(ch) != ink:
            sys.exit(f"{ch}: the BDF's placement differs from the mockup's EXTRA13")
        extras.append(ink)

    cells = [rows_of(g) for g in atlas + extras]
    lines = [
        "// Copyright 2026 JD Lien",
        "// SPDX-License-Identifier: GPL-2.0-or-later",
        "//",
        "// GENERATED by scripts/gen_mono_font.py -- do not edit. The configuration",
        "// menu's 1-bit small face: Cozette 6x14, the 95 ASCII glyphs as the shipped",
        "// atlas has them (assets-src/current/Iosevka-Medium-13.png, FONT_SMALL), and",
        "// five more from assets-src/cozette.bdf at 0x80-0x84. A byte a row, column 0",
        "// in bit 7.",
        "#pragma once",
        "",
        "#include <stdint.h>",
        "",
        f"#define FONT_MONO_W     {CW}",
        f"#define FONT_MONO_H     {CH}",
        "#define FONT_MONO_FIRST 0x20   /* ' ' */",
        "#define FONT_MONO_ASCII 95     /* 0x20-0x7E */",
        "#define FONT_MONO_XFIRST 0x80  /* the extras' codes */",
        f"#define FONT_MONO_N     {len(cells)}",
        "",
    ]
    for i, (ch, cp) in enumerate(EXTRAS):
        name = {0x2039: "LSAQUO", 0x203A: "RSAQUO", 0x2022: "BULLET", 0x25B8: "TRIANGLE", 0x2713: "CHECK"}[cp]
        lines.append(f'#define FONT_MONO_{name:8} "\\x{0x80 + i:02x}"   /* {ch} U+{cp:04X} */')
    lines += ["", "static const uint8_t font_small_mono[FONT_MONO_N][FONT_MONO_H] = {"]
    for i, rows in enumerate(cells):
        lines.append("    {" + ", ".join(f"0x{r:02X}" for r in rows) + "},   /* " + label(i) + " */")
    lines += ["};", ""]
    text = "\n".join(lines)

    if a.check:
        old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if old != text:
            sys.exit(f"{OUT} is stale: run scripts/gen_mono_font.py")
        print("font_small_mono.h is current")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {OUT}: {len(cells)} glyphs, {len(cells) * CH} B")


if __name__ == "__main__":
    main()
