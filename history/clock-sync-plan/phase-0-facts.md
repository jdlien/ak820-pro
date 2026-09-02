# Phase 0 — hardware facts (measured 2026-09-01)

Build: `via-instrumented-9d3316bd6d-dirty-20260901-135139.bin` (Phase 0
instruments + `HC_RTCTEST` hooks), flashed 13:55. Slider in the **BT**
position with the cable in for every test below — which itself produced
the first finding. Host: `hostagent/rtc_phase0.py`. Board timebase during
the tests: period 33600 (fresh EEPROM seed), running ~7000 ppm slow, so
board-cycle figures are ~0.7 % short of true ms where noted.

## Findings that change the plan

| # | Fact | Consequence |
|---|---|---|
| F1 | **Raw-HID replies DO come back over USB with the slider in BT.** Every `GET`/`HC_RTC`/`HC_RTCTEST` round-trip answered while typing went over the air (`[ch582] sent=1279`). | The plan's "wired position required for replies" assumption (inherited from CLAUDE.md/docs) is wrong for this firmware. Host sync can measure and correct in BT with the cable in; the `--no-wait` send-only path is only for a truly reply-less case, if one exists. T0.3 was therefore measured in the BT position directly. **Docs corrected** (workspace commit ca375de): the mechanism is board commit `4b86d95014` (2026-08-29), which overrode the weak no-op `bluetooth_send_raw_hid()` in `drivers/bluetooth/bluetooth.c` to send replies back over USB; the 08-28 "no reply" captures predate it. |
| F2 | **PCF I2C is ~6× slower than estimated**: 1-byte read **42–44 cycles ≈ 1.3 ms**, 8-byte write **80–81 cycles ≈ 2.4 ms** (bus idle). | §3.6 boot acquisition at 10 ms cadence = ~100 reads × 1.3 ms = ~130 ms of blocking spread over 1 s (13 % of that second, in ≤1.3 ms slices), not the 1.5 % claimed. Still inside C2's bound but needs re-sizing in Phase 3: lower the coarse cadence (e.g. 20 ms → ±10 ms, 65 ms/s) and/or tune `PCF8563_I2C_DELAY_NOPS` (15 NOPs ⇒ ~30 kHz effective; the PCF8563 is rated to 400 kHz). Each §3.5 step is 1.3–2.4 ms, never > 20 ms. |
| F3 | **The old edge-hunting method (`clock-phase.py`, `clock-error.sh`) has a ±1 s ambiguity**: it snaps to the nearest host boundary, so a board 954 ms ahead reads as "46 ms behind". T0.6 shows the two methods disagree by exactly 1000 ± 3 ms. | The `cnt` method is unambiguous and is now the reference; `--edge` remains valid only as a *sub-second* cross-check. Morning drift *slopes* stand; the absolute "behind by X" figures may have been a second off. |

## Test results

