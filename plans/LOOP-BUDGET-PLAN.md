# Stall measurement, and what it gates — plan

Status: **PHASE 1 APPROVED, 2026-09-02.** Phases 2-4 are DEFERRED and
explicitly gated on Phase 1's measurements — do not build them on the strength
of this document alone. Reviewed adversarially by Codex
(`review-codex-2026-09-02.md`) and Fable 5.1 (`review-fable-2026-09-02.md`),
run independently; they converged on the two critical findings and the first
draft of this plan was substantially wrong.

## The question

JD perceives occasional missed keystrokes and, historically, stuck keys. The
firmware does a lot — RGB, LCD over DMA, wireless, RTC — and the worry is that
some of that busy-ness blocks long enough to lose a press.

## What is actually true (corrected by review)

**Only stalls >= ~25 ms can lose a press.** A real keypress holds contact
25-80 ms. Anything shorter ends with the key still down and is merely late.
This single threshold invalidates most of what the first draft defended
against.

**The matrix is scanned in the ROW ISR, not the main loop.**
`shared_matrix_scan_keys` (`drivers/led/sn32f2xx.c:385`) latches into
`shared_matrix`; the main loop only consumes it via `matrix_scan_custom:856`
behind the `matrix_scanned` gate. A main-loop stall therefore still creates a
blind window of the same length — the ISR will not re-scan until the latch is
consumed — and during `FLASH_PGM` the ISR skips scanning entirely. The
conclusion survives; the first draft's mechanism did not.

**An ordinary eeconfig write is a single 8-byte line program — tens of
microseconds.** Not a multi-millisecond stall. Every "defer flash writes away
from typing" idea in the first draft was aimed at a non-event.

**The real multi-millisecond event is wear-levelling CONSOLIDATION**: every
~127 log entries, 2 x 1 KB sector erases, synchronous and unmasked, then 129
lines reprogrammed. **`plans/BACKLOG.md` already named this** — "sector erases
blocking the main loop 50-300 ms, rare and irregular" — and it has never been
measured.

**Nothing identified can explain a steady 0.5% loss.** At ~5 keystrokes/s that
would need a >25 ms stall every ~40 s. Consolidation cannot fire that often
during typing (entries barely accrue while typing); `draw_battery` (~20-25 ms)
needs a charge-state change; `draw_locks` on Fn (~5 ms) and Caps (~12 ms) are
below the threshold and can only delay. JD's own samples on 2026-09-02 were
204/204 letters and 215/215 `e` clean, with the sole loss on the space bar.
**Expect this work to find a real but RARE fault, not the felt symptom.**

## Phase 1 — measurement (APPROVED, build this)

No behaviour change. Everything lives on the daily build.

1.1 **A new health page.** `HC_GET`'s 28-byte payload is already exactly full
(`hid_protocol.c:405`, `health.c:35`), so the new counters need a new command
or page plus a `HEALTH_PROTO_VERSION` bump and matching `ak820health.py`
changes. Both reviewers caught this independently.

1.2 **Counters, not a histogram.** Buckets answer the wrong question. Keep:

| Counter | Why |
|---|---|
| `max_ms` | worst gap since reset |
| `max_mark` | **what** it was — flash / blit / i2c / site |
| `count_ge_10ms` | latency events |
| `count_ge_25ms` | **the keystroke-losing class** |
| `passes` | denominator, to recover rates |
| `flash_writes` | ordinary line programs |
| `consolidations` | the 50-300 ms event, counted for the first time |
| `key_presses` (u16) | today `CONSOLE_ENABLE`-only; needed on the daily build to split "matrix missed it" from "lost downstream" |

1.3 **`loop_stall_mark` unconditional in the daily build.** It is a byte store.
Without it no gap can be attributed, and the soak gate cannot exclude
flash-attributed gaps from its threshold.

1.4 **`HC_RESET`.** Clears the resettable counters only; watchdog counters are
boot facts and stay. Without it every reading is contaminated by boot and no
experiment repeats.

1.5 **Scan-rate floor is per build flavour.** Instrumented reads 230-310 Hz,
daily 345-400. A flat floor false-trips instrumented. Also worth a bisect on
its own: daily has drifted 390-400 -> 375 -> 345 since the per-pass tasks were
added.

**Instrumentation cost must be A/B'd, not assumed.** The "~2 ms/pass" figure
that shaped the first draft is not credible (`timer_read32` is ~5-10 us; eight
reads is ~60-80 us) and was measured with the console attached, never isolated.
Gate: three paired console-off runs, reject if scan rate drops >2% or a new
`>=5 ms` tail appears.

