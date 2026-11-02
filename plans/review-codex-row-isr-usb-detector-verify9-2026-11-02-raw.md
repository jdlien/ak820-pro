**READY TO FLASH for the bench’s silence injections.** The eighth verify’s remaining P1 is **fixed** in `5c0e6249d0`. I found no new defect introduced by this round.

Reviewed the ten fixes, prior findings and dispositions, decoder, bench script and supplied ELF. The ELF’s SHA-256 matches HEAD’s manifest. Verification was read-only; no hardware was accessed.

**1. Pre-release time aging recovery — fixed.**

Both final exclusion-release paths now advance the generation, rebase `time_stamp` to the current timer, and establish a new stale frame baseline: [thread release, rowisr.c:360](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:360), [I-class release:390](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:390).

The requested observer-order replays produced:

| Trace | HEAD result |
|---|---|
| **10.020 ms** observation → exclusion at **10.025** → release at **18.010** | Release changes the stamp from **1,878 to 3,376**. |
| Tick at **18.015 ms** → row at **18.030** | Re-prime adds **one tick**, then the row adds three. Recovery remains pending; it no longer expires after only 20 µs. |
| Subsequent row at **718.030 ms** | Compares **1 ms against 700 frames** and rejects. **Two losses, one USB rejection, zero healthy services across these intervals.** |
| Rejection at **360.990 ms** → refused re-prime at **2,408.990** → row at **2,409.010** | Rejects the **56,320-tick** gap; returning row sees the changed generation. **Two losses, one USB rejection, one guard rejection.** |
| Rejection at **360.990 ms** → exclusion ends at **660.995** → silence **661.000–2,409.000** → tick/row at **2,409.010/030** | Rebased stamp leaves a **73-tick** gap. Generation mismatch excludes the interval. **Two losses, one USB rejection, no guard rejection.** |

Replaying the first trace with the parent’s release behavior reproduces its false healthy acceptance. HEAD removes that difference.

**2. Discarded time and three-state trust — fixed within the stated contract.**

The extension has only two additions, both guarded by `gap < 1500`: [re-prime:284](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:284) and [ordinary observation:305](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:305). I found no remaining path that imports excluded time or an unguarded re-prime residue.

[`take_snapI():476`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:476) preserves bus-up, freshness and pending recovery separately. Freshness requires movement **strictly less than 750 extension ticks ago**—4 ms.

| Transition | Verified behavior |
|---|---|
| Guard rejection or refused re-prime | Advances generation and captures current FRMNO as stale/pending. Movement inside discarded time cannot restore freshness. |
| Exclusion | Freezes extension and frame tracking. Final release resets both baselines; partial release and clearing an already-clear mask do not start recovery. |
| Pending start, fresh end | Performs the frame comparison. |
| Pending start, nonfresh end | Excludes the interval as unjudged, without another loss. |
| No movement during recovery | Pending expires after 1,500 additional guarded ticks—8 ms. |
| Handler’s frame rejection | Preserves freshness because it discards no time. |
| Frames stop without a flag | Freshness expires; a fresh-start/stale-end interval rejects once. Later known-stopped starts enter the declared blind spot. |

The documented limitation remains: an unflagged frame stop shortly before an aliasing silence can escape detection. That is distinct from the fixed counterexamples, whose frames remained continuously live.

**3. Conditional adoption and loss accounting — fixed.**

[Adoption:865](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:865) requires **both** current validity and `time_gen == s1.gen`.

| Activity before rejection | Result |
|---|---|
| No intervening invalidation | Adopt only the handler’s new generation; count once immediately. |
| Tick invalidated, still INVALID | No adoption; count the generation change at the next entry. |
| Tick invalidated and re-primed | Same: present validity cannot conceal the generation change. |
| Later discard after adoption | Its newer generation remains visible, including across commit. |

The model passed **210 orderings**, including preemption between the rejection’s unlock and its accounting assignments. Ordinary recovery after one rejection counted once; a separate subsequent alias counted again.

Losses remain an interval counter: several generation advances observed together coalesce. An exclusion with row services inside it can count separately at entry and release.

Within the live-bus, 13-second contract, I found no remaining reviewed ordering that duplicates a loss, misses a distinct qualifying interval, or accepts its alias as healthy.

**4. Spurious suppression and sleep cancellation — remain fixed.**

The [zero-boundary return:816](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:816) precedes USB judgment and preserves the previous baseline. A coincident bus event cannot turn that re-entry into another pulse; the event is judged on the next genuine interval.

Both dev and ladder deep sleep reach [common teardown, sleep.c:484](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), which invokes [unconditional cancellation, rowisr.c:1051](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1051), including when the tick was already stopped. The earlier admission return does not sleep. Plain WFI/PMU light sleep remains separate.

**5. Silence firing — fixed; report limitations unchanged.**

[Firing-time logical checks:214](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214) precede masking. The [actual pin read:176](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:176) remains inside the mask; a high pin prevents firing.

HEAD’s ELF confirms:

- Mask at **`0x253ec`**, rising store at **`0x25400`**, with nine intervening instructions.
- Falling store at **`0x25424`**, immediately followed by unmask at **`0x25426`**.
- Length arithmetic and report bookkeeping outside the masked function.

**There is no 200 µs wait:** [line 230 uses `wait_ms(2)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. The later VALID bit describes recovered state. The report still does not retain the actual last-before/first-after observer pair; precise timing remains the witness’s measurement.

Actual decoder checks passed for recovery packing, equal rejected gaps, counter wrap and silence status. **42,025 release-phase cases and 5,600 nominal injection cases also passed**, with outcomes judged from observation gaps rather than requested duration alone. The accepted waveform-measurement limitations remain; **no P1 blocks this bench flash.**