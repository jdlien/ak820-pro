**NOT READY for stages 0–3 as written.** Two corrections remain in stage 2’s acceptance specification. Neither requires restoring the withdrawn battery long-gap guarantee.

The eighth review’s exclusion/recovery fix **is met**: D3 now holds exclusions active, retains a loss generation across re-primes, and stage 2 exercises recovery before the row handler returns. Reset/disconnect injections and one-loss accounting are also present.

1. **Must-fix before building — stage 2: the explicit seven-second expectation still overrides the rate-dependent rule.**

   [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:895) requires predictions from measured duration and clock rate, but subsequently requires seven seconds on battery to be **INVALID by the guard** unconditionally.

   That outcome is correct only near the nominal rate. For example, at **187,425 Hz**—400 ppm below nominal—a seven-second interruption leaves **1,255 ticks**, approximately **6.69 ms**, which passes the 8 ms guard. This follows from [CT16B5’s configuration](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:766); the [IHRC reference](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:145) supplies no bound excluding that rate. D3 correctly permits this alias.

   **Fix:** label the numerical residues as nominal examples and make every explicit outcome conditional on the measured rates and duration uncertainty. For a mandatory guard-rejection test, select a duration whose entire uncertainty interval leaves a residue safely above 8 ms.

2. **Must-fix before building — stage 2: the specified battery test and independent timing method do not establish the no-USB case.**

   [The gate](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:890) times the injection around its raw-HID command. But this bench’s battery-powered, raw-HID-accessible state **still has active USB data and SOFs**. Cutting power alone therefore exercises the USB witness again. Cutting data removes that command/reply timing path. These states are explicitly distinguished in [the bench documentation](/Users/jdlien/code/ak820-pro/docs/test-bench.md:143).

   Host command round-trip duration also includes dispatch and reply latency; it is not the actual interrupt-silence duration without a stated uncertainty bound.

   **Fix:** distinguish power source from USB-witness availability. Specify a delayed injection armed before disconnect, executed after bus discontinuity has settled, with its result retained through reconnection. Measure the actual mask/hold interval using start/end markers on the independent waveform witness, or another explicitly bounded independent method. Use that measured interval for finding 1’s predictions.

Two remaining factual corrections are nonblocking:

- **Should-fix — D3’s row-only scope:** [“of any length”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:488) contradicts the preceding one-hour supported interval. Replace it with the stated bound.
- **Should-fix — D3’s watchdog claim:** [“a longer silence ends in a watchdog reset”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:528) still treats approximately 12.3 seconds as an upper bound. [Hardware.md](/Users/jdlien/code/ak820-pro/docs/hardware.md:349) records an observation; the [watchdog reference](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:801) makes the timeout ILRC-dependent. State the USB proof’s time scope separately from the watchdog’s measured recovery.

I found no further regression in the earlier publication, scan-fairness, brightness-calibration, waveform, bootloader, sleep, priority or SPI safeguards. The register keys/masks, STOP clearing CEN, IOEN-to-GPIO behavior, GPIO atomics, I2C direction switching, conditional light arithmetic, and saved object/ELF resource figures check out. No additional running interrupt-side GPIO MODE/CFG writer surfaced. Stop/restart waveform behavior and baseline pulse energy appropriately remain prerequisites for later stages.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under that condition; 62.5 µs remains experimental.** Consolidation still permits short-press loss and a ≥25 ms pass as the explicitly retained exception.

All inspection stayed inside the repository. No files were modified and no builds ran.