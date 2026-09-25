#!/usr/bin/env python3
"""The two screensaver animations (AMBIENT: the board idle for a while).

claude-octopus-sleep.gif  no Claude Code session at work: the octopus sleeps,
                          squashed, eyes closed, breathing slowly, "z"s rising
                          and fading. Slightly darker: it stays on screen long.
claude-octopus-work.gif   a session at work: the octopus behind a little
                          keyboard, two tentacles typing in turn, the pressed
                          key lighting up.

Same style as mkoctopus.py: 32x32 pixel art scaled 4x, 10 frames of 100 ms.
"""
import os
import math
from PIL import Image, ImageDraw

S, K, N = 32, 4, 10
BG = (0, 0, 0)


def scaled(img):
    return img.resize((S * K, S * K), Image.NEAREST)


# ------------------------------------------------------------------- sleep
def sleep(i):
    ORANGE, DARK, HI = (200, 100, 20), (150, 65, 10), (215, 140, 70)
    EYE, Z = (60, 40, 30), (120, 140, 200)
    t = i / N
    breath = math.sin(2 * math.pi * t)            # one breath per cycle (1 s)
    w, h = 20, 9 + round(breath)                  # wide and low: lying down
    cx, base = 14, 27
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    for k in range(6):                            # tentacles flat on the ground, still
        x = cx - 9 + k * 3 + (1 if k > 2 else 0)
        d.line([x, base, x + (1 if k > 2 else -1), base + 2], fill=ORANGE)
        d.point((x + (1 if k > 2 else -1), base + 3), fill=DARK)
    top = base - h
    d.ellipse([cx - w // 2, top, cx + w // 2 - 1, base + 1], fill=ORANGE)
    d.ellipse([cx - w // 2 + 3, top + 1, cx - w // 2 + 6, top + 2], fill=HI)
    ey = base - h // 2
    for ex in (cx - 4, cx + 3):                   # closed eyes
        d.line([ex - 1, ey, ex, ey + 1, ex + 1, ey], fill=EYE)
    # three "z"s rising diagonally and fading, staggered in time
    for k in range(3):
        p = (t + k / 3) % 1.0                     # 0 just born, 1 gone
        zx = round(cx + 7 + p * 6)
        zy = round(top - 1 - p * 12)
        fade = 1 - p
        col = tuple(round(c * fade) for c in Z)
        size = 2 if p < 0.5 else 3
        d.line([zx, zy, zx + size, zy], fill=col)
        d.line([zx + size, zy, zx, zy + size], fill=col)
        d.line([zx, zy + size, zx + size, zy + size], fill=col)
    return scaled(img)


# ------------------------------------------------------------------- work
def work(i):
    ORANGE, DARK, HI = (255, 128, 20), (200, 80, 10), (255, 175, 90)
    EYE, SHINE = (20, 20, 30), (255, 255, 255)
    KB, KEY, LIT = (70, 70, 80), (110, 110, 125), (0, 230, 255)
    t = i / N
    cx, base = 16, 17
    w, h = 16, 12
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    top = base - h
    d.ellipse([cx - w // 2, top, cx + w // 2 - 1, base + 1], fill=ORANGE)
    d.ellipse([cx - w // 2 + 2, top + 1, cx - w // 2 + 5, top + 3], fill=HI)
    ey = top + 6                                  # eyes looking down
    for ex in (cx - 4, cx + 3):
        d.rectangle([ex - 1, ey, ex + 1, ey + 1], fill=EYE)
        d.point((ex + 1, ey + 1), fill=SHINE)
    # the little keyboard: 8 keys in a row, in front of the octopus
    d.rectangle([4, 26, 27, 31], fill=KB)
    keys = [5 + k * 3 for k in range(8)]
    # two tentacles type in turn: the left on keys 0-3, the right on 4-7,
    # a different key each stroke (a fixed sequence that looks random)
    seq_l, seq_r = [1, 3, 0, 2, 1], [5, 7, 4, 6, 5]
    beat = i % 2                                  # 0: the left types, 1: the right
    step = i // 2
    hit = seq_l[step % 5] if beat == 0 else seq_r[step % 5]
    for k, x in enumerate(keys):
        d.rectangle([x, 27, x + 1, 28], fill=LIT if k == hit else KEY)
    for side, seq in ((0, seq_l), (1, seq_r)):
        target = keys[seq[step % 5]] if beat == side else keys[seq[(step + side) % 5]]
        down = beat == side                       # this tentacle is pressing
        x0 = cx - 5 if side == 0 else cx + 4
        y0 = base - 1
        y1 = 26 if down else 22
        for j in range(0, 9):                     # tentacle from body to key
            fx = j / 8
            x = round(x0 + (target - x0) * fx)
            y = round(y0 + (y1 - y0) * fx)
            d.point((x, y), fill=ORANGE if j < 8 else DARK)
            d.point((x + 1, y), fill=ORANGE if j < 8 else DARK)
    for k in range(4):                            # the other tentacles hang behind
        x = cx - 6 + k * 4
        d.line([x, base, x, base + 3], fill=DARK)
    return scaled(img)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, fn in (("claude-octopus-sleep", sleep), ("claude-octopus-work", work)):
        frames = [fn(i) for i in range(N)]
        out = os.path.join(here, name + ".gif")
        frames[0].save(out, save_all=True, append_images=frames[1:], duration=100, loop=0)
        print(f"{out}: {len(frames)} frames")
