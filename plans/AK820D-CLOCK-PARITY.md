# ak820d clock parity — what the Rust port must not change

Status: **REFERENCE, written 2026-09-05** for phase 3 of
[AK820D-PLAN.md](AK820D-PLAN.md). Nothing here is a proposal; it is a
transcription of what `hostagent/ak820-timekeeper.py` does today and why, so a
rewrite can be checked against it rather than reasoned about.

## Why this document exists

Out of the box this board's clock drifted badly and could only ever be set to
within a few seconds. An always-on clock on a computer-attached device that is
visibly wrong is worse than no clock. The current behaviour — host syncs landing
within a few ms, a disciplined ILRC, corrections that slew instead of jumping —
is the result of a lot of measurement, and several of the constants below exist
because a *reasonable-looking* value failed in a way that took hours to see.

A rewrite that quietly changes a gate or a gain would regress this **invisibly,
on a timescale of hours**. Nothing in a unit test would catch it.

**The rule: port the constants and the gate conditions verbatim. If a value
looks arbitrary, it is not — find the comment before changing it.**

## Constants (`ak820-timekeeper.py`, verbatim)

| Name | Value | Meaning |
|---|---|---|
| `LOOP` | 15 s | main loop period |
| `SYNC_INTERVAL` | 300 s | periodic sync once the residual is small |
| `SYNC_INTERVAL_FAST` | 180 s | periodic sync while the last residual exceeded `FAST_ABOVE_MS` |
| `FAST_ABOVE_MS` | 60 ms | threshold that selects the fast interval |
| `SLEEP_GAP` | 60 s | loop gap above which the host is assumed to have slept |
| `BIAS_INTERVAL` | 900 s | continuity needed before a bias *seed* measurement |
| `LEARN_MIN_ELAPSED` | 90 s | minimum spacing between the two syncs a residual is measured across |
| `LEARN_MAX_BEFORE` | 400 ms | larger residuals are convergence or a step, not a rate error |
| `LEARN_GAIN` | 0.25 | low gain: each residual carries ILRC wander as noise |
| `LEARN_MAX_DP` | 6 ticks | "period unchanged" tolerance (~180 ppm) |
| `BIAS_LIMIT` | 600 ppm | matches the firmware's own sanity clamp |

## The four failures these encode

Each of these was a real regression. They are the reason the values are not
round numbers.

1. **`SYNC_INTERVAL_FAST` must leave the board's frequency window alone.**
   A slew writes the period register ~3 times (start, remainder, restore) and
   **every write restarts the frequency window.** At a 120 s interval against
   the firmware's then-128 s locked window the window *never completed*: the
   loop froze at a wrong period, the residual stayed large, so the interval
   stayed fast — a self-sustaining trap that held a **+300 ms plateau for six
   hours on 2026-09-04**. 180 s leaves ~150 clean seconds. **Any sync interval
   must be longer than the firmware's window plus a slew.**

2. **`LEARN_MIN_ELAPSED` was 240 s**, which is longer than the fast interval —
   so the learner could never fire while the residual was large, which is
   precisely the one time it was needed. Now 90 s.

3. **`LEARN_MAX_DP` 6 with `LEARN_GAIN` 0.25.** The ILRC wanders ±300 ppm on
   5-minute scales and the board's loop follows it a few ticks per window, so
   "period unchanged" never strictly happens. A wider gate plus low gain
   averages the wander out instead of waiting for a quiet moment that never
   comes.

4. **The frame-count bias is a SEED ONLY.** Measuring b from a 15-minute frame
   count against the wall clock produced **−369..+587 ppm** on a controller that
   the phase-0 test had pinned at **+78 ±3**. Each new value re-steered the
   clock, producing a 5-minute sawtooth of 150–330 ms (2026-09-03). It now only
   seeds a cache that has no bias; `learn_bias()` owns the value from then on.

## Sync triggers

Evaluated every `LOOP`, in this order — first match wins:

| Reason | Condition |
|---|---|
| `enumerated` | present now, not present last loop (a slider flip or replug reboots the board) |
| `wake` | `now - last_loop > SLEEP_GAP` (the host slept) |
| `periodic` | `now - last_sync >= interval` |

