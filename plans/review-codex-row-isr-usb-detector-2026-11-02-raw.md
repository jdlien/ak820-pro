Reviewed **`fdbad7e4a5`**, the working-tree decoder, and the matching dev ELF/bin; their hashes match the manifest. This was a read-only review, with arithmetic and decoder-layout checks, no rebuild or hardware access.

1. **P1 — “Trusted” does not establish continuous SOFs.**  
   [rowisr.c:359](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:359), [rowisr.c:674](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:674).

   The repository already documents the counterexample: after the bench’s data cut, the driver can remain `USB_ACTIVE` while `FRMNO` stops ([sleep.c:42](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:42)). Successive short row intervals then compare approximately 0 ms against 0 frames and remain “trusted.” A subsequent nominal 700 ms silence leaves 178 CT16B5 ticks, rounds to **1 ms**, and passes against frozen `df=0`. The record therefore claims a trusted, accepted comparison where the independent clock is absent.

   There is also a concrete LLD path to ACTIVE with the PHY disabled: a status word containing **SUSPEND and an earlier, pending SOF** first disables the PHY and suspends, then the same handler’s SOF branch calls `_usb_wakeup()` and restores ACTIVE. That branch does not restore the PHY. See [hal_usb_lld.c:240](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:240) and [hal_usb_lld.c:303](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:303).

   The generation catches that initial suspend interval, but subsequent frozen intervals become trusted again. The detector needs a stronger continuity qualification; an unobservable disconnect must be reported as outside its guarantee.

2. **P1 — An armed silence can survive deep sleep when the tick was already stopped.**  
   [rowisr_diag.c:159](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:159), [indicators.c:226](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/indicators.c:226).

   Arming while the tick is stopped is allowed—and needed for the scan-only tests. But `pwm_tick_stopI()` returns immediately when already stopped, before `rowisr_diag_cancelI()`. Deep-sleep entry calls that function after stopping the row scheduler ([sleep.c:484](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484)).

   Consequently, an injection armed during tick-stopped operation can remain armed across sleep and fire after wake, blocking input for up to eight seconds outside the intended test window. Cancellation must occur even on an already-stopped tick, or explicitly at deep-sleep entry.

3. **P1 — USB rejection bypasses the duplicate-epoch guard.**  
   [rowisr.c:695](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:695), [rowisr.c:705](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:705).

   Rejection sets `valid1=false`, so `boundaries_between()==0` is never checked. Unlike an eight-millisecond guard failure, a USB bus event need not span a scheduler slot.

   If a spurious re-entry in an already-serviced epoch coincides with a bus event, it proceeds through row rotation and can arm another pulse when `s6.tc` remains before the deadline. Step 6 checks crossings **since this entry**, not whether the preceding invocation already serviced this epoch. This violates the one-service rule and can alter the displayed row/pulse. Epoch ownership must survive a statistical rejection.

4. **P2 — Adopting the generation can make a duration across a real loss look valid.**  
   [rowisr.c:698](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:698), [rowisr.c:846](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:846).

   `s1.gen` is replaced, but `s1.ext`, `s1.tc`, and `s1.valid` remain the original observation. If the tick invalidated and discarded a gap between that observation and rejection, the old timestamp is now labelled with the recovered generation. Exit can accept its duration despite the missing time.

   Even without that race, USB rejection leaves the duration acceptance test enabled while `valid1` rejects the service’s entry interval. Preserve the original measurement snapshot and track the adopted baseline separately. USB continuity fields captured at step 6 and exit are currently unused, so a long aliasing interruption inside the handler is also only detected by a later entry, after duration accounting may have accepted it.

5. **P2 — The marker’s availability is checked at arm time, not firing time; its documented offsets are understated.**  
   [rowisr_diag.c:164](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:164), [rowisr_diag.c:174](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174).

   Win Lock or its preview can turn on during the delay. If C15 is already high when the injection fires, there is no rising marker edge.

   Both edges are correctly inside the mask, but their separation from mask/unmask is more than one store. The ELF shows function-call overhead before the rising edge, and indicator bookkeeping plus three diagnostic updates after the falling edge. The plan’s two-store, under-0.1-µs-per-end allowance is therefore unsupported. Recheck/reserve the pin at firing and bound the actual instruction paths.

6. **P2 — The record cannot provide all the evidence its labels and gates require.**  
   [rowisr.c:676](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:676), [rowisr.c:470](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:470), [rowisr_diag.h:84](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:84).

   Bus-event rejection does not update `usb_last_dt_ms` or `usb_last_df`; “last rejection’s spans” therefore shows an older disagreement, or initial zeros.

   Also, `time_valid` is the state **at the later read**, usually already re-primed. Neither reply retains the rejected observation gap or synchronized observer/marker endpoint stamps. Thus the required near-threshold predictions cannot be established from this record. The integer-millisecond injection interface also cannot request 7.5, 7.9, 8.1 or 8.5 ms ([rowisr_diag.c:297](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:297)).

7. **P3 — Several comments overstate the implementation.**  
   [usb_main.c:169](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/tmk_core/protocol/chibios/usb_main.c:169) says the hook runs before the stack acts, but HAL reset/suspend/wakeup have already changed the driver state. [rowisr_diag.h:101](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:101) should distinguish observation-gap thresholds from requested silence lengths and retain the 13-second scope. `dt_ms >> 9` is approximately **0.1953%**, rather than exactly 0.2%.

**(a) Generation and counting.** In the ordinary thread-fired injection, the intended adoption works: if the tick/guard rejects before entry, generation mismatch suppresses the USB comparison; if USB rejects first, adopting its generation prevents counting that same rejection again next time. `time_invalidateI()` also avoids another bump while already INVALID. Multiple checks of the same uncommitted consumer interval collapse to one reported loss.

