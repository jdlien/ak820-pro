# Codex: the scan through writes and the early cleanup (2026-10-27)

JD (10-27), after the dev Write test: "On blank, cleanup does a very
noticeable flicker. On Scan, cleanup does cause a more subtle flicker ...
I think on dimming, using the scan strategy and doing the cleanup on
dimming could help"; then "build 1-3 and the Dim + cleanup test ... it
totally makes sense to use an interactivity timer". qmk_firmware-ak820pro
`920ad3f2..e0769d16` (branch `gremlin/write-test`), then the fixes
`e0769d16..4e04a28f` and `4e04a28f..dc8e6d0c`. The prompts:
`plans/review-prompt-flash-tidy.txt`, `-fix.txt`, `-fix2.txt`; the raw
replies: `plans/review-codex-flash-tidy-raw.md`, `-fix-raw.md`,
`-fix2-raw.md`.

## The first reply, verbatim (e0769d16)

- **P2:** [menu.c:2001](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2001) can wait forever on Solid. [sn32f2xx.c:998](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:998) counts only changed buffers: dimming produces at most one commit; identical subsequent frames produce none. Count completed renders instead.
- **P2:** [flash_tidy.c:43](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_tidy.c:43) aliases activity timestamps every 65.536 seconds. A later pause with matching low bits skips cleanup entirely. Rearm on observed activity.
- **Risk:** [flash_tidy.c:49](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_tidy.c:49) automatically erases the sole persistent copy on battery. Power loss before the checksum commits can lose all settings; reserve gating cannot prevent slider brownouts. The quarter-full threshold increases erase frequency up to approximately fourfold.

No new masking, LCD-drain, sleep, or watchdog blocker found; UART erase stalls remain. Host tests weren’t rerun: process execution was unavailable.

## Dispositions (4e04a28f)

- **P2 Solid, fixed:** `sn32f2xx_flush()` counts every call. Only
  rgb_matrix's render loop calls it, once a render (`rgb_matrix.c:441`),
  so two counts after the cap mean a whole render begun after it is on
  the LEDs.
- **P2 aliasing, fixed:** no stored activity time. A failure blocks the
  next try until a pass sees input.
- **The risk, accepted and bounded:** every consolidation has it, forced
  or early; the early ones are timed at a pause, not riskier each. The
  threshold went from a quarter to half the log, so they at most double
  the count; written into `flash_tidy.h` and docs/leds.md. A cleanup
  mid-use now needs half a log of writes without a pause (~30 settings
  changes, ~8 profile saves).

## The re-check, verbatim (4e04a28f)

- **New P2:** [flash_tidy.c:32](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_tidy.c:32) skips rearming below threshold. Program/checksum failures reset usage ([wear_leveling.c:320](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:320)), so subsequent input can be missed and an idle refill remain blocked. Rearm before the threshold check; [test.c:35](C:/Users/jdlien/code/ak820-pro/scripts/flash_tidy_test/test.c:35) masks this by preserving usage on failure.
- Solid closes at [sn32f2xx.c:972](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:972); timestamp aliasing is removed.
- [Half-full threshold](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_tidy.c:17) reduces consolidation amplification to approximately twice. Power-loss risk remains, explicitly documented at [flash_tidy.h:34](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_tidy.h:34).

Tests/build not rerun: process execution unavailable.

## Dispositions (dc8e6d0c)

- **New P2, fixed:** while blocked, the idle time is read first, before
  the threshold, and the block cleared on input; the timer read is paid
  only while blocked. The test's fake now models a failed program that
  empties the log; its new case (a key, then a refill 5 min into the next
  pause with no key since) fails on `4e04a28f`'s flash_tidy.c and passes
  on `dc8e6d0c`'s.

## Host tests

`scripts/flash_tidy_test/run.sh` (new: flash_tidy.c verbatim against
stubs) and `scripts/menu_s0_test.c` pass. Mutants caught: Dim + cleanup
without the frame wait, without the 50 ms, without stopping the ten; the
tidy without the rearm, without the block, at a quarter, and lit on
battery in every mode.
