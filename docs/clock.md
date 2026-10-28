# The clock: two RTCs, sub-second sync, the divider trim, and host sync

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
  delta (`FRMNO`); every **32** accepted samples housekeeping proposes a
  period — a half step when the delta's sign disagrees with the previous
  window's (noise, or the onset of a move), a **full step once two windows
  agree** (drift: the ILRC wandering, followed within one window) — corrected
  by the SOF bias the host **learns from the sync residual** (see "The
  5-minute sawtooth"; the bias is load-bearing, ~47 ms per 10 min uncorrected;
  cached in `~/.ak820ctl-cap`). Firmware `8608c4f680`, 2026-09-04: a
  fresh-seed clock went 33600 → 33520 in **90 s** and then held ±2 ticks; the
  old 128-s half-step loop took ~20 min. Was: 128-s windows once locked and
  half steps always, which lagged the wandering ILRC by 100–160 ms per 5 min.
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
  - ⚠️ **Every transaction blacks out the LEDs** (found 10-27): it holds
    the row ISR's interrupt off for its length, up to 3.4 ms, and a write
    is three bursts over a second (STOP and the time, the release, the
    bracket). After every host sync that made a correction, so every 5
    minutes on USB: JD saw it, and filmed it at 240 fps
    ([leds.md](leds.md), "The other flicker"). JD's call: write the PCF
    only when the lights are dark or after a long stretch without typing.
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
reference's error and cannot help). With a host agent syncing it, none of
this is the operative bound.

**Three trim traps, all hit during development — do not re-derive:**

1. *Restarting the window on a phase snap* — the snap fires exactly when
   drift is large, so the trim never ran once. Hence the snap-immune window.
2. *Trimming on any nonzero difference* — a 1 s-resolution reference over a
   60 s window always shows ±1; the loop limit-cycled forever. Hence the
   window/diff minimums.
3. *Applying the full correction* — quantisation overshoot becomes a
   standing oscillation. Hence half-step damping.

## Across a deep sleep (the deep-sleep build)

The board sleeps in the SN32's Deep-sleep with the system timer stopped
([hardware.md](hardware.md), "Deep sleep"). The SN32 RTC counts on asleep,
but its second interrupts are cleared rather than served, and ⚠️ **asleep its
second runs ~13% slow** (3,139 counted for 3,600 over the hour of 10-19; the
ILRC unloaded): the counted seconds are a fallback, not the slept time. The
design: [`plans/DEEP-SLEEP-BUILD-PLAN.md`](../plans/DEEP-SLEEP-BUILD-PLAN.md),
section 4; the code: `rtc.c`, "Deep sleep's recovery".

1. **Before the lock** (`rtc_sleep_prepare`): the PCF read once, under the
   arbiter below. A failed read does not stop the sleep; the counted seconds
   then stand. The board sleeps only with the clock quiet: no slew, no reload,
   no PCF write pending or running, no acquisition (`rtc_sleep_ok`).
2. **Under the lock, at the wake** (`rtc_account_sleepI`, `rtc_wake_beginI`):
   both software clocks (ours and the LLD's calendar) take the counted
   seconds before any second is served. The SOF reference is broken outright
   and re-qualifies, the trim window restarts (the slow asleep seconds are not
   the awake ILRC's), and the 60 s discipline is suspended.
3. **The coarse read**, once `sleep.c`'s input gate lets go (the waking key
   counted, or 50 ms): the PCF again, and the slept seconds are its
   difference, checked against the counted (between half and twice; one
   outside is a bad read, and the counted stand). The clocks take the
   difference; the calendar is set to the PCF's whole seconds; the old host
   sync's flag is cleared. **Unless a host sync came since the wake**: every
   host set bumps `host_sync_gen`, the recovery notes it at the wake, and a
   newer host time always wins. Sets the firmware makes itself carry
   `RTC_SETF_INTERNAL` (0x80) and never count as the host's; the host's flags
   are masked to keep it out.
4. **The phase**: the boot acquisition, every field reset, runs again to find
   the PCF's second edge, now split into **one transaction a pass** (its
   states `WAIT_SPLASH`, `COARSE`, `FULL`, `CONFIRM`, `DONE`, `ABORTED`) and
   keeping the bracketed second it measured from, so a pass that comes late
   cannot set the clock a second wrong. A full read is given 900 ms
   (`ACQ_FULL_MAX_MS`). The dev hook op 14 sub 6 holds the next full read 1 s
   past its bracket's edge, once: it must reacquire.

