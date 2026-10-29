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
| 09:44:49-09:44:57 | ~13.9 mA for 9 s inside sleep 4, then back to ~3.1 mA (the cable came out some time after 09:41) |
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
- **Unexplained:** the 9 s at ~13.9 mA at 09:44:49, the level of the dark
  stretch before sleep 4, left no trace on the board: no new sleep, no
  stray, and sleep 4's counted seconds span it. The board's own wake loop
  has no path that runs 9 s and returns without one, so it was probably the
  radio module, not the core; the overnight sleeps had nothing like it
  (max 3.77 mA).
- **When the cable came out is not certain.** JD remembers shortly before
  9; the chat has his "I'll unplug now" at 09:40:42, after the Shift. The
  sleeps' draw sides with the chat: sleep 1 (cable in) 3.28 mA and sleep 2
  (out) 3.12, against sleep 3 3.51 and sleep 4 3.19. Taken as in through
  sleep 3 and out from about 09:44:49, which would make the 9 s the pull.

Files: `slots-0858.json`, `slots-1037.json` (op 24's slots 0-10 and the watchdog record, read
with `ds_slots.py`, in `../ds-phase-check-20261029-0002/`), `run.log`.