| Test | Result | Pass? |
|---|---|---|
| **T0.1** `SECCNTV` same-value write | `SECCNT` 6218 → **0** immediately; +100 µs read 9 cycles. `period+1` then restore: 10377 → 0. `RTCEN` 1→0→1: 10227 → 0. | **Yes** — same-value write resets; reset latency ≤ 1 cycle; `RTCEN` fallback also works (not needed). |
| **T0.2** tick-ISR latency `L` | idle 60 s: min 0 / max 7 / mean 2 cycles (1 cycle = 29.8 µs). **BT typing 90 s: min 0 / max 6 / mean 2.** | **Yes.** `LATE_CYCLES` can be ~170 (5 ms); R3 compensation jitter ≤ 7 cycles ≈ 200 µs. (RGB-animation and forced-flash-program cases not yet run; the mechanism is ISR-priority-bound and typing is the relevant load.) |
| **T0.3** `FRMNO` deltas | BT position, cable in: every delta **1006–1009** over 60 s, `d_zero=0 d_reject=0`, epoch stable, `usb_active|fn_valid = 0x03`. 60480 frames / 60.02 s host. | **Yes** for BT+cable. Wired position not separately run (F1 makes it the same USB path). **Mac-asleep and cable-out cases still to run** (need a sleep cycle / unplug; `usb_active` gating is in place either way). |
| **T0.4** PCF I2C cost | see F2 | measured |
| **T0.5** PCF STOP on the CHMC D8563F clone | Control_status_1 reads **0x08** at rest (TESTC set — factory default per datasheet), 0x28 with STOP. Release→first increment: **491.3, 489.0, 491.0, 493.6, 493.1 ms** (board cycles; ×1.007 ≈ 492–497 true ms); each sample late by 0–6 ms of HID poll. | **Yes — STOP works on the clone.** `D_first ≈ 0.49 s`, not the datasheet's 0.5078. Re-measure once the frequency loop is disciplined (Phase 2) and use the measured constant. |
| **T0.6** `rtc_now()` coherence | `stale_count = 0` throughout (incl. under typing); cnt vs edge agree to 6.2 ms spread (= poll granularity) modulo the 1 s ambiguity (F3). | **Yes.** |
| **T0.7** HID `GET` round trip, n=100 | **min 4.88 / median 5.94 / p90 6.08 / p99 10.03 / max 10.03 ms.** | U ≈ (10.0−4.9)/2 + 0.5 ≈ **3 ms worst, ~0.6 ms typical**. The SET-lead half needs Phase 1's `0x03`. |
| **T0.8** this Mac's SOF bias | 600056 frames in 600.009 s ⇒ **b = +78.1 ppm ± 3.3** (controller frames run fast vs wall clock). Epoch unchanged across the run. | measured. Uncorrected that is ~47 ms per 10-min sync interval, so Phase 2's bias term is load-bearing, not optional (as the plan already says). MacBook internal controller; a dock/hub will differ — cache keyed by controller ID. |
| **T0.9** console in the BT position | `qmk console` connects (`Console Connected: AJAZZ AK820 PRO`), `[health]`, `[stall]`, `[ch582]` lines stream. | **Yes** — instrumented console works in BT; the on-LCD snapshot is not a Phase 2 prerequisite. |
| `sizeof(time_t)` | **8** | no 2038 issue |

## Health (§6 gate)

| | daily, pre-flash | instrumented, post-flash + tests |
|---|---|---|
| `loop_gap_max_ms` | 19 | 7 (later 14 via console `[health]`) |
| `scan_rate` | 356 | 305 / ~250 (console attached) — in the instrumented band |
| `blit_timeouts` | **2 (pre-existing)** | 0 |
| BT `tx_timeouts/tx_sent` | 206/4812 = 0.043 | 84/1281 = 0.066 (boot-heavy, short sample) |
| `[stall]` (instrumented only) | no prior record | ~110–130/s, worst 7–8 ms, unattributed (`?`) |

The `[stall]` instrument counts main-loop gaps ≥ 4 ms and the instrumented
loop period is ~4 ms (scan ~250 Hz with the console attached), so the
count is that flavor's noise floor, not a Phase 0 effect: Phase 0 adds
nothing per main-loop pass (the only new thread-context work is one
locked read at 10 Hz) and ~2 µs per second in the tick ISR. **This number
is the reference for Phase 1's comparison.** `blit_timeouts = 2` on the
daily build predates this work (recorded, not caused).

## Live demonstrations of the problems Phase 1/2 fix

- After `ak820ctl clock` (legacy `0x01`, boundary-aligned send) the board
  read **+676 ms ahead**: whole seconds set, prescaler phase untouched.
- With the period at the fresh seed 33600, `FRMNO` showed 1007–1008
  host-ms per RTC second within one second of boot — the SOF reference
  reveals a 7000 ppm error instantly, where the PCF trim needs ≥ 5 min per
  half-step.

## Constants for later phases

| Name | Value | From |
|---|---|---|
| `LATE_CYCLES` | 170 (≈ 5 ms) | T0.2 (max seen 7) |
| ISR write jitter bound | ≤ 7 cycles | T0.2 |
| `D_first` (clone) | 0.49 s (re-measure in Phase 2) | T0.5 |
| PCF 1-byte read | 1.3 ms | T0.4 |
| PCF 8-byte write | 2.4 ms | T0.4 |
| HID RTT | 4.9 / 5.9 / 10 ms (min / median / p99) | T0.7 |
| U (host uncertainty) | ~3 ms worst | T0.7 |
| SOF bias `b` (this Mac, internal controller) | +78 ppm ± 3 | T0.8 |

## Post-test health (instrumented build, after all Phase 0 tests, ~18 min uptime, BT typing throughout)

`loop_gap_max_ms` 15 · `scan_rate` 267 (console attached part of the time) ·
`blit_timeouts` 0 · `tx_timeouts/tx_sent` 195/3425 = 0.057 (boot-heavy
short session; the 0.042 baseline is a long sustained burst — re-check in
Phase 1 over ≥ 300 frames after boot traffic) · `wdt` clean.
