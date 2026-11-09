One P2 is fixed; the timing P2 remains. Firmware line numbers below refer to `b7c12ca088`.

**P1**

| Finding | Result |
|---|---|
| New board-safety regression | None established. |

**P2**

| Original finding | Verdict | Trace |
|---|---|---|
| Observation can mask mode 1’s fault | **Fixed** | [lcd_bus.c:304](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:304) contains no added observation. After excluding comments, whitespace and the original’s daily-disabled `WDT_TEST_HOOKS` blocks, its executable source matches `4790208267`’s send exactly. The BUSY wait flows directly into the original cleanup and return. Reply bytes 7–8 remain zero; [lcd_diag.py:33](/Users/jdlien/code/ak820-pro/scripts/lcd_diag.py:33) skips them without shifting subsequent fields. |
| Long gaps alias into false minima | **Not fixed** | [lcd_bus.c:412](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:412) checks a **16-bit modular pass difference**, but `lcd_diag_pass()` only increments the counter—it never expires `dma_since_window`. After **65,536 + n passes**, the age reads **n**, admitting stale samples whenever `n ≤ 8`. The tick subtraction can therefore still produce a false minimum. |

The pass-counter trace:

- `housekeeping_task_kb()` calls `display_pass_end()` unconditionally at [ak820pro.c:682](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:682), outside the 10 Hz block. That calls `lcd_diag_pass()` once per pass.
- The completion ISR records the tick, reads `lcd_pass_no` into `dma_done_pass`, and publishes the pending marker before `blit_done` at [lcd_bus.c:1206](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1206). The aligned volatile 16-bit handoff is sound: the ISR only reads the main-thread counter, and CPU painters quiesce DMA before consuming the stamps.
- An ordinary adjacent wrap, `65535 → 0`, correctly gives age **1**. The defect is retaining a pending sample through an **entire counter cycle**.
- A reachable case is an idle USB dashboard with clock off, no active playback/text changes, and stable battery/status. No periodic paint must replace or consume the marker. Caps-on later takes `draw_locks_diff()` → `draw_padlock()` → `lcd_fill_rect_ok()` → `lcd_window_polled()` before its label DMA. Landing in the wrapped acceptance interval admits the stale timestamp.
- `zero` now clears a pending marker correctly, but automatic expiration is still missing. Expiring it when its age first exceeds eight passes would close this wrap hole.

**P3**

| Finding | Result |
|---|---|
| Additional confirmed findings | None. Source equivalence does not establish identical binary timing; the dispatcher and surrounding instrumentation remain. |

Read-only review; nothing changed and no build run.

**NOT READY**