# Codex review: the power page on v0.4.0's curve (5937de2), 2026-11-13

gpt-6-astra at xhigh, read-only, from 20:14 (prompt: the commit, the firmware sources, six areas; given the code, not the conclusions). Its report verbatim; dispositions follow.

---

1. **P0 — The generator and oracle can silently miss a changed drive scale.** [power_model.py:186](/Users/jdlien/code/ak820-pro/scripts/power_model.py:186), [power_model.py:387](/Users/jdlien/code/ak820-pro/scripts/power_model.py:387).

   `wide_path()` reads the fallback `ROWISR_K_Q6` definition, assumes it is effective, and injects that assumption into the oracle. Adding the valid definition `#define ROWISR_K_Q6 150u` to firmware `config.h` leaves both generated firmware data and oracle source unchanged. I verified this with an in-memory source mutation.

   For full white with screen 42%, that firmware would count **208.149 mW**, while the page would still report **296.538 mW**. The tests cannot detect this because their oracle also uses the incorrectly assumed scale.

   The same coverage gap accepts changes to the flush’s value read, Solid’s local-value classification, and dither-phase advancement. The wide test checks encoded widths, not the complete path through caps, emitted ticks and accounting.

   **Fix:** resolve effective release-build macros and test the complete Solid-to-accounted-drive path against extracted C. Until then, reject changes to all unmodelled dependencies, rather than checking selected statements’ presence.

2. **P0 — CI permits a pin change that moves published figures without failing.** [power-page.yml:67](/Users/jdlien/code/ak820-pro/.github/workflows/power-page.yml:67).

   The workflow suppresses every generated-data mismatch, although the stated reason is allowing SHA-only changes. The remaining tests pin only selected settings; the oracle regenerates alongside the changed curve.

   In an in-memory simulation, changing `curve_q6[200]` from **3849 to 3951**—still monotonic—and supplying the corresponding oracle row left **all 13 tests passing**. White at value 200, screen 42%, changed:

   - Draw: **161.364 → 162.400 mW**
   - Balanced continuous runtime: **97.375 → 96.851 hours**

   Thus the claim at lines 63–64 that a number-changing pin still fails is false. Combined with finding 1, CI can also publish figures that disagree with the firmware.

   **Fix:** allow only provenance/SHA differences automatically. Fail on semantic changes to generated data until the committed data and affected published figures are reviewed.

3. **P0 — The revised worked example gives wrong numbers for its specified screen setting.** [docs/power.md:269](/Users/jdlien/code/ak820-pro/docs/power.md:269).

   The example specifies screen **level 8**, but calculates with **8/48 backlight duty**. On the release, level 8 has duty **1/48**; level 54 supplies 8/48. This obsolete label is retained in the example rewritten for v0.4.0.

   At white value 191 and actual screen level 8, `model.js` gives **149.370 mW active** and **119.463 mW dimmed**, not 155 and 125. Using the example’s stated schedule and 13.35 mW sleep assumption gives **985.55 mWh/day and 15.81 days**, rather than 1,016 mWh/day and 15.3 days.

   **Fix:** specify screen **54% (old level 8)**, or recalculate the example for current level 8.

4. **P1 — Historical sweep drives depend on the current firmware’s colour table.** [model.js:117](/Users/jdlien/code/ak820-pro/site/power/model.js:117), [model.test.js:215](/Users/jdlien/code/ak820-pro/site/power/model.test.js:215).

   `sweepRgb()` reconstructs a 2026-10-21 measurement using current `fw.cie1931`. This happens to work at this pin: I verified that `color.c` and `led_tables.c` are unchanged from `36afff30e8`.

   However, changing a future pin’s `CIE1931_CURVE[160]` from 80 to 81 silently changes historical “white 160” from `[80,80,80]` to `[81,81,81]`. The measurement and its firmware have not changed. With corresponding regenerated HSV fixtures, **all 13 tests still pass**; the “keeps the drive it ran at” assertion merely repeats the current-table calculation.

   **Fix:** preserve historical drive vectors, or the historical conversion and table, separately from the current firmware data.

5. **P1 — The new text incorrectly describes existing brightness-sweep evidence as absent.** [index.html:727](/Users/jdlien/code/ak820-pro/site/power/index.html:727), [POWER-CHARTS-PLAN.md:74](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:74).

   The repository already contains a tracked, two-pass `current_map.py --set percent` sweep in [percent-map-20261105/results.json](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/percent-map-20261105/results.json). It records white and purple settings, charge-register current, and **pack voltage for every hold**. Its curve and steady Solid emission arithmetic match the release.

   Consequently, “has not had a sweep,” “one reading,” and “voltage, unrecorded” misdescribe the evidence. Calculating directly from those records gives:

   | Setting | Measured | Page model | Model error |
   |---|---:|---:|---:|
   | White 50% | 136.069 mW | 129.006 mW | −5.19% |
   | White 75% | 161.548 mW | 155.656 mW | −3.65% |
   | White 90% | 217.758 mW | 214.434 mW | −1.53% |

   These include USB data and exclude the screen. The page’s approximate middle-range warning is supported, but “agrees at 90–100%” obscures the measured 90% discrepancy.

   **Fix:** distinguish the missing comprehensive *knobs* sweep from this existing brightness sweep; ingest its recorded voltages and report its residuals separately from the old driver’s 0.99% result.

On the six requested areas:

