**READY TO FLASH — no P1 found in this exit-only change. Two P2s remain: the elapsed-statistics protection is not equivalent to the old verdict.** The entry detector, generation accounting, baselines and arm are unchanged.

- **P2: USB suspend does not invalidate the extension.** [rowisr.c:1106](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1106). [usb_event_kb():467](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:467) increments **`usb_gen` only**. USB suspend is not a `time_excl` exclusion; deep sleep is.

  Consequently, an entry taken with trusted USB, followed by a suspend and an aliasing silence inside the handler, can finish with unchanged `time_gen`, both snapshots valid, and zero frames elapsed. A positive reconstructed duration then enters all four elapsed fields. The old exit rejected the changed bus state/event generation. The next entry detects the event but cannot retract that sample. Reset near frame zero has the analogous hole.

  **Fix:** retain exit bus-state, pending-event, bus-generation and freshness qualification. Checking `sx.gen` cannot replace checking `ugen`. Correct the claim at line 1095 that bus events necessarily drop the sample.

- **P2: `df <= 2` changes the duration population and is insufficient for longer handlers.** Same [condition at line 1106](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1106). A correctly observed 3 ms handler is discarded, although the former span comparison accepted it. Conversely, there is no enforced “extension read as under a slot” condition: five lost CT16B5 wraps, approximately 1,747.627 ms, plus approximately 300.373 ms of preemption during which the tick keeps observing, give a 2,048 ms handler. The frame difference is zero, the extension reports approximately 300 ms, and this condition accepts a wrong positive sample. The former comparison rejects it.

  **Fix:** retain the modular span comparison for durations, including longer observed spans. Restoring the former exit validation while keeping the signed reconstruction resolves both findings.

On your five questions:

1. **The ordinary isolated aliases are rejected.** With continuously advancing frames and otherwise short handler execution, the 349.525 ms multiples within D3’s 13 s scope cannot pass the two-frame filter; the guard handles the large residues. “350 or more frames” needs the modulo qualification: six wraps give approximately **49 frames modulo 2,048**, still rejected.

   Already-off-USB operation retains the declared blind spot. An active exclusion does guarantee `s1.valid == 0`: its entry invalidates time and observations cannot re-prime until it ends. **Recovery alone does not** imply invalidity; time may already be re-primed while frames remain pending. Without an exclusion, `frm_trackI()` reads hardware even during recovery.

   For the observed **256-frame discrepancy**, either an erroneous exit or entry frame value rejects the duration. A bad entry may also trigger the unchanged entry rejection. This establishes safety for that discrepancy, not arbitrary torn values.

2. **The signed reconstruction is correct within the reviewed scope.** [rowisr.c:518](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:518) reconstructs the reset count from elapsed time minus phase. With healthy observations, zero boundaries means increasing TC; crossing a reset supplies the necessary slot through `b2`. Quantization is far below half a slot.

   Negative results can still reach the signed check with frozen frames or the bus-event hole above. The prior six-wrap example therefore still needs this guard. **Nonnegative does not establish correctness:** lost wraps can also produce positive samples.

3. **The exit’s masked source sequence is exactly `take_timeI()` plus one FRMNO read.** There is no added explicit out-of-line helper or division there; the helpers are `static inline`. Actual absence of emitted calls cannot be certified from C alone. The entry section is unchanged.

4. **The wire layout and sample denominators remain correct.** Both [Python](/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:241) and [Rust](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:698) divide by `elapsed_samples`; neither requires every service to contribute. “Shortest handler” still reads `elapsed_min`. However, the new cutoff excludes valid long samples, and `win_cpu_pct` extrapolates the accepted mean using slot rate. That estimate assumes representative samples and can be biased by this exclusion.

5. **The source establishes savings, not a defensible new microsecond total.** The former exit measured **14.53 µs**. This removes `frm_trackI`, the bus/freshness snapshot fields and `usb_distance_ticks`; it retains time observation, locking, boundary reconstruction and record updates, adding the frame cutoff and signed check. Thus it saves part of 14.53 µs, not all of it. The unchanged entry’s **7.33/9.56 µs** remain baseline measurements, not newly verified timings.

Sub 10’s `put16(&data[15], 256u)` matches the decoder. HEAD matches `5bf8de959a`; its parent’s tree matches `95ef5cbc5d`. No builds, tests or bench commands were run.