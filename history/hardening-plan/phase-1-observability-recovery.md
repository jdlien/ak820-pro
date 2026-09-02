# Phase 1 — Observability and recovery

**Theme:** cap the blast radius of every future bug, and make sure the next
incident starts with data instead of theorising. Do this **before** the
riskier phase-3 refactors so their soak testing has teeth.

**Exit criterion:** a deliberate main-loop stall recovers by itself within
seconds; one console line summarises board health; a scripted stress run
exists that exercises the known trigger paths concurrently.

## 1.1 Hardware watchdog (the major change)

Every catastrophic failure so far shares one signature: main loop stalled,
power cycle required (the eeconfig/blit hang, the blit-timeout crawl before
it was bounded). A watchdog converts that whole class from "board bricked
until you reach the dip switch" into "board blips and reboots itself".

Design:

- **Use the existing ChibiOS-contrib driver, not bare registers.** The SN32
  WDG LLD already exists
  (`lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/WDT/hal_wdg_lld.c`)
  and the SN32F290 platform includes its build file. Enable `HAL_USE_WDG` +
  `SN32_WDG_USE_WDT` and use `wdgStart`/`wdgReset`/`wdgStop`. The LLD is
  lightly exercised — audit it (clock source, max reachable timeout, config
  semantics) rather than trusting it, but do not duplicate it.
- **Kick at the very END of `housekeeping_task_kb()`**, after the 10 Hz
  block (RTC I2C, animation, display) and after `housekeeping_task_user()`.
  A kick at entry certifies only that a pass *started* — it hands a freshly
  wedged pass another full timeout and proves nothing about the downstream
  tasks. Never kick from any ISR: the historical hangs left ISRs running
  (the row mux kept one row lit), so an ISR-side kick defeats the point.
- **Start the WDT only after init completes** (end of keyboard post-init) —
  boot deliberately blocks for long stretches (`lcd_init()` alone spends
  240 ms in `wait_ms`, plus the asset index read and RTC seed).
- **Timeout ~3 s** — well above every legitimate blocking window: bounded
  blit waits (~250 ms, several per pass worst-case), sector erase (ms),
  and the full 48-sector asset-provision erase sequence.
- **⚠️ Reset-during-flash-write must be tested BEFORE enabling generally.**
  A WDT reset can land mid-program/mid-erase in the EFL wear-leveling
  store, and a corrupted logical store must not become a boot loop or
  silently trashed eeconfig/dynamic-keymap state. Required before the
  "blast-radius cap" claim is honest: verify `wear_leveling_efl` recovers
  (or resets to defaults cleanly) after interruption at program and erase
  boundaries — inject a deliberate stall inside the write path to force the
  WDT to fire there, and confirm the board boots with sane config. This
  also gates phase 4, which adds more writers.
- **Reset-loop escape.** A deterministic boot-time failure (LCD, RTC I2C,
  corrupt eeconfig) plus a WDT is an endless 3 s reset loop, possibly on
  battery. Count consecutive WDT resets in noinit/retained RAM; past a
  small threshold (e.g. 3), boot in a degraded mode — skip the risky
  subsystem(s) and/or leave the WDT off — so the board stays flashable and
  usable as a keyboard.
- **Post-reset breadcrumb:** the SN32 exposes a reset-status register
  (`RSTST.WDTRSTF`), so the cause is knowable. Log `[wdt] reset (n=N)` at
  boot on the console **and expose the count over raw HID** (an `ak820ctl
  info`-style field) — the LCD marker alone is useless when the LCD is the
  failing subsystem, and the console may not be attached.
- **`QK_BOOT` interaction needs a concrete code change, not just checking:**
  `bootloader_jump()` (weak, `platforms/chibios/bootloaders/sn32_dfu.c`)
  writes the RAM magic and calls `NVIC_SystemReset()` — nothing stops the
  WDT first, and a WDT that survives into the bootloader's wait loop would
  reset out of it mid-flash. Override `bootloader_jump()` for this board to
  `wdgStop()` before setting the magic. Also verify empirically whether the
  WDT even survives `NVIC_SystemReset()` on this part; the override is
  correct either way. Release blocker for this phase.

**Verification:** temporary magic-key test hooks (both-shifts + key style):
(a) spin forever with interrupts enabled → reset in ~3 s, clean boot, cause
logged; (b) spin *inside* the flash-write path → same, plus config survives
or resets cleanly; (c) stall inside RTC I2C and inside
`housekeeping_task_user()` — the kick placement must catch all of them.
Then remove the hooks. Soak a normal session for zero spurious resets,
including VIA writes and a full asset provision (the 48-sector erase runs on
the main loop — confirm the kick cadence survives it). Verify `Fn`+`Esc` →
bootloader → flash → reboot works end-to-end with the WDT enabled.

## 1.2 Unified health counters — raw HID primary, console secondary

**The daily build now has NO console** (`console: false` since commit
6689927483), which inverts the original design: the raw-HID counter report
is the PRIMARY observability channel — it exists in every flavor — and the
`[health]` console line is the instrumented-flavor extra. Counters
accumulate in RAM unconditionally (they cost nothing); only the reporting
differs by flavor.

Two lessons from the loop-gap investigation, now binding on every probe:

