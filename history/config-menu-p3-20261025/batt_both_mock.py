"""The dashboard's battery row with hours AND percent, from the shipped status
font (assets-src/current/Iosevka-Medium-20.png, 10x23 cells), laid out as
display.c draws it: battery at x 5..28 + nub, the 13 px icon slot at 35..47,
the text right-aligned to end at x 123 (PANEL_WIDTH - 4)."""
import os
import sys
from PIL import Image

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets-src", "current", "Iosevka-Medium-20.png")
W, H = 10, 23
STATUS_Y = 105
BULB = ["......#......", ".#.........#.", "..#.......#..", ".....###.....",
        "...#######...", "##.#######.##", "..#########..", "..#########..",
        "..#########..", "...#######...", "....#####....", "....=====....",
        "....+++++....", ".....+++....."]
atlas = Image.open(A).convert("RGB")


def ink(px):
    r, g, b = px
    return not (r > 200 and b > 200 and g < 80) and r + g + b > 300


def glyph_cols(ch):
    c = ord(ch) - 32
    cols = [gx for gx in range(W) for gy in range(H) if ink(atlas.getpixel((c * W + gx, gy)))]
    return (min(cols), max(cols)) if cols else None


def row(text, gap=None):
    """`gap`: None draws `text` in uniform 10 px cells (as now); a number
    splits it at its space and closes the space to `gap` px."""
    img = Image.new("RGB", (128, 30), (0, 0, 0))
    y0 = 5   # STATUS_Y + 5 - 105
    for x in range(5, 29):
        img.putpixel((x, y0), (0, 220, 0)); img.putpixel((x, y0 + 11), (0, 220, 0))
    for y in range(y0, y0 + 12):
        img.putpixel((5, y), (0, 220, 0)); img.putpixel((28, y), (0, 220, 0))
    for y in range(y0 + 4, y0 + 8):
        for x in (29, 30):
            img.putpixel((x, y), (0, 220, 0))
    for y in range(y0 + 2, y0 + 10):
        for x in range(7, 22):
            img.putpixel((x, y), (0, 220, 0))
    for y, r in enumerate(BULB):
        for x, c in enumerate(r):
            if c != ".":
                img.putpixel((35 + x, y0 - 2 + y), (255, 255, 255) if c == "#" else (180, 180, 180))
    if gap is None:
        parts, widths = [text], [len(text) * W]
    else:
        a, b = text.split(" ")
        parts, widths = [a, b], [len(a) * W, len(b) * W]
    total = sum(widths) + (gap or 0) * (len(parts) - 1)
    x = 124 - total
    ok = x >= 48
    for p in parts:
        for ch in p:
            c = ord(ch) - 32
            for gy in range(H):
                for gx in range(W):
                    if ink(atlas.getpixel((c * W + gx, gy))):
                        img.putpixel((x + gx, gy), (255, 255, 255) if ok else (255, 60, 60))
            x += W
        x += gap or 0
    return img, 124 - total


cases = [("62% 31h", None), ("18% 6h", None), ("99% 160h", None), ("99% 160h", 6), ("99% 160h", 4),
         ("99%160h", None), ("100% 160h", 4), ("100%", None), ("160h", None)]
for ch in "0123456789%h<":
    print(repr(ch), glyph_cols(ch))
S, pad = 5, 8
sheet = Image.new("RGB", (128 * S + 2 * pad + 260, len(cases) * (30 * S + pad) + pad), (40, 40, 40))
from PIL import ImageDraw
d = ImageDraw.Draw(sheet)
for i, (t, g) in enumerate(cases):
    im, x0 = row(t, g)
    y = pad + i * (30 * S + pad)
    sheet.paste(im.resize((128 * S, 30 * S), Image.NEAREST), (pad, y))
    need = 124 - x0
    d.text((128 * S + 2 * pad, y + 50), f"{t!r} gap={g}  {need} px of 76  {'fits' if x0 >= 48 else 'NO'}", fill=(255, 255, 255))
    print(f"{t!r:12} gap={g}: needs {need} px of 76 (starts x={x0}) {'fits' if x0 >= 48 else 'DOES NOT FIT'}")
out = sys.argv[1]
sheet.save(out)
print("wrote", out)
