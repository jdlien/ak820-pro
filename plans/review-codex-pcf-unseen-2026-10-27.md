# Codex: the PCF write only when nobody is looking (2026-10-27)

JD (10-27), after the 240 fps clip showed the clock chip's write flickering
the board after every sync (docs/leds.md, "The other flicker";
history/pcf-flicker-20261027/): "Update the clock, only write the RTC when
we sleep or after a pretty long no-typing delay. The failure mode is pretty
minor since the board corrects the clock in a few minutes after a reboot
anyways". qmk_firmware-ak820pro `dc8e6d0c..65f86da5` (branch
`gremlin/pcf-unseen`), then the fixes `65f86da5..6c0501dc`,
`6c0501dc..d72bfaf4` (with `c067502f`) and `d72bfaf4..ecb10f0e`. The
prompts: `plans/review-prompt-pcf-unseen.txt`, `-fix.txt`, `-fix2.txt`,
`-fix3.txt`; the raw replies: `plans/review-codex-pcf-unseen-raw.md`,
`-fix-raw.md`, `-fix2-raw.md`, `-fix3-raw.md`.

## The first reply, verbatim (65f86da5)

- **P2 — Offline clock discipline stops.** Disconnect USB with a deferred write, then keep typing with RGB lit and no wireless clock updates: [rtc.c:1522](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1522) keeps it pending indefinitely; [rtc.c:2291](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2291) suppresses both PCF snapping and rate calibration. The MCU free-runs, and the eventual write transfers accumulated drift into PCF. Preserve rate discipline during deferral.
- **P2 — Diagnostic bursts starve.** [rtc.c:2246](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2246) requires `!pcf_pending`; accepted overrun/depth bursts now stall until darkness or ten minutes without input.

No normal sleep/wake deadlock found; the bench script forces darkness before arming. The [new tests:126](C:/Users/jdlien/code/ak820-pro/scripts/rtc_pcf_sync_test.c:126) cover only the predicate, missing these interactions. Static review of the exact revisions; tests weren’t rerun because process execution was unavailable.

**Dispositions:**
- **P2, the offline discipline: fixed in `6c0501dc`, then again in
  `c067502f`** (below). A pending PCF write stops RTC_AUTO_CALIBRATION
  (`rtc.c`, it waits on a pending or stale PCF), so a deferral off USB left
  the board free-running and carried its drift into the PCF.
- **P2, the dev bursts: fixed in `6c0501dc`.** An armed `burst_active()`
  lets the write start; `burst_step()` still waits for it to finish.

## The re-check, verbatim (6c0501dc)

Not both closed.

- **P2 remains:** the timeout bounds starvation, but calibration stays disabled before accumulated drift is written into PCF (~9 seconds at 1% error): [rtc.c:2307](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2307), [rtc.c:1495](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1495).
- **New P2:** a sync accepted before `wake_coarse()` gets aged by its sleep correction without rebasing `last_sync_secs`, potentially exceeding 900 immediately: [rtc.c:2013](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2013), [rtc.c:1524](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1524).
- **Dev burst starvation is closed:** [rtc.c:1522](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1522), [rtc.c:2262](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2262).

Wake/acquisition clears and radio/INTERNAL/SKIP_PCF paths otherwise look consistent. [New tests:126](C:/Users/jdlien/code/ak820-pro/scripts/rtc_pcf_sync_test.c:126) cover the predicate, not these interactions. Static review; execution unavailable.

**Dispositions:** the host-quiet timer (a host set within 15 min) bounded
the deferral but left the discipline off for minutes, and a sleep's
correction to `rtc_seconds_count` aged it. **Both fixed in `c067502f` by
narrowing the deferral to where nothing reads the PCF:** USB's SOF owning
the rate (`REF_SOF`). There RTC_AUTO_CALIBRATION returns early and the
sleep refuses a live bus (DSB_USB), so a late write costs nothing; the
reference leaves `REF_SOF` within one 10 Hz `rtc_ref_task()` of the bus
going, and the write then goes at once, before the discipline resumes. The
timer is gone. The idle time is read once a second
(`last_input_activity_elapsed()` is a 64-bit divide here), in two bytes
for the heap gap's 128 B floor (`d72bfaf4`).

## The third look, verbatim (d72bfaf4)

**Not unconditionally.** Sleep-age P2 is closed; ordinary USB exits preserve write-before-calibration ([rtc.c:2318](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2318)).

**Conditional P2:** [ak820pro.c:648](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:648) skips `rtc_task()` during animation, freezing `REF_SOF` after unplug/suspend. Lit typing can then defer indefinitely; eventual writing preserves accumulated drift. JD’s documented empty animation slot avoids this trigger.

`DSB_USB` can clear before `REF_SOF`, allowing sleep, but pending writes block it ([sleep.c:245](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:245), [rtc.c:1888](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1888)). Radio sets and cache clearing look sound; low-byte collisions delay at most one second ([rtc.c:1535](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1535)). [Tests:129](C:/Users/jdlien/code/ak820-pro/scripts/rtc_pcf_sync_test.c:129) cover the predicate, not these interactions. Static review; tests not rerun.

**Dispositions:** the sleep-age P2 closed. **The conditional P2 (an
animation skips `rtc_task()`, freezing `ref_state` at `REF_SOF` after an
unplug): fixed in `ecb10f0e`**: `pcf_start_ok()` reads
`usbGetDriverStateI(&USBD1) == USB_ACTIVE` itself, under the same short
lock `rtc_task()` uses, and defers only with both. `rtc_fast_task()`, where
the gate runs, is not gated on the animation. JD's animation slot is empty,
so it could not have fired on this board.

## The narrow re-check, verbatim (ecb10f0e)

**P2 closed.** [rtc.c:1533](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1533) permits writes when USB is inactive despite stale `REF_SOF`; the fast task continues during animation.

**Lock safe:** normal and recovery calls ([rtc.c:2281](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2281), [rtc.c:2261](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2261)) run in unlocked thread context; wake releases its lock at [sleep.c:612](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:612). The critical section only reads driver state.

No new findings in `d72bfaf4..ecb10f0e`. Static review; tests not rerun.

**Disposition:** cleared; flashed on the keyboard on gremlin at 20:36
10-27 (JD: "flash it once codex clears it").

## Open, not codex's

On battery with the Mac's radio clock (the keyboard on Buzz, cable out) the
write still follows each sync, so the flicker stays there. Deferring there
needs the board's own discipline settled first: it runs between radio syncs
against a fresh PCF.
