**No P1. One P2 diagnostic integration issue; no P3.**

**P2 — The host wake-ring reader stops at the newly intentional sequence gaps.**  
[sleep.c:454](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:454) correctly reserves the attempt number, but [overrun_diag.py:119](C:/Users/jdlien/code/ak820-pro/scripts/overrun_diag.py:119), called by `wakes()`, stops at the first missing number. With completed entries 8–15 and attempt 16 interrupted, the next sequence is 17 and the reader returns **no wakes**, hiding the retained history. After attempt 17 completes, it returns only 17.

**Fix:** give `wakes()` gap-tolerant traversal bounded to eight attempts, retaining sequence checks and excluding empty records. Keep the shared contiguous-ring reader’s behavior for its other callers.

The firmware fixes otherwise check out:

- **Boot validation:** `watchdog_boot_check()` captures reset cause before `sleep_boot_check()`. Raw-HID dispatch and sleep execution start afterward; neither fallback runs prematurely. Validation needs only initialized RAM and the captured cause.
- **Slot 10:** its payload and validity flag start zero in `.bss`. Only successful magic/reset-cause validation populates them. Later sleeps cannot overwrite that copy.
- **Sequence:** reservation precedes teardown; ring indexing and stray snapshots both use `ds_last.seq`. Modulo-8 indexing remains bounded, including uint16 wrap.
- **Comments/magic:** the phase descriptions now express marker boundaries; `ds_kept` allows older inherited records; DSL1 is rejected.
- **Sleep safety:** no new wait, reset condition, peripheral operation, or sleep-control change. Existing pre-commit ELFs confirm the 152-byte dev heap gap and unchanged SRAM-helper instructions; only its flash-address literal moved.

This was read-only review of the exact commit changes and existing artifacts; no rebuild or board test was run.

**Verdict: OK to keep on the board.**