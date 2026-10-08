Three pre-flash blockers, **F1–F3**, below. No files modified. I reran the Python grid and v3/v4/v5 decoder tests successfully; the C suites were audited, not rebuilt, because they create files. The BIN/ELF hashes match the clean `872f1f8a67` manifest.

1. **Model: mostly right, two implementation failures.** Ceiling precedence, rise limiting, 990 cap, LOST accumulation/holding, clock-based OVERRUN, UNKNOWN handling, replug debt, relaxed adoption and FULL cancellation match B.

   **F1 — FROM-FLAT does not latch the first five reports.** [battery.c:1183](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:1183) latches the estimate at the next battery task; reports update it individually beforehand. With bursts `10,10,10` then `10,10,11`, the first-five estimate is 10.00, but the latched six-report estimate is 10.17: UNKNOWN instead of FROM-FLAT. The reverse misclassification is possible too. [sim.c:118](/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:118) delivers one report followed immediately by a battery task, hiding this. Latch at estimate creation and test bursts.

   **F2 — resuming before handover adoption reuses an untrusted held level.** [battery.c:675](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:675) clears `adopt_owed`, then accepts any numeric `level`. After a handover without a relaxed estimate, that number is still the old display. B requires UNKNOWN-CHG until a level was adopted. With `PAUSE_S == RELAX_S`, resuming just after handover readily hits this. Preserve the adoption-validity distinction.

2. **Numbers: arithmetic right; calibration approval missing — F3.** The [generated header](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery_tail.h:4) matches the generator: 314 nodes, τ 5.78047 h, ending rate 53.94 pm/h. Agreement between the two measurements supports 133; feasibility does not establish the knee.

   Shipping this as an explicitly unvalidated measurement experiment is defensible. It does **not** satisfy [B’s contradiction rule](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-REFINE-PLAN.md:410), and trial 2 alone will not measure the knee. I recommend **“Charge” for sessions until the knee is measured or the model is revised**.

   The claimed “up to ~5 points” underestimate is unsupported. Assuming the net rise remains 133 pm/h and reserve is 30 pm: at 7 h, the alternative is **90.1% versus model 84.4%**; at 7.5 h, **96.8% versus 88.2%**. Actual error depends on where current falls.

   The placeholder overstates that same alternative by 14.4 points at 2 h and 25.8 at 4 h. But the replacement is **not uniformly more conservative**: from 950, its initial rate is 60.9 versus 37.0 pm/h, and OVERRUN arrives after **1.70 versus 4.35 h**. Slow near-full top-ups are an unvalidated case.

3. **Thirty-minute constants: numerically safe; visible tradeoff.** [battery.c:579](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:579) uses adequate counters; `RELAX_S * 1000u` is 32-bit, 1,800,000 ms. LOST stops at 1800 seconds; stale LOST at 600; both freeze during pauses. No short-value overflow found.

   After UNKNOWN/LOST unplugging, the dashboard has an empty bar and **blank number**, camera `--%`, until 30 minutes plus five new reports. During a below-clamp pause, a known number holds; unknown reads **“USB”**, camera `--%`. Acceptable for calibration, poor daily feedback. An earlier provisional unknown-only estimate would be a policy change, not a timer fix.

   Minor divergence: [battery.c:864](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:864) runs the clamp countdown even while re-seat is owed: a known high level can lose roughly 1 point during the supposed hold.

4. **Histogram: right.** [battery.c:290](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:290) resets counts with the ring; eviction precedes insertion; trimming and rounding equal the sort at every fill. Each bin is ≤64. The retained sum is ≤4900—49 retained reports at fill 63—and the scaled numerator uses `uint32_t`. No overflow.

5. **RTC scheduler: budget right; first-save claim needs qualification.** [rtc_persist.c:14](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/rtc/rtc_persist.c:14) implements the stated thresholds. A sane stored value makes reboot wait six hours again. Both paths share one budget; normal RTC persistence cannot exceed four sessions per day, comfortably below ten with the stated exclusions. Host time sync writes the PCF, not a second internal-flash period copy.

   It intentionally can save a **not-yet-converged** candidate. However, fresh EEPROM plus an already-matching PCF seed can produce **no candidate and no first save**: [rtc.c:961](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/rtc/rtc.c:961) requires drift, and line 980 requires a changed period before proposing. The [harness](/Users/jdlien/code/ak820-pro/scripts/diag_sim/sim.c:233) injects a proposal directly; its “reboot” case also never resets scheduler state. These integration cases remain untested.

