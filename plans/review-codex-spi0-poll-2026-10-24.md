# Codex review: the polled SPI0 bulk send (2026-10-24)

Prompt: [`review-prompt-spi0-poll.txt`](review-prompt-spi0-poll.txt). Reviewed: firmware `a03fc9d3` on `gremlin/fill-poll`. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**My review verdict: safe to flash `a03fc9d3` as-is to gremlin’s test board for this experiment. No blocker found.** I found three should-fix issues in failure handling and measurement, plus a timing limitation that needs board validation.

I verified the branch head, parent `4b899118`, and the three changed files against local Git objects. This was a static review; I did not build, flash, or run hardware tests. All reads stayed inside the requested directory.

1. **Should-fix — a failed chunk is reported to callers as successfully painted.**  
   [lcd_bus.c:160](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:160), [lcd_bus.c:266](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:266), [lcd_bus.c:304](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:304).

   On timeout, `spi0_poll_send()` resets the controller’s FSM/FIFOs and returns `void`. The fill and RAM-blit loops advance past the entire chunk; the stream subtracts all `n` bytes. They continue with CS asserted and the existing panel window.

   The panel received only a prefix. Subsequent chunks therefore occupy the wrong positions; an interrupted byte or RGB565 pair can also corrupt alignment. The menu nevertheless advances and eventually commits the slot because its fill callback returns success. Unlike DMA failure, polling failure does not set the loss flag that triggers repaint.

   **Fix:** return success/failure, stop the enclosing operation on failure, release CS, and invalidate/retry the complete rectangle with a fresh window. Do not continue from the next nominal chunk.

   Assuming `FRESET` successfully resets the FSM, subsequent commands can work: the next `spiSend` initializes its own indices. That repairs bus operation, not the damaged rectangle.

2. **Should-fix — the BUSY-tail timeout silently hands back a non-idle controller.**  
   [lcd_bus.c:167](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:167).

   If all RX bytes arrive but BUSY remains asserted past the bound, this branch merely breaks. It neither resets the FSM nor increments `spi0_poll_giveups` nor sets `PO_FAIL_SPI0_POLL`. It then restores IE and lets callers change CS/DC or start another transfer without establishing idle.

   **Fix:** route both timeout branches through one failure path: record the failure, reset the FSM/FIFOs, perform bounded cleanup, and return failure as above. The final drain should also be bounded if this helper promises recovery from stuck status signals.

   This is a fault-path defect, not an expected consequence of normal row-ISR preemption.

3. **Should-fix — the LED-rate script can accept incomplete painting as an improvement.**  
   [menu_s0_ledrate.py:69](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_ledrate.py:69), [menu_ops.c:147](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:147).

   The new failure **is externally visible** on dev builds: op 27 sub 5 exposes `PO_FAIL_SPI0_POLL` as `invariant_fail & 0x20`. However, this script ignores that field, mutation status, and `wait()`’s outcome. Its `pixels_done` deadline also expires silently. Combined with finding 1, dropped painting can produce an attractive ISR rate while the requested workload is not successfully rendered.

   The new count getter has no reporting caller; the sticky bit is the usable observation. The fuller session runner checks `invariant_fail`, but this measurement script does not.

   **Fix:** assert accepted mutations, expected terminal outcomes, `pixels_done`, and zero invariant failures; save those observations with the rates. Treat timeouts as failed measurements. Also calculate passes/s using actual elapsed time rather than `secs`: the final blocking toggle can overrun the nominal window. The ISR/s calculation already uses the board’s elapsed time.

4. **Note — 512-byte chunks bound storage and individual polling attempts, not main-loop latency.**  
   [lcd_bus.c:264](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:264), [menu_fixture.c:71](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:71), [menu_fixture.c:88](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:88).

   There is no yield between chunks. An F1 half-row sends **1,708 bytes** synchronously; an F2 tile sends **2,048 bytes**, both in one pass. Restoring row service consumes more of that pass’s wall time, although removing interrupt overhead may offset it. It is therefore not justified to assert either a slowdown or continued `<25 ms` passes from source alone.

   A pass can cross 25 ms without approaching the spin limit. The existing stall counters will correctly count that, including time spent preempted.

   **Fix if measured:** subdivide paint operations across main-loop passes using smaller rectangles and fresh windows. Returning between 512-byte pieces while leaving an open stream would violate the current ownership contract. For this flash, measure F1, F2, and dashboard RAM draws with `ge25`, worst-pass time, and completed-paint throughput.

The normal-path interrupt hand-off looks sound:

