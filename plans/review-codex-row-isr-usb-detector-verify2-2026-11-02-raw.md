**NOT READY TO FLASH for the bench’s silence injections.** Finding 1 remains a P1, and HEAD introduces another P1 that can count one USB silence twice.

Reviewed `19dc250cf2` and its two preceding fixes. The supplied ELF matches HEAD’s manifest hash. Verification used source, disassembly, in-memory state models and synthetic decoder inputs. No files were changed or hardware accessed.

- **Finding 1 — P1: partly fixed.**  
  [Invalidation stales `frm_seen_ext`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:273), but leaves `frm_seen` unchanged. The immediately following [`frm_trackI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:294) can undo that staling using movement that occurred **inside the discarded gap**. Both the tick and [`take_snapI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:408) have this ordering.

  Counterexample, with stale ACTIVE, PHY enabled and no bus-event flag:

  1. Observers stop for 20 ms. FRMNO advances once near the beginning, then freezes.
  2. The returning observer rejects the 20 ms gap and stales freshness.
  3. Its frame read differs from the pre-gap `frm_seen`, so it immediately stamps that frozen value as fresh.
  4. After re-prime and a new row baseline, a 700 ms silence leaves **178 timer ticks**, rounding to **1 ms** against `df=0`. It passes without another loss.

  The state model reproduced this with freshness age only 228 ticks. Frames had actually stopped over 20 ms earlier, outside the declared four-millisecond residual. Recovery must first establish a post-gap frame baseline, then require subsequent movement.

- **New defect — P1: self-invalidation can count one silence twice.**  
  [`time_invalidateI()` now stales freshness](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:283), while [`service_commit()` adopts only the generation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:705), retaining `s1.usb == true`.

  A 350 ms alias on a continuously healthy USB bus can therefore produce:

  1. A span disagreement: `usb_rejects++`, generation increment, one loss.
  2. Re-prime and successful service commitment with the adopted generation.
  3. The next row arrives before the next SOF. FRMNO has legitimately not changed, but freshness remains artificially stale.
  4. The [untrusted-end branch](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:750) rejects again: `usb_events++`, another generation increment and another loss.

  This requires no second interruption or actual bus event. The model produced **one span rejection, one false event rejection and two losses**. It directly contradicts the [bench’s 350/700/1049 ms expectations](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/silence_check.sh:54). The adopted baseline’s USB qualification must account for freshness being deliberately reset.

- **Added P2 — row-only hold across a frame wrap: fixed.**  
  [The tick now tracks FRMNO](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:302). A row-only hold whose tick preserves the extension also preserves frame freshness. The exact 2.048-second model returned to the same FRMNO and correctly accepted the interval without a loss.

- **Finding 4 — P2: the original adoption and duration defects are fixed.**  
  [Adoption now requires both validity and `time_gen == s1.gen`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:777). For the reviewed snapshot/rejection race:

  | State at rejection | Adoption | Loss accounting |
  |---|---|---|
  | No intervening tick invalidation | Yes | Once immediately |
  | Tick invalidated, still INVALID | No | Once at the next entry |
  | Tick invalidated and re-primed | No | Once at the next entry |

  The old timestamp is no longer relabelled after a tick-discarded gap, including the scan-only and flash-skip commits. These interleavings neither duplicate nor omit the loss. The separate freshness regression above introduces duplication **after** successful adoption.

  [Exit now takes a full snapshot and checks its USB span](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:919) before accepting duration, closing the reviewed inside-handler alias case for a USB-trusted entry.

- **Finding 5 — P2: partly fixed.**  
  The [firing-time state checks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:211) remain outside the mask; that is sound for these main-loop-maintained states. The [actual pin is checked under the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174), catching the tick’s output.

  The ELF confirms length arithmetic stays outside `silence_masked`. Masking is at `0x25070`, the rising store at `0x25084`; the falling store at `0x250a8` immediately precedes `cpsie i` at `0x250aa`.

  However, the [revised “under 0.2 µs” bound](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1137) is still too small: there are nine intervening instructions before the rising store, including three loads. Nominal zero-wait Cortex-M0 timing is about **14 cycles through that store, or 0.29 µs at 48 MHz**, before additional stalls. The mechanism is repaired; the numerical uncertainty remains understated.

- **Finding 6 — P2: partly fixed, with a new attribution error.**  
  [The copied state now includes observer stamps and guard gaps](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:320), and both report pages match the decoder.

  The old 200 µs wait is now [`wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. It accommodates ordinary scan-only re-prime timing, but remains a scheduler delay. `valid1` is recovered state at the later copy, not the rejected gap’s verdict.

  The report still does not retain the actual **last-before/first-after observation pair**: the pre-mask copy can be superseded, and the post-wait stamp is a later observation. Thus it still cannot establish the plan’s precise observation-gap proof.

  **New error:** [`guard_rejected` compares gap values](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:187), rather than a rejection counter. Two guard rejections with the same tick gap leave those values equal; the [CLI then says “not the guard’s”](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:288). A synthetic report with generation `7→8` and guard gap `3750→3750` reproduced that false attribution. A guard sequence/count or retained reason is needed.

- **Finding 7 — P3: partly fixed.**  
  The [revised header](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:97) correctly distinguishes observation gaps, service latency and the 13-second scope. HAL-hook ordering and span/512 wording remain corrected. Outstanding inaccuracies include the endpoint bound above, the [“As built” under-0.1-ms observer-offset claim](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:705), and the report attribution.

The previously fixed P1s remain fixed. The [zero-boundary return precedes the USB verdict](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:741), preserving duplicate-epoch suppression. [Deep-sleep entry cancels unconditionally](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:960); both dev and idle-ladder sleeps reach it through [the common path before teardown/WFI](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), even with the tick already stopped. The earlier return aborts sleep admission. Plain WFI/PMU light sleep does not use that cancellation path.

**The deciding P1s are false freshness reacquisition across discarded time and the newly introduced double-count after USB rejection.**