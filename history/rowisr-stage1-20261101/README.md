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

**The wake read (`wake_watch.sh`, then `wake_read.sh wake-detector-read`,
19:05:58-19:06:39, `wake-detector-read.json`, `wake-detector-read.log`,
`wake-watch.log`):** white slept on its own at 16:46:47 and JD's key
woke it at 19:05:58 (the logger: 3.4 mA to 48.5 mA), the watcher's read
6 s later. The deep-sleep record: woke on the key (column bit p2 0x10),
slept 6,851 counted s (8,405 by the PCF, 2.3 h), no stray, no reset, the
first sleep since the boot. The row record since the 16:44:17 reset:
epoch losses 2 (the data cut's suspend at 16:44:17, a bus event, and the
sleep, each one by design), invalid services 1, spurious invocations 1,
late omissions 4, no stall >= 25 ms, 17 key presses. So the spurious
count tracks the sleep and wake and not the silences: 0 across the
sixteen silences, 1 across this one sleep and wake, 3 across stage 2's
six (two of them around the 11:07 sleep). A second entry inside a slot
already serviced, at the wake where CT16B4 restarts, is the reading;
counted and left without a pulse, the count stays the diagnostic. The
20 s window after it: 3,743.5 slots/s, no slot missed, no pulse omitted,
the handler's mean 63.3 µs (52.5 at the 11:10 read on stage 2, 60 at the
11-01 measure; the detector's per-slot snapshot is the candidate for the
difference, not separated from the lighting's content: the warm
windows' job), CPU 23.7%; the maxima since the reset latency 82.5 µs,
elapsed 206.3 µs. White back in its standing state at 19:06:39 and
released.

### The warm windows (11-02, 20:43-20:45, `warm_windows.sh`)

The runner's three health windows on the detector build, the holds
skipped (`warm-windows.log`, `run-detector.log`, `detector.json`,
`compare-detector.txt`; the ladder held at Always on, JD's theme, the
daemon paused), against stage 2's of 11-01 (`stage2.json`):

| window (24 s) | stage 2 | the detector | change |
|---|---|---|---|
| idle, the handler's mean (page 4, µs) | 59.8 | 78.8 | +19.0 |
| repaint (the debug page toggled each second) | 59.8 | 78.8 | +19.0 |
| pcf (clock-chip transactions every 250-300 ms) | 59.7 | 78.8 | +19.1 |
| CPU share, idle (%) | 22.4 | 29.5 | +7.1 points |
| the handler's max (idle / repaint / pcf, µs) | 144 / 144 / 117 | 133 / 165 / 160 | |
| slots/s, rows/row/s, row gap max, loop gap, stalls >= 25 ms | 3745 / 208.1 / 5 ms / 3 ms / 0 | the same | none |

**So the detector costs the handler 19 µs a slot by page 4's hook,
7 points of CPU.** Page 7's own elapsed shows +10.8 (52.5 at the 11:10
read on stage 2; 63.3 at 19:06 and again at 20:43 here, the latter with
the ladder at DIM, so the lighting level is not in it); the 8 µs between
the two measures is not read from the code yet (page 4's hook brackets
the whole vector). The shortest handler rose from 26.6 to 30.8 µs. The
slot rate, the row rate, the row gaps, the loop gap and the stall count
did not move, and the page 7 windows before and after missed and omitted
nothing. The object tells where it goes: the handler (`Vector90` in
`rowisr.o`) carries seven library divides, two of them the detector's and
on every slot (the extension's span converted to ms for the judgment at
step 1 and again at the exit, `(dext * 2 + 187) / 375`, `__aeabi_uidiv`
each) and five from stage 2 (the colour from `cur_row % 3`, the
boundaries-crossed count's `(dt + half) / slot_ticks` with its 64-bit
path, `half = slot_ticks / 2`). The next commit judges in ticks (the
frames' milliseconds times 187.5 against the extension's ticks, the
tolerance in ticks), so the hot path carries no divide of the detector's,
and the record's milliseconds are converted off it.

