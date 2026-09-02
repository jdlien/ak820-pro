# Phase 3 — PCF phase-correct write + boot acquisition (2026-09-01)

## What shipped

- **Six-state STOP writer** in `rtc_fast_task()` (PLAN.md §3.5): STOP_READ →
  STOP_WRITE → TIME_WRITE → RELEASE_READ → RELEASE_WRITE → VERIFY, one I2C
  transaction per main-loop pass, only with the LCD DMA idle, plus
  RECOVER (STOP can never be left asserted; "PCF possibly stopped" health
  flag while unrecovered) and a **BRACKET** state added after the first
  hardware round (below).
- **Boot acquisition** (§3.6, coarse step only): after the splash, one
  1-byte PCF seconds read every 8 main-loop passes until the value
  changes; edge = midpoint of the bracketing reads; full 7-byte read plus a
  seconds re-read for rollover safety; `rtc_set_time_ms(pcf, elapsed,
  FORCE_STEP|SKIP_PCF)`. Cancelled by any host sync. Aborts after 1.5 s.
- `display_splash_done()`; status page 4 (`HC_RTC` page 4): PCF state,
  STOP asserted, release error, runs, restarts, recovery flag, acquisition
  state/uncertainty/step, boundary error, adapted release lead.

## Hardware round 1 — the off-by-one

First boot after the flash: acquisition DONE, stepped the board by 295 ms
(the whole-second seed's random phase), ±14 ms; the post-flash host sync
found the board at **+3.4 ms** — the PCF phase left by Phase 1/2's plain
writes. Four STOP runs: release error 4–7 ms, no restarts.

Slider-flip reboot (no host sync; agent paused): acquisition stepped +348
→ board at **+877 ms**. Diagnosis: `ps_plan` wrote `S = cur+1` and aimed
the first increment at boundary(cur+1), where the register then reads
cur+2 — **one second ahead**. A direct test (plain write at four random
phases, bracket the next increment: 981/980/979/982 ms after the previous
board boundary regardless of write time) confirmed the clone does NOT
reset its prescaler on a plain time write, so the +3.4 ms first boot was
luck of the old phase, and the STOP path is the only phase-setting path.

## Hardware round 2 — self-measuring

Fix: `S = cur`. Plus **BRACKET**: after VERIFY, 1-byte reads each pass
from 60 ms before to 400 ms after the aimed boundary; the increment's
midpoint minus the aimed boundary is the real error, half of it feeds the
release lead (`pcf_d_first_ms`, clamped 300–800). Measured on four
consecutive syncs:

| run | release err | **boundary err** | lead after |
|---|---|---|---|
| 2 | +5 | **+8 ms** | 494 |
| 3 | +4 | **+5 ms** | 496 |
| 4 | +7 | **+6 ms** | 499 |
| 5 | +7 | **−6 ms** | 496 |

So the PCF's real increment now lands within ±8 ms of the true boundary,
and the constant that T0.5 measured (490 ms) was right to ~6 ms; the
unexplained ~120 ms in round 1 is not reproduced and is attributed to the
now-fixed labeling plus acquisition timing on a 7000 ppm-slow post-flash
clock.

## Slider-flip reboot with no host sync

15:28:46 board gone (BT → cable) → 15:28:47 back. Timekeeper paused. Samples
every 0.5 s: −665.6 ms (whole-second seed, random phase) → acquisition
stepped **+688 ms** (±14) → **+13.3 ms** at 15:28:49, then −13 ms/s — the
fresh 33600 seed against the now-warm ILRC (33212), because the persist
had not fired (see below). Extrapolated to the acquisition instant the
phase was ≈ +15–20 ms: **inside the ≤ 20 ms exit criterion**, with no host
involvement.

## Persist bug found on the way

`rtc_ref_task()` only persisted inside the `delta != 0` branch, so a loop
that converged cleanly (33212 held for two 128-s windows) never stored its
period and the next reboot re-seeded at 33600 — the ~12 ms/s drift JD saw
"over a minute or two" after the flip. Fixed: persist after every window
evaluation (≥ 10 min uptime, ≥ 64 ticks from stored).

## Health

`stale_count` 0, `i2c_fail` 0, no restarts, STOP never left asserted;
`deferred_passes` counts the passes the machine skipped for a busy blit.
