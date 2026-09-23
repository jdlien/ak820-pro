# Third crash hunt — DMA arm timing (2026-09-23 13:01 → 14:01)

`scripts/crash_hunt.py --hours 1` against an **instrumented** build carrying
v7, the lost-write fix and the arm-window timing
(`via-instrumented-a5a06614be-dirty-20260923-125750.bin`, token `0x0a8a1d5b`;
its source is firmware `02db293696`). `scripts/consolelog.sh` captured the
console. Same stress as the [first](../crash-hunt-2026-09-22/) and
[second](../crash-hunt-2026-09-23-v7/) hunts. The owner was on another
keyboard. Plan: [`plans/CRASH-HUNT-PLAN.md`](../../plans/CRASH-HUNT-PLAN.md).

## Result

**One hour, no reset.** 194,068 DMA arms; 16,270 text pushes, 1,681 playback
flips, 180 effect changes, 120 keymap flips and 120 synchronous RGB saves.
Keymap, encoders and lighting matched the backup at exit.

- **6 blit timeouts, all transfers that never started**, all recovered by one
  retry. 2 busy-waits (the guard of the 2026-09-22 fix, waiting out an
  overlap).
- 25 non-flash stalls of 25 ms or more: the console's own output on the
  instrumented build. The daily build under the same stress had 8 in ten
  hours.

## What the arm timing says

The timing asked whether an interrupt landing in the arm window -- from
FLASH_CS low through the READ command to `DMAEN` -- lets the DMA trigger
pass unseen. Ticks are 5.33 µs; "slow" is more than 10.

| | all arms | the 6 never-starts |
|---|---|---|
| command phase slow | 23,275 of 194,068 (12.0%) | **none** (0–3 ticks) |
| fire phase slow | 24 (0.01%) | **none** (0–2 ticks) |

**Every never-start armed fast**, so the arm window isn't what goes wrong
in these six. That fits the 2026-08-30 finding that residue in SPI1's RX FIFO
isn't it either.

## The lead: every one was a clock digit

All six timeout lines are identical but for the timing:

```text
kind=0 ris=0e|0f cnt=659/659 s0=69 s1=25 ris1=08
```

`cnt` is `DMACNT`, programmed as bytes − 1: 660 bytes, 330 pixels, 15×22.
That is exactly one cell of `ASSET_IOSEVKA_REGULAR_30`, the clock face, and
nothing else draws with it. Under this stress the clock band repaints after
every playback flip, so clock digits are roughly 5–7% of blits. Six of six
by chance would be about one in ten million.

What sets a clock digit apart from a text glyph is not the path (both go
through the glyph queue and pump). It is one of these:

- the transfer length (660 bytes against 168 or 460 for the text faces);
- the source region in the external flash;
- when it is armed: at the RTC second edge, and under this stress right
  after a synchronous band clear, itself a DMA from flash address 0.

A retry of the same glyph always succeeded, so a bad address is out.

**Next:** the instrumented timeout line should carry the source address,
w×h, and the previous blit's source, length, and the time since it finished.
A per-face blit count would give the exposure.

## Files

- `console-blit.log` -- every blit-related console line: the six timeouts
  and the once-a-minute `[lcd] arms=` base rates.
- `hunt.csv`, `events.log`, `run.json` -- the hunt's readings, log and
  arguments.
