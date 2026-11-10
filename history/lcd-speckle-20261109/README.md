# The song title garble, 11-09: the counter reads

The investigation is `plans/LCD-TITLE-GARBLE-PLAN.md` and `plans/BACKLOG.md`'s
first item; the split's protocol and reading rules are
`plans/LCD-DIAG-SPLIT-PROTOCOL.md`. These files are the board's counters, read
over `scripts/lcd_diag.py` in short data-line windows (relay 2 off throughout,
for the drain), and the photos and health reads from earlier in the day.

## The builds

| Build | Token | Old send | On white |
|---|---|---|---|
| `lcd-diag` `5688b2a975` | `0x8edc1022` | at `0x83c` | 15:14-22:32, and from 23:00:33 (the standing state, mode a) |
| `lcd-diag` `1bc39c8281`, the split | `0x6d970a9b` | at `0x848` | 22:32:46-23:00:05 |

Both are daily builds that boot into fix A (mode a). In each, `old` is
`4790208267`'s polled send. Its instructions are the same in both builds; only
its address and its literal pool's RAM addresses differ (codex's review of the
split, `plans/review-codex-lcd-diag-split-raw.md`, item 2).

## What the old send did

| When | Build | Old mode's result | Windows | Counters |
|---|---|---|---|---|
| 15:14:57-15:38:32 | 5688b2a975 | garbled (JD's Bluetooth changes) | 53 | all 0 |
| 16:55:34-16:59:30 | 5688b2a975 | garbled (the camera: one title painted, the next never did) | 75 | all 0 |
| 22:33:24-22:57:04 | 1bc39c8281 | **clean x14** | 274 | all 0 |
| 23:00:40-23:09:44 | 5688b2a975 | **garbled at change 3** (Virtua - Final Destination, 23:08:55: the artist not replaced, a line of noise at the top) | 105 | all 0 |

"All 0": give-ups, strays, late and windows not idle; every polled window
began with TX empty, RX empty and not BUSY, and none came within about 190 us
of a DMA's completion. Fix A's stretches between (15:38-16:55, 16:59-17:36,
22:32-22:33, 22:57-23:00) were clean with every counter 0, and `exit_extra` 0
on the split.

## What it shows

The same evening, the same board, the same songs and the same send
instructions: 5688b2a975's old mode garbled within three changes and the
split's did not in fourteen. So the earlier garbles did not depend on the
afternoon's conditions. They depend on the build: something that moved between
the two images. Candidates, from codex's instruction-level comparison:

- **The send's address.** `spi0_poll_send_old` moved 12 bytes (`0x83c` to
  `0x848`), and everything around it shifted. Flash wait states make a polling
  loop's cycle timing depend on its alignment, so the same loop can complete
  its count at a different point relative to the shifter.
- **The window's code around each part.** In the split, old's window is a
  copy per mode with direct calls. Against 5688b2a975 it is shorter at CASET
  (8 cycles to 0 between DC low and the call; 5 to 3 from the return to DC
  high) and after RAMWR (9 to 3), and the same at XS to RASET, where the
  column end goes out.

Either way the fault is sensitive to time at the scale of a few cycles, or to
code placement, and not to anything the counters can see. That matches fix A
curing it with none of its checks ever firing. It also means the split's
other modes can't be read against an old mode that doesn't garble: a split
needs the old path's code and layout identical to 5688b2a975's, or a bus
capture.

## Files

- `health-*.txt`, `photo-*.jpg`, `dev-read-1353.txt`, `wake-ring-1448.txt`:
  the morning's health reads and photos, the dev build's read, the wake ring.
- `fixA-read-145*.txt`: fix A (`6683c18134`) over 2.4G and Bluetooth.
- `diag-*.txt`: 5688b2a975's afternoon (old 15:14-15:38 and 16:55-16:59, the
  camera clip; A between), and the read before the split's flash
  (`diag-read-173618-preflash.txt`).
- `split-*.txt`: the split, its boot read, step 1 (old, clean x14), and back to A.
- `back-*.txt`: 5688b2a975 reflashed at 23:00:33, old set at 23:00:40, the
  garble's read at 23:09:44, and A from then.
