**No new flash blocker found in `13c5e910..04ce7093`.**

- [menu.c:556](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:556): titles—including Save/Delete confirmations and Rename—retain the Profiles folder. Confirmation content is unchanged.
- [menu.c:1173](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1173): existing node/lit signatures cover the fixed icons, colour and split geometry.
- [menu.c:1243](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1243): each action row becomes four chunks/operations instead of three, but remains **nine paint passes** (`1+1+3+4` versus `1+4+4`), maximum 488 bytes/piece. Labels fit.
- [font_small_mono.h:182](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/res/font_small_mono.h:182): independent BDF reconstruction matched all 136 glyphs and generator codes, including `0xA4–0xA8`. Menu macros and [count assertion](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_text.c:10) agree. Added glyph data is 70 constant bytes; no new RAM buffer.

Process execution was denied: tests and hardware timing weren’t rerun; the 136 B heap gap remains reported.