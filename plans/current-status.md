# Current status

Updated 2026-10-20 (the newest block is first below; the crash hunt's notes follow it). The crash hunt's section was last updated 2026-09-24, 12:45; its plan is
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md). **Phase 1b is closed (10-14). The
INA228 power logger is on the pack and recording (10-15)**; next is using it,
below.

## Why

One spontaneous, unexplained watchdog reset on 2026-09-22 at ~13:13
([incident](../history/incident-2026-09-22-wdt/README.md)). The retained
operation breadcrumbs added that afternoon
([WATCHDOG-BREADCRUMBS.md](WATCHDOG-BREADCRUMBS.md)) will name where the main
loop stopped next time. The crash hunt adds what they cannot say (a CPU fault
versus a hang, the PC, stack depth, why blits time out) and tries to provoke
the next reset instead of waiting for it.

## 2026-10-21 morning — RESUME HERE

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

**Owed:** codex's RTC failure-path tests (Gremlin); the stack watermarks
after a long run (each flash resets them: read them on the morning of
10-22, after ak820-pro-1e's power-charts sweep tonight).

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
