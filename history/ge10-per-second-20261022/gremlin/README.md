# The edge-pump fix on Gremlin's board (17:03 10-22)

The parent README found one pass of 10 ms or more every second on the Mac's
board. This directory is the same check on Gremlin's board: a baseline on
`36afff30e8`, then `ce229f87c6` (`mac/edge-pump`, codex cleared) flashed, then
the same reads.

**The conditions, both halves:**
- on the USB cable, powered by it;
- the daemon's transport `usb`, radio and lockchan off;
- now-playing showing a paused track (static text), so the only load was the
  daemon's 5-min syncs and health samples;
- no typing.

**The builds:**
- **before:** `via-dev-36afff30-20261021-142453.bin`, token `0x75e44ccc`, at
  26.4 h of uptime;
- **after:** `via-dev-ce229f87-20261022-165939.bin`, token `0x32d3502c`,
  built here. Flashed 17:03:24-17:03:59; the enumerated sync at 17:04:06
  read before -37.1 ms, after -1.3 ms. `ds_deep_wfi.constprop.0` stayed at
  `0x2000152c`.

**The reads** (`ak820health.py --stalls`, text and `--json`):

| File | Time | `count_ge_10ms` | `count_ge_25ms` |
|---|---|---|---|
| `stalls-base1-py` | 16:52:36 | 21,344 | 0 |
| `stalls-base2-py` | 17:03:16 | 21,456 | 0 |
| `stalls-after1-py` | 17:15:32 | 22 | 0 |
| `stalls-after2-py` | 17:26:12 | 32 | 0 |

**The result:**

| | Before (`36afff30e8`) | After (`ce229f87c6`) |
|---|---|---|
| ge10 between the two reads | 112 in 640 s, 0.175 a second | 10 in 640 s, 0.016 a second |
| ge10 since boot | 0.22 a second (26.4 h) | 0.024 a second (32 in ~1330 s) |
| ge25 | 0 | 0 (nonflash 0) |
| `loop_gap_max_ms` | 20 (`blit`) | 20 (`blit`) |
| passes a second | 214 (4.66 ms a pass) | 226 (4.42 ms a pass) |
| `blit_pump`'s share of slow-pass time | 14.8% | 2.2% |

Before the flash, about one second edge in five crossed 10 ms here, against
nearly every one on the Mac's board. The difference is the loop: `ch582`
costs the same per pass on both boards (1.23 ms here, 1.21 ms on the Mac),
and the Mac's extra ~0.6 ms a pass is all `unaccounted`.

**What the ring showed** (the last 16 slow passes):
- **Before:** 11 or 12 of 16 were the second edge's pass, `second_edge 3`
  with `blit_pump 2`, at 10-13 ms. The rest were `battery 1`, `display_hk 3`
  with no pump.
- **After:** none had the pump on the edge's pass, and none had the pump
  stacked with `battery`, `display_hk` or `leds`, the moved cost codex warned
  of. All 16 were exactly 10 ms:
  - 11 were the 10 Hz block: `battery 1-2` with `display_hk 3` (or
    `display_hk 1` with `ch582 4`, or `unaccounted 6-7`). These are the 1 Hz
    latch run from the 10 Hz call when the edge's own attempt was gated on a
    queue still painting, and the fix does not touch them. Latching the second
    only from the edge site, and retrying on the next pass, is a possible
    next cut (`plans/BACKLOG.md`).
  - 3 were the edge's pass with the 10 Hz block on it: `second_edge 3`,
    `battery 1-2`, no pump.
- `blit_pump`'s 7.4 ms of slow-pass time after the flash says a few of the
  earlier slow passes carried the pump; the ring had rolled past them.

**Not separated:** after the flash the board had been up only ~20 min,
and a fresh boot's loop ran ~0.24 ms a pass faster. Some of the drop may be
that. The ring's change in what the slow passes are made of is the cleaner
evidence.
