# Warren's status: the configuration menu (resume here)

Warren is gremlin's session (the Windows test PC). It owns the configuration
menu's build: [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
(revision 15). Results: [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md) §10-17.
This file is the thread; read it first after a context loss. Updated
2026-10-27 ~10:55.

## Where things stand

- **S0 is complete.** A1-A13 passed on the keyboard on gremlin, with recorded
  exceptions (GREMLIN-RESULTS §10). Firmware branch `gremlin/config-menu`
  (`4b899118`).
  - **P5a MERGED (10-25, 22:50):** `ak820pro-jdlien` fast-forwarded to
    `5ecc9a32`, which carries the effects' speeds (`93e55f78`) under it.
    JD: "I can take the effect speeds on faith, they aren't mission
    critical. I can play with them later." main has deps.lock pinned, the
    flash notes (CLAUDE.md, README, docs/hardware.md: flash.sh keeps the
    profiles and the live settings) and ten core files (the two animations
    with the speed hooks). The keyboard on Buzz is the session on Buzz's to
    flash; its first flash from `30f1e0cf` resets the settings one last time.
  - **MERGED (10-25, 19:05), all fast-forwards:**
    - `ak820pro-jdlien` to `30f1e0cf`;
    - ChibiOS-Contrib's `ak820pro-patches` to `5a1674e905`;
    - main to `7a679e9`, with deps.lock pinned, CLAUDE.md updated and
      AGENTS.md added.

    The session on Buzz flashes the keyboard on Buzz. The daily build on
    gremlin waits for the release. Codex now reads AGENTS.md, so the review
    prompts no longer say "there is no AGENTS.md". What came before:
  - **Not merged yet.** The agreement with the session on Buzz (the Mac; its
    session's bridge is listed as "Relay control and power monitoring
    status") was to wait for the keyboard on Buzz's drain on `b9555ff3e6` to
    reach its RGB cut. **JD released that (10-25, ~18:15):** "I'm not too
    worried about finishing the drain at this point. I might as well just
    start it over again given how far away it still is." The merge now
    waits on JD's polish ("a few bits of polish and we can consider merging
    this into the daily build and the version running on Buzz"). Its order
    stands:
    1. a daily build runs on the keyboard on gremlin (needs JD's Fn+Esc to
       get back to dev);
    2. the session on Buzz flashes the menu onto the keyboard on Buzz;
    3. then the merges into `ak820pro-jdlien`, `deps.lock` and main.

    Don't touch `ak820pro-jdlien`, `deps.lock` or main until JD calls the
    merge, and tell the session on Buzz first.
- **S1 is in progress** on firmware branch `gremlin/s1` (qmk_firmware), on top
  of `gremlin/fill-poll` (the LED fix) on top of `gremlin/config-menu`. The
  chibios-contrib submodule is pinned at branch `gremlin/s1-fifo-ie`
  (`5a1674e905`, the FIFO dispatch respecting IE).
- **The S1 gate PASSES on `a8b98bc0`** (GREMLIN-RESULTS §16): the longest
  pass 13.8 ms, every LED window 0.998-1.000, every completion inside
  1,000 ms. **The failure paths pass, 24 of 24** (§17, devfault).
- **JD's real spin on `a8b98bc0`** (`history/config-menu-s1-20261024/spin-a8b98bc0.json`):
  6 passes over 15 ms, the worst 15.6, nothing dropped, none >= 25. The
  synthetic gate can't see this: op 27's turns bypass `quantum/encoder.c`,
  whose drain waits ENCODER_MAP_KEY_DELAY (1 ms) after each half of every
  detent, captured or not.
- **The encoder fix, `cbcf93b6`** (in every later build): a weak hook,
  `encoder_map_delay_wanted_kb()`, skips `quantum/encoder.c`'s 1 ms waits
  for detents the menu swallowed (`menu/menu_glue.c`). Codex cleared it
  (`review-codex-s1-encoder-2026-10-24.md`); its finding 3 (the knob is
  polled once a pass, so no backlog forms) removed the bounded drain I'd
  added. quantum/encoder.c is now a seventh core file with a local change:
  CLAUDE.md's list needs it at the merge.
- **The mono text, dev `cbb51ac1`** (token
  `0xc10209a3`, gap 240 B). `lcd_blit_mono` through the stream (a halfword
  a pixel), the face `graphics/res/font_small_mono.h` from
  `scripts/gen_mono_font.py`, `menu/menu_text.c` (a cell at a time), and
  the fixture's **F3** (op 27 sub 0 patterns 16-19: lit/half, lit/full,
  inverted/half, inverted/full; a click on rows 0-5 cycles; row 6 F2, row 7
  Diagnostics). Codex: `review-codex-s1-mono-2026-10-24.md` (three rounds).
  GREMLIN-RESULTS §19, §19b:
  - every style keeps every pass under 15 ms (13.1-14.5); a mono piece
    5.1-5.4 ms; a move ~165 ms; failure paths 36 of 36 on devfault;
  - **JD settled: lit text** (plan "Open" 1); **half rows** by efficiency
    ("Open" 2); the face is tiny, kept for now (BACKLOG: a larger face).
