I agree with the architecture, but revision 1 needs corrections before implementation. The main blockers are the 62.5 µs timer lifecycle, missed-slot detection, timing instrumentation, stage 2’s brightness claim, and the precision path’s buffer/accounting contract.

No files changed; no builds run. Below, `qmk/` means `qmk_firmware-ak820pro/`, and `kb/` means its `keyboards/a_jazz/ak820pro/` directory.

The decision log’s dispositions should be:

| Decision | Verdict and evidence |
|---|---|
| CT16B4 scheduler, separate one-shot PWM timers | **Agree, conditional on proving stop/restart/output behaviour.** B4 is free; separating scheduling from pulse generation removes callback duration from the nominal cadence. It does not guarantee delivery of every field. [Timer inventory and semantics](./docs/sn32f299.md:689). |
| Fail dark, count omissions, never replay | **Agree. The specified implementation cannot yet do this reliably:** one latched match flag cannot count elapsed slots; the deadline check must also be atomic with arming. See D2/D3 changes below. |
| Explicit zeros for `NO_LED` | **Agree.** The bounds check is compiled only for software PWM. Correction: nine holes mean **27 invalid LED-index lookups per field**, because each position is visited for three colours—not nine. [Driver:515](./qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:515). |
| Correct colour order and discard the old rainbow calculation | **Agree with the steady-state code derivation; physical wiring remains unverified.** For key row `k`, software submits R at slot `3k−1`, B at `3k`, G at `3k+1`, modulo 18. That does not independently prove which physical LED each mux pin drives. [Driver:491](./qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:491). |
| Reject the purported 30 µs unselect delay | **Agree.** It is six compiler-barrier loop iterations at this timebase, not a calibrated 30 µs wait. Calling it “nothing” is unnecessary; call it short and uncalibrated. [Driver:158](./qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:158). |
| Move precision upstream of the byte conversion | **Agree.** CIE value lookup and subsequent mixing both quantize into bytes. A wider downstream LUT cannot undo either. [Colour conversion:22](./qmk_firmware-ak820pro/quantum/color.c:22). |
| Start acquisition in matrix initialization | **Agree, but starting the timer alone does not establish Bootmagic correctness.** Its first scan must already contain samples that can start debounce. See D1 below. [Bootmagic:63](./qmk_firmware-ak820pro/quantum/bootmagic/bootmagic.c:63). |
| Qualify 72.8% as callback occupancy; measure the complete handler | **Agree with the qualification; disagree that D10 currently measures the complete handler.** Existing hooks include preemption and exclude re-arm/IRQ machinery. Scheduler `TC` alone introduces different errors. [Health:65](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:65). |
| Finer staging, same-session comparisons, 3% preservation gate | **Agree.** However, stage 2 cannot retain cadence merely by leaving the existing re-arm sequence unchanged. |
| Common bootloader quiesce; retain dark frame through wake | **Agree.** Both address recorded failures, and common quiesce must cover Bootmagic’s direct jump too. [Bootloader override:127](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog.c:127), [sleep admission:263](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:263). |
| Power savings require measurement | **Agree.** Awake idle still spins; CPU percentage is not battery percentage. [Config:248](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:248). |
| Consolidation can overwrite a complete short press | **Agree.** Continued acquisition does not preserve transitions during blocked consumption. Its duration must be remeasured after optimization, rather than assumed to remain 58 ms. [Publication contract](./plans/MATRIX-PUBLISH-PLAN.md:235). |
| Keep STOP-without-RST and a strict duty ceiling | **Agree as conservative rules.** The asserted simultaneous STOP/RST outcome and terminal-equality behaviour still need verification. Also, codex did explicitly identify the STOP/RST trap; “codex lacked” is inaccurate. [Raw design:83](./plans/review-codex-row-isr-design-2026-10-31-raw.md:83). |
| Keep the scan’s “columns already high” argument | **Conditional.** It requires the preceding output to have finished and ownership restoration to behave as assumed. The present 62.5 µs design violates the stopped-counter premise. |
| Keep the rebuilt rig and per-stressor delivery counts | **Agree.** Fix isolation, timing references and the raw-counter limitation below. |
| Keep the numerical reason for postponing I²C unmasking | **Agree as a load estimate:** divide by remaining CPU fraction, rather than add the occupancy percentage. The merged 3.1–3.3 ms range is reasonable; stage 4 should use its actual preceding occupancy. |
| Keep measured object sizes | **Agree with measuring existing artifacts; correct their classifications and distinguish object totals from linked savings.** Figures below. |
| Reject prepared frames and field-boundary handoff | **Agree with rejecting the expensive prepared-frame scheme for the initial rewrite. Disagree that this also rejects pointer swapping.** Immediate slot-visible pointer swapping can retain today’s committed-frame contract using the existing two buffers. |
| Reject a universal 25 µs handler ceiling | **Agree.** It is 20% at 125 µs and 40% at 62.5 µs. The revised 20/12 µs targets correspond to 16%/19.2%. Keep separate deadline-tail gates. |
| Reject 444 Hz as the destination | **Only conditionally agree.** Make 889 Hz an experiment with an explicit precision/brightness tradeoff. Clean omission counts alone do not justify it: preserved output then uses only about 619 width codes, and byte channel 1 changes by approximately −17%. |

