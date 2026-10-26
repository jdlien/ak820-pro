# Codex: P5b, the settings profiles' menu and the Next and Previous keys (2026-10-25)

Six rounds, verbatim, then dispositions: three on the code, three on the
fixes from the board's measures.
1. `plans/review-prompt-p5b-code.txt`: qmk_firmware-ak820pro `5ecc9a32..761f4cdb`
   (branch `gremlin/p5b`; `5ecc9a32` is P5a, the mainline).
2. `plans/review-prompt-p5b-code-verify.txt`: `761f4cdb..28fac431`.
3. `plans/review-prompt-p5b-code-verify2.txt`: `28fac431..9ca4ed6a`.
4. `plans/review-prompt-p5b-code-verify3.txt`: `9ca4ed6a..417c50c1`.
5. `plans/review-prompt-p5b-perf.txt`: `417c50c1..b4d29a29`, the first cost fix.
6. `plans/review-prompt-p5b-perf2.txt`: `b4d29a29..57d5e900`, the second.

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

**No remaining must-fix blocker found in `28fac431..9ca4ed6a` before a development flash on gremlin.**

- [profiles.c:498](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:498) checks the failure latch independently of `pend`, closing the P2. [profiles_test.c:559](/C:/Users/jdlien/code/ak820-pro/scripts/profiles_test.c:559) covers flushes after a failed tick and repeated flushes.
- The immediate RGB baseline refresh preserves `last_nkro`, fixing the swallowed NKRO notification and allowing subsequent RGB adjustments to surface.

**One nonblocking feedback edge:** [param_overlay.c:175](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:175) leaves `param_force_kc` pending. Tap an RGB adjustment, then a profile key before the next poll: the forced-readout branch can still replace the profile name. Clearing `param_force_kc` in the rebase, before its early return, would close that edge without touching NKRO.

Static review only: process execution was denied, so I inspected the tests but did not rerun them or independently verify the reported build.

## Round 4 (417c50c1)

Yes, it closes the note. I verified `9ca4ed6a..417c50c1`: the sole change clears `param_force_kc` before the early return, preventing a stale forced RGB readout from replacing the profile name. NKRO tracking remains untouched.

I found no new blocker to a development flash on gremlin. The assignment uses existing storage and adds no allocation, buffers, or blocking work.

Static review only; process execution was denied, so I did not rebuild or independently verify the reported 136 B heap gap.

## Round 5 (b4d29a29)

**No required changes before flashing `b4d29a29` on gremlin.** I found no static blocker in the exact two-file diff.

- **Snapshot/repaint:** [menu.c:1800](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1800) invalidates for input; [menu.c:1903](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1903) invalidates before the pump and consumes host-write invalidation. Key loads, VIA/Fn changes and recovery openings reach this ordering. No persistent signature/paint disagreement found; completing the physical repaint still takes multiple passes.

- **Readers outside tick exist:** input retargets and op 27’s `ms_settled()`/`ms_unsettled()` scans ([menu_ops.c:204](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:204)). These can observe the previous snapshot, but the following tick refreshes it before painting.

- **Raw CRC:** [menu.c:1008](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1008) reads one byte at a bounded slot address, used only as signature bits. Stale validity cannot authorize a load or unsafe payload access. Paint/load paths retain validation; host changes invalidate rows, including CRC collisions.

- **CRC/capture:** [profiles.c:49](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:49) matches all 256 reference entries and 200 strings, independently checked. The matching dev ELF places its 256 bytes in read-only `.rodata` at `0x323cc`. [profiles.c:232](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:232) omits only the unused capture CRC.

Artifact hashes match provenance; the heap gap is 136 B. I inspected the C tests but could not rerun them because process execution was denied. The timing improvement still needs board measurement.

## Round 6 (57d5e900)

**No required changes before flashing `57d5e900` on gremlin.** I found no static blocker in the requested `menu.c` diff.

- **Wrap and gaps:** [menu.c:1911](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1911) handles ordinary wrap correctly. An exact 8192 ms gap can alias the stored tick, including after reopening: that first tick may retain the old snapshot. With normal passes resumed, the next bucket invalidates it within 128 ms, plus scheduling latency. It does **not** wait another 8.2 seconds. The 128 ms bound excludes time without ticks and completion of the staged repaint.

- **Signature/paint:** [menu.c:573](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:573) supplies the shared snapshot; input marks it stale at line 1804, and host writes invalidate both rows and snapshot at [line 1907](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1907). I found no introduced path that permanently accepts mismatched paint or loses a persistent change.

- **Flags/failure:** [menu.c:1917](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1917) preserves stale/tick bits; the other updates preserve `PFS_FAILED`. These accesses run serially in the main loop. A previously unseen failure while closed still flashes at the next open’s tick.

I verified the exact Git blobs and exhaustively checked the flag masks and single-wrap alias arithmetic. I inspected the host tests but could not rerun them because process execution was denied.

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
- **Round 3's note (a forced RGB readout still replacing the name): fixed
  in `417c50c1`,** `param_force_kc` cleared in the rebase. Round 4 cleared
  it.
- **The board's measure after round 4** (`417c50c1`, flashed 23:52):
  with a profile active, the settled top level's passes were 1.8 ms
  longer (6.6 to 8.4 ms; the pump's scope 1.31 to 3.10 ms a pass; passes
  of 10 ms or more, 20 to 110 in 8 s). The screen settled: the cost was the
  Profiles row's signature, its bit-at-a-time crcs at every scan.
  - **`b4d29a29`:** a once-a-pass snapshot and crc8 from a table. Round 5
    cleared it. On the board it cut the active case to 2.27 ms but raised
    the empty case 1.31 to 1.87: an A/B of the same procedure on both
    builds, page two the equal control (1.12), showed the snapshot's own
    reads cost ~0.55 ms a pass on this core.
  - **`57d5e900`:** the snapshot read every 128 ms, and at once after a
    click or a host's write. Round 6 cleared it (an exact 8.192 s gap can
    alias the tick: the next 128 ms refreshes it). On the board: page one
    1.28 ms empty, 1.32 active, page two 1.12; passes of 10 ms or more back
    to ~20 in 8 s. `history/config-menu-p3-20261025/p5b-cost-417c50c1.txt`.
- **Mutants at `57d5e900`:** 45, 42 caught. The survivors: the entry
  invalidation, Load's latched clock, and a host write's stale mark
  (without it, a second repaint within 128 ms).
