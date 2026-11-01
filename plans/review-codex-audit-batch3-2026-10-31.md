# Codex review of the audit's third batch, settings (2026-10-31)

Codex (gpt-6-astra, xhigh, read-only) on `qmk_firmware-ak820pro`
`6dd881bf04` (profiles: F-030, F-011, F-012, F-041), `d61b87b4ba`
(wear_leveling: F-010), `80a4ccd52b` (the dynamic keymap: F-017) and the two
audit changes in `67f13f6aaf` (sleep: F-020, F-027), with their host tests.
Verbatim below; it held the batch with one P1, two P2s and a P3, and found
F-017, F-020, F-027, F-041 and Reset settings sound.

Dispositions (Buzz's session), in the firmware's `f70c493e0e` (profiles) and
`f40d3b47a1` (wear_leveling):

- **P1, the default layer as the side the boot goes by: fixed, as codex
  proposed.** The settings' owner is a byte of its own (`PROF_OWNER_ADDR`,
  just below the block, out of VIA's macro buffer: 19 B to 18), written
  `OW_MOVING | side` before a flip's first write and `OW_SETTLED | side`
  after its flush. The flip's order is now the pending pair, the side left's
  record, then the side arrived at's settings and flush, and the boot
  finishes a flip a cut stopped before it looks for a move while off or a
  stale record. The default layer is no longer read; `prof_boot_side()` is
  gone. `scripts/profiles_cut_test` cuts before every durable step of three
  kinds of flip (both sides profiled; Windows only; the Mac only), the first
  cut in the countdown with nothing written (codex's failure), and reboots
  with the switch on each side: every outcome is the side's own settings or,
  once the side left's record is in, its profile. The audit's verify-036
  sweep, which found two bad cuts in the old order, finds none. A PDF() key
  moves nothing now.
- **P2, a backup restored on the switch's other side: fixed.** HC_PROFILES
  sub 8 says the restored live settings are the other side's; the board
  takes them as that side's and flips to the switch's, as a live flip.
  `ak820profiles.py restore` sends it when the backup's `switch` differs
  from the board's, and notes it on a firmware without sub 8. The commit
  writes the owner byte as the switch's side first. `profiles_cut_test`
  restores a Windows backup on the Mac with and without sub 8 (without, the
  old result: Windows' settings on the Mac, the Mac's lost at the next
  boot); `scripts/profiles_host_test.py` covers the host's six cases.
- **P2, the CRC-8 passing a four-bit tear: fixed, as codex proposed.** Byte
  7 is a Berger code, the count of 0-bits in bytes 0-6; under the tear model
  (a cut only drops logical 1-bits) no tear passes it. Codex's exact tear is
  case E of `scripts/wear_leveling_torn_test`, and case F samples 1,700 tears
  over the whole line, data and check bits alike. Run against the CRC-8
  version, E replays the write at address 4 (keymap_config `E631`, as codex
  computed) and F finds one more silent change. Whether the chip's tears
  have these shapes is still unmeasured.
- **P3, QMK's own 8-byte tests: fixed.** The write counts are 4 bytes a
  line, the playback fixtures carry the check, and a torn-line case is
  added. `lib/googletest` is not checked out here, so
  `scripts/wear_leveling_gtest` builds QMK's five suites unedited on a
  minimal googletest shim; all five pass.

---

**I would hold this batch for the profile-side issue below.** I found one P1, two P2s, and one P3.

Reviewed `6dd881bf04`, wear-leveling `d61b87b4ba`, keymap `80a4ccd52b`, and only the two audit changes in sleep commit `67f13f6aaf`.

1. **P1 — The default layer records a switch reading before the profile transition commits.**  
   [keymap.c:74](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keymaps/via/keymap.c:74), [profiles.c:612](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:612), [profiles.c:636](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:636).

   The keymap immediately calls:
   > `set_single_persistent_default_layer(MACBASE);`

   But profiles wait three ticks before `settle_side()`. After a reboot on that newly persisted side, the new cleanup does:
   > `if (last_of(cur_side(), rec) && writable() == PROF_OK) last_clear();`

   **Failure:** Start on Windows with durable Windows settings and a last record containing Mac’s modified settings. Flip to Mac, then brown out during the 200–300 ms countdown. EEPROM now says Mac, but the live settings still belong to Windows. The reboot treats this as an unchanged switch, loads nothing, and deletes Mac’s valid snapshot. Thus a last record naming the current physical side is **not always stale**.

   There is another way to violate the same assumption without an interrupted switch: a VIA-assigned `PDF(2)` persists Mac’s default layer while profiles remain on Windows. [process_default_layer.c:25](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_default_layer.c:25) calls:
   > `set_single_persistent_default_layer(layer);`

   The next reboot falsely infers an off-power switch movement and can file Windows settings as Mac’s.

   **Fix:** Track the durable settings owner and an unfinished transition explicitly, independently of QMK’s default layer. Recover that transition before clearing records; use the audit’s transaction-state approach for the flush window. Merely delaying the default-layer write moves the ambiguity to another cut point.

   Add resets immediately after the default-layer write and throughout the countdown/flush. The current [side-test reboot helper:23](/Users/jdlien/code/ak820-pro/scripts/profiles_side_test/test.c:23) calls `settle()` before resetting, so it misses this case.

2. **P2 — Restoring a backup on the opposite side creates another valid “current-side” last record that boot deletes.**  
   [ak820profiles.py:520](/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:520), [ak820profiles.py:540](/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:540), [profiles.c:636](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:636).

   The backup saves `"switch": g.side`, but restore does not use it to reconcile ownership:
   > `want = convert(block, g)`  
   > `st, sent = apply_live(h, live)`

   **Failure:** Back up on Windows: live = Windows, last = Mac. Restore while the switch is on Mac, including after flashing. The host restores Windows’ live settings and Mac’s last record unchanged. On the next reboot, the persisted default layer says Mac, so the new cleanup deletes Mac’s valid settings and retains Windows’ settings on Mac. The old boot swap could recover this arrangement.

   **Fix:** Before restoring, compare the backup’s side with the board’s side. Either refuse a mismatch or reconcile live/last ownership explicitly. Test opposite-side restore followed by reboot and flips in both directions.

3. **P2 — CRC-8 does not reject every tear allowed by F-010’s model; a concrete four-bit tear still corrupts unrelated settings.**  
   [wear_leveling.c:170](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:170), [wear_leveling.c:578](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:578).

   Playback accepts a line unless:
   > `l > WL_MULTIBYTE_MAX || log.raw8[7] != wl_line_crc(&log)`

   Using the keyboard-settings values already present in the host fixture, these logical lines both have CRC `4A`:

   ```text
   intended: 20 00 25 31 EE 7F 29 4A
   torn:     20 00 04 31 E6 6F 29 4A
   ```

   Only four logical 1-bits disappear. Length remains four, but address changes from 37 to 4. The subsequent:
   > `memcpy(&wear_leveling.cache[a], &log.raw8[3], l);`

   sets `keymap_config` to `0xE631` and overwrites bytes 6–7. Later consolidation makes this permanent. I verified the checksum arithmetic in memory; whether hardware produces this tear shape remains unmeasured.

   **Fix:** For the stated one-direction bit-loss model, use a check that detects every such loss—for example, the complemented population count of bytes 0–6. Dropping data bits increases the required check value, while dropping check bits can only decrease its stored value. Add the exact counterexample above. The current [tear enumeration:254](/Users/jdlien/code/ak820-pro/scripts/wear_leveling_torn_test/test.c:254) explicitly keeps “the data bits … whole,” missing these combined header/payload tears.

4. **P3 — QMK’s existing eight-byte-store tests still describe the old format.**  
   [wear_leveling_8byte.cpp:50](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/tests/wear_leveling_8byte.cpp:50).

   The test loops through `length <= 5` and asserts:
   > `EXPECT_EQ(std::distance(inst.log_begin(), inst.log_end()), 1);`

   Five bytes now require two lines. Playback fixtures also construct entries without the new checksum. These assertions/fixtures will fail under the changed implementation.

   **Fix:** Update the write-count expectations and construct valid checksummed playback fixtures.

The following paths checked out:

- **Initialization and ordinary flashing:** [keyboard.c:448](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/keyboard.c:448) reads `eeconfig_read_default_layer()` before `dip_switch_init()`, and the board hook captures it before the keymap hook. Flashing erases the store. On a fresh Mac boot, the apparent Windows→Mac transition encounters no profiles; [flash.sh:288](/Users/jdlien/code/ak820-pro/flash.sh:288) then waits `sleep 6` before restoring. Same-side restoration is sound.
- **Reset settings:** [profiles.c:717](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:717) uses `set_pair(0xFFu)` and `last_clear()`, retaining user slots without resetting the default layer. Completed-reset behavior is consistent.
- **F-011/F-012:** Clearing an orphan after Load/Save on a truly settled side is appropriate. After a completed flush, the new boot behavior avoids the old false swap, provided ownership is correct. The documented mid-flush mixture remains; this is not the audit’s full transactional fix.
- **F-041:** [profiles.c:361](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:361) uses `rec[PR_FIELDS] & PF_PROFILE`, correctly excluding power from the star comparison while live-record application retains it.
- **F-010 mechanics:** Four-byte splitting, checksum placement, rejection before copying, and forced consolidation preserve the valid prefix when a checksum fails. `wear_leveling_log_used()` measures physical bytes; `flash_tidy.c` uses byte thresholds, so neither assumes five payload bytes.
- **F-017:** `eeprom_update_block(be, address, 2)` reaches wear leveling as one write. Relative keycode alignment, odd-offset leading bytes, trailing single bytes, encoder directions, and the 720-byte boundary are correct. An in-memory sweep of 21,721 offset/length combinations found no indexing errors. Odd packet boundaries remain partial-key updates by API definition; `flash.sh` uses aligned 28-byte chunks.
- **F-020/F-027/F-008:** The queue check runs under the Cortex-M0 system lock and unwinds before teardown. `if (!rc_usb_watch && !rc_active) return;` preserves both active recovery and the later USB observation. F-008 is explicitly documented in all three requested documents; it remains unfixed.

I reviewed the supplied host-test sources but did not build or execute them. No files were changed, no device interfaces were opened, and all file reads stayed inside the repository.

---

## Codex's verify of the redo (10-31 evening)

On `f70c493e0e` and `f40d3b47a1`: the four findings above closed, and five
P2s and two P3s raised. Dispositions (Buzz's session), in the firmware's
`c7b8b2b53e` and the outer repo's `3d8e2b3`, `9eb5b37`, `798ee30`:

- **P2 1, a cut between the commit and sub 8: fixed.** The host applies and
  flushes the live record with the block unpublished, then commits naming
  its side (sub 3's [7]); the commit writes the owner before the magic and
  arms the flip to the switch's side itself. Sub 8 goes (it was in no
  release). `scripts/profiles_cut_test` cuts the restore at each of its 83
  steps: no profiles before the magic, each side its own after.
- **P2 2, mutations before the boot's check: fixed.** `writable()` refuses
  SD_BOOT; begin, apply and Reset too; `prof_tick()`'s boot condition reads
  the recovery and the restore directly.
- **P2 3, a failed settings flush publishing OW_SETTLED: fixed** (and again
  below). `env_settings_flush()` reports failure from
  `wear_leveling_failures()`; `flush_settings()` latches TX_FAILED.
- **P2 4, the host's unconfirmed flip: fixed** (and again below). Sub 7's
  [10]: a flip pending, the latch; `confirm_side()` polls it.
- **P2 5, a 19-byte macro backup aborting the restore: fixed.** The keymap and
  the knob restore without the macros, exit 3, which `flash.sh` takes as a
  warning (`scripts/keymap_macro_test`).
- **P3 6, the cut tests: done.** Wear leveling's 4-byte lines, a second cut in
  every recovering boot, failures injected with a control that must fail, a
  pending Load, the boot gate.
- **P3 7, the menu test's counts: fixed** (14 and 15, the owner's order).

## Codex's second verify, Batches 3 and 4 (10-31 night)

On `75e78cb508` (the link hold, from Warren's reading), `f79515e37a`,
`ad917da23d`, `cd9fce3039`, `c7b8b2b53e`, `time-util-ak820pro`
`4cc6571` and the outer repo's commits since `77b4f08` (prompt:
`review-prompt-audit-batch34-verify.txt`): no P1; four P2s and two P3s.
It found the link hold, the four-report cap, both idle paths of the WIP
latch, the relock, `FC_INFO`, the boot gate, the commit's order and the
macro restore sound. Dispositions, in the firmware's `d99b9d3499` and
`time-util-ak820pro` `1ca3cb2`:

- **P2 1, a deferred write failing before the flush: fixed.** The failure
  count saturates and counts `wear_leveling_consolidate()` too, and
  `env_settings_flush()` reports false while any write has failed since the
  boot: the failed write's bytes sat in the cache and the flush skipped them
  as unchanged. The cut test's fake now caches its settings as wear leveling
  does, with the failure sticky; a restore whose deferred write fails before
  the flush stays unpublished, and the control publishes.
- **P2 2, `confirm_side()` skipping a flip the commit armed: fixed.** It polls
  after every commit to a capable firmware, whatever the sides looked like
  before, and decides the flip from the side the commit named and the side
  settled after; sub 7's [10] bit 2 reports the switch's reading. Codex's
  counterexample (settled on Windows, the switch already on the Mac, a
  Windows backup) and its latched variant are host test cases, failing on
  the old host.
- **P2 3, flash sessions unserialized: fixed.** `flash_lock()`: `flock` on
  `$TMPDIR/ak820ctl-flash.lock`, a `Local\` mutex on Windows (not built
  on this Mac), from before the first flash command to the end of `main()`.
  `scripts/flash_channel_test` holds the lock and sees a second session
  refuse with nothing erased.
- **P2 4, the clock's uncorrelated replies: fixed.** `xfer()` itself takes
  only a matching full report, for every command; `xfer_flash()` folds into
  it. A clock sample that waited out a foreign report is a slow one, which
  the transaction discards. No clock-specific test (the fake device has no
  RTC); the correlation is the flash test's.
- **P3 5, the cut test's allowance: fixed.** Windows' profile value is allowed
  only on a Windows boot and for a second cut at or after the recovering
  boot's first step toward Windows. The kb block is still modelled as two
  lines, not the real ten bytes; only the screen level is read from it.
- **P3 6, the warnings: fixed.** The macro warning says the board's own were
  left as they were; `flash.sh`'s last note claims only the keymap and the
  knob.

### Verbatim, the first verify

The four original counterexamples are addressed. **Five P2 issues and two P3 gaps remain; I would hold the profile changes.** I found no new P1.

| Original finding | Closed? |
|---|---|
| P1: default layer mistaken for settings ownership | **Yes, for the reported countdown-cut and `PDF()` cases.** The independent owner byte fixes that ambiguity. |
| P2: opposite-side restore | **Yes for an uninterrupted restore.** Interrupted restores remain unsafe, as below. |
| P2: CRC-8 accepts the four-bit tear | **Yes, under the stated one-direction bit-loss model.** |
| P3: QMK’s eight-byte tests describe the old format | **Yes.** Counts, playback fixtures and the added torn-line case match the new format. |

1. **P2 — A cut before sub 8 recreates the opposite-side restore failure.**  
   [profiles.c:753](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:753), [ak820profiles.py:561](/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:561).

   Restore a Windows backup on Mac: live Windows settings = 25, saved Mac last-record = 95. Commit publishes the block and marks ownership **settled Mac**. The host then applies and flushes Windows’ 25, and only afterward sends sub 8.

   Cut after that flush but before sub 8: boot sees settled Mac, retains Windows’ settings, and [clears Mac’s valid last record](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:685). Cuts between commit, apply and the component flushes likewise have no restore-phase recovery.

   **Fix:** Make source ownership and restore progress durable within the restore transaction, retaining recovery information until application and flushing finish. Publish magic only after the necessary metadata. Alternatively, refuse opposite-side restores before modifying anything. Simply sending sub 8 earlier introduces a countdown/apply race.

2. **P2 — External mutations can run before `SD_BOOT` resolves ownership.**  
   [profiles.c:298](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:298), [profiles.c:692](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:692), [profiles.c:916](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:916).

   The initial switch reading sets `SD_SETTLED` to the physical side before reading the durable owner. `writable()` does not reject `SD_BOOT`; Load, Save, Delete, Rename and Prof keys can therefore operate against that provisional state. Sub 5 also permits application before this check.

   Example: boot physically on Mac with Windows-owned live settings. An early sub-5 application replaces those settings before housekeeping; boot then identifies them as Windows-owned and captures the replacement as Windows’ outgoing snapshot. Raw HID is serviced [before housekeeping](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/main.c:54), so this ordering is available on the board.

   **Fix:** Resolve boot ownership before accepting external mutations, or give those entry points a separate `SD_BOOT` busy gate. Do not simply add it to `writable()`: `prof_tick()` currently uses that function to decide whether boot checking may run.

3. **P2 — Settings-flush failures can still publish `OW_SETTLED`.**  
   [profiles.c:624](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:624), [menu_glue.c:273](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:273), [eeprom_wear_leveling.c:38](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/eeprom/eeprom_wear_leveling.c:38).

   `env_settings_flush()` returns no status, and QMK discards the underlying write result. These failures never set `TX_FAILED`.

   A transient failed kb-config write that leaves its log location erased, followed by successful RGB and owner writes, produces mixed durable settings with a settled owner. Boot consequently skips recovery. The same problem exists in `boot_recover()`.

   **Fix:** Propagate or latch failures from the settings writes, and publish settled ownership only after both flushes succeed. A cached readback cannot establish durability. This is the existing wrapper limitation now undermining the new transaction marker.

4. **P2 — The host reports success when the asynchronously scheduled flip fails.**  
   [ak820profiles.py:375](/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:375), [profiles.c:959](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:959).

   Sub 8 acknowledges after writing source ownership and scheduling the countdown. If `last_put()` or the final owner write subsequently fails, the firmware latches failure, but `tell_side()` merely sleeps 600 ms, prints “the board flipped”, and returns successfully. The following block/live reads do not report that latch.

   I confirmed the host behavior using the actual extracted `tell_side()` with a fake transport and a failure injected during its sleep: it sent only sub 8 and reported success.

   **Fix:** Expose and poll the flip’s completion/error result. A fixed delay is not confirmation that its writes succeeded.

5. **P2 — A valid full 19-byte macro backup can abort the entire restore after flashing.**  
   [ak820keymap.py:250](/Users/jdlien/code/ak820-pro/hostagent/ak820keymap.py:250), [flash.sh:292](/Users/jdlien/code/ak820-pro/flash.sh:292).

   Concrete old buffer: fifteen empty macros, then macro 16 containing `AB`, its terminator, and the validity byte—19 bytes total. `macros_used()` returns 18 bytes; the new buffer permits 17 before its flag.

   The size check correctly refuses this buffer, but only **after firmware flashing erased EEPROM**, and before restoring any keymap data. Three retries then exit `flash.sh`, also skipping profiles and live settings. The backups survive, but the board remains reset.

   **Fix:** Check macro capacity against the target firmware before flashing. Alternatively, restore the independent keymap/settings while explicitly reporting that the macros could not fit.

6. **P3 — The cut tests omit recovery cuts and restore cut windows.**  
   [profiles_cut_test/test.c:184](/Users/jdlien/code/ak820-pro/scripts/profiles_cut_test/test.c:184), [profiles_cut_test/test.c:220](/Users/jdlien/code/ak820-pro/scripts/profiles_cut_test/test.c:220).

   The sweep disables cutting before reboot, so `boot_recover()` always completes uninterrupted. Restore tests exercise completed sequences only. Also, each 26-byte record-body write and each settings flush is modeled as one durable step, although wear leveling splits them into physical lines.

   Consequently, these tests can pass while findings 1 and 3 remain.

   **Fix:** Nest a second cut sweep inside recovery; cut restore commit/apply/flush/sub-8 transitions; inject returned failures as well as resets; and exercise physical-line boundaries. Add pending menu choices and pre-boot-check actions to the initial states.

7. **P3 — The menu integration test still expects the pre-owner write counts.**  
   [menu_s0_test.c:4091](/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4091).

   First Save still expects 13 writes and settlement 14. Formatting now adds the owner write, making those counts 14 and 15. Unlike `profiles_test.c`, these assertions were not updated.

   **Fix:** Update both counts and assert the owner write’s address/value and ordering.

The following checks were sound:

- **Flip and recovery cut ordering:** Before `OW_MOVING`, the old owner remains authoritative. Until the outgoing last-record state commits, recovery repeats the flip from the old live settings. Once that record commits, recovery reloads the destination profile and flushes it before settling ownership. Repeating a cut during that recovery follows the same states. I found no additional ownership inversion in these source traces. Losing the destination’s modifications after its snapshot is overwritten remains the documented fallback.
- **Profile-write failure latch:** Failures in the pending pair, moving marker or outgoing record prevent application; failure of the final owner write leaves durable moving ownership for reboot recovery. Failure clearing a consumed record leaves a stale record that boot can remove. The settings-flush and host-reporting exceptions are findings 3 and 4.
- **Unformatted blocks:** Fresh-flash and aborted-restore blocks ignore the leftover owner. `format()` establishes ownership before publishing magic. Sub 8’s unformatted no-op is consistent with having no side-specific profiles.
- **Menu actions and Reset:** During an ordinary flip countdown, Load/Save/Prof keys correctly use the outgoing settled side. Delete handles both active nibbles and associated snapshots; Rename retains its invalidate/body/state ordering. Completed Reset clears both selections and the last record while preserving user slots. The boot-pending exception is finding 2.
- **Normal same-side firmware upgrade:** Flashing erases the old wear-leveling format; `flash.sh` waits six seconds before restoring. With fitting macros, the first unformatted boot, block commit, live application and flush have consistent ownership. No sub 8 is needed in this settled same-side case.
- **Macro boundaries:** Macros occupy **787–804**, owner **805**, profiles **806–1023**. VIA accesses and QMK macro reset respect the 18-byte size. The dev Write test now targets **803**, preserving validity byte 804 and owner 805. In-memory checks of the actual `macros_used()` confirmed that empty old buffers and the old dev-test spare byte migrate safely.
- **Berger check:** The original seven data bytes require check **33**; the four-bit tear requires **37**, so it is rejected. Dropping data bits increases the required count; dropping check bits decreases the stored count. An entirely dropped line is the existing zero end marker and safely loses that final write. All appended eight-byte log records use the multi-byte encoding; optimized records remain restricted to two-byte stores. Consolidated data and its FNV hash are separate and unchanged. Log occupancy and `flash_tidy.c` remain measured in physical bytes.

I reviewed both commits, their callers and all supplied test sources/runners. I did not build or execute the file-writing test runners; execution was limited to isolated, in-memory Python checks. No USB/HID interfaces were opened, no files were changed, and reviewed files stayed inside the requested repository.
### Verbatim, the second verify

**No new P1 found. Four P2 issues remain, plus two P3 gaps.**

1. **P2 — A failure before the explicit flush can still produce a successful restore.**  
   [menu_glue.c:276](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:276), [wear_leveling.c:762](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:762).

   Counterexample: sub 5 applies the backup, then the host pauses two seconds—inside `TX_TICKS`. The ordinary deferred RGB write runs and fails to unlock flash, after updating the wear-leveling cache. Sub 6 subsequently snapshots the already-incremented failure count; its forced RGB write skips the unchanged cached bytes. It reports success, and commit publishes the owner and magic over settings that never fully landed. Choose sufficient log space so no subsequent consolidation repairs them.

   A failed standalone `wear_leveling_consolidate()` also escapes this counter entirely.

   **Fix:** expose a sticky persistence-failure flag covering normal writes and explicit consolidation. Have profile writes and flush confirmation consult it until reboot or verified recovery. Test a deferred failure between apply and flush using the real cache’s unchanged-write behavior. Batch 3 finding 3 is only partially fixed.

2. **P2 — `confirm_side()` can skip a flip that commit actually arms.**  
   [ak820profiles.py:387](/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:387), [profiles.c:774](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:774).

   Counterexample: restore a Windows backup during an existing Win→Mac countdown. Geometry still reports Windows because `[9]` describes `SD_SETTLED`, while the physical switch already requests Mac. Commit correctly arms the Mac flip, but `src == g.side` makes confirmation return immediately. Read-back can finish before the flip fails.

   I reproduced this with the host test’s fake board: restore returned **0**, with the flip still pending and only the initial geometry query issued. Completing the flip then returned **`0x82`**, including the failure latch.

   **Fix:** check pending/failure status after every capable commit, irrespective of the initial source-side comparison. Either wait for a settled board before beginning or expose the physical target separately. Determine the read-back comparison from the completed transition. Batch 3 finding 4 remains incomplete.

3. **P2 — Flash sessions still need serialization.**  
   [ak820ctl.c:120](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:120), [hid_protocol.c:277](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:277).

   Counterexample on Windows: process A begins writing address A; process B begins address B, replacing the firmware’s shared `fw_addr/fw_fill`; A’s next data packet now contributes to B’s write. Both processes can accept each other’s identically headed acknowledgements. A later CRC failure does not undo the damage. Having one provisioning executable does not prevent two instances.

   **Fix:** acquire an OS-wide per-device lock before opening a write/erase/CRC session, retaining it through verification and relocking. Add a two-client interleaving test. The cross-channel correlation fix is sound; this portion of the original Batch 4 finding remains unresolved.

4. **P2 — Keeping the clock’s uncorrelated `xfer()` preserves cross-channel failures.**  
   [ak820ctl.c:73](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:73), [ak820ctl.c:375](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:375).

   Counterexample: while the sole clock client awaits GET, it receives another process’s `FC_INFO/FS_BUSY` reply: `07 11 01 01`, followed by zeros. `xfer()` accepts it, `get_offset()` reads protocol zero, and `cmd_clock()` records a legacy capability and performs a legacy set against modern firmware.

   **Fix:** require full-length, matching channel/command replies for clock transactions too. Retain the separate single-clock-owner rule: correlation cannot distinguish two clock clients, but it does reject flash/text replies. This is a retained defect, not a regression introduced by the new flash helper.

5. **P3 — The second-cut allowance hides more than the documented Windows return-flip loss.**  
   [profiles_cut_test/test.c:252](/Users/jdlien/code/ak820-pro/scripts/profiles_cut_test/test.c:252).

   `w2` permits Windows’ profile value whenever **any** second cut exists. For example, `k=0`, `mac=true`, `c2=0`, with results Mac=95 and Windows=20 passes—even though the recovering boot never flips toward Windows and the second cut precedes its first durable write. Windows should retain 25 there.

   **Fix:** allow 20 only when the recorded execution actually reaches the relevant cut window in a flip toward Windows. Also tighten the storage model: its two-line keyboard block differs from the real ten-byte block, and its flush fake bypasses the cache behavior behind finding 1. Batch 3 finding 6 is improved, but not closed.

6. **P3 — The macro warnings assert outcomes that were not established.**  
   [ak820keymap.py:282](/Users/jdlien/code/ak820-pro/hostagent/ak820keymap.py:282), [flash.sh:382](/Users/jdlien/code/ak820-pro/flash.sh:382).

   A manual restore with oversized macros leaves existing board macros untouched, yet says “the board has none.” Separately, after three failed profile restores, `flash.sh` still reaches the new warning saying the settings were restored.

   **Fix:** say the macros were skipped and existing macros left unchanged; report settings success only when the corresponding restore succeeded.

What I checked and found sound:

- **Batch 3 finding 1:** pages → live apply/flush → active byte → owner → magic closes the original commit/sub-8 cut window. Timeout expiry leaves the block unpublished and the later commit rejected.
- **Batch 3 finding 2:** the `SD_BOOT` gates cover Load, Save, Rename, Delete, profile stepping, begin, apply and Reset. Clearing `SD_BOOT` before `boot_check()` avoids self-blocking.
- **Commit bookkeeping:** begin discards the previous pending pair; profile mutations stay blocked during restore; commit replaces the old countdown. I found no separate firmware defect in those interactions.
- **Immediate flush failures:** failures occurring inside the explicit flush now latch and prevent settled-owner publication. Fixed addresses are in bounds, and this flush cannot wrap the failure counter.
- **Read-back:** excluding the last record after a confirmed flip is appropriate; that record legitimately changes.
- **Batch 3 findings 5 and 7:** oversized macros preserve keymap/encoder restoration with exit 3, and `flash.sh` continues. The menu test’s 14/15 write counts and owner ordering are corrected.
- **Batch 4:** the four-report cap closes the reported watchdog-starvation loop; both idle observations preserve WIP damage; relocking covers ambiguous unlock failure and propagates failure; `FC_INFO` now waits for idle.
- **Tests/docs:** the flash test now uses actual `ak820ctl`, asset tests exercise loading and ID lookup, the idle-blit interleaving is covered, the dependency pin matches, and animation documentation says 243.
- **`75e78cb508`:** repeated module `36/33` cycles no longer restart the hold indefinitely. Board selections retain their hold, wake rearms the module allowance, and the promotion timer remains separate.

I ran both Python host tests successfully with **in-memory fixtures and device imports stubbed**, plus the confirmation counterexample above. I did not build the C tests because the sandbox rejects temporary-file creation. No files were changed, no USB/HID interfaces were opened, and source inspection stayed inside the repository.
## Codex's third verify: the second round's fixes and the low sweep (10-31 night)

On `d99b9d3499`, `time-util-ak820pro` `1ca3cb2`, the outer repo's `d2338a7`
and the low sweep `f3d7079d5f` (prompt: `review-prompt-audit-verify3.txt`):
no P1; four P2s and three P3s. Every low-sweep fix read as correct (F-021,
F-029, F-036, F-037, F-038, F-039, F-042, F-043, the op 17 clamp; F-040's
health latch), and the sticky failure, `confirm_side()`, the correlated
`xfer()` and the lock's lifetime sound. Dispositions, in the firmware's
`4c7395a4c6` and `time-util-ak820pro` `cbff6b7`:

- **P2 1, a store failure between the flush and the commit: fixed.**
  `latched()` folds `env_store_failed()` (any wear-leveling failure since the
  boot) into the profiles' latch wherever it is read: the commit's writes,
  `writable()`, `prof_write_failed()` (sub 6, sub 7's [10] bit 1, the menu),
  the restore's begin. `scripts/profiles_cut_test` fails the store between
  a successful flush and the commit: unpublished, [10] 0x86.
- **P2 2, the lock not machine-wide: fixed.** A `Global\` mutex on Windows
  (not built on this Mac); `/tmp/ak820ctl-flash.lock` on POSIX, opened
  read-only so another user can flock it; a lock that can't be made refuses
  the session. The channel test checks that refusal too.
- **P2 3, F-031's commit accepting a tail that arrived late: accepted.**
  Without arrival stamps in the UART queue, a byte drained after a pass of
  the board's own cannot be told from one the module sent late: codex's
  counterexample (an empty read at 19 ms, the tail drained at 22 ms) and the
  audit's F-031 case (the tail waiting behind a 20 ms pass) look the same.
  The audit chose to keep the frame. The window is one pass at most (an
  empty read past the lifetime aborts, `raw81_test.py`'s 10c), and a frame
  still needs its sum, its CRC16 envelope and a fresh session seq. Dev
  builds only.
- **P2 4, F-040 under a whole wrap of animation: accepted.** It needs an
  animation running without a break for 49.7 days; the latches and the
  uptime stay where they are.
- **P3 5, the cut test's allowance: fixed.** Windows' profile value is
  allowed only for a second cut after the flip toward Windows emptied
  Windows' snapshot (its first block write after the owner byte), and only
  where the Mac has a profile to overwrite it with. Codex's counterexample
  must now recover 25. The kb block's two-line model remains.
- **P3 6, the ratchet test passing on cases that never ran: fixed.** It fails
  on a setup error, a control that rose or a short count.
- **P3 7, the clock comment: fixed.** The fastest sample usually passes over
  one that waited; no RTC fake was built.

### Verbatim, the third verify

**No P1 found. Four P2 issues and three P3 gaps remain.** These are source-level findings; the Python profile suite passed with in-memory fixtures.

1. **P2 — A store failure after sub 6 still escapes commit and confirmation.**  
   [profiles.c:759](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:759), [menu_glue.c:187](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:187).

   Counterexample: restore on the backup’s own side. Sub 6 flushes successfully. Before sub 3, an eligible `flash_tidy_task()` consolidation erases the store but fails while programming it. `wl_failures` becomes nonzero; `TX_FAILED` remains clear. Subsequent small commit writes succeed, and no flip requires another flush. Sub 7 reports no failure, while read-back compares against the intact RAM cache. The host reports success over damaged durable settings.

   **Fix:** consult the global store-failure state before publishing magic/ownership, latch it into profile failure state, and expose it through sub 7. Add failure injection **between the successful flush and commit**, including failed consolidation.

2. **P2 — `flash_lock()` does not guarantee machine-wide exclusion.**  
   [ak820ctl.c:145](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:145).

   Counterexamples:
   - Two Windows logon sessions obtain different `Local\ak820ctl-flash` mutexes and can interleave writes to the same firmware buffer.
   - `CreateMutexA()` returning `NULL`, or POSIX `open()` failing, permits the operation without a lock.
   - Different `TMPDIR` values select different POSIX lock files.

   **Fix:** fail closed on lock-creation errors and use a shared namespace/path—`Global\` on Windows, with appropriate access handling. Keep the existing lifetime through verification and relocking. Test creation failures and namespace differences; the current held-file test covers ordinary contention only.

3. **P2 — F-031 removes effective lifetime checking at commit.**  
   [raw81.c:114](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/raw81.c:114), [raw81.c:140](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/raw81.c:140).

   Counterexample: collect the first 33 bytes at time zero, observe an empty queue at 19 ms, receive the valid checksum byte at 21 ms, and drain it at 22 ms. Commit tests the saved **19 ms** age and accepts the frame despite its 20 ms lifetime.

   More generally, `empty_tick` is initialized at the start and updated only when its age is below the lifetime. Its commit check therefore cannot reject this late completion. I checked the timing arithmetic using a valid generated envelope.

   **Fix:** distinguish arrival time from processing time, using receive timestamps or equivalent queue metadata. Preserve acceptance of bytes that arrived promptly behind a long firmware pass, while rejecting genuinely late tails. Restore that distinction in the tests; rewriting the former commit-timeout case removed its coverage.

4. **P2 — F-040 still depends on observations that animation playback can suppress across a complete wrap.**  
   [ak820pro.c:665](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:665), [rtc_persist.c:32](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc_persist.c:32), [indicators.c:343](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:343).

   Counterexample: start continuous animation five seconds after boot on USB and stop it at uptime `2^32 + 3000` ms. Animation suppresses `rtc_task()`, so the accumulator misses the entire wrap and sees only 3000 ms. The persistence boot delays return.

   On a packless board, the same animation can prevent `battery_is_absent()` from ever latching its 15-second grace. Returning to the dashboard at that time falsely reinstates the grace until timer value 15000.

   **Fix:** maintain uptime and latch boot thresholds from unconditional periodic work. Keep RTC bus operations gated separately. The added `diag_sim` assertion calls `rtc_persist_due()` with an already-correct 64-bit value; it does not exercise this integration.

5. **P3 — The second-cut allowance still accepts loss before the recovery writes anything.**  
   [profiles_cut_test/test.c:267](/Users/jdlien/code/ak820-pro/scripts/profiles_cut_test/test.c:267).

   Counterexample: `k=0`, first cut at `c=n` after the completed Windows→Mac flip, recovery on Windows, and `c2=w2_from=0`. The second cut happens **before** the first owner write. Windows’ last record still contains 25, so Windows must recover 25. Nevertheless, the oracle accepts results Windows=20, Mac=95.

   **Fix:** permit fallback to the profile only after a durable step actually destroys the incoming side’s saved snapshot. The first owner-write index is too early, especially with the inclusive comparison. Add an assertion that rejects the counterexample above. The acknowledged two-line approximation of the real ten-byte keyboard block also remains.

6. **P3 — The battery ratchet suite can pass when its cases fail to run.**  
   [battery_ratchet_test/test.c:284](/Users/jdlien/code/ak820-pro/scripts/battery_ratchet_test/test.c:284), [run.sh:20](/Users/jdlien/code/ak820-pro/scripts/battery_ratchet_test/run.sh:20).

   Counterexample: every gap case returns a setup error. `setup` increases, `rose` remains zero, the executable returns success, and the launcher matches “0 gap cases with the level rising.” Control-case rises are also omitted from the exit condition.

   **Fix:** fail on `rose || ctrl_rose || setup`, require the expected completed-case count, and propagate rises during setup.

7. **P3 — The clock’s “fastest sample discards foreign-report waits” claim is false.**  
   [ak820ctl.c:92](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:92), [ak820ctl.c:405](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:405).

   Counterexample: all five GET samples wait through foreign traffic. Minimum RTT still selects one; it cannot discard all affected samples. The verification GET is a single sample without that selection.

   **Fix:** describe minimum RTT as a heuristic and add RTC-specific fake-device coverage. If excluding such samples is required, have `xfer()` report discarded traffic and explicitly exclude/retry those measurements.

What I checked and found sound:

- **Sticky failures:** saturation and explicit-consolidation accounting are correct. The unchanged-cache deferred-write counterexample is fixed. Refusing later flushes until reboot is a defensible conservative policy; finding 1 concerns incomplete enforcement.
- **`confirm_side()`:** polling every capable commit closes the previous pending-countdown escape. Comparing the committed side with the settled side fixes that reported case, and reported failures/timeouts are rejected. The caller’s new regression cases pass.
- **`xfer()`:** full-length, channel/subcommand and command-or-unhandled matching closes the foreign `FC_INFO/FS_BUSY` → legacy-clock fallback. Same-command traffic still requires exclusive ownership.
- **Flash-lock lifetime:** restricting it to flash operations and retaining it through verification/relocking is appropriate; ordinary `info` and clock commands do not replace the firmware’s write/CRC session.
- **Macro warnings:** both now describe only established outcomes.

| Low-sweep fix | Reading verdict |
|---|---|
| F-021 | Correct: forgetting an estimate ends the run; the downward guard independently prevents a stale target raising the level. |
| F-029 | Correct in both keymaps: restores only saved `no_gui`. |
| F-036 | Correct: `was_pair` forces repaint when the shared buffer retains its pointer. |
| F-037 | Correct: playback consumes relayout; its exit paths force the necessary repaint. |
| F-038 | Correct for the reported collision: class changes invalidate the rows, including on entry. |
| F-039 | Correct: an idle blit wait no longer claims the stall mark. |
| F-040 | Health’s settle latch is correct; ordinary sampled RTC deltas wrap correctly. The animation gaps remain above. |
| F-042 | Correct: panel ownership gates Pairing’s backstop; entering debug rolls back the edit. |
| F-043 | Correct for the round trip: return releases forced Dim before rebuilding the menu stack. |
| Dev op 17/sub 4 | Correct: the maximum is now 5000 ms. |

I reviewed the specified commits and test sources. I ran `profiles_host_test.py` with device imports stubbed, JSON fixtures entirely in memory, and bytecode writing disabled. I did not build or run the C tests because the sandbox prohibits temporary-file creation. No files changed, no USB/HID devices were opened, and file inspection stayed inside the repository.