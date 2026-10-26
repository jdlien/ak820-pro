# Codex on P2a's design (Indicators, the Connection stub), 10-25 night

Prompt: `plans/review-prompt-p2a-design.txt`. The section: `plans/CONFIG-MENU-P1-DESIGN.md`,
"P2a". Codex read the tree mid-change (the code was being written beside it); its line
references are to `781d071f`.

## Dispositions

1. **The restart rule for per-pin writes (must change):** taken, and it was a real bug
   in the code already written: with `ch = out ^ 0xFF`, a restart with Caps full on
   skipped Caps and left it dark. The tick's decision is now pure, in the generated
   `indicator_levels.h`: `ind_tick_out()` (the groups, the force, the sigma-delta) and
   `ind_pins_to_write()` (all three after a restart, `IND_OUT_UNKNOWN`), which the ISR
   calls inline. The host tests run every output against every last state, and a
   restart with Caps at 100% and a retained accumulator (`test_ind_levels`).
2. **The timing gate (must change):** taken. The old firmware's baseline was measured
   before the flash (`scripts/ind_timing.py`, `history/config-menu-p2a-20261025/`):
   idle, and Caps lit from the host at level 1. The new firmware is measured at idle,
   Caps at 1% from the host (matched), and all three LEDs forced at 1%, 82%, 83% and
   100% through a new dev-only bench op (op 27 sub 15: the force bits and both levels,
   live; an external writer of the indicators, so it cancels an open indicator edit
   first). Each run: the main loop's pass rate, the row ISR's rate and CPU share, the
   passes over 10 and 25 ms; and the menu's board pass with all three at 82%, against
   C10's 17 ms.
3. **The P2 proof (must change):** taken:
   - the settings block's production code (`kb_eeconfig.c`, verbatim, in the diag
     simulator against stubs): stored bytes 0, 1, 2, 101, 102 and 255 for each field
     alone; a zero-filled block (QMK's answer to an old version); saved Off, 1% and
     100%; the deferred, coalesced write; an unchanged save writing nothing;
   - the flash counters: pages 0-2 byte-identical to `781d071f`'s `flash_stats.c`
     under the same old-fields workload (a one-off comparison, recorded); page 3's
     attribution for each field alone, both together counting as mixed, an unchanged
     write, and the reset;
   - `ak820health.py` reads page 3 through a new optional-page transaction that takes
     the firmware's unhandled reply to that command and page as "not answered" (shown
     "-"), and a host test of it; the simulator's stubs go to nine bytes and stop
     faking page 3.
   - Persistence across a reboot: JD's power cycle, as for P1b.
- **`ind_force` volatile:** it is.
- **Freeze page 1's loop at six:** done (`KBF_PAGE1`).
- **The curve's wording:** taken: "keeps today's tested minimum brightness", not
  "the dimmest that doesn't flicker"; "perceptually spaced", not calibrated.
- **Group accumulators:** two (4 B), as built; the design's RAM line corrected.
- **The force-lifecycle routes:** the host tests cover Save, Cancel, the hold, the
  opener's close mid-edit, the backstop and the bench writer; the Diagnostics handoff
  and the wake release reach the same rollback (`panel_owner.c`), already tested for
  P1b's edits.
- **The board scripts' row constants** (`menu_p1a_board.py`, its Power-to-Clock step;
  `menu_boot_board.py`'s row 7): taken.
- **`docs/leds.md`'s UART priority (1, where `mcuconf.h` says 0):** noted for the docs
  pass; not this change.

## The review, verbatim

**Yes. I would amend three parts before writing code:** the pin-write restart rule, the ISR performance test, and the persistence/compatibility proof. The overall menu structure, indicator curve, and edit transaction are workable.

This review uses firmware **`781d071f`** and the P2a proposal as initially read. The working tree changed during the review; firmware line references below refer to that baseline. I made no changes and read only inside the repository.

