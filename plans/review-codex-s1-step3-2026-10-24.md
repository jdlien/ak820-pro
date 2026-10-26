# Codex review: revision 13 and the gate's first fixes (2026-10-24)

Prompt: [`review-prompt-s1-step3.txt`](review-prompt-s1-step3.txt). Reviewed: the build plan's revision 13 and `gremlin/s1` `f1c2dcf7`. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Safe to flash `f1c2dcf7` to gremlin’s test board for testing; I found no flash-safety blocker. Revision 13’s signature-only resume rule is sound for pixel correctness. However, its operation-accounting implementation and some gate checks need fixes before accepting a C10 result.**

I compared the specified commits through local Git objects and confirmed the reviewed files match HEAD. Process execution was unavailable, so I did not independently run the C tests, rebuild, or exercise hardware. All file access stayed inside the repository.

1. **Should-fix — a resumed operation is timed from its resumed suffix.**  
   [menu_slots.c:159](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:159), [plan:694](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:694).

   Paint one piece of a four-piece half-row, then retarget another row while this slot’s signature stays unchanged. `new_target()` clears `op_started`; the next `paint_piece()` sets it again and starts a fresh timer. The operation’s eventual end updates `last_op_ticks` and potentially `op_max_ticks` with **only the suffix’s latency**.

   That contradicts revision 13’s explicit “counted when it ends, but not timed.” The synchronous operation still counts once, but its timing is misleading.

   **Fix:** distinguish operation progress from timing validity. A retarget invalidates the current operation’s timing origin; resuming a later piece must not establish another origin. Timing starts again at the next genuinely new operation. Test unchanged-signature retargets at every piece boundary, checking the counters and timing **after completion**. The existing test at [menu_s0_test.c:851](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:851) checks immediately after retargeting and misses this.

2. **Should-fix — retargeting during a glyph DMA drops its completion accounting.**  
   [menu_slots.c:96](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:96).

   Arm a title glyph, then retarget the selection while that DMA remains busy. `settle_ops()` cannot settle it yet, but `new_target()` clears `ops_inflight`. The title signature remains unchanged, and its chunk cursor already advanced when the glyph was armed. Revision 13 therefore resumes at the next glyph.

   The retained glyph eventually lands correctly, but its operation is never counted at completion, and its DMA piece timing is lost. Previously, restarting the title obscured this by sending the glyph again.

   **Fix:** retain the pending completion record for work whose progress survives the retarget. Settle it exactly once, with operation timing invalidated as required, while preserving the pending-stop cancellation rule. Add a test that retargets **before** `dma_settle()`, then checks the operation increment and piece timing.

3. **Should-fix — the gate retries state-changing commands as though they were reads.**  
   [menu_s1_gate.py:142](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:142), [menu_s1_gate.py:147](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:147).

   `bracketed()` reruns its callback when a successful response takes over 25 ms. Here the callback sends a mutation. For example, a slow layout-toggle acknowledgement causes another toggle: F1 → F2 → F1. The layout completion predicate only requires a changed generation and settled pixels, so this altered workload can pass.

   Detents and op 1 can likewise execute multiple times for one recorded cause.

   **Fix:** send mutations once. Record their brackets and fail or explicitly invalidate an excessively uncertain trial; do not replay them. Keep automatic retries for observational reads. Check the expected destination page/layout and the exact detent count.

4. **Should-fix — late completion can still pass the gate.**  
   [menu_s1_gate.py:181](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:181), [menu_s1_gate.py:242](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:242).

   `wait_poll()` checks success before the deadline. A read started just before the deadline can return a successful sample after it and be accepted. The continuous case records `final_ms` without subsequently requiring it to be ≤500 ms. Paced repaints similarly clear their pending cause before checking whether completion was late.

   Also, `wait_poll()` always returns the state-read timestamp even when its predicate depends on the later measurement read.

   **Fix:** require the completion evidence’s timestamp to meet the deadline before accepting it. Preserve each read’s bracket and use the timestamp appropriate to the evidence—both samples when combining state and measurements. Apply the same rule to paced repaint completion.

5. **Should-fix — the final progress bucket includes post-burst settling.**  
   [menu_s1_gate.py:374](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:374).

   The script waits for final settlement, polls again, and only then closes the last bucket. A burst with no commits during its last 500 ms can pass because a commit after input stopped is credited to that bucket.

   The elapsed-time exit at line 359 can also omit the final scheduled detent after a host scheduling delay; the script checks the cursor against however many it sent, without requiring 200.

   **Fix:** close and validate all burst buckets independently of final settlement, using timestamped samples at the scheduled boundaries. Check bucket coverage and exactly 200 detents. Keep post-burst settlement as a separate measurement.

   Findings 3–5 remain in the earlier gate rewrite; the `perf_counter()` substitution does not introduce or resolve them.

