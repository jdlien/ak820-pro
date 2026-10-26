# Codex: a split row's cells 2-9 in 5-row pieces (2026-10-25)

Prompt: `plans/review-prompt-p3-split5.txt`. Diff: qmk_firmware-ak820pro `1de9df2f..1ff3d405`. Verbatim below; dispositions at the end.

---

**No must-fix changes before flashing this dev build on the keyboard on gremlin.**

- **Coverage agrees.** [menu.c:698](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:698) and [menu.c:738](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:738) produce:
  - Unsplit chunks: **1/4/4 pieces**.
  - Split chunks: **1/1/3/4 pieces**.
  - Lead/icon: `(r0,rows)=(0,14)`; split chunk 2: `(0,5),(5,5),(10,4)`; ordinary halves: `(0,4),(4,4),(8,4),(12,2)`.
  
  Lit/unlit geometry is identical. Enumeration found no gaps or overlaps across x=0–124, y=0–13. Title/confirm halves remain four pieces each.

- **Mid-operation changes restart correctly.** Split-changing row content changes the signature; [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265) rejects stale progress and line 313 resets both cursors. Palette changes explicitly invalidate through [menu_ops.c:280](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:280).

- **Bounds pass.** The new piece uses **480/512 payload bytes** and **30/64 bitmap bytes**. The [new assertion, menu.c:707](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:707), is sound; the preceding assertion already guarantees a nonzero row count. Overall maximum remains 488 bytes.

- **No fixed-four dependency.** [menu_slots.c:221](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:221) counts completed chunks, preserving stops; C10 and the [ring, loop_acct.c:86](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/loop_acct.c:86), measure actual time. Split rows still have four logical ops.

No new flash hazard found. Keep the existing [BT release/drain](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1333) and [battery-reserve guard](C:/Users/jdlien/code/ak820-pro/flash.sh:177).

Exact commits inspected; geometry checked in memory. C tests/build could not run because process creation is blocked. Hardware timing remains unverified.
---

## Dispositions

- No must-fix: flashed as `1ff3d405`.
- "Split rows still have four logical ops": whether a pass's cost follows the piece or the op is what the board's pass on `1ff3d405` settles.
