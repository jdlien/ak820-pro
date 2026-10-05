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
        python3 scripts/battery_fit.py --refit [--write]

--refit is Phase 1b's A (plans/BATTERY-GAUGE-REFINE-PLAN.md, A1-A2): both
runs on one footing, leave-one-out in each direction, the pooled curve for
the firmware, and the sensitivities the plan asks for. --write also saves the
output and each run's per-point file into the run folders. The legacy path
(no --refit) is unchanged: run 1's fit-output.txt reproduces byte-identical.
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
                    # Only the refit (--refit) reads these.
                    "c5_min": int(r["c5_min"]) if r["c5_min"] else None,
                    "c5_max": int(r["c5_max"]) if r["c5_max"] else None,
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


# =============================================================================
# Phase 1b, A: the refit on both runs (plans/BATTERY-GAUGE-REFINE-PLAN.md,
# A1-A2). Runs only with --refit. Nothing above changes, so run 1's
# fit-output.txt still reproduces byte-identical.
#
# Two runs of one pack at one load: the leave-one-out numbers are a two-run
# consistency check, not a confidence bound, and the acceptance thresholds are
# engineering thresholds.

RUN2 = os.path.join(HERE, "..", "history", "battery-2026-10-01-drain")
RUN2_LOG = "log-20261003-1929.csv"   # v4, 10-min entries, the PLAIN mean of every 5C
                                     # report, stamped at the period's end
RUN2_VIDEO = "video-trace.csv"       # the gauge's TRIMMED mean read off the debug
                                     # page, every ~15 min, wall times +-1 min
RUN2_START = datetime(2026, 10, 2, 11, 0, 0)     # JD: "unplugging now 11:00:00 precisely"
RUN2_CUT = datetime(2026, 10, 4, 13, 33, 25)     # the LED step in the video, +-5 s
RUN2_FIRST_END = datetime(2026, 10, 2, 11, 15)   # the inclusion rule: entries ending after
# The 19:29 dump's plug-in came after the last completed entry, so the log has
# no trace of it. An assumed duration, with run 1's charge credit r; the range
# is reported as a sensitivity.
RUN2_PLUG = datetime(2026, 10, 3, 19, 29, 40)
PLUG_S, PLUG_S_RANGE = 45.0, (15.0, 90.0)
WHITE_SEGMENT = "full white (lights on)"

NOMINAL_MIN = {"log": 10.0, "video": 15.0}
# Smoothing in time, the same bandwidth for both sources: a running median over
# +-15 min (+1 min for the video's +-1 min timestamps), then a centered mean
# over a 50-min window. A segment splits only at a real gap, > 1.5x the
# source's nominal interval; the two sources are never smoothed together.
MEDIAN_HALF_S = 16 * 60
MEAN_HALF_S = 25 * 60
BANDS = [(0, 3600), (3600, 3800), (3800, 3950), (3950, 4036)]
BAND_NAMES = ["3.40-3.60", "3.60-3.80", "3.80-3.95", "3.95-4.036"]
ACCEPT = {"below": (1.0, 3.0), "plateau": (3.5, 9.0)}   # (rms, |worst|), points


def run1_points():
    """Run 1 on the legacy time axis (build(), unchanged), with the refit's
    censoring: no USB in the entry, and no report on either clamp (c5_min 0 or
    c5_max 100 -- a mean that includes a bound is not a measurement)."""
    rows = load()
    pts, t_cut, r = build(rows)
    pts, t_cut, r = build(rows, run_h=t_cut)
    out = []
    for p in pts:
        if p["end"] > CUT or p["fu"] != 0.0 or p["c5"] is None:
            continue
        if p["c5_min"] in (None, 0) or p["c5_max"] in (None, 100):
            continue
        out.append({"src": "log", "wall": p["end"] - timedelta(minutes=5), "t": p["t_mid"],
                    "mv": c5_to_mv(p["c5"]), "level": 1 - p["t_mid"] / t_cut,
                    "w": NOMINAL_MIN["log"]})
    return out, t_cut, r


def run2_rows():
    with open(os.path.join(RUN2, RUN2_LOG)) as f:
        log = list(csv.DictReader(f))
    with open(os.path.join(RUN2, RUN2_VIDEO)) as f:
        video = list(csv.DictReader(f))
    return log, video


