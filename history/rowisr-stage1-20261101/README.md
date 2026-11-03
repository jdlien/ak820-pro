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
