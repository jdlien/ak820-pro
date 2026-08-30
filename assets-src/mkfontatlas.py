#!/usr/bin/env python3
"""
Render a TTF/OTF into the AK820 Pro's glyph-atlas PNG format.

Emits exactly what mkraw.py expects: one row of fixed-width cells, printable
ASCII 0x20..0x7E, with a magenta (255,0,255) marker at each cell's top-left.
Marker spacing IS the advance and marker count IS the glyph count, so the atlas
is self-describing and mkraw.py needs no changes.

WHY THIS EXISTS: the shipped atlases were rendered WITHOUT HINTING, so stems
landed wherever the outline happened to fall on the pixel grid. Capital P came
out with a 1px left stem while B, D and R all got 2px -- visibly wrong at 10px
wide. Hinting snaps stems to whole pixels, which is the entire point of it at
these sizes.

MONOCHROME BY DEFAULT, deliberately. Anti-aliasing at 10-20px turns a 1px stem
straddling a boundary into two grey columns, which reads as blur rather than
smoothness. Use --aa only for large glyphs (the clock numerals at ~30px), where
there are enough pixels for gradation to read as a smooth edge.

Usage:
  mkfontatlas.py FONT.ttf OUT.png --size 20 --cell 10x23 [--baseline N]
  mkfontatlas.py FONT.ttf OUT.png --size 30 --cell 15x34 --aa
  mkfontatlas.py FONT.ttf --probe --size 20        # report natural metrics
"""
import argparse, sys, zlib, struct

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  ./venv/bin/pip install Pillow")

FIRST, LAST = 0x20, 0x7E
MARKER = (255, 0, 255)


def load(path, size, aa):
    # layout_engine=BASIC keeps Pillow off HarfBuzz so we get plain, predictable
    # positioning; we place each glyph ourselves anyway.
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def probe(font):
    """Natural ink extent across the printable set, to pick a cell size."""
    asc, desc = font.getmetrics()
    lo = hi = 0
    wmax = 0
    for c in range(FIRST, LAST + 1):
        try:
            box = font.getbbox(chr(c))
        except Exception:
            continue
        if box is None:
            continue
        lo = min(lo, box[1]); hi = max(hi, box[3])
        wmax = max(wmax, box[2] - box[0], int(font.getlength(chr(c))))
    return asc, desc, lo, hi, wmax


def render(path, size, cw, ch, baseline, aa):
    font = load(path, size, aa)
    n = LAST - FIRST + 1
    img = Image.new("RGB", (cw * n, ch), (0, 0, 0))
    d = ImageDraw.Draw(img)
    # "L" gives an 8-bit mask which Pillow fills via the FreeType rasteriser;
    # for monochrome we threshold it so every pixel is fully on or fully off.
    for i in range(n):
        c = chr(FIRST + i)
        x0 = i * cw
        # Centre the glyph horizontally in its cell using the real advance.
        adv = font.getlength(c)
        ox = x0 + max(0, int(round((cw - adv) / 2)))
        d.text((ox, baseline), c, font=font, fill=(255, 255, 255), anchor="ls")

    if not aa:
        px = img.load()
        for y in range(ch):
            for x in range(cw * n):
                v = 255 if px[x, y][0] >= 128 else 0
                px[x, y] = (v, v, v)

    # Cell markers last, so nothing overwrites them.
    px = img.load()
    for i in range(n):
        px[i * cw, 0] = MARKER
    return img


def write_png(img, out):
    w, h = img.size
    px = img.load()
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            r, g, b = px[x, y][:3]
            rows += bytes((r, g, b))

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
    ap.add_argument("--size", type=int, required=True, help="ppem to render at")
    ap.add_argument("--cell", help="WxH cell, e.g. 10x23")
    ap.add_argument("--baseline", type=int, help="baseline row within the cell")
    ap.add_argument("--aa", action="store_true", help="anti-alias (large sizes only)")
    ap.add_argument("--probe", action="store_true", help="report metrics and exit")
    a = ap.parse_args()

    if a.probe:
        f = load(a.font, a.size, False)
        asc, desc, lo, hi, wmax = probe(f)
        print(f"size {a.size}: ascent {asc} descent {desc}")
        print(f"  ink rows {lo}..{hi}  (height {hi - lo})")
        print(f"  widest glyph {wmax}px")
        print(f"  suggested cell {wmax}x{asc + desc}, baseline {asc}")
        return

    if not (a.out and a.cell):
        sys.exit("need OUT.png and --cell WxH")
    cw, ch = (int(v) for v in a.cell.lower().split("x"))
    baseline = a.baseline if a.baseline is not None else load(a.font, a.size, False).getmetrics()[0]
    img = render(a.font, a.size, cw, ch, baseline, a.aa)
    write_png(img, a.out)
    print(f"wrote {a.out}: {img.size[0]}x{img.size[1]}, {LAST-FIRST+1} cells of {cw}x{ch}, baseline {baseline}, aa={a.aa}")


if __name__ == "__main__":
    main()