def run2_points(r, plug_s=PLUG_S, offsets=None):
    """Run 2 on the same footing: t_eff from 11:00:00, each log entry's span
    counted at its own LED drive (clipped at 11:00:00, so the 11:09 entry's USB
    minute is excluded by time), full white after the last entry, and the
    plug-in modeled as plug_s with no draw and r x plug_s put back."""
    offsets = offsets or {}
    log, video = run2_rows()
    p = lambda led: BASE + (1 - BASE) * led / 1000.0
    spans = []                     # (start, end, power) from the log, clipped
    for e in log:
        end = datetime.strptime(e["time"], "%Y-%m-%d %H:%M")
        start = max(end - timedelta(minutes=10), RUN2_START)
        if end <= RUN2_START:
            continue
        spans.append((start, end, p(float(e["led_pm"]))))
    log_end = spans[-1][1]

    def t_eff(t):
        h = 0.0
        for s, e, pw in spans:
            if t <= s:
                break
            h += (min(t, e) - s).total_seconds() / 3600 * pw
        if t > log_end:
            h += (t - log_end).total_seconds() / 3600     # full white, p = 1
        if t >= RUN2_PLUG + timedelta(seconds=plug_s):
            h -= (1 + r) * plug_s / 3600                  # no draw, and r x put back
        return h

    T = t_eff(RUN2_CUT)
    pts = []
    for e in log:
        end = datetime.strptime(e["time"], "%Y-%m-%d %H:%M")
        if end <= RUN2_FIRST_END or not e["pack_mv"] or "external" in e["flags_any"].split():
            continue
        assert int(e["c5_min"]) > 0 and int(e["c5_max"]) < 100     # what pack_mv's presence means
        mid = end - timedelta(minutes=5)
        pts.append({"src": "log", "wall": mid, "t": t_eff(mid),
                    "mv": c5_to_mv(float(e["c5_mean"])) + offsets.get("log", 0.0),
                    "w": NOMINAL_MIN["log"], "pack_mv_logged": int(e["pack_mv"])})
    for v in video:
        if v["segment"] != WHITE_SEGMENT:
            continue
        t = datetime.strptime(v["wall_time"], "%Y-%m-%d %H:%M:%S")
        pts.append({"src": "video", "wall": t, "t": t_eff(t),
                    "mv": float(v["pack_mv"]) + offsets.get("video", 0.0), "w": NOMINAL_MIN["video"]})
    for q in pts:
        q["level"] = 1 - q["t"] / T
    led_batt = [int(e["led_pm"]) for e in log
                if datetime.strptime(e["time"], "%Y-%m-%d %H:%M") > RUN2_START + timedelta(minutes=10)]
    return pts, T, min(led_batt), log_end


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def smooth_time(pts):
    """Each source on its own, split at real gaps, smoothed by timestamp.
    Returns [(t_eff, smoothed mV)] in t_eff order, and the segments' ends."""
    out, ends = [], []
    for src in sorted({q["src"] for q in pts}):
        s = sorted((q for q in pts if q["src"] == src), key=lambda q: q["wall"])
        segs, cur = [], [s[0]]
        for a, b in zip(s, s[1:]):
            if (b["wall"] - a["wall"]).total_seconds() > 1.5 * NOMINAL_MIN[src] * 60:
                segs.append(cur); cur = []
            cur.append(b)
        segs.append(cur)
        for seg in segs:
            near = lambda q, half: [x for x in seg if abs((x["wall"] - q["wall"]).total_seconds()) <= half]
            med = {id(q): _median([x["mv"] for x in near(q, MEDIAN_HALF_S)]) for q in seg}
            for q in seg:
                w = [med[id(x)] for x in near(q, MEAN_HALF_S)]
                out.append((q["t"], sum(w) / len(w)))
            ends.append((seg[0]["t"], seg[-1]["t"]))
    out.sort()
    return out, ends


def path_from(pts, T, gap=None, hold=None):
    """mV against t_eff: smoothed, the cut at 3400 mV appended, made monotone.
    hold: None (linear across a gap in time), "high" (the gap's earlier voltage
    held to its far side) or "low" (the later one held back to its near side),
    for the gap (t0, t1) in t_eff."""
    sm, _ = smooth_time(pts)
    if gap and hold:
        t0, t1 = gap
        before = [v for t, v in sm if t <= t0][-1]
        after = [v for t, v in sm if t >= t1][0]
        sm.append((t1 - 1e-6, before) if hold == "high" else (t0 + 1e-6, after))
        sm.sort()
    ts = [t for t, _ in sm] + [T]
    vs = pava_decreasing([v for _, v in sm] + [3400.0])
    return ts, vs


