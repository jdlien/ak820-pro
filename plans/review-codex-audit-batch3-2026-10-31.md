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