The revision-0 corrections listed at the end are otherwise appropriate. “Both missed: nothing yet” should be replaced by the findings below.

The numerical corrections are:

| Quantity | Checked result |
|---|---|
| Present mean slot | `1/3876 = 258.002 µs`; field `4.64396 ms`, `215.333 Hz`. |
| Callback decomposition | `187.9 × 3876 = 72.83%`; minimum-body contribution `62.02%`; inferred scan increment `(187.9−160)×3 = 83.7 µs`. These remain elapsed-time estimates, not exclusive execution costs. |
| Nominal old light | `256/4.8 MHz = 53.333 µs`; **20.67%** of the mean slot. Code 255’s assumed pulse is `53.125 µs`, giving **1.144% per die**. All are conditional on the unresolved old waveform. |
| 125 µs cadence | 8,000 slots/s; **444.444 fields/s and samples/s/row**; row interval 2.25 ms. |
| 62.5 µs cadence | 16,000 slots/s; **888.889 fields/s and samples/s/row**; row interval 1.125 ms. |
| Preservation factors | **4.845** and **2.4225**, before calibration. Top widths round to **1,235 ticks / 25.729 µs** and **618 ticks / 12.875 µs**, respectively. |
| Available preserved width levels | About **1,236 levels / 10.27 bits** first; **619 levels / 9.27 bits** second. G5’s 10.3-bit statement applies only to the first cadence. |
| Fringe at 200°/s | Old adjacent/max separation: **3.10′/6.19′**. At 444 Hz: **1.5′/3′**. At 889 Hz: **0.75′/1.5′**, before jitter. G3’s “under 2′” does not hold at the first cadence for the widest colour pair. |
| Handler shares | 25 µs at 258 µs: **9.69%**; 20 µs at 125 µs: **16%**; 12 µs at 62.5 µs: **19.2%**. |
| I²C expansion estimate | `2.6/(1−0.16…0.20) = 3.095…3.25 ms`; at 72.8%, about **9.56 ms**. |

The baseline measurement supporting the first rows is [hardware.md:778](./docs/hardware.md:778). D4 also incorrectly uses the **1,235-tick first-cadence width** when calculating second-cadence headroom. With the correct second-cadence width and a 12 µs handler, nominal headroom is **37.625 µs before the guard**, not approximately 25 µs.

The GPIO masks and PFPA values check out against [config.h:9](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:9) and [keyboard.json:142](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keyboard.json:142):

- Mux rows: A `0xB00`, B `0x30`, C `0x3C00`, D `0x73F00`.
- Key rows: A `0xC0000`, B `0x8C000`, D `0x80000`.
- Columns: A `0xF0`, C `0x43FF`.
- PFPA: B0 `0x3332`, B1 `0x0F00`, B2 `0`.
- Used PWM masks: B0 `0xF`, B1 `0xFF0`, B2 `0xE`.

