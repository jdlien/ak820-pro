# Codex on P2a's code (`8b4aec16`), 10-25 night

Prompt: `plans/review-prompt-p2a-code.txt`. No firmware change before the flash.

## Dispositions

1. **The timing pass with all three at 82%:** taken. `menu_p1a_board.py --no-ind`
   skips its indicator edits (they reset the force bits); the timing run sets force 3
   at 82 and 83 by sub 15, checks it by sub 14 before and after, then the board pass,
   against the 17 ms limit. The functional pass (with the indicator edits) runs apart.
2. **`ind_timing.py`'s cleanup:** taken before the flash: it refuses while an edit is
   open, and puts back the force bits it found as well as the levels.
3. **Connection's off-Bluetooth text and "Charging":** the code stands and the design
   text follows it: "Slots: coming soon" is on every link (the menu will manage the
   slots whatever the slider says), and the row is the mockup's "Charging" with its
   editor's title "Charging light" (the mockup is authoritative for words). Both are
   in `MENU-TEXT.md` for JD's text pass.
4. **The frozen-link test:** taken after the flash: the live link changes between
   pieces of the first paint and after an invalidation, every line keeps the snapshot,
   and a reopen shows the new one.
5. **Coverage:** taken after the flash, before acceptance: `kbee.c` seeds all seven
   old bytes and compares them, and a pending write with a cancel after it;
   `indicators_load_saved()` is three lines over the decoder `kbee.c` tests and
   `indicators.c` needs the HAL, so it is covered on the board (a level surviving the
   power cycle); the Diagnostics handoff, the wake release and a replacing `me_open()`
   with an indicator edit open, in the host tests; the counters' saturation above 255
   and at 65535 and the whole reset payload, in the simulator; every starting byte
   0-255 both ways for the fine steps.
- **The tick's cost:** measured on the board (the timing gate); "~15 cycles" was the
  arithmetic, not the tick.

## The review, verbatim

**No firmware change is required before an initial dev flash of `8b4aec16`, based on this review.** Acceptance still needs the timing measurements, and the current board script needs adjustment to establish the promised worst-case workload.

I verified that all 18 changed firmware files match the requested target commit and inspected its retained ELF.

1. **Fix before running the timing acceptance gate: the board pass cannot maintain all three indicators at 82%.**  
   [menu_p1a_board.py:251](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:251) expects force bits `1` when opening Lock lights. If the bench has established force `3`, that assertion fails. Subsequent turns change 82% toward 100%, and closing the editors clears their force bits. The later measurements therefore lose the requested workload.

   **Change:** run the functional indicator tests separately, then run a dedicated menu timing pass with force `3`, levels `82,82`, verified before and after. Avoid indicator transactions during that interval; retain the 17 ms limit.

2. **Bench cleanup can leave a cancelled preview applied.**  
   [ind_timing.py:49](C:/Users/jdlien/code/ak820-pro/scripts/ind_timing.py:49) captures live levels before sub 15 cancels an open edit. Cleanup at line 59 restores those captured preview levels and always clears force, ignoring the saved `before["force"]`.

   For example, an edit previewing 35% over an original 17% gets cancelled correctly by firmware, but the script subsequently restores 35%.

   **Change:** reject an active edit before mutating anything, then restore both levels **and the original force mask**. This is a bench-script defect, not a normal menu-path defect; it can follow the flash.

3. **Connection’s off-Bluetooth text differs from the agreed design.**  
   [menu.c:687](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:687) retains “Slots: coming soon” off Bluetooth and fills all four lines. The design specifies the link, “The slider picks”, “BT, 2.4G or cable.”, then a blank fourth line. [menu_s0_test.c:2836](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2836) reproduces the implementation’s discrepancy.

   **Change:** correct the off-Bluetooth array and its expected frame. The list also says “Charging” where the design says “Charging light”; reconcile that wording. Neither blocks flashing.

