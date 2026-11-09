# Current status

Updated 2026-11-04, 20:45. The block below is where things stand, written to
be read cold. The dated blocks under it are the record as it was written
each day, newest first, and they end with the September crash hunt.

## 2026-11-03 night — stages 3 and 4 of the row ISR rewrite went onto white hands-free; stage 4b is on it with the night's soak

JD's advance go at 02:25 ("continue development autonomously, pressing
keys, measuring power draw, etc and flashing builds as you see fit"), the
presser built on the logger's QT Py (A1 = (0,13) Delete = F19, A0 =
(3,14) PgDn = F20), driven from the logger's REPL by
`scripts/presser_repl.py`; every flash of the night woken, pressed and
read with no hand on the board. The record, run by run:
[`../history/rowisr-stage1-20261101/README.md`](../history/rowisr-stage1-20261101/README.md),
from "The exit-only build's flash" on; the plan's process log from
02:27.

**On white since 05:08: stage 4b, `row-isr` `6b90f3b821`** (dev, token
`0x4215c3e2`, heap gap 400 B): stage 3's scan without mode writes (the
key row selected and deselected by BSET/BCLR alone, the columns as two
port reads, the settle on the scheduler's counter, the consume's XOR under
its lock, the rig's keys counted at the scan), the frame counter read
twice twelve cycles apart (the register tears at a byte carry, seen
directly: 48 torn reads in 16.8 million), the sections opt-in, and the
clock chip's transaction with the row ISR running through it for the
ordinary 10 ms transactions while the 5 ms ones (the pre-sleep read, the
wake's recovery) keep the hold-off. **What passed tonight:** the exit-only
build (6.6 us back by the stamps); the short-tap gate exact at 25, 15, 12
and 10 ms on both channels and with a cross-row chord, every press and
release counted at the scan and `raw_edges` exact (the consume's
undercount gone); the 8 ms boundary 72 +/- 2 of 100 over six batches
against the old scan's 76, the scan exact on all of them (debounce's
against the main loop's pass); Q1's settle sweep 19 of 19 exact from 2 us
down to no settle under JD's lighting and solid red, green and blue (the
default stays 2 us, all margin); six-row fairness within one; the silence
set 16 of 16 on stage 3b; deep sleep's wakes with the waking key kept 5
of 5 on the exit build, 5 of 5 on stage 3, 3 of 3 on stage 4 and 3 of 3
on 4b; page 4's handler mean 71.6 us a slot at 26.8% CPU (the detector
78.8, the sections' commit had hidden the exit-only saving). **What stage
4 taught:** unmasked, a 7-byte clock read stretches to ~5.5 ms, twice its
2.6 (the handler and the 20 kHz tick), so the deep sleep's 5 ms reads
timed out at 1.7% in a burst; 4b keeps the hold-off for those alone. The
night's soak (`soak_watch_awake.sh`, data on, the daemon syncing, a read
every 20 min to `soak-stage4b.jsonl`) **ran 4 h 16 min clean and ended
at 09:35**: the writer 52 runs settled with no restart, the 8-byte write
4.64 ms worst and the 7-byte read 5.47 against the 10 ms deadline, none
failed, 57.7 million frame-counter intervals judged and none rejected,
no pass >= 25 ms, no watchdog event. White went back to the standing state
(data off, the daemon running). **10:04, the camera run on 4b**
(`camera_runs.sh`): JD filming at 240 fps on Hutch's relay; a control of
20 held clock-chip reads (dark frames expected), then the daemon's sync
at 10:04:09 and the writer's unmasked write right after (its runs 52 to
53, the bracket settled); the board's side met, **JD's verdict on the
clip (no dark frame after 10:04:08) is the gate**, pending. White handed
to Hutch at 10:04 for Warren's keep-alive measurement M4. **Warren's
keep-alive is cherry-picked onto `row-isr`** (`c043db65dd`,
`a088b51c8b`; the dev artifact `via-dev-a088b51c8b-20261103-100249.bin`,
token `0xcf3e1101`, heap gap 376 B), not flashed: its flash waits on
JD's go after M4. JD is at the bench from 10:25 with a slow-motion
camera on a tripod (a Pixel 8 at 1/8, 240 fps) for the filmed gates.
**11:28: the camera gate is met**, from the Mac (the phone over adb,
`scripts/phonecam.py`; the clip measured by `scripts/clip_dips.py`):
two clock-chip writes forced by `ak820ctl clock` under a dev burst,
filmed at full white in a dark room, nothing in the writer's windows
where a held read is 39-82% of a frame's light
(`history/rowisr-stage1-20261101/README.md`, "The gate met from the
Mac"). The 10:04 clip was void (the lights were off: Power saver's
ladder, 3 min after the last key). Found on the way: the LCD's blits
cost the LEDs one slot's light on two or three rows (an open item in
`plans/ROW-ISR-PLAN.md`). White back in the standing state at
11:32:43 and handed to Hutch for M4; `pcf-unseen`'s deferral
retirement is unblocked, JD's call. The keep-alive artifact rebuilt
with Hutch's battery-icon commit: `via-dev-8355011389-20261103-110611.bin`,
token `0x0ec277e2`, not flashed.
**12:35: stage 5 built and reviewed, waiting on white.** JD's word "push
ahead to the next step" (the 125 us cadence, today; a go for stage 5
builds on white). Stage 5a (`4294a3befd`: the handler cheaper, the
exit's and the arm's extension snapshots replaced by the scheduler's
counter, the column loop unrolled with a Q6 multiply), 5b
(`2c11b9ff01`: `ROWISR_CADENCE_US 125` in config.h) and 5c
(`078216ec89`: codex's P2s, the width rounded and the scale 300/64 on
the measured duty, the dropped elapsed samples counted; the comments
`22bad4ea79`), reviewed READY twice (`plans/ROW-ISR-PLAN.md`'s log).
**The flash candidate: `via-dev-078216ec89-20261103-122923.bin`, token
`0x7c425589`**, after Hutch's M4 ends (~13:11 by Buzz's clock):
`stage5_flash.sh` (the flash, the cost window, the light, the presser
gate), then `stage5_gates.sh` (the UART counts, five wakes, the silence
set, the camera gate). The fallback for the night is `8355011389`
(`0x0ec277e2`, 4b with the keep-alive), agreed with Hutch.
**RESUME HERE (20:58 11-04): D9, the precision path, is on white and JD
is judging its curve by eye.** Written for a fresh session.

*The newest state, which overrides the paragraphs under it where they differ:*
**White runs the DEV build of `row-isr` `4790208267` since 13:39 11-09 (token `0x50f8f2d1`), the daily
soak ended: the daily paints the large song font's letters wrong at nearly every title change, over USB
too, so released firmware may carry it (`plans/BACKLOG.md`'s first item). Data line up 13:38:14,
daemon out 13:39:05, boot ~13:39:54, data line off and daemon back 13:40:10; relay 2 off but for
JD's 13:36:51-13:38:11 charge (Hutch's books). Next: a track change on dev, Bluetooth, then one
read of op 27's sticky failures and the display probe.**
**Before it, the DAILY build of `row-isr` `4790208267` from 00:35 11-07 (token `0x3501ba59`; dev
`0x50f8f2d1`), the soak restarted, the drain running on: daemon out and data line up 00:35:18, off and
back 00:36:13, relay 2 off throughout.** The paragraph after next says what it adds.
**Before it, the DAILY build of `row-isr` `4c85f385a9` from 13:55 11-05 (token `0xae868950`;
dev `0xc7bc1681`, devprobe `0xea3c593d`), the soak, with JD typing on it.** It has every effect
on the curve, the hold's ramp, the Cycles' place kept through a speed change, the ceilings
`SAVER_VAL` 191 (75%) and `DIM_VAL` 102 (40%), `Rain`, and Help's saturation keys. No bootloader
over USB and no dev hooks: the way back to dev is JD's `Fn`+`Esc`, and `ladder_check`, `current_map`
and `rowisr_diag` do not run on it. The gauge, `ak820 health` and `Fn`+`D` do. Flashes need his word.
⚠️ **On that build and every release through v0.3.1, the receiver for the Mac's lock-light frames is
missing, so no now-playing text or clock sync reaches the board wirelessly, while the daemon's log reads
as if they do (`lockchan=waiting`, frames counted as sent).** Release builds of the dongle's raw HID
(`raw81`) still lack it.
**Moved 11-05: the Bluetooth receiver is in every build, and on `ak820pro-jdlien`.** `row-isr`
`4790208267` (daily token `0x3501ba59`, heap gap 2136 B; dev `0x50f8f2d1`, 336 B; fpb `0x20196ead`,
2136 B), and the same two commits on `ak820pro-jdlien` at `cbd0d2f308` (daily `0xe41f89da`, 2016 B;
its dev compiles but fails `build.sh`'s check for the row ISR's detector, which that branch lacks
until the merge). Also in them: an idle pass reads no time for the two polls; the ACK deferral in
every build, the release builds' lost press or stuck release, older than the channel; a refused
legacy clock SET claims nothing; a wake forgets the raw-HID media lease. Host tests pass, and codex is
READY on both branches (`plans/review-codex-lockchan-every-build-raw.md`, `-verify-raw.md`), with the
limits it names: a sustained inbound stream can delay a report by the deferral's 50 ms cap, and an ACK
later than the cap can still be misattributed. On white since 00:35 11-07. **Verified on white 11-08:**
the title over Bluetooth on the panel by JD's eye ("the song title is showing"), and his first key after
~38 h untouched woke the board and the Mac, the daemon's wireless clock frame out 20 s later. ⚠️ A flash from a daily build:
`flash.sh` backs up first, so the data line comes up and the daemon goes out before JD's `Fn`+`Esc`, not
after it. **`deps.lock` stays at v0.3.1's `cfe6c2d3a5`:** the
branch was already one commit ahead of it, the combination of these commits with the old row ISR has
never run, and the row ISR's merge moves the pin. At that move, add `build.sh`'s check that every
flavour carries `lockchan_feed`. `--radio` stays dev-only until the 2.4G run.

