No new flash blocker found.

[menu.c:1318](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1318) and [1410](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1410) correctly shift lead, split icon, halves and RULE_CHUNK. [l_first:1436](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1436) matches RK_ITEM’s kind/node layout; Clock’s path stays intact. [menu_slots.c:310](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:310) skips only committed rows; partial/invalid rows restart at zero.

[power_bulb.c:73](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/power_bulb.c:73) matches power_bulb_px, including padding, invalid inputs and swapped byte order. Payload remains 392/512 bytes. [Test:1983](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1983) checks four entry bulbs and none on moves.

Static review only: process execution was denied, so builds/tests weren’t rerun.