#!/usr/bin/env python3
"""Render Fn+D's camera page as the firmware draws it, from the SHIPPED font
atlases (assets-src/current/), so a layout can be judged before a build.

The layout mirrors display.c's cam_lines[] exactly: each line is a fixed grid
of `cols` cells centred on the 128 px panel, and the text is centred in the
grid by padding ((cols - n) // 2 leading spaces). Keep the two in step.

  scripts/camera_page_preview.py out.png [--scale 3]

Renders a sheet of typical and edge cases. Needs Pillow (the venv has it).
"""
import argparse, os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "..", "assets-src", "current")
FONTS = {"clock": ("Iosevka-Regular-30.png", 15, 22), "status": ("Iosevka-Medium-20.png", 10, 23)}
# display.c cam_lines[]: (font, cols, y)
LINES = [("clock", 8, 4), ("clock", 7, 32), ("clock", 8, 64), ("status", 11, 98)]
CASES = [("3.712V", "58%", "14:03:27", "5C 62@3"),
         (">4.036V", "100%", "09:41:05", "5C 100@1"),
         ("<3.161V", "3%", "23:58:40", "5C 0@2"),
         ("-.---V", "--%", "--:--:--", "5C --")]


def load():
    return {k: (Image.open(os.path.join(A, f)).convert("RGB"), w, h) for k, (f, w, h) in FONTS.items()}


def ink(px):
    r, g, b = px
    return not (r > 200 and b > 200 and g < 80) and r + g + b > 300   # bright, not the magenta marker


def page(atlas, texts):
    img = Image.new("RGB", (128, 128), (0, 0, 0))
    for (font, cols, y), s in zip(LINES, texts):
        a, w, h = atlas[font]
        s = s[:cols]
        x0 = (128 - cols * w) // 2
        x = x0 + ((cols - len(s)) // 2) * w
        for i, ch in enumerate(s):
            c = ord(ch) - 32
            for gy in range(h):
                for gx in range(w):
                    if 0 <= c < 95 and ink(a.getpixel((c * w + gx, gy))):
                        img.putpixel((x + i * w + gx, y + gy), (255, 255, 255))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--scale", type=int, default=3)
    a = ap.parse_args()
    atlas, S, pad = load(), a.scale, 12
    sheet = Image.new("RGB", (len(CASES) * (128 * S + pad) + pad, 128 * S + 2 * pad), (40, 40, 40))
    for i, c in enumerate(CASES):
        sheet.paste(page(atlas, c).resize((128 * S, 128 * S), Image.NEAREST), (pad + i * (128 * S + pad), pad))
    sheet.save(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
