# Fix the one-row matrix publish (the aliasing beat)

> **STATUS: DONE — shipped 2026-09-03, `qmk_firmware@e6cce28858`.**
> Audited by codex/gpt-5.6-sol (`plans/review-codex-sol-matrix-2026-09-03.md`),
> which confirmed the mechanism, corrected the arithmetic, and recommended a
> simpler fix than the staging buffer proposed below. That recommendation is
> what shipped. **The plan text from here down is the pre-audit proposal, kept
> unedited as the record; read the Outcome section at the bottom for what was
> actually built and measured.**

Status: **DRAFT FOR AUDIT, 2026-09-03.** Not built. Written to stand alone —
assume the reader has no prior context.

## TL;DR

A key on this keyboard can go **~160 ms without being sampled**, on an idle
board, with the main loop running perfectly and every health counter clean. A
keypress lasts 25–80 ms, so a press that falls in that window is lost with no
trace. Cause: the driver publishes the matrix after sampling **one row**, and
which row it samples is set by an aliasing beat. Fix: accumulate a full matrix
in the ISR across one row cycle (~0.96 ms) and publish a complete snapshot.

## Background a fresh reader needs

**Board.** AJAZZ AK820 Pro, 82-key ANSI, SN32F299 Cortex-M0 @48 MHz, QMK fork
on branch `ak820pro-jdlien`. Repo layout, build and flash: see `README.md`;
board conventions: `CLAUDE.md`.

**The matrix scan is physically coupled to the RGB LED multiplexing.** The RGB
matrix drives one row at a time; only the row currently energised can be read.
`config.h:11` sets `SN32F2XX_PWM_DIRECTION COL2ROW`, and the board's
`diode_direction` is also `COL2ROW`, so the driver takes its
"PWM direction == diode direction" path, which reads **one row per call**.

**Where.** `drivers/led/sn32f2xx.c` (a QMK core file this fork already patches;
changes there are weak-hooked/no-op for other SN32 boards):

- `shared_matrix_scan_keys(matrix_row_t current_matrix[], uint8_t current_key, uint8_t last_key)`
  ~line 402. Guarded by `if (!matrix_scanned)`. Reads **one row**
  (`matrix_read_cols_on_row(current_matrix, current_key)`) then sets
  `matrix_scanned = true`.
- Called from the row ISR path ~line 484, once per row slot, with
  `current_key_row` cycling 0..`SN32F2XX_RGB_MATRIX_ROWS` (`ROWS_PER_HAND` is
  `MATRIX_ROWS` = 6, `config.h:22`).
- `matrix_scan_custom()` ~line 875 (main loop): returns false unless
  `matrix_scanned`; otherwise `memcmp`/`memcpy` the **whole rolling**
  `shared_matrix` into `raw_matrix`, then clears `matrix_scanned`.
- There is a `matrix_locked` / `first_scanned` interlock intended to keep row
  coverage fair across a cycle. **It does keep totals fair. It does not fix the
  gap** — see measurements.

**Debounce** is `sym_defer_pk` at 5 ms (`keyboards/a_jazz/ak820pro/rules.mk`).
Debounce runs *after* this sampling, so anything missed here is invisible to it.

## The defect, measured (2026-09-03)

Instrumentation added in firmware `0c23a6f4f4`: weak hooks
`input_note_row_scan()` (ISR: records which row was sampled) and
`input_note_consume()` (main loop: does the timing, counts raw edges).
Exposed on health page 3 (`HC_GET3`, proto v4); read with
`./venv/bin/python hostagent/ak820health.py --rows --stalls`.

Three 15-second idle runs:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| `consumes` | 5168 | 5141 | 5178 |
| `row_samples` spread | 825–897 | 849–870 | 848–875 |
| **`row_gap_max_ms`** | **165 (row 1)** | **169 (row 5)** | **156 (row 3)** |
| `count_ge_25ms` | 0 | 0 | 0 |
| `blit_gap_max_ms` | 0 | 0 | 0 |

**Row totals are fair (<4% spread). Individual gaps are ~9× the mean.** The
worst row differs each run. No main-loop stall is involved: `count_ge_25ms` is
zero throughout, and this reproduces on an idle board.

### Why: an aliasing beat

The row sampled at each consume is whichever the PWM is driving at that instant.

