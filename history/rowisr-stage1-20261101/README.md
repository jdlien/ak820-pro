# The row ISR rewrite, stage 1 on white: the A/B against the v0.3.0 base (2026-11-01)

The first flash of the row ISR rewrite ([`plans/ROW-ISR-PLAN.md`](../../plans/ROW-ISR-PLAN.md),
stage 1: the RGB driver and the key matrix moved board-local with the ChibiOS
PWM machinery kept, so the move itself can be measured). White, JD's board,
mid-drain on its pack at 35%, on Buzz's bench. The audit session flashed the
v0.3.0 candidate (`4c7395a4c6`, token `0x6f758b40`) at 14:40 and ran its
release checks; white was handed over at 16:29. JD's go for the interim
flash was given in the afternoon; the go for the second flash (the fix) at
17:55.

## What ran

`session.sh all` (this directory): the daemon paused, data on, the base run
of `scripts/rowisr_baseline.py` on the candidate, `flash.sh` with stage 1
(`a8a567308d`, `via-dev-a8a567308d-20261101-121551.bin`, token
`0x19884af9`), the same run, `compare`. Six attempts before a clean one:

| Attempt | Time | What stopped it |
|---|---|---|
| 1 | 16:29 | the runner read the loop-gap figure from the wrong health page (`KeyError`) |
| 2 | 16:30 | the power ladder: Power saver caps the RGB value at 128 and dims and darkens the board minutes after the last key, which raw HID is not; the holds read white 64 below dark. The runner now sets Always on for the run and puts the mode back |
| 3 | 16:35 | white had deep-slept in the gap (Power saver, three minutes after JD's 16:29 key); no board on USB |
| 4 | 16:46 | woken with relay 2 (the charger pin is a wake source), but a charger wake with no key goes straight back to sleep once the 5 V is gone |
| 5 | 16:47 | relay 2 on, the data link brought up while it was on (data on holds off the sleep), relay 2 off: awake. The ladder's stage was read back before it had moved (stage 3 after a wake): the runner now waits for it to settle |
| 6 | 16:48 | the clean run: base 16:48-17:11, flash 17:11, stage 1 17:12-17:35 |

Relay 2 was closed three times for the wakes, at JD's suggestion (16:46:47-49,
16:47:58-48:03 and 17:45:42-48): 0.46 + 0.91 + 0.92 = 2.29 mAh of charge
into the drain's pack, the audit session's figures from `power.csv`. The
runner's lighting holds ran with the board in Always on (16:48-17:11 and
17:12-17:35), Power saver put back after each; attempt 5's failure had left
Always on persisted until the 17:45 probe restored it.

## Stage 1 against the base (`compare.txt`)

| Window | Metric | Base | Stage 1 | Change |
|---|---|---|---|---|
| idle | ISR/s | 3744.1 | 3705.2 | −1.04% |
| idle | mean µs | 195.9 | 198.2 | +1.17% |
| idle | CPU % | 73.4 | 73.4 | 0 |
| idle | row gap max ms | 5 | 6 | +1 (the record's worst is 6) |
| repaint | ISR/s | 3744.1 | 3704.7 | −1.05% |
| repaint | mean µs | 195.9 | 198.3 | +1.23% |
| pcf | ISR/s | 3696.2 | 3654.1 | −1.14% |
| pcf | mean µs | 195.8 | 198.3 | +1.28% |
| pcf | row gap max ms | 9 | 9 | 0 |
| all | stalls ≥ 25 ms | 0 | 0 | 0 |
| all | UART overruns | 0 | 0 | 0 |

The callback costs about 2.3 µs more per slot (the I-class locks in the
row helpers), so the slot rate is 1% lower; the CPU share is identical.
ACK timeouts grew 2-3 a window on the base and 5-6 on stage 1, but the
base had been up two hours and stage 1 ten seconds, so the link was still
settling; a warm comparison is owed.

Every lit state's total draw was the same on both builds within 0.5 mA
(white 64: 45.18 both; white 255: 88.73 against 88.33), but the dark state
(Solid, value 0) read 40.62 mA on the base and 41.94 on stage 1, steady
across three holds each, so every incremental figure came out 1.3 mA lower
on stage 1 and `compare` flagged all 24.

## The 1.3 mA at dark, found

Probes on stage 1 (`dark_probe2.py`, Always on, 40 s holds): Solid value 0
42.00 mA; the same with the key scan skipped (dev op 28 sub 4) 42.03; the
RGB matrix off (effect 0) 42.00; value 0 again 42.00. Not the scan, not the
effect. The driver's per-slot code is identical in both builds (diffed by
both sessions).

The cause is the plan's "harmless" out-of-bounds read: the hardware-PWM
path reads `led_state[led_index]` without a NO_LED check, and nine matrix
positions have no LED (key (0,14) and eight positions that are no key
either), so each slot reads `led_state[255]`, three bytes past the array.
Where that lands depends on the link:

