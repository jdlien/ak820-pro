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