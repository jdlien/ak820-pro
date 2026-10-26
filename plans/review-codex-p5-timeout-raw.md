No new flash blocker in `553108e5..1f3c79e9`.

- [menu_ops.c:167](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:167): 32-bit timeout; fixture/profile preview 60 s; editors/Pairing/Rename retain 180 s.
- [menu_ops.c:189](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:189), [menu.c:2161](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2161): reported fields and hints introduce no timing hazard.
- [sleep.c:273](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:273), [display.c:3066](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3066): menu and unfinished restore block sleep.
- [power.c:66](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:66): Lights out already sleeps at 60 s.
- [menu_s0_photos.py:10](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_photos.py:10): stale “24 s” comment; 15 s keepalive remains safe.

Generated Help matches. Builds/tests weren’t rerun: process execution denied.