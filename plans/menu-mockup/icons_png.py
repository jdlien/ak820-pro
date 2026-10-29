#!/usr/bin/env python3
# The 8 x 16 icons as a PNG to edit by hand, and back.
#
#   python3 icons_png.py export menu-icons-8x16.png       the template, from the icons as they are
#   python3 icons_png.py import menu-icons-8x16.png [-n]  read it back: icons16.js, the faces, the mockup
#
# One icon a row, each in its cell (16 x 16 for a pair, 8 x 16 for a single) at its place in the
# menu's row, the label after it in Terminus Bold as the menu sets it. Inside a cell, a light pixel
# (luminance and alpha 128 or more) is ink; anything else is not, so the tinted cell, the cap-height
# band and any antialiasing don't matter. Only the cells are read. The PNG may be scaled up by a
# whole number. -n shows what would change and writes nothing.
import os, re, shutil, subprocess, sys, time
from PIL import Image

D = os.path.dirname(os.path.abspath(__file__))
MOCKUP = os.path.join(D, "..", "config-menu-mockup.html")
FACES = [("termb", "terminus/ter-u16b.bdf")]
PAIRS = {0x88, 0x8a, 0x8d, 0x90, 0x92, 0x96, 0x98, 0x9a, 0x9c, 0x9e, 0xa0, 0xa4, 0xa6, 0xa9, 0xac}
ICONS = [(0x95, "Lighting"), (0x96, "Screen"), (0x9c, "Connection"), (0x8c, "Power"), (0x9a, "Indicators"),
         (0x8d, "Clock"), (0xa2, "Battery"), (0xa3, "Profiles"), (0x98, "Bootloader"), (0xab, "Defaults"),
         (0x8f, "Diagnostics"), (0x90, "Help"), (0x92, "About"), (0x94, "Exit"), (0xa4, "Load"), (0xa6, "Save"),
         (0xa8, "Rename"), (0xa9, "Delete"), (0x8a, "Saved (green)"), (0x9e, "Trying (grey)"), (0xa0, "Failed (red)"),
         (0x88, "Menu title"), (0x85, "Back"), (0x86, "Opens a page"), (0xac, "Font")]
X0, Y0, PITCH, CAP = 4, 4, 20, (2, 11)            # the cell's left edge, the first row, a row's pitch, Terminus's capitals
W, H = 128, Y0 + len(ICONS) * PITCH
BG, CELL, BAND, INK, LABEL = (0, 0, 0), (44, 44, 44), (40, 44, 72), (255, 255, 255), (140, 140, 140)

def face(name="termb"):
    h = open(os.path.join(D, "f-%s.hex" % name)).read().strip()
    return lambda i: [int(h[(i * 16 + r) * 2:(i * 16 + r) * 2 + 2], 16) for r in range(16)]

