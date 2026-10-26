# Codex: P5e, the settings profiles' preview (2026-10-26)

JD (10-26): "Might be fun to have a way to preview the profile ... or just
preload the profile as the user scrolls over it to preview it"; "Resting
like after between 0.3s to a second or a second probably makes sense so
the board doesn't go crazy as you scroll."

Rounds, verbatim, then dispositions:
1. `plans/review-prompt-p5e-code.txt`: qmk_firmware-ak820pro `94072f55..953e9258`
   (branch `gremlin/p5e`, on P5d).
2. `plans/review-prompt-p5e-verify.txt`: `953e9258..651d23f9`.

## Round 1 (953e9258)

**Yes—fix three P2 regressions before flashing `953e9258`.**

- **A previous preview can become saved settings.** [profiles.c:300](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:300): start with live effect C, preview A, then preview B whose effect ID is unknown. B retains A’s effect. Load skips B’s unknown effect, saves the remaining RGB fields—which dirties the whole RGB configuration—and `me_keep()` discards C’s snapshot. A’s unselected effect becomes persistent. Omitted lighting/LCD fields similarly inherit previous previews. Resolve skipped fields against the original live snapshot, and restore that baseline before applying Load.

- **Previews bypass the 24-second idle close.** [menu_ops.c:162](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:162): `ME_PROFILE` makes `me_active()` true, selecting the **180-second** backstop. The preview remains displayed and deep sleep stays blocked. Exclude profile previews from the editor timeout extension.

- **`pv` becomes stale after Load followed by an external write.** [menu.c:2000](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2000): Load A closes the edit but leaves `pv=A`. Press Next to load B; without an open edit, this produces `ME_PEND_CHANGED`, not `ME_PEND_CANCELLED`. Clicking A then hits `pv_show()`’s equality return and incorrectly keeps showing B. Invalidate the cached slot on external changes even when no edit was cancelled.

Add these cases to [test_preview():4207](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4207).

Otherwise, capture paths cancel previews first; the RGB flush gate and separate saved LCD copy prevent incidental persistence. Saving setters persist equal preview values correctly. Ordinary exits, diagnostics and restore-pop restore live settings; failed Loads retain rollback; Next/Previous cancel open previews. Editor cancellation still independently pops with “Cancelled”. The `*` is displayed after returning to the top level and restoring live settings.

Static review only: process execution was denied, so tests and hardware timing were not rerun. Links use current working-tree lines; an unrelated Save-new optimization changed `menu.c` during review.