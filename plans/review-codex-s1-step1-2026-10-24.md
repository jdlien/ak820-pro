# Codex review: S1, the first increment (2026-10-24)

Prompt: [`review-prompt-s1-step1.txt`](review-prompt-s1-step1.txt). Reviewed: `gremlin/s1` at `517b5dda` (pieces under `MB_PASS_BYTES`, `end_op()`, the entry check, HC_POLLFAULT, the chibios-contrib FIFO dispatch patch). Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Safe to flash `517b5dda` to gremlin’s test board for this experiment; no blocker found.** I found correctness and test-coverage issues that should be fixed before accepting S1’s failure/stop behavior. This clearance does not extend to Buzz.

I verified the commit chain, submodule revision, changed-file contents, and host-test contents against local Git objects. All file reads stayed inside the permitted directory. This was static review: process execution was unavailable, so I did not independently rerun the tests, build, or flash.

1. **Should-fix — a failed non-final piece never ends or counts its op.**  
   [menu_slots.c:105](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:105), [menu_fixture.c:99](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:99).

   `mb_fill()` communicates failure through the loss flag, but the fixture returns `true` regardless. `paint_piece()` then increments `piece` and returns early whenever more pieces remain. It never calls `end_op()` for that failed op.

   Concrete case: repaint B with `stop_n = 11`. After the nine glyphs and separator, fail any of the first three pieces of row 0’s first half. The result is `ops == 10`, `stopped == false`, and a pending loss. Navigation before the next pump cancels the stop; without navigation, loss recovery restarts painting and reaches 11 on a replacement title glyph. Neither matches C4’s requirement to count and latch **when the failed op ends**.

   The final-piece failure test passes because that piece happens to take the ordinary `end_op()` path.

   **Fix:** distinguish busy, successful piece, and failed operation. On failure, end/count the op exactly once, latch its stop immediately, discard remaining piece progress, and wait for the owner’s loss handler. Also stop the scrollbar callback after a failed track fill: [menu_fixture.c:105](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:105) currently sends its thumb afterward.

2. **Should-fix — the entry guard omits the required `SPI_READY` check.**  
   [lcd_bus.c:182](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:182).

   `blit_done`, BUSY, and RX_EMPTY describe DMA/application and peripheral state; they do not establish that the ChibiOS FIFO driver has relinquished ownership. An erroneous entry with a stranded `SPI_ACTIVE` transfer and idle hardware passes this guard, masks its interrupt, and borrows its FIFO.

   I found no current healthy caller that creates that overlap: synchronous window sends and main-thread serialization supply the missing guarantee. This is incomplete defensive hardening, rather than a normal-path flash blocker.

   **Fix:** require `SPID0.state == SPI_READY` before masking IE, alongside the existing DMA/BUSY/RX checks. Keep refusal non-destructive; do not reset an owner whose transaction has not been accounted for.

3. **Should-fix — the host tests leave important C4 boundaries untested.**  
   [menu_s0_test.c:635](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:635), [menu_s0_test.c:660](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:660), [menu_s0_test.c:708](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:708).

   The tests substantiate several claims: summed fill bytes per scheduler pass, eventual A/B frames after retargeting and selection changes, F2 layout interruption, and the synchronous end-of-op latch. But:

   - The general failure sweep checks eventual pixels, not the failed op’s immediate count and stop. It therefore misses finding 1. It also does not require every armed fault to be consumed.
   - `pass()` settles DMA **and calls `ms_step()` before navigation**. Moreover, `ms_ops()` itself settles operations. These cases do not independently establish that `new_target()` and invalidation settle a newly completed DMA before discarding state.
   - The new boundary sweeps omit close/reopen and return-from-another-owner, including release of an already reached stop through `fresh`.
   - Fake fill failures paint nothing; they do not model the hook’s prefix-painted and fully-painted-but-failed cases.

   **Fix:** test each failed piece with immediate count/stop assertions; explicitly complete or fail a DMA and navigate/invalidate before calling either `ms_step()` or `ms_ops()`; add fresh-opening/owner-return boundary cases and require fault consumption. The reported 53 mutant failures are useful evidence for the latch, but do not cover these separate guarantees.

4. **Note — HC_POLLFAULT exercises common cleanup, but bypasses timeout detection.**  
   [lcd_bus.c:199](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:199).

   Both modes finish receiving their chosen byte count and wait for real BUSY to clear before line 208 forces `ok = false`. Mode 0 genuinely leaves a pixel-payload prefix; mode 1 genuinely reports failure after delivering everything. Both execute the production reset, counter, sticky-bit, loss, drain, and IE-restoration path.

   They **do not** exercise either spin-limit decision, the latency of exhausting those limits, or resetting hardware that remains busy. Calling mode 1 proof of a stuck-BUSY recovery would overstate the result.

   **Fix:** describe the present hook as forced-give-up cleanup coverage. To cover timeout control flow, inject stalled-progress/BUSY predicates into the bounded loops themselves. Actual stuck-hardware recovery remains a board-validation question.

   For these injected cases, bus and panel recovery look sound: cleanup restores FIFO operation, callers close CS, and repaint opens a fresh window/RAMWR. Finding 1 affects accounting and stops, not eventual repaint recovery.