- **Driver idle:** fills and RAM blits quiesce DMA, then finish `lcd_window()` through synchronous `spiSend`. Streaming begins the same way; subsequent chunks follow a completed poll. `spiSend()` waits for completion and unlocks before returning. `bus_quiesce()` alone is not a general SPI-driver-idle check, but the surrounding call sequence supplies that guarantee.
- **No concurrent DMA starter found:** animation and glyph pumping run on the main thread. `blit_done_cb()` releases CS and marks completion; it does not chain a transfer. The backlight ISR does not paint. Raw-HID dispatch is performed by the main-thread task. There is no current path that prepares or fires DMA during a polled send.
- **IE versus NVIC:** masking the peripheral source is appropriate here. However, `IE = 0` masks **DMA interrupts too**; keeping the NVIC vector enabled would not rescue a genuinely overlapping DMA. Safety comes from quiescence and serialization.
- **Pending interrupts:** the driver examines raw RIS/FIFO state without checking IE or `SPI_ACTIVE` at [hal_spi_v2_lld.c:105](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:105). A pending vector alone, with empty RX and cleared relevant flags, does nothing. A stale threshold flag can execute idle completion; an interrupt during polling with RX data could steal bytes. I found no normal call path creating that condition: completed sends drain RX and clear the flag, and polling creates no enabled interrupt source. As defensive hardening, assert READY/no-DMA/empty-RX at entry and make FIFO dispatch respect its enable and ownership state. Do not disable the shared vector throughout the transfer.

The FIFO algorithm itself is correct under those entry conditions. `tx - rx <= 8` counts every outstanding word, including words already received but not drained. Preemption can fill RX to eight entries but cannot overflow it because nothing queues a ninth. `TX_FULL` prevents overfilling TX; `RX_EMPTY` gates reads. Receiving all `n` words establishes transfer progress more reliably than the BUSY-only `spi1_raw_byte()` idiom. The final BUSY wait, drain, and literal `IC = 1 << 2` are the right normal-path ordering.

DATA accesses match the driver’s byte-buffer writes and full-register reads. DL remains eight bits, and polling preserves the already-enabled DFDLY setting required at 24 MHz.

For **512 bytes**, the limit is **33,768 outer iterations**. The wire transfer is approximately **171 µs**, or 8,192 CPU cycles at 48 MHz. That leaves substantial polling headroom. Crucially, time spent inside the row ISR consumes **zero polling iterations**, while SPI can finish the queued bytes. **A healthy transfer should not hit this limit merely because the row ISR occupies 74% of wall time.** This is an execution-work bound, not a wall-clock deadline.

Finally, polling adds no interrupt-masked region. Backlight priority 2, USB priority 1, and UART priority **0** can preempt it; `docs/leds.md` is stale about UART priority, as [mcuconf.h:77](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/mcuconf.h:77) confirms. Main-thread USB processing, wireless parsing/ACK work, and key consumption still wait for the fill to return.

The existing fill/RAM-blit watchdog scopes remain effective and the watchdog is kicked only after a completed pass. They provide attribution and eventual recovery, not a 25 ms latency guarantee. Commands/windows still generate SPI interrupts, so the expected result is removal of the bulk-transfer disturbance, not necessarily zero repaint-related jitter.
---

## Dispositions (Warren, 10-24)

Verdict: safe to flash to gremlin's test board as it was, no blocker. All three
should-fixes were fixed before the flash anyway, in firmware `f2b107be` and the
script.

1. **A failed chunk reported as painted: fixed.** `spi0_poll_send()` returns
   success. On a give-up it sets `blit_lost`, the flag a DMA given up sets, so
   the owner's loss handler repaints (C1). `lcd_fill_rect` and `tx_pixels` stop
   at the failed chunk and release CS. A broken stream drops the rest of its
   bytes (`stream_broken`) and its owner repaints. Retrying the rectangle in
   place is left to that repaint, as for DMA.
2. **The BUSY-tail timeout: fixed.** Both timeouts go through one failure path:
   FRESET, the count, `PO_FAIL_SPI0_POLL`, `blit_lost`. The final RX drain is
   bounded (16 reads).
3. **The script could accept incomplete painting: fixed.**
   `scripts/menu_s0_ledrate.py` now fails the run on:
   - a refused or non-`done` sub 0;
   - `pixels_done` not reached in 2 s;
   - a non-zero `invariant_fail` (which includes `0x20`, the new bit).

   passes/s now uses the real elapsed time. The baseline on `4b899118` was
   rerun under these checks (`ledrate-baseline-4b899118.json`): every
   repaint completed, and the toggling windows read 3,039 and 3,062 row
   ISR/s against 3,725 on the dashboard.
4. **Main-loop latency (note): to be measured.** The flash's run records ge25,
   the worst pass, and ge10 per window, against the baseline. If the polled
   fills push a pass over 25 ms, the fix is codex's: smaller rectangles
   across passes, never an open stream across them.

Defensive hardening (an entry assert of READY, no DMA and empty RX; a FIFO
dispatch that respects IE): not done for the prototype. Noted for S1, if the
polled path is kept. The stale UART priority in `docs/leds.md` (codex: UART is
0, per `mcuconf.h:77`) is noted for that doc's next edit.