| | |
|---|---|
| consume rate | ~344/s → 2.91 ms apart |
| row advance | ~6267/s (row ISR ~18,800/s, key rows advance once per 3 RGB slots) |
| full row cycle | ~1044 Hz → 0.96 ms |
| rows advanced per consume | **~18.2 → fractional drift ~0.2 rows** |

Because the drift is fractional, the sampled row **creeps**: a row is sampled in
a short burst of consecutive consumes, then ignored while the phase walks around
the other five. Model predicts **57 samples/s per row; measured 57** — exact.
The predicted beat is ~83 ms against a measured 156–169 ms, so the row-advance
figure above is off by roughly 2× (audit should pin it down), but the shape and
the sample rate are confirmed.

### Consequence

A press+release inside a row's gap is never sampled, so it never reaches
debounce, never becomes a key event, and is invisible to `key_presses` (which
lives in `process_record_kb`, after debounce) and to every loop-stall counter.
This is a keystroke-loss mechanism that requires **no stall at all**.

It matches the owner's long-standing symptom: intermittent, not key-specific,
not reproducible on command, clean in slow single-key tests (a deliberate 60–80
ms press spans a sample), worse in fast typing, indistinguishable from mistyping.

**Two earlier diagnoses were wrong and are retracted** — see
`plans/INPUT-PATH-PLAN.md`: main-loop stalls (`count_ge_25ms_nonflash` is 0
throughout) and the `sym_defer_g` debounce swallow (real mechanism, but its
global timer restarts on a raw state *change*, not per scan, so realistic typing
does not sustain it).

## Proposed change

**Publish a complete matrix, not a rolling one.** In the ISR, accumulate row
samples into a staging buffer and only assert `matrix_scanned` once every row
has been sampled in the current cycle. The main loop then always consumes a
coherent full-matrix snapshot.

Effect: every key is sampled once per row cycle (~0.96 ms) regardless of the
consume rate or its phase — worst-case gap ~1 ms instead of ~160 ms, an order of
magnitude below the shortest keypress.

Sketch (illustrative, not final):

```c
static matrix_row_t staging[MATRIX_ROWS];
static uint8_t      rows_seen_mask;          /* bit per row */

/* in the ISR, per row slot */
matrix_read_cols_on_row(staging, current_key);
rows_seen_mask |= (1u << current_key);
if (rows_seen_mask == ALL_ROWS_MASK && !matrix_scanned) {
    memcpy(shared_matrix, staging, sizeof(shared_matrix));
    rows_seen_mask = 0;
    matrix_scanned = true;
}
```

### Constraints the design must respect

1. **Only the energised row is readable.** A full snapshot must be accumulated
   across a cycle; it cannot be taken in one call.
2. **ISR cost.** This runs in the row ISR at ~6267 row-slots/s. The board is
   already ~72% ISR (`docs/leds.md`). A `memcpy` of 6 × `matrix_row_t` per
   *cycle* (~1044/s) is cheap; per *slot* would not be.
3. **Tearing.** `shared_matrix` is read by the main loop without a lock.
   Publishing must not leave it half-updated. Today's code has the same
   exposure; the fix should not worsen it.
4. **The scan is skipped entirely during flash programming** — the row ISR
   returns early while `EFLD1.state == FLASH_PGM`. A full-snapshot scheme does
   not change that; presses during an internal-flash write are still lost. Out
   of scope here (see `plans/BACKLOG.md`, wear-levelling consolidation ~33 ms).
