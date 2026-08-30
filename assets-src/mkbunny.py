#!/usr/bin/env python3
"""Bunny logo -> 128x128 white-on-black splash for the AK820 Pro LCD.

The source is BLACK ink on a TRANSPARENT ground, so the alpha channel IS the
shape. The panel draws on black, so we invert: ink -> white, transparent ->
black. That also makes the artwork's negative space (face, inner ear) read as
dark, which is how the logo is meant to look on a dark ground.

Downsampling is an AREA AVERAGE, not nearest-neighbour: 612x792 -> ~90x116 is a
6.8x reduction, and point-sampling that would shred the thin ear strokes. The
grey edge values it produces cost nothing, since the target is RGB565 anyway.
"""
import sys, os, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if False else "/Users/jdlien/code/ak820-pro/time-util-ak820pro/assets")
from mkraw import decode_png

SRC = "/Users/jdlien/Library/Mobile Documents/com~apple~CloudDocs/Projects/Bunny Logo/1x/Artboard 1.png"
DST = "/Users/jdlien/code/ak820-pro/time-util-ak820pro/assets/sonixqmk.png"
OUT_W = OUT_H = 128
TARGET_H = 116          # leave a margin: the LCD is recessed and the bezel clips edges

w, h, px = decode_png(SRC)
print(f"source {w}x{h}")

# alpha = ink coverage; inverted output means white where the ink was
alpha = [px[y * w + x][3] for y in range(h) for x in range(w)]

scale = TARGET_H / h
dst_h = TARGET_H
dst_w = max(1, round(w * scale))
print(f"scaled to {dst_w}x{dst_h}")

# box filter: average the source rectangle that maps to each destination pixel
small = [0] * (dst_w * dst_h)
for dy in range(dst_h):
    y0 = int(dy * h / dst_h); y1 = max(y0 + 1, int((dy + 1) * h / dst_h))
    for dx in range(dst_w):
        x0 = int(dx * w / dst_w); x1 = max(x0 + 1, int((dx + 1) * w / dst_w))
        tot = n = 0
        for sy in range(y0, y1):
            base = sy * w
            for sx in range(x0, x1):
                tot += alpha[base + sx]; n += 1
        small[dy * dst_w + dx] = tot // n

ox = (OUT_W - dst_w) // 2
oy = (OUT_H - dst_h) // 2
print(f"centred at +{ox},+{oy}")

# compose onto black, emit colour type 2 (rgb) to match the asset it replaces
rows = bytearray()
for y in range(OUT_H):
    rows.append(0)                                  # filter type 0 (None)
    for x in range(OUT_W):
        v = 0
        if oy <= y < oy + dst_h and ox <= x < ox + dst_w:
            v = small[(y - oy) * dst_w + (x - ox)]
        rows += bytes((v, v, v))

def chunk(typ, data):
    return (struct.pack(">I", len(data)) + typ + data +
            struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", OUT_W, OUT_H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
       + chunk(b"IEND", b""))
open(DST, "wb").write(png)

lit = sum(1 for i in range(0, len(rows)) if False)  # placeholder
nonblack = sum(1 for y in range(OUT_H) for x in range(OUT_W)
               if (oy <= y < oy + dst_h and ox <= x < ox + dst_w and small[(y-oy)*dst_w + (x-ox)] > 8))
print(f"wrote {DST}  ({len(png)} bytes)  ink coverage {100*nonblack/(OUT_W*OUT_H):.1f}%")
