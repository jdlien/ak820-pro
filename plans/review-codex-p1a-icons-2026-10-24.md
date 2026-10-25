# Codex on JD's icons (`925f029b`), 10-24

Prompt: `plans/review-prompt-p1a-icons.txt`. Run: `codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh -s read-only`.

## Dispositions

- **No must-fix findings.** Flashed to the keyboard on gremlin.
- **The non-dev branch is not compiled by the host tests** (the `-DMENU_ENABLE` build still defines `MENU_HOST_TEST`): covered by the daily build of `925f029b` (`via-daily-925f029b-20261024-205930`, token `0xf7dd0bd4`), which compiled with no warnings, `check_style` the constant 0. No change.

## The review, verbatim

**No must-fix findings.** I’d proceed with the test-board flash based on this review of `925f029b` and the uncommitted generator.

- **Cursor cleanup is covered.** Every list row—including blank, Help, and About rows—owns x 0–124. Losing `lit` changes its signature; repainting chunk 0 clears x 0–3. Partial targets that change restart from piece 0. Confirm transitions clear and invalidate; returning from another owner clears afresh; loss repair invalidates every slot. I found no path that preserves an unchanged signature after another screen overwrites its lead. [menu_slots.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:257)
- **Geometry is consistent.** Row chunk 0 covers x 0–63; title/confirm chunk 0 covers x 3–63; chunk 1 always covers x 64–124. Both chunks use pieces of 4/4/4/2 rows. Maximum bitmap storage is 32 bytes; maximum pixel payload is exactly 512 bytes. The slot machinery makes no equal-width assumption. [menu.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:366)
- **Lead clipping arithmetic is correct.** Glyph lookup uses line-relative `i`; destination indexing uses `i-c0`. Bands inside, across, and past the lead behave correctly, including widths shorter than the lead. An in-memory translation checked against a per-pixel reference produced zero mismatches across 856,520 cases. [menu_text.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_text.c:31)
- **Codes and generation check out.** Literal boundaries prevent hex-escape extension; icon/check copies supply exactly two non-NUL bytes and preserve `out[20]`. I independently reconstructed all 118 glyphs from the BDF: every bitmap row matches the committed header. Splitting preserves both halves, and the generator’s validation failures occur before output is written.
- **The non-dev branch looks correct.** `check_style` becomes constant zero; the setter and op-27 handler share compatible development/test guards.

Verification limit: process execution was blocked, so I could not rerun the C suites or compile firmware. Also, the `-DMENU_ENABLE` host variant still uses `MENU_HOST_TEST` and runs only `test_menu_enable()`; it does **not** validate the actual non-dev preprocessing branch. [menu_s0_test.c](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2125)