# Codex's third verify of P3 (the menu's pair failing closed), 10-25

Prompt: `plans/review-prompt-p3-verify3.txt`. Line references are to
`ea91b3d0`. The response: firmware `560689ea`.

## Dispositions

1. **An other-slot ACK after the target's leaves false confidence (must
   fix):** taken. An ACKed select frame sets `select_tx_failed` to whether
   its slot isn't the requested one: the last select through decides.
   `btui.c`'s `target_refused_mixed` (older BT 3 then BT 2 queued, the new
   BT 3 refused, a stale 5B 32): lost, no pair. A mutant with the old rule
   fails it.
2. **LOST doesn't override CONNECTED on a current-slot click (must fix):**
   taken: the click sends nothing only on a select that isn't lost, whether
   it reads connected or linking. `test_p3`: connected on a lost select
   re-selects.

## The review, verbatim

**Yes—fix the remaining wrong-slot pairing path before flashing.** There is also a slot-click recovery bug.

1. **Other-slot ACKs can leave false delivery confidence:** [ch582f_ajazz.c:1479](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1479).

   Concrete sequence: queue older selects **BT3 → BT2**, fill the ring, then request **Pair BT3**. Its new select is refused. A delayed `5B 32` retires `PA_SELECT`. While draining, the older BT3 ACK clears `select_tx_failed`; the following BT2 ACK leaves it clear. Once the queue empties, selection reads ACKED and the menu sends `A6 51` **on BT2**.

   An ACKed other-slot select must invalidate delivery confidence; a subsequent target-slot ACK can restore it. Add this mixed-slot refusal case beside [btui.c:484](C:/Users/jdlien/code/ak820-pro/scripts/ch582_sim/btui.c:484). The existing test fills the queue with polls, so misses it.

2. **LOST does not override CONNECTED for a current-slot click:** [menu.c:1168](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1168).

   At boot, all target selects can give up, a poll ACK can stop cold-boot retries, and an old-slot `5B 32` can leave **CONNECTED + LOST**. Clicking the requested slot then says “Already on” without reselecting. Require `!ENV_PF_SEL_LOST` for both CONNECTED and LINKING shortcuts. Pairing’s LOST path already reselects.

The remaining checks:

- **No ACKED while a select remains outstanding:** the scan includes every queued slot and the in-flight head. Simple give-up/refusal paths fail closed.
- **Normal delivered-and-answered reconnects recover:** no permanent LOST/PENDING mechanism found there.
- **Driver equivalence:** `pa`, `conn_state`, and TX queue transitions remain those of `a7c19f85`; the additions only affect observations.
- **Flash:** no additional cable-mode hazard found in this scope. The inspected dev ELF has **136 B**, eight above the floor; recheck after fixes.

Static verification against the exact Git objects and matching test source; process execution was unavailable, so tests were not rerun.