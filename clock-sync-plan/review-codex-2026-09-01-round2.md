# Codex review round 2 — 2026-09-01

Second adversarial pass by Codex CLI 0.151.0 (`codex exec`, read-only
sandbox) over PLAN.md draft 2. Part A re-judged all 27 round-1 findings
(21 resolved, 6 partial); Part B raised 14 new findings. **All 14 accepted**
and folded into draft 3 the same day; the 6 partials are closed by the
same edits (mapping below).

| B# | Sev | Disposition in draft 3 |
|---|---|---|
| 1 | Critical | Phase 1 ships a minimal deferred single-write PCF path in `rtc_fast_task()` (bus-idle gated); the synchronous handler write is gone from Phase 1 onward. Closes A#2. |
| 2 | High | Slew specified as THREE reload writes when `r ≠ 0`; event-by-event test cases listed. Closes A#16. |
| 3 | High | R3 gains a range rule: if `L ≥ target/2` compensation is abandoned, the nominal value written, the window and any in-flight operation marked late; every compensated value range-checked before the LLD call. |
| 4 | High | SOF bias is no longer inferred from offset residuals. The board exposes a running valid-frame counter; the host computes `b_ppm` from frames vs its own wall clock over ≥ 10 min, keyed by USB controller, and sends it in `0x03`. Sign defined algebraically. Closes A#21. |
| 5 | High | `rtc_now()` returns `false`/STALE with no timestamp after exhausted retries; callers postpone. Closes A#4. |
| 6 | High | SET lead is an empirically calibrated `lead_ms` (payload encoded after the timestamp; residual of 20 trials corrects the lead), not a generic RTT/2. Closes A#14. |
| 7 | High | State machine gains consecutive-success/failure counters, a `NONE` probe cadence, explicit entry/exit actions, and cancellation of pending `P_target`. Closes A#17. |
| 8 | High | PCF state machine split into six single-transaction states; deadline revalidated immediately before the release write. |
| 9 | Medium | §3.9 no longer moves the repaint: on an RTC edge the per-iteration task triggers one extra pass of the existing, fully gated `display_housekeeping_task()`. |
| 10 | Medium | Boot edge timestamp = midpoint of the bracketing reads, half-width as uncertainty. |
| 11 | Medium | `volatile` mirror, sampled once before touching `SN_USB`; `fn_last` invalidated on every false transition. |
| 12 | Medium | Phase 2 BT evidence redefined: send-attempt log only, plus instrumented console (if T0.9 passes) or the on-LCD snapshot as prerequisite. Closes A#24. |
| 13 | Medium | Phase 0 states that `HC_RTCTEST` mutates the RTC deliberately, restores state, and the baseline gate runs before and after. |
| 14 | Low | Version byte at `[11]` in BOTH replies; host requires exact version 2 and refuses unknown values. |

A#5 (multi-second delayed callback aliasing through 11-bit `FRMNO`) is
**acknowledged as a residual limitation** in draft 3 §7: `SECCNT` resets at
every match, so a callback delayed ≥ 2 s cannot be detected from `L`. Such
a delay is outside the operating envelope (it would also starve UART2 and
USB); the 10-minute host sync is the backstop.

## Verbatim round-2 output

## PART A — Round-1 dispositions

