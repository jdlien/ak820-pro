#!/usr/bin/env python3
"""Fit this pack's runtime curve from the 2026-09-28 drain test.

The level the gauge shows is the fraction of RUNTIME left at full white
(docs/battery.md, "What the level means"), with 0% at the RGB cut (3400 mV;
JD, 2026-10-01). A timed run gives it directly -- level = 1 - t/T -- once the
time axis counts only full-white consumption. This script builds that axis
from the run's three log dumps and prints a curve for battery.c.

The axis is "equivalent full-white hours" (t_eff). Per 10-minute log entry:

    t_eff += dt * ( (1 - f_usb) * p(led_pm)  -  r * f_usb * charging )

  f_usb     fraction of the entry on USB, from the entry's MEAN VDD: on the
            pack VDD sits at the buck-boost's ~3.90 V, on USB at V_USB_*;
            the mean interpolates between them. (The log has no duration.)
  p(led)    power relative to full white: BASE + (1 - BASE) * led_pm/1000.
            BASE is the lights-off share, from the tail after the cut.
  r         charge current over full-white draw: a minute of charging puts
            back r minutes of full-white runtime. r = F_CC * T / T_CC, from
            the 09-28 charge from flat (constant current ~T_CC hours
            delivering ~F_CC of the charge); the pack capacity cancels.

What the logs do not cover (the two gaps between dumps) is in GAPS, from
history/battery-2026-09-28-drain/readings.csv. Every number here is an
estimate with a source; run with --sensitivity to see what each costs.

Usage:  python3 scripts/battery_fit.py [--sensitivity] [--points out.csv]
"""
import csv, os, sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "..", "history", "battery-2026-09-28-drain")
LOGS = ["log-20260929-1356.csv",    # v3: 09-28 15:47 boot -> 09-29 13:48
        "log-20260930-1956.csv",    # v4: 09-29 13:58 flash -> 09-30 19:48
        "log-20261001-0503.csv"]    # v4: 09-30 20:44 reboot -> 10-01 04:54
PERIOD_H = 10 / 60

# 5C -> pack mV: the fitted line (docs/battery.md).
SLOPE, OFFSET = 114.22, 361.04
def c5_to_mv(c5): return (c5 + OFFSET) * 1000.0 / SLOPE

# VDD levels for f_usb. On the pack: each entry's own neighbours set the
# baseline (it droops from 3901 to ~3872 mV through the night under full
# white). On USB in the BT position: ~4193 mV while charging in constant
# current (09-28 charge log, flat 03:00-07:00), ~4408 mV idle with the
# charger terminated (09-28 18:48-19:48).
V_USB_CHARGING = 4190.0
V_USB_IDLE = 4408.0

BASE = 0.33     # lights-off power / full-white power: the fall rate after the cut
                # (3406 -> 3374 mV, 02:34-03:14, ~8 mV/10 min) over the full-white
                # rate extrapolated to the same voltage (~22 mV/10 min) -- rough,
                # and an upper bound, since the full-white curve steepens there
F_CC = 0.80     # share of a full charge delivered in constant current (typical
                # for a TP4056-class charger; unmeasured here)
T_CC = 3.92     # h of constant current from flat, 09-28: CHRG low 03:02, 5C 100
                # at 06:57 (history/battery-2026-09-25/readings.csv)

# The cut, from the 02:04-02:14 entry's led_pm 924: full drive for 92.4% of it.
CUT = datetime(2026, 10, 1, 2, 4) + timedelta(minutes=10 * 0.924)

# Gaps between dumps, from readings.csv. Each: (start, end, [(minutes, kind)])
# with kind "white" (on the pack at full white), "usb_charging", or "off"
# (dark: no draw at all). Minutes not listed are full white.
GAPS = [
    # 13:48-13:58 on 09-29: on the pack until the dump at ~13:55, then USB
    # (charging) through the dump and flash.sh until the new boot at ~13:58.
    # The 14:08 entry's VDD covers the USB time after the boot.
    (datetime(2026, 9, 29, 13, 48), datetime(2026, 9, 29, 13, 58),
     [(3.0, "usb_charging")]),
    # 19:48-20:44 on 09-30: the 19:57 dump (~40 s on USB, by the pattern of the
    # logged ones: 6-72 s), then the probe short at ~20:43 -- dark until JD's
    # slider flip booted it at ~20:44 (the next log's first entry).
    (datetime(2026, 9, 30, 19, 48), datetime(2026, 9, 30, 20, 44),
     [(40 / 60, "usb_charging"), (0.5, "off")]),
]


def load():
    rows = []
    for name in LOGS:
        with open(os.path.join(RUN, name)) as f:
            for r in csv.DictReader(f):
                end = datetime.strptime(r["time"], "%Y-%m-%d %H:%M")
                rows.append({
                    "end": end, "start": end - timedelta(minutes=10),
                    "vdd": float(r["vdd_avg"]), "c5": float(r["c5_mean"]) if r["c5_mean"] else None,
                    "led": float(r["led_pm"]), "flags": r["flags_any"].split(),
                })
    rows.sort(key=lambda x: x["end"])
    return rows


