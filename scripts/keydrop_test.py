#!/usr/bin/env python3
"""Count dropped keystrokes end to end with the key presser (--presser A|B:
scripts/presser.py, the PC817C rig; docs/test-bench.md, "The key presser") or
the old wake rig (relay 1 across the F19 key: history/wake-rig-2026-10-16/),
and the Mac's listener (AK820 F19 Listener, writing
~/Library/Logs/ak820pro/f19.log).

    venv/bin/python scripts/keydrop_test.py [--presser A|B] [--n 200] [--dwell 40] [--gap 60] [--trial-csv <drain.csv>] [--out <csv>]

Three counts for one batch of n presses:
- sent: the closures, stamped at the presser's contact (its own clock, put on
  the Mac's by a round-trip sync before and after, both reported) or, with the
  relay, on the Mac as each command returns;
- the board: raw_edges (before debounce; 2 per press) and key_presses (after);
- the Mac: F19 downs and ups in the listener's log.
And each press's latency, the closure to the Mac's key-down event: the 5 ms
debounce, the firmware, the CH582F, the BT link and macOS together (plus the
relay's armature, with the relay). The presser's batch runs on its board, so
the dwell and gap are exact; the relay's are timed here.

⚠️ key_presses counts every key: keep hands off the keyboard while it runs.
⚠️ The listener sees no keys while the Mac is locked (the lock screen's
secure input), and on this Mac the displays sleeping locks it: so it refuses
to start locked, holds the displays awake for the run (`caffeinate -d`), and
flags the result if the Mac locked anyway.
With --trial-csv it waits for the gap after a running bench_trial's read
(raw HID is exclusive on macOS) and must finish before the next.
"""
import argparse
import csv
import os
import statistics as st
import subprocess
import sys
import time

import presser

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "hostagent"))
import ak820health as health  # noqa: E402

LOG = os.path.expanduser("~/Library/Logs/ak820pro/f19.log")


def mac_locked():
    """The console session's CGSSessionScreenIsLocked, present (true) only
    while the lock screen is up."""
    out = subprocess.run("ioreg -n Root -d1 -a | plutil -extract IOConsoleUsers xml1 -o - -",
                         shell=True, capture_output=True, text=True).stdout
    i = out.find("CGSSessionScreenIsLocked")
    return i >= 0 and out[i:i + 80].find("<true/>") >= 0


def counts():
    return health.read_stalls()["key_presses"], health.read_rows()["raw_edges"]


def listener_events(offset):
    with open(LOG) as f:
        f.seek(offset)
        ev = []
        for line in f:
            p = line.split()
            if len(p) >= 2 and p[1] in ("down", "up"):
                ev.append((float(p[0]), p[1]))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--dwell", type=float, default=40, help="ms the relay is closed")
    ap.add_argument("--gap", type=float, default=60, help="ms open between presses")
    ap.add_argument("--trial-csv", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--presser", default=None, choices=["A", "B", "a", "b"],
                    help="the key presser's channel; without it, relay 1 (the old rig)")
    a = ap.parse_args()
    run_s = a.n * (a.dwell + a.gap) / 1000 + 5
    if a.trial_csv:
        with open(a.trial_csv, newline="") as f:
            last = float(list(csv.DictReader(f))[-1]["epoch"])
        start = last + 20
        if time.time() > last + 270 - run_s:
            start = last + 320
        if time.time() < start:
            print(f"waiting {start - time.time():.0f} s for the gap after the trial's read", flush=True)
            time.sleep(start - time.time())
    if not os.popen("pgrep -x ak820-f19-listener").read().strip():
        sys.exit("the listener is not running: open -a \"$HOME/Applications/AK820 F19 Listener.app\"")
    if mac_locked():
        sys.exit("the Mac is locked: the listener sees no keys at the lock screen; unlock it first")
    awake = subprocess.Popen(["caffeinate", "-d", "-w", str(os.getpid())])   # no display sleep, so no lock

    try:
        key = presser.open_key(a.presser)
    except presser.PresserError as e:
        sys.exit(str(e))
    offset = os.path.getsize(LOG)
    kp0, re0 = counts()
    presses, releases, dwells = [], [], []
    with key:
        for t_down, t_up, dwell_ms in key.batch(a.dwell, a.gap, a.n):
            presses.append(t_down)
            releases.append(t_up)
            dwells.append(dwell_ms)
        key.finish()
        clock_note = key.clock_note()
    time.sleep(1.5)   # the last key's trip to the Mac
    locked_after = mac_locked()
    awake.terminate()
    kp1, re1 = counts()
    ev = listener_events(offset)
    downs = [t for t, k in ev if k == "down"]
    ups = [t for t, k in ev if k == "up"]

    # Latency only where it is unambiguous: every press arrived, so the k-th
    # key-down is the k-th press (the link delivers in order), at any speed.
    # Otherwise counts only: matching each arrival to "the latest press before
    # it" pinned trips on the wrong press once a trip outlasted the press
    # period (the first runs' "missed 1" and "missed 21", 10-16).
    lat = []
    if len(downs) == a.n:
        lat = [(t - p) * 1000 for t, p in zip(downs, presses)]
    missed = a.n - len(downs)
    raw, kp = (re1 - re0) & 0xFFFF, (kp1 - kp0) & 0xFFFF
    q = sorted(lat)
    pct = (lambda p: q[min(len(q) - 1, int(p * len(q)))]) if q else (lambda p: float("nan"))
    print(f"{a.n} presses by {key.name}, dwell {a.dwell:g} ms (actual mean {st.mean(dwells):.2f}), gap {a.gap:g} ms "
          f"({a.n / (presses[-1] - presses[0] + (a.dwell + a.gap) / 1000):.1f}/s)")
    print(f"  the board: raw edges {raw}/{2 * a.n}, key presses {kp}/{a.n}")
    print(f"  the Mac:   F19 down {len(downs)}/{a.n}, up {len(ups)}/{a.n}")
    if locked_after:
        print("  ⚠️ the Mac was locked at the end: keys at the lock screen went unlogged, so the Mac's count is not valid")
    if q:
        print(f"  latency, {'the closure' if a.presser else 'the relay command'} to the Mac's key-down: "
              f"min {q[0]:.1f}  median {st.median(q):.1f}  p95 {pct(0.95):.1f}  max {q[-1]:.1f} ms")
    print(f"  ({clock_note})")
    if a.out:
        new = not os.path.exists(a.out)
        with open(a.out, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "n", "dwell_ms", "gap_ms", "raw_edges", "key_presses", "mac_down", "mac_up",
                            "missed", "lat_min", "lat_median", "lat_p95", "lat_max", "key", "clock"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), a.n, a.dwell, a.gap, raw, kp, len(downs), len(ups),
                        missed] + ([f"{q[0]:.1f}", f"{st.median(q):.1f}", f"{pct(0.95):.1f}", f"{q[-1]:.1f}"]
                                        if q else ["", "", "", ""]) + [key.name, clock_note])


if __name__ == "__main__":
    main()
