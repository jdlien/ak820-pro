- **P2 remains — [menu.c:1994](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1994):** A Ten-writes consolidation can consume the 50 ms without advancing RGB rendering; the dim’s write then precedes its flush. Require a committed frame. The test checks elapsed time only.
- **P1 closed:** checked unlock/drain/relock, [wear_leveling.c:331](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:331).
- **Macro P2 closed:** spare-byte boundary preserves terminators and sentinel, [menu_glue.c:253](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:253).
- **P3 closed:** label/title guards, [menu.c:205](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:205), [menu.c:588](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:588).

No additional findings. Static review; execution denied.