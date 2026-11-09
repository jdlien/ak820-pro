# Backlog: done items

Moved out of [`plans/BACKLOG.md`](../plans/BACKLOG.md) once their work was finished, verbatim, with
their headings, so a pointer to a backlog section by name finds it here. Each was checked as
finished before the move: the firmware fixes they name are in v0.3.1 (`cfe6c2d3a5`), and the host
ones are on `main` or were superseded by the daemon.
Two `###` items are promoted to `##`. "Sleep after the LED cut in every mode" is here because
"A day of typing after the LED cut" in the backlog replaced it.

**Moved 2026-11-09** (25 items):

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

## Scan-rate observation

Instrumented builds read ~230-310 Hz (console + probes overhead); the daily
build reads ~375 Hz. Judge scan-rate bands per flavor.

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

## ~~The Windows host path is untested~~ — ran 2026-09-05, superseded 2026-09-06

`hostagent/nowplaying-windows.py` ran as a Scheduled Task from 2026-09-05
23:00 and is the oracle the Rust daemon's media loop was ported from. On
Windows the daemon (`ak820 install`) now replaces it: `install` unregisters
the Python task, and if the PowerShell installer re-registers it the Python
agent exits at once because the daemon holds its mutex. The file stays as
the reference implementation and the rollback.

## Two comments in this tree document code that does not exist

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

## Whole-second clock slips: four, on both boards, both OSes, both host implementations (found 2026-09-16) -- explained 10-31 (audit F-009): the GET reply tears the seconds from the count

**The cause (10-31, [`AUDIT-2026-10-31.md`](AUDIT-2026-10-31.md), F-009):** `rtc_read_into()` (`hid_protocol.c:1385-1401`) takes the calendar from `rtc_get_time()` and SECCNT from a second, separate `rtc_now()`; a second edge between the two makes the reply read ~1,000 ms low. The host model gives 1 GET in ~1,700-3,300; 4 were seen in ~5,170 syncs. The board's clock was never wrong, only the reading. The fix builds the reply from one `rtc_now()` stamp: built on `audit-fixes` (Batch 1, `scripts/rtc_get_stamp_test`), on white since 15:29 10-31.


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
