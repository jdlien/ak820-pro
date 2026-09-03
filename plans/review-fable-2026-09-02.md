# Fable 5.1 review — LOOP-BUDGET-PLAN, 2026-09-02

Adversarial design review. Findings integrated into the plan rewrite of the
same date. Companion: `review-codex-2026-09-02.md` — the two were run
independently and converged on the two critical findings.

---

## Verdict

Phase 1 is mostly sound. Phases 2 and 3 are built on two factual errors about
*where the >=25 ms stalls actually come from*. Phase 2 cannot bound the stalls
that matter (they live inside single sub-tasks); Phase 3 gates an event that is
harmless while making the dangerous one (wear-levelling consolidation) *more*
likely to land mid-typing. Phase 4's soak gate would fail on its own stimulus.

## Premise corrections (these drive the findings)

**P1. Only stalls >= ~25 ms can lose a press; shorter ones only delay it.** A
press lasts >= 25 ms; a shorter stall ends with the key still down and the
ISR-side snapshot catches it. The target class is exclusively >= 25 ms.

**P2. The matrix is scanned in the ROW ISR, not the main loop** —
`drivers/led/sn32f2xx.c:385-419` (`shared_matrix_scan_keys`, called from
`update_pwm_channels`:466), latched into `shared_matrix` and *held* until the
main loop consumes it in `matrix_scan_custom`:856-864 (the `matrix_scanned`
gate). A main-loop stall freezes the scan after one ~1 ms frame, and during
`FLASH_PGM` the ISR skips scanning outright (:649). The blind window still
equals the stall length, so the conclusion survives — but the mechanism matters
for reasoning about what "the ISR keeps running" buys.

**P3. An ordinary eeconfig flush is a SINGLE 8-BYTE LINE PROGRAM, not a
multi-ms event.** The kb block (5 B), `rgb_config_t` (8 B) and a VIA keycode
(2 B) each become exactly one log entry at `BACKING_STORE_WRITE_SIZE 8` → one
`efl_lld_program` → one masked busy-wait of "tens of microseconds"
(`efl_ramtext.diff:31-32`), plus the pre-write blit drain (<= ~1 ms normally).
**The multi-ms event is CONSOLIDATION**: every ~127 entries ((2048-1024-8)/8)
the driver erases 2 x 1 KB sectors synchronously and unmasked
(`hal_efl_lld.c` `efl_lld_start_erase_sector`, `wear_leveling_efl.c:141-164`)
and reprograms 129 lines (`wear_leveling.c:257-290`). `plans/BACKLOG.md:58`
already names it — "sector erases blocking the main loop 50-300 ms, rare and
irregular" — and it is the one number the plan never measures.

**P4. The "~2 ms/pass for timer reads" datum is implausible and should not be
binding.** `timer_read32` (`platforms/chibios/timer.c:100-118`) is a lock, a
tick read and one 64-bit `TIME_I2MS` — ~5-10 us on an M0 at
`CH_CFG_ST_FREQUENCY 187500`. Eight reads ~= 60-80 us, not 2 ms. The
270 -> 175 Hz drop was measured "with the console attached" and never isolated.
Re-measure before it constrains design.

## Findings

### CRITICAL

**C1. Phase 2 bounds nothing that matters.** The budget is checked *between*
sub-tasks; the >=10 ms stalls are *inside* single ones:
- `draw_battery` (`graphics/display.c:925-1000`): DMA clear + `lcd_blit_wait`,
  5 `lcd_fill_rect`s, an 11-run bolt, fill rect, 3-4 synchronous glyphs. By the
  author's own figures (`docs/display.md:269-273` ~0.85 ms/rect;
  `findings-bounded-wait.md` 1.3-2 ms/sync glyph) that is **~20-25 ms on a
  charge-state change** — the most plausible source of today's 25 ms max.
- `draw_locks` Caps on (`:1054-1140`): padlock 5 rects + 4 glyphs ~= 12 ms.
  Fn down/up: clear + 2 glyphs ~= 5 ms on *every* Fn press while typing.
- `kb_eeconfig_task` write; `rtc_task` -> `pcf_read` -> `rtc_bus_guard` ->
  `lcd_blit_wait` (`rtc/rtc.c:213-240`).

