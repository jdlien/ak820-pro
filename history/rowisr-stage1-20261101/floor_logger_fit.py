#!/usr/bin/env python3
"""The logger pass's slope: floor-logger.log's levels (every LED at N ticks,
one colour, 20 s each) paired with power.csv's rows (field 1 the time, 6
the mA), the first 5 s of each level dropped for the settle; the mean mA
per level, the dark baseline (N=0 of the same colour's run) subtracted,
and a least-squares slope in mA per tick (every LED) with its intercept
(codex: the mux drive current is independent of the width)."""
import re, sys, datetime as dt
ROOT = "/Users/jdlien/code/ak820-pro"
LOG = ROOT + "/history/rowisr-stage1-20261101/floor-logger.log"
CSV = ROOT + "/history/power-bench-2026-10-15/power.csv"
day = dt.date.today()
levels = []   # (t, colour, N)
colour = None
seen = set()
for line in open(LOG):
    m = re.match(r"\[(\d\d):(\d\d):(\d\d)\] (.*)", line)
    if not m: continue
    t = dt.datetime.combine(day, dt.time(int(m[1]), int(m[2]), int(m[3])))
    msg = m[4]
    mc = re.match(r"(red|green|blue): every LED", msg)
    if mc: colour = mc[1]; continue
    mn = re.match(r"N=(\d+)$", msg)
    if mn and colour and (t, colour, int(mn[1])) not in seen:
        seen.add((t, colour, int(mn[1]))); levels.append((t, colour, int(mn[1])))
    if msg.startswith("dark") and colour and levels and levels[-1][1] == colour and levels[-1][2] != -1:
        levels.append((t, colour, -1))   # the run's end
rows = []
for line in open(CSV):
    f = line.rstrip("\n").split(",")
    try:
        ts = dt.datetime.strptime(f[0], "%Y-%m-%d %H:%M:%S"); ma = float(f[5])
    except (ValueError, IndexError): continue
    if ts.date() == day and ts.hour >= 15: rows.append((ts, ma))
out = {}
for i, (t, c, n) in enumerate(levels):
    if n < 0: continue
    t_end = levels[i + 1][0] if i + 1 < len(levels) else t + dt.timedelta(seconds=20)
    vals = [ma for ts, ma in rows if t + dt.timedelta(seconds=5) <= ts < t_end]
    if vals: out.setdefault(c, {})[n] = (sum(vals) / len(vals), len(vals))
for c in ("red", "green", "blue"):
    if c not in out: continue
    d = out[c]; base = d.get(0, (None, 0))[0]
    print(f"{c}: " + ", ".join(f"N={n}: {v:.3f} mA ({k} rows)" for n, (v, k) in sorted(d.items())))
    pts = [(n, v - base) for n, (v, k) in d.items() if n > 0 and base is not None]
    if len(pts) >= 2:
        sx = sum(n for n, _ in pts); sy = sum(y for _, y in pts); sxx = sum(n * n for n, _ in pts); sxy = sum(n * y for n, y in pts); k = len(pts)
        slope = (k * sxy - sx * sy) / (k * sxx - sx * sx); icpt = (sy - slope * sx) / k
        print(f"  above dark: " + ", ".join(f"{n}: {y:+.3f}" for n, y in sorted(pts)) + f"; slope {slope * 1000:.1f} uA/tick (every LED), intercept {icpt * 1000:+.0f} uA")