- **ON THE KEYBOARD ON GREMLIN NOW: dev `ffa80947`** (token `0x73928d54`,
  gap 232 B): the mono text above plus the dashboard's text slot staged,
  one heavy step a main-loop pass (codex twice,
  `review-codex-s1-textslot-2026-10-24.md`). A track change between two
  lines and one made the gate's 19.6-20.3 ms passes (§19c); now the slot's
  worst is 4.0 ms. **The gate PASSES** (§19d): the longest pass 14.8 ms.
  **JD checked real track changes on the panel: "titles looked clean"**
- **Scripts made today:** `menu_s1_spin.py STOP OUT [--style N]` (arms the
  opener; sub 10 from the menu's opening; the ring for passes over 15 ms),
  `menu_s1_styles.py` (each style's cost, no hands), `menu_s1_dashwatch.py`,
  and `menu_s1_fault.py`'s 12 mono cases.
- ⚠️ **With JD looking at the panel:** put the screen up and LEAVE it
  there (a held session; switch only when asked). An automated demo that
  moves on by itself frustrated JD (10-24).
- **P1a, the real menu, ON THE KEYBOARD ON GREMLIN NOW: dev `5527c898`**
  (token `0x69ff475f`, gap 192 B). Fn+knob opens it in every flavour.
  Design: `CONFIG-MENU-P1-DESIGN.md` draft 3.1 (codex three rounds); code:
  codex two rounds (`review-codex-p1a-code-2026-10-24.md`). Host tests: the
  S0 suite plus `test_menu`, `test_menu_stress`, and a `-DMENU_ENABLE`
  build's `test_menu_enable`. On the board (GREMLIN-RESULTS §20,
  `scripts/menu_p1a_board.py`): every screen right in 9 runs; **timing
  misses C10 marginally** (one pass of 15.1-16.8 ms in about two runs of
  three): a text piece is ~5.6 ms. Since then (all in GREMLIN-RESULTS
  §20-20c and the design doc's "JD's first look" and "JD's decisions"):
  JD's first look ("flawless, as designed"), his tweaks (`22312b44`,
  `62bb64f9`: the scrollbar first, #FF9A9A for Back and Exit, the dot's
  space), the piece's time measured (§20b; JD chose (b), ~16-17 ms
  accepted), the hint pair and the `report_kind` fix (`1e84bf17`, on the
  board from ~20:00, dev token `0xd0254b00`).
