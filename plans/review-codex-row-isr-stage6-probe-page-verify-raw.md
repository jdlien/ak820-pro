Reviewed `bbf5d6069e..b9f892460d` and the specified host diffs. No builds, tests, or board commands run.

- **P1 — resolved.** [panel_owner.c:106](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/panel_owner.c:106) releases synchronously before changing the session. Exit, top-level Back, the 60-second timeout, op 27 sub 11, sub 6 disarm, the physical opener and wake-release closure all reach `do_close()`. `cancel_pending()` needs no release: PENDING is entered before any page opens. The opening backstop at [menu.c:2276](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2276), diagnostics return and per-pass cleanup remain sound. [menu_s0_test.c:5627](/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:5627) now checks immediate release, immediate reopening and no subsequent duplicate release.

  The `menu.h` include at [panel_owner.c:8](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/panel_owner.c:8) is actually unconditional; the call and declaration are guarded. This is sound for board and `MENU_HOST_TEST`: its header chain contains standard types and the pure `menu_input.h`/`panel_owner.h`, protected by `#pragma once`.

- **P2 — resolved.** [rowisr_diag.c:417](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:417) records the latest setter; release checks that owner. [menu_glue.c:255](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu_glue.c:255) consistently sets/releases `ROWISR_PAT_MENU`. The requested sequences are correct:

  | Sequence | Result |
  |---|---|
  | Page sets → host sets → page leaves | Host pattern remains |
  | Host sets → page enters/sets → page leaves | Menu pattern released; overwritten host pattern is not restored |
  | Page sets → host off → page leaves | Off sets owner to 0; later menu release does nothing |
  | Page sets → host takes over/off → page changes colour/ticks | Page reacquires ownership; its subsequent exit releases it |

  Invalid host indices preserve the standing pattern. Repeated cleanup cannot cancel a later host write. The no-RGB stubs at [rowisr_diag.c:441](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:441) match both declarations, and sub 3 remains RGB-guarded.

- **P3 — prompt corrected; nonblocking notes remain.** [rowisr_baseline.py:299](/Users/jdlien/code/ak820-pro/scripts/rowisr_baseline.py:299) no longer directs the operator to the retired page. One clarification: profile keys and host settings restores **do not close Floor probe**. They cancel ordinary previews ([profiles.c:573](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/profiles.c:573), [profiles.c:955](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/profiles.c:955)); the probe remains until a real exit. The earlier rendering, capture, bounds, storage, title-ID and sleep conclusions stand. Coverage still lacks host takeover in the fake ([menu_s0_test.c:1445](/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1445)) and probe rendering beyond Small. No remaining blocking finding identified.

READY for a flash of the dev and devprobe flavours.