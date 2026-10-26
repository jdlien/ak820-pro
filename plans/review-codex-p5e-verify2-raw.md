**Yes, P2 is closed.** [menu.c:1914](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1914) invalidates the stale slot before click dispatch, allowing the preview to reopen.

Reading pending bits does **not** consume them: [menu_edit.c:169](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_edit.c:169) only returns `pending`. [menu.c:2006](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2006) still takes and clears them; the cancelled-editor input guard, “Cancelled” pop, and single cancellation retarget remain intact.

[test_preview_codex():4411](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4411) now exercises the immediate click, followed by the after-tick case at line 4420.

**No flash blocker found in this diff.** It adds no static state; your reported 136 B exceeds [build.sh:210](/C:/Users/jdlien/code/ak820-pro/build.sh:210)’s 128 B floor. Static review only: process execution was denied, so tests and hardware timing weren’t rerun.