def cell_of(glyph, code):
    """The icon's cell as rows of '.'/'#', from the face as built (a pair's two codes side by side)."""
    w = 16 if code in PAIRS else 8
    rows = [glyph(95 + code - 0x80)] + ([glyph(95 + code + 1 - 0x80)] if w == 16 else [])
    return ["".join("#" if rows[x // 8][r] & (0x80 >> (x % 8)) else "." for x in range(w)) for r in range(16)]

def template():
    g, img = face(), Image.new("RGB", (W, H), BG)
    px = img.load()
    for k, (code, label) in enumerate(ICONS):
        y0, cell = Y0 + k * PITCH, cell_of(face(), code)
        for r, line in enumerate(cell):
            for x, ch in enumerate(line):
                px[X0 + x, y0 + r] = INK if ch == "#" else BAND if CAP[0] <= r <= CAP[1] else CELL
        for i, c in enumerate(label):
            rows = g(ord(c) - 0x20)
            for r in range(16):
                for x in range(8):
                    if rows[r] & (0x80 >> x): px[X0 + 16 + i * 8 + x, y0 + r] = LABEL
    return img

def read(path):
    img = Image.open(path).convert("RGBA")
    s = img.width // W
    if s < 1 or img.size != (W * s, H * s):
        sys.exit("%s is %d x %d; the template is %d x %d (or a whole multiple of it)" % (path, img.width, img.height, W, H))
    px = img.load()
    def ink(x, y):
        r, g, b, a = px[x * s + s // 2, y * s + s // 2]
        return a >= 128 and 0.299 * r + 0.587 * g + 0.114 * b >= 128
    cells, stray = {}, []
    ref = template().load()
    for k, (code, label) in enumerate(ICONS):
        y0, w = Y0 + k * PITCH, 16 if code in PAIRS else 8
        cells[code] = ["".join("#" if ink(X0 + x, y0 + r) else "." for x in range(w)) for r in range(16)]
        # drawing beside a single's cell, or in the gaps, is not read: say so
        out = sum(1 for y in range(y0 - 2, y0 + 18) for x in range(0, X0 + 16)
                  if 0 <= y < H and not (X0 <= x < X0 + w and y0 <= y < y0 + 16)
                  and ink(x, y) != (sum(ref[x, y]) >= 384))
        if out: stray.append("%s: %d pixel%s outside its %d-px cell, not read" % (label, out, "" if out == 1 else "s", w))
    return cells, stray

def entry(code, cell, comment):
    rows = [r for r in range(16) if "#" in cell[r]]
    top, bot = rows[0], rows[-1]
    w = max(line.rindex("#") for line in cell if "#" in line) + 1
    art = ['"%s"' % cell[r][:w] for r in range(top, bot + 1)]
    lines = ["    " + ", ".join(art[i:i + 7]) for i in range(0, len(art), 7)]
    return "  0x%02x: { top: %d, art: [   // %s\n%s] }," % (code, top, comment, ",\n".join(lines))

def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("export", "import"): sys.exit(__doc__ or open(__file__).read().split("\nimport")[0])
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "export":
        template().save(path)
        print("wrote", path, "%d x %d, %d icons" % (W, H, len(ICONS)))
        return
    new, stray = read(path)
    old = {code: cell_of(face(), code) for code, _ in ICONS}
    labels = dict(ICONS)
    changed = [c for c, _ in ICONS if new[c] != old[c]]
    for note in stray: print("note:", note)
    empty = [labels[c] for c in changed if not any("#" in l for l in new[c])]
    if empty: sys.exit("empty: " + ", ".join(empty) + "; nothing written")
    if not changed: print("no icon changed"); return
    for c in changed:
        print("\n%s (0x%02x)%s" % (labels[c], c, "" if c in PAIRS else ", a single"))
        for a, b in zip(old[c], new[c]): print("  %s   %s" % (a, b))
    if "-n" in sys.argv[3:]: print("\n-n: nothing written"); return
    src = open(os.path.join(D, "icons16.js")).read()
    shutil.copy(os.path.join(D, "icons16.js"), os.path.join(D, "icons16.js.%s" % time.strftime("%H%M%S")))
    for c in changed:
        pat = re.compile(r"  0x%02x: \{ top: \d+, art: \[   // ([^\n]*)\n.*?\] \}," % c, re.S)
        m = pat.search(src)
        if not m: sys.exit("icons16.js has no entry for 0x%02x" % c)
        src = src[:m.start()] + entry(c, new[c], m.group(1)) + src[m.end():]
    open(os.path.join(D, "icons16.js"), "w").write(src)
    for name, bdf in FACES:
        subprocess.run(["node", "mkfont8.js", bdf, "f-%s.hex" % name], cwd=D, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["node", "build.js", MOCKUP], cwd=D, check=True)
    print("\n%d icon%s changed; the faces and the mockup rebuilt" % (len(changed), "" if len(changed) == 1 else "s"))

if __name__ == "__main__":
    main()