Worst case = budget + longest sub-task, i.e. unchanged. Half of these draws are
`static` inside `display_housekeeping_task` (`display.c:1877-1925`), invisible
to a table in `ak820pro.c`. **Replace with**: (a) make `LOOP_SITE` timing
unconditional inside the 10 Hz block (~20 timer reads per 100 ms — free) and
assert a per-sub-task ceiling in instrumented builds; (b) fix the two known
draws by the method the author already proved (`display.md:266-274`, "prefer a
RAM tile over rectangle runs") — battery outline + bolt and the padlock as one
`lcd_blit_ram` each, and route CAPS/WIN/FN through the glyph queue. ~50 lines.

**C2. Phase 3 gates the wrong event, and `EFL_FORCE_AFTER_MS` guarantees the
stall lands mid-typing.** A single write is < 25 ms and cannot lose a press, so
the quiet gate buys nothing. A continuous typist never opens the window, so at
30 s the write fires *while typing by construction* — and if it is the ~128th
entry it triggers a 50-300 ms consolidation. The gate moves the only dangerous
case *onto* the typing path. The deferral also extends the brownout loss window
(`docs/hardware.md:7-29`). The existing settle gates (`RGB_SETTLE_MS 900`,
`KB_EECONFIG_SETTLE_MS 5000`) already keep ordinary writes off the typing path.
**Replace with**: no key-quiet gate on ordinary writes; target consolidation —
expose log fullness from `wear_leveling.c` and run a *proactive* consolidation
from the 10 Hz block when the log is >= ~75% full AND no key event for >= 500 ms
AND `!lcd_blit_busy()`, with **no forced timeout**. Count `flash_writes` and
`consolidations` in health.

### HIGH

**H1. VIA and core paths bypass every proposed gate.** `id_custom_save` ->
`via_qmk_rgb_matrix_save` -> `eeconfig_force_flush_rgb_matrix`
(`quantum/via.c:737-739`, `rgb_matrix.c:102-104`) is an *immediate* synchronous
write from `raw_hid_task`, not "arming the deferred flush" as `soak.py:22-27`
and the plan assume. Likewise `dynamic_keymap_set_keycode`,
`set_single_persistent_default_layer` on the mac/win dip flip
(`keymaps/via/keymap.c:116-118`), and `eeconfig_update_keymap` on the NKRO
magic toggle (`quantum/action_util.c:234`). None passes
`rgb_matrix_eeprom_flush_allowed()` or `kb_eeconfig_task()`.

**H2. Phase 4.1's soak gate fails on its own stimulus and cannot detect a
dropped keystroke.** The soak issues ~300 keymap + ~150 `rgb_save` synchronous
writes per 300 s (`soak.py:190-215`) → ~3-4 consolidations per run, all > 4 ms.
"FAIL if any gap exceeds the budget" is always red unless flash-attributed gaps
are excluded, which requires `loop_stall_mark` (`ak820pro.h:75-79`) to be
unconditional in the daily build (it is a byte store; make it so). The soak
types nothing — it measures loop gaps only. Do not present it as a
keystroke-loss gate.

**H3. The Phase 1 payload does not fit.** `HC_GET` already fills all 28 payload
bytes (`hid_protocol.c:405-409`, `health.c:35-68`). The new counters need a new
command/page, a `HEALTH_PROTO_VERSION` bump, and `ak820health.py` changes.

### MEDIUM

**M1. `modified_consumer_task` must not be deferred.**
`MODIFIED_CONSUMER_HOLD_MS 150` (`config.h:411`) holds REAL Shift+Alt after a
knob spin; a 100 ms deferral makes it 250 ms — inside the inter-key gap — so the
next typed key carries Shift+Alt (on macOS, an input-source switch). Move it to
the per-pass section (one timer compare, `consumer_mod.c:66`).

**M2. `display_second_edge_task` runs the whole display block per-pass, outside
the 10 Hz block** (`ak820pro.c:475`, `display.c:1868-1875`): `draw_clock` /
`draw_battery` fire there once a second. Any table in `ak820pro.c` misses it.

**M3. Scan-rate floor must be per flavour, and the drift is itself a finding.**
Instrumented reads 230-310 Hz (`BACKLOG.md:35-38`); daily has gone 390-400
(2026-09-01) -> 375 -> 345 (2026-09-02). A flat 250 false-trips instrumented,
and the ~12% daily drop since the per-pass tasks were added deserves a bisect.

**M4. `lcd_blit_wait` phase 2 is a 100-250 ms bounded spin**
(`graphics/lcd_bus.c:649, 691`) when a blit started but its IRQ was lost —
reachable from `lcd_clear_rect`, `rtc_bus_guard`, `backing_store_pre_write_hook`,
`draw_ampm`. The largest blind window short of consolidation; only visible in
the histogram if the mark is unconditional.

**M5. `send_report` blocks up to 100 ms** (`usb_main.c:393`) if the host stops
polling while `USB_ACTIVE`. Wired only, rare, but a textbook keystroke-eater the
plan does not list.

**M6. 4.2's "housekeeping precedent" is not one.**
`tests/housekeeping/test_housekeeping.cpp` mocks `housekeeping_task_kb` and
compiles no board code. A board scheduler test needs a standalone pure-C module
plus a host compile (or a `test.mk` `SRC +=` with a `timer_read32` stub). Plan
it as new work.

**M7. 4.3's power and localisation.** 600 chars at a true 0.5% rate passes clean
5% of the time (adequate); at 0.1% it passes 55%. State the bound. And
`key_press_count` is `CONSOLE_ENABLE`-only (`ak820pro.c:275-290`): put a u16
press counter in health so the daily build can split "matrix missed it" from
"lost downstream".

### LOW

**L1.** Patched EFL landmine: `efl_lld_program` erases the *whole sector*
in-line if the target line is not erased. Wear-levelling never hits it
(append-only), but any direct writer would silently destroy the log, and a
"program" can secretly become an "erase". Document it.

**L2.** `sym_defer_g` global defer adds 5 ms after a stall before the latched
change commits — latency only, no loss. No action.

**L3.** Health counters die on slider brownouts (`hardware.md:23-26`).
CLAUDE.md says raw-HID replies work in any mode with the cable (4b86d95014)
while `BACKLOG.md:45-52` still says they do not — reconcile before 4.4 depends
on it.

**L4.** `HC_RESET`: define what it clears. The soak uses deltas against a
baseline; WDT counters are boot facts and should not be resettable.

## Answers to the five open questions

1. **`HK_BUDGET_MS`** — 4 ms is the wrong quantity to fix. The MCU is ~72% ISR
   (`docs/leds.md:66-71`), so 4 ms wall ~= 1.1 ms CPU; budget in wall-clock
   regardless. Set: housekeeping-to-housekeeping gap <= 10 ms is the goal,
   >= 25 ms is the failure, 10 Hz block soft budget 6 ms, **per-sub-task hard
   ceiling 5 ms** measured and asserted in instrumented builds.
2. **Non-deferrable sub-tasks** — none is hard-real-time. Only
   `modified_consumer_task` has a user-visible failure when deferred (M1): move
   it per-pass. `anim_task` is a no-op on this unit; `bt_pair_hold_task`
   deferral = pairing 100 ms late. Drop `must_run_every_tick`.
3. **VIA gate** — no. VIA writes happen while the user is in VIA, not typing,
   and the write itself is < 25 ms. Handle the *consolidation* a VIA write can
   trigger (C2) and the immediate `id_custom_save` path the soak misdescribes
   (H1).
4. **Shape** — not a histogram. Keep `count_ge_10ms`, `count_ge_25ms`,
   `max_ms`, `max_mark` (flash/blit/i2c/site, unconditional), `passes`, plus
   `flash_writes`, `consolidations`, `key_presses` (u16). That answers "how
   often does a keystroke-eating stall happen and what was it".
5. **Outside the 10 Hz block** — yes: `display_second_edge_task` (M2); raw-HID
   immediate writes and the consolidation they can trigger (H1/C2);
   `lcd_blit_wait` recovery spin (M4); `rtc_fast_task` ~0.4-1 ms normally but a
   20 ms clock-stretch timeout on a stuck bus (`rtc.c:28`); USB send 100 ms
   (M5); `wait_ms(8)` in `process_modified_consumer` — bounded, harmless.
   Per-pass instrumentation is not banned by physics (P4).

## What to build instead, in order

1. Phase 1 with H3 fixed, unconditional stall mark, and
   `flash_writes`/`consolidations`/`key_presses` counters. Then **measure**: one
   line write, one consolidation, `draw_battery` on a charge flip, `draw_locks`
   on Caps. One evening; it decides everything below.
2. RAM-tile the bolt/battery outline/padlock; queue the lock labels (C1).
3. Proactive quiet-time consolidation, no forced timeout (C2).
4. Soak gate with attribution-aware thresholds: non-flash gaps <= 10 ms; single
   write <= measured X; consolidation <= measured Y and count == expected (H2).
5. Skip the cooperative scheduler.
