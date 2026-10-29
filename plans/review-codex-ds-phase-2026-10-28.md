# Codex: the deep sleep's watchdog phases (2026-10-28)

The keyboard on gremlin took a watchdog reset ~8 min into an untouched deep
sleep on 10-28 (GREMLIN-RESULTS §21), and the record named only
`deep_sleep()`. JD: "you can build the diagnostic, but you should
collaborate with the agent on Buzz". qmk_firmware-ak820pro's
`gremlin/ds-phase`: `8ec0c8b9..27d1105d` (the phases, sites 28-31; on dev
builds the sleep under way kept through a reset, op 24 slot 9), then the
fixes `27d1105d..fcb7ae00`; the host side main `e5e019e`. The prompts:
`plans/review-prompt-ds-phase.txt`, `-fix.txt`; the raw replies:
`plans/review-codex-ds-phase-raw.md`, `-fix-raw.md`. Both builds went onto
JD's board on Buzz before their reviews came back (JD: flash first, fix
after), `27d1105d` at 23:51 and `fcb7ae00` at 00:03.

## The review, verbatim (27d1105d)

No **P1** finding: I found no new path that should hang, reset, lose a key, or corrupt operational state. There are two **P2** diagnostic issues and one **P3** wording issue.

1. **P2 — Power-reset invalidation is deferred too long.**  
   [sleep.c:436](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:436) checks reset cause only on the first diagnostic read or sleep ([sleep.c:493](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:493), [sleep.c:543](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:543)). An LVD/POR boot can retain the magic but damaged/stale contents, then watchdog-reset elsewhere before either call. The next boot sees only WDT flags and accepts those contents. Thus immediate POR/LVD reads are protected, but a subsequent warm reset can resurrect rejected evidence.

   **Fix:** perform validation/invalidation once on every boot, immediately after reset-cause capture, before normal operation. Keep the read-time guard as a fallback.

2. **P2 — An interrupted sleep reuses its sequence number.**  
   [sleep.c:451](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:451) assigns `wake_seq` to the attempt; [sleep.c:479](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:479) assigns it to the stray snapshot. It advances only when the completed wake is appended at [sleep.c:374](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:374).

   If attempt N records strays and resets before that append, the next sleep also gets N. If that sleep has no strays, slot 8 still describes the failed sleep but now matches the successful sleep’s ring entry.

   **Fix:** reserve an attempt sequence at teardown and use that reserved value throughout, including the ring append. Document gaps for interrupted attempts and distinguish sequence from “entries written.”

3. **P3 — The phase comments claim more than the markers prove.**  
   [sleep.c:328](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:328) says `DS_WAKING` means the core “never ran flash code again.” It actually means the SRAM marker committed and `ph_own` has not subsequently committed. Flash instructions could have started executing, or an already-expiring watchdog could reset during the wait.

   Similarly, `DS_ASLEEP` is written **before** WFI, and `DS_UNLOCKED` **before** unmasking ([watchdog_record.h:27](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.h:27)).

   **Fix:** describe marker boundaries, without asserting the instantaneous execution state or cause. Also describe `ds_kept` as “inherited and not replaced this boot”: it can survive multiple boots, not necessarily originate in the immediately preceding one ([sleep.h:119](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.h:119)).

The other requested checks look sound, with these limits:

- **Execution and timing:** I checked the existing dev and daily ELF helper bytes. Both retain the SRAM literal pool, two phase stores, unchanged delay, then the first flash read. The added stores extend the delay slightly; they introduce no wait or peripheral change. They can still affect reproduction of an incompletely understood timing fault. `ds_keep_boot()` stays outside the lock; `ds_last_begin()` runs after locked admission. The doubled reset flags add no new reset condition. Packed accesses introduce no new alignment hazard in these builds. The bulk-copy casts discard volatile semantics, but there is no concurrent writer on these main-task paths; the progress and terminal stores remain volatile.

- **Scopes:** [watchdog_record.c:98](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c:98) saves/restores the entire encoded word. Consequently, nested scopes correctly report their phase as parent and restore that phase afterward; the outer cleanup restores housekeeping. `ready`, the null-pointer fallback, and main-loop-only usage are consistent. No new ISR writer appeared.

- **Startup and memory:** [rules_memory.ld:78](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/common/startup/ARMCMx/compilers/GCC/ld/rules_memory.ld:78) places these objects after `__ram0_noinit__`; [crt1.c:236](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/common/startup/ARMCMx/compilers/GCC/crt1.c:236) stops clearing there. This port uses **`CRT0_AREAS_NUMBER`, default 8**, confirmed by the ELF’s 128-byte area table. The supplied addresses and 184-byte heap gap match; there is no overlap with `.ram7` or DFU magic.

- **Retention limits:** `DSL1` alone does not authenticate arbitrary firmware layouts or bootloader activity. Bump/invalidate it for incompatible layouts; invalidate before DFU if cross-flash evidence must be rejected. I found no ROM stack/data map proving preservation of this new region. The [DFU shim:37](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/platforms/chibios/bootloaders/sn32_dfu.c:37) only shows the magic handling and ROM call.

- **Host:** [health.rs:173](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:173) matches sites 27–31 without colliding with 32+. The [C test:190](C:/Users/jdlien/code/ak820-pro/tests/watchdog_record_test.c:190) correctly covers direct phase encoding, warm-reset decoding, and enclosing cleanup. It does not cover the two retained-sleep lifecycle issues above.

For the incident, **29 supports the wake/flash-transition candidate but does not prove it; 31 supports an unlock/ISR problem but also covers subsequent main-thread recovery; 28 cannot distinguish remaining asleep from failure before the waking marker.** Clock-ceiling software resets require slot 9: the ordinary crash record intentionally rejects non-WDT resets.

This was a read-only source and ELF review. I could not execute the tests because process creation was denied.

**Verdict: OK to keep on the board.**

**Dispositions** (all in `fcb7ae00`):
- **P2, validation deferred: fixed.** `sleep_boot_check()` runs right after
  `watchdog_boot_check()` in `ak820pro.c`; the read and sleep paths keep
  `ds_keep_boot()` as the fallback.
- **P2, the sequence reused: fixed.** `ds_last_begin()` reserves
  `wake_seq++` at the teardown; the ring entry and slot 8 use `ds_last.seq`;
  slots 0-7's last two bytes are the next number. The magic is now `DSL2`,
  so nothing `27d1105d` wrote is accepted.
- **P3, the wording: fixed.** Each phase is described as a boundary, not a
  proven state (`watchdog_record.h`, `sleep.c` above `ds_deep_wfi()`);
  `ds_kept` as inherited and not yet replaced.
- **Not from codex:** slot 10, the record the boot inherited, frozen into
  `.bss` at boot: on battery the next ladder sleep replaces slot 9 within
  minutes of a reset, so the overnight run would have lost it.
- Codex's open question on the bootloader's use of that RAM: Buzz's session
  re-flashed the same build after a sleep and slot 9 came back with the
  inherited flag set (`history/ds-phase-check-20261028-2350/`), and slot 10
  after `fcb7ae00`'s re-flash (`history/ds-phase-check-20261029-0002/`).

## The re-check, verbatim (fcb7ae00)

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

**Disposition:** the P2 fixed in `scripts/overrun_diag.py`: `wakes()` walks
the last eight numbers with `walk_attempts()`, skipping a gap instead of
stopping at it and leaving out empty slots; `walk_back()` is unchanged for
the OE and monitor rings. Tested offline on codex's case (8-15 written, 16
cut short, next 17: entries 9-15), a wrap past 0xFFFF, an empty ring and
the first sleep, without importing the module (it loads `hid`).