1. **RESOLVES** — `rtc_fast_task()` precedes the pump, skips while `lcd_blit_busy()`, and explicitly never invokes `rtc_bus_guard()` or `lcd_blit_wait()`.
2. **PARTIALLY resolves** — deferred Phase-3 traffic and the 20 ms fault bound are honest, but Phase 1 still performs the new `0x03` PCF write synchronously in the HID handler, contradicting R5 and the stated architecture ([PLAN.md:471](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:471)).
3. **RESOLVES** — normal slew reload is correctly `P_nom − d`.
4. **PARTIALLY resolves** — SECIF is checked, but the exhausted-retry fallback blindly returns `sec+1`; pending SECIF records no missed-event count, so this is not coherent after starvation lasting multiple periods ([PLAN.md:153](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:153)).
5. **PARTIALLY resolves** — USB state and `L` reject ordinary delays, but the claim that a multi-second delayed callback yields `SECCNT ≥ one period` is unsupported for a free-running/resetting counter and still needs T0.2/T0.3 hardware proof ([PLAN.md:251](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:251)).
6. **RESOLVES** — estimator accumulators and multiplication are explicitly 64-bit with a range check.
7. **RESOLVES** — the alternative is sound: all writes update the hardware and `RTCD1.period` together, while `P_nom` is separately owned and reported.
8. **RESOLVES** — a missed release restarts STOP/write/release and recomputes the calendar.
9. **RESOLVES** — release requires an idle bus, is timestamped around the actual operation, and restarts when late.
10. **RESOLVES** — full seven-byte calendar read plus seconds re-read provides rollover consistency; elapsed post-edge time compensates subsequent reads.
11. **RESOLVES** — coarse polling is reduced, delayed until after splash, DMA-aware, and tested using stall count and typing.
12. **RESOLVES** — byte 11 is an explicit nonzero protocol-version discriminator.
13. **RESOLVES** — `--no-wait` selects exactly one command using a wired capability cache.
14. **PARTIALLY resolves** — GET offset arithmetic is correct for `T3=T2`, but SET still assumes `rtt/2` is outbound delivery latency even though `hid_write()` only establishes host-side submission, not device receipt ([ak820ctl.c:76](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:76), [PLAN.md:353](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:353)).
15. **RESOLVES** — the proposed PCF control operations are read-modify-write and verify preservation of TEST bits.
16. **PARTIALLY resolves** — latency compensation is arithmetically sound for `L < target`, but a nonzero remainder requires three reload writes, contradicting the claimed two-write design, and no underflow guard is specified.
17. **PARTIALLY resolves** — states and window resets now exist, but `NONE` transitions and PCF failure ownership are underspecified, while “byte-for-byte” PCF fallback still uses the blocking legacy bus-guard path.
18. **RESOLVES** — `rtc_now()` snapshots the active period and the protocol separately exposes active and nominal periods.
19. **RESOLVES** — millisecond, flags, complete date, time, weekday, and minimum-year validation are required before mutation.
20. **RESOLVES** — legacy `0x01` semantics remain unchanged.
21. **PARTIALLY resolves** — learning is mandatory, but `offset_residual / elapsed` is not a valid isolated estimate of SOF bias and its sign convention is unspecified.
22. **RESOLVES** — the persistent agent detects enumeration, wake-like wall-clock gaps, and periodic deadlines.
23. **RESOLVES** — reboot phase and eight-hour holdover are separate tests, with the 58 ppm arithmetic corrected.
24. **PARTIALLY resolves** — T0.9 exists, but Phase 2 still claims BT-position “log lines” containing reply-only measurements even though replies are explicitly unavailable there ([PLAN.md:343](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:343), [PLAN.md:486](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:486)).
25. **RESOLVES** — instruments are explicitly implementation deliverables and precede their use.
26. **RESOLVES** — the persistence threshold is consistently 64.
27. **RESOLVES** — USB priority is no longer mischaracterized and FRMNO behavior is gated on T0.3.

## PART B — New adversarial findings

1. **Critical — the Phase-1 implementation directly violates R5 and C2.** R5 says all PCF traffic caused by HID is deferred ([PLAN.md:135](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:135)); Phase 1 explicitly performs the existing synchronous PCF write inside `0x03` ([PLAN.md:471](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:471)). That path calls `rtc_bus_guard()`, which may invoke `lcd_blit_wait()`, followed by a 20 ms I2C operation ([rtc.c:101](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:101), [rtc.c:161](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:161)). **Fix:** ship the minimal deferred one-write state machine in Phase 1, or force `skip_pcf` and defer all PCF persistence until Phase 3; qualify R4/R5 by phase only if the blocking path is deliberately retained.

