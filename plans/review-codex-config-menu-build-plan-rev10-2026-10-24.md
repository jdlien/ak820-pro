# Codex verification: the build plan, revision 10 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev10.txt`](review-prompt-config-menu-build-plan-rev10.txt). Reviewed: revision 10. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**No. Revision 9 was not ready, and revision 10 still needs three corrections before S1’s code.** I compared `d440c8f` with current HEAD and checked the cited firmware at `4b899118`.

| Disposition | Verification |
|---|---|
| 1. Whole-workload timing | Scope, layout clears and the **>15,000 µs** boundary are corrected. The interval’s reset contract still conflicts with its fields. |
| 2. Debug composition generations | Initial composition is now required, but an update can still be credited with an earlier completion. Loss invalidation also needs reconciliation. |
| 3. Counter and sampling validation | Units, modular uptime and request/reply brackets are improved. Saturation and reset detection remain incomplete. |
| 4. Separate transition rule | **Met.** Successive windows through completion, an additional window, per-kind averaging and the timeout resolve the original finding. |

C4’s revision 9 lifecycle correction remains consistent with the ordering defect in `menu_slots.c`; I found no further lifecycle blocker.

1. **Must-fix before S1’s code — correct the interval’s reset and counter semantics.**

   **Where:** [C10, arm and field layout](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:904), and its counter rules at line 948.

   `arm=1` explicitly zeroes **26–27**, which now contain the supposedly boot-stable `boot_id`. It omits **24–25**, which contain “passes in the interval.” These instructions contradict both field definitions and the protocol summary’s “zeroing its maxima and counts.”

   Also, the interval pass counter **saturates**, while the general rule prescribes modular deltas for u16 counters. Saturation loses subsequent increments; modular subtraction cannot recover them. At the plan’s approximately 220 passes/s, it saturates after **298 seconds**; at the permitted 500/s, after **131 seconds**.

   **Fix:** Reset bytes **6–15, 19 and 24–25**, preserving the boot identity. Explicitly name the source of each validation counter. The simplest choice is health page 2’s **u32 `passes` alongside ge10/ge25**, which are snapshotted together in [health.c](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:195). Treat the saturating interval total as a summary only, or change it to a wrapping counter with bounded sampling.

2. **Must-fix before S1’s code — make debug completion identify the tested update and remain false during repair.**

   **Where:** [C10’s debug completion procedure](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:931).

   “Read `dbg_gen` after the update’s cause” does not establish that composition has processed that cause. For example, a clock second changes while `dbg_gen == dbg_done_gen == 42`; a read before deferred composition still returns 42, and the prescribed wait can succeed immediately. Composition is deferred in [display.c](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:840).

   The rewritten predicate also drops revision 9’s explicit **clear-finished and clean-grid** conditions. After a settled page suffers a loss, its handler consumes the loss, dirties the shadows and restarts clearing without necessarily changing the composed target. The old generation equality can therefore survive while repair is outstanding. See [debug_page_invalidate()](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1232).

   **Fix:** Capture the page/generation **before** the cause and require the corresponding new composition before accepting completion, or expose a cause/composition token. Restore the clear-finished, clean-grid and no-pending-composition requirements, and explicitly invalidate completion on page reset and loss. Preserve final-transfer and pending-loss checks.

3. **Must-fix before S1’s code — use observable reset identity rather than inferring every reset from counter bounds.**

   **Where:** [C10’s boot identity](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:928) and reset-detection rule at line 958.

   A value derived from boot-time uptime and RTC subseconds is **not guaranteed to change across boots**. Those inputs can repeat.

   Likewise, a health reset need not produce an excessive modular delta. If counters are small at the first sample and reset shortly afterward, their subsequent values can exceed the first sample normally. ge10/ge25 can remain zero, pass deltas remain plausible, and the small ISR-count loss can remain within the LED tolerance. [health_reset()](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:178) resets those counters without resetting uptime.

   **Fix:** Specify an observable measurement-session identity that is lost on reboot—such as a boot-cleared armed token—or a boot epoch with defined guarantees. Expose a separate generation incremented by every `health_reset()` and reject changes across the sampled interval. Counter plausibility checks should remain additional checks.

**Note — the numerical targets are meaningful prospective gates; the existing measurements do not prove them all achievable.** No numerical relaxation is required by the evidence:

- The recorded throughput corresponds to roughly **357–417 ms per full repaint**, supporting a **1,000 ms** paced target as plausible, not establishing its worst case. The polled result is specifically **12 toggles per 5 s**. [Results §10](/C:/Users/jdlien/code/ak820-pro/plans/GREMLIN-RESULTS.md:475)
- The sustained ISR ratio is approximately **3678/3726 = 0.9871**, above **0.98**. The **1,000–10,000 ISR/s** and **500 passes/s** plausibility bounds encompass the recorded rates.
- The **500 ms transition thresholds remain unverified**: the recorded transition measurements used **1 s windows**. They cannot establish the minimum over each shorter window.
- Committed-slot progress is an improvement. However, [the scheduler](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:121) restarts a partial slot when `tgen` changes, so some slots still must finish within the approximately **50 ms** target lifetime. Full-fixture throughput alone neither proves nor disproves that. Final settlement within **500 ms** also needs measurement.
- The **15 ms whole-pass** target is intentionally stricter than the prototype’s observed **23–24 ms** maximum. Splitting work and measuring the complete armed workload are necessary to demonstrate it.

Static verification only; no files changed, builds ran or board measurements were taken.
---

## Dispositions (Warren, 10-24): all three accepted, folded into revision 11

1. **The interval's reset and counters: accepted.**
   - `arm` 1 zeroes bytes 6-15, 19 and 24-25.
   - Bytes 24-25 wrap and are a summary only. Validation uses health page
     2's u32 `passes`, ge10 and ge25, snapshotted together in `health.c`.
2. **Debug completion tied to the tested update and false during repair:
   accepted.**
   - **The predicate** has its clear-finished, clean-grid
     (`dbg_dirty`/`cam_dirty`) and no-pending-composition terms back.
   - **A page reset and a loss's invalidation each move `dbg_gen`,** so a
     repair is a new generation.
   - **The script reads `dbg_gen` before the cause,** waits for it to move
     past that value, then for `dbg_done_gen` to equal it. Only causes that
     change the composed target count as tested updates: an op 1, or the
     Camera page's clock second.
3. **Observable reset identity: accepted.** `boot_id` is gone. In its place:
   - **a session token** (bytes 26-27), 0 at boot in RAM cleared at reset,
     set by each `arm` 1 from a boot-cleared counter that skips 0. Reading
     0, or a changed token, ends the session;
   - **a health-reset generation** (byte 28), moved by every
     `health_reset()`. It must not change across an interval.

   The plausibility bounds stay as checks of their own.

**The numbers note:** no change. The targets stand as prospective gates for
S1 to demonstrate on the board, with codex's caveats recorded:
- the 500 ms transition windows haven't been measured yet (S0 used 1 s);
- slots must finish inside a ~50 ms target lifetime during a spin;
- the prototype's 23-24 ms is what the split has to bring down to 15.
