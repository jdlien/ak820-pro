# The clock: two RTCs, sub-second sync, the divider trim, and the timekeeper

Code: `rtc/rtc.c`, `rtc/rtc_lld` additions via the `rtc_lld` ChibiOS patch.

> **Sub-second clock sync is IMPLEMENTED** (2026-09-01, phases 0-3: firmware
> commits 6b05be68e3, cc786793ec, f7d3d97e11). Design:
> Measured results and hardware facts: `history/clock-sync/phase-0-facts.md`,
> `phase-1-2-results.md`, `phase-3-results.md`. Read those before changing
> anything under `rtc/`. (The design plan and its five review rounds were
> retired once implemented; `git log` has them if the reasoning is ever needed.)

## Architecture

Two physical clocks. A battery-backed **PCF8563** (CHMC D8563F clone) and
the **SN32 internal RTC** — the live 1 Hz clock the display reads, running
off the **ILRC** (untrimmed on-chip RC, nominally 32 kHz, ~34.3 kHz on this
unit, temperature-dependent). A reference state machine picks what
disciplines the SN32: **`SOF`** (USB host attached — frame-number frequency
discipline + host time sync; the PCF becomes write-only), **`PCF_LEGACY`**
(no host — the original snap/trim loop against the PCF), **`NONE`**.

## Sub-second sync (the current behaviour, host attached)

- **`RTC_SET_TIME_MS` (0x03)** — "at receipt, true time was t + ms". Sets
  the software seconds and restarts the prescaler with a first period sized
  to land the next second-edge on the boundary; the tick ISR restores the
  nominal period. Full validation before any write. Measured: ten
  consecutive syncs land at **−0.2..−3.1 ms**. Legacy `0x01` is unchanged
  (whole-second only).
- **Reload ownership**: `rtc.c` owns the nominal period; every steady-state
  `SECCNTV` write happens **in the tick ISR at the match**, so a trim no
  longer resets `SECCNT` mid-second (it used to discard the elapsed
  fraction — mean 0.5 s per trim; now < 1.6 ms).
- **SOF frequency loop**: per RTC second the ISR accumulates the USB frame
  delta (`FRMNO`); every 32 accepted samples (128 once locked) housekeeping
  proposes a period with half-step damping, corrected by the host-measured
  SOF bias (**+78 ppm ± 3 on this Mac's internal controller** — the bias is
  load-bearing, ~47 ms per 10 min uncorrected; cached per controller ID in
  `~/.ak820ctl-cap`). Took a fresh-seed clock from 7000 ppm to −66 ppm in
  18 min.
- **Slew**: on a synced clock, |offset| ≤ 500 ms is slewed at 20 ms/s via
  latency-compensated transient periods — no visible jump (a 204 ms
  correction slewed over N=11 seconds in testing).
- **PCF phase write (STOP bit)**: a six-state writer in `rtc_fast_task()`
  (one I2C transaction per main-loop pass, only with the LCD DMA idle;
  STOP can never be left asserted — RECOVER path + health flag). It
  self-measures: a BRACKET state hunts the first increment and feeds half
  the error back into the release lead. Measured boundary error **±8 ms**.
  - ⚠️ **The clone does NOT reset its prescaler on a plain time write**
    (measured at four random phases) — the STOP path is the *only* way to
    set PCF phase. And the release-to-first-increment delay is **≈0.49 s on
    this clone**, not the datasheet's 0.5078.
  - ⚠️ Off-by-one trap: the seconds register to write during STOP is
    `cur`, not `cur+1` — aiming at boundary(cur+1) left the PCF a full
    second ahead (hardware round 1).
- **Boot acquisition**: after the splash, a coarse PCF edge-hunt (1-byte
  read every 8 passes, ≤1.5 s, cancelled by any host sync) phase-steps the
  clock. A no-host slider-flip reboot came up at **+13 ms**.
- **Display edge repaint**: one extra gated display pass on the RTC edge,
  so the digits change within a main-loop pass of the tick.

The old "~0.5 s seed lag" and "post-sync phase differs per sync" notes are
**fixed by the above** (both were uncontrolled SN32/PCF prescaler phase) —
do not re-derive them from stale docs.

## Legacy discipline (`PCF_LEGACY` — standalone, no USB host)

The original loop still runs when no host is attached: phase snap at
`RTC_DRIFT_THRESHOLD_S` (2 s) drift, divider trim from a snap-immune window
(`rtc_seconds_count` + PCF absolute time; `RTC_CAL_MIN_WINDOW_S 300`,
`RTC_CAL_MIN_DIFF_S 2`, half-step damping). The trim's arithmetic is
unchanged but it now *proposes* the nominal period instead of writing the
register (the ISR applies it).

