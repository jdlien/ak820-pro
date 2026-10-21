#!/usr/bin/env python3
"""The RGB's power per colour, fitted from a `current_map.py --set rgb-curve`
summary: P = P_off + A + B_r S_r + B_g S_g + B_b S_b, where S_c is a
colour's channel sum in LED-buffer units (81 LEDs x 0-255, from the board's
own drive per mille, so QMK's CIE curve is already applied) and P_off the
map's "rgb off" steps. Prints the fit, each step against it and against the
summary's recorded model (Phase 2's one B, 2.857 uW, the board's at the
time), and the stage map's purple as an out-of-sample check.

    venv/bin/python scripts/rgb_fit.py [summary.txt]
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = os.path.join(HERE, "..", "history", "power-bench-2026-10-15", "rgb-curve-20261019", "summary.txt")
# One channel full on every LED. 81, the rgb_matrix layout in keyboard.json:
# the drive per mille divides by LED_LOAD_MAX = RGB_MATRIX_LED_COUNT * 3 * 255
# (battery.c). Until 10-21 this said 82, so the slopes it fitted (battery.c's
# P_RGB_*_NW) came out 81/82 of these (plans/BACKLOG.md). N scales every
# column alike, so this is the same fit rescaled exactly; the per mille is a
# rounded integer, though, so the drive itself is only approximate (red at
# value 16 sums 162, `led 2` gives 123.9): a refit from the settings through
# QMK's CIE table is a separate refinement (codex, 10-21).
N = 81 * 255
B_ONE = 2.857e-3      # Phase 2's mW per unit, every channel alike (the summary's "model")
ROW = re.compile(r"^\s*\d+ (\S+(?: \d+| off)?)\s+[\d.]+ mA .*?,\s+([\d.]+) mW, led (\d+)(?:, model ([\d.]+) mW)?", re.M)


def solve(m, v):
    """Gaussian elimination with partial pivoting."""
    n = len(v)
    a = [row[:] + [v[i]] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def main():
    rows = ROW.findall(open(sys.argv[1] if len(sys.argv) > 1 else SUMMARY).read())
    offs = [float(mw) for name, mw, _, _ in rows if name == "rgb off"]
    off = sum(offs) / len(offs)
    xs, ys, steps = [], [], []
    for name, mw, pm, model in rows:
        if name == "rgb off":
            continue
        s = int(pm) / 1000 * 3 * N
        c = name.split()[0]
        x = {"red": (s, 0, 0), "green": (0, s, 0), "blue": (0, 0, s)}.get(c, (s / 3,) * 3)   # white, jd
        xs.append((1.0,) + x)
        ys.append(float(mw) - off)
        steps.append((name, float(mw), float(model) if model else None))
    ata = [[sum(r[i] * r[j] for r in xs) for j in range(4)] for i in range(4)]
    aty = [sum(r[i] * y for r, y in zip(xs, ys)) for i in range(4)]
    a, br, bg, bb = solve(ata, aty)
    mean = (br + bg + bb) / 3
    print(f"rgb off {off:.1f} mW; A {a:.2f} mW; B red {br * 1e3:.3f}, green {bg * 1e3:.3f}, blue {bb * 1e3:.3f} uW/unit "
          f"(Phase 2's one B, {B_ONE * 1e3:.3f}); weights to their mean: {br / mean:.3f} {bg / mean:.3f} {bb / mean:.3f}")
    by = {}
    for (name, mw, model), x in zip(steps, xs):
        fit = off + a + br * x[1] + bg * x[2] + bb * x[3]
        by.setdefault(name, []).append((mw, fit, model))
    print(f"{'step':10s} {'measured':>8s} {'fit':>7s} {'error':>6s} {'one-B':>6s}")
    worst = 0.0
    for name, v in by.items():
        mw = sum(t[0] for t in v) / len(v)
        fit = sum(t[1] for t in v) / len(v)
        worst = max(worst, abs(fit / mw - 1))
        one_b = f"{100 * (v[0][2] / mw - 1):+5.1f}%" if v[0][2] else "-"
        print(f"{name:10s} {mw:8.1f} {fit:7.1f} {100 * (fit / mw - 1):+5.1f}% {one_b:>6s}")
    print(f"worst fit error {100 * worst:.1f}%")
    # Out of sample: the stage map's purple (hue 191, blue full, red the rest of
    # its drive 498), 211.9 mW measured, Phase 2's one-B model 215.7. Its rgb-off is this map's.
    s = 0.498 * 3 * N
    p = off + a + br * (s - N) + bb * N
    print(f"purple, the stage map: fit {p:.1f} mW against 211.9 measured ({100 * (p / 211.9 - 1):+.1f}%; one-B +1.8%)")


if __name__ == "__main__":
    main()