2. **High — the advertised “two-write slew” cannot implement its own remainder algorithm.** A nonzero `r` needs: start `P_nom-d`, last-interval `P_nom-d-r`, then restore `P_nom`—three reload writes. Applying `r` on the same tick as restoration cannot affect the interval that just ended ([PLAN.md:203](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:203)). **Fix:** specify three writes when `r != 0`, or distribute the remainder by choosing `|r|` intervals at `d±1`; add exact event-by-event tests for `N=1`, positive/negative offsets, and every remainder sign.

3. **High — R3 lacks a mandatory underflow/range rule.** `target − L` is correct only when `L ≤ target`; unsigned subtraction otherwise wraps and `rtc_lld_set_period()` silently clamps it to the 20-bit maximum, producing an approximately 31-second interval at 33.6 kHz ([PLAN.md:126](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:126), [hal_rtc_lld.c:267](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC/hal_rtc_lld.c:267)). **Fix:** if `L >= target`, abandon compensation, mark the operation/window late, and schedule a safe nominal reload; range-check every compensated target before calling the LLD.

4. **High — the SOF-bias learner does not identify SOF bias.** `offset_residual / seconds_since_last_sync` mixes ILRC tracking error, previous slew/step residual, host-set asymmetry, estimator transients, temperature drift, and SOF error. The sign used by `P_target = f_ilrc·(1+sof_bias)-1` is also undefined ([PLAN.md:263](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:263), [PLAN.md:273](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:273)). An EMA merely smooths this confounding; it does not remove it. **Fix:** estimate SOF period directly from host elapsed monotonic time versus accumulated FRMNO frames over a wired interval, define the sign algebraically, persist controller identity with the estimate, and invalidate it after hub/controller changes.

5. **High — `rtc_now()` invents time after exhausted retries.** The ISR clears SECIF before incrementing software time ([hal_rtc_lld.c:115](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC/hal_rtc_lld.c:115)); SECIF is a flag, not a count of elapsed matches. After prolonged masking, `sec+1` cannot establish whether one or several periods elapsed ([PLAN.md:153](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:153)). Returning it can corrupt phase setting, PCF deadlines, and host diagnostics. **Fix:** return `false`/STALE without a usable timestamp; callers must postpone corrective actions. If recovery is required, re-anchor from host or PCF.

6. **High — SET delivery compensation uses an unproven timestamp and the wrong latency model.** The GET formula with a single board timestamp is correct under the stated symmetry assumption, but `hid_write()` returning does not mean the report reached `raw_hid_receive()`; the current utility treats it only as a host write result ([ak820ctl.c:72](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:72)). Moreover, a payload cannot literally contain a timestamp sampled “immediately before `hid_write`” unless it is encoded after that sample, adding another unbounded interval ([PLAN.md:359](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:359)). **Fix:** include a host sequence/timestamp and have the board reply with its receive timestamp, calibrate one-way SET delay separately, or set to `clock_gettime()` captured immediately before payload encoding plus a measured encode/write-to-receive lead—not generic RTT/2.

7. **High — the reference-state machine does not define actual failure transitions.** `PCF_LEGACY` invokes `rtc_clock_discipline()` only at its long check interval, yet `NONE` depends on detecting I2C failure/VL; no failure count, timeout, success threshold, or transition action is defined. “Either reference appears” likewise gives no PCF probing rule while in `NONE` ([PLAN.md:227](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:227)). **Fix:** define consecutive-success/failure counters, probe cadence, entry/exit actions, cancellation of pending `P_target`, and which task owns those probes.

8. **High — the PCF state-machine transaction count and atomic-step claim are false.** `STOP_SET` is a read plus write; `RELEASE` is another read plus write. With `TIME_WRITE` and `VERIFY`, a successful run uses six transactions, not at most five, and each table “step” is not one transaction ([PLAN.md:289](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:289)). If the bus becomes busy between either read/write pair, the saved control byte and deadline age across passes. **Fix:** split these into explicit `STOP_READ`, `STOP_WRITE`, `RELEASE_READ`, and `RELEASE_WRITE` states; revalidate deadline immediately before the release write; state a six-transaction minimum and unbounded retries with bounded per-pass work.

