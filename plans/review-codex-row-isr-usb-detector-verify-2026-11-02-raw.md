**NOT READY TO FLASH for the bench’s silence injections. Finding 1 remains a P1:** discarded time can keep frozen USB frames “fresh,” allowing a later aliasing silence to pass.

Reviewed `ca5c82e2b9` and `53a432e7e6` against `fdbad7e4a5`. The supplied ELF matches HEAD’s manifest hash. This was read-only source, disassembly, arithmetic and decoder verification; no hardware access or changes.

1. **P1 — USB trust: partly fixed.**

   The PHY check closes the stale-SOF/PHY-disabled case. With uninterrupted observations, frozen FRMNO also ages out after 4 ms. However, [the freshness test](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:386) uses `time_ext`, while [guard invalidation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:265) discards the gap without invalidating `frm_seen_ext`.

   A concrete counterexample, with stale ACTIVE, PHY enabled and no event flag:

   - FRMNO stops shortly after its last observed movement.
   - A 20 ms observation gap is rejected; those 20 ms never enter `time_ext`.
   - The tick re-primes and ordinary row services establish a new baseline. FRMNO remains “fresh” despite having stopped over 20 ms earlier.
   - A subsequent 700 ms silence leaves 178 timer ticks, rounded to 1 ms. Frozen `df=0` passes the tolerance, and the freshness age still remains below 750 ticks.

   **That second silence produces no loss.** This exceeds the documented residual of frames stopping within the preceding 4 ms: the lost extension time stretches that window. Freshness qualification must be invalidated across a discarded gap and reacquired from subsequent frame observations.

2. **P1 — Armed silence surviving deep sleep: fixed.**

   [The driver’s sleep entry now cancels first](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:928), independently of whether the tick is already stopped.

   Both the [dev sleep](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:944) and [idle-ladder sleep](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:997) use the common path, which calls this entry [before teardown and WFI](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:478). Its earlier return aborts admission without sleeping.

   Plain WFI/PMU light sleep does not use this deep-sleep cancellation; an actual tick stop retains its existing cancellation. Arming during established scan-only/tick-stopped operation remains possible as intended.

3. **P1 — USB rejection bypassing duplicate-epoch suppression: fixed.**

   [Boundary reconstruction and the zero-boundary return](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:723) now precede the USB verdict. The reviewed same-epoch re-entry with a coincident bus event returns before row rotation or pulse arming.

   The pending USB discontinuity can be judged on the next genuine interval; the spurious return does not commit a replacement baseline.

4. **P2 — Generation adoption hiding discarded time: partly fixed.**

   Keeping `s1` unchanged fixes the original duration relabelling: [exit accounting](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:902) rejects a duration spanning a changed generation.

   But [`time_valid != 0`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:758) does **not** establish that no tick invalidation occurred after `s1`. The tick can invalidate, then re-prime before rejection:

   | State at USB rejection | Generation advance | `epoch_losses` accounting |
   |---|---:|---|
   | No intervening tick loss | +1 | Once immediately |
   | Tick invalidated, still INVALID | +1 | Once at the next entry |
   | Tick invalidated and re-primed | +2 | Once immediately; `seen_gen` adopts both |

   Thus this race itself does not newly count the same uncommitted interval twice or omit its loss counter. **Its remaining defect is baseline adoption:** the third case still [labels the old snapshot with the new generation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:687).

   The ordinary pulse path’s pending-match check prevents commitment after such a long preemption. However, [scan-only and flash-skip paths commit directly](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:791), allowing the following interval to be accepted across discarded time. Adoption needs a generation comparison against `s1`, not merely present validity.

   The prior concern about an aliasing interruption *inside* the handler also remains: step 6 and exit take time-only snapshots, so duration accounting can precede the next entry’s USB rejection.

5. **P2 — Marker availability and endpoint offsets: partly fixed.**

   [Firing-time checks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:188) now reject a lit/previewed indicator and re-read the actual pin under the mask. Moving the state checks before masking is sound here: their state is maintained by main-loop code, while the pin read catches the tick’s output.

   The falling edge is fixed: the ELF has the GPIO store at `0x25008`, immediately followed by `cpsie i` at `0x2500a`. Bookkeeping and resynchronization follow unmasking.

   **The rising-edge claim still disagrees with the ELF.** Masking occurs at `0x24fb0`; the rising store is at `0x24fe2`, with **24 intervening instructions**, including the compiler-moved length arithmetic from [line 185](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:185). It is not merely a pin load, branch and store, and cannot meet the plan’s [under-0.1-µs allowance](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1133). The marked interval remains correctly inside the mask, but its uncertainty is understated.

6. **P2 — Diagnostic evidence: partly fixed.**

   Fixed: [both rejection paths record their spans](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:748); microsecond requests support fractional milliseconds; the added USB/report fields match the host decoder. Constructed wire-layout and modular-delta checks passed.

   Remaining limitations:

   - [`rowisr_time_read()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:298) copies existing state; it neither observes the timer nor returns the observer’s `time_stamp`. The report therefore still lacks the synchronized endpoints needed to determine the actual observation gap.
   - The [200 µs wait](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:215) compiles to `chThdSleep(38)`. Scheduling and interrupt work can delay the read further. With the tick stopped, it also does not guarantee a second scan-only observation and re-prime.
   - **New misleading attribution:** a generation change during that wait may come from USB rejection, not the guard. A 350/700 ms alias can therefore be printed as [“the guard rejected it”](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:282). The last rejected guard gap may also belong to an earlier injection.

   The bench appropriately leaves 7.9/8.1 ms ungated, but [its other length-based predictions](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/silence_check.sh:52) still do not constitute the plan’s measured observation-gap proof.

7. **P3 — Overstated comments: partly fixed.**

   The [HAL-hook ordering](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/tmk_core/protocol/chibios/usb_main.c:169), [span/512 tolerance](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:744), and observation-gap/13-second distinction are corrected.

   However, [the revised injection documentation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.h:101) retains the single-store endpoint description and asserts observer offsets below 0.1 ms. The latter conflicts with [the plan’s explicit service-latency qualification](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:618). The new guard-only interpretation of the report is also incorrect, as above.

**Additional introduced defect — P2: a healthy row-only hold can lose USB trust.** Freshness is updated only by `take_snapI()`, not by the tick. If a row-only hold spans an integer 2.048-second frame-counter wrap, its next FRMNO can equal the previous value despite continuous SOFs. The tick has correctly advanced `time_ext`, so [freshness expires](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:389) and the interval is rejected as a USB event. Its actual modulo clock comparison would agree. This violates the promised exact reconstruction of row-only holds maintained by the tick.