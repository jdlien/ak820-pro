# Phases 1 and 2 — results (2026-09-01)

Both phases were built, flashed and verified on the same afternoon as
Phase 0, on the instrumented flavor, slider in the BT position with the
cable in throughout. They are committed together because Phase 2's ISR
scheduler subsumed Phase 1's restore path in the same functions; the plan's
"one commit per phase" rule was traded for one coherent commit with both
phases' evidence recorded here.

## Phase 1 — phase-correct set, no phase loss on trim, deferred PCF write, display edge

| Exit criterion (PLAN.md §5) | Measured | Pass |
|---|---|---|
| \|offset\| ≤ 3U across 10 syncs | ten consecutive `ak820ctl clock` runs: after-residuals **−0.2 … −3.1 ms**, U 1.1–3.4 ms each | **yes** |
| a trim moves phase < 1 ms | second trim (33489 → 33378, 14:28:03) caught at 1-s sampling: jump **−0.7 … −1.6 ms**, rms 0.5 ms — zero within resolution; the old code lost up to 1000 ms per trim | **yes** (at the method's ~1 ms resolution) |
| digits change within one main-loop pass of the tick | JD: "flipping okay, display reads just fine" — consistent flip timing; not filmed | **visual only** |
| deferred PCF path runs, never hangs | `pcf` write executed on every sync; `i2c_fail` 0; `deferred_passes` 0 (no blit was ever busy at the moment of a write — the path is exercised, the deferral branch is not yet) | **yes** |
| `stale_count` | 0 throughout, incl. under BT typing | **yes** |

Two things learned:

- **The sub-second fraction must be `1 − (active+1 − cnt)/(nominal+1)`**, not
  `cnt/(active+1)`. Inside the shortened first period after a set the
  active register is small, and the naive formula read a growing "after"
  residual (−76 → −790 ms across ten syncs) that was purely a host-side
  decoding error. Fixed in `ak820ctl`, `rtc_phase0.py`, and the firmware's
  own `offset_before`.
- **Latency compensation (R3) buys nothing for a write whose value is the
  new steady value** — the register must end up holding `P_nom`, so the
  interval containing the final write is long by exactly the ISR service
  latency `L` (0–7 cycles, ≤ 200 µs). Implemented as: transient slew
  writes compensated (exact), final restore uncompensated. Documented in
  `rtc.c`.

## Phase 2 — SOF frequency discipline, slew, host-supplied bias, agent

Console after the Phase 2 flash (fresh EEPROM, seed 33600 ≈ 7000 ppm slow):

```
14:36:37 [rtc] slew 204 ms: N=11 d=623 r=1
14:37:19 [rtc] sof window n=32 ms=32288 -> f=33281 target=33282 P 33600 -> 33441
14:37:51 [rtc] sof window n=32 ms=32161 -> f=33279 target=33280 P 33441 -> 33361
14:38:23 [rtc] sof window n=32 ms=32087 -> f=33274 target=33275 P 33361 -> 33318
14:38:55 [rtc] sof window n=32 ms=32046 -> f=33272 target=33273 P 33318 -> 33296
14:39:27 [rtc] sof window n=32 ms=32026 -> f=33270 target=33271 P 33296 -> 33284
14:39:59 [rtc] sof window n=32 ms=32011 -> f=33273 target=33274 P 33284 -> 33279
```

- `ref_state` = SOF from the first evaluation (three clean FRMNO seconds);
  `ref_transitions` 1; `window_rejects` 0.
- Drift **7000 ppm → −343 ppm in four minutes, → −240 ppm at seven
  minutes**, with the period still half-stepping by 1–2 cycles per window
  (1 cycle ≈ 30 ppm). Estimates fall 33281 → 33270 over the run: the ILRC
  warming after the reboot — the temperature wander the loop is for.
- FRMNO deltas after convergence: 1000/1001 per RTC second.
- Host sync during convergence: **before −745 ms → after −1.8 ms** (step,
  |offset| > 500 ms); the next sync **−3.8 ms → slewing** (N = 1).
- Bias +78 ppm sent by `ak820ctl` (from `~/.ak820ctl-cap`, measured in
  T0.8) and reported "in use" by the board.
- `ak820-timekeeper.py` installed as a LaunchAgent (replacing the 3-hourly
  `clocksync`): its first "enumerated" sync ran within 2 s of load.
- Locked drift, 5-minute sampler 13–18 min after boot: P_nom 33273 → 33270 → 33266 (128-sample windows), slope **−244 ppm over 4 min → −109 over 2 min → −66 ppm over the last minute** — the ILRC still warming; each locked window resolves ±8 ppm. Agent cadence set to 5 min so |offset| stays < 20 ms even at this residual.

Health after all of it (instrumented, ~25 min uptime, BT typing):
`loop_gap_max` unchanged, `blit_timeouts` 0, `stale_count` 0, `i2c_fail` 0,
ISR latency max 7 cycles, `lat_n` 465.

## Deviations from the plan, recorded

1. Phases 1 and 2 share one commit (above).
2. R3 compensation applies to transient writes only (above).
3. The Phase 2 exit's 24 h wired soak at 30-s cadence has not been run
   yet — the agent's 10-min log plus a follow-up sampler are the interim
   evidence. Schedule the soak overnight.
4. The persist threshold 32 → 64 applies to both the SOF estimator and the
   legacy trim.
5. The "no-wait" send-only path stays in `ak820ctl` but is unnecessary on
   this firmware: replies arrive in the BT position (Phase 0 F1).

## Constants now in the firmware

| | |
|---|---|
| `LATE_CYCLES` | 170 |
| `WIN_INITIAL` / `WIN_LOCKED` | 32 / 128 samples |
| `SLEW_MAX_MS` | 500 |
| slew rate | 2 % (20 ms/s) |
| `RTC_MIN_FIRST_MS` | 20 |
| first-period register range | 500 … 0xFFFFF |
| steady/slew register range | 14000 … 80000 |
| persist threshold | 64 ticks, ≥ 10 min uptime |