5. **Do not regress LED behaviour.** `shared_matrix_rgb_disable_output()` is
   called before scanning; the RGB field rate (1046 Hz) and the interrupt
   priority table are load-bearing (`docs/leds.md` — "if Bluetooth regresses,
   check the interrupt priority table first").
6. **`matrix_locked` / `first_scanned` may become redundant.** Decide whether to
   remove or retain it; removing dead interlocks is preferable to leaving two
   mechanisms that disagree.

## Validation

Before/after, same session, same conditions (the historical scan-rate figures
are not comparable — `docs/hardware.md` records why):

1. `ak820health.py --reset`, idle 15 s, `--rows --stalls`. **Expect
   `row_gap_max_ms` to fall from ~160 ms to ~1–3 ms** and `row_samples` to rise
   to roughly `consumes` per row (every consume now sees every row).
2. Repeat under typing load and under `scripts/soak.py`.
3. `scan_rate` must not fall (it is the main-loop rate, ratio 0.997 — see
   `docs/hardware.md`); the soak gate fails below 320 Hz idle.
4. `raw_edges` vs `key_presses`: a press and release are two raw edges, so
   expect ~2× once typing. A large excess means edges are being seen and then
   lost in debounce.
5. Type normally for a day and compare dropped-character rate subjectively —
   the only end-to-end measure available.

## Risks

- **This is the input path on a daily-driver keyboard.** A bug means the owner
  cannot type to fix it. Escape hatch: stock firmware image (see `README.md`,
  SHA256 recorded) and `flash.sh`, which backs up and restores the VIA keymap.
- ~~Higher effective sample rate could surface switch chatter the slow sampling
  was masking.~~ **RETRACTED, and it is backwards.** Bounce rejection requires
  RE-SAMPLING inside the debounce window. Today a row's raw bits only change
  every ~18 ms while `debounce()` runs every ~2.9 ms with a 5 ms per-key
  counter (`sym_defer_pk.c`: transfer when `counter <= elapsed_time`), so the
  debouncer spends its window confirming that a STALE value — one it is not
  re-reading and which cannot change — has not changed. **Bounce rejection is
  currently a no-op; all the 5 ms buys is latency.** After this fix, ~1 ms
  sampling puts ~5 samples inside the window and debounce becomes operative for
  the first time. So the fix SUPPRESSES chatter rather than surfacing it.

  Residual, correctly framed: bounce is a solved problem. If it survives a
  functioning 5 ms per-key debounce, the switch is faulty — replace it, or raise
  `DEBOUNCE` deliberately with switch traces. Do not treat that as a regression
  in this change.
- Any change to `sn32f2xx.c` affects a shared QMK core driver. Keep it behind
  the existing board-selected path and weak hooks.

## Explicitly NOT proposed

- **The ISR timestamped event queue (T2b)** in `plans/INPUT-PATH-PLAN.md`. It
  was aimed at main-loop stall immunity, and stalls are not happening. This fix
  is upstream of it and far smaller. Re-evaluate only if measurements after this
  change still show loss.
- **Sticky-bitmap edge capture (T2a)** — killed in audit: cannot represent
  multiplicity, order or duration.
- **Splitting wear-levelling consolidation** — separate, riskier, deferred.

## Questions for the auditor

1. Is the aliasing-beat explanation correct? Pin down the true row-advance rate;
   the model predicts a ~83 ms beat against a measured 156–169 ms.
2. Is the staging-buffer publish sound in ISR context — tearing, memory
   ordering, `volatile`/barrier requirements for `shared_matrix` and
   `matrix_scanned` between ISR and main loop on Cortex-M0?
3. Does publishing only on a complete cycle risk **starving** the main loop of
   updates if a row is persistently skipped (e.g. the ISR early-returns during
   flash programming, or `current_key_row >= ROWS_PER_HAND`)? Should there be a
   staleness fallback that publishes an incomplete snapshot rather than none?
4. What breaks if `matrix_locked`/`first_scanned` is removed?
5. Confirm or refute: is per-key bounce rejection currently a NO-OP because a
   row's raw bits are stale between fresh samples (~18 ms) while the debounce
   window is 5 ms — i.e. does the fix make `sym_defer_pk` operative rather than
   risk surfacing chatter? If so, does `DEBOUNCE 5` remain the right value once
   ~5 samples actually fall inside the window?
6. Anything else on this path that loses or reorders keystrokes and is not
   already recorded in `plans/INPUT-PATH-PLAN.md` §2 or `docs/hardware.md`?

---

# Outcome (2026-09-03)

## What shipped, and how it differs from the proposal above

Not the staging buffer. `shared_matrix_scan_keys()` scans **straight into
`shared_matrix`** on every genuine key-row transition (`last_key != current_key`).
`matrix_scanned` is demoted from a scan gate to a dirty flag, and the main loop's
compare/copy/clear in `matrix_scan_custom()` runs under `chSysLock()` /
`chSysUnlock()` — the pattern `sn32f2xx_flush()` already used — so an ISR write
cannot land mid-copy. A six-bit `rows_seen` mask withholds readiness until every
row has been sampled once, so the loop never consumes uninitialised rows at boot.

No second buffer, no ISR `memcpy`, no atomics. The audit's Q3 memory-ordering
finding was real for the *staging* design but does not apply here: `chSysLock()`
masks interrupts on Cortex-M0 and carries compiler barriers, so the ISR is atomic
with respect to the locked copy and reordering inside it cannot be observed.

`matrix_locked` / `first_scanned` (auditor question 4) were removed. They existed
to keep row coverage fair under the one-row scheme, which no longer exists. The
binary is byte-identical before and after removing `matrix_locked`, confirming it
was already unreachable.

## Measured, three 12-second idle runs

| | before | after |
|---|---|---|
| worst gap between samples of one row | 156–169 ms | **5–7 ms** |
| samples per row per second | ~57 | **~217** |
| spread across the six rows over 12 s | 825–897 | **2599–2603** |
| `scan_rate` | 326–378 | 301–338 |
| `count_ge_25ms_nonflash` | 0 | 0 |

The spread collapsing from ~70 counts to ~4 is the real signature: rows are
sampled in strict rotation now rather than phase-selected. A 25–80 ms keypress is
now sampled 5–17 times instead of possibly zero.

First real-world check, same day: a 30-second monkeytype run at 118 wpm,
**294 characters, 100% accuracy, zero incorrect**. Suggestive rather than
conclusive on its own — at the ~0.5% drop rate originally reported, a clean 294
is roughly a 1-in-4 event — but it is the direction expected, and repeated clean
runs compound quickly.

## Instrumentation had to be fixed before the result was visible

Per-row gap timing lived in `input_note_consume()` because, under the old code,
"time between consumes naming row R" *was* "time between samples of row R". After
the fix the ISR scans ~4 rows per consume, so the consume-side version refreshed
only one row's timestamp per consume and reported **159–308 ms — worse than
before** — while sampling had in fact improved 4x. It moved into
`input_note_row_scan()`, which runs in the ISR and uses `chVTGetSystemTimeX()`
(`timer_read32()` takes a lock and must not be called there).

Worth recording as a pattern: **a fix that changes the shape of an event can
invalidate the instrument built to measure it.** The first reading after this
change said the fix had failed.

## Auditor questions, answered

1. **Aliasing correct?** Yes, mechanism confirmed. Arithmetic corrected: 4.8 MHz
   / 256 = 18,750 ISR/s, row advancing every third ISR = 6,250 rows/s = 1,041.667
   cycles/s. The plan's 6267/s came from rounding 18,750 to 18,800. The audit also
   correctly flags that the plan's "57/s predicted, 57/s measured" agreement was
   **tautological** — one row accepted per consume divided six ways — not evidence
   for the beat model.
2. **Staging publish sound?** Moot; not built. See above for why the shipped
   design needs no atomics.
3. **Starvation risk?** No. Flash programming pauses both advancement and
   scanning, so the mask resumes afterward; RGB rows equal the six matrix rows on
   this board, so `current_key_row >= ROWS_PER_HAND` never occurs; RGB-off and
   animations only change duties. No staleness fallback needed. `rows_seen`
   implements the audit's "never publish uninitialised unseen rows".
4. **What breaks without `matrix_locked`/`first_scanned`?** Nothing. Removed.
5. **Was debounce a no-op?** Yes, and the fix makes it operative rather than
   surfacing chatter. `DEBOUNCE 5` stays for now — it is the first time it has
   ever had multiple samples in its window, so it should be observed before being
   retuned.
6. **Anything else on the path?** Nothing new surfaced. The one open item is the
   row-rate discrepancy below.

## Still open

**Per-row sampling is ~217/s against 1,041.7/s derived from the timer
configuration — a factor of ~4.8.** Six independent counters agree to within 4
counts over 12 s, so the measurement stands and the derivation has a wrong term.

Leading hypothesis, untested: `rgb_callback` overruns its 53 µs period. It
disables 35 pins, walks 17 columns calling `pwmEnableChannel`, and scans a matrix
row, all at 48 MHz. If that costs ~256 µs, the ISR runs back-to-back and its own
execution time — not the timer — sets the rate. That would also explain the
otherwise-odd ~330/s main loop on a 48 MHz M0, and it would mean raising
`SN32F2XX_RGB_PWM_FREQ` buys nothing.

**Next step is measurement, not analysis:** count `rgb_callback` entries and
accumulate its duration, expose both on a health page. Two diagnoses on this path
have already been retracted for reasoning ahead of measurement.

This does not affect the fix. 4.6 ms already samples a keypress 5–17 times. But
if the hypothesis holds there is another ~4.8x available in both scanning and
main-loop headroom, and an unexplained factor is exactly the shape of the thing
that hid this bug for so long.
