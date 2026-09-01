# Findings — concurrency audit (phase 2.1)

Audited 2026-09-01 at QMK commit `a4382c747c` (chibios-contrib
`ak820pro-patches` tip). Method: enumerated execution contexts, then traced
the actual call chain for every static/global in the board files, the two
core-edit files, and the ChibiOS patches. Cortex-M0 ground rules: aligned
8/16/32-bit loads and stores are single-copy atomic; no atomic RMW exists;
`chSysLock()` masks via PRIMASK (everything).

## Verified ownership model

| Context | Priority / rate | Owns (writes) |
|---|---|---|
| main loop (QMK thread) | ~390 Hz housekeeping, sub-ms task loop | ALL keyboard logic: matrix/encoder, process_record, housekeeping tasks, `ch582_task()` **including the whole CH582F parser, state machine, and frame TX queue**, display state + glyph queue + panel shadows, blit arming (`blit_done = false`), eeconfig/EFL writes, raw HID (`raw_hid_task()` in `usb_main.c:517` — main loop, not ISR), health counters, watchdog kick/state |
| row-scan PWM ISR (CT16B0/1/2, prio 3, ~18.8 k/s) | LED mux | reads `led_state[]`; writes `matrix_scanned`/`shared_matrix` (SHARED_MATRIX) |
| GPT tick (CT16B3, prio 2, 20 kHz) | backlight + indicator PWM | RMWs `bkl_phase`, `ind_phase`; reads `bkl_level`, `display_powered`, `ind_*` |
| UART2 ISR (prio 1) | ChibiOS serial driver | **byte queues only** — plan's corrected claim VERIFIED: `ch582_task()` is called from `bluetooth_task()` (`quantum/keyboard.c:793`, main loop) and drains bytes via `chnReadTimeout` (`ch582f_ajazz.c:672`); no CH582F state is touched from ISR context |
| SPI0 DMA completion ISR | per blit | sets `blit_done`, raises CS (`blit_done_cb`, `lcd_bus.c:676`) |
| **RTC 1 Hz ISR** (`rtc_second_cb`, `rtc.c:287`) | 1 Hz | RMWs `rtc_seconds_count`, `rtc_check_seconds` — **a sixth context the plan's table omitted** |

## Findings (ranked)

### 1. LOW — class (a): `rtc_check_seconds` RMW in the RTC ISR races the main-loop reset

`rtc.c:295` (ISR): `rtc_check_seconds = MIN(rtc_check_seconds + 1, RTC_CHECK_INTERVAL_S);`
`rtc.c:517` (main, `rtc_task`): `rtc_check_seconds = 0;`

Interleaving: the ISR loads the old value, the main loop stores 0, the ISR
stores old+1 — the window reset is lost. Failure scenario: the next
calibration check fires ~1 s later instead of after the full interval (the
value is at the cap, so old+1 re-caps and re-triggers). The trim itself
cannot go wrong — it measures from `rtc_seconds_count` plus the PCF's
absolute time, not this counter — so the worst case is one early, harmless
re-check, at a coincidence rate of (one instruction pair) × 1 Hz vs one
reset per interval. **Disposition: fix-now (trivial)** — wrap the `= 0` in
`chSysLock()/chSysUnlock()`, or have the ISR only increment below the cap
and accept the same benign outcome. Not worth more machinery.

### 2. LOW — class (c): `display_powered` lacks `volatile`

`display.c:87` `static bool display_powered = true;` — written by main
(`display_set_power`, line 195), read every GPT tick in ISR context
(`display_backlight_tick`, line 151). Single-byte, and each ISR entry
reloads it (no caching loop exists), so this is benign **today** — but it
is the one ISR-read variable in the tick path without `volatile`, while all
its siblings (`bkl_level`, `ind_*`) have it. A future refactor that loops
over it could silently cache. **Disposition: fix-now (one keyword)** for
consistency of the discipline.

### 3. INFO — `sn32f2xx_blank()` has no caller

`drivers/led/sn32f2xx.c:738`, exported at `sn32f2xx.h:84`; grep finds no
call site. Its own comment scopes it to callers "about to stop the ISR" —
the direct-jump-to-bootloader experiment that was reverted. Reset-based
paths (WDT reset, `NVIC_SystemReset` in `bootloader_jump`) put GPIOs in
reset state anyway, and the masked EFL program window (ms-scale, one row
held at full duty) is a documented, accepted artifact that a blank call
could not fix without killing the whole frame. **Disposition:
accept-and-document** (keep as the tool for any future stop-the-ISR path).

