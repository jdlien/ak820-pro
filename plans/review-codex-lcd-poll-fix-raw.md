No P1 or P2 regressions found. One P3 diagnostic issue. Reviewed `862acd7b0c` and the host decoders read-only; ran no build.

**P1**

| File:line | Finding | Scenario |
|---|---|---|
| — | None found. | — |

**P2**

| File:line | Finding | Scenario |
|---|---|---|
| — | None introduced by this commit. | — |

**P3**

| File:line | Finding | Scenario |
|---|---|---|
| [lcd_bus.c:252](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:252), [256](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:256) | `spi0_poll_late` can miss a send that waited for TX to empty. Use the same status observation for the decision and counter. | The first read sees `TX_EMPTY == 0`; the last queued byte enters the shifter before the second read, which sees `1`. `waited` remains false. Preemption enlarges this opportunity. Transfer completion remains correct, but zero does not establish that no FIFO wait occurred. |

The send’s correctness:

- **Entry drain:** With the bus quiesced, `blit_done`, `SPI_READY`, and no shifting, discarding RX leftovers is safe. Sixteen reads cover the eight-entry FIFO; persistent nonempty status returns failure. The idle driver IRQ may also drain leftovers before masking, so `strays` is not a complete census of everything left by DMA.
- **Receive accounting:** The new guard maintains `rx <= tx <= stop`. Consequently, reaching `rx == stop` proves every requested byte was written to DATA. Each buffer index is written once. A late stray can still count as an outstanding byte’s echo; the new completion fence supplies the protection in that case.
- **Exit:** With the documented status semantics and no competing producer, three observations of `TX_EMPTY && !BUSY` prevent successful return with queued bytes or an active shifter. The caller retains CS/DC throughout. The final bounded drain removes remaining echoes before the literal threshold-clear and IE restoration.
- **Failures and injection:** Receive-progress and completion timeouts reset the FSM/FIFOs, latch `blit_lost`, and return false. Entry rejection preserves another owner’s state. WDT mode 0 sends `floor(n/2)` bytes—including zero for a one-byte command—then fails; mode 1 sends everything then fails. Both retain cleanup and caller-abort behavior. Neither injection actually tests a stuck status bit.
- **Bounds:** For a 224-byte payload, the receive-loop threshold is 15,336 iterations and the combined completion threshold 16,336. Actual callers send at most 512 bytes per invocation, so arithmetic cannot overflow. These are work limits, not wall-clock deadlines; ISR time does not consume them.

There is an **existing hang limitation**, unchanged by this commit: the inner RX drain at [lcd_bus.c:236](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:236) has no spin check. If `RX_EMPTY` becomes permanently false during the transfer, execution never reaches the outer timeout. Thus the function is not bounded against every possible peripheral-status failure.

All callers remain compatible:

- `tx_pixels`, `lcd_fill_rect_ok`, and `lcd_stream_bytes` stop the affected operation after failure.
- All five sends in `lcd_window_polled` stop before the next DC transition on failure.
- Its four callers—fill, stream begin, RAM blit, and flash blit—retain CS cleanup and loss recovery. None requires refusal merely because entry RX contains leftovers, or requires an early BUSY-only return.
- [lcd_blit_flash:1196](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1196) remains valid between Prepare and Fire: Prepare leaves DMA disabled and `blit_done` true. Successful polling preserves the programmed DMA configuration. A failed window invokes `dma_unprepare()` and returns without Fire.

If the hypothesis is wrong, the normal-path cost increases modestly: one comparison/branch per received entry and three idle observations per send. A glyph has six sends: five window parts plus its 224-byte payload. Counter increments occur only on exceptional observations. Polling remains in thread context with the row ISR enabled, so the shared SPI0/row priority does not turn these waits into ISR blocking. DMA teardown is unchanged. There is no new algorithmic reason for a 25 ms glyph stall, although actual timing remains unmeasured.

Health compatibility is correct:

- [health.c:384](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/health.c:384) writes little-endian `strays` at payload bytes **24–25**, then `late` at **26–27**. Comments `26` and `28` denote the cursor after each write.
- [Python:221](/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:221) uses the correct 28-byte `<2I2H3I2H` layout. [Rust:583](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:583) correctly reads full-report offsets **28** and **30**.
- Older firmware explicitly zeroed those four bytes. Older Python discards the reserved u32; older Rust ignores it. Existing fields and report length are unchanged.
- Both counters saturate at 65,535 and persist until reboot; `health_reset()` does not clear them.

READY