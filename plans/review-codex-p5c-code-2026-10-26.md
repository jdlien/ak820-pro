# Codex: P5c, the settings profiles' Rename (2026-10-26)

The plan's design (plans/SETTINGS-PROFILES-PLAN.md, "Rename"): the one page
that takes typing, WAIT, CAPTURE and DRAIN in one byte.

Rounds, verbatim, then dispositions:
1. `plans/review-prompt-p5c-code.txt`: qmk_firmware-ak820pro `2ce410e7..740555b2`
   (branch `gremlin/p5c`, on P5e).
2. `plans/review-prompt-p5c-verify.txt`: `740555b2..f9b4035c`.
3. `plans/review-prompt-p5c-verify2.txt`: `f9b4035c..13c5e910`.

## Round 1 (740555b2)

**Yes—changes are needed before flashing `740555b2`.**

- **P2 — one-shot layers remain enabled.** [menu_glue.c:387](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:387): `reset_oneshot_layer()` clears bookkeeping, **not `layer_state`** ([action_util.c:200](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action_util.c:200)). Enter Rename with an armed `OSL(WINFN)` and Fn remains enabled after exit; subsequent Esc can invoke the bootloader. Clear the active one-shot layer as well, using the full fulfilment mask or explicitly disabling its saved layer before resetting. The plan’s prescribed API is insufficient.

- **P2 — reopening breaks DRAIN.** [menu.c:1995](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1995): hold a captured key, cancel, then click Rename again before releasing it. Assigning `RN_WAIT` forwards its orphan release into QMK. Contrary to the comment, releases can act: VIA-mapped `RM_*` controls execute on release. Preserve swallowing until the previous drain completes, then arm capture.

- **P2 — name signatures can suppress repaint indefinitely.** [menu.c:2003](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2003): `"cd"` and `"da"` both produce `0x52AB`. If edits coalesce before repaint, the scheduler can retain the old displayed name while saving the new one. Explicitly invalidate the name slot when consuming `RN_EDITED`; the hash alone cannot establish pixel equality.

- **The planned loss cancellation is missing.** [menu.c:1659](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1659): the actual loss path calls `menu_screen_invalidate()` → `menu_invalidate()`, which only invalidates pixels. It never takes the assumed `MENU_CLEAR`/`screen_open()` path, so Rename and CAPTURE survive. Add cancellation and draining for Rename losses.

Otherwise, the built configuration’s matrix events reach the gate before tapping; USB and BT share that path. Combos and key overrides are disabled. VIA/default-layer lookup, Mac/Win selection, physical Shift, ignored transparent/non-basic codes, the additive tapping accessor—including `NO_ACTION_TAPPING`—and profile write ordering look sound. Ordinary exits and sleep admission show no additional blocker.

The ELF confirms **`pg` 12 B, `rn` 1 B, heap gap 136 B**. Add regressions for the findings; the current one-shot fake merely counts calls. Static review only: process execution was denied, so tests and hardware timing were not rerun.
## Round 2 (f9b4035c)

**1–2 are closed; 3 has one remaining case; 4 is acceptable.**

- **P2 — 3 remains incomplete:** [menu.c:2156](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2156). If `"cd"` → `"da"` edits and Enter arrive before one tick, `RN_ENTER` bypasses the invalidation and clears `RN_EDITED`. If saving returns `PROF_BUSY`, [menu.c:2024](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2024) keeps Rename open; the identical signature leaves `"cd_"` displayed, although retrying saves `"da"`. Invalidate slot 2 whenever `k & RN_EDITED`, before handling Enter/Esc. Extend the collision test with Enter and recovery enabled.
- **1 closed:** [menu_glue.c:391](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:391) clears all fulfilment bits, turning the active one-shot layer off.
- **2 closed:** [menu.c:1996](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1996) preserves DRAIN; [menu.c:675](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:675) rearms capture only when idle.
- **4 acceptable:** [panel_owner.c:250](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:250) preserves the page and ownership. Retaining its capture through repaint introduces no identified harm.

I’d finish 3 before flashing. No additional regression or hardware flash-safety issue found in this diff. Static review only: process execution was denied; tests and hardware behavior weren’t rerun.
## Round 3 (13c5e910)

**Closed.** [menu.c:2156](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2156) invalidates slot 2 before Enter/Esc. [menu_s0_test.c:4627](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4627) queues edits and Enter without an intervening tick, then checks the retained page, busy title, and `da_` pixels.

No commit/cancel regression found: [menu.c:1694](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1694) switches layouts; [menu_slots.c:121](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:121) resets slot states and stages clearing. The extra retarget cannot resurrect Rename.

**No new flash blocker for gremlin identified in this diff:** no added storage or blocking drawing. Static review only; process execution was denied, so passing tests and the 136 B heap gap remain your reported results.
## Dispositions

**Round 1, [P2] one-shot layers remain enabled: fixed in `f9b4035c`.**
`env_clear_oneshots()` now clears every fulfilment bit of an active
one-shot layer (`clear_oneshot_layer_state(ONESHOT_START |
ONESHOT_TOGGLED)`), which turns the layer off, then resets it. The plan's
`reset_oneshot_layer()` alone cleared only the bookkeeping. No host test
(the fakes have no `layer_state`); codex read it closed.

**Round 1, [P2] reopening breaks DRAIN: fixed in `f9b4035c`.** A Rename
opened while the last capture's DRAIN runs keeps draining, swallowing that
key's release, and moves to CAPTURE once the keys are up with the page
showing. Test: a captured key held through a cancel and a reopen (DRAIN
reported, its release swallowed, then CAPTURE).

**Round 1, [P2] the name's signature can suppress a repaint: fixed in
`f9b4035c`, then `13c5e910`.** An edit invalidates the name's line, and
(round 2) does so before an Enter or Esc of the same pass is taken, so a
refused Enter keeps the page showing the name it would save. Tests: "cd"
then "da", alone and with Enter refused in a recovery (both fail without
the fix).

**Round 1, a loss doesn't end the capture: no change.** A loss under the
menu repaints the page, which stays the one showing, so the capture goes
on with it; a MENU_CLEAR (`screen_open()`) and every close end it. Codex
(round 2): acceptable, no harm identified.

**Round 1's other answers** (no change): every matrix event reaches the
gate before tapping, on USB and BT alike; combos and key overrides are off
in this build; the default layer's lookup, the Mac/Win switch, Shift from
the matrix, the transparent and non-basic codes ignored, the accessor
under NO_ACTION_TAPPING and the rename's writes are sound.

**Mutants** (`p5c_mutants.py`, 28): one survives, an empty slot's rename
check, which `prof_rec_valid()`'s state check also makes.