- **Icons (10-24 evening):** the icon picker
  (https://claude.ai/artifact/CQcZf9LUWnyvUQyMaCa8PM, made by
  `scripts/gen_icon_gallery.py`); JD's picks built in `925f029b` (dev token
  `0x58ddeb40`): the wrench, ◀ ▶, the circled check, the cursor in x 0-2,
  top-level icons. After JD's look ("looking quite good"): **`541a8cbd` ON
  THE KEYBOARD ON GREMLIN NOW** (dev token `0xbe41a355`, flashed at JD's
  word before codex finished; codex then: no must-fix): the squared check,
  each section's icon on its headings, the cursor in its own grey
  (`MENU_CURSOR` #A5A2A5, its own chunk). The selected row's yellow stays
  (white, #FFF7C6, #FFFF00 tried live). Design doc: "JD's icons".
  (Live tuning, op 27 sub 13 and `menu_tune.py`, retired 10-25: the
  palette is const, its 14 B the settings profiles'.)
- 📌 **PINNED, JD (10-24): a manual review of ALL the menu's text before P1
  is accepted** -- Help's topics (`gen_menu_text.py`, its one amendment "3
  min mid-edit" approved), the labels, values, titles, flashes, the hint,
  About's lines, Reset counters' pages. JD will edit them himself.
  **JD is editing `plans/MENU-TEXT.md` now (uncommitted, his): don't touch
  it.** When he's done: carry his edits into the code in one batch, and
  bring the file's glyphs up to date (◀ ▶, the check, the icons; it still
  shows ‹ > •). One of his lines is cut off: "JD: I wonder if we can".
- **Next:**
  1. **P1b and the bootloader item are ON THE KEYBOARD ON GREMLIN:
     `781d071f`** (dev, token `0x6b34941c`; GREMLIN-RESULTS §20e-g). P1b:
     design draft 3 (codex three rounds), code (codex: the queued-click race
     fixed; the bands fill rows: the longest pass 16.2 ms), the board pass
     PASS (98 steps), the exit gates PASS (`menu_p1b_gates.py`, 31 of 31),
     the owed host tests in. JD's wake-dark-frame fix (`52acdffe99`) merged
     at his ask. The bootloader item: built, codex-reviewed twice, entered
     from the menu on the board and flashed back. The cursor is the thin bar
     (U+1FB70, JD). Help's text comes from `plans/MENU-TEXT.md` (committed,
     JD's), its quoted numbers checked against the firmware.
     **Owed before P1b is accepted:** a power cycle to prove a save survives
     a reboot; C10's gates on the editors (`menu_s1_gate.py`'s 15 ms to 17).
     JD tried Lighting 10-25 ~01:30: "The UI looks excellent", small effect
     quirks "not worth chasing"; he asked for fine steps (done, P2a).
  2. **ON THE KEYBOARD ON GREMLIN NOW: `a9f750ff`** (dev, token
     `0xa3282d1c`, 10-25 02:55; GREMLIN-RESULTS §20h). On top of P1b:
     - **P2a** (`8b4aec16`): Indicators (Lock lights, Charging: 0-100, 1% a
       detent, 8 fast, the preview lights the LEDs; a sigma-delta tick,
       `indicator_levels.h` from `scripts/gen_indicator_levels.py`;
       kb_eeconfig v5 bytes 7-8; flash counters' page 3), the Connection
       stub (the link frozen at open, the shortcuts), eleven top-level rows,
       the editors' fine steps (JD: "micro-adjustments by one
       value/percent": the next percentage a detent, hue 1 unit; fast 8%/12).
     - **P2b** (JD: the Screen "way too coarse"): the backlight 0-100 on the
       same table and sigma-delta; `Fn`+`PgUp`/`PgDn` 1% a press with the
       lights' repeat (JD's ask); dim cap 37, default 42 (the old duties);
       kb_eeconfig v6; the battery log v8 (`bkl100`); `battery_sim` follows
       the scale (`sim_bkl.h`).
     - Board: the menu pass right; the gates 30/30; page 3's attribution;
       the A/B vs `781d071f` (the Hue editor's ~18.5 ms is both builds'
       tonight). **The cost of lit indicators:** at 82% on all three LEDs
       -15% main-loop passes (the menu's longest pass 20.3 ms); at 1% or one
       LED, the old firmware's cost. The backlight's toggles are free (it
       writes every tick); the indicators' per-change writes and their two
       groups' arithmetic are the cost (§20h). **Proposed, not built:** write
       the three pins every tick while any is lit, and skip a group's
       arithmetic at 0 and full duty (the charging light at Off while
       charging steps every tick now). Keeps the sigma-delta; no flicker
       trade-off. (A hybrid with period PWM above ~8 ticks was considered
       and dropped: it trades flicker for CPU.)
     - **JD's power cycle passed (10-25 ~08:30):** "settings gets saved and
       persists after I unplug" (the lock lights). Codex's test gaps are in
       (`fcf4552`). **Still owed:** JD's look at the Screen's 1% steps.
     - **At the merge:** `power_model.py` (parses `bkl_duty`, 24),
       `current_map.py` (sweeps 0-23), `gauge_replay.py` (reads `bkl`): the
       session on Buzz's tools; CLAUDE.md's core-file list and docs.
  3. **P3, Connection (JD, 10-25 ~07:00: "can we do the BT channel
     selection now? ... also pairing"):** firmware `c66e6eaf` on
     `gremlin/s1`, tests `4ef7c41`. Design draft 2 (codex's design review:
     four must-fixes, all taken: the pair never sent mid-bounce or after a
     lost select, a driver fact for the select's outcome, an unsure phase,
     the stand-in cut off from the radio). The top level shows the link;
     off BT, JD's page ("Switch to BT mode to change Bluetooth settings.");
     on BT the slots with the current one's word, and Pair a device with a
     live Pairing page. Host tests pass (`test_p3`); `scripts/ch582_sim/`
     runs `bt_ui.c` and the driver verbatim (`btui.c`, twelve cases, two
     mutants caught). Dev gap 136 B.
     - **Codex's code review** (`review-codex-p3-code-2026-10-25.md`): five
       must-fixes, all taken in `47567935` (a key's hold superseded by menu
       actions; "Already" superseding a pending pair; the select's ACK as
       the boundary, `select_unsent`, **assuming the module ACKs before it
       answers: to check on the wire with the RX tap, slider on BT**; the
       bounce's end resetting the link; the last tries' windows). Six more
       `btui.c` cases, each with a mutant caught (18 cases).
     - **The knob (JD, 10-25 ~08:20):** "the first click in any direction
       doesn't move ... If I reverse direction, the same thing", gone after
       his reboot. Cause: the knob rests where its pins agree (00, 11), so
       the count's parity at rest is fixed at init; pins read mid-change
       there leave it half a detent off for the session. Fix `44d11c28`:
       `ENCODER_REST_PINS_EQUAL` (a local change to
       `drivers/encoder/encoder_quadrature.c`, CLAUDE.md's core-file list at
       the merge) zeroes the count at every rest. `scripts/encoder_sim/`
       runs the decoder verbatim: the rule passes every case; without it, a
       half-detent start shows exactly JD's symptom. **The rests (00/11)
       are inferred, not measured:** op 27 sub 14 byte 17 reads the
       decoder's state; read it right after the flash with the knob at rest
       (0 or 3 confirms; 1 or 2 means reflash without the rule: with 01/10
       rests a reversal's first detent is lost and turns fire mid-detent).
     - **Codex's verify** (`review-codex-p3-verify-2026-10-25.md`): two more
       holes in the ACK boundary, and the boundary itself could restart a
       legitimate attempt. **Backed out** (`a7c19f85`): the driver's rules are
       `a9f750ff`'s; the wrong-slot safety comes from order (never during a
       bounce or select retry; the pair queues behind the target's select);
       the pair is sent even if the link already reads advertising.
     - **Then (10-25, 09:00-13:10), all cleared by codex before each flash
       (`review-codex-p3-verify2..4`, `-pairnow`, `-icons`, `-green`,
       `-white`, `-split5`):** the select's outcome failing closed
       (`ea91b3d0`, `560689ea`); the knob's rests read 00 and 11, as the
       rule assumes; JD's power cycle of the lock lights passed. JD's
       changes on the board: Pair a device pairs the current slot, "On the
       device, add" (`d6483b2b`); the current slot's status icon, coloured
       (`2d8512ae`); the check box green on every page and `Pair device to
       BT 1` (`eb00c2ee`); the top level's icons white, lit or not
       (`1de9df2f`), whose 8 extra pieces cost ~100 ms a top-level repaint
       until a split row's cells 2-9 went to 5-row pieces (`1ff3d405`); the
       selected row's icon #FFF7C6 (`b99d5405`, on the board since 13:36).
       GREMLIN-RESULTS §20i-20j.
     - **Owed (JD):** a slot switch on the real radio (BT 2 and back), a
       pairing on a slot he doesn't mind losing (and a stop), the knob by
       hand; his look at the icons and colours. Possible next: colours for
       the top level's icons (JD, 10-25: "not right away"; green and red
       stay status colours, Connection's would be the rune's blue).
  4. **P4, Battery (JD, 10-25 ~13:35: "The only feature remaining is the
     battery indicator toggle between hours of use and percent"):** firmware
     `d56980c9` on `gremlin/s1`, on the board since 13:53 (GREMLIN-RESULTS
     §20k; codex: no must-fix). A top-level Battery row under Clock, and
     Diagnostics under Bootloader on page two (JD); Percent / Hours of use;
     `kb_eeconfig` byte 9 (version 7); the dashboard's `160h` through
     `graphics/batt_text.c`. **The dev heap gap is 128 B, the floor:** any
     more dev RAM needs savings first (codex's candidate: `draw_battery()`'s
     `last_fw`, `last_txt_x`, `last_txt_w` as `uint8_t`).
     - **Its preview (JD: "preview the percent and hours of use ... and also
       show a warning if it's not going to display yet"):** each choice's row
       shows its readout, and rows 4-6 a note while the hours aren't ready
       (`e0f9a21f`; codex's P3 on the note fixed in `ab03ab38`, on the board
       14:31; its signatures keyed by `batt_key()`, not formatted text, in
       `8ce81e5d`: the text cost 19 ms passes).
     - **Owed (JD):** the hours with the cable out, after an hour awake on
       battery; the preview by eye.
     - **Asked (JD's call):** a faster average for the hours readout (1-2 h,
       the gauge keeping its 12 h), so a lighting change shows within an
       afternoon; it needs the RAM above.
  5. **The Clock options (JD, 10-25), done:** 24h and 12h without seconds
     (`DISPLAY_CLOCK_24H_HM` 4, `_12H_HM` 5), Fn+C over all six, live
     examples on the menu's rows, a tick repainting only the right half
     (`ms_layout_t.first_chunk`, C3 rule 6's exception): `8ce81e5d`, JD by
     eye: "New clock modes look great ... looks flawless". The rows named as
     Fn+C names them, `24h:ss` and `12h:ss` (JD), and an unset clock's
     signatures apart (codex's P2): `22ec0d3d`. One RTC read a second, its
     sample sharing About's 12 B (the scans' `rtc_get_time()`, through
     newlib's `localtime_r`, made 23 ms passes): `c374004b`.
  6. **JD (10-25, ~14:50): "I think this means we're basically done the
     entire menu system ... Let's make a few bits of polish and we can
     consider merging."** P1c and P1d, and JD's text edits, wait on his
     polish list.
  7. **The RGB effects' speeds (JD, 10-25 ~19:00), on the keyboard on
     gremlin since ~19:25:** firmware `93e55f78` on `gremlin/fx-speed` (on
     `30f1e0cf`; not merged).
     - Each curve is geometric in speed: Cycle All 10 min to 10 s; L-R and
       U-D 2 min to 2 s; Jellybean a drop every 2 s to 30 a second.
     - Two weak hooks in quantum/rgb_matrix (four core files touched).
     - Codex: no must-fix (`review-codex-fx-speed-2026-10-25.md`).
     - Owed: JD's feel for the speeds (retune `rgb_speed.c`'s constants),
       and his notes on the other effects. Then the merge, telling the
       session on Buzz first.
  8. **Settings profiles** (`plans/SETTINGS-PROFILES-PLAN.md`, written on
     Buzz; JD's go to build, 10-25 ~20:30, relayed by the session on Buzz:
     "Seems like [Warren] is probably ready to take over at this point").
     - **P5a is on the mainline** (`5ecc9a32`, merged 10-25 22:50; see the
       top). It has the store, HC_PROFILES, the stable effect ids,
       `ak820profiles.py`, the macro backup and flash.sh's profiles step.
       Codex cleared it in two rounds. GREMLIN-RESULTS §20m has the
       board's measure and the round trip.
     - **P5b MERGED (10-26, ~10:05):** `ak820pro-jdlien` fast-forwarded
       to `57d5e900`; main pins it. On the keyboard on gremlin since ~00:48
       10-26, on the keyboard on Buzz since 09:49 (the session on Buzz's
       flash, at JD's word). JD: "everything works really well so far. I'm
       thrilled." The power cycle after a restore passed: "profiles come
       back and load after power cycle." The Profiles row and pages, Load,
       Save and Delete with confirms, the summary, the `*`, the four-frame
       stack, PROF_NXT/PROF_PRV, the active slot deferred through
       kb_eeconfig's settle. Codex: six rounds
       (`review-codex-p5b-code-2026-10-25.md`). GREMLIN-RESULTS §20n has
       the board's passes and the `*`'s cost, found on the board and fixed
       (the profiles' snapshot read every 128 ms; crc8 from a table).
     - **The dev heap gap is still 136 B** after P5b's 6 B (the fourth
       frame 3, the pending active slot 1, the snapshot and its flags 2):
       alignment slack. P5c's Rename needs ~1 B and the name in the
       `pg` union.
     - **P5d, JD's pick (10-26): eight in the existing storage, Save new,
       a preview after a rest.** "Resting like after between 0.3s to a second or a second
       probably makes sense so the board doesn't go crazy as you scroll"
       and "Four is barely enough, 8 feels about right. I think we can go
       ahead and use eight in the existing storage. That sounds like safer
       and there's no need for 32." Order: P5d (eight, Save new), P5c
       (Rename; Save new opens it), then the preview (0.6 s to start, one
       number to tune).
       - **Built: `94072f55`** on `gremlin/p5d` (dev, token `0xd1c65f0b`,
         heap gap 136 B). The block 218 B at 806-1023, magic 0xA2; VIA's
         macros 19 B, sized by DYNAMIC_KEYMAP_MACRO_EEPROM_SIZE (QMK's
         100 B check reads the maximum, which keeps its default);
         HC_PROFILES nine pages in order, sub 7 the geometry; the menu one
         node for the eight slots (pslot the open page's), Profiles = Back,
         the saved slots, "+ Save new" (the first free slot, so a delete's
         gap refills and "Profile n" keeps n = slot + 1; "Full" at eight).
         ak820profiles.py converts four-slot backups.
       - **Codex** (`review-codex-p5d-code-2026-10-26.md`): round 1's P2,
         the list shrinking under the cursor, fixed by prof_list_fit().
         70 mutants, 3 survive (accepted).
       - **On the keyboard on gremlin since 11:04 10-26** (flash.sh
         converted JD's two profiles into the eight). JD: "Testing the +
         New Profile, seems to work great." P5d's board pass: GREMLIN-RESULTS
         §20o (22 ms at Save new's click, trimmed on P5e's branch).
     - **P5e, the preview** (JD: "No Profile 'sneak peek preview' feature
       yet, but that'll be really useful when it lands"; done before
       Rename): `651d23f9` on `gremlin/p5e` (dev, token `0x34f92556`, heap
       gap 136 B). On Profiles, a 600 ms rest on a saved profile shows its
       lighting and LCD level, unsaved, as an ME_PROFILE edit (menu_edit.c
       snapshots and restores both, holds the RGB flush); the target is the
       live settings with the record's fields over them; a click shows it at
       once; Load restores then applies; Save's confirm, Save new, Back's
       and Save new's rows, leaving, a delete, the close and a restore's pop
       show the live settings; an external change holds them until the knob
       moves; the idle close stays 24 s. Codex round 1: three P2s, fixed
       (`review-codex-p5e-code-2026-10-26.md`); round 2 pending. 32 mutants,
       3 survive. To flash with `scratchpad/p5e_flash_passes.sh` (5 quiet
       minutes, flash.sh, then the board passes with JD's profiles stashed
       and put back).
       **On the keyboard on gremlin since 11:51** (GREMLIN-RESULTS §20p:
         both board passes clean). JD asked to try the 0.6 s rest.
     - **P5c, Rename: `13c5e910`** on `gremlin/p5c` (dev, token
       `0x8f2239f1`, heap gap 136 B), the plan's design: a Rename row before
       Delete; WAIT (the matrix idle, the knob masked, and
       `action_tapping_idle()`, a new additive accessor in
       quantum/action_tapping.c: an eleventh core file for CLAUDE.md's list
       at the merge), CAPTURE (every key but the knob's swallowed in
       menu_pre_process(), read by the default layer's keycode, Shift from
       the matrix), DRAIN; the one-shots cleared at CAPTURE, an armed
       one-shot layer turned off; Fn read as up for the knob; typing
       restarts the idle timer (Rename takes the 180 s backstop); Save new
       doesn't open it (Decided 4). Codex: three rounds
       (`review-codex-p5c-code-2026-10-26.md`). 28 mutants, 1 survives.
       On the keyboard on gremlin since 12:38 (GREMLIN-RESULTS §20q). JD:
       "Typing to save a name seems to work perfectly ... Perfect."
     - **P5d, P5e and P5c MERGED (10-26, ~13:05):** `ak820pro-jdlien` at
       `13c5e910`, main pins it. The session on Buzz told; its first flash
       converts the keyboard on Buzz's four profiles into the eight.
     - **The profile page's polish MERGED (10-26, ~15:45):**
       `ak820pro-jdlien` at `553108e5`, main pins it, on the keyboard on
       gremlin since ~15:14: the action icons (the circled arrows for Load
       and Save, the pencil, Octicons' trashcan), a grey rule over the
       summary, the bulb on the LEDs' line, the preview at 300 ms
       (GREMLIN-RESULTS §20r-20t). JD: "I'm happy with it now." He runs it
       for a while. Rename's cursor editing: skipped (JD: unless the
       keyboard becomes a note-taking tool).
     - **The Next and Previous keys: done** (10-26; JD bound Fn+A and Fn+S
       in VIA: "all works great!").
     - **The idle close at 60 s MERGED (10-26, ~17:50):** `ak820pro-jdlien`
       at `1f3c79e9`, main pins it, on the keyboard on gremlin since ~17:30
       (GREMLIN-RESULTS §20u; codex: no blocker). JD: "Let's increase to
       60s." Editors, Pairing and Rename keep the 3-minute backstop.
     - **MENU-TEXT.md corrected (10-26, JD: "You can make the
       corrections"):** the glyphs (`◀`, `▶`, the check box), the top
       level's thirteen rows, the Clock's option names, Battery as built, a
       Profiles section with every profile page's words, the title flashes,
       "60 seconds idle". JD's own text untouched.
     - **Owed (JD):** a read of MENU-TEXT.md's new Profiles section, for
       wording. Before a release for other owners: eight profiles leave VIA
       19 B of macros (a four-profile build would keep 127 B); Rename types
       as US QWERTY reads the keys (JD, 10-26: noted, no fix asked; a
       layout option or a host-side rename if an owner needs one).
     - **The daily of the mainline builds clean (10-26, 18:45):**
       `via-daily-1f3c79e9-20261026-184552` (token `0xb26693c6`), every
       release check passed, heap gap 2256 B (the dev's 136); the menu is in
       it, the raw-HID jump and the overrun diagnostics are not. Not flashed:
       JD keeps the dev build on the keyboard on gremlin for now. Nothing
       left unmerged: the outer repo's one other branch,
       `power-modes-revision`, is the pre-rebase copy of commits main has.
     - **The keyboard on Buzz runs `1f3c79e904` since 20:29 10-26** (dev,
       token `0x60a8fe4b`, flashed mid-drain on battery with every setting
       kept; `553108e5f2` from 16:01), from Buzz's session. JD there: "This
       config menu is just awesome." The one thing raised: the menu's text
       is small. Noted only; no change asked.
     - **Both, the battery readout's third option (10-26, ~22:45): on the
       keyboard on gremlin, NOT merged** (`gremlin/batt-both` at
       `0ada282c`, GREMLIN-RESULTS §20v; codex: no blocker, two findings
       fixed). JD: "an option to show hours & percent". `85% 160h`; 8 cells
       close the space to 4 px; `100%` alone where it would be 9. The
       readout is set to Both there. **Owed (JD):** the dashboard's text,
       after an hour awake on battery (the slider to BT or 2.4G first: it
       was on the cable's position); then merge. **Next after it (JD):** an
       experimental fork with a bigger menu font ("might be interesting to
       see you do an experimental fork to try").
       JD's call on the Both order (hours first or percent first) is open:
       kept percent first, offered the flip.
     - **The Win/Mac switch loads each side's last profile (10-27, ~09:40):
       on the keyboard on gremlin, NOT merged** (`gremlin/os-profiles` at
       `bf29a081`, branched from `gremlin/batt-both`, so merge Both first;
       GREMLIN-RESULTS §20w; codex: no blocker). JD: "implement the profile
       association with win/Mac switch", always on (BACKLOG.md's entry of
       10-27 has the design, and why whole keymaps in profiles don't fit).
       The active byte a slot a side (magic 0xA3); `ak820profiles.py`
       converts. Set up there for JD's flip: Windows RGB Cycle, the Mac
       Cyan-Magenta.
     - **Then, the same branch (10-27, ~10:55): each side kept as left, JD's
       defaults, Reset settings** (`33d6d4ae`, GREMLIN-RESULTS §20x; codex:
       four P2s fixed and closed). Seven profiles, the eighth record the
       side not in use as it was left (magic 0xA4); the defaults in one
       place (warm white Solid 75%, screen 60, both lights 5, 24h:ss,
       Percent, Balanced); Reset settings under Bootloader (↺). On the
       keyboard on gremlin since ~10:40, every board check passed.
     - **Then the Power page's bulbs** (`a5d9171c`, JD: "use the power mode
       icons that we show on the battery row, right aligned"; the mock-up
       `history/config-menu-p3-20261025/power-bulbs-mock.png`, as built
       `power-bulbs-as-built.png`): codex's review running at ~10:55.
       **Owed (JD), all three at once:** a real flip, to the Mac's side and
       back (Cyan-Magenta, then RGB Cycle as left); a look at the Power
       page; Reset settings only if he wants his settings reset. Then merge
       `gremlin/batt-both` and `gremlin/os-profiles`, pin deps.lock, and
       CLAUDE.md's Fn line ("up to eight" profiles: seven; Reset settings).
     - **Was next: icons for the slot page's actions** (JD: "Let's see if we
       can pick some icons for the Load/Save/Rename/Delete"). Shortlisted
       from Cozette (`scratchpad/icon_cands2.py`): Load the restore arrow
       (U+F006F) or the inbox tray (U+1F4E5); Save the floppy (U+1F4BE),
       its outline (U+1F5AB) or the outbox tray (U+1F4E4); Rename the
       pencil (U+F040) or the tag (U+F02B); Delete the trash (U+F1F8) or
       Octicons' trashcan (U+F48E). The floppies and trays are 11 px tall,
       the pencil 6, the trash 9. Waiting on JD's pick.
     - **JD's ideas (10-26), as first answered.** "I think maybe
       just a 'Save New' makes more sense than finite grayed out unused
       slots. We'd have to have a limit after some amount, but probably
       way more than 4", and a preview of a profile from the list.
       Warren's answer:
       - **The store:** the EEPROM can't grow (wear-levelling keeps all
         1 KB of it in RAM; the heap has 8 B over its floor). Eight fit in
         it by taking 108 B of VIA's macro buffer (127 B to 19; JD uses
         none). For more, the records move to two 1 KB pages of the MCU's
         own flash (the dev build ends at 209 KB of 253; a page erase is
         1-2 ms), A/B so a power loss mid-save keeps the rest, capped at
         32, read in place with no RAM copy; the active byte stays in the
         EEPROM, so the keys never erase a page; the macros get their
         108 B back. A new flash writer, through the EFL driver the
         wear-levelling uses, and a build check that the image ends below
         the pages.
       - **The list:** only the saved profiles, "Save new" last (greyed,
         "Full", at the cap), new ones at the end and a delete closing the
         gap, since each write rewrites the page. "Save new" opens P5c's
         Rename with "Profile n" filled in.
       - **The preview:** the summary under the list fits only four
         (Back, four rows and three lines are the screen), so it stays on
         the profile's page. Instead the lighting and the screen level of
         the profile the cursor rests on, after ~0.3 s (an effect's
         animation restarts at each change); RAM only; Back, the session's
         timeout or an Fn lighting key restore; a click keeps it on the
         profile's page and Load commits it; Save's confirm shows the live
         lighting, what it would save.
       - **Order:** the store, the list with Rename (P5c), the preview,
         each through codex and a board pass before JD sees it.
     - **Owed:** the keys bound in VIA and pressed.
- **The gate procedure (each run):**
  1. flash the build (`./flash.sh` in MSYS2);
  2. `venv-win/Scripts/python.exe scripts/devhook.py reset < /dev/null`;
  3. `venv-win/Scripts/python.exe scripts/menu_s1_gate.py --out
     history/config-menu-s1-20261024/gate-<build>.json < /dev/null`;
  4. record the result in GREMLIN-RESULTS.

## What S1 has done so far (all codex-reviewed before each flash)

- **The LED flicker fix:** colour fills held off the RGB row ISR (-18%).
  Bulk SPI0 sends are polled with SPI0's IE cleared (`spi0_poll_send`); since
  revision 14 their window is polled too (`lcd_window_polled`), and since
  revision 15 the DMA arm's. The row ISR now keeps ~99.4-100% of its rate
  during menu activity. JD by eye: "no flicker", "feels responsive, not
  instant".
- **`MB_PASS_BYTES` (512):** a slot's op is sent in pieces, one a pass.
  - `end_op()` counts an op and latches a reached stop together. That closed
    a real S0 race: navigation could cancel a just-reached stop.
  - A failed piece ends its op.
  - Revision 13: a PARTIAL slot resumes while its own signature is
    unchanged. Revision 8's "same generation" starved spins. An op cut by a
    retarget is counted when it ends, untimed, and a glyph in flight is kept.
- **C10's instrumentation:** op 27 sub 10, read by `scripts/menu_s1_gate.py`:
  - **timing:** piece, op and repaint latency, the longest pass in an armed
    interval, the count over 15 ms, the clear bands;
  - **targets:** `tgen`, settled, superseded, committed;
  - **the debug page:** its generations, `dbg_sec`, the RTC's second, and
    `debug_done` (sub 5 byte 31);
  - **the session:** a boot-cleared token and the health-reset generation,
    with byte 31 flagging an aliased interval;
  - **where it lives:** `menu/menu_meas.c` holds the extended tick and the
    pass timing, which `menu_pass_begin()` takes first in the pass. DMA ends
    are timed at CS release (`lcd_blit_end_tick16`).
- **Dashboard timing fixes found by the gate (affect every build):**
  - after the restore's clear, the text lines' and clock's shadows are marked
    blank (`shadow_mark_all_blank`); the text slot stage went from 16 ms to
    0.5;
  - the restore's battery outline is one edge a pass, and the connection row
    and clock come in two passes;
  - the debug page composes only the page showing;
  - the pump yields in a pass where the debug page composed, and the 10 Hz
    composition defers in a pass where the pump painted.
- **The entry check and hardening:**
  - `spi0_poll_send` refuses unless DMA is idle, `SPID0` is READY, BUSY is
    clear and RX is empty;
  - HC_POLLFAULT (0x75, devfault) takes `n, mode, skip` to fault a window
    send or the payload; `scripts/menu_s1_fault.py` runs the 24 cases.
- **Findings recorded for later:**
  - the Fn timing miss inside a tap-hold's tapping term, settled as
    documented (plan "Open" 5);
  - the "100%" ghost on gremlin's LCD (BACKLOG);
  - the housekeeping text slot can reach 16 ms on a track change: a
    dashboard path, not yet staged.

## Working rules (from JD and the handoff)

- **Codex before every flash.** `codex exec -m gpt-6-astra -c
  model_reasoning_effort=xhigh -s read-only -C <repo> -o <out> "$(cat
  prompt)" < /dev/null`. Save each review verbatim with dispositions as
  `plans/review-codex-*.md`, and keep its prompt as `plans/review-prompt-*`.
- **Flash only the keyboard on gremlin.** JD has given a standing go. Never
  flash or touch the keyboard on Buzz. Name the keyboards "the keyboard on
  gremlin" and "the keyboard on Buzz": both are JD's.
- **One hands-on action per message to JD.**
- **Never enumerate HID.** Never use `python -` (stdin); write scripts to
  files and run them with `< /dev/null`. Use the Edit tool for C with `\n`:
  heredocs collapse the backslashes.
- **Builds:** MSYS2 for build and flash
  (`/c/msys64/msys2_shell.cmd -mingw64 -defterm -no-start -here -c "..."`).
  Git Bash for git. Never `find /`.
- **Host tests:** `gcc -std=c11 -Wall -Wextra -DMENU_HOST_TEST -I $D/menu
  scripts/menu_s0_test.c $D/menu/{panel_owner,menu_input,menu_slots,
  menu_fixture,menu_ops}.c`, with mingw64's gcc first on `PATH`.
- **Scrub family words before pushing.** Push freely; tags and releases need
  JD.
