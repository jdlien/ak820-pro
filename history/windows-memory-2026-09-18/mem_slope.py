"""Least-squares slope of the daemon's private bytes, with a 95% CI.

usage: python mem_slope.py CSV [skip_first_n]

Regresses private_bytes on elapsed hours and on smtc_polls (the daemon's own
count of 3 s media cycles, each of which is at least one HID exchange). Prints
the slope in bytes/hour and bytes/cycle with 95% confidence intervals, so a
flat result reads as a bound rather than as "no growth seen".
"""
import csv
import statistics
import sys


def fit(xs, ys):
    """slope, intercept, r2, and the standard error of the slope."""
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in resid)
    sst = sum((y - my) ** 2 for y in ys)
    se = (sse / (n - 2) / sxx) ** 0.5 if n > 2 else float("nan")
    return slope, intercept, (1 - sse / sst if sst else float("nan")), se


def main():
    path = sys.argv[1]
    skip = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if r.get("private_bytes")][skip:]
    if len(rows) < 3:
        sys.exit(f"{len(rows)} usable samples; need at least 3")
    hours = [float(r["elapsed_h"].replace(",", "")) for r in rows]
    priv = [float(r["private_bytes"]) for r in rows]
    ws = [float(r["working_set"]) for r in rows]
    polls = [float(r["smtc_polls"]) for r in rows]
    span_h = hours[-1] - hours[0]
    print(f"{len(rows)} samples, {rows[0]['at']} -> {rows[-1]['at']} ({span_h:.2f} h of a daemon "
          f"already up {hours[0]:.1f} h at the first sample)")
    print(f"media cycles over the window: {polls[-1] - polls[0]:,.0f}   "
          f"private bytes {priv[0]/1e6:.3f} -> {priv[-1]/1e6:.3f} MB   "
          f"working set {ws[0]/1e6:.3f} -> {ws[-1]/1e6:.3f} MB")
    # Writes, not cycles, are the denominator the macOS 48 B/write figure uses.
    # Idle cadence (media state none), from agent.rs:375 and media.rs:63-72:
    # one PLAYBACK write every 3 s poll, plus one CLEAR keepalive write every
    # 10th poll (30 s), so 1.1 writes per cycle; the clock and health opens add
    # about 72 writes an hour, which is under 0.5% and is ignored here.
    writes = [p * 1.1 for p in polls]
    for label, xs, unit, scale in (("hour", hours, "B/h", 1.0), ("media cycle", polls, "B/cycle", 1.0),
                                   ("HID write", writes, "B/write", 1.0)):
        s, _, r2, se = fit(xs, priv)
        lo, hi = s - 1.96 * se, s + 1.96 * se
        print(f"  private bytes per {label:11}: {s*scale:+10.3f} {unit:8} "
              f"95% CI {lo*scale:+.3f} .. {hi*scale:+.3f}   r2 {r2:.3f}")
    dc, dw = polls[-1] - polls[0], writes[-1] - writes[0]
    print(f"  what a leak would have added over this window: 56 B/cycle -> {56*dc/1e6:.3f} MB, "
          f"48 B/write (the macOS NSValue) -> {48*dw/1e6:.3f} MB; observed {(priv[-1]-priv[0])/1e6:+.3f} MB")


if __name__ == "__main__":
    main()
