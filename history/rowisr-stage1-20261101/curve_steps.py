#!/usr/bin/env python3
"""What each percent stop of the menu's brightness slider drives under a
curve table, by rowisr.c's wide_width(): the mean ticks a field for JD's
purple (hue 178 sat 219 renders chroma 77, 35, 255) and for full chroma, and
which detents change no channel at all. Arithmetic only: it says where the
widths stop moving, not what the eye sees.

    gen_curve12.py --stops 4 | curve_steps.py        (or --log, --hybrid 2)
"""
import re, sys
s = sys.stdin.read(); body = s[s.index("{") + 1:s.rindex("}")]
t = [int(x) for x in re.findall(r"\b\d+\b", body)]; assert len(t) == 256
K = 300
def wide(c, v):
    recip = (((t[v] * K) >> 4) * 256 + 127) // 255
    q8 = (c * recip + 128) >> 8; w, f = q8 >> 8, q8 & 0xFF
    if w >= 16: return float(w + (1 if f >= 128 else 0))
    q = (f + 32) >> 6
    return w + q / 4
prev = None; flat_all = []; flat_blue = []
print(" pct   v    R      G      B   ratio")
for p in range(0, 101):
    v = (p * 255 + 50) // 100
    w = tuple(wide(c, v) for c in (77, 35, 255))
    if prev is not None:
        if w == prev: flat_all.append(p)
        if w[2] == prev[2]: flat_blue.append(p)
    if p <= 26 or p % 10 == 0:
        r = f"{w[2] / prev[2]:5.2f}" if prev and prev[2] else "    -"
        print(f"{p:4d} {v:3d} {w[0]:6.2f} {w[1]:6.2f} {w[2]:7.2f} {r}{'  (no channel moved)' if prev is not None and w == prev else ''}")
    prev = w
print("detents where no channel moves:", flat_all or "none")
print("detents where blue does not move:", flat_blue or "none")