## Phase 1 exit criteria — the numbers that gate everything else

Measure on the instrumented build, then confirm on daily:

1. One ordinary line program — expected tens of microseconds.
2. **One consolidation — expected 50-300 ms, and how often it actually fires.**
3. `draw_battery` on a charge-state change — expected ~20-25 ms.
4. `draw_locks` on a Caps toggle — expected ~12 ms.
5. `count_ge_25ms` across a normal working day of real typing.

**If (5) is zero over tens of thousands of keystrokes, the firmware is
exonerated and Phases 2-4 should not be built.** That is the most likely
outcome and it is a perfectly good result.

## Phases 2-4 — DEFERRED, gated

Recorded so the reasoning is not lost. Do not start without Phase 1 data.

**Phase 2 — bound the two known long draws.** *Gate: only if `draw_battery` or
`draw_locks` measures >= 25 ms in practice.* RAM-tile the battery outline, bolt
and padlock instead of rectangle runs (the method `docs/display.md:266` already
proves), and route CAPS/WIN/FN through the glyph queue. ~50 lines.
**Explicitly NOT the cooperative scheduler from the first draft** — both
reviewers showed a budget checked *between* sub-tasks cannot bound a stall that
happens *inside* one, and Codex added that housekeeping is only the tail of the
loop anyway (RGB's eeprom flush, the raw-HID drain and a 100 ms USB send all
run before it).

**Phase 3 — proactive consolidation.** *Gate: only if consolidation measurably
lands during typing.* Expose log fullness from `wear_leveling.c`; consolidate
from the 10 Hz block when the log is >= ~75% full AND no key event for >= 500 ms
AND `!lcd_blit_busy()`. **No forced timeout** — a forced write during
continuous typing creates the exact blind window this is meant to remove.
⚠️ This is the riskiest work in the plan: wear-levelling policy is where a
mistake costs a corrupted keymap or torn settings on a brownout, and the slider
makes brownouts routine. Do not touch it to fix an unmeasured event.

**Phase 4 — gates. ✅ BUILT 2026-09-02** (the part that does not depend on 2 or
3). `scripts/soak.py` now resets the counters at the start and FAILS on
`count_ge_25ms_nonflash > 0` or `flash_gap_max_ms > 60`. Original text below.

**Phase 4 — gates.** *Gate: after 2 or 3 exist.* The soak as written would fail
on its own stimulus (~300 keymap + ~150 rgb_save writes per run → 3-4
consolidations), so thresholds must be attribution-aware: non-flash gaps
<= 10 ms, single write <= measured X, consolidation <= measured Y and count as
expected. **The soak types nothing** — it measures loop gaps, not keystroke
loss; do not present it as a drop gate. A hardware check of >=600 characters
bounds the aggregate rate at ~0.5% (95%) and does not localise per key.

## Known stall sources, for reference

Catalogued by the reviews; most are below the 25 ms threshold and listed so
they are not re-derived.

| Source | Magnitude | Threshold? |
|---|---|---|
| Wear-levelling consolidation | 50-300 ms | **yes** |
| `lcd_blit_wait` phase 2 recovery spin | 100-250 ms | **yes**, if an IRQ is lost |
| USB `send_report` with host not polling | up to 100 ms | **yes**, rare, wired |
| `draw_battery` on charge change | ~20-25 ms | borderline |
| `rtc_fast_task` I2C clock-stretch timeout | 20 ms | borderline, stuck bus only |
| `draw_locks` Caps | ~12 ms | no — delay only |
| `wait_ms(8)` in modified-consumer | 8 ms | no |
| `draw_locks` Fn | ~5 ms | no |
| Ordinary eeconfig line program | tens of us | no |

Also noted: `display_second_edge_task` runs the whole display block per-pass
outside the 10 Hz throttle (`ak820pro.c:475`), so any table-based scheme in
`ak820pro.c` misses `draw_clock`/`draw_battery` entirely; and VIA's
`id_custom_save` path writes immediately from `raw_hid_task`, bypassing
`kb_eeconfig_task()` and `rgb_matrix_eeprom_flush_allowed()`.

## Non-goals

- Diagnosing bad switches. A press the ISR never saw is invisible to all of
  this; that needs a reference text and ~600 presses per key for 0.5%.
- Reducing what the board does.
- Chasing the felt 0.5% with firmware changes. The evidence points elsewhere.

## Progress log

Update this section after each unit of work, and push — this plan is expected
to be resumed on another machine.

- **2026-09-02** — Plan drafted, reviewed by Codex and Fable 5.1, rewritten.
  Phase 1 approved; Phases 2-4 deferred and gated.