5. **Note — lowering the budget requires more than changing the constant.**  
   [menu_fixture.c:49](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:49), [menu_fixture.c:105](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:105).

   At **512**, the bound holds:

   | CPU paint | Maximum bytes per scheduler piece |
   |---|---:|
   | F1 half-row | 488 |
   | F2 tile portion | 512 |
   | Separator | 240 |
   | Scrollbar, both fills | **276** |

   The scrollbar comment incorrectly says 224 bytes together: that excludes its 52-byte thumb. A later change to 256 would exceed the budget there. Smaller limits can also exceed a whole row’s width because `rows_per_piece()` floors its result at one.

   **Fix:** correct the comment and either assert the supported minimum budget or subdivide these cases when tuning it.

6. **Note — a lower observed maximum needs completed-work and interval evidence.**  
   [menu_s0_session.py:311](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:311), [health.c:160](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:160).

   A11 waits for mutation completion, not completion of each requested repaint. With more yielding, subsequent mutations can supersede more unfinished pixels. Also, the recorded prototype’s 24 ms is a maximum since the flash, not an isolated fixture interval.

   **Fix:** retain A11 as the interaction workload, and separately measure completed F1/F2 repaints and selection changes, recording completion latency/throughput alongside the maximum. Bracket measurements after boot settling, use matched lighting/transport/instrumentation, and separate injected-fault runs. The existing health maximum can support this increment’s experiment; deferred C10 instrumentation is not a defect in this increment.

The remaining paths look correct:

- **Scheduler:** there is one `ms_step()` dispatch per menu pump and one paint callback per step. Slots remain `PARTIAL`; continuation requires matching generation and signature. Normal final pieces count once, busy retries do not. Reached stops survive retargeting/invalidation and pause clears; sub 0 and `fresh` release them. Clear-band progress survives navigation independently.
- **Healthy SPI entry:** `spiSend()` completes after its RX has been drained. The short BUSY allowance covers a trailing hardware indication; row-ISR preemption does not consume its iteration budget. DMA completion waits for the transmit tail, and the subsequent synchronous window commands precede polling. I found no expected healthy entry refusal. A refusal costs dropped drawing, a sticky failure, and owner repaint—not just the short entry wait.
- **ChibiOS ownership and IRQs:** `SPI_ACTIVE` is appropriate for the current SPID0/SPID1 FIFO transfers: the wrappers set it before priming TX. SPI1’s raw command/DMA window is protected by its disabled vector, with cleanup before re-enabling it. SPI0 polling masks IE; DMA dispatch remains ahead of FIFO dispatch. Thus the idle drain has no legitimate current owner’s bytes to steal. With RXFIFOTHIE disabled, a raw threshold flag cannot continuously assert that interrupt source; an already pending vector can return without creating an endless level-triggered loop.
---

## Dispositions (Warren, 10-24)

Safe to flash, no blocker. The three should-fixes were fixed before the flash,
in firmware `6a9a16b7` and the host tests:

1. **A failed non-final piece never ended its op: fixed.**
   - The paint callback returns `ms_paint_t` (BUSY, DONE or FAILED).
     `mb_fill()` and `lcd_fill_rect_ok()` report a give-up.
   - A failed piece ends its op at once (`end_op()`: counted, its stop
     latched), and the slot sends nothing more: it waits, PARTIAL, for the
     owner's loss handler.
   - The scrollbar sends no thumb after a failed track.
2. **The entry check's missing `SPI_READY`: fixed.** It now also requires
   `SPID0.state == SPI_READY`, and refuses without resetting anything.
3. **The tests' gaps: fixed** (`scripts/menu_s0_test.c`):
   - **every failed piece of a B repaint** is checked at once: counted, its
     stop latched, the latch surviving navigation before the next pass;
   - **each title glyph's DMA** is settled directly, then navigation or a
     loss comes before any `ms_step()` or `ms_ops()`;
   - **a fresh opening and a return from another owner** at every piece
     boundary, and a reached stop let go by each;
   - **give-ups** with nothing painted and with a prefix painted (HC_POLLFAULT
     mode 0's shape);
   - **consumed faults are counted** and required. Late in a repaint no
     fill is left to fail, so a fault there goes unused.

   Two mutants: a failed piece treated as done fails 96 checks; no settle in
   `new_target()` fails 18.

**Notes:**
- **4. HC_POLLFAULT: taken.** Its comment now calls it forced-give-up
  cleanup coverage. The spin limits' own detection, and a BUSY that never
  clears, remain a board question.
- **5. The budget's floor: taken.** The scrollbar comment says 276 B
  (track 224 plus thumb 52), and `_Static_assert(MB_PASS_BYTES >= 276u)`
  holds the floor until those cases are split.
- **6. The measurement: taken.** This flash's worst-pass reading is an
  interaction measurement, bracketed after boot settles. Completed F1/F2
  repaints and selection changes are timed separately, with their
  throughput, and C10's instrumentation (next increment) makes that exact.
