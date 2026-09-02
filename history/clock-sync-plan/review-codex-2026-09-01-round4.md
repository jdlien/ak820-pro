# Codex review round 4 — 2026-09-01

Fourth pass (final verification) by Codex CLI 0.151.0 over PLAN.md
draft 4. Part A: of round 3's 8 findings, 5 resolved, 3 partial. Part B:
3 findings (1 High, 2 Medium). Verdict: "1 remaining High item; 0
Critical." The lead-estimator algebra was independently re-derived and
confirmed correct (negative feedback, geometric convergence on the true
outbound delay). **All 3 accepted** and folded into draft 5 the same day:

| B# | Sev | Disposition in draft 5 |
|---|---|---|
| 1 | High | `GET[27]` now carries the **full 8-bit** `sof_epoch` (`pcf_release_err_ms` moves to `HC_RTC` page 2 only; flags b5..b7 back to reserved). Host requires an identical epoch byte at both ends and restarts on any change or controller-ID change. |
| 2 | Medium | Fault matrix expanded: per post-STOP state, (a) one transient failure ⇒ plain retry, no `RECOVER_STOP`; (b) five consecutive ⇒ `RECOVER_STOP` + STOP cleared; (c) abort/new-queue while `stop_asserted` ⇒ recovery before restart. |
| 3 | Medium | Code map no longer says "kept verbatim": estimator equations and cadence retained, the direct mid-second reload call removed, application via tick-applied `P_target`. |

## Verbatim round-4 output

## PART A

B1 — **RESOLVED** — Steady/slew reloads use `[14000,80000]`; deliberate first periods use `[500,0xFFFFF]`. The `MIN_FIRST_MS` branch keeps every `ms=0..999` representable at both stated `P_nom` extrema.

B2 — **RESOLVED** — With `o = B − H`, `target = H_enc + lead`, and `board_at_receipt = H_enc + delay + o`:

`o′ = lead − delay − o`, hence `e = o′ + o = lead − delay`.

The update is negative feedback:

`lead_next = lead − (lead − delay)/4 = ¾lead + ¼delay`

so it converges geometrically on `delay`. Excluding stale/slewing samples and clamping to `[0,10] ms` are appropriate.

B3 — **PARTIAL** — `stop_asserted` and `RECOVER_STOP` make the intended recovery algorithm sound, but the verification is internally inconsistent: the fault test kills each transaction only once, while recovery is entered after at least five failures. A one-shot failure merely retries successfully and cannot demonstrate `RECOVER_STOP`. Fix the test matrix to inject five consecutive failures and explicit abort/new-queue events after every post-STOP state.

B4 — **PARTIAL** — The continuous counter and epoch rule fix ordinary rejected intervals, but only `sof_epoch mod 8` is exposed. Eight continuity breaks between host observations produce an apparently unchanged epoch, allowing a corrupted interval to be accepted. The `<24 h` rule protects counter wrap, not epoch aliasing. Expose the full `uint8_t sof_epoch`—or a wider continuity generation—and compare that exact value.

B5 — **PARTIAL** — The state-machine and Phase 1 text correctly preserve only the estimator arithmetic and reroute application through `P_target`, but the code map still says `rtc_clock_discipline()` is “kept verbatim.” That contradicts the required removal of its direct mid-second `rtc_lld_set_period()` call. Replace that phrase with “estimator arithmetic retained; proposal/application path rewritten.”

B6 — **RESOLVED** — `pcf_avail_fail` now has precise event, reset, saturation, ownership, and visibility semantics; SOF exit and NONE recovery are defined.

B7 — **RESOLVED** — The common representable range is restricted to 2026–2098, the post-increment timestamp is revalidated, and conversion failures reject before writes.

B8 — **RESOLVED** — Phase 2 now uses a 30-second wired sampler plus logged data bounding between-sample excursion; wireless evidence is explicitly characterized as weaker and does not pretend the final rebooting read proves continuous phase.

## PART B

1. **High — three-bit `sof_epoch` can alias valid after eight continuity failures.** The board maintains a full `uint8_t`, but GET exposes only flags b5–b7. Eight breaks between sampled replies leave the exposed epoch unchanged even though `sof_frames_total` no longer represents uninterrupted elapsed frames. A false bias within the accepted ±600 ppm range can then discipline the RTC incorrectly. **Fix:** expose and compare the complete epoch or a wider generation counter; restart measurement on any generation change or controller/reset identity change.

2. **Medium — STOP fault verification cannot exercise its claimed recovery path.** A single killed transaction does not meet the specified `≥5 attempts` transition. **Fix:** test one transient failure separately, then five consecutive failures and every abort/replacement path while `stop_asserted`; assert STOP-clear recovery after each.

3. **Medium — the code map still promises a verbatim legacy function that Phase 1 must modify.** This leaves implementation ownership ambiguous. **Fix:** state explicitly that only its estimator equations and cadence remain unchanged; direct reload application becomes a queued `P_target`.

**VERDICT: 1 remaining High item; 0 Critical.**

Checked and correct:

- Lead-estimator signs and negative-feedback update.
- Split first-period versus steady/slew reload ranges.
- Slew register arithmetic and remainder handling.
- Full year/post-increment validation.
- Deferred Phase 1 PCF write.
- STOP recovery design itself.
- `pcf_avail_fail` semantics.
- Thirty-second Phase 2 wired evidence design.