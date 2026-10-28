# The clock chip's write flickers the LEDs (2026-10-27, the keyboard on gremlin)

The second cause of JD's "board flickers once in a while", found after the
consolidation's blink was moved out of sight (`plans/BACKLOG.md`, "The LED
blink at an internal-flash write"; `docs/leds.md`, "The other flicker").
Firmware `dc8e6d0c` (dev, token `0x42b3bf75`), on USB, the daemon owning the
clock.

## What JD saw

Two flickers that no action of theirs explained: one ~17:55 "in between me
trying the options" on the Write test page, one ~19:05 "scrolling between my
selected theme and Save new" on Profiles.

## What ruled things out

`flicker_watch.py` (read-only, 1 s; `flicker-watch.log`): each flash write,
each pass >= 25 ms and each second the row ISR's rate fell 2% below its
median. Around 19:05: settings writes, but no cleanup, no long pass, no dip.
The rate's second-to-second spread at rest is ~0.2%; a 3 ms hold is 0.3% of
a second, so this watcher could never see the cause.

The daemon's log (`%LOCALAPPDATA%\ak820pro\ak820-agent.log`) had a periodic
clock sync a minute or two before each: 17:55:12 and 19:05:14. Each sync's
accepted correction requests a phase-correct write to the PCF8563
(`rtc.c`, `pcf_sync_request()`), and every PCF transaction holds the row
ISR's interrupt off (`ak820_i2c_xfer_begin()`). The longest since boot:
115 ILRC cycles, ~3.4 ms (`pcf_max.py`, HC_RTC page 2).

## The prediction and the clip

Predicted: the next sync at ~19:15:14, the write a few seconds on (the sync
slews its correction first; -51 ms took ~3 s). JD filmed the keys at 240 fps
(iPhone slow motion, 847 frames, 19:15:16-19:15:19 by the keyboard's clock,
read off the LCD in the frames). `vid_rows.py` takes each key row's mean R,
G, B per frame (`clip-rows.csv`); `vid_events.py` lists the frames where the
board dims against its rolling median. The rows' own beat against the
camera (every ~7 frames, one row-colour caught alone) averages out over the
board; three bursts do not:

| Frames | Clip, played at 30 fps | Board's clock | Board dims | The writer's step (`pcf_machine_step()`) |
|---|---|---|---|---|
| 456, 457, 460 | 15.2 s | ~19:15:17.9 | 4.4-9.4% | STOP read, STOP write, time write: 3 transactions |
| 578 | 19.3 s | ~19:15:18.4 | 4.6% | release read and write, ~0.49 s before the boundary |
| 683-698 (6 frames) | 22.8-23.3 s | ~19:15:18.9 | 4.6-7.5% | the bracket's reads, hunting the first increment |

JD placed the first at "about 15 s" of playback. In each dark frame every
row dims alike and no row-colour runs hot: the row timer stops at each
period's end until the ISR re-arms it (`drivers/led/sn32f2xx.c`), so a held
ISR leaves every LED off, not one row lit. The seconds digit turned at
frames ~226, 481 and 727 (17, 18, 19). The spacing fits the writer's plan
if the digit is drawn ~0.1 s after the board's second turns: the writes at
~18.0, the release 0.49 s before 19.0, and the bracket ending on 19.0, where
the PCF's first increment is timed.

## The fix on the board (`ecb10f0e`, 20:36-20:47)

`pcf-unseen-board-ecb10f0e.json` (`pcf_unseen_board.py`, HC_RTC
page 4): the sync at the board's return left a write pending, still
pending a minute later with the lights on; held dark, it ran in 1.5 s;
the next sync's waited, lit and untouched, until 10 min after the boot.
Before the fix the page counted 42 writes against 41 syncs since 16:33.

## Then

JD's call: the clock is synced as before; the PCF is written only when
nobody is looking (the lights dark, which every deep sleep comes after, or a
long stretch without typing). The write plans from the board's clock when it
runs (`ps_plan()` reads `rtc_now()`), so a late write is as accurate as an
early one.
