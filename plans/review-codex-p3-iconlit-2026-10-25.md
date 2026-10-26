# Codex: the selected row's icon tinted (2026-10-25)

Prompt: `plans/review-prompt-p3-iconlit.txt`. Diff: qmk_firmware-ak820pro `1ff3d405..b99d5405` (32314c3f added a palette slot for it; b99d5405 took the slot back, since it cost the dev heap 8 B, 136 to 128, the floor: a first review of 32314c3f was stopped unread). Verbatim below; dispositions at the end.

---

**No mandatory code changes found in the requested net diff.**

- **Repaint:** [menu.c:627](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:627) includes lit in bit 0 for both `RK_ITEM` and `RK_VALUE`. Changed signatures restart the whole row at [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265), repainting the icon with its new colour.
- **One lit row:** [menu_slots.c:294](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:294) prioritizes cleanup and blocks another lit row. `maybe_lit` is set before the first piece and cleared only after complete unlit repaint, covering the icon chunk.
- **Palette unchanged:** MP order/count ([menu.h:36](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.h:36)), seven-entry arrays and setter ([menu.c:142](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:142)), and opcode 27/13 ([menu_ops.c:280](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:280)) match `1ff3d405`.
- **Flash:** No new blocker. Reported 136 B exceeds the 128 B floor. BT flashing uses battery power; retain the existing reserve check ([flash.sh:177](C:/Users/jdlien/code/ak820-pro/flash.sh:177)).

The updated test expectation matches `0xFFB8`. Tests/build were not rerun: process execution was denied.
---

## Dispositions

- No must-fix: flashed as `b99d5405`.
- The reserve check: `flash.sh` keeps it; nothing to change.
- The tests codex could not run: `menu_s0_test` passes, and its oracle fails 137 checks against `1ff3d405`'s menu.c (the lit row's icon white).
- No board pass: the change is a colour in the same chunks and pieces as `1ff3d405`, whose pass is `board-1ff3d405.json`.
