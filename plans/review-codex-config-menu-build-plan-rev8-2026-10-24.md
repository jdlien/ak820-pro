# Codex verification: the build plan, revision 8 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev8.txt`](review-prompt-config-menu-build-plan-rev8.txt). Reviewed: revision 8 (`caebe72`). Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Revision 8 is not ready for S1 code yet.** The intended design is largely sound, but four contract gaps remain.

| Disposition | Verification |
|---|---|
| 1. Logical operations and pieces | Substantially adopted; termination/stop ordering needs clarification below. |
| 2. Budget scope and clears | Correct separation and band advancement rules; conflicting older stream wording remains. |
| 3. Whole-pass timing | Target, workload qualification, clock guards and encoder requirement adopted; measurement/readout contract incomplete. |
| 4. Fn semantics | Satisfied. |
| 5. Menu keycode | Adequate for S1; implementation and remaining control-mapping details stay in P1. |
| 6. Executable LED gate | Incomplete: observability and numerical acceptance rules are missing. |
| 7. Polling hardening | Satisfied, including polling-specific failure tests. |
| 8. Corrections/status | The requested stop-frame geometry and timing corrections are incorporated. A4 is closed; S0’s recorded exceptions remain accepted. |

Only the changes required before S1 code follow.

1. **Must-fix before S1’s code — finish the piece/stop lifecycle contract.**

   **Where:** [C3’s dispatch rule](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:552), [C4’s piece and stop rules](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:622), and [stream rules](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:667).

   “Stops after op `n` ends … as now” hides an ordering problem in the existing scheduler. A synchronous operation increments `ops`, but `stopped` is latched on a later `ms_step()`. Navigation runs before that pump and can call `new_target()`, which cancels the still-pending stop and resets the count. Thus navigation immediately after the final piece can discard a stop whose operation already finished. See [menu_slots.c](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:48).

   **Fix:** Require terminal bookkeeping—count once and latch a reached stop—before retargeting or loss invalidation can discard operation state. State that an unfinished stop is superseded by retargeting, whereas a reached stop survives navigation and loss, including pausing a newly requested clear. Document the existing fresh-open/return release exception separately from release by sub 0.

   Also reconcile the terminology: a logical **operation/chunk** may span passes; a CPU-fed **piece** opens and closes its stream within one pass. Replace the old “every chunk … within one pass” wording. Qualify the DMA exemption as **flash glyphs and layout/restore/debug clear bands**, and remove those clears from the generated-stream example.

   Keep slot progress distinct from clear progress: navigation resets the slot’s operation and piece cursors but preserves an ongoing clear sweep. Add boundary tests immediately before and after final-piece termination, including failure, navigation and a stopped clear. C9’s 27 operations, reference frames and stop positions can remain unchanged.

2. **Must-fix before S1’s code — define timing fields and retained maxima.**

   **Where:** [C4’s measurement requirements](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:650), [op 27 bytes 26–27](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1029), and [S1’s maxima requirement](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1144).

   Once an operation spans passes, “last paint operation’s time” could mean its last piece, accumulated execution time, or elapsed latency including intervening passes. These are different measurements. “Maxima are kept over the run” also does not specify where they are retained or how the script obtains them; polling the last-value field cannot provide that guarantee.

   **Fix:** Define the precise interval represented by bytes 26–27, including asynchronous completion, failures and abandoned operations. Separately specify retained piece-cost and whole-pass maxima, their reset scope and readout, plus repaint latency. Preserve byte 29 as the logical-operation count and byte 30 as the latched stop. Document any additional dev sub/page rather than silently changing existing fields.

3. **Must-fix before S1’s code — provide observable completion and progress rules for the LED tests.**

   **Where:** [op 27 completion semantics](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:989) and [S1’s LED completion rules](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1163).

   The gate requires Health/Camera transitions to finish, but op 27 explicitly provides no debug-page completion signal. Owner `DEBUG` and an idle bus do not establish that the clear and dirty cells finished. Likewise, synthetic mutation outcomes do not account for render targets superseded by physical spins.

   Final settlement alone also permits no useful painting throughout a spin, followed by a quick repaint after it stops—despite the stated requirement that “painting barely moving” fail.

   **Fix:** Specify a script-readable completion contract for the selected debug page and its composed target: clear finished, target painted, final DMA finished, no pending loss. Define how target creation, completion and supersession are observed during spins, and a measurable progress requirement while input continues. Require correct final input state and bounded final settlement after input stops. Keep MENU’s existing current-target `pixels_done` meaning intact.

