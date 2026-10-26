# Codex: P5a, the settings profiles' store and HC_PROFILES (2026-10-25)

Two rounds, verbatim, then dispositions.
1. `plans/review-prompt-p5a-code.txt`: qmk_firmware-ak820pro `93e55f78..d5a3a4aa`
   (branch `gremlin/p5a`; `d557d2ae`, the palette made const, before it).
2. `plans/review-prompt-p5a-verify.txt`: `d5a3a4aa..5ecc9a32`.

## Round 1 (d5a3a4aa)

**I would fix two issues before flashing P5a:**

- **[P1] Failed writes leave cache changes that retries trust.** [profiles.c:197](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:197): real [wear_leveling_write():693](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:693) updates its cache **before** programming. If a save’s body write fails, retrying identical settings can skip that body as “unchanged,” then commit the state and report success despite incomplete durable data. Likewise, failed magic publication at [profiles.c:264](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:264) leaves the block formatted in RAM. Latch/recover write failures before allowing further operations. [profiles_test.c:28](C:/Users/jdlien/code/ak820-pro/scripts/profiles_test.c:28) currently returns failure **before** updating its fake cache, hiding these cases; test cache-first failures and retries.

- **[P2] Effect ID 0 silently becomes effect 1.** [profiles.c:120](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:120) recognizes zero as `RGB_MATRIX_NONE`, but applying it reaches [rgb_matrix.c:620](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:620), which clamps zero to one. An imported record therefore changes to another effect while returning `PROF_OK`. Reject/skip zero or implement explicit supported semantics. The fake setter lacks this clamp, and the test mentioning ID 0 never exercises it.

**Flash accounting is safe on the current paths.** Unchanged `eeprom_update_*` operations stop before the attribution hook; changed operations consume its pending writer synchronously. Profile writes still reach the backing-store session hook and count as `FW_OTHER`. See [eeprom_driver.c:52](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/eeprom/eeprom_driver.c:52) and [flash_stats.c:60](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:60).

Otherwise, I found no additional blocker in placement, normal write ordering, CRC coverage, recovery/restore gates, token/page handling, preview cancellation, flush, HID dispatch/bounds, or daily exclusion of dev subs. Compiled profile frames are modest; the main-thread stack is separately reserved at 2 KB. Board timing with compaction and durability after a power cycle remain required.

Limitations: local `main`, `origin/main`, and the working plan lack Decided 9–12 and the reply-byte table, so those additions remain unverified. I verified the requested firmware revision and inspected its ELF artifacts; process execution was unavailable, so I did not rerun tests/builds.

## Round 2 (5ecc9a32)

**Both findings are resolved in `5ecc9a32`. I found no new blocker to a controlled dev/BT flash on gremlin.**

- **P1:** [profiles.c:81](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:81) latches failure and blocks subsequent writes. Save/delete/load and Begin check it; [tx_close():243](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:243) preserves it.
- **P2:** [profiles.c:135](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:135) rejects ID 0’s mapping, preserving the current effect and reporting effect-skipped.
- **No write remains in flight when the latch trips:** programming waits for BUSY to clear before returning errors ([hal_efl_lld.c:338](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:338)); erase also completes synchronously.
- **Failed consolidation propagates failure**, but the latch cannot undo its erase. Whole-EEPROM loss remains the existing backend risk ([wear_leveling.c:303](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:303)). Other EEPROM writers remain enabled and could later consolidate the cache.
- **Reads remain potentially misleading:** [menu helpers:90](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:90) and [HC sub 0:305](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:305) can show/export attempted, nonpersistent state; sub 0 still returns OK. Treat that as a cache snapshot, not verified flash contents.
- **One qualification:** a load that *first triggers* failure has already applied settings before its active-byte write ([profiles.c:234](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:234)). Subsequent loads apply nothing.

I inspected exact commit blobs and revised tests. Execution was denied, so builds, mutants and 136 B remain your reported results. Board timing with consolidation and reboot durability still need validation.

## Dispositions

- **P1 (wear_leveling_write() updates its cache before the flash): fixed
  in `5ecc9a32`.**
  - The first failed profile write latches (`TX_FAILED`, a spare bit of
    the transaction byte). That refuses every later profile write, and a
    load before it applies anything, until a reboot reloads the cache.
  - The test's fake now updates its cache before it fails, as the real
    layer does.
  - Four mutants aim at the latch.
- **P2 (effect id 0 clamped to effect 1): fixed in `5ecc9a32`.** Id 0 is
  never assigned, and a record holding it loads without its effect.
- **Round 2's notes: no change.**
  - After a failed write, reads are the cache, not verified flash: that's
    the latch's premise, and the failure is reported when it happens.
  - A load that first trips the latch has already applied its settings.
    They landed, through their own writers; only the active marker didn't.
  - A cut consolidation losing the whole EEPROM is the existing backend
    risk, which the plan states.
- **Flashed `5ecc9a32` (dev, token `0x8bfea199`) on the keyboard on
  gremlin at ~21:13.** The board's measure and the flash.sh round trip
  followed (GREMLIN-RESULTS §20m).
