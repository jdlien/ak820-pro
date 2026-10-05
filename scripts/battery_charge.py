#!/usr/bin/env python3
"""Phase 1b, B1: calibrate the charging model from the recorded charges from
flat (plans/BATTERY-GAUGE-REFINE-PLAN.md, B1).

Per charge: its start, `5C` reaching the clamp, the VDD rise (the KNEE), and the
charger's termination, with led_pm alongside VDD (the board's own load moves
VDD: +59 mV for LED 1000 -> 499 on 10-01). These are timings against the
sensor clamp and VDD, NOT measured CC/CV phases.

Definitions, so a cold session reproduces them:
- clamp: the first sample whose every report is 100 (one-minute: the value;
  ten-minute: c5_min == 100).
- plateau: the median VDD over the 30 min before the clamp, at the LED drive
  the knee is judged at.
- knee: the first sample from 30 min before the clamp on whose VDD is
  >= plateau + KNEE_MV. A one-minute sample is a time (+-1 min); a ten-minute
  entry is an interval, and its midpoint is used (+-5 min).
- termination: CHRG released, from each charge's record (below).

T_TAIL = termination - knee. t_knee = knee - start. K_CC is only BOUNDED here
(B3 measures it): if 70-90% of a full charge goes in before the knee,
K_CC = (700..900 pm) / t_knee.

The start classification is the plan's Note 1 reconstruction: the first five
reports of the first interval in ascending order from its logged min (09-28:
its logged 4, no zero invented). The first estimate averages them untrimmed;
<= 10.00 counts is FROM-FLAT.

Usage: battery_charge.py [--tail K_CC L_KNEE T_TAIL_H --header out.h]
With --tail it writes the firmware's tail table (B's TAIL_X16) for those
parameters, using the same construction tail_grid.py checks.
"""
import csv, os, statistics, sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "..", "history")
KNEE_MV = 10
FMT = "%Y-%m-%d %H:%M"

# Each charge: its log(s), its start, and its termination with the source.
CHARGES = [
    {"name": "09-28", "logs": ["battery-2026-09-25/charge-dumps/log-20260928-1034.csv"],
     "start": "2026-09-28 03:02", "start_src": "readings.csv: plugged in, CHRG low, 5C 2 -> 3 -> 4",
     "term": ("2026-09-28 12:32", "2026-09-28 12:32"),
     "term_src": "readings.csv 12:32: 'Charge LED out -- CHRG released ~9.5 h into the charge'; "
                 "the log ends at 10:34, and power was interrupted around then too"},
    {"name": "10-01", "logs": ["battery-2026-10-01-charge/log-20261001-1947.csv"],
     "start": "2026-10-01 08:46", "start_src": "readings.csv: plugged in ~08:45, boot ~08:46",
     "term": ("2026-10-01 18:06", "2026-10-01 18:16"),
     "term_src": "the 18:16 entry: charging in flags_any, not at its end"},
]
# The 10-04 charge is added below once its post-reboot log exists.
C1004_SEG2 = os.path.join(HIST, "battery-2026-10-04-charge")


def load(path):
    rows = []
    with open(os.path.join(HIST, path)) as f:
        for r in csv.DictReader(line for line in f if not line.startswith("#")):
            end = datetime.strptime(r["time"], FMT)
            if "c5_mean" in r:
                rows.append({"end": end, "dur": 600, "vdd": int(r["vdd_avg"]),
                             "c5_min": int(r["c5_min"]) if r["c5_min"] else None,
                             "c5_max": int(r["c5_max"]) if r["c5_max"] else None,
                             "c5_mean": float(r["c5_mean"]) if r["c5_mean"] else None,
                             "led": int(r["led_pm"]), "chg_end": r["charging"] == "1",
                             "chg_any": "charging" in r["flags_any"].split()})
            else:
                rows.append({"end": end, "dur": 60, "vdd": int(r["vdd_avg"]),
                             "c5_min": int(r["module_pct"]), "c5_max": int(r["module_pct"]),
                             "c5_mean": float(r["module_pct"]), "led": None,
                             "chg_end": r["charging"] == "1", "chg_any": r["charging"] == "1"})
    return rows


def mid(r):
    return r["end"] - timedelta(seconds=r["dur"] / 2)


def analyse(c, rows):
    start = datetime.strptime(c["start"], FMT)
    clamp = next((r for r in rows if r["c5_min"] == 100), None)
    out = {"name": c["name"], "start": start, "start_src": c["start_src"], "clamp": clamp}
    if clamp is None:
        return out
    t_c = clamp["end"] if clamp["dur"] == 60 else mid(clamp)
    win = [r for r in rows if t_c - timedelta(minutes=30) <= r["end"] < clamp["end"]]
    led = win[-1]["led"] if win else None
    plateau = statistics.median(r["vdd"] for r in win if r["led"] == led)
    knee = next((r for r in rows if r["end"] >= t_c - timedelta(minutes=30) and r["led"] == led
                 and r["vdd"] >= plateau + KNEE_MV), None)
    out.update({"t_clamp": t_c, "plateau": plateau, "plateau_led": led, "knee_row": knee,
                "t_knee": (knee["end"] if knee["dur"] == 60 else mid(knee)) if knee else None,
                "knee_pm": 1 if (knee and knee["dur"] == 60) else 5})
    t0, t1 = (datetime.strptime(x, FMT) for x in c["term"])
    out.update({"term": t0 + (t1 - t0) / 2, "term_pm": (t1 - t0).total_seconds() / 120,
                "term_src": c["term_src"]})
    # Note 1's opening: the first five reports.
    r0 = rows[0]
    if r0["dur"] == 60:
        first5 = [r0["c5_min"]] * 5
    else:
        first5 = sorted([r0["c5_min"]] + [r0["c5_min"]] * 4)  # ascending from the logged min
    out["first_est"] = sum(first5) / 5
    return out


