**Yes—one P2 remains before flashing.**

- **[P2] Flush still reports success after a deferred failure.** At [profiles.c:493](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:493), the latch is checked only when `pend` is nonzero. But `write_active()` clears `pend` **before** attempting the write. Therefore: load another slot → `prof_tick()` fails → sub 6 returns `PROF_OK`. A second flush after a failed flush likewise returns success. Check the failure latch independently of `pend`; clean/no-pending should remain OK. Add assertions after the failed settle and repeated flush in [profiles_test.c:555](/C:/Users/jdlien/code/ak820-pro/scripts/profiles_test.c:555), before resetting.

`apply_live()` treating that error as failure is correct: cache readback cannot prove persistence. A full block restore already refuses a latched board at Begin; a normal firmware flash/reboot clears the RAM latch.

The menu half closes the original finding: [menu.c:1878](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1878) reports the failure, including at the next open because closed-menu processing does not consume the edge.

The profile-name overwrite is fixed. There is a **nonblocking feedback regression** at [param_overlay.c:191](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:191): reprime absorbs an NKRO toggle before the next poll. NKRO itself still changes correctly. An immediate RGB-only baseline refresh would preserve that notification and subsequent RGB adjustments.

No other static blocker found in the exact four-file range. Tests were inspected, not rerun: process execution was denied.