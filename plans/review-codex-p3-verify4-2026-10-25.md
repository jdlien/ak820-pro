# Codex's fourth verify of P3: cleared for the flash, 10-25

Prompt: `plans/review-prompt-p3-verify4.txt`. Firmware `560689ea`, tests `a509882`.

## Dispositions

- **No must-fix.** The intentional failure states codex names (a module that
  never ACKs stays pending; a boot whose selects all fail stays lost after a
  poll's ACK stops the boot retry) are recoverable by a re-select, which the
  menu's slot click now does on a lost select. A live link whose delivery
  evidence was lost can be re-selected by a click: intended.

## The review, verbatim

**No further must-fix found before the dev/cable flash**, within this scope.

1. **Pairing:** [ch582f_ajazz.c:1481](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1481) now makes an other-slot ACK invalidate confidence and a subsequent requested-slot ACK restore it. [Line 1698](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1698) includes the in-flight head and every queued select. Combined with [bt_ui.c:204](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:204), I found no remaining path sending the menu’s pair to a slot other than the last selected target.

   Normal ACKed-and-answered boots/reconnects recover. A module that never ACKs can remain PENDING; a boot whose selects all fail can remain LOST after a poll ACK stops boot retries. Those are intentional failure states, recoverable by reselection.

2. **Slot click:** [menu.c:1169](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1169) preserves the no-select shortcut for current CONNECTED/LINKING states unless LOST. Only CONNECTED+LOST gains reselection. A physically live link with lost delivery evidence can therefore be reselected, intentionally; a normally confirmed live link is unaffected.

3. **Flash:** No additional cable-mode hazard found. These edits add no persistent RAM. Your **136 B** heap gap remains **8 B above** the stated floor.

Verified the exact firmware Git objects and matching `a509882` test sources, including `target_refused_mixed` and CONNECTED+LOST coverage. Tests were **not rerun** because shell execution was unavailable.