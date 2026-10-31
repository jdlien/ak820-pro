**No P1 findings. Three P2 findings; no P3 findings.** I reviewed `fcb7ae00b44..6ce20ccef98` and the supplied dev ELF, read-only. No rebuild or board access.

1. **P2 — The boot guard opens before the retained census is protected.**  
   [sleep.c:470](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:470) sets `ds_kept_checked = true` before clearing or freezing `DSI_WATCH` at lines 476–489. `sleep_boot_check()` runs with interrupts enabled.

   **Scenario:** a watchdog reset leaves `OPENED|WATCH`. During the next boot’s validation, a PWM, SysTick, UART2 or USB interrupt passes both tests and changes the preceding boot’s census. A USB entry can replace the retained `INSTS`; another handler can replace `last`. The subsequent freeze preserves that contamination. The ELF confirms this ordering.

   **Fix:** keep the guard false until validation and census disposition finish, with publication ordered against ISR access.

2. **P2 — A previous wake’s census can acquire the failed sleep’s sequence number.**  
   [sleep.c:594](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:594) derives the census’s sequence from `ds_last`, but [sleep.c:531](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:531) starts a new attempt without invalidating the previous closed census.

   **Scenario:** sleep N completes; N+1 then resets at site 29, 64 or 66, before `ds_irq_open()`. After reboot, slot 11 contains N’s counts, `INSTS` and `CLOSED` flag, labelled N+1. This falsely associates successful interrupt restoration with an attempt that never reached unmasking.

   **Fix:** invalidate a non-frozen census when the new attempt begins, or retain its actual owning sequence.

3. **P2 — Nested hooks can erase IRQ identities, beyond the documented lost counts.**  
   [sleep.c:502](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:502) updates `seen` through an unprotected read-modify-write; lines 508–509 write `last` after that work.

   **Scenario:** USB loads `seen`; priority-0 UART2 preempts, records its bit and returns; USB resumes and stores its stale mask, erasing UART2’s bit. USB then overwrites `last`, although UART2 entered more recently. The compiled instructions permit both interleavings. `n_all` can similarly undercount.

   **Fix:** serialize the short shared-state update, or explicitly treat missing bits and `last` as unreliable under nesting. Doubling the final store protects reset retention, not concurrency.

The other requested checks support keeping this build running:

- **Hook safety and cost:** the ELF confirms calls from USB, UART2, SysTick, RGB row and PWM tick handlers. These are ordinary C handlers, with exception-return state preserved before the call. The inactive hook executes about a dozen instructions plus the call, including an eight-byte stack save; it takes no lock and touches no peripheral. It also runs at the **20 kHz GPT rate**, so the aggregate cost matters more than the row ISR alone. I found no concrete timing-budget violation; its actual effect on throughput remains unmeasured.
- **Startup and special handlers:** startup masks interrupts before RAM initialization; `chSysInit()` unmasks afterward. HardFault, the unhandled-vector recorder and the NMI context-switch handler do not invoke this prologue hook. The early bootloader branch also precedes unmasking. The new hook does not insert a C call into those naked handlers.
- **Retention:** apart from finding 1, an interrupted window freezes for the following application boot; the next reset clears that frozen census, and another reset does not resurrect it. New windows are intentionally suppressed during the frozen boot. POR/LVD or a magic mismatch clears it. A same-layout warm reflash follows these rules; the bootloader detour does not itself run `ds_keep_boot()`.
- **SRAM wake path:** the ELF keeps the helper and literals in SRAM. Both marks come from the live caller’s stack. The 260-iteration delay remains intact; the dummy flash load precedes both site-64 stores. No earlier flash access was introduced.
- **IDs and memory:** sites 64–67 fit the existing byte fields and complemented 16-bit path; cleanup restores the complete saved word. The loop-site assertion has the correct boundary. The ELF confirms a 128-byte heap gap without overlap. The current [health.rs:180](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:180) already names 64–67; older executables retain the numeric IDs as `unknown_N`.

For interpretation, `INSTS` is non-clearing, but its prologue sample can precede a different value read by the LLD. SysTick contributes to `n_all` and `last=15`, never `seen`. NMI is outside the census. `last` is not the active/hung-handler identity: a stuck USB handler can keep receiving SysTick interrupts. Also, `CLOSED` means the close marker was reached; a few instructions and scope cleanup still precede the actual return.

**Verdict: OK to keep on the board.**