def knots_from(paths, levels=LEVELS, top_pm=900):
    """Knots at even steps of level: for each, the mean over the given runs of
    each run's smoothed voltage at that fraction of its runtime. One run is a
    single-run curve; two are the pooled curve."""
    mv, pm, raw = [], [], {}
    for l in levels:
        vals = [mv_at(ts, vs, (1 - l / 1000) * T) for ts, vs, T in paths]
        raw[l] = vals
        v = round(sum(vals) / len(vals))
        if mv and v <= mv[-1]:
            continue
        mv.append(v); pm.append(l)
    mv.append(4036); pm.append(top_pm)
    return mv, pm, raw


def errors(curve, pts):
    cmv, cpm = curve
    return [(level_at(cmv, cpm, q["mv"]) / 10 - 100 * q["level"], q) for q in pts]


def stats(errs):
    if not errs:
        return None
    n = len(errs)
    rms = (sum(e * e for e, _ in errs) / n) ** 0.5
    wsum = sum(q["w"] for _, q in errs)
    wrms = (sum(q["w"] * e * e for e, q in errs) / wsum) ** 0.5
    worst = max((e for e, _ in errs), key=abs)
    return n, rms, wrms, worst


def score_lines(curve, pts, label):
    errs = errors(curve, pts)
    lines = [f"  {label}"]
    srcs = sorted({q["src"] for q in pts})
    for src in (["all"] + srcs if len(srcs) > 1 else ["all"]):
        sel = [x for x in errs if src == "all" or x[1]["src"] == src]
        for (lo, hi), name in zip(BANDS + [(0, 3950)], BAND_NAMES + ["below 3.95"]):
            s = stats([x for x in sel if lo <= x[1]["mv"] < hi])
            if s:
                n, rms, wrms, worst = s
                lines.append(f"    {src:5s} {name:10s} n {n:3d}  rms {rms:4.2f}  time-weighted rms {wrms:4.2f}  worst {worst:+6.2f}")
    return lines, errs


def accept(errs):
    """The plan's thresholds, per point and time-weighted."""
    out = {}
    for key, (lo, hi) in [("below", (0, 3950)), ("plateau", (3950, 4036))]:
        s = stats([x for x in errs if lo <= x[1]["mv"] < hi])
        n, rms, wrms, worst = s
        r_max, w_max = ACCEPT[key]
        out[key] = (rms <= r_max and wrms <= r_max and abs(worst) <= w_max, rms, wrms, worst)
    return out


