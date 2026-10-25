# Codex: the green check box everywhere and the Pair row (2026-10-25)

Prompt: `plans/review-prompt-p3-green.txt`. Diff: qmk_firmware-ak820pro `2d8512ae..eb00c2ee`. Verbatim below; dispositions at the end.

---

**No must-fix changes found** in `2d8512ae..eb00c2ee` for the specified dev flash on gremlin, slider on BT.

- **Checkbox coverage:** Text and colour share `is_option()`. BT bullets and choice-page `saved_row()` cover Power, Clock, Effect and Lights; Back, blank and value rows remain unsplit. Every rendered checkbox gets `MENU_SAVED`; BT status icons retain their intended colours. [menu.c:560](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:560), [menu.c:677](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:677).

- **Scrolling and scheduler:** Effect scrolling can change a physical row’s split. Its signature includes node, option index, bullet and highlight. The scheduler checks that signature before resuming **or committing**, and resets chunk/piece on replacement. This satisfies C3/C4; footprint and piece bounds remain unchanged. [menu.c:627](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:627), [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265). Preview clicks save and pop; reopening snapshots the new saved option. [menu.c:1144](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1144).

- **Pair row:** The 18-cell label fits, its displayed value stays empty, and its internal slot value remains in the signature. No remaining dependency on `label_of(N_PAIRNOW)` exists in titles, flashes, About or `menu_ops.c`. [menu.c:598](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:598).

- **Memory:** Available dev artifacts confirm unchanged `.data`/`.bss`, the new table in `.rodata`, and **136 B** heap gap versus the **128 B** floor. [build.sh:209](C:/Users/jdlien/code/ak820-pro/build.sh:209).

Reviewed the uncommitted test oracles. C tests and a fresh build were **not run** because process creation is blocked.
---

## Dispositions

- No must-fix: flashed as `eb00c2ee`.
- "The 18-cell label": it is 19 (`Pair device to BT 1`), from cell 0; it fits the row's 20 either way. No change.
- The tests codex could not run: `menu_s0_test` passes both ways (S0 and MENU_ENABLE), and the updated oracles fail 22 checks against `2d8512ae`'s menu.c (the box not green on Power, Clock, Effect and Lights).
