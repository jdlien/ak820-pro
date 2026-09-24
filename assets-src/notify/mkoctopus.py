#!/usr/bin/env python3
"""The hopping orange octopus shown when Claude Code finishes a turn.

Pixel art drawn procedurally at 32x32 and scaled 4x (nearest) to the 128x128
panel: 10 frames, 100 ms each -- the firmware's fixed GIF rate. It squashes on
landing (eyes closed), stretches on the way up, and its six tentacles wave out
of phase. Writes claude-octopus.gif next to this script.

    ./venv/bin/python assets-src/notify/mkoctopus.py
    ./venv/bin/python hostagent/ak820notify.py gif-upload 1 assets-src/notify/claude-octopus.gif
"""
import math
import os

from PIL import Image, ImageDraw

S, K = 32, 4                       # canvas, scale -> 128x128
N = 10                             # frames per hop
ORANGE, DARK = (255, 128, 20), (200, 80, 10)
HIGHLIGHT, CHEEK = (255, 175, 90), (255, 90, 90)
EYE, SHINE, SHADOW, BG = (20, 20, 30), (255, 255, 255), (60, 30, 5), (0, 0, 0)


def frame(i):
    t = i / N
    hop = abs(math.sin(math.pi * t))          # 0 on the ground, 1 at the top
    squash = 1 - hop if hop < 0.25 else 0     # only near the ground
    w = 16 + round(4 * squash)                # head width
    h = 13 - round(3 * squash)                # head height
    cx, base = 16, 26 + round(-9 * hop)       # base = where the tentacles start
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    sw = round(12 - 6 * hop)                  # shadow shrinks as it rises
    d.ellipse([cx - sw // 2, 29, cx + sw // 2, 30], fill=SHADOW)

    for k in range(6):                        # tentacles, symmetric about cx
        x = cx - 8 + k * 3
        wig = round(1.5 * math.sin(2 * math.pi * t * 2 + k))
        length = 4 + round(2 * hop)
        for j in range(length):
            xx = x + (wig if j >= length // 2 else 0)
            d.point((xx, base + j), fill=ORANGE if j < length - 1 else DARK)
            d.point((xx + 1, base + j), fill=ORANGE if j < length - 2 else DARK)

    d.ellipse([cx - w // 2, base - h, cx + w // 2 - 1, base + 1], fill=ORANGE)
    d.ellipse([cx - w // 2 + 2, base - h + 1, cx - w // 2 + 5, base - h + 3], fill=HIGHLIGHT)

    ey = base - h // 2 - 1
    for ex in (cx - 4, cx + 3):               # happy closed eyes when squashed
        if squash > 0.3:
            d.line([ex - 1, ey + 1, ex, ey, ex + 1, ey + 1], fill=EYE)
        else:
            d.rectangle([ex - 1, ey - 1, ex + 1, ey + 1], fill=EYE)
            d.point((ex, ey - 1), fill=SHINE)
    d.point((cx - 6, ey + 2), fill=CHEEK)
    d.point((cx + 5, ey + 2), fill=CHEEK)
    return img.resize((S * K, S * K), Image.NEAREST)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-octopus.gif")
    frames = [frame(i) for i in range(N)]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=100, loop=0)
    print(f"{out}: {len(frames)} frames")
