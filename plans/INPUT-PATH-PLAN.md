# Input path: what still loses a keystroke, and what to do about it

Status: **DRAFT FOR AUDIT, 2026-09-03.** One change already landed and is
awaiting real-world validation (§1). Everything else is proposed, not built.
Companion: `LOOP-BUDGET-PLAN.md` (stall measurement, phase 1 + gate built).

## Established by measurement, not assumption

1. **The matrix is scanned in the ROW ISR**, not the main loop —
   `shared_matrix_scan_keys` (`drivers/led/sn32f2xx.c:385`) latches into
   `shared_matrix` and the loop consumes it via `matrix_scan_custom:856`
   behind the `matrix_scanned` gate.
2. **The ISR will not re-scan until the loop consumes the latch.** So a
   main-loop stall freezes input capture for its whole duration.
3. **Scan rate == main-loop rate** — measured ratio 0.997 (7549 passes / 20.4 s
   vs `scan_rate` 372). Per-pass work costs scan rate 1:1.
4. **Only stalls >= ~25 ms can LOSE a press.** Contact lasts 25-80 ms; anything
   shorter ends with the key still down and merely delays it.
5. **`count_ge_25ms_nonflash` is 0** across normal typing (25 min, 469 key
   presses, 532k passes). Unexplained stalls are not happening in practice.
6. **Wear-levelling consolidation is 33 ms** — above threshold, but needs ~127
   flash writes to fire and the idle write rate is ~1 per 25 min.

## §1 — The bug that was actually losing keystrokes (LANDED, unvalidated)

`sym_defer_g`, QMK's default, **silently swallows short presses**:

```c
if (changed)                      debouncing_time = now;      /* ANY key */
else if (elapsed >= DEBOUNCE)     if (memcmp(cooked, raw))    /* FINAL state */
```

The timer is **global** and the commit compares **final state**. A key that goes
down and back up before the whole matrix is quiet for `DEBOUNCE` (5 ms) leaves
`raw == cooked`, `memcmp` finds nothing, and the press is discarded. It never
becomes an event, so nothing downstream sees it — including `health.c`'s
`key_presses`, which lives in `process_record_kb`, AFTER debounce. **That is why
every counter read clean while characters went missing.**

Fast typing makes it worse: during a burst the matrix is rarely quiet for 5 ms,
so commits are deferred to the end of the burst and any key completing a full
cycle in between vanishes. This matches every property of the reported symptom —
intermittent, not key-specific, not reproducible on command, clean in slow
single-key tests, indistinguishable from mistyping.

It is also the transposition mechanism: batched commits are emitted by
`matrix_task` in `for row -> for col` order, not press order. `the` -> `teh`
falls straight out (h = r3c6, e = r2c3).

**Changed to `asym_eager_defer_pk`** — press reported immediately (short press
cannot be swallowed), key locked out `DEBOUNCE` ms afterwards (press chatter
still filtered), release deferred per key (release chatter still filtered), and
per-key rather than global (no batched commit, so ordering improves).

**Known trade:** eager-on-press trusts the first edge, so a worn switch changes
failure mode from a silent DROP to a visible DOUBLE. Given this owner has
replaced corroded switches before, that is a deliberate accepted risk — a
double is at least actionable.

**Validation still owed:** one dropped `v` observed in several pangram
repetitions post-change. Inconclusive. Needs days of normal use.

## §2 — What can STILL lose a keystroke after §1

§1 fixed the debounce swallow. It does **not** fix the stall swallow: because
the ISR will not re-scan until the loop consumes the latch (fact 2), a press and
release occurring entirely inside a main-loop stall is still lost.

Remaining stall sources at or above the 25 ms threshold:

| Source | Magnitude | Frequency |
|---|---|---|
| `lcd_blit_wait` phase-2 recovery spin (`graphics/lcd_bus.c:649,691`) | 100-250 ms | only when a blit IRQ is lost |
| USB `send_report` with host not polling (`usb_main.c:393`) | up to 100 ms | rare, wired |
| Wear-levelling consolidation | 33 ms | ~every 127 flash writes |
| `rtc_fast_task` I2C clock-stretch timeout | 20 ms | stuck bus only |

All are rare. None was observed during normal typing. They are the residual
risk, not the current fault.

## §3 — Proposed, tiered by risk

### Tier 1 — bounded and independent (low risk)

- **T1.1 Keep the blit recovery spin off the input path.** A 100-250 ms wait is
  4-10x the losing threshold. Prefer "skip the blit and retry next pass" over
  "wait" wherever the caller runs on the main loop. Needs care: the wait exists
  to stop a flash write overlapping in-flight DMA, which is a documented
  board-wedging hazard.
- **T1.2 Do not block the loop on USB.** Key reports should queue rather than
  wait up to 100 ms for a host that is not polling.
- **T1.3 Cap `rtc_fast_task`'s I2C exposure** so a stuck bus cannot cost 20 ms
  of input capture.

### Tier 2 — the architectural change

Make input capture independent of main-loop timing. Two variants:

- **T2a (minimal): sticky press accumulator.** The ISR keeps scanning and ORs
  observed presses into a bitmap the loop consumes alongside current state. A
  press+release inside a stall then still yields a press followed by a release,
  instead of nothing. Much smaller than T2b, but synthesises events rather than
  recording them, and loses true ordering and timing.
- **T2b (full): timestamped edge queue.** ISR debounces per key and pushes
  `(row, col, pressed, time)` into a lock-free ring. `matrix_scan_custom`
  always reports no change; the loop drains the ring and calls
  `action_exec(MAKE_KEYEVENT(...))` directly. Stalls become pure latency, and
  ordering resolves to the ISR scan rate (~53 us) instead of the loop rate
  (~2.7 ms). Tap-hold and combos would get truer timestamps than today.
  Cost: reimplements what `matrix_task` does for free — ghosting checks,
  `switch_events`, wakeup keys, `should_process_keypress` — and RGB reactive
  effects still need matrix state maintained alongside. Estimate 300-500 lines,
  mostly in an already-forked core file.

### Tier 3 — deferred

- Splitting wear-levelling consolidation so it cannot block 33 ms. Highest risk
  in the codebase: a mistake costs a corrupted keymap or torn settings, and the
  mode slider makes brownouts routine. Do not start without evidence it lands
  during typing.

## Questions for the auditor

1. Is §1's diagnosis correct, and is `asym_eager_defer_pk` the right algorithm
   here, or is `sym_defer_pk` / a shorter `DEBOUNCE` a better trade given switch
   wear? Is the doubled-keypress risk understated?
2. Is T2a sound, or does synthesising a press+release pair from a sticky bitmap
   break QMK's key-event model — tap-hold, combos, key overrides, `TAPPING_TERM`
   behaviour, or the encoder map?
3. In T2b, what breaks by bypassing `matrix_task`? Enumerate what must be
   reimplemented, and whether QMK's action layer tolerates events arriving with
   timestamps that are not "now".
4. Is T1.1 safe, given the pre-write blit drain exists to prevent a documented
   board wedge? Is there a formulation that keeps the safety and drops the wait?
5. What else on the input path can lose or reorder a keystroke that this plan
   does not list? Consider ghosting/`has_ghost_in_row`, NKRO vs 6KRO report
   limits, the CH582F queue dropping reports when full
   (`ch582f_ajazz.c:532`), and encoder/consumer interactions.
6. Ranked: what is worth building, and what is not worth the regression risk on
   a daily-driver keyboard?
