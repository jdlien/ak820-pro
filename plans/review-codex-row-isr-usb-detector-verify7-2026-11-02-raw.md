**NOT READY TO FLASH.** The sixth verify’s exact refused-re-prime finding is **fixed**, but an exclusion can still preserve the same adopted baseline across discarded time. That remaining P1 can let a subsequent aliasing silence read healthy on a continuously live bus.

Reviewed **`d5bdaa7c43`**, the eight fixes, prior reviews, decoder and bench script. The supplied ELF matches HEAD’s manifest SHA-256. Verification used source, ELF disassembly, in-memory observer-order models and synthetic decoder inputs. No files were changed or hardware accessed.

**1. Remaining P1 — adoption followed by an exclusion can still hide discarded time.**

The hole is in [`time_invalidateI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:319): it does nothing when `time_valid` is already clear.

After a frame-counter rejection, [commit can retain a VALID snapshot with the adopted generation G](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:762), while the shared extension remains INVALID. If an exclusion starts before re-prime:

- [Exclusion entry](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:349) leaves generation G unchanged.
- [Observations during exclusion](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:277) advance `time_stamp` while discarding elapsed time.
- [Exclusion release](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:357) stales the frames but does not change G.
- If the row observer was held off, no intervening INVALID service replaces the adopted baseline.

The dev lock exclusion is exposed through [`od_set_lock_mode()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:176), and the [row-only hold permits this overlap](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:106).

The model reproduced this ordering with continuous SOFs, ACTIVE, PHY enabled and no bus event:

| Event | Result |
|---|---|
| Rejected service at **360.990 ms** commits its adopted baseline | One loss; baseline VALID in G, extension INVALID. |
| Exclusion begins before re-prime; rows are held while ticks continue | Time is discarded; generation stays G. |
| Last excluded tick at **660.990 ms**; exclusion ends at **660.995 ms** | Frames become stale/pending; G remains unchanged. |
| Separate all-interrupt silence from **661.000 to 2,409.000 ms** | **1,748 ms** with no observer. |
| Tick at **2,409.010 ms** | Raw gap is **74 ticks**, below the guard; re-prime succeeds in G and frame movement restores freshness. |
| Row at **2,409.030 ms** compares with the adopted baseline | Extension difference **78 ticks**, rounded to **0 ms**, versus **one frame**: accepted; `serviced_valid++`. |

**Result: one loss and one USB rejection despite the second silence.** The accepted interval spans approximately 2.048 seconds, including discarded exclusion time. This is inside the proof’s scope and is not the stopped-frame blind spot.

The exclusion must break continuity with a surviving adopted baseline even when shared time was already INVALID. This defect also exists in HEAD~1; it is an additional surviving hole, not a regression caused by HEAD’s new assignments.

**2. Sixth verify’s 360.990 ms refused-re-prime trace — fixed.**

[HEAD now advances `time_gen` and the guard rejection count before discarding a refused re-prime](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:283).

Rerunning the original trace:

| Observation | HEAD result |
|---|---|
| Frame-counter rejection at **360.990 ms** | First loss; generation G adopted. |
| Tick at **2,408.990 ms**, after 2,048 ms | Discards **56,320 ticks**, advances to G+1, counts a guard rejection. |
| Row at **2,409.010 ms** | Detects generation mismatch, counts the second loss and excludes the interval. It no longer returns as spurious. |
| Row at **2,409.395 ms** | May accept only the short interval since the replacement baseline. |

HEAD produces **two losses, one USB rejection and one guard rejection**. HEAD~1 reproduces the previous **one-loss** failure.

**3. Three-state trust — ordinary transitions remain fixed.**

[`take_snapI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:462) retains bus-up, freshness and recovery separately. Freshness requires movement **strictly less than 750 extension ticks ago**, or 4 ms.

| Transition | Verified behavior |
|---|---|
| Guard rejection or refused re-prime | Captures current FRMNO as stale/pending; movement inside discarded time cannot immediately restore freshness. |
| Ordinary exclusion end | Tracking was frozen; the final real release establishes a stale baseline. Clearing an already-clear exclusion does nothing. |
| Pending-start interval ending fresh | Frame comparison runs, including after an ordinary guard or exclusion recovery. |
| Pending-start interval ending without fresh frames | Excluded as unjudged, rather than accepted as healthy. |
| Recovery without movement | Pending expires after **1,500 additional guarded extension ticks**, or 8 ms. |
| Frames stop without a flag | Freshness ages out; fresh-start/stale-end rejects once. Subsequent known-stopped starts enter the declared blind spot. |
| Handler’s own rejection | Preserves freshness, avoiding the earlier duplicate rejection before the next SOF. |

The remaining P1 concerns **baseline continuity across an exclusion**, not incorrect freshness reacquisition.

**4. Conditional adoption and loss accounting — reviewed tick races remain fixed.**

[Adoption requires both current validity and `time_gen == s1.gen`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:851).

| Activity between snapshot and rejection | Adoption | Loss accounting |
|---|---|---|
| No invalidation | Yes | Once immediately |
| Tick invalidates; still INVALID | No | Once at the next entry |
| Tick invalidates and re-primes | No | Once at the next entry |
| Tick also refuses another re-prime before the next service | No | Still one lost consumer interval |

A guard rejection **after** successful adoption now produces the next loss, whether it happens before or after commit. Ordinary recovery after one rejection counts once; a separate subsequent 700 ms silence counts twice. Sleep plus its refused first re-prime remains one loss.

I found no new double-count regression from HEAD. Multiple faults within one uncommitted interval still collapse into one interval loss, as specified. The exclusion ordering above remains a false-negative exception.

**5. Spurious suppression and deep-sleep cancellation — fixed.**

The [zero-boundary return still precedes the USB verdict](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:802), preserves the baseline and prevents the reviewed coincident bus event from enabling another pulse.

Both dev and ladder deep sleeps reach [the common teardown](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), which calls [unconditional driver-entry cancellation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1036), including when the tick was already stopped. The earlier admission return does not sleep. Plain WFI/PMU light sleep remains a separate path.

**6. Silence firing and report — mechanism fixed; measurement limits unchanged.**

[Firing-time logical checks precede masking](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214); [the actual pin check is inside the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174). A high pin prevents firing.

HEAD’s ELF confirms:

- Mask at `0x253c8`; rising store at `0x253dc`, with nine intervening instructions.
- Falling store at `0x25400`, immediately followed by unmask at `0x25402`.
- Length arithmetic and report bookkeeping outside the masked function.

**There is no 200 µs wait:** [HEAD uses `wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. The report’s later VALID bit describes recovered state, not the interrupted gap’s verdict. Its copies still do not retain the actual last-before/first-after observer pair; that measurement remains deferred to the witness.

The **2,400 isolated-injection phase/order cases passed** the nominal model, and actual decoder checks passed for recovery-bit packing, equal guard gaps and rejection-counter wrap. Those checks do not exercise the adopted-baseline → exclusion → alias sequence above. **That remaining P1 decides the NOT READY verdict.**