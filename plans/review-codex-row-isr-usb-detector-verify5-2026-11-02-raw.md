**NOT READY TO FLASH.** The fourth verify’s exact recovery example is fixed, but the new recovery timeout leaves another P1: an unguarded re-prime can prematurely declare a continuously live bus’s frames stopped, allowing the following aliasing silence into valid statistics.

Reviewed `832e5db7d7`, the six-fix history, decoder and bench script. The supplied ELF matches HEAD’s manifest SHA-256. Verification used source, ELF disassembly, in-memory state models and synthetic inputs to the actual decoder functions. No files were modified or hardware accessed.

1. **Finding 1 — recovery interval: partly fixed; a P1 remains.**

   The ordinary recovery now works. [`take_snapI()` retains separate bus, freshness and pending fields](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:443), and [pending starts qualify for USB judgment](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:790). A pending-start interval ending fresh is compared; one ending without fresh frames is excluded as unjudged. The previous 20 ms guard → short re-prime → pending baseline → 700 ms counterexample now produces two losses.

   **The timeout can nevertheless expire using time that was never validated.** [Re-prime adds the raw gap without applying the guard](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:280). Immediately afterward, [`frm_trackI()` uses that addition to expire recovery](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:322).

   Reproduced in the observer-order model with uninterrupted SOFs, ACTIVE, PHY enabled and no bus events:

   | Step | Result |
   |---|---|
   | A 20 ms gap reaches the guard | INVALID, generation incremented, current FRMNO captured, freshness cleared, recovery pending. |
   | Before re-prime, observers are silent for 2,048 ms | FRMNO completes one wrap and returns to the captured value. |
   | The next observation re-primes | It adds **56,320 raw ticks** without guarding them. FRMNO appears unchanged, so this addition expires recovery. |
   | A scan-only service commits before the next SOF | Its baseline is `valid=1, bus=1, fresh=0, pending=0`. |
   | A separate 700 ms silence follows | Its gap leaves **178 ticks**. Frames advance by 700, but USB checking is skipped because the starting baseline has neither freshness nor pending recovery. The interval enters valid statistics. |

   The model produced **one guard loss, zero USB rejections, and a valid service across the final 700 ms silence**. The 2,048 ms gap was already within invalid recovery; the decisive error is accepting the *subsequent* interval after committing a new baseline.

   The same timeout issue exists whenever an exclusion’s first re-prime imports a sufficiently large pre-release gap. Recovery expiry must not treat an unguarded re-prime residue as evidence of eight milliseconds without host frames.

2. **Freshness across discarded time: the previously identified mechanisms remain fixed.**

   [Staling captures current hardware FRMNO](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:264), [tracking stops throughout exclusions](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:315), and a real exclusion’s end establishes another stale baseline. Movement recorded during discarded time cannot immediately resurrect the old freshness timestamp.

   The trust rule remains strictly **less than 750 extension ticks**, or 4 ms. With ordinary observations, a bus that stops frames without a flag loses freshness; the fresh-start/stale-end interval produces one event rejection. Subsequent intervals start with frames known stopped and fall into the declared USB blind spot.

   After a stale, ordinary pending intervals remain excluded until movement or timeout. These transitions behaved correctly in the model; the P1 above concerns **what elapsed time is allowed to expire that pending state**.

3. **Fourth verify’s new P2 — clearing an already-clear exclusion: fixed.**

   Both [thread-context release](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:340) and [I-class release](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:363) require an actual nonzero-to-zero mask transition before staling frames.

   Reapplying a nonexcluded lock mode now preserves freshness and produces no false loss. Clearing one bit while another exclusion remains also does not start recovery.

4. **Conditional adoption and the earlier double-count: fixed for the reviewed races.**

   [Adoption requires both `time_valid != 0` and `time_gen == s1.gen`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:832). Present validity alone is correctly insufficient.

   | Activity between snapshot and rejection | Adoption | Loss accounting |
   |---|---|---|
   | No intervening invalidation | Yes | Once immediately |
   | Tick invalidated; still INVALID | No | Once at the next entry |
   | Tick invalidated and re-primed | No | Once at the next entry |

   The handler’s rejection preserves frame freshness, and [commit preserves the snapshot’s trust fields while adopting only its own generation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:743). A 350 ms rejection followed by a normal service counts once; 350 ms followed by a separate 700 ms silence counts twice.

   These races neither duplicate nor omit the reviewed **consumer-interval loss**. Multiple faults before a new committed baseline can still collapse into that one interval, as specified. The remaining P1 instead loses an interval *after* a new baseline is committed.

5. **New P2 — the unjudged counter corrupts the reported recovery flag at 128.**

   [`usb_unjudged` uses `sat8()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:845), which saturates at **255**. [Serialization ORs it directly with the recovery flag in bit 7](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:584), although the protocol promises a counter saturating at **127**.

   Synthetic tests through [`usb_dict()`](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:169) confirmed:

   | Actual count; actual pending false | Decoded count | Decoded pending |
   |---|---:|---|
   | 127 | 127 | false |
   | 128 | 0 | **true** |
   | 255 | 127 | **true** |

   This affects reporting, not the internal detector state. The counter needs seven-bit saturation.

6. **Spurious-entry suppression and deep-sleep cancellation: remain fixed.**

   [The zero-boundary return precedes USB judgment](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:781), without replacing the baseline. The reviewed coincident bus event cannot turn that same-epoch re-entry into another pulse.

   Both dev and ladder deep sleeps use [the common teardown](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), reaching [unconditional cancellation in the driver’s sleep entry](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1017), including when the tick was already stopped. The earlier admission return does not sleep. Plain WFI/PMU light sleep does not use this deep-sleep cancellation path.

7. **Silence firing and report: mechanism fixed; measurement limitations unchanged.**

   [Firing-time state checks remain before masking](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214), appropriate for these main-loop-maintained states. [The actual pin read remains under the mask](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174); a high pin prevents firing.

   HEAD’s ELF confirms mask at `0x25180`, rising store at `0x25194` with nine intervening instructions, and falling store at `0x251b8` immediately followed by unmask at `0x251ba`. Length arithmetic and bookkeeping remain outside.

   **There is no 200 µs wait:** [HEAD uses `wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. The report copies state before firing and after that scheduler delay. Its post-wait VALID bit describes recovered state, not the interrupted gap’s verdict. It still lacks the actual last-before/first-after observer pair. Equal-gap attribution and wrapping rejection-counter decoder tests passed.

8. **Finding 7 — documentation: partly fixed.**

   [The header now correctly names the record rather than the report](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:114), and [“As built” explicitly defers synchronized observer stamps](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:715).

   Remaining inconsistencies include [the gate still requiring those stamps “in the record”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1156), and [the detector overview describing only trusted starts](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:386), omitting the new pending-start behavior.

The isolated bench injections matched their nominal model predictions. They do not exercise the delayed re-prime sequence above. **The deciding P1 is recovery expiring on unvalidated re-prime time, followed by a live-bus alias being accepted as healthy.**