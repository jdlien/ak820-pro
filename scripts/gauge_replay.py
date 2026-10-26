#!/usr/bin/env python3
"""A7 (plans/POWER-CAMPAIGN-PLAN.md): the energy-count gauge proposed for
Phase 2 (plans/PHASE2-BUILD-PLAN.md), replayed on recorded drains against
the measured truth, beside the board's own level.

The proposal, per 10-minute RAM-log entry:
  count   falls by the modelled energy of the entry: P_model(led_pm, duty) x
          600 s, over the energy per per-mille of the pack (E_CAP / 1000).
  band    the voltage's say: curve(V) +/- U, U = half the curve's change over
          V +/- SIGMA_MV, plus U_MIN. Above the band, the count is pulled
          down to its top (the ratchet); below it, the count waits (it never
          rises on battery). At the top clamp (5C 100) the only bound is
          "at least 90%".
The board would run this each second; ten-minute steps are a coarser check
of the same rule (they cannot show the ratchet's 1%-per-15-s easing).

Drains:
  R3  10-15/18, flash 2f: truth = energy left from the pack logger
      (scripts/r3_level.py).
  2e  10-12/14, flash 2e: truth = time left (1 - t/T), which R3 showed is
      the energy truth within 0.1 point at this load. It rebooted at ~10:04
      10-14: the replay carries the count across (the board itself would
      have restarted from the voltage then).

    python3 scripts/gauge_replay.py [--sigma 12] [--umin 15] [--ecap 15579]
"""
import argparse, csv, os, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# battery.c's fitted curve and 5C line.
CURVE_MV = [3400, 3456, 3490, 3520, 3538, 3564, 3591, 3640, 3680, 3723, 3748, 3785, 3814, 3831,
            3846, 3856, 3868, 3896, 3945, 3981, 3996, 4003, 4007, 4010, 4016, 4036]
CURVE_PM = [0, 10, 20, 30, 40, 50, 60, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500,
            550, 600, 650, 700, 750, 800, 850, 900]
BKL_DUTY = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 23, 26, 29, 33, 37, 42, 48]
# Log v8 (the menu's P2b) records the LCD level 0-100 as "bkl100": its duty in
# whole ticks of 48, rounded as display_backlight_duty() rounds it.
LEVEL_TICKS = [(d + 128) >> 8 for d in __import__("gen_indicator_levels").table()]

# The load model, pack power in mW, from R1 (history/power-bench-2026-10-15/
# current-map-20261015-2210): mA x vcell, USB data attached as in R1 and the
# drains replayed here.
P_BASE = 114.0                    # every light out (27.33 mA at 4.172 V)
P_BKL_FULL = 39.1                 # backlight at duty 48/48 (9.37 mA), linear in duty
P_RGB = [(0, 0.0), (251, 17.9), (502, 43.0), (1000, 188.7)]   # white 64/128/255, by led_pm


def curve(mv):
    if mv <= CURVE_MV[0]: return 0.0
    if mv >= CURVE_MV[-1]: return float(CURVE_PM[-1])
    for i in range(1, len(CURVE_MV)):
        if mv < CURVE_MV[i]:
            return CURVE_PM[i - 1] + (mv - CURVE_MV[i - 1]) * (CURVE_PM[i] - CURVE_PM[i - 1]) / (CURVE_MV[i] - CURVE_MV[i - 1])
    return float(CURVE_PM[-1])


def c5_to_mv(c5):
    return (c5 + 361.04) * 1000.0 / 114.22


def bkl_duty(r):
    """A log row's backlight duty in ticks of 48: v8's bkl100, or bkl 0-23 before it."""
    if r.get("bkl100"):
        return LEVEL_TICKS[min(int(r["bkl100"]), 100)]
    return BKL_DUTY[min(int(r["bkl"]), 23)]


def p_model(led_pm, duty, rgb_on):
    p = P_BASE + P_BKL_FULL * duty / 48
    if rgb_on:
        for (x0, y0), (x1, y1) in zip(P_RGB, P_RGB[1:]):
            if led_pm <= x1:
                p += y0 + (y1 - y0) * (led_pm - x0) / (x1 - x0)
                break
    return p


