# Backlog — known, accepted, or deferred items

## Next phase: record in daily use, then polish for other owners (2026-10-18)

The order agreed after the sleep experiments:

1. **Record over days and weeks** with the ladder and (once built) deep sleep
   in daily use: R5's logged drain at real use, the gauge against the logged
   energy, the runtime against R3's, how the timings feel.
2. **If it holds up, clean up and polish for a broader release**, for other
   AK820 Pro owners rather than upstream. Things that would need doing,
   none started:
   - a README a stranger can follow cold (flash, VIA, Fn+B, what deep sleep
     does and how a key wakes it), separate from the working notes;
   - JD-specific defaults made neutral or documented (the default keymap is
     JD's VIA layout; the bench's relay key at (0,13));
   - the bench tooling (relay, logger, `uhubctl`) and `history/` set apart
     from what an owner needs;
   - the daily and fpb builds carrying the features, released through the
     existing tag-and-CI path, with the clean-install check;
   - the firmware commits pushed and `deps.lock` pinned to them;
   - a final pass for anything personal (the public-repo rule: no family or
     household details);
   - power charts and a calculator page on GitHub Pages
     ([`POWER-CHARTS-PLAN.md`](POWER-CHARTS-PLAN.md)); its sweep runs before
     step 1's full charge, not during it.

## Connected over BT but no typing after a wake (2026-10-29) -- JD's bug; located 10-30: Windows stops attaching the board's keyboard collection to the session (the keys reach hidclass); the trigger unproven, the daemon's lock-light frame the suspect

JD, ~23:35 10-29, over BT: "After being away for a bit, the
keyboard claimed it was connected but I couldn't type after logging in
(which, oddly, worked). I had to switch bt channels back and forth." JD:
not worth chasing until it reproduces.

