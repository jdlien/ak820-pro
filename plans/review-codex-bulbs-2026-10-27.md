# Codex: the Power page's bulbs (2026-10-27)

JD (10-27): "use the power mode icons that we show on the battery row, right
aligned on the right edge"; the mock-up: "looks great, this would look nice
and help anchor the icons to the modes for users ... Do it when your current
task is done." qmk_firmware-ak820pro `33d6d4ae..a5d9171c` (branch
`gremlin/os-profiles`). The prompt: `plans/review-prompt-bulbs.txt`; the raw
reply: `plans/review-codex-bulbs-raw.md`.

## The reply, verbatim

No new flash blocker found in static review.

[Battery rendering](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1829) preserves all 728 bulb pixels, colours and geometry. [Chunk handling](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1292) correctly uses four chunks, five when split; `l_pieces`/`l_paint` agree and `RULE_CHUNK` remains distinct. Signatures cover mode/split changes; [l_first](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1428) remains Clock-only.

The [bulb transfer](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1405) is synchronous, uses existing scratch, and sends 392/512 budgeted bytes; text stops at x110. Artifact hashes and 136 B heap gap verified. [Pixel checks](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1972) reviewed; tests/build weren’t rerun because process execution was denied. Hardware pass timing remains unmeasured.

## Dispositions

- **No blocker:** flashed (`via-dev-a5d9171c-20261027-103954`, token
  `0x894fb5c1`, heap gap 136 B).
- **The pass timing on the hardware:** measured, the menu's pass and a look
  at the Power page (GREMLIN-RESULTS §20y).

## The board's measure, and the speed-up

`a5d9171c` on the board (GREMLIN-RESULTS §20y): the bulb's piece 9.7 ms
against a text piece's 6, the Power page's longest pass 18.7 ms, and a move
between two bulbs' rows ~340 ms against ~230 (both rows' bulbs repainted).
`ce3f842d`: power_bulb_row() fills a row with its colours looked up once;
the bulb is its row's first chunk, and l_first() skips it while the row
stays the same option. The prompt: `plans/review-prompt-bulbs-fix.txt`; the
raw reply: `plans/review-codex-bulbs-fix-raw.md`.

## Codex's check of the speed-up, verbatim

No new flash blocker found.

[menu.c:1318](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1318) and [1410](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1410) correctly shift lead, split icon, halves and RULE_CHUNK. [l_first:1436](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1436) matches RK_ITEM’s kind/node layout; Clock’s path stays intact. [menu_slots.c:310](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:310) skips only committed rows; partial/invalid rows restart at zero.

[power_bulb.c:73](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/power_bulb.c:73) matches power_bulb_px, including padding, invalid inputs and swapped byte order. Payload remains 392/512 bytes. [Test:1983](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1983) checks four entry bulbs and none on moves.

Static review only: process execution was denied, so builds/tests weren’t rerun.

### Disposition

- **No blocker:** flashed (`via-dev-ce3f842d-20261027-105808`, token
  `0x59b75946`, heap gap 136 B); its timing in GREMLIN-RESULTS §20y.
