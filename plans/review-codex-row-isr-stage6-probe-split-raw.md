Reviewed both diffs. No builds or test suites run.

**P1 — must fix**

| File:line | Finding and failing scenario |
|---|---|
| — | None found. |

**P2 — should fix**

| File:line | Finding and failing scenario |
|---|---|
| [menu.c:1626](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:1626), [menu_slots.c:181](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu_slots.c:181) | **The signature still masks the row index with `3u`.** `PR_TICKS2 == 4` therefore gives signature **0** for uncaptured, unhighlighted `Ticks R = 0`, matching a blank row. Scenario: rapidly navigate from Indicators through Configuration → Diagnostics → Floor probe before intermediate pages repaint row 4. Its committed blank signature matches, so **Ticks R remains missing until selected or invalidated**. Split also aliases Color’s signatures. Allocate collision-free signatures for all five controls, disjoint from blank and other row kinds. Simply widening the mask would overlap Battery’s `0x1000` range. |

**P3 — notes**

| File:line | Finding and scenario |
|---|---|
| [menu.c:2483](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2483), [menu.c:2836](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2836) | **Capture is sound.** Turns precede the click; turns arriving after a latched click are dropped. Captured turns cannot move the cursor onto Split, and Split never sets `editing`. Pointer selection is correct; the NULL fallback returns safely. |
| [menu.c:490](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:490), [menu.c:413](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:413) | **Bounds and storage are sound.** Six rows fit both faces; cursor wraps through 0–5; `row_node()` rejects higher indices. `Color R <Green>` fits Large’s 15 columns. The six-byte probe state remains inside the asserted 12-byte union. |
| [rowisr_diag.c:445](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:445) | **Split rendering is bounded:** 90 lookups, nine holes skipped, all 81 LEDs assigned once. It runs once per completed effect render in thread context without masking interrupts. No timing defect identified; actual cost was not measured. |
| [rowisr_diag.c:490](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:490), [rowisr_diag.py:399](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:399) | **Wire offsets agree:** second colour sent at `[9..11]`, returned/read at `[8..10]`. No other consumer of those reply bytes found. Update the stale four-byte reply description at [rowisr_diag.h:66](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:66). |
| [menu.c:2474](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2474), [panel_owner.c:106](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/panel_owner.c:106) | **Release paths remain sound for split.** Back/hold and session closure release it; Fn+D retains it during Health and releases on return or closure. A newer host-owned pattern survives menu cleanup. |
| [menu_s0_test.c:2008](/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2008) | **Coverage misses P2:** navigation helpers settle every repaint, preventing the intermediate-page scenario. Add that regression in both faces. |

NOT READY