def f_usb(row, baseline):
    """Fraction of the entry on USB, from its mean VDD."""
    if "external" not in row["flags"]:
        return 0.0
    v_usb = V_USB_CHARGING if "charging" in row["flags"] else V_USB_IDLE
    f = (row["vdd"] - baseline) / (v_usb - baseline)
    return min(max(f, 0.0), 1.0)


def build(rows, base=BASE, r=None, run_h=52.0):
    """t_eff at each entry's midpoint, and at the cut. r defaults from run_h."""
    if r is None:
        r = F_CC * run_h / T_CC
    p = lambda led: base + (1 - base) * led / 1000.0
    # Start: the first entry that ran on the pack after the 09-28 USB interlude.
    i0 = next(i for i, x in enumerate(rows)
              if x["end"] > datetime(2026, 9, 28, 19, 0) and "on_batt" in x["flags"])
    t, out = 0.0, []
    prev_end = rows[i0]["start"]
    for i in range(i0, len(rows)):
        x = rows[i]
        # A gap before this entry?
        for (gs, ge, events) in GAPS:
            if prev_end <= gs and x["start"] >= ge - timedelta(minutes=1):
                total = (ge - gs).total_seconds() / 60
                special = sum(m for m, _ in events)
                t += (total - special) / 60 * p(1000)           # full white
                for m, kind in events:
                    if kind == "usb_charging":
                        t -= r * m / 60                         # charge put back
                    # "off": no draw, no charge
        # Baseline VDD: the nearest clean neighbours' mean.
        nb = [rows[j]["vdd"] for j in (i - 1, i + 1)
              if 0 <= j < len(rows) and "external" not in rows[j]["flags"]]
        baseline = sum(nb) / len(nb) if nb else 3900.0
        fu = f_usb(x, baseline)
        charging = "charging" in x["flags"]
        if x["end"] > CUT:
            # The cut's entry: count full white up to the cut, then stop.
            frac = (CUT - x["start"]).total_seconds() / 600
            t_cut = t + frac * PERIOD_H * p(1000)
            out.append(dict(x, t_mid=t + 0.5 * frac * PERIOD_H, fu=0.0, clean=False))
            return out, t_cut, r
        dt_cons = PERIOD_H * ((1 - fu) * p(x["led"]))
        dt_chg = PERIOD_H * fu * (r if charging else 0.0)
        t_mid = t + 0.5 * (dt_cons - dt_chg)
        t += dt_cons - dt_chg
        clean = (fu == 0.0 and x["c5"] is not None and x["c5"] < 99.5)
        out.append(dict(x, t_mid=t_mid, fu=fu, clean=clean))
        prev_end = x["end"]
    raise SystemExit("the cut was not found in the logs")


