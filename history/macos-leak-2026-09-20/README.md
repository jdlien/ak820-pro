# The macOS daemon's footprint after the autorelease-pool fix (2026-09-20)

**The 24 h → 48 h window is flat to the kilobyte: +0 KB over 288 consecutive
samples, 23.93 h and ~30,400 HID writes.** Before the fix the same daemon grew
about 1.9 MB/day.

The mechanism is what establishes the fix, not this measurement: IOKit's
`-[IOHIDDeviceClass setReport:…]` boxes the callback context in an `NSValue`
via `+[NSValue valueWithPointer:]`, which is autoreleased into the **calling**
thread's pool. A Rust thread has none, so every async write left a live 48-byte
`NSConcreteValue` for the life of the process — 25,788 of them after 26,000
exchanges, named by `malloc_history`. `cf::Pool` in `write_report` drains them.
This window confirms that holds in production; it does not carry the argument.

## The numbers

`ak820-agent 0.1.1 (v0.1.1-52-g4e9d5cd)`, Developer ID signed, owning the clock.
One pid (3863) for the whole 48 h, so no restart is hidden in the series.

| window | samples | footprint | per write | r² |
|---|---|---|---|---|
| 0–48 h | 576 | 2,849 → 3,249 KB (+400) | +1.334 B | 0.251 |
| **24–48 h** | **288** | **3,249 → 3,249 KB (+0)** | **+0.000 B** | **0.000** |

At the pre-fix 48 B/write, the 24–48 h window would have added **1.390 MB**.
Observed: **0.000 MB**.

⚠️ **Why the second day is the one that counts.** All the growth is in day one
(+400 KB) and then it stops completely. That is warm-up, and a 0–48 h slope of
+1.33 B/write is that warm-up smeared over the whole window rather than a rate.
Quoting it as a per-write cost is precisely the error that made this bug take a
day to find: an earlier draft of the plan reported a "26 B/cycle floor" that was
one-time warm-up divided by a cycle count, and it did not exist.

## The board was really exchanging

A flat footprint proves nothing if the daemon was idle or the keyboard
unplugged. In the 24–48 h half: **285 clock syncs** against ~287 expected at one
per 300 s, and every sync is a successful board transaction. 27,602 media polls.
No `board:` transition in the log for the whole window.

## What this does not say

- **One machine, one workload.** Elysium, Apple silicon, macOS 27.0, mostly
  idle media with JD present. It does not cover sleep/wake cycles, a
  board that goes absent and returns, or a machine that is busy for days.
- **48 h, not weeks.** A leak slower than ~0.2 KB/h would hide inside the 16 KB
  page quantisation over this window.
- **`phys_footprint` measures impact, not live objects.** It cannot exclude a
  leak that is reachable, nor every kernel allocation made on our behalf. The
  direct evidence for the mechanism is `malloc_history` and the heap census, not
  this series.
- **The fix is scoped to `write_report` only.** Open, close and the registry
  enumeration are deliberately not pooled: they measured exactly zero growth
  over 40,000 cycles, and draining a pool around a call that does not need one
  risks releasing something IOKit expects to outlive it.

## Reproducing

`mem-sample.sh` is the sampler as it ran, detached, every 5 min for 48 h. It
records pid and process start time in every row — ⚠️ **a slope drawn across a
restart is meaningless**, and that is the failure this column exists to catch.

Companion: [`../windows-memory-2026-09-18/`](../windows-memory-2026-09-18/),
where Windows is bounded at +0.70 B/write over 4.01 h.
Full investigation: [`../../plans/AK820-AGENT-MACOS-LEAK-PLAN.md`](../../plans/AK820-AGENT-MACOS-LEAK-PLAN.md).
