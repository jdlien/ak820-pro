# The wake fixes' gate, case 3, on white (2026-11-01, 20:17-21:13)

Codex's gate for the wake fixes (`70f7c1ea10e`,
[`plans/review-codex-wake-fixes-2026-10-31.md`](../../plans/review-codex-wake-fixes-2026-10-31.md),
item 4) asks for both USB bits back, a host's frames after the wake and HID
working, with no reset, across four USB cases. Case 3 is a `uhubctl`
reconnection across a deep sleep. **It passes, in two forms.**

The board: white on the row ISR's stage 2 (`b120a2069c`, dev, token
`0x4849bde6`, flashed 19:44). That is v0.3.1's base `cfe6c2d3a5` plus the
row ISR rewrite. The USB driver is the same, and `sleep.c` differs by 2
lines, so the case counts for v0.3.1. Power saver, JD's lighting, on the
pack throughout (relay 2 never closed: the drain), the data on port 2 of
`3-1.3.4` only. The runner is [`case3.py`](case3.py). It pauses the
daemon (macOS raw HID is exclusive), drives the data line and reads the
board once it is back on USB. It never enumerates HID.

## Results

| Run | What | The wake | Back on USB | Record (op 14 sub 4, page 1) |
|---|---|---|---|---|
| 3a, 20:17-20:38 | data on to the sleeping board, no key | none in 20.5 min (3.50 mA mean, 4.43 max) | never | (stopped; data off) |
| 3a, 21:02-21:03 | data on to the sleeping board, then a key | JD's key, 21:03:51 | 3.8 s after the wake | key; slept 2693 counted s; flags `0x5B`: re-attach, frames within 20 s, PCF, acq |
| 3b, 21:05-21:13 | data off, asleep, a key, data on 30 s later | JD's key, 21:12:30 | 0.9 s after the data on | key; slept 55 counted s (66 PCF s); flags `0x4B`: re-attach, PCF, acq |

- **A host's attach does not wake a deep sleep.** With the data on for 20.5
  min the board stayed asleep. The Mac's kernel logged no USB event at all.
- **3a: a key wake into a host that had nothing to talk to.** No frames came
  within 3 s, so the recovery's re-attach ran (D+ off 100 ms, then on). The
  Mac enumerated the board right after (its three HID interfaces), and the
  frames-within-20-s flag latched. Codex's concern was that the D+ toggle
  does not set `PHY_EN`. The host's reset reached the board anyway, and
  only the driver's reset, resume and wakeup handlers turn the transceiver
  on (each sets `PHY_EN` with `ESD_EN`), so both bits are back. This is
  inferred from enumeration, as in case 1: this build cannot read `CFG`
  (black's census is ds-phase only).
- **3b: the plain reconnect.** The re-attach ran into no host (data off).
  The data came on 27 s later: enumerated in 0.9 s, HID reads after it.
  Neither frames flag can latch here by design (`0x04` only inside the
  recovery's USB step, `0x10` within 20 s of the wake). The frames are shown
  by the enumeration and the HID traffic.
- **No reset anywhere.** Page 1 counts **2 sleeps since the boot**
  (20:10:11-21:03:51 and 21:11:29-21:12:30) and **3287 s slept**, against
  the logger's 3282 s under 6 mA since 19:44. Page 4's uptime is the system
  timer's, which stops in Deep-sleep: 2043 s awake plus 3282 s asleep is
  the 5345 s since 19:44:00 less 20 s (the flash itself). The watchdog's
  last-boot flag is clear. PLL 87 loops on both wakes, 0 strays, no
  recovery step timed out.
- **Whether the waking key typed was not checked.** JD pressed a key only
  to wake the board, and nobody looked for it on the Mac. The record's
  `key_gain` (0 on both) says nothing here: the firmware counts it only on
  a sleep the bench armed (op 14 sub 4, `sleep.c`'s `arm_task`), and these
  were the ladder's own sleeps. (Corrected 11-02: this line first read the
  0 as the key lost on the host.)

⚠️ The logs print FAIL for 3a (21:03) and 3b. That is the runner's first
check, not the board. It wanted flag `0x04` and an uptime equal to the
wall clock: `0x04` cannot latch once a re-attach has run, and uptime
excludes the time asleep. `case3.py` as committed checks the 20 s flag (3a
only) and uptime plus the logger's time asleep. The JSONs keep the raw
reads.

## Also seen

- **The ~62 s bursts before 19:20 were not wakes.** From 17:45 to 19:20 the
  logger shows ~14.5 mA for ~10 s every ~62 s. That is the radio module's
  level; the MCU awake draws 27 mA or more. They stopped after the 19:44
  flash, with the daemon running or paused. Their cause is open.
- **The row ISR session's 20:07:15 "no board on USB" was a host-side miss.**
  The kernel log shows white's interfaces starting at 20:06:11.55, 0.5 s
  after the data came on. The check was `system_profiler SPUSBDataType |
  grep 0x8009`, since replaced by the `ioreg` form, which has no miss on
  record. All three `ioreg` forms this runner logs saw the board in the
  same poll.
