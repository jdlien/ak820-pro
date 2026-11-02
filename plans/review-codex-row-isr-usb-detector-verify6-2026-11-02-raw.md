**NOT READY TO FLASH.** The fifth verify’s exact recovery-expiry counterexample is fixed, but HEAD introduces another P1: a rejected re-prime can discard time without invalidating an already-adopted baseline, allowing a later comparison to accept that interval as healthy.

Reviewed **`9d702160c8`**, its seven-fix history, the decoder and bench script. The supplied ELF matches HEAD’s manifest SHA-256. Verification used source, ELF disassembly, in-memory observer-order models and synthetic inputs to the actual decoder functions. No files were modified or hardware accessed.

**Finding 1 — partly fixed; a new P1 decides the verdict.**

The [new re-prime guard](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:280) fixes the fifth verify’s example. A 2,048 ms gap while INVALID no longer adds its 56,320-tick residue to the extension. It refreshes the stale frame baseline and leaves recovery pending. The sequence **20 ms guard rejection → delayed re-prime → pending baseline → separate 700 ms silence** now produces two losses in the model.

However, that new branch discards time **without changing `time_gen`**. This breaks the assumption supporting the handler’s adoption: [its rejection previously discarded nothing](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:306), so [commit retains the snapshot’s validity and trust while adopting the new generation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:755).

The [scan-only commit path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:881) can commit that adopted baseline without executing step 6’s re-prime. Consider the ordering where no tick re-primes before that commit:

| Step, with continuously moving SOFs and no bus events | HEAD’s result |
|---|---|
| An aliasing gap is rejected by the frame counter; scan-only commits the adopted baseline | One loss. `last_snap.valid=1`, adopted generation G; global `time_valid=0`. |
| Before re-prime, the next observation gap is 2,048 ms | The new guard discards 56,320 ticks and stales frames, but leaves generation G unchanged. FRMNO has completed one wrap. |
| A subsequent observation re-primes; a new SOF restores freshness | Global time becomes VALID again in generation G. The old adopted baseline still qualifies. |
| The next eligible service compares against that baseline | The discarded 2,048 ms is absent from the extension and also invisible modulo FRMNO. The comparison passes. |

A concrete phase trace in the model used an initial rejected service at **360.990 ms**, the tick’s rejected re-prime at **2,408.990 ms**, and a row observation 20 µs later. That first row returns as spurious. At the next actual scheduler slot, **2,409.395 ms**, the extension reports approximately **0.405 ms**, rounded to **0 ms**, against **one frame**. It passes the three-millisecond tolerance and increments `serviced_valid`.

**HEAD reports one loss and one USB rejection; the same trace on HEAD~1 reports two losses and two USB rejections.** This is a regression within the 13-second scope, on a live bus. It is not the declared stopped-frame blind spot.

Whenever re-prime discards time, it must break continuity with any surviving adopted baseline. Guarding the residue alone is insufficient.

**Three-state trust and ordinary recovery — fixed for the reviewed transitions.**

[`take_snapI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:455) preserves bus-up, freshness and pending separately. Freshness requires movement **strictly less than 750 extension ticks ago**, or 4 ms.

| Transition | Verified behavior |
|---|---|
| Guard rejection while VALID | Discards the gap, advances the generation and captures current FRMNO as stale/pending. Movement inside the discarded gap cannot resurrect freshness. |
| Exclusion ends | Tracking remained frozen during exclusion. Only the final real exclusion release establishes a new stale baseline; clearing an already-clear bit does nothing. |
| Pending-start interval | Ending fresh invokes the frame comparison; ending without fresh frames excludes the interval as unjudged. |
| Frames stop without a flag | Ordinary observations age freshness out; a fresh-start/stale-end interval rejects once. Later known-stopped starts fall into the declared blind spot. |
| Recovery receives no frames | With ordinary observations, pending expires after 1,500 additional extension ticks—8 ms. |

The relevant [staling/tracking](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:264), [exclusion release](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:342), and [verdict branches](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:802) behave as intended. The remaining P1 concerns continuity of the adopted consumer baseline, rather than premature recovery expiry.

**Conditional adoption — the earlier races remain fixed, but the new discard escapes them.**

[Adoption requires both present validity and `time_gen == s1.gen`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:844).

| Activity before the handler’s rejection | Adoption | Loss accounting |
|---|---|---|
| No intervening invalidation | Yes | Once immediately |
| Tick invalidated; still INVALID | No | Once at next entry |
| Tick invalidated and re-primed | No | Once at next entry |

These cases produced no duplicate loss. A rejection followed by ordinary recovery and a separate 700 ms alias also produced two losses. The new P1 occurs **after adoption**, when an INVALID-state guard discard leaves that adopted generation unchanged.

**Finding 5 — wire byte: fixed.**

[`usb_unjudged` now saturates at 127](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:857), matching [serialization’s bit-7 recovery flag](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:596). Synthetic inputs through [`usb_dict()`](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:169) verified saturation and both flag states. Counts above 127 no longer fabricate recovery.

**Spurious suppression and deep-sleep cancellation — remain fixed.**

The [zero-boundary return precedes the USB verdict](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:793), preserving the baseline and preventing the reviewed coincident bus event from enabling another pulse in the serviced epoch. Its placement is correct; the new P1 gives it a baseline whose continuity is no longer valid.

Both dev and ladder deep sleeps reach [the common teardown](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:478) and [unconditional driver-entry cancellation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1029), including when the tick was already stopped. The earlier admission return does not sleep. Plain WFI/PMU light sleep is separate from this deep-sleep cancellation.

**Silence firing and report — remain fixed, with the stated measurement limits.**

[Firing-time logical state checks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214) precede masking. The [actual pin read remains inside the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174); a high pin prevents firing.

HEAD’s ELF confirms:

- Mask at `0x2521c`; rising store at `0x25230`, with nine intervening instructions.
- Falling store at `0x25254`, immediately followed by unmask at `0x25256`.
- Length arithmetic and bookkeeping outside the masked function.

**There is no 200 µs wait.** [The code uses `wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. The report copies state before firing and after that scheduler delay. Its later VALID bit describes recovered state, not the interrupted gap’s verdict. The actual last-before/first-after observer pair remains absent; equal-gap and wrapping guard-counter attribution tests passed.

**Finding 8 — the requested documentation corrections are fixed.**

The [detector overview now includes recovery and pending starts](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:393). The [gate now assigns synchronized observer stamps to the witness](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1156), explicitly distinguishing them from the record’s extension reading and spin count.

The isolated bench injections matched their nominal model predictions. They do not exercise the **adopted rejection → discarded re-prime → fresh comparison across the unchanged generation** sequence that remains the deciding P1.