def h(td):
    return td.total_seconds() / 3600


def main():
    charges = list(CHARGES)
    res = []
    for c in charges:
        rows = []
        for p in c["logs"]:
            rows += load(p)
        res.append(analyse(c, rows))
    print("B1: the recorded charges from flat (timings against the sensor clamp and VDD)\n")
    tt = []
    for a in res:
        print(f"{a['name']}: start {a['start']:%H:%M} ({a['start_src']})")
        if a.get("clamp") is None:
            print("  5C never clamped in the log\n")
            continue
        print(f"  5C at the clamp   {a['t_clamp']:%H:%M}  ({h(a['t_clamp'] - a['start']):.2f} h in)")
        led = a['plateau_led'] if a['plateau_led'] is not None else "n/a (not in the v1 log)"
        print(f"  VDD plateau       {a['plateau']:.0f} mV at LED {led} (30 min before the clamp)")
        if a["t_knee"]:
            print(f"  knee (VDD +{KNEE_MV})    {a['t_knee']:%H:%M} +-{a['knee_pm']} min  "
                  f"(VDD {a['knee_row']['vdd']}; t_knee {h(a['t_knee'] - a['start']):.2f} h)")
        pm = f"+-{a['term_pm']:.0f} min" if a["term_pm"] else "an observation, error unknown"
        print(f"  termination       {a['term']:%H:%M} {pm}  ({a['term_src']})")
        if a["t_knee"]:
            t = h(a["term"] - a["t_knee"])
            tt.append(t)
            print(f"  T_TAIL            {t:.2f} h   total {h(a['term'] - a['start']):.2f} h")
        print(f"  first estimate    {a['first_est']:.2f} counts -> "
              f"{'FROM-FLAT' if a['first_est'] <= 10.0 else 'UNKNOWN-CHG'} (Note 1 reconstruction)\n")
    if tt:
        print(f"T_TAIL: {', '.join(f'{x:.2f}' for x in tt)} h -> median {statistics.median(tt):.2f} h "
              f"(the median of {len(tt)})")
        tk = [h(a["t_knee"] - a["start"]) for a in res if a.get("t_knee")]
        print(f"t_knee: {', '.join(f'{x:.2f}' for x in tk)} h")
        lo, hi = 700 / max(tk), 900 / min(tk)
        print(f"K_CC bound (70-90% of a full charge before the knee): {lo:.0f}-{hi:.0f} pm/h "
              "(B3 measures it)")


def write_tail(k_cc, l_knee, t_tail_h, out, note):
    """The firmware's tail table (plan B): M at each minute from the knee, in
    1/16 pm, ending at exactly 990 * 16 at T_TAIL rounded to the minute. The
    construction is scripts/battery_sim/tail_grid.py's, which checks it over
    B1's whole grid."""
    sys.path.insert(0, os.path.join(HERE, "battery_sim"))
    import tail_grid as TG
    if TG.solve(k_cc, l_knee, round(t_tail_h * 60) / 60) is None:
        raise SystemExit(f"infeasible: 0 < 990 - L_KNEE < K_CC * T_TAIL fails for "
                         f"K_CC {k_cc}, L_KNEE {l_knee}, T_TAIL {t_tail_h} -- revise the model, "
                         "never the measurements")
    tau, a, ts, _, nodes = TG.table(k_cc, l_knee, t_tail_h)
    assert all(b >= x for x, b in zip(nodes, nodes[1:])), "the tail must not fall"
    lines = [
        "// Copyright 2026 JD Lien",
        "// SPDX-License-Identifier: GPL-2.0-or-later",
        "/* GENERATED by scripts/battery_charge.py --tail -- never hand-edit.",
        f" * {note}",
        f" * K_CC {k_cc} pm/h, L_KNEE {l_knee} pm, T_TAIL {ts // 60} min "
        f"({ts / 3600:.4f} h): tau {tau:.5f} h, A {a:.3f} pm,",
        f" * ending at {(a - 990) / tau:.3f} pm/h. M = A - (A - L_KNEE) e^(-t/tau) from the knee,",
        " * one node a minute in 1/16 pm, the last exactly 990 * 16 (plan B). */",
        "#pragma once",
        "#include <stdint.h>",
        f"#define BATT_K_CC_PM_PER_H {k_cc}u",
        f"#define BATT_L_KNEE_PM     {int(round(l_knee))}u",
        f"#define BATT_T_TAIL_S      {ts}u",
        f"#define BATT_TAIL_N        {len(nodes) - 1}u   /* nodes 0..N, one a minute */",
        "static const uint16_t batt_tail_x16[BATT_TAIL_N + 1] = {",
    ]
    for i in range(0, len(nodes), 12):
        lines.append("    " + ", ".join(str(x) for x in nodes[i:i + 12]) + ",")
    lines.append("};")
    lines.append('_Static_assert(sizeof(batt_tail_x16) / sizeof(batt_tail_x16[0]) == BATT_TAIL_N + 1, "tail table length");')
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}: {len(nodes)} nodes, tau {tau:.4f} h, A {a:.2f}")


if __name__ == "__main__":
    if "--tail" in sys.argv:
        i = sys.argv.index("--tail")
        k, lk, tt = float(sys.argv[i + 1]), float(sys.argv[i + 2]), float(sys.argv[i + 3])
        out = sys.argv[sys.argv.index("--header") + 1]
        note = sys.argv[sys.argv.index("--note") + 1] if "--note" in sys.argv else ""
        write_tail(int(k), lk, tt, out, note)
    else:
        main()
