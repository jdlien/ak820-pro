# Fix the one-row matrix publish (the aliasing beat)

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
- Higher effective sample rate means **more raw edges reaching debounce**, which
  could surface switch chatter that the slow sampling was accidentally masking.
  If phantom or doubled keys appear after this, that is the likely cause, and it
  is information about switch condition rather than a regression in the fix.
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
5. Does a ~17× increase in effective per-key sample rate change debounce
   behaviour in a way that needs `DEBOUNCE` retuning?
6. Anything else on this path that loses or reorders keystrokes and is not
   already recorded in `plans/INPUT-PATH-PLAN.md` §2 or `docs/hardware.md`?
