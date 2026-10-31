# Codex review of the audit's second batch, the clock (2026-10-31)

Codex (gpt-6-astra, xhigh, read-only) on `qmk_firmware-ak820pro`
`5cab8145e0..5e7b03b7f1` (branch `audit-fixes`: F-005, F-006, F-016, F-025,
F-026) and their host tests. The prompt asked it to check four deliberate
choices. Verbatim below; it held the batch with one P1, three P2s and a P3,
all in F-005 and F-006's boot recovery, and found F-016, F-025 and F-026
sound.

Dispositions (Buzz's session), all in the firmware's `895c086af7`:

- **P1, the boot's failed release handed to the writer's recovery: fixed.**
  The boot check is its own release-only retry (`pcf_ctl_step()`: read,
  release, read back), one transaction at the 60 s check's cadence while the
  writer is idle, and it never writes the calendar. The writer starts no run
  without a valid clock. `scripts/pcf_stop_reset_test`'s `outage` case: the
  bus out 90 s from the boot, so the release and the seed both fail; STOP
  comes off once the PCF answers, the clock is set from it, nothing holds the
  board awake, and the calendar is never written.
- **P2, a failed control read taken for "running": fixed.** Until a read says
  the PCF runs, it is maybe stopped (no reference, no elapsed seconds) and the
  check is retried. The `ctlfail` case: no snap back, STOP released, the
  board on its own time.
- **P2, the stale guard holding off the seed retry: fixed.** The retry runs
  before that guard; the seed is the boot's provisional one, the PCF kept
  stale. `scripts/pcf_seed_retry_test`'s `stopped` case.
- **P2, the seed test failing the wrong transaction: fixed.** It fails the
  seven-byte calendar read itself, checks the clock unset at boot and before
  the retry's 60 s, and runs the sleep after the fix. With the retry removed
  from `rtc.c`, three of its four scenarios fail.
- **P3, the acquisition not rearmed after a late seed: fixed.** Once the clock
  is set and the PCF a reference, an acquisition a wake gave up goes again;
  the `sleepfirst` case.

---

**I would hold this batch before flashing: one P1, three P2s, and one P3.** The problems are in boot recovery and its tests; I found the F-016, F-025 and F-026 implementations sound.

Reviewed the four commits through `5e7b03b7f1`, the five audit findings, clock documentation, RTC LLD, sleep/acquisition paths, and all five host-test sources. This was static review only: no tests, builds, device access, or file changes.

1. **P1 — Exhausted boot recovery can enter the writer without a valid clock and prevent sleep indefinitely.**  
   [rtc.c:1535](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1535), [rtc.c:1762](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1762)

   The new boot path enters `ps_state = PS_RECOVER`. After six unsuccessful recovery attempts, the existing code executes:
   ```c
   pcfs.stale = true; pcfs.no_retry = false;   /* STOP may be set: a run is owed */
   ```
   This defeats the deliberate “do not write back unasked” policy. After another 60 counted seconds, `pcf_sync_retry_due()` requests a normal calendar write.

   **Failure scenario:** STOP is detected, but the release and calendar seed fail during a bus outage. Recovery exhausts its attempts; the bus later recovers. The normal writer reaches [rtc.c:1633](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1633):
   ```c
   stop_asserted = true; ps_attempts = 0;
   if (ps_plan()) ps_state = PS_TIME_WRITE;   /* else: stay, re-plan next pass */
   ```
   `ps_plan()` cannot succeed because `rtc_now()` rejects `!rtc_valid`. Successful STOP writes repeat forever; they reset the attempt counter. Meanwhile, the pending/running writer blocks seed retries, and `rtc_sleep_ok()` refuses sleep. A transient bus failure has become a persistent stopped PCF and awake board.

   Even when the initial seed succeeds, this route eventually rewrites the board’s guess and clears staleness without a host correction.

   **Fix:** Keep boot STOP recovery as a release-only operation, with bounded attempts and deferred retries independent of calendar validity. Preserve `no_retry` for calendar writes until a host accepts persistence. Guard normal writer admission against an invalid board clock. Test recovery exhaustion with both successful and failed seeds.

2. **P2 — A failed boot control read silently leaves the original frozen-clock bug intact.**  
   [rtc.c:1528](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1528)

   The code treats failure to read Control_status_1 like a successful observation that STOP is clear:
   ```c
   if (!pcf_reg_read_raw(0x00, &ctl) || !(ctl & PCF_CTL_STOP)) return;
   ```
   `rtc_init()` then unconditionally calls `rtc_seed_from_pcf()`.

   **Failure scenario:** A reset leaves STOP asserted. The first control read NACKs, but the following calendar read succeeds. No stale/recovery flags are set; the board seeds from frozen time, acquisition times out, and the discipline snaps back every minute. Short sleeps can again accept zero PCF elapsed time because `pcf_maybe_stopped` is false. F-006’s retry cannot repair this: it only rereads the calendar.

   **Fix:** Distinguish “STOP clear” from “control state unknown.” Retain a pending control check after failure, retry it with backoff, and exclude the PCF from authoritative calendar and sleep-elapsed use until its running state is established. Do not write a guessed control value.

3. **P2 — Staleness blocks the new seed retry after a successful STOP release.**  
   [rtc.c:2389](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2389), [rtc.c:2404](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2404)

   The retry is below:
   ```c
   if (pcfs.stale || pcf_maybe_stopped || slew_state != SLEW_IDLE || reload_pending) return;
   ```

   **Failure scenario:** Boot detects STOP, successfully releases it, and marks `pcfs.stale` with `no_retry`. Only the subsequent calendar seed fails. The PCF now runs and answers normally, but every `rtc_task()` returns before `if (!rtc_valid)`. No automatic write clears staleness either. The clock stays unset until a host sets it—the F-006 failure remains for this combination.

   **Fix:** Separate initial fallback seeding from authoritative discipline. After STOP is confirmed released, permit an invalid clock to retry the same provisional seed that boot permits, while retaining staleness and prohibiting discipline/acquisition/writeback. Keep the recovery, bus-use and cadence guards.

4. **P2 — The seed-retry regression test no longer fails the seed.**  
   [pcf_seed_retry_test/test.c:164](/Users/jdlien/code/ak820-pro/scripts/pcf_seed_retry_test/test.c:164), [test.c:276](/Users/jdlien/code/ak820-pro/scripts/pcf_seed_retry_test/test.c:276)

   The failure injector rejects the next transaction:
   ```c
   if (pcf_fail_next > 0) { pcf_fail_next--; pcf_xfers_failed++; return MSG_TIMEOUT; }
   ```
   The “first” scenario calls `boot(1)`. With F-005 included, that transaction is now the Control_status_1 read. The calendar seed succeeds immediately. Checking validity and acquisition DONE at 120 seconds therefore passes even if the new seed-retry block is removed.

   **Fix:** Fail the first seven-byte calendar read specifically. Assert that the clock is invalid immediately after boot, stays invalid before the retry deadline, and becomes valid after a later calendar transaction. Add stopped-PCF plus failed-seed coverage and a USB/SOF case. The current “fixed” branch also returns before the existing sleep scenario, so that scenario does not test the fix.

5. **P3 — A successful delayed seed does not restart acquisition if a wake already aborted it.**  
   [rtc.c:2069](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2069), [rtc.c:2409](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2409)

   Wake recovery sets:
   ```c
   acq_state = rtc_valid ? ACQ_WAIT_SPLASH : ACQ_ABORTED;
   ```
   A later successful seed only executes `if (rtc_valid) clock_gen++;`.

   **Failure scenario:** The clock remains invalid through a sleep, then a subsequent seed retry succeeds. Acquisition stays ABORTED, so the comment that it “starts once [the seed] takes” is false. The clock becomes usable but retains the coarse seed’s arbitrary phase until another wake or host sync.

   **Fix:** Rearm acquisition after the first successful delayed seed when the PCF is eligible as a reference. Test a sleep while invalid followed by successful seeding.

What I checked and found sound:

- **F-005’s successful path and wake accounting:** `pcf_sync_host_skipped()` sets `no_retry` on the initially clean state; [rtc_pcf_sync.h:100](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc_pcf_sync.h:100) requires `!s->no_retry` for automatic requests. Acquisition explicitly aborts on `pcfs.stale`. In [wake_coarse():2078](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2078), `!pcf_maybe_stopped` gates elapsed-time use, while `!pcfs.stale` separately gates adopting the absolute calendar. Using differences from a successfully restarted but stale PCF is appropriate: its fixed absolute offset cancels.

- **Early `rtc_bus_guard()` is safe:** [ak820pro.c:88](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:88) initializes the RTC before the display and watchdog. Nevertheless, [lcd_bus.c:912](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:912) initializes `blit_done = true`; the wait’s hardware-polling loops require `!blit_done`, and it returns successfully at line 1284.

- **F-006’s ordinary retry placement:** Resetting the check counter under lock preserves the cadence. Placing the retry before `REF_SOF` correctly allows seeding when USB supplies frequency but no host has supplied calendar time. The staleness exception above needs correction.

- **F-016:** [hid_protocol.c:45](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:45) rejects year values above 98, then validates month before calling `rtc_days_in_month()`. Short-circuit evaluation protects the table index; the shared helper handles Gregorian leap years. Invalid dates return before `rtc_set_time()`.

- **F-025:** The [LLD handler:115](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC/hal_rtc_lld.c:115) reads/clears RIS, then performs `rtc_time++` before the callback. Consuming SECIF and NVIC pending under the step’s lock correctly prevents that increment from corrupting the freshly set calendar. Keeping `reload_pending` preserves the intended first period. The skipped callback loses one `rtc_check_seconds` increment and one latency sample—a one-tick scheduling/telemetry omission. `interval_cycles = 0; win_valid = false;` prevents the SOF estimator from treating the interrupted interval as a valid measurement.

- **F-026:** [rtc.c:590](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:590) compensates exactly the two start cases whose next tick rewrites the register: `slew_left == 1`, or `slew_left == 2 && slew_r != 0`. Otherwise, the first interval accounts for `L + v + 1`, and untouched intervals use the unchanged register plus one. The remainder is followed immediately by restoration. The residual is consequently bounded by the start and restore latencies, rather than accumulating with slew length.