- `enumerated` sleeps **2 s** before syncing, to let the board settle after boot.
- After a successful sync,
  `interval = SYNC_INTERVAL_FAST if abs(before) > FAST_ABOVE_MS else SYNC_INTERVAL`.
- When the board is absent, both the bias-seed state and the learner state are
  **cleared** — an absence breaks the continuity both depend on.

## The learner

`learn_bias()` runs after every successful sync but **learns only when every one
of these holds**:

- `reason == "periodic"` — an enumeration or a wake breaks the baseline
- a previous sample exists, and both samples have a known nominal period
- `before is not None`
- `slewing` — i.e. `"(slewing)"` in the output **and no `"warning:"`**; a step
  means the clock was unset, far off, or just flashed, and is not a rate sample
- `abs(before) <= LEARN_MAX_BEFORE`
- `ref_state == 2` — the SOF reference is actually in use
- **settled**: `abs(prev_pnom - pnom) <= LEARN_MAX_DP`
- `elapsed >= LEARN_MIN_ELAPSED`

Then:

```
e_slow = -before * 1000.0 / elapsed          # ppm the board runs slow
b_new  = clamp(b - LEARN_GAIN * e_slow, ±BIAS_LIMIT)
```

written to `ak820ctl`'s cache (`~/.ak820ctl-cap`, `"proto lead_ms b_ppm"`) so
the *next* sync sends it. Every sync updates `state["learn"] = {t, pnom}`
regardless of whether it learned.

When the gates hold except `settled`, the Python agent **logs the hold**
(`bias hold: P … -> … (loop still moving); residual … not learned`). Keep that
line: it is how you tell "the learner is working and declining" from "the
learner is broken". It was observed doing exactly this at 11:54 on 2026-09-05.

## ⚠️ `HOME`, on Windows

`ak820ctl` keys its cache off `getenv("HOME")` (`ak820ctl.c:225`), falling back
to `"."`. Windows sets no `HOME`; MSYS2 sets a POSIX path a native binary cannot
resolve. The Python agent pins one and exports it. **A Rust port that owns the
cache in-process removes this failure mode entirely** — and should, rather than
reproducing the workaround. If it instead keeps shelling to `ak820ctl`, the
`HOME` export is mandatory: without it the two write different files and the
learned bias silently never arrives.

## How to verify the port — shadow mode

The two implementations **cannot both run against the board**: raw HID is
exclusive, and two things setting the clock would fight. So do not A/B live.

**Phase 3a — shadow.** `ak820d --shadow` runs the full loop, reads status,
evaluates every gate, computes `b_new` — and **writes nothing**, logging what it
would have done. Run it alongside the Python agent, which is doing the real
work, and diff the decisions: same reasons chosen, same gates passing, same
`e_slow`, same `b_new` within rounding. Any divergence is a port bug, found
before it can touch the clock.

**Phase 3b — take over.** Stop the Python task, run the Rust daemon for real,
and measure the board directly with the existing instrument:

```
venv-win\Scripts\python.exe hostagent\clock-phase.py
```

It reports phase error in ms. Baseline recorded 2026-09-05: **mean +15.9 ms,
median +15.8, spread 1.5** (and +17.0 on a later run), against a host itself
~20 ms behind NTP. Anything in that neighbourhood over a multi-hour run is
parity. A slow upward drift, or a residual that stays large while the interval
stays fast, is failure 1 above returning.

**Do not judge either implementation in under ~15 minutes.** Corrections slew,
and the learner needs at least two periodic syncs (`LEARN_MIN_ELAPSED` 90 s,
`SYNC_INTERVAL` 300 s) before it can move the bias at all.

## Keep the oracle

`hostagent/ak820-timekeeper.py` stays in the repo and stays installable on
Windows after the Rust daemon ships, until the daemon has run clean for a week.
It is the reference implementation, it is what macOS uses regardless, and it is
the only thing that can settle "did the port change this, or did the hardware?"