A tick invalidating between snapshot and rejection does not inherently produce a second loss count; the unsafe part is relabelling its earlier timestamp, finding 4. The 32-bit loss generation resolves the reviewed 16-bit alias. The previously dispositioned over-hour behavior—rejecting without an invalidation/bump—remains unchanged.

**(b) and (d) USB conditions and hook coverage.** ACTIVE is a conservative eligibility condition, not a necessary condition for receiving SOFs: enumeration states can receive them too. It is insufficient to prove continuity.

| Condition | Result |
|---|---|
| Ordinary host suspend | Pending SUSPEND or the HAL transition/generation catches the interval, subject to the stale-SOF problem above. |
| Resume | The LLD restores PHY/ESD and clears RESUME without a HAL event. Normal suspended-state recovery remains covered by the earlier suspend generation and subsequent SOF-triggered wakeup. |
| Wakeup | Generation changes only when `_usb_wakeup()` actually transitions from SUSPENDED. A raw WAKEUP serviced while ACTIVE does not bump it. |
| Data disconnected, VBUS retained | Frozen FRMNO with stale ACTIVE is possible; finding 1 applies. |
| VBUS cut, data retained | SOFs and enumeration continue on this bench. This correctly remains USB-qualified; it is not the no-USB test. |
| Plain WFI | It need not stop the peripheral clocks. The idle hook restores any changed PHY bits, but supplies no detector continuity event. |
| PMU Sleep | Can disable the PHY without a HAL bus event. Its existing live-bus admission restriction reduces exposure; the detector itself does not track this transition. |
| Deep sleep | The explicit time exclusion and cleared pair prevent reconstruction across sleep, independently of PHY behavior. |
| First interval after enumeration | If its starting snapshot was untrusted, the USB comparison is skipped. It may remain extension-valid; it is not a USB-certified interval. |

The hook executes synchronously in USB interrupt context, before QMK queues/deals with the event. RESET, SUSPEND and WAKEUP increment the generation; ADDRESS, CONFIGURED, UNCONFIGURED and STALLED do not. The latter events do not inherently interrupt SOFs.

HAL state changes preceding the hook do **not** create a row-snapshot race: USB priority 1 outranks row priority 3, and snapshots mask interrupts. The omissions are raw LLD events that raise no HAL callback and intervals skipped because their starting endpoint was untrusted.

**(c) Arithmetic.** The conversion and unsigned modulo arithmetic are correct:

- One tick is `2/375` ms; `(dext*2+187)/375` rounds correctly.
- Frame subtraction and modular distance correctly produce a distance from 0 through 1024 ms.
- At the hour bound, `dext=675,000,000`; the conversion numerator is `1,350,000,187`, safely within 32 bits.
- FRMNO’s one-millisecond steps versus sub-millisecond row intervals are covered by the three-millisecond allowance. Requiring frame movement every row would be wrong.
- The closest nominal wrap alias inside 13 seconds is **49.152 ms** at six CT16B5 wraps. The next close approach is **5.461 ms at 14.330539 s**; exact coincidence is **131.072 s**. The scoped arithmetic is sound for the stated board clock envelope and continuous SOFs.
- Seconds-long row-only holds remain reconstructable when the tick preserves the extension. Their frame comparison uses the full extended duration.

Beyond 13 seconds there is no promised rejection proof. At sufficiently long consumer intervals the growing tolerance can cover the entire modular distance range. The watchdog does not strengthen that proof.

**(e) Injection behavior.** The spin correctly accumulates successive unsigned 16-bit CT16B5 differences, counting wraps through frequent polling. Eight seconds needs only 1,500,000 ticks. Odd requested milliseconds round down by half a timer tick. The counter remains running in this awake thread context.

The delay is serviced from housekeeping, before the synchronous PCF transactions in that pass ([ak820pro.c:615](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/ak820pro.c:615)). It therefore does not interrupt an in-progress clock-chip I2C transaction.

During the requested mask, keyboard sampling stops, USB requests/enumeration can time out, UART bytes can be lost, and software-PWM outputs retain their instantaneous levels. RGB one-shots still park. Main-loop and kernel timekeeping can miss CT16B5 wraps; diagnostic readings after a long injection must not be treated as undisturbed uptime. A nested row hold’s tick countdown pauses and its physical duration stretches.

The watchdog remains unfed throughout. Normal prior passes feed it during the arming delay; eight seconds fits the stated nominal timeout, but the temperature graph is not a guaranteed minimum. The refusal limits are implemented; the marker-delay and already-stopped cancellation defects remain.

**(f) RAM and timing.** The ELF confirms:

| Item | Previous dev | This dev |
|---|---:|---:|
| Heap gap | 576 B | **536 B** |
| `rec` | 60 B | **72 B** |
| `last_snap` | 12 B | **16 B** |
| Row-handler local stack allocation, excluding saved registers | 60 B | **76 B** |

The snapshot adds FRMNO, bus-generation, state and conditional INSTS reads. The ELF retains those volatile reads at step 6 and exit even though their USB results are unused. The longer saved snapshot also adds commit stores inside step 6.

The new frame-span divide is outside the mask, and the step-6 crossing check remains division-free. Snapshot reads and the record’s software fields are protected coherently. The additional work consumes part of the unchanged 120-tick admission margin; its timing and stack watermarks still need measurement. Static inspection alone does not establish a timing failure.

The host decoder’s USB and silence offsets passed constructed wire-layout checks.

**Verdict: NOT READY for the bench’s silence injections.** The deciding P1s are false USB trust with frozen FRMNO, an injection surviving already-stopped-tick sleep, and USB rejection bypassing duplicate-epoch suppression.