1. **Fix the restart rule for per-pin writes.**

   The proposal says to write only changed pins, but today’s sentinel assumes that any difference causes **all three** pins to be written: [indicators.c:98](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:98). Restart restores that sentinel at [indicators.c:210](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:210), after stop has driven the pins low.

   With a naïve `changed = out ^ ind_last_out`, restarting with Caps full-on gives `out = 1`, `changed = 0xFE`: **Caps is skipped**. Recording `ind_last_out = 1` then leaves it physically low indefinitely at 100%.

   **Change:** explicitly treat `0xFF` as invalid and force `changed = 0x07` for that tick. Alternatively, establish a reliable pins-low/cache-zero invariant. Keep stop/start under their existing lock. Test restart with all output masks, full duty, and retained accumulators that produce an immediate pulse.

2. **Replace “50%” with the actual worst switching workload, and make timing an acceptance gate.**

   [The proposed board test](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:984) uses both groups at 50%. On this curve, displayed **50% is 14.15% electrical duty**, about 5,660 transitions/s per lit pin. Displayed **82% is 49.47% duty**, about **19,788 transitions/s per pin**—roughly 59,365 writes/s with all three LEDs active.

   Also specify how that board workload is established: the menu only forces one group at a time. Real Caps and GUI lock plus the charging preview can exercise all three.

   The “~15 cycles” estimate is not a bound on the complete tick. [pwm_tick_cb](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:149) also runs `od_tick()` in dev builds and the backlight handler; [display_backlight_tick](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:283) writes its GPIO every tick. The lower-priority row handler reloads channels, scans keys, and rearms its timer after that work: [sn32f2xx.c:490](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:490), [sn32f2xx.c:776](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:776). Extra tick work can therefore reduce RGB activity and main-loop progress.

   **Change:** compare the existing firmware with the replacement under matched lighting, backlight, transport and instrumentation. Include idle, 1%, 82–83%, and 100%; measure tick service/rate, RGB activity, scan/main-loop rate and menu latency. Carry forward the applicable C10 limits. A new-firmware 0-versus-50 comparison alone is insufficient.

3. **Add the P2 proof explicitly to the test plan.**

   [P2’s contract](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1446) requires byte-identical old pages, separate write attribution, and correct boot decoding. [P2a’s tests](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:965) do not yet demonstrate all three. Reopening an editor demonstrates live RAM state, not persistence.

   **Change:** require tests of the production settings code for stored bytes `0`, `1`, `2`, `101`, `102` and `255`, independently for both fields, plus an old-version block. Verify defaults, saved Off, 1%, 100%, invalid fallback, boot application, delayed/coalesced writes, unchanged saves, and cancellation during an already-pending write.

   Add golden payload comparisons for pages 0–2 under unchanged workloads; page-3 attribution for each field alone, both together as `mixed`, unchanged writes, saturation and reset; and an old-firmware `RTC_UNHANDLED` host test.

The detailed checks otherwise come out as follows.

**The sigma-delta arithmetic is correct.** With `F = 12288`, `0 ≤ acc < F` and `0 ≤ duty ≤ F`, the largest sum is **24575**. Integer promotion and assignment back to `uint16_t` are safe. One subtraction suffices. Duty zero never emits a pulse, including with a retained residual; duty `F` emits every tick and preserves the residual.

Keeping the accumulator while its group is unlit is also sound. Resume changes the first-pulse phase, but cannot create an out-of-range accumulator or a pulse at zero. Ensure an inactive group’s output bits are cleared even though its accumulator is frozen.

Aligned, standalone `volatile uint16_t` duties are appropriate for this M0. Make **`ind_force` volatile too**, since the main loop writes it and the ISR reads it. The level getters need not read volatile state if only the main loop uses those levels.

I numerically checked all 101 table entries and simulated all nonzero levels. The table is strictly increasing and the endpoint arithmetic agrees. For every level with duty `d > 0`, the longest consecutive dark run is exactly:

`ceil(12288 / d) − 1` ticks.

For physical pulse-start spacing, adjacent on-ticks merge above half duty; for levels 1–99 the maximum is `ceil(12288 / min(d, 12288 − d))`.

