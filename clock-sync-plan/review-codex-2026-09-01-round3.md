# Codex review round 3 — 2026-09-01

Third adversarial pass by Codex CLI 0.151.0 over PLAN.md draft 3.
Part A: of round 2's items, 14 resolved, 6 partial, 2 not resolved.
Part B: 8 new findings (5 High, 3 Medium). Verdict: "5 remaining High
items; 0 Critical." **All 8 accepted** and folded into draft 4 the same
day (the two NOT-RESOLVED items, both about the lead-calibration algebra,
are fixed with the reviewer's own corrected estimator).

| B# | Sev | Disposition in draft 4 |
|---|---|---|
| 1 | High | Reload range split: steady/slew values in [14000, 80000]; deliberate first periods in [500, 0xFFFFF]; model test covers every ms 0..999 at P_nom extrema. |
| 2 | High | Lead calibration replaced with the reviewer's estimator: with o = B−H and o′ = target − board_at_receipt, e = o′ + o = lead − delay; lead −= e/4, clamped [0, 10] ms; stale/slewing samples excluded. Closes A14/B6-round2. |
| 3 | High | `stop_asserted` + `RECOVER_STOP`: STOP can never be left asserted; NONE/back-off unreachable while it is; "PCF possibly stopped" health flag; per-state fault-injection test. |
| 4 | High | `sof_frames_total` made continuous (counts every delta while continuity holds); `sof_epoch` (flags b5..b7) increments on any continuity break; host uses an interval only with an unchanged epoch and < 24 h; F = (u32)(end − start). |
| 5 | High | `PCF_LEGACY` no longer described as byte-for-byte: estimator arithmetic unchanged, result re-routed through the tick-applied P_target path (this IS Phase 1's "no phase loss on trim"); span invalidated on external reloads. |
| 6 | Medium | `pcf_avail_fail` defined (consecutive failed reads across trim/probes/acquisition, reset on any successful read, saturating); SOF exit goes to PCF_LEGACY unconditionally; the write machine feeds the counter only via its read steps. |
| 7 | Medium | Year range 2026..2098; the +1 branch validated after increment; mktime failure rejects. |
| 8 | Medium | Phase 2 wired evidence is a 30 s-cadence sampler over 24 h, not the 10-min log; wireless evidence explicitly weaker (send-only + console/on-LCD). |

## Verbatim round-3 output

## PART A — Round-2 dispositions

B1 — **RESOLVED** — Phase 1 now defers the PCF write through the bus-idle-gated fast task.

B2 — **RESOLVED** — The schedule now has three writes when `r != 0`, including the final restore, with appropriate sequence tests.

B3 — **PARTIAL** — Underflow is avoided, but the universal `[14000,80000]` rule rejects valid short first periods produced by phase setting.

B4 — **PARTIAL** — The bias equation and sign are correct, but `sof_frames_total` counts only accepted samples, so rejected intervals corrupt `F/H`; wrap handling is unspecified.

B5 — **RESOLVED** — Exhausted coherent-read retries return no timestamp and callers defer.

B6 — **NOT RESOLVED** — The replacement lead-calibration equation has inconsistent offset signs and positive feedback; it does not converge to outbound delay.

B7 — **PARTIAL** — The table adds counters, probes, and transition actions, but contradicts the promised unchanged fallback and does not fully define counter resets/readability ownership.

B8 — **PARTIAL** — Six transactions and the pre-release deadline check are now explicit, but failure/abort recovery can leave PCF STOP asserted indefinitely.

B9 — **RESOLVED** — The original display gates and latch remain intact; the edge path invokes at most one extra pass per RTC second, not every main-loop pass.

B10 — **RESOLVED** — Both bracketing reads are timestamped and their midpoint and half-width are used.

B11 — **RESOLVED** — The USB-active mirror is volatile, sampled once, and checked before `FRMNO`; `fn_last` is invalidated.

B12 — **RESOLVED** — Wireless evidence is limited to send attempts plus contemporaneous console/on-device evidence and a final wired phase read.

B13 — **RESOLVED** — Phase 0 explicitly identifies the mutating tests, restores state, and runs baseline gates separately.

B14 — **RESOLVED** — Both replies use exact version 2 at byte 11; zero alone selects legacy and unknown versions are refused.

A2 — **RESOLVED** — The Phase-1 HID-triggered PCF write is deferred.

A4 — **RESOLVED** — No timestamp is invented while `SECIF` ambiguity remains.

A5 — **PARTIAL** — The ≥2-second/2048-ms alias remains technically unresolved; §7.5 now acknowledges and bounds it instead of claiming detection.

A14 — **NOT RESOLVED** — SET delivery is no longer assumed to equal RTT/2, but the proposed calibration estimator is mathematically wrong.

A16 — **RESOLVED** — Three-write remainder handling and latency-compensated ISR reloads are specified and estimation is invalidated around writes.

A17 — **PARTIAL** — A state table exists, but “unchanged byte-for-byte” PCF fallback still conflicts with tick-owned, phase-preserving reload application.

A21 — **PARTIAL** — Direct host/SOF comparison replaces residual inference, but its counter does not represent all elapsed frames reliably.

A24 — **RESOLVED** — The BT gate no longer claims reply-derived measurements after the rebooting slider flip.

## PART B — New findings

1. **High — the global reload range makes ordinary phase sets impossible.** The plan requires every LLD value to be at least 14,000 ([PLAN.md:123](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:123)), while phase setting writes `first - 1`, where `first=(P_nom+1)R/1000` ([PLAN.md:174](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:174)). At `P_nom≈33,600`, any unbranched `R` below about 417 ms produces a value below 14,000. In particular, `R=20 ms` produces about 671, so roughly 40% of valid millisecond phases fail. **Fix:** distinguish nominal/slew bounds from deliberate first-period bounds. Validate first periods against the hardware’s actual safe range, including `first >= 1`, and separately test every `ms=0..999` at nominal extrema.

2. **High — the lead calibration has the wrong sign and mixes opposite offset conventions.** GET defines `o = board − host` ([PLAN.md:381](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:381)), while firmware `offset_before` is `payload target − board`. They cannot be subtracted as two observations of the same quantity. Even if both were redefined as `true − board`, excessive lead makes `o'−o` positive, and `lead += error/2` increases the excessive lead: positive feedback. A large first-sync step does not repair that algebra. **Fix:** define all signs explicitly. With GET offset `o=B−H`, the delivery residual is approximately `e=o'+o=lead−delay`; update `lead -= αe`. Better, return a receive timestamp/sequence and fit outbound delay directly. Exclude stepped/slewing or stale samples and clamp plausible lead values.

3. **High — PCF transaction failure can permanently stop the battery-backed clock.** After `STOP_WRITE`, failures in `TIME_WRITE`, either release state, or verification have no defined cleanup transition ([PLAN.md:303](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:303)). Three failures can drive the reference state to `NONE` while STOP remains set. Backoff then preserves a frozen PCF, defeating boot reference and holdover. **Fix:** track whether STOP was successfully asserted; on abort/backoff, enter a dedicated recovery path that clears STOP using the preserved control bits. Do not enter `NONE` until recovery succeeds or a distinct “PCF possibly stopped” fatal health state is exposed. Test failure injection after every transaction.

4. **High — the host SOF-bias measurement is not measuring elapsed frames.** `sof_frames_total` advances only inside `if (ok)` ([PLAN.md:248](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:248)), but the host divides its change by uninterrupted host elapsed time. One omitted one-second delta during a 600-second observation biases the estimate by about −1667 ppm—larger than both the USB tolerance and the protocol’s accepted ±600 ppm range. Counter wrap is merely noted, not defined; a 32-bit 1-kHz counter wraps in about 49.7 days. **Fix:** maintain a separate continuous SOF-frame counter whenever USB continuity is established, independent of estimator-window acceptance, or expose validity epochs and make the host restart on any gap. Specify `F=(u32)(end-start)`, reject intervals spanning reset/controller change, and limit the interval to less than one wrap.

5. **High — “unchanged” PCF fallback still destroys phase and violates reload ownership.** The current `rtc_clock_discipline()` directly calls `rtc_lld_set_period()` from the main loop ([rtc.c:336](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:336)), which resets `SECCNT`. Draft 3 simultaneously says it remains byte-for-byte unchanged, every proposal is applied at the next tick, and Phase 1 has “no phase loss” ([PLAN.md:238](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:238), [PLAN.md:241](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:241), [PLAN.md:501](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:501)). Those claims cannot all hold. **Fix:** preserve the legacy estimator arithmetic, but turn its result into a queued `P_target` applied by the callback under R3; invalidate its span after every external reload. Stop describing the whole function as unchanged.

6. **Medium — PCF “consecutive failure” semantics remain incomplete.** The plan does not state which successful operation resets the failure counter, whether failures from host persistence and reference probes share it, or how `SOF` determines “PCF is readable” without performing a probe. **Fix:** define separate availability and operation counters, reset rules, saturation, probe ownership, and exact transition actions for every success/failure event.

7. **Medium — protocol validation misses representability after calendar advancement.** Input validation permits years beyond the PCF’s 2000–2099 representation and does not validate `t+1` used by the short-first-period branch. `2099-12-31 23:59:59.999` can advance to 2100, while the existing PCF write stores only `year % 100`. **Fix:** restrict accepted and derived timestamps to the common SN32/PCF range, validate after every `+1`, and test year/month/day rollover and `time_t` conversion failure.

8. **Medium — Phase 2 does not measure its “at every time” requirement.** Ten-minute wired samples prove only the sampled instants; wireless evidence contains no phase measurements during the run, and the sole final read occurs after a reboot ([PLAN.md:523](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:523)). Neither establishes the stated between-sync bound. **Fix:** sample wired phase substantially faster than the claimed maximum excursion or derive a conservative bound from logged frequency/error; add a non-rebooting on-device phase/error record for wireless operation.

VERDICT: 5 remaining High items; 0 Critical.

Checked and correct:

- The three-write slew arithmetic is correct for both signs and nonzero remainder.
- `b = F/(1000H)−1` and `f_true=f_est(1+b)` have the correct algebraic sign when `F` is complete.
- `[3..9]` is exactly the existing seven-byte calendar payload; `[10..11]` for milliseconds does not overlap it in a 32-byte report.
- The display edge check performs one extra fully gated housekeeping call per RTC second. Text expiry, connection state, lock state, playback tick, and `last_shown_sec` remain guarded; it is not a 400 Hz execution path.
- The midpoint bracketing rule removes detecting-poll bias.
- The successful PCF path now contains exactly six single-transaction states, with the release deadline checked after the bus-idle gate and immediately before the write.