**Standalone accuracy**: ±2 s is the design bound (the snap threshold);
~1 s is the floor — the PCF exposes whole seconds and its own crystal
drifts ~58 ppm (~5 s/day, measured; the trim faithfully reproduces the
reference's error and cannot help). With the timekeeper running, none of
this is the operative bound.

**Three trim traps, all hit during development — do not re-derive:**

1. *Restarting the window on a phase snap* — the snap fires exactly when
   drift is large, so the trim never ran once. Hence the snap-immune window.
2. *Trimming on any nonzero difference* — a 1 s-resolution reference over a
   60 s window always shows ±1; the loop limit-cycled forever. Hence the
   window/diff minimums.
3. *Applying the full correction* — quantisation overshoot becomes a
   standing oscillation. Hence half-step damping.

## Persistence, and what a reflash costs

The converged period is persisted (kb_eeconfig, coalesced deferred write,
sanity 28000-40000) **after every window evaluation** once uptime ≥ 10 min
and the value is ≥ 64 ticks from what is stored; `rtc_init()` prefers the
stored period. (Persisting only on a *changed* proposal was a bug — a loop
that converged cleanly never stored, and the next reboot re-seeded at
33600 with ~12 ms/s drift.) `RTC_PERIOD_INITIAL` (33600, measured
2026-08-30) is only the fresh-EEPROM fallback — ⚠️ **never upstream it**;
the ILRC varies part to part and with temperature.

**Reflashing ERASES the emulated EEPROM**, stored period included. With the
host attached, the SOF loop re-converges in **~4 min** (7-12 ms/s drift
early on); standalone, the legacy trim gets inside the 2 s deadband in
~10-15 min but full half-step convergence takes **hours** (each ≥ 300 s
window halves the remaining error — which is exactly why the SOF loop
exists). **Designed, not a fault.**

## The timekeeper (host side)

`hostagent/ak820-timekeeper.py` + `com.jdlien.ak820pro.timekeeper`
LaunchAgent: syncs on device enumeration, on wake, and every 5 min; logs to
`~/Library/Logs/ak820pro-timekeeper.log`. It replaced the retired 3-hour
`ak820-clocksync.sh` agent (2026-09-01). `ak820ctl clock` is now an
NTP-style calibrated-lead sync (calibration cache `~/.ak820ctl-cap`:
`proto lead b_ppm`); `hostagent/rtc_phase0.py` reads the `HC_RTC` status
pages 1-4 (sync/frequency/slew/PCF-writer state).

Host sync requires the USB cable (the HID interface has to exist) but
**the slider position does not matter** — raw-HID replies return over USB
in any mode (commit 4b86d95014; `history/clock-sync/phase-0-facts.md` F1). A
board left unplugged for days drifts at the PCF's ~5 s/day; the
on-enumeration sync catches it as soon as it is plugged back in.

## The 5-minute sawtooth, and what the loop is really fighting (2026-09-03)

The clock read ¼–½ s slow by eye. The timekeeper log showed why: every
periodic sync found the board **150–330 ms behind**, slewed it back, and five
minutes later it was behind again — for hours, on a converged loop. Three
findings, in the order they were established:

1. **The host-measured SOF bias was noise.** `bias_step` counted
   `sof_frames_total` against the wall clock over 15 min and cached the result
   for `ak820ctl` to send on every sync. The values it produced ran
   **−369…+587 ppm** on a controller phase 0 had put at +78 ± 3, and each new
   one re-steered the loop's target by hundreds of ppm. Root cause of the
   noise: the counter is only updated in the tick ISR, by ~1000 in one jump
   per RTC second, so any read lags the true frame count by 0–1000 frames
   depending on where in the second it lands, and two reads differ by up to
   ±1000 frames of pure phase noise — ±1100 ppm over 900 s. **Do not measure
   frequency from `sof_frames_total` against host timestamps** unless the
   window is hours long or the read is placed mid-second. (Six consecutive
   one-minute windows read −789, −7720, +9638, −6047, −5994, +1722 ppm while
   the Mac's wall clock held +7 ppm against its monotonic clock and NTP said
   +95 ms throughout: the reference was clean, the readout was not.)
2. **The fix is to learn the bias from the residual itself** (NTP's way): the
   board behind by `before` ms over `elapsed` s is `−before·1000/elapsed` ppm
   slow, and the loop targets `f_sof·(1+b)`, so the timekeeper moves `b` by a
   quarter of that per sample (`learn_bias()`), only from a slew-sized residual
   with the SOF reference in use and the board's period within 6 ticks of the
   previous sync, and writes it to `ak820ctl`'s cache. The frame-count
   measurement now only seeds a cache that has no bias. Whatever the bias's
   true cause, the residual is the observable that matters, and this drives it
   to zero.
3. **The ILRC wanders more than the loop can follow.** With the reference
   proven clean, the board's nominal period still moved
   33225 → 33198 → 33260 → 33248 → 33236 → 33244 over an hour — a few hundred
   ppm on 5-minute scales, most visibly after the flash that raised the LED
   default (more current, warmer board). The loop half-steps on 128-s windows
   once locked, so it lags a moving target by 100–160 ms per 5 min. Two
   mitigations shipped host-side: the timekeeper syncs every **120 s while the
   last residual exceeded 60 ms** (300 s otherwise), and the learner's gate
   tolerates that wander. The real fix is firmware: shorter locked windows
   (32 s) and fuller steps when consecutive deltas agree, so the loop follows
   the oscillator within ~half a minute. Not done; measure with the
   instrumented build's `[rtc] sof window` lines before tuning.

Also corrected: the "~4 min" post-flash re-convergence is ~20 min in practice,
because the ±16-tick lock threshold (±480 ppm) switches to 128-s windows early
and the last dozen ticks then halve once per window.

## Timebase note

QMK's millisecond timer runs ~1.2% slow under the current interrupt load
(see [leds.md](leds.md)) — **the clock is unaffected**: the display reads
the SN32 RTC's hardware registers, and both discipline paths use
`rtc_seconds_count` / `FRMNO` / PCF absolute time, none of which touch
`timer_read32()`.