6. **Note — revision 13 retains a contradictory navigation rule.**  
   [CONFIG-MENU-BUILD-PLAN.md:714](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:714).

   It still says navigation resets the slot’s operation and piece cursors. Navigation now preserves them when the current PARTIAL slot’s signature is unchanged.

   **Fix:** say navigation discards progress only when the slot’s signature changes, its state is invalidated, or its cursor is abandoned. Preserve the separate rule that navigation does not restart a running clear. Together with findings 1–2, this means the amendment does **not yet describe exactly what the code does**.

7. **Note — skipping Health composition also freezes Health’s ISR sampling baseline.**  
   [display.c:1126](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1126).

   `prev_entries`, `prev_ticks`, and `prev_ms` no longer update on Camera. On returning to Health, its first displayed ISR sample averages the time away rather than a recent one-second interval; a health reset meanwhile can make that first delta invalid.

   Camera does not need this side effect, and the gate reads its own ISR counters, so this is not a Camera-completion or flash blocker.

   **Fix:** rebaseline the Health-only sample on entry and show `--` until the next valid interval.

The remaining lifecycle checks look correct:

- **Signature-only resume:** F1’s signatures encode pattern, slot and selection; F2’s pixels have no omitted mutable dependency. Layout changes invalidate every slot regardless of signature. Clears finish before slot painting starts. Loss invalidates the cursor before further painting; fresh openings invalidate everything and restart the clear. A cursor abandoned while PARTIAL becomes INVALID, so moving away and back cannot reuse its old piece position. Changing away and back without painting in between is safe.
- **Stops and C10’s target books:** synchronous resumed operations count at their eventual end in the new target’s operation count. An unreached stop is cancelled by retargeting; a reached stop continues holding, including across layout changes, until release or fresh entry. Settlement tests current signatures, not the stored slot generation, so retained slot progress does not settle an old target or double-count settlement. Findings 1–2 concern operation measurement, not the settled/superseded target books.
- **Camera:** the early return leaves `draw_debug_page()`’s dirty comparison and `dbg_note_composed()` running. Camera uses its own changed flag and grid; completion still checks composition, RTC second, transfers and loss. Page entry resets both grids, and dashboard return uses a fresh restore. I found no missing Camera dependency beyond the Health-only baseline noted above.
- **Restore splits:** band 1 resets `restore_sub` before every restarted restore, including after WAITING or a second request. Stage 2 resets it before advancing; stage 4 forces once, then holds until all five outline edges are attempted. Forced battery repaint resets `outline_edge` and marks all parts dirty **before** the per-pass guard, so a deferred call retains its work. The guard clears at pass end. Loss prevents DONE and leads to a fresh repair; it need not immediately reset the subcursor. Outside restore, successive `draw_battery(false)` calls preserve outline progress. The remaining battery parts drain through RESIDUAL. I found no new hang or skipped-part path.

The saved candidate binaries and ELFs match their manifests. Heap gaps are **dev 264 B, devfault 152 B, daily 2,368 B**, all above the stated 128 B floor. The new spin test supports aggregate progress and final-frame correctness; it does not establish every 500 ms progress bucket or the operation-accounting cases above.
---

## Dispositions (Warren, 10-24)

Safe to flash, and revision 13 sound for pixel correctness. Every finding
was fixed before the flash, in firmware `gremlin/s1` after `f1c2dcf7`, the
plan, the host tests and the gate.

1. **A resumed op timed from its suffix: fixed.**
   - A retarget no longer forgets an op in progress; it marks it untimed
     (`op_untimed`). A resumed op keeps its start and ends untimed, and a
     genuinely new op starts a fresh origin.
   - An abandoned or invalidated slot's op is dropped.
   - **Host test:** a selection change there and back at every pass of a B
     repaint's rows; the first op to end is untimed or whole.
     `f1c2dcf7`'s scheduler fails it 47 times.
2. **A retarget during a glyph's DMA dropped its count: fixed.** The
   in-flight op is kept (`ops_inflight` survives `new_target()`, marked
   untimed) and counted once at its DMA's end. Host test: retarget, then
   `dma_settle()`; `ms_ops()` is 1, once. `f1c2dcf7` fails it.
3. **The gate replayed mutations: fixed.** Mutations and op 1 are sent once.
   A bracket over 25 ms fails the trial as uncertain. The layout change must
   land on screen 2; the burst must send exactly 200 detents.
4. **Late completions could pass: fixed.**
   - **The evidence:** a judgement's evidence is the later of its two reads,
     and its end must meet the deadline, in `wait_poll()`, the paced
     repaints (checked before clearing) and the transitions.
   - **The burst:** its final 500 ms is checked.
5. **The final bucket included settling: fixed.** Buckets close on forced
   polls at their scheduled 500 ms boundaries, the last at the burst's end,
   before the post-burst wait. All 20 are checked.
6. **The plan's navigation rule: fixed.** Navigation keeps a PARTIAL slot's
   cursors while its signature is unchanged. A new bullet states the untimed
   resumed op and the kept in-flight glyph.
7. **Health's stale ISR baseline: fixed.** A page reset sets
   `dbg_isr_rebase`, and the first composition shows "--" and starts a fresh
   window.
