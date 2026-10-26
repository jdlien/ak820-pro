**Yes—the P2 is closed in all three named paths. No new static blocker for gremlin’s flash found.**

- Host writes fit every stacked Profiles frame and request a retarget: [menu.c:1969](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1969).
- Returning from a slot reselects it if valid, then fits regardless of validity: [menu.c:1565](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1565).
- Delete fits after its two-frame pop: [menu.c:1840](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1840).

Other frames are untouched; Profiles always has at least Back and Save new, preventing underflow: [menu.c:628](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:628).

Snapshot ordering is correct: host writes and input mark it stale before fitting; `row_count()` refreshes through `pfs_get()`: [menu.c:589](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:589), [1866](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1866). Retargeting remains outside scans; menu processing precedes the pump: [ak820pro.c:607](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:607).

One coverage gap: the added regressions don’t exercise host deletions under **Delete confirmation**: [menu_s0_test.c:4055](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4055).

Tests were inspected, not rerun—process execution was denied. The patch adds no static RAM; the reported 136 B heap gap does not establish runtime stack or timing margin.