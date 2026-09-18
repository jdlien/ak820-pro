# The Windows daemon's memory is flat (2026-09-18)

The macOS leak of `plans/AK820-AGENT-MACOS-LEAK-PLAN.md` (~1.9 MB/day, an
autoreleased `NSValue` per HID write inside IOKit, fixed in `bf7b7f3`) raised
the obvious question for the other platform. This is gremlin's answer, measured
on the live daemon at `e07fdfa` — the Phase 0 build, running since
2026-09-17 10:19:13 and owning now-playing and the clock.

**The mechanism, not this measurement, is what makes the leak macOS-specific:**
the leaked object is an Objective-C `NSValue` allocated inside IOKit's HID
implementation, and the Windows transport has no counterpart. This agrees with
that; it does not carry it.

## Method

`mem_sample.ps1` samples every 5 minutes for 4 hours, appending CSV. Each row
carries the process's private bytes, working set, peak working set, handles,
threads and CPU seconds, **and the daemon's own `smtc_polls` and `clock_syncs`**,
so the slope has a denominator taken from the workload rather than assumed.

The first sample is **26.7 h after the process started**, so no warm-up is
inside the window. That matters: the macOS investigation was misled for a day
by a first-day figure that mixed ramp with leak, and by a slope quoted as a
per-operation cost.

Writes, not polls, are the denominator, because the leaked object was one per
write. Idle cadence, from `agent.rs:375` and `media.rs:63-72`: one `PLAYBACK`
write per 3 s poll, plus one `CLEAR` keepalive write every 10th poll, so **1.1
writes per cycle**; the clock and health opens add ~72 writes an hour, under
0.5%, and are ignored.

`mem_slope.py` fits the least-squares slope with a 95% CI. Re-run from this
folder, it reproduces the numbers below.

## Result

49 samples, 2026-09-18 13:02:13 → 17:02:36 (4.01 h), pid 37728 throughout,
4,804 media cycles (~5,284 writes). Private bytes 2,879,488 → 2,883,584: net
**+4,096 B, one page**.

| | slope | 95% CI | r² |
|---|---|---|---|
| per hour | −1,537 B/h | −3,999 .. **+925** | 0.031 |
| per media cycle | −1.28 B | −3.34 .. **+0.77** | 0.031 |
| per HID write | −1.17 B | −3.03 .. **+0.70** | 0.031 |

**The bound is the result.** The upper CI is +0.70 B/write, or 0.022 MB/day.
The macOS leak measured 48 B/write, so this excludes it by about **69×**. Over
this window a 48 B/write leak would have added 0.254 MB; the observed change
was +0.004 MB. r² of 0.031 says time explains ~3% of the variation: the line is
noise, not a trend.

What makes a flat line credible here rather than merely small:

- Private bytes took **five distinct values, every one a multiple of 4,096**
  (2,822,144 ×1; 2,846,720 ×1; 2,879,488 ×16; 2,883,584 ×22; 2,887,680 ×9).
  The counter quantises to pages and the whole 4-hour range is 64 KB.
- It went **down** twice, at 14:52 and 16:52. A monotonic leak cannot.
- Handles 157 and threads 6 in 48 of 49 samples (155/5 in the one that caught a
  teardown), so no handle or thread leak either.
- Working set 7.356 → 7.434 MB, range 7.344–7.438 MB: paging drift.
- CPU 79.9 → 92.2 s, 12.3 s over 4.01 h = **0.085% of one core**.

## What this does not say

- 4.01 h, not 24. With 4 KB quantisation and a 64 KB noise band a longer window
  would tighten the CI, but the question asked — is the macOS rate present
  here — is already answered 69× over.
- The per-write figure rests on the 1.1 writes/cycle model above. If the true
  rate were double, the bound halves to +0.35 B/write and the conclusion
  survives; the error moves it the safe way.
- **Idle only.** Media state was `none` throughout, so text writes were `CLEAR`
  keepalives. A window with real titles sends two `SET_LINE` writes per change.
  That is the same write path with a different payload and count, so it would
  tighten the denominator rather than test another mechanism. Not measured.
- No clean-process baseline was taken, deliberately. Restarting for one would
  have thrown away the 26.7 h head start that makes this window post-warm-up.
