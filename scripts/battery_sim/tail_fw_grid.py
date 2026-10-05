#!/usr/bin/env python3
"""The charging model's tail through the FIRMWARE, at every point of B1's grid
(plans/BATTERY-GAUGE-REFINE-PLAN.md, B2: "the firmware path (the generated
table through battery.c's lookup)" and "OVERRUN timing ... at every grid
point, the degenerate corner included").

tail_grid.py checks the construction in Python; this checks that battery.c
implements it. At each grid point it:

  1. writes battery_tail.h with the real generator (battery_charge.write_tail);
  2. builds tail_fw.c, which #includes battery.c verbatim, and requires,
     EXACTLY, against tail_grid.py's functions:
       - the header's N, T_TAIL, K_CC, L_KNEE, and a last node of 990 * 16;
       - tail_x16(s) for every second to T_TAIL + 1 h (so the index saturates
         at exactly 990 * 16 with no read past the table);
       - tail_entry_s(l0) for every l0 from the knee to 989, with the X16 entry
         property itself (M at the entry second >= l0 * 16, the second before
         < l0 * 16);
       - M, second by second, from model_start() through model_advance() for
         starts below, at and above the knee, to T_TAIL + 1 h past it;
     and on those trajectories: the 1 h rise <= K_CC + 1 pm from every start
     second, never above 990, never falling, and the shown whole pm within
     0.7 pm of the analytic curve in the tail;
  3. builds sim.c with the same header and runs m_overrun from starts below,
     at and above the knee: "Charge" by OVERRUN after (T_TAIL - entry) +
     T_OVERRUN of charging from a start above the knee, knee + T_TAIL +
     T_OVERRUN from below, +-1 s. Starts above ~900 cannot be made on the pack
     (the curve tops out at the clamp; the clamp guess is 950), so above that
     the entry and the clock are checked by step 2 alone.

At round 3's set (K 160, t_knee 4.1, R 30, T_TAIL 5.35) and at the shipped
header's set it also runs the model scenarios the plan names there. Usage:

  tail_fw_grid.py [--src DIR] [--point K TKNEE R TTAIL] [-j N]

--src is the firmware directory (default: the board's, or $BATTERY_SIM_SRC).
Exit status 1 if anything fails; infeasible points are reported, never fitted.
"""
import argparse
import concurrent.futures as cf
import contextlib
import io
import itertools
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import tail_grid as TG          # noqa: E402  the specification
import battery_charge as BC     # noqa: E402  the generator the firmware ships from

ROOT = os.path.join(HERE, "..", "..")
CC = ["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-function"]
T_OVERRUN = 3600
ROUND3 = (160, 4.1, 30, 5.35)
NAMED = ["m_partial_below_knee", "m_early_clamp", "m_delayed_termination", "m_delayed_unplug",
         "m_topup_near_full", "m_just_full"]


def knee_int(lk):
    return math.floor(lk + 0.5)


def expected_traj(nodes, k, lki, l0, secs):
    """M after model_start(l0) and each model_advance(), as the spec says."""
    out = []
    if l0 >= lki:
        t = TG.enter(nodes, l0)
        out.append(TG.show_pm(TG.m_fw(nodes, t)))
        for _ in range(secs):
            t += 1
            out.append(TG.show_pm(TG.m_fw(nodes, t)))
        return out
    out.append(l0)
    lin, tail = 0, None
    for _ in range(secs):
        if tail is None:
            lin += 1
            m = l0 + k * lin // 3600
            if m < lki:
                out.append(m)
                continue
            tail = 0
        else:
            tail += 1
        out.append(TG.show_pm(TG.m_fw(nodes, tail)))
    return out


