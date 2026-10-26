# Codex on P1b's design, draft 1 (10-24 night)

Prompt: `plans/review-prompt-p1b-design.txt`. Answered by draft 2 (the
design doc's "P1b" section).

## Dispositions

1. **Writers missing:** taken. VIA's `id_device_indication` (a toggle) and
   *any* VIA command on the RGB-matrix channel, reads included (so a lighting
   backup can't capture a preview: `flash.sh`, `ak820lighting.py`); the magic
   `eeconfig_init()` cancelled in `command_extra()` before `command_common()`
   runs it; `RM_FLGN`/`RM_FLGP`, with `flags` in the snapshot. The reset cases
   told apart: `QK_CLEAR_EEPROM` and every reset or bootloader entry discard
   RAM, and no shutdown path flushes the RGB config (`quantum.c:208-239`), so
   the flush hold leaves EEPROM at the saved values: nothing to roll back (a
   rollback at shutdown would also undo the splash's full brightness). VIA's
   `id_eeprom_reset` isn't an RGB writer. `HC_STALL` mode 2 is excluded as
   destructive fault injection. `param_repeat_step()` cancels before
   computing its step.
2. **Bit 0 is lit:** taken: `0xE000 | which << 10 | variant << 9 | value << 1
   | lit`. A previewing choice's check marks the entry snapshot's value.
3. **Rollback before the owner changes:** taken: `menu_edit_rollback()`,
   called by `panel_owner.c` at every accepted transition away from the menu
   (close, the opener's close, disarm, the wake-release close, the debug
   page's handoff and dev op 1) before `set_owner()` and the session change;
   it restores and nothing else. An external writer's cancel is the rollback
   plus the pop and "Cancelled". The animation's refused start cancels
   nothing. No writer hook is reachable from `menu_input()`'s call tree (the
   adapter calls QMK's setters, never a hooked entry point); a host test
   counts it.
4. **Hue bands' overlap:** taken: each band's signature is the strip's
   presence and the marker's centre relative to the band, -2..9, or none;
   the marker's absolute hue (Second color's `(hue + speed) & 255`). Costs
   restated: a coalesced input can repaint every band.
5. **RAM:** taken: rebudgeted from the linked builds of `541a8cbd` (every
   flavour); P1b needs ~12 B with no latched RGB copy (the rows read the
   config as they compose; a value changing mid-paint changes the signature,
   which restarts the slot); the piece-timing instrumentation (14 B, dev)
   leaves with P1b; the debug page's text buffers named as P1c/P2's
   reclamation.
6. **Tests:** taken: the production path on the board for every writer that
   can be driven without destroying JD's state (VIA packets by script, the
   Fn keys by JD; an op 27 counter of external cancels); the rest
   (the magic reset, `RM_FLG*`) by a host test of the keycode classification
   and by inspection. Clean against dirty at entry, Save then edit then
   Cancel, a forced VIA save mid-preview, the lights off through all three,
   against a fake RGB core with QMK's early returns and dirty flags. Piece
   boundaries for both editors with retarget, loss, close and reopen, the
   glyph DMA and failed sends. C10's gates on the editors. Every flavour's
   RAM and the stack watermarks. JD's Fn+arrows replace the wake rig's RM
   key on gremlin (the rig is Buzz's). The board script fails a pass over
   17 ms (JD's (b)) and still counts those over 15.
- **Implementation notes** (taken into the design): `ms_set_layout()` both
  ways; Diagnostics' parent cursor computed, not `2`; the title ids;
  `mb_pixels` inside `lcd_bus.c`; the big glyph by flash DMA; the 180 s
  backstop only while previewing, signed; an external cancel after 24 s idle
  may close the list at once (accepted).

## The review, verbatim

**Yes. I would amend the draft before coding.** The overall approach is workable, but writer coverage, highlight signatures, cancellation ordering, and RAM accounting need changes. No files were changed.

I would resolve these before implementation:

1. **C6’s writer inventory is incomplete.**

   The proposed VIA hook is correctly placed: [`via.c:296`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:296) calls it before dispatch. But RGB-channel Set/Save are not VIA’s only RGB writers. `id_set_keyboard_value / id_device_indication` reaches `rgb_matrix_toggle_noeeprom()` through [`via.c:167`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:167). Add that command to the cancellation hook, then let VIA process and reply normally.

   **The enabled command/magic subsystem supplies another live writer.** Both shifts plus Backspace invokes `eeconfig_init()` at [`command.c:344`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/command.c:344); command support is enabled at [`keyboard.json:22`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keyboard.json:22). This replaces RGB configuration and force-flushes it through [`eeconfig.c:122`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/eeconfig.c:122). Cancel the transaction **before** that reset—for example, through `command_extra()`, returning false to continue normal processing. `eeconfig_init_kb()` is too late: RGB defaults have already been written.

   Include `RM_FLGN`/`RM_FLGP` explicitly. They write `flags` at [`process_rgb_matrix.c:97`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_rgb_matrix.c:97). The “whole RGB config” snapshot in [the draft:487](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:487) omits flags; add it, or explicitly establish that cancellation preserves this untouched field. Seven snapshot bytes plus field/state bytes can still fit nine bytes.

   Distinguish the reset cases: VIA’s `id_eeprom_reset` only resets VIA storage via [`via.c:120`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:120), whereas `QK_CLEAR_EEPROM` normally invalidates EEPROM and reboots ([`process_quantum.c:57`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_quantum.c:57)). They are not interchangeable writers.

2. **The new signature breaks the scheduler’s bit-zero contract.**

   [The proposed formula:542](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:542) is injective and distinct from the existing **row** classes. I enumerated all 7,168 combinations: no aliases or overlaps with item, text, About, or blank rows.

   However, [`menu_slots.h:41`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.h:41) requires **bit 0 to mean lit**. The scheduler tests that bit when cleaning, withholding, starting, and committing rows ([`menu_slots.c:271`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:271)). With the draft, an odd value looks highlighted regardless of selection; a selected even value looks unlit.

   Keep the existing contract:

   ```c
   0xE000 | (which << 10) | (variant << 9) | (value << 1) | lit
   ```

   This still fits exactly. Screen must use its full level byte, including the top-level row; Speed/Second color must include the live-effect-derived variant. Preview-choice checkmarks must remain tied to the **entry snapshot**, not the live preview: P1a’s [`saved_row():138`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:138) currently reads the live model.

3. **“Restore before owner changes” needs an actual pre-transition mechanism.**

   [`do_close():93`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:93) returns `PO_ACT_EDIT_CANCEL`, but changes the owner and session before returning. `enter_debug()` does the same. [`display_po_event():3971`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3971) applies actions afterward, and [`menu_ops_apply():75`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:75) currently ignores cancellation.

   Therefore, merely handling `PO_ACT_EDIT_CANCEL` in `menu_ops_apply()` cannot satisfy [the draft’s ordering:481](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:481). Specify a synchronous rollback hook at accepted transitions, before `set_owner()` and session changes. Cover close/opener, disarm, wake-release close, and **DBG_PAGE/dev op 1 handoff**, which can interrupt an editor without ending the session.

   Separate transaction rollback from “pop and flash Cancelled.” Owner handoff should restore without unnecessarily navigating/repainting the departing menu. An animation start is currently **refused** during a session ([`panel_owner.c:170`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:170)); it should not cancel an edit.

   Also specify cancellation during `menu_input()`: it retains a frame pointer and subsequently processes the latch ([`menu.c:617`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:617)). If an external write cancels from a called path, the old input must not continue into Save or another pop. Internal preview/save/restore calls must remain distinguishable from external writers.

   Finally, orderly bootloader entry bypasses this owner machinery. The splash writes maximum LCD brightness at [`display.c:1331`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1331), reached both from QK_BOOT and [`hid_protocol.c:1343`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1343). Cancel before the splash; cover ordinary reboot/reset paths too.

4. **The hue-band signature needs an explicit overlap rule.**

   [Draft line 556](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:556) says “marker’s column relative to” the band, but must specify that a marker **outside** the band can still affect it. Its triangle extends two pixels either side ([`mockup:543`](C:/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:543)).

   For an eight-column band, encode the signed relative center from **−2 through 9**, plus a distinct “no overlap” state. Otherwise, treating every center outside the band as absent leaves triangle pixels stale. Each repaint must regenerate the strip/background underneath the entire clipped marker.

   Define this using the **absolute second-color hue**, `(hue + speed) & 255`, and test every boundary, wrap, reversal, and large jump. Range-band edge signatures are sufficient because their outline/background are fixed.

   Correct the cost claims too: coalesced turns can change all seven range bands, or four separated hue bands. “One or two” and “two or three” are not universal bounds.

5. **The RAM claim is based on an obsolete baseline.**

   [Draft line 583](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:583) counts six new model bytes, but the named RGB fields plus LCD level require **seven** before any packing. The fast-turn rule also needs previous-turn state; `menu_input()` receiving `now` does not supply a previous-turn timestamp.

   I read the archived clean [541a8cbd ELF](C:/Users/jdlien/code/ak820-pro/ak820pro-builds/out/via-dev-541a8cbd-20261024-211843.elf), verified against its [manifest hash](C:/Users/jdlien/code/ak820-pro/ak820pro-builds/out/via-dev-541a8cbd-20261024-211843.json:11):

   | Build | `.data` | `.bss` | Heap gap |
   |---|---:|---:|---:|
   | S1 `ffa80947` | 2,792 | 26,656 | 232 B |
   | Current `541a8cbd` | 2,808 | 26,712 | **160 B** |

   Current head has consumed **72 B**, rather than the earlier ~30 B P1a estimate. Using the design’s own 312 B S0/S1 accounting gives **384 B already**, then at least 16 B for P1b, 12 B for P1c, and 36 B reserved for P2/P3: **448 B before additional timing state/padding**. The projected heap gap would be 96 B, below the 128 B floor.

   Rebudget from current linked artifacts and name the reclamation needed. P1b alone likely fits, but “under C5’s 420 B” is not established, and the devfault-only log trim does not help dev.

6. **The test plan needs production-path and persistence cases, not only menu fakes.**

   The existing host target excludes `menu_glue.c`, VIA, RGB core, and display hardware glue ([`menu_s0_test.c:9`](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:9)). A fake VIA packet that directly calls cancellation cannot prove the actual hook’s placement or forced-flush behavior.

   Add explicit coverage for:

   - Real dispatch/classification of VIA Set, Save, device indication, magic reset, all RM keys including flags, wrappers, repeats, and LCD writers.
   - Clean versus already-dirty RGB at entry; Save → another edit → Cancel; forced VIA Save during preview; disabled RGB across preview/save/cancel.
   - Cancellation during input processing and every owner handoff, asserting restored values **before** owner mutation.
   - Piece-boundary retarget/loss/close-reopen for both editors, including glyph DMA completion and failed polled sends.
   - C10’s LED-rate, transition, continuous-input progress, and final-settlement gates. Extending `menu_p1a_board.py`’s timing check alone does not cover these.
   - Every-flavour linked RAM and worst-case stack watermarks.

   The listed P1 persistence, disabled-save, visibility, Diagnostics, VIA, and hands-on gates are otherwise present. Preserve the explicitly planned wake-rig RM test, or mark JD’s Fn+arrow test as its deliberate replacement ([build plan:1437](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1437)). The timing script still fails any >15 ms pass ([`menu_p1a_board.py:202`](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:202)); reconcile that with JD’s accepted timing amendment before running the gate.

The following parts check out, with these qualifications:

- **Named key interception order is correct.** `process_record_kb()` precedes both lighting handlers ([`quantum.c:355`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/quantum.c:355)). RM acts on release; UG acts on press. The custom RGBM wrappers act on press, and [`param_repeat_step():44`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:44) needs its own hook. Cancel before computing an increment, not merely before storing an increment calculated from the preview.

- **The RGB adapter’s persistence argument is sound once writers are covered.** `_noeeprom` preserves an existing dirty flag because `eeconfig_flag` uses OR ([`eeconfig.h:191`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/eeconfig.h:191)). Rollback restores RAM while the hold remains active; releasing it lets the previous pending save persist restored values. Save must use the saving setter even when the preview already equals the target. Forced Save bypasses the board guard ([`rgb_matrix.c:102`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:102)), making pre-dispatch cancellation essential. Persistence remains deferred, not guaranteed at the instant “Saved” appears.

- **Temporary enable does not inherently flash or restart every preview.** Enable/disable setters schedule `STARTING`; they do not themselves render. The adapter runs synchronously, and rendering sees the final enable state. Effect initialization depends on final effect/enable versus the last rendered values ([`rgb_matrix.c:344`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:344)). HSV/speed previews while already enabled need no mode call. Avoid gratuitously restoring mode on every preview; actual effect changes and Lights changes appropriately initialize effects.

- **Screen’s adapter matches C7.** [`bkl_effective():267`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:267) lifts power/cap, applies minimum level 1, then respects wake hold. `display_set_brightness()` changes only requested RAM; the persisted block is separate. Thus an unrelated pending block flush cannot capture a Screen preview. SCR cancellation must occur before [`display_brightness_up/down():335`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:335) reads the level. Dev op 5 changes requested **power**, not level; cancelling for it follows the existing explicit C6 policy, though it is broader than the stated conflict domain. SCR_TOG need not cancel a level edit.

- **Slot and byte counts work.** Range is 13 slots; hue is 22; the limit is 24. Range bands are at most 320 B, hue bands 336 B, and a 10×23 glyph is 460 B. Put the generated-pixel implementation inside `lcd_bus.c`, which owns the scratch, with a thin backend wrapper. Follow its acquire/send/release, panel byte order, and failure cleanup ([`lcd_bus.c:228`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:228)). The big glyph uses flash DMA, **not scratch**. Explicitly select layouts through `ms_set_layout()` both entering and leaving editors; `ms_retarget()` alone cannot erase the old geometry.

- **Timeout semantics are right.** Replace the unconditional 24-second test at [`menu_ops.c:155`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:155) with 180 seconds only while a preview transaction is active. Preserve signed elapsed-time handling. External cancellation after 24 seconds of knob inactivity may therefore close the returned list immediately; do not reset the clock merely to display “Cancelled.”

- **The claimed nonwriters are correctly excluded.** Power caps, battery cut, and sleep operate below requested configuration. [`power.c:119`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:119) changes scale/caps and can restart an effect without changing its configuration. Host text, playback, consumer modification, and lock-light traffic supply no additional normal RGB/LCD-level writer. The deliberate terminal fault path `HC_STALL` mode 2 does overwrite persisted LCD data through [`kb_eeconfig_test_write():161`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:161); explicitly exclude that destructive fault injection from ordinary transaction guarantees.

One flashing edge case also needs a stated policy: the **restore** in `flash.sh` is covered—it uses ordinary VIA RGB Set/Save packets ([`ak820lighting.py:122`](C:/Users/jdlien/code/ak820-pro/hostagent/ak820lighting.py:122)). But its **backup** reads live values before bootloader entry ([`flash.sh:153`](C:/Users/jdlien/code/ak820-pro/flash.sh:153)). Flashing during an edit can therefore capture a preview and restore it permanently afterward. Cancel/close before taking the backup, or explicitly exclude flashing from the cancellation guarantee; cancelling at the splash is too late for that backup.

**Half-row slots can wait.** The existing nine-piece whole-row repaint remains correct, and deferring ticking Clock examples makes the performance tradeoff reasonable. New title-ID allocation, replacing Diagnostics’ hard-coded parent cursor at [`menu.c:512`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:512), and final wording/icons can be handled during implementation and the planned text review. The transaction, signature, lifecycle, and RAM corrections should precede it.