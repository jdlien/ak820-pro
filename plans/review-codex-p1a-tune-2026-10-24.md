# Codex on the palette/timing build (62bb64f9), 2026-10-24

Prompt: [`review-prompt-p1a-tune.txt`](review-prompt-p1a-tune.txt). No must-fix; flashed.

## The review, verbatim

**No must-fix issue found in `62bb64f9` before the test-board flash.**

- **Palette/build guards:** `#FF9A9A → 0xFCD3` is correct. Daily/fpb/instrumented use the const palette; dev/devfault and host tests get mutation/composition timing. The added instrumentation is excluded from release paths. Saved ELFs confirm **2,312 B daily / 160 B dev**, with dev’s 32 B increase accounted for by palette/timing storage plus alignment.
- **Repaint:** invalidation discards partial work without clearing `maybe_lit`; retargeting starts a fresh target. Old-highlight cleanup ordering and loss recovery remain intact. Confirm’s six slots repaint correctly. Fixture/closed sessions only store the colour; the next menu opening paints it. See [menu_ops.c:274](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:274).
- **Timing:** modulo-16-bit subtraction handles a counter crossing within a piece shorter than one counter period (~349.5 ms). Expansion subtracts accumulated sends correctly. Invalid rectangles return without recording a sample; broken windows still record timing and release the stream correctly. These are independent maxima, so their reported values need not add up. See [lcd_bus.c:429](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:429).
- **Sub 12:** the dispatcher requires 32 bytes; header bytes survive, `[5]` is status, offsets **6/8/10/12/14** hold saturated little-endian microseconds, and `[16..31]` are zero. Arg 1 returns the previous maxima and resets them.

**Verification limit:** process launching was unavailable, so I couldn’t rerun builds/tests or certify every flavour. The inspected ELFs are labelled `22312b44-dirty`, not exact-commit builds. The added host case covers settled palette repaint; partial/loss/confirm and inactive-session behaviour were reviewed by tracing the code.