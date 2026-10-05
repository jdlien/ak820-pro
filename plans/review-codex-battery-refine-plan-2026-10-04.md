# Codex review of BATTERY-GAUGE-REFINE-PLAN.md, round 1 (2026-10-04)

gpt-6-astra, reasoning xhigh, read-only, codex-cli 0.160.0. Verbatim. Dispositions: the plan's "Review dispositions".

1. **P1 — The flash sequence contradicts the measurement gate.** [The sequence](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:100) puts C’s write-rate fix and its new counters into flash 1, but [gate 3](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:400) requires the counters to identify the writer **before C2 is written**. B3 can also require a firmware correction, although flash 2 is described principally as the stall fix.

   **Change:** Make flash 1 the diagnostic/calibration build; measure C1, D and B3; put the resulting C2, D and B corrections into flash 2. Define which independent changes may accompany flash 1, and allow another iteration if verification fails. Two flashes should be an expectation, not a constraint that overrides the gates.

2. **P1 — A1 cannot derive the 19:29 plug-in duration from the cited entry.** [A1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:139) says its VDD gives the USB duration. The [last CSV entry](/Users/jdlien/code/ak820-pro/history/battery-2026-10-01-drain/log-20261003-1929.csv:284) is entirely battery operation: VDD 3901, charging 0, external 0, and no external flag. The [observation](/Users/jdlien/code/ak820-pro/history/battery-2026-10-01-drain/readings.csv:7) places the raw-HID response at 19:29:51, after that completed interval.

   **Change:** Model this plug-in as an event inside the unlogged gap, with an explicitly assumed duration and sensitivity range. Do not fabricate a VDD-derived measurement. At the initial unplug, use the recorded 11:00:00 boundary and clip the straddling interval; specify how that replaces, rather than duplicates, a VDD-based correction.

3. **P2 — The two estimators are not established as interchangeable, and the existing smoother is unsuitable unchanged.** [A1’s “both are unbiased” assertion](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:135) is unsupported: trimming changes the expectation for asymmetric distributions, including clipped or changing signals. The sources have different averaging windows and no simultaneous overlap establishing an offset. In addition, [the fitter](/Users/jdlien/code/ak820-pro/scripts/battery_fit.py:163) splits at gaps **greater than 15 minutes**, so ordinary 15-minute video samples with a few seconds’ timestamp jitter become separate segments. Its sample-count smoothing gives different time bandwidths to 10-minute and 15-minute data. [Knot interpolation](/Users/jdlien/code/ak820-pro/scripts/battery_fit.py:188) still crosses missing intervals after smoothing has been segmented.

   **Change:** Specify source-specific timestamps, a common time-based smoothing bandwidth, jitter tolerance, clamp censoring and source-boundary handling. Flag knots interpolated through the four-hour gap. Report sensitivity to estimator offsets and gap interpolation; do not claim an offset check was performed without paired evidence.

4. **P2 — Whole-run leave-one-out is useful, but the validation claims and gate overstate it.** The reported 216-point results are reproducible, including plateau RMS approximately 3.16 and worst error −8.50 points. However, [A2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:149) provides only two reciprocal holdouts from one pack. Adjacent points are correlated, and scoring the pooled curve on its two training runs is not independent validation. [Gate 1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:395) confuses those scores with the leave-one-out targets. [D4’s “accept ~±5”](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:422) is not supported by the observed −8.5.

   **Change:** Retain whole-run holdouts, label pooled scores as training diagnostics, and report each direction separately, with time-weighted and source-separated errors. Specify the exact inclusion rule that produces 216 points; the fitter’s existing mean-based clamp filter selects different points. Treat the targets as engineering acceptance thresholds, not confidence bounds. A third drain may be deferred, but replace “validates A” with a limited two-run consistency claim and report the actual plateau error.

