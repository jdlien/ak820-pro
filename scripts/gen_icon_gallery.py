#!/usr/bin/env python3
"""The Cozette icon picker (an artifact for JD, 10-24): every icon-like glyph
in assets-src/cozette.bdf, placed in the menu face's cell exactly as
scripts/gen_mono_font.py places the extras (mkbdfatlas.py: baseline row 9,
its xshift), in the menu's colours, to shortlist icons for the menu.

    python scripts/gen_icon_gallery.py OUT.html [--names glyphnames.json ...] < /dev/null

--names takes Nerd Fonts' name lists (github.com/ryanoasis/nerd-fonts), so
the private-use icons, which have no Unicode names, can be searched by name:
v3's glyphnames.json, and v2.3.3's css/nerd-fonts-generated.css (v2 has no
JSON) for the nf-mdi block Cozette still carries in the BMP's private use
area. 10-24's page used v3.2.1 and v2.3.3.

Each glyph is placed as an extra would be (kind, the last field):
0  one 6x14 cell: ASCII's shift if the ink fits with it, else unshifted (box
   drawing and the full blocks use columns 0-5);
1  two cells, 12x14: designed double width (DWIDTH 12);
2  two cells: 7 px of ink on a 6 px advance (columns 0-6, overlapping both
   neighbours by design, as half of Cozette's icons are), so no one cell
   holds it; placed unshifted in 12.
No glyph in these ranges crosses the 14 rows (checked: it refuses)."""
import argparse
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "assets-src"))
import mkbdfatlas  # noqa: E402

BDF = os.path.join(ROOT, "assets-src", "cozette.bdf")
CH, BASELINE = 14, 9
CATS = [
    ("Nerd Font icons", [(0xE000, 0xF8FF)]),
    ("Material icons", [(0xF0000, 0xFFFFF)]),
    ("Emoji and pictographs", [(0x1F000, 0x1FAFF)]),
    ("Arrows", [(0x2190, 0x21FF), (0x27F0, 0x27FF), (0x2900, 0x297F), (0x2B00, 0x2B2F), (0x2B4C, 0x2BFF)]),
    ("Shapes, boxes and blocks", [(0x2500, 0x25FF), (0x1FB00, 0x1FBFF)]),
    ("Symbols and dingbats", [(0x2010, 0x205E), (0x2100, 0x218F), (0x2300, 0x23FF), (0x2600, 0x27BF),
                              (0x2B30, 0x2B4B)]),
]


def dwidths(path):
    out, enc = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("ENCODING"):
            enc = int(line.split()[1])
        elif line.startswith("DWIDTH") and enc is not None:
            out[enc] = int(line.split()[1])
    return out


def place(g, base, dx):
    """-> (width, shift, kind) for a glyph whose advance is `base`."""
    px = mkbdfatlas.glyph_pixels(g, BASELINE)
    lo, hi = min(x for x, _ in px), max(x for x, _ in px)
    for w in (base, base + 6):
        for s in (dx, 0, -lo):
            if lo + s >= 0 and hi + s < w:
                return w, s, (1 if base == 12 else 0) if w == base else 2
    sys.exit(f"ink columns {lo}..{hi} fit no cell")


def raster(g, w, s, cp=0):
    rows = [0] * CH
    for x0, y in mkbdfatlas.glyph_pixels(g, BASELINE):
        x = x0 + s
        if not (0 <= x < w and 0 <= y < CH):
            sys.exit(f"U+{cp:04X}: ink at ({x},{y}) outside {w}x{CH}")
        rows[y] |= 1 << (w - 1 - x)
    digits = (w + 3) // 4
    return "".join(f"{r:0{digits}x}" for r in rows)


def nerd_names(paths):
    names = {}
    css = re.compile(r'\.(nf-[a-z0-9_-]+):before\s*\{\s*content:\s*"\\([0-9a-fA-F]+)"')
    for path in paths:
        text = open(path, encoding="utf-8").read()
        if path.endswith(".css"):
            pairs = [(m.group(1), m.group(2)) for m in css.finditer(text)]
        else:
            pairs = [("nf-" + k, v["code"]) for k, v in json.loads(text).items() if k != "METADATA"]
        for key, code in pairs:
            names.setdefault(int(code, 16), []).append(key)
    return {cp: " ".join(dict.fromkeys(n)) for cp, n in names.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--names", action="append", default=[])
    args = ap.parse_args()
    out = args.out
    nerd = nerd_names(args.names)
    glyphs = mkbdfatlas.parse_bdf(BDF)
    dw = dwidths(BDF)
    dx = mkbdfatlas.xshift(glyphs)
    data, seen = [], set()
    for k, (_, ranges) in enumerate(CATS):
        for a, b in ranges:
            for cp in range(a, b + 1):
                if cp not in glyphs or cp in seen:
                    continue
                seen.add(cp)
                if not mkbdfatlas.glyph_pixels(glyphs[cp], BASELINE):
                    continue   # blank
                w, s, kind = place(glyphs[cp], 12 if dw.get(cp, 6) > 6 else 6, dx)
                bits = raster(glyphs[cp], w, s, cp)
                try:
                    name = unicodedata.name(chr(cp)).lower()
                except ValueError:
                    name = nerd.get(cp, "")
                data.append([cp, w, bits, name, k, kind])
    ascii_ = {}
    for cp in range(0x20, 0x7F):
        ascii_[cp] = raster(glyphs[cp], 6, dx, cp)
    page = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_gallery_template.html"),
                encoding="utf-8").read()
    page = page.replace("/*DATA*/", json.dumps(data, separators=(",", ":")))
    page = page.replace("/*ASCII*/", json.dumps(ascii_, separators=(",", ":")))
    page = page.replace("/*CATS*/", json.dumps([c[0] for c in CATS]))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print(f"wrote {out}: {len(data)} glyphs; one cell {sum(1 for d in data if d[5] == 0)}, "
          f"double width {sum(1 for d in data if d[5] == 1)}, 7 px {sum(1 for d in data if d[5] == 2)}")


if __name__ == "__main__":
    main()