- **An instrument must not touch the subsystem under test, and must report
  somewhere inert.** The LCD-reporting probe fed its own stalls and ran
  away to 154 ms; the console report died with the console. Counters in
  RAM, read out over raw HID, satisfy this by construction.
- **Thresholds sit well above the noise floor** — the 4 ms gap threshold
  flagged ordinary ~3.4 ms loop jitter ~90×/s and buried the real 20–53 ms
  events.

The instruments exist but grew piecemeal per-incident: `[lcd] blit timeout
#N`, `[ch582]` tx counters, loop-gap probe, `key_stat_task`. Consolidate:

- One line, printed **on meaningful change only**, e.g.
  `[health] blit_to=0 uart_to=3 uart_drop=0 gap=18ms scan=391`. "On change"
  needs care for naturally jittery values: quantise scan rate into tolerance
  bands and report the loop-gap max only when a new max is set after the
  settle window (the probe already does this), so the line cannot become
  continuous traffic — console load itself perturbs the host (see the
  2026-08-30 incident).
- Include: blit timeout count, UART tx timeout/drop counts, malformed-frame
  count (phase 2), worst main-loop gap since boot, matrix scan band, WDT
  reset count (from 1.1).
- Snapshot the counters atomically (brief interrupt mask) before formatting.
- **Also expose the cumulative counters over raw HID** (extend the existing
  info reply): console-only observability disappears during exactly the
  stalls being investigated, and the raw-HID path works where the console
  isn't attached.
- Keep the console line `CONSOLE_ENABLE`-gated like the existing
  instruments. The loop-gap probe graduates from `LOOPGAP_INSTRUMENT`
  (LCD-reporting, temporary) into this permanent line; per its own comment
  the LCD path was only needed while the console itself was under test.
- Document the healthy baseline numbers in the CLAUDE.md quirks section so a
  future session can tell signal from noise at a glance.

## 1.3 Soak / stress harness (host side)

A script (`hostagent/soak.sh` or Python beside `ak820text.py`) that hammers
the known trigger paths **concurrently** while capturing the timestamped
console log:

- Text pushes at high cadence (both lines, varying lengths) — LCD DMA blits.
- VIA-style dynamic-keymap writes via raw HID — internal-flash writes racing
  those blits (the reliable hang reproduction, per CLAUDE.md).
- RGB adjustments via raw HID (`qmk_rgb_matrix` channel) — the eeconfig path.
- Cycle through every enabled RGB effect with a dwell on each, longest on
  the custom ones (RAINFALL, DRIFT) — new per-frame code whose CPU cost
  shows up in the scan-rate band, exercised while text pushes contend for
  the panel (the contended case that mattered for DRIFT's acceptance).
- Periodic `ak820ctl info` round-trips as the liveness probe; a missed reply
  is the failure signal, with the console log showing what preceded it.

**Transaction discipline:** one owning process, one request/reply dispatcher
— only ONE reply-bearing transaction in flight at a time, or the concurrent
producers consume each other's replies and manufacture false liveness
failures. Concurrency comes from *firmware-side* cadence overlap (write-only
text packets interleaved between transactions), not from parallel host
requests on one interface.

**Pass criteria are rates, not "any increase":** the measured healthy BT
baseline is ~0.042 ACK timeouts/frame sustained (boot traffic runs ~0.58 and
must be excluded), so a soak that fails on any counter tick fails by design.
Thresholds over a minimum sample count for timeout rates, tolerance bands
for scan rate and loop gap; hard-fail immediately only on: dropped frames,
liveness loss, blit timeouts, or a WDT reset. Runs for a configurable
duration; exits nonzero with the last N console lines on failure.

Constraints: the harness owns the raw-HID interface for its duration — stop
the nowplaying LaunchAgent while it runs (`launchctl unload`, reload after),
and never run it alongside VIA or a second `qmk console`. Soak runs use the
**instrumented flavor** (console + probes); after a green soak, flash the
daily flavor and re-run a shortened pass reading counters over raw HID only
— what ships is what got soaked. Deliberately OUT
of scope: flipping the mode switch during an asset provision — CLAUDE.md
documents that as destructive (the erase has already happened); if that
resilience is ever tested, it is a manual, eyes-open test with a planned
re-provision after.

Wired mode only (raw-HID replies route through the active host driver).
A BT-mode variant can only do write-only pushes + console watching.

**This harness is the gate for every phase-3 change**: green soak before,
green soak after.

## 1.4 Keep, formalised

The timestamped console capture recipe from CLAUDE.md becomes a one-liner
script (`scripts/consolelog.sh`) so it is always run the same way, appending
to `~/Library/Logs/ak820pro-console.log`. Guard against the known
self-inflicted wound: the script refuses to start if another `qmk console`
is already running (`pgrep`), since a second instance spins in an exclusive-
access retry loop and degraded the host badly on 2026-08-30.

## Deliverables

- [ ] WDT running, kick in housekeeping, ~3 s timeout, boot-time cause log;
      bootloader interaction verified safe.
- [ ] Stall test performed and removed; zero spurious resets over a full
      soak including asset provisioning.
- [ ] `[health]` line replacing the piecemeal instruments; baselines
      documented.
- [ ] Soak harness with pass/fail exit; documented invocation.
- [ ] `scripts/consolelog.sh` with the pgrep guard.
