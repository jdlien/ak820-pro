**NOT READY TO FLASH.** HEAD fixes the two exact third-verify counterexamples, but another recovery interval can still hide an aliasing silence on a continuously live USB bus. There is also a new false-loss case when clearing an exclusion that was already clear.

Reviewed `e81e8770e0` and the five-fix history. The supplied ELF’s SHA-256 matches HEAD’s manifest. Verification used source, disassembly, in-memory clock models and synthetic inputs to the actual decoder functions. No files were modified or hardware accessed.

1. **Additional P1 — an untrusted recovery baseline still hides a separate silence.**

   Re-priming sets `time_valid` independently of frame freshness at [rowisr.c:277](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:277). A service can therefore commit `valid=1, usb=0`. The next interval’s validity does not require USB qualification, and [USB checking requires `last_snap.usb`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:763).

   Reproduced with uninterrupted SOFs, ACTIVE, PHY enabled and no bus events:

   - A 20 ms gap triggers the guard, increments the generation and stales freshness.
   - Before the next SOF, observations re-prime the extension and a row service commits a valid but USB-untrusted baseline.
   - A separate 700 ms silence follows.
   - Its raw gap leaves **178 ticks**. The returning observation restores frame freshness, but USB comparison is skipped because the **starting** baseline was untrusted.
   - The interval enters valid statistics and replaces the baseline, permanently losing its evidence.

   The model produced **one loss for two silences**, accepting the second interval with **188 extended ticks**, including surrounding normal time. The [scan-only commit path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:842) reproduces this without relying on pulse-admission timing.

   HEAD’s new exclusion-end staling creates the same window after an exclusion. Recovery must prevent this interval from becoming healthy merely because USB judgment was unavailable at its starting endpoint.

2. **Finding 1 — partly fixed overall; the specific false-freshness mechanism is fixed.**

   [The tracker now stops during exclusions](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:312), and [ending the last exclusion establishes a stale FRMNO baseline](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:333). Movement recorded during discarded time can no longer keep frozen frames qualified.

   The guard likewise [captures the current FRMNO when staling](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:262). [`take_snapI()` retains all four trust conditions](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:431), including freshness strictly below 750 ticks.

   The frozen-frame exclusion model now remains untrusted. The remaining P1 is how that untrusted recovery baseline is consumed, described above.

3. **Third verify’s post-rejection P1 and the earlier double-count — fixed for the rejection/adoption path.**

   [Commit preserves the snapshot’s USB qualification](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:728), while [the handler’s own invalidation preserves freshness](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:803). Thus the ordinary 350 ms rejection does not manufacture an untrusted next endpoint, and a subsequent 700 ms silence is checked. The model produced two span rejections and two losses.

   Adoption correctly requires **both** `time_valid != 0` and `time_gen == s1.gen`:

   | Tick activity before rejection | Adoption | Loss accounting |
   |---|---|---|
   | No intervening invalidation | Yes | Once immediately |
   | Invalidated, still INVALID | No | Once at the next entry |
   | Invalidated and re-primed | No | Once at the next entry |

   These interleavings neither duplicate nor omit the reviewed loss. The original snapshot remains unchanged; a later generation change remains visible. The P1 above arises after committing an untrusted recovery baseline, rather than from this conditional adoption.

4. **New P2 — clearing an already-clear exclusion can manufacture a loss.**

   [The release branch](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:333) calls `frm_staleI()` whenever the resulting mask is zero, even if no exclusion ended.

   [`od_set_lock_mode()` calls it unconditionally](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:176). Reapplying `OD_LOCK_UNLOCKED`, or switching between nonexcluded modes, can therefore stale healthy frames without invalidating time or discarding a gap. If the next row precedes the next SOF, its trusted-start/untrusted-end comparison produces a false `usb_events` increment and epoch loss.

   The model reproduced one loss with no silence, exclusion or bus event. Staling on release needs an actual transition from an active exclusion mask to zero.

5. **Finding 5 — partly fixed; firing mechanism verified.**

   [Firing-time state checks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214) remain before masking, sound for these main-loop-maintained states. [The actual pin read remains under the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174); a high pin prevents firing.

   HEAD’s ELF confirms:

   - Mask at `0x25198`; rising store at `0x251ac`, with nine intervening instructions.
   - Falling store at `0x251d0`; immediately followed by unmask at `0x251d2`.
   - Length arithmetic, resynchronization and report bookkeeping outside the mask.

   The revised [sub-microsecond estimate](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:105) now allows for flash waits. Its absolute hardware bound remains unverified; the ELF establishes instruction placement.

6. **Finding 6 — partly fixed, with the remaining limitation explicitly deferred.**

   There is **no 200 µs wait in HEAD**: [it uses `wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. Scheduling can delay the subsequent copy further.

   The report contains copied state before firing and after that delay. `valid1` describes recovered state at the later copy; it is not the interrupted gap’s verdict. It still lacks the actual last-before/first-after observer pair.

   [Attribution by the guard’s rejection count](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:188) is fixed. Actual decoder tests passed for equal consecutive rejected gaps, counter wrap, USB fields and both report pages.

7. **Finding 7 — partly fixed.**

   The freshness comments, decoder attribution and [“As built” report description](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:705) now match their implementations.

   Remaining overstatements include the [header calling the report the observation-gap verdict](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:111), and the [plan requiring synchronized observer stamps “in the record”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1148), which this report does not retain.

The previous spurious-entry and deep-sleep fixes remain **fixed**. [The zero-boundary return precedes USB judgment](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:766), without replacing the baseline. [Deep-sleep entry cancels unconditionally](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:985); both dev and ladder sleeps reach it through [the common teardown](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), including an already-stopped tick. The earlier admission return does not sleep. Plain WFI/PMU light sleep does not use this cancellation path.

**The deciding P1 is the unjudged recovery interval after guard invalidation or exclusion.** The bench’s separated injections do not exercise it; their nominal isolated-case counts passed the clock model, which does not establish detector correctness across this recovery window.