- **1 — Sound for the pinned release’s steady Solid average.** Solid renders `hsv_to_rgb(h,s,255)`; luminosity factors are 1; active/dim power scale is 255; the flush reads and caps the configured value. Lights-off scale zero makes every channel zero. The 18 × 125 µs field is 2,250 µs, so field cadence cancels when converting accumulated ticks to average drive: `mean_ticks × 64 / 300`. Dither decoding matched all 65,536 encoded entries. White drive is **254.933** at full, **47.573** under the saver/low-battery cap, **4.48** under the dim cap, and zero when off. The fixed RGB cost remains charged throughout a nonzero committed dithered frame, matching the firmware.
- **2 — Not fail-closed.** The extracted width function and tables are verbatim; the two reconstructed assignment strings match this pin. The oracle does not establish complete pipeline parity, as finding 1 demonstrates.
- **3 — Correct at this pin, with the historical dependency defect above.** Keeping old byte drives is appropriate. Mapping by channel sum works for the plotted white and primary-colour points. Old white 128 maps near 75%; old white 64 maps to **54.36%**. The changed runtime expectations follow the release arithmetic.
- **4 — Main new runtime figures match the model.** I reproduced 52.54, 102.07, 123.66 and 59.97 hours, the pause costs, and the under-0.1-day preset changes. The documentation exceptions are above; I found no additional demonstrated error in the changed README figures.
- **5 — Not sound as a general figure-change gate.** Finding 2 demonstrates the gap.
- **6 — No additional demonstrated defect in the changed calculator logic.**

`power_model.py --check` and all 13 supplied-fixture tests passed. No files were modified. I did not rebuild the oracle, run GitHub Actions, or measure hardware; exact short-window accounting, omitted pulses, and physical runtime on release hardware remain unverified.
---

## Dispositions (11-13)

Every finding checked against the code and the data before fixing; all five
accepted. Each fix is in the commit after `5937de2`.

1. **The scale can move silently: accepted, fixed.** Reproduced the reasoning:
   `rowisr.c` defaults `ROWISR_CADENCE_US` and `ROWISR_K_Q6` under `#ifndef`, so
   a definition the build sees first wins, and `wide_path()` read only the
   default. `scale_guard()` now fails on any definition (`#define`, `#undef`,
   `-D`, a make variable, a JSON key; comments stripped) of the cadence, the
   scale, the reference or the luminosity in the keyboard's build-wide files
   (`config.h` but its one cadence, `rules.mk`, `keyboard.json`, the keymaps'
   `rules.mk`/`config.h`), in the board headers `rowisr.c` includes, in
   `rowisr.c` outside the `#ifndef` defaults, and in `build.sh` outside
   devprobe; every luminosity definition must be 1. The flush's value read and
   encoding, the dither's phase and clock join the verbatim lines; Solid must be
   in `power_wide_mode()` and not in `power_local_value_mode()` (function
   bodies, not the file); `apply()`'s stages must open with the caps model.js
   applies. Mutation-tested in memory: `ROWISR_K_Q6 150u` in `config.h`, a `-D`
   in `rules.mk` and in the via keymap's, a define in `power.h`, luminosity 2,
   Solid made local-value, the dim's cap halved, the dither clock doubled, the
   value read halved, the `#ifndef` removed: each caught. On "test the
   complete Solid-to-accounted-drive path against extracted C": the 11-05
   percent sweep's holds carry the board's own `model_mw`, its firmware's
   battery model and curve the pin's by blob, and the page's model now equals
   it at all 21 holds within 0.14 mW (a test): the whole path, on the real
   firmware, at this pin. A C harness of the flush and the accounting is not
   built; the guards make a change to either fail instead.
2. **CI permits a figure-moving pin: accepted, fixed.** The first version
   warned on every drift; the claim that the tests catch a moved figure held
   only for the figures they pin. `--check` now exits 3 when the committed and
   fresh documents differ in `firmware.sha` alone, 1 on anything else; CI warns
   and publishes a fresh build on 3 and fails otherwise. The `curve_q6[200]`
   mutation is not sha-only (checked).
3. **The worked example's screen level: accepted, fixed.** On P2b's 101
   levels, level 8 is 1 tick; 8 of 48 is 54%. The example now says 54% (8 of
   48) and its sums are the model's: 155 mW awake (LEDs 41.7), ~125 dimmed,
   ~1,014 mWh a day, ~15.4 days (was 15.3). The level-8 label predates this
   commit; the commit rewrote the example around it.
4. **The old sweep leans on today's colour code: accepted, fixed.** Each sweep
   in `power_evidence.json` records the blob ids of the files its rendering
   depends on at its own firmware (the knobs sweep: `color.c`, `color.h`,
   `led_tables.c` at `36afff30e8`; the percent sweep: those and
   `curve12.h` at `d6656f9262`); `power_model.py` fails when the pin's differ,
   so the drives must be frozen in the evidence before such a pin moves. The
   test's "keeps the drive it ran at" stays, its comment now says what holds it.
5. **The percent sweep exists: accepted, fixed.** The text "has not had a
   sweep", "one reading" and "voltage unrecorded" were wrong. Confirmed its
   firmware has the release's curve, colour code and battery model (blobs) and
   wide path (`git diff d6656f9262 d59cb1fb0c`), and its figures: the board
   draws 5.5% more than the model at white 50% (Astra's 5.19% is the same gap
   as a fraction of the measured draw), 3.8% at 75%, 1.6% at 90%. It is now
   evidence: parsed by `bench_sweep()`, a table and a computed paragraph on the
   page, a test (the board's own model at every hold; dark 0.2%, lit 5.5%),
   `docs/power.md`'s accuracy paragraph, and `BACKLOG.md`'s gauge item. The
   chart's dots are still the 10-21 sweep's.
