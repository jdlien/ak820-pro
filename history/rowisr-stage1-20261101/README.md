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

## Stage 2 on white, the same night (19:20-20:10)

The hot path ([`plans/ROW-ISR-PLAN.md`](../../plans/ROW-ISR-PLAN.md), D2,
D3, D7, D8, D10: CT16B4 the slot scheduler, CT16B0/1/2 one-shot pulse
timers, the ChibiOS PWM service gone), after codex's two reviews
(`plans/review-codex-row-isr-stage2-2026-11-01-raw.md`, NOT READY on one
P1 and twelve P2s, all dispositioned; the verify review READY TO FLASH).
`session.sh stage2` flashed `8e86b8d90a` (token `0xf6a21a82`) at 19:20
after JD's key and ran the windows and the holds as `stage2`
(`run-stage2.log`, `stage2.json`, `compare-stage2.txt`); `session.sh
holds` flashed the fix below, `b120a2069c` (token `0x4849bde6`), at 19:44
and reran the holds as `stage2fix` (`run-stage2fix.log`, `stage2fix.json`,
`compare-stage2fix.txt`). White stayed awake between the two because the
holds step's data-on came within the minute.

### The first frame answered Q6

JD saw the boot frame white with magenta on A, X, C, V, N, M, PgDn and the
right arrow, then the restored theme peach and pink instead of purple and
blue. The magenta keys are exactly the keys one row above the nine matrix
positions with no LED ((0,14), (3,12), (4,1), (4,14), (5,3), (5,4), (5,5),
(5,7), (5,8); the ninth key above one is `]`): at a near-white frame the
green pin of key row k was being given the red of key row k+1, zero over a
hole. So the mux pins are R, B, G per key row, as `config.h` always said,
and the old driver's B, G, then the next row's R was a one-slot lead over
the pins: its widths reach the LEDs a cycle after their write, and stage
2's one-shot restart takes the widths written before it, so the same
submission order rendered red from blue, blue from green and green from
the row below's red (peach alphas, pink mods). The fix (`2d5a5d3e7f`):
the key row advances on the first pin of its group, the scan slot with it,
the D8 index and the decoder's row labels follow. With it, `b120a2069c`:
the verify review's divide in the masked arm section is a comparison.

### The handler, from the windows (`compare-stage2.txt`, on `8e86b8d90a`)

| Window | Metric | Base | Stage 2 | Change |
|---|---|---|---|---|
| idle | ISR/s | 3744.1 | 3745.2 | +0.03% |
| idle | mean µs (page 4, the scan included) | 195.9 | 59.8 | −69% |
| idle | CPU % | 73.4 | 22.4 | −69% |
| idle | max µs | 256 | 144 | |
| idle | row gap max ms | 5 | 5 | 0 |
| idle | loop gap ms | 11 | 3 | |
| repaint | mean µs | 195.9 | 59.8 | −69% |
| repaint | loop gap ms | 17 | 5 | |
| pcf | ISR/s | 3696.2 | 3696.3 | 0 |
| pcf | mean µs | 195.8 | 59.7 | −69% |
| pcf | row gap max ms | 9 | 9 | 0 |
| all | stalls ≥ 25 ms | 0 | 0 | 0 |
| all | ACK timeouts a window | 2-3 | 0 | |