The link in the windows: ACK timeouts grew 7 and 4 across the 24 s
windows (62 to 73 since the boot, 148 to 167 sent) where stage 2's grew
0. Not the handler's: the coordinator's reading across the same runner's
windows on every build (timeouts per frames sent, idle to repaint and
repaint to pcf: the base 2/5 and 3/5, stage 1 6/6 and 5/5, stage 2 0/6
and 0/5, the detector 7/5 and 4/5) makes stage 2's zeros the outlier;
the UART overrun count is 0 on every build and UART2 sits above the row
interrupt, so a longer handler cannot delay a receive; and the cause is
the module's bimodal ACK turnaround (`docs/wireless.md`, "The 50%
tx_timeouts rate": about half the ACKs past the 10 ms deadline, a slow
one taking two or three retries, the slow mode when the module is idle).
Since the boot the detector reads 73 of 167, mostly wakes and 5 s polls
(the doc's per-wake figure, 4 of 9, is the same); stage 2's whole run
311 of 1,157 with typing keeping the module busy. The
cumulative page 7 from the 16:44 reset to 20:43: 1.67 M slots, 583
missed (0.035%), 40 omitted, latency max 89.6 µs, elapsed max 206.3 µs;
across the pcf window and the restores, 1,249 missed in 166 k slots (the
clock chip's hold-off, by design). The runner put Power saver back;
white was dark at stage 3 by the end and released at 20:44:55.

### The trim's flash and its windows (11-02, 23:19-23:22, `trim_on_wake.sh`, `trim_flash.sh`): no gain, the divides were not the cost

JD's go came at 23:03 with white asleep, so a watcher on the power logger
(`trim_on_wake.sh`: two samples over 20 mA, above the Mac's lock-light
bursts into the sleeping module at ~14 mA) caught his key at 23:19:18
(46.3 mA) and ran `trim_flash.sh`: the token before 0x60d4a06b, the flash
23:19:23-23:19:52 with its backups and restores, the token after
0x1a291156, then `warm_windows.sh trim 0x1a291156`.

| Window, page 4 | stage 2 | detector | the trim |
|---|---|---|---|
| idle, mean us | 59.8 | 78.8 | 80.0 |
| idle, CPU % | 22.4 | 29.5 | 29.9 |
| repaint, mean us | 59.8 | 78.8 | 80.0 |
| pcf, mean us | 59.7 | 78.8 | 79.9 |
| page 7, `win_elapsed_mean_us` | 52.5 | 63.3 | 63.9 |

Against the detector every gate is within tolerance (+1.5%); against
stage 2 the same six metrics fail. **The two divides were not the cost.**
Stage 2's own vector, rebuilt from `b120a2069c` for the comparison
(`stage2.elf`), calls `__udivsi3` twice, `__aeabi_uldivmod` twice and
`__aeabi_uidivmod` once: stage 2 had divides on every slot and was the
fast one. The vector grew from 945 to 1,449 instructions and the 20 kHz
tick's `rowisr_time_observe` from 49 to 145, but the slot's common path
through the new code is on the order of 150 instructions, not the 900
cycles the 19 us are. What remains is the reads themselves: the handler
reads three USB registers at the entry snapshot and three at the exit
(FRMNO, CFG, INSTS), and the tick reads FRMNO every 50 us at priority 2,
preempting the handler at 3 about 1.3 times a slot; at ~2 us a read that
is the whole 19, and the growth splits the way the reads do (10.8 us
inside page 7, where the entry's reads are; 8.2 outside, where the
exit's are). Measured next: `95ef5cbc5d` (token 0xda2a24d5, heap gap
408 B) stamps T_SCHED's TC at seven points of the handler (op 28 sub 11)
and times 256 masked reads of each register (sub 10,
`rowisr_diag.py readcost | sections`).

**Two span rejections in the record** (165,641 judged; the detector run
had none in 165 k, the silence check none in 171 k): the last with 0 ms
by the extension and 256 by the frames, two entry snapshots 267 us apart
whose frame numbers differed by 256. A torn read of the 11-bit FRMNO at a
0x0FF to 0x100 carry fits exactly (the low byte still 0xFF with bit 8
already set); a real jump of 256 frames in 267 us cannot happen. Each
costs one epoch loss and one or two invalid services, nothing the LEDs
see. If it recurs, the fix is to read FRMNO until two reads agree; noted
in the plan. ACK timeouts 8/10/13 since the boot across the three windows
(the detector run's 62/69/73): the module's, as before.

### The cost diagnostic (11-03, 00:06-00:08, `diag_on_usb.sh`, `diag_flash.sh`): the reads are free, the sections say it is the instruction count

JD's go at 23:50 with white asleep and the power logger about to leave the
bench for the presser rig's soldering, so the watcher used USB presence
instead (`diag_on_usb.sh`: the daemon paused, the data line on, a
sleeping board does not enumerate and a woken one does within seconds).
His key came at 00:06:22; the flash 00:06:24-00:06:57 (token before
0x1a291156, after 0xda2a24d5), then the readings over the data line.

**A register read costs nothing** (`readcost-diag.txt`, op 28 sub 10: 256
masked reads of one register, the least of 8 trials, in HCLK cycles a
read with the loop's own six instructions included): USB FRMNO 11, USB
INSTS 11, USB CFG 11, CT16B5's TC 12, a RAM word 11. The USB block's
registers read as fast as RAM; the second theory was wrong too.

**The handler's sections** (`sections-diag-1.txt`, `-2.json`, op 28 sub
11: T_SCHED's TC stamped at seven points, the six deltas summed over the
services that reached the exit; two 10 s windows of 37,474 and 37,487
services, identical to 0.03 us):

| Section | mean us |
|---|---|
| 0: the entry snapshot (the lock, the flag, `take_snapI`) | 7.33 |
| 1: step 1's checks and the frame counter's judgment | 9.56 |
| 2: steps 2 to 5 (the mux rows, the scan, the match registers) | 37.89 |
| 3: step 6, the arm | 10.88 |
| 4: the exit snapshot | 5.79 |
| 5: the exit judgment and the record | 8.74 |
| total, stamp 0 to stamp 6 | 80.20 |

Page 7's window read 64.6 us and 24.2% CPU with the stamps in; page 4
since the boot 85.7 us (284,619 entries, 4,575,099 ticks; the boot's
first seconds and the restores' USB traffic in it). The record was clean:
epoch losses 1 and invalid services 1 (the boot's), spurious 0; the frame
counter judged 283,631 intervals with none rejected, so the trim run's
two 256-frame rejections did not recur here (one in a few hundred
thousand, or rarer).

**What it means.** The four sections that are the detector's, both
snapshots and both judgments, sum to 31.4 us, with no single hot spot:
7, 10, 6 and 9. Stage 2 had a smaller version of each (its entry snapshot
without the frames and the bus, its step 1 without the judgment, its
exit without the judgment), and the growth of 19-20 us is spread across
all four. Since the reads are free, the cost is the instruction count:
the bookkeeping the detector runs every slot (two snapshots of 20 bytes
with the bus state from three registers and the freshness, the validity
conditions, two calls to `boundaries_between`, two to
`usb_distance_ticks`, the record's updates, the 20-byte copy into
`last_snap`) is a few hundred instructions, and on this core, fetching
from flash with wait states and no cache, an instruction costs 3-5
cycles: section 2, stage 2's own LED and scan work of ~300 instructions,
takes 1,819 cycles. The 20 kHz tick at priority 2 lands in whichever
section it interrupts and inflates every one by the same share. The
remedy is structural, not a trim: judge the frame counter every eighth
slot (2 ms, the same alias guarantee, the attribution coarser by 2 ms)
and drop the exit judgment (the next entry's judgment covers an aliasing
silence inside the handler; one elapsed sample is what it protected).
Designed next, in the plan.

### The exit-only build's flash (11-03, 02:26-02:30, `exit_on_usb.sh`, `exit_flash.sh`, the presser's wake): 6.6 us back by the stamps, page 4 blind to it through the sections' own commit

JD's advance go for the night at ~02:25 (the presser built, Hutch's
contact check passed, white released at 02:17). The watcher armed at
02:26:13; the presser's one press of A1 ((0,13), 100.3 ms actual) at
02:26:25 woke white from its deep sleep and it enumerated 4 s later: the
first flash with no hand on the board. The flash 02:26:30-02:27:01 (token
before 0xda2a24d5, after 0x9e2d894a), the readings over the data line,
white back in the standing state at 02:30:25.

**The sections** (`sections-exit-1.txt`, `-2.json`; two 10 s windows of
37,454 and 37,456 services, identical to 0.01 us), against the cost
diagnostic's:

| Section | diagnostic, us | exit-only, us |
|---|---|---|
| 0: the entry snapshot | 7.33 | 7.28 |
| 1: step 1's checks and the frame counter's judgment | 9.56 | 8.80 |
| 2: steps 2 to 5 | 37.89 | 37.63 |
| 3: step 6, the arm | 10.88 | 10.80 |
| 4: the exit snapshot | 5.79 | 2.41 |
| 5: the exit judgment and the record | 8.74 | 6.67 |
| total, stamp 0 to stamp 6 | 80.20 | 73.59 |

**6.6 us back**, where the design said: the exit snapshot 3.4 us lighter
(time only, FRMNO and `usb_gen` beside it, against the full snapshot with
its three USB registers and the freshness) and the exit judgment 2.1 us
(the spans compared once, no bus or freshness verdict). The readcost
unchanged (11, 11, 11, 14, 11 cycles).

**The warm windows** (`exit.json`, `compare-exit.txt`,
`compare-exit-vs-detector.txt`): page 4's mean **80.2 us** in all three
windows, the trim's 80.0, the detector's 78.8, stage 2's 59.8; CPU
30.0%; rows 208.1/s; `row_gap_max` 5, 5 and 9 ms; no stall. Page 4 saw
none of the 6.6 us, and the arithmetic says why: page 4's hooks bracket
the stamps plus what lies outside them, and this dev build still carries
the sections' instrumentation, whose commit (six unwrapped subtractions
and sums, ~70 instructions) runs after stamp 6 at 3-5 cycles an
instruction: ~6 us a slot. The trim, with no sections, read 80.0; this
build reads 73.6 by its stamps plus ~6 of commit plus the hooks: 80.2.
So the saving is real by the handler's own stamps, and page 4 will show
it only on a build whose sections are compiled out: the next build makes
them opt-in (`ROWISR_SECTIONS`), off in the dev build JD runs. Page 7's
window (entry snapshot to exit snapshot, no stamps' commit in it) read
59.8 us after the runner against the trim's 63.9 and the diagnostic's
64.6: the same saving, seen from inside.

**The silence set** (`silence-check-exit.log`, `silence-check-exit.json`):
**15 of 16 as predicted.** The fourteen USB cases exactly as on the
detector (5, 7.5 and 7.9 ms exact; 8.1 ms the guard's first rejection at
a gap of 8.123 ms; 8.5, 20, 100 and 200 ms the guard; 350, 700 and
1,049 ms the frame counter, the spans 1/351, 1/700 and 1/1,050 ms;
1,000, 2,048 and 7,000 ms the guard, the residues 301.0, 300.4 and
9.5 ms; the spin within 3 us of the asked length on every case), and
the battery 350 ms case (one loss, the bus event's). **The battery 20 ms
case FAILED on the count: 4 losses, not 2** (the suspend's bus event, the
guard's own, and **two frame-counter rejections whose last spans read 0 ms
by the extension and 256 by the frames**: `usb_last_dt_ms` 0,
`usb_last_df_ms` 256 in `usb_after`). That is the signature the trim run
showed twice in ordinary running (`usb-trim-after.txt`: 2 of 165,641
judged, the same 0/256) and the diagnostic and this run's own windows
never (0 of 283,631; 0 of 165,610 after the runner): **a torn read of
FRMNO at a byte carry.** One torn read explains a pair: 0x0FF read as
0x000 while the carry into bit 8 is in flight gives that interval a
frame span of -255 (1,793 modulo 2,048) and the next, from the torn
baseline the re-prime adopted, +256; both rejected, two false losses.
Rare (four in some 600,000 judged intervals tonight, the two of them in
this case's window by chance) and harmless to the keys and the light,
but a false loss is a false silence, so the next build reads FRMNO
until two consecutive reads agree (one extra load, ~11 cycles, on the
snapshot) and carries a dev scan (op 28 sub 14) that reads the register
back to back for seconds and records every step other than 0 or +1
with its pair of values, to see the tear itself.

The record after the runner (`record-exit-after.txt`): losses 0, invalid
0, spurious 1, omissions by the arm deadline 43 (the trim's 37 after its
runner: the pcf window's hold-offs; 1 before the runner in 20,293
services). The frame counter after: 165,610 judged, none rejected.

### The presser's short-tap baseline on the exit-only build (11-03, 02:37-02:43, `presser_gate.sh exit`): exact to 10 ms, the boundary at 8

The scan's gate counted at the board, the first run of the rig the plan
asked for ("The key-press rig"): batches pressed from the logger's REPL
(`scripts/presser_repl.py`, the dwell on the QT Py's clock, ~1 ms
resolution, the actual min and max reported), the counts read before and
after each over the data line with the daemon paused (`presser_count.py`:
health page 2's `key_presses`, after debounce, and page 3's `raw_edges`,
before it; a press is one key_press and two raw edges). The board woke
from its deep sleep on the script's own first press. The old scan (stage
2's, the interim scanner with its mode writes) on `f0ec5c68df`
(`presser-gate-exit.json`, `.log`):

| Batch | dwell asked, actual (us) | key_presses | raw_edges |
|---|---|---|---|
| A1 (0,13) x200, 75 ms gap | 25 ms, 25,054-25,482 | 200 of 200 | 399 of 400 |
| A1 x200 | 15 ms, 15,045-15,441 | 200 of 200 | 400 of 400 |
| A0 (3,14) x200 | 25 ms, 25,054-25,451 | 200 of 200 | 399 of 400 |
| A1 x100 | 12 ms, 12,054-12,451 | 100 of 100 | 199 of 200 |
| A1 x100 | 10 ms, 10,040-10,559 | 100 of 100 | 200 of 200 |
| A1 x100 | 8 ms, 8,056-8,453 | **76 of 100** | 199 of 200 |
| A1 x100 at 25 ms with A0 held | 25 ms | 101 of 101 | 202 of 202 |

**Every press of 10 ms or more registered, on both channels and with a
cross-row key held** (the chord: A0's own press and release counted once,
no phantom on either column, no leak); **at 8 ms a quarter are lost**,
the debounce boundary (sym_defer_pk, 5 ms, a row sampled every 800 us):
the old rig put it near 10 ms, and this is the number stage 3 must not
worsen. `raw_edges` short by one in three of the batches is the consume's
known undercount (the unlocked compare, BACKLOG.md), which stage 3's
locked XOR removes: on it the column must read exact. `row_gap_max`
10 ms through the run (the counters not reset before it; the script
resets them now). An earlier launch found white asleep and stopped: the
script now wakes it with one press first.

### Deep sleep's wakes with the waking key kept, by the presser (11-03, 02:52-03:10, `deep_wake_presser.sh 5 exit`): 5 of 5

The gate stage 1 and stage 2 owed, run with no hands: white left to
sleep (Power saver, 3 min after the last key, the data line off; asleep
at 3.3-3.7 mA on the logger), one press of A1 ((0,13), 100 ms), the data
line on, white present within seconds, the counts read, the data line
off again; a cycle 0 for the baseline read. The verdict is the board's
`key_presses`, +1 a cycle (the Mac would lose the first key after a
30 min sleep anyway, the module's link drop; these sleeps were 3 min).
`deep-wake-exit.json`:

| Cycle | woke | press command to present, s | key_presses | losses | spurious | frame rejects / bus events, since the reset |
|---|---|---|---|---|---|---|
| 1 | 02:56:28 | 10.3 | +1 | +2 | +0 | 2 / 5 |
| 2 | 02:59:46 | 10.4 | +1 | +2 | +0 | 2 / 6 |
| 3 | 03:03:04 | 10.4 | +1 | +2 | +0 | 2 / 7 |
| 4 | 03:06:21 | 10.4 | +1 | +2 | +0 | 2 / 8 |
| 5 | 03:09:39 | 10.4 | +1 | +2 | +0 | 2 / 9 |

**Every waking key kept, no spurious invocation, two losses a sleep
(the exclusion's entry and its end, by design), one bus event a cycle
(the data line's reconnection), and the frame counter's rejections
steady at 2 through the five sleeps** (the torn pair from before the
run; none new). The "press command to present" column includes the
REPL's ~7 s of setup before the pulse; the wake itself, from the
earlier runs, is 3-4 s to the enumeration.

### Stage 3 on white (11-03, 03:12 on, `stage3_flash.sh`, `3673b234f0`): the scan without mode writes, the presser's gates exact, the frame counter's tear seen

The flash at 03:11:45-03:12:16 (the token before 0x0a2f280e's predecessor
0x9e2d894a, after 0x0a2f280e), white woken by the presser, the status
clean (`status-stage3.json`: no column-map fault, no hardware fault, the
prime complete, the row line enabled, the settle 96 ticks).

**The frame counter's tear, seen directly** (`frmscan-stage3.txt`, op 28
sub 14, 25 s of back-to-back reads from the housekeeping task): 16,776,704
reads, 23,544 steps of +1, **48 other steps, the pairs kept 0x7FF -> 0x700,
0x700 -> 0x000, 0x1FF -> 0x100**. FRMNO updates in two steps at a byte
carry, the low byte first, and a read between the steps returns the torn
value; 48 such reads over the ~92 byte carries in the scan, each tear two
"other" steps, so about a quarter of the carries were caught with reads
some 0.35-0.5 us apart: a torn state of roughly 4-6 HCLK cycles, one
12 MHz USB clock. That is the hardware fact behind the 0/256 ms
rejections. The first stage 3 build read the register twice back to back
(a third time on disagreement), and its first hour still logged **23
rejections where 3 were expected** (the silence set's 350, 700 and 1,049
ms), the last at spans 0/256: two adjacent loads can both land inside a
4-6 cycle torn state and agree. The fix in `67a4ccf2b3`: the two reads
twelve cycles apart (and the third, after a disagreement, twelve more);
flashed next.

**Six-row fairness** (`rows-stage3.txt`, 20 s): 4,163, 4,164, 4,164,
4,163, 4,163, 4,163 samples a row, the spread 1 (208.2 a row a second);
`raw_edges` 0 over 35,358 consumes with nothing pressed.

**The short-tap gate with the counts at the scan**
(`presser-gate-stage3.json`, 03:13-03:16; the counters reset first, so
`row_gap_max` is the run's):

| Batch | dwell, actual (us) | key_presses | raw_edges | at the scan (presses/releases) | elsewhere | row_gap_max |
|---|---|---|---|---|---|---|
| A1 (0,13) x200 | 25 ms, 25,054-25,482 | 200 of 200 | **400 of 400** | 200/200 | 0 | 5 ms |
| A1 x200 | 15 ms, 15,045-15,502 | 200 of 200 | 400 of 400 | 200/200 | 0 | 5 ms |
| A0 (3,14) x200 | 25 ms, 25,054-25,451 | 200 of 200 | 400 of 400 | 200/200 | 0 | 5 ms |
| A1 x100 | 12 ms, 12,054-12,451 | 100 of 100 | 200 of 200 | 100/100 | 0 | 5 ms |
| A1 x100 | 10 ms, 10,040-10,437 | 100 of 100 | 200 of 200 | 100/100 | 0 | 5 ms |
| A1 x100 | 8 ms, 8,056-8,453 | **69 of 100** | 200 of 200 | 100/100 | 0 | 5 ms |
| A1 x100 at 25 ms, A0 held | 25 ms | 101 of 101 | 202 of 202 | 100/100, A0 1/1 | 0 | 5 ms |

Every press and release reached the matrix (the scan's own count) and
every transition reached debounce (`raw_edges` exact now, the consume's
undercount gone), nothing pressed itself anywhere, the chord clean, the
worst row gap 5 ms. At 8 ms, 69 of 100 against the old scan's 76: the
scan saw all 100 and debounce dropped 31, so the loss is debounce's
against the main loop's ~3 ms pass (sym_defer_pk reports a key only once
its raw state has held 5 ms across the loop's checks, and an 8 ms press
can release before the check that would have reported it), the same
mechanism on both builds; 69 against 76 is inside one batch's noise and
the boundary batches are repeated on the next flash to say more.

**Q1's settle sweep** (`settle-sweep-stage3.json`, 03:42-03:50, the chord:
A0 held, 100 presses of A1 at 15 ms; the counts at the scan and after
debounce; 1.5 s idle at each setting first): **19 of 19 exact**, with
JD's lighting at 96, 48, 24, 12, 6, 3 and 0 ticks and solid red, green and
blue at full at 96, 24, 6 and 0: no phantom, no miss, no idle press at
any setting, down to no settle at all. A pressed column falls through its
diode into the driven-low row faster than the handler can read it, and
the unpressed ones were left high by the terminal match with nothing to
rise through, as D3 step 3 argued. The default stays 96 ticks (2 us, 0.67
us a slot averaged over the three slots): all of it margin. The sweep
was delayed 26 min by a hung `uhubctl` (below).

**The silence set** (`silence-check-stage3.log`, 04:12): the fourteen
USB cases exactly as on the detector and the exit-only build (5, 7.5 and
7.9 ms exact; 8.1 ms the guard at 8.133 ms; 8.5, 20, 100 and 200 ms the
guard; 350, 700 and 1,049 ms the frame counter at 1/351, 1/700 and
1/1,049; 1,000, 2,048 and 7,000 ms the guard at 301.0, 300.5 and 9.5 ms).
**The two battery cases did not run**: the last key was 23 min back, so
the ladder deep-slept the board the moment the data line went off for
the first cut, and the set's runner found no board after it (the script
now holds the ladder at Always on through the cuts, and wakes a sleeping
board with one press first, as every runner does now). **The warm
windows did not run** for the same sleep (the runner wakes it now). Both
go on the next flash.

**Two hangs of `uhubctl`** (03:16-03:42 and 03:50-04:12): an `-a on`
issued within a second of another script's `-a off` on the same port
never returned, twice, 26 and 22 min lost each time with white awake and
lit; killed by hand, the on had taken effect. Every runner now pauses 3 s
before its first on and bounds every `uhubctl` with `timeout 20`.

### Deep sleep's wakes on stage 3 (11-03, 04:14-04:31, `deep_wake_presser.sh 5 stage3`): every key kept, one spurious invocation at a wake

The same gate on `3673b234f0` (`deep-wake-stage3.json`), the board
asleep at 3.3-3.8 mA before each press:

| Cycle | woke | key_presses | losses | spurious | frame rejects / bus events, since the gate's reset |
|---|---|---|---|---|---|
| 1 | 04:17:59 | +1 | +2 | +0 | 23 / 4 |
| 2 | 04:21:16 | +1 | +2 | +0 | 23 / 5 |
| 3 | 04:24:34 | +1 | +2 | +0 | 23 / 6 |
| 4 | 04:27:52 | +1 | +4 | +0 | 25 / 7 |
| 5 | 04:31:09 | +1 | +2 | +1 | 25 / 8 |

**Every waking key kept (5 of 5), two losses a sleep by design, one bus
event a cycle.** Two things beside it: **cycle 4 added two
frame-counter rejections** (23 to 25), the adjacent-read build's torn
pair again (the spaced reads of `67a4ccf2b3` flash next); and **cycle 5
counted one spurious invocation** (an entry inside an epoch already
serviced, counted and left before any verdict), which the script's
verdict calls a FAIL. The same was seen once across a wake on the
detector build (11-02 19:06, "spurious 1 across the wake") and never
across a silence; harmless by construction (nothing is reconstructed or
armed on it), noted as the wake's.

### Stage 3b on white (11-03, 04:32-04:51, `stage3b_flash.sh`, `67a4ccf2b3`): the spaced reads hold, the silence set 16 of 16, page 4 at 71.6 us

The spaced frame-counter reads (twelve cycles between the two, twelve
more before a third) flashed at 04:31:31-04:32:02 (token 0x0a2f280e to
0x4326ec84), white woken by the presser.

**The frame counter, 10 min with nothing injected**
(`usb-stage3b-10min.txt`, `record-stage3b-10min.txt`): **2,247,661
intervals judged, none rejected**; losses 0, invalid 0, spurious 0,
omissions 0. The adjacent-read build rejected ~4 in the same time (23
in its first hour). After the whole run (the runner's windows, the
silence set, the gates): 165,780 more judged since the set's reset,
none rejected, the record's last rejection 0/0 since the boot. The tear
is beaten by the spacing.

**The short-tap gate** (`presser-gate-stage3b.json`): the same seven
batches as stage 3's first run, exact at 25, 15, 12 and 10 ms on both
channels and with the chord (every press and release counted at the
scan, `raw_edges` exact, nothing elsewhere, `row_gap_max` 5 ms); **75 of
100 at 8 ms**. **The boundary batches** (`presser-gate-stage3b-boundary.json`):
A1 at 8 ms 72, 73 and 71 of 100, A0 at 8 ms 69; A1 at 10 ms 100 and 100,
A0 at 10 ms 100, the scan exact in all seven. So stage 3's 8 ms figure
is **72 +/- 2 of 100 over six batches** (69, 75, 72, 73, 71, 69) against
the old scan's one batch of 76: the same boundary, set by debounce
against the main loop's pass, not by the scan, which counted every
press on every batch.

**The silence set** (`silence-check-stage3b.log`, `.json`): **16 of 16**
as predicted, the ladder held at Always on through the two data cuts
and put back; the battery 20 ms case at its two losses (the suspend's
bus event and the guard's own) with no frame rejection, the case the
exit-only build failed through the torn read; 350 ms on battery one
loss (the bus event's), the silence undetected, the declared limit.

**The warm windows** (`stage3b.json`, `compare-stage3b.txt`,
`compare-stage3b-vs-detector.txt`): **page 4's mean 71.6 us a slot in all
three windows, CPU 26.8%** (the detector 78.8 and 29.5; the trim, the
diagnostic and the exit-only build 80.0-80.2 with the sections' commit
in; stage 2 59.8 and 22.4); the handler's max 122.7, 149.3 and 122.7 us;
rows 208.1/s; `row_gap_max` 5, 5 and 9 ms; no stall. The compare's
"FAIL" lines are its +/-3% band on a 9% improvement over the detector
and a 20% rise over stage 2: what remains over stage 2 is the
per-slot judgment, the plan's open question for JD (two silences within
2 ms as two, ~8 us). The record after the runner: losses 0, invalid 0,
spurious 1, omissions by the arm deadline 13 (the pcf window's
hold-offs; the trim's 37 and the exit-only build's 43 after their
runners), no missed slot.

The soak watch began at 04:51 (`soak_watch.sh stage3b`: a press and a
read every 20 min, white sleeping between), and stage 4's flash took
over at 04:52.

### Stage 4 on white (11-03, 04:52-05:07, `stage4_flash.sh`, `c2bc29c745`): the transaction unmasked runs a read to 5.5 ms, so the 5 ms paths keep the hold-off (stage 4b)

D6 as first built: the clock chip's transaction with the row ISR running
through it (no `sn32f2xx_row_irq_hold` in `ak820_i2c_xfer_begin/_end`),
the writer's bracket width on status page 4. Flashed 04:52:34-04:53:05
(token 0x4326ec84 to 0x8a213e0e), the pages read 20 s after the boot
(`rtc-status-stage4-0.txt`: `i2c_max_cycles` already 183 ILRC cycles,
~5.5 ms, from the boot's reads under the restores' flash writes;
`overrun-status-stage4-0.txt`, op 22's per-kind whole calls: a 1-byte
read 2.37 ms, a 7-byte read 5.61 ms, none failed).

**The burst with presses through it** (`burst-presses-stage4.txt`,
`rtc-status-stage4-burst.txt`): 300 7-byte PCF reads 40-80 ms apart
(dev op 23, which runs them on the deep sleep's 5 ms deadline) with 200
presses of A1 at 25 ms running through them: **the presses exact**
(key_presses +200, raw_edges +400, `row_gap_max` 5 ms, the delivery
under I2C load with the handler running through every transaction),
**but 5 of the 300 reads failed** (`i2c_fail` 0 to 5; op 22's "PCF read
7" 323 calls, 6 failed with the stuck test's one; `i2c_max_cycles` 184,
~5.5 ms, the deadline's edge). Every burst of 10-19 (1,000 reads each,
with the hold-off) had none. So with the handler (27% of the CPU) and
the 20 kHz tick preempting the bit-banged transfer, a 7-byte read runs to
~5.5 ms, about twice its 2.6 ms and not the plan's 3.1-3.6, and the 5 ms
deadline cuts the slowest: the pre-sleep read and the wake's recovery
would fail the same way. **The stuck-bus test** (`stuck-stage4.txt`,
`rtc-status-stage4-stuck.txt`): the transfer ran into its 10 ms deadline
(`i2c_max_cycles` 331, 9.85 ms; one pass >= 10 ms, none >= 25) and the
driver restarted; 20 ordinary reads after it, none failed. **The warm
windows** (`stage4.json`, `compare-stage4.txt`): 70.9 us a slot, 26.6%
CPU (stage 3b's 71.6), the frame counter clean (166,964 judged, none
rejected). **Three sleeps and wakes** (`deep-wake-stage4.json`,
`rtc-status-stage4-before-wakes.txt`, `-after-wakes.txt`): every key
kept, `i2c_fail` unchanged at 6 and `stale_count` 0 across the three
pre-sleep reads and three recoveries on the 5 ms deadline (six
transactions; the burst's rate says one in sixty fails).

**Stage 4b** (`6b90f3b821`): the transactions on the short deadline
(`pcf_short_timeout`: the pre-sleep read, the wake's recovery, the dev
burst that mimics them) keep the hold-off, where the board is dark or
waking anyway; the ordinary 10 ms transactions stay unmasked and lit, the
writer's 8-byte write estimated ~7 ms at the measured stretch and the
night's awake soak to show it (op 22's per-kind maxima every 20 min,
`i2c_fail` to stay flat, the writer's runs and brackets). Codex READY;
flashed at 05:08. The camera gate, a forced write with no dark frame on
USB and off, stays JD's; `pcf-unseen`'s deferral stays until it passes.

### Stage 4b on white (11-03, 05:07-05:19, `stage4b_flash.sh`, `6b90f3b821`): the burst clean, the stuck test as designed, three wakes kept, the awake soak on

The hold-off kept for the 5 ms transactions alone. Flashed
05:07:24-05:07:55 (token 0x8a213e0e to 0x4215c3e2). **The burst with
presses through it** (`burst-presses-stage4b.txt`,
`rtc-status-stage4b-burst.txt`): 300 held 7-byte reads, **none failed**
(`i2c_fail` 0), the 200 presses exact (key_presses +200, raw_edges +400),
`row_gap_max` 9 ms during the held reads (each a ~2.6 ms gap in the scan,
as before stage 4; the plan's gate judges the hold-off's windows apart).
**The stuck test** (`stuck-stage4b.txt`): one failure, its own, the 10 ms
deadline (`i2c_max_cycles` 330), one pass >= 10 ms and none >= 25, 20
ordinary reads after it clean; op 22's spans zeroed after it so the
night's maxima are the healthy ones. **Three sleeps and wakes**
(`deep-wake-stage4b.json`): every key kept, `i2c_fail` unchanged at 1,
`stale_count` 0 (the held pre-sleep reads and recoveries). Two spurious
invocations across the held burst and the first wake, counted and
harmless. **The awake soak** started at 05:19 (`soak_watch_awake.sh
stage4b`: data on, the daemon syncing the clock every 5 min, a read
every 20 min of the handler's record, the frame counter, the health
vitals and stalls, page 2 and 4 and op 22's per-kind whole-call maxima:
`soak-stage4b.jsonl`, the summary lines in `stage4b-flash-run.log`). Its
first read: 170 1-byte reads at 1.76 ms whole-call max, 19 7-byte reads,
none failed, the frame counter 232,279 judged and none rejected.

**The soak's end, 09:35 (4 h 16 min awake, the daemon syncing the clock
every 5 min; `soak-stage4b.jsonl` reads 1-13, the final reads in
`stage4b-flash-run.log`, `health-stage4b-soak-end.txt`):** the frame
counter **57,670,167 intervals judged, none rejected on the spans** (6
for bus events: the data line's cycles), no loss and no spurious
invocation since the wakes (9 and 2), 124 omissions by the arm deadline
(the held reads' hold-offs and the runner's); the clock chip's
**writer 52 runs, 0 restarts, the release error 2 ms, the boundary error
-1 ms, the bracket's width 6-7 ms, no miss**, 51 slews; the unmasked
ordinary transactions' whole-call maxima: **the 8-byte write 4.64 ms (52
calls), the 7-byte read 5.47 ms (19), the 1-byte read 2.38 ms (1,109),
the 1-byte write 1.70 ms (104), none failed** (`i2c_fail` 1, the stuck
test's); the health counters over 10.4 million passes: one pass >= 10 ms
(the stuck test's own), **none >= 25 ms**, the loop gap's maximum 12 ms
and the I2C gap's 9 ms (the stuck test), no watchdog event; three UART
overruns in the night, none during a clock transaction, 1,646 ACK
timeouts on the BT link over the four hours (its long-standing rate).
So the ordinary transactions run unmasked at about half the 10 ms
deadline with the writer settling every time, which is stage 4b's
hands-free gate; the camera's is JD's. White went back to the standing
state at 09:36 for Warren's keep-alive measurements and JD's camera
check.

### The camera run on stage 4b (11-03, 10:04, `camera_runs.sh`): the control's held reads, then the writer's unmasked write, filmed by JD

JD at the desk with the phone at 240 fps, the steps relayed by Hutch.
The dev build has no direct forced-write op (`HC_RTCTEST` is the
instrumented build's), so the write was the clock writer's own,
triggered by the daemon's sync as it started, which the firmware admits
on the data line only after 10 min without a key (pcf-unseen): white
woken by one press at 09:50:13, held awake on the data line with the
daemon paused, nothing touching it after. At 10:04:00.6 the positive
control, 20 7-byte reads 100 ms apart on the short deadline (the row ISR
held off through each: a ~2.6 ms gap in the scan, the dark frames JD saw
after every sync before stage 4); at 10:04:07.2 the daemon started, synced
at 10:04:09 (the board +87.2 ms off after four hours on BT, corrected to
+0.4 ms) and the writer ran its three transactions unmasked right after:
**the writer's runs 52 -> 53, boundary error 0 ms, the bracket's width
7 ms, no miss, STOP clear** (`camera-page4-before.txt`, `-after.txt`,
`camera-runs.log`). The board's side of the gate is met: the write
happened with the LEDs driven throughout. Only the bench's battery
state was filmed (the data line on, no 5 V: the USB-powered case needs
relay 2 and the drain says no). White back in the standing state at
10:04:24 and handed to Hutch for Warren's keep-alive measurements.
⚠️ **The clip is void: the lights were off.** The power log reads
31 mA through the run (awake and dark; lit it is 49-54 mA): Power
saver's ladder turns the RGB off 3 min after the last key, and the
wake press was 14 min before. A dark board cannot show a dark frame,
in the control or in the write. Found by the Mac-driven run below.

### The camera from the Mac (11-03, 10:47-10:51, `camera_control_clip.sh`): the first clip dark, the ladder held, the control's 20 reads measured at 5-7%

The phone now films from the Mac over adb (`scripts/phonecam.py`,
`docs/test-bench.md`, "The camera"): start and stop stamped on both
clocks, the clip pulled and deleted from the phone, 240 fps real time
as frames / 240, the first frame ~0.74 s after the start key. And the
clip is judged by measurement, not by eye: `scripts/clip_dips.py` takes
every frame's mean luma (ffprobe's signalstats) over a crop of the keys
and lists the frames well below the median. One 8 s clip each, the
burst (dev op 23: 20 held 7-byte reads 100 ms apart, the row ISR held
off through each) fired 3 s after the record command.

- **10:47, `control`: nothing.** 1,840 frames, the keys' luma flat
  (median 90.6, scaled MAD 0.26, min 89.2: no frame 2% under), the
  burst done on the board (20 of 20, 1,989 ms first to last). The power
  log said why: 31 mA, the lights off since 10:32, three minutes after
  the 10:29 wake press. The 10:04 run above was filmed in the same
  state. So: **the ladder held at Always on (dev op 14 [1,0], mode 2
  before) and a relight press at 10:50:36** (53.7 mA after).
- **10:50, `control2`: all 20 reads, each one frame.** The keys'
  luma (crop 990:410:260:100) median 133.9, scaled MAD 0.40 (0.3%);
  the burst's reads at frames 194 to 671, **25 frames (104.2 ms)
  apart, 5-7% under the median in one frame each**, two of them
  straddling a frame boundary as 3.6-3.8% in each of two; 13 to 26
  MADs below the noise; outside the burst no frame 2% under
  (`camera-control2-dips.txt`, `-luma.csv`). Luma is the best channel
  (the dip 25.7 MADs; Cb 11.8, saturation 11.7, Cr nothing), so the
  finder stays on luma. **Where the light goes is the keys' own glow:**
  the difference between the dip frame 445 and its neighbour, amplified
  ten times, is the ring of light around every keycap and nothing else
  (`camera-control2-dipdiff.jpg`, the frame `camera-control2-frame445.jpg`).
  The dip is shallow because the room is lit (the keys' luma 134 of 255
  against the bench's 11 in the test-bench doc's clip) and the caps are
  opaque: a ~2.6 ms gap in a 4.17 ms frame removes most of the LED light
  in that frame, and the LEDs are about a tenth of the crop's luma. Ample:
  the finder's default depth is 3%, ten times the noise.

So the camera sees a ~3 ms dark gap at this framing, in room light, with
the keys cropped; and the lights must be on and the ladder held for any
filmed gate on battery.

- **11:01, `control-2x`: JD's 2x zoom and a lower exposure, as good,
  framed better.** The Pixel 8 has no second lens on this mode: 2x is a
  crop of the main sensor. The keys fill the frame (crop 1650:670:110:30,
  the screen and the knob in it), the median luma 67.7 (the exposure
  lowered by hand), the file still 240 fps (`com.android.capture.fps`;
  the UI check for 1/8x fails while the exposure panel is open, so the
  file's tag is the check). The 20 reads at 25 frames apart, **depth
  6.8% mean (3.1 to 10.3) against a noise of 0.37%, depth/noise 18.7
  against the 1x crop's 18.9** (5.5% mean against 0.29%): neither an
  improvement nor a regression for the luma gate, and the better framing
  for anything spatial. Two things to know at 2x: the camera settles its
  exposure over the clip's first quarter second (six 3% dips in the
  first 60 frames, now listed apart by `clip_dips.py` and not counted),
  and the baseline's tail reaches the 3% threshold twice in 1,800 frames
  (frames 230 and 654, 3.0-3.1% under, where the real dips are 5-10%):
  read an event's depth, not just its presence.

### The gate clip from the Mac (11-03, 11:05 on, `camera_gate_clip.sh`): two spoiled runs, the control at 100% white, and the LCD's blits seen on the LEDs

One 22 s clip holding the control (the burst at T) and then the
daemon started at T+6, its sync ~2 s later and the writer's unmasked
write right after; page 4 before and after. Two runs before the one
that counts:

- **11:05, `gate`: spoiled three ways.** The burst got `raw HID
  interface busy or absent` at 11:05:30 (no holder found: nothing of
  mine open since 11:02:18, Hutch's and the camera session's tools off
  white, the power steady at 51.7 mA, so no drop; unexplained), the
  script then ran late so the daemon started at 11:06:06 after the clip
  had ended (the write did happen, runs 54 to 55, off camera), and from
  11:05:34 JD's arm and watch sat over the keys (the frame's luma down
  25%). The script rewritten on the wall clock (the clip T-5 to T+17,
  the burst at T retried on a busy interface, the daemon at T+6).
- **11:10, `gate2`: the control at 100% white, but no write.** JD had
  set white to full white by hand at about 11:07:50 (54 to 92 mA), a
  key press that restarted the firmware's 10-min no-key clock, so the
  daemon's sync at 11:10:22 left the write deferred (runs 55 to 55).
  The control, though, is now unmistakable: **the 20 reads 20-39%
  under the keys' luma (median 50.6) against 1.3% noise**, the whole
  board losing light at once, every row
  (`camera-gate2-controldip-diff.jpg`; `camera-gate2-dips.txt`,
  `-luma.csv`). At full white every slot's pulse fills its slot, so a
  gap takes the whole field's light, where at JD's blue 177 it took a
  tenth.
- **Seen in that clip: the LCD's blits cost the LEDs a slot.** Besides
  the control, 5-6% single-frame dips on two or three key rows at a
  time, not the whole board (`camera-gate2-scrolldip-diff.jpg`,
  `-secondsdip-diff.jpg`): about once a second before the daemon
  started (the clock's seconds redraw: frames 164, 436, 670) and in a
  ~71 ms lattice after it (the now-playing text's scroll, every 283,
  221 or 62 ms at the 5% threshold, many more just under: the profile
  line is '+' throughout). The row ISR's record read at 11:14 has its
  omissions spread evenly over every row and colour (16-25 each, 224
  by the arm deadline since the last reset, epoch losses 19), so this
  is not a row dropped but a slot started late: at 100% the pulse is
  the slot's full width and a late start is truncated by the next
  slot, which the blue clips at value 177 could not show (a short
  pulse fits a late slot). SPI0's DMA shares priority 3 with the row
  ISR (`docs/leds.md`). Invisible to the eye (5% of one 4 ms frame),
  counted as an open item for the plan: measure the handler's latency
  with page 7 reset before and after a scroll, and whether stage 5's
  cadence changes it.
- **11:20, `gate3`: the control again, no write, the room light off.**
  The script's daemon start failed (`Bootstrap failed: 5`): the daemon
  was already running, put back at 11:14:25 after the record read, after
  the script's own bootout at 11:13:40; so no `sync (enumerated)` at
  T+8 and runs 57 to 57 (the periodic sync at 11:19:29 had written
  before the T-20 read: 55 to 57 between 11:14:23 and 11:19:40). And
  at 11:20:09 the room light went off (the frame's luma 51 to 24 over
  0.17 s, white's draw unchanged at 92 mA), which the finder's MAD
  swallowed into a 20% threshold: 18 of the 20 reads over it. The
  daemon's sync is a poor trigger for a filmed write: it needs a
  whole-second change or the 10-min no-key rule, and a start fails if
  the daemon is up.

### The gate met from the Mac (11-03, 11:28:45, `camera_write_clip.sh write1`): two unmasked writes filmed at 240 fps in a dark room, no trace

**The write forced on cue.** With the daemon paused, `ak820ctl clock`
runs the same protocol-2 transaction the daemon does; its acceptance
marks the clock chip stale (`pcf_sync_host_accepted`), and a dev op 23
burst running at the time admits the writer at once (`pcf_start_ok()`
returns true while a burst is active, and the burst steps only between
the writer's runs: `!pcf_pending && ps_state == PS_IDLE && burst_step()`),
so neither the 10-min rule nor the daemon is needed. In one 22 s clip
(5,200 frames, the room dark since 11:20, white at JD's full white, 92
mA): the control at T (20 held reads 100 ms apart), the markers from
T+4 (40 held reads 250 ms apart, 10 s), a sync at T+5.5 (before
+4.8 ms) and another at T+9 (before -0.2 ms), each followed by the
writer's unmasked run: **runs 57 to 59, both writes happened**, the
board -1.2 ms off after (`camera-write1-record.log`, `-page4-*.txt`,
`camera-gate-run.log`).

**What the clip shows** (`camera-write1-dips.txt`, `-luma.csv`; the
keys' luma median 24.8, scaled MAD 0.68 = 2.7%, the finder's floor 4
MADs = 11%):
- the control's 20 reads at frames 664 to 1140, 25 frames apart,
  **39-79% under** (the LEDs are nearly all the light now);
- the markers at 61 frames (254 ms) from frame 1596, **with two gaps
  where the burst waited for the writer: frames 1842-2488 (2.7 s, from
  the first sync at frame ~1917) and 2673-3486 (3.4 s, from the second
  at ~2757)**: the writer's runs, each bracketed by a marker before
  and after, the second boundary wait included;
- **inside those two windows, nothing**: no event at the 11% floor,
  and at a 3% floor the windows match the clip's quiet stretches in
  every figure: 15.6% and 16.7% of frames under 3% against 15.7% in
  the quiet tail (the camera's 240 Hz beating against the LED scan,
  a3's "one row under half its glow about every 7th frame"), the
  minimum 22.2 (11% under) in all three, the mean 24.78 against 24.79.
  The LCD-blit dips (11-13%) appear 17 times outside the windows and
  not inside them (the clock's redraw is quiet while the writer owns
  the chip, it seems).

**Verdict: the camera gate of stage 4 is met.** A held 7-byte read's
~2.6 ms gap takes 39-82% of a frame's light; the writer's three
unmasked transactions, run twice, take none that the clip can see. The
bench's battery state only (the data line on, no 5 V): the USB-powered
case runs the same transaction on the same path and was not filmed
(relay 2 is the drain's). Scripts: `camera_write_clip.sh LABEL HH:MM:SS
[CROP]`; the phone needs no hands (`scripts/phonecam.py`, the camera
session's lock since 11:30), white needs its lights on and the ladder
held, and nothing in the frame.

### Stage 5 on white (11-03, 12:47 on, `stage5_flash.sh`): the 125 us cadence, the light exact, the handler 50 us, the scan slots' omissions found and cut 26x

JD's word at 11:40: push ahead to the cadence, today. The plan's gate for
it is the handler's cost (≤ 20% at 8,000 slots a second), so **stage 5a**
(`4294a3befd`) first made the handler cheaper at the old cadence: the
exit's extension snapshot and its verdict by the two spans replaced by
the scheduler's counter against step 1's (a sample kept when no boundary
passed between the two reads), step 6's crossed check read off the
hardware (the flag, or the counter below step 1's) instead of the
extension's reconstruction, the fifteen match registers unrolled with the
colour's byte plane chosen once and the width a Q6 multiply and shift
(the flash scale table gone until stage 6's curve), and the cadence a
compile-time switch (`ROWISR_CADENCE_US`: the slot, the terminal and the
scale together). **Stage 5b** (`2c11b9ff01`) set 125 us; **5c**
(`078216ec89`) took codex's P2s (the width rounded, the scale 300/64 on
the measured 267 us duty, the dropped elapsed samples counted); **5d**
(`6a9fc0fcfe`) the window 1,535 and the settle 0.5 us. Two codex
reviews, READY both (`plans/review-codex-row-isr-stage5-*`); 5d's two
literals went without one. Each flash: the board woken by the presser,
the flash hands-free, the ladder held at Always on, a relight press, the
counters reset, 300 s lit at JD's full white (sat 0, value 255) with
nothing touching the board, then page 4, page 7, the record, the rows
and the logger's mean over the last 120 s.

| | 4b (267 us) | 5c (`0x7c425589`, 12:49-12:54) | 5d (`0x717d9b6a`, 13:02-13:07) |
|---|---|---|---|
| services a second (page 4) | 3,745 | 7,999 | 7,997 |
| handler mean / min / max, us (page 4, inclusive; the mean and the share from a 2 s pair taken after the hold, the extrema since the reset) | 71.6 / - / - | 50.0 / 32.0 / 117.3 | 49.5 / 32.0 / 117.3 |
| elapsed share between the hooks (preemption in, the wrapper out) | 26.8% | 40.0% | 39.6% |
| lit draw at full white, mA (31.1 dark) | 92.1 | 92.12 | 92.32 |
| pulses omitted | 0 | 2,311 of 2,417,753 (0.096%) | 87 of 2,417,188 (0.0037%) |
| omissions by the arm deadline | 0 | all (saturated) | all (89 at the record's later read) |
| per key row R / B / G | - | 255 / 1-9 / 1-10 (R saturated; B 32, G 36 in all) | 3-23 / 2-4 / 1-3 (61 R, 15 B, 13 G) |
| latency max, us (page 7) | - | 72.8 | 74.9 |
| `row_gap_max`, ms | 12 (a wake) | 3 | 3 |
| missed slots, losses, spurious | 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| tx_sent / tx_timeouts over the window | - | 73 / 25 | 73 / 35 |

**What the numbers say.**
- **The field is 444 Hz and the full-white draw is the same to a
  decimal**: 92.12 and 92.32 mA against 92.1. The 61 mA incremental
  "within 0.4%" subtracts 4b's dark reference (31.1 mA), not a new dark
  hold on 5d, and a changed CPU occupancy can move that base: a dark hold
  on 5d is owed, and the gate's per-colour, value-64 and low-code holds
  with it. Code 1 is 5 ticks at 125 us against 10 at 267: +6.8% of
  cadence-normalized duty at the bottom, before the transistors (the
  rounding, codex), which is the low-code gate's reason. The scale
  300/64 (the measured duty at k = 10 scaled by 125/267) stands at full
  white; D4's 4.845 would have been 3.5% bright.
- **The handler is cheaper in absolute terms (71.6 to 50 us) and dearer
  in share (26.8% to 40%)**: at twice the rate, 5a's savings (the exit,
  the arm's reconstruction, the loop) bought 22 us of 72, not the 47 the
  plan's 20% asks. The old callback driver ran at 73% and the board
  worked; codex's judgment: a target to revise, not an operating limit,
  the release evidence being delivery, overruns, the tick's regularity,
  stalls and omissions under load. Its ranking of what is left: section
  2 (the mux rows, the scan, the match registers) in SRAM on the daily
  build (~10 us, low teens at best: the 5d vector is 3,404 B, the daily
  gap 2.3 KB, the dev gap 368 B, so a section, not the handler); the
  cheap instruction cuts (the width's x300 is five shift-adds a column,
  `(75 b + 8) >> 4` or a flash table; `rec.serviced++` unread since 5c);
  the every-eighth frame judgment (~8 us, 39.6% to ~33%, a real
  diagnostic concession: the 00:22 counterexample loses a second
  aliasing silence inside 1 ms at this cadence).
- **5c's omissions had one dominant cause**: 2,243 of 2,311 red slots
  (the record's R counters saturated at 255 a row; B 32 and G 36 in
  all), the red slot being the one that carries the key scan before the
  arm, and every omission by the deadline: a late entry (the latency
  tail at 73 us), or a preemption after it, on a scan slot passed 80 us.
  Red is disproportionately vulnerable, not alone (codex's correction). 5d's window 1,535 (1.28x over the full width) moved the deadline
  to 90.5 us and the settle to 0.5 us (stage 3's sweep was exact at 0):
  **26x fewer, 87 in 300 s (61 R, 15 B, 13 G at the record's read), one
  slot in 3.4 s**, one row-colour dark for one 2.25 ms field, which the
  count alone does not prove invisible (a run of 1 globally does not
  exclude the same row-colour on successive fields: codex). The residual
  is a latency tail past 90 us: the entry latency reaches 74.9 us with
  the daemon paused (a maximum, so possibly several handlers and masked
  intervals stacked, not one 75 us interferer), and a prompt entry can
  be preempted before its arm. The order on this board is UART2 0,
  SysTick 0, USB 1, the 20 kHz tick 2, the row ISR with SPI0 and SPI1 at
  3 (`mcuconf.h`, `docs/leds.md`): the SPI completions cannot be
  preempted by the row handler, and the 20 kHz tick's gap monitor
  (`overrun_diag.py mon`) cannot acquit them, since a priority-3 handler
  delays the row while the tick stays regular. The plan's "zero in quiet
  runs" is not met to the letter; codex's order of remedies: find and
  shorten the interference; move the scan's bookkeeping (the publish,
  the health and rig accounting) behind the arm, keeping the electrical
  scan before it; the terminal 1,279 (5.3 us for 7% headroom) only if
  the rest justifies it. Its judgment: keep 125 us and 1,535, accept
  about one isolated omission in 3.4 s for release once the mixed-load
  and optical checks pass.
- **The scan is faster, not slower**: the presser's 8 ms dwell registered
  88 of 100 on 5c against 72 on stage 3, every closure reaching the
  scanner and every transition the consumer (raw_edges exact), only
  `process_record` missing 12: the debounce's boundary (5 ms,
  `sym_defer_pk`, judged when the main loop consumes), where an ~8.1 ms
  closure spans one 4.8 ms matrix period at 267 us and three or four
  2.25 ms periods at 125, so the capture improves without the cadence
  deriving the 88. 10 ms stays the demonstrated reliable dwell; 10 and 12
  ms exact (`presser-gate-stage5.json`, 5c's run; 5d's settle has its own
  presser gate in the chain).
- **tx_timeouts** 25 and 35 of 73 frames in a window on the data line
  with the daemon paused: the module's link idle while USB carries the
  keys; the radio kinds and the ACK rate come with the gates chain's UART
  step, which waits for Buzz locked (the presser keys into the front app
  otherwise: 12:54's lesson, JD's beeps and Xcode).

The runner's first run restored the ladder after the presser gate, whose
own trap had already taken the board off the data line, so the ladder
stayed at Always on until 12:58 (put back by hand); the runner now puts
it back before the gate and the gate is optional (`PRESSER=no`).

**The camera gate at 125 us (13:09-13:11, `stage5_gates.sh 0x717d9b6a
stage5d 4`): met.** The studio lights off from the Mac at 13:09:37
(`scripts/studio_lights.py off`, the 42 Studio entities; JD saw the
control's flicker from the next room's dark), the ladder held, one
relight press, `camera_write_clip.sh write-stage5d 13:10:56`: the
control's 20 held reads at frames 684-1162, 25 frames apart, **23-67%
under the keys' luma** (median 31.6); the markers at 61 frames from
1522 with the two gaps that are the writer's runs, **frames 1767-2165
(the first sync at 13:11:01.5) and 2592-3408 (the second at 13:11:05)**,
the writer's runs 0 to 2 since the boot's reset; **inside the two
windows nothing but the markers' own second frames**: no frame 8%
under, the 3% figures (2.0% and 6.7% of frames) below the quiet tail's
18.8%, the minimum 23.0 and 22.4 being the markers' tails. Two 11-12%
events of two and three frames at 10.43 and 10.45 s (13:11:04.3),
between two markers and before the second sync, are not the writer's
(its windows are the lattice gaps); the seconds redraw costing omitted
slots is the plausible cause, not an established one (the clip does not
count omitted slots, and a slot's share of a frame's luma was not
measured: codex). The lights restored at 13:11:38
(`camera-write-stage5d-dips.txt`, `-luma.csv`, `-page4-*.txt`,
`stage5d-gates-camera.log`).

**The presser gates on 5d (13:14-13:33, `stage5_gates.sh 0x717d9b6a
stage5d 123`; `stage5d-gates-123.log`).**
- **The UART step:** OE 0 before and after a 200-press batch at 25 ms
  (`overrun-stage5d-before.txt`, `-after.txt`), the longest handlers USB
  80 us, the system timer 16, UART2 11; the 20 kHz tick's gap monitor
  through the batch: 634,596 ticks, no gap >= 128 us, the longest 107 us,
  the main loop in the module's code at it; the clock chip's kinds under
  the faster ISR: the 7-byte read's whole call 7.5 ms and the 8-byte
  write's 6.1 (5.5 and 4.6 on 4b), the 4-byte read 3.1, the 3-byte write
  2.2, none failed, every masked span 5 us; the margin to the 10 ms
  deadline is a quarter now, the 5 ms paths held as before.
- **Five ladder sleeps with presser wakes** (`deep-wake-stage5d.json`):
  **the waking key kept 5 of 5** (key_presses +1 each, raw_edges +2),
  each wake 10.2 s from the press command to the enumeration (the REPL's
  setup inside; 10.3-10.4 on 4b), losses +2 each (the sleep's exclusion
  and the bus event, as on 4b and stage 4), no frame rejection; **the
  script's FAIL on two cycles is spurious invocations at the wake, 1 and
  2** (3 in 5 wakes; 0 in 3 on 4b, 1 in 5 on stage 3): an invocation
  inside an epoch already serviced, which counts and leaves (D3 step 1),
  harmless by design, more frequent at 6,000 ticks: the restart from 0
  at the wake and the first boundary are closer. Noted, not a loss.
- **The silence set: ALL PASS** (`silence-check-stage5d.json`): on USB
  100, 200 ms by the guard (losses 1, frame rejects 0); 350, 700, 1,049
  ms past the guard and rejected by the frame counter (1 each); 1,000,
  2,048, 7,000 ms by the guard; the spin's count exact (1049.003 at
  worst); on battery 20 ms two losses (the bus event's and the guard's),
  350 ms the bus event's alone, the declared limit; omissions 2-9 a case
  (the silence's own missed slots are counted apart: missed 0). The
  injections' marker on the Win Lock pin and the parked LEDs: JD saw the
  Win Lock light and the keys alternate at 13:32 and asked.

**Stage 5d's gates, then:** met: the field, the light at full white, the
row gaps, the presser's taps (5c's run), the camera gate, the UART step
(no overruns), the wakes (the key kept 5 of 5), the silence set; not to
the letter: the handler's share (39.6%), zero quiet omissions (87 in
300 s), and the spurious invocations at the wake (3 in 5) as a note.
Owed: the mixed-load window, the dark hold and the per-colour holds, the
low codes by camera (`stage5_loads.sh`, `stage5_lowcodes.sh`), on 5e.

### Stage 5e on white (11-03, 13:34 on, `stage5_flash.sh ... stage5e 300 yes`): the trims, the presser gate, the pack at 15% and the low cap

5e (`739fe1b635`, token `0xf222e31c`) flashed at 13:34:08 for the night.
**Its lit draw at full white before anything else: 91.70 mA** (the
logger, 13:35:10-13:37:40, 151 rows; 5d 92.32, 4b 92.1: the width table
is the same scale). **The presser gate: 6 of 7 exact**, 8 ms at 82 of
100 (88 on 5c, 72 on stage 3: the debounce boundary), 10 ms and up
exact, raw_edges exact, the rig's count at the scan 100 of 100 with A0
held (`presser-gate-stage5e.json`). **Its first cost window is void:**
the ladder's hold at Always on had not taken (the mode written, not
read back; a race with the flash's settings restore is the suspect,
5d's run having worked by timing), so Power saver turned the lights off
at 13:37:54 and page 4's 2 s pair at 13:40 measured a dark handler
(49.4 us, 39.5%: not comparable; `health-isr-stage5e.txt`), the record
25 omissions over 2.9 lit minutes (`record-stage5e.txt`: R 2-4, B 0-2,
G 0-3 a key row; 1,374,332 pulses emitted of 2,417,278 slots; one
missed slot), the light 31.24 (dark). `stage5_window.sh` now reads the
mode back (three tries) and checks the lit draw at the start and at
200 s. **Then the pack:** the battery page read 14.9% at 13:47 (vcell
3,715 mV; the count's band 10-20%), so the firmware's low cap
(`LOW_CAP_PM` 150) has held the lights down since about 13:42: "full
white" draws 55 mA. Today's full-white hours at 92 mA spent it; the
drain runs to the RGB cut as JD wants, uncharged. So: the per-colour
and value-64 holds wait for a charge (capped, they would measure the
cap); the dark hold, the mixed-load window and the low codes (values
1-64, under the cap) run now; the cost window runs under the cap (the
handler's work does not depend on the widths, only a dark row skips
the arm).

**5e's lit window under the cap (13:54-13:59, `stage5_window.sh
0xf222e31c stage5e-lit 300`, `LIT_MIN=45`, a keep-lit press every 100 s;
`health-isr-stage5e-lit.txt`, `health-sched-stage5e-lit.txt`,
`record-stage5e-lit.txt`):** 8,000.5 services a second; **the handler
52.3 us mean, 32.0 min, 128.0 max, 41.8%** (the 2 s pair at the end,
the board dimmed under the cap at 51 mA, a press 100 s before);
2,563,920 slots over the 320 s with the presses, **78 omitted
(0.0030%), all by the deadline: R 43, B 17, G 18**; latency max 86.0 us
(74.9 on 5d's quiet window: the keep-lit presses' USB reports raise
the tail); elapsed max 102; no missed slot, no loss, no spurious;
`row_gap_max` 3 ms. **So 5e's trims are in the noise**: the mean 52.3
against 5d's 49.5 (different conditions: the cap, the dim, the
presses), the omissions 78 against 87 with red's share down from 69%
to 55% (the scan's bookkeeping behind the arm did take a little off the
scan slots), and the tail set by what preempts the handler, not by its
own length: the USB handler's 80 us is the lead. 5e stays the night's
build (reviewed, no regression; its presser gate passed; the sleep path
is 5d's).

**The mixed-load window and the dark hold on 5e (14:00-14:06,
`stage5_loads.sh 0xf222e31c stage5e 12`; `mixed-sched-stage5e.txt`,
`mixed-record-stage5e.txt`, `mixed-overrun-stage5e.txt`,
`mixed-health-stage5e.txt`, `dark-stage5e.txt`).** The mixed load: the
daemon up (its sync, the now-playing text), a burst of 300 clock-chip
reads 40-80 ms apart (dev op 23, the short deadline, the row ISR held
off through each) and 200 presses at 25 ms through it, 113 s: 901,904
slots, **237 pulses omitted (0.026%, the gate under 0.1%)**, the longest
run 2, one spurious invocation, latency max 81 us, no loss; the
colours even under load (key row 0: R 16, B 17, G 9); **9,037 missed
slots (1.0%) are the burst's held reads**, each a ~3 ms hold-off of the
scheduler's line (20-24 slots), by design, not the handler's. The radio
channel with the daemon's text: 2,714 frames sent, 149 timeouts (5.5%),
no drop, no overrun. **The dark hold: 31.28 mA** (the lights off by the
ladder, the board awake on the data line; 4b 31.1), so the full-white
incremental on this build's own base is **60.4 mA (5e, 91.70 lit) and
61.0 (5d, 92.32)** against 4b's 61.0: within 1%, the light gate at full
white closed with its own dark reference.

**The low codes by camera (14:07-14:10, `stage5_lowcodes.sh`): no
result.** Solid white at values 0, 1, 2, 4, 8, 16, 32, 64, a 3 s clip
each with the room dark: the value 0 clip read 34.3 (the lamps still
fading at 14:08:00, four seconds after the off command) and values 1
to 64 all 8.1-10.1, flat: in the dark the phone's exposure and gain
float per clip and compress every level to the same luma, so the sweep
says nothing about the codes (`lowcodes-stage5e.txt`; JD was also
watching a video in the room). The low codes need a fixed-gain
instrument: the photodiode on the plan's witness, or the logger for the
codes it can resolve; the value ladder on the logger follows.

**The dev build's RAM, for the SRAM experiment** (`nm --size-sort` on
5e's ELF, 26,592 B of symbols): `log_buf` 12,960 B (the RAM battery
log), `wear_leveling` 1,032, `fa_tab` 640, `scratch_buf` and `gq` 512
each, `tx_q` 456, two rings of 448 and 320 (the overrun diagnostics),
`tile.*` 390-160, `led_state` and `led_state_buf` 243 each, the ds-phase
`wake_ring` 208 and the RX tap's 208, `dbg_text`/`dbg_shown` 198 each,
`prof_ring` and `mon_ring` 160. The dev diagnostics' rings and taps are
about 1.5 KB; a ~1 KB `.ramtext` for the handler's section 2 would need
the overrun rings and the RX tap compiled out of that measurement build
(the gap is 376 B; the daily's 2.3 KB holds it as is).

**The value ladder on the logger (14:12-14:21, `stage5_loads.sh ... 4`,
`valueladder-stage5e.txt`, `-v2.txt`): the scale is linear in the byte
over a fixed row-drive term.** The first run (JD's Alphas/Mods effect)
was confounded twice: the effect keeps the mods at their own colour (so
"value 0" drew 41.9 mA) and the cap's dim at 1 min and lights-off at 3
landed on the later steps. The second run: the Solid effect, a keep-lit
press before each step, white at 0, 32, 64, 96, 128 (the cap's ceiling),
40 s each, read against the firmware's drive accounting (D8's `led_pm`,
the bytes' share of the maximum; the bytes are QMK's CIE curve of the
value, so value 32 is bytes of 3-4 and 1.5%):

| value | mA | over value 0 | the drive accounting | mA at 100% by this step |
|---|---|---|---|---|
| 0 | 41.93 | - | 0.0% | - |
| 32 | 46.76 | +4.83 | 1.5% | 322 |
| 64 | 48.28 | +6.35 | 4.6% | 138 |
| 96 | 50.88 | +8.95 | 10.2% | 88 |
| 128 | 54.71 | +12.78 | 18.8% | 68 |

Two things in it. **The "dark" with the Solid effect at value 0 is
41.9 mA, not the dark hold's 31.3**: the hold's lights-off stage also
turns the screen's backlight off (`screen_off_ms` equals
`lights_off_ms` in every ladder), so the backlight at JD's 100% is the
10.6 mA between them, and the LEDs' own incremental at full white is
**50.4 mA** (92.3 - 41.9), the 61 against 4b's 61 being like against
like (both darks had the screen off). **The increments fit a fixed
term plus a line:** 4.3 mA at any lit value plus 46 mA per 100% of the
bytes' share (64: 4.3 + 2.1 = 6.4 against 6.35; 96: 9.0 against 8.95;
128: 12.9 against 12.78; 100%: 50.3 against 50.4). The fixed term is the
mux row's drive: a lit row's transistor is selected for the whole slot
whatever the pulse's width (F-033's phantom was this current on a dark
row, fixed by not selecting it), so a short pulse costs the row's base
current as a long one does. So the light (the pulse width) is linear in
the byte as the table makes it, the accounting agrees with the bytes
(the CIE curve included), and the power model's "dark and base terms"
have their number: the base is ~4.3 mA while any LED is lit, the slope
~46 mA at full. The lowest codes (bytes 1-7) are below what the logger
resolves and stay for the photodiode.

**The low codes by camera with JD's exposure lock (14:22-14:24,
`stage5_lowcodes.sh ... stage5e-lock`; `lowcodes-stage5e-lock.txt`):
monotonic at the camera's resolution, the floor QMK's.** JD long-pressed
the preview to lock AE/AF (14:17), and the lock held across the
volume-key starts: the dark level 2.55 and the clips comparable. Over
the dark: values 1, 2, 4, 8 all +0.35 to +0.39 (value 4 under value 2 by
0.02, the noise), 16 +0.47, 32 +0.81, 64 +1.87. QMK's CIE curve maps
values 1-8 to a byte of 0-1, 16 to ~1, 32 to ~3, 64 to ~12, so the sweep
is the curve's floor and then the driver's bytes 1, 3, 12: a byte of 1
(a 5-tick pulse, 0.1 us) lights measurably, and the three rise as the
camera's gamma predicts for light in proportion to the byte (Y ~ L^0.45:
1 : 1.6 : 3.1 against 1 : 1.7 : 4.0 measured, the last high by the
byte estimates). No plateau the driver made; the gate's values 1-16 are
one byte apart at most under the curve, which is stage 6's subject, not
stage 5's.

### Stage 5f, the SRAM trial (11-03, 14:31-14:37, `12f2c14cad`, token `0x08ddac91`): the hot section in SRAM buys nothing measurable

Codex's first-ranked lever for the handler's share: the hot section (the
scan slot's electrical scan, the fifteen match registers, the mux
select) as `rowisr_hot()`, 404 B at 0x20001394 in `.ramtext` as sleep.c's
WFI, a long call from the handler; the column loop rolled in SRAM (the
unrolled one overflowed the RAM by 8 B), the dev diagnostics' rings
shrunk for the room (the OE ring 32 to 8, the gap monitor's 16 to 4; the
heap gap 424 B). Reviewed (`plans/review-codex-row-isr-stage5f-*`: the
extraction behaviour-preserving, the placement sound; its P2, the host
reader's page counts, fixed and tested on the build). Flashed on USB
power during the charge and measured over the same 300 s window lit at
full white, the daemon paused (`stage5f-flash-run.log`,
`health-isr-stage5f.txt`, `health-sched-stage5f.txt`,
`record-stage5f.txt`):

| | 5d (battery, lit) | 5e (battery, cap, dimmed, presses) | 5f (USB power, lit) |
|---|---|---|---|
| services a second | 7,997 | 8,000 | 8,002 |
| handler mean / min / max, us | 49.5 / 32.0 / 117.3 | 52.3 / 32.0 / 128.0 | 51.7 / 32.0 / 106.7 |
| share between the hooks | 39.6% | 41.8% | 41.4% |
| omissions in 300 s (R / B / G) | 87 (61 / 15 / 13) | 78 in 320 s (43 / 17 / 18) | 50 (22 / 13 / 15) |
| latency max, us | 74.9 | 86.0 | - |

**The mean did not move**: 51.7 against 49.5 and 52.3, inside the
variation between windows (the conditions differ: the cap and the
keep-lit presses on 5e, USB power on 5f). So the cost diagnostic's
reading, "an instruction fetched from flash costs 3-5 cycles on this
core", does not hold for this section as the saving it predicted:
either the flash's fetch is faster for straight-line code than the
diagnostic's sections suggested, or the section's time is in its
stores and loads (the fifteen match registers, the table and index
loads from flash, the port reads) rather than its fetch, and SRAM moves
none of those. The omissions' 50 against 87 is the lower maximum
(106.7 against 117.3) and USB power's quieter board, not a cost gain.
**The trial is closed**: `ROWISR_RAMTEXT` is 0 (the same code inline in
flash, the rings at full size), 5e is the night's build. What is left
for the 20% target is the every-eighth judgment (~8 us, JD's call) and
nothing cheap; codex's revision of the target stands.

### The evening on white (11-03, 15:05-15:13, `stage5_evening.sh`): the charge, 5e back, the colour holds, the hand-over

Relay 2 on from 14:25:15 to 15:05:16 (0.55 A, about 340 mAh back; the
battery page 31.3% after, the cap off). 5e flashed back over the trial
at 15:06 (token `0xf222e31c`); a 120 s lit window on battery: the
handler 52.4 us, 41.9%; **the full-white draw 90.51 mA after the charge
(90.62 in the hold), 92.3 before it**: the pack's voltage moves the
regulator's draw by ~2%, so the light gate's comparisons are at like
charge states (`stage5-evening-run.log`, `health-isr-stage5e-night.txt`,
`light-stage5e-night.txt`). **The per-colour and value-64 holds**
(`holds-stage5e.txt`; 45 s each, the logger's mean over 30 s, the drive
accounting read with each):

| hold | mA | over the screen-on dark (41.9) | the drive accounting |
|---|---|---|---|
| red (h0 s255 v255) | 65.81 | +23.9 | 40.9% |
| green (h85) | 61.71 | +19.8 | 41.3% |
| blue (h170) | 59.16 | +17.3 | 41.3% |
| white, value 64 | 47.12 | +5.2 | 4.6% |
| white, value 255 | 90.62 | +48.7 | 100.0% |

A caveat: the holds ran on JD's Alphas/Mods effect (the script sets the
hue, the saturation and the value, not the effect), so each "colour" is
the alphas at that colour plus the mods at the effect's second colour,
which is why a pure colour reads 41% of the maximum rather than 33%.
The accounting is still the x axis the light should be linear in: white
64 and 255 sit on the ladder's line (4.3 + 46 x share: 6.4 and 50.3
against 5.2 and 48.7), and the colours spread about it, red above (23.9
against the line's 23.1) and blue below (17.3), the LEDs' own per-colour
currents, which `battery.c`'s model carries per colour (the per-colour
RGB model of 10-19). The plan's gate against stage 0's holds wants the
same holds on the Solid effect at a matched charge state; what is
settled today is the scale and the accounting (the ladder), the
full-white draw within 2% across three builds and two charge states, and
the colours' spread for the model's refit (stage 7). JD's lighting
restored from the dump taken before the holds; the standing state at
15:13:21; white handed to Hutch for Warren's M2/M3 overnight on 5e.

### Stage 5g on white (11-03, 19:36-20:34, `4f19e6c31f`, token `0x34d7c5fb`): the every-eighth judgment measured, 0.2 us, to be reverted

JD's go at 19:36 (N = 8, the timeline accelerated: the awake soak
tonight instead of a second night), white claimed back from Hutch at
19:37 (its evening on 5e: 11 keep-alive wakes every 24:58, 0
disconnects, `m23-evening.json`). The first cadence attempt
(`1d73bf3ed5`, 00:14, reverted on codex's P1 at 00:22) had taken a
time-only snapshot between judging services; the P1 was a coverage
hole, not the two-aliases-in-one-interval point JD had been told: a
guard-visible gap between two judging services made the judged interval
discontinuous, the judgment was skipped and the baseline moved past it,
and an alias on either side of the gap was never judged. **Stage 5g
(`1dfa597991`, 19:50)** keeps the full snapshot at every service and
decimates the judgment alone, judging the pending interval at any
discontinuity before the baseline is given up; codex's three rounds
(19:58 two P1s, 20:10 one P1, 20:18 READY; `plans/ROW-ISR-PLAN.md`,
"Stage 5g's reviews") added the entry-snapshot end (`usb_last`: a
crossed service's entry is evidence too), the retake of an untrusted
baseline when the frames' trust returns, the forced judgment of a
recovery baseline at its first fresh entry, and the silence report's
two fixes (its sequence read under the mask, the verdict PENDING under
two opportunities; its two pages paired by the run count).
`0b5e547705` (20:02), `4f19e6c31f` (20:12, heap gap 336 B against 5e's
376). JD typed on 5e meanwhile (19:42-20:18): **the colour fringe all
but gone at 444 Hz**, seen only on a deliberate rapid flick and most on
the rig's capless LEDs (no diffuser); **the screen's drawing (the menu,
the text pages) about twice as fast**, the main loop's share of the
core having gone from ~27% to ~60%.

**The flash (20:18:46-20:19:25, `stage5_flash.sh ... stage5g 300 no`,
`stage5g-flash-run.log`):** the token right. Its window
(20:19:54-20:24:54) ran at JD's own lighting (val 141, set while he
judged the rainbow and restored by the flash), 56.0 mA steady, so it is
void for the light gate (`LIT_MIN` 60) and biased low for the cost (a
dark row skips its select and arm): 51.6 us, 41.3%, max 122.7, 44 late
omissions, 0 spurious, 0 losses, `row_gap_max` 3 ms. The guarded
`stage5_window.sh` (20:25) refused it at 56.02 mA. **The full-white
window (20:27:56-20:33:46, `stage5g_window_fullwhite.sh`: JD's choice
saved to `lighting-5g-jd-choice.json`, val 255 restored from
`lighting-before-holds-stage5e.json`, the window, his choice put back;
`stage5g-window2-run.log`, `health-isr-stage5g.txt`,
`health-sched-stage5g.txt`, `record-stage5g.txt`, `light-stage5g.txt`):**

| | 5e lit (13:35) | 5e night (15:06 on) | **5g full white** |
|---|---|---|---|
| page 4 mean, us | 52.3 | 52.4 | **52.1** |
| page 4 share | 41.8% | 41.9% | **41.7%** |
| page 4 max, us | | 128.0 | 128.0 |
| late omissions in 300 s | 78 | 87 | 81 |
| spurious, losses | 0, 0 | 0, 0 | 0, 0 |
| `row_gap_max` | 3 ms | 3 ms | 3 ms |
| the lit draw | | | 91.2-91.6 mA (4b 92.1) |

**0.2 us.** The skipped arithmetic was worth ~3 us a slot; the
bookkeeping that correctness demanded (the full snapshot kept and
copied, the discontinuity and trust tests, the held statistics) costs
about as much. The detector's cost lives in its snapshot, not its
judgment, so the ~7 us is only to be had by compiling it out. **JD's
decision (20:36): revert the decimation to 5e's per-slot judgment
tomorrow, keep the silence report's two fixes, and put the detector
behind a flag the dev build sets and the daily build does not;** the
release then gets the saving and the dev build the simplest correct
instrument. Tonight's soak runs on 5g as flashed (reviewed, equivalent
in coverage but for the two declared concessions: two aliases in one
interval are one rejected interval, and a 4 ms pause of the host's SOFs
straddling a baseline is no longer a loss).

**The awake soak from 20:34 (`soak_watch_awake.sh stage5g`,
`soak-stage5g.jsonl`, `soak-stage5g.log`):** the data on, the daemon
loaded, a read every 20 min with the daemon paused ~15 s, JD typing on
it, his lighting his own. Read 1 (20:34:23): losses 2 (the boot's), 0
frame rejects of 331,285 intervals judged, `i2c_max_cycles` 251, 0
fails, `row_gap_max` 3 ms. The silence set and the five wakes are
skipped tonight on JD's instruction (they run on tomorrow's build, which
needs them anyway). White goes to Hutch asleep at about 00:35 for
Warren's M2/M3.

**The soak's result (20:34:15-00:35:19, 4 h 1 min, 13 reads,
`soak_summary.py soak-stage5g.jsonl`): clean.** Losses 2 throughout (the
boot's), spurious 0, invalid services 2 (the boot's), `row_gap_max`
3 ms at every read; the frame counter judged 14,786,064 intervals and
rejected none (2 bus events, the boot's); the clock chip's writer 49
runs good, 0 restarts, `i2c_max_cycles` 251, 0 failures; 18,700 blits
with no fault; `msp_free` 536, `psp_free` 936; the late omissions
saturated at 255 by the second read (0.003% of 29 million slots, as 5e
measured); the rig's keys 14 (JD's typing is not counted there). White
asleep in the standing state at 00:35:24 (the data cut sleeps an idle
board at once: 3.47 mA at 00:35:27, the pack 28.7%), the daemon running,
relay 2 off; handed to Hutch for Warren's M2/M3.

### Stage 5h built overnight (11-03, 22:23-23:45, `a1a0c783d5` to `bde904e491`): the per-slot judgment back, the detector a dev-only flag, the floor probe's flavour; codex READY; flashed 11-04 (the next section)

JD's bedtime question (22:23): on white the lights dimmed by the value
keys hold from 1% to about 3%, step, hold to 5-6%, step. The cause is
QMK's CIE 1931 table (`quantum/led_tables.c`, really CIELAB's 1976 L*)
applied to the value before the 8-bit byte the driver sees: values 1-9
all leave it as byte 1, 10-18 as byte 2, 19-26 as 3, 27-33 as 4; of 256
values 175 distinct bytes, of the 128 below half brightness 48. Not the
rewrite's doing (the stock driver had exactly 255 widths, the byte its
limit); the rewrite's timers have 1,195 widths at full scale, 4.7 a
byte, reachable only from a wider conversion (the plan's D9, stage 6).
The 444 Hz field halved the widths (2,550 at 267 us) and raises the
dimmest steady level (the shortest pulse that lights fires 444 times a
second), and makes two- and four-field dithering usable (222 and 111 Hz
patterns; the eye's fusion rate falls with the light). Recorded in the
plan's stage 6 with the per-colour floor calibration JD will do by eye
(red's forward voltage a volt below green's and blue's), the camera at
the two capless keys as the check: "The floor is measured first, per
colour", and Q2.

**Stage 5h (`a1a0c783d5`, 23:25), tomorrow's agreed first commit, done
tonight on JD's "what can you work through overnight":** the frame
counter's judgment at every service again (5e's form on 5g's pure
`usb_judge`, `last_snap` to `s1`); the whole detector behind
`ROWISR_USB_DETECT` (`config.h`: 1 under `AK820_DEV_HOOKS`, 0 otherwise:
the constants, `frmno_read`, the freshness state with `frm_staleI` and
`frm_trackI` as stubs, the bus-event generation and `usb_event_kb`, the
snapshot's frame fields and `take_snapI`'s six register reads, the
judgment, the adoption, the sub 6 record's frame bytes), which
`build.sh` checks by `usb_event_kb`'s symbol type (ours in a dev build,
the USB handler's weak default in daily and fpb); the silence report's
two fixes kept, its sequence now the services entered past the spurious
check in every build; `ROWISR_K_Q6` overridable and the flavour
`devprobe` (64: a byte its width in ticks, the board at 21% of its
light), stage 6's floor probe; `scan_key_row` under
`SN32F2XX_SLEEP_HOOKS` (a daily build of the branch had not been made
since scan-only took the only call, and failed on the unused function).
The builds (`build-stage5h.sh`, `build-stage5h-*.log`):

| flavour | artifact (of `bde904e491`, the final) | token | heap gap |
|---|---|---|---|
| dev (the candidate for white) | `via-dev-bde904e491-20261103-234013.bin` | `0xfeeeb2db` | 368 B (5g 336) |
| daily (the detector out) | `via-daily-bde904e491-20261103-234032.bin` | `0xcaa61e41` | 2656 B; `usb_event_kb` weak |
| devprobe (the floor probe) | `via-devprobe-bde904e491-20261103-234052.bin` | `0xefa1c31f` | 368 B |

(The superseded builds: `a1a0c783d5` at 23:28, dev `0xd67c292a`, daily
`0x304b98d4`, devprobe `0x9c7f221c`; `703df88a9d` at 23:37, dev
`0x24f30c92`, daily `0x74cd2124`, devprobe `0x8ae8a53b`.) **Codex on `a1a0c783d5` (23:28-23:35,
`plans/review-prompt-row-isr-stage5h.txt`, the raw output beside it):
READY, no P1.** Its P2: the probe build's drive accounting reported the
byte as the value (4.7x the light), which on battery would run the
gauge down and could pull Saver's cap in early; fixed in `703df88a9d`
by `ROWISR_K_REF_Q6`, the cadence's calibrated scale, as the D8 unit
whatever scale is in force. Its notes, all taken: the judgment
equivalent to 5e's (Q1), the detector-off isolation checked against the
daily ELF's disassembly (Q2: no USB register or `USBD1.state` read in
the handler or the observer), the two-service wait sufficient and
conservative (Q3), the symbol check and the flag transport (Q4), the
probe arithmetic sound (Q5), and the comment rot: the rejection comment
no longer claims step 6 checks the generation (it reads the hardware's
flag and counter since 5a), sub 8's "2 ms after" is the bounded wait,
sub 9's [16] is a saturating lower bound of the services entered (an
entry counts whether it judged or not) with PENDING the conservative
reading, the host's strings follow. **The verify round on `703df88a9d`
(23:37-23:39, `-verify`): READY, no P1 or P2, the P2 resolved**, five
more comment spots (the "2 ms after" in the diag's header and the host's
docstring, "each judges" where an invalidated entry counts too, "not
yet in" where the verdict may be in, the drive comment's unit under a
probe): `bde904e491`, comment-only, the final build above. Owed on the
flash, on JD's go: the full-white window (the dev
build's cost should read 5e's ~52 us, the detector in; the daily build's
is the release's figure, expected ~45), the silence set
(`stage5_gates.sh TOKEN stage5h 3`), the five wakes (`2`), then a daily
build's short soak.

**JD's clock-sync question (20:31: does the faster main loop tighten
the daemon's syncs?), from the daemon's log (`clocksync_compare.py` in
the scratchpad; periodic syncs only, an enumerated one follows a
reconnect):**

| period | periodic syncs | before, mean / median / p95 / max (ms, absolute) | rtt mean / p95 (ms) | U mean (ms) |
|---|---|---|---|---|
| stage 4b's night, 05:08-09:35 | 39 | 6.4 / 5.2 / 16.0 / 20.0 | 2.06 / 2.60 | 1.17 |
| stage 5g, 20:19-00:35 | 37 | 6.3 / 4.4 / 15.8 / 16.8 | 2.33 / 3.00 | 1.44 |

The same within noise: the residual between syncs is the RTC's drift
over the 300 s (5-6 ms, 17-20 ppm), which the handler does not touch,
and the transaction's rtt is 2 ms either way. The old ISR has no
periodic sample on the Mac (the 10-19 soak's syncs were all post-wake
enumerated ones; the 10-31 to 11-02 log has none, the data line off in
the standing state), so against it the only figure is gremlin's Windows
daemon of 09-06 (p95 21.0 ms), a different host. The answer: no
measurable change.


### Stage 5h on white (11-04, 08:32-10:01): the flash, the window at full white, the silence set, the five wakes; Hutch's M4 arrived

JD's go at 08:30. White came from Hutch at 08:31:38, asleep in the
standing state: its M4 with-run (one press after 30+ min asleep) had
waited since 08:10 for Buzz's unlock and was stopped before its press.
The flash (`stage5_flash.sh ... stage5h 300 no`, `flash-stage5h-run.log`,
`flash-stage5h.log`): the presser's A1 woke white at 08:32:37 (asleep
since 00:36 but for the keep-alive's 18 wakes; op 24's sleep ring went
unread, Hutch's choice, since a read is a wake), the write at 08:32:43,
the token `0xfeeeb2db` read back at 08:33:13, the keymap, the profiles
and the live settings restored. The lighting the flash put back is
JD's Purple/Blue (Alphas/Mods, hue 178, sat 219, val 125,
`lighting-5h-jd-choice.json`), not last night's white at 141, so the
flash script's own 300 s window ran at it (08:33:43-08:38:43,
`record-stage5h.txt`, `rows-stage5h.txt`, `health-sched-stage5h.txt`):
the handler 51.2 us mean and 40.9% at 7,998 a second (max 112 us), 31
omissions by the arm deadline in 2.42 million slots, 0 spurious, 0
invalid services, 0 epoch losses, row gap 3 ms, loop gap 4 ms; the lit
draw 49.4 mA is that setting's, not the reference's; the UART counts
(72 sent, 38 timeouts) the same as 5e's flash window, the boot's
pattern. The full-white window (`stage5h_window_fullwhite.sh`, the 5g
script with the token and this morning's lighting restored after;
08:41:20-08:47:19, `window-stage5h-run.log`, `health-isr-stage5h.txt`,
`light-stage5h.txt`), the lit draw 91.57 mA at the start, 91.52 at
200 s, 91.61 over the last 120 s (the gate 89.1-95.2):

| build at full white | handler mean | CPU share | max | omitted in 300 s |
|---|---|---|---|---|
| 5e `739fe1b635`, the per-slot judgment | 52.3 us | 41.8% | 128 us | 87 |
| 5g `4f19e6c31f`, every eighth with the snapshot kept | 52.1 us | 41.7% | 128 us | |
| **5h `bde904e491`, the per-slot judgment behind the flag** | **52.8 us** | **42.2%** | **128 us** | **65** |

So the per-slot judgment's return costs what 5g measured it at, inside
a window's noise (5e's two windows read 49.4 and 52.3). Page 7 on the
window: 2,565,849 slots, 0 missed, 65 pulses omitted (66 by the arm
deadline), latency max 80 us, elapsed max 113.0 us, 7 elapsed samples
dropped for a boundary inside the handler, 0 spurious, 0 invalid, 0
epoch losses, the shortest handler 30.17 us; row gap 3 ms (row 5), loop
gap 4 ms. The first run of that window (08:39:19,
`window-stage5h-run-noboard.log`) found no board: the flash script's
data cut had put white to sleep at once (the last key over 3 min back)
and the 5g script's `on_data` had no wake press (on 5g it ran seconds
after JD's typing). The rule, now in the script: a script that brings
the data line up and finds no board presses one of the rig's keys
(Delete or PgDn on the QT Py) and waits 15 s, as the gates script does.

**The silence set** (`stage5_gates.sh 0xfeeeb2db stage5h 3`,
08:39:21-08:40:36, `silence-check-stage5h.log` and `.json`): **10 of
10.** On the data line 100, 200, 350, 700, 1,049, 1,000, 2,048 and
7,000 ms each one loss; the frame counter's reject at 350, 700 and
1,049 ms only (the rejection spans 1/351, 1/700, 1/1050 ms), the
extension's guard at the others (its gap 100.0, 200.1, 301.0, 300.4
and 9.5 ms); 0 spurious, 0 missed slots, 7,267-7,339 intervals judged
in each, the extension reading 2.1-3.2 ms across each silence. On
battery with the data cut: 20 ms two losses (the bus event's and the
silence's own, as expected) and 350 ms one (the bus event's; the
silence's own undetected, the declared blind spot); USB ACTIVE after
each. The ladder held at Always on for the cuts and Power saver put
back; the counters reset after.

White went back to Hutch at 08:47:19 in the standing state on 5h (the
lighting JD's Purple/Blue; asleep by the ladder from about 08:50) for
its M4 with-run on 5h, which waits for JD's press at Buzz with white
asleep 32+ min. Owed on 5h after it: the five wakes
(`stage5_gates.sh 0xfeeeb2db stage5h 2`, about 20 min, each cycle
waiting 3 min for the sleep) and the daily build's short soak
(`via-daily-bde904e491-20261103-234032.bin`, `0xcaa61e41`, the
release's handler figure, ~45 us expected): a daily build has no
bootloader jump, so the return to dev is `Fn`+`Esc`, JD at the board.

**Hutch's M4 with-run on 5h (09:20): ARRIVED.** White asleep from
08:48:25 with the keep-alive holding the link, Buzz unlocked, no key;
the rig's press at 09:20:33, 32 min after the sleep; F19 reached the
Mac in the same second and white's link had no bluetoothd event; the
wake ring on the board: a reason-7 wake at 1,308 counted s (the default
rate after the flash) and the key's wake at 290 counted / 349 PCF s, no
strays, nothing timed out; since the flash `count_ge_25ms` 0, row gap
max 7 ms (Hutch's record, `history/keepalive-20261103/`).

**The five wakes** (`stage5_gates.sh 0xfeeeb2db stage5h 2`, 09:44-10:00,
`gates-stage5h-2.log`, `deep-wake-stage5h.json`; white asleep and
untouched since 09:28:51 when they began): **5 of 5 kept the key.** Each
cycle: the ladder's sleep 3 min after the last key, the rig's Delete,
white on USB 10.1-10.2 s after the press command (the REPL's own setup
inside that), the counts read: key presses +1 each (5 to 9), epoch
losses +2 each (the data cut's suspend and the reconnect's reset, one
loss apiece by design), spurious +0 (3 since the boot, all before the
first cycle), frame rejects 0, bus events +1 a cycle, invalid services +1 a cycle
(cycle 2 alone +2). The invalid count is by design: the one service
whose interval spans the reconnect's reset is rejected by the frame
counter (one loss, no statistics), and the wake's own first service is
never counted, since both sleep hooks clear the handler's last snapshot
(`sn32f2xx_sleep_enterI`, `sn32f2xx_sleep_exitI`: no interval to judge)
even though the generation moved under it by the sleep's exclusion and
its end, the cycle's other loss (`loss_gen` +3 a cycle, two of the
three seen at one entry: losses +2). Cycle 2's extra invalid service
came with no extra loss, so it was an interval the frame counter left
unjudged (both ends in the frames' recovery) or an exclusion's, which
the read does not separate. White back to Hutch at 10:01 in the
standing state.
That closes stage 5h's hands-free gates; what remains on it is the
daily build's soak, JD at the board.
### Stage 6's floor by eye (11-04, 12:05-15:10): every colour lights at one tick, the eye's step limit, the white's composition, a held key's column neighbours

JD's go at 12:05 with the office dark. He entered the bootloader by hand,
so `flash.sh` found no firmware to read and used the morning's 08:32
backups (the keymap, the lighting, the profiles; the battery log since
08:32 not dumped); `devprobe` `bbf5d6069e` (token `0x9413cb17`: stage 5h
plus sub 3's every-LED pattern, index 254, codex READY) was on white at
12:07, the ladder held at Always on for the session (`flash-stage6-probe.log`).
On this flavour a byte is its pulse width in ticks (`ROWISR_K_Q6` 64),
full scale 255 ticks, the board at a fifth of its light.

**The instruments, as they grew through the afternoon** (the commits on
`row-isr`, every flash hands-free from the dev flavour's bootloader jump,
`flash-stage6-probe-page.log`; the builds `build-stage6-probe-*.log`):

- `floor_eye.py COLOUR`: the timed staircase, every LED at 1, 2, 3, 4, 5,
  6, 8, 10, 15, 20, 30, 50 ticks, 4 s each, the level on the LCD's text
  line ("R N=3"), logged with times (`floor-eye.log`). Red ran once
  (12:11); JD wanted his own pace.
- `floor_set.py` as `~/.local/bin/probe`: `! probe red 3` typed at this
  session's prompt sets every LED, `probe dark`, `probe off`; each call
  logged. His red readings came this way (12:18-12:20).
- **Diagnostics > Floor probe**, a dev-only menu page in the Write
  test's place (that page retired: its question, Scan against Blank at a
  flash write, was settled by eye on 10-27; the menu's node table is
  full at 64, so a page reuses nodes). Built by a fork of this session
  while JD probed: rows Color and Ticks, a click capturing the knob (a
  turn a tick, 0-255, no wrap; the colour round red, green, blue), the
  pattern on every LED while the page is open and released on every way
  out, nothing saved. Codex's first round found a real P1 (two opener
  reports in one pass could close and reopen the session before the
  per-pass release and strand the pattern on the keys) and a P2 (the
  release was by history, not ownership, so leaving the page cancelled
  a pattern the host set after it): fixed, verify READY, `b9f892460d`
  (`0x74ec7b22`) on at 12:49 (its first build `53d64bcdb4`, `0x6403558a`,
  on at 12:35 on JD's "just flash it now"). Then **Color's click took the
  knob too** (`116c06c7f9`, `0x0d49c431`, 13:40; codex READY), so a colour
  change needs no key press (below), the label "Color" on the screen. Then
  **the split** (`d39525bee3`, 14:07): Color R and Ticks R for the right
  half of the board (columns 8-14) and a Split switch, the two halves
  abutting for a match; sub 3's index 253 with the second colour at
  [9..11], the host's `led split R G B R2 G2 B2`. Codex's P2: the row
  signature kept two index bits, so Ticks R at 0 shared the blank row's
  signature and Split shared Color's, and a fast page change could leave
  a row unpainted; each row its own range in `bfff926086` (`0x3b47b8a1`,
  on at 14:13; verify READY: 2,080 combinations distinct). The host test
  (`scripts/menu_s0_test.c`) covers the page in both builds.
- The 5 V relay on from 14:49 for the match (the pack at 14.7%, under
  the low cap's Saver ladder, which darkens an idle board at 3 min), off
  again for the logger pass.

**The readings** (`floor-eye.log`; JD's words, the office dark, the bare
LEDs seen through the capless keys, `led-die-capless-IMG_0812.jpg`: the
three dies in three quadrants of the package, red top right, green bottom
left, blue bottom right, each a point):

| | visible at | a one-tick step stops showing at |
|---|---|---|
| red | 1 tick, "clearly visible and very dim" | 6 to 7 (~15%) |
| green | 1 tick, "very visible"; 1 to 2 "very steep" | 11 to 12 (~9%) |
| blue | 1 tick, "pretty similar" to green | about 11 to 12 |

So **the floor is below the probe's reach**: a one-tick pulse (21 ns a
field, a duty of one in a hundred thousand) lights every colour clearly in
the dark, and the dimmest levels will be made by skipping fields (one
tick every second or fourth field), not by shorter pulses; JD's "barely
perceptible" sits under a tick. **The eye's ratio limit** is the shape
the curve's bottom needs: steps of 9-15% or more, growing by ratio, not
by equal ticks (from 1 to 2 is a doubling, which he called steep). At
equal ticks **green is the brightest, red just under, blue well under**.
The split match on USB power, the left half red at 12: **green at 9,
maybe 10** ("green 12 is just slightly too bright"), **blue at 23** ("pretty
close"), so red 1.26 and blue 2.4 times green's ticks for the same
brightness, a tick's uncertainty either way. The match was made at 12
rather than at 1 or 2 because a tick there is a doubling or a 50% step
and the nearest setting can be far from equal; at 12 a tick is 8%, the
eye's own limit.

**What the gains are, and are not.** Mid-afternoon I told JD a dim white
of equal ticks would look green; that was wrong, and corrected: full
white on this board is equal ticks on all three, so equal ticks at any
level has the same mix, as long as each colour's light stays proportional
to its width. The gains describe the white's composition, a cross-check
for any later camera numbers, not a correction the table needs. What the
eye cannot measure is that proportionality in the first few ticks, per
colour, where the LED is still turning on (a short red tick giving less
than its share would turn the dimmest white cyan): that is the plan's
"linear-from tick" and the camera's pass, still owed (the phone at the
capless keys, the exposure locked, pixel sums at 1, 2, 3, 4, 6, 8 ticks
per colour, hands-free once the phone is placed). JD's thought of lighting
all three dies at once and tuning each by eye is a better instrument for
the same ratio, so it was not built.

**A held key brightens the LEDs above and below it in its column.** The
knob's click (a key to the firmware) brightened the keys as JD compared
levels; any key does it, only its column, only while held, invisible at
his Purple/Blue. The mechanism, from the slot's order (`rowisr.c`, the
hot section): step 2 deselects every mux row, and within a microsecond
step 3 scans one key row with the columns released to their pull-ups and
the key row driven low; a held key pulls its column low through its
diode, and the LED on that column in the row just deselected still has
charge on its anode rail (or a transistor still turning off), so it
lights for the scan's microsecond: about 48 ticks' worth once a field,
a 17% nudge on one LED at his lighting, four to fifty times a 1-12 tick
level. A stage 6 fix in the row ISR (the scan after the match-register
writes, or a deliberate gap after the deselect), gated by JD's eye at 3
ticks with a key held. Meanwhile the page's captures let every
comparison be made with nothing pressed.

**The logger pass** (15:04-15:10, `floor-logger.log`; its lines doubled by a `tee` beside the script's own log): every LED at 0, 10, 15,
20, 30 and 50 ticks per colour, 20 s a level, on battery (the 5 V relay
off, the INA228 being pack-side) with the stage forced ACTIVE (dev op 14
sub 2: the pack at 14.7% is under the low cap, whose Saver ladder would
have darkened the keys at 3 idle minutes; raw HID is not activity).
`floor_logger_fit.py` pairs the levels with the INA228's rows (the first
5 s of each dropped) and fits the rise over the run's own dark:

| colour | dark (mA) | +10 ticks | +15 | +20 | +30 | +50 | slope, every LED | intercept |
|---|---|---|---|---|---|---|---|---|
| red | 41.19 | +1.55 | +1.81 | +1.82 | +2.07 | +2.43 | 20.7 uA/tick | +1.42 mA |
| green | 41.30 | +1.42 | +1.51 | +1.66 | +1.76 | +2.05 | 15.5 uA/tick | +1.29 mA |
| blue | 41.38 | +1.39 | +1.54 | +1.60 | +1.72 | +1.97 | 13.6 uA/tick | +1.30 mA |

Two things in it. **The intercept is the mux's own cost of lighting at
all, about 1.3-1.4 mA whatever the level:** a row with any width is
selected every field (its transistor's base current), and a dark row is
not (`rowisr.c`, step 5; F-033's lesson), so the dimmest possible pattern
on every key costs 1.4 mA before any light, the same as a bright one's
mux share. The power model already carries a per-row term; this is its
measured size at the probe's cadence. **The slope is the LED current:**
per LED and tick, 0.26 uA red, 0.19 green, 0.17 blue, which at a tick's
duty (21 ns in a 2.25 ms field) is a pulse current of about 28, 21 and
18 mA. Scaled to full white (1,195 ticks a colour) the slopes give
59.5 mA above the mux's 1.4, against the ~50 mA the full-white window
measured above the dark board (91.6 lit); the rows are 1 Hz with a
scatter of ~0.1 mA against rises of 1.4-2.4, so the slopes carry about
20%, and the difference is inside that and the long pulse's droop. The
light per tick is linear from 10 to 50 within the scatter; below 10 the
logger cannot see, which is the camera's range.

**White after it:** the standing state (the data line off, the daemon,
the relay off) with the mode put back to Power saver, which the session's
hold had set to Always on and the 12:35 restore had persisted (the
board's live record and the backup file both verified); the dev build
`0x11e5314a` back on at 15:19 on JD's go. White to Hutch, with a flash
moratorium agreed for the drain's last 15% (about two days at his use):
the flashes below ran over the data line alone, which feeds the pack
nothing.

**The held-key fix, the same evening (17:0x-17:20, `81622b7a43` and
`245fcfe8e3`; codex READY, no P1 or P2, `review-codex-row-isr-stage6-heldkey-raw.md`).**
First the dev build's own check, by camera and by eye, found nothing: at
the dev scale a value of 1 is five ticks, and no key held showed a change
on the bare LEDs (the clips in `heldkey/`, PgDn held by the rig for 3 s
inside a 12 s clip, Esc held by JD: the capless points within noise), so
the effect is about a tick's worth of light, a doubling at the probe's
dimmest level and a fifth at five ticks. The slot order said which LED:
the scan of key row k ran in the slot preparing mux row (k, R), a
microsecond after step 2 deselected the previous slot's row (k-1, G), the
only rail with its charge still on it, so a held key at (k, c) lit
(k-1, c) green: the key above, the top row's in the bottom row. The fix
scans the row before the one being prepared, whose green rail step 2
just deselected, so the flash lands on the held key's own LED under the
finger; each key row is still scanned once a field, one slot-triple
later (codex: the sample's phase moves, the interval and the debounce do
not; the flash-program guard's slot neither scans nor publishes, a
comment put right). **JD's gate on the probe build, red at 1 tick:** the
key above a held key no longer brightens, with a trace left on PgDn when
the key under it is held; but **holding PgUp makes PgDn light up
considerably more**, the knob and Right arrow nothing visible: the row
BELOW. So the stored-charge picture is incomplete: at one tick the
pulses are 21 ns and drain no rail, so every rail in the held key's
column may still hold charge at its scan, and which LED shows depends on
what the eye can see past the caps. Not chased further tonight (his
call); the measurement is the camera on the probe build at 1 tick with
a key held in a column of bare LEDs. The dev build `245fcfe8e3`
(`0x154c76fb`) went back on at 17:20, white to the standing state.

### D9 on white (11-04, 17:08-17:57): the precision path on one wide frame, the purple's red back at 5%

JD's evening ask after the floor work: his purple theme (Alphas/Mods, hue
178, sat 219) was pure blue under 8% brightness: QMK curves the value
first (5% is a lightness of about 1 of 255 under CIE), then multiplies
the channels by it and truncates, so red's 30% of that 1 is 0 while blue
keeps the 1. "Go through to
completion", the camera his until the eye check. The design is the plan's
**"D9 revised (11-04)"**, written against the 11-04 RAM ledger
(`arm-none-eabi-nm` on the dev ELF: the gap 368 B, the two byte frames
243 B each, the dev-only RX tap ring 208 B, the battery log 12,960): one
wide frame instead of the original D9's two. The committed frame holds
each LED's pulse widths in ticks (12 bits, `led_w[81][3]`, +243 B); the
render buffer stays QMK's bytes; for an effect whose value is the same on
every LED (Solid, Alphas/Mods, the three Cycles, Jellybean: `power.c`'s
whitelist, `power_wide_mode()`), the board's `rgb_matrix_hsv_to_rgb()`
wrap converts the colour at full value so the bytes hold the chroma, and
the flush applies the value (the config's under the ladder's cap) at 12
bits through a 16-bit CIE L* curve (`rgb/curve12.h`, 512 B of flash,
`scripts/gen_curve12.py`; `--gamma` for the exponent evening). Under a
tick the field is skipped (one tick every second field from 0.5, every
fourth from 0.25, flagged above the terminal and resolved by a field
counter in the handler). The other effects (Typing Heatmap, RAINFALL,
DRIFT: a value per LED) and the dev patterns stay on the byte path
through `width_lut[]`, now loaded at the flush, not in the handler. The
conversion runs unmasked (a halfword store is atomic; a field can mix old
and new LEDs across a transition, D8's coherence relaxed on purpose). The
RX tap went opt-in (`CH582_RXTAP`) for the RAM: the dev gap 344 B, the
daily 2,416.

**Two codex rounds, both NOT READY, both taken** (`review-codex-row-isr-d9-design-raw.md`,
`-code-raw.md`): the first version let the wrap's calls decide a frame's
encoding, and Jellybean paints nothing in a frame without a drop, so such
a frame would have read its chroma as raw bytes and blazed; a brightness
change in such a frame would never have landed; a raw pattern with the
chroma's own bytes would have skipped the conversion; and a pattern's
release over a sparse painter would have left raw bytes read as chroma.
The second version (`4ff4caf4d6`): the encoding is the mode's, the value
is read at the flush, an encoding or a value change converts the frame
even with no byte moved, and a pattern's release re-inits the effect.
The third (`13d7d8bd71`, token `0x85c5ed74`; devprobe `0xb074f1ef`, daily
`0x9cc1d614`) is comments and the host side (the overrun diagnostic takes
an absent tap as optional, the generator rejects a zero exponent): its
code is the second's. Accepted from the reviews, in the plan: the old
path applied CIE to the value and truncated the products, so widths
differ by a few ticks mid-range and the bottom is dimmer (a value of 1
was five ticks, now half a tick on alternate fields); the hue is not kept
under a value of about 4; the fixed mux term overstates a frame of
dithered ticks; the dev build with the tap on is unsupported.
`scripts/check_curve12.py` runs the flush's arithmetic over every
(chroma, value) at the three scales: every width below the terminal,
monotonic in both, the tops exact (1,195, 255, 2,550 ticks).

**On the board** (`flash-stage6-d9.log`; every flash over the data line
alone, the drain's moratorium kept in substance: nothing fed the pack):
the first version at 17:41 (`0xb4061e41`), the second at 17:46
(`0x3cc82483`). **The camera's before and after at value 13** (`d9_cam.sh`,
`d9cam/`): on the byte-path build the bare LEDs read red 1-4, blue 77-97
(pure blue, JD's complaint in numbers); on D9 red 14-28, blue 65-80: the
purple. **The gates on the second version** (`d9_gates.py v2e`, the
ladder's stage forced ACTIVE for the run, which the first three attempts
lacked and the instrument's own faults spoiled: Power saver's dim cap at
one idle minute had flattened 128 and 255 to 64, and its lights-off at
three had darkened the Jellybean step; the bare LEDs' positions taken
from the floor clips, the frame past 300 in each clip):

| gate | read at the four bare LEDs | result |
|---|---|---|
| the purple ramp 1, 2, 4, 8, 13, 26, 64, 128, 255 | blue 3.5/10 at 1, 18 at 2, 48 at 4, 60 at 8, 83 at 13, 125 at 26, 189 at 64, then the camera saturates; red 1-10 at 8 (one tick), 20-40 at 13 (two ticks), 43-80 at 26 | monotonic; the red from 13 on the camera (from 4 in ticks) |
| RGB toggled off and on at 64 | off: (3, 0, 2) on every LED; back on within 15% of before | pass |
| the dev pattern on (red at byte 1) and off | on: red 61-95 with green and blue under 10; off: the purple back | pass |
| Jellybean at 64 left 3 s, the value to 13 with no drop | 64: four different colours 80-177; 13: the same colours at 10-100, not dark | pass: the value lands without a drop |

The one honest miss in the table: at a value of 8 the purple's red is one
tick, which the camera reads at 1-10 against JD's floor finding that one
tick is "clearly visible" to the eye; the gate's criterion moved to 13
and 26. Above 64 the camera saturates and re-meters each clip (128 read
above 255 on the fourth run), so the ramp is judged to 64.

**Codex's two verify rounds** (`review-codex-row-isr-d9-verify-raw.md`,
`-verify2-raw.md`): no P1 in either; the first's P2s, taken in
`7edd3997f9` (the fourth version, token `0x4126ca00`, on white 18:02,
the gates run again: the ramp monotonic to 64, the toggle, the pattern,
Jellybean's dropless value change all pass): a mode that comes back
before a flush (A, a chunk of B, A) kept B's chunk in the buffer as
chroma, since QMK's compare at render saw A == A, so a two-line local
core edit in `rgb_task_start()` invalidates the last-flushed effect when
the effect to render changes (`quantum/rgb_matrix/rgb_matrix.c`); the
dev pattern's block on the wide path moved from its command to the hook
that installs its bytes (a chroma frame rendered before the command and
flushed after it would have shown at full for a frame); a pattern's
release clears the render buffer before the re-init (flags that exclude
LEDs would have kept raw bytes); the overrun diagnostic's tap fallback
takes only an op the build answers unhandled. The second round's
remainder: the transition validation (tearing at hue, brightness and
byte/wide changes, which a settled-frame camera run cannot see) and the
handler's warm window are owed with the exponent evening, and the last
stale comments went in the final commit, **`7dad75d506`: dev token
`0x5c792f4d` (on white from 18:07, the fourth's code), devprobe
`0xcadc2613`, daily `0xd49b8772`, the gaps 344 and 2,416 B**; white back
in the standing state at 18:08 (Power saver, the relay off, the daemon),
Hutch told.

**JD's eye on D9 (the L\* build, 20:0x):** "Looks much better on those
colors": a representative hue from about 4%, a fair mix even at 1-3%
(before: blue to 4%, cyan to 8%). The brightness "a smooth, even gradient
for most of the curve", but: steps imperceptible above about 25%, visible
jumps under 25% and big ones under 20% (20 to 19 noticeable, 13 to 12
big, 8 to 9 bigger, 3 to 2 and 2 to 1 big); and the hue wobbling at the
bottom: indigo at 6%, purple at 5, magenta at 4, almost blue at 3. Both
read straight off the arithmetic. The CIE L\* curve, stepped in equal
percent, changes the light 4% a step near half scale (under the eye's
8-9%), 9% at 20%, 13% at 10%, 33% at 3% and 50% at 2%: its linear bottom
is additive in ticks, so the ratios grow as the light falls. And at 3-6%
the purple's red is 1.6-2.3 ticks and its green 0.7-1.1, so rounding each
to a whole tick moves the red-to-blue ratio by up to a third from one
step to the next. **The build of 20:28 (`6e7924ac26`, dev `0xdfb885fb`;
devprobe `0x7b367d92`, daily `0x831605d8`; on JD's "go for it and flash
as soon as possible, before you send for a codex review")** does two
things: the dithered entry carries a quarter-tick fraction on top of a
base width under 16 ticks (bit 15 the flag, bits 11-14 a four-field
pattern, bits 0-10 the base; the handler drives the base plus this
field's bit), so the channels' ratios hold to an eighth of a tick; and
the curve is geometric (`gen_curve12.py --log`: a constant 3.1% a value
unit from half a tick at 1 to the top, about 8% a percent step
everywhere, the eye's threshold), **which moves the slider's middle: 49%
is about 2% of full light on it against 18% on L\*, and today's look sits
near 78%**. That trade is JD's to judge; the generator makes the next
candidate (`--gamma G`, `--log`, or a pinned midpoint) in a minute, and
the exhaustive host check (`scripts/check_curve12.py`) runs the flush's
arithmetic on any table. One more build at 20:36 on his ask
(`b45a904f11`, dev `0xc3b0ea56`; devprobe `0xeafa5d2a`, daily
`0xc0f7878f`): the menu editors' fast turn toned down, since a quick spin
stepped 8% a detent and skipped the steps he wanted to see: the shipped
builds 4% within 60 ms, the dev build none. With no acceleration the
range took him four spins, so the build of 20:41 (`a86a07610f`, dev
`0xfbcd040d`; devprobe `0x06cda486`, daily `0x6115beeb`) replaces the
fork with three tiers on every build, by the gap between detents: a slow
turn 1%, a medium spin (within 110 ms) 2%, a fast one (within 50 ms, or
two detents in one input) 3%, hue 1, 2 and 4 units (`config.h`'s
`MENU_FAST_*` and `MENU_MED_*`; `menu.h`'s defaults keep the two-tier
values for the host test). Codex's round on the dither
and the curve (`review-codex-row-isr-d9-dither-raw.md`, after the flash
on JD's word): READY, no P1 or P2; its notes: the flagged decode is seven
Thumb instructions with the shift hoisted; the channels' quarter patterns
share the phase, so a mixed-fraction LED cycles through mixed and
single-colour fields at 111 Hz (at the 267 us cadence it would be 52 Hz),
an eye result not a frequency one; the ratio error bound is 0.128 tick
after the fixed-point rounding; and on the devprobe flavour the log
curve's full chroma is dark to a value of 3 (the probe's raw patterns
unaffected). His eye on the curve is where the record ends tonight.

## Files

- `session.sh`, `session.log`: the six attempts and the clean run; `run-base.log`, `run-stage1.log`, `base.json`, `stage1.json`, `compare.txt`, `flash.log`.
- `settings-before.json`, `lighting-before.json`: the last run's dumps (restored); `settings-after-probe.json`.
- `dark_probe.py` / `dark_probe2.py` and their logs: the probes; `dark_after_sleep.*`: the aborted slept-board test (its relay wake is the third charge); `peek.log`: an HC_PEEK attempt that found white asleep.
- `fix_check.sh`, `fix_check.log`: the fix's flash and holds; `base_fix_check.sh`, `base_fix_check.log`: the base plus the fix, and stage 1 plus the fix back.
- Stage 2: `flash-stage2.log`, `run-stage2.log`, `stage2.json`, `compare-stage2.txt`, `sched-after-stage2-flash.txt`, `health-after-stage2-flash.txt`, `sched-after-stage2-run.txt`, `record-after-stage2-run.txt` (its sub-5 fields misread by 4 bytes, see above); the fix: `flash-stage2fix.log`, `run-stage2fix.log`, `stage2fix.json`, `compare-stage2fix.txt`, `sched-after-stage2fix.txt`; `power_saver_back.sh`, `power_saver_back.log`, `settings-after-mode.json`; `lighting-restore.log`, the backup put back at 21:13.
- `battery-before.txt`, `battery-after.txt`, `health-after-flash.txt`.
- 11-02: `scan_only_check.sh` (enter/exit, the first attempt: `scan-only-enter.json`, `scan-only-exit.json`, `scan-only-check.log`), `scan_only_key.sh` (the one-run check: `scan-only-key.json`, `scan-only-key.log`), `wake_read.sh` (`wake-dark-read.json`, `wake-dark-read.log`).
- 11-02 afternoon: `preflash_read.sh` (`preflash-read.json`, `preflash-read.log`), `flash-detector.log`, `silence_check.sh` (`silence-check.json`, `silence-check.log`), `wake_watch.sh` (the logger-driven wake read: `wake-detector-read.json`, `wake-detector-read.log`); `wake_read.sh` takes an optional label since 16:45 so a second read keeps the first's JSON.
- 11-02 evening: `warm_windows.sh` (`warm-windows.log`, `run-detector.log`, `detector.json`, `compare-detector.txt`, `sched-window-detector-before.txt` and `-after.txt`, `record-detector-before.txt` and `-after.txt`, `usb-detector-after.txt`).
- 11-02 night: `trim_on_wake.sh` and `trim_flash.sh` (`trim-on-wake.log`, `flash-trim.log`, `run-trim.log`, `trim.json`, `compare-trim.txt`, `compare-trim-vs-detector.txt`, the `-trim-` windows and records); `diag_on_wake.sh` and `diag_flash.sh` for the cost diagnostic (`95ef5cbc5d`): `readcost-diag.txt`, `sections-diag-1.txt`, `sections-diag-2.json`, `sched-window-diag.txt`, `record-diag.txt`, `usb-diag.txt`.

- 11-03, the presser's night (JD's advance go; every run hands-free): `../../scripts/presser_repl.py` (the presser from the logger's REPL: `pulse`, `batch`, `hold`, `--hold`), `../../scripts/presser_count.py`; `exit_on_usb.sh` and `exit_flash.sh` (`exit-on-usb.log`, `flash-exit.log`, `sections-exit-*`, `readcost-exit.txt`, `silence-check-exit.*`, `exit.json`, `compare-exit*.txt`, the `-exit-` windows and records); `presser_gate.sh LABEL TOKEN [boundary]` (`presser-gate-*.json/.log`: `exit`, `stage3`, `stage3b`, `stage3b-boundary`); `deep_wake_presser.sh N LABEL TOKEN` (`deep-wake-*.json/.log`: `exit`, `stage3`, `stage4`, `stage4b`); `settle_sweep.sh` (`settle-sweep-stage3.json/.log`); `stage3_flash.sh` (`stage3-flash-run.log`, `status-stage3.json`, `frmscan-stage3.txt`, `rows-stage3.txt`, `silence-check-stage3.log`); `stage3b_flash.sh` (`stage3b-flash-run.log`, `usb-stage3b-*.txt`, `record-stage3b-*.txt`, `silence-check-stage3b.*`, `stage3b.json`, `compare-stage3b*.txt`); `stage4_flash.sh` and `stage4b_flash.sh` (`stage4*-flash-run.log`, `rtc-status-stage4*-*.txt`, `overrun-status-stage4*-*.txt`, `burst-presses-stage4*.txt`, `stuck-stage4*.txt`, `stage4.json`, `compare-stage4*.txt`); `soak_watch.sh` (`soak-stage3b.jsonl`, white sleeping between reads) and `soak_watch_awake.sh` (`soak-stage4.jsonl`, `soak-stage4b.jsonl`: the night's reads, one JSON line each). The codex reviews: `../../plans/review-codex-row-isr-{exit,exit2,stage3,stage3-verify,stage3-frmno,stage4,stage4b}-2026-11-03-raw.md`.

## Lessons

- **The presser turns the scan's gates into counts, and a night runs
  itself.** One press from the logger's REPL wakes a deep-sleeping board
  (it enumerates ~4 s later with the data line on), so a runner can flash,
  gate and sleep white with nobody at the bench; the counts at the scan
  (op 28 sub 12) say what the matrix saw, `raw_edges` what reached
  debounce, `key_presses` what left it, and the three together place a
  miss (the 8 ms boundary is debounce's, the scan exact).
- **A hardware register can tear.** FRMNO updates low byte first over a
  few cycles at a byte carry; two adjacent loads can both land in it, so
  "read until two agree" needs the reads spaced past the tear (twelve
  cycles here). Measure a tear with back-to-back reads before trusting a
  retry.
- **Preemption doubles a bit-banged transfer, not "plus the handler's
  share".** The clock chip's 2.6 ms read ran to 5.5 ms with the handler
  and the tick through it; a deadline sized for the masked transfer then
  cuts the slowest. Measure the whole call per kind (op 22) before moving
  a deadline or a mask.
- **`uhubctl -a on` within a second of another script's `-a off` hangs**
  (twice, 26 and 22 min, the on in effect): pause 3 s and run it under
  `timeout 20`.
- **The ladder sleeps the board the moment the data line goes off** when
  the last key is more than 3 min back (the data line holds an awake board
  awake, nothing more): hold the ladder at Always on across a data cut
  (dev op 14 sub 1 arg 0, and 2 to put Power saver back) or wake it with a
  press first.
- **A `pkill -f NAME` kills any waiter whose command line names NAME**:
  the two launchers that waited on `soak_watch*` died at the runner's
  first line (harmless: the runner had already started).
- **A theory that matches the magnitude is still a theory.** Five software
  divides at 100-200 cycles each added up to the 19 us on paper, and the
  build without them cost the same; stage 2's own vector had divides and
  was fast. Stamp the sections before trimming anything.

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