The register corrections are small but important:

| Register detail | Disposition |
|---|---|
| B4 MR9 IE/RST bits 21/22; STOP bit 23 clear | Correct. Nominal words: `MCTRL=0x5A600000`; MR9 `5999` first, `2999` second. Verify the actual period rather than relying solely on `−1` arithmetic. |
| B0/B2 MR9 STOP bit 23 | Correct: stop-only `MCTRL=0x5A800000`. |
| B1 MR12 STOP bit 8 in MCTRL2 | Correct. |
| B0/B2 PWMCTRL IO bits `20+n` | Correct. Mode 1 encodes as zero; active words are `0x5AF0000F` and `0x5AE0000E`, with IO-disabled words `0x5A00000F` and `0x5A00000E`. |
| Write key | Required for the small timers’ MR/MCTRL/PWMCTRL writes. **TMRCTRL is not on the keyed-register list.** Remove the key from TMRCTRL writes and the risk list’s claim about it. |
| Match equal to terminal | The plan’s categorical “never goes inactive” conflicts with the manual summary’s special equality case. Keep `< terminal` as a conservative restriction; distinguish equality from `> terminal`. |
| STOP clears CEN | Already documented by the current timer header. Treat explicit CEN restart as the contract, with hardware verification—not an entirely unanswered source question. |

Sources: manual pp. 118–149 as summarized in [sn32f299.md:706](./docs/sn32f299.md:706), and [sn32_ct.h:346](./qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/sn32_ct.h:346).

I inspected existing objects and saved ELFs without compiling:

- `sn32f2xx.o`: **2,324 B executable text, 252 B rodata, 482 B initialized writable data, 548 B bss**. Thus “2,576 B code” includes rodata; **482 B is not constant data**.
- The three configurations are 160 B each; PWMDriver objects are 24 B each. **552 B reclaimable RAM is correct.**
- PWM LLD executable text is **3,188 B**; generic `hal_pwm.o` adds **304 B**. These object totals are not guaranteed linked savings.
- White’s saved dev ELF has **224 B heap gap**; black’s `fcb7ae00b4` has **152 B**. Their spare space above the floor is **96 B and 24 B**, respectively.
- White’s dev load occupies approximately **240,944 bytes**, consistent with “241 kB,” or **235.3 KiB**. The `.bin` is padded to 256 KiB and cannot measure used flash.

The configuration/object layouts are in [PWM header:139](./qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.h:139); the saved artifacts are [white](./ak820pro-builds/out/via-dev-5c8c5f5ea8-20261030-172709.elf) and [black](./ak820pro-builds/out/via-dev-fcb7ae00b4-20261029-000229.elf).

These are the concrete section changes I would make.

1. **D2/D3: make timer lifecycle and deadline admission explicit before allowing 62.5 µs.**

   An 85.3 µs one-shot has **not stopped at the next 62.5 µs slot**, even though its useful light pulse finished after 12.9 µs. D3 assumes stopped counters, leaves IO enabled on LED-only slots, writes duties, then writes TC. That assumption is false at the second cadence; it can also fail at 125 µs when a late previous arm is followed by an early next handler.

   Choose one defined mechanism: shorten the terminal window to a proven per-cadence bound, or explicitly stop/release all three timers before rewriting/repositioning them on **every** serviced slot. Verify what TC writes and CEN changes do to the actual PWM output, including whether selecting the mux before arming creates an extra pulse. Preserve the strict width ceiling.

   Put the final epoch/deadline check **inside the same critical section as arming**. Otherwise UART/USB can preempt between “fits” and CEN. Include the last timer’s arm skew and handler tail in the guard.

   **Gate:** deliberately delay service at different phases, including across several slots. No repeated or overlong pulse, no wrong-row pulse, bounded critical section, correct zeros, and omissions attributed to the affected row/colour.

