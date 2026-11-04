Reviewed both diffs. No builds or test suites run. No blocking defect found.

**P1 — must fix**

| File:line | Finding and failing scenario |
|---|---|
| — | None found. |

**P2 — should fix**

| File:line | Finding and failing scenario |
|---|---|
| — | None found. |

**P3 — notes**

| File:line | Finding and scenario |
|---|---|
| [menu.c:2462](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2462), [panel_owner.c:106](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/panel_owner.c:106) | **Exits remain sound for either capture.** Back/hold clears capture and releases the pattern; session closure, including idle timeout, releases synchronously. External closure leaves the editing byte, but input is gated and probe re-entry zeroes it. |
| [menu.c:2297](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2297) | **Fn+D retains the existing behavior:** the pattern remains during Health; returning releases it and rebuilds Diagnostics. No capture survives re-entry. |
| [menu.c:2476](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2476) | **Wrap is correct for every `int8_t` turn count.** Integer promotion gives signed sums −128…129; remainder is −2…2, so one conditional `+3` suffices. Arithmetic enumeration confirmed all 768 colour/count pairs. |
| [menu.c:1136](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:1136), [menu.c:1620](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:1620) | **Capture/value changes repaint correctly.** Row index, value, capture and highlight occupy distinct bits: 1,036 distinct signatures across both rows. |
| [menu.c:1466](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:1466), [menu.c:2817](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2817) | **Buffer and navigation are sound.** `<Green>` needs eight bytes including NUL; the complete row fits both faces. Captured turns leave the cursor fixed, so `activate()` releases the same row. No remaining click-cycle assumption found. |
| [menu_s0_test.c:5608](/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:5608) | **Nonblocking coverage gap:** Color tests exercise only ±1 turns. Color-captured hold, external close, Fn+D and idle closure lack dedicated cases; these paths were checked by inspection. |

READY