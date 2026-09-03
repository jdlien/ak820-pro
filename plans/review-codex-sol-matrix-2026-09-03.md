# Codex/gpt-5.6-sol audit — MATRIX-PUBLISH-PLAN, 2026-09-03

Four focused questions. Verdict: aliasing mechanism CONFIRMED (with corrected
numbers), no starvation risk, and a SIMPLER fix than the staging buffer.

---

1. **HIGH — Q3:** The staging design is non-tearing only if `matrix_scanned` remains an ownership latch: ISR copies only while false; main reads only while true, then clears it ([sn32f2xx.c:402](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:402), [sn32f2xx.c:874](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:874)). The flag is already `volatile`, but `volatile` does not order nonvolatile `shared_matrix` accesses ([sn32f2xx.c:107](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:107)). Use `_Atomic bool` acquire/release for both ownership handoffs, or compiler barriers before publishing true, after observing true, and before clearing false. `staging`, its mask, and `shared_matrix` need not be volatile. Cortex-M0 SRAM needs no extra hardware barrier once compiler ordering and single-core ownership are correct.

2. **MEDIUM — Q1:** Aliasing is the correct mechanism, but 6267/s is not. PWM is 4.8 MHz with a 256-tick period, hence 18,750 ISR/s ([config.h:107](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:107), [config.h:123](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:123), [sn32f2xx.c:124](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:124)). The key row advances every third ISR: exactly 6,250 rows/s, or 1,041.667 six-row cycles/s ([sn32f2xx.c:464](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:464)). The beat is `1 / |1041.667 − 3·fconsume|`; rounding 18,750 to 18,800 and consumption to 344/s badly magnifies error near this resonance. The factor-of-two error is in the small detuning, not the physical row rate. Local cadence around 345/s plus jitter produces the observed gaps. “57/s predicted/measured” is tautological—one accepted row per consume divided among six rows—not confirmation of the beat model.

3. **LOW — Q2:** None of the listed normal paths causes permanent starvation. Flash pauses both advancement and scanning, so the partial mask resumes afterward ([sn32f2xx.c:667](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:667)). Here RGB rows equal the six matrix rows, so `current_key_row >= ROWS_PER_HAND` never occurs ([config.h:6](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:6), [sn32f2xx.c:478](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:478)). RGB-off and animation only change duties; the PWM callback keeps running, and scanning precedes output enable ([sn32f2xx.c:480](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:480), [sn32f2xx.c:756](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:756)). No incomplete-publish fallback is required. For fault containment, watchdog missing completion only while `EFLD1.state != FLASH_PGM`; on expiry reinitialize/reset and retain the last complete snapshot. Never publish uninitialized unseen rows.

4. **RECOMMENDATION — Q4:** Yes: scan directly into `shared_matrix` on every actual key-row transition (`last_key_row != current_key_row`), set `matrix_scanned` as a dirty flag, and wrap main’s compare/copy/clear in `chSysLock()`/`chSysUnlock()`. That yields ≈1,041.7 samples/s per row without a staging buffer or ISR `memcpy`; optionally suppress readiness until a six-bit initial `rows_seen` mask is complete. The driver already uses this exact lock pattern to protect a main/ISR buffer copy ([sn32f2xx.c:813](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:813)).

---

## What was done with it

**Q4 was adopted verbatim.** The staging buffer in the plan was dropped in
favour of the audit's simpler scheme: scan straight into `shared_matrix` on
every `last_key != current_key` transition, demote `matrix_scanned` to a dirty
flag, and wrap the main loop's compare/copy/clear in `chSysLock()` /
`chSysUnlock()`. The `rows_seen` mask suggested at the end of Q4 was included,
so the loop cannot consume uninitialised rows after boot.

**Q3 (HIGH) was resolved by adopting Q4 rather than by adding atomics.** The
finding is correct about the *staging* design it was asked to review: there,
both sides touched the buffer concurrently and `volatile` on the flag would not
have ordered the nonvolatile buffer accesses. The shipped design has no such
handoff. `chSysLock()` masks interrupts on Cortex-M0 and carries compiler
barriers, so an ISR write to `shared_matrix` either completes entirely before
the critical section or begins entirely after it — reordering inside the ISR
cannot be observed, because the ISR itself is atomic with respect to the locked
copy. No `_Atomic` was needed.

The one deliberate unlocked read of `shared_matrix` is
`input_note_consume()`, which runs before the lock because it reads the timer.
A torn read there skews a health counter and nothing else; this is stated in a
comment at the call site.

**Q1 (MEDIUM) corrected the plan's arithmetic and the correction was taken.**
The plan said 6267 rows/s from rounding 18,750 ISR/s to 18,800; the exact
figures (4.8 MHz / 256 = 18,750 ISR/s, row advancing every third ISR = 6,250
rows/s = 1,041.667 six-row cycles/s) are now what `sn32f2xx.c` and
`docs/hardware.md` state. The audit is also right that the "57/s
predicted/measured" agreement in the plan was tautological — one row accepted
per consume, divided six ways, is true under the old code regardless of whether
the beat model holds. It was not the confirmation the plan claimed.

**Q2 (LOW) required no change.** Its recommendation to never publish
uninitialised unseen rows is what `rows_seen` implements.

## Measured outcome, same day, on hardware

| | before | after |
|---|---|---|
| worst per-row sampling gap | 156–169 ms | **5–7 ms** |
| samples per row per second | ~57 | **~217** |
| spread across the six rows (12 s) | 825–897 | **2599–2603** |
| `scan_rate` (main loop) | 326–378 | 301–338 |
| `count_ge_25ms_nonflash` | 0 | 0 |

The near-zero spread is the signature that the aliasing is gone: rows are now
sampled in strict rotation instead of being phase-selected.

**Open, and traceable to this audit:** measured per-row sampling is ~217/s,
against the 1,041.7/s the audit derives from the timer configuration — a factor
of ~4.8. The measurement is not in doubt (six independent counters agree to
within 4 counts over 12 s), so the derivation has a wrong term in it. It does
not affect the fix — 4.6 ms already samples a 25–80 ms keypress 5–17 times —
but it means up to another ~5x may be available, and an unexplained factor is
exactly the shape of thing that caused two retracted diagnoses in this project.
