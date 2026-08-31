#!/usr/bin/env python3
"""
Import a BDF bitmap font into the AK820 Pro's glyph-atlas PNG format.

Emits exactly what mkraw.py expects: one row of fixed-width cells, printable
ASCII 0x20..0x7E, magenta (255,0,255) marker at each cell's top-left. Marker
spacing IS the advance and marker count IS the glyph count.

WHY A SECOND IMPORTER, ALONGSIDE mkfontatlas.py: at 13px an outline font is a
LOTTERY. Iosevka lost it repeatedly -- capital P's stem collapsed at size 20,
lowercase t doubled at 14, the b/h/p arch joins had to be closed by hand, and
'j' shipped with a 2px stem where every other lowercase stem is 1px. Each was
patched individually; none of the patches survives a regeneration.

A BDF carries the pixels a human already placed. There is no ppem to choose, no
hinting mode, no threshold -- so the entire class of defect stops existing, and
the output is byte-reproducible instead of depending on the FreeType version
that happened to be installed. That is the whole argument for this file.

THE BASELINE IS PINNED, NOT DERIVED. display.c centres text on the transport
icon by its cap-to-baseline ink (TEXT_FONT_DY, TEXT_BIG_DY, the icon_y ladder in
draw_text_slot), and the two-line layout stacks cells exactly TEXT_LINE_H apart.
Landing the new baseline on the row the old one used keeps every one of those
constants correct, which is what makes a font swap an ASSETS-ONLY change: same
cell, same glyph count, same filename -> flash_assets.h comes out byte-identical,
so no firmware rebuild and no asset-id shift. Let the baseline float and you buy
a firmware change for nothing.

Usage:
  mkbdfatlas.py FONT.bdf OUT.png [--cell 7x14] [--baseline 9]
  mkbdfatlas.py FONT.bdf --probe            # ink extents, to choose a baseline
"""
import argparse, sys, zlib, struct

FIRST, LAST = 0x20, 0x7E
MARKER = (255, 0, 255)


def parse_bdf(path):
    """-> {codepoint: (w, h, xoff, yoff, [rows of ints])}

    BDF geometry, since it is easy to get subtly wrong: BBX w h xoff yoff places
    the bitmap's LOWER-LEFT corner at (xoff, yoff) relative to the origin, which
    sits on the baseline at the left edge of the advance. Bitmap rows are listed
    TOP first, and each row is hex padded up to a whole number of bytes.
    """
    glyphs = {}
    enc = bbx = None
    rows = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("ENCODING"):
            enc = int(line.split()[1])
        elif line.startswith("BBX"):
            bbx = tuple(int(v) for v in line.split()[1:5])
        elif line == "BITMAP":
            rows = []
        elif line == "ENDCHAR":
            if rows is not None and bbx and enc is not None and enc >= 0:
                glyphs[enc] = (*bbx, rows)
            enc = bbx = None
            rows = None
        elif rows is not None and line:
            rows.append(int(line, 16))
    return glyphs


def glyph_pixels(g, baseline):
    """-> set of (col, row) in CELL coordinates, with row `baseline` being the
    last row occupied by a glyph that does not descend."""
    w, h, xoff, yoff, rows = g
    nybbles = (w + 7) // 8 * 2          # hex digits per row, byte-padded
    out = set()
    for r, val in enumerate(rows):
        bits = val << (0 if nybbles * 4 == w else 0)
        for c in range(w):
            # MSB of the padded row is column 0.
            if (val >> (nybbles * 4 - 1 - c)) & 1:
                out.add((xoff + c, baseline - (yoff + h - 1 - r)))
    return out