2. **D3/D10: replace the flag-count and modulo-time assumptions.**

   `RIS` has a bit per match source, not a queue of match occurrences. Two or twenty MR9 matches still produce one bit. Scheduler TC is also modulo one slot: a handler delayed 5 ms can appear to have very low latency.

   Track elapsed slot epochs using the independent system counter together with scheduler phase; detect a match occurring during service as well. Keep separate counts for elapsed slots, serviced handlers, emitted pulses, omitted pulses and longest omission burst. Define whether LED rotation follows elapsed or serviced slots; keep key acquisition independently fair.

   At exit, TC is **entry latency plus elapsed handler time**, not handler cost. It also excludes the instructions after the read and exception return. Use wrap-aware entry/exit differences, an independent elapsed-time cross-check, and account for the remaining assembly/port overhead. Label preempted elapsed occupancy honestly.

   **Gate:** known 1-, 2-, and multi-slot holds must produce the expected elapsed-slot deficit; no modulo alias may report them as healthy. Re-prime at sleep and cadence changes.

   D10 also needs a wire layout: page 4 has only four reserved bytes, insufficient for all proposed fields. Preserve its existing fields and add a diagnostic page. Update **Rust CLI/daemon and Python**, not Python alone. [Current page layout](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:360), [Rust decoder](./ak820-agent/src/health.rs:476).

3. **Stages 1–3: stop claiming neutrality “by construction.”**

   Stage 2 removes scan work while the old callback still re-arms at its end. That necessarily shortens slots and changes average drive. [The re-arm is at driver:782–800](./qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:782).

   Either introduce fixed scheduling before removing the scan overhead, or temporarily compensate the old timing and prove the resulting cadence/current. Record any remaining timing change rather than describing it as unchanged.

   Stage 0 also cannot entirely be “no firmware change”: existing `HC_PEEK` permits **SRAM only**, and the mask probe holds the global lock rather than providing the specified 5 ms row-only IRQ hold. Add a small, bounded diagnostic build for register capture/row-only holds after collecting the untouched baseline. [Peek restriction](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:991), [existing probe dispatch](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1299).

4. **D1/stage 1: complete the integration contract.**

   Turning all three `SN32_PWM_USE_CT16B*` options off while retaining `HAL_USE_PWM TRUE` hits the PWM header’s **“no CT peripheral assigned” error**. Disable the unused HAL PWM service too. Replace the `&PWMDn` column-map representation; those objects should no longer exist. Define board-owned LED-count/configuration interfaces rather than relying on `RGB_MATRIX_SN32F2XX` side effects. [Configuration error](./qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.h:93).

   Prime all six rows before Bootmagic’s first debounce scan, with a bounded synchronous initialization scan or an explicit readiness wait. Merely starting an asynchronous timer can leave Bootmagic’s first scan empty; its second scan then only starts debounce. Ensure later RGB initialization cannot clear acquired matrix state. [Initialization order](./qmk_firmware-ak820pro/quantum/keyboard.c:459), [lite matrix initialization](./qmk_firmware-ak820pro/quantum/matrix_common.c:145).

   Use verified vendor register members or explicit register offsets. The LLD’s small-timer structs declare `MR[5]`; copying their `MR[9]` indexing into the new code inherits an out-of-array C access. [Timer structs](./qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/sn32_ct.h:270).

   **Gate:** Bootmagic with settings already valid and after settings reset; RGB disabled; all existing build flavours; no PWM objects/vectors retained accidentally; early common quiesce safe before full RGB initialization.

5. **D8: keep the masked copy initially, but separate publication from preparation.**

   The copy is a reasonable first implementation. Its actual documented bound is **10–16 µs**, not a measured universal 10 µs. “Within the guard” must be tested against other delays. [Flush:971](./qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:971).

   A cheaper alternative remains available without prepared `[18][15]` frames: immediately swap the existing RGB front/back pointers under a short lock, then copy the new front into the reusable back **unmasked**, preserving state for effects that update only selected LEDs. This has the same next-slot visibility as the present copy. Thus RAM-heavy preparation and field-boundary adoption should be rejected separately from pointer swapping.

   Also, today’s “committed dark” means the **front buffer** is dark; it does not prove that an already-programmed hardware pulse has ended. Sleep’s explicit blanking must remain authoritative.

   **Gate:** partial-update effects, unchanged Solid flushes, “two renders” consumers, power-cap changes during rendering, and dark admission through sleep/cleanup. Re-measure the masked interval if buffers become 16-bit.

