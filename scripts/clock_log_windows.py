#!/usr/bin/env python3
"""Tile a clock log into non-overlapping N-sync windows and print the spread.

The Phase 0 gate of the cross-platform plan compares the clock BEFORE and
AFTER the platform-seam refactor on the same machine and board. One table
against another cannot tell a regression from an unlucky afternoon, so this
cuts each log into windows of N periodic syncs (50 by default, the size of the
3b takeover table) and prints how much the per-window statistics move. A
refactor passes when its windows sit inside the baseline's spread.

Reads the Rust daemon's log (%LOCALAPPDATA%\\ak820pro\\ak820-agent.log) and,
because the sync and bias lines are the same format, the retired Python
timekeeper's. It never touches the board.

A window never spans a break. A run of periodic syncs breaks on a process
start, any `board:` transition, a wake or enumerated sync, or a gap between
periodic syncs longer than --max-gap (the loop's slowest cadence is 300 s).
The tail of each run that does not fill a window is counted and dropped.
--across-breaks tiles straight through them instead, which is how the 3b
table was taken (its 50 syncs span two daemon restarts).

A window is N MEASURED syncs: periodic syncs that logged a `before`. The
ones that did not still fall inside it and are counted.

Per window:
  |before| median / p95 / worst  over the measured syncs. Median is the upper
                                 middle, sorted[n // 2], and p95 is
                                 sorted[int(0.95 n)]: the statistics the 3b
                                 table used, which this reproduces (50 syncs
                                 from 14:40:29, and the Python's 252)
  bias                           range of the `b` each `bias learned` line set
  learned / held                 `bias learned` and `bias hold` lines
  fail                           periodic syncs ending `[rc=N]`
  unmsr                          periodic syncs with no `before` and no rc: a
                                 `warning: residual ... exceeds 3U`, or the
                                 Python's whole-second `clock set to ...`
  warn                           `[warn]` lines and any `warning:` line
  slip                           whole-second slips: |before| within 1000 +- 60 ms
                                 with |after| under 60 ms (plans/BACKLOG.md). Counted,
                                 and kept OUT of the |before| statistics and the
                                 window size, so one slip can neither fail nor pass
                                 a window; --keep-slips puts them back, which is how
                                 the published 3b table was computed

Gate mode (Phase 0 of plans/AK820-AGENT-CROSSPLATFORM-PLAN.md, as rewritten after
the 2026-09-16 review): --gate P95_MAX WORST_MAX [BIAS_SPREAD_MAX] judges the first
3 windows against the baseline's maxima -- FAIL if any window has a failed,
unmeasured or warn sync, or if 2 or more of 3 exceed P95_MAX or WORST_MAX; PASS
if none does and bias spread stays within BIAS_SPREAD_MAX; EXTEND once to 6 if
exactly one exceeds, then FAIL on 2 or more of 6.
  media                          now-playing lines inside, and every state the
                                 window saw (the state at its start included);
                                 the gate wants this condition matched
"""
import argparse
import re
import statistics
import sys
from datetime import datetime

TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")
BEFORE = re.compile(r"before ([+-]?\d+(?:\.\d+)?) ms")
AFTER = re.compile(r"after ([+-]?\d+(?:\.\d+)?) ms")
SLIP_MS, SLIP_TOLERANCE_MS, SLIP_AFTER_MS = 1000.0, 60.0, 60.0
LEARNED = re.compile(r"b [+-]?\d+ -> ([+-]?\d+) ppm")
FAILED = re.compile(r"\[rc=-?\d+\]$")
MEDIA = re.compile(r"^(none|play|pause|stop)( |$)")
START = re.compile(r"^(ak820-agent \d|timekeeper start)")


def when(text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"not a time: {text!r} (use 'YYYY-MM-DD[ HH:MM[:SS]]')")


def rank(xs, q):
    """sorted(xs)[int(q * n)], clamped: the 3b table's median and p95."""
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)]


class Window:
    def __init__(self, media_state):
        self.first = self.last = None
        self.before = []
        self.biases = []
        self.learned = self.held = self.failed = self.unmeasured = self.warned = self.media_lines = 0
        self.slips = 0
        self.states = [media_state] if media_state else []

    def row(self):
        a = sorted(abs(x) for x in self.before)
        return dict(
            first=self.first, last=self.last, syncs=len(self.before),
            median=rank(a, 0.5), p95=rank(a, 0.95), worst=a[-1],
            bias_lo=min(self.biases) if self.biases else None,
            bias_hi=max(self.biases) if self.biases else None,
            learned=self.learned, held=self.held,
            failed=self.failed, unmeasured=self.unmeasured, warned=self.warned, slips=self.slips,
            media_lines=self.media_lines,
            states="/".join(dict.fromkeys(self.states)) or "?",
        )


