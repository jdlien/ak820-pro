# Codex on the hint pair and the refused-opener fix (1e84bf17), 2026-10-24

Prompt: [`review-prompt-p1a-hint.txt`](review-prompt-p1a-hint.txt). No fix required; flashed.

## The review, verbatim

**No fix required before the controlled test-board flash.** I found no blocker in `1e84bf17`.

- **Title namespace/signature:** `T_HINT_BACK = 20`, distinct from flashes 16–18 and `T_HINT = 19`. It fits both `title_id`’s byte and the title slot’s 16-bit signature; there is no masking or collision. [menu.c:131](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:131)

- **Timing and latching:** each 6000 ms cycle gives the screen title at 0–3999, Turn at 4000–4999, and Back at 5000–5999. Flashes take precedence until elapsed time reaches 1300 ms, then clear. `menu_tick()` independently checks the desired title, so model changes cannot swallow expiry or phase transitions. Input resets idle; the title updates before painting, and a changed signature restarts any partial title. Choices and other non-list screens remain excluded. [menu.c:600](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:600)

- **Every opener route is sound:** physical and subs 4/11 install the new kind before synchronous opening callbacks. ANIM refusal restores `report_kind` and clears the provisional live kind. PENDING cancellation preserves the accepted pending kind; OPEN closure preserves the closing session’s reporting kind. Physical OPEN closure uses the queued close latch, bypassing kind selection. Immediate reopening replaces stale live kind, and `MI_BUSY` exits before touching either kind. [menu_ops.c:33](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:33), [menu_ops.c:343](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:343)

Optional follow-up coverage: physical ANIM refusal, the reverse fixture→refused-sub-11 case, and exact phase boundaries. Their absence does not justify holding this flash.

I verified the reviewed firmware against the commit’s Git objects. This was static review: process creation was denied, so I could not independently rerun the host tests. All file access stayed inside the requested directory.