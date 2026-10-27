"""The Power page with each mode's bulb right-aligned on its row (JD, 10-27:
"use the power mode icons that we show on the battery row, right aligned on
the right edge"). The page is the menu host build's own frame (power-*.ppm,
menu_power_dump.c); the bulbs are display.c's bulb_art in its colours."""
import sys
from PIL import Image, ImageDraw

D = sys.argv[1]
ART = {
    "full": ["......#......", ".#.........#.", "..#.......#..", ".....###.....", "...#######...", "##.#######.##",
             "..#########..", "..#########..", "..#########..", "...#######...", "....#####....", "....=====....",
             "....+++++....", ".....+++....."],
    "normal": [".............", ".............", ".............", ".....###.....", "...#######...", "...#######...",
               "..#########..", "..#########..", "..#########..", "...#######...", "....#####....", "....=====....",
               "....+++++....", ".....+++....."],
    "saver": [".............", ".............", ".............", ".....###.....", "...##***##...", "...#*****#...",
              "..#*******#..", "..#*******#..", "..#*******#..", "...#*****#...", "....#***#....", "....=====....",
              "....+++++....", ".....+++....."],
    "minimal": [".............", ".............", ".//..........", "..//..##.....", "...//...##...", "....//...#...",
                "..#..//...#..", "..#...//..#..", "..#....//....", "...#....//...", "....#....//..", "....====..//.",
                "....+++++....", ".....+++....."],
}
COL = {
    "full": {"#": (255, 255, 255), "+": (180, 180, 180), "=": (100, 100, 100)},
    "normal": {"#": (255, 255, 255), "+": (180, 180, 180), "=": (100, 100, 100)},
    "saver": {"#": (255, 255, 255), "*": (128, 128, 128), "+": (180, 180, 180), "=": (100, 100, 100)},
    "minimal": {"#": (142, 162, 198), "+": (107, 121, 148), "=": (76, 86, 106), "/": (220, 220, 220)},
}
ROW_Y0, ROW_H = 15, 14
MODES = [(1, "full"), (2, "normal"), (3, "saver"), (4, "minimal")]   # (row, mode): Back is row 0


def ink_right(im):
    """The rightmost lit column of the rows' text: where right-aligned values end."""
    w, h = im.size
    best = 0
    for y in range(ROW_Y0, h):
        for x in range(w):
            if sum(im.getpixel((x, y))) > 60:
                best = max(best, x)
    return best


def compose(name, right):
    im = Image.open(f"{D}/{name}.ppm").convert("RGB")
    for row, mode in MODES:
        y0 = ROW_Y0 + row * ROW_H
        for dy, line in enumerate(ART[mode]):
            for dx, ch in enumerate(line):
                if ch != ".":
                    im.putpixel((right - 12 + dx, y0 + dy), COL[mode][ch])
    return im


top = Image.open(f"{D}/power-balanced.ppm").convert("RGB")
# The title's right-aligned text ends where the rows' cells do: column 19's last pixel.
right = 123
print("the rows' rightmost ink without the bulbs:", ink_right(top), "; the bulbs end at x", right)
S = 4
panes = [compose("power-balanced", right), compose("power-lightsout", right)]
out = Image.new("RGB", (len(panes) * (128 * S + 24) + 24, 128 * S + 48), (40, 40, 40))
dr = ImageDraw.Draw(out)
for i, p in enumerate(panes):
    x = 24 + i * (128 * S + 24)
    out.paste(p.resize((128 * S, 128 * S), Image.NEAREST), (x, 24))
    dr.rectangle([x - 1, 23, x + 128 * S, 24 + 128 * S], outline=(90, 90, 90))
out.save(f"{D}/power-bulbs-mock.png")
for i, p in enumerate(panes):
    p.save(f"{D}/power-bulbs-1x-{i}.png")
print("wrote", f"{D}/power-bulbs-mock.png")
