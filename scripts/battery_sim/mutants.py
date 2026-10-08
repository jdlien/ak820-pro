#!/usr/bin/env python3
"""B2's mutants table (plans/BATTERY-GAUGE-REFINE-PLAN.md, "Mutants, each
caught"): each mutant is a textual change to a COPY of flash 2's battery.c (or,
for the generator's, to the generator in this process), and each must make the
test the plan names for it fail. First every catching test runs on the
unmutated source and must pass, or a "caught" would mean nothing.

The round-4 "990 cap removed" mutant is retired, as the plan says: a table
ending at 990 with a saturated index makes a separate cap redundant.

Usage: mutants.py [--src DIR]   (default: the board's battery.c, or
$BATTERY_SIM_SRC). Exit status 1 if a mutant survives or a clean run fails.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tail_fw_grid as G   # noqa: E402
import tail_grid as TG     # noqa: E402

ROUND3 = G.ROUND3
CORNER = (230, 4.25, 0, 5.0)   # the degenerate corner: M shows 990 hours before the clock arrives
CC = ["cc", "-std=c11", "-O1", "-Wall", "-Wno-unused-parameter", "-Wno-unused-function"]
SAN = ["-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]

LOOKUP_SAT = "    if (i >= BATT_TAIL_N) return batt_tail_x16[BATT_TAIL_N];\n"
OVERRUN_CLOCK = "    } else if (m_in_tail && t_tail >= BATT_T_TAIL_S + T_OVERRUN_S) {"
CHG_TICK = "/* Once a second while the model is open. */\nstatic void chg_tick_1hz(void) {"

# (name, [(old, new), ...] on battery.c, [catchers]); a catcher is
# ("sim", scenario), ("asan", scenario) or ("grid", point).
MUTANTS = [
    ("FULL leaves the pause's relax timer running",
     [("        chg_close(CHG_FULL);\n"
       "        /* The pause that led here started RELAX_S; FULL needs no relaxed\n"
       "         * estimate, and emptying the ring would drop FULL until it refills. */\n"
       "        relax_cancel();",
       "        chg_close(CHG_FULL);")],
     [("sim", "m_full_holds")]),
    ("FROM-FLAT latched at the next task, not the fifth report",
     [("    if (c5_count == C5_MIN_EST) boot_first_latch(c5_est);\n", ""),
      ("            level_report(m);",
       "            if (m != C5_EST_NONE) boot_first_latch(m);\n            level_report(m);")],
     [("sim", "m_flat_burst"), ("sim", "m_flat_burst_above")]),
    ("a resumption after an unadopted handover starts from the held number",
     [("    bool unadopted = adopt_owed;\n", "    bool unadopted = false;\n")],
     [("sim", "m_pause_after_unadopted")]),
    ("K_CC = 0",
     [("uint32_t m = m_l0 + (BATT_K_CC_PM_PER_H * m_lin_s) / 3600u;",
       "uint32_t m = m_l0 + (0u * m_lin_s) / 3600u;")],
     [("sim", "m_partial_below_knee")]),
    ("the tail started at clamp entry (round 1's formula)",
     [("    model_advance();\n    uint16_t e     = battery_5c_x100();",
       "    { uint16_t e0 = battery_5c_x100();\n"
       "      if (!m_in_tail && e0 != C5_EST_NONE && c5_top(e0)) { m_in_tail = true; t_tail = 0; } }\n"
       "    model_advance();\n    uint16_t e     = battery_5c_x100();")],
     [("sim", "m_early_clamp"), ("sim", "m_early_clamp_below"), ("grid", ROUND3)]),
    ("the ceiling U ignored",
     [("    if (cand > bound) cand = bound;\n", "    (void)bound;\n")],
     [("sim", "m_ceil_hold30"), ("sim", "m_ceil_60_29"), ("sim", "m_ceil_clamp_exit")]),
    ("the rise limiter removed",
     [("        uint16_t nl = cand < up ? cand : up;", "        uint16_t nl = cand; (void)up;")],
     [("sim", "m_ceil_clamp_entry")]),
    ("the LOST timer resetting at the clamp instead of holding",
     [("    if (below) lost_a_s = (m_pm > u + LOST_PM) ? (uint16_t)(lost_a_s + 1u) : 0u;   /* else it holds */",
       "    lost_a_s = (below && m_pm > u + LOST_PM) ? (uint16_t)(lost_a_s + 1u) : 0u;")],
     [("sim", "m_ceil_clamp_hold")]),
    ("the re-seat before RELAX_S",
     [("            below_run = 0;\n            if (!relax_done) return;\n            adopt_relaxed(m);",
       "            below_run = 0;\n            adopt_relaxed(m);")],
     [("sim", "m_reseat_0929")]),
    ("the lookup index not saturated (reads past the table)",
     [(LOOKUP_SAT, "")],
     [("grid", ROUND3), ("asan", "m_delayed_termination")]),
    ("OVERRUN keyed on M reaching 990 instead of the clock",
     [(CHG_TICK, "static uint32_t mut_s990;\n" + CHG_TICK),
      (OVERRUN_CLOCK,
       "    } else if (m_in_tail && m_pm >= LEVEL_MODEL_CAP && ++mut_s990 >= T_OVERRUN_S) {")],
     [("grid", CORNER)]),
    ("OVERRUN timed from session start instead of the tail clock",
     [(CHG_TICK, "static uint32_t mut_sess;\n" + CHG_TICK),
      (OVERRUN_CLOCK, "    } else if (++mut_sess >= BATT_T_TAIL_S + T_OVERRUN_S) {")],
     [("grid", ROUND3)]),
    ("entry above the knee by node only (no in-segment solve)",
     [("            return i * 60u + ((target - batt_tail_x16[i]) * 60u + d - 1u) / d;",
       "            (void)d;\n            return (i + 1u) * 60u;")],
     [("grid", ROUND3)]),
    ("UNKNOWN treated as a number",
     [("    } else if (level != LEVEL_UNKNOWN) {\n        chg_st   = CHG_MODEL;",
       "    } else if (true) {\n        chg_st   = CHG_MODEL;")],
     [("sim", "m_unknown_start")]),
]


def round2_table(k, lk, t_h):
    """Round 2's generator: tau = T_TAIL / ln((1000 - L_KNEE) / 10), M = 1000 - g."""
    ts = round(t_h * 3600 / TG.NODE_S) * TG.NODE_S
    tau = (ts / 3600) / math.log((1000 - lk) / 10)
    curve = lambda s: 1000 - (1000 - lk) * math.exp(-(s / 3600) / tau)
    nodes = [round(curve(i * TG.NODE_S) * TG.FRAC) for i in range(ts // TG.NODE_S + 1)]
    nodes[-1] = 990 * TG.FRAC
    return tau, 1000.0, ts, curve, nodes


def build(src, mutations, sanitize=False):
    d = tempfile.mkdtemp(prefix="mutant-")
    shutil.copytree(os.path.join(HERE, "stubs"), d, dirs_exist_ok=True)
    for f in ("battery.c", "battery.h", "power.c", "power.h", "battery_tail.h"):
        shutil.copy(os.path.join(src, f), d)
    p = os.path.join(d, "battery.c")
    s = open(p).read()
    for old, new in mutations:
        if s.count(old) != 1:
            raise SystemExit(f"mutation site not found exactly once: {old[:70]!r}")
        s = s.replace(old, new)
    open(p, "w").write(s)
    b = subprocess.run(CC + (SAN if sanitize else []) + ["-I" + d, "-o", os.path.join(d, "sim"),
                       os.path.join(HERE, "sim.c"), p, os.path.join(d, "power.c"), "-lm"],
                       capture_output=True, text=True)
    if b.returncode:
        raise SystemExit(f"build failed: {b.stderr[:600]}")
    return d


def caught(d, catcher):
    """True if the catcher FAILS on the source in d."""
    kind, what = catcher
    if kind == "grid":
        tag, status, fails = G.point((what, d, what == ROUND3))
        return status == "fail", (fails[0] if fails else status)
    if kind == "asan":
        sd = build(d, [], sanitize=True)
        try:
            o = subprocess.run([os.path.join(sd, "sim"), what], capture_output=True, text=True)
        finally:
            shutil.rmtree(sd, ignore_errors=True)
        msg = next((l for l in o.stderr.splitlines() if "ERROR" in l or "runtime error" in l), "")
        return o.returncode != 0, msg.strip()[:120]
    o = subprocess.run([os.path.join(d, "sim"), what], capture_output=True, text=True)
    msg = next((l for l in o.stdout.splitlines() if "FAIL line" in l), "")
    return o.returncode != 0, msg.strip()[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.environ.get("BATTERY_SIM_SRC",
                    os.path.join(G.ROOT, "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro")))
    a = ap.parse_args()
    bad = 0

    clean = build(a.src, [])
    try:
        catchers = sorted({c for _, _, cs in MUTANTS for c in cs} | {("grid", ROUND3), ("sim", "m_early_clamp")},
                          key=str)
        for c in catchers:
            fails, msg = caught(clean, c)
            print(f"{'FAIL' if fails else 'ok  '} clean {c[0]} {c[1]}" + (f": {msg}" if fails else ""))
            bad += fails
    finally:
        shutil.rmtree(clean, ignore_errors=True)
    if bad:
        print("FAIL mutants: a catcher fails on the unmutated source; nothing below would mean anything")
        sys.exit(1)

    for name, muts, cs in MUTANTS:
        d = build(a.src, muts)
        try:
            hits = [(c, msg) for c in cs for ok, msg in [caught(d, c)] if ok]
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if hits:
            print(f"ok   caught: {name} -- by {', '.join(f'{c[0]} {c[1]}' for c, _ in hits)}")
            print(f"       {hits[0][1]}")
        else:
            bad += 1
            print(f"FAIL SURVIVED: {name} (catchers {cs})")

    # The generator's mutant: round 2's tau, at round 3's set, through the
    # firmware (header, lookup and model) with the spec patched to match, so
    # only the plan's named checks can catch it.
    real = TG.table
    TG.table = round2_table
    try:
        tag, status, fails = G.point((ROUND3, a.src, True))
    finally:
        TG.table = real
    named = [f for f in fails if "1 h rise" in f or "m_early_clamp" in f]
    if named:
        print(f"ok   caught: the generator using round 2's tau formula -- {named[0]}")
    else:
        bad += 1
        print(f"FAIL SURVIVED: the generator using round 2's tau formula ({status}: {fails[:2]})")

    print(f"{'FAIL' if bad else 'ok  '} mutants: {len(MUTANTS) + 1 - bad} of {len(MUTANTS) + 1} caught")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