What is known: the keys reached the host for the login, then stopped; the
board still showed BT connected; switching channel away and back (the
CH582's link made again) brought typing back, with no reset or power
cycle.

**Where, from the logs: gremlin's own board, on gremlin**,
by elimination (read only; JD's to correct):
- **Not on Buzz, by its logs** (Buzz's session): JD's board had no key
  after 23:33:47 (dim 23:34:47, asleep 23:36:49), no held title went at
  any return that evening, and the Mac's `bluetoothd` shows no channel
  switch all day (only six remote link drops, each ~30 min into a quiet
  sleep, each made again within ~1 s of the next key); it stayed
  connected to Buzz from 22:47:15 to 23:59, and was asleep from 23:36:49
  to at least 23:44.
- **gremlin:** the screen woke at 23:34:08 and the session unlocked at
  23:34:23 (Winlogon/Operational 1, 2). The daemon (0.2.0, `--lockchan`)
  had the lock-light channel granted all day, so a BLE AK820 was
  connected: the pairing `CC:40:5F:CA:52:BC` from 10-20. It had held a
  title since 19:23:29, and sent it at 23:34:39, 16 s after the unlock.
  It then sent a transport pause at 23:34:42 and a clock at 23:34:57.

**A lead to check first, not a cause:** the daemon's lock-light hold went
from 45 s to 3 min that morning (`9bfdbb0`; Buzz 09:04, gremlin 09:06). A
title held while JD was away goes at the first input after the login,
which on gremlin was 16 s after the unlock. So a lock-light frame (a burst
of `IOCTL_KEYBOARD_SET_INDICATORS` LED reports over BLE) would have
reached the board just as typing stopped. 52 such frames went into JD's
sleeping board that day (`history/ds-phase-cableout-20261029/`), harmless
as far as its power log shows.

**The repeat, 10-30 08:40-09:08, located** (the board left as it was; the
board's counters over its cable, raw input on gremlin, and an HCI trace by
Burrow, an elevated session on gremlin):
- **The firmware:** token `0xb5f2fdab` is a clean dev build of
  `8ec0c8b9b4` (`more-info`), flashed at Gizmo by Gizmo's session at
  JD's word, 23:34 10-28. The same source as JD's board's
  `0xe612779e`; nothing in the BT, UART or CH582 paths.
- **The same shape:** gremlin's screen woke at 08:40:36 and the session
  unlocked at 08:40:49. The daemon's first lock-light frame since
  23:47:18 went at 08:41:21, 32 s later. After that, no typing.
- **The board is fine:** its MCU counted every key and handed each to the
  CH582 as an `A1` frame. All were ACKed, with `tx_drops` 0, no reset
  and the watchdog record empty. The ACK timeouts climbed (10% of sends
  early on, ~60% by 08:59), and all were retried successfully.
- **The link is fine:** Windows showed it connected and read the battery
  over GATT. Caps Lock from another keyboard lit the board's light, as a
  Write Command to handle `0x0040`. The knob and the play key worked
  throughout, as notifications on `0x0047`, reaching raw input from the
  BLE device's `Col04`.
- **The keys reached Windows:** each one is a Handle Value Notification
  on `0x003C` (8 bytes) in the HCI trace, and hidclass's
  `NumReadReports` grew by exactly the link's notification count
  (385 = 219 + 120 + 46). There were no CCCD, Protocol Mode or other
  writes, and no reconnection. But raw input got **no** keyboard events
  from the BLE device's `Col01`. So the loss was above hidclass, in
  kbdhid, kbdclass or the session's raw input.
- **What cleared it:** JD RDP'd in (09:06:01) and came back to the
  console (reconnected 09:08:07). The board's keys reached raw input at
  09:08:08.4, and typing has worked since. A session reconnect re-attaches
  the keyboards to the session, as a channel switch does by reconnecting
  the board.
- **The suspect:** the daemon's Windows sender opens exactly that
  collection's keyboard-class interface (`Col01`, access 0) and sends
  `IOCTL_KEYBOARD_SET_INDICATORS` bursts through it
  (`platform/windows/lock_lights.rs`), holding the handle while the
  channel is granted. Both times the frame came 16-32 s after an unlock.
  The Mac's sender does the same within seconds of a wake (16 times on
  JD's board since 10-29 09:40) without a loss, but it has no kbdclass.
  Unproven.

**The repro, 10-30 09:12-11:40: none of seven runs reproduced it**
(cable out, the channel granted; raw input, the daemon's log and
Winlogon on gremlin; Burrow's HCI trace and hidclass rundowns):
- **A frame mid-typing**, at the cable pull (09:12:23) and later
  ones: typing carried on.
- **A 9 s lock** (09:13:45-54): clean.
- **The incidents' whole chain** (Lights out; locked 09:17:41; the
  board asleep 09:18:40). The CH582 ended the link itself at
  09:48:39.687, exactly 30:00 after its last packet (reason 0x13, as
  on the Mac). A key at ~09:54:13 got the reconnect at 09:54:23.4:
  host-initiated from a passive accept-list scan, encryption at +50 ms
  (bonded), MTU 527/76, the Scan Refresh exchange (0x002B/0x0028), the
  LED restore. There was no GATT discovery and no CCCD or Protocol Mode
  write. The unlock was at 09:54:35 and the daemon's frame writes at
  09:54:37-56 ("sent clock"), and typing was fine. The daemon's
  handle survived the drop (hidclass OpenCount 13 throughout).
- **Idle stretches unlocked**, the board asleep in Lights out, a frame
  at the return (10:07, 10:12): clean.
- **Balanced, locked 37 min** (10:28:48-11:05:55; asleep, the link
  held). The unlock was at 11:06:11, then hands off while the frame
  went (11:06:11-29) and the play-time frames after, then a return at
  11:34 after the board's sleep: clean.
- **A frame takes ~20 s of writes** before the daemon logs it as sent
  (~350 Write Commands to `0x0040`). So in both incidents the writes
  began at or just after the unlock, as they did in these runs.
- **No filter drivers:** the BLE keyboard's stack is `kbdclass` |
  `kbdhid` | `mshidumdf`. gremlin's radio is a MediaTek adapter
  (0489:E13A, driver 1.1043.0.542) on Windows 11 25H2 (26200).
  Web reports of BLE keyboards "connected but not typing" on Windows
  after sleep or idle are common across brands (Logitech, Microsoft,
  HP), fixed by toggling Bluetooth or re-pairing. None documents this
  exact split (the consumer collection alive, the keyboard detached).

**Also seen:** on Windows the waking key is lost, but only once the
link has dropped (30 min of the board's radio silence). At 09:54 the
first key took ~10 s to get a link (Windows' passive scan while locked
and dark), and only one report of it arrived; the Mac reconnects within
~1 s. After a sleep with the link still held (11:05, 11:34; JD: the
first key "correctly seemed to pass through"), it is not lost. A faster advertising burst after a wake might help; not
investigated.

**If it recurs:** don't switch channels. Plug the cable in, slider on BT
(the BT state survives that), and read `ak820 health`. Check raw input
per collection, and have an elevated shell take a HIDCLASS rundown. The
trigger is still unproven. To clear or convict the daemon: a stretch of
daily use with `--lockchan` off.

## A watchdog reset inside a deep sleep (2026-10-28) -- open: the keyboard on gremlin, ~8 min into an untouched sleep on BT, cable out; (c) ruled out on JD's board; the diagnostic `gremlin/ds-phase` on JD's board since 23:51 10-28, its overnight cable-out run clean (GREMLIN-RESULTS §21)

The record named only `deep_sleep()` (site 27), and the sleep's facts were
in `.bss`. Reading the code leaves (a) a wedge at the wake's first flash
fetch, (b) an interrupt storm at the unlock, (c) the WDT counting asleep.
`gremlin/ds-phase` (`27d1105d`) splits the site into phases (28-31) and, on
dev builds, keeps the sleep under way through a reset (HC_DEVHOOK op 24
slot 9). Buzz's session runs the repro on its bench: unfed armed sleeps
(for c), long untouched sleeps on battery with the host away, and, by JD's
hand, sleeps with the cable fully out (the bench's cable stays in the hub).

**(c) is out: the WDT does not count in Deep-sleep** (23:31-23:50 10-28,
[`../history/wdt-asleep-20261028-2330/`](../history/wdt-asleep-20261028-2330/README.md)).
Three armed sleeps, unfed, on JD's board ran to the cap: 120, 120 and 600
counted seconds, against an ~11.5 s timeout. Before tonight the only
evidence was 10-18's single 30 s run. So the reset needed the core awake
~12 s without a feed: (a) or (b). For (b), `usb_phy_onI()` turns the USB
transceiver on at every wake, and the driver stays `USB_ACTIVE` after a
pull.

**What's different from every bench sleep:** the cable fully out (relay 2
and `uhubctl` cut the power and the data, but D+/D- stay on the hub port),
and the host away (it's always been near, or the board on 2.4G). Gremlin's
board had slept cable-out six times before, each woken on purpose within
minutes.

**On JD's board since 00:03 10-29** (`fcb7ae00b4`, token `0xf2a645a7`;
`27d1105dc1` from 23:51): slot 9 survives a reset through the bootloader
([`../history/ds-phase-check-20261028-2350/`](../history/ds-phase-check-20261028-2350/README.md)),
so a reset inside a sleep will now say where, what woke it, when and the
strays.

**Next:**
1. The board untouched overnight with its cable fully out, on the pack. The
   logger timestamps any wake.
2. Then long sleeps on the pack, with the host away where it can be done.


## A day of typing after the LED cut: sleep at 60 s and a dim screen on the reserve (2026-10-28) -- JD's call, to build after the reserve is measured

JD (10-28): "There's almost no downside to aggressive sleeping when the
board is in this state since the lights are off anyways. But at least we
could ensure the board continues to type for a day or so after we get to
the LED cut... a user can make it through the rest of their day before they
have to charge in most cases." This revisits "Sleep after the LED cut in
every mode" (10-21, below), which was left alone.

- **Today, after the cut** (3400 mV, `power_set_lights_cut`): the RGB is
  capped to 0 and nothing else changes. Below 15% the ladder already runs
  Power saver's stages and sleeps at 3 min (`low_now`, `LOW_CAP_PM`); Lights
  out keeps its 60 s; Always on never sleeps.
- **The change:** once the cut fires, sleep after 60 s idle (Lights out's
  `sleep_ms`) and cap the screen while awake (`SCREEN_DIM_LEVEL`, 37 of
  100, or lower). In `power.c`: `power_sleep_wanted()`'s shortening under
  `low_now` gains one under `lights_cut`, and `apply()`'s backlight cap one
  for the cut. To settle when built: Always on too (the 10-21 proposal said
  yes; `power_sleep_wanted()` returns false for it first), and how dim the
  screen goes.
- **What it buys, modelled:** the reserve was ~5 h awake and dark at
  ~26 mA on 10-02, about 130 mAh. A working day of 8 h at ~10 mA (60 s
  sleep, mostly asleep between bursts) and 16 h asleep at ~3 mA is about
  130 mAh: a day, but only just. The sleep is the lever (3 mA against ~27
  awake); the screen is ~1 mA at JD's level, a few mA brighter.
- **Measure first:** R5, the drain since 04:44 10-24, runs on past the cut
  to shutdown and measures the reserve as built at real use, and what ends
  it (`plans/current-status.md`). Size the change against that.

## The Win/Mac switch loads each side's last profile (2026-10-27) -- BUILT: `bf29a081`, then each side kept as left (`33d6d4ae`, the eighth record; JD: "don't lose your settings") on `gremlin/os-profiles`, on the keyboard on gremlin (GREMLIN-RESULTS §20w, §20x), MERGED 10-27 (`ce3f842d`); its note below "So a change since the load ... is lost" no longer holds

JD (10-27): "can we make it so that the current profile is remembered for
windows and Mac layers so when a user flicks the switch, it changes to the
last profile used with that layer? ... blue keys on windows mode and
rainbow cycling on Mac mode". Then: "I think always on makes sense here
... Cheap feature to built that might actually be legitimately useful."

- **How:** each side remembers one slot. The menu's Load, Save and Save
  new and the Prof+/Prof- keys record theirs as the current side's; a
  Delete clears it from either side; Rename moves nothing. A flip (the
  dip switch's index 0, `dip_switch_update_kb()`) loads the other side's
  as the Prof keys do (`prof_step()`: `cancel_previews()`, then
  `prof_load()`, the name in the status band). A side with none changes
  nothing. No menu row (JD: always on).
- **Storage:** the profile block is full (218 B: the magic, the active
  byte, 8 x 27). The active byte splits into a nibble a side (0-7, 0xF
  none), the active slot being the switch's side's: a new magic (0xA3),
  and `hostagent/ak820profiles.py` converting 0xA2 (both sides the old
  active), so `flash.sh`'s backup carries the pair. No macro bytes.
- **Rules:** load once the switch has rested ~250 ms (a bouncing contact
  loads once); the boot's own reading isn't a flip (`dip_switch_init()`
  runs before the EEPROM is read); never reload at a boot, since the
  slider's flips reboot the board and would wipe unsaved changes each
  time. So a change since the load (the `*`) is lost on a flip there and
  back, accepted: there are no 27 B for a live copy a side. A switch
  moved while the board is off keeps the old side's settings until the
  next flip.
- **Cost:** a Prof key press's (tried on the board, P5b) and the deferred
  active byte; QMK already writes the default layer at every flip.
- **Keymaps in profiles (asked the same day): not whole ones.** The two
  sides already have their own base and Fn layers, so with this a flip
  changes the keys and the lighting together. A layer is 180 B (6 x 15 x
  2) of a 1 KB emulated EEPROM that's full, and wear_leveling.c keeps all
  of it in RAM (`cache[WEAR_LEVELING_LOGICAL_SIZE]`), where the dev
  build's heap gap is 136 B against a 128 B floor; the flash has room
  (220 KB of 256), the RAM doesn't. Keymaps on the asset flash would
  rewrite ~360 B of the EEPROM at every load, a consolidation (~58 ms,
  below) every few. What would fit: a byte of QMK's key options a
  profile (swap Alt and GUI, Caps as Ctrl), if a record's byte is found.

## "Icon only": a battery readout of the icon alone (2026-10-27) -- JD's idea; built 10-30 (`5c8c5f5ea8`, branch `icon-only`), on white since 17:28 10-30

**Built as below** (`history/icon-only-20261030/`), with three things the
pin didn't settle: Icon only is bit 4 of the byte (the face took bits 2-3
on 10-28, so the readout's 2-bit field was full), `Low`, `Charge`, `USB`
and `No Batt` stay (they say what an empty or red bar means), and in Large
the note is two lines (`Hours in 40 min` / `on battery.`). A firmware from
before reads the byte as garbage (percent), so `ak820profiles.py` restores
it there as Percent.

JD (10-27): "maybe we could have a 'None' option under the battery menu.
Pin that for later... for someone that wants a more minimal screen ...
Users still get the battery icon gauge so there's still an indication of
life but maybe some people don't like the stress of seeing the percent drop
a percent at a time."
- **The shape:** a fourth readout after Both (the Clock's Off is last too);
  kb_eeconfig's byte 4, profiles' range 1-4 (a record holding 4 reads as
  invalid on a firmware before it, so a downgrade drops that profile), the
  dashboard's text slot left clear. The icon, the bolt and the bulb stay,
  and so does the low warning: the icon's colour and the status band's
  "Battery low" (3550 mV) don't use the text.
- **The page:** Back, Percent, Hours of use, Both, the new row in row 4 (the
  blank one), the note under it at rows 5-7 with the profile summary's grey
  rule on its first line (`RULE_CHUNK`, `row_ruled()`) in place of the gap.
  Its preview blank.
- **The name: "Icon only"** (JD: "None sounds like we just keep the whole
  region blank, which I don't think we should do"; "the calmer choice").
  **The icon keeps its colours** (JD: "Apple would just keep it monochrome
  white, but I'm okay to retain that").

## The LED blink at an internal-flash write (2026-10-27) -- JD's bug; the consolidation is the blink; the scan through writes and the early cleanup built (`dc8e6d0c`, on the keyboard on gremlin, not merged); the other flicker is the clock chip's write after each sync

JD (10-27): "the board flickers once in a while. Hard to replicate, somewhat
sporadic, and subtle. But it does look glitchy when it happens"; "I mainly
notice the lights ... I haven't noticed screen blinking."
- **The mechanism** (docs/leds.md, "What an internal-flash write does"):
  while EFLD1 is in FLASH_PGM the row ISR de-selects every mux row
  (`drivers/led/sn32f2xx.c`), so the board is dark for each program call;
  a consolidation (~every 16 saves) rewrites 1 KB in chunks, a run of
  blanks over tens of ms. The deferred writes (RGB ~1 s, kb_eeconfig 5 s,
  the profiles' pair after kb's) put the blink seconds after its cause.
- **Who writes, unprompted** (the daemon's `ak820-health.csv`, a week): in
  quiet stretches ~1 a night, the clock's period (rtc_persist, ~04:30);
  on battery the level's milestones; the rest JD's own changes.
- **The idea:** the guard went in 09-01 on the belief that masked program
  windows froze a row for milliseconds; 10-04 corrected it (masked 10-20 us
  a line, the ISR runs between). The bright row came from the old code
  SKIPPING the scan in FLASH_PGM. So scanning straight through a write may
  show nothing (a row a few us late), and keep the key scan going too. The
  cost: writes slower (the ISR takes ~73% of the CPU), the consolidation's
  ~58 ms pause longer.
- **The test (JD: "a dev-only option in the menu that lets you do a write
  strategy test"):** a dev-only Diagnostics page: a write, a burst, a
  consolidation, and the guard's strategy as a choice switched at run time,
  so the same writes compare by eye. Deferring writes to when the board is
  dark only with a deadline (Always on, or typing for hours, never goes
  dark), and it trades against the change-of-computers brownout that today's
  flip fix guards.
- **JD's eyes on the page (10-27, Solid near-white):** One write and Ten
  writes show nothing on either strategy ("zero flicker"). Cleanup on Blank
  is "a very noticeable flicker"; on Scan, "a more subtle flicker". So the
  ordinary write is not the blink JD sees: the consolidation is. What Scan
  leaves is most likely the erase: two 1 KB pages, 1-2 ms each, stall the
  CPU and the row ISR (sn32f299.md, p. 251), so the scan stops with every
  LED off (the clock chip's video showed that stall: below). Not yet
  tried: Dim + write.
- **How often a consolidation comes:** when the log fills, never on a timer.
  The log is 127 lines; a write takes a line per 5 bytes of its block. A
  settled kb_eeconfig change (10 B) or an RGB save (8 B) costs 2, a profile
  save ~8, a Win/Mac flip with profiles ~10 (the 27 B last record, RGB, kb).
  So one every ~60 ordinary changes, ~16 saves or ~12 flips; the background
  writers alone (the clock's period nightly, the level's milestones on
  battery) every few weeks. The daemon's week can't count JD's own: the
  test passes reset the counters many times a day.
- **JD's direction (10-27):** "on dimming, using the scan strategy and doing
  the cleanup on dimming could help ... we just have to do it on a timer
  with 'always on' or plugged in configurations."; then "build 1-3 and the
  Dim + cleanup test ... Someone who hasn't typed for ten minutes is
  probably not looking closely at their keyboard."
- **Built (`gremlin/write-test`, `4ee668eb`..`dc8e6d0c`; codex three
  rounds, `plans/review-codex-flash-tidy-2026-10-27.md`):** the scan through
  a flash program by default (`sn32f2xx_pgm_scan`); `flash_tidy.c`, a
  consolidation once the log is half full, when the committed frame is dark
  and 30 s pass without input, or after 10 min without input on USB or in
  Always on (on battery the other modes go dark first); the Write test's
  Dim + cleanup, waiting for two rendered frames after the cap. Docs:
  docs/leds.md, "The blink is the consolidation". GREMLIN-RESULTS §20z.
- **Dim + cleanup, by eye (10-27, ~17:55):** JD: "can't see any flicker at
  the dim". But JD saw one flicker "in between me trying the options"
  and wonders whether there is another cause. The board's counters for
  those minutes (17:53:58-17:57:40): 13 flash writes, 10 passes >= 25 ms,
  every one in a flash write (none outside), no early cleanup (the count
  stayed 2) and the log empty, so no full-log consolidation either. Each
  long pass was a Cleanup or Dim + cleanup click, unless JD clicked fewer
  than ten. Not counted there: the row ISR slowed by the CPU-fed SPI0
  fills (docs/leds.md), which the fill-poll fix cut to 1.3% of the rows.
  A read-only watcher on gremlin logs every flash write, long pass and
  dip in the row rate with its time, for JD to match a flicker against
  the keyboard's clock.
- **The second cause: the clock chip's write (10-27, ~19:05-19:20).** JD
  saw another "scrolling between my selected theme and Save new" on
  Profiles. The watcher saw nothing there, but the daemon's log had a
  clock sync a minute or two before each sighting (17:55:12, 19:05:14).
  Every sync's correction requests a PCF write, and every PCF transaction
  holds the row ISR off, which leaves all the LEDs off. Predicted at
  19:15:14 + the slew; JD filmed it at 240 fps and saw "a set of (I
  think) three flickers": three bursts, the writer's three steps, on
  the second (history/pcf-flicker-20261027/; docs/leds.md, "The other
  flicker").
- **JD's call:** "Update the clock, only write the RTC when we sleep or
  after a pretty long no-typing delay. The failure mode is pretty minor
  since the board corrects the clock in a few minutes after a reboot
  anyways". Built (`gremlin/pcf-unseen`, `65f86da5`..`ecb10f0e`; codex
  four rounds, `plans/review-codex-pcf-unseen-2026-10-27.md`): on USB
  the writer's start waits for the committed frame dark or 10 min without
  input; off USB it goes at once (codex: the board's own discipline
  against the PCF waits on a pending one, so deferring off USB left it
  off and carried drift into the PCF). A run under way finishes (STOP is
  never left asserted). Open: on battery with the Mac's radio clock, the
  write still follows each sync.
- **Open:** 16 settings writes 19:01-19:05 (the log 0 to 304 B) while
  JD was on Profiles; scrolling and its previews write nothing
  (`prof_preview()` and the rollback are `_noeeprom`), so either JD
  saved or loaded, or something writes that shouldn't.
- **Owed:** JD's watch on the board day to day; then the merge.

## The default keymap as AJazz ships the board (2026-10-27) -- JD's call, the polish phase

JD (10-27): "the default keymap should probably reflect how AJazz ships
these boards, because my layout doesn't even match the keys and most
people probably wouldn't expect the Fn layer that I have (mostly inspired
by the Vortex Pok3r's defaults)". Today `keymaps/via/keymap.c` and
`keymaps/default` are JD's VIA layout (`scripts/keymap_to_c.py`); the base
layers and the Fn layers should be the stock firmware's, from AJazz's
manual and the stock images (fpb/ajazz-ak820-pro has them), with this
firmware's own keys (the menu's knob click, the profile keys, Fn+D, Fn+B,
Fn+C) placed where the stock Fn layer leaves room. JD keeps his layout in
VIA, as now. A menu item to put the keymap back to that default (QMK's
`dynamic_keymap_reset()`) is a separate feature, after it, with its own
confirm: the keymap is the hardest thing to lose and `flash.sh`'s backup
is the only copy off the board.

## A wear-leveling consolidation blocks one pass ~58 ms (2026-10-25) -- measured, not profiles'; every settings write can trigger one

P5a's first board measure (`history/config-menu-p3-20261025/p5a-measure-5ecc9a32.json`,
`scripts/p5a_measure.py`; plans/SETTINGS-PROFILES-PLAN.md, "When"), on the
keyboard on gremlin with JD's Drift at full brightness and speed:

| Pass | Median | Worst |
|---|---|---|
| No write (baseline, 20) | 6.4 ms | 8.4 ms |
| One profile save (26 B body and 3 single bytes; 23 saves) | 10.7 ms | 14.6 ms |
| A save that consolidated (2) | 58.4 ms | 58.9 ms |

- **Ordinary saves are inside C10's 15 ms ceiling,** so the plan's rule
  stands: profile writes happen at the click.
- **A consolidation came about every 16 saves:** wear_leveling.c:303 erases
  the 2 KB backing store and rewrites the 1 KB cache. That pass is over the
  25 ms bound where a key can be lost.
- **It isn't the profiles' doing.** Every writer of the emulated EEPROM can
  land on one: kb_eeconfig's settled write, VIA's keymap and lighting saves,
  the RGB flush. Profiles only make writes a little more frequent when
  someone saves a lot.
- **Today's exposure:** a consolidation is rare (the log fills after ~1 KB
  of writes), and the profile saves come from a knob click in the menu, not
  mid-typing.
- **If it matters:** split the consolidation across passes (erase a page a
  pass, then program it in pieces). That's a change to quantum/wear_leveling
  or the EFL backing store, both core files.

## The key lights flash at a deep-sleep wake (2026-10-24) -- cause found: the sleep starts before the dark frame is committed; fixed in `52acdffe99`, on JD's board since 22:02 10-24, proven at 22:19 10-24

JD saw it twice on `b9555ff3e6`, on the pack, at his daily setting
(Alphas/Mods, hue 185, sat 227, val 115, speed 231), the screen fine:
- **~10:45 10-24,** after ~6 h asleep: every key flashed white, then his
  colours.
- **That evening:** a flash, dark, a flash, all within ~50 ms.

**The video (JD's phone, slow motion, the wake at 21:16:22 10-24, in
Balanced).** 120 frames at 120 fps, 8.3 ms each. The audio track runs
1.0 s against the 120 frames, and the dark gap fits the 10 Hz tick (below).
The screen's clock reads 21:16:22 throughout. From the first lit frame:
- **0-42 ms (frames 5-9): the keys lit in JD's colour, at about half the
  relit frames' pixel level.** Its red/green/blue share is 0.19/0.24/0.58,
  against 0.19/0.24/0.57 relit: the same colour, dimmer, which is the dim
  stage's frame (value 64 against his 115). Not white.
- **42-100 ms (10-16): dark.**
- **~100 ms (17): the screen lights.**
- **~140 ms (22): the keys back at his colour.**

**The cause.**
1. In one 10 Hz pass, `power_task` applies the dark stage: scale 0, the
   screen's cap 0, the effect's re-init.
2. At the end of that same pass, `sleep_task` sleeps. Its RGB gate is
   `power_rgb_dark()`, which is `applied_scale == 0` and so true at once;
   the backlight's gate is the cap.
3. `rgb_matrix_task` never runs in between, so `led_state` (what the row
   ISR drives) keeps the frame from before: the dim frame in Balanced.
4. `sn32f2xx_sleep_enterI` turns the outputs off around it, and
   `sn32f2xx_sleep_exitI` turns the ISR back on with it at the wake.
5. The first render at scale 0 then commits zeros, ~40 ms after the wake:
   five calls of 17 LEDs, and the 16 ms flush limit.
6. The next 10 Hz block comes ~100 ms after the wake. The system timer
   stood still through the sleep, so the block's 100 ms counts from the pass
   that slept. It applies the lit stage, and one render later the keys
   light.

**Why only now:** since `0e322097f4` (10-20 16:25, the modes' revision),
Balanced goes dark and to sleep at the same 20 minutes, and Power saver at
the same 3. Before it, Balanced turned the lights off at 5 minutes and slept
at 7, so the zero frame was committed two minutes before the sleep. Lights
out goes dark at once and sleeps at 60 s, so it shows no flash.

**The first sighting's frame was the full one.** That sleep began at
04:44:31, five seconds after relay 2 went off, with JD idle well past 20
minutes. So the board went from USB power, lit at his full setting, straight
to dark and asleep in one pass, and the frame it kept was the full one.

**The fix: `52acdffe99` on `mac/wake-dark-frame`** (on `b9555ff3e6`; on JD's board since 22:02 10-24, mid-drain, with his go). JD's second 120 fps video (22:19:52 10-24, a wake from a real deep sleep) shows the keys going dark to his colour in one frame, with no dim frame and no gap, and the ladder still sleeps. Handed to Warren for the menu's build. It has two parts:
- **Gate the sleep on the committed frame.** `blockers()` sets `DSB_RGB`
  until the driver's `drive_now[]` sums are zero too, through a new
  `sn32f2xx` accessor. The sleep then starts ~40 ms later, and a wake starts
  dark. The risk to check: anything that kept the committed frame lit would
  block every sleep. The scale applies in `sn32f2xx_set_color` on every
  path, so at scale 0 every render commits zeros. The soak's sleep counts
  would show it.
- **Run the ladder's tick in the wake's first pass** (`power_task()` in
  `recovery_begin`). The keys then light one render after the key, ~40 ms,
  not ~140.

**The review** (an independent Claude reviewer, since codex isn't
installed on Buzz) found no must-fix and no should-fix. Its nits:
- **A comment overstated things.** A notice can be posted at the wake, but
  it only sets the display's flags. Fixed.
- **The low cap sees the level from before the sleep for one tick.** A
  sleep that crossed 15% lights the keys at the mode's ceiling for ~100 ms,
  once a discharge. Noted in the code. It cannot show at JD's value (115,
  under Saver's 128).
- **The bench's sleep arm masks `DSB_RGB` whole,** as designed: it sleeps
  lit on purpose. Left.
- **A separate blocker bit for "not yet committed".** Left: `0x4000` is
  Warren's `DSB_MENU`, and op 14's stage read-back tells the two apart.

The first code read (10-24) took `led_state` to be all zeros asleep, which
is where it went wrong. The rest of it stands: no board code paints every
LED one colour, the key rows driven at the wake are not LED rows (B14, B15,
B19, D19, A19, A18), the settings writes wait out the recovery, and
`RGB_MATRIX_TIMEOUT` is not set.

## A ghost of the dashboard's "100%" on gremlin's LCD (2026-10-24) -- noted, low priority

S0's photos (`plans/GREMLIN-RESULTS.md` §10) showed a faint "100%" in the
bottom-right dark grey fills: the dashboard's battery percentage, which
gremlin's screen shows day and night on USB, since it never sleeps there.
Most likely LCD image retention, which usually fades, not OLED-style
burn-in; not yet proved. JD (10-24): don't worry much, keep a note. If it
ever matters:
- **The test:** hold a grey fill over it for 10 min, photographed at the
  start and the end.
- **The remedies:** a pixel or two of shift for static text now and then;
  the screen off after a long idle, even on USB; the panel's inversion
  setting. JD's board sleeps on battery, so it's less exposed.

## ~~A bootloader item in the menu~~ (2026-10-24) -- DONE: built with P1b (`781d071f`, codex twice), on JD's board since 10-25; Reset settings sits under it since 10-27

Built as below: the Bootloader page (`plans/MENU-TEXT.md`), entered from
the menu on the board and flashed back. `Fn`+`Esc` stays bound. The
original note:

From JD's first look at P1a: a standalone item that says what it's for
("Use this to update the firmware"), a click to confirm "Enter Bootloader",
and how to leave without flashing (the slider to Bluetooth and back to USB,
or unplug and replug in wired mode). Then `Fn`+`Esc` needn't stay bound.
JD: "maybe we don't need it at all", and the words wait for his text pass.
Notes: it's `reset_keyboard()` / the dev build's `HC_BOOTLOADER` path; the
bootloader looks exactly like a dead board (CLAUDE.md), so the screen's
last words before the jump matter; never on battery past the RGB cut
(`flash.sh`'s reserve rule).

## Help's Shortcuts from the live keymap (2026-10-24) -- JD: "cool to have in there later"

Help's Shortcuts page is fixed text (`plans/MENU-TEXT.md`, generated by
`scripts/gen_menu_text.py`), so a VIA remap leaves it wrong. The menu could
build the page at runtime from the dynamic keymap: find which key holds
each function on the Fn layers and name it. Needs a keycode-to-label table
and the key names. Skipped for now (JD, 10-24). Meanwhile the cheap half,
checking the text against the *default* keymap at build time as the
generator already checks the times it quotes, is still open.

## The menu's text is tiny: a larger face (2026-10-24) -- JD's idea, a redesign, later

JD on the panel (S1's F3, Cozette 6x14, 20 columns by 8 rows): "_tiny_
... maybe a font size is going to be useful. But that's a massive
redesign. For now let's proceed with the tiny fonts." The next size the
board has is the 10x23 Iosevka face: 12 columns, 4-5 rows, so every
screen's words and paging change (`config-menu-mockup.html` stays the
spec). A middle size (8x16 or so, 16 columns by 7 rows) would need a new
1-bit face; `scripts/gen_mono_font.py` makes one from a BDF the same way,
at ~1.6 KB of the MCU's flash. Cost per row grows with the cell's area.

## ~~Fast spins leave old menu rows highlighted~~ (2026-10-24) -- FIXED in P1a (10-24): one lit row at most

P1a's scheduler paints a row's un-highlight before any new highlight
(`plans/CONFIG-MENU-P1-DESIGN.md`, the maybe-lit mask), and the host tests
check one lit row at most after every pass, through reversals, wraps and
preemption. The original note:

JD (F3, the slow build): "if I scroll at just the right speed I can make
most of the options turn yellow". Each detent retargets: the new row's
highlight and the old row's un-highlight are two slots, and a retarget
before the old one repaints leaves it yellow while newer ones start. For
P1: paint the old highlight's removal before (or with) the new one, so at
most one row is ever lit; the slot order in `menu_slots.c` decides it.
Check it again on the faster composer (`cbb51ac1`), where a move takes
~165 ms instead of ~210.

## The knob is sampled once a main-loop pass (2026-10-24) -- noted, measure before acting

Found in codex's review of the encoder change (`plans/review-codex-s1-encoder-2026-10-24.md`, finding 3):
`encoder_driver_task()` reads the quadrature pins once a pass, from the
main loop, not the row ISR that scans the matrix. One sample can enqueue at
most one detent, so no backlog forms, but a long pass is a long gap
between samples: at 15 ms a pass the knob is read at ~67 Hz. A fast spin
that moves two transitions between samples loses or garbles a detent, and
op 27's "nothing dropped" can't see that (it counts coalesced turns, not
transitions). JD (10-24) on fast spins: "'hard as I can' gets ignored by
the hardware, I'm sure". It may be this, not the hardware.
- **To measure:** count the quadrature driver's skipped transitions (both
  pins changed between samples: `encoder_LUT`'s entries 3, 6, 9 and 12 in
  `drivers/encoder/encoder_quadrature.c`, which count as no movement)
  during a hard spin, on a dev build.
- **If it matters:** sample the pins in the row ISR (~3,900 Hz) into a small
  ring, and decode in the main loop.

## `count_ge_10ms` ticks once a second: the clock's second edge (2026-10-22) -- fixed in `ce229f87c6`, on gremlin; JD's board after the drain

On `36afff30e8`, every second produces one pass of 10-13 ms
(`history/ge10-per-second-20261022/`). HC_ACCT's ring makes it:
- `second_edge 3`: the 1 Hz `draw_clock` and `draw_battery`;
- `blit_pump 2`: the pump moving a glyph in the same pass;
- `unaccounted 4`: QMK's core;
- `ch582 1`.

That is ~86,000 a day, against 0.18 a second on `b2a07e0d37`. Nothing is
lost: it is latency, at worst a few ms on a press landing in that pass, and
`count_ge_25ms` stayed at 6 overnight and all day. But a counter that ticks
at the clock's cadence can no longer show a regression.

**The fix, `ce229f87c6`** (`26b36e3ea0` plus comments, codex cleared,
`plans/review-codex-edge-pump-2026-10-22.md`): the 1 Hz latch sets
`clock_ticked_this_pass`, and the pump returns on it as it does on
`pass_deferred`. `ak820pro-jdlien` and `deps.lock` point at it.

**On gremlin's board** (USB, a paused track, no typing; 640 s windows,
`history/ge10-per-second-20261022/gremlin/`): `count_ge_10ms` fell from
0.175 a second to 0.016, `count_ge_25ms` 0 throughout. No slow pass in the
ring has `second_edge` with `blit_pump` any more, and none has the pump
stacked with the 10 Hz scopes. JD's board takes it after the drain's cut.
There the rate was ~1.1 an awake second through the night (awake and dark,
the data on), and 0.26 from 14:56 to 18:19 (lit typing on the pack).

**What is left, and the next cut if it matters.** Of the 16 slow passes after
the fix, all exactly 10 ms:
- **11 are the 10 Hz block** (`battery 1-2`, `display_hk 3`): the 1 Hz latch
  run from the 10 Hz call, because the edge's own attempt was gated on a queue
  still painting and `edge_seen` had already moved. Idea, not built: latch the
  second only from the edge site and retry it the next pass, so the clock's
  diff never lands in the 10 Hz block.
- **3 are the 10 Hz block landing on the edge's pass** (`second_edge 3` with
  `battery 1-2`).
- The `battery` scope in both is the 64-bit time math (below, "64-bit time
  math on every main-loop pass").

## The keyboard as an agent pager: an attention key (2026-10-22) -- idea, the most worth doing of the bigger ideas

**The idea.** JD runs several Claude sessions a day, and they wait for him
unnoticed. Claude Code's hooks (a session needs input, or has finished) call
`ak820 notify`. The daemon sends it to the board, where one key turns amber
over the lighting and the text slot says `2 waiting: ak820-pro, webapps`.
Pressing that key brings up the waiting session. On an all-white board one
amber key is hard to miss. A notice that lands while the board sleeps shows
on the next wake.

**Prior art: quill4gen7's `notify` branch** (credited in the README). It has
notifications on the LCD, a Claude Code hook, and answers from the keyboard.
- **The answers:** allow, deny, cancel and options 1-4, sent as unbound
  "application launch" consumer usages, each after a marker naming the
  question.
- **The transports:** Linux only, over the dongle and the cable. The lock
  lights carry data in, and the consumer usages carry answers out, both
  plain HID, so it is portable in principle. Bluetooth is untested.
- **What we have that it lacked:** macOS and Windows hosts for the lock
  lights over BLE, the dongle's raw-HID relay, and the daemon on both.
- Its details are in "Community", quill4gen7, items 1-2 below.

**The paths, by connection:**

| Connection | Host to board | Board to host |
|---|---|---|
| USB | raw HID | raw HID |
| 2.4G | raw HID over the dongle, ~26 ms | the same |
| Bluetooth | the lock-light channel (P3 on the Mac, P0 on Windows) | a key the daemon watches for, as the F19 listener does (Input Monitoring) |

**What it takes, a few days:**
- **Firmware:** a lock-light frame type for notices, and an overlay that
  lights one key over any effect.
- **Daemon:** a `notify` command, and a local way for hooks to reach it.
  macOS raw HID is exclusive, so it goes through the daemon, never the
  Python tools.
- **The hooks.**
- **To check first:** raising the right terminal tab depends on the
  terminal app.
- **Power:** one lit key is small against JD's lighting.

**Open questions:**
- Approve from the keyboard? The screen shows ~30 characters, so a prompt is
  approved from one line (`Bash: git push`). Treat "take me there" as the
  main action, and allow-from-the-keyboard as JD's call, for low-stakes
  prompts at most.
- The same overlay makes cheap follow-ons:
  - a CI light from `gh`;
  - the next meeting on the clock band (needs calendar consent on the Mac);
  - knob modes labelled on the screen.

**Linux:** a fourth daemon backend: hidraw found through sysfs (no
enumeration), the lock lights through sysfs, the clock as elsewhere,
now-playing through MPRIS (a D-Bus dependency, or `playerctl`). quill4gen7
already wrote that Linux side. Asking them is JD's call.

## "Battery low" with the hours left (2026-10-22) -- planned, with the flash after the drain

The time-left estimate is already shown in three places:
- on the battery row once under 10 h (`18% 6h`);
- once on a wake after 2 h or more asleep (`6h use left`);
- at any length on `Fn`+`D`'s camera page.

The low-battery alert itself still says only `Battery low` (`battery.c`, at
3550 mV, ~4.5% and ~2.3 h before the cut at JD's settings). The idea: put
the number in the alert, the moment someone is actually looking for it.
- **The text:** the alert slot holds 12 characters (`CONN_STATUS_MAX`), so
  `Batt low: 2h` or `Batt low <1h`.
- **The fallback:** plain `Battery low` when there is no time left to show:
  the average under an hour old, the level unknown, or the cut latched
  (the same conditions as power.c's `6h use left`).
- **Check first:** the drain in progress is the first to reach the warning
  with the estimate on the board. Read its time left over data near the
  bottom, and set it against when the cut actually comes, before putting
  the number in an alert.
- **When:** build it with `ce229f87c6`'s flash after the drain, through
  codex like any flash.

## Time left on a long sleep's wake, as the battery row, and a QR code to the power page (2026-10-22) -- the first planned, the second parked

**The wake notice, at any level.** Today a wake after 2 h or more asleep
(`RC_LONG_SLEEP_S`, sleep.c) shows `6h use left` in the status band, for
`PARAM_OVERLAY_HOLD_MS` (2 s), and only under 10 h (`power.c`, `left < 600u`).
- **No threshold.** Any cap misreads across settings. At full white the most
  there ever is is ~55-60 h, so a cap at 99 h would show every time. With the
  lights off it would show only from ~2/3 down, which looks broken.
- **The battery row itself, not the status band.** For ~5 s the whole row
  gives way to the time left, as an alternative gauge, then comes back. The
  width is the same in both places: the big face is 10 px a glyph, so the
  full width holds 12 (x 4 to 124, inside the bezel), as the status band
  does (`CONN_STATUS_X`, `CONN_STATUS_MAX`). The row's usual 7 cells are only
  because the icon and the bulb share its line. `143h of use` fits (the most
  is ~150 h, awake and dark), and so does `<1h of use`; `143h use left` (13)
  does not, in either place. The row is the better place because it is the
  gauge, and the status band carries the now-playing title. Hours only: "days" would read as calendar days
  to the next charge at your real use, which the board can't know.
  - ⚠️ The camera page's `4d` from 100 h has the same problem: hours there
    too.
- **The same conditions as today, less the cap:** on battery, the level
  known and not cut, the average an hour old or more. On USB, nothing.
- **Details for the plan:**
  - The wake holds the backlight dark until the row is repainted from the
    corrected level (`display_wake_repainted`). The time view comes after
    that release, from the debited level, or it is that repaint.
  - The big digits are synchronous, ~2.5 ms a glyph (`BATT_TXT_CHUNK`), so
    the view paints and restores a few glyphs a pass, as the row already
    does. Keep each pass under 10 ms.
  - Keep it to the long-sleep wake, the morning and after lunch. Balanced
    wakes several times an hour on a stop-start day, and a view on each
    would become wallpaper.
- **Cost:** a timed view of the row and its restore. It could ride the
  flash after the drain, with the "Battery low" hours (above).

**A QR code to the power page with the board's own settings.**
- The page already takes its settings in the URL
  (`site/power/index.html`, `syncUrl`): `v`, `h`, `s`, `lcd`, `mode`,
  `radio`, `rgb=0`, `lcdon=0`, `fx=other`. The board knows every one of them.
- **Size:** leaving out the page's defaults, the URL is ~45-85 bytes, a QR
  version 4 or 5 (33 or 37 modules). At 3 px a module that's ~100-110 px,
  so it fits the 128 px panel.
- **What it needs:**
  - an encoder in firmware: Nayuki's `qrcodegen` (MIT), a few KB of flash
    and a few hundred bytes of stack;
  - a page to show it, for example a third tap of `Fn`+`D` after the
    camera page, painted in bands as the debug page is, so it never stalls
    typing.
- **Why:** an owner scans it and sees what their settings cost, then moves
  the sliders.
- **Parked:** fun, but not planned. A key that types the same URL with
  QMK's `SEND_STRING` would be even simpler, and is no more planned.

## Power saver's typing cap at 65% instead of 50% (2026-10-21) -- parked, decide after daily use

`SAVER_VAL` (128, 50%) caps the lighting while typing in Power saver. The
idea is 166 (~65%), where white starts to look properly bright in a lit
room. Modelled (white 100%, screen 5, BT): typing draw 153 -> 181 mW (+18%;
the LEDs 42 -> 70 mW), Power saver's days office 10.8 -> 9.4, stop-start
15.5 -> 13.8, light use 21.3 -> 19.2 (10-13% fewer), still ~40% ahead of
Balanced's 6.6 on an office day. ~73% is where brightness per mW of the whole
board peaks (QMK's CIE curve against the model), so 65% is still on the cheap
side. **If done, split the constant:** `SAVER_VAL` is also the low-battery
cap every mode takes at or below 150 permille, which should stay at 128.
Then the simulator, `ladder_check`, the docs' "half brightness", codex, a
flash. Parked because 50% or less is the setting JD uses most; other owners
may want it brighter.

## The model's base reads ~1.5 mW light with nothing lit (2026-10-21) -- noted, no change

The 10-21 sweep of every knob
([`current-map-20261021-1738/`](../history/power-bench-2026-10-15/current-map-20261021-1738/README.md))
has every lit state within 1% of `model_nj`, but the dark floor at 115.6 mW
against 114.0. Measured from that floor, the first lit drive costs ~7 mW
against `P_RGB_A`'s 8.64, so the two errors cancel once an LED is on, which
is where JD's settings live. Moving ~1.5 mW from `P_RGB_A` to `P_BASE` would
fix the dark and screen-only states without moving the lit ones.
- **Why it waits:** the offset has drifted between maps (within 0.03% on
  10-15, +0.9 mW on 10-19, +1.6 today), so a refit should follow a second
  dark-floor measurement on the same firmware, not one run.
- **What it affects:** lights-out and screen-only time-left, by ~1.4%.
- **If done:** battery.c, the simulator's expectations, the docs' figures,
  the page's test gates (dark 1.8%, screen 1.4%), codex, a flash.

## The power page could model Cycle All (2026-10-21) -- offered, not built

On 10-21, Cycle All at 255 and 128 drew 211.0 and 139.5 mW. The model
averaged over every hue at saturation 255 gives 211.1 and 139.2, within
0.2%. So the page's Effect menu could offer Cycle All (and any effect that
moves one hue across every LED) as that average, instead of "not modelled".
Effects that light keys differently (reactive, Alphas/Mods) would still be
out.

## The RGB model's 82 LEDs: the board has 81 (2026-10-21) -- FIXED on `rgb-81-leds`, codex cleared, lands with the next merged flash

Found by codex reviewing [`POWER-CHARTS-PLAN.md`](POWER-CHARTS-PLAN.md),
confirmed against the source. The board has **81** RGB LEDs
(`keyboard.json`'s `rgb_matrix` layout; `config.h:33`), and the drive per
mille the bench records divides by `RGB_MATRIX_LED_COUNT * 3 * 255`
(`battery.c:540`). But `scripts/rgb_fit.py:15` turns that per mille back
into channel sums with `N = 82 * 255`, so the per-colour slopes it fitted,
now `battery.c`'s `P_RGB_R/G/B_NW`, are low by 81/82 (~1.2%). The firmware
then applies them to its real 81-LED sums.

- **Effect:** the board's modelled RGB draw reads ~1.2% low, about 0.7% of
  the total at full white and screen 5 (294.4 mW modelled where the fit
  meant 296.6). The gauge's count runs that much slow on the plateau, so the
  level reads slightly high (the dangerous direction, if small), and the
  time-left slightly long.
- **The fix, on two branches named `rgb-81-leds`:**
  - **Firmware `36330d5ec8`** (on `ak820pro-jdlien` at `9e52400ec9`):
    `battery.c`'s slopes 3681 / 2565 / 2322 nW, from `rgb_fit.py` rerun with
    81 (3681.25 / 2564.53 / 2322.01; the same fit rescaled, `P_RGB_A`
    unchanged). Dev, daily and fpb compile with no warnings.
  - **Host `df8553b` + `7178afb`** (on `main` at `d225f6c`): `rgb_fit.py`'s
    `N`; the simulator's stub, uniform buffer, half load and replay
    conversion, all 81; `docs/power.md` and `docs/battery.md`'s slopes and
    their accuracy claims.
  - **Simulator:** against the fix, every scenario passes; against
    `9e52400ec9` with 81-LED stubs the energy count's scenarios fail
    (`c_rate`'s draw 298.5 mW against 300.65); the pinned baselines are
    unchanged.
- **Codex cleared it** ([`review-codex-rgb-81-leds-2026-10-21.md`](review-codex-rgb-81-leds-2026-10-21.md)):
  the firmware for the next dev flash, after the current test session; the
  host branch only **with the `deps.lock` pin in the same commit**, since
  it fails the default simulator run against today's pin. The order: merge
  and push `36330d5ec8` into `ak820pro-jdlien`, then merge the host branch
  and move `deps.lock` to the merged firmware in one host commit, then run
  `scripts/battery_sim/run.sh` with no override (it reads the firmware
  checkout, so `./setup.sh` first). Its should-fixes, all documentation,
  are in `7178afb`.
- **Effect once flashed:** at full white and screen 5 the modelled draw
  goes 294.4 -> 296.6 mW untethered (+0.74%); the count runs that much
  faster, the low cap's 150 permille arrives ~20 min sooner on an
  uninterrupted full-white count, and the time-left shortens to match.
  RGB-off, sleep, the voltage thresholds and `HC_POWER`'s format are
  unchanged.
- **Left, separate and small:** the per mille is a rounded integer, so
  the fit's drive is approximate (red at value 16 sums 162, `led 2` gives
  123.9). Refitting from the recorded settings through QMK's CIE table
  gives 3681.16 / 2565.98 / 2323.79 nW and an intercept of 7.600 mW
  against 7.713 (codex's finding 3). Worth doing with the power-charts
  sweep, which records the settings, not as a fix of its own. Also left:
  `rgb_fit.py` and the simulator could read the LED count from
  `keyboard.json` instead of carrying it.

## Lock-light frames into a sleeping board cost ~1.6 mA on average (2026-10-21) -- fixed in the daemon (`HOLD_IDLE`), to install on the Mac

Found in the mainline soak's hour asleep
([`../history/mainline-soak-20261020/`](../history/mainline-soak-20261020/README.md)).
The hour passed at 3.01 mA, but its first 19 minutes carried 19 bursts at
~13 mA, each 8-11 s long, every ~63 s. The 10-19 hour, with no lock-light
channel, had none. The bursts were the Mac daemon's now-playing frames, the
title's 60 s refresh (`policy.rs`, `REFRESH`): the cable's data was cut, so
it took BT, a track was playing, and the last frame (01:00:23 by its status
file) ends the last burst (01:00:15-25). After that the Mac's screen locked
and the frames stopped. The board never woke (no strays): the cost is the
module's radio taking the writes.
- **What it costs:** about 10 mA for 10 s a minute, so ~1.6 mA on average
  on top of 3 mA asleep, about +50%, whenever the board sleeps on BT while
  the Mac plays music and is unlocked.
- **Not a regression** in anything shipped: a cost of the channel in daily
  use, beside a Mac playing music. The board sleeps at 20 min in Balanced,
  3 in Power saver and 60 s in Lights out (`power.c`, `ladders[]`).
- **The fix, in the daemon** (`sender.rs`, `HOLD_IDLE`; codex's review
  and its dispositions are in
  [`review-codex-lockchan-hold-2026-10-21.md`](review-codex-lockchan-hold-2026-10-21.md)):
  no text or transport frame once the host's input has been idle 45 s.
  Lights out sleeps at 60 s and a frame lasts up to 12 s, so a frame begun
  before the hold ends before the board can sleep, when the board's keys
  were the last input. It is a heuristic, not a bound: the trackpad can make
  the host's idle time shorter than the board's. The wake guess
  (`IDLE_ARM`, 30 s) is armed by then; on the first input it sends what was
  held, `WAKE_DELAY` (4 s) later, so a media key's change has time to show.
  The clock frames share the hold (`aa2a4be`, Gremlin's session; its own
  60 s gate is gone). The status file's lock-light state reads `held`
  meanwhile. Nothing changes in the firmware: the frames already do not
  count as activity, because the ladder reads
  `last_input_activity_elapsed()` (the matrix and the knob).
- **3 min since 10-29** (`sender.rs`, `HOLD_IDLE`). At 45 s a track that
  changed while nobody touched the Mac showed only at the next touch (seen
  01:43 10-29 on BT with the cable out, the title ~45 s late, and again
  with ~90 s untouched), though Balanced sleeps at 20 min. At 3 min
  Balanced and Always on lose nothing, Power saver (asleep at 3 min) at
  most a frame in flight, and Lights out (asleep at 1 min) ~2 title
  refreshes into a sleeping board each idle stretch: bounded, unlike the
  ~1.6 mA without a hold. The daemon's log now says when a frame is held
  (`lockchan: held, N s without input: the title waits for the next`) and
  when the player's title reached the channel (`lockchan: title from the
  player ...`), so a late title says which.
- **What the user sees:** the board keeps the last title until its 3 min
  expiry after the last refresh, so an idle desk shows it ~4-6 min past
  the last touch (~3-4 min with the 45 s hold), then the clock. A track
  that changes during the hold shows on the next touch; until then the
  board shows the old title or, past the expiry, the clock.
- **A Mac that is asleep or locked sends nothing already.** Asleep, the
  daemon is suspended with everything else. Locked, the channel refuses
  because the user's locks are unknown (R4-1); that is what ended the
  soak's bursts at 01:00:23. The gap was the time between walking away and
  the auto-lock, with music playing.
- **The host's idleness is not the board's.** `HIDIdleTime` counts the
  trackpad and every keyboard. With only the trackpad in use, the host is
  busy while the board sleeps, and the frames keep going. The hold is
  conservative (it never holds a frame from a board that a key just
  touched), not complete.
- **The same signal could keep the board awake while the user is at the
  Mac (an idea, not decided).** The daemon would send a "present" frame,
  a new type the board counts as activity, while the host's input is
  recent. That closes the trackpad gap above: the board would not sleep
  while the user is there. What it costs: awake and dark is ~25.8 mA
  against 3.0 asleep, so ~23 mA (~0.6% of the 4011.6 mAh pack an hour)
  while the user mouses without typing. It would buy the first key's wake:
  that key already reaches the Mac (median 72 ms, max 126 in the soak),
  but the board has to relight. One variant holds off only the sleep step
  and lets the lights dim on the ladder as now. It only matters off USB:
  on the cable, the ladder does not run. Lights out (60 s) is the mode it
  would undercut most; leave it out there.

## Sleep after the LED cut in every mode (2026-10-21) -- considered, left alone; REVISITED 10-28: JD wants it ("A day of typing after the LED cut", top)

The proposal: once the LED cut fires (3400 mV), sleep after 60 s idle in
every mode, Always on included. Today Always on never sleeps, even on the
reserve; the other modes sleep at 3 min below 15% (Lights out at 60 s).
- **What it would buy:** Always on's reserve is ~5 h awake and dark
  (~26 mA; the 10-02 run's 5 h 01 min). Asleep at 3 mA an idle board would
  last days. For the other modes, 60 s instead of 3 min saves ~0.8 mAh an
  idle stretch, maybe 10% more reserve.
- **What it would cost:** a mode called Always on that starts sleeping.
  What the user would see is the screen going dark when idle, and a first
  key that has to wake the board (it is kept).
- **Why left alone:** someone on Always on likely has a cable at hand, and a
  board that dies is back the moment it is plugged in. Lights out already
  sleeps at 60 s, and the "Battery low" notice comes at 10%. Revisit if a
  dead board ever costs something real, such as a long unplugged trip.

## A stray-wake storm in a soak beside lock-light frames (2026-10-20) -- not the frames; cause not known yet

Found in the power-modes flash's BT soak (`845996c39c`,
`history/power-modes-20261020/deep-bt*`): 17 of 20 cycles passed. The
daemon was installed with `--lockchan`, and each cycle cut the cable's data,
so it took BT and sent about 45 frames across the run (one in flight in
cycle 20).
- **Cycle 5 ended its sleep as `strays: 1000`** (`DS_STRAYS_MAX`): the
  sleep loop's WFI returned 1000 times with neither a wake pin's `RIS` bit
  nor a second. The waking tap then reached the Mac in 39 ms (an awake board;
  awake-from-sleep taps took 63-102).
- **Cycles 14 and 19 counted a UART overrun** at the wake: likely incoming
  frames meeting the wake's masked stretches (the PCF's reads).
- **2.4G, no frames:** 9 of 10, no strays, no overruns (the one failure a
  known 25 ms wake paint).

**Tested the same evening** ([`../history/stray-test-20261020/`](../history/stray-test-20261020/README.md)):
80 frames sent into 10 sleeps gave no stray and no overrun; neither did a
10-sleep control. **Frames into a sleeping board are harmless.** The soak's
overruns most likely came from the daemon's clock syncs at each data-on: a
sync writes the PCF. The stray is still unexplained, about one in 50 sleeps.
The diagnostic (`6fda6cd1c2`, op 24 slot 8) now names its source the next
time; the long soak is the place to catch one. The stray cycle's 39 ms
tap-to-Mac latency is no sign of an awake board: 28-54 ms is ordinary while
the BLE link carries traffic.

**First claimed, then corrected the same hour: that each frame ends the
sleep.** One stray wake in about 45 frames says frames do not reliably do
it. So the 60 s refresh does not wake the board every minute. Whether the
traffic matters at all is unproven. The 10-18/19 night (247/247, no
lock-light frames) had no strays.

**What the code already does** (`sleep.c`, `deep_sleep()`), which narrows
it:
- UART2's receiver is switched off (`RXEN`);
- every NVIC line is disabled and cleared but P0-P2 and the RTC;
- SysTick is stopped and its pending bit cleared;
- GPIO `IE` is set only on the wake pins, and the RTC's only on SECIE;
- `take_second()` clears the RTC in the peripheral and the NVIC.

So a stray is a WFI that returns with none of those. The candidates:
- a pending exception the loop does not clear (PendSV: PRIMASK masks it,
  but it can still end a WFI);
- a port IRQ from a pin outside the wake mask;
- spurious returns from noise on a pin.

**Next:**
1. **A dev diagnostic:** at the first stray and at the exit, the full `RIS`
   of P0-P3, `NVIC->ISPR & ISER`, `SCB->ICSR`, and the counted second of the
   first stray (how fast they came).
2. **A deliberate test:** many frames sent during a long bench sleep
   (`ak820 lockchan send --repeat` while the board sleeps, the daemon
   paused), and the same sleep with none, for a rate per frame against a
   control.
3. **Then the fix, through codex,** shaped by what the diagnostic shows.
   Also clear UART2's status at the wake, so bytes lost to a sleep are not
   counted as overruns.

**The sender keeps its cadence** (agreed with Gremlin). Host idle does not
mean the board is asleep: in Always on, or while JD listens without typing,
the board is awake, and without refreshes the title would expire mid-track.
**Only the clock frame (type 4, being designed) is held while input is idle
past 60 s,** with one sent at the wake guess instead.

## The clock flashes for ~3 s at every title frame over the lock lights (2026-10-20) -- FIXED, flashed 20:30 10-20 (`dd8391c28d`); codex's repaint P3 for the next build

Seen by JD on the first supervised play-times run over BT (`6fda6cd1c2`, the
daemon `v0.1.1-715`): the clock showed for a moment on returning to the
board, and for a couple of seconds at a song change.
- **Why:** the board turns playback off on every type 1
  (`lockchan_media_commit`, so a new title never shows the old song's time).
  The type 3 that restores it is a separate frame, about 3 s behind. In
  between, the band falls back to the clock.
- **When:**
  - a song change (new title, then its type 3);
  - the wake guess's resend after the first input past 30 s idle;
  - **every 60 s refresh** (`sender.rs`: type 1 is refreshed and forces a
    type 3), so a minutely flash while JD just listens.
- **Fix 1, small, board-side:** a type 1 whose lines and icon match what is
  shown leaves playback alone. That covers the refresh and the wake resend.
  The sender still follows every type 1 with a type 3, as codex required.
- **Fix 2, optional (JD's call):** a type 1 with a new title and the play
  icon shows 0:00 counting instead of the clock, corrected by the type 3
  within seconds.
- **Built, both, in `dd8391c28d`** (`mac/lockchan-pm`, JD wanted both).
  `lockchan_media_readout` (pure; `scripts/lockchan_media_test.c`, 8
  planted mutants killed) decides from what the slot showed before the
  frame:
  - **keep:** the same lines, with the play icon in both the slot and the
    frame. The readout's own expiry is not renewed.
  - **guess:** other lines replacing a live title, playing. It counts from
    0 at the frame's anchor, so a title frame's own airtime (3-5 s) is
    counted, and lasts 10 s at most. A track resumed part way reads low
    until its type 3.
  - **off:** anything else, as before. That covers no live title (expired,
    or after a deep sleep's wake), a pause, and the same title resumed.
- A pause already hands the band to the clock (type 3 state 0), so it
  needs nothing.
- **JD's check over BT, 20:31-20:54 10-20** (flashed 20:30): no clock
  flashes. At a new track the guess shows no total time, and runs a couple
  of seconds behind Music until its type 3 lands (~3 s after the title).
  Both are the guess as designed:
  - the title frame carries no duration;
  - the time before the title frame's anchor goes uncounted: the change
    reaching the sender (MediaRemote's notice, the loop's 500 ms slice),
    then the warm-up and quiet.

  **Option, not built:** a combined frame (title, position and duration).
  It would show the total at once and need no guess, for about 6 bytes
  more airtime per title. It means a new type, the sender and the board.
  Worth it only if the guess bothers JD in use.

## Slept seconds count the wake's awake seconds twice (2026-10-20) -- small, left

From Gremlin's `rtc.c` work for the wireless clock. `wake_coarse()` adds
`diff` (the PCF's elapsed seconds against the counted ones) to
`rtc_seconds_count`. The seconds awake between the wake and the coarse read
are in both, so each sleep's slept total runs about a second or two long,
and the gauge's slept seconds with it. Left as is: small against a sleep of
minutes to hours. Fix it with `wk_ticks0` (Gremlin's branch has it) if the
gauge's energy count ever needs it.

## The agent in its own repo: a notarized Mac release, a signed Windows build (2026-10-20) -- pending, for later

JD is fine with moving `ak820-agent/` to a separate repository and
releasing it properly from there:
- **macOS:** notarized and stapled;
- **Windows:** properly code-signed.

He has everything this needs. Today Phase 6 stops before Apple
([`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md)):
the Mac `.dmg` is signed but not notarized, and the Windows zips (v0.1.0,
v0.1.1) are unsigned. None of it is started:

1. **The new repo,** with `ak820-agent/`'s history (a subtree split or
   `git filter-repo`) and its release workflow moved over.
   - **Its fixtures come from this repo,** so they move or are vendored:
     `scripts/gen_ascii_fold.py` checks against `hostagent/ak820text.py`,
     and `scripts/clock_oracle.c` is the pinned `ak820ctl.c`.
   - **The vendored MediaRemote helper** (`ak820-agent/helper/`) moves with
     it.
2. **macOS, Phase 6:**
   - `scripts/package-macos.sh`'s `.dmg` notarized and stapled, as the
     plan's signing section lays out (after `../streamdeck-now-playing/build/`);
   - `INSTALL-macos.txt` brought up to date.
3. **Windows: JD already pays for Azure Artifact Signing** (formerly
   Trusted Signing), and
   `../unifi-protect-viewer/.github/workflows/release.yml` is the template:
   - its step `azure/trusted-signing-action@v0.5.0`, with the same endpoint,
     signing account and certificate profile, and the three secrets
     `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` (that
     repo's `RELEASING.md` lists them);
   - here it goes in `.github/workflows/release.yml` between `cargo build
     --release --locked` and the zip, over `ak820-agent/target/release`,
     filtered to `exe`. Signing changes the exes, so the sha256 sums must be
     taken after it, as they already are;
   - skipped when the secrets are absent, as the viewer does, so it can land
     before they are added. Adding them is JD's, in the repo's settings;
   - `scripts/sandbox-6b.ps1`'s clean-install check run on the signed zip.
   - The viewer's macOS job is a pattern for CI notarization too
     (`CSC_LINK`, `APPLE_ID`, an app-specific password), but this agent's
     Mac release can stay local (`package-macos.sh --submit`).
4. **Releases from tags there.** This repo's README points at them, and the
   firmware's artifacts stay released here.
5. **The installer:** `ak820 install` already does the work on both. Windows:
   the zip plus `ak820 install` is enough. Mac: a double-click wrapper in
   the `.dmg`, not a `.pkg` (a `.pkg` installs as root, and the daemon is a
   per-user LaunchAgent).
6. **Updates: notify, then update on request.** A daily check of the
   repo's Releases shown in `ak820 status` and the log (one a user can turn
   off: it contacts GitHub), and an `ak820 update` the user runs. That
   command verifies the download's signature names the same publisher
   (the Developer ID team; the Artifact Signing certificate), checks that
   the board's firmware speaks the new build's protocols, then reinstalls.
   Not silent self-updating: the agent and the firmware move together (type
   4 needed both), and an agent ahead of its firmware breaks the clock or
   the channel quietly.
7. **First, the firmware path for strangers:** the agent does nothing on
   stock firmware. A prebuilt daily build, flashing steps a stranger can
   follow, and an agent that says "this firmware is too old: flash vX".
8. **When:** after the protocol has held still for a couple of weeks. The
   lock-light channel, the radio and the clock changed almost daily in
   October, from two sessions on one repo.
9. **Release defaults:**
   - `--lockchan` only against firmware with the lock-LED handler: it is
     dev-only today, on `mac/lockchan-pm`, not in a daily build;
   - the Mac's `--radio` the same, for the 2.4G dongle's raw HID.

## Power mode icons and names: done (2026-10-19)

The modes are renamed (Always on, Balanced, Power saver, Lights out), and on
battery the bolt's slot shows the mode as a bulb: lit with rays, lit, dimmed,
and unlit and struck through. Same RAM tile and one transfer as the bolt; Fn+B
on the pack showed no pass of 25 ms or more. On the board since 16:16 10-19
(`83d8768c64`), the shapes and colours judged on the panel. Left: nothing,
but the bezel clipping the slot at an angle, noted. The record:
[`POWER-MODE-ICONS-PLAN.md`](POWER-MODE-ICONS-PLAN.md).

## Balanced and Power saver: widen the spread, or merge them? (2026-10-20) -- decided: widen

**Decided 10-20: widened**, with Balanced gentler too:
[`POWER-MODES-REVISION-PLAN.md`](POWER-MODES-REVISION-PLAN.md). Built on
branches and host-tested, not yet flashed. The discussion as it stood:


**Widening it, the option leaning ahead.** Today the two differ only in idle
timings, and both run full brightness while typing, which is what costs.
- **The change:** Power saver caps the LEDs at value 128 while typing too.
  - Under QMK's CIE curve that is about half as bright to the eye, and a
    quarter of the LED power (43 mW against 189).
  - Its idle timings stay as they are.
- **Modelled, in days a charge** (Balanced → Power saver now → Power saver
  half-lit; Lights out for scale):
  - JD's logged use: 13.2 → 13.7 → **21.3** (Lights out 26.8).
  - Stop-start (4 h typing, twenty 15-min breaks): 8.7 → 9.7 → **15.6**
    (21.9).
  - The office worst case (8 h nonstop): 5.9 → 6.0 → **10.7** (14.6).
- **What follows from it:**
  - **Below 15%** every mode takes Power saver's stages (`power_task`), so
    typing would drop to half brightness at low battery in Always on and
    Balanced too. Probably right, given the "Saving power" notice, but a
    choice.
  - **Someone already at value 128 or less** gains nothing, since the cap
    only lowers. A cap relative to the user's own value (half of it) would
    reach them, but saves less for them anyway.
  - **A side benefit:** the ladder acts only on battery and never changes a
    setting, so the cap gives "bright on USB, dimmer on battery" with no
    setting to touch. The battery level is fixed at 128, though, not one the
    user picks.

**A gentler Balanced, proposed alongside.** The intent: it works as if
plugged in unless you are most likely gone, or watching a movie. Today's
1-minute dim is distracting to someone still at the desk.
- **The proposed ladder:** dim at 10 min, LEDs off at 15, screen off at 20,
  deep sleep at 21. The screen-off and the sleep could be one step at 20:
  the backlight has to be off before a sleep anyway, and a dark minute
  awake costs ~2 mWh and buys nothing.
- **Modelled, in days a charge** (today's Balanced → this one):
  - the office day (8 h nonstop, one absence): 5.9 → 5.8;
  - an evening movie (3 h of typing, a 2 h movie): 12.9 → 11.9;
  - JD's logged use: 13.2 → 11.1 (−16%);
  - stop-start (4 h of typing, twenty 15-min breaks): 8.7 → 5.8 (−33%).
    Each break now stays lit for 10 of its 15 minutes; Power saver is the
    mode for that day.
- **The cost is per absence:** about 10 minutes at full lights, ~50 mWh
  (0.3% of the pack) more than today each time.

**The set it makes:**
- **Always on:** behaves as if plugged in, always.
- **Balanced:** as if plugged in, until you are probably gone.
- **Power saver:** half-bright, and quick to dim and sleep.
- **Lights out:** dark.

Each one now differs from its neighbours in how it feels, not only in a few
minutes of timing.

**Merging them** was the first idea. The model says the two are close in practice
([`../docs/power.md`](../docs/power.md), "The power modes at JD's use"):
- **At JD's logged use:** Balanced ~13.2 days, Power saver ~13.7, within
  ~4%. Nearly all idle time is in stretches of hours, and both spend those
  asleep.
- **For someone who stops and starts:** with 4 h of typing and twenty
  15-minute breaks a day, ~8.8 days against ~9.7, about 10%.
  - Power saver saves ~9 mWh a break, from dimming at 30 s instead of 1 min,
    going dark at 2 min instead of 5, and sleeping at 3 instead of 7.

What differs most is the feel: Power saver dims after 30 s.

**The case for merging.** Three modes, each with a clear reason:
- Always on, for people who never want the board dark;
- Balanced;
- Lights out, for the most battery.

Below 15% every mode already takes Power saver's stages, so that behaviour
would stay as the automatic low-battery stage, not a mode.

**No drain is needed to decide.** Both modes use the same measured stage
draws (within 2% of the logger), so the gap is arithmetic, not a model
waiting on data. R5 measures Balanced either way.

**If merged:**
- The mode is persisted (kb datablock byte 6, values 0-3). Keep the enum's
  values, drop Saver from `Fn`+`B`'s cycle, and map a stored Saver to
  Balanced at boot.
- Saver's bulb art goes. The docs' mode table loses a column.

## A battery mutant the simulator no longer catches: the re-seat before RELAX_S (2026-10-20)

`mutants.py` (B2's table) had not run since Phase 2: `tail_fw.c` lacked a stub
for the LED drive Phase 2 added, so every grid catcher failed to link. With
the stub (on the power-modes branch), 17 of B2's 18 are caught. One survives
on `8b06e4dcc4`'s battery.c, unchanged by the power work:
- **The mutant:** the re-seat taken before RELAX_S (`if (!relax_done)
  return;` removed).
- **Its catcher, `m_reseat_0929`,** passes anyway. Phase 2 rewrote it for the
  count: the level is the count, re-seated into the voltage's band, and its
  check is "under 900 and in the band", which an early re-seat also meets.
- **To decide:** whether an early re-seat can now do harm (then the catcher
  needs a sharper check, such as the exact level after RELAX_S), or whether
  the band makes RELAX_S's wait redundant here (then the mutant retires, as
  round 4's "990 cap" did).

Until then `mutants.py` lists it in `KNOWN_SURVIVORS` and prints it on every
run instead of failing.

## ~~The animation's resume clears the whole panel synchronously (43-44 ms)~~ FIXED 2026-10-20 (`ce70c8da41`) (2026-10-19)

Routed through the staged restore with the boot redraw: 20 restores measured
with no pass >= 25 ms, the longest blit 19 ms
([`../history/uart-latency-20261020/`](../history/uart-latency-20261020/README.md)).


`display_redraw_dashboard()` (`display.c`), the path the animation's resume
and the boot take, still does one `lcd_clear_rect()` of the full panel:
43-44 ms on the loop that scans the matrix, over the 25 ms line (codex, the
overrun/Caps implementation review, finding 5). It fires on a timer, so
nobody is usually mid-word, which is why it was left whole when the Fn+D
restore was staged. **To do:** route it through the staged restore, or clear
in bands one per pass, as the restore does.

## UART overruns on the radio link, ~1-2 an hour, likely the PCF's I2C (2026-10-19)

**Mostly fixed 2026-10-20 (`ce70c8da41`, then `b2a07e0d37`;
[`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md),
[`../history/uart-latency-20261020/`](../history/uart-latency-20261020/README.md)).**
The PCF's transfer runs unlocked, with only the row ISR held off, and UART2
sits above USB. Under stage 2's back-to-back load:
- the PCF burst's 199-205 OEs an arm (7.7% of requests lost) fell to 3-6;
- with no burst, priority 0 against 1 gives 2-5 against 9-15.

**What is left:** ~1 OE a minute under full load. The gap monitor sees
almost no interrupt gap of 128 µs or more, so the suspects are masked
stretches of ~90-128 µs, below its first threshold. Lower that threshold,
or add one at 90 µs, to name them.


The module-to-board link loses a byte now and then: **92 overruns in 51.9 h
on flash 2f's drain, 13 in 16.9 h on 2e, 6 in the 2.5 h after the 10-19
icons flash** (HC_LINK `uart_overrun`; no framing or parity errors). It is
the link's base rate, not deep sleep's: the 10-19 soak's 3 in 85 min match
it (`history/deep-cycles-20261019-icons/`). A lost byte costs a module frame
(an ACK, retried; a `5C`; a link state), never a key, which goes the other
way.

**The likely cause, inferred:** the PCF8563's I2C is bit-banged (ChibiOS's
fallback LLD), and `i2cMasterTransmitTimeout` runs the whole transaction
under `osalSysLock()` (`lib/chibios/os/hal/src/hal_i2c.c:203-214`), so UART2
goes unserviced for its length: up to 101 ILRC cycles, ~2.9 ms, against a
16550-style FIFO whose unstated depth, if 16 bytes, holds ~1.4 ms at 115200.
The host's sync writes the PCF every 5 min; two syncs fell in the Caps
windows after the soak, when the module was busy.

**Measured 10-19** ([`OVERRUN-CAPS-PLAN.md`](OVERRUN-CAPS-PLAN.md), [`../history/overrun-ab-20261019/`](../history/overrun-ab-20261019/README.md)): the PCF's long reads do cause overruns under load, but **the receiver holds far less than 16 bytes** (a per-byte lock's 0.3 ms stretches overran ~8x more often), and overruns with nothing in progress continue. The per-byte lock is not the fix; the depth is next.

**To do:** first confirm it (do the overruns line up with PCF transactions:
a cheap per-overrun stamp, or an hour's correlation with the daemon's sync
times). Then a bit-bang without the whole-transaction lock. ⚠️ The open-drain
emulation switches pin modes with read-modify-writes of P0's `MODE`
(`SW_I2C_USE_OPENDRAIN FALSE`, `hal_pal_lld.c:202-227`), and P0 also carries
two key rows (A18, A19) that the row ISR drives, so each mode switch needs a
short lock of its own (or `BSET`/`BCLR`-only writes). A plan and codex first.

## ~~flash.sh syncs the clock beside the daemon: two owners~~ FIXED 2026-10-19 (`9880f47`)

`flash.sh` ends with `ak820ctl clock` while the daemon, if installed, does its
own sync on the board's enumeration: two clock transactions at once, which
`CLAUDE.md` says can pair one's reply with the other's timestamps into a
wrong offset with a plausible round trip. **Seen 10-19:** the 16:16 flash
(another session's), then the daemon's syncs at 16:17:15 (`before -153.2
ms`) and **16:20:16 (`before -2064.5 ms`)**: the board two seconds off,
three minutes after a flash, before any bench run. Not proven to be the
collision (the whole-second slips are on record too, at -1000 ms). **Fix:**
`flash.sh` leaves the clock to the daemon when it is running (`ak820
status`), or pauses it around its own sync.

**Fixed by the Gremlin session, `9880f47`:** `flash.sh` leaves the sync to a
daemon whose status file says `clock=this daemon` and was written in the last
2 minutes (macOS and Windows paths both), and never runs `ak820ctl` on
Windows. Verified on Gremlin: one sync, `sync (enumerated)` at -25.2 ms, 7 s
after the board returned. The Mac's status file carries the same line.

## `raw_edges` undercounts by design; it could be exact (2026-10-19)

The health counter `raw_edges` comes up ~0.5% short of 2 per press (797-799
of 800 on 10-18, 397-399 of 400 per burst on 10-19) while `key_presses`
counts every press. Why: `matrix_scan_custom()` (sn32f2xx.c) counts edges
UNLOCKED, before the locked compare and copy, so an edge the row ISR
publishes between the two is copied (and processed) but never counted; the
next consume sees nothing to count. Keystrokes are not affected: all n
presses register, and a key cannot register again without its release, so
all 2n edges reached QMK. The comment gives the reason as a timer read,
which moved into the ISR since (`input_note_row_scan()`), so the count could
now go inside the lock (a popcount over 6 rows) and be exact, and the tests
could check `edges == 2n` again. Cheap; for a flash that is happening anyway.

## The bench's restore dies with the run (2026-10-18)

The sleep scripts restore relay 2, the data and the board in a `finally`,
and their deadline guard is a thread, so a killed run leaves the keyboard
unplugged (docs/test-bench.md, "Truly unplugged, from software"). It cost
1 h 46 min on the pack on 10-18 and would have stopped the overnight queue
at its first check. The fix: a small watcher process, started first, that
puts the bench back if its parent's PID disappears. Until then, check the
relay and the port after killing a run.

## From the manual's distillation (docs/sn32f299.md, 2026-10-18): five things to check

Found while writing [`docs/sn32f299.md`](../docs/sn32f299.md); none verified
on the board, none urgent:

- **battery.md's "free pins" list is partly wrong.** B6/B7 are the CH582F's
  UART and B10/B11 the external flash's data lines, assigned through the pin
  mux rather than by name; the flash is on SPI1, not on SPI0's MISO. Recheck
  the list (and any doc that says the flash shares SPI0) before using a pin.
- **SysTick's priority may be 0, the highest**, above UART2: ChibiOS's
  default of 8 seems to overflow the M0's 2-bit field. Reading `SCB->SHPR[1]`
  on the board (a dev hook) settles it; see docs/leds.md's priority table.
- **ChibiOS's GPIO interrupt handler can lose edges**: it reads the flags,
  then clears all of them (the SPI0 lost-completion pattern). Unused here
  (`PAL_USE_CALLBACKS` is off); a wake handler must clear only what it read.
- **The package pitch disagrees**: the manual's LQFP80 is 0.4 mm, battery.md
  records the clone as 0.5 mm.
- **The reference repo's README gives P1.2 as both the encoder's A pin and
  the flash's WP#.**

## Community: who is building on this, and when to reach out (2026-10-10)

**TOUCH BASE WITH fpb once the battery work and the power ladder are close to
done** (JD, 10-10). JD has never contacted him. Bring:
- an offer to test his **v2 panel** builds (JD's unit is one; his are
  "untested on real hardware");
- pointers to the battery gauge, the clock sync and the test bench;
- **the battery gauge first.** JD (10-10): it is the biggest win for other
  forks because it is the part they can least reproduce. It took weeks of
  bench trials, a cable with its 5 V routed through a relay, and soon an
  INA228 wired to the pack; adopting it costs a flash. fpb would likely do
  such hardware work himself (his repo traces the module's pads and the
  pinouts), and he already uses our work, but none of his commits is battery
  work. ⚠️ The curve is fitted to JD's pack: one drain on a second unit
  would show how well it carries over before it is offered as general.

**fpb (Fernando Birra), the upstream port**, is using this work:
- he **starred `jdlien/ak820-pro`**;
- `jdlien/qmk_firmware` is a GitHub fork of `fpb/qmk_firmware`, in his fork
  network;
- `jdlien/time-util-ak820pro` forks his `time-util-ak820pro`.

From 09-02 to 09-27 he shipped 38 firmware commits, among them this list's
upstream items:
- 1.1, 1.3 and 3.2;
- **2.1-2.4 in one commit (`21f103fd19`) that nearly repeats the write-up**;
- `LCD_PANEL_V1/V2`, "cross-referenced against a fork that hit and fixed this
  on its own unit".

None of it is battery work (`ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md`, "Upstream
status").

**quill4gen7, the one other fork with original work.** Forked both of JD's repos
on 09-24 and built on `ak820pro-jdlien` (merge base `44e7314e65`): branches
`notify` (ak820-pro), `ak820pro-notify` and `quill-personal` (qmk_firmware),
the personal one with Italian commit messages. Its `docs/notify.md` describes
host notifications on the LCD, with questions answered from the keyboard and
a Claude Code hook. Ideas worth taking:
1. ⭐ **A host-to-board data channel over the air.** **Built to a proven
   transport and parked (10-18):**
   [`LOCK-LED-CHANNEL-PLAN.md`](LOCK-LED-CHANNEL-PLAN.md). The only thing the CH582F
   forwards from host to board is the keyboard-LED bitmap (`5A <leds>`). It
   toggles Num and Scroll Lock (keys this board lacks) as bits: ~10 ms a bit,
   CRC-8, each frame sent twice. Measured 42/42 frames intact at 8-40 ms a bit
   on the 2.4G receiver. Bluetooth takes the same path but is untested. The
   host side is Linux-only: driving one keyboard's LEDs from macOS or Windows
   is "the open question". **For us:** clock sync and now-playing without the
   cable (both are USB raw HID today), at ~100 bit/s.
   **Assessed 10-10, drawbacks included. Worth one experiment, Mac only:**
   - **Host side effects depend on the OS.** On Linux each keyboard's LEDs
     are separate, so the system lock state never moves (proven by
     quill4gen7). On macOS no system-wide Num or Scroll behaviour depends on
     them, so the risk is low, but whether the Mac can set one Bluetooth
     keyboard's LED is unknown. On Windows the lock states are global:
     toggling them hits other keyboards' number pads, Excel's scroll mode and
     anything that watches. Avoid Windows unless per-device indicator calls
     prove clean. A KVM in the path may drop or merge the updates; the CRC
     rejects those frames, so it fails safe.
   - **Board side: a stall hazard here.** The LCD's lock band shows Scroll
     Lock (`display.c` ~1834), and each repaint costs ~25-30 ms. The decoder
     must own Num and Scroll, the band must ignore them, and Caps is never
     touched.
     **Keep SCR instead of removing it (as quill4gen7 did): show it settled.**
     - The host ends every frame by putting the lights back as they were.
       That's one extra report, since any state is one move from any other.
     - The band shows Scroll Lock only once it has held for ~1.5 s, longer
       than any gap inside a frame and than the 500 ms between a frame's two
       copies.
     - A frame then never changes the indicator, a real Scroll Lock (another
       host, an app) still shows, ~1.5 s late, and the band repaints once per
       settled change, not once per bit.
     - If the restore is lost, SCR shows wrongly until the next change. The
       frame's CRC does not cover the restore, so a valid frame can still
       leave it wrong, for good if the host then locks (codex, 10-18:
       `LOCK-LED-CHANNEL-PLAN.md` now keeps Scroll out of the default profile).
     - The likely real use is a key remapped to Scroll Lock and bumped by
       accident ("why is Excel scrolling the sheet?"). The board sent that
       press itself, so a Scroll Lock change arriving within ~250 ms of its
       own `KC_SCRL` can show at once; only changes it did not cause wait to
       settle. (macOS ignores the key; Windows echoes it in milliseconds.)
   - **Power: negligible.** One BLE output report and one `5A` UART frame per
     bit, in bursts of 1-2 s. Only a constant stream would show.
   - **Limits:** ~100 bit/s, one way, each frame sent twice; timing to
     ~0.1 s at best (BLE connection-interval jitter), against ~3 ms on USB.
   - **The module's BLE descriptor (read from the Mac's registry, 10-17):**
     the only host-to-device report is the LED byte (report 2, 1 byte); there
     are no feature reports. Everything else is input: a 6-key keyboard and a
     120-key bitmap, system power keys, a 5-button mouse with wheel and pan,
     consumer keys, an eject bit, and a Surface Dial collection. The LED field
     is **5 bits** (Report Count 5 against usages 1-3), so macOS makes
     controls for Num, Caps and Scroll only, but a raw output report can set
     bits 3-4 too. If the module forwards them in `5A` (the board's guard
     already accepts `d <= 0x1F`), the host owns 4 bits, not 2: 15 moves per
     change, ~3.9 bits, against quill4gen7's 1. Unknown until the firmware can
     show `host_leds`. Probe: `hostagent/ledprobe/`, `scripts/build-led-probe.sh`.
   - **Link 2 PROVEN, 23:22:35-23:23:37 10-17: the Mac sets this keyboard's
     Scroll Lock over Bluetooth.** `ledprobe run`: SCR blinked six times on
     the LCD as sent; all 12 BLE writes returned success. The USB control
     before it (Scroll Lock on for 20 s over the cable) showed nothing, as
     `led_update_kb` says: in BT mode the lock lights come from the radio
     only. Each synchronous `IOHIDDeviceSetReport` 5 s apart took
     **23.7-355.3 ms (median 106)**, against 2.1-2.4 ms over USB.
   - **That was the idle link waking up, not a floor per report.** `ledprobe
     pace 40` at 23:27:48, back to back: the first write 236.1 ms, then
     27.6-47.1 ms (median 29.9), **26.2 writes/s**. ~30 ms looks like two
     connection events per acknowledged write (request, then response, at a
     ~15 ms interval: an inference, not read off the link). So a frame pays
     one wake-up, then ~33 reports/s while each write waits for the last.
     Async writes (`IOHIDDeviceSetReportWithCallback`) might pack more into
     each event; untested. Whether the board received all 40 is unknown
     until the hook below.
   - **Typing removes the wake-up, nothing else.** `pace 200` at 23:46:30
     with JD typing throughout: the first write 25.0 ms (idle: 236.1), then
     median 29.9, p90 31.1, max 44.9 ms, 33.1 writes/s. The steady ~30 ms is
     the link's, busy or not.
   - **The Mac's own Caps Lock updates do not wipe the host's bits.** `hold`
     at 23:48:30: Scroll Lock set over BLE, then Caps on and off from the
     keyboard; SCR stayed lit through both (on the LCD). So a Caps press
     mid-frame does not garble it, at least on macOS.
   - ⚠️ **Locked, the Mac refuses every write.** The display slept at
     23:49:37 and the session locked with it; `night` at 23:51:15 opened the
     BLE device, then all 54 synchronous writes and all 200 async ones came
     back `0xe00002e2` (`kIOReturnNotPermitted`) in under 1 ms: nothing was
     sent. Input Monitoring holds only while the session is unlocked, as the
     F19 listener is blind then (`docs/test-bench.md`). For the daemon: no
     clock or now-playing over the air while the Mac is locked, so resync on
     unlock. Its three tests (repeats, the unnamed bits, async writes) ran
     again unlocked at 08:02 10-18, below.
   - **The stall hazard above is real: one pass >= 25 ms during these
     tests.** The guard's count went from 0 (23:45:51 10-17) to 1 (23:50:52):
     `loop_gap_max_ms` 25, marked `blit`. That window holds `pace 200`
     (Scroll Lock toggled ~33 times a second) and `hold`'s two Caps presses;
     the guard reads every 5 min, so which one is not known, but the burst
     means one band repaint per toggle (an inference). The settled indicator
     above removes it: one repaint per settled change.
     (`history/battery-2026-10-15-drain-2f/README.md`.)
   - **Rule for the encoding (codex, flash 2g): never leave Scroll Lock
     changed for 1.5 s at a stretch inside a frame**, pauses and retries
     included. The settled indicator restarts its clock only on a Scroll Lock
     transition, so a frame that holds the bit flipped that long shows SCR.
   - **Repeats are sent, Mac side.** `night`, 08:02:29 10-18: a write of the
     value already set took as long as a change (18 repeats median 29.7 ms,
     6 changes 30.2; 27.5-42.1). macOS does not drop a repeat; it goes out
     and is acknowledged. Whether the module passes a repeated `5A` on to the
     SN32 is still unknown.
   - **Bits 3-4 are sent too, Mac side.** `0x08`, `0x10` and `0x18` each
     took a full acknowledged write (medians 30.0, 30.1, 29.8 ms; `0x04`
     29.8), so a raw report carries the whole byte. Whether the module
     forwards them is the hook's to say.
   - **Async writes do not beat the link.** 200
     `IOHIDDeviceSetReportWithCallback` writes were all accepted in 11.2 ms
     and all completed successfully, the last at 6226.9 ms: **32.1/s**, the
     same as synchronous (33.1/s). The ceiling is one acknowledged write per
     ~31 ms, not the Mac's call overhead. So the budget is ~32 reports/s:
     with all 5 bits forwarded and repeats counted, 5 bits per report is
     ~160 bit/s, a 30-character title in ~2 s. With 3 bits and change coding
     it is ~2.8 bits per report, ~90 bit/s (both inferences from the Mac-side
     times).
   - **Where it would live: the Rust daemon (`ak820-agent/`).** It already
     owns now-playing and the clock on both OSes, and only one process may
     run clock transactions, so a clock over the air cannot be a separate
     tool. The lights become a second transport for the same messages, used
     when the cable's raw HID is absent; on macOS it is the probe's
     `IOHIDDeviceSetReport`, in the daemon's hand-rolled IOKit style.
   - **Windows is unproven and harder** (from memory, unverified):
     1. a per-keyboard output report (`HidD_SetOutputReport`): Windows holds
        keyboard collections exclusively, so an app's write is probably
        refused;
     2. the keyboard class driver's `IOCTL_KEYBOARD_SET_INDICATORS`, the old
        trick of disk-activity LED tools: sets one keyboard's lights without
        moving the lock state, but untested on Windows 11 and on a BLE
        keyboard, and Windows may reassert the lights on any lock change;
     3. toggling the real lock keys: global, the side effects above. Few
        machines have two keyboards, so the other keyboards' lights are
        cosmetic; the lock *state* is not, for the seconds a frame lasts:
        Scroll Lock moves Excel's arrows and is a hotkey in software KVMs
        (Synergy's cursor lock), Num Lock turns some laptops' letter keys
        into digits, and the toggles are injected keystrokes apps can see.
        Workable as a last resort if frames go only while the user is idle
        (`GetLastInputInfo`) and the state is restored after each.
     A Windows probe first, finding the board without enumerating HID (the
     daemon's finder already does), and only if a Windows PC uses the
     keyboard wirelessly: over the cable, raw HID already does all of it.
   - **The test that answers the rest without JD's eyes (after R3, one `dev`
     flash):** a dev hook that returns the last `5A` byte and a count of `5A`
     frames. The probe then sends all 32 byte values and reads back what
     arrived (which bits pass), sends the same byte twice (are repeats
     forwarded? if so, no change is needed per report), and sweeps the pace
     as quill4gen7 did (40 down to 6 ms) to find where reports merge. Width,
     repeats and speed in one sitting, over the cable, no LCD watching.
   - **The payoff:** clock sync and now-playing over BT. Off USB the clock
     drifts: it was 1.6 s off after 26 min on battery on 10-08.
   - **First step, one evening on the Mac, testing item 2 at the same time:**
     can macOS set this keyboard's Num and Scroll LEDs over BT with no other
     effect, and do the `5A` frames reach the board (it counts them)? And the
     other way: can a Mac app read an unbound usage the board sends over BT?
     Both hinge on the Mac exchanging these reports with one BT keyboard. If
     neither works, drop both. A distraction from the battery work (JD,
     10-10): after Phase 1b, not during it.
2. ⭐ **A board-to-host channel over the air: unbound media keys.** Besides
   keystrokes, the only thing the CH582F carries from board to host is a
   consumer report (`A3`), and it passes unusual usages through. quill4gen7
   answers questions with "AL" (application launch) usages that nothing binds
   on his desktop:
   - allow `0x191` AL Finance, deny `0x1AB` AL Spell Check, cancel `0x1BD`
     AL Info, options 1-4 `0x1B6` `0x1B7` `0x1B8` `0x1BC`;
   - each answer follows a marker naming the question it answers (`0x199`,
     `0x1A7`, `0x1AE`, `0x18E`), at 10 Hz with a release between, so reports
     never merge;
   - the host reads the "Consumer Control" input device (media keys only,
     never typing).

   **Proven on one board, Linux only, over the 2.4G receiver and the cable;
   not over Bluetooth** (his `docs/notify.md`, branch `notify`). **For us:**
   - **the real battery level on the host:** a marker and two digit usages
     every few minutes, under a second of reports each, so negligible power.
     A menu-bar item on the Mac, the Rust daemon on Windows. It cannot change
     System Settings' number ("macOS shows the module's battery percent",
     below);
   - with item 1, a two-way channel over BT: clock sync and now-playing
     without the cable.
   - **Unknowns:** Bluetooth; whether a Mac app can read these usages from a
     BT keyboard (likely behind Input Monitoring); whether macOS or any app
     acts on one, so check each usage before using it.
3. **A raw-HID jump to the bootloader**, compiled in only with
   `-DNOTIFY_RAW_BOOTLOADER`. **For us:** unattended flashing on the bench. Its
   caveat stands: any process that can open raw HID could drop the board into
   a state that looks dead.
4. **An AMBIENT screensaver** (a GIF after N s idle) where the waking key is not
   swallowed: prior art for Phase 2's wake rule.
5. A settings menu on Fn plus the knob, and per-key-category "cyber" lighting.

**Nothing new elsewhere:** `naviltsev/qmk_ak820pro_firmware` is a copy of fpb's
branches (created and last pushed in the same minute); `smsourov` and the older
`ajazz-ak820-pro` forks have no commits of their own.

## The level after a flash: two niceties, low priority (2026-10-11)

**What:** a flash wipes the board's RAM. On battery the level comes straight back
from the pack voltage (1.5% within seconds after the 15:39 flash on 10-11). On
USB power the charger lifts the voltage, and the charging model has no starting
point, so the screen says "Charge" until FULL, or until an unplug plus `RELAX_S`
(30 min).

**JD (10-11):** a nice touch at most. Owners do not flash every 30 minutes, and
only development does.
- **The correct one: hand the level back.** `flash.sh` already dumps the battery
  log seconds before the flash, so the Mac knows the level. A raw-HID "seed"
  command after the flash would let the charging model carry on. It needs a
  firmware command and its bounds, and dev builds only would do.
- **The cosmetic one: a provisional level** for the 30 minutes after an unplug
  the model could not track. Show the voltage's reading at once, marked as
  provisional; it starts a few points high and drifts down as the pack relaxes.
  Flash 2b's item 4, not built.

## macOS shows the module's battery percent, not ours: what could change it (2026-10-10)

**What:** macOS's Bluetooth battery (System Settings) is the CH582F's own
`5C`, a straight line on the pack voltage, served over Bluetooth's battery
service. It reads high most of the way down: 96% against our 66.4% at 03:50
10-10, and, computed from the line and our curve, ~59% at our 10% and ~27% at
the RGB cut. Our firmware runs on the SN32 and reaches the module only over
UART. The right number is already on the LCD; this is about the host. Three
routes:

1. **A module command that sets it: low odds, desk work first** (flash 2b
   item 5, task 8.7). All known traffic runs the other way: the SN32 polls
   (`A6 53`) and the module answers `5C`. Three commands the stock firmware
   sends are unexplained: `A4` (a 2-byte "parameter"), `A8` and `AB`. Do not
   probe them blind. `A7` drops the link and `A9` writes the advertised name
   into the module's storage, so a stored setting changed by mistake could
   not be put back. Find where the stock SN32 image sends them and what feeds
   them. Only a 0-100 value from something battery-like earns one live test.
2. **The level on the host instead, over media keys** (Community, quill4gen7
   item 2): a menu-bar item on the Mac, the daemon on Windows. Never System
   Settings.
3. **Replace the module's firmware: the big hammer, not for now.**
   - **Access is not through the keyboard's USB port.** The module's traced
     link to the SN32 is serial only. fpb's README ("MCU-BT Module wiring")
     traces five pads of a 2×5 header beside the module:
     - the module's pins 10 and 11 (the SN32 link);
     - pins 6 and 7 (`RXD1`/`TXD1`, its UART1);
     - pin 17 (`PB22`).

     On WCH's CH58x chips `PB22` selects the ROM bootloader at power-on, and
     UART1 is a serial ISP port (from memory: verify against the CH583
     datasheet). It looks like the factory's programming header. Using it
     means opening the case.
   - **No way back yet.** Nobody has published the stock module image, and as
     far as we know WCH's ISP bootloader has no read-out command. Erase it and
     the board's wireless is whatever we write.
   - **What we would write:** WCH's SDK has a BLE HID keyboard example with a
     battery service, so the percent is easy. The work is:
     - bonding with three hosts;
     - Bluetooth as solid as stock;
     - the 2.4G dongle, whose protocol is undocumented: likely lost unless
       the dongle is reflashed too.
   - **The reason it might be worth it is power, not the percent.** With stock
     firmware the module's idle draw is out of our hands. If Phase 2's INA228
     measurements show the module is what limits Bluetooth life, owning its
     firmware is the only fix. Decide then.
   - **A first look that changes nothing:**
     - check whether AJAZZ's updater ships a module image, which would be a
       way back;
     - case open: a 3.3 V USB-serial adapter on `RXD1`/`TXD1`, with `PB22`
       held low at power-on, should reach the bootloader. It reports the chip
       ID and its protection settings without erasing, and a normal power-up
       returns it to stock;
     - if read protection is off, the chip's 2-wire debug link might dump the
       stock firmware, making the project reversible. Its pins are not among
       the five traced pads; they may be among the other five.

## USB connects with no 5 V in the wireless positions: a spec deviation we now rely on (2026-10-08)

**What:** in the BT and 2.4G positions the board runs from its battery, and
QMK connects USB at boot regardless of VBUS (`init_usb_driver()`,
`tmk_core/protocol/chibios/usb_main.c:346`, an unconditional
`usbConnectBus`). The board has no VBUS sensing. So on a cable whose 5 V is
cut but whose data lines are not, the board enumerates and works over data
alone, without charging. Found on the Acasis hub, whose port buttons cut VBUS
only: `docs/test-bench.md`, and `history/battery-2026-10-08-partial-charge/`
from 15:41 to 16:10. On cable the board runs from USB, so with no 5 V it is
simply off.

**Strictly a violation:** USB 2.0 §7.1.5.1 requires a self-powered device's
D+ pull-up to be powered from, or switched by, VBUS, so that with no VBUS it
puts no current on the data line. The cost here is ~1 mA through the 1.5 kΩ
pull-up into an unpowered port (a laptop that is off, say). No harm is known.

**Kept deliberately:** it is the test bench's data-only mode. The board can be
read and dumped while it discharges, without charging it.

**If it is ever fixed:** gate `usbConnectBus` on `battery.c`'s supply decision
(EXTERNAL), and disconnect when the supply returns to BATTERY. That costs the
dwell (~0.5 s) at every plug-in, and the bench loses its data-only mode. Offered
upstream as a note (`ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md`, 3.3), not as
a patch.

## ⚠️ Concurrent raw-HID use breaks VIA, and has been all along (2026-09-05)

**Symptom JD sees:** VIA's console fills with `Receiving incorrect
response for command`, and lighting or keymap changes appear not to take.

**Cause.** Windows delivers HID input reports to every open handle, so any
other process talking to the board injects replies into VIA's stream. Measured
with VIA's own log: it asked `CUSTOM_MENU_SET_VALUE` and received
`07 11 01 00 85 60 17 CE` — an `FC_INFO` reply meant for another process — and
also `07 12 04 00`, the **now-playing agent's** `TEXT_PLAYBACK` echo. That agent
writes every ~3 s, so this is a near-certainty during any VIA session.

⚠️ **One injected report desyncs VIA persistently.** After the first bad pair,
every subsequent command received the *previous* command's echo; the stream
does not resynchronise on its own.

⚠️ **The writes still land.** The board executes and echoes each command — VIA
loses the confirmation, not the write. So a change made during a desync has
probably applied even though VIA reported an error, and VIA's displayed state
may then disagree with the board. Read values back (lighting is
`[0x08, 3, 1..4]`) rather than trusting the UI afterwards.

**Workaround now:** stop the host agents before a VIA session — `ak820
status` shows the daemon and the older Python/bash agents, on either OS.

**Fix, proposed for `ak820-agent` phase 4** and recorded in
[AK820-AGENT-PLAN.md](AK820-AGENT-PLAN.md#️-via-coexistence-the-broadcast-is-bidirectional-and-via-is-the-victim):
VIA's traffic is unmistakable in the daemon's drain log — leading id
`0x07`/`0x08`/`0x09` on QMK lighting channel `0x03`, which none of our four
channels can collide with — so the daemon can defer non-urgent work while VIA
is active. A clock sync has 300 s of slack and no reason to spend it stepping
on somebody's UI. That would make the daemon **better** for VIA than the Python
agents it replaces.

## ~~Red LED-row flash during/after RGB adjustment~~ — FIXED 2026-09-01 (6ca0102941)

**Resolution:** the driver's own `EFLD1.state != FLASH_PGM` guard skipped
the row ADVANCE during flash programming but left the current mux row
energized, so the masked program windows froze that row at its live colour
slot for the whole multi-ms write (~18x brightness: red one time, green
another). The FLASH_PGM branch now de-selects every mux pin (ISR-safe GPIO
writes; `sn32f2xx_blank()` is NOT ISR-safe under hardware PWM). Verified by
JD: long hue/brightness sweeps AND 15 host-forced EEPROM writes at 1 Hz --
no pops and no perceptible darkening. The
proposed-fix notes below are historical.

**Symptom (historical):** holding an RGB adjust key (e.g. Fn+Up), a row of red LEDs
flashes briefly. Longstanding, cosmetic.

**Root cause (understood, not guessed):** the settled eeconfig write fires
~0.9 s after the values stop moving (RGB_SETTLE_MS). The EFL program window
masks interrupts for its few-ms duration (efl_ramtext.diff -- deliberate,
see the audits), which freezes the LED row mux mid-cycle: whichever hardware
row was energized in its RED time-slot stays lit at full duty until the
write completes. It is the flash write announcing itself.

**Proposed fix:** blank the LED matrix around the program window --
`sn32f2xx_blank()` exists for exactly this (forces every row/col pin
high-Z; created for the stop-the-ISR case, currently zero callers). Call it
from `backing_store_pre_write_hook()` before the write.
**⚠️ The blocker to resolve first:** blank changes pin MODES to high-Z; if
the row ISR only writes levels/duties and never re-initialises pin modes,
the matrix stays dark after the write. Verify whether `rgb_callback` /
the driver's row advance reconfigures modes per cycle, or add an explicit
re-init after the write. Needs a hardware round-trip -- do not ship blind.

## Row-ISR body: the one lever that lifts scan rate, main loop and field rate together (measured 2026-09-03)

`rgb_callback` re-arms its PWM counter at its END, so its period is (body +
~70 µs) and the body sets everything downstream. Health page 4
(`ak820health.py --isr`): 3,876 ISR/s, body **188 µs mean** (160 µs LED-only,
261 µs with the row scan), **72.8% of the CPU**. Where it goes: 15
`pwmDisableChannel` + 15 `pwmEnableChannel` through the ChibiOS API at ~5 µs
each (osalSysLock/Unlock, driver dispatch, RMW on PWMIOENB/PWMCTRL), 18 row-pin
writes, and a ~85–100 µs row scan whose `select_row`/`unselect_row` go through
`palSetLineMode` (slow on SN32). Direct register writes and a pre-computed
IOENB mask per row would plausibly halve the body; the row scan could drive the
row pin without a mode change. Every 10 µs off the body is ~+4% ISR rate, i.e.
+4% field rate AND +4% per-row sampling AND a proportionally faster main loop.
Not for now: it is a rewrite of a shared core driver on the input path of a
daily driver, and JD's constraint is "any flickering is a non-option".
Measure with `--isr` before and after; the observer effect of the hooks is nil.

## Clock: the sync interval and the firmware's frequency window must agree, and nothing checks it (2026-09-04)

`sync_interval` (host, `ak820-timekeeper.py`) must exceed `WIN_LOCKED` (firmware,
`rtc/rtc.c`) plus a slew's settling: a slew writes the period register ~3 times
and every write restarts the frequency window, so a window longer than the
clean stretch between syncs never completes and the loop freezes. That is
exactly what happened 05:30–11:00 on 2026-09-04: a 120-s "fast" interval
against the then 128-s window froze the loop at a wrong period while the ILRC
sped up ~0.8 % overnight, the residual stayed at +300 ms per sync, and the
large residual is what kept the interval fast — the symptom sustained its own
cause. Both constants were individually reasonable; only their product was
wrong, and it presented as "the clock is 300 ms off", not as two constants
disagreeing. Fixed by hand (interval 180 s, window 32 s), which restores the
convention but not a check.

**Proposed:** expose `WIN_LOCKED` and the slew rate on an `HC_RTC` page and have
the timekeeper read them at startup and refuse or warn if its interval is too
short. That turns an unenforceable cross-language, cross-repo comment into a
runtime check on the only channel that sees both sides; the health version byte
degrades it gracefully on older firmware.

## Scan-rate observation

Instrumented builds read ~230-310 Hz (console + probes overhead); the daily
build reads ~375 Hz. Judge scan-rate bands per flavor.

## rx_malformed baseline

The fault suite's byte soup legitimately raises rx_malformed (by ~5 per
run) for the remainder of that boot. Normal-use expectation is 0 growth.

## On-LCD health readout (BT-mode diagnostics)

Raw-HID replies don't come back in BT mode, and flipping the slider to read
them wired POWER-CYCLES the board (see CLAUDE.md), wiping the counters. The
only way to diagnose a BT session is to show the counters ON THE PANEL --
e.g. a magic-key or Fn-combo that paints tx_sent/timeouts/drops/gap into
the text band for a few seconds. Small, uses display_set_param_status-like
plumbing.

## Keystroke-miss hunt (transport-independent)

JD perceives occasional missed keystrokes on BOTH transports; tonight's BT
bursts measured clean (drops 0, coalescing never engaged). Prime suspect:
wear-leveling sector erases blocking the main loop 50-300 ms, rare and
irregular. Protocol: instrumented build + consolelog.sh + normal typing;
the [stall] line attributes any >=4 ms gap to flash/blit/i2c the moment it
happens. Run when it next "feels bad".

## Slider power asymmetry + host-switch key clearing (2026-09-01, Rachel + JD)

Measured: wired->BT does NOT reboot; BT->wired reboots EVERY time (power-
source switchover; direction-asymmetric ride-through). The boot reset cause
is now readable -- HC_CONN reply byte 7 carries raw RSTST. MEASURED
2026-09-01: the BT->cable flip reset is rstst=0x05 (LVD+SW, no POR) --
an LVD BROWNOUT during the power-source switchover. Question CLOSED.

Held-key-across-host-switch: QMK's handle_host_changed() verifiably never
clears report state (Rachel, from source), but the predicted stuck key did
NOT reproduce on macOS. clear_keyboard() now runs before the route flips
anyway (bt_ui_mode_slider). Upstream issue DEFERRED until the consequence
reproduces on some host (try Windows) -- the source-level observation alone
is thin receipts.

## RTC: reflash erases the persisted trim; SECCNTV write costs ~0.5 s phase (2026-09-01) — trim phase loss FIXED
**Status 2026-09-03:** the SECCNTV phase loss is already gone — every steady-state
period write happens in the tick ISR at the match since the sub-second work
(`docs/clock.md`, "Reload ownership"), so the "apply trims at a second boundary"
idea below is done. What remained was the 5-minute sawtooth, diagnosed and
mitigated host-side the same day (`docs/clock.md`, "The 5-minute sawtooth");
the outstanding firmware item is the loop's tracking bandwidth against ILRC wander.

Measured after the flash marathon: board ~4100-6200 ppm slow, halving per
trim -- RE-CONVERGENCE from the compile-time seed, not a regression. Two
facts to carry: (1) every reflash erases eeconfig incl. the persisted
divider period, so the ~hour-long climb (with 2 s snaps) restarts after
each flash until the first post-10-min trim persists again; (2) per SN32F299
datasheet 12.5.6 (found by the f4 session), writing SECCNTV resets SECCNT,
so each trim discards the elapsed fraction of the current second -- a mean
0.5 s phase loss per trim, later corrected by a snap. Possible improvement:
apply trims only at a second boundary (right after the 1 Hz callback) to
bound the loss to ~0. Also: the ILRC's temperature coefficient means a
fixed RTC_PERIOD_INITIAL can be thousands of ppm off on a different day --
the persisted value is the real seed; the constant is only for fresh EEPROM.

## Host tooling — found during the packaging work (2026-09-01)

### `nowplaying-macos.sh` still hides late Automation failures

`probe_automation()` now reports a TCC denial at startup, which closes the case
that made the agent look like "nothing is playing" forever. But the per-call
getters still send `osascript` stderr to `/dev/null`, so a permission **revoked
while the agent is running** is silent again until the next restart. Low
priority — revocation mid-run is rare — but the fix is cheap: have `state_of()`
distinguish an empty result from an error and log the first one it sees.

### ~~The Windows host path is untested~~ — ran 2026-09-05, superseded 2026-09-06

`hostagent/nowplaying-windows.py` ran as a Scheduled Task from 2026-09-05
23:00 and is the oracle the Rust daemon's media loop was ported from. On
Windows the daemon (`ak820 install`) now replaces it: `install` unregisters
the Python task, and if the PowerShell installer re-registers it the Python
agent exits at once because the daemon holds its mutex. The file stays as
the reference implementation and the rollback.

### `ak820ctl` and the timekeeper both open the raw-HID interface

Not a defect today — the timekeeper shells out per transaction, so it holds the
interface only for the length of one call, and `install-agents.sh` refuses to
install a second clock agent. Neither runs unattended now: the Rust daemon
owns the clock and runs its own transaction (on Windows since 2026-09-06, on
the Mac since 2026-09-16), so the timekeeper is the fallback and `ak820ctl`
runs by hand. Worth remembering before adding any third host tool that
polls: on macOS the interface is exclusive to hidapi (see "macOS raw HID is
EXCLUSIVE" in
[AK820-AGENT-CROSSPLATFORM-PLAN.md](AK820-AGENT-CROSSPLATFORM-PLAN.md)), on
Windows replies reach every open handle, and either failure looks like a
firmware fault rather than a host one.

## Status-band text uses synchronous per-glyph blits — measured, NOT a defect

`draw_locks()`, `draw_battery()` and `draw_conn_number()` paint through
`lcd_draw_flash_text()`, which is synchronous and issues **one LCD operation per
glyph** — a window command, a flash read and a DMA arm each, all of which dwarf
the ~460 bytes of a 10×23 cell. The clock and host-text bands do not do this;
they queue through `display_blit_pump()` at one glyph per main-loop pass.

**Measured 2026-09-03, page closed, over the cable, ~10 Caps Lock presses:**

```
count_ge_25ms        0        blit_gap_max_ms   22
count_ge_10ms       19        key_presses       54
```

**22 ms, and that is under the line that matters.** A stall shorter than the
shortest keypress (25 ms) cannot lose a press — the key is still down when the
loop catches up. So this costs latency, never a keystroke, and it does not need
fixing on those grounds. The prediction that it "has been costing a stall on
every Caps press" was wrong; the measurement is what corrected it.

It exceeded 25 ms in exactly one place: the **Fn+D debug-page exit**, which forced
a full repaint after clearing, so `draw_locks` painted CAPS *and* WIN *and* the
slot text in one pass. ~30 ms, on a deliberate keypress, on a feature added the
same day. **Fixed the same evening (`821431e3e4`)** without touching the queue:
the restore stays on its lock stage painting one component per pass, and
`draw_battery()` stopped clearing its whole 128x22 strip (~7.6 ms) on every
percent tick. Measured after the flash: `count_ge_25ms_nonflash` 0 across
several dismissals and 682 presses, `blit_gap_max_ms` 20 (Caps-on, unchanged).

### If it is ever worth doing

Route the status band's text through `queue_line()` like the clock band already
does. With the exit stall gone this would only trim the 10-20 ms Caps/battery
paints and the sub-10 ms hitches — the queue moves glyphs, not the padlock,
bar, bolt or clears — so the payoff is latency, not keystrokes.

**Weigh the risk honestly.** This is shared dashboard code that runs constantly,
and it was broken twice on 2026-09-03 while chasing this same class of problem —
once badly enough to hang the board and trip the watchdog (`8dc74f7015`,
reverted). With nothing on the board over 25 ms any more, the remaining exposure
is zero keystrokes and a few milliseconds of latency. That is a poor trade for
touching this subsystem without a plan.

Related, larger, same file: `display.c` is ~2,200 lines carrying ten owners
(clock, playback, text band, battery, locks, connection strip, backlight,
splash, glyph queue, shadow diffing, debug page). The queue and its shadow
machinery are a self-contained subsystem with real invariants and would be much
safer behind their own boundary.

### Two comments in this tree document code that does not exist

Both cost real time on 2026-09-03 by being believed:

- **`lcd_draw_flash_text_staged()`** — declared in `lcd_bus.h`, recommended by
  name in the host-text band's comments as the fix for exactly this problem, and
  **has no definition anywhere in the tree**. Using it is a link error.
- **`display_set_param_status()` "draws ~12 blocking DMA blits"** — stale. It
  copies a string and sets `text_dirty`; the band draws through the glyph queue.
  Both sites are now annotated with which part is historical.

A file that confidently documents something untrue is worse than one that
documents nothing.

## Timekeeper: a 13-minute sync gap, and why it still matters (2026-09-05, Windows)

**Symptom.** The Windows timekeeper Scheduled Task logged `timekeeper start` at
15:11:46 with no corresponding stop, and no periodic syncs between 14:58:04 and
that restart -- 13 minutes with a 300 s cadence, so two syncs are missing. The
board free-ran and was **+1042.5 ms** out by the time it resynced, corrected as
a *step* rather than a slew because it exceeded the slew threshold.

There were five starts that day; the other four were deliberate restarts
during development (install, the CREATE_NO_WINDOW fix, the share-mode
experiment).

**Cause: the host bugchecked.** Confirmed from the System event log after the
fact -- an earlier draft of this entry speculated about Claude Code session
teardown, which was wrong.

| | |
|---|---|
| 14:58:04 | last sync before the gap |
| **15:02:56** | unexpected shutdown; **BugCheck `0x0000001A` (MEMORY_MANAGEMENT)**, dump at `C:\WINDOWS\MEMORY.DMP` |
| 15:10:30 | boot |
| 15:11:46 | `timekeeper start` -- 76 s after boot, i.e. at logon |

So the agent did not die; the machine did. The task's at-logon trigger brought
it back correctly and it resynced on its own. Nothing here is an agent defect,
and the restart policy never needed to fire.

**Root cause, from the kernel dump** (analysed in a separate session; bucket
`0x1a_31_nt!MiApplyCompressedFixups`, crash time 15:03:01 by the dump, five
seconds later than the event log's write): a third-party utility launched a WPF
process, and the kernel faulted while re-basing the shared NGEN image
`PresentationFramework.ni.dll` for it -- `NtCreateSection` ->
`MiShareExistingControlArea` -> ... -> `MiApplyCompressedFixups`, decoding its
own compressed relocation stream from paged pool and running off the end of a
4 KB page.

**It is persistent RAM corruption, not a transient read.** Three single-bit
flips in ONE 64-byte cache line of kernel paged pool -- phys `0xe638f808c` bit
3, `0xe638f8094` bit 2, `0xe638f80ac` bit 7 -- inside the relocation stream for
page `0x13ed000`. Decoding the corrupted stream with the kernel's exact
semantics reproduces both the bugcheck and the scribbled target page with zero
bytes of mismatch, and flipping those three bits back matches the on-disk
`.reloc` block exactly. The other 1,106 page streams in the block are intact.
Recommendation to JD was MemTest86 and the ASUS 2402 BIOS.

### ✅ CLEARED 2026-09-06 — the machine is stable, and flashing is allowed again

JD applied the **ASUS 2402 BIOS** plus tuning tweaks, then ran a **clean
MemTest86 pass** and about **five hours of y-cruncher** without error. That is
the clearance this item was waiting for: a memory test is the only thing that
speaks to three bit flips in one cache line, and a five-hour stress run covers
the load-dependent case a short pass would not.

**The do-not-flash rule below is lifted.** It is kept, struck through, because
the *reasoning* in it is not about this machine — it is a permanent property of
the flashing pipeline, and the next person to ask "would a corrupted image be
caught?" deserves the answer.

⚠️ **Keep the hash habit anyway.** Not because the RAM is suspect now, but
because `sonixflasher` verifies against **what it sent**, so nothing downstream
of `build.sh` can catch a corrupted buffer — on any machine, ever. Reproducible
builds make the check free:

    sha256sum ak820pro-builds/out/via-daily-<hash>-*.bin   # must all agree

**Historical status:** during 2026-09-05 the rule stood, and the phase-0
`ak820-agent` work was done entirely without flashing.

**Nothing of ours is in the stack**: no `hidclass`, `HIDUSB`, `kbdhid` or
`mouhid`, no I/O manager at all, no Bluetooth. A concurrent-HID-open experiment
of ours had ended about five minutes earlier and was explicitly checked and
ruled out; it is recorded here only so the coincidence is not rediscovered as a
suspicion later.

### ~~⚠️ Consequence for this repo: do not flash from a machine with bad RAM~~ — lifted 2026-09-06

A bit flip in a firmware image between `build.sh` and the board would not be
caught by anything in the current pipeline. `sonixflasher` reports
`Flash Verification Checksum: OK` by comparing the board against **what it
sent**, so a buffer corrupted before transmission verifies perfectly. The
structural checks in `build.sh` (initial SP, reset vector, USB descriptor) only
sample three places and would miss a flip anywhere else in the 256 KB image.
There is no read-back path to compare against: the stock firmware cannot be
read off the board, and neither can ours.

~~Until the memory is cleared, either do not flash, or verify the artifact by
hash before flashing.~~ **Reproducible builds make that easy and are the reason
this is checkable at all**: two clean builds of the same commit are
byte-identical, measured 2026-09-05.

    sha256sum ak820pro-builds/out/via-daily-<hash>-*.bin   # must all agree

Checked after the fault was identified, with no errors: `git fsck --full
--strict` on this repo (every object SHA verifies, so no flip reached git),
a clean working tree, and all three clean builds of `8608c4f6` still hashing to
`e504bf9dddc91dd1...`.

**Two reasons it is worth keeping.**

- It is a real instance of the whole-second blind spot recorded in
  [AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md):
  `clock-phase.py` recovers sub-second phase only, so it would have reported
  this ~1.04 s error as roughly +42 ms.
- `-Status` reported **Running** throughout, which is exactly the
  "task running can coexist with hours of failed syncs" gap the Codex review
  raised. Evidence for the daemon's observability requirement: *last successful
  sync* has to be a first-class readout, not liveness.

**Kept anyway**, because the two observations above stand on their own: the
instrument cannot see a whole-second error, and `-Status` reports Running while
nothing is being synced. Both are requirements on the Rust daemon regardless of
what caused this particular outage.

**If a gap recurs with no bugcheck:** log on exit as well as entry, and check
the Task Scheduler operational log.

## Host tooling still enumerates HID; only ak820text was fixed (2026-09-05)

**Why it matters.** `hid_enumerate` on Windows opens **every** HID device on the
machine to read its attributes; the VID/PID filter is applied afterwards and
spares none of them. `../jdrgb/docs/ups-wedge-incident.md` records that pattern
twice wedging an APC Back-UPS here.

`hostagent/ak820text.py` was fixed (`61038c6`, `b31acd9`): cached path,
exponential backoff, and a `GetSystemPowerStatus` gate that holds off while AC
is offline and for 60 s after it returns -- the window jdups measured both
wedges in. **The rest was not.** Still enumerating:

| Source | Frequency |
|---|---|
| `ak820-timekeeper.py` `hid_present()` | every `LOOP` (15 s) |
| `ak820-timekeeper.py` `controller_id()` (Windows) | every loop while the cache has no bias |
| `ak820ctl` — **every invocation**, including `clock --bias` | 2-3 per sync |
| `clock-phase.py`, `ak820health.py` | per run |

Roughly 8 enumerations a minute, continuously, plus the per-sync ones.

**Accepted for now** on jdups' own evidence: it saw no trouble in the window we
were running hard, and enumeration on steady mains has never hurt it. But
⚠️ **fix the timekeeper's two before any long capture run for
[AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md) phase 3a**, which
deliberately runs the oracle harder and longer than normal operation.

The Rust agent removes the class entirely, and as of 2026-09-05 this is built
rather than intended: `ak820-agent`'s discovery reads the Configuration
Manager's own records and opens nothing. `ak820 list` prints the ratio it
avoids — **33 HID interfaces present, 5 of them this board's** — and at most
one of those five is ever opened.

**2026-09-06:** the Python now-playing agent is retired on this machine (the
daemon has its job), which removes `ak820text.py`'s share. The timekeeper's
two enumerations per loop went with it at 14:40 the same day (`ak820 install
--clock`, the plan's phase 4b): **nothing on this machine enumerates HID now**
except a hand-run `ak820ctl` or `clock-phase.py`.

## The daemon's verify residual runs +1.7 ms above the C's (2026-09-06)

Measured across the takeover's first ten syncs: `after` minus `before` — the
verify GET's offset against the burst's min-RTT sample — averages +1.7 ms
(max +2.9) in the daemon, +0.4 (max +1.2) in the last 60 Python-driven
`ak820ctl` syncs on the same board. Everything else in the line is inside the
C's spread (`plans/AK820-AGENT-PLAN.md`, "Phase 3b evidence").

**Why it is not urgent:** neither learner uses `after`. The lead learns from
the SET reply's receipt offset and the bias from `before`; `after` feeds the
printed line and the stepped-case `warning:` gate only.

**Why it is worth understanding:** a single sample's offset sitting +2 ms off
the min-RTT sample's means the two transports' write/read asymmetry differs,
and asymmetry is what the midpoint estimate cannot see — so `before` itself
could carry a small constant offset the C's did not. The check is cheap:
capture a burst's five (t0, t1, board) triples with `ak820 clock --raw` (with
the daemon stopped, never beside it) and compare per-sample offsets against
the same capture through `ak820ctl clock --read` on the pinned C.

## nowplaying-macos.sh: the measured cost of the poll loop

**The macOS port is BUILT and replaced this agent on JD's Mac on 2026-09-16
— see [`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md)**
(drafted 2026-09-10, reviewed, dispositioned in 9f5f7d3; the bash agent is
disabled there and stays as the fallback). That plan covers MediaRemote in much
more depth than anything here, including the nuance that it is *not* purely
event-driven — it carries a heartbeat, and the plan explicitly forbids claiming
otherwise; its Phase 5a has the before and after.

This entry recorded the one thing the plan did not yet quantify: **what the
bash agent actually costs.** Verified against the script 2026-09-16:

- `INTERVAL` is 3 s (`nowplaying-macos.sh:40`), and each field is its own
  `osascript`: `running` per app (twice), `player state`, then while playing
  `name`, `artist`, `player position`, `duration` — **6 to 8 `osascript` per
  3-second loop while playing**: 6 with Spotify playing, 7 with Music playing
  and Spotify closed, 8 with Spotify open but stopped and Music playing (it
  falls through, asking both apps for `player state`). Corrected 2026-09-16 by
  the Fable review's finding 9; this said "up to 7".
- Every push runs a **fresh venv Python** (`ak820text.py`), so the exclusive HID
  interface is opened and closed per update. This is also why the `mkdir` lock at
  `$TMPDIR/ak820pro-nowplaying.lock` exists; holding the interface open for the
  process lifetime retires it in favour of a single-instance check.
  ⚠️ **Rejected for the port, 2026-09-16.** On macOS a lifetime open locks
  `ak820health.py`, `ak820keymap.py` and `ak820lighting.py` out for good — they
  work only by retrying between the agents' brief opens. The daemon opens per
  interaction, as the Windows daemon already does; a single-instance guard
  still replaces the lock. See the plan's exclusivity section.

Reported by another session diagnosing this Mac, **not verified here, re-measure
before citing**: ~100–200k short-lived processes/day, each `osascript`
registering with WindowServer and its exit making FocusManager re-evaluate focus,
on a machine at swap 24.6/25.6 GB with `fseventsd` at 20 GB and 58 days uptime.
They did confirm the agent itself does not leak — 1.5 MB after 6.7 days.

Note this is a *cost* argument, and the plan's own "Why" section is explicit that
cost does not justify the port — unification, capability and two named defects
do. Useful as a supporting measurement; not a reason on its own.

**Measured 2026-09-16, macOS 27.0, Music.app playing** with
`scripts/agent_overhead_macos.py`: five 240 s windows, the agent frozen with
`SIGSTOP` in alternate ones.

| | per 240 s window | share of one core |
|---|---|---|
| the agent's own child processes (kernel rusage, exact) | 50.6 / 38.4 / 53.2 CPU-s | **19.7%** |
| `tccd`, `launchservicesd`, `trustd`, `runningboardd`, `launchd`, which move only while it runs | ~20–30 CPU-s | ~8–12% |
| **total** | | **~30%, continuously while playing** |
| for contrast: the sibling's event-driven MediaRemote helper | 0.76 CPU-s in 98 min | ~0.01% |

What this does **not** confirm:
- **The ~100–200k processes/day.** System-wide launches ran 1,068–1,604 a
  minute in every window, paused or not; post-upgrade Spotlight indexing buried
  the agent's share. The script's structure gives about 20 launches per 3 s
  while playing, so ~570k a day. That figure is derived, not measured.
- **The WindowServer/FocusManager churn.** WindowServer used 105–124 CPU-s per
  window whether the agent ran or not; any effect is below the resolution.
  Music.app's cost of answering Apple events was likewise invisible.

JD's complaint that the Mac "seems to suffer a lot of overhead" from
this agent is therefore **confirmed on CPU**. Cost stays a supporting argument
in the plan's terms, but it is now JD's stated priority for the port.

## Whole-second clock slips: four, on both boards, both OSes, both host implementations (found 2026-09-16)

**The signature, identical every time:** a periodic sync reads `before` about
**one second low** (e.g. `-1006.4 ms` where the true offset was a few ms), the
SET lands normally (`after` in single digits), **no bias line follows** (the
learner correctly refuses it), the scheduler comes back **~180 s later instead
of 300**, and that sync is back in single digits. The board was one second
behind for at most one sync interval, and nothing warned.

| when | board / firmware | host | before → after | next sync |
|---|---|---|---|---|
| 2026-09-06 04:41:24 | gremlin, `8608c4f6-dirty` | Windows, Python + `ak820ctl` | −987.2 → +13.2 ms | 180 s, +2.0 |
| 2026-09-06 09:04:42 | gremlin, `8608c4f6-dirty` | Windows, Python + `ak820ctl` | −994.5 → +6.3 ms | 180 s, −12.0 |
| 2026-09-08 19:58:51 | gremlin, `8608c4f6-dirty` | Windows, Rust daemon | −1006.4 → −7.0 ms | 180 s, −4.9 |
| 2026-09-10 15:01:46 | the Mac's, pre-`b89777` | macOS, Python + `ak820ctl` | −999.8 → −0.8 ms | 183 s, −7.1 |

The three gremlin rows were found by the Claude session on gremlin
(`scripts/clock_log_windows.py`, committed in `8cf2c8d`) from logs that live on
gremlin; the Mac row was read here from `~/Library/Logs/ak820pro-timekeeper.log`.
The takeover table's "worst 994.5 ms" (`AK820-AGENT-PLAN.md:274`) is the second
row, and the first was hidden behind it because the table reports only the
worst. A 2026-09-02 `-1131.5 → -131.8` on the Mac is **not** counted: older
firmware, and `after` did not land.

**What this rules out, and what it cannot.**

- **Not the transport, not the OS, not the Rust port.** It appears through
  hidapi and through `CreateFile`, on Windows and macOS.
- ⚠️ **Not ruled out: the shared clock contract.** The Rust daemon reproduces
  `ak820ctl`'s transaction by design, so a contract-level flaw (say, a GET
  sample whose seconds and fraction straddle a second boundary) would appear in
  both, and **oracle parity would carry it faithfully to macOS**. Firmware is
  the other candidate. A torn seconds/fraction read fits the signature — exactly
  one second, a clean verify right after — but that is a hypothesis, not a
  finding.
- ⚠️ **The rate changed, which says there is a condition, not just chance.**
  Four slips in roughly 1,900 periodic syncs up to the evening of 2026-09-10, then **none** in
  about 3,270 since: gremlin's 1,614-sync baseline (09-09 → 09-15) and the
  Mac's 1,657 syncs after 09-10 18:00. At the earlier rate about 6–7 were
  expected. Gremlin's firmware did not change in that time.
- **HID text traffic does not separate them — checked 2026-09-16.** Both
  now-playing agents send traffic even when nothing plays and log none of it:
  a playback request every 3 s and a text keepalive every 30 s
  (`agent.rs:271-300`, `media.rs:63-72`; `nowplaying-windows.py:241`,
  `:255-262`). That steady traffic was running at all three gremlin slips, with
  no media change within ±10 min of any of them. It **also ran through the
  zero-slip baseline**. Slip 3 is the sharpest case: the daemon runs media,
  clock and health **sequentially on one thread** (`agent.rs:267-320`), so its
  own text cannot interleave with its own clock transaction. That rules out
  self-contention, though not a foreign process: discarded foreign reports go
  only to the status file's overwritten `foreign_reports`. Slips 1 and 2 had a
  second process on the HID (`ak820ctl` beside a now-playing agent).
  **Reported by the gremlin session from its logs and the code.**
- *A coincidence, not a finding:* both zero-slip eras begin at a restart.
  gremlin's begins at the 09-09 03:27 Windows Update reboot (unknown whether
  the board lost USB power). The Mac's begins near `b89777`'s commit at 17:57
  on 09-10, and presumably its flash. Against it: gremlin's board had absent
  blips on 09-06 20:08, likely a reset, and slip 3 came after that.

**Why it matters now:** this is the "plausible wrong time" failure mode the
whole clock effort exists to prevent, and neither implementation warns.
Minimum ask, whatever the cause: **warn when `before` jumps by ~1 s against
the previous sync**, so the next one is visible without a log dig.

⚠️ **Do not poll either board to look into it** — a clock read spoils the live
agent's sync. Start from the logs, and from `rtc.c`'s GET reply construction.

## Stalls during the S2 transport soaks (2026-09-16, the Mac's board) — probably ours

After the S2 and Phase 1 soaks, `ak820 health --stalls` read
`count_ge_25ms_nonflash 12`, `count_ge_10ms 1180`, `blit_timeouts 216`, with
`loop_gap_max_mark blit`, at `key_presses 27804` (counters since the board's
last boot; ~15:35 MDT). `plans/current-status.md` had recorded **0** such stalls
across a 13-hour overnight on this board.

**Probable cause, not proven: the soaks.** They drove `TEXT_PLAYBACK` state 0 —
the daemon's idle readout — tens of thousands of times, much of it while the
bash now-playing agent was pushing state 1 for music that was playing. Each flip
hands the band between the clock and the playback readout, which is an LCD
redraw, and the slowest stall is marked `blit`. JD was typing throughout.
The soaks were stopped the moment the counter was seen.

**Read again (2026-09-16):** `count_ge_25ms_nonflash` was **14** at 20:01:50,
when the daemon started, and **15** at 20:46:57. Between 15:35 and 20:01 the only
board traffic was the bash now-playing agent and the Python timekeeper, as
before today; nothing new. **So it rose**, which by the rule below means the
soaks did not cause all of it. The daemon now samples these counters into its
status file every 5 minutes, so the rate is visible without polling.

**How to tell:** re-read the counters after an hour or more of ordinary use with
no bulk traffic. If `count_ge_25ms_nonflash` is still 12, the soaks caused all of
it; if it rose, something else is stalling and `docs/hardware.md`'s
keystroke-loss section applies.

⚠️ **Rule for every future transport soak:** use a command that touches only RAM
on the board — health page 1 (`HC_GET`) — never one that can move the LCD, and
never while JD is typing or a now-playing agent is live. The
`TEXT_PLAYBACK` choice was made to be "production traffic, faster"; faster is
exactly what production traffic is not.

## 64-bit time math on every main-loop pass (2026-10-20)

On the M0 every `TIME_I2MS`/`TIME_I2US` of a run-time value, `timer_read32()`
and `timer_elapsed32()` is a 64-bit software divide: ~100-250 µs under the
row ISR's 73%. The UART-latency build added one per pass and `b2a07e0d37`
took it out: `rtc_fast` fell from 0.207 to 0.061 ms a pass. Others predate it.

**Gremlin's objdump of `ce70c8da41`'s callers of the 64-bit helpers:**
- `sleep_task`
- `energy_tick` (9 multiplies, 7 divides)
- `board_ms_now` (every pass during an acquisition)
- `pcf_machine_step`
- `rtc_task`
- QMK's `usb_idle_timer_elapsed` and `usb_shared_idle_timer_elapsed`
- the housekeeping cadence check (`ak820pro.c`)
- health sampling (`health.c`)

**To do:** count them with HC_ACCT. Move the ones that run every pass to
system-tick compares against constants (`TIME_MS2I(constant)` folds at
compile time). And a fast `timer_read32`, which Gremlin proposed.

**Why it matters:** the slow passes under radio load are 10-12 ms, built by
stacking, so a fraction of a millisecond a pass decides how many cross
10 ms. None reaches 25 ms.

## Request RTT under radio load: what the UART-latency build still adds (2026-10-20)

Stage 2's 1000-stream RTT median read 25.1-25.6 ms on `ce70c8da41` at ~1 h
up, and 27.0-27.5 ms on `b2a07e0d37` within 10 min of a boot (twice, the
daemon swapped between). The fix cannot add time, so uptime was the
first suspect. **But Gremlin's board separates by build, not uptime**
(01:21 10-20, `history/raw81-v2-gremlin-b2a07e0d.json`):

| build | median RTT | ge10 per 1000 |
|---|---|---|
| 0ae4 | 25.0 ms | +11 |
| ce70 | 26.9 ms, flat at 27 min up | +35 to +39 |
| b2a0 | 25.9 ms | +17 to +24 |

So the fix took back about half there. The ~1 ms and ~+10 left against
0ae4 are likely the always-on dev UART hooks. The test is a dev build with only
the UART enter/exit hooks compiled out: a daily build answers no raw81
request, so the 1000-stream cannot run on it. This Mac's board reads b2a0 at ~27 ms at every uptime
(1 to 56 min, and across a reboot), so not uptime. Its one 25 ms ce70
reading came straight after the hour-long A/B and stays unexplained.