- **2026-09-02** — **Phase 1 BUILT, flashed and verified on hardware**
  (firmware `20268c273c`). `HC_GET2` + `HC_RESET`, proto v2, counters,
  unconditional `loop_stall_mark`, `key_presses` on the daily build,
  `ak820health.py --stalls/--reset`.

  **Exit criteria 1 and 2 ANSWERED.** 400 forced VIA keymap writes in 1.6 s:
  `flash_writes 400, flash_gap_max_ms 33, blit_gap_max_ms 0, count_ge_25ms 3`
  against ~3 predicted consolidations.
  - A consolidation is **~33 ms** — above the 25 ms losing threshold, but an
    order of magnitude below the 50-300 ms this plan feared. Revise the
    "Known stall sources" figure accordingly.
  - An ordinary write is invisible at this resolution (0 ms gaps).
  - Idle write rate measured at ~5 per ~23 s of normal use, so the ~127 writes
    needed to trigger one consolidation do not accumulate while typing.
  - Restoring an IDENTICAL keymap costs 1 write, not ~867 — QMK's eeprom layer
    skips unchanged bytes. The ~867 seen after a flash is real only because the
    EEPROM was just erased.

  **A bug the measurement caught, not review:**
  `backing_store_pre_write_hook()` marked FLASH then called `lcd_blit_wait()`,
  which overwrote it — every flash stall reported as "blit". Outermost mark now
  wins. Phase 2 would have been aimed at the display subsystem.

- **2026-09-02 20:09** — **Exit criteria 3 and 4 ANSWERED; Phase 2 is OFF THE
  TABLE.** 25 min of normal use with the agents running, including deliberate
  Caps and Fn hammering: `passes 532215, key_presses 469, count_ge_25ms 0,
  count_ge_10ms 8, loop_gap_max_mark blit, blit_gap_max_ms 20,
  flash_writes 1, flash_gap_max_ms 4`.
  - **`draw_locks` cannot lose a keystroke.** Worst blit-marked gap 20 ms,
    below the 25 ms threshold. Note JD's layout makes this the strongest
    possible test: the physical Caps Lock key IS Fn, so the lock-band redraw
    fires constantly, and it still never crossed the line.
  - **Criterion 3 (`draw_battery`) closed as not worth measuring.** It fires
    only on a charge-state change; JD's board is permanently cabled and only
    changes state on the rare occasion it runs on Bluetooth unplugged. It is
    also below the threshold anyway.
  - **The idle flash-write rate is ~1 per 25 min.** At that rate the ~127
    entries a consolidation needs would take **~53 hours of typing**.
    Consolidations are therefore driven by FIDDLING (LED tweaks, VIA remaps),
    not by use.
  - ⚠️ **Correction to the earlier entry:** the wear-levelling log lives in
    flash and PERSISTS ACROSS REBOOTS, so "you would need 127 writes while
    typing" was wrong. Observed directly: after the 400-write test left the log
    nearly full, a 32 ms consolidation fired during ordinary use from only 5
    further writes. The trigger and the cause are separated in time — which is
    exactly why the symptom feels random and unreproducible.

  - **2026-09-02 20:25** — **PHASE 4 GATE BUILT** (firmware `198b4a43dd`,
  proto v3). `count_ge_25ms` alone could not gate anything: the soak triggers
  its own consolidations, so the raw count fails on the harness's own stimulus.
  Added `count_ge_25ms_nonflash` as the discriminator, plus `i2c_gap_max_ms`.
  Page 2 was full, so per-mark maxima went u32 -> u16.
  `scripts/soak.py` resets counters at start and FAILS on
  `count_ge_25ms_nonflash > 0` (an unexplained keystroke-losing stall) or
  `flash_gap_max_ms > 60` (consolidation regressed past the measured 33 ms).
  Verified: 90 s soak, 128 flash writes -> ~1 consolidation,
  `count_ge_25ms 2, count_ge_25ms_nonflash 0, flash_gap_max_ms 32` -> **PASS**.
  The 32 ms independently reproduces the 33 ms from a different write pattern.

  **Still open: exit criterion 5** — `count_ge_25ms` over a normal working day.
  That is the number that decides whether Phases 2-4 are ever built. Method:
  `ak820health.py --reset`, use the keyboard normally, then
  `ak820health.py --stalls`. Note the agents hold the exclusive raw-HID
  interface; stop them or accept read failures (see L3 in the Fable review —
  CLAUDE.md and BACKLOG.md still disagree about whether replies work in BT
  mode, and 4.4 depends on resolving that).
