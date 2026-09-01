# Hardware verification checklist

Steps that need JD at the keyboard. Software work proceeds ahead of these;
nothing is flashed without you. Run top to bottom when convenient — each
entry says what to do and what "pass" looks like. Build artifacts are in
`ak820pro-builds/out/` (never flash the shared `$QMK_HOME` binary).

## Phase 0 — build provenance

- [ ] Flash the current daily artifact via
      `./flash.sh ak820pro-builds/out/via-daily-<newest>.bin`
      (Fn+Esc first; flash.sh dumps/restores the VIA keymap).
      **Pass:** checksum OK, board back as 0x8009, panel normal, typing
      normal — proves a script-built binary from the committed patches
      branch is flightworthy. Everything later builds on this.

## Phase 1 — watchdog + health (commit a4382c747c)

Flash the newest **instrumented** artifact first for the tests, then the
daily one to live on. `./scripts/consolelog.sh` in one terminal for the
console tests.

- [ ] **Normal boot, no spurious resets.** Flash instrumented; use the board
      normally ~10 min including some VIA edits and RGB adjustment.
      **Pass:** `python3 hostagent/ak820health.py` shows
      `wdt_consecutive_resets 0`, `wdt_fired_last_boot False`, and no
      `[health]` anomalies in the console log.
- [ ] **Watchdog catches a wedge.** `python3 -c "import sys;
      sys.path.insert(0,'hostagent'); from ak820health import open_device;
      h=open_device(); h.write(bytes([0,0x07,0x13,0x7E,1]+[0]*27))"`
      — the board wedges silently (typing dead).
      **Pass:** it comes back BY ITSELF in ~12 s (measure it — if ~2x off,
      the WDTPRE encoding assumption in watchdog.c is wrong; halve/double
      WDT_TC). Console shows `[wdt] reset recovery: consecutive=1`;
      ak820health shows `wdt_fired_last_boot True`.
- [ ] **Reset near a flash write.** Same command with mode `2` instead
      of `1`. **Pass:** board self-recovers; afterwards VIA still shows the
      correct keymap, the BT slot memory survives, and RGB settings are
      sane — i.e. the interrupted-write recovery left the EEPROM store
      usable. (kb-config pad byte 0 gets toggled by the test; harmless.)
- [ ] **Degraded-mode escape.** Run the mode-1 wedge 3x in a row without a
      power cycle. **Pass:** after the 3rd reset the board boots with
      `wdt_degraded True` and stops resetting; a power cycle (slider off
      ~10 s) clears it back to normal.
- [ ] **Bootloader interaction.** With instrumented flashed, `Fn`+`Esc` →
      bootloader; leave it sitting for 60 s. **Pass:** it STAYS in the
      bootloader (0x7140, no self-reset — proves wdgStop before the jump
      works), then flash normally and the board comes back.
- [ ] **Soak.** `launchctl unload ~/Library/LaunchAgents/com.jdlien.ak820pro.nowplaying.plist`,
      then `python3 scripts/soak.py --seconds 300`. **Pass:** `SOAK PASS`,
      worst loop gap well under 60 ms. Reload the agent after.
- [ ] **RTC trim note:** each WDT reset costs the (unpersisted) divider trim
      — expect the clock to re-converge for a few minutes after the reset
      tests. Phase 4 persists it.
- [ ] Finish by flashing the newest **daily** artifact; quick re-run of the
      first checklist item's checks.

## Phase 2 — audit fixes (commit c2b0bd4b9c)

Rides along with the phase-1 flash (same artifacts). Additional checks:

- [ ] **BT regression pass for the TX coalescing change.** In BT mode, type
      a sustained fast burst; verify no stuck keys, no missed releases, and
      `[ch582]`/health `tx_drops` stays 0. The coalescing only engages when
      the ring is nearly full, so normal typing must be byte-identical to
      before.
- [ ] **Clock set still works:** `ak820ctl clock --no-wait` (wired), panel
      time correct — confirms the new RTC validation accepts real dates.
- [ ] **Malformed counter stays 0** in normal use (wired and BT):
      `ak820health.py` → `rx_malformed 0`. A nonzero here with healthy
      typing means the heuristic is too eager — report, don't ignore.
- [ ] **(Optional, advanced) asset re-provision during an instrumented
      soak**: start `soak.py`, then run an `ak820ctl flash write` of the
      current `flash_assets.bin` concurrently is NOT possible (one raw-HID
      owner) — instead: stop the soak, provision normally, power-cycle,
      re-run the soak, confirming provisioning + the new firmware coexist.
- [ ] **Record baselines into CLAUDE.md** after the first clean instrumented
      session: typical `[health]` line, worst loop gap, scan band — the
      numbers a future session compares against.

## Phase 3 — refactors (commits 1b6b6f8003..ba2d6a2cd4)

Same artifacts as phases 1-2. The refactors target zero behaviour change,
so the verification is "everything still works", plus the BT fault matrix:

- [ ] **General pass:** typing, encoder (incl. fast spins + the LSA
      fine-volume on Mac layers), Fn hotkeys, RGB adjust hold-to-repeat and
      end-stop readouts, LCD brightness keys, NKRO toggle readout, VIA
      keymap edit, dip switches (Mac/Win logo + mode slider), clock,
      battery icon/percent/bolt, lock band, media text + playback timer.
- [ ] **Clock/playback band via the glyph queue:** watch the seconds tick
      (no flicker), start/stop media (band swaps cleanly, no stranded
      pixels), let a >1 h video run past the hour (font switch relayout
      clean).
- [ ] **BT matrix (findings-ch582-states.md):** pair/unpair on all three
      slots; cancel-pairing on the same slot (the bounce -- ~1 s recovery);
      select an unreachable slot (Link failed + remedy text, digit lazy
      pulse); 2.4G mode; media keys over BT while LINKING; a macOS slow
      reconnect.
- [ ] **Fault injection (instrumented):** `python3 scripts/bt_faults.py`
      — ALL FAULT TESTS PASS. Then toggle the mode slider to restore real
      link state.

## Phase 4 — persistence (commit 08aecac174)

- [ ] **Brightness survives a power cycle:** set a non-default level with
      Fn+PgUp/PgDn, wait ~6 s (the settle window), slider off ~10 s, back
      on. **Pass:** the level is what you set, not `LCD 56%`.
- [ ] **BT slot still remembered** (now via the deferred flush): select
      slot 2, wait ~6 s, power cycle in BT mode → reconnects to slot 2.
- [ ] **RTC trim persists:** run wired ≥ 10 min (instrumented build:
      `[rtc] trim` lines should be rare/absent thanks to the 33600 seed;
      if a trim fires after the 10 min mark it persists). Power cycle,
      then watch the first 15 min of console: **zero** `[rtc]` trim/snap
      lines means the stored seed took. (First boot after this flash still
      uses RTC_PERIOD_INITIAL until one post-10-min trim runs.)
- [ ] **Fresh-block fallback:** nothing to do unless you ever
      `eeconfig_init` -- then defaults return and re-persist on use.
- [ ] **Re-run the phase-1 mode-2 WDT test** once after this flash: the
      interrupted-write recovery now protects four live fields; confirm
      slot/brightness/period all read back sane after the reset.

All software phases are complete; whatever remains above is the hardware
gate for the whole plan.
