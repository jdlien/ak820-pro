# Codex on JD's first-look changes (22312b44), 2026-10-24

Prompt: [`review-prompt-p1a-jd1.txt`](review-prompt-p1a-jd1.txt). No must-fix; flashed. Its qualification (an interrupted transition's partial resumption and the highlight cleanup come before the scrollbar) is as designed.

## The review, verbatim

**No must-fix issue found in `22312b44`; I would proceed with the controlled test-board flash.**

- **Slots:** signatures, chunk/piece counts, painting and row-coordinate arithmetic consistently use the new indices. `L_LIST` and About’s invalidation cover exactly **3–10**. The scrollbar is outside the one-lit-row range, so odd scrollbar signatures cannot become highlights. Confirm still safely delegates only slots **0 and 1**; its text-piece calculation cannot accidentally use scrollbar geometry. [Slot handling](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:301)
- **Signature and colour:** confirmed—`node` already distinguishes Back/Exit, and `lit` distinguishes selection. No additional signature field is needed. Selected leave rows remain yellow; unselected ones use `MENU_LEAVE`. `0xE410` correctly encodes `#E08080` in RGB565. [Signature](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:272)
- **Text bounds:** cell 0 holds bullet/space, cell 1 retains its initialized space, and labels start at cell 2. “Power saver” occupies cells **2–12**. Option labels truncate safely to **18 cells**, preserving the terminator at index 20; no current option truncates. [Text composition](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:237)
- **Regression:** the new check observes the moved thumb while row 0 still contains its old text, before settling—appropriate coverage of the requested ordering. [Test](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1700)

One qualification: existing partial-slot resumption and highlight cleanup retain priority over ordinary ascending-slot painting. Thus scrollbar-first is not unconditional during an interrupted transition; that is not a flash blocker.

I verified the commit through local Git objects and confirmed both changed files match. This was static review: process creation was denied, so I could not independently rerun the reported passing tests. All file access stayed inside the requested directory; nothing was changed.