6. **D4/D8/D9/stage 5: define physical output and power accounting together.**

   A global omission percentage cannot correctly discount a nonuniform frame: dropping a bright red slot and dropping an empty slot have different costs. Accumulate emitted width sums per colour/slot, then normalize to the existing equivalent-byte-drive units outside the ISR. Specify the treatment of `lit_ms` separately.

   Retain the model interface, not an unconditional promise that its coefficients survive. It includes **base power and an 8.64 mW lit overhead**, as well as colour coefficients; changing cadence can change overhead even when pulse energy is preserved. [Battery model:556](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:556).

   Fit preservation against **incremental LED milliwatts after subtracting the candidate’s own dark baseline**, using forward/backward colour holds. A 5% tolerance on whole-board current can hide most of the LED load at value 64. Electrical power is a proxy for luminance, so retain fixed-exposure optical checks.

   The second cadence also violates “every stored value within 5%” under simple rounding: channel 1 maps to two ticks instead of the ideal 2.4225, approximately **17.4% low**. Decide whether low-code compatibility or 889 Hz wins; do not silently waive G4.

   For precision, specify both wide render and wide committed buffers: **972 B total, +486 B over today**, before metadata. One 486 B front buffer alone cannot retain uncommitted 16-bit rendering. Put the register map in `const` flash; an init-built 15-entry pointer/key table otherwise spends approximately 120 B of the recovered RAM.

   **Gate:** per-colour/low-drive preservation, power-model residuals at both cadences, explicit buffer/metadata budget and the 128 B floor on each board’s feature set. Keep 889 Hz optional until those pass.

7. **D6/D7 and risks: strengthen coexistence and wake gates.**

   Removing interrupt-side GPIO mode writes addresses the demonstrated I²C race. Keep the unlocked HAL hooks, bus admission and recovery arbitration. Add the **5 ms wake/pre-sleep deadline** to Q3; normal transactions use 10 ms in the actual macro despite the stale nearby “20 ms” comment. [RTC timeout](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:36).

   Keep the SPI DMA size sweep, but repeat it at **both cadences and after precision work**. “10–60 µs” is not an established maximum delay: higher-priority interruptions and simultaneous pending sources still contribute. Include VIA key assignment while LCD DMA runs—the repository’s reliable original flash/DMA reproduction—not only RGB saves. [Recorded hang](./docs/hardware.md:579).

   Add actual **20 kHz tick rate and maximum service gap** to the gates. The present monitor records only gaps ≥128 µs, so it cannot certify a 62.5 µs scheduler or detect every lost 50 µs tick. [Monitor thresholds](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/overrun_diag.c:198).

   Retain the normal ChibiOS prologue/epilogue initially. A bare low-priority handler can be interrupted by an OS-aware handler; the nested handler’s epilogue does not perform the outermost return work. Q7 needs a port-level correctness argument, not merely passing debug checks. [Port epilogue](./qmk_firmware-ak820pro/lib/chibios/os/common/ports/ARMv6-M/chcore.c:124).

   Finally, black’s unexplained deep-sleep reset remains open. Preserve its retained phase diagnostics; bound any new CRST waits. Test long **fully unplugged** BT sleeps and charging/knob wakes on both boards, beyond short rig cycles. Preserve the SRAM WFI routine and its delay. [Open two-board failure](./plans/BACKLOG.md:152), [SRAM wake dependency](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:313).

