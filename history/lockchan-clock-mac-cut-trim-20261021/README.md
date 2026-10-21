# The Mac's wireless clock with the frame trim, a 30 min cut (14:29-14:59 10-21)

The same test as the morning's
([`../lockchan-clock-mac-cut-20261021/`](../lockchan-clock-mac-cut-20261021/README.md)),
on the firmware with Gremlin's frame trim:
- **The board:** `36afff30e8` (dev, token `0xef38330e`), which is `01abfe0ecf`
  merged with `36330d5ec8`. Flashed 14:22, log in
  [`../flash-trim-20261021/`](../flash-trim-20261021/flash.log).
- **The daemon:** `21e8fe8`, main with Gremlin's `a2dbd65` (STEPPED, the
  clock's idle hold). Installed 14:23:23.

`run.sh` waited for a USB sync with `|before| <= 25 ms`, then ran
`deep_cycles.py --board-only --awake --dwell 1800 --rtc-gate`. That put
the board on its pack with the data cut, the stage forced to SCREEN_OFF and
never asleep, the slider on BT. JD used the Mac on other keyboards throughout.

**The settle after the flash.** The flash erases the persisted RTC period:
- 14:23:26: before -459.8 ms (slewing);
- 14:26:27: before -2885.1 ms (stepped), the SOF loop still re-converging;
- 14:29:27: before -8.8 ms, settled, and the cut began at 14:29:29.

A cut started on the first sync would have opened the frames' window on a
board still slewing.

**The frames** (op 17 sub 8; zero before, after the cut):
- **applied 4, refused 0, rejected 0, retried 0, dropped 0;**
- **rate trims 2:** the period went from 32284 (the SOF loop's, at the cut)
  to **32322**, +0.12%;
- **the last frame's offset: -3 ms** (target - board), 300 s after the one
  before. That is ~10 ppm, under the 50 ppm floor, so it took no trim.

The frames went at 14:41:46 (737 s after the sync: `OWNER_FLOOR`), then at
14:46:47, 14:51:50 and 14:56:53. The spacing was 300 s, not `EVERY` (600 s):
JD's input paused for 30 s or more inside each interval, which fires the wake
guess, and the wake guess sends at `MIN_GAP` after the last frame
(`lockchan/clock.rs`).

**At the replug** (14:59:49), 180 s after the last frame, the daemon's
sync found the board **-20.0 ms** (board minus host).

| | Morning, no trim | This run |
|---|---|---|
| Last frame's offset | -1616 ms | **-3 ms** (300 s) |
| At the replug | **+1106.3 ms** (481 s after the last frame) | **-20.0 ms** (180 s after) |
| Period off USB | 32463, untrimmed | 32284, trimmed to 32322 |

Scaled to `EVERY`'s 600 s spacing (no pauses in input), the replug's
~23 ms in 180 s (from +3 ms ahead to 20 behind) is ~75 ms before each
frame, against the morning's ~1.6 s.

**deep_cycles said FAIL, for one reason: `key 8`, not 1.** The bench's
wake-rig key (relay 1) has wires soldered to the switch. They shorted when
JD moved the board mid-run, which made 7 presses the run did not make; the
Mac beeped at each. Every other gate passed:
- the board stayed awake, with no reset;
- no pass reached 25 ms;
- the link's gated counters stayed at zero (`timeouts` 146 of 384 sent is
  ungated; the morning's run had 188 of 366);
- the RTC gate passed.

Files:
- `trace.log`: the daemon's status every 10 s.
- `cut.log` and `cut/deep-cycles.json`.
- `counters-before.txt` and `counters-after.txt`.
- `wait.log`: the unsettled sync.
