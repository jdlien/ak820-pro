# Codex: the dev Write test (2026-10-27)

JD (10-27): "if you have ideas you want me to test with my human eyeballs
(and optionally, high speed camera) ... we can add a suite I can trigger
from the cool new menu system". qmk_firmware-ak820pro `ce3f842d..3a661db1`
(branch `gremlin/write-test`), then the fixes `3a661db1..920ad3f2`. The
prompts: `plans/review-prompt-write-test.txt`,
`plans/review-prompt-write-test-fix.txt`; the raw replies:
`plans/review-codex-write-test-raw.md`,
`plans/review-codex-write-test-fix-raw.md`.

## The first reply, verbatim (3a661db1)

**Hold the flash.**

- **P1 — [wear_leveling.c:328](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:328):** Cleanup erases before unlocking, from `FLASH_STOP`, bypassing the LCD DMA drain. Wrap consolidation in checked unlock/lock.
- **P2 — [menu_glue.c:252](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:252):** The last macro byte is the validity sentinel ([dynamic_keymap.c:149](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/dynamic_keymap.c:149)). Writing `0x55` persistently disables every macro. Choose a spare preceding byte.
- **P2 — [menu_glue.c:258](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:258):** The cap changes before rendering finishes; “Dim + write” writes before the dimmed frame reaches PWM. Wait for its flush.
- **P3 — [menu.c:583](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:583):** Test strings remain unguarded for daily.

No new scan hazard found: [hal_efl_lld.c:336](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:336) masks START-through-BUSY, protecting flash code/const reads; erase scanning already existed. Consolidation blocks ~58 ms baseline; Scan duration is unmeasured, versus ~12 s watchdog. Sleep cannot interleave; [DSB_FLASH](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:253) remains. Normal dim [release paths](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1932) look correct.

Static review; execution denied.

## Dispositions (920ad3f2)

- **P1, fixed:** `wear_leveling_consolidate()` takes `wear_leveling_unlock()`
  and `wear_leveling_lock()` as `wear_leveling_write()` does.
- **P2 the sentinel, fixed:** the write goes to the byte before the last,
  refused unless the sixteen terminators lie before it.
- **P2 the dim's flush, fixed by the clock:** the write waits 50 ms after
  the cap (a two-phase wait); the host test fails a mutant without it.
- **P3, fixed:** the label and titles under `MENU_WTEST`.

## The check, verbatim (920ad3f2)

- **P2 remains — [menu.c:1994](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1994):** A Ten-writes consolidation can consume the 50 ms without advancing RGB rendering; the dim’s write then precedes its flush. Require a committed frame. The test checks elapsed time only.
- **P1 closed:** checked unlock/drain/relock, [wear_leveling.c:331](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:331).
- **Macro P2 closed:** spare-byte boundary preserves terminators and sentinel, [menu_glue.c:253](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:253).
- **P3 closed:** label/title guards, [menu.c:205](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:205), [menu.c:588](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:588).

No additional findings. Static review; execution denied.

## Dispositions (the check)

- **The remaining P2:** judged a test's timing, not a safety matter, and
  `920ad3f2` flashed with JD told not to start Dim + write during Ten writes.
  The smoke test passed (`history/config-menu-p3-20261025/wt-smoke-920ad3f2.json`).
  **Fixed in `4ee668eb`:** the dim's step, now Dim + cleanup, waits for two
  frames committed after the cap (`sn32f2xx_led_commits()`) as well as
  50 ms, and stops the ten writes; the host test holds the frames for 2 s
  and the cleanup waits (mutants without the frame wait, without the 50 ms,
  and without stopping the ten all fail). Reviewed with the early cleanup:
  `plans/review-codex-flash-tidy-2026-10-27.md`.

## What JD saw

One write and Ten writes: "zero flicker" under either strategy. Cleanup
under Blank "a very noticeable flicker", under Scan "a more subtle
flicker" (plans/BACKLOG.md, "The LED blink at an internal-flash write").
