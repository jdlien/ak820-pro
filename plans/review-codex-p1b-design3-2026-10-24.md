# Codex on P1b's design, draft 3 (10-24 night)

Prompt: `plans/review-prompt-p1b-design3.txt`.

## Dispositions

- **The three fixes are sound; no blocking change.** The design is cleared for code.
- **Wording, taken:** the fast turn's exact predicate (`abs(turns) >= 2 || (have_previous_turn && now - last < 90)`, a flag, not a zero timestamp) and its tests; "every pass" qualified (a fixture doesn't tick; the return from Diagnostics installs a fresh target).

## The review, verbatim

**The three fixes are sound; no further blocking design change is needed.** Two statements need more precise wording before implementation.

1. **Fast-turn clock: correct.** `menu_input()` already receives a `uint32_t now`. A 32-bit unsigned subtraction fixes the 65,556 ms alias and handles timer wrap.

   In [the fast-turn paragraph](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:472), “cleared” should mean **no previous turn in this editor**, not merely timestamp zero. Also change “first turn is never fast” to **“first single-detent input is never time-accelerated”**: the independent two-or-more-detents rule still applies. The intended predicate is:
   ```c
   abs(turns) >= 2 ||
       (have_previous_turn && (uint32_t)(now - last_turn_ms) < 90u)
   ```
   Explicitly retain tests for long idle, 32-bit wrap, and editor re-entry.

2. **Pending-change notification and retarget: correct, with an exception to “every pass.”** [Board housekeeping](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:582) runs repeats, then `menu_task()`, then the display pump. [The glue](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:170) calls `menu_ops_task()`, whose normal MENU path ticks before pumping.

   **Not literally every pump has a preceding `menu_tick()`:** fixtures do not tick, and [the Diagnostics-return branch](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:128) returns immediately after switching back to MENU. That return already calls [`menu_return_from_diag()`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:505), installing a fresh layout, target and full clear. Consequently, this exception does not expose stale value painting or miss target creation. Qualify the design’s sentence; no control-flow change is required.

   [`ms_retarget()`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:149) directly calls `new_target()`, so it supplies the required generation, settlement, supersession and interrupted-timing bookkeeping. An **unreached** stop is cancelled; an already reached stop remains held, including one reached by a just-completed DMA. Because `op27_poll()` precedes the tick, cancellation is reported next pass. During a layout clear, retarget preserves clear progress, and [`ms_settled()`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:322) cannot declare settlement early.

3. **Production transaction sequencing and tests: correct.** Moving sequencing into host-built `menu_edit.c`, with only primitive calls replaced, resolves the previous test-boundary defect. The specified semantics match QMK: [disabled mode/HSV setters return early](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:605), saving setters mark dirty even for unchanged values, and [`eeconfig_flag(false)` preserves existing dirtiness](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/eeconfig.h:191). Temporary enable, restoring enable last, and always invoking the saving setter are therefore appropriate.

   [The revised board assertions](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:740) observe ordering through returned values, increments, surviving writes/toggles and reboot persistence. The inspection exceptions are now explicit. This adequately closes round two’s third finding.

Read-only source review against the checkout whose `gremlin/s1` ref resolves to `541a8cbd`; no files changed or tests run.