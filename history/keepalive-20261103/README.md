# The keep-alive's measurements on white (11-03)

The module ends the BLE link 30 min after the last traffic it sees
([docs/wireless.md](../../docs/wireless.md), "The module ends the link"), and
the Mac takes ~2.4 s to rebuild it: the first key after a long sleep is lost.
Warren's keep-alive (`gremlin/keepalive`, `6cbbb8df653` and `3b04a983a24`,
codex: [`plans/review-codex-keepalive-2026-11-03.md`](../../plans/review-codex-keepalive-2026-11-03.md))
wakes the board dark every 25 real minutes on BT while it is connected, for
the first 18 h of an absence, so its poll keeps the link up. On row-isr as
`c043db65dd` and `a088b51c8b`.

## M1: what a held link costs asleep (from the logs, 09:35)

`power.csv` (INA228, 1 Hz) around the six reason-719 drops of 11-01/02, white
asleep on battery with the data off each time. Mean current in 5-min bins,
averaged over the six:

| min from the drop | -30 | -25 | -20 | -15 | -10 | -5 | +0 | +5 | +10 | +15 |
|---|---|---|---|---|---|---|---|---|---|---|
| mA | 3.61 | 3.55 | 3.62 | 3.61 | 3.52 | 3.57 | 3.44 | 3.44 | 3.44 | 3.44 |

- **Held 3.580 mA, dropped 3.441: +0.14 mA** (by drop +0.08, +0.13, +0.145,
  +0.15, +0.18, +0.15; six of six).
- Dropped is flat: each drop's four bins after it within 0.01 mA.
- Samples over 3.8 mA: 8-88 per 10 min held, 0-4 after (the connection
  events, aliased at 1 Hz).
- The link, not the time asleep: in the three burst cases white had slept long
  before the held window, and the step still falls at the drop.

So a keep-alive costs ~0.14 mA for the link plus its wakes (M3). At ~3.44 mA
asleep that is ~4-5%, ~2 mAh a 12 h night. JD's call (09:40): build it, with
an 18 h bound ("it would survive a typical evening after leaving work and
coming back in the morning").

## M4's control: the waking key after a drop, no keep-alive

`m4_control.sh N`: white asleep on battery with the data off and the daemon
paused (no lock-light frames to hold the link); white's own drop in
bluetoothd; one presser press of A1 ((0,13), F19); F19's arrival from the F19
listener's log; then the board's `key_presses` over the data line, which
separates a lost key from a failed press. Buzz must be unlocked at the press.

- ⚠️ **Match white's device, not "reason 719".** The iPhone's link drops with
  reason 719 too (`peerType iPhone`, `localRole=Peripheral`). White's line is
  `PowerLogger device "EB982520-A7AC-8123-705D-800ADA51BE60" disconnect`
  since JD's re-pair at ~01:10 11-03 (`0E7229B8-…` before it, the id of the
  11-01/02 drops; every re-pair changes it). The 12:01 run was given the old
  id, so it waited out its 40 min without seeing the drop; the press still
  came 11 min after it.
- **The control, 12:01 run, trial 1** (`m4-control-1201.json`): white asleep
  from 12:05:02, no wake; its link dropped at 12:34:55.851 (reason 719,
  `localRole=Central`, 29:53 after the sleep: the last poll); the presser
  pressed A1 at 12:46:19; the board counted it (`key_presses` +1) and **F19
  never reached the Mac**, which reconnected at 12:46:19.46. **The waking key
  is lost after a drop.** Stopped after one trial to give white to stage 5;
  the 11-02 22:36 wake (docs/wireless.md) is the second case.
- **The 11:34 run is void** (`m4-control-invalid-1134.json`): a key on white
  at 11:39:16 restarted the sleep, and both "drops" were the iPhone's (11:53:03,
  11:57:44), so both presses came inside 30 min and F19 arrived. The runner
  now restarts its wait when the logger sees white awake.
- The 10:05 run was stopped for the camera gate before its first press
  (`m4-control-run-aborted-1005.log`).

## The with-run (on row-isr's stage 5 build)

M2 (does a reason-7 wake's poll restart the module's 30 min: 2+ h of
keep-alive sleeps and no 719 for white's device), M3 (the logger's integral
over each reason-7 wake), and M4 with the keep-alive (presses after 30+ min).
M2 and M3 can run overnight; M4's presses need Buzz unlocked. sleep.c is
untouched by stage 5. Warren's watch items:

1. Stage 5's own sleep and wake (`sn32f2xx_sleep_enterI()`/`sleep_exitI()`,
   rewritten on row-isr): a few short ladder sleeps with presser wakes first,
   the ring clean, so a failed wake is not read as the keep-alive failing.
2. UART2 under the 125 us cadence: a lost ACK or 5C shows as
   `SLEEP_RC_RADIO` in `rc_timed_out` on the reason-7 wakes.
3. M3 measures stage 5's awake-dark draw; white's 11:31 11-02 stray (28.8 mA
   for 3.1 s, stage 2) is the earlier reference.

### The evening on stage 5e (15:14-19:36 11-03)

`m23_overnight.sh` (the daemon paused, the data off, one presser press, then
`m23_read.py` every 30 min: the logs only, no board traffic), on 5e
(`739fe1b635`, token `0xf222e31c`) from 15:14:53 until Blackberry took white
back for stage 5g at 19:36 (`m23-evening.json`):

- **The link held for 4 h 19 min asleep, 0 disconnects** of white's device.
  Without the keep-alive the module would have ended it at ~15:47:50, 30 min
  after the sleep at 15:17:55. **M2: a keep-alive's poll restarts the
  module's 30 min.**
- **The calibration works.** The first wake came 25:56 after the sleep on
  the default rate (1308 counted s); the second came 24:57 after its entry,
  once the first had measured white's rate (~841 per mille, against 10-19's
  872); then every 24:58 (median of 11).
- **M3: each wake is dark, 5 s and ~98 mA·s above the 3.36 mA floor** (the
  INA228's own charge register; peaks 28.5-29.1 mA), ~0.065 mA over 25 min,
  against Warren's estimate of 79 mA·s. With M1's held link, the keep-alive
  costs ~0.2 mA asleep, ~6% of the floor.

The read after: every ring entry reason 7 at ~1308 counted s (fewer once the
rate is measured); no 719 for white's device. Past the bound, the last
keep-alive comes at up to 18 h of absence, the sleep after it runs on the
86400-counted-s backstop (~27.5 h real) until a key, and white's 719 lands
~30 min after that last reason-7 wake.
