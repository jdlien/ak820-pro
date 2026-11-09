Two P2 findings affect the diagnostic’s conclusions. I found no new board-safety blocker for the stated one-day test. Firmware line numbers below refer to `bc1b9f42cb`.

**P1**

| File:line | Finding | Scenario |
|---|---|---|
| — | None found. | No new hang, watchdog-reset or lost-key path established for the intended use. |

**P2**

| File:line | Finding | Scenario |
|---|---|---|
| [graphics/lcd_bus.c:322](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:322) | **The observation can mask the fault.** The extra STAT read, tests and conditional increment execute before returning to the caller’s DC flip. The archived ELF confirms this ordering. At 24 MHz, a byte takes only ~0.333 µs. | The original BUSY check exits while a final byte remains queued/shifting. Added bookkeeping gives it time to finish under the correct DC. It can also finish before the observation, leaving `old_queued == 0`. A clean mode-1 run is therefore inconclusive. |
| [graphics/lcd_bus.c:415](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:415) | **Long gaps alias into false minima.** The 16-bit subtraction is valid only for elapsed intervals below 65,536 ticks: ~349.525 ms. Nothing expires `dma_since_window`. | A CPU-painted window 65,537 ticks after the last DMA callback reports **1 tick (5.33 µs)** instead of ~349.531 ms, potentially replacing the minimum permanently. Use an extended timestamp or reject aged samples. |

**P3**

| File:line | Finding | Scenario |
|---|---|---|
| — | No additional confirmed findings. | — |

Answers to the remaining checks:

1. **Mode 1 matches the original daily-build send logic**, apart from the observation block. The omitted original `WDT_TEST_HOOKS` sections are inactive in daily builds. Source equivalence does not preserve timing: the dispatcher, window instrumentation and DMA callback instrumentation also change timing.

2. **Switching cannot split a send, window, or synchronous paint call.** USB HID dispatch and drawing execute sequentially on the main thread. It **can split a multi-pass repaint between glyphs**, and can occur while an already-armed DMA runs; changing `poll_mode` does not alter that DMA.

3. **The timestamp handoff is safe under the existing bus invariant.** The ISR publishes the volatile timestamp before `blit_done`; CPU painters quiesce the bus before reading it, and only main-thread code arms another DMA. `st_lld_get_counter()` reads the same hardware counter in either context. This measures callback-to-window time, including subsequent interrupt delays—not hardware-completion-to-window time. `window_is_dma_arm` correctly excludes DMA setup windows and resets even when their send fails. The reply’s offsets, widths, little-endian encoding and 32-byte bounds match `scripts/lcd_diag.py`. `zero` preserves the pending DMA marker, so its first subsequent interval may begin before zeroing.

4. **No source-level reason for an existing `build.sh daily` check to fail.** This branch-only command does not enable the prohibited dev hooks. Mode 1 retains the original unbounded RX-drain loop if `RX_EMPTY` permanently sticks; that is inherited behavior, with no evidence here that this diagnostic triggers it.

Reviewed read-only; no build run. The existing daily artifact’s hashes match its manifest. The readiness blocker is diagnostic validity, not a demonstrated board hazard.

**NOT READY**