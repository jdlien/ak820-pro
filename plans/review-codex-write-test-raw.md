**Hold the flash.**

- **P1 — [wear_leveling.c:328](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:328):** Cleanup erases before unlocking, from `FLASH_STOP`, bypassing the LCD DMA drain. Wrap consolidation in checked unlock/lock.
- **P2 — [menu_glue.c:252](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:252):** The last macro byte is the validity sentinel ([dynamic_keymap.c:149](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/dynamic_keymap.c:149)). Writing `0x55` persistently disables every macro. Choose a spare preceding byte.
- **P2 — [menu_glue.c:258](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:258):** The cap changes before rendering finishes; “Dim + write” writes before the dimmed frame reaches PWM. Wait for its flush.
- **P3 — [menu.c:583](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:583):** Test strings remain unguarded for daily.

No new scan hazard found: [hal_efl_lld.c:336](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:336) masks START-through-BUSY, protecting flash code/const reads; erase scanning already existed. Consolidation blocks ~58 ms baseline; Scan duration is unmeasured, versus ~12 s watchdog. Sleep cannot interleave; [DSB_FLASH](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:253) remains. Normal dim [release paths](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1932) look correct.

Static review; execution denied.