### 4. INFO — `health_note_rx_malformed()` must stay main-loop-only

`health.c:31` does an unguarded 32-bit RMW (`rx_malformed++`). It currently
has **zero callers**; the intended caller (phase 2.3, the CH582F parser) is
main-loop, which is fine. If it is ever called from ISR context the counter
needs masking. **Disposition: accept-and-document** — noted here and worth
one comment line when the caller lands.

## Areas verified clean (evidence, one line each)

- **CH582F driver state** (`conn_state`, five pending flag/timer pairs,
  `module_alive`, tx queue head/tail/in-flight, `tx_stat_*`): every writer
  traced to `ch582_task()`/`process_record`/housekeeping — all main loop;
  the `volatile` qualifiers are superfluous but harmless.
- **Frame-copy lock** (`sn32f2xx.c:775`, commit bba2012d07): `chSysLock()`
  is PRIMASK on M0, so the row ISR cannot land mid-`memcpy`; the race it
  claims to close is closed, cost ~16 µs bounded, and both
  `led_state_buf` writers (`set_color`, `flush`) are main-loop.
- **Blit machinery**: `blit_done` is `volatile` (`lcd_bus.c:551`), set only
  in the DMA completion callback, cleared only at main-loop arm
  (`lcd_bus.c:595`); the timeout/abort path is idempotent against a
  late-firing completion (both raise CS and set done); `blit_count`,
  `blit_retries`, retry parameters are main-only.
- **Glyph queue + panel shadows** (`gq[]`, `gq_n/gq_i`, band shadows): all
  writers are display functions called from raw HID (main via
  `raw_hid_task`), housekeeping, or `process_record` — main-loop-only, and
  the pump cannot race `backing_store_pre_write_hook()` since both run on
  the main loop (flash writes are synchronous there).
- **Backlight/indicator PWM**: `bkl_level` main-write/ISR-read single-byte
  `volatile`; `bkl_phase`/`ind_phase` ISR-only RMW; `ind_*` flags and
  levels single-byte `volatile`, main-write/ISR-read. Correct by size and
  qualifier (finding 2 excepted).
- **`bt_pair_timer`/`bt_pair_armed`**: `process_record_kb` (main) and
  `bt_pair_hold_task` (housekeeping, main) — same context, no race.
- **Watchdog + health state**: main-loop-only. (The original top-of-heap
  word placement was superseded the same day by a reserved `.ram7` linker
  region — see the phase-1 Codex review fix — so the heap-collision
  question is now moot by construction.)
- **Custom effects** (`rgb_matrix_kb.inc`): all statics touched only inside
  the `.inc` (zero external references); simulation steps gated on
  `params->iter == 0` (lines 44, 207) so LED_PROCESS_LIMIT chunking cannot
  multiply the rate; DRIFT accumulators are `uint32_t` (line 194), wrapping
  on whole table periods.
- **EFL masked program window** (`hal_efl_lld.c:60`,
  `__disable_irq`-bracketed, `.ramtext`-resident): nothing added since
  assumes live interrupts inside it — the blit is drained *before* via the
  pre-write hook, the watchdog tolerates it by four orders of magnitude
  (and the WDT counts on the ILRC, which PRIMASK cannot mask, so the
  masked window remains guarded), and `loop_stall_mark` writes are plain
  stores.
- **`matrix_locked`/`matrix_scanned`** (SHARED_MATRIX): upstream pattern,
  single-byte `volatile`, row-ISR-write/main-read.
- **`loop_stall_mark`**: multi-site but all main-context writers (blit
  wait, RTC I2C, EFL hook), instrumented builds only.

## Scan-rate note

Per-frame CPU of DRIFT/RAINFALL could not be measured in this audit
(read-only, no hardware run); the `[health]` scan-rate band during the
phase-1 soak with each effect dwelled is the measurement — already in the
soak/checklist design.

## Out-of-scope observation

`lcd_blit_wait`'s start-detection loop reads `SN_SPI0->RIS` with magic mask
`0x30u` in two places — a named constant would help; the bounded-wait audit
covers that function.
