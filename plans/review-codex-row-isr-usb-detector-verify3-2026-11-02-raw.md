**NOT READY TO FLASH.** The original double-count is fixed, but HEAD introduces an unchecked interval that can hide a second silence. Freshness also remains unsafe across an exclusion.

Reviewed `ecd63d0c77` and its preceding three fixes. The supplied ELF matches HEAD’s manifest. Verification used source, disassembly, in-memory state models and synthetic decoder inputs. No files were changed or hardware accessed.

1. **Finding 1 — P1: partly fixed.**

   The exact second-verify counterexample is fixed: [`frm_staleI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:260) now captures the current FRMNO and stales its timestamp. Movement inside the guard’s discarded gap therefore cannot immediately restore freshness. [`take_snapI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:425) retains the ACTIVE, PHY, pending-event and `<750`-tick freshness checks.

   **An exclusion still permits the same underlying false freshness.** While excluded, [`time_observeI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:275) updates the stamp but freezes `time_ext`. Nevertheless, [`frm_trackI()` still runs](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:318), and [ending the exclusion](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:330) does not stale that qualification.

   Reproduced sequence:

   - Enter the dev lock-mode exclusion; observe one further frame movement.
   - Frames freeze for 20 ms, with stale ACTIVE, PHY enabled and no event flag. Observers continue, but freshness age remains **zero** because the extension is frozen.
   - End the exclusion and establish a valid row baseline.
   - A subsequent 700 ms silence contributes only **178 timer ticks**. Its approximately 1 ms span passes against frozen `df=0`, with no new loss.

   Qualification must exclude movement recorded while time is being discarded and require movement after recovery.

2. **Second verify’s new P1 — double-count after span rejection: fixed.**

   [`time_invalidateI(false)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:798) preserves freshness. The ordinary 350 ms rejection followed by another row before the next SOF now produces one loss.

   The [conditional adoption](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:795) correctly checks **both** validity and generation:

   | Tick activity before rejection | Adoption | Loss accounting |
   |---|---|---|
   | No intervening invalidation | Yes | Once immediately |
   | Invalidated, still INVALID | No | Once at next entry |
   | Invalidated and re-primed | No | Once at next entry |

   These interleavings neither duplicate nor omit the reviewed loss, and do not relabel the pre-gap snapshot.

3. **New P1 introduced by HEAD — the next interval can lose a separate silence entirely.**

   [`service_commit()` forcibly clears `last_snap.usb`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:726). Consequently, [the next interval bypasses USB checking](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:768), while remaining eligible for valid interval statistics.

   With **continuous healthy SOFs**:

   - A 350 ms silence causes one span rejection and an adopted baseline.
   - The extension re-primes.
   - Before the next serviced entry, a separate 700 ms silence occurs.
   - Its raw observation gap aliases below 8 ms. Generation remains unchanged, but USB comparison is skipped because the adopted baseline has `usb=0`.
   - The returning service commits a fresh baseline, permanently losing the second silence’s evidence.

   The model produced **one loss for two silences**, accepting the second interval with only 188 extended ticks including surrounding normal time. Preserving freshness addresses the original duplication; blanket suppression adds this false-negative window. The bench’s widely spaced injections do not exercise it.

4. **Finding 5 — P2: partly fixed; firing mechanism fixed.**

   [Firing-time state checks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214) remain before masking, appropriately for main-loop-maintained state. The [actual pin read is under the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174); a high pin prevents firing.

   ELF verification confirms:

   - Mask: `0x25130`; rising store: `0x25144`, with nine intervening instructions.
   - Falling store: `0x25168`; immediately followed by unmask at `0x2516a`.
   - Length arithmetic and bookkeeping remain outside.

   The corrected **approximately 0.3 µs nominal** estimate is consistent with that sequence. The documented absolute “under half a microsecond” bound still lacks allowance established for flash/peripheral stalls.

5. **Finding 6 — P2: partly fixed.**

   The [guard rejection count](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:255) and [decoder comparison](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:188) fix equal-gap misattribution. Synthetic tests passed for identical consecutive gap values, including counter wrap; USB and both report-page layouts also passed.

   **HEAD waits 2 ms, not 200 µs**, at [rowisr_diag.c:230](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. This accommodates ordinary recovery but remains a scheduler delay.

   The report still copies state before firing and after that delay. It does **not** retain the actual last-before/first-after observer pair. `valid1` is recovered state at the later copy, not the interrupted gap’s verdict; precise near-threshold observation offsets remain unavailable.

6. **Finding 7 — P3: partly fixed.**

   HAL ordering, observation-gap terminology and nominal marker timing are corrected. Remaining inaccuracies include:

   - [“staled by every invalidation”](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:242), despite the deliberate `false` argument.
   - [Decoder documentation](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:55) and [printed explanation](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:290) still describe attribution by a changed gap value.
   - The [plan’s claim that the report records observer offsets](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:705) exceeds the retained evidence.

The previously fixed protections remain intact: [the spurious return precedes the USB verdict](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:761), preserving epoch ownership. [Deep-sleep entry cancels unconditionally](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:978); both dev and ladder sleeps reach it through [the common path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), even with the tick already stopped. The earlier return aborts admission without sleeping. Plain WFI/PMU light sleep does not use that cancellation path.

**The deciding P1s are freshness surviving discarded exclusion time and HEAD’s suppression of a separate silence in the next interval.**