The record (page 7 and op 28 sub 5; `sched-after-stage2fix.txt`,
`power_saver_back.log`): over 5.82 M slots since the 19:44 boot, 401
missed (the flash's settings restore), 24 pulses omitted of 2.90 M emitted
(14 by the arm deadline, the longest run 1), the worst entry latency
104.9 µs, the longest handler 161.8 µs, the shortest 28.5 µs, no epoch
loss, no spurious service, no invalid service; a 60 s window of the dark
idle board (Power saver's stage 3) 47.4 µs mean, 17.7% share by page 7's
snapshot-to-snapshot figure. The first decode of sub 5 read the reply from
byte 0 instead of past its 4-byte header (a "4,871-long run of omissions"
was `0x1307`, the header's bytes); `rowisr_diag.py` is fixed.

### The light, from the holds (`compare-stage2fix.txt`, incremental mA, dark subtracted)

| State | Base | Stage 2 (fix) | Change |
|---|---|---|---|
| white 64 | 4.56 | 5.88 | +29% |
| white 128 | 10.85 | 12.21 | +12.6% |
| white 255 | 48.11 | 49.67 | +3.2% |
| red 64 / 128 / 255 | 3.09 / 5.70 / 21.64 | 2.12 / 4.81 / 20.82 | −32 / −16 / −3.8% |
| green 64 / 128 / 255 | 2.69 / 4.55 / 15.63 | 1.94 / 3.82 / 14.95 | −28 / −16 / −4.3% |
| blue 64 / 128 / 255 | 2.64 / 4.35 / 14.45 | 1.87 / 3.60 / 13.77 | −29 / −17 / −4.7% |
| dark | 40.62 | 40.94 | +0.3 mA |

The return leg repeats the forward leg within 0.05 mA. Stage 2's light is
additive: its white equals the sum of its single colours within 1% at
every level (64: 5.88 against 5.93). The base's is not: its white 64 is
54% of the sum of its single colours (4.56 against 8.42), its white 255
93% (48.1 against 51.7). So the base's per-slot light depended on what
the neighbouring slots carried, which a clean pulse cannot reproduce, and
no single scale lands every state within 3%. k stays 10, set at
full-scale white (+3.1%); the four full-scale states together are within
1% of the base (99.2 against 99.8 mA). The +0.3 mA at dark is within the
day's drift (the base's dark read 40.58-40.62 across the afternoon, the
fix round 40.93-40.94 across its three holds).

On the unfixed first build the colour holds showed the rotation in the
draw too (`compare-stage2.txt`): its "red" lit the green pins (13.6 mA at
255, the base's green 15.6 less the nine missing LEDs), its "green" the
blue pins (13.8 against 14.5), its "blue" the red pins (21.0 against 21.6).

### Two faults in the runner

The settings dump was taken after Always on was set, so the `--live-only`
restore put Always on back at the end of both runs (a board in Always on
never sleeps on battery); fixed in `scripts/rowisr_baseline.py` (the dump
first), and Power saver put back by hand at 20:09
(`power_saver_back.sh`, `power_saver_back.log`). And a step's EXIT trap
turning data off lets the idle board deep-sleep within the minute; the
first run of that script looked for the board with `system_profiler` and
missed it, `ioreg` finds it.

White was left on stage 2 (`b120a2069c`, token `0x4849bde6`) at 20:10 in
its standing state: JD's lighting and Power saver read back, data off, the
daemon running, relay 2 off. **JD's eye, 20:40-20:50, by keys only while
the wake-gate session held white:** the theme right on every key (the
F row, the nav cluster, the arrows, the modifiers and the backslash blue,
the alphas, numbers and punctuation purple, as his profile has them), and
with the saturation taken to zero from the keyboard (his layout's Fn+`,`)
a uniform white with no tint over the nine holes. **The lighting went back
from the backup at 21:13, once the wake-gate session had released white**
(`lighting-restore.log`): hue 178, sat 219, val 177, speed 231 read back.
Before the restore the board read sat 191, neither the 0 JD had taken it
to by keys nor the 219 of the 20:10 dump; the two deep-sleep wakes of
case 3 lay between. Unexplained (a key after the check, or a wake
re-applying a flushed record over the keys' change, are the candidates),
noted in the backlog, not chased. **The wake-gate session's case 3 on
white (21:03-21:13, [`../wake-case3-20261101/`](../wake-case3-20261101/README.md))
counts toward stage 2's deep-sleep wakes:** two deep-sleep wakes on JD's
key with the RGB lit, re-enumerated within 4 s of the wake, no reset, no
stray. Owed on it: scan-only, the rest of deep sleep's wakes and the wake
with the RGB dark (the verify review's bring-up list); the witness's
pulse gates.

### Scan-only on white (11-02 morning, `scan_only_check.sh`, `scan_only_key.sh`)

The dev build's light-sleep mask bit 0 (op 14 sub 3, `sleep.c`'s
`light_task`) asks the row handler for scan-only while the RGB is dark;
the stage forced to LIGHTS_OFF (op 14 sub 2) makes it dark. Measured over
the data line with the daemon paused, the board awake on battery since
the 19:44 boot (the lights dark on purpose for the minutes it took, which
JD saw):

| | lit, the ladder held ACTIVE | scan-only | lit again after the exit |
|---|---|---|---|
| slots a second (page 7, 10-15 s windows) | 3743.3 | 1598.9-1599.1 (the 625 µs slot) | 3742.8-3743.0 |
| missed slots | 0 | 0 | 0 |
| pulses emitted / omitted | 56,176 / 0 | 0 / 0 | 56,168-56,175 / 0 |
| handler mean, CPU share | 52.5 µs, 19.6% | not sampled (the LED path samples) | 52.6 µs, 19.7% |

The mask took the moment the stage went dark (`applied` 1 and scan-only
in force 1.5 s after the force) and left the moment the stage was forced
ACTIVE, the exit by the RGB path with the mask still set (`applied` 0,
scan-only off, the lit rate and the pulses back in the next window, the
columns taken back at once: no wrong-colour or stale row seen). **JD's
key under scan-only (11:04:26, 74 s after the arm): the key count grew
by one with scan-only in force at the read** (the sub-3 reply carries the
state before its own set, so it says what was in force as the key was
seen). The record was unchanged across both runs (spurious 1, epoch
losses 3, invalid services 0, all from the night, below), the lighting
read back unchanged (h178 s219 v177), the force released and Power saver
read back at the end; `scan-only-key.json`, `scan-only-key.log`. The
first attempt (`scan-only-enter.json`, `-exit.json`, `scan-only-check.log`,
10:55-11:01) passed its entry and exit but could not place JD's keys
inside the mask's 255 s limit (a byte of seconds; the "press now"
handshake outlived it, and the mask had lapsed by the exit's read), so
the one-run script watches the key count itself and re-arms the mask
every 200 s. The night before, at 22:39, the same script found the board
asleep: JD's "pressed" had been from memory.

### The wake with the RGB dark (11-02, 11:07-11:10, `wake_read.sh`)

After the scan-only check white idled in Power saver: dim at 60 s, dark at
180 s, deep sleep at 11:07:30 (the logger: 3.29 mA), so the sleep began
with the RGB dark, as every Power-saver sleep does. JD's key at about
11:09:30, and by his eye the lights came straight up in his theme with
nothing else first (the wake's dark-frame handling, the 10-24 fix, on
stage 2's driver). The read inside the next minute (`wake-dark-read.json`,
`wake-dark-read.log`): the deep-sleep record slept 118 counted s and woke
on the key, 0 strays, no reset (the watchdog flags clear; uptime 2,955 s
plus 52,590 s slept is the time since the 19:44 boot); the sleep page's
fourth sleep since the boot; the row handler's record one epoch loss more
(4, one per sleep, INVALID on entry as designed) and two more spurious
invocations (3, below); the 20 s window 3,742.9 slots/s, 0 missed, 0
omitted, 52.47 µs mean, 19.6% share: the handler as before the sleep.
Hutch's Rust decoder (`ak820 health --sched --window 15`, `ae72d2b`) read
the same page in the same read, its window 3,742.8/s and 52.46 µs: the
parity check the stage 2 review's finding 12 asked for, done on a board.
The key kept across the wake is not shown by this (the sleep record's
`key_gain` counts only on a bench-armed sleep); that gate stays owed.

**The record since the boot (19:44 11-01 to 11:10 11-02: 15.4 h, 14.6 of
them asleep, 4 deep sleeps, case 3's two re-attaches, the holds and the
scan-only runs):** 10.42 M slots, 1,599 missed (0.015%), 83 pulses
omitted, the longest run of omissions 1, latency max 104.9 µs, elapsed
max 207.8 µs (161.8 at 20:10 11-01: a longer run sometime in the night,
unattributed), elapsed min 26.6 µs, epoch losses 4 (the sleeps), spurious
invocations 3 (a second entry inside a slot already serviced, counted and
left without a pulse, `rowisr.c`'s step 1; one in the night, two around
the 11:07 sleep or its wake; benign by design, the count is the
diagnostic), invalid services 0, no stall >= 25 ms, loop gap max 8 ms.

### The detector flash and the silence set (11-02, 16:40-16:44, `preflash_read.sh`, `flash.sh`, `silence_check.sh`)

JD's key and his go at 16:40. **The last read of the `b120a2069c` run
(`preflash_read.sh`, 16:41, `preflash-read.json`, `preflash-read.log`):**
21 h on white (19:44 11-01 to 16:42 11-02), 53 min of it awake, 6 deep
sleeps (72,233 s, 20.1 h); 11.14 M slots, 2,095 missed (0.019%), 108
pulses omitted, the longest run of omissions 1, latency max 106.9 µs,
elapsed max 208.3 µs, epoch losses 6 (one per sleep), spurious
invocations 3 (unchanged across the last two sleeps), invalid services
0, no stall >= 25 ms, loop gap max 8 ms, 302 key presses. The wake ring
(op 24 slots 0-7) named the coordinator session's 11:31 self-wake: wake
#4, reason strays, 1,000 strays inside one counted second 911 s into the
sleep (about 1,095 s by the PCF), no key pin, the column ports' GPIO
interrupts (IRQ 29 and 31) pending in ISPR with nothing enabled outside
the wake set; the board awake 3.1 s and asleep again until JD's key
(15,396 counted s). The sleep loop never clears the port lines' NVIC
pending bits, so one pending line makes every later WFI return at once:
one event, counted a thousand times (the coordinator's reading of the
code; Warren's path, `plans/BACKLOG.md`, "A stray-wake storm").

**The flash (`flash-detector.log`, 16:42:25-16:42:47):**
`via-dev-5c0e6249d0-20261102-134106.bin`; the keymap (720 B over 4
layers), the profiles and the live settings restored and read back, the
lighting through the live record, the battery log saved, the token
`0x60d4a06b` read back at 16:43:24; the clock left to the daemon.

**The silence set (`silence-check.log`, `silence-check.json`,
16:43:24-16:44:17): 16 of 16 as the plan predicted.** Over the data
line with the daemon paused, a silence of every interrupt from the
housekeeping task (op 28 sub 7) at each length, and the record's deltas
across it (the spin's own count of CT16B5 is the length column):

| asked (ms) | the spin's count (ms) | losses | by | missed slots | invalid services |
|---|---|---|---|---|---|
| 5 | 5.003 | 0 | exact | 18 | 0 |
| 7.5 | 7.499 | 0 | exact | 28 | 0 |
| 7.9 | 7.899 | 0 | exact | 29 | 0 |
| 8.1 | 8.101 | 1 | the guard, gap 8.117 | 0 | 2 |
| 8.5 | 8.501 | 1 | the guard, gap 8.528 | 0 | 2 |
| 20 | 20.000 | 1 | the guard, gap 20.011 | 0 | 2 |
| 100 | 100.000 | 1 | the guard, gap 100.064 | 0 | 4 |
| 200 | 200.000 | 1 | the guard, gap 200.043 | 0 | 4 |
| 350 | 350.000 | 1 | the frame counter, spans 1/351 | 0 | 1 |
| 700 | 700.000 | 1 | the frame counter, spans 1/700 | 0 | 1 |
| 1,049 | 1,049.003 | 1 | the frame counter, spans 1/1,049 | 0 | 1 |
| 1,000 | 1,000.000 | 1 | the guard, gap 301.0 | 0 | 4 |
| 2,048 | 2,048.000 | 1 | the guard, gap 300.4 | 13 | 4 |
| 7,000 | 7,000.000 | 1 | the guard, gap 9.5 | 0 | 2 |

No spurious invocation and no bus-event rejection in any case, and each
report named the run it came from. 350, 700 and 1,049 ms are the tick's
349.5 ms aliases: the guard saw a millisecond and the frame counter the
silence (the spans column: the extension's ms against the frames').
2,048 ms is the frame counter's own alias, held by the guard. The 13
slots missed around the 2,048 ms case (the only rejected case with any)
are unattributed. With the data cut (the silence armed with a 5 s delay,
the data off, the silence on battery with the bus suspended, the data
back on for the read): 20 ms two losses (the suspend's bus event and
the guard's own), 350 ms one loss (the bus event's alone) with the
silence undetected, the declared limit. Before the set, 44 s after the
boot, the record held one loss and one invalid service (the guard's
last gap 155.7 ms; the boot or the restores, unattributed). The health
counters were reset at 16:44:17, white slept on its own at 16:46:47
(3.9 mA on the logger); the next read (`wake_watch.sh` waiting on the
logger for JD's key, then `wake_read.sh wake-detector-read`) is the
spurious count across one wake, alone.

## Files

- `session.sh`, `session.log`: the six attempts and the clean run; `run-base.log`, `run-stage1.log`, `base.json`, `stage1.json`, `compare.txt`, `flash.log`.
- `settings-before.json`, `lighting-before.json`: the last run's dumps (restored); `settings-after-probe.json`.
- `dark_probe.py` / `dark_probe2.py` and their logs: the probes; `dark_after_sleep.*`: the aborted slept-board test (its relay wake is the third charge); `peek.log`: an HC_PEEK attempt that found white asleep.
- `fix_check.sh`, `fix_check.log`: the fix's flash and holds; `base_fix_check.sh`, `base_fix_check.log`: the base plus the fix, and stage 1 plus the fix back.
- Stage 2: `flash-stage2.log`, `run-stage2.log`, `stage2.json`, `compare-stage2.txt`, `sched-after-stage2-flash.txt`, `health-after-stage2-flash.txt`, `sched-after-stage2-run.txt`, `record-after-stage2-run.txt` (its sub-5 fields misread by 4 bytes, see above); the fix: `flash-stage2fix.log`, `run-stage2fix.log`, `stage2fix.json`, `compare-stage2fix.txt`, `sched-after-stage2fix.txt`; `power_saver_back.sh`, `power_saver_back.log`, `settings-after-mode.json`; `lighting-restore.log`, the backup put back at 21:13.
- `battery-before.txt`, `battery-after.txt`, `health-after-flash.txt`.
- 11-02: `scan_only_check.sh` (enter/exit, the first attempt: `scan-only-enter.json`, `scan-only-exit.json`, `scan-only-check.log`), `scan_only_key.sh` (the one-run check: `scan-only-key.json`, `scan-only-key.log`), `wake_read.sh` (`wake-dark-read.json`, `wake-dark-read.log`).
- 11-02 afternoon: `preflash_read.sh` (`preflash-read.json`, `preflash-read.log`), `flash-detector.log`, `silence_check.sh` (`silence-check.json`, `silence-check.log`), `wake_watch.sh` (the logger-driven wake read: `wake-detector-read.json`, `wake-detector-read.log`); `wake_read.sh` takes an optional label since 16:45 so a second read keeps the first's JSON.

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
- Across a rejected gap the missed-slot count reads 0 by design (the
  re-prime re-bases the slot count and the invalid services carry it);
  compare losses and invalid services there, missed slots only across an
  accepted one.
- "Harmless" out-of-bounds reads are not: the plan's and the audit's note
  on `led_state[255]` cost 1.3 mA at dark on one layout and an unknowable
  phantom on the other.
