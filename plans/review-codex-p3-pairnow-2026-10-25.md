# Codex on P3 draft 3 (Pair a device pairs the current slot), 10-25

Prompt: `plans/review-prompt-p3-pairnow.txt`. Firmware `d6483b2b`, tests `93a1a50`.

## Dispositions

- **No firmware change.** Cleared for the flash.
- **The board pass with the slider on BT (test runner):** taken.
  `connection()` runs entirely on op 27 sub 16's stand-in now, the off-BT
  page included, so its clicks never reach a real link.

## The review, verbatim

**No firmware change is required before flashing. One board-test adjustment is needed before running the gate with gremlin’s slider on BT.**

- **[scripts/menu_p1a_board.py:160](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:160):** `connection()` requires an off-BT live link, but `check()` only records failure and continues. On BT, the next two clicks open Connection and activate its current-slot row before the stand-in is installed—potentially cancelling pending pairing or issuing a real reselection. Install the USB stand-in before those clicks when live BT is detected, or abort on the unmet precondition. This is a test-runner issue, not a flash blocker.

- **Removed nodes/title:** No executable references remain to `N_PAIRLIST`, `N_PAIR0–2`, or `T_PAIRLIST`. Pairing is node 44, hence screen **60**; both test consumers match. Op 27 derives the ID through [menu.c:1367](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1367).

- **Row and navigation:** [menu.c:538](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:538) puts the latched slot into `val`; painting and the signature both use it. [menu.c:1177](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1177) pairs that slot, re-syncs, moves Connection’s cursor, pushes depth 2→3, and changes layout. Leaving pops directly to Connection. Slider-following and the whole-page backstop remain correct.

- **Slot mismatch:** Input re-syncs before activation ([menu.c:1240](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1240)), eliminating ordinary previous-pass staleness. Any mismatch taking the existing reselection branch remains covered by verify4’s delivery guarantees: pairing waits for the target select, including queued/bounce selects, and fails closed on LOST.

- **Flash:** No new persistent RAM; your **136 B** gap remains **8 B above** the floor. BT-position flashing retains the existing battery-reserve constraint in [flash.sh:177](C:/Users/jdlien/code/ak820-pro/flash.sh:177).

Verified exact Git objects and matching `93a1a50` test sources. Driver and `bt_ui.c` are unchanged. Tests were not rerun because process execution was unavailable.