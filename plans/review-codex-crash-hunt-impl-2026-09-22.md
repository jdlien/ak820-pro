# Codex review of the crash-hunt implementation — 2026-09-22

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox, 230,193 tokens. Reviewing the uncommitted Part A/B/C implementation of
[CRASH-HUNT-PLAN.md](CRASH-HUNT-PLAN.md) and the first v7 builds (21:13/21:14,
since deleted), before any flash. The hang fix in `lcd_blit_flash()` did not
exist yet. Verbatim below.

**Dispositions:** all twelve adopted. 1: stale builds deleted, rebuilt.
2: `HC_FAULT` 1–4 and `HC_STALL` refused while degraded; B6 cold-resets after
every second test. 3: the whole paused lifetime is inside one try/finally.
4: an RGB-off start is refused. 5: one snapshot under `chSysLock`, `blit_done`
re-checked, abort inside the lock, `never_started` from the snapshot.
6: "rebooted" is decided by uptime going backwards. 7: the agent treats page-6
uptime going backwards as a new boot. 8: `-g`, and `build.sh` checks that
`HardFault_Handler` resolves to `fault.c:<line>`. 9: `blits_issued`
saturates. 10: B6 expects parent `test_fault`. 11: rotation failures
propagate. 12: artifacts are staged as `.partial` and the `.bin` is published
last.

---

No confirmed High-severity defect in the supplied fault handlers. I found the following issues. **The working trees changed during review; the named ELFs now differ from the current page-6 implementation.**

1. **Medium — Page 6 changed meaning without changing version.** Current [health.rs:247](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:247) decodes report bytes 24–25 as `blit_busy_waits`; both supplied v7 ELFs emit **retry attempts** there. The current C source agrees with the new Rust decoder, but those artifacts do not. **Fix:** retire the supplied artifacts and rebuild matching firmware; version the layout if both variants must remain readable.

2. **Medium — B6’s test sequence disables the watchdog before the lockup test.** [hid_protocol.c:591](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:591) accepts destructive tests while degraded. Running modes 1, 2 and 3 within ten minutes reaches count 3; mode 4 then tests lockup with the watchdog **off**, yielding a misleading failure. Ageing the retained count does not rearm it. **Fix:** reject fault injection when degraded and require a cold reset between validation cases.

3. **Medium — Agent restoration is not guaranteed on failure.** The agent is paused before the protected region at [crash_hunt.py:382](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:382). Directory creation, CLI discovery or log opening can fail before `try`; exceptions during cleanup can also bypass `resume_agent()`. **Fix:** put the entire paused lifetime inside an outer `try/finally`, with agent restoration independent of settings verification and logging.

4. **Medium — Starting with RGB disabled silently loses its remembered effect.** Discovery at [crash_hunt.py:415](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:415) enables and changes effects. VIA reports `0` when disabled, so the backup lacks the remembered mode; restoring `0` merely disables the last discovered mode, then cleanup saves it. Verification still passes. **Fix:** refuse RGB-off starts until the actual mode can be backed up separately from enable state. This also affects `--no-flash` cleanup.

5. **Medium — Timeout classification still races completion.** [lcd_bus.c:752](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:752) computes `never_started` from different reads than the subsequent snapshot. An ISR between RIS and CNT reads can produce `IRQ_LOST` after completion was actually delivered; a stale `never_started` can override contradictory snapshot data and trigger a retry. **Fix:** exclude completion-handler interleaving, recheck completion, and derive classification/retry from one consistent final observation; classify changing observations as unknown.

6. **Medium — Recovery still reports old watchdog evidence as a new crash.** [crash_hunt.py:332](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:332) uses `wdt_fired_last_boot` alone. After one watchdog reset, any later transport timeout can generate another “WATCHDOG RESET” capture without a reboot. The periodic uptime correction added during review does not fix this branch. **Fix:** establish a boot transition using previous uptime and elapsed time before attributing the recovery to a watchdog reset.

7. **Medium — Count ageing makes recurring terminal faults disappear from the agent log.** [agent.rs:434](/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:434) suppresses identical count/record pairs. Two faults hours apart at the same PC can both have count 1 and identical format-2 records, so the second recovery is suppressed. **Fix:** include boot-transition detection from page-6 uptime in deduplication.

8. **Medium — Archived ELFs lack source-line information.** [build.sh:33](/Users/jdlien/code/ak820-pro/build.sh:33) does not enable debug information. Both artifacts lack DWARF sections; verified `addr2line` output is `Vector50 at ??:?`. Inlined `health_command` also loses its identity. **Fix:** compile with `DEBUG_ENABLE=yes` or equivalent debug flags and verify an expected source location before publishing the archive.

9. **Low — `blits_issued` wraps despite the saturating-counter contract.** [lcd_bus.c:635](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:635) increments unconditionally. **Fix:** saturate at `UINT32_MAX`, or explicitly document wrapping and handle it in rate calculations.

10. **Low — Mode 1 cannot produce B6’s stated parent.** [hid_protocol.c:592](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:592) enters `TEST_FAULT`, so the terminal parent is `test_fault`, not `raw_hid`. **Fix:** update B6’s expectation or remove that additional scope.

11. **Low — Failed CSV rotation can silently mix schemas.** [history.rs:147](/Users/jdlien/code/ak820-pro/ak820-agent/src/history.rs:147) treats rotation as successful even when both renames fail, then appends a new header and new-format rows to the old file. **Fix:** propagate rotation/read errors and append only after successful rotation.

12. **Low — Build failures can leave apparently publishable artifacts.** Files receive final names before checking at [build.sh:81](/Users/jdlien/code/ak820-pro/build.sh:81). An `nm`, copy or manifest-writing failure exits outside the explicit removal branch. **Fix:** stage the complete artifact set and publish after validation, with failure cleanup covering all three files.

The core firmware checks were reassuring:

- Both stubs use valid ARMv6-M instructions, select the frame before changing SP, and cannot fall through into `.ltorg`.
- Emergency stacks are aligned and above the normal stacks: daily `0x20003648–0x200036c8`, instrumented `0x20003880–0x20003900`. Actual maximum recorder stack use is **20 bytes for HardFault, 28 for unhandled**; `commit_terminal` is inlined.
- `chSysHalt` contains the hook and passes its incoming LR correctly. Its chain uses **36 bytes of the current stack**, rather than the emergency stack.
- Frame loads are bounded to ram0, ending before retained RAM at `0x20007ff0`. Magic commit ordering, `ready` suppression of scope cleanup, count validation/ageing, format-2 offsets and watermark bounds checked out.
- Instrumented mode 2 faults at `Vector50` (`0x8d70`) with exception **20**; mode 3 records exception **19**, PC **0**. Mode 4 commits the original fault before its second UDF causes architectural lockup. [ARM fault-handling reference](https://documentation-service.arm.com/static/5ea6ce5e9931941038def8c1#page=43). Mode 5 writes its allocation; the direct main-thread call chain consumes **1,160 bytes**, excluding interrupt/context-switch overhead.

Both manifest hashes and handler vectors matched. Shell syntax checks passed. C and Rust test execution was blocked by the read-only sandbox. I changed no files, opened no devices, ran no firmware/release build, and left the hunt untouched.