9. **Medium — the display edge task is not safe as described.** The current clock latch is reached only after `display_housekeeping_task_user()`, pause/splash checks, and—critically—`gq_pending()==false` ([display.c:1605](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1605)). Moving “exactly the work” into an unconditional per-iteration task before the pump can append or reset queue state while an earlier repaint is still draining; the queue is fixed-size and silently drops pushes when full ([display.c:1395](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1395)). **Fix:** preserve all existing gates, do not advance `last_shown_sec` until repaint was successfully queued, and leave playback/battery ownership in the 10 Hz task unless independently proven safe. Test an RTC edge during a full text/playback repaint.

10. **Medium — the boot edge timestamp is biased to the detecting poll.** The PCF edge occurred somewhere between the previous and current 10 ms reads, but Draft 2 treats the current “edge pass” as the edge instant ([PLAN.md:310](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:310)). The stated “±10 ms” hides a systematic 0–10 ms lateness and the fine path repeats the same mistake at main-loop granularity. **Fix:** timestamp both bracketing reads and use their midpoint, with half-width as uncertainty; add the measured full-read/re-read delay afterward.

11. **Medium — `usb_active_flag` is only conditionally correct and the plan omits the concurrency contract.** `usbGetDriverStateI()` is explicitly an I-class macro ([hal_usb.h:389](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/hal/include/hal_usb.h:389)), so calling it under `chSysLock()` in thread context is valid. But the ISR-read mirror must be `volatile` or accessed atomically, and state must be sampled before any possibly unsafe `FRMNO` read; “plain byte” does not establish compiler visibility ([PLAN.md:256](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:256)). **Fix:** declare the mirror `volatile uint8_t`, update it under the lock, have the callback read it once before touching `SN_USB`, and invalidate `fn_last` on every false transition.

12. **Medium — Phase 2’s BT acceptance evidence cannot exist.** The plan acknowledges that BT-position health and GET replies do not return over USB ([PLAN.md:343](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:343)), yet requires 10-minute BT “log lines” as evidence ([PLAN.md:486](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:486)). `--no-wait` yields no before/after, bias, state, or flags. **Fix:** log only send attempts during the BT run, then use an on-device retained snapshot/on-LCD diagnostics or a no-reboot transport to collect interval evidence; an end read after a reboot validates only final phase.

13. **Medium — Phase 0 is not actually behavior-neutral or independently verifiable.** It adds `rtc_now()`/extended GET before T0.6 validates coherent reads, and `HC_RTCTEST` performs reload writes needed to validate R1/R3 assumptions. Yet the gate says baseline unchanged because Phase 0 “adds only reads” ([PLAN.md:426](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:426), [PLAN.md:462](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:462)). **Fix:** state that tests cause deliberate transient RTC mutations, isolate them behind explicit commands, restore prior period/phase afterward, and run the baseline gate before and after test invocation separately.

14. **Low — protocol validation is asymmetric and the version marker is too weakly specified.** The layout fits within 32 bytes, but the host falls back on any byte-11 zero without first requiring `[3]==ok`, while “nonzero means new firmware” permits accidental future/garbage values. `0x03` also uses version at a different offset ([PLAN.md:337](/Users/jdlien/code/ak820-pro/clock-sync-plan/PLAN.md:337)). **Fix:** require valid framing, success, and exactly supported version values; reject unknown versions explicitly and centralize a fixed capability offset or magic/version pair.

## Checked and correct

- R3’s core arithmetic is correct when `0 ≤ L < target`: because the write resets the counter, `L + (target−L+1) = target+1` cycles.
- No new fast-task path in Draft 2 calls `rtc_bus_guard()` or `lcd_blit_wait()`; the remaining violation is the explicitly synchronous Phase-1 HID path.
- `usbGetDriverStateI()` under a short system lock is a legitimate I-class API use.
- The GET protocol fields occupy bytes 0–27 and fit in a 32-byte report; both period values fit in 16 bits under the 28,000–40,000 clamp.
- The NTP offset expression with a single board timestamp (`T3=T2`) reduces correctly to `B − (t_send+t_recv)/2`.
- Read-modify-write of PCF Control_status_1 preserves unrelated bits in principle.
- The 64-bit estimator multiplication avoids the round-1 overflow.