def is_slip(msg, before):
    a = AFTER.search(msg)
    return (a is not None and abs(abs(before) - SLIP_MS) <= SLIP_TOLERANCE_MS
            and abs(float(a.group(1))) < SLIP_AFTER_MS)


def windows(path, size, since, until, max_gap, across_breaks, keep_slips=False):
    done, runs = [], []
    media_state = None
    cur = None          # the window being filled
    tail = None         # a window just filled: its last sync's bias line is still to come
    run = None          # [first sync, last sync, syncs] of the current run

    def brk(reason, t):
        nonlocal cur, tail, run
        if run:
            runs.append((run[0], run[1], run[2], len(cur.before) if cur else 0, f"{t} {reason}"))
        cur = tail = run = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            m = TS.match(raw.rstrip("\r\n"))
            if not m:
                continue
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            msg = m.group(2)
            media = MEDIA.match(msg)
            if media:
                media_state = media.group(1)
                if cur or tail:
                    (cur or tail).media_lines += 1
                    (cur or tail).states.append(media_state)
                continue
            if (since and t < since) or (until and t > until):
                if run:
                    brk("--since/--until", t)
                continue
            if not across_breaks:
                if START.match(msg):
                    brk(msg.split(";")[0], t)
                    continue
                if msg.startswith("board:"):
                    brk(msg[:60], t)
                    continue
                if msg.startswith(("sync (wake)", "sync (enumerated)")):
                    brk(msg[:17], t)
                    continue
            if msg.startswith("sync (periodic)"):
                if run and not across_breaks and (t - run[1]).total_seconds() > max_gap:
                    brk(f"gap of {t - run[1]}", t)
                if run is None:
                    run = [t, t, 0]
                tail = None
                if cur is None:
                    cur = Window(media_state)
                    cur.first = t
                b = BEFORE.search(msg)
                if "warning:" in msg:
                    cur.warned += 1
                if FAILED.search(msg):
                    cur.failed += 1
                elif not b:
                    cur.unmeasured += 1
                elif not keep_slips and is_slip(msg, float(b.group(1))):
                    cur.slips += 1
                else:
                    cur.before.append(float(b.group(1)))
                    run[2] += 1
                cur.last = run[1] = t
                if len(cur.before) == size:
                    done.append(cur)
                    tail, cur = cur, None
                continue
            owner = cur or tail
            if owner is None:
                continue
            if msg.startswith("bias learned"):
                owner.learned += 1
                b = LEARNED.search(msg)
                if b:
                    owner.biases.append(int(b.group(1)))
            elif msg.startswith("bias hold"):
                owner.held += 1
            elif msg.startswith("[warn]") or "warning:" in msg:
                owner.warned += 1
    brk("end of log", "")
    rows = [w.row() for w in done]
    return rows, runs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", help="ak820-agent.log (or ak820pro-timekeeper.log)")
    ap.add_argument("--since", type=when, help="ignore syncs before this local time")
    ap.add_argument("--until", type=when, help="ignore syncs after this local time")
    ap.add_argument("--window", type=int, default=50, help="periodic syncs per window (50)")
    ap.add_argument("--max-gap", type=float, default=330, help="seconds between periodic syncs that break a run (330)")
    ap.add_argument("--across-breaks", action="store_true", help="tile through restarts, board transitions and gaps")
    ap.add_argument("--keep-slips", action="store_true", help="count whole-second slips as ordinary syncs (the 3b table's way)")
    ap.add_argument("--gate", nargs="+", type=float, metavar="MAX",
                    help="P95_MAX WORST_MAX [BIAS_SPREAD_MAX]: the Phase 0 verdict against the baseline's maxima")
    args = ap.parse_args()

    rows, runs = windows(args.log, args.window, args.since, args.until, args.max_gap, args.across_breaks, args.keep_slips)

    print(f"{args.log}")
    if not args.across_breaks:
        dropped = 0
        print(f"runs of measured periodic syncs: {len(runs)}")
        for first, last, n, tail, why in runs:
            full = n // args.window
            dropped += n - full * args.window
            if full:
                print(f"  {first} -> {last} ({last - first}), {n} syncs, {full} window(s); ended: {why.strip()}")
        print(f"  (runs too short for one window omitted; {dropped} syncs dropped in all)")
    if not rows:
        sys.exit(f"no window of {args.window} periodic syncs in range")

    print()
    print(f"{'#':>3}  {'first sync':19}  {'last sync':19}  {'n':>3}  {'med':>5} {'p95':>5} {'worst':>6}"
          f"  {'bias ppm':>9} {'sprd':>4}  {'lrn':>3} {'hld':>3}  {'fail':>4} {'unmsr':>5} {'warn':>4} {'slip':>4}  media")
    for i, r in enumerate(rows, 1):
        bias = f"{r['bias_lo']:+d}..{r['bias_hi']:+d}" if r["bias_lo"] is not None else "-"
        spread = r["bias_hi"] - r["bias_lo"] if r["bias_lo"] is not None else 0
        print(f"{i:>3}  {r['first']!s:19}  {r['last']!s:19}  {r['syncs']:>3}  {r['median']:5.1f} {r['p95']:5.1f} {r['worst']:6.1f}"
              f"  {bias:>9} {spread:>4}  {r['learned']:>3} {r['held']:>3}  {r['failed']:>4} {r['unmeasured']:>5} {r['warned']:>4} {r['slips']:>4}"
              f"  {r['media_lines']} line(s), {r['states']}")

    print()
    print(f"spread across {len(rows)} window(s) of {args.window}:   min   median      max")
    cols = [
        ("|before| median, ms", lambda r: r["median"]),
        ("|before| p95, ms", lambda r: r["p95"]),
        ("|before| worst, ms", lambda r: r["worst"]),
        ("bias low, ppm", lambda r: r["bias_lo"]),
        ("bias high, ppm", lambda r: r["bias_hi"]),
        ("bias spread, ppm", lambda r: None if r["bias_lo"] is None else r["bias_hi"] - r["bias_lo"]),
        ("learned", lambda r: r["learned"]),
        ("held", lambda r: r["held"]),
        ("failed syncs", lambda r: r["failed"]),
        ("unmeasured syncs", lambda r: r["unmeasured"]),
        ("[warn] lines", lambda r: r["warned"]),
        ("whole-second slips", lambda r: r["slips"]),
        ("media lines", lambda r: r["media_lines"]),
    ]
    for name, get in cols:
        v = [x for x in map(get, rows) if x is not None]
        if v:
            print(f"  {name:32} {min(v):8.1f} {statistics.median(v):8.1f} {max(v):8.1f}")
    playing = sum(1 for r in rows if r["states"] != "none")
    print(f"  windows whose media state was anything but none: {playing} of {len(rows)}")

    if args.gate:
        print()
        print(gate_verdict(rows, *args.gate))


