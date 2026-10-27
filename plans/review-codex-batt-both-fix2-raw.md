Closed: [menu.c:1842](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1842) invalidates slots 4–10 before `push()` and `show()`, matching [Clock’s order:1833](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1833). This forces repaint despite the colliding signature.

[menu_s0_test.c:3504](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3504) covers the quick re-entry regression.

No flash-safety blocker found in this diff for gremlin; no added persistent RAM or synchronous drawing. Host builds weren’t rerun: execution was denied.