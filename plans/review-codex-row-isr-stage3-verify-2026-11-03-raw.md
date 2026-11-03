**READY TO FLASH — for the controlled dev flash on white to obtain measurements.** No remaining P1 found at `3673b234f0`. This does not establish stage 3 acceptance.

1. **The settle fix is correct for both periods.** [scan_settle()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:721) computes elapsed ticks modulo **12,816**, or **30,000** in scan-only. Both operands and their difference fit safely in `int32_t`.

   With `t0=12810` and `TC=4`, it computes `-12806+12816=10`, so a 96-tick wait continues. Likewise, `29994→4` gives 10 in scan-only. There is **one TC read per loop body**, confirmed in both saved ELFs; the sign check and exit comparison use that same sample. A reset between the initial `t0` read and the first loop read is handled correctly. A reset after a loop’s read cannot invalidate the already elapsed delay.

   **Bound qualification:** without preemption, the wait ends within `settle_ticks` plus one loop iteration. That is not an unconditional wall-clock bound: higher-priority interrupts can extend it, and an interruption spanning whole periods can cause additional waiting through modulo aliasing. Neither causes an early sample.

   No reachable stopped-counter hang was introduced. MR9 resets without stopping; IRQ holds leave the counter running. Sleep/quiesce stop it from locked thread paths that cannot execute during this handler. Cadence changes return before scanning, so the period remains fixed throughout the wait.

2. **Rig refusal and sentinel handling are correct.** [rowisr_rig_set()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:756) compares the completed candidate pair before storing anything. Duplicate candidates preserve both old positions; swapping distinct positions works. Row `0xFF` preserves the entire position; an invalid row or column also preserves that position. These are position-level semantics, not independent coordinate updates.

   The ISR only reads the positions, and the sole setter runs in the main thread, so preparing candidates outside the lock is safe. The ELF’s locked portion is exactly four byte stores. Refusal remains silent at protocol level: sub 12 returns the retained positions and still reads/clears counters.

3. **Daily’s no-op is safe at its sole call site.** [RIG_NOTE](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:778) evaluates plain nonvolatile locals, with no side effects, and marks `prev` used. The saved daily ELF eliminates the old-matrix load and rig instrumentation entirely. The macro would evaluate side-effecting arguments if introduced later.

4. **The handler cost change is confined to settling.** Comparing the saved dev ELFs, `Vector90`’s instructions are unchanged after normalizing relocated addresses, including its masks and calls. The masked call remains the local `Vector90+0x978` tail. The scan helper adds period-load setup, a sign branch per iteration, and an addition when negative; its only call remains `input_note_row_scan`. Settling remains outside the mask. The FRMNO edit changes only its comment.

The host decoder now correctly exposes byte 31, and `sections` preserves “no reply” instead of mislabelling it. One nonblocking leftover: [print_status()](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:200) still omits `col_map_fault`; only JSON exposes it. Add the warning there to complete the earlier diagnostic note.

Review used source and saved-ELF inspection only. No files changed; no builds, tests, or board access.