def s_knee(k, lki, l0):
    return 0 if l0 >= lki else -(-(lki - l0) * 3600 // k)


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def point(args):
    (k, tk, r, t_h), src, named = args
    lk = k * tk - r
    lki = knee_int(lk)
    tag = f"K {k} t_knee {tk} R {r} T_TAIL {t_h}"
    if TG.solve(k, lki, round(t_h * 60) / 60) is None:
        return tag, "infeasible", []
    fails = []
    d = tempfile.mkdtemp(prefix="tailfw-")
    try:
        shutil.copytree(os.path.join(HERE, "stubs"), d, dirs_exist_ok=True)
        for f in ("battery.c", "battery.h", "power.c", "power.h"):
            shutil.copy(os.path.join(src, f), d)
        with contextlib.redirect_stdout(io.StringIO()):
            BC.write_tail(k, lk, t_h, os.path.join(d, "battery_tail.h"), f"tail_fw_grid: {tag}")
        tau, a, ts, curve, nodes = TG.table(k, lki, t_h)

        # --- 2. the lookup and the model, through battery.c's own functions ---
        b = run(CC + ["-I" + d, "-o", os.path.join(d, "tail_fw"), os.path.join(HERE, "tail_fw.c"), "-lm"])
        if b.returncode or b.stderr.strip():
            return tag, "fail", [f"tail_fw build: {b.stderr.strip()[:400]}"]
        starts = sorted({0, max(0, lki - k - 50), max(0, lki - 1), lki, min(989, lki + 1),
                         (lki + 989) // 2, 989})
        spans = {l0: s_knee(k, lki, l0) + ts + 3600 for l0 in starts}
        p = run([os.path.join(d, "tail_fw")] + [f"{l0}:{spans[l0]}" for l0 in starts])
        if p.returncode:
            return tag, "fail", [f"tail_fw exit {p.returncode}"]
        lines = {}
        trajs = {}
        for ln in p.stdout.splitlines():
            f = ln.split()
            if f[0] == "R":
                trajs[int(f[1])] = [int(x) for x in f[2:]]
            else:
                lines[f[0]] = [int(x) for x in f[1:]]
        n, t_fw, k_fw, lk_fw, last = lines["P"]
        if (n, t_fw, k_fw, lk_fw, last) != (len(nodes) - 1, ts, k, lki, 990 * 16):
            fails.append(f"header {lines['P']} != {(len(nodes) - 1, ts, k, lki, 990 * 16)}")
        want_x = [TG.m_fw(nodes, s) for s in range(ts + 3601)]
        x = lines["X"]
        if x != want_x:
            i = next(i for i, (u, v) in enumerate(zip(x, want_x)) if u != v) if len(x) == len(want_x) else -1
            fails.append(f"tail_x16 differs from the spec at s={i}")
        if x[ts] != 990 * 16 or x[-1] != 990 * 16:
            fails.append(f"past T_TAIL not exactly 990*16: {x[ts]} {x[-1]}")
        e = lines["E"]
        want_e = [TG.enter(nodes, l0) for l0 in range(lki, 990)]
        if e != want_e:
            fails.append("tail_entry_s differs from the spec")
        for l0, s in zip(range(lki, 990), e):
            if x[s] < l0 * 16 or (s and x[s - 1] >= l0 * 16):
                fails.append(f"entry at l0 {l0}: s {s}, x16 {x[s - 1] if s else '-'} / {x[s]}")
                break
        for l0 in starts:
            got = trajs.get(l0)
            if got != expected_traj(nodes, k, lki, l0, spans[l0]):
                fails.append(f"M from {l0} differs from the spec")
                continue
            if any(v2 < v1 for v1, v2 in zip(got, got[1:])):
                fails.append(f"M from {l0} falls")
            if max(got) > 990:
                fails.append(f"M from {l0} exceeds 990: {max(got)}")
            worst = max((got[s + 3600] - got[s] for s in range(len(got) - 3600)), default=0)
            if worst > k + 1:
                fails.append(f"M from {l0}: a 1 h rise of {worst} pm > K_CC + 1")
            sk = s_knee(k, lki, l0)
            t0 = TG.enter(nodes, l0) if l0 >= lki else 0
            dev = max((abs(got[sk + i] - curve(t0 + i)) for i in range(0, ts - t0 + 1)), default=0)
            if dev > 0.7:
                fails.append(f"M from {l0}: {dev:.3f} pm from the curve in the tail")
            if got[-1] != 990:
                fails.append(f"M from {l0} ends at {got[-1]}, not 990")

        # --- 3. OVERRUN through the whole charging path (sim.c) ---
        b = run(CC + ["-I" + d, "-o", os.path.join(d, "sim"), os.path.join(HERE, "sim.c"),
                      os.path.join(d, "battery.c"), os.path.join(d, "power.c"), "-lm"])
        if b.returncode or b.stderr.strip():
            return tag, "fail", fails + [f"sim build: {b.stderr.strip()[:400]}"]
        for l0 in sorted({max(0, lki - 100), lki, (lki + 900) // 2 if lki < 900 else lki, 960}):
            o = run([os.path.join(d, "sim"), "m_overrun", str(l0)])
            m = re.search(r"OVERRUN (\d+) (\d+)", o.stdout)
            if o.returncode or not m:
                fails.append(f"m_overrun {l0}: {o.stdout.strip().splitlines()[-3:]}")
                continue
            at, lost = int(m.group(1)), int(m.group(2))
            want = (ts - TG.enter(nodes, at) if at >= lki else s_knee(k, lki, at) + ts) + T_OVERRUN
            if abs(lost - want) > 1:
                fails.append(f"OVERRUN from {at}: at {lost} s, want {want} +-1")
        for s in (NAMED if named else []):
            o = run([os.path.join(d, "sim"), s])
            if o.returncode:
                fails.append(f"{s}: " + " / ".join(l.strip() for l in o.stdout.splitlines() if "FAIL" in l))
        return tag, "fail" if fails else "ok", fails
    finally:
        shutil.rmtree(d, ignore_errors=True)


def shipped_point(src):
    """The shipped header's (K, L_KNEE, T_TAIL) as a grid-style point."""
    h = open(os.path.join(src, "battery_tail.h")).read()
    g = lambda n: int(re.search(rf"#define {n}\s+(\d+)u", h).group(1))
    return g("BATT_K_CC_PM_PER_H"), 1.0, -(g("BATT_L_KNEE_PM") - g("BATT_K_CC_PM_PER_H")), g("BATT_T_TAIL_S") / 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.environ.get("BATTERY_SIM_SRC",
                    os.path.join(ROOT, "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro")))
    ap.add_argument("--point", nargs=4, type=float)
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.src, "battery_tail.h")):
        sys.exit(f"{a.src} has no battery_tail.h: not flash 2's battery.c")
    if a.point:
        pts = [(int(a.point[0]), a.point[1], int(a.point[2]), a.point[3])]
    else:
        pts = list(itertools.product(TG.K_RANGE, TG.TKNEE, TG.R_RANGE, TG.TTAIL))
    jobs = [(p, a.src, p == ROUND3) for p in pts]
    if not a.point:
        jobs.append((shipped_point(a.src), a.src, True))
    bad = infeasible = ok = 0
    with cf.ProcessPoolExecutor(max_workers=a.j) as ex:   # the checks are Python: one GIL each
        for tag, status, fails in ex.map(point, jobs):
            if status == "infeasible":
                infeasible += 1
                print(f"infeasible  {tag}")
            elif status == "ok":
                ok += 1
            else:
                bad += 1
                print(f"FAIL {tag}")
                for f in fails[:6]:
                    print(f"     {f}")
    print(f"{'FAIL' if bad else 'ok  '} tail_fw_grid: {ok} points ok, {bad} failed, {infeasible} infeasible "
          f"(of {len(jobs)}; round 3's set and the shipped header also ran {', '.join(NAMED)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
