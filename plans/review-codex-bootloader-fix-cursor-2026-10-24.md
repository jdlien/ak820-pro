# Codex on the bootloader fixes (`6a1dd119`) and the cursor bar (`781d071f`), 10-24 night

Prompts: `plans/review-prompt-bootloader-fix.txt`, `plans/review-prompt-cursor-bar.txt`.

## Dispositions

- **Both: no fix.** Flashed together (`781d071f`). The triangle's mentions in comments and the design prose: tidied with the next design-doc pass.

## The bootloader fixes, verbatim

**Yes—all three fixes are right.** I reviewed `6a1dd119`, directly after `077ab77c`, and found no new issue requiring a fix before flashing.

- **Bootloader:** [Preparation and failure handling](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:99) match `HC_BOOTLOADER`: clear, fresh releases, drain, then splash/reset only on success. Failure leaves the confirmation page usable with “Try again.” Omitting the idle guard is appropriate for physical knob confirmation.
- **Scrollbar:** [The clamp](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:531) affects both the signature and drawing without changing list navigation. Exit’s thumb is now correctly at **y=27–126**.
- **Reserve:** `battery_on_battery() && power_lights_cut()` matches `flash.sh`’s predicate.

The host-test source includes the updated boolean stub, refusal-page assertion, and second-page thumb checks. All five changed firmware files match the commit.

This is a source-review verdict: process launching was denied, so I couldn’t rerun tests or the build. No files changed.
## The cursor bar, verbatim

**No required fix found before flashing.**

- Keep the **4-px lead**: the bar fits at x=0, text stays at x=4, and the whole lead is repainted, clearing unused pixels. Signatures track row state, not glyph shape.
- The shape assertion already expects the bar; rendering checks use the generated glyph ([test:997](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:997)).
- The one-cursor watcher scans **all 14 rows and x=0–2** for `MENU_CURSOR`, so it detects the bar correctly ([watcher:1396](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1396)).
- Some comments/design prose still describe a triangle; cleanup is optional.

Reviewed commit `781d071` and current sources. Tests weren’t run: process launch was denied.