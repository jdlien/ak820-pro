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
- Then ICONS, JD's picks from the icon picker (10-24,
  scripts/gen_icon_gallery.py), from 0x85, placed by place(): ASCII's shift
  when the ink fits a cell with it, else unshifted; a glyph wider than a cell
  (double width, or 7 px of ink on a 6 px advance) takes two codes, its left
  and right halves. The picker draws with this same place().
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
EXTRA_NAMES = ["LSAQUO", "RSAQUO", "BULLET", "TRIANGLE", "CHECK"]
# JD's picks, 10-24: (the macro's name, the code point, its cells). A code
# is its place in this list; menu_text.h spells the codes, and the host tests
# hold it to these (nothing stores them, so a removal only moves the later
# ones).
ICONS = [
    ("TRI_L", 0x25C0, 1),          # ◀ Back
    ("TRI_R", 0x25B6, 1),          # ▶ a row that opens a page
    ("CURSOR", 0x1FB70, 1),        # the selected row's, in its line's lead (columns 0-2): the thin bar
                                   # (JD, 10-24; U+1FB6C's triangle was "a little too cramped")
    ("WRENCH", 0x1F527, 2),        # 🔧 before "Configuration"
    ("CHECK_BOX", 0xF631, 2),      # the saved option (nf-mdi-checkbox_marked; JD: the circle "doesn't look good")
    ("I_POWER", 0xF0E7, 1),        # the top level's icons: nf-fa-bolt,
    ("I_CLOCK", 0xF017, 2),        # nf-fa-clock,
    ("I_DIAG", 0xF2DB, 1),         # nf-fa-microchip,
    ("I_HELP", 0xF059, 2),         # nf-fa-question_circle,
    ("I_ABOUT", 0xF05A, 2),        # nf-fa-info_circle,
    ("I_EXIT", 0xF00D, 1),         # nf-fa-times;
    ("I_LIGHT", 0xF834, 1),        # P1b: Lighting, nf-mdi-lightbulb (JD's pick),
    ("I_SCREEN", 0xF108, 2),       # Screen, nf-fa-desktop;
    ("I_BOOT", 0xF498, 2),         # the bootloader item, nf-oct-desktop_download
    ("I_IND", 0xF185, 2),          # P2a: Indicators, nf-fa-sun (JD's pick: "super bright light shining in your eye"),
    ("I_CONN", 0xF293, 2),         # Connection, nf-fa-bluetooth (the picker's proposal); in blue, a slot advertising
    ("I_WAIT", 0xF252, 2),         # P3: a slot linking, in grey (JD: "waiting/pending"), nf-fa-hourglass_half
    ("I_FAIL", 0xF057, 2),         # P3: a slot failed, in red (JD: "red x in a circle"), nf-fa-times_circle
    ("I_BATT", 0xF57F, 1),         # P4: Battery, nf-mdi-battery_60 (vertical, the bolt's height; F240 is 7 x 5 px)
    ("I_PROF", 0xE5FE, 1),         # P5b: Profiles, nf-custom-folder_open (JD: "A place where you save stuff")
    ("I_LOAD", 0xF0A8, 2),         # a profile's actions (JD, 10-26): Load, nf-fa-arrow_circle_left ("pointing
                                   # at the keyboard"; the plain arrow looked like Back's, the row above),
    ("I_SAVE", 0xF0A9, 2),         # Save current here, nf-fa-arrow_circle_right,
    ("I_RENAME", 0xF040, 1),       # Rename, nf-fa-pencil,
    ("I_DELETE", 0xF48E, 2),       # Delete, nf-oct-trashcan
]


def read_png(path):
    """-> (w, h, rows of (r, g, b, a)), a = 255 for RGB. 8-bit RGB or RGBA,
    non-interlaced."""
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
        rows.append([tuple(line[x * bpp:x * bpp + 3]) + ((line[x * bpp + 3],) if bpp == 4 else (255,))
                     for x in range(w)])
        prev = line
    return w, h, rows


def atlas_glyphs():
    w, h, px = read_png(ATLAS)
    n = mkbdfatlas.LAST - mkbdfatlas.FIRST + 1
    if (w, h) != (CW * n, CH):
        sys.exit(f"{ATLAS}: {w}x{h}, want {CW * n}x{CH}")
    # Strict, so the check below proves the atlas's RGB565 too, not only its
    # ink: opaque magenta at each cell's (0, 0) and nowhere else, and every
    # other pixel opaque pure black or pure white (codex, 10-24).
    black, white, marker = (0, 0, 0, 255), (255, 255, 255, 255), mkbdfatlas.MARKER + (255,)
    out = []
    for g in range(n):
        ink = set()
        for y in range(CH):
            for x in range(CW):
                v = px[y][g * CW + x]
                if (x, y) == (0, 0):
                    if v != marker:
                        sys.exit(f"{ATLAS}: cell {g}'s marker is {v}, not opaque magenta")
                elif v == white:
                    ink.add((x, y))
                elif v != black:
                    sys.exit(f"{ATLAS}: cell {g} ({x},{y}) is {v}: only opaque black and white are allowed")
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