8. **Rig section, stage 6 and release check: close the observability gaps.**

   `raw_edges` is counted by comparing the consumer’s old and fresh matrices; it is **not an ISR transition counter**. A whole press overwritten during cleanup is absent from it too. The bench already records one-short raw counts with every press delivered. Add temporary ISR-side transition counts for the rebuilt rig’s keys, or avoid claiming that the existing chain locates every loss. [Counter implementation](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:122), [historical anomaly](./docs/test-bench.md:650).

   Define reliable release dwell as well as press dwell. Short-tap acceptance should **not worsen**; “must not move” incorrectly rejects improvement. Faster sampling removes a bounded sampling component, not 4.6 ms from every latency: under uniform phase, the expected mean sampling reduction is approximately **1.20 ms first / 1.76 ms second**.

   A plain MCU-driven MOSFET is not galvanically isolated. Prefer an optocoupler/PhotoMOS arrangement, qualify its turn-off and polarity, and timestamp actual contact closure at the rig—not just the host serial command.

   In stage 6, append both the stable profile effect ID and the QMK custom effect entry; update the effect-name table and VIA definition. Test preview/cancel, both Win/Mac remembered states, host backup/restore and transitions between byte and wide effects. Stable profile IDs and QMK mode numbers are different namespaces. [Effect IDs](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rgb_effects.c:15), [profile application](./qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:355).

   Keep consolidation input loss explicitly characterized separately from the zero-loss ordinary-write gate. Also soften “only fix”: unavailable SRAM vectors rule out the proposed interrupt solution, but do not themselves rule out a wholly SRAM polling erase routine. That would require separate proof and substantial work; it need not enter this rewrite.

The remaining questions and cheapest useful measurements are:

| Question | Cheapest measurement on this bench |
|---|---|
| What does the current driver actually emit during a stall? | Register capture plus repeated row-only IRQ holds at Solid white; INA228/240 fps establish gross energy/hot-row behaviour. A scope/photodiode is needed to establish individual pulse shape. |
| Does stop-only PWM restart cleanly, including zero and terminal edges? | Small dev diagnostic on all three timers; widths 0, 1, terminal−1 and invalid widths, with delayed service. Record TC/CEN and gross optical output. Fast waveform proof still needs borrowed optical/scope equipment. |
| Which physical row/colour does each slot drive? | Single-key, single-colour patterns for every key row, with a slow tagged diagnostic slot sequence. Full-board Solid and untagged 240 fps video cannot uniquely establish sub-frame ordering. |
| How much column-release/select/restore settling is necessary? | Dev delay sweep with held cross-row chords, each colour active, using rig commands and ISR samples; repeat on both boards and retain margin. |
| Can both cadences meet latency and omission limits? | Corrected epoch/handler instrumentation, short health windows, mixed LCD/UART/flash load, per-slot omissions and longest bursts; include the tick rate. |
| Are preserved brightness and battery units still valid? | INA228 charge deltas and MAX17048 voltage, dark-subtracted forward/backward white/R/G/B holds, then low-drive holds. Fit each cadence separately. |
| Are the smallest pulse steps optically distinct? | Camera/logger can reject obvious plateaus or nonmonotonicity. They cannot establish 20.8 ns optical resolution; that remains open without a photodiode/scope. |
| Does I²C preemption preserve the clock and wake contracts? | Per-kind transaction times, 5 ms recovery path, stuck-bus restart, release/bracket errors and daemon residuals, followed by sleep/wake cycles under load. |
| Does cleanup lose presses, and how long does it block after optimization? | Stall/flash counters plus phase-swept 25–40 ms rig presses across forced cleanup; compare ISR transitions, consumed transitions, debounced events and host events. |
| Is black’s long-sleep reset independent of this rewrite? | Preserve its phase diagnostic build; fully unplugged long BT sleeps, logger wake edges and retained reset records. White’s clean short sleeps cannot settle black’s failure. |
| Is the precision RAM budget viable? | A complete allocation ledger now; later linker/stack-watermark checks for each flavour. Existing object savings alone do not prove it. |

The strongest version of this plan keeps 444 Hz as the first complete, calibrated release candidate, then earns 889 Hz through the additional low-code, timer-lifecycle, power and coexistence gates.