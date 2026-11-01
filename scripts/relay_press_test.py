#!/usr/bin/env python3
"""Press a key through the key presser (--presser A|B: scripts/presser.py, the
PC817C rig; docs/test-bench.md, "The key presser") or the old wake rig's relay
(relay 1 of the bench's USB relay, wired across one key's switch:
plans/POWER-CAMPAIGN-PLAN.md, R7) and count what the board registered, to
find how short and how fast a press can be.

    venv/bin/python scripts/relay_press_test.py [--presser A|B] [--out <csv>] [--n 10] [--trial-csv <drain.csv>]

Each batch is n presses of a set dwell (closed) and gap (open), timed on the
presser's board (exact, the actual dwell reported) or, with the relay, by the
Mac. Before and after it, the board's health counters:
- raw_edges: raw matrix transitions BEFORE debounce (a clean press and
  release are two); fewer than 2n means the relay's contact never closed;
- key_presses: presses AFTER debounce (sym_defer_pk, 5 ms per key); fewer than
  the presses whose contact closed means debounce discarded them.
Keep n even if the key toggles something (play/pause ends where it started).

The relay is a separate USB device from the keyboard (16c0:05df), driven here
in-process: a 9-byte feature report, 0xFF on / 0xFD off, relay 1 only, so
relay 2 (the keyboard's 5 V) is never touched; checked before and after. The
board's counters are raw HID, which a running bench_trial owns on macOS:
with --trial-csv the test waits until 20 s after the trial's latest read and
must finish 30 s before the next.
"""
import argparse
import csv
import os
import sys
import time

import presser

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "hostagent"))
import ak820health as health  # noqa: E402

# (dwell ms, gap ms): realistic down to below the relay's and debounce's limits,
# then the gap shrunk at a dwell that registers.
BATCHES = [(100, 100), (60, 60), (40, 40), (25, 40), (15, 40), (10, 40), (7, 40),
           (5, 40), (3, 40), (25, 25), (25, 15), (25, 10), (15, 10)]


def counts():
    s = health.read_stalls()
    r = health.read_rows()
    return s["key_presses"], r["raw_edges"]


def wait_for_gap(trial_csv, need_s):
    with open(trial_csv, newline="") as f:
        last = float(list(csv.DictReader(f))[-1]["epoch"])
    start, deadline = last + 20, last + 300 - 30
    now = time.time()
    if now > deadline - need_s:
        start, deadline = last + 300 + 20, last + 600 - 30
    if start > now:
        print(f"waiting {start - now:.0f} s for the gap after the trial's read", flush=True)
        time.sleep(start - now)
    return deadline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--trial-csv", default=None)
    ap.add_argument("--presser", default=None, choices=["A", "B", "a", "b"],
                    help="the key presser's channel; without it, relay 1 (the old rig)")
    a = ap.parse_args()
    need = sum(a.n * (d + g) for d, g in BATCHES) / 1000 + len(BATCHES) * 1.5
    deadline = wait_for_gap(a.trial_csv, need) if a.trial_csv else None

    try:
        key = presser.open_key(a.presser)
    except presser.PresserError as e:
        sys.exit(str(e))
    rows = []
    with key:
        # The rig first: one slow press must reach the matrix, or a broken
        # switch reads as "the presser is too slow" (the first sweep, 16:10 10-16).
        kp0, re0 = counts()
        key.press(300)
        time.sleep(0.3)
        kp1, re1 = counts()
        if (re1 - re0) & 0xFFFF < 2:
            sys.exit(f"the rig is not pressing: one 300 ms press gave raw edges {(re1 - re0) & 0xFFFF}, "
                     f"presses {(kp1 - kp0) & 0xFFFF}; check the switch's wiring")
        print(f"rig check: one 300 ms press gave raw edges {(re1 - re0) & 0xFFFF}, "
              f"presses {(kp1 - kp0) & 0xFFFF}", flush=True)
        key.press(300)   # the check press toggled the key once; undo it
        time.sleep(0.3)
        kp0, re0 = counts()
        for dwell, gap in BATCHES:
            if deadline and time.time() > deadline - (a.n * (dwell + gap) / 1000 + 2):
                print("stopping: the trial's next read is due", flush=True)
                break
            on_ms = [r[2] for r in key.batch(dwell, gap, a.n)]
            time.sleep(0.15)   # the last release's debounce
            kp1, re1 = counts()
            row = {"dwell_ms": dwell, "gap_ms": gap, "n": a.n,
                   "on_ms_mean": round(sum(on_ms) / len(on_ms), 2),
                   "raw_edges": (re1 - re0) & 0xFFFF, "key_presses": (kp1 - kp0) & 0xFFFF}
            rows.append(row)
            print(f"dwell {dwell:3d} ms gap {gap:3d} ms (on {row['on_ms_mean']:6.2f} ms): "
                  f"raw edges {row['raw_edges']:3d}/{2 * a.n}, presses {row['key_presses']:3d}/{a.n}",
                  flush=True)
            kp0, re0 = kp1, re1
        key.finish()
        print(f"({key.name}: {key.clock_note()})", flush=True)
    if a.out and rows:
        new = not os.path.exists(a.out)
        with open(a.out, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["time"] + list(rows[0]))
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **r})


if __name__ == "__main__":
    main()
