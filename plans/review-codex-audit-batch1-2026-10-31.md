# Codex review of the audit's first batch (2026-10-31)

Codex (gpt-6-astra, xhigh, read-only) on `qmk_firmware-ak820pro`
`5c8c5f5ea8..b72462ba58` (branch `audit-fixes`: F-002, F-009, F-007 and
F-028, F-003, F-004) and the outer repo's `ca30679` (the build check and four
host tests). The prompt asked it to check, not accept, three deliberate
choices: F-003's backstop alone, F-009's unset reply when no stamp can be
taken, and where F-004's tracker is fed. Verbatim below.

Dispositions (Buzz's session):

- **P2 1, the tracker before `keycode_config()`: fixed** in `5cab8145e0`. The
  tracker maps the keycode first; `scripts/consumer_mod_test` links QMK's real
  `keycode_config.c` with `MAGIC_ENABLE` and has a scenario S (Alt and GUI
  swapped), which leaves Alt stuck on the first version and passes now.
- **P2 2, the ordering gap skipped when every bit was already held: fixed**
  in `5cab8145e0`. A burst's start pays the gap again; the test's host can
  deliver keyboard reports late, and scenario L (Option held, Shift 1 ms
  before the detent, reports 4 ms late) sends Alt+Volume on the first version
  and passes now.
- **P3, the clock test's exceptional paths: taken in part.** The no-stamp
  case is in `scripts/rtc_get_stamp_test` (SECIF pending through every try:
  the reply is unset and zeroed). A period that changes between the stamp
  and the fill cannot happen in that model, where time moves only inside a
  calendar decode and the fill has none; not added.
- Codex could not run the tests in its sandbox (`mktemp` refused); they were
  run on Buzz, all passing.

---

**No P1 found in this batch. Two P2 issues remain in F-004.** The other fixes look sound on source review.

1. **P2 — The modifier tracker records keycodes before QMK remaps them.**  
   [consumer_mod.c:43](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/consumer_mod.c:43) uses:
   ```c
   if (!IS_MODIFIER_KEYCODE(keycode)) return;
   uint8_t bit = MOD_BIT(keycode);
   ```
   But QMK subsequently applies `keycode = keycode_config(keycode);` in [keymap_common.c:57](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/keymap_common.c:57).

   **Concrete failure:** enable QMK’s Alt/GUI swap, hold the key mapped to raw `KC_LALT`, turn the Mac volume knob, wait for the burst timeout, then release the key. QMK actually holds GUI, while `mcons_phys` records Alt. The timeout therefore preserves the burst’s synthetic Alt and clears `mcons_mods`; releasing the physical key releases GUI, leaving **Alt stuck down**. This is separate from the explicitly accepted MT/OSM/LM limitation.

   **Fix:** track the effective modifier after `keycode_config()`, matching QMK’s action path. Add a remapping regression case. The current harness bypasses this conversion: [test.c:125](/Users/jdlien/code/ak820-pro/scripts/consumer_mod_test/test.c:125) directly calls `register_code(code)`.

2. **P2 — The new missing-bit optimization removes a necessary USB ordering delay.**  
   [consumer_mod.c:69](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/consumer_mod.c:69) now puts the entire delay inside:
   ```c
   uint8_t missing = mods & (uint8_t)~get_mods();
   if (missing) {
       ...
       wait_ms(MODIFIED_CONSUMER_GAP_MS);
   }
   ```
   **Concrete failure:** in USB 6KRO mode, hold Option, then press Shift immediately before the first Mac knob detent. Both bits are already present in `get_mods()`, so the detent skips the delay. The Shift report can still be queued when the consumer endpoint delivers Volume; macOS sees Option+Volume and opens Sound settings.

   This follows from [usb_main.c:383](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_main.c:383): reports are “enqueued into an output queue,” with keyboard and consumer reports sent on separate endpoints. The previous implementation waited on the first detent regardless of already-held modifiers. A removal-only burst change, such as `LSA(Volume)` → `LALT(Volume)`, likewise loses its former ordering delay.

   **Fix:** retain the ordering delay when starting/changing a burst, as well as when restoring missing bits. Preserve the fast path for an unchanged burst. Test with delayed keyboard-report delivery; [test.c:72](/Users/jdlien/code/ak820-pro/scripts/consumer_mod_test/test.c:72) currently applies `host_mods = r->mods` immediately, so it cannot expose this race.

What I checked and found sound:

- **F-002:** [keyboard.json:22](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keyboard.json:22) sets `"command": false`; the obsolete hook is removed. [build.sh:151](/Users/jdlien/code/ak820-pro/build.sh:151) checks `$3 == "command_proc"` outside the flavor switch, so every flavor is covered. A failure reaches the existing structural-check rejection before artifact publication. The documentation updates agree with this behavior.

- **F-009:** [hid_protocol.c:1391](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1391) takes one `rtc_now(&s)`, uses `s.t`, and passes that same stamp to the tail formatter. [rtc.c:816](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:816) uses `s->cnt` and `s->period_active`. This removes both identified sampling mismatches. On failure, the calendar remains zeroed and `data[3] = ok ? 1 : 0`; the uninitialized stamp is never consumed.

  The changed failure reply is compatible with both hosts. [ak820ctl.c:283](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:283) fills protocol and RTT before returning `-2`; the measurement loop explicitly says `if (rc == -2) continue`. SET still proceeds, and lead learning requires `good`. `--read` reports unset and exits 1. Rust’s [seconds_of_day():225](/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/mod.rs:225) returns `None` when unset; [transaction.rs:370](/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:370) admits only `Some(sample)`. No valid measurements means no lead learning. An unset verification sample is unavailable, not a measured zero—although the C’s printed summary substitutes `0.0`.

- **F-007/F-028:** [ak820pro.c:166](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:166) checks `connection_get_host() != CONNECTION_HOST_USB` before attempting wake. Both wireless slider positions actually select Bluetooth routing in `bt_ui.c`. The suspended/remote-wake checks remain, and the stamp, read, and elapsed calculation are consistently 32-bit. This fixes the 65.536-second aliases; the analogous 49.7-day limitation remains as acknowledged by the audit.

- **F-003:** the backstop-only choice is reasonable given the documented ambiguity of `5B 23`. [ch582f_ajazz.c:1843](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1843) clears only `is_pairing` after the unsigned elapsed comparison. [sleep.c:269](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:269) uses precisely that flag for `DSB_PAIRING`. Cancellation still checks `conn_state == CH582_CONN_PAIRING`, preserving the bounce after expiry. The timestamp is refreshed on both pair requests and `5B 31`; plain selection and cancellation explicitly clear the blocker. The separate, existing F-022 cross-slot bounce behavior remains.

- **F-004’s core repair:** for ordinary, unremapped modifiers, placing `consumer_mod_note_key()` before the sequencer is correct. `mods & ~get_mods()` restores a released bit on the next detent, and `mcons_mods & ~mcons_phys` preserves a held modifier at timeout. Rename’s earlier event capture also waits for all keys to be released before capturing, so it does not strand a tracked modifier release.

**P3 — RTC exceptional-path coverage is missing.** [rtc_get_stamp_test/test.c:175](/Users/jdlien/code/ak820-pro/scripts/rtc_get_stamp_test/test.c:175) tests steady state with `active == nominal`; its sweep treats every unset reply as failure. It never deliberately exhausts `rtc_now()` retries or changes the active period during decoding. Add those cases to protect the two deliberate behaviors above.

I inspected all four host harnesses. I could not execute them: the first runner failed at `mktemp` with `Operation not permitted` under the read-only sandbox, before compilation. Both commit whitespace checks passed. No files were changed, no devices were accessed, and all inspected files were inside the repository.