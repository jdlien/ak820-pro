# Codex: P5b, the settings profiles' menu and the Next and Previous keys (2026-10-25)

Three rounds, verbatim, then dispositions.
1. `plans/review-prompt-p5b-code.txt`: qmk_firmware-ak820pro `5ecc9a32..761f4cdb`
   (branch `gremlin/p5b`; `5ecc9a32` is P5a, the mainline).
2. `plans/review-prompt-p5b-code-verify.txt`: `761f4cdb..28fac431`.
3. `plans/review-prompt-p5b-code-verify2.txt`: `28fac431..9ca4ed6a`.

## Round 1 (761f4cdb)

Yes—fix these two issues before flashing.

- **[P2] Deferred active-byte failures are reported as success.** [profiles.c:326](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:326) clears `pend` and discards `wr8()`’s result; [profiles.c:489](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:489) then returns `PROF_OK` unconditionally. Load a different slot and fail that byte’s write during sub 6: flush acknowledges success, although reboot can lose the choice. Cache readback cannot establish durability. The scheduled-write path likewise latches failure without showing “Save failed.” Propagate the write status, report an existing latch, and surface the deferred failure in the menu; retain the prohibition on retries until reboot. Add failure injection specifically for the deferred byte.

- **[P2] The profile-name overlay gets overwritten by RGB polling.** [menu_glue.c:179](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:179) posts the loaded name without updating the parameter poller’s baseline. If the load changes lighting, the next 10 Hz `param_status_task()` detects it and replaces the name with “RGB Off,” an effect name, brightness, etc. ([param_overlay.c:197](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:197)). Re-prime the poller after a successful load. The supplied tests call `prof_step()` directly, so they miss this integration.

Otherwise, I found no additional static blocker in the signatures, invalidation sites, confirmations, four-frame navigation, bounded names/compositions, or press-only dispatch. Normal settle ordering prevents sleep before the active write; backup includes the pending choice, and an accepted restore supersedes it. Bootloader is correctly row 8.

All 14 changed files match `761f4cdb`. The dev ELF confirms the 136 B heap gap and a separate 2,048 B process stack; that is not a runtime stack-margin measurement. Shell execution was unavailable, so I inspected the tests but could not rerun them or measure board timing.

## Round 2 (28fac431)

**Yes—one P2 remains before flashing.**

- **[P2] Flush still reports success after a deferred failure.** At [profiles.c:493](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:493), the latch is checked only when `pend` is nonzero. But `write_active()` clears `pend` **before** attempting the write. Therefore: load another slot → `prof_tick()` fails → sub 6 returns `PROF_OK`. A second flush after a failed flush likewise returns success. Check the failure latch independently of `pend`; clean/no-pending should remain OK. Add assertions after the failed settle and repeated flush in [profiles_test.c:555](/C:/Users/jdlien/code/ak820-pro/scripts/profiles_test.c:555), before resetting.

`apply_live()` treating that error as failure is correct: cache readback cannot prove persistence. A full block restore already refuses a latched board at Begin; a normal firmware flash/reboot clears the RAM latch.

The menu half closes the original finding: [menu.c:1878](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1878) reports the failure, including at the next open because closed-menu processing does not consume the edge.

The profile-name overwrite is fixed. There is a **nonblocking feedback regression** at [param_overlay.c:191](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:191): reprime absorbs an NKRO toggle before the next poll. NKRO itself still changes correctly. An immediate RGB-only baseline refresh would preserve that notification and subsequent RGB adjustments.

No other static blocker found in the exact four-file range. Tests were inspected, not rerun: process execution was denied.

## Round 3 (9ca4ed6a)

(pending)

## Dispositions

- **P2, the deferred active slot's failure: fixed in `28fac431`, and
  again in `9ca4ed6a` after round 2.**
  - `28fac431` reported the pending choice's own write. Round 2 found the
    hole: `write_active()` clears the choice before writing, so after the
    tick's write failed, a later flush had nothing pending and answered
    OK. `9ca4ed6a`: HC_PROFILES sub 6 writes a pending choice if it can,
    then answers `PROF_WRITE_FAILED` whenever the latch holds, else OK.
    flash.sh's restore (`apply_live()`) then fails on a latched board,
    which codex agrees is right: the cache can't vouch for the flash.
  - `prof_tick()` still writes it silently, its failure latched by `wr()`.
    `menu_tick()` flashes "Save failed" when `prof_write_failed()` rises
    (`was_failed`, 1 B), in the menu or at its next open.
  - The latch's refusals stay until a reboot.
  - Tests: the deferred byte's failure injected in `profiles_test.c` (the
    latch; the flush's status when its write fails and when the latch
    holds the choice) and in `menu_s0_test.c` (a key's deferred failure
    flashing "Save failed").
- **P2, the key's overlay overwritten by the RGB poll: fixed in
  `28fac431`, refined in `9ca4ed6a`.** `28fac431` reprimed the whole poll
  after a load; round 2 noted that also swallowed an NKRO toggle's
  overlay in the same 100 ms. `9ca4ed6a`: `param_status_rebase_rgb()`
  takes only the lighting as the poll's baseline (its statics moved to
  file scope). menu_glue.c isn't host-tested; JD's eye on the board
  covers it.
- **Before codex, the host test found one bug:** a summary row's signature
  carried the record's crc in bit 0, which is a row's lit bit to the
  scheduler (`menu_slots.c`). The row then waited forever behind the
  cursor's row, never painting. The crc moved up a bit; a sweep of 40
  records settles each.
- **Mutants:** 38 at `9ca4ed6a`, 36 caught. The two survivors are accepted: the slot
  pages' entry invalidation (redundant while every name change is a host
  write, which repaints the menu; P5c's Rename will lean on it), and
  Load's latched clock (without it, one extra retarget).
