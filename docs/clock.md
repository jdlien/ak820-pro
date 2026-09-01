# The clock: two RTCs, the divider trim, and the resync agent

Code: `rtc/rtc.c`, `rtc/rtc_lld` additions via the `rtc_lld` ChibiOS patch.

> **Active project:** a peer session is implementing sub-second clock sync —
> see `clock-sync-plan/PLAN.md` (workspace root) for the current design and
> phase status. Check it before changing anything under `rtc/` or the
> host-side sync tooling.

## Architecture

Two physical clocks. A battery-backed **PCF8563** (CHMC D8563F clone) is the
reference; the **SN32 internal RTC** is the live 1 Hz clock the display
reads, seeded from the PCF and disciplined to it. The SN32 RTC runs off the
**ILRC** — an untrimmed on-chip RC oscillator, nominally 32 kHz, actually
~34.3 kHz on this unit (~4% fast, and temperature-dependent).

Discipline loop (`rtc_clock_discipline()`, every `RTC_CHECK_INTERVAL_S` 60):

- **Phase snap**: `rtcSetTime()` when the SN32 drifts ≥ `RTC_DRIFT_THRESHOLD_S`
  (2 s) from the PCF.
- **Divider trim**: adjusts the SN32 period (SECCNTV) from a measurement
  window built from two **snap-immune** quantities — `rtc_seconds_count`
  (free-running, untouched by `rtcSetTime`) and the PCF's absolute time.
  Windows lengthen and steps shrink as it locks; phase snaps stop entirely
  once converged.

**Three trim traps, all hit during development — do not re-derive:**

1. *Restarting the window on a phase snap* — the snap fires exactly when
   drift is large, so the trim never ran once. Hence the snap-immune window.
2. *Trimming on any nonzero difference* — the reference has 1 s resolution,
   so a 60 s window always shows ±1 and the loop limit-cycled between the two
   quantised answers forever. Hence `RTC_CAL_MIN_WINDOW_S 300` and
   `RTC_CAL_MIN_DIFF_S 2`.
3. *Applying the full correction* — quantisation overshoot becomes a standing
   oscillation. Hence half-step damping.

## The trim is persisted (2026-09-01, hardening phase 4)

After 10 min uptime, an accepted trim that moves ≥ 32 ticks from the stored
value is persisted (kb_eeconfig, coalesced deferred write, sanity range
28000-40000); `rtc_init()` prefers the stored period. `RTC_PERIOD_INITIAL`
(33600, measured on this unit 2026-08-30) is now only the fresh-EEPROM
fallback.

- ⚠️ **NEVER UPSTREAM the seed value** — the ILRC varies part to part and
  with temperature; 33600 would start another unit further off than nominal.
- **Reflashing ERASES the emulated EEPROM**, stored period included, so a
  flash restarts convergence from the seed. Measured 2026-09-01 after six
  flashes in one night: ~6000 ppm slow, halving per trim, for the first
  ~10-15 min. **That re-convergence is designed behaviour, not a fault** —
  the constant is thousands of ppm off on a different day (ILRC tempco),
  which is exactly why the trim persists rather than trusting any seed.

## Accuracy bounds — what is design, what is floor

- **±2 s is the design bound, not residual error**: `RTC_DRIFT_THRESHOLD_S 2`
  is where the snap fires, so the loop guarantees it. 1 would halve it at the
  cost of visibly jumping more often.
- **~1 s is the hard floor regardless of trim quality**: the PCF exposes
  whole seconds only. Beating it needs a different reference — that is what
  the clock-sync plan is about.
- **A residual ~0.5 s average lag is a fixed phase offset, not drift**:
  seeding/snapping lands at an arbitrary point within the PCF's current
  second. Removing it means polling for the PCF's seconds rollover at set
  time (up to 1 s of I2C polling to buy half a second).
- **Post-sync phase differs per sync** (+67 ms one run, −229 ms another, each
  with near-zero internal spread) — the signature of an uncontrolled
  prescaler, and it is on the **SN32 side** (`rtcSetTime()` does not reset
  its divider); the PCF shows no uniform-second scatter. Inferred from two
  samples. Also: each trim's SECCNTV write can lose up to a second of phase.
  If sub-second accuracy is wanted, this is where it lives — see the plan.

## ⚠️ The PCF8563 itself drifts ~58 ppm (~5 s/day) — a scheduled resync IS needed

Measured at 24 h: 5 s fast. (An earlier "no scheduled sync needed" note was
measured a few hours after setting — inside the ±2 s deadband, so it looked
like nothing.) **The divider trim cannot help**: it disciplines the SN32 *to*
the PCF, so it faithfully reproduces the reference's error. Do not go looking
in `rtc.c` when the clock drifts minutes per month.

**Fix: the timekeeper agent** — `hostagent/ak820-timekeeper.py` +
`com.jdlien.ak820pro.timekeeper` LaunchAgent (part of the clock-sync
project; see `clock-sync-plan/PLAN.md`). It syncs on device enumeration, on
wake, and every 5 min, logging to `~/Library/Logs/ak820pro-clocksync.log`.
It **replaced** the older 3-hour `ak820-clocksync.sh` +
`com.jdlien.ak820pro.clocksync` agent (retired 2026-09-01, plist removed) —
the 3 h/10800 sizing rationale in that script predates sub-second sync.

- Host sync requires the USB cable (the HID interface has to exist), but
  **the slider position does not matter** — raw-HID replies return over USB
  in any mode (commit 4b86d95014; verified in the BT position,
  `clock-sync-plan/phase-0-facts.md` F1). `ak820ctl clock --no-wait`'s
  write-only path guards against a limitation that no longer exists.
- A board left unplugged for days drifts the full ~5 s/day; the
  on-enumeration sync catches it as soon as it is plugged back in.

## Timebase note

QMK's millisecond timer runs ~1.2% slow under the current interrupt load
(see [leds.md](leds.md)) — **the clock is unaffected**: the display reads the
SN32 RTC's hardware registers, and the trim uses `rtc_seconds_count` plus the
PCF's absolute time, neither of which touches `timer_read32()`.