def gate_verdict(rows, p95_max, worst_max, spread_max=None):
    """The Phase 0 rule, mechanically. Returns the verdict text."""
    def over(r):
        return r["p95"] > p95_max or r["worst"] > worst_max

    def dirty(r):
        return r["failed"] or r["unmeasured"] or r["warned"]

    if len(rows) < 3:
        return f"GATE: INCOMPLETE -- {len(rows)} window(s); the rule needs 3"
    first = rows[:3]
    if any(dirty(r) for r in first):
        return "GATE: FAIL -- a failed, unmeasured or [warn] sync in the first 3 windows"
    n_over = sum(over(r) for r in first)
    spread_ok = spread_max is None or all(
        r["bias_lo"] is None or r["bias_hi"] - r["bias_lo"] <= spread_max for r in first)
    if n_over >= 2:
        return f"GATE: FAIL -- {n_over} of 3 windows exceed p95 {p95_max} or worst {worst_max}"
    if n_over == 0:
        return "GATE: PASS" if spread_ok else f"GATE: FAIL -- bias spread above {spread_max} ppm"
    if len(rows) < 6:
        return f"GATE: EXTEND -- 1 of 3 exceeds; run to 6 windows ({len(rows)} so far)"
    six = rows[:6]
    if any(dirty(r) for r in six):
        return "GATE: FAIL -- a failed, unmeasured or [warn] sync in the extension"
    n_over = sum(over(r) for r in six)
    if n_over >= 2:
        return f"GATE: FAIL -- {n_over} of 6 windows exceed p95 {p95_max} or worst {worst_max}"
    return "GATE: PASS (after one extension)" if spread_ok else f"GATE: FAIL -- bias spread above {spread_max} ppm"


if __name__ == "__main__":
    main()