| Build | `led_state + 765` lands in | Bytes |
|---|---|---|
| base `4c7395a4c6` | `__compound_literal.13` + 17: the raw-HID IN queue's slot 0 (`usb_endpoints.c`) | the last raw-HID reply's data bytes 13-15 |
| stage 1 `a8a567308d` | `wear_leveling` + 125: the EEPROM's RAM cache | settings bytes, nonzero, constant |

A nonzero phantom makes the slot assert its mux row and put a phantom width
on the empty column: the row and column transistors' base current with no
LED to show it, present only while the frame is dark (a lit frame asserts
the row anyway). The audit of 10-31 had this as F-033 and estimated it as
"row-transistor base current at most, unmeasured"; it is 1.3 mA on stage
1's layout, and the base's own dark figure carried a phantom from whatever
reply sat in slot 0, so neither 40.62 nor 41.94 is the true dark draw.

**The fix** (`b3270996d3` on `row-isr`, the audit's F-033 form): `continue`
on `led_index >= SN32F2XX_LED_COUNT` at the top of the per-column loop in
`update_pwm_channels()`; the column stays released, since
`shared_matrix_rgb_disable_output()` ran this slot. The software-PWM path
always had it. The mainline gets the same line (v0.3.1, JD's call), and the
base plus the fix is measured when that candidate goes on white, which
closes stage 1's LED-power gate properly.

## The fix on white

`fix_check.log` (17:56-18:01): stage 1 plus the fix,
`via-dev-b3270996d3-20261101-175317.bin` (token `0x991e7b11`), flashed over
the first build after JD's key woke white, four 40 s holds in Always on:

| State | Base (unfixed) | Stage 1, first build | Stage 1 + fix |
|---|---|---|---|
| dark (Solid, value 0) | 40.62 | 41.94 | 40.62 / 40.61 |
| white 64 | 45.18 | 45.18 | 45.26 |
| white 255 | 88.73 | 88.33 | 88.72 |

With the fix, stage 1 matches the base on every state to a tenth of a
milliamp; the base's dark figure that afternoon was clean (its slot-0 bytes
happened to be zero through the holds). The second half of the gate,
`base_fix_check.log` (18:05-18:09): the base plus the same fix (the audit
session's `f033-noled` build, `cfe6c2d3a5`, token `0xc1237f1a`), flashed
after JD's key, the same four holds, then stage 1 plus the fix flashed
back:

| State | Base + fix | Stage 1 + fix | Change |
|---|---|---|---|
| dark | 40.58 / 40.61 | 40.62 / 40.61 | +0.1% |
| white 64 | 45.25 | 45.26 | 0 |
| white 255 | 89.35 | 88.72 | −0.7% |

**Stage 1's LED-power gate passes with the fix in both builds**, and the
rest of stage 1's hands-free gates passed in the A/B above. White was left
on stage 1 plus the fix (`b3270996d3`, token `0x991e7b11`) at 18:09, in its
standing state: JD's lighting and Power saver read back, data off, the
daemon running, relay 2 off. Still owed on this build: Bootmagic, deep
sleep's five wakes and the phantom-or-missing count (the presser, 11-02),
and a warm set of windows for the ACK-timeout comparison.

## Files

- `session.sh`, `session.log`: the six attempts and the clean run; `run-base.log`, `run-stage1.log`, `base.json`, `stage1.json`, `compare.txt`, `flash.log`.
- `settings-before.json`, `lighting-before.json`: the last run's dumps (restored); `settings-after-probe.json`.
- `dark_probe.py` / `dark_probe2.py` and their logs: the probes; `dark_after_sleep.*`: the aborted slept-board test (its relay wake is the third charge); `peek.log`: an HC_PEEK attempt that found white asleep.
- `fix_check.sh`, `fix_check.log`: the fix's flash and holds; `base_fix_check.sh`, `base_fix_check.log`: the base plus the fix, and stage 1 plus the fix back.
- `battery-before.txt`, `battery-after.txt`, `health-after-flash.txt`.

## Lessons

- A runner on this board must hold the power ladder off (Always on) and
  put the mode back: Power saver caps the value and darkens an idle board,
  and raw HID is not activity.
- A deep-sleeping board is not on USB; the charger pin wakes it only for a
  second unless the data link is up before the 5 V goes.
- Never edit a bash script while it runs: bash reads it incrementally, and
  the running `session.sh` hit a syntax error at its end when the `windows`
  step was added to it (after its useful work; the EXIT trap still ran).
- The link's counters count since the boot; compare their growth per
  window, not the totals, across a flash.
- "Harmless" out-of-bounds reads are not: the plan's and the audit's note
  on `led_state[255]` cost 1.3 mA at dark on one layout and an unknowable
  phantom on the other.
