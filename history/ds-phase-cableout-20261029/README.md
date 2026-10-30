# The overnight cable-out run on Warren's ds-phase (10-28/29)

The diagnostic for gremlin's WDT reset inside a deep sleep
([`../../plans/BACKLOG.md`](../../plans/BACKLOG.md), "A watchdog reset inside
a deep sleep"; GREMLIN-RESULTS §21), on JD's board: Warren's `fcb7ae00b4`
(dev, token `0xf2a645a7`), on its pack (relay 2 off), with the USB cable
pulled out of the keyboard. Out, the data lines float, as on gremlin's
board; with the relay and `uhubctl` alone they stay held by the hub's
pull-downs. Balanced: asleep 20 min after the last key.

## Timeline (10-29)

| Time | What |
|---|---|
| 00:05:36 | USB data off after the flash and its check (`../ds-phase-check-20261029-0002/`) |
| 00:24:57 | asleep (sleep 1) |
| 01:37:18 | sleep 1 ends at a key; the cable came out about then (out by 01:38) |
| 01:37-03:35 | JD's use, on BT |
| 03:45 | the dim (35.3 to 32.7 mA), 10 min after the last key |
| 03:55:05 | asleep (sleep 2) |
| 08:52:51 | sleep 2 ends at a key, the cable out |
| ~08:54 | the cable back in |
| 08:55:09-08:55:39 | data on for the read (`slots-0858.json`), the daemon paused |
| ~08:55 | Fn+B to Power saver for the day's run |
| 08:58:11 | asleep (sleep 3), the cable still in |
| 09:40:20 | sleep 3 ends at a key (right Shift) |
| 09:43:42 | dark at ~13.5 mA for 14 s, then asleep (sleep 4) at 09:43:56 |
| 09:44:49-09:44:57 | ~13.9 mA for 9 s inside sleep 4, then back to ~3.1 mA: a lock-light frame (below) |
| 10:33:54 | sleep 4 ends at a key; the cable back in |
| 10:37:17-10:37:20 | data on for the read (`slots-1037.json`), the daemon paused |

## What the board and the power log say

- **Sleep 2:** 15,012 counted seconds (17,706 real, the RTC's second
  ~15% slow asleep), woken by a key (P2 `0x100`), flags `0xc0` (slept,
  returned), **0 strays**. The power log: 3.12 mA mean, 3.77 max, no rise
  in 4 h 55 min.
- **Sleep 1:** 3,610 counted seconds, a key (P2 `0x200`), 0 strays.
- **No reset:** the watchdog record is empty (`valid` false,
  `consecutive_resets` 0), and slot 10 holds only sleep 0, the check's
  30 s sleep inherited at the 00:03 re-flash. After the 08:52:51 wake the
  current held at ~36.9 mA, with no restart ~12 s on.

## What it shows

Not a reproduction. Asleep, the core wakes once a counted second (the RTC)
and goes back: ~15,000 of those with the data lines floating, lead (a)'s
moment, all clean, and no stray wake at all. The real wake, where
`usb_phy_onI()` turns the USB block back on (lead (b)'s moment), passed
once for certain with the cable out (08:52:51) and probably twice
(01:37:18).

Next: Power saver for a day of JD's use with the cable out (a sleep after
every 3 min pause, a real wake at every return), read in the evening.
Slot 10 and the watchdog record keep a reset until the next one; the ring
keeps the last eight sleeps.

## The midday read (10:37)

- **Sleep 3:** 2,122 counted s, a key (P2 `0x4000`), 0 strays.
- **Sleep 4:** 2,526 counted s (2,998 real from 09:43:56), a key (P0
  `0x10`), 0 strays, flags `0xc0`.
- **No reset:** the watchdog record empty, `consecutive_resets` 0, slot 10
  still sleep 0; the stray snapshot empty. `next_seq` 5.
- **The 9 s at ~13.9 mA at 09:44:49 was a lock-light frame, not the core
  and not the cable** (found that evening). It left no trace on the board:
  no new sleep, no stray, and sleep 4's counted seconds span it. The day's
  log has 52 like it, ~10 s each, ~63 s apart while the Mac was in use with
  the keyboard asleep (34 between 18:04 and 18:41), and they stop at the
  daemon's "held" (09:45:51, 17:49:31, 18:14:20, 18:42:10). The known
  ~1.6 mA average of frames into a sleeping board (`plans/BACKLOG.md`).
- **When the cable came out is not certain.** JD remembers shortly before
  9; the chat has JD's "I'll unplug now" at 09:40:42, after the Shift. The
  sleeps' draw sides with the chat: sleep 1 (cable in) 3.28 mA and sleep 2
  (out) 3.12, against sleep 3 3.51 and sleep 4 3.19, though frames into a
  sleeping board move these means too.

## The afternoon, from the power log (10:37-19:00)

Twelve sleeps, each ended by a wake to the lit level, from 3 s to 2 h
32 min (15:12:48-17:45:04); among them 1 h 12 min (17:48:45-19:00:46) with
44 frames into it. Nothing in the
current looks wrong; the board's record decides whether any wake was a reset.

Files: `slots-0858.json`, `slots-1037.json` (op 24's slots 0-10 and the watchdog record, read
with `ds_slots.py`, in `../ds-phase-check-20261029-0002/`), `run.log`.

## The evening read (10-30 12:49)

White's cable was out ~12:31-12:47 10-30 while black sat on the relay cable
(`../black-health-20261030/`, `../ds-phase-black-20261030/`). Data was on
12:49:19-12:49:21 (`slots-1249.json`). White read 49.3% and 3888 mV, and
its uptime was 30,154 s, 8.4 h awake since the 10-29 flash.

- **No reset in 32 sleeps since the 10-29 flash:** `next_seq` 32. Slot
  10 still holds sleep 0 (the check's 30 s sleep), the watchdog record is
  empty, and `consecutive_resets` is 0.
- **The ring, sleeps 24-31:** every one woken by a key, flags `0x40`, 0
  strays. Sleep 24 is the night of 10-29/30, 27,577 counted s (~9 h).
  Slot 9 is sleep 31: 715 counted s, a key, `0xc0`. The stray snapshot is
  empty.
- **So no repeat on white** across a day of Power saver with the cable out
  and two nights. The diagnostic moves to black, the board that reset
  (`../ds-phase-black-20261030/`).

⚠️ From 12:43 10-30 both boards run `fcb7ae00b4` with the same token
(`0xf2a645a7`). Tell them apart by the level (white is mid-drain), the
profiles' names, or the ring's `next_seq`.

## The end on white (10-30 17:28)

White went to the mainline plus Icon only at 17:28:27 10-30
(`../icon-only-20261030/`), without a last read of the slots. Its battery
log, dumped at that flash, runs unbroken from 00:20 10-29 to 17:20 10-30
(165 entries, 15 min apart), and the RAM log restarts at any reset: **no
reset on white in the whole run**, 41 h with ~31 h of it asleep.
