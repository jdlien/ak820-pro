#!/usr/bin/env python3
"""The orange octopus waiting for a question: it is arriving from the host.

Shown from GIF slot 5 while an ASK frame comes in over the LED channel (the
board ignores keys meanwhile, see docs/notify.md). Same style as
mkoctopus.py (32x32 pixel art scaled 4x, 100 ms frames): the octopus looks
up at a ring of eight yellow dots spinning over its head, a bar fills
underneath. 12 frames, one turn of the ring (a slot holds 15 at most).
Writes claude-octopus-load.gif.
"""
import os
import math
from PIL import Image, ImageDraw

S, K, N = 32, 4, 12
ORANGE, DARK = (255, 128, 20), (200, 80, 10)
HIGHLIGHT, CHEEK = (255, 175, 90), (255, 90, 90)
EYE, SHINE, SHADOW, BG = (20, 20, 30), (255, 255, 255), (60, 30, 5), (0, 0, 0)
DOT, DIM = (255, 220, 40), (130, 105, 25)
BAR, TRACK = (255, 220, 40), (50, 40, 10)


def frame(i):
    t = i / N
    cx, base = 16, 24
    w, h = 16, 12
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    # The ring: a bright head going round with a two-dot trail.
    ox, oy, r = cx, 6, 4
    for k in range(8):
        a = 2 * math.pi * k / 8 - math.pi / 2
        x, y = round(ox + r * math.cos(a)), round(oy + r * math.sin(a))
        lag = (i * 8 // N - k) % 8
        col = DOT if lag == 0 else (tuple(c * 2 // 3 for c in DOT) if lag == 1 else DIM)
        d.point((x, y), fill=col)

    d.ellipse([cx - 6, base + 4, cx + 6, base + 5], fill=SHADOW)
    for k in range(4):                                  # tentacles, a slow wave
        x = cx - 6 + k * 3 + (1 if k > 1 else 0)
        wig = round(0.8 * math.sin(2 * math.pi * t + k))
        for j in range(4):
            xx = x + (wig if j >= 2 else 0)
            d.point((xx, base + j), fill=ORANGE if j < 3 else DARK)
            d.point((xx + 1, base + j), fill=ORANGE if j < 2 else DARK)

    top = base - h
    d.ellipse([cx - w // 2, top, cx + w // 2 - 1, base + 1], fill=ORANGE)
    d.ellipse([cx - w // 2 + 2, top + 1, cx - w // 2 + 5, top + 3], fill=HIGHLIGHT)

    ey = top + 5                                        # eyes looking up
    blink = i == 7
    for ex in (cx - 4, cx + 3):
        if blink:
            d.line([ex - 1, ey + 1, ex + 1, ey + 1], fill=EYE)
        else:
            d.rectangle([ex - 1, ey - 1, ex + 1, ey + 1], fill=EYE)
            d.point((ex, ey - 1), fill=SHINE)
    d.line([cx - 1, ey + 4, cx, ey + 4], fill=DARK)
    d.point((cx - 6, ey + 3), fill=CHEEK)
    d.point((cx + 5, ey + 3), fill=CHEEK)

    # The bar: fills in one turn and starts again.
    x0, x1, y = 4, 27, 30
    d.line([x0, y, x1, y], fill=TRACK)
    fill = x0 + round((x1 - x0) * (i + 1) / N)
    d.line([x0, y, fill, y], fill=BAR)
    return img.resize((S * K, S * K), Image.NEAREST)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-octopus-load.gif")
    frames = [frame(i) for i in range(N)]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=100, loop=0)
    print(f"{out}: {len(frames)} frames")
