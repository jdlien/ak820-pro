Reviewed `row-isr` at **`a13054e5d2`**, including its previous-commit implementation, the requested plan sections, local register references, callers, host tools, and stored stage-2 ELFs. No files were modified and no hardware was accessed.

I found **one P1 affecting keyboard input**, plus P2 defects in epoch validation, accounting, and diagnostics. The timer addresses, keys, match-control bits, and PWM control constants themselves are correct.

1. **P1 — Deep-sleep exit takes the columns away from an active scan-only scanner.**  
   Location: [rowisr.c:724](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:724), with the scan-only branch at [rowisr.c:578](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:578).

   **Failure:** Enter deep sleep while scan-only is active. Wake unconditionally calls `columns_active()`, but preserves `scan_only`. Subsequent scan-only slots do not call `columns_release()` because there is no mode transition. They scan columns driven high by the parked PWM outputs instead of pull-up inputs. With Lights out keeping RGB dark, scan-only can remain active and key detection remains unreliable, including the waking press.

   The reverse transition has a smaller related defect: leaving scan-only restores PWM ownership only when the next ordinary scan slot calls `columns_active()`. Earlier LED slots can be counted as emitted without driving the columns.

   **Fix:** Restore column ownership explicitly for the resulting mode: released throughout scan-only, active before any ordinary LED arm. Exercise deep sleep with scan-only retained and RGB kept dark.

2. **P2 — The USB long-silence detector specified by D3 is absent.**  
   Location: [rowisr.c:246](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:246), [rowisr.c:307](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:307).

   **Failure:** A 350 ms or 700 ms silence of both observers can return VALID even with USB active. At nominal clock rate, the raw gaps are only 89 and 178 CT16B5 ticks. Neither trips the 1,500-tick guard. There is no `FRMNO` comparison, pending bus-event check, or USB bus-event generation in this implementation. The battery-only blind spot therefore also exists on the USB bench.

   **Fix:** Implement D3’s USB continuity-qualified comparison and merge its rejection with the observation-gap rejection into one loss transition. Until then, USB long-silence results cannot establish the promised epoch correctness.

3. **P2 — The degraded-mode exclusion is checked before degraded mode is known.**  
   Location: [rowisr.c:833](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:833).

   **Failure:** `matrix_init_custom()` starts this driver before keyboard post-init. `watchdog_boot_check()` determines degraded mode later, at [ak820pro.c:104](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/ak820pro.c:104). The one driver-side check therefore sees the initial false value. A degraded boot keeps reporting valid epochs although the watchdog bound has been removed.

   **Fix:** Declare the exclusion when `watchdog_boot_check()` actually sets degraded mode, or immediately afterward. Do not rely on the earlier initialization check.

4. **P2 — An epoch is marked serviced before the final crossing check.**  
   Location: [rowisr.c:541](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:541), [rowisr.c:568](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:568).

   **Failure:** Clear `RIS`, then get preempted across a boundary before taking `s1`. The new match remains flagged, while `s1` already belongs to its epoch. Step 6 rejects the arm as crossed. However, `last_snap` already records that epoch as serviced. The pending invocation clears the flag, reconstructs zero boundaries, and returns as “spurious.” The intended immediate service of the new epoch is lost.

   **Fix:** Make acknowledgement and entry capture coherent, and commit the serviced-epoch state at the final decision as D3 specifies. Keep elapsed-slot accounting distinct so a rejected attempt does not double-count boundaries on retry.

5. **P2 — Reconstruction uses the wrong period in scan-only and compares snapshots across a timer reset.**  
   Location: [rowisr.c:321](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:321), [rowisr.c:581](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:581).

   **Failure:** Scan-only runs at 30,000 HCLK ticks, but `boundaries_between()` always divides by 12,816. One ordinary scan-only interval therefore commonly becomes **two elapsed slots**, creating nonexistent misses and invalidating the latency classification.

   Leaving scan-only also resets scheduler `TC` after `s1`, then continues through step 6 and the exit measurement using that old snapshot. A sufficiently late entry can produce a negative reconstructed duration which becomes a large unsigned value.

   **Fix:** Associate snapshots with the active period/configuration generation. End the transition invocation after changing cadence, or capture a fresh entry baseline after the reset. Never reconstruct across a cadence change.

