#!/usr/bin/env python3
"""The precision path's curve (plans/ROW-ISR-PLAN.md, "D9 revised"): the
value byte to the light it means, at 16 bits, in Q6 byte units (full scale
255 x 64 = 16,320, the byte-path LUT's unit, so the cadence's scale and the
devprobe flavour's apply to both paths alike). The default is the CIE L*
lightness (Y = L/903.3 under L = 8, ((L + 16)/116)^3 above, L = v/255 x 100),
QMK's own table's shape kept at full precision; --gamma G writes a power
curve instead, for the exponent-by-eye evening. Monotonic, 0 at 0, exact at
255. --log writes a geometric curve instead: a constant ratio a value unit
from half a tick at 1 (7 Q6 units at the reference scale) to the top, about
3.1% a unit, 8% a percent step, which JD's eye on 11-04 asked for (L* steps
of 4% near half scale were invisible and its 13-50% steps under 10% were
jumps). Writes rgb/curve12.h in the firmware tree given, or prints the table.

--hybrid KNEE writes the bottom on the quarter-tick grid (at the reference
scale: 0.5, 0.75, 1 ... KNEE ticks, two values each, so every second detent
is a visible step and none is wasted under a tick, where the four-field
pattern has nothing finer) and a geometric curve from KNEE to the top (JD's
eye on the geometric curve, 11-04: "nothing, nothing, jump" under 5%).

--stops KNEE lays that grid on the slider instead of on the value: the menu
steps in percent (2.55 values a detent), and two values a level both skips
levels and leaves flat detents above the knee, where the geometric step is
finer than a quarter tick. So each percent stop gets its own level (1% half a
tick, then a quarter tick a percent to KNEE ticks; the values between two stops
hold the lower) and the geometric part starts at the knee's stop. With KNEE 4
the ratio falls smoothly into the geometric's 6.9% a percent, and that is
coarser than a quarter tick above 3.6 ticks and about a whole tick above 16.
One full-channel repeat remains: 36% and 37% both round to 17 ticks. A colour
with a weaker channel still moves there.

    scripts/gen_curve12.py [--gamma G | --log | --hybrid KNEE | --stops KNEE] [--out PATH]
"""
import argparse, sys

def cie(x):
    L = x * 100.0
    return L / 903.3 if L <= 8.0 else ((L + 16.0) / 116.0) ** 3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamma", type=float, default=None, help="a power curve's exponent instead of CIE L*")
    ap.add_argument("--log", action="store_true", help="a geometric curve: a constant ratio a value unit from 7 Q6 units (half a tick at the reference scale) at 1 to the top")
    ap.add_argument("--hybrid", type=float, default=None, metavar="KNEE", help="the quarter-tick grid from half a tick to KNEE ticks (two values a level), then geometric to the top")
    ap.add_argument("--stops", type=float, default=None, metavar="KNEE", help="each percent stop its own quarter-tick level from half a tick to KNEE ticks, then geometric to the top")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.gamma is not None and a.gamma <= 0: sys.exit("--gamma must be positive (0 would be a flat table; omit it for CIE L*)")
    if a.stops:
        if a.stops < 0.75 or a.stops > 16: sys.exit("--stops KNEE: 0.75 to 16 ticks")
        q6_per_tick = 4096.0 / 300.0   # the reference scale's unit
        val_of_pct = lambda p: (p * 255 + 50) // 100   # menu.c's
        n = int(round((a.stops - 0.5) / 0.25)) + 1      # the percent stops on the grid
        v_knee = val_of_pct(n); knee_q6 = a.stops * q6_per_tick
        t = [0] * 256
        for p in range(1, n + 1):
            lo = 1 if p == 1 else val_of_pct(p)
            hi = v_knee if p == n else val_of_pct(p + 1) - 1
            for v in range(lo, hi + 1): t[v] = round((0.5 + 0.25 * (p - 1)) * q6_per_tick)
        for v in range(v_knee + 1, 256):
            t[v] = round(knee_q6 * (16320.0 / knee_q6) ** ((v - v_knee) / (255.0 - v_knee)))
    elif a.hybrid:
        if a.hybrid < 0.75 or a.hybrid > 16: sys.exit("--hybrid KNEE: 0.75 to 16 ticks")
        q6_per_tick = 4096.0 / 300.0   # the reference scale's unit (ROWISR_K_REF_Q6 300 at 125 us)
        levels = [0.5 + 0.25 * i for i in range(int(round((a.hybrid - 0.5) / 0.25)) + 1)]   # 0.5 .. KNEE by quarters
        bottom = [round(l * q6_per_tick) for l in levels for _ in (0, 1)]   # two values a level
        n_b = len(bottom); knee_q6 = a.hybrid * q6_per_tick
        rest = [round(knee_q6 * (16320.0 / knee_q6) ** ((v - n_b) / (255.0 - n_b))) for v in range(n_b + 1, 256)]
        t = [0] + bottom + rest
    elif a.log:
        t = [0] + [round(7.0 * (16320.0 / 7.0) ** ((v - 1) / 254.0)) for v in range(1, 256)]
    else:
        f = (lambda x: x ** a.gamma) if a.gamma else cie
        t = [round(f(v / 255.0) * 16320) for v in range(256)]
    assert t[0] == 0 and t[255] == 16320 and all(t[i] <= t[i + 1] for i in range(255)), "monotonic, 0 at 0, exact at 255"
    name = (f"a quarter tick a percent stop to {a.stops:g} ticks, then geometric" if a.stops else f"the quarter-tick grid to {a.hybrid:g} ticks, then geometric" if a.hybrid else "a geometric curve (a constant ratio a unit)" if a.log else (f"a power curve, exponent {a.gamma}" if a.gamma else "the CIE L* lightness"))
    lines = [f"/* Generated by scripts/gen_curve12.py ({'--stops %g' % a.stops if a.stops else '--hybrid %g' % a.hybrid if a.hybrid else '--log' if a.log else ('--gamma %g' % a.gamma if a.gamma else 'CIE L*')}): do not edit.",
             f" * The precision path's curve (D9 revised): value 0..255 to {name} at",
             " * 16 bits in Q6 byte units (255 x 64 = 16,320 at full scale). The flush",
             " * scales it by the cadence's ROWISR_K_Q6 into ticks (rowisr.c). */",
             "static const uint16_t curve_q6[256] = {"]
    for i in range(0, 256, 8):
        lines.append("    " + ", ".join(f"{x:5d}" for x in t[i:i + 8]) + ",")
    lines.append("};")
    text = "\n".join(lines) + "\n"
    if a.out:
        open(a.out, "w").write(text); print(f"wrote {a.out}: v=1 {t[1]}, v=2 {t[2]}, v=13 {t[13]}, v=26 {t[26]}, v=128 {t[128]}")
    else:
        sys.stdout.write(text)

if __name__ == "__main__":
    main()
