# Does the watchdog count in Deep-sleep? No (23:31-23:50 10-28)

The question came from gremlin's board, which took a WDT reset (site 27,
`WDT_SITE_DEEP_SLEEP`, RSTST 0x03) about 8 min into an untouched ladder sleep
on BT at ~23:02 10-28. One of the leads was a WDT that counts asleep, with the
RTC's second no longer coming. Until tonight, the only evidence that it does
not count was a single 30 s unfed sleep on 10-18
(`../deep-sleep-20261018-1-key/`, run 3). Every sleep since then feeds it each
counted second, which would hide a counting WDT.

**The run:** `wdt_asleep.py` (this folder), on JD's board (`8ec0c8b9b4`,
dev), mid-drain:
- **on the pack:** relay 2 off, never touched;
- **data cut** (`uhubctl`);
- **the stage** forced dark;
- **armed** with op 14 sub 4 and `no_feed`, no press;
- **entry and wake** read from the INA228's current.

The daemon was paused, and the RAM battery log was dumped first
(`~/Documents/ak820pro-battlogs/`, `-pre-wdt-test`).

| cap (counted s) | awake again after (real s) | asleep | woke | strays | WDT reset |
|---|---|---|---|---|---|
| 120 | 138.9 | 3.36 mA | the cap, 120 s counted | 0 | no |
| 120 | 138.7 | 3.47 mA | the cap, 120 s counted | 0 | no |
| 600 | 711.8 | 3.32 mA | the cap, 600 s counted | 0 | no |

**The watchdog does not count in Deep-sleep.** That's 840 counted seconds
unfed, against a timeout of ~11.5 s, with the record empty and RSTST 0x01
(the flash's software reset) after each run. A reset inside a sleep therefore
needs the core awake for ~12 s without a feed:
- a wedge at the wake (the errata-37 class);
- or an interrupt that never lets go after the unlock.

The counted second ran 16-19% slow here (712 s real for 600 counted).

USB data was on 20:18:58-23:31:49, 23:34:37-23:34:55, 23:37:43-23:38:01 and
23:50:22-23:51:25; the next run's data on 23:52:27-23:53:47; off from 23:53:47.
