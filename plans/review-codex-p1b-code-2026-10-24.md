# Codex on P1b's code (`feeb9aa3`, `8cb713e3`), 10-24 night

Prompt: `plans/review-prompt-p1b-code.txt`.

## Dispositions

1. **A queued click reported "Saved" after an external cancel (must fix):** fixed in the next commit: an editor or previewing choice whose edit is closed takes no input; `menu_tick()` pops it with "Cancelled". Regressions: an external write with a click, and with a turn, queued behind it (op 27 flies one input at a time, so the turn-and-click case is two passes); they fail without the fix.
2. **The cancel's pop retargeted twice:** fixed (one target; the regression checks the generation moves by one).
3. **The strip's colours weren't QMK's:** fixed: `hsv_to_rgb_impl()`'s arithmetic; the test's reference is QMK's code with two values checked by hand (hue 0 red, hue 213 0xF81F).
4. **The agreed exit coverage isn't all there yet** (long idle and the 32-bit wrap, piece-boundary loss/DMA/close-reopen in the editors, forced-save semantics, restoration before the owner changes; the board pass's VIA, dev ops, disabled save, Lights save, the editors' C10 gates; the S1 gate's 15 ms): owed before P1b is accepted, not before this flash to the test board.
- **RAM:** 17 B unpadded of new state (`ed` 9, `pending` 1, `ext_count` 2, `ft_last` 4, `ft_have` 1); dev +8 B net after the 14 B of timing left; the ledger to update; the stacks' watermarks still owed.

## The review, verbatim

**Yes. I would fix the cancelled-edit click race before flashing.** I found no preview-persistence leak, stranded edit, stale-pixel signature, or CPU paint-budget overrun in the reviewed paths.

**Must fix before flash:**

1. **A queued click can report “Saved” after external cancellation.**  
   [menu_ops.c:135](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:135) dispatches input before consuming pending cancellation. The external hook has already restored the snapshot and cleared `ed.field`, but the editor remains the current screen.

   Reproduction: open Brightness, preview a change, then receive an external RGB write and a knob click before the next menu task. [menu.c:1025](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1025) calls the now-inactive `me_save()`, flashes **Saved**, and pops. The subsequent tick sees a list, so its cancellation branch never replaces that message. Effect/Lights have the same problem through `activate()`.

   **Change:** suppress editor/preview-choice input when its transaction has already closed, letting `menu_tick()` perform the cancellation pop. Alternatively, process cancellation before input while discarding the input batch belonging to the cancelled editor; merely moving the tick earlier could apply that click to the parent. Add regression cases for external cancellation plus click and turn-plus-click, checking **Cancelled**, the parent screen, and preservation of the external value.

**These can wait until P1b acceptance:**

2. **External cancellation creates two targets.**  
   [menu.c:1071](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1071) calls `pop()`, which creates a target through `ms_set_layout()` or `ms_retarget()`. Then `pend` makes `moved` true and line 1081 retargets again. This adds an artificial supersession and resets target timing twice.

   **Change:** track whether the pop already created a target and avoid the second retarget, while still synchronizing the model/title. Assert one generation increment for cancellation.

3. **The hue strip does not use this checkout’s QMK colour conversion.**  
   [menu.c:693](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:693) uses `h / 43`; [quantum/color.c:56](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/color.c:56) uses different sextant and interpolation arithmetic. For example, strip hue 213 produces `0xF01F` instead of QMK’s `0xF81F`. This is a small colour discrepancy, not a signature defect.

   **Change:** use a narrow environment primitive backed by `hsv_to_rgb()`, or reproduce its exact arithmetic. The reference at [menu_s0_test.c:2168](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2168) copies the implementation’s formula, so it currently endorses the discrepancy.

4. **The supplied tests do not yet implement the agreed exit coverage.**  
   [test_p1b():2200](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2200) covers useful normal paths, but lacks the promised long-idle/32-bit-wrap cases, editor piece-boundary loss/DMA/close-reopen cases, forced-save semantics, and restoration assertions *before* owner mutation. The `MENU_ENABLE` build runs only `test_menu_enable()`.

   The [board pass:199](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:199) exercises navigation and cancellation; it does not exercise VIA ordering/persistence, dev ops 4/5, disabled Save, Lights Save, or the editors’ continuous-input/LED-rate gates. Extend those before treating P1b as accepted. The existing S1 gate also still enforces 15 ms and zero `over15`; its editor adaptation remains outstanding.

The other requested checks came out as follows:

- **Transaction sequencing:** `set_field()` correctly handles disabled mode/HSV setters and restores enable last. Save invokes the saving setter even for unchanged Effect. `restore()` handles initially-off brightness edits and both directions of Lights preview correctly; speed/flags restoration needs no temporary enable. `me_open()` rolls back before taking another snapshot. Domain cancellation and pending-bit accumulation are correct apart from their later consumption above.
- **Hooks:** RM/UG interception precedes the board’s early returns and QMK’s lighting handlers. Ranges and endpoint assertions match this checkout. SCR, RGBM, repeats, dev ops, magic reset, and the flush hold are correctly placed. VIA reads only the two bytes protected by its length check, uses the correct IDs, leaves other channels alone, and returns false for normal dispatch. Owner rollback precedes both close and debug handoff.
- **Rendering/navigation:** row counts, snapshot checkmarks, value-row lit bit/colour, formatting, editor entry/exit layout changes, acceleration/clamps, Diagnostics return, and editor cursor reporting are consistent with the design. Independent enumeration found no pixel aliases across **6,056 band/value cases**, and all **7,168 value-row signatures** were distinct. New bands send at most **336 B**, big glyphs **460 B** by DMA, and text pieces **488 B**. Layout clears remain the separate DMA-band path.
- **Backend/table:** `lcd_blit_gen()` follows the existing stream’s byte order, scratch lifetime, and failure cleanup. Big glyphs use the intended font. The nine enabled effects have the correct names/order, and the overlay shares that table.

**RAM fits the completed builds, with less spare room than the estimate.** I hash-verified the archived `8cb713e3` ELFs: **dev 152 B**, **devfault 200 B** heap gap. A matching daily artifact was not yet available.

The new mutable state totals **17 unpadded bytes**: `ed` 9, `pending` 1, `ext_count` 2, `ft_last` 4, and `ft_have` 1. After removing 14 bytes of instrumentation and accounting for alignment, dev grows **8 B** overall. Update the ledger; the counter and previous-turn flag need explicit accounting. The layouts, hints, and effect table are in flash.

The band contexts are **6 B / 22 B**, remain alive through synchronous sending, and introduce no static pixel buffer. In the dev ELF, `band_paint()` is folded into `e_paint()`’s **96-byte frame**; `lcd_blit_gen()` has a **64-byte frame**. Editor titles additionally call through `l_paint()` and `text_piece()`, so measure that path too. The 2,048-byte main-thread stack reservation is unchanged; fresh watermarks remain required.

No files changed. Reviewed firmware files matched the committed blobs. Process execution was denied, so I could not rerun the host suites or builds.