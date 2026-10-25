# Codex: the top level's icons in white (2026-10-25)

Prompt: `plans/review-prompt-p3-white.txt`. Diff: qmk_firmware-ak820pro `eb00c2ee..1de9df2f`. Verbatim below; dispositions at the end.

---

**No must-fix changes before this dev/BT flash.** One nonblocking palette caveat:

- **Coverage:** All eleven top-level entries split: ten `RK_ITEM` rows and Screen’s `RK_VALUE`. No submenu reuses an `icon_of()` node; other row kinds are excluded. [menu.c:47](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:47), [menu.c:678](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:678).

- **Signatures:** `RK_ITEM` embeds the node. `RK_VALUE`’s `which` plus variant uniquely distinguishes its nodes, including Screen. Swapping between icon and plain rows changes the signature; the scheduler checks before resuming or committing and restarts chunk/piece at zero. [menu.c:627](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:627), [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265).

- **Cost:** Eight split rows add eight paint passes and logical operations to a full first-page repaint: **28 → 36 ops**. Pixel payload is unchanged overall; each icon piece is **336 B**, largest piece remains **488 B**, below **512 B**. Work remains one piece per pass; actual hardware timing wasn’t measured here. [menu.c:690](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:690).

- **Zero colour:** Setting `MP_WHITE=0` makes icons inherit the row foreground, so black cannot be selected. This causes no stale-progress hazard through the dev command: it invalidates and retargets. Separating split eligibility from colour would fix that optional tuning limitation. [menu.c:680](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:680), [menu_ops.c:280](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:280).

No new static state or BT/bootloader changes. Reported **136 B** heap gap clears the **128 B** floor by 8 B. [build.sh:209](C:/Users/jdlien/code/ak820-pro/build.sh:209).

Exact commit scope and updated oracle inspected. C tests/build were not rerun: process creation is blocked.
---

## Dispositions

- No must-fix: flashed as `1de9df2f`.
- Cost (28 to 36 ops on a full first-page repaint, one piece a pass): the board's menu pass measures it on `1de9df2f`.
- Zero colour (black can't be picked for the icons through the dev palette): accepted. Black icons on the black background aren't a look anyone wants, and the daily build's palette is const.
- The tests codex could not run: `menu_s0_test` passes both ways, and the updated oracle fails 794 checks against `eb00c2ee`'s menu.c (the icons in the row's colour).