def refit():
    write = "--write" in sys.argv
    lines = []
    say = lines.append

    p1, T1, r = run1_points()
    p2, T2, led_min, log_end = run2_points(r)
    gap = (max(q["t"] for q in p2 if q["src"] == "log"), min(q["t"] for q in p2 if q["src"] == "video"))

    say("Phase 1b, A: the refit on both runs (scripts/battery_fit.py --refit)")
    say("")
    say(f"run 1  T {T1:.2f} h of full white (the legacy axis); r = {r:.1f}; {len(p1)} points under the")
    say("       refit's censoring (no USB in the entry, no report at 0 or 100)")
    say(f"run 2  T {T2:.2f} h ({(RUN2_CUT - RUN2_START).total_seconds() / 3600:.2f} h wall, "
        f"{RUN2_START:%m-%d %H:%M:%S} -> {RUN2_CUT:%m-%d %H:%M:%S}); the {RUN2_PLUG:%H:%M:%S} plug-in "
        f"modeled as {PLUG_S:.0f} s at r = {r:.1f}")
    say(f"       {sum(q['src'] == 'log' for q in p2)} log + {sum(q['src'] == 'video' for q in p2)} video = "
        f"{len(p2)} points; lowest led_pm in an on-battery entry: {led_min} (no dim stretch)")
    say(f"       the data gap: {log_end:%m-%d %H:%M} (last entry) -> the first video sample; "
        f"t_eff {gap[0]:.2f} -> {gap[1]:.2f} h")
    say("")

    # The run-1 curve on run 2 as docs/battery.md states it: the 216-point rule,
    # levels on the WALL clock, (13:33:25 - t) / 50.56 h, and the log's mV as
    # logged (pack_mv, whole mV). That reproduces the stated figures exactly
    # (plateau rms 3.156, worst -8.490). The refit below uses t_eff, and the
    # unrounded mV from c5_mean: on the plateau 1 mV is up to ~2.5 points, so
    # the rounding alone moves a single point's error by up to ~1 point.
    p2_wall = [dict(q, mv=q.get("pack_mv_logged", q["mv"]),
                    level=(RUN2_CUT - q["wall"]).total_seconds() / 3600 / 50.56) for q in p2]
    legacy = ([3400, 3460, 3491, 3523, 3537, 3566, 3596, 3640, 3676, 3721, 3747, 3783, 3813, 3832,
               3846, 3855, 3867, 3894, 3943, 3982, 3999, 4006, 4008, 4011, 4017, 4036],
              [0, 10, 20, 30, 40, 50, 60, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500,
               550, 600, 650, 700, 750, 800, 850, 900])
    say("The run-1 curve on the board (759e265796) scored on run 2, as stated in docs/battery.md")
    say("(levels on the wall clock, the 216-point rule; a reproduction, not a new result):")
    ls, _ = score_lines(legacy, p2_wall, "run-1 curve vs run 2, wall-clock levels")
    lines += ls
    ls, _ = score_lines(legacy, p2, "run-1 curve vs run 2, t_eff levels (the refit's axis)")
    lines += ls
    say("")

    paths = {}
    paths[1] = path_from(p1, T1) + (T1,)
    paths[2] = path_from(p2, T2) + (T2,)
    c1 = knots_from([paths[1]])
    c2 = knots_from([paths[2]])
    cp = knots_from([paths[1], paths[2]])

    say("Leave-one-out (out-of-sample), by band; errors in points, curve minus truth:")
    ls, e12 = score_lines(c1[:2], p2, "fit on run 1 alone, scored on run 2")
    lines += ls
    ls, e21 = score_lines(c2[:2], p1, "fit on run 2 alone, scored on run 1")
    lines += ls
    say("")
    say("Acceptance (engineering thresholds: below 3.95 V rms <= 1.0, worst <= 3; plateau rms <= 3.5,")
    say("worst <= 9; rms both per point and time-weighted):")
    verdicts = {}
    for name, errs in [("run 1 -> run 2", e12), ("run 2 -> run 1", e21)]:
        a = accept(errs)
        verdicts[name] = a
        for key in ("below", "plateau"):
            ok, rms, wrms, worst = a[key]
            say(f"  {name}  {key:8s} rms {rms:4.2f} / {wrms:4.2f} tw  worst {worst:+6.2f}  "
                f"{'MEETS' if ok else 'MISSES'}")
    all_ok = all(v[k][0] for v in verdicts.values() for k in v)
    say("  => " + ("met in both directions: the pooled curve goes to the firmware (no D4)."
                   if all_ok else "MISSED: take decision D4; do not tune further on two runs."))
    say("")

    say("Training diagnostics -- the pooled curve scored on the runs it was fitted to (NOT validation):")
    ls, _ = score_lines(cp[:2], p1, "pooled vs run 1")
    lines += ls
    ls, _ = score_lines(cp[:2], p2, "pooled vs run 2")
    lines += ls
    say("")

    say("Knots (mV at each level): run 1 alone / run 2 alone / pooled (the firmware's)")
    gap_levels = [l for l in LEVELS if gap[0] < (1 - l / 1000) * T2 < gap[1]]
    for l in LEVELS:
        v1, v2 = cp[2][l]
        flag = "  <- run 2's value inside its data gap" if l in gap_levels else ""
        say(f"  {l / 10:5.1f}%  {v1:7.1f}  {v2:7.1f}  {round((v1 + v2) / 2):5d}{flag}")
    say(f"  {90.0:5.1f}%  4036 (the clamp's bound; LEVEL_CLAMP_EXIT)")
    dropped = [l for l in LEVELS if l not in cp[1]]
    if dropped:
        say(f"  dropped (not strictly rising): {', '.join(f'{l / 10:g}%' for l in dropped)}")
    say("")
    say("static const uint16_t curve_mv[] = {" + ", ".join(map(str, cp[0])) + "};")
    say("static const uint16_t curve_pm[] = {" + ", ".join(map(str, cp[1])) + "};")
    say("")

    # Sensitivities.
    say("Sensitivity -- the gap (19:29 -> 23:30 10-03): run 2's knots inside it, and the scores, with the")
    say("gap interpolated linearly in time, or held at either end's voltage (the monotone extremes):")
    for hold in (None, "high", "low"):
        pth = path_from(p2, T2, gap, hold) + (T2,)
        c2h = knots_from([pth])
        cph = knots_from([paths[1], pth])
        ks = "  ".join(f"{l / 10:g}%: run2 {cph[2][l][1]:.0f} pooled {round(sum(cph[2][l]) / 2)}" for l in gap_levels)
        _, ea = score_lines(c2h[:2], p1, "")
        s_b = stats([x for x in ea if x[1]["mv"] < 3950]); s_p = stats([x for x in ea if x[1]["mv"] >= 3950])
        say(f"  {hold or 'linear':6s} {ks}")
        say(f"         run 2 alone -> run 1: below 3.95 rms {s_b[1]:.2f} worst {s_b[3]:+.2f}; "
            f"plateau rms {s_p[1]:.2f} worst {s_p[3]:+.2f}")
    say("")
    say("Sensitivity -- the plug-in's assumed duration (with r):")
    for s in (PLUG_S_RANGE[0], PLUG_S, PLUG_S_RANGE[1]):
        q2, t2, _, _ = run2_points(r, plug_s=s)
        pth = path_from(q2, t2) + (t2,)
        cps = knots_from([paths[1], pth])
        _, ea = score_lines(c1[:2], q2, "")
        a = accept(ea)
        moved = max(abs(a_ - b_) for a_, b_ in zip(cps[0], cp[0])) if len(cps[0]) == len(cp[0]) else float("nan")
        say(f"  {s:3.0f} s  T2 {t2:.3f} h  pooled knots move <= {moved:.0f} mV; run 1 -> run 2: "
            f"below rms {a['below'][1]:.2f} worst {a['below'][3]:+.2f}, plateau rms {a['plateau'][1]:.2f} "
            f"worst {a['plateau'][3]:+.2f}")
    say("")
    say("Sensitivity -- one source shifted +-2 mV (the two estimators were never sampled together, so no")
    say("offset between them is measurable; this is a sensitivity, not a correction):")
    for src in ("log", "video"):
        for d in (-2.0, 2.0):
            q2, t2, _, _ = run2_points(r, offsets={src: d})
            pth = path_from(q2, t2) + (t2,)
            cps = knots_from([paths[1], pth])
            c2s = knots_from([pth])
            _, ea = score_lines(c1[:2], q2, "")
            _, eb = score_lines(c2s[:2], p1, "")
            a, b = accept(ea), accept(eb)
            moved = [f"{l / 10:g}% {round(sum(cps[2][l]) / 2) - round(sum(cp[2][l]) / 2):+d}"
                     for l in LEVELS if round(sum(cps[2][l]) / 2) != round(sum(cp[2][l]) / 2)]
            say(f"  {src:5s} {d:+.0f} mV  pooled knots moved: {', '.join(moved) or 'none'}")
            say(f"              run 1 -> run 2 plateau rms {a['plateau'][1]:.2f} worst {a['plateau'][3]:+.2f}; "
                f"run 2 -> run 1 plateau rms {b['plateau'][1]:.2f} worst {b['plateau'][3]:+.2f}")

    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if write:
        with open(os.path.join(RUN2, "refit-output.txt"), "w") as f:
            f.write(text)
        for pts, T, path, folder in [(p1, T1, paths[1], RUN), (p2, T2, paths[2], RUN2)]:
            with open(os.path.join(folder, "refit-points.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["source", "time", "t_eff_h", "level_pct", "pack_mv", "smoothed_mv",
                            "err_pooled", "err_loo"])
                other = c2 if pts is p1 else c1
                for q in sorted(pts, key=lambda q: q["t"]):
                    w.writerow([q["src"], f"{q['wall']:%Y-%m-%d %H:%M:%S}", f"{q['t']:.3f}",
                                f"{100 * q['level']:.2f}", f"{q['mv']:.1f}",
                                f"{mv_at(path[0], path[1], q['t']):.1f}",
                                f"{level_at(cp[0], cp[1], q['mv']) / 10 - 100 * q['level']:+.2f}",
                                f"{level_at(other[0], other[1], q['mv']) / 10 - 100 * q['level']:+.2f}"])
        sys.stdout.write("\nwritten: refit-output.txt (run 2's folder), refit-points.csv (each run's)\n")


if __name__ == "__main__":
    if "--refit" in sys.argv:
        refit()
    else:
        main()
