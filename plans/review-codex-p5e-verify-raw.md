**Two closed; the third remains partially open.**

**P2 — external change plus queued click still bypasses preview.** [menu_ops.c:135](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:135) processes input before `menu_tick()`. Load A, then externally load B and queue a click on A before the next menu pass. [menu.c:646](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:646) returns because `pv == A`; the page opens showing B. The new invalidation at [menu.c:2004](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2004) then sets `PV_HELD`, leaving that page without a preview. Invalidate before dispatching input. The regression test’s [200 ms rest](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4411) hides this ordering; add the immediate-click case.

The other two are closed:

- Snapshot-based preview and baseline restoration before Load are correct, including refused Load: [profiles.c:295](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:295), [menu.c:1816](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1816).
- Profile previews use the 24-second timeout: [menu_ops.c:164](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:164).

**Save new looks sound:** [menu.c:1796](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1796) handles slot 0 and an unformatted block correctly. Success replaces the active bits and clears `*` consistently with capturing live settings; failure marks the snapshot stale without installing a synthetic success.

No additional storage-corruption or flash-safety blocker found. I’d fix the remaining P2 before flashing. Static review only: process execution was denied; tests and changed-build hardware timing were not rerun.