**A new drain runs from FULL: relay 2 off at 13:56:13 11-05**, the gauge reading FULL 100%, the
pack 4140 mV, `charge_mah` -2754.007 in `history/power-bench-2026-10-15/power.csv`, the data line
off, Power saver, his lighting Alphas/Mods at 64%. It runs to the RGB cut. Leave relay 2 off; any
charge in the drain is noted beside it. The last drain averaged 11.6 mA, so about two weeks.
**mAh since FULL = `charge_mah` + 2754.007** while the count runs unbroken (a jump or a gap in
`charge_mah` means a restart: rebase it, as the last drain's section does). The charge before
it: relay 2 on at 20:11:25 11-04 (`charge_mah` 414.24), ~530 mA tapering to termination at
~05:48 11-05: 3119 mAh in over 9.6 h, 3168 by 13:56 with the charger's top-ups at FULL, against
the last drain's 3243 net out.
- **Flashed mid-drain at 00:35 11-07 (the daily `4790208267`), the count unbroken**, so the baseline
  stands: from 13:56:08 11-05 to 00:37 11-07 the logger has no gap over 5 s, no step off the
  current's integral and no charging sample. At the data line's rise (00:35:18): **368.2 mAh since
  FULL over 34.65 h, 10.63 mA mean**, the pack 4020 mV. The window to 00:36:13 cost 0.55 mAh (mean
  37 mA, peak 69).
- ⚠️ **The conditions change at 00:35:18 11-07: read the drain in two parts there.** The build
  before it dropped the Mac's lock-light frames; this one paints the title and clock from them, the
  load the dev builds carried in earlier drains, unmeasured here.
- **Part 2, from 00:35:18 11-07 to JD's first key at 14:52:09 11-08 (the logger to 14:53:12):
  38.3 h, 129.3 mAh, 3.375 mA mean**, under 6 mA 99.6% of the time. No one touched white in it, so
  it says nothing yet of the frames' load awake. The count is still unbroken: no gap, no jump, no
  charging sample. **Whole drain to 14:53 11-08: 72.95 h, 497.5 mAh since FULL, 12.4% of R4's
  4011.6, 87.6% left**, the pack 4004 mV.
  - The keep-alive woke white 43 times, every ~25:02 from 01:06:39 to 18:38:02 11-07 (~5 s each, peak
    ~27 mA), then stopped at its 18 h bound. Asleep, the mean was **3.386 mA from 07:00 to 18:00 11-07
    with the link held and the wakes in it, 3.186 mA from 19:30 11-07 to 11:00 11-08** after the
    module's drop: the keep-alive and the held link cost ~0.2 mA here.
  - **One wake unexplained: 11:20:17 11-08, 10 s, peak 26.9 mA, dark**, no key and nothing in the
    daemon's log. Its shape is a keep-alive wake's, but it came 16 h 42 min after the last one, well
    before the backstop's ~27.5 h, with the bound already past.
  - The board's gauge read 92% at about 14:53 (Power saver), against 87.6% by the count. ⚠️ It is not
    counting from FULL: the flash wiped the saved level, and a reboot on battery starts from the
    pack's voltage ([docs/battery.md](../docs/battery.md), "The level after a flash"), here 4020 mV
    on the plateau.
- **A data-line window, 11:45:48-11:45:51 11-09** (the daemon out ~11:45:46, back 11:45:51; relay 2
  off), Blackberry's health read for the stray pixels (BACKLOG). White was awake at ~41 mA through
  it, and the count is still unbroken, with no charging sample. At it: **93.8 h, 602.4 mAh since
  FULL, 15.0% used**, the pack 3992 mV.
- **Another, 12:11:46-12:11:52 11-09** (the daemon out 12:11:45, back 12:11:52; relay 2 off),
  Blackberry's second read for the stray pixels. White was awake at ~42 mA, and the count is still
  unbroken. At it: 94.3 h, 613.1 mAh since FULL, 15.3% used, 3994 mV.
- **The slider to 2.4G at ~13:25 11-09** (JD, to try the titles there), a reboot as a rule. Awake,
  white drew ~44.5 mA on 2.4G against ~42 on BT just before.
- ⚠️ **A charge, 13:36:51-13:38:11 11-09: the drain is no longer unbroken.** Relay 2 went on by
  mistake (taken for the data line) and the pack charged at ~294 mA, **6.56 mAh in** (`charge_mah`
  -2109.716 to -2116.276). I switched it off at 13:38:12, read back off. Just before it: **95.7 h,
  644.3 mAh since FULL, 16.1% used**, 3990 mV. The INA228 counts both ways, so `charge_mah +
  2754.007` stays exact as the **net** since FULL (637.7 mAh right after). Read the drain from here
  as net, with that charge inside it.
- **A data-line window, 13:38:14-13:40:10 11-09**, relay 2 off. With the daemon running, the
  title went over the cable at 13:38:16, and the stray pixels came with it: the paint fails on the
  daily over USB too (BACKLOG). Then the dev flash: the daemon out 13:39:05, flash.sh's backups
  13:39:06 (the battery log empty after the slider's reboot), JD's `Fn`+`Esc` between 13:39:20 and
  ~13:39:50, boot ~13:39:54 on **the dev build of `row-isr` `4790208267`** (token `0x50f8f2d1`,
  read back), settings and lighting restored; the data off and the daemon back at 13:40:10. JD moved
  the slider back to BT soon after (a reboot as a rule), and on dev the titles change cleanly.
- **Two data-line windows, white asleep, nothing read** (Blackberry; relay 2 off): the data up
  13:44:24-13:44:37 (the daemon out 13:44:22, back 13:44:37), then 13:44:51-13:45:07 (the daemon
  out 13:44:49, back 13:45:07), with a relay 1 tap at 13:44:51 that did not wake it (the wake rig
  has been broken since the bench moved). No key reached the Mac.
- **A data-line window, 13:53:03-13:53:07 11-09** (the daemon out 13:53:02, back 13:53:07; relay 2
  off), Blackberry's dev read on white's first wake after 13:44
  (`history/lcd-speckle-20261109/dev-read-1353.txt`).
- **The slider to 2.4G at ~14:21:50 11-09** (a reboot), then **a sleep measurement on 2.4G,
  14:22:50-14:38**: dev, Power saver, music playing, white untouched. It slept at 14:25:55 (3.33 mA
  floor), but the daemon's radio sessions (every ~34 s) each drew a ~5 s blip to ~16 mA. Twice it
  woke lit at ~44 mA for 3-4 min: 14:26:49 and 14:33:21. Both were KEY wakes on matrix columns
  nobody pressed (the wake ring, `history/lcd-speckle-20261109/wake-ring-1448.txt`), each within
  seconds of a radio session's start. **The mean over 14:26-14:38 was ~28 mA.**
- **A data-line window, 14:48:19-14:48:44 11-09** (JD's key woke white at 14:48:17; the daemon out
  14:48:17, back 14:48:44; relay 2 off): the wake ring read, then **fix A flashed from dev, no
  `Fn`+`Esc`**: `via-daily-6683c18134-20261109-142621.bin` (`row-isr`, token `0x2ca0ce80`; the
  title fix, raw81 in every build, the hardening). Settings restored.
- **Two more data-line windows on fix A** (relay 2 off), Blackberry's counter reads: 14:54:49-14:54:53
  (the daemon out 14:54:47, back 14:54:53; titles over 2.4G clean) and, after the slider back to BT
  at ~14:57 (a reboot), 14:58:19-14:58:24 (the daemon out 14:58:18, back 14:58:24; a BT title clean,
  the token read back). Every counter read zero both times
  (`history/lcd-speckle-20261109/fixA-read-1454.txt`, `fixA-read-1458.txt`).
- **The switchable diagnostic, from 15:14:53 11-09:** `lcd-diag` `5688b2a975`
  (`via-daily-5688b2a975-20261109-151210.bin`, token `0x8edc1022`; never merged), fix A with the
  old send kept beside it, a RAM mode byte, and boots in A's mode. Its flash: the data line up
  15:13:09-15:15:02 (the daemon out 15:13:08), JD's `Fn`+`Esc`, relay 2 off, no charging by the
  logger. Mode switches over the data line (Blackberry; relay 2 off throughout):
  - 15:14:57, set to old, inside the flash's window;
  - 15:38:31-15:38:33, read and set to A's mode;
  - 16:55:32-16:55:35, set to old for the camera;
  - 16:59:28-16:59:31, back to A's mode.

  Old mode garbled over BT, A's mode stayed clean (`plans/BACKLOG.md`'s first item).
- **A data-line window, 17:36:17-17:47:02 11-09** (the daemon out 17:36:16, back 17:47:03; relay 2
  off): a read of `lcd-diag`'s counters and flash.sh's backups for the split build `1bc39c8281`.
  No `Fn`+`Esc` came, so flash.sh timed out at 17:46:52 and nothing was written. White stays on
  `5688b2a975` in A's mode.

Tests on `feef9b4bfe`, whose firmware differs from this only in Help's text, Rain's mode number
and a moved rule: the ladder check passes in full, the warm window reads 51.9 us and 41.5% at full
white, the transitions show no blaze or dark frame (the README's end). JD's eye passed Rain. Codex's
two rounds since: no firmware failure, every P2 taken. **Never run on this ISR, by the record:
2.4G** (white has been on BT since before it; the plan's 2.4G gates have no result), so black's
turn should settle it (Warren has the list, 11-05). Next: the soak; black's night (Warren); the
docs' remainder, `site/power/`'s calculator among them, still pinned to the old curve; the merge
and release (at the merge, `check_effect_ids.py`'s `ADDED` line goes).

**Black's missed slots, closed.** Black's window of 22 missed slots (of 959,875 in 120 s, the
daemon's task stopped) was one event, not a rate: `flash_tidy.c`'s lit tidy, after 10 min without
input on USB power, crossed inside that window. `ak820 rowisr` read it on the same boot: tidies 1,
last lit, the last of 8 erases at uptime 600 s, and the 25 ms main-loop stall is the same event. So
one whole-store erase, two 1 KB pages, costs ~22 slots (2.75 ms). The floor without an erase is 1-3
misses in 120 s, 0.0002%, with no gap at the tick reaching 197 us, no UART overrun, the USB handler's
longest 85-91 us, and the same 1 missed in 120 s with the gap monitor on or off, so the monitor is
cleared (`plans/GREMLIN-RESULTS.md`, section 22). Not chased further, and no read of JD's is owed
for it. Unexplained and small: the 5 in the 60 s just after boot and the 9 in the 300 s dark window,
each below one erase's count. The tool stays: `ak820 rowisr` (Windows, dev builds;
`ak820-agent/src/rowdiag.rs`), and a missed count should be read beside its erases from here on.

**The curve is settled by JD's eye (`--stops 4`).** His calls: the battery's 20-35% less
light is fine, old profiles need no conversion, the `Fn`+arrow keys keep raw values, the
hold's 4-5 s is good, the Cycles' speed fix is good, Drift stays as it is for now. Then
the order below, its first item done.

*What is on white:* `row-isr` `a86a07610f`, dev token `0xfbcd040d` (since
20:41; devprobe `0x06cda486`, daily `0x6115beeb`; the gaps 344 and
2,416 B; its last commit the menu editors' three-tier acceleration on
every build: 1, 2 and 3 percent by the spin, JD dialling it in), in the standing state (the data line off, the daemon running,
relay 2 off, Power saver; JD's lighting Alphas/Mods hue 178 sat 219, val
131 as he left it), Hutch's on the books. The pack is at ~14% on a drain
to the RGB cut; the flash moratorium (JD, Hutch, 15:2x) stands in
substance: every flash since went over the data line alone and fed the
pack nothing, and each had JD's word. The next flash needs his word.

*What D9 is* (the plan's "D9 revised", the README's "D9 on white"): the
committed frame holds pulse widths at 12 bits; the uniform-value modes
(Solid, Alphas/Mods, the Cycles, Jellybean) render chroma and the flush
applies the value through a 16-bit curve (`rgb/curve12.h`, generated by
`scripts/gen_curve12.py`, checked by `scripts/check_curve12.py`); under
16 ticks the fraction of a tick is a four-field pattern; the dev RX tap
is opt-in (`CH582_RXTAP`); a two-line QMK core edit in `rgb_task_start()`
invalidates the last-flushed effect on a mode change. Six codex rounds
(`plans/review-codex-row-isr-d9-*-raw.md`): the design and the first code
NOT READY, both taken; two verify rounds with no P1; the dither and
curve build's round READY with no P1 or P2 (its notes in the README).

*Where JD's eye is:* on the L* build he found the hue right to 1-3%, the
brightness steps invisible above 25% and jumps under 20%, and a hue
wobble at 3-6%. The 20:28 build answers the wobble (the quarter-tick
dither) and offers a geometric curve (8% a percent step everywhere, the
slider's middle at 2% of full light instead of 18%). **His verdict on
that build is the next input.** If he wants L*'s middle with the
geometric's evenness, the answer is a pinned midpoint: generate a table
that is geometric below a chosen value and L*-like above (a short
addition to `gen_curve12.py`), build dev with `AK820_QMK_HOME=$PWD/
qmk_firmware-ak820pro-rowisr ./build.sh dev`, flash on his word
(`./flash.sh` with the daemon booted out and the data line up:
`history/rowisr-stage1-20261101/d9_cam.sh` shows the sequence; put the
standing state back after), and ask again. The camera gates are
`d9_gates.py LABEL` (hands-free, the ladder forced active; the bare
LEDs' frame positions are fixed in it).

*Then, in order:* (1) the curve settled and its codex round READY; (2)
the handler's warm window on D9 (`stage5_window.sh TOKEN LABEL 300`, the
LUT load left the hot path: expect a little under 5h's 52.8 us); (3) the
transition validation by camera (a brightness step inside a clip); (4)
the camera's linearity pass at 1-8 ticks on the devprobe flavour and its
look at the held-key remainder (`led all` / the Floor probe page; the
Pixel on the bench, `scripts/phonecam.py`); (5) after the RGB cut: the
daily soak (JD's `Fn`+`Esc` for the return), black's night on the branch
(Warren), the docs' remainder (leds.md's rewrite section, hardware.md's
table, sn32f299.md, the health pages, power.md's LED figures with the
11-04 mux intercept), the merge of `row-isr` onto `ak820pro-jdlien`,
`deps.lock`, the builds, a tag and the release. The memory files
`row-isr-plan` and `boards-white-black` carry the same, shorter.
**JD's eye is the open gate**: the hue to the bottom with the value keys,
the steps' evenness, no flicker at the dithered levels (values 1-3); then
the exponent evening (`scripts/gen_curve12.py --gamma G`). The flash
moratorium was kept in substance (every flash over the data line, the
pack fed nothing) with JD's "through to completion" as the go.

**Before it (17:25 11-04): stage 6's floor evening is done; white ran
the dev build of `row-isr` `245fcfe8e3`** (token `0x154c76fb`, heap gap
368 B: stage 5h plus the dev Diagnostics page **Floor probe** in the
Write test's place, sub 3's every-LED and split patterns, and the
held-key fix; the devprobe of the same commit is `0x82df55bc`, the daily
`0xa462d003`). **A flash moratorium on white until the RGB cut** (the
drain's last 15%, ~2 days): flashes over the data line feed the pack
nothing, but the agreed rule is none; the work until then is off the
board (D9's RAM ledger and design, the docs, black's night). The
readings (the README's "Stage 6's floor by eye", `floor-eye.log`): every
colour visible at one tick; the unit step lost at 6-7 ticks (red) and
11-12 (green, blue); green the brightest at equal ticks; the split match
red 12 = green 9-10 = blue 23 (red 1.26 and blue 2.4 times green: the
white's composition, not a table correction; equal ticks keep the hue).
Found: **a held key brightens the LEDs above and below it in its column**
at the dim end (the scan's microsecond on the just-deselected mux rail;
a stage 6 fix in the row ISR). The logger pass's current slope per colour
is in the README. **The mode was set to Always on for the session and
persisted by a restore: Power saver is put back with the standing state**
(done 15:13: the board's live record reads Power saver, and `~/Documents/ak820pro-profiles.json` was refreshed from it, since a flash from a hand-entered bootloader restores that file). Next, in order:
(1) the dev build back on white (`via-dev-bfff926086-20261104-141323.bin`,
`0x11e5314a`, hands-free) or the daily soak first (`via-daily-bfff926086-
20261104-141344.bin`, `0xf6243273`; the return needs JD's `Fn`+`Esc`);
(2) the camera's linearity pass (the phone at the capless keys, the
exposure locked, pixel sums at 1-8 ticks per colour; `led all` or the
page); (3) the held-key ghost: the fix is in (`245fcfe8e3`, the slot scans the
row whose rail it just deselected; codex READY), the key above no longer
brightens, but a held PgUp lights PgDn at 1 tick (the row below), so the
remainder is the camera's on the probe build, a held key in a column of
bare LEDs, not chased further on JD's call;
(4) D9's wide conversion with the floors, the eye's ratio and the gains
above; (5) stage 7 as before. White is Blackberry's until the standing
state is restored and Hutch told.

**Before it (10:05 11-04): white ran stage 5h since 08:33** (`row-isr`
`bde904e491`, dev token `0xfeeeb2db`, heap gap 368 B; flashed on JD's
08:30 go) **and every hands-free gate on it is met** (the README's
"Stage 5h on white"): the full-white window 52.8 us and 42.2% at 8,002
a second (5g 52.1/41.7, 5e 52.3/41.8), the lit draw 91.6 mA (the gate
89.1-95.2), 65 omissions in 300 s, 0 spurious, 0 invalid services, row
gap 3 ms; the silence set 10 of 10; the five wakes 5 of 5 kept the key
(0 spurious, 0 frame rejects, +2 losses a wake = the data cut's bus
events); and Hutch's M4 with-run on it ARRIVED (the rig's key 32 min
into a keep-alive-held sleep reached the Mac in the same second).
**White is Hutch's since 10:01, in the standing state on 5h** (the
lighting JD's Purple/Blue, Alphas/Mods val 125,
`lighting-5h-jd-choice.json`, which the flash restored in place of
last night's white at 141; claim it by message before any board
contact). Next, in order: (1) the daily build's short soak
(`via-daily-bde904e491-20261103-234032.bin`, `0xcaa61e41`: the
release's handler figure, ~45 us expected, the detector out; the flash
from dev is hands-free, the return to dev is `Fn`+`Esc`, so JD at the
board, or the daily left on for a stretch, his call); (2) stage 6's
floor evening (`devprobe` `via-devprobe-bde904e491-20261103-234052.bin`,
`0xefa1c31f`; the plan's "The floor is measured first, per colour":
JD's eye in a dark room per colour, the camera at the capless keys,
the logger); (3) black's night on the branch (Warren), the docs'
remainder (leds.md, hardware.md's table, sn32f299.md, the health
pages, power.md's LED figures), the merge of `row-isr` onto
`ak820pro-jdlien`, `deps.lock`, the daily and fpb builds, the tag and
the release, the clean-Windows install check. Bench notes from the
morning: the full-white window script (`stage5h_window_fullwhite.sh`)
presses the rig's Delete when the data line comes up with no board
(its first run found none, the flash's data cut having slept white at
once); the F19 listener swallows the rig's F19/F20 since 13:26 11-03,
so the presser gates no longer need Buzz locked, only white untouched.**
**Before it (23:45 11-03): stage 5h was built, codex READY twice (no
P1; its one P2 fixed; comment rot fixed), pushed, and waited for JD's go
to flash on 11-04: `row-isr` `bde904e491` (dev
`via-dev-bde904e491-20261103-234013.bin`, token `0xfeeeb2db`, heap gap
368 B; the daily `0xcaa61e41`, the detector out, 2656 B; the floor
probe `devprobe` `0xefa1c31f`), the per-slot judgment back, the
detector behind `ROWISR_USB_DETECT` (the dev build only), the silence
report's two fixes kept, `ROWISR_K_Q6` overridable for stage 6's floor
measurement with the drive accounting on the calibrated unit (the
README's "Stage 5h built overnight"). The flash command, once JD says
go: `history/rowisr-stage1-20261101/stage5_flash.sh
ak820pro-builds/out/via-dev-bde904e491-20261103-234013.bin 0xfeeeb2db
stage5h 300 no` (white claimed from Hutch first), then
`stage5g_window_fullwhite.sh` if JD's lighting is on it, then
`stage5_gates.sh 0xfeeeb2db stage5h 3` and `2`. On the flash: the full-white window, the
silence set (`stage5_gates.sh TOKEN stage5h 3`), the five wakes (`2`),
then a daily build's short soak. The dim-end question of 22:23 (the
value keys' plateaus at the bottom) is the CIE table before the byte,
recorded in the plan's stage 6 with the per-colour floor calibration JD
will do by eye (`devprobe`, the camera at the capless keys as the
check): "The floor is measured first, per colour". The clock-sync
comparison: 4b's night and 5g's evening the same within noise (the
README's table); no old-ISR sample on the Mac. **The 5g soak ended
00:35 clean** (4 h 1 min, 13 reads: losses 2 of the boot, 0 spurious,
14.8 million frame intervals judged and 0 rejected, the clock 49 runs
good and 0 restarts, 18,700 blits and no fault); **white is Hutch's
since 00:35, asleep in the standing state on 5g** (3.47 mA, the pack
28.7%) for Warren's M2/M3: claim it back before the 5h flash.**
**Before it (20:40 11-03): white runs stage 5g (`row-isr`
`4f19e6c31f`, token `0x34d7c5fb`) since 20:19 with the awake soak on it
from 20:34 (`soak_watch_awake.sh stage5g`, a read every 20 min, JD
typing); Blackberry stops it at about 00:35 and hands white to Hutch
asleep for Warren's M2/M3. JD's two calls are made: (1) the every-eighth
judgment measured 0.2 us (52.1 us, 41.7% at full white against 5e's
52.3, 41.8%), so **tomorrow's first commit reverts the decimation to the
per-slot judgment, keeps the silence report's two fixes (the pages
paired by the run count, the PENDING verdict) and puts the detector
behind a compile-time flag the dev build sets and the daily build does
not** (the release gets the ~7 us; the daily build then owes a short
soak of its own); (2) the timeline: tonight's awake soak instead of a
second night. Then: the silence set and the five wakes on the revert
build (skipped tonight on JD's instruction), black's night (Warren),
the clock-sync residuals of this night against the 4b/5e nights and the
10-20 old-ISR soak (JD's question: does the faster main loop tighten
them), the docs' remainder (leds.md, hardware.md's table, sn32f299.md,
the health pages, power.md's LED figures), the merge onto
`ak820pro-jdlien`, `deps.lock`, the daily and fpb builds, a tag. JD's
eye on 444 Hz: the colour fringe all but gone (a deliberate rapid
flick, the capless rig LEDs only); the screen's drawing about twice as
fast. The record: the README's "Stage 5g on white", the plan's "Stage
5g's reviews" and its log.**
**Before it (15:25 11-03): two of JD's calls open: (1) the every-eighth
silence judgment (~8 us of the 50 us handler, 40% to ~33%; two
aliasing silences inside 1 ms would count as one: a diagnostic
concession, the arm deadline and the dark-by-hardware untouched); (2)
the release pace: JD may skip the full night. The remaining evidence
the plan wants is an awake soak on 5e (4b's was 4 h clean), black's run
(Warren), then the merge onto `ak820pro-jdlien`, `deps.lock`, the daily
build and a tag.** White is Hutch's since 15:15 for the asleep night
(Warren's M2/M3); the awake soak conflicts with it, so the order is JD's.
**15:15: white handed to Hutch for the night on stage 5e
(`739fe1b635`, token `0xf222e31c`), asleep in the standing state, the
pack at 31% after a 40 min charge (relay 2 off).** The SRAM trial (5f,
`12f2c14cad`) measured no gain and is closed (`ROWISR_RAMTEXT 0`); the
per-colour holds and the value ladder are in the README. **Stage 5e on
white since 13:34** (5f from 14:31 to 15:06), the night's build. 5c (12:47) and 5d (13:02) before it. Stage
5's gates: the field 444 Hz; the light at full white 91.7-92.3 mA
against 4b's 92.1, the dark hold 31.3, the value ladder linear in the
byte over a 4.3 mA row-drive term; the handler ~50 us and ~40%
(codex: the 20% target to revise); omissions 0.003% quiet (the latency
tail, the USB handler's 80 us the lead) and 0.026% under mixed load
(the gate 0.1%); `row_gap_max` 3 ms; the presser exact from 10 ms; the
wakes 5 of 5 kept (spurious invocations at the wake noted); the silence
set all pass; the camera gate met (the writes unmasked, no trace); the
clock chip's transactions 7.5/6.1 ms; the low codes monotonic by
camera with an AE lock. Codex's judgment: keep 125 us and 1,535, a
small omission budget, release qualification after the operational
gates. **White's pack hit 15% at 13:42 (the low cap); relay 2 ON since
14:25 to charge for the per-colour and value-64 holds**, then white to
Hutch asleep for Warren's M2/M3 and the night's soak. Open for JD: the
every-eighth judgment (~8 us), the SRAM experiment (a daily flash by
hand or a dev build with the overrun rings compiled out), the release
tag after the nights on white and black. The record:
`history/rowisr-stage1-20261101/README.md` ("Stage 5 on white" and
after), the plan's log, `docs/leds.md` ("The row ISR rewrite").
**13:02: stage 5d is on white, `6a9fc0fcfe`, token `0x717d9b6a`** (5c
`078216ec89` from 12:47 to 13:01): the 444 Hz field, the light exact
(92.3 mA at full white against 92.1), the handler 49.5 us and 39.6% CPU
(the plan's 20% missed; the old driver's 73%), `row_gap_max` 3 ms, 5c's
0.096% omissions (all red slots: the scan slot past the 80 us deadline)
cut 26x by 5d's window 1,535 and 0.5 us settle to 87 in 300 s, the
presser 6 of 7 exact (8 ms at 88 of 100, better than 72). The record:
`history/rowisr-stage1-20261101/README.md`, "Stage 5 on white". Owed on
5d: the camera gate (13:09, running), the presser gates (the UART
counts, five wakes, the silence set: `stage5_gates.sh 0x717d9b6a
stage5d 123`, with Buzz LOCKED: the presser keys into the front app),
codex's and JD's judgment on the residual omissions, the night's soak
with Warren's M2/M3. **Owed to JD:** the camera gate on
4b (a forced PCF write with no dark frame, on USB and off; `pcf-unseen`'s
deferral stays until it passes); his eye on the light and the keys; the
plan's open question (two silences within 2 ms counted as two, the
per-slot judgment's ~12 us over stage 2); stage 5 waits on the witness
and the camera. Bench lessons of the night in the README's sections: an
`uhubctl -a on` within a second of another script's `-a off` hangs
(every runner pauses 3 s and bounds it), the ladder deep-sleeps the board
at a data cut when the last key is more than 3 min back (hold it or wake
it), a REPL soft reboot of the logger's QT Py does not restart the
drain's count.

## 2026-11-02 afternoon — D3's USB frame-counter detector is on white, its silence set 16 of 16

The long-silence detector of [`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md) (D3
case 5: the entry snapshot's USB frame counter against the tick
extension, modulo 2,048 ms, within 3 ms plus 0.2%; a bus-event
generation from a hook at the head of `usb_main.c`'s event callback;
three trust states at each end, the bus up, the frames fresh within
4 ms, a recovery pending after a stale) and the all-interrupt silence
injection (op 28 subs 6-9, `scripts/rowisr_diag.py usb|silence|report`)
went through nine codex rounds, each a real hole of one family,
discarded time surviving in a consumer's baseline, closed by one
invariant, wherever time is discarded the loss generation moves, and
onto white at 16:42 on JD's go (`row-isr` `5c0e6249d0`, token
`0x60d4a06b`, heap gap 464 B). **The silence set passed 16 of 16 as
predicted** ([`../history/rowisr-stage1-20261101/`](../history/rowisr-stage1-20261101/README.md),
"The detector flash and the silence set"): 5, 7.5 and 7.9 ms exact;
8.1 ms the guard's first rejection at a gap of 8.117 ms; 8.5 to 200 ms
the guard; 350, 700 and 1,049 ms past the tick's 349.5 ms alias and
caught by the frame counter; 1,000, 2,048 and 7,000 ms the guard at the
predicted residues; one loss per rejected case and never two; with the
data cut, 20 ms the guard's loss beside the suspend's and 350 ms
undetected, the declared limit. Before the flash, the last read of
stage 2's 21 h run (6 sleeps, 3 spurious invocations, no stall) and the
wake ring, which named the coordinator's 11:31 self-wake as the strays
backstop: one GPIO line left pending in the NVIC, every later WFI
returning at once (Warren's path, [`BACKLOG.md`](BACKLOG.md), "A
stray-wake storm"). **The wake read after it (19:06):** white slept on
its own at 16:46:47 and JD's key woke it at 19:05:58, the logger-driven
watcher reading the record 6 s later: woke on the key, 2.3 h asleep,
no stray, no reset; since the counter reset epoch losses 2 (the data
cut's bus event and the sleep, each one by design), spurious
invocations 1 and none across the sixteen silences, so the count
tracks the wake, where the slot timer restarts; the window after it
3,743.5 slots/s with nothing missed or omitted and the handler's mean
63.3 µs (52.5 on stage 2 at 11:10, not yet separated from the
lighting's content). White released at 19:07, in its standing state.
**The warm windows (20:43) separated it: the detector costs the handler
19 µs a slot** by page 4's hook, 59.8 to 78.8 µs in the runner's idle,
repaint and pcf windows at Always on, the CPU 22.4% to 29.5%, every
rate, gap and stall count unchanged. The object says where: two library
divides the detector put on every slot (the extension's span converted
to milliseconds for the judgment at step 1 and at the exit) beside three
that stage 2 already carried on every slot (the colour's modulo 3, the
boundaries count at step 1 and the exit). Next, on the branch: the
judgment in ticks and the other two by comparison and a counter, so the
hot path has no divide; codex; one flash on JD's key; the windows again.
White released at 20:45 in its standing state.
Still owed on stage 2: deep sleep's wakes with the waking key kept, the witness's
pulse gates and the long-gap injections (the presser and the witness's
wires first: JD's hands). Next hands-free: the injection ops with the
32-bit generation, the warm windows (the handler's mean under the
detector at a held lighting state among them).

**22:36, the slow first key.** After a 1 h 52 min sleep the first key on
white took a few seconds to register on the Mac. Measured from the Mac's
log, not the board: the module ends the Bluetooth link 30:00 after the
last traffic it saw (six drops in two days, each to the second), and the
rebuild at the next key takes the Mac 2.4 s, the keys in between lost.
Awake, the 5 s battery poll keeps the link; asleep, only the Mac's
lock-light frames do; so this came with deep sleep on 10-19, not with the
row ISR, and a sleep under 30 min keeps the link and the first key
instant (22:44:48, a 3 min sleep). Written up in
[`../docs/wireless.md`](../docs/wireless.md) ("The module ends the
link") and `BACKLOG.md` ("The first key after a long sleep"), with the
keep-alive wake as the idea, ~0.02 mA; accepted, pinned.

**23:19, the trim flashed: no gain.** On JD's go (23:03) a watcher on the
logger caught his key at 23:19:18 and `trim_flash.sh` put `a47c134079`
(token `0x1a291156`) on white and ran the warm windows: 80.0 us a slot
against the detector's 78.8 and stage 2's 59.8. The divides were not the
cost: stage 2's own vector, rebuilt for the comparison, had five divide
calls and was the fast one. The handler's new code cannot execute the
900 cycles; the reads can: six USB register reads a slot (FRMNO, CFG,
INSTS at each snapshot) and the 20 kHz tick's FRMNO read preempting it.
**The cost diagnostic `95ef5cbc5d` (token `0xda2a24d5`) went on white
at 00:06 11-03** (JD's go 23:50, his key 00:06:22; the watcher on USB
presence, the logger off the bench for the presser rig) and answered it:
**a register read is free** (11 cycles a loop iteration for the USB
registers and a RAM word alike), and **the handler's sections** over
37,000 services are entry snapshot 7.3 us, step 1 and the judgment 9.6,
steps 2-5 37.9, the arm 10.9, exit snapshot 5.8, exit judgment and
record 8.7, total 80.2: the detector's four sections 31 us with no hot
spot, the instruction count of its bookkeeping at 3-5 cycles an
instruction from flash. **The cadence (`1d73bf3ed5`, the judgment every eighth service) was
reverted on codex's P1**: a guard silence inside the eight-service
interval hides an aliasing silence that follows it within 2 ms, which
the per-service judgment catches; whether that must count as two is
JD's call (~8 us a slot). **The safe half, `f0ec5c68df`,
token `0x9e2d894a`, is on white since 02:27 11-03** (the exit snapshot
time only, the elapsed sample's verdict by the two spans and the
bus-event generation with the bus up, after codex's READY on
`5bf8de959a` and its verify of `7e438dc9b5`, every P2 fixed), flashed on
JD's advance go for the night and woken by the presser's own press: the
sections read 73.6 us against the diagnostic's 80.2 (the 6.6 us the
design said), page 4 still 80.2 because the dev build's section
instrumentation costs the same ~6 us outside the stamps (compiled out
next); the silence set 15 of 16, the one FAIL a pair of false
frame-counter rejections at the spans 0/256 ms, a torn FRMNO read at a
byte carry (seen twice on the trim too), fixed next by reading until two
reads agree (`history/rowisr-stage1-20261101/README.md`, "The exit-only
build's flash"). Also seen: two span rejections in the
trim's run, 0 ms by the extension and 256 by the frames, a torn FRMNO
read at a carry by the look of it; a read-until-equal if it recurs.

## 2026-11-02 morning — stage 2's scan-only and the wake with the RGB dark pass on white

Two of the stage 2 bring-up's owed checks, each on one key from JD
([`../history/rowisr-stage1-20261101/`](../history/rowisr-stage1-20261101/README.md),
"Scan-only on white"). **Scan-only:** light sleep's mask bit 0 with the
ladder held at LIGHTS_OFF put the row handler into scan-only within
1.5 s: 1,599 slots a second (the 625 µs slot), no missed slot, no pulse
emitted or omitted, the record unchanged; JD's key was seen with
scan-only in force; forcing ACTIVE took it out at once, 3,743/s with
pulses in the next window and the lighting unchanged. The first
attempt's "press now" handshake outlived the mask's 255 s limit, so the
check became one script that watches the key count itself. **The wake
with the RGB dark:** Power saver's own deep sleep at 11:07:30, JD's key
two minutes later, the lights straight up in his theme by his eye; the
read after it: slept 118 s, woke on the key, no stray, no reset, one
epoch loss for the sleep as designed, the handler at 3,743/s and 52.5 µs
in the 20 s after. Hutch's Rust `ak820 health --sched --window`
(`ae72d2b`) decoded page 7 on the board beside the Python. The record
since the 19:44 boot (15.4 h, 14.6 asleep, 4 sleeps): 10.42 M slots,
1,599 missed, 83 omitted, latency max 104.9 µs, elapsed max 207.8 µs,
3 spurious invocations (benign by design), no stall. White in its
standing state since 11:10:31; Hutch has it next for the long-sleep key
test. Still owed on stage 2: deep sleep's wakes with the waking key kept,
the witness's pulse gates and the long-gap injections (the presser and
the witness's wires first), D3's USB long-silence detector. Next
hands-free: D3's detector, the injection ops with the 32-bit generation,
the warm windows.

## 2026-11-01 night — the row ISR's stage 2 is on white, and its first flash settled the pin order

Stage 2 of [`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md), the hot path on direct
registers (CT16B4 the slot scheduler, CT16B0/1/2 one-shot pulse timers,
the ChibiOS PWM service gone), went on white at 19:20 after codex's two
reviews (NOT READY on one P1 and twelve P2s, then READY TO FLASH; both
dispositioned in the plan). **Its first frame was wrong in a way that
answered the plan's open question Q6:** peach alphas and pink mods from
the purple and blue theme, and at the boot default's near-white frame
magenta on exactly the nine keys one row above an LED-less matrix position
(A, X, C, V, N, M, `]`, PgDn, Right). The mux pins are R, B, G per key
row, as `config.h` always said; the old driver submitted B, G, then the
next row's R because its widths reached the LEDs one slot late, and stage
2's one-shot restart has no such lag. Fixed (`2d5a5d3e7f`), plus the
verify review's divide in the masked arm section (`b120a2069c`), flashed
at 19:44 and the holds rerun. **White runs stage 2 (`b120a2069c`, token
`0x4849bde6`) since 19:44**, in its standing state (Power saver put back by
hand at 20:09: the runner's settings dump had been taken after its Always
on, now fixed). Measured
([`../history/rowisr-stage1-20261101/`](../history/rowisr-stage1-20261101/README.md)):
the slot rate identical (3745/s), the handler's mean 60 µs against the
callback's 196 and the CPU share 22% against 73%, no stall, the row gaps
as before, the loop gap shorter; over 5.8 M slots 401 missed and 24
pulses omitted, the worst entry latency 105 µs, no epoch loss. Light: at
full scale within 1% of the base by total (white +3%, each single colour
4-5% under), and the old driver turns out not to be additive across
colours (its white 64 was 54% of the sum of its single colours; stage 2's
is the sum within 1%), so the plan's 3% state-by-state gate cannot be met
by any one scale: k stays 10 and the gate is restated. JD's eye at 20:45:
the theme right on every key, and a uniform white with nothing over the
nine holes at zero saturation, and his lighting back from the backup at
21:13 once the wake-gate session's case 3 had released white (two
deep-sleep wakes on his key with the RGB lit, no reset: they count toward
stage 2's wakes; the board read sat 191 before the restore, unexplained,
in the backlog). Next: the presser's
bring-up (stage 0's short-tap baseline, stage 1's key gates, stage 2's
deep sleep and scan-only), the witness's wires and the pulse gates, D3's
USB long-silence detector, then stage 3.

## 2026-11-01 evening — the row ISR's stage 1 measured on white: it passes, with one fix

Stage 1 of [`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md) went on white and came
through its A/B against the v0.3.0 candidate
([`../history/rowisr-stage1-20261101/`](../history/rowisr-stage1-20261101/README.md)):
the callback 1% slower, the CPU share identical, no stall, the row gaps as
before, every lit state's draw identical. The one difference, 1.3 mA more
at dark, was the audit's F-033 (`led_state[255]`, the NO_LED read), which
the new link layout had put on the wear-leveling cache; fixed on
`row-isr` (`b3270996d3`) in the audit's form and measured with the fix
in both builds (dark 40.6 mA on each). **White runs stage 1 plus the fix
(token `0x991e7b11`) since 18:09**, in its standing state. Owed on it
with the presser (11-02): Bootmagic, deep sleep's five wakes, the
phantom-or-missing count; and a warm set of windows for the ACK-timeout
comparison. The runner (`scripts/rowisr_baseline.py`) now holds the
ladder at Always on for a run. Next: the presser's bring-up and the
short-tap baseline, the witness's wires, then stage 2 from the measured
slot rate (3705/s on stage 1, 3744 on the base) and the pulse train.

## 2026-11-01 — v0.3.0 released

**v0.3.0 is published** ([the Release](https://github.com/jdlien/ak820-pro/releases/tag/v0.3.0)):
the firmware `4c7395a4c6` (the 10-31 audit's fixes, below, and the battery
readout's Icon only) as the daily and fpb builds, the agent 0.3.0 for
Windows, the assets and `via.json` unchanged since v0.2.0.
`ak820pro-jdlien` is fast-forwarded to it and `deps.lock` pins it (main
`d90032a`, the tag; `1b9adc8` the power page's sha). The candidate's checks
on white passed (14:40-16:29,
[`../history/v030-rc-white-20261101/`](../history/v030-rc-white-20261101/README.md)):
the new profiles restore's first run on hardware read back, the Win/Mac
flip, a deep sleep at 3.7-3.8 mA, the wake on a key. Then white went to
the row ISR's stage 1 A/B (below) at 16:29. It came back at 17:35 with
stage 1 on it (`a8a567308d`, token `0x19884af9`, flashed 17:12 with the
settings kept), its standing state restored (data off, the daemon running,
Power saver); the A/B's record is `../history/rowisr-stage1-20261101/`.

- ⚠️ **Three short charges in the drain:** the A/B's session woke white by
  closing relay 2 for a few seconds (the charger's edge wakes the board),
  with JD's go, and `power.csv` shows the pack charging at -546 mA each
  time: 16:46:47-16:46:49 (`charge_mah` 325.446 to 324.991, 0.46 mAh),
  16:47:58-16:48:03 (325.068 to 324.154, 0.91 mAh) and 17:45:42-17:45:48
  (371.762 to 370.844, 0.92 mAh). 2.29 mAh in, against 4,011.6:
  negligible to the runtime, but subtract it if the drain's arithmetic is
  ever done to the mAh. No more are planned; a slept-board test wakes
  white with a key.

- **v0.3.1 is published** ([the Release](https://github.com/jdlien/ak820-pro/releases/tag/v0.3.1),
  tagged at main `6cad24d` 22:25 11-01): the firmware `cfe6c2d3a5`
  (v0.3.0 plus F-033's fix, measured on white: a dark frame 40.6 mA,
  `plans/BACKLOG.md`) as the daily (token `0x09c4964a`) and fpb
  (`0x64eafd40`) builds of 18:36, heap gap 2288 B; the agent 0.3.1, a
  version bump only (`0da637a`); the assets and `via.json` unchanged since
  v0.2.0 (their hashes match v0.3.0's). `ak820pro-jdlien` and `deps.lock`
  have pointed at `cfe6c2d3a5` since 18:36.
- **The wake fixes' hardware gate is complete** (codex cleared
  `70f7c1ea10e` on four USB cases passing): case 1 on black 10-31; case 3
  on white 21:03-21:13 11-01, in both forms (data on to the sleeping board,
  then a key: the recovery's re-attach, enumerated 3.8 s after the wake;
  data off, a key, data on 30 s later: enumerated in 0.9 s), on stage 2,
  which carries v0.3.1's USB and sleep code unchanged
  ([`../history/wake-case3-20261101/`](../history/wake-case3-20261101/README.md));
  a host's attach does not wake a deep sleep (20.5 min, data on); cases 2
  (21:37, the cable's insertion woke black on CHRG, both bits off at the
  wake as the driver left them) and 4 (21:41-22:02, gremlin's S3 woken by
  black's key on a back port in two of three tries, nothing through the
  power-switched hub, the power button's resume with black kept) on black
  (`plans/GREMLIN-RESULTS.md` section 21). No reset in any; case 4's two
  cold power-ons were power losses on cable. Case 4 ran on black's
  pre-F-007 build: the mechanism, not F-007's guard (the release notes
  say so).
- **Owed:** the clean-Windows install check: `scripts/sandbox-6b.ps1`
  can't run on gremlin, whose Windows Sandbox was left off on 09-16 (the
  RDP black-screen fix). Turning it on needs an elevated feature install
  and a reboot of JD's PC: JD's call.
- **After any `deps.lock` pin:** run `scripts/power_model.py` and commit
  `site/power/power.json`, which records the pinned firmware's sha; the
  power-page CI's `--check` fails otherwise (it did on `d90032a`).
- **Not in it:** Warren's waking-key hold for BT (measurement first, on black, for the next release).

## 2026-11-01 evening — the witness's software and stage 0's runner written; white's session sequenced

JD okayed an interim flash of the row ISR's stage 1 on white mid-drain
(36% left, 4-5 days to the cut). The audit session flashes its v0.3.0
candidate (4c7395a4c6, `via-dev-4c7395a4c6-20261031-224044.bin`) and
runs its release checks first, then hands white over; the stage 1 A/B
follows in one sitting: `scripts/rowisr_baseline.py run --label base`,
`flash.sh` with `via-dev-a8a567308d-20261101-121551.bin`, the same run as
`stage1`, `compare`. Bench state for it: the daemon paused
(`launchctl bootout`/`bootstrap`), data on only for the session, relay 2
never touched, the lighting and the live settings dumped and restored.
Written today, no hardware needed: the waveform witness as a module of
the presser's board (`scripts/presser/witness.py`, the PIO at 125 MHz,
`scripts/witness.py` on the Mac, `scripts/witness_selftest.py`), and the
runner. The witness's front end is a 1 kΩ series resistor per line with
the keyboard on the bench's battery state, not an LVC buffer to buy
([`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md), rig item 4: the two rules). What
waits for the presser (JD wires it 11-02): stage 0's short-tap baseline,
Bootmagic, deep sleep's wakes, the phantom-or-missing count; for the
witness's wires: the pulse-train capture and stage 0b's lifecycle tests.

## 2026-11-01 — the row ISR rewrite's stage 1 built on `row-isr`; waiting on the rig

Stage 1 of [`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md) (D1: the RGB driver and the
key matrix board-local, `keyboards/a_jazz/ak820pro/rgb/rowisr.c`, with the
ChibiOS PWM machinery kept so the move can be measured against the old
driver) and stage 0b's dev op 28 (`rgb/rowisr_diag.c`,
`scripts/rowisr_diag.py`: the timers' registers, a marked row-only
hold-off, a one-LED pattern) are built on the firmware branch `row-isr`,
in the worktree `qmk_firmware-ak820pro-rowisr/` (built with
`AK820_QMK_HOME=$PWD/qmk_firmware-ak820pro-rowisr ./build.sh dev`; the main
clone stays the audit session's checkout). Based on `audit-fixes`
4c7395a4c6, which v0.3.0 fast-forwards onto the mainline, so no rebase is
expected. Builds: dev at a 136 B heap gap (the untouched base 152), daily
and fpb 2296 B. ⚠️ **Nothing flashed.** Stage 1 goes on white only after
stage 0's baseline is taken with the rig on the firmware white runs then,
and only on JD's word. Needed for stage 0: the presser on its own RP2040
(the bench's QT Py is the power logger) and the witness, which needs an LVC
Schmitt buffer per probed line (the plan's rig item 4). Codex reviewed
the move twice (`review-codex-row-isr-stage1-2026-11-01-raw.md`: NOT READY,
four P1s in the diagnostics and the bootloader quiesce, all fixed;
`review-codex-row-isr-stage1-verify-2026-11-01-raw.md`: READY TO FLASH for
stage 1's measurements), dispositioned in the plan under "Stage 1's
review". The branch is committed in the worktree at `a8a567308d`, not
pushed.

## 2026-10-31 night — the audit's fixes done on `audit-fixes`; v0.3.0 waits on white's check

The firmware audit's fixes ([`AUDIT-2026-10-31.md`](AUDIT-2026-10-31.md),
[`BACKLOG.md`](BACKLOG.md)'s audit section for what is fixed and open) are
done on the firmware's `audit-fixes`: five batches, codex's review of each
and two verify rounds with every finding fixed or dispositioned
(`review-codex-audit-batch1-2026-10-31.md` to `-batch4-`), then the low
sweep. 28 host tests in `scripts/audit_tests.sh`, plus the menu suite,
`raw81_test.py`, `profiles_host_test.py`, `diag_sim`. A protocol change for
any host tool: a profiles restore now applies the live record before its
commit, and the commit names the live settings' side (sub 3's [7]; sub 8
is gone, never released); `ak820profiles.py` does it.

**On white since 20:19 10-31: `57d1368f17`** (Batches 1-5, token
`0x191986cf`, [`../history/audit-fixes-flash2-20261031/`](../history/audit-fixes-flash2-20261031/README.md)).
Since then, on no board yet: the review fixes (the link hold's bound, the
raw HID cap, the WIP latch, `FC_INFO`, the restore's order, the boot gate,
the sticky store failure) and the low sweep. The last dev build:
`via-dev-d99b9d3499-20261031-222523.bin` (token `0x9a76b429`, heap gap
152 B); the daily `via-daily-d99b9d3499-20261031-222831.bin` (2288 B).
Codex's third verify of the second round and the low sweep was running at
22:30.

**The release, v0.3.0 (JD's go, 10-31):**
1. White wakes (one key: relay 2 stays off for the drain) and the release
   candidate goes on as a dev build with `flash.sh`; a check on it: a deep
   sleep and a wake on battery, typing over BT, a Win/Mac flip and back.
2. `ak820pro-jdlien` fast-forwards to `audit-fixes` (34 commits, clean),
   `deps.lock` pins it, `./build.sh daily` from the clean pin.
3. The agent changed since v0.2.0 (Warren's lock-light hold, `ak820 sleep`,
   the crash sites): `ak820-agent/Cargo.toml` and `Cargo.lock` to 0.3.0,
   `cargo test`.
4. `git tag -a v0.3.0`, push; CI makes the Release with the agent zip;
   `scripts/release-firmware.sh v0.3.0`.
5. `scripts/sandbox-6b.ps1 -Tag v0.3.0 -Wait` runs on Windows only: gremlin
   (Warren).
6. Docs: CLAUDE.md's "Current state", `README.md` if anything a stranger
   sees changed.

Not in it: Warren's waking-key hold for BT (on Batch 5, not ready at 22:30);
the wake fixes' case 3 is unrun (it needs a key on white with the script
armed). Next after the release: the row ISR rewrite, below.

## 2026-10-31 — the row ISR rewrite is planned and READY, not built

[`ROW-ISR-PLAN.md`](ROW-ISR-PLAN.md), revision 14: the RGB row ISR
rewritten board-local on direct registers, with a fixed-rate slot timer
on CT16B4, one-shot pulse timers parked dark, the key scan without mode
writes (which ends the clock chip's flicker), a 444 Hz field as the
release candidate and 889 Hz as an experiment, brightness preserved by
calibration against a stage-0 baseline. Made from two independent designs
(Claude's blind draft and codex's), a collaborator audit and fourteen
readiness reviews, the last one READY for stages 0-3; the raw reviews are
beside it as `review-codex-row-isr-*-raw.md`. Nothing built. Stage 0
needs the key-press rig rebuilt: JD's QT Py RP2040 with PC817C
optocouplers into gutted-switch plugs (parts arriving 11-01; the wiring
reference is a private artifact), plus a waveform witness. The first code,
the presser's CircuitPython and a serial backend for the bench scripts, is
written (`scripts/presser/`, `scripts/presser.py`, `--presser` in
`keydrop_test.py` and `relay_press_test.py`; 24 in-process checks pass;
nothing on a board yet). ⚠️ The QT Py on the bench is the power logger,
so the presser needs its own RP2040 (a second QT Py or a Pico).

## 2026-10-22 — RESUME HERE

### Where the project is

**Feature-complete for JD's board.** Everything planned is built, merged
and on the board:
- the power modes, the ladder and deep sleep;
- the gauge with its time-left estimate;
- the lock-light channel: the title, play times, and the clock (type 4)
  with Gremlin's frame trim;
- Gremlin's PCF writer fixes;
- the RGB model over 81 LEDs.

**The configuration menu is on the mainline and on JD's board since
19:08 10-25** (Warren's S0 through P4 and the Clock options; Fn + the
knob's click opens it). It went on mid-drain at JD's word instead of after
the drain. What is left is real use and a soak, and the polish and release
for other owners.

**Settings profiles are complete on JD's board since 13:29 10-26**: P5a-P5e
and P5c (`13c5e910cb`, main `77220e2`), eight slots with Save new, the
preview and Rename. Before it, **P5a and P5b from 09:49 10-26**
(`plans/SETTINGS-PROFILES-PLAN.md`): P5a, the store, `HC_PROFILES` and
`flash.sh`'s profiles backup; P5b, the Profiles pages and the
Next/Previous keys. P5b went on from Warren's branch so JD could look at
the pages on his own board, and merged after his look (main `a252afd`).
**The profile page's polish since 16:01 10-26** (`553108e5f2`, main
`6361951`): the actions' icons, the summary's grey rule and the 300 ms
preview; and since 20:29, the menu's idle close at 60 s (`1f3c79e904`,
main `94d4fa3`). Fn+A and Fn+S are the Previous and Next profile keys on
both Fn layers. **Since 21:54 10-27, Warren's clock-chip flicker fix
ahead of the mainline** (`ecb10f0e9b`, `gremlin/pcf-unseen`), on top of
10-27's mainline (`ce3f842de2`, main `ccb9ea0`): the Win/Mac switch's
profiles, the battery readout's Both, Reset settings and the Power page's
bulbs.

### Pending, decided (10-29)

- **The overnight cable-out run (10-28/29): clean, not a reproduction**
  (`../history/ds-phase-cableout-20261029/`). Warren's `fcb7ae00b4` on
  JD's board, on its pack, the USB cable pulled out of the keyboard by
  01:38 10-29, so the data lines floated as on gremlin's board (the relay
  plus `uhubctl` leave them held by the hub's pull-downs). The night's
  sleep, 03:55:05 to JD's key at 08:52:51 with the cable still out:
  15,012 counted seconds, 0 strays, 3.12 mA, no reset (the watchdog record
  empty, slot 10 only the check's sleep). So ~15,000 per-second RTC wakes
  with the lines floating and one certain real wake, all clean. Read
  08:55:09-08:55:39 (data on, the daemon paused); sent to Warren.
- **Running from ~08:55 10-29: Power saver for a day of JD's use with the
  cable out,** for many sleeps and real wakes in gremlin's condition (a
  sleep after every 3 min pause). It stretches the drain's runtime against
  Balanced: note it in the drain's figures. The evening: the cable in,
  data on, the daemon paused, `ds_slots.py` (slots 0-10, the watchdog
  record), the power log's sleeps and any restart, then back to Balanced
  if JD wants.
- **Done 09:04 10-29: the lock-light hold at 3 min, with two log lines**
  (main `9bfdbb0`, the daemon 0.2.0 `v0.2.0-7-g9bfdbb0` installed on Buzz
  with `--clock --radio --lockchan`). `HOLD_IDLE` held text and transport
  frames once the host's input had been idle 45 s, so on BT a track that
  changed while nobody touched the Mac showed only at the next touch. 3 min
  costs nothing in Balanced (asleep at 20 min), and is bounded in Power
  saver and Lights out (`BACKLOG.md`, "Lock-light frames into a sleeping
  board"). The log now says `lockchan: title from the player ...` when a
  title reaches the channel and `lockchan: held, N s without input: ...`
  when a frame waits. On gremlin since 09:06:50 (Warren; Windows tests 497
  pass, the 2 old local_time failures unchanged).

### What is running

- **Firmware on white since 17:28 10-30: `5c8c5f5ea8`** (the branch
  `icon-only` on the mainline `8ec0c8b9b4`; dev, token `0x5b880dd4`, heap
  gap 224 B): the battery readout's Icon only (`BACKLOG.md`, "Icon only";
  `MENU-TEXT.md`, "Battery"). Flashed mid-drain on its pack with the
  settings kept (`../history/icon-only-20261030/`). Warren's ds-phase
  diagnostics are off white now (its run there was clean: 32 sleeps, no
  reset); they run on black.
- **Before it, on JD's board from 00:03 10-29: Warren's `fcb7ae00b4`**
  (`gremlin/ds-phase`; dev, token `0xf2a645a7`, heap gap 152 B): the
  build below plus codex's fixes (the kept RAM checked at every boot, the
  sequence reserved at the teardown) and **op 24 slot 10**, the sleep a
  reset cut short, frozen at boot so the next sleep can't overwrite it.
  Checked: `../history/ds-phase-check-20261029-0002/`. USB data on
  00:02:36 for the flash, off after it.
- **Before it, from 23:51 10-28: Warren's `27d1105dc1`**
  (`gremlin/ds-phase`, on `8ec0c8b9b4` below; dev, token `0xbc3b64c4`,
  heap gap 184 B): deep sleep's phases in the watchdog record, and the sleep
  under way kept through a reset (op 24 slot 9). It's the diagnostic for
  gremlin's WDT reset in a deep sleep ([`BACKLOG.md`](BACKLOG.md), "A WDT
  reset inside a deep sleep on gremlin's board"). Flashed twice, 23:50-23:53,
  flash.sh exit 0 each time, everything restored. Before it, three unfed
  armed sleeps showed the WDT does not count in Deep-sleep
  (`../history/wdt-asleep-20261028-2330/`). USB data off from 23:53:47.
- **Before it, from 23:09 10-28: `8ec0c8b9b4`** (dev,
  `via-dev-8ec0c8b9b4-20261028-230846.bin`, token `0xe612779e`, 240,582 B,
  heap gap 224 B, the branch `more-info` on the mainline below): Help's
  More info (P1d), the credits beside the splash's bunny and a turn to a QR
  code to the repository, in all three faces
  ([`MENU-TEXT.md`](MENU-TEXT.md), "Help > More info"). The art is
  `scripts/gen_menu_art.py`'s (a stdlib QR encoder; the code decodes with
  macOS's CIDetector and Vision from the host test's frames in every face).
  Every host check passes (ASan and UBSan too), and the oracle matches
  every frame but the dev Write test's row, as before. flash.sh exit 0 at
  23:09:41, everything restored; the screen's default level 80 went on
  with it (a default only: the live level stays JD's). Codex: no findings,
  "OK to keep on the board". JD at 23:40: the page looks good, and the QR
  code scans on his iPhone. USB data on 20:18:58-23:31:49; the intervals
  after it are in `../history/wdt-asleep-20261028-2330/`.
- **The mainline is `c4bc085271` since the evening of 10-28** (Warren
  fast-forwarded `ak820pro-jdlien` from `ce3f842de2` and pinned
  `deps.lock`; JD: "we should get everything merged into main now"). It is
  JD's board's build plus the screen's default level 80, and it carries
  Warren's `gremlin/pcf-unseen` and the dev Write test. Gremlin's keyboard
  ran it from 20:51 (token `0x189635f2`); JD on the Font page there:
  "Identical to the board on Buzz."
  Since then the boards are called white (JD's) and black (gremlin's).
  Black ran `8ec0c8b9b4` dev (token `0xb5f2fdab`, flashed from Gizmo at
  23:34 10-28), from 12:43 10-30 Warren's ds-phase `fcb7ae00b4`
  (token `0xf2a645a7`, `../history/ds-phase-black-20261030/`), and since
  03:19 10-31 `05ef0f5bbc9` (token `0x4de76a30`, after `935e6e1bd2` from
  03:12): the wake's finer phases (sites 64-67, the CT16B3 spin at 66)
  and phase 31's interrupt census (op 24 slot 11), read on gremlin with
  `ak820 sleep` (GREMLIN-RESULTS §21). Its unfed sleep (04:00 10-31, the
  cable pulled by JD) ran 120 counted s with no reset, so the WDT does
  not count in Deep-sleep on black either; that wake's census caught the
  audit's F-045 state (`BUS_SUSPEND` latched, `PHY_EN` on, `ESD_EN` off)
  with no USB interrupt in the window. 10-28's shape ran next (05:00 to
  14:12 10-31, in Power saver where 10-28 was Balanced: 14 min idle on
  USB, the cable pulled, untouched):
  9 h 12 min asleep and no reset, 29,659 counted seconds each a return to
  flash and a feed, so the per-second loop is unlikely to be the site;
  its census showed `ESD_EN` off again. Black stays on the ladder for a
  repeat of the watchdog reset in a deep sleep.
- **Before it, from 20:39 10-28: `fbc6c4a1fd`** (dev, token
  `0xd044efc5`): the build below plus bold page titles and a bold song title
  in 10px (JD: "we still judiciously use bold"). flash.sh exit 0 at
  20:39:48, everything restored. B8's redraw times measured at 20:30 on the
  build below (`plans/MENU-8X16-PLAN.md`). Codex: no findings.
- **The screen's default level 80, from 60** (config.h; a fresh flash and
  Reset settings): built at 20:42 without a flash (JD: "no need to flash
  this"), and on the board with the More info build at 23:09.
- **Before it, from 20:19 10-28: `8b0f47e245`** (dev,
  `via-dev-8b0f47e245-20261028-201700.bin`, token `0xb9f4c717`, 236,758 B,
  heap gap 224 B): JD's decisions relayed by ak820-pro-90. Terminus regular
  as a third face (8px, 10px, 10px bold), the Font page's preview after a
  0.3 s rest and its note, the face saved in every profile, About in
  Diagnostics as System info (fourteen top-level rows), the camera page
  removed. Every host check and the oracle pass. JD: "Flash it now, if
  there are substantive fixes, we can flash that again": flash.sh exit 0 at
  20:19:27, everything restored (the live settings in 8px). Codex's
  review came back after: no findings, "OK to flash". USB data on 18:22:30-19:53:16, and again
  from 20:18:58 for this flash.
- **Firmware on JD's board since 18:59 10-28: `ccfe080920`** (token
  `0x65019724`): the build below plus the 10px face's icons from the
  12 px set in four greys, and the Font icon JD picked (both faces).
  flash.sh exit 0 at 18:59:54. Codex reviewed both evening commits
  (the spacing and the icons): no findings, "OK to keep on the board"
  (`plans/review-codex-menu-font-switch-2026-10-28.md`).
- **Before it, from 18:44 10-28: `59b2c9d7b3`** (token
  `0x1765e95a`): the build below plus the dashboard's spacing (the song
  lines a row apart, the clock 2 down, the lock row 1 down) and the Font
  values renamed 8px and 10px. flash.sh exit 0 at 18:44:35, everything
  restored. Its predecessor ran 18:22-18:44 with no pass >= 25 ms
  (longest 16 ms). USB data on 18:22:30-19:53:16 (relay 2 off).
- **Before it, from 18:22 10-28: `36fe62ea9c`**, the Font
  setting (`plans/MENU-8X16-PLAN.md`), on the firmware's local `menu-8x16`,
  not pushed (`via-dev-36fe62ea9c-20261028-170658.bin`, token `0xf9274d6f`,
  heap gap 128 B). Codex cleared it. Flashed mid-drain on the pack:
  flash.sh exit 0 at 18:23:00, the keymap, the profiles and the live
  settings restored and read back, the clock synced at 18:23:03 (-188.8 ms
  to -0.2), no pass >= 25 ms in the first health read. USB data on
  17:09:05-17:21:17 (the board asleep, never enumerated, nothing flashed)
  and again from 18:22:30 for the flash and B8's look. Next: B8 on the
  board (the plan's checklist).
- **Before it, from 11:04:59 10-28: `3b6e43ef73`, a local
  branch `font-test`** (dev, token `0xcddf82ef`, heap gap 128 B, the
  floor): `ecb10f0e9b` below plus a temporary Font test page under
  Diagnostics (dev builds only), which turns through whole 128 x 128
  frames read from the external flash at 0xE00000 ("AKFT" and a count,
  then a frame every 32 KB), to judge the 8 x 16 menu faces on the panel
  itself (`plans/config-menu-mockup.html`). An independent review found
  nothing at P1 or P2. Not for merging: drop it when the face is chosen.
  - **Flashed mid-drain, on battery** (relay 2 off), with JD's go. The
    USB data had been on since 10:31:36, when the Mac rebooted (the hub
    came back with the port on). The jump waited once for a key, then
    took; `flash.sh` restored and read back the keymap, the two profiles
    and the live settings.
  - **The frames:** 16 of the 44 rendered (Cozette as built, 7; Terminus
    Bold, 9), 557,056 B to 0xE00000, CRC verified on the board, 293 s at
    about 2.7 KB/s (27 B a raw-HID round trip), the daemon paused
    11:21:01-11:25:55. A first try at all 44 (1.47 MB, about 11 min) ran
    in the foreground with its progress hidden and was stopped partway
    (the daemon down 11:06-11:15); the 16-frame write replaced its start,
    and the header's count keeps the page off the rest.
  - **Data off at 11:26:09.**
  - ⚠️ **The frames must be lo byte first:** the flash-to-panel DMA swaps
    each pair (`mkanim.py` says the same of its frames). The first upload
    was hi first, and JD saw the dim grey (#C8C8C8) as a dark purple.
    `frames.js` was fixed, and a second upload put the comparison on the
    board: the top level once in each face (Cozette, Terminus Bold,
    Terminus, Spleen, Dina Bold, Dina), its title naming the face; 229,376
    B, CRC verified, 123 s, the daemon paused 11:49:33-11:51:37. Data on
    again for it, 11:48:54-11:51:42.
- **Before it, from 21:54:52 10-27: `ecb10f0e9b`, Warren's
  `gremlin/pcf-unseen`, not yet merged** (dev, token `0xdc5524d4`, heap gap
  128 B, exactly the floor). It is the mainline `ce3f842de2` (main
  `ccb9ea0`: each side of the Win/Mac switch keeps its own profile, the
  battery readout's Both, JD's defaults and Reset settings, the Power
  page's bulbs) plus `gremlin/write-test` (the softer LED blink at an
  internal-flash write, the early cleanup, the dev Write test in
  Diagnostics) and the PCF write only where nobody watches the LEDs: on
  USB it waits for the lights dark or 10 min without input; off USB it goes
  at once. Codex four rounds (`plans/review-codex-pcf-unseen-2026-10-27.md`
  on `warren/config-menu`); GREMLIN-RESULTS §20z. Main's host side runs it
  as is (Warren's branch adds only tests).
  - **Flashed mid-drain, on battery** (relay 2 off), at JD's word ("flash
    the latest"): data on at 21:54:21, the jump at once. `flash.sh`
    restored and read back the keymap, converted the two profiles
    ("Purple/Blue", "Rainbow Slow") to the switch's sides, both sides
    loading "Purple/Blue", and restored the live settings (Purple/Blue,
    screen 69%, battery hours, Balanced).
  - **The clock:** +1823.4 ms at the first sync (the PCF read at boot,
    likely drifting since USB data went off 25 h earlier), -1693.8 ms at
    the next (the period re-learning), then -13.9 and -33.3 with the loop
    moving. Data off at 22:06:03: 7.2 mAh in the window.
  - **Back to the pin:** `setup.sh` checks the firmware clone's HEAD
    against `deps.lock`, so `git -C qmk_firmware-ak820pro checkout
    ak820pro-jdlien` before the next `setup.sh`, or fast-forward to the
    merge when it lands.
- **Before it: `1f3c79e904`, from 20:29:34 10-26, the mainline from
  `94d4fa3` to `ccb9ea0`** (dev, token `0x60a8fe4b`, heap gap 136 B).
  It is `553108e5f2` with the menu's idle close at 60 s, not 24; editors,
  Pairing and Rename keep the 3-minute backstop. GREMLIN-RESULTS §20u.
  - **Flashed mid-drain, on battery** (relay 2 off), with JD's go: data
    on at 20:28:39; the jump waited 26 times for keys to go quiet (JD
    typing). `flash.sh` restored and read back the keymap (with Fn+A and
    Fn+S on `PROF_PRV` and `PROF_NXT`, bound in VIA at 16:16), the
    profiles and the live settings.
  - **The clock:** -389.3 ms at the first sync, -1551.2 ms at the next,
    then -37.6 with the loop moving. Data off at 20:40:34: 7.3 mAh in the
    window.
- **Before it: `553108e5f2`, from 16:01:57 10-26, the mainline from
  `6361951` to `94d4fa3`** (dev, token `0x9286ca96`, 219,522 B, heap gap
  136 B). It is `13c5e910cb` plus Warren's profile page polish, menu
  code and font data only: the actions' icons (circled arrows for Load and
  Save, a pencil for Rename, a trashcan for Delete), a grey rule above each
  profile's summary with the bulb on its H/S/B line, and the preview after
  300 ms, not 600. No storage or protocol change. GREMLIN-RESULTS §20r-t;
  JD had it on gremlin's keyboard from ~15:14.
  - **Flashed mid-drain, on battery** (relay 2 off), with JD's go: data
    on at 16:01:21; the jump waited seven times for keys to go quiet (JD
    typing). `flash.sh` restored and read back the keymap, the profiles
    (one saved, "Purple/Blue") and the live settings.
  - **The clock:** -321.2 ms at the first sync, -1721.0 ms at the next
    (the period re-learning), then -28.6 with the loop moving. Data off at
    16:13:01: 6.81 mAh in the window.
- **Before it: `13c5e910cb`, from 13:29:59 10-26, the mainline from
  `77220e2` to `6361951`** (dev, token `0xffc7a951`, heap gap 136 B).
  It is `57d5e90030` plus Warren's P5d (eight slots, Save new; the block
  218 B at 806-1023, magic 0xA2, nine HC_PROFILES pages, sub 7 the
  geometry; VIA's macros 19 B), P5e (a 0.6 s rest on a profile previews
  its lighting and screen) and P5c (Rename, with `action_tapping_idle()`:
  twelve core files). GREMLIN-RESULTS §20o-q.
  - **Flashed mid-drain, on battery** (relay 2 off), with JD's go: data
    on at 13:29:30, the jump took at once. The first flash that kept the
    settings: `flash.sh` saved and restored the live settings (Balanced,
    24h:ss, locks 1, charging 0, percent) through `HC_PROFILES`; no
    profiles were saved on the board, so none converted. The screen read
    61 before and 63 after: JD adjusting it during the flash, not the
    restore.
  - **The clock:** -264.3 ms at the first sync, -1676.5 ms at the next
    (the period, which no restore carries, re-learning), then -23.8 with
    the loop moving. Data off at 13:41:04: 6.71 mAh in the window.
- **Before it: `57d5e90030`, from 09:49 10-26, the mainline from
  `a252afd` to `77220e2`** (dev, token `0xde2973aa`, 214,346 B, heap gap 136 B).
  Main `a252afd` pinned it (Warren's merge after JD's look). It is `5ecc9a32cc` (P5a and Warren's effects'
  speeds, `93e55f78`) plus P5b: the Profiles row as
  page one's last (Bootloader to page two), the Profiles and slot pages,
  Load, Save and Delete with confirms, the summary, the `*`, and `PROF_NXT`
  and `PROF_PRV`, appended and unbound. Codex cleared it in six rounds
  (`plans/review-codex-p5b-code-2026-10-25.md` on `warren/config-menu`);
  Warren's board passes are GREMLIN-RESULTS §20n, with JD's look and a
  power cycle on this board (slider to cable, cable out): the profiles
  came back and loaded.
  - **Flashed mid-drain, on battery** (relay 2 off throughout), with JD's
    go: data on at 09:49:04, the jump waited three times for keys to go
    quiet (JD typing), and `flash.sh` restored and verified the keymap and
    the lighting. Its profiles step skipped, as it must from firmware
    before P5a, so the EEPROM's settings reset once more: Balanced, and the
    screen, indicator, clock and readout settings to their defaults. Every
    flash from here keeps them.
  - **The clock:** -402.0 ms at the first sync (09:49:47), then -1465.6,
    then -14.5 and -30.0 ms with the loop still moving, as after the flash
    before. Data off at 10:00:57.
- **Before it: `30f1e0cfde`, the mainline until 10-26** (dev, token
  `0x195cbf4c`, 206,326 B, heap gap 128 B, the floor), from 19:08:05
  10-25. `ak820pro-jdlien` and `deps.lock` point at it, and ChibiOS-Contrib
  at `5a1674e905` (main `7a679e9`, Warren's merge). It is `b9555ff3e6` plus
  Warren's `gremlin/s1`: the configuration menu (S0, S1, P1a-P4, the Clock
  options), the LED fix (`gremlin/fill-poll`) and the wake fix below.
  - **Flashed mid-drain, on battery** (relay 2 off throughout), with JD's
    go: data on at 19:06:57, the jump took at once, and `flash.sh` restored
    and verified the keymap and the lighting.
  - **The flash reset what the EEPROM holds**: the power mode back to
    Balanced, and the screen, indicator, clock and battery readout settings
    to their defaults.
  - **The clock:** the first sync found +4556.0 ms (21 h untethered with no
    lock-light frames, below). The RTC period re-learnt as before: -1559.3,
    then -19.8 to -26.9 ms a 5 min sync with the loop still moving (the
    chip warming awake on USB), past the first period save at 10 min. Data
    off at 19:24:44.
  - **Not yet run on JD's board:** Warren's polish items for JD's ruling
    (the Hue editor's 17-19 ms passes, Diagnostics' ~1.08 s settle, the lit
    indicators' cost) and JD's own checks (hours on battery, a BT slot
    switch, a pairing). Warren's effects speed change (`gremlin/fx-speed`)
    comes as a later flash.
- **Before it: `52acdffe99`** (dev, token `0xab194817`), from 22:02:56
  10-24, on `mac/wake-dark-frame`. It is `b9555ff3e6` plus the wake's
  dark-frame fix (`plans/BACKLOG.md`, "The key lights flash at a
  deep-sleep wake"):
  - the sleep waits for the committed frame to be dark;
  - the wake restages the ladder at once.

  An independent review found no must-fix and four nits: one comment fixed,
  one noted, two left. Codex isn't installed on Buzz.
  - **Flashed mid-drain, on battery** (relay 2 off throughout), with JD's go.
  - **The first jump was refused,** a minute of "a key moved in the last
    2 s" while JD typed. The retry jumped at 22:02:36.
  - **`flash.sh` restored and verified** the keymap and the lighting.
  - **The gauge came back at 95.0%** (the clamped boot's guess), against
    94.6% by the logger.
  - **The clock settled** at +1.4 ms at 22:08:55.
  - **Proven at 22:19:52 10-24** by JD's second 120 fps video, of a wake
    from a real deep sleep (asleep at 22:18:25, 2.7 mA). The keys went dark
    to his colour in one frame, with no dim frame and no gap, and the ladder
    still sleeps.
  - **Handed to Warren that evening;** it went into the menu's build
    (`88057ba7f1`) and so into the mainline.
- **Before it: `b9555ff3e6`**, the mainline until 10-25 (dev, token
  `0x3c117332`), from 23:48:26 10-23, built and flashed from Buzz, the new
  Mac. It is `36afff30e8` plus the once-a-second slow pass's fix
  (`ce229f87c6`, below) and a comment crediting quill4gen7 in `lockchan.c`
  (the same code). Gremlin's board ran it from 17:03 10-22 (token
  `0x32d3502c`).
- **Before it: `36afff30e8`** (dev, token `0xef38330e`), from
  14:22 10-21. It is Gremlin's frame trim (`01abfe0ecf`, codex cleared after
  four rounds) merged with `36330d5ec8` (the 81-LED model).
- **The Mac's daemon, on Buzz: `v0.1.1-839-g17e77d5`** (`--clock --radio
  --lockchan`, signed with the Developer ID), installed 23:49:13 10-23. Its
  first syncs after the flash, 3 min apart, found the board -1649.5, then
  -704.8, then -8.8 ms off: the RTC period the flash erased, re-learning. By
  23:55 it had converged and was slewing, with the interval back to 300 s.
  - ⚠️ **Its lock-light channel has never sent a frame on Buzz**
    (found 19:25 10-25): `lockchan_frames_sent=0`, 752 failures, the last
    error "Input Monitoring has not been granted to this program yet". So
    with the data cut, the board has had no clock and no now-playing from
    the Mac since the move, and the drain so far has none of the lock-light
    frames' draw into a sleeping board (~1.6 mA while music plays).
  - **Fixed at 19:28 10-25:** JD granted `ak820-agent` Input Monitoring,
    and the daemon restarted at 19:28:43. Its first frames went at once (a
    title at 19:28:59, the transport, a clock at 19:29:12 with latency -14
    ms), with no failures. The drain has the lock-light frames from here.
  - Elysium's `21e8fe8` (from 14:23 10-21) still runs, but without the
    board. Elysium will be wiped once everything has moved over.
- **The bench:**
  - relay 2 off: the board on its pack;
  - uhubctl hub `3-1.3.4` port 2 off: no USB data (the new Mac, from
    10-23; `0-1.4` port 2 on the old one);
  - relay 1 off;
  - the INA228 logging to `history/power-bench-2026-10-15/power.csv`,
    under launchd since 21:14:45 10-24 (`com.jdlien.ak820pro.powerlog`;
    `scripts/power_log_agent.sh status`);
  - JD's daily setting (effect 2, hue 178, sat 219, val 125, speed 231 at
    the flash of 09:49 10-26; the screen at the default, 42 of 100), the
    slider on BT, Balanced again since that flash. The drain from FULL runs since
    04:44:26 10-24.
- **The clock's 30 min cut passed** on this build: the replug found -20.0 ms,
  against +1106.3 ms the morning before without the trim
  ([`../history/lockchan-clock-mac-cut-trim-20261021/`](../history/lockchan-clock-mac-cut-trim-20261021/README.md)).

### Stopped 20:11:24 11-04, short of the RGB cut: the untethered drain at real use, from FULL 04:44:26 10-24

The drain restarted on `b9555ff3e6`, with Buzz's daemon (`--clock --radio
--lockchan`) and the slider on BT. It was to run to the RGB cut.

- **The end:** relay 2 switched on by hand at 20:11:25 11-04, the pack
  charging at ~530 mA from then. The last row on the drain, 20:11:24,
  `charge_mah` 414.29: **3243 mAh net since FULL (±18, the 11-03 offset
  below), 80.8% of R4's 4011.6, ~768 mAh (19.2%) left by the logger,
  after 11 d 15 h 27 min (279.45 h).** The board read lower near the
  bottom: its low cap at 15% came at 13:42 11-03 and it read 14.7% at
  14:49 11-04, where the logger's count left 19.5% and 18.5%.
- **Not a clean runtime: two long charges fell inside it**, both for
  the row ISR's light measurements, out of the low cap's ladder (under
  15% it darkens an idle board at 3 min): 14:25:16-15:05:15
  11-03 (365.3 mAh in) and 14:49:48-15:03:49 11-04 (128.3 mAh in),
  besides the short wakes' charges (eight of 2-6 s, 3.6 mAh in all: 10-26
  13:08-13:13, 10-28 12:41, 11-01 16:46-17:45). **497.2 mAh in, so ~3,740
  mAh out over the 279 h, 13.4 mA on average**, the row ISR's bench
  windows, the flashes and the gates included: not JD's use alone. The
  net count is the pack's state; the out count is what the board drew.
- **What it answers and what it does not:** the board ran untethered for
  over 11 days with a fifth of the pack left by the logger; the runtime
  to the RGB cut at real use is still unmeasured. A new drain from FULL
  is JD's call.

- **The charge:** relay 2 on at 23:46:52 10-23, with `charge_mah` at 50.83.
  It tapered to ~-79 mA and terminated at 04:16:03 10-24 (`charge_mah`
  -1116.977): 1167.8 mAh in over 4 h 29 min.
- **FULL, verified:** six reads from 04:18:54 to 04:43:55, every one
  `external (USB) (full)`, 100.0%, the charger pins CHRG high and STDBY high.
- **The start:**
  - relay 2 off at 04:44:26;
  - hub `3-1.3.4` port 2 off at 04:44:29, and the keyboard left USB.
  - **`charge_mah` at the start: -1116.956** (04:44:25). Since FULL =
    `charge_mah` + 1116.956.
- **The draw:** 27-33 mA for the 3 s with the data still on (dark, idle since
  ~23:45), then ~3.0 mA asleep from 04:44:31.
- **The daemon at the start:** board absent, radio silent (the slider is on
  BT), lockchan held. Its last health read before the cut (04:44:24) showed
  `stall_ge_25ms` 0 and a worst loop gap of 24 ms (`blit`).
- **To 14:11:47, 9.45 h, 98.2 mAh:** 6.99 h asleep at 2.96 mA, 2.46 h awake
  at 31.45 mA (JD's daily setting), none above 40 mA. JD's first wake was
  ~10:45.
- ⚠️ **The logger died at 14:11:47 10-24 and restarted at 19:06:12.**
  - **The cause:** cmux, the terminal app, restarted at 14:11:59, and its
    restart killed the logger even though `--detach` had double-forked and
    `setsid` it. It died with no log line and no crash report.
  - **The QT Py never reset:** `qt_ms` runs on unbroken, so the INA228's
    charge register counted through the gap.
  - **The gap, 4.9 h, used 51.95 mAh** (10.6 mA on average). Totals since
    FULL stand; only the gap's profile is lost.
  - At 19:06:54, 150.2 mAh since FULL (3.7%).
  - **Fixed at 21:14:45 10-24: the logger runs as a LaunchAgent**
    (`scripts/power_log_agent.sh`), out of cmux's reach. The switch lost
    no row: one a second through it, `qt_ms` unbroken. At 21:15:04, 196.2
    mAh since FULL (4.9%).
- **The flash of `52acdffe99` mid-drain:** data on 21:51:44-22:09:03,
  9.53 mAh in those 17 min, none charged. Afterwards, 219.1 mAh since FULL
  (5.5%, at 22:09:05). The pre-flash battery log is
  `~/Documents/ak820pro-battlogs/log-20261024-220230-preflash.csv`. The
  board's gauge restarted at its 95.0% guess, so its check against the
  logger runs from FULL to 22:02 and from 22:03 on, not across the flash.
- **Power saver from ~22:15 10-24** (JD, `Fn`+`B`). The flash had reset
  the mode to Balanced. From the logger: dimmed 1 min and asleep 3 min
  after his input, against Balanced's 10 and 20.
- **The results to 18:24 10-25** (37.7 h, 340.9 mAh since FULL, 8.5%):
  - **The gauge from FULL to the flash (17 h, Balanced):** the board's
    level within ~0.5 point of the logger's, and its modelled energy 864.0
    mWh at 21:48 against ~864 measured. After the flash it restarted at
    95.0% (truth 94.6%), and JD read 92% at ~18:20 against ~91.2% by
    energy.
  - **Balanced** (04:44-21:51 10-24, 17.1 h): 12.24 mA on average, asleep
    65% of the time at 2.98 mA and awake 35% at 31.5 mA.
  - **Power saver** (22:15 10-24 to 18:24 10-25, 20.2 h): 5.89 mA, asleep
    91% at 3.18 mA and awake 9% at 32.2 mA, half the charge in that 9%.
  - **Awake, the board drew 28-36 mA**, none above 44: at val 115 the keys
    add 3-8 mA to the 27.3 mA dark base. The sleep timeout sets the
    runtime, not the brightness.
  - **Modelled from FULL to the cut** (15,579 mWh, constant power): ~13
    days at Balanced's average, ~27 at Power saver's. One day each, and the
    two days were a Saturday and a Sunday.
- **The flash of `30f1e0cfde`, the menu, mid-drain:** data on
  19:06:57-19:24:44, 10.48 mAh in those 17.8 min, none charged; 365.5 mAh
  since FULL at 19:24:47. The pre-flash battery log (v7) is
  `~/Documents/ak820pro-battlogs/log-20261025-190706-preflash.csv`. The
  board's gauge restarted from the voltage again, so its check runs FULL to
  22:02 10-24, 22:03 10-24 to 19:06 10-25, and from 19:08 10-25 on. The
  drain runs on to the RGB cut on the menu's build. The new build's log is
  v8, whose LCD column is `bkl100` (0-100; `scripts/gauge_replay.py` reads
  both).
- **The flash of `57d5e90030`, P5b, mid-drain:** data on
  09:49:04-10:00:57, 6.93 mAh in those 11.9 min, none charged; 478.0 mAh
  since FULL at 10:00:58 (11.9%). The pre-flash battery log (v8, 58
  entries) is `~/Documents/ak820pro-battlogs/log-20261026-094912-preflash.csv`.
  The board's gauge restarts from the voltage again, so its check runs
  from 09:50 10-26 on as its own leg.
- **The flash of `13c5e910cb`, P5c-P5e, mid-drain:** data on
  13:29:30-13:41:04, 6.71 mAh in those 11.6 min, none charged; 580.0 mAh
  since FULL at 13:41:04 (14.5%). The pre-flash battery log is
  `~/Documents/ak820pro-battlogs/log-20261026-132937-preflash.csv`.
- **The flash of `553108e5f2`, the profile page's polish, mid-drain:**
  data on 16:01:21-16:13:01, 6.81 mAh in those 11.7 min, none charged;
  656.2 mAh since FULL at 16:13:01 (16.4%). The pre-flash battery log (v8,
  10 entries) is
  `~/Documents/ak820pro-battlogs/log-20261026-160127-preflash.csv`.
- **VIA, binding Fn+A and Fn+S:** data on 16:16:03-16:17:03, the daemon
  stopped for it; 658.5 mAh since FULL after.
- **The flash of `1f3c79e904`, the menu's 60 s close, mid-drain:** data
  on 20:28:39-20:40:34, 7.3 mAh in those 11.9 min, none charged; 774.7 mAh
  since FULL at 20:40:34 (19.3%). The pre-flash battery log (v8, 17
  entries) is
  `~/Documents/ak820pro-battlogs/log-20261026-202845-preflash.csv`. Each of
  these flashes restarts the board's gauge from the voltage, so its legs
  begin at 13:30, 16:02 and 20:30 10-26.
- **The lighting changed by ~20:50 10-26:** JD moved from Alphas/Mods
  (h178 s219 v125) to a slowly cycling rainbow, and the drain runs on with
  it as real use. The board's battery log records each entry's LED drive
  (`led_pm`), so the change shows there, and the drain also checks the
  per-colour model against a moving colour mix. By 21:54 10-27 the
  rainbow was saved as a second profile ("Rainbow Slow", Cycle L-R) and
  the live lighting back on "Purple/Blue".
- **The flash of `ecb10f0e9b`, the clock chip's flicker fix, mid-drain:**
  data on 21:54:21-22:06:03, 7.2 mAh in those 11.7 min, none charged;
  1053.2 mAh since FULL at 22:06:02 (26.3%; the logger's count unbroken
  since 13:00 10-26). The pre-flash battery log (v8, 101 entries) is
  `~/Documents/ak820pro-battlogs/log-20261027-215429-preflash.csv`. The
  board's gauge leg begins at 21:55 10-27.
- **The flash of `3b6e43ef73`, the Font test, mid-drain:** data on
  10:31:36-11:26:09 (the Mac's reboot turned it on), 33.7 mAh in those
  54.6 min, none charged; 1144.3 mAh since FULL at 11:26:09 (28.5%). The
  pre-flash battery log is
  `~/Documents/ak820pro-battlogs/log-20261028-110439-preflash.csv`. The
  board's gauge leg begins at 11:05 10-28.
  The comparison frames' upload: data on 11:48:54-11:51:42, 2.07 mAh in
  2.8 min; 1161.1 mAh since FULL at 11:51:42.
- ⚠️ **The logger's charge count restarted twice on 10-26. From 13:00:02.8,
  mAh since FULL = `charge_mah` + 557.488** (±0.05 in all). From 12:51:38
  to 13:00:00 it was + 552.646; before that, + 1116.956. The second: relay
  2 closed for 3 s at 13:00:01.2 with the keyboard's cable in port 2 and
  data on; the hubs dropped again at once (the last row 13:00:00.55,
  4.818931; the count back at 13:00:02.83; 2.28 s, 0.023 mAh, uncounted),
  and the relay board then left USB. With the cable out of the hub
  (12:57-12:59) relay 2 closed with nothing dropped. The first: The
  relay's control lead broke when the bench went under the desk; after
  JD's resolder, a 1 s pulse of relay 2 (12:51:36.6) pulled down the hubs'
  5 V and reset the relay board, the QT Py and hub `3-1.3.4` together.
  The last row before it: 12:51:36.07, -564.330560 (552.625 since FULL);
  the first after: 12:51:41.55, 0.033778 (3.3 s of counting at 36.8 mA),
  so ~2.2 s at 34.7 mA (0.021 mAh) went uncounted. No charge reached the
  pack (the current stayed positive throughout). The hub's reset also put
  the keyboard's USB data on, 12:51:39-12:52:03. Relay 2 closed cleanly on
  the same hubs at 23:46 10-23, so the repair was the suspect. **Fixed by
  13:10:** JD found stray strands of the keyboard cable's braid barely
  touching the new joints, separated the wires and trimmed them. Relay 2
  then charged at ~366 mA four times (13:08:45, 13:10:17, 13:12:09, and a
  3 s pulse from the Mac at 13:13:14), with no drop and the count intact;
  ~1 mAh went into the pack, counted.
- ⚠️ **The count restarted a third time at 12:31:55 10-30. From then, mAh
  since FULL = `charge_mah` + 1960.53** (±0.1). The logger's cable was
  pulled by accident:
  - **The gap:** the INA228 stopped answering after 12:30:01.83, when the
    count was 1401.950 (1959.44 since FULL, 48.8% of R4's 4011.6 mAh; the
    board showed 49%). The QT Py then left USB at 12:30:50 and booted again
    at 12:31:54.
  - **The bridge:** the new count began at ~12:31:54.8. The 113 s between
    went uncounted, ~1.09 mAh at ~34.8 mA (36.2 before, 33.5 after).
  - The board ran on its pack throughout (relay 2 off).
- **White's cable out from ~12:31 10-30.** JD moved black (gremlin's
  board) onto the relay cable. White's USB data is unavailable until its
  cable is back; the drain runs on untethered.
- **White's cable back by 12:49 10-30.** USB data on 12:49:19-12:49:21
  (the evening read, `../history/ds-phase-cableout-20261029/`) and
  17:28:28-17:28:59 (Icon only's flash, on its pack, the settings kept;
  47.7% just before). White was still in Power saver at the flash, as since
  ~08:55 10-29: note it in the drain's figures.
- ⚠️ **The count restarted a fourth time at 12:59:59 10-30, and read ~0.26x
  until ~15:25 10-31.** Found 11-02, not seen at the time:
  - **The restart:** `charge_mah` fell from 8.846525 (12:59:58) to
    0.000197 (12:59:59) while `qt_ms` ran on unbroken. So the INA228 lost
    power and the QT Py did not. 1969.38 mAh since FULL at 12:59:58.
  - **The scale:** from that second, `current_ma` and `vshunt_uv` both read
    about a quarter of the truth: asleep 0.78 mA against 3.3 before and
    after, awake ~10.7 against 41-44. That fits the chip back at its reset
    values (ADCRANGE 0, SHUNT_CAL 4096: 0.26x) and unconfigured until the
    logger's reconnects of 15:25-15:29 10-31, after which the readings are
    right again (asleep 3.3-3.4 mA) and the register runs on unbroken. This
    is an inference from the readings; the chip's registers were not read.
  - **The charge:** 76.59 mAh counted from the restart to 15:24:57 10-31,
    ~294-322 mAh true (x3.84 by the reset calibration, x4.2 by the asleep
    currents' ratio). Roughly 220-245 mAh went uncounted. The 63 s gap in
    the rows at the reconnect (to 15:26:00) is under 1 mAh either way.
  - **So from ~15:25 10-31, mAh since FULL = `charge_mah` + 2201 (±14).**
    At 11:40 11-02 (`charge_mah` 504.17), 2691-2719 mAh since FULL, 32-33%
    of R4's 4011.6 left. The board read 36% on 11-01, which agrees; the
    uncorrected count would say 38-39% today.
  - **Three more restarts on 11-03, each a QT Py unplug** while the
    presser was built on it. The REPL's soft reboots did not restart it.
    The segments:
    - 564.346 at 23:52:19;
    - 13.136 from 00:33:04 to 00:51:39;
    - 28.480 from 01:28:32 to 02:06:55;
    - the count from 02:11:22 on.
    The gaps add ~22 mAh (±5): white awake 1380 s of them by its uptime,
    at 27-47 mA, the rest asleep at ~3.4. The scale is right after each:
    asleep 3.25 mA at 02:11:22. **So from 02:11:22 11-03, mAh since FULL
    = `charge_mah` + 2829 (±18)**; at 02:14 that is ~1180 mAh left, 29%.
  - Its anomaly is visible in a day's mean asleep current, which a check
    on the logger should look at: an INA228 that silently resets at its
    defaults keeps recording plausible numbers.

### Stopped 23:46:52 10-23: the untethered drain at real use, restarted from FULL

⚠️ **This drain stopped, and the one above replaced it.** Moving to the
new Mac spoiled its two checks. Two slider moves rebooted the board (~19:44,
~23:44), which restarted its count since FULL. The logger missed 6.5 h,
and the pack took 32 mAh mid-run. Its results up to 14:53 10-23 stand (the
nights, the day profile, JD's daily setting). Relay 2 went on at 23:46:52,
and the board was flashed to `b9555ff3e6` at 23:48.

The record of the stopped drain follows. It was the first drain with the
ladder and deep sleep at JD's real use.

- **Started 23:18:26 10-21 from a verified FULL:** 423 mAh in, terminated
  at 22:53:31, and the board read FULL, 100.0%. The logger's `charge_mah`
  read -3249.13 at 23:18:41.
- ⚠️ **The first night never slept.** Relay 2 was off but the USB data was
  left on, and a host's frames block deep sleep (`DSB_USB`, `sleep.c`).
  - The board dimmed at 00:02 (32.9 mA) and went dark at 00:12 (27.7 mA).
    It then stayed awake and dark at ~28 mA until 08:10.
  - That cost 285.5 mAh, 7.1% of 4011 mAh, and the board read 93%, so the
    gauge was right. Asleep, the night would have cost ~26 mAh.
  - The informal on-pack stretch from 10:51 10-21 had the data on too, so
    it never slept either.
- **The data was cut at 08:16:01 10-22** (`charge_mah` -2962.51). Since then
  the setup matches a real owner's.
  - 08:16-14:58 used 368.2 mAh, mostly typing at full white (~73 mA).
  - 11:40-13:10 was asleep at 3.1 mA.
  - **08:16-18:18, 10.0 h, used 424.2 mAh** (the logger): 5.29 h lit at
    73.3 mA (388.2 mAh, 91%), 0.73 h dimmed at 31.9 mA (23.3), 4.02 h
    asleep at 3.2 mA (12.7). Each idle went 10 min lit, 10 min dimmed,
    then asleep, as Balanced should.
  - **At 18:19, 711 mAh since FULL** (17.7% of 4011). The board read
    81.6%, from 2888.7 mWh counted since FULL, and 5 deep sleeps since
    boot, every one woken by a key, 0 strays. `count_ge_25ms` still 6.
- **The night of 10-22/23 slept:** 21:34:47 to 10:07:27, 12.5 h at 3.09 mA,
  38.8 mAh, against 285.5 mAh for the awake night before.
- **Read at 10:16 10-23** (data on 10:16:54-10:16:59, the board awake, no
  key needed):
  - 890 mAh since FULL (22.2%). The board read 76.9% from 3618.5 mWh counted
    since FULL. That's 9 deep sleeps since boot, the last woken by a key,
    and 0 strays.
  - ⚠️ **`count_ge_25ms` 7, one more since 18:20 10-22** (non-flash, worst
    still 29 ms `blit`), across 4 deep sleeps. The ring had already cycled
    past it, and HC_ACCT's `long_passes` counts only passes long enough to
    wrap its scopes, so nothing names it. Maybe the known 26-28 ms wake
    blit. Unexplained.
  - **JD's daily setting since ~20:10 10-22** (read 10:31:57-10:32:05 10-23,
    `ak820lighting.py show`): effect 2 (the dual-colour mode), hue 185, sat
    227 (89%), val 115 (45%), speed 231; light purple and blue. Full white
    was never what JD would use day to day.
    - Awake at ~32.5-32.9 mA, against ~28 dark, so the lights cost ~4.5 mA
      (LED drive 7.3%). At this setting the awake board's floor is ~86% of
      its draw.
    - The board's model agrees within ~1%: 138.7 mW against the logger's
      140.1, both with the USB data on. The model counts the data's 7.1 mW,
      so set a read's draw against logger rows taken with the data on.
    - So the drain is two settings: full white until ~20:10 10-22, JD's
      daily setting after. That fits R5's purpose (a drain at JD's real
      use) better than full white did. R3 already holds full white's
      figure (4011.6 mAh, ~55 h of use).
    - At this pace (~320 mAh a day like 10-22, and ~123 h of use a charge),
      the cut is ~9-10 days from 10:16 10-23, not ~5. The bench stays on
      until then, unless JD stops the drain early.
  - `count_ge_10ms` ran 0.32 an awake second at 215 passes a second (still
    `36afff30e8`).
- **The night of 10-22/23** is the asleep night to set against 10-21/22's
  awake one.
- **Reads go over the data alone:** port 2 on, relay 2 still off. Cut the
  data again after, or the board cannot sleep. The reads so far, on 10-22:
  14:56:38-14:58:02, 15:06:26-15:06:31, 18:19:48-18:19:58, and on 10-23
  10:16:54-10:16:59, 10:31:57-10:32:05 and ~23:30-23:34:24 (the new Mac,
  JD plugging the cable in). The board
  was asleep for the last, and the data can't wake it: relay 1 tapped the
  rig's F19 first (18:19:41, the Mac locked, so nothing typed), which
  costs ~17 mAh of ladder before it sleeps again.
- ⚠️ **The old Mac went down mid-drain, and the bench moved to a new Mac
  (10-23).** The board ran on its pack throughout: relay 2 stayed off, and
  a relay board that loses power opens its contacts.
  - **The old logger's last row: 14:53:09 10-23**, `charge_mah` -2233.06, so
    1016.1 mAh since FULL. (An earlier look saw 14:22:56 as the last row;
    the CSV carried over to the new Mac runs to 14:53:09.)
  - **~19:44: the board rebooted,** when JD moved the slider from BT to
    2.4G (the new Mac had no Bluetooth pairing). A slider move is a
    power-source switch. The time comes from the board's 229-minute average
    at 23:33, and `wdt_fired_last_boot` reads False. The reboot lost:
    - the RAM battery log from before it;
    - the board's count since FULL. At 23:33:17 it read 538.5 mWh, 76.6%,
      band 56.6..90.7%.
  - **The slider went back to BT at ~23:44,** after the new Mac was paired.
    That move likely rebooted the board again. From 23:45 the drain is on
    BT, as it was before 19:44.
  - **The QT Py lost power when it moved hubs, and its charge register
    cleared.** From its uptime, it booted at ~21:25:22. The new register read
    78.7 mAh at 23:33:37: 36.8 mA on average from 21:25, so the board was
    awake that whole stretch.
  - **14:53:09-21:25:22, 6.5 h, went unmeasured:** ~20 mAh if the board
    slept throughout (3.1 mA), ~216 if it was awake at JD's daily setting
    (33 mA). So since FULL = 1016.1 + the gap + the new `charge_mah`: 1115
    to 1311 mAh at 23:34. The board's own count cannot bridge it, because
    the reboot restarted that count.
  - **The new Mac, 23:30-23:35:**
    - `setup.sh` rebuilt the venv on Homebrew's Python 3.15; the old one
      pointed at a pyenv 3.13.9 this Mac lacks. It is kept as
      `venv.old-pyenv-3.13.9`.
    - `uhubctl` and `libusb` came from Homebrew.
    - JD plugged the relay cable in (data only).
    - `relay status`: both off. The board read `supply battery`.
    - **Logger restarted 23:33:35** (pid in `power.pid`).
    - **Data cut at 23:34:24, hub `3-1.3.4` port 2,** and the keyboard left
      USB. The draw fell from ~37.5 to ~35.5 mA.
    - **23:39:49-23:45:11: relay 2 on, the pack charging** at ~366-390 mA.
      The register fell from 82.09 to 49.92: 32.2 mAh back into the pack,
      which the register nets out. The `on` was a plug-in to the gauge,
      and the `off` an unplug.
    - Data on 23:42:27-23:45:11 for VIA: (0,13) is play/pause again on
      layers 0 and 2 (read back). The keymap backup is at
      `~/Documents/ak820pro-keymap.json`, taken 23:44:52.
    - **Relay 2 off and the data cut at 23:45:11.** The keyboard left USB,
      and the logger read +33.2 mA.
  - **Not on the new Mac yet:**
    - the daemon (no Rust toolchain), so no clock sync, no now-playing and
      no lock-light frames to the board;
    - the old Mac's `~/Documents/ak820pro-*`: the lighting and keymap
      backups, and the battery logs;
    - the Home Assistant token in the Keychain (`bench_power.py`);
    - `gh`, and `~/bin/relay`.
  - **The wake rig is gone** (a lead tore off its switch on 10-23). A read
    of a sleeping board needs a key pressed by hand
    ([docs/test-bench.md](../docs/test-bench.md), "The wake rig").
- **At the cut:** the logger sees a ~45 mA step at ~3.40 V. Then data on,
  dump the RAM battery log (`ak820battery.py log`), relay 2 on. Nothing
  watches for the cut yet: set a watcher on the logger once the level
  nears 20%.
- **Proposed, JD's call:** let this drain stand in for R5 as the gauge's and
  the runtime model's held-out check. Then the RGB-off drain
  (`POWER-CAMPAIGN-PLAN.md`, R5) is dropped and nothing else needs the
  logger.

### The once-a-second slow pass: fixed in `ce229f87c6`, on gremlin

**The finding** (14:56 10-22, after 23 h up;
[`../history/ge10-per-second-20261022/`](../history/ge10-per-second-20261022/README.md)):
- `count_ge_10ms` stood at 80,024, about one a second. HC_ACCT's ring shows
  the same pass every second: `second_edge 3, blit_pump 2, unaccounted 4,
  ch582 1`, 10-13 ms.
- In `housekeeping_task_kb()` (`ak820pro.c`) the order is `rtc_fast_task`,
  then `display_second_edge_task`, then `display_blit_pump`. On the tick,
  the edge runs the 1 Hz `draw_clock` and `draw_battery`, the pump then
  moves the first queued glyph in the same pass, and QMK's core adds its
  ~4 ms.
- **It is not new, just closer to the line.** The clock has shown seconds
  since the first firmware (`DISPLAY_CLOCK_SHOW_SECONDS`). On 10-20
  (`b2a07e0d37`, overnight, 2.4G, on USB) the same pass crossed 10 ms 0.18
  times a second, and on gremlin's board on `36afff30e8` (USB) 0.17-0.22.
  - Up to 14:56 JD's board averaged 5.28 ms a pass, against gremlin's
    4.66. `ch582` is the same on both (1.21 against 1.23 ms), so it is not
    BT; the difference was all outside the scopes (3.59 against 2.98 ms).
  - **From 14:56 to 18:19 it ran 4.65 ms a pass, like gremlin's, and
    crossed 10 ms 0.26 times an awake second, against ~1.1 before.** The
    earlier stretch was mostly the night awake and dark with the data on;
    this one mostly lit typing on the pack. Which condition slowed the loop
    (the RGB off, or the live USB) is not pinned.
  - The row ISR is unchanged: 73.3% of the CPU and 194 us mean, against
    72.8% and 188 on 09-03.
  - Not the power-mode bulb: it repaints only when the mode changes.

**Why fix what costs no keys:** the matrix is sampled in the row ISR, and 25
ms is the line for loss, so nothing is lost. But a press landing in that
pass goes out up to a few ms late, and a counter that ticks at the clock's
cadence can no longer show a regression. That counter is how every stall
in this project's history was found. Raising its line to 12 ms was
considered and dropped: the passes are 10-13 ms, and every earlier
measurement is at 10.

**The fix, `ce229f87c6`** (`26b36e3ea0` plus comments; codex found no
must-fix or should-fix,
[`review-codex-edge-pump-2026-10-22.md`](review-codex-edge-pump-2026-10-22.md)):
the 1 Hz latch sets `clock_ticked_this_pass`, the pump returns on it as it
does on `pass_deferred`, and `display_pass_end()` clears it. The glyph goes
out on the next pass, ~5 ms later.

**On gremlin's board** (USB, a paused track, no typing;
[`../history/ge10-per-second-20261022/gremlin/`](../history/ge10-per-second-20261022/gremlin/)):
`count_ge_10ms` fell from 0.175 a second to 0.016 over matched 640 s
windows, with `count_ge_25ms` 0 throughout. No slow pass in the ring has the
edge with the pump any more, and none has the pump stacked with the 10 Hz
block. What is left is the 10 Hz block (`BACKLOG.md` has the next cut, not
built).

**On JD's board, after the drain:** read `count_ge_10ms` against uptime
(which stops in deep sleep) and the ring, against 0.26 an awake second lit
on the pack and ~1.1 awake and dark with the data on.

### After the drain

1. Dump the RAM battery log, then charge to FULL.
2. **Done early, mid-drain (19:08 10-25, JD's call):** the menu, the LED
   fix and the wake fix are merged and on JD's board (`30f1e0cfde`). The
   daily build on gremlin is deferred to before the release (Warren). Next
   from Warren, each through codex and its own flash: the effects speed
   change (`gremlin/fx-speed`), then settings profiles if JD gives the go
   (`CONFIG-MENU-P1-DESIGN.md`, "Settings profiles").

   Candidates for a later flash, each through codex (`BACKLOG.md`):
   - the hours left in the "Battery low" alert, if the drain shows the
     estimate right near the bottom;
   - the long-sleep wake's time left as ~5 s of the whole battery row, at
     any level, in hours (`143h of use`); the camera page's `4d` to hours
     too. Proposed, JD's call: build it as
   `daily`, the build releases ship, so the soak runs what owners get. A daily build has
   no bootloader jump, so later flashes need `Fn`+`Esc`.
3. Strip the bench (the relay wires, the logger), and JD puts the foam and
   silicone back.
4. The soak is JD's daily use. Read the counters over a cable now and then.
5. Polish and release for other owners:
   - minor polish, and cleaning up the repo;
   - a tag and its firmware;
   - the Mac and Windows agents released separately, each with a proper
     installer. The Mac build is not published yet: Phase 6 stops before
     Apple's notarization.

### Bigger ideas (10-22), after or beside the release

**The keyboard as an agent pager** (`BACKLOG.md`, "The keyboard as an agent
pager"). Claude Code's hooks light one key amber and name the waiting
sessions on the screen, and the key takes you to them. It is quill4gen7's
`notify` idea on our transports, and more useful day to day than now-playing.
Not planned yet: write the plan first, after reading quill4gen7's
`docs/notify.md` and hook. quill4gen7 is now credited in the README,
`docs/wireless.md` and `lockchan.c`.

**A configuration menu on the knob** ([`CONFIG-MENU-PLAN.md`](CONFIG-MENU-PLAN.md),
a draft; the build plan is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)).
`Fn` plus a knob click opens a list of every board setting, the knob moves
and clicks, and the debug pages move into it. The design, its decisions, and what is still open.

### Open, none of them blocking

- **The keys flash at a deep-sleep wake: cause found from JD's slow-motion
  video (21:16 10-24).** The sleep starts in the same pass as the dark
  stage, before a dark frame is committed, so the wake shows the old dim
  frame for ~40 ms. Then the keys are dark until the 10 Hz tick, ~140 ms
  after the key. It has been there since the modes' revision (`0e322097f4`,
  10-20). The fix is proposed in `plans/BACKLOG.md`, not built, and would
  go with the flash after the drain.
- **Six passes of 25 ms or more since the flash** (worst 29 ms, `blit`). The
  same six at 23:14 10-21 and at 14:56 10-22, so none overnight or today.
  The 30 min cut added none (14:29-14:59), so they came in 14:22-14:29 or
  14:59-23:14 (the power-charts sweep was in there). They are not the wake
  paint: the board had not slept once.
- **A stray wake in about one sleep in 50,** unexplained. The diagnostic
  (op 24 slot 8) names the next one.
- **UART overruns at 1-2 an hour,** the link's long-standing rate.
- **The clock's idle hold** (Gremlin's question): an awake board with the
  host idle gets no clock frames, so it drifts ~1-2 s a half hour.
  Recommended leaving it: the clock shows minutes, the wake guess corrects
  it ~4 s after input resumes, and Balanced is asleep by 20 min. JD hasn't
  ruled.
- **Owed:** codex's RTC failure-path tests (Gremlin).
- **The wake rig's wires short** when the board is moved, which makes stray
  presses of its key.

### Bench rules learned this stretch

- **Run the power logger as a LaunchAgent during a drain**
  (`scripts/power_log_agent.sh install`). One started from a cmux shell
  died at the next cmux restart, even detached. `power_log.py` now refuses
  a second recorder on the same CSV or port. `uninstall` when the bench is
  stripped.
- **Data alone never deep-sleeps** (`docs/test-bench.md`). A battery run
  meant to match real use cuts both relay 2 and port 2.
- **FULL is `(full)` with 100.0%, never the `done` flag.** The charger's
  DONE pin has never read low on USB (`docs/battery.md`, "The charger").
  A watcher that also waited for `done` let the board sit at FULL from
  04:18 to 04:44 10-24 before the drain started by hand.
- **After a flash, wait for a settled sync** (|before| <= 25 ms) before any
  cut. The erased RTC period took ~6 min to re-converge (-460 ms, then
  -2885 ms, then -8.8 ms).
- **The stack watermarks after 23 h:** interrupt 568 of 1024 bytes free,
  main 968 of 2048.
- **To flash a new pin:**
  1. Merge and push.
  2. Pin `deps.lock`, and run `python3 scripts/power_model.py` in the same
     commit. A pin change deploys the power page, whose `--check` fails
     unless `site/power/power.json` carries the new sha.
  3. Build dev.
  4. Relay 2 on, flash, relay 2 off.

## 2026-10-21

**On the board since 01:50 10-21: `9e52400ec9`** (dev, token `0x3c899a32`).
It is the mainline, now everything in one build: the power modes, deep
sleep, the lock-light channel with play times and the clock-flash fix,
Gremlin's PCF writer fixes, and Gremlin's wireless clock (type 4).
- **Its first checks passed:** 30/30 deep-sleep cycles with the RTC gate
  (01:55-02:19): no pass reached 25 ms, and there were no UART errors,
  strays or resets. Every reconnect synced, before-offsets 30-104 ms. The
  Mac sends no type 4 yet: its latency is still unmeasured (step 1 below).
- **`ak820pro-jdlien` is fast-forwarded to it, and `deps.lock` pins it.**
  The diagnostic branches (`mac/sleep-*`) and `bulb-slash-preview` were
  never for merge. They were deleted on 10-21 with the merged `mac/*`
  branches; the patches are in
  [`../history/firmware-branch-archive-20261021/`](../history/firmware-branch-archive-20261021/README.md).
- **The overnight soak on `7ae8575c1a` passed, apart from known items**
  ([`../history/mainline-soak-20261020/`](../history/mainline-soak-20261020/README.md)):
  - 139/150 sleep cycles; the 11 failures were 6 of the 25 ms wake paint
    and 5 UART overruns, both known;
  - 15 min awake off USB, the board within the standalone ±2 s bound;
  - an hour asleep at 3.01 mA;
  - every reconnect synced, and every PCF write settled.
- **Found in the soak, fixed since:** lock-light frames into a sleeping
  board cost ~1.6 mA on average while the Mac played music. The daemon now
  holds every frame type after 45 s with no input (`8ea6f2b`, the clock's
  `aa2a4be`; `BACKLOG.md`). It reaches the Mac with step 2's reinstall.
- **The ILRC's period moves ~0.6% with temperature** (32331 cool and dark,
  32537 warm on USB), which matters to type 4's slew limit (Gremlin's).

**The morning's steps, done 09:36-10:14 (no hands):**
1. **The Mac's latency: -14 ms** (39/40 frames, sd 2.7;
   `history/lockchan-clock-latency-mac-20261021/`).
2. **The Mac's daemon reinstalled at 09:38** with it, the frame hold and the
   clock's hold. No consent prompt came up.
3. **The clock test, a 30 min cut** (`history/lockchan-clock-mac-cut-20261021/`):
   2/2 type-4 frames applied on schedule, none refused. But the board ran
   ~0.25% fast off USB: 1616 ms ahead at the second frame, +1106 ms at the
   replug. So 10 min frames leave a ~1.6 s sawtooth. The fix is Gremlin's
   call: a trim from the frames' offsets, or a faster cadence. Gremlin runs
   the same test by hand on Windows.

**On the board since 10:50 10-21: `36330d5ec8`** (token `0x57c22634`):
`9e52400ec9` plus ak820-pro-1e's 81-LED fix (battery.c's RGB slopes;
`history/flash-81leds-20261021/`). `deps.lock` pins it.
- **On the pack since 10:51, in Balanced at JD's daily use (relay 2 off).**
  This is a note, not R5: it didn't start from a verified FULL, and
  ak820-pro-1e's power-charts sweep (~3 h, ~120 mAh) runs in the middle of
  it tonight. The INA228 logs all of it
  (`history/power-bench-2026-10-15/power.csv`). R5 starts from a FULL after
  the sweep.
- **The power-charts sweep ran 17:38-20:28,** then a charge from 20:52.
  The untethered drain that followed is in the 10-22 block above.

**On the board since 14:22 10-21: `36afff30e8`** (dev, token `0xef38330e`):
Gremlin's frame trim (`01abfe0ecf`, codex cleared after four rounds,
`plans/review-codex-lockchan-clock-trim-*2026-10-21.md`) merged with
`36330d5ec8`. `ak820pro-jdlien` and `deps.lock` point at it, and Gremlin's
board runs it too. **The Mac's daemon is `21e8fe8`** (main, with Gremlin's
`a2dbd65`), installed 14:23 after the flash.
- **Gremlin's attended BT tests passed:** a 23 min idle hold with no frames
  drifted 1.66 s (the ILRC's wander, not a phase error), and with frames
  every 10 min the replug found -38.0 ms.
- **The Mac's 30 min cut passed** (14:29-14:59,
  [`../history/lockchan-clock-mac-cut-trim-20261021/`](../history/lockchan-clock-mac-cut-trim-20261021/README.md)):
  - 4 frames applied, none refused; 2 rate trims (32284 to 32322);
  - the last frame's offset was -3 ms, and the replug 180 s later found
    -20.0 ms, against the morning's +1106.3 ms;
  - `deep_cycles` said FAIL only for 7 extra presses: the wake rig's wires
    short when the board is moved.
- **After a flash, wait for a settled sync before any cut.** The erased
  RTC period took ~6 min to re-converge (-460 ms, then -2885 ms, then
  -8.8 ms).
- **Open (Gremlin's, put to JD):** the idle hold stops clock frames, so a
  board left awake with the host idle gets the raw ILRC drift, ~1-2 s per
  half hour.
- To flash a new pin: merge, push, pin `deps.lock` and run
  `python3 scripts/power_model.py` in the same commit (a pin change deploys
  the power page, whose `--check` fails unless `site/power/power.json`
  carries the new sha), build dev, relay 2 on, flash, relay 2 off.

## 2026-10-20 evening

**On the board since 17:11: `845996c39c`** (`mac/lockchan-pm`, dev, token
`0x2e279a39`). It is the power modes revised (`5df4e0e3b7`) plus the
lock-LED handler and the play times (type 3) with codex's fixes.
- **`ak820pro-jdlien` and `deps.lock` are at `5df4e0e3b7`;** the lock-LED
  commits stay on their branch until the stray question below is settled.
- **Validated** ([`../history/power-modes-20261020/`](../history/power-modes-20261020/README.md)):
  - deep sleep 17/20 on BT and 9/10 on 2.4G, every cycle asleep and woken
    by its key;
  - `ladder_check --rig` passes once its Heatmap floor is fixed (re-judged
    from the run's data).
- **Since 18:30 on the board: `6fda6cd1c2`** (dev, token `0xa647bcb6`):
  the stray diagnostic (op 24 slot 8) and the readout tied to its title,
  both cleared by codex.
- **Since 20:30 on the board: `dd8391c28d`** (dev, token `0x28e58a4c`):
  a lock-light title frame no longer flashes the clock. A repeat of the
  shown title keeps the play time, and a new title starts a guess until its
  type 3 (`BACKLOG.md`, "The clock flashes"). Codex cleared it; its P3,
  the repaint lag at a guess, goes into the next build with Gremlin's
  `rtc.c` fixes.
- **Lock-light frames do not end the deep sleep:** 80 frames into 10
  sleeps, no strays and no overruns, and a control the same
  ([`../history/stray-test-20261020/`](../history/stray-test-20261020/README.md)).
  The soak's one stray, about one in 50 sleeps, is unexplained; the
  diagnostic names it next time. The long soak is where to catch one.
- **The Mac's 450 ms data gap is measured:** 20/20 `Sent` frames committed
  with the daemon's raw HID quiet. The daemon's release build
  (`v0.1.1-699`) is signed but not installed; reinstalling it brings play
  times, the gap, the orderly stop and Gremlin's two sender fixes.
- **Gremlin:** the type 3 sender, the wake resend's 4 s wait, and the BT
  clock (type 4) designed and under codex. Its `rtc.c` fixes
  (`gremlin/rtc-clock-fixes` `090378fd`) wait for my review after codex.
- **The agent's own repo** with a notarized Mac release and a signed Windows
  build: decided, for later (`BACKLOG.md`).

## 2026-10-20 (morning)

**On the board since 01:04 10-20: `b2a07e0d37`** (dev, token `0x398a2e17`;
`ak820pro-jdlien` and `deps.lock` point at it). It is the UART-latency build
([`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md)):
- the PCF's transfer unlocked, with only the row ISR held off;
- UART2 above USB;
- the animation's stop and the boot redraw through the staged restore;
- the pass budget compared in ticks.

**Measured overnight, no hands**
([`../history/uart-latency-20261020/`](../history/uart-latency-20261020/README.md)):
- **Overruns:** the PCF burst's 7.7% of requests lost became 0.05-0.1% at
  the defaults.
- **The release matrix passes, with no pass >= 25 ms anywhere:** the stuck
  bus, 20 staged restores, and 200 relay presses during a request stream.

**The daemon carries now-playing over the 2.4G dongle on the Mac too.**
- **What runs:** `v0.1.1-628-g5a9bac1`, installed `--clock --radio` at
  01:06. The Mac's radio half is `b2b85f3` plus codex's fixes; the reviews
  are in [`RAWHID-24G-DAEMON-PLAN.md`](RAWHID-24G-DAEMON-PLAN.md).
- **The cable-out test passes:** the radio qualified 6.6 s after the data
  cut, the band read back as sent, and the radio stood down 3.6 s after
  the data came back.
- ⚠️ **On macOS, flock and POSIX record locks never see each other.** Every
  Mac tool on the radio lock uses flock.

**Next, with JD at the desk, one action at a time:**
1. A track playing, the cable pulled: the band and the playback readout
   over the radio.
2. A track change while on the radio.
3. The cable back.
4. Optional: the board's deep sleep on the radio, then a key.

Gremlin's Windows cable-out test needs JD's hands there too.

**Then:**
- the backlog's new items: 64-bit math per pass, the OEs left, the ~1 ms
  of RTT the build still adds (a dev variant without the UART hooks);
- R5.

## 2026-10-19

**The night's runs, no hands, all on `53afebd553`** (each folder has a README):
- **The RGB curve** (`../history/power-bench-2026-10-15/rgb-curve-20261019/`):
  white within 0.7% of the model at every value; red, green and blue alone
  up to 7.7% off. **A per-colour fit is within 0.6% at every step**
  (`scripts/rgb_fit.py`): red 1.29x the mean per unit, green 0.90, blue 0.81.
- **The stages** (`stages-20261019/`): the model within 2% at all 24 steps
  (target 5%).
- **The sleep baseline** (`../history/sleep-baseline-20261019-0251/`): 2,000
  rig presses, every one counted; raw edges ~0.5% short by design
  (`BACKLOG.md`).
- **The deep-sleep soak** (`../history/deep-soak-20261019/`): **247 of 247**;
  stopped in cycle 248 by the daemon holding raw HID 11 s (the open now
  waits 30 s). ~3 ACK timeouts a cycle, no give-ups.
- **The awake control** (`../history/awake-control-20261019/`): 30 of 30,
  and ~3 timeouts a cycle awake too: **the retries are not the wake's**, so
  the wake's ~28 ms first-key cost (10-18) is unexplained.
- **One hour asleep** (`../history/deep-sleep-20261019-1h/`): pass at 3.17 mA.
  **The record counted 3139 s for 3600: asleep, the RTC runs ~13% slow**
  (the 10-18 cycles agree), caught on the wake by the PCF's 2 s snap. The
  build takes slept time from the PCF (`SLEEP-PLAN.md`).

**Adopted 10-19, not built:** time left as hours of use, on the battery row
under ~10 h and on a wake after a long sleep (`SLEEP-PLAN.md`); the wireless
clock as the lock-LED channel's item 5, after deep sleep and now-playing, a
sync every few minutes (`LOCK-LED-CHANNEL-PLAN.md`).

**Flashed 10:34 10-19 (flash 2j):** `442c9f49c9` (dev, token `0xc8227691`),
the Scroll hold only for frames that can carry Scroll (lock-LED item 2),
after codex's review (no must-fix; `LOCK-LED-CHANNEL-PLAN.md`). Keymap and
lighting restored and read back, the clock synced to -3.4 ms. Before it, the
wake rig checked after JD's switch shorted when the keyboard was moved: 200
of 200 presses at 40/60 and 25/40 ms.

**The deep-sleep build is done, not flashed** (plan:
[`DEEP-SLEEP-BUILD-PLAN.md`](DEEP-SLEEP-BUILD-PLAN.md) revision 5, cleared by
codex after a plan review and four verifies). Firmware `6df01722a8`..`bf7d7d0280`,
local on `ak820pro-jdlien`, not pushed; all four flavours build with no
warnings and pass `build.sh`'s new checks (the sleep's production path in
every flavour, no dev mutation handler in daily or fpb). Artifacts:
`via-dev-bf7d7d0280-20261019-121358.bin` (token `0xec3c77f1`) and
`via-daily-bf7d7d0280-20261019-121424.bin` (`0xe65fead1`). Outer repo
`a4a810a`: the bench scripts on record v2, `deep_cycles.py` through the
ladder's own path (Minimal plus op 14 sub 5) with validation 1's gates,
`ak820battery.py sleep` (`HC_POWER` page 1, 28 bytes: the blockers' u16
added to the plan's 26), and the docs (hardware.md "Deep sleep", clock.md
"Across a deep sleep", display.md "At a deep sleep and its wake",
battery.md "The gauge across a deep sleep"). The simulator: 146 of 146; the
drains' replays worst +1.9 / +2.1 with the per-colour model (were +1.1 /
+1.2: the logs carry only the total drive).

**The mode names are settled:** Always on / Balanced / Power saver / Lights
out, with a bulb icon in the bolt's slot on battery
([`POWER-MODE-ICONS-PLAN.md`](POWER-MODE-ICONS-PLAN.md), `db175ae`). Another
session builds it on its own branch off `bf7d7d0280`, as its own flash
after this one.

**Flashed 12:57 10-19: the deep-sleep build, `752d4bcda7`** (dev, token
`0x4aeddcd6`), after codex's implementation review (3 must-fix, 6
should-fix) and two verifies, every finding taken (the plan's last three
tables). Keymap and lighting restored and read back; the clock synced to
-0.4 ms; the sleep page answers; no stall of 25 ms or more. `7df8a08e96`
(codex's one-line USB fix to the log's night levels) is committed on top,
not flashed: it rides with the power-mode icons' flash.

**Smoke tests on `752d4bcda7`, 13:02-13:05 10-19** (`../history/deep-sleep-smoke-20261019-press/`,
`-widths/`): a bench sleep woken by the rig, PASS (woke on P2.8, one key,
3.31 mA asleep, the PCF's seconds, the acquisition done, the re-attach,
nothing timed out); the 32-bit widths (`--preset 65500 --cap 60
--no-press`), PASS (woke on the cap at exactly 60 counted seconds past 65,500;
the PCF 71 s for them). JD then asked for the soak on the icons build.

**Flashed 13:18 10-19: the power-mode icons, `26fcafaeca`** (dev, token
`0x47773c72`; codex: a review and a verify, no must-fix; the plan
[`POWER-MODE-ICONS-PLAN.md`](POWER-MODE-ICONS-PLAN.md)). It carries
`7df8a08e96`. **Then the bulbs reworked on the panel with JD** (another
session; display.c art and colours only, no codex): previews 15:54-16:08,
**`83d8768c64` on the board since 16:16** (dev, token `0xcf9da0e0`): collar
bases, Lights out's bulb slate with a light-grey slash.

**The soak on it, 13:19-14:43: 97 of 100**
([`../history/deep-cycles-20261019-icons/`](../history/deep-cycles-20261019-icons/README.md)).
Every cycle slept and woke through the ladder, one key, no reset, no pass
of 25 ms or more, the PCF within 1 s of the logger. **The three failures
were UART overruns** (module to board; no key lost) **at the link's
long-standing base rate, not the sleep's**: ~1.8 an hour on flash 2f's
drain (92 in 51.9 h), ~2 an hour in the soak. Likely the PCF's bit-banged
I2C masking interrupts up to ~2.9 ms (inferred). **Fn+B** on the pack: no pass of 25 ms or more, worst
21 ms; **the CAPS paint alone reached 25 ms once in ~600 toggles**
([`../history/fnb-caps-20261019-jd/`](../history/fnb-caps-20261019-jd/README.md)).

**Afterwards, 16:16-17:45** (the plan's "Validation results (10-19)" has
every item's state):
- **Balanced's real ladder sleep passes**: asleep 421.0 s after the rig's tap
  (want 420), the PCF 65 s against the logger's 64
  (`../history/ladder-sleep-20261019-balanced/`). **Nearly an hour asleep in Lights
  out** (16:41-17:37, `../history/ladder-sleep-20261019-hour/`): 55 min 55 s
  until a key, **13.25 mW asleep** on the logger against the firmware's 13.35;
  a slider move then reset the board, losing its record of the sleep. `scripts/ladder_sleep.py` runs
  one ladder sleep at a mode's real time; `--charge-wake` was not needed
  (Gremlin's board passed the cable wake).
- **The firmware is pushed** (`ak820pro-jdlien` to `de5450e487`, ChibiOS-Contrib
  `ak820pro-patches` to `27e852d25a`) and **`deps.lock` pins it**: a fresh
  `setup.sh` builds the board's code. JD: push freely now (after the
  family-details scrub); tags and releases still ask.
- **Gremlin** (the Windows 11 PC, its own AK820 on `de5450e487`, a Claude
  session reachable over Remote Control as "Go ahead confirmation") took the
  lock-light channel, the 2.4G dongle and Windows testing:
  [`GREMLIN-HANDOFF-2026-10-19.md`](GREMLIN-HANDOFF-2026-10-19.md), results in
  [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md). Deep sleep passes there in 2.4G
  (key, knob and cable wakes, the waking key kept); its `flash.sh` fixes
  (Documents under MSYS2, the keymap tool's reply match, no HID enumeration,
  and the post-flash clock left to a daemon that owns it, both platforms)
  are pushed; a Windows lock-light route over 2.4G exists
  (`IOCTL_KEYBOARD_SET_INDICATORS`, Num and Scroll only).
- **A clock oddity, not ours:** −2064.5 ms at 16:20:16, three minutes after
  another session's flash, with `flash.sh` then syncing beside the daemon
  (fixed since, `BACKLOG.md`).

**Next, in order:**
1. **The rest of the validation** (the plan's table): the clock without the
   daemon and the acquisition's split (op 14 sub 6); a P0 key and a chord by
   hand; the full-pack insertion; a host appearing while asleep; the backstop's
   real length over a weekend; a daily build on the board; R5, a logged drain
   at JD's daily use. The per-wake clock offset needs a run that leaves the
   daemon its HID (`ladder_sleep.py` does).
2. **The overruns** (pre-existing, ~1-2 an hour, `BACKLOG.md`): confirm the
   cause (do they line up with PCF transactions?), then a plan: the PCF's I2C
   without a whole-transaction lock (its pin-mode writes are read-modify-
   writes on P0, which also carries two key rows, so each needs a short lock
   of its own).
3. **The CAPS paint's 25 ms** (the lock band, `display.c`): split or queue it.

## 2026-10-18

**R3 and its charge are done** (cut 02:01:22 10-18 after 50.39 h, ~4012
mAh out; 3972.4 mAh back in over 9.90 h;
[`../history/battery-2026-10-15-drain-2f/`](../history/battery-2026-10-15-drain-2f/README.md)).
**Flash 2h went on at 12:18 10-18** and its board tests ran 12:20-12:30: 17
of 18 frames exact ([`LOCK-LED-CHANNEL-PLAN.md`](LOCK-LED-CHANNEL-PLAN.md),
"Measured on the board, flash 2h"). **Flash 2i went on at 15:18: 24 of 24
frames exact, P3 included** (below). **The channel is parked; next is the
power work** (the ladder, an accurate gauge, a runtime estimate).

### Sleep experiments on the board (10-18, 18:24)

**Flashed `f38bb1e8a4`** (dev, token `0xc8da78d5`): Minimal mode plus the
sleep experiments of [`SLEEP-PLAN.md`](SLEEP-PLAN.md), all off unless
`HC_DEVHOOK` op 14 sub 3 (light sleep's sizing mask) or sub 4 (the
deep-sleep experiment) turns them on. Codex: a plan review, an
implementation review and two verifies, every finding dispositioned there.
The SN32F299 manual is distilled in [`../docs/sn32f299.md`](../docs/sn32f299.md).

**Measured the same evening** (on `53afebd553` since 19:12: USB judged by
its frame number, which the first deep run needed):
- **Light sleep with WFI: ~4.7 mA less dark (17%)**, no press lost;
  without WFI the steps cost current instead.
- **Deep sleep: 3.2 mA asleep against ~27 awake (88% less); a key wakes it
  and the waking key is not lost** (the rig's column and JD's A, which
  reached the Mac). The watchdog does not count asleep.
[`SLEEP-PLAN.md`](SLEEP-PLAN.md), last section; the history folders.

**Then, 20:14-20:47:** 50 of 50 deep-sleep cycles passed at the Mac (the
first key 64 ms median against 36 awake: the wake costs ~28 ms, the key is
kept); `history/deep-cycles-20261018/`.

**Queued overnight 10-18/19, no hands** (each waits for the one before):
00:30 the RGB-curve map, then the stages map, then `sleep_baseline.py`, then
`deep_cycles.py --board-only --n 300` (`history/deep-soak-20261019/`), then
one 1-hour deep sleep and a key (`history/deep-sleep-20261019-1h/`). If the
keyboard is dead in the morning, a cycle never woke: the slider to cable and
back.

**Decided** (`SLEEP-PLAN.md`, last section): deep sleep is the standby,
starting at screen-off (a first draft: Normal 7 min, Saver 3, Minimal 30 s);
a key or the slider wakes it; no sleep while the screen is lit. **Next:** the
build plan for it (codex first).

### Minimal mode on the board (10-18, 17:31)

**Flashed `460ca22840`** (dev, token `0x4adb46b6`): Phase 2 plus a fourth
power mode, Minimal (`Fn`+`B`: Full, Normal, Saver, Minimal). On battery it
keeps the RGB and the backlight off even while typing, and lights the
backlight for 4 s when the band first paints a message (an overlay, an
alert, a link state, new host text), and while `Fn`+`D`'s pages are open.
One codex review and three verifies, every finding dispositioned
([`PHASE2-BUILD-PLAN.md`](PHASE2-BUILD-PLAN.md)); 126 simulator cases.
The verifies also fixed two older display bugs: host text returning after
its 3-minute expiry stayed blank, and the bootloader screen stayed dark
under a dark stage.

**Checked on the board, 17:32** (`scripts/minimal_check.py`, relay 2 off,
hands-free; [`../history/phase2-minimal-check-20261018-1732/`](../history/phase2-minimal-check-20261018-1732/minimal-check.json)):
dark, the model reads 114.0 mW (base plus USB data) and the logger 27.51 mA;
new host text lifts the model +4.1 mW (JD's backlight level) for ~4 s and
the logger to 28.51 mA; an identical push changes nothing (27.54 mA); new
text again lifts it again. Pass.

**Queued tonight, after the two maps (no hands):** `scripts/sleep_baseline.py`,
light sleep's first gate (`BATTERY-GAUGE-PLAN.md`, "Its gate is the wake
rig"): on the pack, the stage forced dark, a 5-min quiet window for the
logger, 2,000 rig presses at typing speed and at the rig's fast edge, single
presses after 1, 5 and 15 min of silence, all counted at the board (runs
with the Mac locked). Output `../history/sleep-baseline-<date>/`.

**Started:** the sleep work. Light sleep (keeps the link and every key) is
the next build, sized first; a deep-sleep experiment (wake on a key, or it
is not worth having) needs JD at hand in case it does not wake. A reference
distilled from the SN32F299 manual is being written to
[`../docs/sn32f299.md`](../docs/sn32f299.md).

### Phase 2 on the board (10-18, 16:54)

**Built, reviewed three times by codex, flashed:** `d3e8389858` (dev, token
`0x6d244bcd`), [`PHASE2-BUILD-PLAN.md`](PHASE2-BUILD-PLAN.md) has the design,
every disposition and the host results (122 simulator cases; both recorded
drains replayed through the firmware within +0.1 / +1.2 points at every
second). The energy-count gauge, time left on the camera page, `HC_POWER`, log
v6, the modes on `Fn`+`B` (bound in JD's VIA keymap and the default keymap).
`1ea968335f` (a comment only) went on with `53afebd553`.

**Checked on the board, 10-18:**
- `ladder_check.py`: all nine effects go to 0.0% drive at once on the off
  stages and come back on the wake (Jellybean included); a quick disable,
  cap change, enable: dimmed, then restored.

**Queued tonight (no hands):** 00:30 the RGB curve map
(`history/power-bench-2026-10-15/rgb-curve-20261019/`), then the forced-stage
map (`stages-20261019/`), each ~25-45 min on battery, lights changing, then
restored and the relay on.

**Next, in order:**
1. Fit the RGB model in buffer units from tonight's map (A and B in
   `battery.c`; per colour if they differ); check the stage map's model
   against the logger (within 5%).
2. The wake/key test: relay off, Saver, the wake rig through the stages,
   `keydrop_test.py`'s three counts. Needs the Mac unlocked and the keyboard
   untouched ~10 min (JD's say-so).
3. R5: a logged drain in Normal at JD's daily use, from a verified FULL
   (JD's say-so; ~4-5 days): the gauge against the logged energy, the model
   against the logger per 15 min, the runtime against R3 (uncontrolled).
4. Then light sleep (measured first), the reserve, a learning capacity.

### Two workstreams, and their order (10-18)

**1. Phase 2, first, build authorized:** an accurate gauge, a time-left
estimate, the ladder.
Done: R1-R4 and A1/A2 (the gauge reads up to 13.7 points low on the plateau,
where 15 mV spans 85-70%, so the fix is counting energy down from FULL with
the board's modelled draw there and reading the voltage below ~3.98 V). Next,
desk work: A3 (the charge), A4 (the load model), A7 (the hybrid gauge and
time-left, replayed on R3 and drains 2c-2e), A8 (the ladder's sizing); then a
plan and codex. Then flashes: the gauge and time-left, R5 (a drain
at another load), the `Fn`+`B` modes, light sleep, the reserve, gate 5.

**2. The lock-LED channel, parked:** the transport is proven (24/24 frames,
P3 moves no light). Left before it shows a title over Bluetooth: the text
frame type, the board putting it in the LCD's text slot (a flash), and the
daemon's sender (the largest piece), plus the resume list's test items; then
Windows (unknown route), 2.4G and an ack path. The daemon's host-side work
fits Phase 2's multi-day drains, when the board cannot be flashed.

### Flash 2g: the 5A trace and the settled SCR (10-18)

Why: what reaches the board of the LED byte a host writes over BLE (which of
the five bits, whether repeats, how close together) can only be read on the
board, and the channel's toggling repainted the lock band (one pass >= 25 ms
during the 10-17 probe tests). Two changes:
- **dev builds only, `HC_DEVHOOK` ops 7-9:** every checksum-valid `5A` frame
  in a 52-slot ring {byte, ms since the previous}, with frame and accepted
  counts. Host: `scripts/devhook.py leds [reset | json]`.
- **every build:** the LCD shows Scroll Lock once it has held 1.5 s, or at
  once within 500 ms of the board's own `KC_SCRL` (`indicators.c`).

Firmware `4aa5e6b443` (local on `ak820pro-jdlien` on top of 2f, **not
pushed**: JD's call), built as `via-dev-4aa5e6b443-20261018-101206.bin`,
token `0x859cb24f`; `daily` builds clean too (`via-daily-4aa5e6b443-20261018-101236.bin`).
The tests: `scripts/ledchannel_test.py` (width, high, repeats, speed, random)
with the LED probe's new `seq` and `aseq` modes.

**Codex review** ([verbatim](review-codex-flash2g-2026-10-18.md), prompt
[`review-prompt-flash2g.txt`](review-prompt-flash2g.txt)): no must-fix.

| # | finding (short) | disposition |
|---|---|---|
| 1 | should fix: an unanswered `KC_SCRL` press stays armed, and ~49.7 days on the timer's wrap makes it look recent | **Fixed:** `update_leds()` disarms it once its 500 ms pass. |
| 2 | should fix: op 7 plus four op-8 reads are not one snapshot; op 8's reply does not say which page it is | **Fixed:** each page now echoes its number (13 entries a page, so the ring is 52, not 56); `devhook.py` reads the header, the pages, the header again, and retries if the count moved. |
| 3 | should fix: only a Scroll Lock transition restarts the settle clock, so "a frame never shows" holds only if the frame never leaves Scroll Lock changed for 1.5 s | **Fixed (comment) and carried to the encoding:** a rule for the channel's design, recorded in BACKLOG. |
| 4 | should fix (plan): the prose's width and repeat sequences exceed the ring | The runner already used shorter ones (32 and 18); now within 52 with room, and `random` cut to 44. |
| 5 | should fix (plan): a 10 ms sleep after a ~30 ms synchronous write tests ~40 ms between starts, not 10 | **Fixed:** the runner reports the measured start-to-start spacing; `speed-async` (the probe's new `aseq`, every write issued at once) is the fastest this Mac can send. |
| 6 | notes: context all main loop; ring, gap, bounds and LE layout fine; raw vs accepted kept apart; reset keeps `host_leds`; the header's `host_leds` is the radio's even in cable mode; nothing dev-only leaks; the 25 ms budget untouched but not proven; missing frames could be UART loss or checksum rejects | Agreed. The runner reads `count_ge_25ms`, `rx_malformed` and the UART overrun and framing counts before and after every test. Slider on BT for the tests. |

### Flash 2h: the lock-LED channel's receiver (10-18)

`lockchan.c` decodes the wire format (`LOCK-LED-CHANNEL-PLAN.md`, "The wire
format", version 0) from the 5A stream, dev builds only: frames counted,
`HC_DEVHOOK` ops 10-13 read them (`scripts/devhook.py frames`), nothing acts
on them. A frame in progress holds the LCD's settled Scroll Lock. Host:
`scripts/lockchan.py` (reference encoder), `scripts/lockchan_test.py` (the
receiver compiled on the Mac against it: all pass), `ledchannel_test.py
frames`. Firmware `3dcbc8b34c` then `b05e7cbc4e` (local, **not pushed**),
built as `via-dev-b05e7cbc4e-20261018-112802.bin`, token `0x9583223d`;
daily `via-daily-b05e7cbc4e-20261018-112824.bin`.

**Codex review** ([verbatim](review-codex-flash2h-2026-10-18.md), prompt
[`review-prompt-flash2h.txt`](review-prompt-flash2h.txt)): one must-fix.

| # | finding (short) | disposition |
|---|---|---|
| 1 | **must fix:** the receiver learned of a link drop only at the end of the UART drain, so a drop, a reconnect and a frame's last reports in one drain could commit an old frame | **Fixed:** `lockchan_link_lost()` at every site at once (the three 5B down states, slot select, pairing, cable mode). |
| 2 | should fix: the Scroll key's show-at-once shortcut bypasses the hold | **Fixed:** not while a frame is in progress. |
| 3 | should fix: the board test sent no baseline, so a fresh receiver loses the first preamble edge | **Fixed:** a warm-up (bit 3 on, off) before every frame; the spec now requires it. |
| 4 | should fix: the board test never failed, skipped `type` and idle, dropped health | **Fixed:** every field, idle after, health kept, exit 1 on failure. |
| 5 | notes: the codec matches v0; no overflow (15^8 - 1 < 2^32); timing and wrap sound; 180 bytes of RAM; the hold applied in cable mode too; back-to-back frames can hold Scroll; Caps wording; the header undersold the CRC's cost | Cable mode: **fixed** (feed, poll and hold only while the radio is the host). The rest: spec and comments reworded. |
| 6 | should fix: the host tests were too kind (Caps-randomising faults, deletions retimed, last-commit-only oracle, slow human presses, no boundaries, encoder and decoder sharing one understanding) | **Fixed:** Caps-preserving faults, bursts with real gaps, every commit checked, presses 20 ms apart, exact boundaries across the wrap, link loss before every write, pinned golden vectors. Shared understanding remains: the spec is the contract. |

**Verify pass on `b05e7cbc4e`** ([verbatim](review-codex-flash2h-verify-2026-10-18.md),
prompt [`review-prompt-flash2h-verify.txt`](review-prompt-flash2h-verify.txt)): two must-fixes.

| # | finding (short) | disposition |
|---|---|---|
| 1 | **must fix:** deferred selects (the bounce's real select, select retries, the `5B 23` re-issue) still skipped the reset; the promotion path leaves `PA_SELECT` pending | **Fixed in `19152be2e3`:** the reset moved into `ch582_send_command()` for every `A6` but the battery poll (`A6 53`), so every select or pair, wherever it is sent from, starts the receiver over. The promotion's leftover retry is then harmless to the channel; whether it should be cleared is a link-machinery question, left as is (BACKLOG). |
| 2 | the shortcut fix, the cable-mode hold, the Caps wording and the cost comment are right | Agreed. |
| 3 | should fix: the quiet after the warm-up was assumed, not enforced | **Fixed:** an explicit 0.3 s wait. |
| 4 | **must fix:** `frames_test` crashed (`KeyError` on the health record); stalls never failed it | **Fixed:** frames and health in separate lists; separate decode and 25 ms verdicts, either exits 1. A dry run with the compiled receiver standing in for the board: 18/18. |
| 5 | should fix: the quiet and gap boundaries did not cross the wrap; poll-side boundaries untested; the reset test cannot see call sites | **Fixed:** every boundary in feed and in poll, each also with the wrap inside the interval. Call-site coverage stays a review item (verify 2). |

**Second verify** on `19152be2e3` ([verbatim](review-codex-flash2h-verify2-2026-10-18.md),
prompt [`review-prompt-flash2h-verify2.txt`](review-prompt-flash2h-verify2.txt)): one must-fix.

| # | finding (short) | disposition |
|---|---|---|
| 1 | **must fix:** the reset ran when a select was queued, not when it went out (first send or retransmit), and old-link LED traffic can arrive while it waits behind other frames | **Fixed in `9cbb1209df`:** `tx_link_change_check()` before both writes in `ch582_tx_pump()`, the enqueue reset kept. A driver-level regression for the TX backlog would need the driver built on the host with HAL stubs: not added; covered by review. |
| 2 | should fix: the 5A promotion leaves a select retry pending, which can reselect a live link | **Fixed:** the promotion now retires pending actions as `5B 32` does (a bounce survives). Every build: it is link machinery, not the channel. |
| 3 | the reset is safe (no keystroke or TX state touched); the A6 classification holds for normal callers (the instrumented `HC_DRIVE` can send any profile byte); the host fixes are right | Agreed. |

**Third verify** on `9cbb1209df` ([verbatim](review-codex-flash2h-verify3-2026-10-18.md),
prompt [`review-prompt-flash2h-verify3.txt`](review-prompt-flash2h-verify3.txt)): both
fixes correct, nothing new; one older gap.

| # | finding (short) | disposition |
|---|---|---|
| 1 | must fix (strict isolation): `5B 32` kept the receiver's candidate, so a reconnect whose down state was lost could finish an old link's frame | **Fixed in `4652a87470`, as codex specified:** reset on `5B 32`, which comes once per link-up (`docs/wireless.md`), so it never cuts a live frame. |
| 2 | the TX checks, the frame layout, battery polls exempt, main-loop context, the promotion mirroring `5B 32` (it clears a pending pair too, as `5B 32` does) | Agreed. |

**The build flashed (12:18 10-18):** `via-dev-4652a87470-20261018-114709.bin`, token
`0x5d53643c`; daily `via-daily-4652a87470-20261018-114730.bin`. Firmware
commits `3dcbc8b34c`, `b05e7cbc4e`, `19152be2e3`, `9cbb1209df`, `4652a87470`
are local, **not pushed**.

### Flash 2i: profile P3 and the 500 ms gap (10-18)

From flash 2h's board results: the module passes all eight bits, and the one
lost frame was a 366 ms write past the 150 ms gap. Firmware `112942fa63`
(local, **not pushed**):
- **P3:** bits 3-7, base 31, 29 bits in 6 digits; its own preamble (bits 5-7
  together), its header in P3. Num, Caps and Scroll never move. A 29-byte
  payload is 64 writes (~2.0 s) against P1's 106.
- **The gap once synced: 150 → 500 ms.**
- **The preamble's spacing limit is the quiet, 150 ms (was 100):** with a 500
  ms gap, a stray Num + Scroll change 300 ms before a frame passed for its
  first transition in the host tests (a frame lost). Now a transition 150 ms
  after the last always starts a preamble.
- **A sender rule in the spec:** the warm-up comes over 500 ms after the
  sender's last write, so a receiver left mid-section by a broken frame has let
  go (without it the host tests lost 703 of 30,000 frames after a faulted one).

Host: `lockchan.py` and `lockchan_test.py` (P3 everywhere, bits 5-7 in the
fault and garbage models, hiccups of 366 and 500 ms, the new boundaries, a
golden P3 vector: all 18,073 checks pass), `ledchannel_test.py frames` with
P3 first. Built as `via-dev-112942fa63-20261018-150802.bin`, token
`0x081daec1`; daily `via-daily-112942fa63-20261018-150823.bin` builds clean.
**Codex review** ([verbatim](review-codex-flash2i-2026-10-18.md), prompt
[`review-prompt-flash2i.txt`](review-prompt-flash2i.txt)): no must-fix.

| # | finding (short) | disposition |
|---|---|---|
| 1 | P3's codec matches the spec and encoder; no overflow (31^6 - 1 < 2^32); header rules, preamble starts and trailer right; golden vectors decoded independently | Agreed. |
| 2 | timing right, wrap included; 100-149 ms quiets now fail (no sender is deployed); an abandoned frame holds Scroll ~350 ms longer; P3 holds Scroll though it never carries it | Agreed. The P3 hold is **deferred** (the channel's resume list, `LOCK-LED-CHANNEL-PLAN.md`). |
| 3 | the sender's wait past the gap is the right rule; no cheap receiver-only reset; daemon advice | Agreed; the advice is on the resume list. |
| 4 | integration sound; padding-set bytes cannot promote LINKING (recovery latency only); a Caps change carried only in a padding-set byte would be dropped by the guard; the trace cannot tell gaps over 254 ms apart | The Caps case: **deferred** (a probe test). The rest agreed. |
| 5 | should fix: deterministic negative tests (forbidden headers, range limits, falling-edge starts, stall reports, golden fed to C, content in boundaries) | **Deferred** with the channel parked (the resume list, item 1). |
| 6 | should fix: the board test's first frame had no wait past the gap; two spec wordings | **Fixed:** a 0.7 s wait since the last write before every warm-up; the spec's preamble and unused-bit wording. |

**Flashed at 15:18 10-18** exactly as reviewed (`112942fa63`); the frames
test then gave **24 of 24 exact**, P3 6/6, no stall
([`LOCK-LED-CHANNEL-PLAN.md`](LOCK-LED-CHANNEL-PLAN.md), "Measured on the
board, flash 2i"). **The channel is parked there**; the power work comes
first.

## 2026-10-15

**Where things stand: the INA228 power logger is on the pack and recording,
and the keyboard is back in JD's daily use with it attached.** Phase 1b stays
closed (the 10-14 block below). The board is unchanged: flash 2e
(`efd5b0f74a`, a `dev` build). The logger's design and every caveat:
[`../docs/test-bench.md`](../docs/test-bench.md), "The power logger".

**The rig (10-15): three USB ports for a keyboard built to need none.**
- the keyboard, through the relay's cable (its 5 V on relay 2), on the dock
  hub `0-1.4` port 2 (`ioreg`: `AK820 PRO@00142000`);
- the relay (`USBRelay4`) on port 3;
- the QT Py on `0-1.4.1` port 4 (`QT Py RP2040@00141400`).

The keyboard is reassembled with the pack's lead brought out of the case:
pack → in-line SH socket → INA228 (the pack on Vin+, the keyboard on Vin−,
VBUS bridged to V+) → SH plug → board. − runs into the INA228's GND hole (the
ground tap) and on to the board; NTC runs straight through; the MAX17048's
Bat is on V+. JD re-pinned the new SH ends to the standard colours (red +,
black −, yellow for the pack's white NTC). Still, identify wires by position
anywhere on this harness, never by colour.

**Recording:** `history/power-bench-2026-10-15/power.csv` since 21:01:13
10-15 (the recorder's PID in `power.pid`, its notes in `power.log`). The
swap's first 20 minutes are in `power-unflipped.csv` and `power-flipped.csv`,
with the sign wrong in places (`power.log` says where). The QT Py's LED:
dim green = recording, amber = nothing reads it, red = the INA228 does not
answer.

**Checked 10-15:**
- the board runs and charges through the harness, and draws **74 mA on
  battery** (RGB on, BT linked);
- the relay still switches it (20:53-21:01);
- the MAX17048 answers;
- the charge register matches the mean current with the temperature
  conversion on (ratio 0.990 over 15.8 min).

**Found 10-15:**
- **The shunt was wired backwards.** JD swapped the two + wires at the
  terminal block (~20:59); checked +74 mA on battery and −136 mA charging.
- ⚠️ **The INA228's VBUS reads ~5.1% (~214 mV) low** against both the
  MAX17048 and the board's `5C` clamp. It held at every current, with VBUS on
  either side of the shunt, and with the solder jumper bypassed by a wire. So
  it is not the harness, the jumper or the MAX17048's wiring. **Take the pack
  voltage from `vcell_mv`.** The next drain shows whether the error is a
  ratio or an offset.
- ⚠️ **Unexplained: the LCD read 22% at 20:47:34**, after the swap's power
  cycles, with the pack full (a photo of the screen); it said FULL, 100%, by 20:51. The
  saved level is written at FULL (100% on 10-14 23:16), so a restore should
  not give 22%. Read the restore path before trusting the level after a pack
  swap.
- The MAX17048's own SOC read 186-203%: its model, on an unknown cell, is
  meaningless here. Its `VCELL` is what counts.
- `uhubctl`: the keyboard is still on `0-1.4` port 2, where the bench doc puts
  it, so the data cut should still reach it. But `uhubctl -l 0-1.4` printed
  nothing within a 10 s limit (10-15). Recheck before relying on it.
- The logger's code changed 10-15 (all in `docs/test-bench.md`): a `temp_c`
  column; the header repeated every minute, since the recorder's unit check
  had never run; the status LED; and in the recorder, escape-code stripping,
  a report of wrong-length rows, a refusal to append to a CSV with other
  columns, and `SHUNT_SIGN`.

### Flash 2f: the backlight from the host (10-15)

Why: the per-load current map must step the screen with
nobody at the keyboard. `HC_DEVHOOK` ops 4-6 (dev builds only): set the
backlight level, switch it off or on (as `Fn`+`Home`, without the overlay),
read it. All three reply `[level, max, on, effective, saved+1]`. RAM only.
Host: `scripts/devhook.py lcd [LEVEL | on | off]`. Firmware `523744c30f`
(local on `ak820pro-jdlien`, **not pushed**: JD's call), built as
`via-dev-523744c30f-20261015-215932.bin`, token `0x754f00c1`.

**Codex review** ([verbatim](review-codex-flash2f-2026-10-15.md), prompt
[`review-prompt-flash2f.txt`](review-prompt-flash2f.txt)): no blocking
finding.

| # | finding (short) | disposition |
|---|---|---|
| 1 | every access is inside the 32-byte report on the real dispatcher; `length < 5` would not guard a shorter buffer | **No change:** unreachable here (codex's own evidence: the dispatcher always passes `RAW_EPSIZE`), and op 2's probe has relied on the same since flash 2d. |
| 2 | nothing set by ops 4/5 can reach flash; `Fn`+`PgUp`/`PgDn` afterwards persists the temporary level ±1; the reply's "saved" is the RAM cache, possibly a pending write | Agreed. A key press adopting the level shown is what a press means. Noted under `devhook.py lcd`. |
| 3 | no torn state or stuck pin; "on" writes the pin high for at most one 50 µs tick before the PWM resumes | Agreed, existing behaviour (the key path is the same). |
| 4 | should fix: the raw HID reply path (`send_report`, 100 ms timeout, queue locks) could stall the main loop ≥ 25 ms if the IN endpoint backs up | **Pre-existing, not changed by this flash:** every host tool's reply takes that path. Watched instead: the map reads the stall counters before and after; any `count_ge_25ms` there reopens it. |
| 5 | dev-only, and `build.sh` still rejects a daily or fpb carrying the hook; instrumented has no negative assertion | Agreed; instrumented builds are never released. |
| 6 | should fix: `devhook.py` accepted a reply to another op, crashed on a short report, and let bad arguments through | **Fixed (host only):** a whole 32-byte report with the echoed op, or nothing; usage checked before the device is opened. `current_map.py` checks the echoed op too. |
| 7 | for the map: the PWM is nonlinear (`bkl_duty[]`, ~417 Hz); VIA RGB changes trigger the parameter overlay (2 s plus its restore); "off" is the backlight only; the battery log's `bkl` is the level at the interval's end | Agreed. The map holds 90 s and skips the first 15 s of each state, well past the overlay. |

### Tonight's runs (10-15, `POWER-CAMPAIGN-PLAN.md`)

- **R1, the per-load map** (22:10-22:40): JD's settings 73.5 mA, RGB off
  28.3, every light out 27.3; the RGB is 62% of JD's draw.
- **R2, USB data** (22:41-22:57): attached costs ~1.7 mA (2.3%).
- **R3, the logged drain, RUNNING since 23:37:59 10-15**
  ([`../history/battery-2026-10-15-drain-2f/`](../history/battery-2026-10-15-drain-2f/README.md)):
  from a verified FULL; the cut expected ~02:00 10-18, then the charge.
  **A mains outage on 10-17 (15:42:35-16:57:12)** took the dock and then the
  Mac (a panic, rebooted). The board ran on through it without a restart,
  and the bench was resumed at 17:10. The logger's hole, ~100 mAh to bridge,
  is in the run's README.
  ⚠️ **Do not flash, poll the board, touch the relay or `uhubctl`, or unplug
  the QT Py until it ends**; the trial and guard own raw HID.
  ⚠️ **If the Mac rebooted, or any of its processes died: run
  `scripts/resume_bench.sh`** at once. It restarts only what is not running
  (the recorder, the trial as `drain-resumed-N.csv`, the guard with
  caffeinate, the F19 listener) and refuses once the drain has reached the
  cut. Left dead past the cut, nothing charges the pack.

### Next, in order (10-15)

1. **The per-load current map** (Phase 2's step 2, the "afternoon with the
   meter", now logged, and hands-free for the lighting). On battery (relay
   off), hold each state ~2 min and take its mean from the charge register
   (Δcharge/Δt, gap-free), each state twice in ABBA order:
   - **RGB:** off, JD's effect, static white at full, and a few brightness
     steps. All of them go over VIA's lighting channel (`ak820lighting.py`'s
     wire format) without its SAVE, so RAM only: no flash write, and a reboot
     restores JD's setting. Restore it at the end anyway
     (`ak820lighting.py restore`).
   - **The screen:** no host command sets it. Full, dim and off are
     `Fn`+`PgUp`/`PgDn`/`Home` by JD, and each writes the saved brightness. A
     dev hook (`HC_DEVHOOK`, a new op) would make it hands-free, but that is a
     flash: JD's call, with a codex review first.
   - **BT** linked against idle. The MCU's share needs the light-sleep build
     (Phase 2 step 4), later.
   - **Repeat near the bottom of a drain:** the buck-boost draws more current
     as the pack falls.
   - Measurement only: Phase 2 stays note-taking until JD says build.
2. **A whole cycle with the logger**, the plan's "calibration run"
   ([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md)): a drain to the cut and
   a charge to FULL, run by `bench_trial.py` and `trial_guard.py` as before,
   with the logger alongside. It gives the pack's mAh (the charge register);
   its voltage curve under a known load (`vcell_mv`); `5C` against the pack
   across the range; the VBUS error's shape; the charge's CC-to-CV knee seen
   directly in the current (task 12, `K_CC` against the level); and the
   step and relaxation at unplug. The campaign as a whole, with codex's
   review: [`POWER-CAMPAIGN-PLAN.md`](POWER-CAMPAIGN-PLAN.md). Before it:
   - decide RGB through the cut as before, or a lowered cut (RAM-only `cfg`);
   - fix `bench_trial.py`'s pack regex (about two lines): it matches only
     the `(estimate 5C …)` form, so some rows have an empty `pack_mv`.
3. **The 22% after the swap** (above): read the saved-level restore path. No
   flash without a codex review.
4. **Phase 2, the power ladder:** note-taking until JD says build (the agreed
   order in [`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md); the PPK2 is
   deferred to step 4). Item 1's numbers say what step 3 is worth.
5. **A release, JD's call when.** The current v0.1.1 (09-06) predates the
   gauge and has no `fpb` binary.
   - Tag `vX.Y.Z`; CI builds the agent zip.
   - `scripts/release-firmware.sh` uploads a clean `daily` and `fpb` of the
     pinned commit.
   - `scripts/sandbox-6b.ps1` checks the install on a clean Windows.
   - A macOS build is not released yet (no notarization).
6. **Low priority (`BACKLOG.md`):**
   - the level after a flash (a seed from `flash.sh`, or the provisional
     level);
   - a module command for macOS's percent;
   - quill4gen7's two channels, one Mac evening;
   - the CH582F firmware question, after Phase 2's numbers;
   - the firmware as a standalone repo (someday);
   - whether to commit the logger's CSVs (~6 MB a day at 1 Hz: gzip or
     decimate them first).

## 2026-10-14 (Phase 1b closed; superseded by the block above for what is next)

**Where things stand: Phase 1b
([`BATTERY-GAUGE-REFINE-PLAN.md`](BATTERY-GAUGE-REFINE-PLAN.md)) is CLOSED.**
Every gate is met, merged, pushed and written up. The design and its
measurements: [`../docs/battery.md`](../docs/battery.md) ("The gauge as built,
Phase 1b"), [`../docs/display.md`](../docs/display.md),
[`../docs/clock.md`](../docs/clock.md), [`../docs/leds.md`](../docs/leds.md).
- **Gate 8 met (10-14).** The charge from 0 (10-09), the 24 h battery soak
  (10-10), and every per-event check, **no measured event reaching 25 ms**:
  - plug-in and unplug;
  - the Fn+D page exits and a lighting write, with a track playing;
  - a track appearing;
  - typed text under a plug-in;
  - FULL on flash 2e (01:41 10-12);
  - **"Battery low"** (between 08:35 and 08:40 10-14) and **the RGB cut**
    (between 13:55:17 and 14:00:17 10-14), on the drain below.
- **The drain on flash 2e (11:34:16 10-12 to the cut,
  [`history/battery-2026-10-12-drain-2e/`](../history/battery-2026-10-12-drain-2e/README.md)):**
  - **runtime 50.35-50.43 h** wall clock (51.13 h last cycle, run 2 50.56 h);
  - **accuracy** against run 2's line: below 52% −0.2 to −4.6 points (within
    −2.0 below 30%); the flat top (70-85%) down to −7.2 (−8.3 last cycle);
    never above +0.4;
  - **the board was off twice on 10-14, under ~13 minutes in all,** for a
    harness swap that did not fit (below). The log was dumped first;
  - the recharge from the cut: relay on 14:01:17, the charger done between
    23:06:39 and 23:11:39 (~9.1 h), FULL a 2.6-point step, LOST/OVERRUN/
    self-check never set. The trial ended `done` at 23:26:39 and the guard
    with it.
- **Firmware merged and pushed (10-12, JD):** `ak820pro-jdlien` at `3e18c70a74`
  on `jdlien/qmk_firmware` (29 commits; the fork's default branch is now
  `ak820pro-jdlien`), pinned in `deps.lock`. The board's flash 2e
  (`efd5b0f74a`) is the same firmware but for comments.

**On the board: flash 2e**, `efd5b0f74a`, `via-dev-efd5b0f74a-20261011-192711.bin`,
token `0x71163528`, since 19:30 10-11. A **`dev` build**:
- **the raw-HID bootloader jump**, so `./build.sh dev` then `./flash.sh
  <artifact>` flashes with no hands. `flash.sh` dumps the battery log first
  and refuses on battery after the RGB cut;
- **`HC_DEVHOOK`**: `scripts/devhook.py press|reset|read` presses Fn+D and
  reads or resets the display probe;
- `daily` and `fpb` carry neither, and `build.sh` checks that.

**On the bench now (as of 23:26 10-14):** nothing running against the board.
**Relay 2 is ON** (the trial leaves it on after FULL), so the pack is full
and the board runs on USB; data on. The QT Py is on USB again (since 15:37
10-15) with **nothing on the harness**. Its code changed 10-15: a temperature
column, and a header repeated every minute (see "The logger runs", below). The
first recorder (`power.csv`) was stopped at 15:54 10-15, and a check run
(`power-v2-check.csv`, 15:57-16:13) confirmed the charge register in the new
mode. **Nothing records until the swap.**

### Next, in order (10-14; superseded)

The INA228 harness was rebuilt with 1.0 mm SH ends and swapped onto the pack
on 10-15: see the 10-15 block above for what came of it and what is next.

### The bench: tests without JD's hands ([`../docs/test-bench.md`](../docs/test-bench.md))

- **Charging:** the keyboard's USB cable runs its 5 V through **relay 2** of a
  USB HID relay (`16c0:05df`, on the dock hub `0-1.4` port 3).
  `venv/bin/python scripts/usb_relay.py status | on 2 | off 2`.
- **Confirm every switch with one `ak820battery.py` read** (its `supply` line).
  IORegistry presence cannot show it: the data wires bypass the relay.
- **Data:** `uhubctl -l 0-1.4 -p 2 -a off|on -e` cuts or restores the
  keyboard's data on port 2. Always pass `-l 0-1.4 -p 2 -e`: port 3 is the
  relay itself, port 4 JD's Stream Deck. Check `uhubctl -l 0-1.4` after any
  re-cabling, and run it under a timeout (macOS has no `timeout`:
  `perl -e 'alarm 10; exec @ARGV' uhubctl …`). ⚠️ On 10-15 that status call
  printed nothing within 10 s: recheck before a trial relies on it.
- **The power logger:** the INA228 and MAX17048 on the pack, read by the QT
  Py and recorded by `scripts/power_log.py` (10-15 block above).
- **The states:** relay off and data on reads the board on battery without
  charging it (QMK connects USB without VBUS); both off is truly unplugged
  (~0.2 mA left on D+); both on is charging and readable.
- **`scripts/bench_trial.py`** runs a trial end to end (wait for the cut,
  charge, relax, charge to full), logs every read and turns the relay off on
  any failure. **`plug_events`-style checks** (relay cycles with a health read
  around each) and the display probe make a per-event check unattended.
- ⚠️ **Test display changes with a track playing** (JD starts one): the
  page-exit and overlay stalls of 10-11 needed one, and every idle test missed
  them.
- ⚠️ **The slider must stay on BT or 2.4G.** On cable, a cut is a cold
  power-off, and the RAM log is lost.
- The "Christmas Tree" outlet (`scripts/bench_power.py`, through Home
  Assistant since 10-13) powers the Acasis hub. It is no longer in the
  keyboard's path.

### Results to keep

- **`K_CC` = 133.0 pm/h**, the mean of three trials. Each trial is the mean of
  its curve and runtime methods: 124 from 0%, 133 from 1.8%, 142 from 5%. It
  rises with the start level. **`RELAX_S` 1800 s** is confirmed by three
  relaxations.
- **Accuracy over a whole cycle:**
  - ±2.5 points from 52% to the cut;
  - up to −8.3 on the curve's flat top (4003-4016 mV covers 70-85%);
  - runtime 51.13 h, +1.1% on run 2.
- **No measurable USB-data overhead at full white** (trials 2 and 3 on
  data-only USB, −5.6% and +5.3% off the curve).
- **Small shapes go in a RAM tile:** every `lcd_fill_rect` run pays an 11-byte
  window command sent byte by byte. The bolt and the transport icon were the
  last stalls (`docs/display.md`).
- **macOS's Bluetooth battery is the CH582F's linear `5C`, not our gauge**
  (96% against 66.4% on 10-10; ~27% at the cut). System Settings reads it live,
  and `system_profiler` shows a stale cached value.

### Also

- **The community** (`BACKLOG.md`, "Community"):
  - **fpb** starred `jdlien/ak820-pro` and shipped our upstream items. **Touch
    base once the battery work and the ladder are near done**: lead with the
    gauge, and offer to test his v2 panel builds.
  - **quill4gen7** forked both repos on 09-24. Worth borrowing: the lock-LED
    host-to-board channel and the media-key board-to-host channel (one Mac
    evening for both), and a screensaver whose waking key still types. Their
    raw-HID bootloader jump is built (flash 2b, `dev` builds).
- **The repos:**
  - `jdlien/ak820-pro` (the hub);
  - `jdlien/qmk_firmware` (`ak820pro-jdlien`, a fork of `fpb/qmk_firmware`);
  - `jdlien/ChibiOS-Contrib` (`ak820pro-patches`, a fork of
    `SonixQMK/ChibiOS-Contrib`, the submodule);
  - `jdlien/time-util-ak820pro` (`ak820pro-local`, a fork of fpb's:
    `ak820ctl`);
  - adjacent: `jdlien/streamdeck-now-playing` (the MediaRemote helper's
    source);
  - pinned from fpb: `fpb/SonixFlasherC`.
- **Build:** the board's code lives on `ak820pro-jdlien` now. Build from a
  clean checkout of it (`./build.sh dev` for JD's board, `daily` for a
  release). The `phase1b-flash2` worktree in this session's job directory is
  merged and can go (`git -C qmk_firmware-ak820pro worktree remove <dir>`).
  The simulators take a tree via `BATTERY_SIM_SRC=` (and `DIAG_SIM_SRC=`,
  `CH582_SIM_SRC=<...>/bluetooth`).
- **The task list:** `.taskmaster/tasks/tasks.json` (local, untracked), tasks
  11-15.
- **Working rules these weeks taught:**
  - one hands-on action per message; JD's manual trials are costly, so
    automate them (memory);
  - **never test a command that can act** (10-08: a test of `bench_power.py
    off` switched the outlet off);
  - confirm relay switches by the board's `supply` line;
  - a codex review (gpt-6-astra, xhigh) before every flash, verbatim, every
    finding dispositioned;
  - **measure before fixing** (10-11: the staging guess missed; the probe
    found the stage).

### Phase 1b's flashes (all on `ak820pro-jdlien` now)

| Flash | Commit | What | On the board |
|---|---|---|---|
| 2 | `28f260225f` | the charging model, log v5, the D fix, C2, the camera page | 12:54 10-08 |
| 2b | `f79b31b68e` | the raw-HID bootloader jump (`dev`) | 15:39 10-11 |
| 2c | `9816c09e79` | one battery component a pass; the bolt as one RAM tile (plug-ins 24-26 to 11-12 ms) | 16:45 10-11 |
| 2d | `6e5de5bdaa` | the display probe and `HC_DEVHOOK` | ~19:10 10-11 |
| 2e | `efd5b0f74a` | the transport icon as one tile; no redundant forced clear (page exit 28.3 to 12.7 ms, overlay 23.1 to 12.7 ms) | 19:30 10-11, now |

`3e18c70a74` adds only comments and is the pinned head.

## 2026-10-04, night (superseded by the block above)

**Next: execute [`BATTERY-GAUGE-REFINE-PLAN.md`](BATTERY-GAUGE-REFINE-PLAN.md)
top to bottom, starting at its Step 0.** That is Phase 1b: refit the curve on
both runs, the charging display, the internal-flash writes behind the LED
blink, and the battery-only stalls. It is at revision 7, after six codex
rounds (gpt-6-astra, xhigh); round 6's verdict was "ready to execute". Every
round is verbatim in
[`review-codex-battery-refine-plan-2026-10-04.md`](review-codex-battery-refine-plan-2026-10-04.md),
and the dispositions are at the end of the plan. **Phase 2, the power
ladder, comes after it.** It is note-taking only until JD asks.

- **Run 2, the validation drain, is done.** Unplugged 10-02 11:00:00, the RGB
  cut came at 13:33:25 10-04 (50.56 h), and the board died at 18:34:54 (from
  JD's time-lapse). See [`../history/battery-2026-10-01-drain/`](../history/battery-2026-10-01-drain/)
  and [`../docs/battery.md`](../docs/battery.md).
- **The 10-04 charge from flat** started ~20:02, with a preservation dump at
  21:44. ⚠️ **At 22:37 the board was in the bootloader**: JD entered it before
  bed for an overnight flash, but no firmware was ready, so the log after 21:44
  is lost. **Check the board's state first:** in `ioreg`, product 28992
  (`0x7140`) is the bootloader and 32777 (`0x8009`) is running. Then follow the
  plan's Step 0, which covers both cases.
- **On the board: `759e265796`** (the fitted curve, whole percent), unless
  something else has been flashed since. Rollback artifact and build token:
  the plan's "Firmware, branch, and artifacts".
- ⚠️ **The keymap and lighting backups date from 09-29 13:57.** `flash.sh`
  must take fresh ones from the RUNNING board; see the plan's flash
  procedure.

## 2026-10-01, morning (superseded by the block above)

**The 09-28 drain test is over, and the curve is fitted, committed and NOT yet
flashed.** Plan and dispositions: [`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md).
Evidence: [`../docs/battery.md`](../docs/battery.md). Run records:
[`../history/battery-2026-09-28-drain/`](../history/battery-2026-09-28-drain/)
-- `readings.csv` (every observation, JD's words, corrections), the
`log-*.csv` dumps, and the fit's `fit-output.txt` / `fit-points.csv`.

**On the board since ~20:20 10-01: `759e265796`** (the fitted curve, whole
percent). The charge from flat before it is dumped and analysed in
`history/battery-2026-10-01-charge/`. **A validation run started at the
unplug, 10-02 11:00:00** (not 10-01 20:19: the board stayed on USB
overnight): `history/battery-2026-10-01-drain/`, white at full drive as on
09-28. The cut is due ~51.6 h later, ~14:36 Sunday 10-04. ⚠️ **Dump the
charge log before any flash or slider flip** -- a charge from flat on this
firmware is wanted for the charging side (CHARGE_IR_MV, the CV creep). The
09-28 charge took ~9.5 h; dump when the charge LED goes out (CHRG released).

**How the run ended:** FULL ~19:52 09-28 (log VDD); "Battery low" ~00:00 10-01
(3544 mV); the RGB cut ~02:13 (from the log's led_pm), **54.4 h wall, 51.6 h
equivalent full white**; lights off after that; "Low" from ~04:24 (<3.30 V);
last seen 05:19 at 3222 mV; **found dead 08:45** (the log after the 05:03 dump
died with it). On replug, 5C read a fresh 0 under charge: the cell went well
below 3.16 V before the protector cut it. A probe short at ~20:44 09-30 lost
~45 min of log and needed a slider flip (cable out) to revive -- see the 09-24
shutdown section of docs/battery.md.

**Phase 1 gates: all met.** 2 (protection) on the last night -- warn, cut, the
cut survives the user, 5 s of USB lifts it, it re-cuts on battery. 4 (meter vs
gauge) -- eight points 4.01-3.22 V, −9 to +11 mV, including 3.22 V below the
fitted range.

**The fit** (`scripts/battery_fit.py`): 0% at the cut (3400 mV, JD's choice),
knots at even steps of level, the clamp exit at 89.6% (the 90% anchor stands).
Each USB plug-in is credited with the charge it put back (r = 10.5; durations
from each entry's mean VDD) and the dim start at its lower power; ±20% on
those moves the level at 3.70/3.55/3.50 V by ≤ 0.1 point. Simulator 27/27
after updating three expectations that were the old curve's numbers (343 ->
187 pm at 5C 70; "starts high" ≥ 50). Firmware commit on `ak820pro-jdlien`.

**Next:**
1. ✅ Charged, dumped, flashed (`759e265796`). The validation run: panel
   readings with times are the data (no plug-in needed); dump rarely, and
   again from the 'Battery low' warning on; the security camera from there.
   Then compare the panel against the runtime it actually had left.
2. **The queued fixes** (plan, "Queued"): "Charge" not the 95 guess while
   charging at the clamp with nothing saved; keep the re-seat owed past a
   clamp reading just after unplug; the stalls (`25:6 10:2449`, worst 35 ms
   blit -- measure first); the backlight flashing bright during a flash write;
   the warning's threshold and re-arm (JD to decide); later, drop tenths.
3. Validate the curve on a second run, ideally filmed (plan, ideas).
4. Phase 2 is **not built**; JD is in note-taking mode.

**Traps from this run:**
- `flash.sh` backs up keymap and lighting **only if the board is running** --
  do not enter the bootloader first, or it restores the 09-24 pastel.
- A flash wipes the RAM log and the EEPROM: **dump first**.
- Dump with the slider on **BT**, then unplug within a minute (longer is a
  charging session, which re-seats the level and charges the pack).
- A loose cable charges without enumerating: check `ioreg` for `0C45`.
- ⚠️ **`0C45` alone does not mean running**: the bootloader is `0C45:7140`,
  the board `0C45:8009`. Before a flash, prove it is running with a raw-HID
  read (`ak820battery.py` answers), not the vendor id -- on 10-01 the board
  was already in the bootloader and flash.sh restored the 09-29 backups.
- Use `set -o pipefail` in dump one-liners, or a failed dump prints "saved".
- 09-30 19:57: `hostagent/ak820battery.py` refused ("no repo venv provides
  'hid'") although `venv/bin/python3` imports `hid` fine. Run
  `venv/bin/python3 hostagent/ak820battery.py log ...` directly. Cause:
  `venv/bin/python3` symlinks to pyenv's 3.13.9, which is also what
  `#!/usr/bin/env python3` runs, and `venv_bootstrap._same()` uses
  `os.path.samefile` (follows symlinks), so its exec-loop guard calls the
  venv "the interpreter we already are". Fix (not applied): guard on
  `sys.prefix` against the candidate's venv root instead.
- **Docs pass, 09-30 evening:** `docs/battery.md` restructured (current
  facts first, withdrawn claims in a dated table at the end), the display
  doc's battery row and debug row, firmware comments (comment-only), and
  as-built notes in the plan. `5C` cadence: 2-3 reports per 5 s poll cycle,
  bunched -- the mechanism is unconfirmed.

## 2026-09-28, 14:55 (superseded)

**The battery gauge (Phase 1) is built, not flashed.** Everything is in
[`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md): the plan, codex's review of it
([verbatim](review-codex-battery-gauge-plan-2026-09-28.md)) and a disposition
per finding.

- **Artifact:** `via-daily-f2bcc26f14-20260928-145123.bin` (token
  `0x97fc73c0`), firmware `f2bcc26f14` on `ak820pro-jdlien`. The idle ladder
  is compiled out; the VDD estimator is deleted.
- **Reviewed twice by codex** (plan, then implementation: flash after eight
  fixes, all applied). `scripts/battery_sim/run.sh`: 23 scenarios, 15 mutants
  caught.
- ✅ **Running since 2026-09-29 ~13:58: `deef6053dd`**
  (`via-daily-deef6053dd-20260929-135459.bin`) -- the level from a trimmed mean
  of 64 `5C` reports, the panel in tenths (`BATTERY_SHOW_TENTHS`, for the
  calibration), ~6 saved-level flash writes a cycle (every write blinks the
  LEDs ~7 ms), log v4. Flashed mid-way through the 09-28 drain test after a
  dump; the run continues. Queued fixes: plans/BATTERY-GAUGE-PLAN.md, "Queued".
- (Previously `487cb8e9f0`, from ~15:41 on 09-28: (`via-daily-487cb8e9f0-20260928-153833.bin`)
  -- `27bf8a4f06` plus "Charge" for "Chrg". ✅ **The charger does terminate
  with the board running in BT on USB:** a top-up of a full pack held CHRG
  low ~11 min (VDD 4484-4489 mV), then released at 15:43 with VDD 4530 mV;
  the gauge went to full and 100%, and saved it. (The worry was the 09-28 note
  that the LED went out "with the board off".)
- (Re-flash ~15:36: `27bf8a4f06`)
  (`via-daily-27bf8a4f06-20260928-153336.bin`), which adds the saved level: a
  reboot at the top clamp (every slider flip) restores it instead of guessing
  95. First read after the flash: BT position on USB, charger topping up,
  level 95 -- the guess, because the flash erased the saved level. It goes to
  100 when CHRG releases, and is saved from then on.
- (First flash, ~14:58, `f2bcc26f14`, from the bootloader, so the keymap and
  lighting came from the 09-24 backups (lighting: effect 2, val 137 -- not the
  solid white of the 09-25 run). First read on USB, cable position: supply
  external, state full, level 100%, `5C` 100, VDD 4831 mV, log period 600 s,
  thresholds 3550/3400 pack mV.)
- **Next: the bench checks** (Phase 1 gates 1-7). ⚠️ The meter comparison and
  the protection test need the pack **under the top clamp** (`5C` < 100),
  i.e. some hours of use on battery first.
- `deps.lock` still pins `44e7314e65`; move it when this is released.
- The 09-27/28 meter readings were recovered from a session transcript into
  `history/battery-2026-09-25/readings.csv`. ⚠️ Write readings there as they
  are taken, not only in conversation.

Everything below is the 09-27 state, kept for its findings; where it says the
battery row must stop showing VDD, or to calibrate the estimator, the gauge
has superseded it.

## Installed right now (2026-09-27, 13:00)

**The work is on the battery: read [docs/battery.md](../docs/battery.md)
first.** Task 8 in `.taskmaster/tasks/tasks.json` tracks it.

- **Firmware: `via-daily-b35d8672b3-20260924-205842.bin`**, token
  `0x583b65cf`. Production fixes (`6b60458dd0`) plus the start of the battery
  work: VDD from the SN32 ADC; a once-a-minute RAM log; low-battery warn and
  RGB cut at 3.55 V and 3.40 V on VDD; the voltage on the battery row.

### ⚠️ Three findings that change the plan

1. **VDD is a BUCK-BOOST output. It is useless as a gauge.** With the pack at
   3.81 V the debug page read **VDD 3.903 V** — above its own input, which no
   linear regulator can do. Across the run the pack fell **4.18 → 3.74 V
   (−440 mV)** while VDD moved **+3 mV**. ⚠️ **This kills the prediction that
   VDD would start following the pack below ~3.95 V.** There is no dropout
   coming.
2. ⚠️ **The estimator (`36be68f16a`) is dead on arrival.** It derives a level
   from VDD via a lithium curve, and VDD is a constant. **Do NOT calibrate the
   `CAL` constants in `battery.c`** — the earlier "Next" step in this file said
   to, and that instruction is withdrawn. The input carries no signal.
3. ⚠️ **The low-battery protection may be inert.** Warn (3.55 V) and RGB cut
   (3.40 V) are thresholds **on VDD**, which is pinned at 3.90. They cannot
   fire until the buck-boost collapses, possibly below the pack protection
   circuit's trip point. **Unverified — confirm before relying on it.** Cheap
   test: `ak820battery.py cfg 3950 3900` (RAM-only, resets on reboot) and see
   whether warn and cut fire at a VDD the rail actually reaches.

### ⭐ The module's `5C` value DOES track the pack

The premise that `5C` is pinned at 100 is **withdrawn**. It moves, and the
`Fn`+`D` debug page row 8 shows it (`ch582_get_battery()`, `display.c:878`).
Settled readings against a standard NMC curve:

| pack | 5C | curve | offset |
|---|---|---|---|
| 3.99 | 85 | 75.9% | +9.1 |
| 3.84 | 78 | 59.8% | **+18.2** |
| 3.81 | 74 | 56.2% | **+17.8** |
| 3.74 | 66 | 46.6% | **+19.4** |

**The last three agree within ±1 point.** `5C` moves 120 points/volt where the
curve moves 132 %/V — it tracks the curve's *shape*, which is why the offset
holds. ⚠️ **If it holds below 3.70 V the remap is a subtraction** (`level =
5C − 18`). The 3.99 outlier is unexplained: charge memory, a wrong generic
curve at the top, or real depth-dependence. **Readings below 3.70 V separate
them, and that is the single most valuable thing to collect.**

⚠️ `5C` is **noisy (±3) and useless while charging** — it snaps to 100 the
instant USB appears and decays over hours. Any gauge built on it needs a median
filter, a ratchet that never rises on battery, and a hold-off after charging.

### ⚠️ TODO before any release: the battery row must stop showing VDD

`b35d8672b3` shows **VDD on the battery row**, which replaced the CH582F's
hardcoded 100%. ⚠️ **It is a constant.** VDD is the buck-boost output and it has
moved 3 mV while the pack fell 440 mV, so the row conveys exactly as much as the
fake 100% it replaced — less, arguably, since "3.90 V" is not even in units a
user can misread.

It **earned its place as an instrument**: watching it sit still while the meter
fell is what exposed the buck-boost, and a percentage derived from VDD would
have hidden that behind a plausible-looking number. But it is a diagnostic, not
a feature, and diagnostics survive by inertia unless someone writes them down.

**Replace it with**, once the mapping is calibrated:

1. `V_pack = (5C + 374.5) / 117.8` — exact to ~±3 mV, ~8.5 mV per count
2. that voltage through **this cell's** curve, fitted from
   `history/battery-2026-09-25/readings.csv`, not a generic NMC table
3. displayed as **bars plus a percentage in 5% steps** — the granularity is what
   tells the user it is an estimate; 1% resolution is a claim we cannot back
4. **ratcheted**: never rising while on battery, reset on charge
5. ⚠️ volts stay on the `Fn`+`D` debug page, where an engineer wants them

### The discharge run

- **Started 2026-09-25 10:54.** ⚠️ Interrupted 09-26 13:22 when the slider went
  to `cable` to wake the Mac, which **reset the board and lost the RAM log**;
  ~20 min on the charger, unplugged again 14:03. Running since.
- **Readings: `history/battery-2026-09-25/readings.csv`** — meter, screen, and
  the analysis inline.
- **At 12:54 on 09-27:** pack **3.74 V**, `5C` **66%**, 49.3 h elapsed, ~51%
  consumed at 1.03 %/h. **Projected ~94 h total (3.9 days), ~45 h left.**
  Lighting full pastel to 15:36 on 09-25, **solid white 100%** since.
- **What to do:** a meter + debug-page reading whenever you pass it. That pair
  is the calibration data. Nothing else is needed from the run.

⚠️ **Two traps for the next run.** The RAM log is **720 entries at one a
minute = 12 hours**, then it wraps — a multi-day run keeps only the last 12 h
unless `LOG_PERIOD_MS` goes to 300000 (5 min → 60 h). And **the Mac needs USB
to wake**, which is what ended this run; use `caffeinate -d` or a second
keyboard.

### Hardware decided on, not yet ordered

- ✅ **MAX17048 fuel gauge** — DigiKey `1528-5580-ND` (Adafruit 5580). The
  retrofit. ModelGauge, no sense resistor, ±1-2%.
- ❌ **1.25 mm 3-pin male+female pigtails**, Amazon ~$15/20 sets, for the pack
  tap: **the wrong size** (10-14). The pack is 1.0 mm, most likely JST SH;
  a JST SH kit replaces them (above). ⚠️ Digi-Key's ready-made PicoBlade assemblies are **female-to-female**
  and cannot make a passthrough alone.
- ✅ Keep the **JST SH 4-pin Qwiic cables** already in the cart — they mate
  with the MAX17048's STEMMA QT, so no soldering to the module.
- 🤔 **QT PY RP2040** — optional, only as a bench rig to prove the gauge before
  touching the keyboard. Any spare MCU does.
- ❌ **INA228 dropped.** Its purpose was fitting a load model for a
  software coulomb count; the MAX17048 replaces that in hardware.
- ❌ **PPK2 not now.** Right instrument for the idle-ladder work later
  (task 9), wrong one for this. ~CA$150 at DigiKey, not the CA$255 Amazon ask.

### ⭐ The retrofit is much easier than it looked

**The board already has an I²C bus.** `halconf.h:15`: an external **PCF8563
RTC on P0.14/P0.15** over the ChibiOS software (bit-banged) I²C fallback LLD.
So SDA and SCL are routed, a driver exists and works, and **no free GPIO is
needed**. MAX17048 is `0x36`, PCF8563 is `0x51` — no conflict. Solder targets
become the PCF8563's SO8 pins or its passives, **not** a 0.5 mm QFP leg.

Full plan, wiring, the three electrical checks (logic levels across two
supplies, pull-ups that may not exist as components, bus capacitance) and the
pin audit: **[docs/battery.md](../docs/battery.md)**, "A real fuel gauge,
retrofitted".

⚠️ The bus is **rationed** — one transaction per main-loop pass with the LCD
DMA idle, because RTC I²C on port A glitches the flash SPI1 pins mid-DMA
(`ak820pro.c:585`). A gauge read every 30 s is negligible but must go through
that gate.

### What is achievable — read before building anything

A trustworthy percentage is **not reachable on the stock hardware**: no ADC
path to the pack, `5C` is the only signal and is voltage-derived, and NMC's
curve is flat through the middle. **The objective is a 5-bar / 10% indicator
that never goes backwards, ±10% mid-range and better at the ends, plus a low
warning that actually fires.** The MAX17048 is what buys a real percentage.

- **Committed locally, not flashed, not pushed** (firmware `ak820pro-jdlien`):
  `91d854f2ff` and `b35d8672b3` (the flashed build); `36be68f16a` (the
  estimator — ⚠️ **do not calibrate, see above**); `3b85686ff7` (the idle
  ladder — ⚠️ **do not flash during a calibration run**, it dims the lights and
  changes the load profile mid-measurement).
- **Pushed 2026-09-24 ~14:00:** ChibiOS `a4f8412134`, firmware `6b60458dd0`,
  main `882b322`.
- **Bluetooth test, 2026-09-24:** 57 minutes on BT with the cable in: 9,597
  frames, 0 drops, 0 malformed, 2.9% late. Then, unplugged, the board **went
  dark with charge left** and came back only on USB: unexplained
  (docs/battery.md).
- **Still not done:** the `HC_BLITFAULT` forced-failure tests; a hunt on
  `6b60458dd0` (`deps.lock` still pins `44e7314e65`).
- **Also open:** the unplug glitch (task 8.6), and the RGB colour breakup at a
  215 Hz field rate (task 9) — ⚠️ **not fixable in firmware**: the fringe
  scales linearly with field rate and needs ~4 kHz, past this M0. Colour choice
  is a free 2×, and a single saturated channel has none at all
  (`docs/leds.md`).

## Why the crash hunt (2026-09-22)

One spontaneous, unexplained watchdog reset on 2026-09-22 at ~13:13
([incident](../history/incident-2026-09-22-wdt/README.md)). The retained
operation breadcrumbs added that afternoon
([WATCHDOG-BREADCRUMBS.md](WATCHDOG-BREADCRUMBS.md)) will name where the main
loop stopped next time. The crash hunt adds what they cannot say (a CPU fault
versus a hang, the PC, stack depth, why blits time out) and tries to provoke
the next reset instead of waiting for it. The plan is
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md); these sections were last updated
2026-09-24, 12:45.

## ✅ The overnight hunt on 44e7314e65 passed (2026-09-24 04:57)

Ten hours: 1,964,044 blits, no timeout of any kind, no busy-wait, no
non-flash stall of 25 ms or more, no reset
([evidence](../history/crash-hunt-2026-09-24-final-daily/)).

## ✅ The DMA "never-start" is solved (2026-09-23)

Every "never started" blit timeout on record was a **completed** transfer
whose completion the SPI0 half-transfer handler erased. It read `RIS` and
then cleared every flag, so a DMATCIF raised between those two instructions
was lost.

Only 660-byte clock digits were exposed, and the reason is timing. The
equal-priority LED row ISR delays that handler until 188–258 µs after the
arm, and a 660-byte transfer completes at 220 µs. The fix (ChibiOS
`c57623d0d2`) clears only what was read and re-checks for the completion.
E5 ran **3 hours and 580,060 blits with no timeout**.

Found with `CURCNT` instrumentation. Along the way, `DMACNT` turned out never
to count down, so "never started" was a label, not a diagnosis. A Codex review
(`gpt-6-astra`, reasoning effort high) supplied the equal-priority
correction. It also found the other fixes of the day:
- the USB lock nesting;
- the CH582F pump order;
- the `IC` read-modify-write.

Full analysis and every disposition:
[`FIRMWARE-FINDINGS-2026-09-23.md`](FIRMWARE-FINDINGS-2026-09-23.md).
Evidence:
[`history/crash-hunt-2026-09-23-lost-completion/`](../history/crash-hunt-2026-09-23-lost-completion/).

## ✅ The fault recorder works, after a fix (2026-09-23)

All seven `HC_FAULT` modes were verified on hardware. The first runs of
modes 1 and 3 came back invalid: on this chip **the last SRAM write before a
loop that never writes again is lost at the watchdog reset**, and every
handler commits its record and then spins. So the final `FAULT_MAGIC` store
was lost, every time. `DSB` doesn't help; one sacrificial write after it
does (`commit_terminal()`, firmware `02db293696`). The watchdog also **recovers a
locked-up core** (mode 4), with the record intact. Details:
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md), "Third result", and
[`docs/hardware.md`](../docs/hardware.md). ⚠️ The v7 daily build lacks the
fix: a fault on it would record as invalid, so a real crash would read
"unavailable".

## ✅ The fix held: ten hours, no reset (second hunt, 23:00 → 09:00)

Same stress that hung v6 in 13 minutes: no reset in 10 h and 1,960,093
blits. The guard caught 7 overlaps, **all 7 alongside a DMA that never
started** -- the predicted mechanism. All 53 blit timeouts were never-starts,
all recovered by one retry. All 8 non-flash stalls ≥ 25 ms (25–26 ms) came
with a never-start recovery. Deepest stack use: interrupt 464/1024, main
680/2048. Settings verified at exit; the agent restored itself at 09:00:15
and is writing v7 rows to `ak820-health.csv`. Evidence:
[`history/crash-hunt-2026-09-23-v7/`](../history/crash-hunt-2026-09-23-v7/).

The first hunt (v6, 21:05) was stopped at 22:03. It ignored `pkill -INT` (a
background job inherits SIGINT as ignored), so it was stopped with SIGTERM
and its settings restored from its backup by hand, verified; the script now
handles both signals. Its evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).

**If the keyboard freezes in ordinary use:** leave it connected. The
watchdog brings it back in ~15 s; read `ak820 health --crash` (on v7 a fault
carries its PC: `scripts/symbolize.sh <pc> <token>`). A cold power-off
destroys the record.

## ⚠️ The hunt reproduced the hang at 21:18:52 — and the cause is found

13 minutes in: `lcd_transfer within text`. A synchronous LCD draw re-armed the
flash->LCD DMA while the glyph pump's last transfer was still in flight, which
left SPI0 unable to complete an ordinary `spiSend()`; no timeout, so the
watchdog. Full mechanism and fix in `CRASH-HUNT-PLAN.md` ("First result").
A second codex pass found the same hole in the CPU draws (Caps padlock,
battery fill, icons) and in every external-flash transaction, so the fix is
now `bus_quiesce()` at the start of every CPU transaction on either bus. That
also gives JD's 13:13 crash (typing, light load) a plausible path. A
narrow third codex pass verified the guard covers every runtime transaction
([review](review-codex-crash-hunt-impl3-2026-09-22.md)). Committed as
firmware `1b7f781887`; flashed 22:59 (see above).

## Health v7 (Part B) — daily flashed 2026-09-22 22:59; validated 2026-09-23

Daily: `ak820pro-builds/out/via-daily-1b7f781887-20260922-225845.*` (flashed
until the 2026-09-23 fault tests; lacks the lost-write fix above). A
HardFault or an unhandled vector now
writes a terminal record with the PC and the interrupted context, and a ChibiOS
halt records its caller. The record's consecutive-reset count clears after 10
healthy minutes, so three spread-out crashes can no longer switch the watchdog
off for good. Page 6 adds stack watermarks, the blit-timeout breakdown and a
build token that `scripts/symbolize.sh` resolves to the archived ELF.
Host simulation passes under ASan/UBSan; the Rust side decodes all of it (364
unit tests). Codex reviewed the implementation twice: no High and twelve
Medium/Low issues the first time
([review-codex-crash-hunt-impl-2026-09-22.md](review-codex-crash-hunt-impl-2026-09-22.md)),
two High (the unguarded bus paths above) and four smaller the second
([review-codex-crash-hunt-impl2-2026-09-22.md](review-codex-crash-hunt-impl2-2026-09-22.md)).
All fixed; the third pass left two small hunt-script fixes, also done. The archived
ELFs now carry line info: `scripts/symbolize.sh <pc> <token>` answers with
file:line.

## Next

1. ✅ The overnight hunt passed; `deps.lock` moved to `44e7314e65`.
2. **Built overnight, committed locally, NOT pushed or flashed:** firmware
   `6b60458dd0` on top of `44e7314e65`. It carries:
   - `lcd_blit_wait()` tracking CURCNT and DMAEN (start, progress, stall in
     a few ms, and the class);
   - the dashboard repainting after a blit given up for good;
   - the debug-page pump's recovery;
   - the internal-flash driver refusing to erase a sector behind a caller's
     back (ChibiOS `f247ebc639`);
   - the UART reporting hardware overrun (ChibiOS `a4f8412134`), counted on
     the instrumented console;
   - stale comments corrected.

   Clean builds: `via-instrumented-6b60458dd0-20260924-001130.bin` (token
   `0x2d80c2ff`) and `via-daily-6b60458dd0-20260924-001152.bin` (token
   `0x70bfdc04`).

   **The board's daily has no remote bootloader jump, so it needs
   JD's Fn+Esc once.** Then, on the instrumented build:
   - `HC_BLITFAULT 1`: expect an IRQ-lost timeout and a successful repaint;
   - `HC_BLITFAULT 2`: expect `[display] a blit was given up`, then a
     dashboard repaint;
   - the wireless test, with the console captured: ACK histogram, orphans,
     and UART overrun, framing and parity counts in Bluetooth mode;
   - an hour of hunting;
   - then the daily, and push.
3. **JD's wireless test** can use either build: the CH582F path is
   identical in both. It is the first real test of the serial fix and the
   pump order.
4. **Still open:**
   - FRESET SPI0 at hand-back (hygiene, deferred);
   - UART overrun counting;
   - the LED ISR's thread-class PWM calls;
   - the raw-HID flash-provisioning policy (anyone on the host can rewrite
     the external flash's assets);
   - the ACK deadline in Bluetooth mode;
   - Mac sleep/wake and the reboot test;
   - a tagged release.
5. **Parked idea** (taskmaster task 6): a QR code to the agent installer via
   a jqr.ca redirect.

## Repository notes

All pushed, 2026-09-23 ~19:00. Firmware `ak820pro-jdlien` is at `44e7314e65`;
ChibiOS `ak820pro-patches` is at `c212e20dd2`. That branch carries three
fixes from today: the serial fix `a3fdffe26d`, the SPI0 lost completion
`c57623d0d2` and the USB fix `c212e20dd2`. It also carries the reverted
dispatch attempt `2a17a73b48` and its revert `bf9310ca84`.

**`deps.lock` still pins `02db293696`** (v7 plus the lost-write fix). It moves
to `44e7314e65` once the overnight hunt passes. The recovery bundle in
`ak820pro-builds/` holds the new ChibiOS tip. `.taskmaster/` stays untracked, as
before; it now holds task 6, the QR idea. The hunt's raw output stays in
`~/Library/Logs/ak820pro/crash-hunt/`; a snapshot of the 21:18 evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).