def pava_decreasing(ys):
    """Isotonic regression: the closest non-increasing sequence (least squares)."""
    blocks = []  # [sum, count]
    for y in ys:
        blocks.append([y, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] < blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s; blocks[-1][1] += c
    out = []
    for s, c in blocks:
        out += [s / c] * c
    return out


def smoothed_path(points, t_cut):
    """mV against t_eff: each unbroken stretch smoothed on its own (a running
    median of 3, then a mean of 5), then made monotone across the whole run.
    Stretches break at the gaps (a lost log, a flash) and at every USB entry,
    so no average reaches across a perturbation."""
    pts = [(p["t_mid"], c5_to_mv(p["c5"]), p["end"]) for p in points if p["clean"]]
    segs, cur = [], [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if (b[2] - a[2]) > timedelta(minutes=15):
            segs.append(cur); cur = []
        cur.append(b)
    segs.append(cur)
    ts, sm = [], []
    for seg in segs:
        v = [x[1] for x in seg]
        med = [sorted(v[max(0, i - 1): i + 2])[len(v[max(0, i - 1): i + 2]) // 2] for i in range(len(v))]
        for i in range(len(med)):
            w = med[max(0, i - 2): i + 3]
            sm.append(sum(w) / len(w))
        ts += [x[0] for x in seg]
    # The cut defines the bottom: the estimate crossed 3400 mV there.
    ts.append(t_cut); sm.append(3400.0)
    return ts, pava_decreasing(sm), pts


def mv_at(ts, sm, t):
    if t <= ts[0]:
        return sm[0]
    for i in range(1, len(ts)):
        if t <= ts[i]:
            return sm[i - 1] + (sm[i] - sm[i - 1]) * (t - ts[i - 1]) / (ts[i] - ts[i - 1])
    return sm[-1]


def level_at(curve_mv, curve_pm, mv):
    """battery.c's curve(): linear between knots, 0 below, the top above."""
    if mv <= curve_mv[0]:
        return 0
    if mv >= curve_mv[-1]:
        return curve_pm[-1]
    for i in range(1, len(curve_mv)):
        if mv < curve_mv[i]:
            return curve_pm[i - 1] + (mv - curve_mv[i - 1]) * (curve_pm[i] - curve_pm[i - 1]) / (curve_mv[i] - curve_mv[i - 1])


def curve_from(points, t_cut, levels_pm, top_pm=900):
    """Knots at even steps of LEVEL: for each, the smoothed voltage at that
    fraction of the run. The top knot is the clamp's bound (4036 mV) at
    top_pm, the firmware's LEVEL_CLAMP_EXIT."""
    ts, sm, pts = smoothed_path(points, t_cut)
    mv, pm = [], []
    for l in levels_pm:
        v = round(mv_at(ts, sm, (1 - l / 1000) * t_cut))
        if mv and v <= mv[-1]:
            continue              # a flat stretch: keep knots strictly rising
        mv.append(v); pm.append(l)
    mv.append(4036); pm.append(top_pm)
    return mv, pm, pts


# Knot levels, per mille: dense at the bottom, where the voltage falls fastest
# and the warning and cut live; every 5% above.
LEVELS = [0, 10, 20, 30, 40, 50, 60, 80, 100, 125, 150, 200, 250, 300, 350, 400,
          450, 500, 550, 600, 650, 700, 750, 800, 850]


def main():
    rows = load()
    pts, t_cut, r = build(rows)
    # Iterate r once: it scales with the run's own full-white length.
    pts, t_cut, r = build(rows, run_h=t_cut)
    clean = [p for p in pts if p["clean"]]
    first_below = next(p for p in pts if p["c5"] is not None and p["c5"] < 99.5 and p["fu"] == 0)
    print(f"start          {pts[0]['start']:%m-%d %H:%M} (first entry on the pack)")
    print(f"cut            {CUT:%m-%d %H:%M:%S}  wall {((CUT - pts[0]['start']).total_seconds() / 3600):.2f} h")
    print(f"T (full white) {t_cut:.2f} h   r = {r:.1f}   BASE = {BASE}")
    print(f"clamp exit     {first_below['end']:%m-%d %H:%M} entry, level {100 * (1 - first_below['t_mid'] / t_cut):.1f}%")
    usb = [(p['end'], p['fu'] * 600) for p in pts if p['fu'] > 0]
    print("USB per entry  " + ", ".join(f"{e:%m-%d %H:%M} {s:.0f}s" for e, s in usb))
    cmv, cpm, cpts = curve_from(pts, t_cut, LEVELS)
    print(f"\n{len(clean)} clean entries.  curve (mV -> % of full-white runtime left):")
    for v, l in zip(cmv, cpm):
        print(f"  {v}  {l / 10:5.1f}")
    print("\nstatic const uint16_t curve_mv[] = {" + ", ".join(map(str, cmv)) + "};")
    print("static const uint16_t curve_pm[] = {" + ", ".join(map(str, cpm)) + "};")
    # In-sample check: the curve at each entry's measured mV against the truth.
    errs = [(level_at(cmv, cpm, v) - 1000 * (1 - t / t_cut)) / 10 for t, v, _ in cpts]
    rms = (sum(e * e for e in errs) / len(errs)) ** 0.5
    print(f"\nin-sample: the curve at each clean entry's mV vs its true level: "
          f"rms {rms:.1f} points, worst {min(errs):+.1f} / {max(errs):+.1f}")
    bands = [(3400, 3600), (3600, 3800), (3800, 3950), (3950, 4036)]
    for lo, hi in bands:
        e = [err for err, (t, v, _) in zip(errs, cpts) if lo <= v < hi]
        if e:
            print(f"  {lo}-{hi} mV: n {len(e):3d}  rms {(sum(x * x for x in e) / len(e)) ** 0.5:4.1f}  worst {max(e, key=abs):+5.1f}")

    if "--points" in sys.argv:
        out = sys.argv[sys.argv.index("--points") + 1]
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["entry_end", "t_eff_mid_h", "level_pct", "pack_mv", "f_usb", "led_pm", "clean"])
            for p in pts:
                w.writerow([f"{p['end']:%Y-%m-%d %H:%M}", f"{p['t_mid']:.3f}",
                            f"{100 * (1 - p['t_mid'] / t_cut):.2f}",
                            f"{c5_to_mv(p['c5']):.1f}" if p["c5"] is not None else "",
                            f"{p['fu']:.3f}", f"{p['led']:.0f}", int(p["clean"])])
        print(f"\npoints -> {out}")

    if "--sensitivity" in sys.argv:
        probe = [3700, 3550, 3500]
        print("\nsensitivity (the curve's level at " + " / ".join(map(str, probe)) + " mV, and T):")
        for label, kw in [("as fitted", {}), ("BASE 0.25", {"base": 0.25}), ("BASE 0.45", {"base": 0.45}),
                          ("r -20%", {"r": r * 0.8}), ("r +20%", {"r": r * 1.2}), ("no charge credit", {"r": 0.0})]:
            p2, t2, _ = build(rows, **kw) if "r" in kw else build(rows, run_h=t_cut, **kw)
            m2, l2, _ = curve_from(p2, t2, LEVELS)
            print(f"  {label:16s} " + "  ".join(f"{level_at(m2, l2, v) / 10:5.1f}" for v in probe) + f"   T {t2:.2f} h")


if __name__ == "__main__":
    main()
