#!/usr/bin/env python3
"""B2's mutants table (plans/BATTERY-GAUGE-REFINE-PLAN.md, "Mutants, each
caught"): each mutant is a textual change to a COPY of flash 2's battery.c (or,
for the generator's, to the generator in this process), and each must make the
test the plan names for it fail. First every catching test runs on the
unmutated source and must pass, or a "caught" would mean nothing.

POWER_MUTANTS do the same to power.c and DRIFT (rgb_matrix_kb.inc), for the
revised power modes (plans/POWER-MODES-REVISION-PLAN.md), caught by the
plain build, the dev-hooks build or the colour build (run.sh's three).

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
# ("sim", scenario), ("asan", scenario), ("grid", point), or, for
# POWER_MUTANTS, ("dev", scenario) or ("colour", scenario): the scenario in
# run.sh's dev-hooks or colour build.
MUTANTS = [
    ("the log's sum and count accept again after the first rejection",
     [("    if (!lg_c5_saturated && lg_c5_n < UINT16_MAX", "    if (lg_c5_n < UINT16_MAX")],
     [("sim", "m_log_saturated")]),
    ("the boot's first estimate skipped while the supply is unknown",
     [("    if (boot_first_taken) return;\n    boot_first_taken = true;\n",
       "    if (boot_first_taken || supply != BATTERY_SUPPLY_EXTERNAL) return;\n    boot_first_taken = true;\n")],
     [("sim", "m_flat_unknown_first")]),
    ("a handover's held number trusted again after an unplug",
     [("    bool unadopted = adopt_owed || level_held;\n", "    bool unadopted = adopt_owed;\n")],
     [("sim", "m_handover_unplug_replug")]),
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
     [("    bool unadopted = adopt_owed || level_held;\n", "    bool unadopted = false;\n")],
     [("sim", "m_pause_after_unadopted"), ("sim", "m_handover_unplug_replug")]),
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


# Survivors already known, printed every run but not counted: each needs its
# catcher looked at, not a pass. The re-seat's: m_reseat_0929 passes with the
# re-seat before RELAX_S since Phase 2 (the level is the count, re-seated into
# the band), on 8b06e4dcc4's battery.c as on this one (BACKLOG.md).
KNOWN_SURVIVORS = {"the re-seat before RELAX_S"}

# (name, file, [(old, new), ...] on that file, [catchers]).
POWER_MUTANTS = [
    ("no re-apply when only the ceiling changes", "power.c",
     [("    if (want != stage || lit != shown_lit || wval != want_val) {",
       "    if (want != stage || lit != shown_lit) {")],
     [("sim", "l_ceiling_moves"), ("dev", "l_set_mode")]),
    ("the low cap not taking Saver's ceiling", "power.c",
     [("            if (wval > SAVER_VAL) wval = SAVER_VAL;\n", "")],
     [("sim", "l_low_cap"), ("sim", "l_low_edge")]),
    ("Normal's old RGB-off time (5 min) restored", "power.c",
     [("{600000u, 1200000u, 1200000u, 1200000u, 255u}", "{600000u, 300000u, 1200000u, 1200000u, 255u}")],
     [("sim", "l_normal"), ("sim", "l_no_lights_off")]),
    ("Saver's ceiling a halving of the value, not a ceiling", "power.c",
     [("    if (hsv.v > val_cap) hsv.v = val_cap;\n",
       "    if (val_cap == SAVER_VAL) hsv.v /= 2;\n    else if (hsv.v > val_cap) hsv.v = val_cap;\n")],
     [("sim", "l_val_cap"), ("colour", "k_hook")]),
    ("the desired and the applied ceiling compared as one", "power.c",
     [("|| wval != want_val) {", "|| wval != val_cap) {")],
     [("sim", "l_modes"), ("dev", "l_under_dim")]),
    ("a held stage on USB without the mode's ceiling", "power.c",
     [("        if (!battery_on_battery()) wval = ladders[mode].active_val;\n", "")],
     [("dev", "l_forced_ceiling")]),
    ("DRIFT's palette built through the ceiling again", "rgb_matrix_kb.inc",
     [("        drift_ramp[i] = hsv_to_rgb(c);", "        drift_ramp[i] = rgb_matrix_hsv_to_rgb(c);")],
     [("colour", "k_drift")]),
    ("DRIFT's value knob not capped", "rgb_matrix_kb.inc",
     [("    if (v > power_val_cap()) v = power_val_cap();\n", "")],
     [("colour", "k_drift")]),
    ("DRIFT's palette cache blind to a hue change", "rgb_matrix_kb.inc",
     [("    if (!drift_pal_valid || drift_pal_h != rgb_matrix_config.hsv.h\n"
       "                         || drift_pal_s != rgb_matrix_config.hsv.s) {",
       "    if (!drift_pal_valid || drift_pal_s != rgb_matrix_config.hsv.s) {")],
     [("colour", "k_drift_usb")]),
]


def round2_table(k, lk, t_h):
    """Round 2's generator: tau = T_TAIL / ln((1000 - L_KNEE) / 10), M = 1000 - g."""
    ts = round(t_h * 3600 / TG.NODE_S) * TG.NODE_S
    tau = (ts / 3600) / math.log((1000 - lk) / 10)
    curve = lambda s: 1000 - (1000 - lk) * math.exp(-(s / 3600) / tau)
    nodes = [round(curve(i * TG.NODE_S) * TG.FRAC) for i in range(ts // TG.NODE_S + 1)]
    nodes[-1] = 990 * TG.FRAC
    return tau, 1000.0, ts, curve, nodes


def build(src, mutations, sanitize=False, target="battery.c", flavour="sim", qroot=None):
    """A sim built from src's sources with `mutations` applied to `target`.
    flavour "dev" adds AK820_DEV_HOOKS; "colour" links QMK's quantum/color.c
    (from qroot, the tree src is in) in place of sim.c's stub."""
    d = tempfile.mkdtemp(prefix="mutant-")
    shutil.copytree(os.path.join(HERE, "stubs"), d, dirs_exist_ok=True)
    for f in ("battery.c", "battery.h", "power.c", "power.h", "battery_tail.h", "rgb_matrix_kb.inc"):
        if f != "rgb_matrix_kb.inc" or os.path.exists(os.path.join(src, f)):
            shutil.copy(os.path.join(src, f), d)
    # The backlight's scale, as run.sh selects it (the menu's P2b: 0-100 once
    # display.c has no 24-entry bkl_duty[]; codex, P2b's code review).
    disp = os.path.join(src, "graphics", "display.c")
    if os.path.exists(os.path.join(src, "indicator_levels.h")) and os.path.exists(disp) and \
            "static const uint8_t bkl_duty[]" not in open(disp, encoding="utf-8").read():
        shutil.copy(os.path.join(src, "indicator_levels.h"), d)
        open(os.path.join(d, "sim_bkl.h"), "w").write("#define SIM_BKL_100 1\n")
    p = os.path.join(d, target)
    s = open(p, encoding="utf-8").read()   # UTF-8 on every host (Windows' default is cp1252)
    for old, new in mutations:
        if s.count(old) != 1:
            raise SystemExit(f"mutation site not found exactly once: {old[:70]!r}")
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    extra, objs = [], []
    if flavour == "dev":
        extra = ["-DAK820_DEV_HOOKS"]
    elif flavour == "colour":
        extra = ["-DSIM_REAL_COLOUR", "-Wno-unused-function", "-idirafter", os.path.join(qroot, "quantum")]
        for f in ("color", "led_tables"):
            o = os.path.join(d, f + ".o")
            c = subprocess.run(["cc", "-std=c11", "-O1", "-DUSE_CIE1931_CURVE", "-I" + os.path.join(qroot, "quantum"),
                                "-I" + os.path.join(qroot, "platforms"), "-c", "-o", o,
                                os.path.join(qroot, "quantum", f + ".c")], capture_output=True, text=True)
            if c.returncode:
                raise SystemExit(f"QMK's {f}.c failed to build: {c.stderr[:600]}")
            objs.append(o)
    b = subprocess.run(CC + (SAN if sanitize else []) + extra + ["-I" + d, "-o", os.path.join(d, "sim"),
                       os.path.join(HERE, "sim.c"), os.path.join(d, "battery.c"), os.path.join(d, "power.c")]
                       + objs + ["-lm"], capture_output=True, text=True)
    if b.returncode:
        raise SystemExit(f"build failed: {b.stderr[:600]}")
    return d


def caught(d, catcher, qroot=None):
    """True if the catcher FAILS on the source in d."""
    kind, what = catcher
    if kind in ("dev", "colour"):
        fd = build(d, [], flavour=kind, qroot=qroot)
        try:
            o = subprocess.run([os.path.join(fd, "sim"), what], capture_output=True, text=True)
        finally:
            shutil.rmtree(fd, ignore_errors=True)
        msg = next((l for l in o.stdout.splitlines() if "FAIL line" in l), "")
        return o.returncode != 0, msg.strip()[:120]
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
    qroot = os.path.normpath(os.path.join(a.src, "..", "..", ".."))
    # The power mutants need the revised power.c (its want_val) and DRIFT.
    power = "want_val" in open(os.path.join(a.src, "power.c"), encoding="utf-8").read() and \
        os.path.exists(os.path.join(a.src, "rgb_matrix_kb.inc"))
    pmuts = POWER_MUTANTS if power else []
    bad = known = 0

    clean = build(a.src, [])
    try:
        catchers = sorted({c for _, _, cs in MUTANTS for c in cs} | {c for _, _, _, cs in pmuts for c in cs}
                          | {("grid", ROUND3), ("sim", "m_early_clamp")}, key=str)
        for c in catchers:
            fails, msg = caught(clean, c, qroot)
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
        elif name in KNOWN_SURVIVORS:
            known += 1
            print(f"KNOWN SURVIVOR: {name} (catchers {cs}; see KNOWN_SURVIVORS)")
        else:
            bad += 1
            print(f"FAIL SURVIVED: {name} (catchers {cs})")

    for name, target, muts, cs in pmuts:
        d = build(a.src, muts, target=target)
        try:
            hits = [(c, msg) for c in cs for ok, msg in [caught(d, c, qroot)] if ok]
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

    n = len(MUTANTS) + len(pmuts) + 1
    print(f"{'FAIL' if bad else 'ok  '} mutants: {n - bad - known} of {n} caught"
          + (f", {known} known survivor{'s' if known != 1 else ''}" if known else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