6. **Camera: right on the normal drawing paths.** [display.c:902](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/graphics/display.c:902) submits one glyph and returns. Entry uses eight 16-row bands; [exit](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/graphics/display.c:1287) stages restoration, including individual lock components. Preview geometry matches. No new normal ≥25 ms bulk-drawing path found. Inherited LCD fault recovery is still capable of longer waits; this is not a hard worst-case timing guarantee.

7. **The named `b793644` changes are legitimate, not loosened.** [model.c:219](/Users/jdlien/code/ak820-pro/scripts/battery_sim/model.c:219) independently scans tail entry; extending stale time beyond RELAX strengthens the missing-report case; adding a below-knee start restores the clamp mutant’s relevance.

   Two remaining coverage problems: [model.c:492](/Users/jdlien/code/ak820-pro/scripts/battery_sim/model.c:492) calls any retained number “adopted,” masking F2. And [model.c:712](/Users/jdlien/code/ak820-pro/scripts/battery_sim/model.c:712) watches FULL for exactly 30 minutes; relaxation starts later, so this dedicated test no longer crosses the timer it claims to test. Parameterize its duration beyond RELAX and refill.

8. **No new hang/reset/brick path found; one log semantics defect.** Watchdog completion feeding and flash/DMA serialization remain intact. The 29-byte log body fits exactly; current host offsets are correct. ELF NOBITS totals 30112 B, including 3376 B heap.

   [battery.c:365](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:365) does **not freeze the aggregate after saturation**: after `661×99`, a rejected 100 can be followed by an accepted 1. Thus the flagged mean/count are not strictly the prefix promised by v5. Extrema remain correct; this is diagnostic, not memory corruption.

   The Rust daemon and `ak820health.py` filter by command and read unchanged health layouts. Previous v3/v4 battery readers reject v5 logs. Much older `1c08e26:hostagent/ak820battery.py:74` can misinterpret HC_CONN units, and its line-104 v1 fallback can misparse logs when pack mV is zero; that incompatibility predates flash 2.

**fix 3 first**

---

## Verification pass 1 (2026-10-08, on c4d7b3702b / c95d0a2) -- verbatim

Read-only audit; no files modified or builds rerun.

- **F1 — partly.** The burst error is fixed, but this captures the **first qualifying EXTERNAL estimate**, not necessarily the boot’s first estimate. Supply, charger and staleness resets restart the five-report count; they never reset an established latch. At report time, latching requires EXTERNAL and `!ran_from_pack`. Estimates while UNKNOWN are neither captured nor marked consumed: five high reports while UNKNOWN, followed by EXTERNAL/reset and five low reports, can therefore qualify FROM-FLAT. The burst scenarios start after supply qualification and miss this. [Latch](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:595)

- **F2 — partly.** Direct resumption is fixed: the number holds through handover/requalification, then becomes **“Charge”**, camera `--%`. A later unplug shows an empty bar/blank number until relaxed re-seat; an unknown clamped pack becomes 950. But **handover → unplug before adoption → replug and qualify before re-seat** still starts MODEL from the held number: unplug clears `adopt_owed`, preserves the number under `reseat`, and `chg_open` ignores `reseat`. [Unplug path](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:874)

- **7 — partly.** The adopted-level test now demonstrates adoption, and FULL monitoring crosses relaxation and refill. However, `m_pause_after_unadopted` selects `tgt_m_minus`, which ignores `stopped`: reports **continue throughout the pause**. It catches today’s equal-timer boundary, but does not test its claimed missing-report case independently of `RELAX_S`. The burst tests are valid; all actual mutant sites are unique and correctly placed, including UNKNOWN. [Test](/Users/jdlien/code/ak820-pro/scripts/battery_sim/model.c:538)

- **8 — resolved.** Saturation now freezes sum/count until period reset while extrema continue. The scenario correctly checks **65439/661** after rejected 100s and subsequent 1s. However, there is **no log-prefix mutant** among the 15, so “each fix … a mutant” overstates coverage. [Accumulator](/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2/keyboards/a_jazz/ak820pro/battery.c:370)

**F3:** The disposition states my figures correctly, with rounding.

**fix 3 first**