| Displayed level | Electrical duty | Maximum pulse-start spacing | Maximum dark run |
|---:|---:|---:|---:|
| 1% | 2.083% | 48 ticks | 47 ticks |
| 2% | 2.165% | 47 | 46 |
| 10% | 2.962% | 34 | 33 |
| 25% | 5.322% | 19 | 18 |
| 50% | 14.152% | 8 | 7 |
| 82% | 49.471% | 3 | 2 |
| 83% | 51.440% | 3 | 1 |
| 99% | 96.167% | 27 | 1 |
| 100% | 100% | continuously on | 0 |

Thus the **48-tick bound holds**, assuming the tick is serviced regularly. At 1% it reproduces today’s pulse train up to phase. This establishes the spacing claim, not an unconditional absence of visible flicker during interrupt delays or flash operations.

**The curve and floor need wording changes, not a redesign.** The old-level equivalents listed in the proposal are correct. Calling this a perceptually spaced control is reasonable; calling its percentages calibrated perceived brightness is stronger than the evidence supports. Strictly increasing duty also does not guarantee that every adjacent step is distinguishable by eye.

“Dimmest that doesn’t flicker” is unsupported: [indicators.c:35](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:35) records a dimmer 64-tick setting without flicker, and the later comment qualifies the old 96-tick measurement. Say **“retains today’s tested minimum brightness.”** Keeping that conservative floor is sensible; tuning it can wait for JD’s assessment of each LED.

**The force-bit lifecycle fits the existing ownership model.** Save and rollback are the two normal transaction-ending paths: [menu_edit.c:115](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_edit.c:115). Both must clear the force before clearing `ed.field`.

The owner already rolls back before closing or handing off to Diagnostics: [panel_owner.c:98](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:98). Opener-close and the three-minute backstop reach that close path; [menu_ops.c:155](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:155) selects the backstop from `me_active()`.

`DSB_MENU` really covers PENDING and the entire OPEN session, including Diagnostics: `po_sleep_blocked()` tests `session != SESSION_NONE`, and [sleep.c:273](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:273) consumes it. Light sleep has its separate tick-stop guard at [sleep.c:117](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:117); adding force bits to `indicators_any_lit()` is correct.

An unexpected wake keeps the session until wake-release closes it, then rolls back. RGB cut does not own these GPIOs. A settings flash does not end the edit or persist its live preview. A watchdog reset clears ordinary force-bit RAM. Add those routes to force-lifecycle tests, especially Diagnostics, opener-close, backstop and unexpected wake.

**I found no competing live level writer or runtime GPIO owner.** The baseline brightness setter has no callers outside `indicators.c`. Keys, VIA and HID do not set these levels. `lockchan.c` decodes host LED reports; it does not drive indicator brightness or pins.

The other pin writes are initialization and tick-stop. QMK initializes Caps in [led.c:120](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/led.c:120), and board post-init initializes Win/Charging. The board’s `led_update_kb()` replaces the core path and returns false. GPIO set/clear uses atomic `BSET`/`BCLR` writes, so other pins on the same ports do not invalidate the output cache.

The new C6 domain is therefore valid. Keep real Caps/GUI/charging state separate from force state, and restore only the edited level. No RGB-style flush inhibition is needed: live levels and `kb_config` are separate, so an unrelated deferred block write can safely proceed during preview.

**Version 5 with nine bytes fits, and the VIA shift is safe for the existing tools.** QMK compares the stored keyboard version with `EECONFIG_KB_DATA_VERSION`; mismatch zero-fills the read destination: [nvm_eeconfig.c:221](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_eeconfig.c:221). It does not migrate the old fields.

The physical backing store is 2048 bytes, but logical EEPROM is **1024 bytes**. Using the actual layout formulas gives:

| Region | Current | Proposed |
|---|---:|---:|
| Core | 0–36 | 0–36 |
| Keyboard block | 37–43 | 37–45 |
| VIA configuration | 44–47 | 46–49 |
| Four-layer keymap, 720 bytes | 48–767 | 50–769 |
| Encoder maps, 16 bytes | 768–783 | 770–785 |
| Macro buffer | 240 bytes | **238 bytes** |

These follow [the EEPROM layout](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_eeprom_eeconfig_internal.h:55) and [dynamic-keymap allocation](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_dynamic_keymap.c:39). The macro buffer remains above QMK’s minimum.