def load_log(paths, t_from, t_to):
    rows = []
    for p in paths:
        with open(p) as f:
            for r in csv.DictReader(f):
                t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M").timestamp()
                if t_from < t <= t_to and r["on_batt"] == "1" and r["c5_mean"]:
                    rows.append((t, float(r["c5_mean"]), int(r["led_pm"]), bkl_duty(r), r["rgb_on"] == "1",
                                 float(r["level"]) if r["level"] else None))
    rows.sort()
    out = []
    for r in rows:                       # two dumps overlap: keep one entry a time
        if not out or r[0] - out[-1][0] > 60:
            out.append(r)
    return out


def replay(rows, t0, ecap, sigma, umin):
    e_pm = ecap * 3600 / 1000            # mW.s per per mille
    count, prev_t, out = 1000.0, t0, []
    for t, c5, led, duty, rgb, board in rows:
        dt = t - prev_t
        prev_t = t
        p = p_model(led, duty, rgb)
        before = count
        count -= p * dt / e_pm
        if c5 >= 99.5:                    # the top clamp: at least 90%
            count = max(count, min(before, 900.0))
        else:
            v = c5_to_mv(c5)
            lv = curve(v)
            u = (curve(v + sigma) - curve(v - sigma)) / 2 + umin
            if count > lv + u:
                count = lv + u                       # the ratchet, down to the band
            elif count < lv - u:
                count = max(count, min(before, lv - u))   # wait for the voltage
        out.append((t, count / 10, board, p))
    return out


def report(name, out, truth):
    bands = {}
    errs, berrs = [], []
    for t, lvl, board, p in out:
        tr = truth(t)
        if tr is None or tr < 0: continue
        e = lvl - tr
        errs.append(e)
        if board is not None: berrs.append(board - tr)
        bands.setdefault(min(int(tr // 10) * 10, 90), []).append((e, None if board is None else board - tr))
    print(f"{name}: {len(errs)} entries")
    print(f"  {'truth':>7} {'n':>4} {'replayed - truth':>22} {'board - truth':>22}")
    for b in sorted(bands, reverse=True):
        es = [x[0] for x in bands[b]]
        bs = [x[1] for x in bands[b] if x[1] is not None]
        f = lambda xs: f"{sum(xs)/len(xs):+5.1f} [{min(xs):+5.1f},{max(xs):+5.1f}]" if xs else "-"
        print(f"  {b:3}-{b + 10:<3}% {len(es):4} {f(es):>22} {f(bs):>22}")
    within = lambda xs, k: 100 * sum(abs(x) <= k for x in xs) / len(xs)
    print(f"  overall replayed: mean {sum(errs)/len(errs):+.2f}, worst {min(errs):+.1f}/{max(errs):+.1f}, "
          f"within 3: {within(errs, 3):.0f}%, within 5: {within(errs, 5):.0f}%")
    print(f"  overall board:    mean {sum(berrs)/len(berrs):+.2f}, worst {min(berrs):+.1f}/{max(berrs):+.1f}, "
          f"within 3: {within(berrs, 3):.0f}%, within 5: {within(berrs, 5):.0f}%")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sigma", type=float, default=12)
    ap.add_argument("--umin", type=float, default=15)
    ap.add_argument("--ecap", type=float, default=15579)
    a = ap.parse_args()

    import r3_level as r3
    pw = r3.integrate(r3.load_power())
    E = pw[-1][2]
    t_cut = r3.epoch(r3.CUT_LAST_ON) + 0.5

    def truth_r3(t):
        if t > t_cut: return None
        return 100 * (1 - r3.at(pw, t)[2] / E)

    run = os.path.join(ROOT, "history", "battery-2026-10-15-drain-2f")
    rows = load_log([os.path.join(run, "log-20261018-0205-rgbcut.csv")], r3.T0, t_cut)
    out = replay(rows, r3.T0, a.ecap, a.sigma, a.umin)
    report("R3 (truth: logged energy)", out, truth_r3)

    run = os.path.join(ROOT, "history", "battery-2026-10-12-drain-2e")
    t0 = datetime(2026, 10, 12, 11, 34, 16).timestamp()
    T = 50.39 * 3600
    rows = load_log([os.path.join(run, "log-20261014-0950-preswap.csv"),
                     os.path.join(run, "log-20261014-1400-rgbcut.csv")], t0, t0 + T)
    out = replay(rows, t0, a.ecap, a.sigma, a.umin)
    report("2e (truth: time left)", out, lambda t: 100 * (1 - (t - t0) / T) if t <= t0 + T else None)


if __name__ == "__main__":
    main()