5. **P1 — B treats an unobserved charging regime as a measured runtime model.** [B’s physical justification](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:197) is too strong. Constant **net cell current** gives approximately linear accumulated charge; this gauge represents remaining runtime/usable energy behind a buck-boost, which is a different quantity. The ASC4056 also has precharge, thermal/current reduction and input-headroom constraints; CHRG low does not establish constant current. Its regulated voltage is approximately 4.2 V, whereas this sensor saturates near 4.036 V. [ASC4056 datasheet](https://offer-product.oss-cn-beijing.aliyuncs.com/product/offer/attachment/2208542158341/file/subPdf_3447_9650_20210413-232932819.pdf)

   The observed VDD change with LED load also prevents treating a VDD rise as an unambiguous CV marker. Neither `F_CC = 0.75–0.85` nor converting the reserve’s runtime-energy estimate into “3% of charge” is measured here.

   **Change:** Describe B as an empirical, bounded display estimate for specified operating conditions. Establish the board’s power-sharing assumptions and qualify behavior for reduced-current USB supplies, varying load, thermal limiting and charges that never attain nominal CC. Outside validated conditions, retain an uncertain “Charge” state rather than advancing a supposedly physical percentage solely with elapsed time.

6. **P1 — B leaves essential state transitions and CV parameters unspecified.** [The proposed exponential](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:202) does not identify `τ` from a termination duration alone: `L_end`, `L_cv` and the finite-time target must also be fixed. An asymptote of 99 cannot reach exactly 99 in finite time. A partial charge can reach the sensor clamp almost immediately; a nearly full top-up need not resemble the five-hour clamp interval measured from flat. Rebooting loses elapsed phase history, and [saved levels](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:466) are sparse discharge milestones, not charging checkpoints.

   **Change:** Add an explicit transition table covering known/unknown start, qualified charging time, stale reports, CHRG interruptions, replug, clamp entry/exit, reboot and termination. Define caps, rounding, phase latching and parameter fitting numerically. Preserve the existing [just-full top-up behavior](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:556), which must not drop 100 to the charging cap. Require bounded, inexpensive firmware arithmetic.

7. **P1 — B3 does not measure `K_CC` as written.** [B3](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:250) calls 40–70% “below the plateau,” but the current table puts 60% at 3982 mV and 70% at 4006 mV—inside it. Charging can lift even a roughly 50% starting voltage into the sensor clamp. The following hour on battery consumes about **1.94 runtime points** at full white, which is omitted from `rise / 1 h`. Reading the displayed level also incorporates the ratchet and re-seat behavior being tested.

   **Change:** Choose starting level and charge duration so both settled endpoints lie in a well-resolved portion of the curve. Derive endpoints offline from raw voltage estimates under identical recorded load; compensate for discharge during settling. Record the relaxation trajectory at 0/5/15/30/60/120 minutes, as [the earlier plan requested](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:342). Require repeat measurements and an uncertainty calculation before using a 15% discrepancy to change firmware. A trial entering the proposed CV state cannot calibrate CC slope alone.

8. **P1 — The re-seat timeout has no defined outcome and can leave a severe underestimate stuck.** [B’s rule](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:214) ends at “first below-clamp estimate or ~2 min,” without saying what happens when the timeout expires while still clamped. In [the existing implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:508), the battery ratchet never increases; the clamp countdown only decreases levels above its floor. Clearing an owed correction while retaining, for example, an underestimated 80% can therefore leave it stuck long after unplugging. Conversely, the first fresh below-clamp estimate is not necessarily relaxed.

   **Change:** Specify the timeout action, freshness requirements, replug behavior and the permitted one-time upward correction. Use measured relaxation to justify the delay. Test both an overestimate and an underestimate, prolonged clamp, missing reports and repeated replugging; do not silently discard the correction at two minutes.

9. **P2 — “Termination” remains an ambiguous FULL heuristic.** [B’s FULL condition](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:209) reproduces [the current test](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:502): external supply, CHRG released and a clamped reading. But [the battery documentation](/Users/jdlien/code/ak820-pro/docs/battery.md:407) records faults with CHRG released and the unusable DONE observation. A fault with terminal voltage still above the sensor ceiling is indistinguishable from successful termination using these inputs. The existing simulator’s charger-fault case uses a below-clamp value and misses this ambiguity.

   **Change:** Call FULL a heuristic, document the unresolved high-voltage fault case, and add that scenario. Define conservative behavior after interrupted/abnormal charging rather than treating every such signal combination as proof of a completed charge.

10. **P2 — B2’s replay gate needs a specified replay adapter and stronger assertions.** [The simulator](/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:213) parses the old seven-field format and advances 60 seconds per row. It cannot replay the newer ten-minute CSVs correctly. The September 28 log ends while charging; [the simulator supplies an artificial two-hour tail and termination](/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:245). Those are not recorded samples. “Partial charge … ends plausibly” is also not an executable assertion.

   **Change:** Plan version-aware parsing, explicit interval durations, treatment of aggregate versus end-state flags, and labeled synthetic tails. Give numerical expected ranges for partial charges and all boundary scenarios. Resolve “≥97 before termination” versus “termination step ≤2”—the latter requires at least 98 immediately beforehand. Replaying timing logs can test implementation behavior, but cannot establish charging-percentage accuracy without independent endpoint measurements.

11. **P2 — C1 misreads the clock evidence and overstates the RTC hypothesis.** [C1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:265) cites 7–12 ms/s as measured oscillator wander and ±0.1% as window noise. [The clock documentation](/Users/jdlien/code/ak820-pro/docs/clock.md:106) identifies 7–12 ms/s as early post-flash error; [the current loop description](/Users/jdlien/code/ak820-pro/docs/clock.md:34) reports roughly ±2 ticks, about ±0.006%, rather than ±0.1%. Separately, it records approximately 0.9% movement across a day. These do not establish 17 persistence writes per hour. The 816-write observation combines USB and battery operation.

   **Change:** Correct the quantities and retain RTC persistence as a hypothesis. Capture proposed period, persisted period, setter/flush counts and reference mode over separate USB/battery intervals. Account for the PCF path’s minimum 300-second accepted trim window. Also correct the stale 128-second-loop discussion in `docs/clock.md` so a fresh session follows the current 32-sample code.

12. **P1 — C2 reintroduces a persistence-starvation trap explicitly documented in the code.** [The three-stable-window requirement](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:286) is unsafe as a general rule for both reference paths. [The legacy path’s comment](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:990) explains why waiting for convergence can wait indefinitely: accepted trim windows become very long near lock. Its persistence check is inside `np != period`; “always persist after ten minutes … as now” is therefore not currently guaranteed on that path. The SOF path specifically handles unchanged accepted values to avoid this bug.

   **Change:** Separate persistence scheduling from accepted corrections. Use one shared write budget, a latest-valid candidate and a bounded first-save rule that works even when the candidate stops changing. Specify a bounded later-save fallback instead of indefinite stability waiting. Leave live frequency tracking and phase correction unchanged. Test fresh EEPROM and reboot behavior on host USB, charger-only USB and battery, including reference changes.

13. **P1 — C4’s proposed backlight guard races with the PWM ISR.** [C4](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:306) says interrupts are masked for the approximately 7 ms write. The actual [flash driver](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:51) masks only each short programming busy window; erase is deliberately unmasked. The begin hook runs before that window, and [the backlight ISR](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:198) can drive the pin high again after `begin` drives it low.

   **Change:** If implementing the guard, add an ISR-observed inhibit flag and set it atomically with forcing the pin low, using only a brief critical section. Honor effective brightness, power state and brightness caps; clear inhibition on every completion/error path. Preserve the existing watchdog scopes. Do **not** mask interrupts around the whole HAL operation—the driver explicitly warns that this loses UART data.

14. **P2 — C1’s subtraction does not identify other writers or consolidation, and C3 needs different counters.** [The proposed subtraction](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:273) mixes logical flush calls with backing-store unlock sessions. A dirty block can return to its previous contents before flushing, producing a call but no physical write. [Wear leveling](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/wear_leveling/wear_leveling.c:678) skips unchanged data and performs consolidation inside an existing write session. Consolidation therefore does not reliably appear as a separate “other writer.”

   **Change:** Track writer context at the actual write boundary, plus separate program and erase counters. For endurance, use actual log encoding: 2048 backing bytes minus 1024 logical bytes minus the eight-byte checksum leaves 1016 log bytes, or 127 eight-byte slots—not one erase per fixed number of logical flushes. Use the MCU datasheet’s **20,000-cycle minimum**, distinguishing it from the 100,000 typical value. :codex-file-citation{path="/Users/jdlien/code/ajazz-ak820-pro/docs/SN32F299_V1.8_EN.pdf" purpose="source"}

15. **P1 — D’s counters cannot attribute stalls to their cause as claimed.** [D1/D2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:336) would count existing marks and then fix the dominant mark. But [the profiler documentation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.h:87) explicitly says a 48 ms pass ending in a 2 ms clear is reported as `blit`. [Health measurement](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:136) times the entire loop interval. A marked pass can contain substantial unmarked work, so waiting for `none` to dominate before instrumenting CH582/battery can miss the culprit entirely.

   **Change:** Keep mark counts as correlations, but add bounded task-duration/co-occurrence measurements sufficient to distinguish the actual expensive operation and cumulative work. Include CH582, battery, display and RTC paths from the outset. Reuse the existing 10 Hz site structure where possible, and explicitly gate instrumentation overhead: the repository records dropped keystrokes from an earlier profiler costing roughly 2 ms per pass.

16. **P2 — The blanket claim that the CH582F TX path does not block is false.** [The plan’s evidence table](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:61) correctly identifies a nonblocking ACK wait, but both send and retransmit call [`sdWrite`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:503). ChibiOS defines it as an output-queue write with [`TIME_INFINITE`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/hal/include/hal_serial.h:268).

   **Change:** Narrow the claim to the ACK wait. Include TX queue wait, retransmissions, RX bursts, UART errors and queued keyboard-state replacement in the investigation. These can affect delivered keystrokes even without a ≥25 ms loop gap. Also distinguish the approximately once-per-minute standalone PCF check from the roughly 400/hour excess; C2 changes persistence, not that read schedule.

17. **P1 — Idle soaks do not verify the keystroke-loss risks introduced by this plan.** [The gates](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:393) omit the earlier plan’s explicit [plug/unplug transition tests](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:684). New percentage, “Charge,” bolt, warning and FULL transitions exercise synchronous display paths; changing pages also changes the workload. “Stall counters do not move while the camera page is up” has neither a duration nor a way to distinguish background stalls.

   **Change:** Require active typing and per-event measurements across plug/unplug, warning, FULL, unknown/known level, page transitions and flash writes. Fix page, connection mode, lighting and host-timekeeper conditions for comparative soaks. Record starting/ending uptime, build token, watchdog reset/degraded state and crash record. A reset must invalidate the soak: it clears RAM evidence, and [three watchdog resets disable the watchdog in degraded mode](/Users/jdlien/code/ak820-pro/docs/hardware.md:266). Define the write-rate gate over an actual interval and distinguish startup/discharge milestones from steady-state writes.

18. **P2 — The preservation and flash instructions need a few concrete completion checks.** [Step 0](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:32) assumes dumping immediately after the LED goes out captures termination, but the log contains completed ten-minute intervals. [The flash instructions](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:111) correctly identify RAM loss and the bootloader trap, but [`flash.sh`](/Users/jdlien/code/ak820-pro/flash.sh:120) continues after a failed lighting backup. EEPROM erasure also removes settings needed for comparable measurements.

   **Change:** Take a preservation dump before disruptive work, then a final dump after a completed interval records termination; record the observed LED event separately. Supply executable commands with a concrete timestamp convention, explicit archived firmware path and post-flash build-token check. Verify fresh keymap **and** lighting backups, record/reapply LCD brightness, clock format, BT slot and test lighting, and identify the known-good rollback artifact. Preserve health/crash evidence before resetting or flashing.

19. **P2 — The warning re-arm default is contradictory.** [E2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:366) permits a real charge **or** voltage recovery above `warn + 100 mV`; [D2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:420) says only a real charge. These produce different behavior after relaxation or a brief plug-in.

   **Change:** Choose one rule explicitly. If retaining voltage hysteresis, specify settled battery-only evidence so transient charging lift cannot re-arm it. Add tests for a short dump plug-in, genuine charge, voltage recovery and repeated low-voltage crossings; preserve the existing light-cut protections.

**Overall verdict:** The plan is not ready to execute as written. After these changes, it can be ready for staged diagnosis and calibration. Shipping the charging model and RTC persistence fix should remain conditional on those measurements, rather than being predetermined contents of flash 1.

---

# Round 2 (2026-10-04), on revision 2 -- verbatim

**Revision 2 is not ready to execute as written.** Of the 19 round-1 findings, **9 are resolved and 10 are partly resolved**.

I reproduced run 1’s committed fit output and points exactly. A2’s inclusion rule produces **159 log entries + 57 video samples = 216 points**, with plateau RMS **3.156** and worst error **−8.490 percentage points**.

The round-1 dispositions are:

| Round-1 finding | Status | Verification |
|---|---|---|
| 1. Flash sequence versus measurement gates | **Resolved** | The [order of work](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:107) moves B, C2 and the D fix after diagnostic measurements and permits another iteration. A separate gate-placement problem remains below. |
| 2. Unlogged 19:29 plug-in | **Resolved** | [A1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:183) explicitly assumes its duration, requests sensitivity, and clips the initial interval without double correction. This matches the CSV and observation record. |
| 3. Estimators, smoothing and gaps | **Partly resolved** | Source separation, time windows, jitter tolerance and offset sensitivity are specified. Clamp censoring remains incomplete, and flagging interpolated knots does not provide gap sensitivity. **R2-7.** |
| 4. Validation claims and acceptance | **Resolved** | [A2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:200) separates directional holdouts from training diagnostics, gives the reproducible inclusion rule, and labels thresholds appropriately. D4 reports the actual plateau error. |
| 5. Charging model presented as measured physics | **Partly resolved** | The empirical framing is improved, but the promised fallback has no executable qualification rule; the four-hour interval is still called established constant current. **R2-1.** |
| 6. Charging states and CV parameters | **Partly resolved** | States, caps, reboot behavior and a formula for τ now exist. UNKNOWN behavior conflicts with replay gates, and the formula introduces problematic partial-charge behavior. **R2-2, R2-4.** |
| 7. B3 calibration | **Partly resolved** | Offline voltage endpoints, settling compensation and a relaxation trajectory are added. The starting measurement is disturbed by USB, the numerical endpoint claim is wrong, and `L_CC_CAP` is not measured. **R2-3.** |
| 8. Re-seat timeout and underestimated level | **Resolved** | [The re-seat rule](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:308) now defines freshness, an upward correction, clamped behavior, missing reports and replugs. UNKNOWN arithmetic needs separate handling under R2-2. |
| 9. FULL heuristic | **Resolved** | [B](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:302) explicitly accepts and documents the high-voltage fault ambiguity and adds its simulator case. This resolves the unsupported certainty claim, not the hardware ambiguity itself. |
| 10. Replay adapter and assertions | **Partly resolved** | Version-aware parsing, durations, aggregate flags and synthetic tails are specified. Several new assertions conflict with the proposed state machine. **R2-2, R2-4.** |
| 11. Clock evidence | **Resolved** | [C1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:403) accurately distinguishes initial drift from convergence, retains the writer hypothesis, and specifies separate reference-mode measurements. |
| 12. RTC persistence starvation | **Resolved** | [C2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:436) separates saving from correction, retains the latest valid candidate, and supplies first-save and later-save scheduling independent of further changes. |
| 13. Backlight guard versus ISR | **Resolved** | [C4](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:475) specifies an ISR-observed inhibit flag, a brief critical section, effective brightness, cleanup and preserved watchdog scopes. This matches the driver’s interrupt constraints. |
| 14. Write attribution and endurance | **Partly resolved** | The 127-slot calculation and 20,000-cycle minimum are correct. Caller-level write context plus setter counts still cannot identify the fields responsible for physical writes or apply the milestone exclusions reliably. **R2-8.** |
| 15. Stall attribution and instrumentation cost | **Partly resolved** | Task timing improves the evidence, but retaining only the largest task loses cumulative causes. The cost gate also needs an executable measurement stage. **R2-5, R2-9.** |
| 16. CH582F blocking and transport risks | **Partly resolved** | The `sdWrite` correction and PCF frequency distinction are correct. Transport measurements remain conditional on stall attribution, omitting losses that need no long stall. **R2-6.** |
| 17. Hardware verification | **Partly resolved** | Active typing, fixed conditions, reset invalidation and interval-based write rates are added. There is still no delivered-input acceptance criterion or rejection of an already degraded watchdog. **R2-6.** |
| 18. Preservation and flash completion checks | **Partly resolved** | Preservation/final dumps, settings, build identity and the existing rollback artifact are covered. The prescribed backup timestamp check does not match script output. **R2-10.** |
| 19. Warning re-arm contradiction | **Resolved** | [E2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:552) and D2 consistently require a real charging session and remove voltage hysteresis while preserving the cut protections. |

The remaining and new findings follow; their identifiers are **R2-1 through R2-11**.

1. **P1 — The “outside validated conditions → Charge” fallback cannot be implemented from the stated rules.**

   [B’s qualification promise](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:258) lists weak supplies, cable losses, thermal limiting and changing load, but its state table enters CC using only a known level, CHRG qualification and an unclamped reading. None identifies the Mac’s source or establishes nominal charging current. Reduced-current charging can satisfy every entry condition and advance the percentage indefinitely.

   The same section still describes roughly four hours of constant current as observed. The records establish sensor-clamp timing and rail behavior; the ASC4056’s regulated voltage is approximately **4.2 V**, above the **4.036 V sensor ceiling**. Clamp entry is not a measured CC/CV transition. :codex-file-citation{path="/Users/jdlien/code/ajazz-ak820-pro/docs/ASC4056.pdf" purpose="source"}

   **Change:** Define an implementable qualification policy, including how qualification is lost and restored. Where these conditions cannot be verified, retain “Charge” or make the numerical model an explicitly selected experimental mode. Describe the observed phases as *before/after sensor clamp*, with physical CC/CV interpretations qualified.

2. **P1 — UNKNOWN charging contradicts the charge-from-flat replay gate.**

   The [state table](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:284) makes boot-on-USB charging UNKNOWN, with no transition to a trusted numerical start before FULL. All three charge-from-flat inputs begin after a boot on USB. Yet [B2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:354) requires every such replay to reach **≥980 pm before FULL**.

   There is also a numerical trap: [`LEVEL_UNKNOWN` is `0xFFFF`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:425). A bare `level >= 980` assertion would pass for UNKNOWN, and the proposed clamped re-seat’s `max(level, 905)` would preserve UNKNOWN.

   **Change:** Separate unknown-start replay assertions from known-start numerical assertions. Explicitly check validity before comparisons, subtraction or `max`. Define the battery-side result when an unknown-start charge is unplugged while still clamped. Do not seed recorded replays with an invented trusted percentage.

3. **P1 — B3 still cannot deliver its promised calibration.**

   [B3 step 2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:375) asks for a settled battery estimate over USB. The firmware [empties the estimator on supply and charging changes](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:222). The read can therefore return no estimate or an estimate already affected by charging, rather than the requested settled starting voltage.

   Its numerical claims also fail against the [current curve](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:381):

   - **5–8% corresponds to 3566–3640 mV**, not 3550–3600 mV.
   - Starting at 5–8% and adding 16–23 points produces **21–31%**, approximately **3789–3835 mV** before settling discharge. That does not guarantee an endpoint below 3.80 V and can enter the shoulder.
   - A low-level one-hour trial does not independently measure the pre-clamp `L_CC_CAP`, although [gate 5 requires it](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:618).

   **Change:** Capture the starting estimate by camera/debug page before connecting USB. Choose duration from the refitted curve with an explicit endpoint margin and rejection rule. Require repeat measurements. Add a separate near-clamp endpoint experiment for `L_CC_CAP`, or explicitly identify it as an extrapolation and remove the claim that B3 measures it.

4. **P2 — The new CV equation can accelerate charging and violate the partial-charge assertion.**

   [The τ formula](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:290) forces every starting level toward 99% over the same from-flat clamp duration.

   With `T_CV = 5.4 h` and `L_cv = 500`, its initial rate is approximately **36.2 percentage points/hour**, faster than B1’s proposed **16–23 points/hour** CC range. After one hour it predicts approximately **758 pm**. For `K_CC = 200 pm/h`, B2’s partial-charge assertion expects **670–730 pm**. Immediate clamp entry from a known partial level is explicitly permitted by the state table.

   Furthermore, fitting one median duration does not validate termination behavior for partial charges and top-ups.

   **Change:** Define numerical behavior and tests separately for unclamped charging, early clamp entry and near-full top-ups. Constrain any intended deceleration explicitly. Calibrate or qualify phase duration by starting condition; do not demand a linear-rise assertion after entering the exponential phase.

5. **P1 — Largest-task attribution still cannot distinguish cumulative stall causes.**

   [D1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:518) retains the winning task’s attribution count and each task’s maximum. A pass containing **8 ms of display work plus 3 ms of battery work** is attributed to display, even if the battery contribution is what changed a previously subthreshold pass into a stall. Separate maxima cannot reconstruct that co-occurrence.

   The proposed `keyboard_task` “remainder” is also broader than that function: the [main loop](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/main.c:47) includes protocol, raw-HID and other work outside it.

   **Change:** Retain bounded duration/co-occurrence evidence for slow passes—such as per-task accumulated time within slow passes and a small slow-pass record ring. Use mutually exclusive scopes and name the remainder “unaccounted,” then split it when material. Ensure fast RTC/display paths and deferred EEPROM flushing are covered.

6. **P1 — The typing gate can pass despite lost input or a disabled watchdog.**

   [D2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:535) collects TX queue events only if timing attribution points toward CH582F. The [verification protocol](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:590) requires typing but accepts events based only on loop gaps.

   The driver can [replace queued keyboard-state frames](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:543) or abandon retransmissions without a ≥25 ms pass. Queue replacement also does not increment the ordinary queue-full drop counter. Recording watchdog degradation without rejecting it permits a soak that starts with [the watchdog disabled](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog.c:89).

   **Change:** Add a known input sequence and host-side delivered-input check, including missing, duplicate and stuck-key outcomes. Capture transport failures, replacements and UART errors independently of stall attribution. Require a non-degraded watchdog at soak start and end, alongside reset invalidation.

7. **P2 — A1 still treats some censored means as measurements and omits gap sensitivity.**

   [A1’s filter](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:191) excludes means ≥99.5. However, the [15:59 entry](/Users/jdlien/code/ak820-pro/history/battery-2026-10-01-drain/log-20261003-1929.csv:119) has mean **99.36**, maximum **100**, and blank `pack_mv`. Several following entries have the same issue. The host deliberately [withholds voltage whenever any report hits a clamp](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:152).

   Flagging knots in the four-hour gap identifies missing evidence but does not quantify how interpolation affects the pooled curve.

   **Change:** For the new fit, either exclude any clamp-containing interval or explicitly model its censoring. Preserve the legacy reproduction path separately. Report sensitivity of gap-dependent knots and scores to alternative monotone interpolations or endpoint bounds.

8. **P2 — C1’s counters still cannot support physical per-field write exclusions.**

   [C1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:417) attributes physical writes to callers such as `kb_eeconfig`, while counting individual fields only at their setters. [The write-rate gate](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:600) then assumes those counts separate physical milestone writes.

   [`kb_eeconfig_task()` flushes the entire coalesced block](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:48). Several fields can share a flush, and a changed field can return to its persisted value before another field causes the actual write.

   **Change:** Carry a mask of fields that differ from the last flushed snapshot into the physical write context. Count mixed-field sessions explicitly and define their treatment in the gate. Do not subtract setter counts from physical write-session counts.

9. **P2 — The gates need executable staging and an instrumentation comparison.**

   [Gate 2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:611) requires the new charging assertions, although the pre-flash-1 work contains only replay infrastructure and B3 has not calibrated the model. Gate 3 requires measured D1 overhead at the build stage, before the diagnostic firmware has run.

   The cited [loop-budget plan](/Users/jdlien/code/ak820-pro/plans/LOOP-BUDGET-PLAN.md:84) also explicitly qualifies the historical “2 ms/pass” attribution and calls for console-off A/B measurements.

   **Change:** Place adapter checks and existing-model regressions before flash 1; place instrumentation A/B qualification immediately after the diagnostic flash and before long soaks; place new-model assertions and mutants after B3, before flash 2. Define the timing measurement and rollback criterion.

10. **P2 — The flash procedure requests timestamps that normal backup output does not contain.**

    [The procedure](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:149) says to confirm both fresh backup timestamps “in its output.” In the running-board path, [`flash.sh`](/Users/jdlien/code/ak820-pro/flash.sh:109) prints dump results, not their timestamps; timestamps are printed for the already-in-bootloader fallback. A lighting failure still continues toward flashing and can leave an old backup available for restoration.

    **Change:** Specify an explicit filesystem timestamp/content check while the script waits for Fn+Esc, and require aborting before bootloader entry on failure. Alternatively, make lighting backup failure fatal and print verified backup metadata.

11. **P2 — The revised evidence table still misidentifies the 7 ms measurement.**

    [The table](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:69) calls `flash_gap_max_ms ≈ 7 ms` the driver’s whole program-state duration. But [`health_loop_tick()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:136) measures the complete interval between housekeeping passes. A flash-marked interval includes preceding DMA drainage and other work; it does not measure `FLASH_PGM` occupancy.

    The datasheet specifies **10 µs typical / 20 µs maximum per 64-bit program operation**, separately from page erasure. :codex-file-citation{path="/Users/jdlien/code/ajazz-ak820-pro/docs/SN32F299_V1.8_EN.pdf" purpose="source"}

    **Change:** Label 7 ms as the observed maximum *flash-marked loop interval*. Measure program, erase and preceding-drain durations separately before assigning the visible blink a duration or mechanism. Keep C4’s erase explanation explicitly hypothetical.

**Verdict: not ready to execute as written.** The preservation and host-analysis steps are usable, but the charging contradictions, calibration gaps, stall attribution and input-delivery gate need correction before the corresponding firmware work proceeds.

---

# Round 3 (2026-10-04), on revision 3 -- verbatim

Model gpt-6-astra, reasoning xhigh, read-only, against commit `bb33583`.

Revision 3 resolves **7 of the 11 round-2 findings**. Four remain partly resolved. Of the ten round-1 findings previously marked partly resolved, **five are now resolved**.

I reproduced run 1’s fit output and points byte-for-byte. A2 still produces **159 log + 57 video = 216 points**, plateau RMS **3.156**, and worst error **−8.490 percentage points**.

“Resolved” below means the revised plan adequately addresses the finding; implementation and hardware verification remain future work.

| Round-2 finding | Revision-3 status | Verification |
|---|---|---|
| R2-1 — Qualification/fallback and physical-phase claims | **Partly resolved** | The CC/CV claims are corrected and LOST has an executable trigger. The ceiling rule contradicts its invariant, and LOST cannot qualify clamped charging. R3-2, R3-5 below. |
| R2-2 — UNKNOWN versus from-flat replays | **Partly resolved** | Sentinel checks and UNKNOWN’s clamped re-seat are specified. The claim that all three recorded charges qualify for FROM-FLAT is false. R3-1. |
| R2-3 — B3 calibration | **Resolved** | B3 reads the starting voltage without USB, requires two trials, compensates settling discharge, and checks the endpoint. The current curve confirms 5–8% = 3566–3640 mV; the shortened trial’s expected endpoint fits the 3810 mV limit. `L_KNEE` is explicitly an extrapolation. |
| R2-4 — Tail acceleration | **Partly resolved** | Changing phases by model level removes the clamp-triggered acceleration mechanism. The replacement equation can still accelerate within the stated parameter range. R3-4. |
| R2-5 — Cumulative stall attribution | **Resolved** | Slow-pass totals and the per-pass ring retain co-occurrence; mutually exclusive scopes and the “unaccounted” remainder address the attribution problem. |
| R2-6 — Input delivery/watchdog gate | **Partly resolved** | Delivered-text checks, unconditional transport inspection and watchdog rejection are added. The proposed retry-abandonment counter is misidentified. R3-3. |
| R2-7 — Censoring and gap sensitivity | **Resolved** | A1 excludes clamp-containing intervals, matching the host’s `pack_mv` rule, and requires both monotone gap extremes. Legacy reproduction remains separate. |
| R2-8 — Physical write attribution | **Resolved** | The persisted-snapshot difference mask and explicit mixed-session treatment match the coalesced write mechanism. |
| R2-9 — Executable gate staging | **Resolved** | Baseline replay, instrumentation qualification and calibrated-model tests now occur at workable stages. Existing health counters supply the pass-rate denominator for A/B qualification. |
| R2-10 — Backup verification | **Resolved** | The explicit filesystem check works while `flash.sh` waits; E7 is required before flash 1 and makes lighting-backup failure fatal. The stated rollback artifact exists. |
| R2-11 — Meaning of 7 ms | **Resolved** | The evidence table now correctly calls this a flash-marked loop interval, consistent with `health_loop_tick()` and the preceding DMA-drain hook. |

The previously partly resolved round-1 findings now stand as follows:

| Round-1 finding | Revision-3 status | Reason |
|---|---|---|
| 3 — Estimators, smoothing, gaps | **Resolved** | Source separation, time-based smoothing, censoring and sensitivities are specified. |
| 5 — Charging model as measured physics | **Partly resolved** | Empirical framing is corrected; qualification/bounding limitations remain. R3-5. |
| 6 — Charging states and parameters | **Partly resolved** | State handling is substantially clearer, but FROM-FLAT, ceiling behavior and tail constraints remain inconsistent. |
| 7 — B3 calibration | **Resolved** | The revised measurement procedure addresses the original defects. |
| 10 — Replay adapter/assertions | **Partly resolved** | Adapter requirements are adequate; recorded-start classification and some numerical assertions/mutants remain problematic. |
| 14 — Attribution/endurance | **Resolved** | Physical field masks and the 127-slot accounting address the finding. |
| 15 — Stall attribution/cost | **Resolved** | Co-occurrence evidence and staged A/B qualification are sufficient for this plan. |
| 16 — CH582F transport risks | **Partly resolved** | Blocking and queue replacement are recognized, but retry exhaustion still lacks the promised counter. |
| 17 — Hardware verification | **Partly resolved** | Typing and watchdog requirements are fixed; the transport-counter gap weakens acceptance. |
| 18 — Preservation/flash checks | **Resolved** | Preservation/final dumps, fresh backups, settings restoration, identity and rollback are covered. |

Remaining and new findings:

1. **R3-1 — P1: The September 28 replay cannot enter FROM-FLAT under the specified rule.**

   [B2](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:383) says all three charges start with `5C = 0`, then requires numerical progress to ≥970 before FULL. But the [September 28 CSV](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv:2) starts at **4**; its [observation record](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:50) says **2 → 3 → 4**. No zero is recorded.

   Under the [state table](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:317), that replay enters UNKNOWN-CHG and remains nonnumerical until FULL. Adding an invented zero prelude would conceal the contradiction.

   **Change:** Either classify September 28 as an unknown-start recorded replay and test FROM-FLAT separately, or broaden trusted-zero qualification to a fresh charging voltage demonstrably below the 3400 mV runtime cutoff, with an appropriate margin. Its first `5C = 4` corresponds to approximately **3196 mV**, so the latter approach can use the actual evidence. Keep any synthetic startup ordering explicitly labeled.

2. **R3-2 — P1: The display equation does not enforce its voltage ceiling.**

   The [equation](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:314) is:

   `level = max(level, min(M, U, 990))`

   Whenever `U` falls below the previous display, this necessarily leaves `level > U`. Using the [current curve](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:381), an estimate falling from **4008 to 4006 mV** lowers `U` from **750 to 700 pm**. With the previous display at 750 and `M = 760`, the new display remains 750. LOST waits another 30 minutes, while B2’s “never above U” assertion already fails.

   Conversely, releasing a binding ceiling can produce a jump larger than 10 pm because the equation contains no rise limiter. The table also lacks a defined MODEL action when the fresh estimate expires and `U` is unavailable.

   **Change:** Define precedence between monotonicity, ceiling enforcement and uncertainty. Specify the transition when a fresh ceiling contradicts the displayed level, including any noise tolerance; define stale-estimate behavior separately from clamped behavior; and retain an explicit rise limiter if the one-second step requirement stands. Test falling estimates, clamp entry/exit and report loss.

3. **R3-3 — P1: “Existing drops” does not count abandoned retransmissions.**

   [D1](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:577) proposes “abandoned retransmissions (the existing drops).” In the actual driver, [retry exhaustion](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:503) calls `ch582_tx_pop()` and returns without incrementing `tx_stat_drop`. That counter increments only on [queue-full rejection](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:584).

   Consequently, the planned diagnostics can report zero drops despite abandoned frames. Existing UART-error collection is also inside `CONSOLE_ENABLE`, whereas this plan builds `daily`.

   **Change:** Require a distinct retry-exhaustion counter at the abandonment branch, alongside queue-full and replacement counters. Explicitly provide UART-error collection in the diagnostic daily build. Verify an exhausted-retry case with no queue overflow: exhaustion must increment while queue-full remains zero.

4. **R3-4 — P2: A fixed τ still does not guarantee a decelerating tail.**

   The [tail formula](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:297) starts with rate:

   `(1000 − L_KNEE) / τ`

   Nothing requires that rate to be ≤ `K_CC`. A parameter set entirely within B1’s stated assumptions gives:

   - `K_CC = 160 pm/h`, `t_knee = 4.1 h`, `R = 30 pm`.
   - `L_KNEE = 626 pm`, `T_TAIL = 5.35 h`, `τ = 1.477 h`.
   - Initial tail rate **253.2 pm/h**, exceeding the preceding **160 pm/h**.
   - From `L0 = 600`, the one-hour result is **787.85 pm**, violating B2’s early-clamp limit of **770 pm**.

   **Change:** Add parameter-domain and rate constraints, including `τ ≥ (1000 − L_KNEE) / K_CC` with consistent units. Define what happens if measured parameters cannot satisfy both deceleration and the termination-step target: revise the model or retain “Charge”; do not adjust measured values merely to pass the assertions.

5. **R3-5 — P2: LOST is a below-clamp consistency check, not operating-condition qualification.**

   [B’s bounding claim](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:281) remains stronger than its mechanism. The plan expressly removes `U` at the clamp and acknowledges that a partial charge can clamp almost immediately.

   Thus a known 600 pm start, continuous CHRG and fresh clamped reports can advance toward 990 indefinitely without any LOST check—even if charging has slowed substantially. The re-seat corrects this only after unplugging. This is the same observable input shape already used by B2’s early-clamp test.

   **Change:** State explicitly that charging above the sensor ceiling proceeds by elapsed time without voltage validation, and that LOST detects only sufficiently large, sustained contradictions below the clamp. Either explicitly accept this limitation for the experimental operating condition or specify when to use “Charge.” Add a prolonged clamped, delayed-termination case; do not present the existing slow-charge test as general supply qualification.

6. **R3-6 — P2: B2 does not explicitly reject the removed-990-cap mutant.**

   [B2’s assertions](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:383) permit values such as **991–994 pm** while clamped: they satisfy ≥970 before FULL, need no large step, have no voltage ceiling, and still round to 99%. Removing the cap from the exponential can produce exactly this behavior.

   **Change:** For sessions starting at or below 990, assert valid numerical output **≤990 until FULL**, and keep CHRG asserted beyond the predicted termination time to exercise saturation. Preserve the separately specified already-full exception. Require this case to fail when the cap is removed.

The re-seat’s revised validity handling, delayed fresh-sample requirement and replug behavior are adequate at plan level, subject to B3 determining the delay. I found no additional blocker in its specification.

**Verdict: not ready to execute as written.** The blocking corrections are the recorded-start/FROM-FLAT contradiction, the incompatible ceiling/display rules, and the missing retry-exhaustion instrumentation. Preservation and host analysis can proceed; these defects should be corrected before the corresponding firmware work.

---

# Round 4 (2026-10-04), on revision 4 -- verbatim

Model gpt-6-astra, reasoning xhigh, read-only, against commit `b954b50`.

**Verdict: not ready to execute cold. The sole P1 blocker is gate 8’s contradiction with the permitted LOST dwell (R4-1).** The other corrections below can be handled during execution.

| Round-3 finding | Revision-4 status | Verification |
|---|---|---|
| **R3-1 — FROM-FLAT** | **Partly resolved** | 10.00 counts converts to **3248 mV**, about 152 mV below cutoff. September 28’s first logged **4** qualifies. The newer logs’ first means are **13.45 and 14.22**, with minima of zero; those statistics do not establish their first five reports. Early observations support from-flat starts, but replay ordering needs an explicit reconstruction. R4-3. |
| **R3-2 — Display precedence** | **Partly resolved** | The [new recurrence](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:375>) correctly holds under a falling ceiling, limits catch-up to 1 pm/s, freezes rises without a fresh estimate, and distinguishes clamp entry/exit. B2’s “no **rise** ends above U” now agrees. `level ≤ M` holds for properly initialized numerical model sessions; it is **not universal**, because the expressly preserved 1000 top-up exceeds capped `M=990`. Gate 8 remains inconsistent. R4-1. |
| **R3-3 — Transport counters** | **Resolved** | The actual driver matches the revised locations: exhaustion at **507**, replacement at **563–580**, queue-full rejection at **585**, and console-gated UART collection at **480–481, 908–922**. One initial send plus eight retries produces **nine timeouts** before abandonment. |
| **R3-4 — Tail acceleration** | **Resolved mathematically** | The new tail starts at `K_CC` and decelerates. For positive `K_CC,T_TAIL`, finite positive τ requires **`0 < 990−L_KNEE < K_CC·T_TAIL`**. All stated ranges satisfy this; their minimum feasibility slack is **374 pm**. I reproduced **L_KNEE=626, τ=2.61175 h, A=1043.880, ending rate=20.62985 pm/h**. Numerical arrival at 990 needs additional care. R4-2. |
| **R3-5 — Qualification above clamp** | **Resolved** | [The limitation](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:291>) is now explicitly accepted for the stated operating condition. LOST is correctly described as a consistency check; delayed termination is exercised. |
| **R3-6 — Removed cap mutant** | **Resolved** | [B2](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:554>) explicitly rejects 991–999, prolongs charging, and includes the `A≈1044` parameter set. That avoids relying on a calibrated asymptote barely above 990. |

The transport harness is realistic. The [driver’s includes](</Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1>) require more than two stub headers: report types, Bluetooth declarations, battery/health callbacks, serial configuration and I/O, timers, and ChibiOS event APIs. These are ordinary host-stubbable interfaces. Copying unchanged sources beside stubs follows the [existing simulator approach](</Users/jdlien/code/ak820-pro/scripts/battery_sim/run.sh:2>). Gate 1’s placement is sound. Its replacement fixture must include an existing queued `0xA1` behind any in-flight frame; a nearly full queue alone does not trigger replacement. I inspected feasibility; no new harness was compiled.

1. **R4-1 — P1: Gate 8 rejects behavior the display rule explicitly permits.**

   **Problem:** A held display can exceed fresh `U` by more than 50 pm for almost 30 minutes before LOST. Gate 8 forbids that immediately whenever outside LOST.

   **Evidence:** [The LOST dwell](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:422>), [B2’s explicit 29-minute non-LOST case](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:568>), and [gate 8](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:934>). For example, `level=M=760`, followed by `U=700`, must hold 760 before LOST qualifies. A ten-minute log entry can therefore legitimately violate the gate; averaging does not resolve this contradiction.

   **Change:** Gate rises against contemporaneous `U`, and gate sustained contradictions against LOST’s accumulated dwell. Also make B2’s “30 pm below display, no LOST” fixture constrain **`M−U`**, not merely `level−U`. Scope the `level≤M` statement to sessions excluding the already-full exception.

2. **R4-2 — P2: The fixed-point accuracy requirement does not ensure timely arrival at 990.**

   **Problem:** Being within 1 pm of the continuous exponential does not ensure crossing 990 within one minute, or starting OVERRUN correctly.

   **Evidence:** [The recurrence](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:368>) and [arrival assertion](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:540>). At the allowed corner `K=230, t_knee=4.25, R=0, T=5`, `L_KNEE=977.5`, τ≈0.054348 h, and **`A−990≈1.386×10⁻³⁹`**. A straightforward Q16 implementation rounds A to 990 and stalls around **989.997**. Flooring never reaches 990; rounding reaches it after roughly **10.5 minutes**, far before five hours. Both remain within 1 pm.

   **Change:** Specify a numerically robust arrival event, such as an independently tracked analytical arrival time with defined saturation/rounding. Test OVERRUN timing across the grid, including starts above the knee. Convert τ to seconds explicitly for the per-second recurrence.

3. **R4-3 — P2: “All three qualify on their own first entries” overstates the retained evidence.**

   **Problem:** Interval minima are not first estimates, and one proposed boundary input is unreachable through the estimator.

   **Evidence:** [10-01’s first row](</Users/jdlien/code/ak820-pro/history/battery-2026-10-01-charge/log-20261001-1947.csv:2>) contains mean/min/max **13.45/0/27**; [10-04’s](</Users/jdlien/code/ak820-pro/history/battery-2026-10-04-charge/log-20261004-2144.csv:2>) contains **14.22/0/28**. Different report orders can reproduce those statistics while producing opposite classifications. The [five-report estimator](</Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:305>) initially averages integer counts without trimming, so its resolution is **0.20 counts**: B2’s first estimate of **10.01** cannot occur.

   **Change:** Cite the early zero observations and explicitly label the chosen startup reconstruction within each first interval. Do not describe its ordering as recorded. Test **10.00 versus 10.20** through real reports; reserve 10.01 for a direct classification-helper test.

4. **R4-4 — P2: Finish specifying the pause handover and parameterize its tests.**

   **Problem:** The policy is workable, but the new tests and estimator handover assume more than the existing machinery guarantees.

   **Evidence:** [`charging_now()`](</Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:182>) includes the CHRG hold; [charger changes clear the estimator while `session` survives](</Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:228>). [PAUSE_S](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:357>) can exceed ten minutes when B3 increases RELAX_S, but [B2](</Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:578>) unconditionally expects handover at ten minutes. Clearing at charger stop guarantees post-stop samples, not samples taken after RELAX_S.

   **Change:** Test relative to final `PAUSE_S`; define pause timing against the qualified charging signal. Require sufficient fresh, post-relaxation evidence before adopting an idle level. Separate the new 60-second model qualification from the historical session flag needed for unplug re-seating. Exercise resumed charging and missing reports at the boundary.

The remaining new behavior is coherent: boot-on-USB shows “Charge” before qualification; short pauses suppress today’s [idle adjustment path](</Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:570>); LOST re-seating as UNKNOWN discards distrusted model provenance; and OVERRUN supplies a defined fallback above the clamp, subject to fixing its numerical trigger as described above.