`flash.sh` restores through `ak820keymap.py`; its buffer offsets are relative to the keymap, and encoders use their own commands: [ak820keymap.py:97](C:/Users/jdlien/code/ak820-pro/hostagent/ak820keymap.py:97). No address adjustment is needed. That backup currently excludes macros—an existing limitation, not a new consequence of this shift.

The +1 encoding is correct. Validate before subtraction, and clamp/reject setter input before addition. Applying immediately after `kb_eeconfig_init()` is early enough; initialize default duties before starting the timer. Deferred saving remains appropriate, with its existing five-second settlement and coalescing behavior.

**The flash-statistics design is correct, with two implementation traps.**

- Eight fields fit every existing `uint8_t` mask, including `0x80`; the per-byte table has nine entries because RTC occupies two bytes. **Freeze page 1’s loop at six**, rather than leaving its current `i < KBF_COUNT`: [flash_stats.c:128](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:128). Otherwise it writes four bytes beyond the 28-byte payload.
- Old firmware does return `RTC_UNHANDLED` for page 3: [hid_protocol.c:781](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:781). But [_txn_page():239](C:/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:239) currently accepts only successful replies, then raises `SystemExit`. Implement a narrowly correlated optional-page response that recognizes unhandled command/page 3 and represents unavailable counters separately from zero.

The simulator needs more than changing its size define: [sim.c:177](C:/Users/jdlien/code/ak820-pro/scripts/diag_sim/sim.c:177) still uses six-byte blocks, and [test_decode.py:24](C:/Users/jdlien/code/ak820-pro/scripts/diag_sim/test_decode.py:24) fabricates successful zero-filled missing pages. That fake would conceal broken old-firmware handling.

**The menu geometry and signatures fit.** `bar_state()` already clamps the scrollbar’s copy of `top`: [menu.c:531](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:531). With eleven rows, page two retains navigation top 8 while the thumb uses top 3. The thumb is 81 pixels high and ends at y=126. No scrollbar redesign is needed.

Append four nodes after existing node 34 to preserve screen IDs. Add their labels, titles, icons, classification, activation and return paths. `which = 7`, variants 0/1, fits the value signature without collision; give Charging its variant explicitly. The Connection signature also fits, and its frozen snapshot plus layout clear is sufficient. Ensure `pop()` recognizes Connection as leaving confirm geometry, and blank the unused fourth line off Bluetooth.

The editor needs max 100, slow step 1, fast step 5 and direct percentage formatting. The existing bar formula then produces exactly `14 + level`.

Update the actual positional assumptions, including:

- [menu_s0_test.c:1778](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1778): expected rows, page-two pixels, navigation offsets and restored cursors.
- [menu_p1a_board.py:39](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:39): row constants; **line 160’s literal one-step Power→Clock move must become two steps**.
- [menu_boot_board.py:17](C:/Users/jdlien/code/ak820-pro/scripts/menu_boot_board.py:17): Bootloader moves from row 5 to 7.

Sub 5 and sub 14 serialize generic byte values; they contain no nine-row or seven-field ceiling requiring a protocol redesign.

**RAM is plausible but needs the linked check.** I read the retained `781d071f` ELF: its heap gap is indeed **152 bytes**. The proposal mixes “per group” accumulators with six bytes of accumulator storage: two groups need four bytes; three per-LED accumulators need six. Resolve that wording, preferably using two group accumulators. Its estimate is conservative rather than dangerously low, but alignment means “137 bytes remaining” is not a measured result.

Keep the per-flavour floor check in [build.sh:196](C:/Users/jdlien/code/ak820-pro/build.sh:196), and measure stacks after the expanded session. The design can proceed without reserving another snapshot.

Actual timing, linked RAM and board persistence checks naturally wait until implementation, but must pass before acceptance. Perceptual tuning and wording can wait for JD. Also update [docs/leds.md:14](C:/Users/jdlien/code/ak820-pro/docs/leds.md:14): it still lists UART priority 1, whereas [mcuconf.h:77](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/mcuconf.h:77) sets UART and the system timer to 0. The tick remains priority 2 and RGB remains 3.