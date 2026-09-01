# Backlog — known, accepted, or deferred items

## Red LED-row flash during/after RGB adjustment (JD, 2026-09-01)

**Symptom:** holding an RGB adjust key (e.g. Fn+Up), a row of red LEDs
flashes briefly. Longstanding, cosmetic.

**Root cause (understood, not guessed):** the settled eeconfig write fires
~0.9 s after the values stop moving (RGB_SETTLE_MS). The EFL program window
masks interrupts for its few-ms duration (efl_ramtext.diff -- deliberate,
see the audits), which freezes the LED row mux mid-cycle: whichever hardware
row was energized in its RED time-slot stays lit at full duty until the
write completes. It is the flash write announcing itself.

**Proposed fix:** blank the LED matrix around the program window --
`sn32f2xx_blank()` exists for exactly this (forces every row/col pin
high-Z; created for the stop-the-ISR case, currently zero callers). Call it
from `backing_store_pre_write_hook()` before the write.
**⚠️ The blocker to resolve first:** blank changes pin MODES to high-Z; if
the row ISR only writes levels/duties and never re-initialises pin modes,
the matrix stays dark after the write. Verify whether `rgb_callback` /
the driver's row advance reconfigures modes per cycle, or add an explicit
re-init after the write. Needs a hardware round-trip -- do not ship blind.

## Scan-rate observation

Instrumented builds read ~230-310 Hz (console + probes overhead); the daily
build reads ~375 Hz. Judge scan-rate bands per flavor.

## rx_malformed baseline

The fault suite's byte soup legitimately raises rx_malformed (by ~5 per
run) for the remainder of that boot. Normal-use expectation is 0 growth.
