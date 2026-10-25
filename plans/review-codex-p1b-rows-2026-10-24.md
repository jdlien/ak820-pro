# Codex on the row-fill change (`07b51f58`), 10-24 night

Prompt: `plans/review-prompt-p1b-rows.txt`.

## Dispositions

- **No must-fix.** Flashed to the keyboard on gremlin; the board script measures the hue editor's passes (GREMLIN-RESULTS §20e).

## The review, verbatim

**No must-fix findings in `07b51f58`; I’d proceed with the test-board flash.** Reviewed against parent `04adb63f`; all five changed working files match the commit.

- **Scratch:** [lcd_blit_rows](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:454) limits rows to 128 pixels in a 256-halfword scratch. It flushes before insufficient space, permits an exact fit, passes the current `p`, then advances by `w`. Both callbacks initialize all `w` halfwords and stay within that span. Synchronous lifetime and failure cleanup remain correct.
- **Byte order:** [MB_PANEL](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_backend.h:34) matches `lcd_blit_mono`’s LUT swap. Palette and strip colours arrive pre-swapped; black remains zero. The [host fake](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:139) correctly unswaps them into RGB565.
- **Envelope:** [env_row](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:724) always receives `w == 8`, so copying/clearing 16 bytes is correct. Precomputed zeros preserve the strip’s horizontal margins; copying occurs only on rows 22–35. Signed `rel` and `rel + d` checks correctly clip the line and 5/3/1 triangle across band boundaries.
- **Bar/integration:** `bar_row` preserves outline precedence and fill logic, including the final six-column band. Callback types and forwarding agree; no stale API references appeared in board sources or scripts. Payload sizes and context lifetimes are unchanged.

Independent JavaScript enumeration matched all **6,056 band/value cases** and checked all **16,384 valid width/height combinations** for scratch batching. These were models, not compiled C tests: process execution was denied, so I could not rerun builds or the host suite.

The timing improvement still needs board measurement; the prior P1b acceptance items remain outstanding. No files changed.