**The arbiter.** From the wake until **the whole recovery** ends
(`sleep_recovering()`, not only the clock's part), every PCF transaction
(the coarse read, the acquisition's, a host sync's write machine) goes
through `rtc_fast_task`'s slot: **at most one a pass, only with the display
bus idle and under 10 ms into the pass** (`sleep_pass_us`), with a **5 ms**
I²C timeout instead of 20. The write machine's STOP recovery takes its write
and its check a pass each. A pass that used the bus defers its display work
to the next (`display_defer_pass`), so the pass stays short and the waking
burst of keys is scanned on time. The acquisition starts only once the gauge
has the slept seconds (`rtc_wake_gauge_taken`), and the gauge runs only in a
pass with no PCF transaction (`rtc_pass_used_bus`, counted from the last
pass's end). The legacy whole-second SET (0x01), which does its I²C
synchronously, is refused through the recovery (the host retries);
`RTC_SET_TIME_MS` is not. The 60 s discipline is suspended through it, and
**never snaps the clock to the PCF while a write to the PCF is pending or
running** (in any state, not only after a sleep): until it lands, the PCF
holds the time from before a host's sync.

**Measured across sleeps (10-19):**
- After 100 wakes in 85 minutes with no host sync (the bench cut USB data
  each cycle), the daemon's first sync read **+288.4 ms**: the board had
  followed the PCF, whose crystal runs ~58 ppm off (0.30 s in 85 min). As
  designed with no host.
- After 8 minutes off USB (7 awake with no SOF reference, then a 65 s
  sleep), the first sync read **+143.6 ms**. The board's frequency loop had
  been reset by a flash 15 minutes before, so how much is the sleep's is not
  yet separated.
- The per-wake offset is measured only by a run that leaves the daemon its
  raw HID after the wake (`scripts/ladder_sleep.py` waits for the daemon's
  sync before its own reads); `deep_cycles.py` holds it, so the daemon's
  syncs fail during a soak.
- ⚠️ `flash.sh` used to sync with `ak820ctl` beside the daemon: two clock
  owners. Since `9880f47` it leaves the sync to a daemon that owns the clock.
  A −2064.5 ms offset three minutes after a flash (16:20 10-19) may have been
  that collision.

**What the sleep must not move** (validation 4): the awake period `P_nom` and
the persistence candidate (`HC_RTC`). Neither learns from asleep seconds.
The calendar can move at the wake, and `clock_gen` counts each change so the
display knows when the face it painted is current
([display.md](display.md), "At a deep sleep and its wake").

## Persistence, and what a reflash costs

**Correcting and saving are separate** (Phase 1b's C2, firmware flash 2,
2026-10-08; `rtc/rtc_persist.c`, `rtc_persist.h`). Both correction paths, the
SOF window and the PCF trim, correct the live period exactly as before, and
each accepted, sane value (28000-40000) becomes the **candidate**. They never
write. One scheduler, run once a minute from `rtc_task()`, owns every save
(kb_eeconfig, coalesced deferred write):

- **The first save:** nothing stored, and uptime ≥ 10 min. It saves whether or
  not the candidate is still moving: a loop that converged cleanly and never
  stored was a real bug once (the next reboot re-seeded at 33600 with ~12 ms/s
  drift).
- **Later saves:** the candidate ≥ 64 ticks from the stored value **and** ≥ 6 h
  since this boot's last save (or since boot). So at most 4 a day, one budget
  for both paths.
- `rtc_init()` prefers the stored period. The saved value only seeds the next
  boot, so holding a save for hours costs nothing but a slightly worse seed.

**Why:** every internal-flash write blinks the LEDs dark for a few ms
([leds.md](leds.md)). Until flash 2 each path saved whenever its value moved
≥ 64 ticks from the stored one, and the PCF path did that **6-8 times a day on
battery** (Phase 1b's C1, 2026-10-05/07): the 64-tick threshold did not keep
temperature wander from causing steady rewrites, as `rtc.c`'s comment had
claimed. Measured since: 3 saves (of 29 proposals) in a 24 h battery soak
(10-09/10), and on the host (`scripts/diag_sim`, `persist`) 3 saves in a day
of the worst wander on both paths, 1 in two settled days. The counts are on
`HC_FLASHW` (`ak820health.py --stalls`): proposals and stores per path, and
the last of each.

*Superseded:* until flash 2 this section read "persisted **after every window
evaluation** once uptime ≥ 10 min and the value is ≥ 64 ticks from what is
stored".

`RTC_PERIOD_INITIAL` (33600, measured 2026-08-30) is only the fresh-EEPROM
fallback — ⚠️ **never upstream it**; the ILRC varies part to part and with
temperature.

**Reflashing ERASES the emulated EEPROM**, stored period included. With the
host attached, the SOF loop re-converges in **~4 min** (7-12 ms/s drift
early on; on `8608c4f680` a fresh seed settled in 90 s), and the first save
follows at 10 min of uptime. Standalone, the legacy trim gets inside the 2 s
deadband in ~10-15 min but full half-step convergence takes **hours** (each
≥ 300 s window halves the remaining error — which is exactly why the SOF loop
exists). **Designed, not a fault.**

## Host sync (the host side)

**The Rust daemon `ak820-agent` keeps the clock** when installed with `ak820
install --clock`: on Windows since 2026-09-06 (Scheduled Task
`\ak820pro\AK820Pro-agent`, log `%LOCALAPPDATA%\ak820pro\ak820-agent.log`), on
JD's Mac since 2026-09-16 (LaunchAgent `com.jdlien.ak820pro.agent`, log
`~/Library/Logs/ak820pro/ak820-agent.log`). It syncs on device enumeration, on
wake, and every 5 min (3 min while the last residual exceeded 60 ms). Its
transaction, scheduler and bias learner are ports of `ak820ctl`'s and the
Python timekeeper's, checked against both
(`plans/AK820-AGENT-CLOCK-PARITY.md`, `plans/AK820-AGENT-CLOCK-TRANSACTION.md`),
and it shares `ak820ctl`'s calibration cache, `~/.ak820ctl-cap` (`proto lead
b_ppm`; under `%USERPROFILE%` on Windows). Exactly one process may own the
clock; the daemon refuses `--clock` while the timekeeper is still set to run.

The **Python timekeeper** it replaced, `hostagent/ak820-timekeeper.py`, stays
as the fallback and the oracle (`com.jdlien.ak820pro.timekeeper` LaunchAgent on
macOS, `\ak820pro\AK820Pro-timekeeper` Scheduled Task on Windows; log
`~/Library/Logs/ak820pro-timekeeper.log` or
`%LOCALAPPDATA%\ak820pro\ak820pro-timekeeper.log`). It shells out to
`ak820ctl clock`, an NTP-style calibrated-lead sync, per transaction. It
replaced the retired 3-hour `ak820-clocksync.sh` agent (2026-09-01).
`hostagent/rtc_phase0.py` reads the `HC_RTC` status pages 1-4
(sync/frequency/slew/PCF-writer state).

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
   mitigations shipped host-side: the timekeeper syncs every **180 s while the
   last residual exceeded 60 ms** (300 s otherwise), and the learner's gate
   tolerates that wander. The firmware fix followed on 2026-09-04
   (`8608c4f680`): 32-s windows and a full step once two consecutive windows
   agree in sign, so the loop follows the oscillator within ~half a minute —
   measured above. ⚠️ The fast interval was 120 s for one night and that
   FROZE the old 128-s loop: a slew writes the period register ~3 times and
   each write restarts the window, so the window never saw 128 clean seconds,
   the residual stayed at +300 ms, and the residual kept the interval fast
   (05:30–11:00). The sync interval must exceed the firmware's window plus a
   slew's settling; nothing enforces that across the two repos
   (`plans/BACKLOG.md`).

**How far the ILRC actually moves:** the nominal period read 33200–33260 on
the evening of 2026-09-03, 33429 at 11:00 the next morning and 33516 by noon —
about **+0.9 % across a day** on one unit at one desk. That is the number
behind the fast-tracking loop: an oscillator that wanders a percent a day was
never going to be held by a 20-minute convergence. It is also why the persist
rate is judged against distance, not time: the period write fires every
64 ticks of net movement, so `writes ≈ Δperiod / 64` is the clean loop and
`writes ≫ Δperiod / 64` would mean the ±2-tick dither is straddling a
threshold — the one way a faster loop could cost flash, fixable with
hysteresis on the persisted value rather than by slowing the loop.
**Superseded (2026-10-08):** distance alone did not bound it. On battery the
PCF path saved 6-8 times a day, so saves now also need 6 h since the last
("Persistence", above).

Also corrected: the "~4 min" post-flash re-convergence is ~20 min in practice,
because the ±16-tick lock threshold (±480 ppm) switches to 128-s windows early
and the last dozen ticks then halve once per window. **Superseded the next day
by `8608c4f680`:** both windows are now 32 samples (`WIN_INITIAL` and
`WIN_LOCKED` in `rtc.c`), so the lock threshold switches nothing and survives
only as the console's lock indicator; a fresh seed settled in 90 s. Nothing in
this section's 128-s figures describes the current loop.

## Timebase note

QMK's millisecond timer runs ~1.2% slow under the current interrupt load
(see [leds.md](leds.md); *leds.md retracted this on 2026-09-03: the timer
reads 1.0001-1.0004 of wall time*) — **the clock is unaffected**: the display
reads the SN32 RTC's hardware registers, and both discipline paths use
`rtc_seconds_count` / `FRMNO` / PCF absolute time, none of which touch
`timer_read32()`.