def dwidths(path):
    """-> {codepoint: DWIDTH} (parse_bdf keeps only the bitmap)."""
    out, enc = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("ENCODING"):
            enc = int(line.split()[1])
        elif line.startswith("DWIDTH") and enc is not None:
            out[enc] = int(line.split()[1])
    return out


def place(g, base, dx):
    """-> (width, shift, kind) for a glyph whose advance is `base` (6, or 12
    for double width): the first of ASCII's shift, none, or flush left that
    keeps the ink inside `base` columns, else inside base + 6. kind: 0 one
    cell, 1 double width, 2 wider than its advance (Cozette's 7 px icons)."""
    px = mkbdfatlas.glyph_pixels(g, BASELINE)
    lo, hi = min(x for x, _ in px), max(x for x, _ in px)
    for w in (base, base + 6):
        for s in (dx, 0, -lo):
            if lo + s >= 0 and hi + s < w:
                return w, s, (1 if base == 12 else 0) if w == base else 2
    sys.exit(f"ink columns {lo}..{hi} fit no cell")


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
    c = chr(0x20 + i)
    return "space" if c == " " else "'\\\\'" if c == "\\" else f"'{c}'"


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
    extras, xlabels, defines = [], [], []
    for (ch, cp), name in zip(EXTRAS, EXTRA_NAMES):
        ink = bdf_cell(glyphs, cp, dx, ch)
        if mock.get(ch) != ink:
            sys.exit(f"{ch}: the BDF's placement differs from the mockup's EXTRA13")
        defines.append((name, [0x80 + len(extras)], f"{ch} U+{cp:04X}"))
        extras.append(ink)
        xlabels.append(f"{ch} U+{cp:04X}")
    dw = dwidths(BDF)
    for name, cp, n in ICONS:
        if cp not in glyphs:
            sys.exit(f"{BDF}: no glyph for U+{cp:04X} ({name})")
        w, s, _ = place(glyphs[cp], 12 if dw.get(cp, 6) > 6 else 6, dx)
        if w // CW != n:
            sys.exit(f"{name} U+{cp:04X}: {w // CW} cells, ICONS says {n}")
        ink = {(x + s, y) for x, y in mkbdfatlas.glyph_pixels(glyphs[cp], BASELINE)}
        if any(not 0 <= y < CH for _, y in ink):
            sys.exit(f"{name} U+{cp:04X}: ink outside the {CH} rows")
        defines.append((name, [0x80 + len(extras) + k for k in range(n)], f"U+{cp:04X}"))
        for k in range(n):
            extras.append({(x - k * CW, y) for x, y in ink if k * CW <= x < (k + 1) * CW})
            xlabels.append(f"{name} U+{cp:04X}" + ("" if n == 1 else " left" if k == 0 else " right"))
    if 0x80 + len(extras) > 0x100:
        sys.exit("more extras than codes 0x80-0xFF")

    cells = [rows_of(g) for g in atlas + extras]
    lines = [
        "// Copyright 2026 JD Lien",
        "// SPDX-License-Identifier: GPL-2.0-or-later",
        "//",
        "// GENERATED by scripts/gen_mono_font.py -- do not edit. The configuration",
        "// menu's 1-bit small face: Cozette 6x14, the 95 ASCII glyphs as the shipped",
        "// atlas has them (assets-src/current/Iosevka-Medium-13.png, FONT_SMALL), and",
        f"// {len(extras)} more from assets-src/cozette.bdf at 0x80-0x{0x7F + len(extras):02X}: five marks, then JD's",
        "// icons (a two-cell icon is two codes). A byte a row, column 0 in bit 7.",
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
    for name, codes, what in defines:
        s = "".join(f"\\x{c:02x}" for c in codes)
        lines.append(f'#define FONT_MONO_{name:12} "{s}"' + " " * (10 - len(s)) + f"/* {what} */")
    lines += ["", "static const uint8_t font_small_mono[FONT_MONO_N][FONT_MONO_H] = {"]
    for i, rows in enumerate(cells):
        lines.append("    {" + ", ".join(f"0x{r:02X}" for r in rows) + "},   /* "
                     + (label(i) if i < 95 else xlabels[i - 95]) + " */")
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