def probe(glyphs):
    lo = hi = None
    xlo = xhi = None
    missing = [c for c in range(FIRST, LAST + 1) if c not in glyphs]
    for c in range(FIRST, LAST + 1):
        if c not in glyphs:
            continue
        px = glyph_pixels(glyphs[c], 0)      # baseline 0 -> rows are -k
        if not px:
            continue
        ys = [y for _, y in px]; xs = [x for x, _ in px]
        lo = min(ys) if lo is None else min(lo, min(ys))
        hi = max(ys) if hi is None else max(hi, max(ys))
        xlo = min(xs) if xlo is None else min(xlo, min(xs))
        xhi = max(xs) if xhi is None else max(xhi, max(xs))
    print(f"printable ASCII: {LAST-FIRST+1-len(missing)}/{LAST-FIRST+1} present")
    if missing:
        print("  MISSING:", " ".join(hex(c) for c in missing))
    print(f"  ink rows {lo}..{hi} relative to the baseline row (0 = baseline row)")
    print(f"  -> {-lo} rows above the baseline row, {hi} below")
    print(f"  ink cols {xlo}..{xhi}")
    print(f"  suggested: --cell {xhi-xlo+2}x{hi-lo+2} --baseline {-lo}")


def xshift(glyphs):
    """Normalise the left side bearing so the leftmost ink column is 0.

    Cozette is designed on a 6px advance with a 1px left bearing (ink cols 1..6);
    the shipped Iosevka atlas starts its ink at col 0 in a 7px cell. Landing the
    new font on col 0 too keeps TEXT_X and TEXT_X2 meaning exactly what they
    meant before -- otherwise every string moves a pixel right, which eats into
    the margin the recessed bezel already wants at the 18-character end.

    The 7px cell against a 6px design also means the spare column becomes
    letterspacing, so col 6 stays blank for every glyph and the 1px gap the
    renderer relies on is preserved.
    """
    lo = min(x for c in range(FIRST, LAST + 1) if c in glyphs
             for x, _ in glyph_pixels(glyphs[c], 0))
    return -lo


def render(glyphs, cw, ch, baseline, dx):
    n = LAST - FIRST + 1
    img = [[(0, 0, 0)] * (cw * n) for _ in range(ch)]
    clipped = []
    for i in range(n):
        c = FIRST + i
        if c not in glyphs:
            sys.exit(f"font has no glyph for {c:#04x} ({chr(c)!r})")
        for (x0, y) in glyph_pixels(glyphs[c], baseline):
            x = x0 + dx
            if not (0 <= x < cw and 0 <= y < ch):
                clipped.append((chr(c), x, y))
                continue
            img[y][i * cw + x] = (255, 255, 255)
    if clipped:
        # Silent clipping is how you ship a font with its descenders shaved off
        # (see the clock atlas in CLAUDE.md). Refuse instead.
        sys.exit("glyph ink falls outside the cell: " +
                 ", ".join(f"{ch_!r}@({x},{y})" for ch_, x, y in clipped[:12]) +
                 (f" ... and {len(clipped)-12} more" if len(clipped) > 12 else "") +
                 "\nwiden --cell or move --baseline")
    for i in range(n):                      # markers last: nothing overwrites them
        img[0][i * cw] = MARKER
    return img


def write_png(img, out):
    h = len(img); w = len(img[0])
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows += bytes(img[y][x])

    def chunk(t, dt):
        return struct.pack(">I", len(dt)) + t + dt + struct.pack(">I", zlib.crc32(t + dt) & 0xFFFFFFFF)

    open(out, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("font")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--cell", default="7x14", help="WxH cell (default 7x14)")
    ap.add_argument("--baseline", type=int, default=9,
                    help="cell row holding the bottom of a non-descending glyph "
                         "(default 9, matching the shipped atlas)")
    ap.add_argument("--xshift", type=int, default=None,
                    help="horizontal nudge; default normalises the leftmost ink "
                         "column to 0, matching the shipped atlas")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()

    glyphs = parse_bdf(a.font)
    if a.probe:
        probe(glyphs)
        return
    if not a.out:
        sys.exit("need OUT.png")
    cw, ch = (int(v) for v in a.cell.lower().split("x"))
    dx = a.xshift if a.xshift is not None else xshift(glyphs)
    img = render(glyphs, cw, ch, a.baseline, dx)
    write_png(img, a.out)
    print(f"wrote {a.out}: {cw*(LAST-FIRST+1)}x{ch}, "
          f"{LAST-FIRST+1} cells of {cw}x{ch}, baseline row {a.baseline}, "
          f"xshift {dx:+d}")


if __name__ == "__main__":
    main()