6. **P2 — Loss reporting and statistical validity do not follow one interval rule.**  
   Location: [rowisr.c:549](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:549), [rowisr.c:684](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:684), [rowisr.c:720](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:720).

   **Failure:** Sleep invalidates the clock but clears `have_last`, so the handler never reports that generation change as an epoch loss. Conversely, an invalid entry may be re-primed by step 6 or exit, and its duration is accepted because exit checks only `sx.valid` and generation equality—not `s1.valid`. Latency and elapsed-slot totals are committed before later observations can invalidate the service.

   **Fix:** Preserve a separately tracked loss generation across pair re-primes. Validate both endpoints and finalize each service’s statistics only after its complete validity result is known. Count each rejected interval once. If wake must wait for the tick to re-prime, enforce that ownership; currently the row handler can re-prime first.

7. **P2 — The epoch arithmetic has an overflow edge and does not enforce its advertised range.**  
   Location: [rowisr.c:324](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:324), [rowisr.c:238](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:238).

   **Failure:** The fast-path bound protects `dext * 256`, but not the subsequent subtraction of a negative phase difference. A valid example is:

   `dext = 8,388,573`, previous phase `12,720`, current phase `0`.

   The mathematical numerator is `2,147,487,408`, exceeding `INT32_MAX`; the signed subtraction has undefined behavior. This is approximately a 44.739 s row-only hold, inside the supported hour.

   Also, `EPOCH_CONSUMER_MAX` is never checked. The eight-bit loss generation can return to its starting value after 256 invalidations during a hold, making a damaged interval appear continuous.

   **Fix:** Reserve phase headroom in the fast-path threshold or use wider subtraction; enforce the consumer bound before reconstruction; use a generation representation that cannot alias within the supported interval.

8. **P2 — Page 7 mixes counting populations and its mean silently wraps.**  
   Location: [rowisr.c:335](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:335), [ak820health.py:242](/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:242).

   **Failure:** `serviced` includes scan-only, flash-guard, invalid, and initial services. Several have no elapsed sample or no elapsed-slot interval. Dividing elapsed sum by that count understates the mean; subtracting it from elapsed slots produces `None` on an otherwise uninterrupted initial run and undercounts subsequent misses.

   The 32-bit HCLK elapsed sum wraps after **89.48 seconds of accumulated handler time**, and the host divides the wrapped total by the lifetime service count. The 16-bit elapsed maximum clips at **1,365.31 µs**, so it cannot report a valid 5 ms injected interruption accurately. Eight-bit diagnostic counters wrap, and the “saturated” per-row output eventually falls back to zero when its underlying 16-bit counter wraps.

   **Fix:** Export a duration-sample count and a matched valid-interval service count, or explicit missed slots. Use a wider elapsed sum with a compatible layout, or documented modular window deltas. Widen or explicitly flag clipped maxima, and saturate counters at increment time where saturation is promised.

9. **P2 — Crossed dark rows are counted as omissions.**  
   Location: [rowisr.c:663](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:663).

   **Failure:** When `width_sum == 0` and `crossed == true`, the code enters the omission branch, increments the row’s omission count, and extends the omission run. This directly contradicts the specified dark-row rule and makes delay tests on dark or sparse frames misleading.

   **Fix:** Classify zero-width rows independently of crossing or lateness. They remain deselected and contribute neither emitted nor omitted pulses; scheduler misses remain separately observable.

10. **P2 — The new timing record excludes driver work beyond the allowed port overhead.**  
    Location: [rowisr.c:539](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:539), [rowisr.c:679](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:679).

    **Failure:** Entry timing begins after the old health hook, flag handling, and much of the observation. Exit timing ends before reconstruction, record updates, and the old exit hook. Those costs are additional to the prologue/epilogue exclusions D10 permits. On a short handler, the difference materially affects the ≤10 µs claim.

    **Fix:** Measure the complete handler independently, or explicitly bound and add the omitted instrumentation costs. Label the existing measurement as its actual snapshot-to-snapshot interval.

11. **P2 — The tick monitor still hides gaps below 128 µs.**  
    Location: [overrun_diag.c:234](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:234).

    **Failure:** The early return precedes updating `mon_max`. Repeated 100 µs gaps—already twice the nominal tick interval—can leave the reported maximum at zero. This prevents the unchanged monitor from establishing D10’s tick-gap gate.

    **Fix:** Track the maximum for every primed observation and lower the diagnostic threshold as planned. The near-8 ms tests also need synchronized observation stamps and validity/generation in the diagnostic record; the current replies do not expose them.

12. **P2 — The daemon decoder required by D10 was not updated.**  
    Location: [health.rs:34](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:34).

    **Failure:** The daemon has no `GET7` or page-7 decoder, so its normal health collection cannot retain the new scheduler evidence. Existing pages remain compatible; the new data is simply absent.

    **Fix:** Add protocol-9 page retrieval, decoding, and output to the daemon, using captured or constructed byte-layout fixtures alongside the Python decoder.

