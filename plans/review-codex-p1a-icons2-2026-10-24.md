# Codex on the squared check, the headings' icons and the cursor's grey (`541a8cbd`), 10-24

Prompt: `plans/review-prompt-p1a-icons2.txt`.

## Dispositions

- **Flashed before this review finished, at JD's word** ("just go ahead and flash it so I can see the new changes now, we can flash another build if we need more changes"). The review then found **no must-fix findings**.
- **The per-pass lit-row watcher ignores the cursor's columns** (a transient second grey cursor would pass): owed, test-only, with the next round of changes.
- **The `MENU_ENABLE` host build doesn't exercise the non-dev branch:** as before, the daily build covers it; to build daily again with the next round.

## The review, verbatim

**No must-fix findings in `541a8cbd`. I’d proceed with the test-board flash.**

- **Geometry is correct:** row chunks cover x **0–3, 4–63, 64–124**. The lead uses stride 1, 14 bitmap bytes, and 112 payload bytes. Text uses stride 8, at most 32 bitmap bytes and 488 payload bytes. Title/confirm chunks remain x **3–63, 64–124**. An in-memory raster comparison found zero mismatches. [menu.c:389](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:389)
- **Scheduling remains sound:** chunk/piece counts are slot-specific; `c_pieces()` correctly maps to title/separator. Unchanged partial targets resume; changed targets restart. Cleanup retains `maybe_lit` until the whole unlit row commits, covering the cursor-only chunk. A full list is now **28 ops**, an ordinary selection move **6**; C9’s fixture remains **27**. [menu_slots.c:257](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:257)
- **Palette and titles check out:** both branches contain index 6; sub 13 accepts it, and sub 14 is gone. Icon-prefixed headings reach at most **16/20 cells**.
- **Codes match:** all `MT_*` agree with the generator/header. The glyph data is exactly the parent’s with the two circled-check halves removed: **116 glyphs, 21 extras**.

Non-blocking test gap: the per-pass [lit-row watcher](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1290) excludes cursor columns and checks only `MENU_LIT`; extending it would catch transient duplicate grey cursors.

Execution was blocked, so I could not rerun C tests or compile firmware. The `MENU_ENABLE` host variant still does not exercise the actual non-dev preprocessing branch.