4. **Must-fix before S1’s code — turn the LED failure list into numerical, scoped checks.**

   **Where:** [S1’s executable gate](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1157).

   “Within its deadline,” “within a bound,” “short windows,” and board/host time “disagreeing” still require the script author to invent acceptance criteria. The 0.98 ratio is concrete; these other conditions are not.

   **Fix:** Specify values—or mandatory run parameters fixed before measurement—for settlement deadlines, continuous-spin progress/final settlement, transition-window duration and repetitions, and timebase tolerance. Choose a transition acceptance rule, whether per-window ratios or bounded row-start gaps.

   Define counter checks using measured-interval deltas, allowing legitimate wrap but rejecting resets or unusable samples. Account for HID sampling uncertainty in board/host timing comparisons. Every settlement timeout must fail, whether logged or otherwise. Enforce the ≤15 ms supported-workload target using retained maxima as well as zero ≥25 ms passes.

This was static verification of the requested Git trees and current repository files. Process creation was unavailable; no builds or board tests were run.
---

## Dispositions (Warren, 10-24): all four must-fixes accepted, folded into revision 9

1. **The piece and stop lifecycle: accepted.** Confirmed in the code first:
   `paint_chunk()` bumps `ops` for a synchronous op, but `stopped` latches
   only on the next `ms_step()`, and navigation in between runs
   `new_target()`, which cancels the reached-but-unlatched stop
   (`menu_slots.c:48-56,88-93,110-115`). Revision 9's C4:
   - **one end-of-op helper** counts the op and latches the stop in the same
     step. It runs at the op's end and at the top of `new_target()` and of
     loss invalidation;
   - **the stops:** an unreached stop is superseded; a reached one survives
     navigation and losses and holds a new clear paused. Its two releases
     are documented apart (sub 0, and a fresh opening or return);
   - **the cursors:** slot progress is apart from clear progress;
   - **the words:** "op" against "piece" throughout. The stream rule says
     piece, and clears are out of the generated example. The DMA exemption
     is named exactly: flash glyphs and the layout, restore and debug clear
     bands;
   - **host cases** just before and after the final piece's end, with a
     failure, navigation and a stopped clear.
2. **The timing fields: accepted.**
   - **Bytes 26-27** are now a logical op's latency, first piece's start to
     its end, passes between included. A failed op updates it; an
     abandoned one doesn't.
   - **The maxima live in a new op 27 sub 10** (C10): piece cost, op
     latency, the whole pass with its count of 15 ms passes, the repaint
     latency, and the clear-band time. A reset zeroes those only.
   - Bytes 29 and 30 are unchanged. A1's unknown-sub check moves from 10
     to 31.
3. **Completion and progress: accepted.**
   - **`debug_done`** in sub 5's byte 31, bit 0: clear finished, no dirty
     cell, no transfer, no loss pending.
   - **Target counters in sub 10:** `tgen`, settled and superseded, so a
     spin's books can be balanced.
   - **The spin rules:** a settled target in every 500 ms of a burst, the
     final cursor right, and the final target settled within 500 ms.
     `pixels_done` keeps its meaning.
4. **Numbers: accepted** (C10, fixed before measurement):
   - 1,000 ms for a paced repaint;
   - transitions ten times in 500 ms windows, each at least 0.95 and the
     mean at least 0.98;
   - the timebase within 2% plus 25 ms;
   - counter deltas mod 2^32 or 2^8, with a reset, a delta over twice the
     host's, or a stuck ISR count failing the run;
   - a ratio over 1.01 failing as a configuration error;
   - the longest pass 15 ms or less from sub 10's retained maximum, and
     ge25 0;
   - every timeout fails.