4. **The frozen-link test does not actually test repainting from the frozen snapshot.**  
   [menu_s0_test.c:2850](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2850) changes the fake live link after the page has settled, then checks the existing framebuffer without invalidating it. A painter that incorrectly read live state could pass because it never runs again.

   **Change:** invalidate and repaint after changing the live link, and change it between pieces of the initial paint. Assert that all lines retain the opening snapshot, then reopen and assert that the new snapshot appears. The production snapshot implementation itself is correct.

5. **Some promised test coverage remains missing or overstated.** These can follow the initial flash, but should be completed or explicitly recorded before acceptance.

   - [kbee.c:35](C:/Users/jdlien/code/ak820-pro/scripts/diag_sim/kbee.c:35) “boots” only `kb_eeconfig_init()`. It tests decoding, but not `indicators_load_saved()` applying defaults/saved levels, nor cancellation while a real settings write is pending. Add those integration cases. At line 95, “bytes 0–6 untouched” checks only bytes 0 and 6, both zero; seed and compare all seven bytes.
   - [menu_s0_test.c:336](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:336) and its wake test at line 417 exercise ownership transitions without an open edit. They do not substantiate the disposition’s claim that rollback during Diagnostics/wake was already tested for P1b. Add both indicator fields, plus replacing an open indicator edit through `me_open()`.
   - [sim.c:218](C:/Users/jdlien/code/ak820-pro/scripts/diag_sim/sim.c:218) lacks the promised saturation test; its reset check examines only each counter’s low byte. Exercise values above 255 and saturation at 65535, then verify the complete reset payload.
   - [menu_s0_test.c:2703](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2703) walks the canonical percentage values, not every starting byte. Extend it to all 256 starting values in both directions. Its expected percentage is an independent loop counter, so this check is **not** circular.

The critical implementation checks came out sound:

- **ISR arithmetic and restart:** accumulator bounds hold at every level; the maximum sum is 24575. Zero stays dark with a retained residual; full duty stays on. Inactive groups retain their accumulators while clearing their output bits. `IND_OUT_UNKNOWN` forces all three pins to be written after restart. GPIO writes resolve to atomic `BSET`/`BCLR`, with no port read-modify-write.
- **Actual tick cost:** the retained `-O2` ELF fully inlines all indicator helpers. Its only callback calls are the existing `od_tick()` and `display_backlight_tick()`. However, [indicators.c:111](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:111) reads both volatile duties even when groups are inactive; the compiled arithmetic includes halfword loads/stores, zero-extension, branches and literal loads. The callback grows from 240 to 368 bytes, including literals. There is no indicator-table lookup in the tick, but instruction/literal flash accesses still matter. **“~15 cycles” is not a bound on the complete tick**, and smaller idle cost remains unproven. A wider local arithmetic temporary is an optimization candidate only if measurements justify it.
- **Force lifecycle and bench ordering:** [menu_edit.c:101](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_edit.c:101) clears the edited group before clearing the field; Save, rollback and replacement edits reach it correctly. Sub 15 validates all arguments before cancellation, cancels before applying levels/forces, and is dev-only. Deferred menu popping does not erase its newly applied force state.
- **Persistence and attribution:** +1 decoding, invalid-group `NULL` handling, setter bounds, boot placement and aligned volatile duty stores are correct. The nine-byte layout and eight mask bits agree. Page 1 remains exactly six counters; page 3 carries the two additions. The static assertions enforce sizes and mask capacity, though not individual field offsets. Optional-page handling correctly distinguishes correlated `RTC_UNHANDLED` from timeout.
- **Menu and steps:** node IDs, icons, titles, `which = 7`, Charging’s variant, frozen Connection signatures and confirm-layout exit paths are correct. Indicators use steps 1/8; hue uses 1/12; Screen remains unchanged. Independent checks of all **512 starting-value/direction combinations** confirmed exactly one displayed percentage point per slow detent, except at clamped endpoints. All 101 duty entries and sigma-delta levels also passed independent numerical checks.
- **RAM:** the exact target dev ELF has a **144-byte gap**, above the 128-byte floor.

I could not execute the C/Python suites because process launches were denied. This assessment uses source inspection, retained machine code and independent in-memory numerical checks. All file access stayed inside the repository; nothing was changed.