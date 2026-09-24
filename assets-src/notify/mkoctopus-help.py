#!/usr/bin/env python3
"""The orange octopus waving its tentacles for attention: a human is needed.

Shown when auto mode blocks an action or a turn ends on an error. Same style
as mkoctopus.py (32x32 pixel art scaled 4x, 10 frames of 100 ms): two
tentacles raised overhead waving out of phase, four below, a small bounce,
eyes wide open and a yellow "!" blinking above. Writes claude-octopus-help.gif.
"""
import os
import math
from PIL import Image, ImageDraw

S, K, N = 32, 4, 10
ORANGE, DARK = (255, 128, 20), (200, 80, 10)
HIGHLIGHT, CHEEK = (255, 175, 90), (255, 90, 90)
EYE, SHINE, SHADOW, BG = (20, 20, 30), (255, 255, 255), (60, 30, 5), (0, 0, 0)
ALERT = (255, 220, 40)


def arm(d, x0, y0, t, side):
    """A raised tentacle: from the side of the head, swaying up."""
    pts = []
    for j in range(9):
        # the tip swings a lot, the base hardly
        sway = math.sin(2 * math.pi * t * 2 + (0 if side < 0 else math.pi)) * (j / 8) * 4
        x = x0 + side * (1 + j * 0.45) + sway * side
        y = y0 - j
        pts.append((round(x), y))
    for k, (x, y) in enumerate(pts):
        col = ORANGE if k < len(pts) - 1 else DARK
        d.point((x, y), fill=col)
        d.point((x + (1 if side < 0 else -1), y), fill=col)


def frame(i):
    t = i / N
    bob = round(1.2 * math.sin(2 * math.pi * t * 2))   # a small bounce, twice a cycle
    cx, base = 16, 27 + bob                              # where the lower tentacles start
    w, h = 16, 12
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    d.ellipse([cx - 6, 30, cx + 6, 31], fill=SHADOW)

    for k in range(4):                                  # lower tentacles
        x = cx - 6 + k * 3 + (1 if k > 1 else 0)
        wig = round(math.sin(2 * math.pi * t * 2 + k))
        for j in range(4):
            xx = x + (wig if j >= 2 else 0)
            d.point((xx, base + j), fill=ORANGE if j < 3 else DARK)
            d.point((xx + 1, base + j), fill=ORANGE if j < 2 else DARK)

    top = base - h
    arm(d, cx - w // 2 + 1, top + 6, t, -1)             # arms up, one each side
    arm(d, cx + w // 2 - 2, top + 6, t, +1)

    d.ellipse([cx - w // 2, top, cx + w // 2 - 1, base + 1], fill=ORANGE)
    d.ellipse([cx - w // 2 + 2, top + 1, cx - w // 2 + 5, top + 3], fill=HIGHLIGHT)

    ey = top + 5                                        # eyes wide open
    for ex in (cx - 4, cx + 3):
        d.rectangle([ex - 1, ey - 1, ex + 1, ey + 2], fill=EYE)
        d.point((ex, ey - 1), fill=SHINE)
    d.line([cx - 1, ey + 4, cx, ey + 4], fill=DARK)     # open mouth
    d.point((cx - 6, ey + 3), fill=CHEEK)
    d.point((cx + 5, ey + 3), fill=CHEEK)

    if (i // 2) % 2 == 0:                               # blinking "!"
        d.rectangle([cx - 1, 1, cx, 5], fill=ALERT)
        d.rectangle([cx - 1, 7, cx, 8], fill=ALERT)
    return img.resize((S * K, S * K), Image.NEAREST)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-octopus-help.gif")
    frames = [frame(i) for i in range(N)]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=100, loop=0)
    print(f"{out}: {len(frames)} frames")
