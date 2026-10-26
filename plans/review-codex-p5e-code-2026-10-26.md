# Codex: P5e, the settings profiles' preview (2026-10-26)

JD (10-26): "Might be fun to have a way to preview the profile ... or just
preload the profile as the user scrolls over it to preview it"; "Resting
like after between 0.3s to a second or a second probably makes sense so
the board doesn't go crazy as you scroll."

Rounds, verbatim, then dispositions:
1. `plans/review-prompt-p5e-code.txt`: qmk_firmware-ak820pro `94072f55..953e9258`
   (branch `gremlin/p5e`, on P5d).
2. `plans/review-prompt-p5e-verify.txt`: `953e9258..651d23f9`.
3. `plans/review-prompt-p5e-verify2.txt`: `651d23f9..2ce410e7`.

## Round 1 (953e9258)

**Yes—fix three P2 regressions before flashing `953e9258`.**

- **A previous preview can become saved settings.** [profiles.c:300](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:300): start with live effect C, preview A, then preview B whose effect ID is unknown. B retains A’s effect. Load skips B’s unknown effect, saves the remaining RGB fields—which dirties the whole RGB configuration—and `me_keep()` discards C’s snapshot. A’s unselected effect becomes persistent. Omitted lighting/LCD fields similarly inherit previous previews. Resolve skipped fields against the original live snapshot, and restore that baseline before applying Load.

- **Previews bypass the 24-second idle close.** [menu_ops.c:162](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:162): `ME_PROFILE` makes `me_active()` true, selecting the **180-second** backstop. The preview remains displayed and deep sleep stays blocked. Exclude profile previews from the editor timeout extension.

- **`pv` becomes stale after Load followed by an external write.** [menu.c:2000](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2000): Load A closes the edit but leaves `pv=A`. Press Next to load B; without an open edit, this produces `ME_PEND_CHANGED`, not `ME_PEND_CANCELLED`. Clicking A then hits `pv_show()`’s equality return and incorrectly keeps showing B. Invalidate the cached slot on external changes even when no edit was cancelled.

Add these cases to [test_preview():4207](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4207).

Otherwise, capture paths cancel previews first; the RGB flush gate and separate saved LCD copy prevent incidental persistence. Saving setters persist equal preview values correctly. Ordinary exits, diagnostics and restore-pop restore live settings; failed Loads retain rollback; Next/Previous cancel open previews. Editor cancellation still independently pops with “Cancelled”. The `*` is displayed after returning to the top level and restoring live settings.

Static review only: process execution was denied, so tests and hardware timing were not rerun. Links use current working-tree lines; an unrelated Save-new optimization changed `menu.c` during review.
## Round 2 (651d23f9)

**Two closed; the third remains partially open.**

**P2 — external change plus queued click still bypasses preview.** [menu_ops.c:135](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:135) processes input before `menu_tick()`. Load A, then externally load B and queue a click on A before the next menu pass. [menu.c:646](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:646) returns because `pv == A`; the page opens showing B. The new invalidation at [menu.c:2004](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2004) then sets `PV_HELD`, leaving that page without a preview. Invalidate before dispatching input. The regression test’s [200 ms rest](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4411) hides this ordering; add the immediate-click case.

The other two are closed:

- Snapshot-based preview and baseline restoration before Load are correct, including refused Load: [profiles.c:295](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:295), [menu.c:1816](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1816).
- Profile previews use the 24-second timeout: [menu_ops.c:164](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:164).

**Save new looks sound:** [menu.c:1796](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1796) handles slot 0 and an unformatted block correctly. Success replaces the active bits and clears `*` consistently with capturing live settings; failure marks the snapshot stale without installing a synthetic success.

No additional storage-corruption or flash-safety blocker found. I’d fix the remaining P2 before flashing. Static review only: process execution was denied; tests and changed-build hardware timing were not rerun.
## Round 3 (2ce410e7)

**Yes, P2 is closed.** [menu.c:1914](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1914) invalidates the stale slot before click dispatch, allowing the preview to reopen.

Reading pending bits does **not** consume them: [menu_edit.c:169](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_edit.c:169) only returns `pending`. [menu.c:2006](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2006) still takes and clears them; the cancelled-editor input guard, “Cancelled” pop, and single cancellation retarget remain intact.

[test_preview_codex():4411](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4411) now exercises the immediate click, followed by the after-tick case at line 4420.

**No flash blocker found in this diff.** It adds no static state; your reported 136 B exceeds [build.sh:210](/C:/Users/jdlien/code/ak820-pro/build.sh:210)’s 128 B floor. Static review only: process execution was denied, so tests and hardware timing weren’t rerun.
## Dispositions

**Round 1, [P2] a previous preview can become saved settings: fixed in
`651d23f9`.** `prof_preview()` now builds its target from the ME_PROFILE
edit's snapshot (`me_base()`, the live settings it opened on) with the
record's fields over it, so a field the record lacks, or an effect this
build lacks, shows the live settings' value, never an earlier preview's.
Load puts the live settings back first (`pv_show(PV_LIVE)`) and applies
over them, exactly as with no preview; a refused Load previews again.
`me_keep()` is gone. Tests: test_preview_codex() (a profile without an LCD
field and with Breathing's id after another's preview; its Load saving the
live effect; a refused Load).

**Round 1, [P2] previews bypass the 24 s idle close: fixed in `651d23f9`.**
menu_ops.c takes the 180 s backstop only for an edit that isn't
ME_PROFILE. Test: 25 s idle with a preview open closes the menu, the live
settings back.

**Round 1, [P2] `pv` stale after a Load and an external write: fixed in
`651d23f9`, then `2ce410e7`.** menu_tick() holds the live settings on any
pending change while `pv` names a slot with no preview open; round 2 found
the click queued before that tick (input runs first in a pass), so
menu_input() also ends `pv`'s slot when a change is pending
(`me_pending()`, not cleared). Tests: the click at once after the change
(fails without the fix) and after a tick.

**Round 2's other answers** (no change): the snapshot-based preview and
the baseline before Load, the 24 s close, and Save new's snapshot use
(slot 0, an unformatted block, a failed save) are sound.

**Round 3: closed.**

**Mutants** (`p5e_mutants.py`, 32): three survive, each accepted:
`pv_show()`'s stale mark (every input marks the snapshot stale anyway); the
hold's `me_field()` guard (a narrow same-pass race, harmless either way);
a mode set when unchanged (an animation restart the fakes can't see).