13. **P2 — Timer initialization no longer establishes a complete peripheral reset state.**  
    Location: [rowisr.c:505](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:505), [rowisr.c:824](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:824).

    **Failure scenario:** A bootloader/handoff leaves nondefault timer configuration. `CRST` resets TC/PC, not the peripheral block. Unlike the previous LLD, initialization omits `sys1ResetCT16Bn()` and leaves registers such as `CNTCTRL`, capture control, and inverted-output controls dependent on inherited state. A retained counter mode could prevent pulses; retained capture configuration could generate unintended interrupts. A failed bounded CRST wait is also silently ignored.

    **Fix:** Restore block resets after enabling the four clocks, then program the configuration. Treat a CRST timeout as a failed initialization and leave outputs safely released. This is a conditional initialization defect; I found no evidence that the present bootloader actually leaves such state.

The register audit otherwise checks out:

| Item | Result |
|---|---|
| Keys and addresses | Correct offsets; `0x5A` on B0/B2/B4 protected writes; no key on B1. |
| Match controls | MR9 IE/RST/STOP at 21/22/23; B1 MR12 STOP at MCTRL2 bit 8. |
| PWM controls | B0 `0x5AF0000F` / `0x5A00000F`; B2 `0x5AE0000E` / `0x5A00000E`; B1 masks `0xFF0`—correct. |
| Pulse configuration | Mode 1, STOP only, terminal 4095, all widths ≤2550, no duty interrupt/reset/stop. |
| Restart | All three TC writes precede their CEN writes. |
| Scheduler | HCLK, PRE 0, MR9 12815, IE+RST, priority 3. |
| Admission | Uses the whole 4096-tick window plus 120 ticks of margin; numerical deadline 8600 ticks. |
| Flags | Running handler writes the observed RIS bits to IC; crossed-path flag is left pending. |
| Ordinary scanning | GPIO initialization really selects pull-up inputs. Releasing IOEN returns those pins to GPIO; interim row helpers change only key-row modes. |
| Quiesce/hold-off | Nested holds target CT16B4; bootloader quiesce cancels diagnostics, disables scheduling, releases columns, parks timers, and makes LED pins inputs. |

The parked-output interpretation and MR=0 inactive behavior are consistent with the supplied reference and plan. Writing TC while stopped, clean restart behavior, and the exact terminal/period timing still need the waveform witness; source review cannot establish those electrical facts.

The emitted-width conversion is dimensionally correct: `acc * 4806 / 10000` produces value×ms at `k=10`, and the remainder is carried. The three 64-bit accumulators are taken and cleared under a lock. `lit_ms` retains committed-frame semantics. I found no practical overflow in this path at its normal once-per-second collection rate.

The stored stage-2 artifacts confirm **576 B heap gap for dev and 2720 B for daily/fpb**. The scale, column, and mux tables reside in flash. Dev’s allocation endpoint is `0x3BD14`, 1,220 bytes below the stored stage-1 endpoint. No `PWMD`/PWM LLD symbols remain; B0/B1/B2 vectors are weak defaults, and CT16B4 owns the new handler. The board-source grep found no executable stale CT16B1 masking call. Interrupt priorities preserve UART/system timer 0, USB 1, tick 2, row/SPI 3. Stack watermarks still require measurement.

For the first bench run after fixes, measure in this order:

1. **Dark startup, then one LED at a low code on each timer group.** Read back control registers and confirm stopped counters reach 4095. This separates routing/initialization failures from brightness calibration.
2. **A 5 ms row-only hold.** Observe current immediately; the later waveform capture must establish that pulses stop rather than repeat.
3. **Full handler time and the final masked section**, including snapshot-to-last-CEN time. The disassembly contains no divide in the arm section, but the 2.5 µs margin and 5 µs ceiling remain measurements.
4. **Scan-only → deep sleep → wake with Lights out retained**, followed by scan-only exit. Ordinary sleep tests and steady-state RGB holds would miss this combination.
5. **Known-frame accounting, omissions, and a run long enough to cross the old elapsed-sum wrap.** Short A/B windows would miss the counter failure.
6. Then perform the specified waveform, long-gap, sparse-frame, and per-colour calibration gates. Add the missing injection/stamp diagnostics before treating those gates as executable.

**Verdict: NOT READY.** P1 finding 1 decides bench bring-up readiness: the supported scan-only/deep-sleep sequence can lose keyboard input after wake. The P2 findings also prevent claiming D3/D10 correctness, even if ordinary lighting and short power comparisons pass.