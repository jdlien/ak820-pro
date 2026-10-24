# Codex review: the polled window (2026-10-24)

Prompt: [`review-prompt-s1-step4.txt`](review-prompt-s1-step4.txt). Reviewed: `gremlin/s1` `86c76027` and the build plan's revision 14. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Safe to flash `86c76027` to gremlin’s test board for this experiment. No blocker found.** I found one should-fix in fault-test coverage and two documentation notes. This does not establish that C10’s timing gate now passes.

I verified the commit against its parent `b3dcaeca`, the referenced ChibiOS submodule `5a1674e9`, and the requested plan diff using local Git objects. All reads stayed inside the permitted directory. Process execution was unavailable, so I did not build or run tests.

1. **Should-fix — HC_POLLFAULT no longer exercises partially delivered pixels.**  
   [lcd_bus.c:306](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:306), [fault consumption at line 196](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:196).

   The next polled send is now the one-byte CASET command. Mode 0 computes `stop = 1 / 2 = 0`, sends **nothing**, and fails. Mode 1 sends CASET and fails before its parameters. Both abort the operation before any pixels. Increasing the fault count fails CASET in successive operations; it does not advance the fault into later window phases.

   Consequently, the existing hook cannot substantiate recovery from partial pixels, fully delivered pixels reported failed, or failures halfway through the window. The cleanup code still works; the test’s coverage changed.

   **Fix:** distinguish window and pixel fault sites, or add a phase/skip selector. Retain both payload modes and exercise failures at each of the five window sends.

2. **Note — revision 14 gives the wrong reason for retaining the DMA window.**  
   [CONFIG-MENU-BUILD-PLAN.md:668](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:668), [lcd_bus.c:296](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:296).

   `spiSN32FlashDmaPrepare()` **does not write SPI0’s IE**. It configures eight-bit operation, programs DMA counts, and disables SPI1’s vector. [Fire():224](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:224) installs `DMATCIE | DMAHTIE`, **after** the window.

   The actual reason the current polled helper cannot replace this window is that [lcd_blit_flash():976](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:976) has already cleared `blit_done`. Its first polled send would refuse. Merely preserving IE would not make that substitution work.

   **Fix:** correct both explanations while retaining the current DMA window.

3. **Note — the timing justification overstates its own numbers.**  
   [CONFIG-MENU-BUILD-PLAN.md:14](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:14), [lcd_bus.c:292](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:292).

   A stated **1.8 ms window is one-third of a 5.4 ms piece**, not “most.” Those figures alone also do not establish that removing this cost brings a 17.05 ms pass below 15 ms.

   **Fix:** reconcile the measurements or say “a substantial part”; retain a fresh C10 run as the acceptance criterion.

The remaining correctness checks look sound:

- **DC/CS timing:** a successful [spi0_poll_send():202](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:202) receives all requested words and then waits for BUSY to clear. Thus it does not confuse “queued into TX” with “shifted out.” DC changes occur after the final clock, with additional cleanup and return instructions between them. Parameters remain under DC=data throughout their four-byte send, and CS remains asserted through the window and pixels.

  I found no required command-to-parameter delay that `tx8()` was supplying. The repository’s GC9107 driver also uses [four-byte address buffers without an intervening delay](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/painter/tft_panel/qp_tft_panel.c:66). That supports the protocol sequence; it is not a measured electrical timing certification.

- **Entry checks:** there are **five sends inside the window**, not six: lengths `1, 4, 1, 4, 1`. A one-chunk payload is the sixth. I found no expected healthy refusal. A successful poll leaves READY unchanged, RX empty, BUSY clear, and the threshold flag cleared before restoring `IE = 4`. The [FIFO interrupt handler](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:105) respects IE and ownership, so a pending FIFO interrupt cannot steal polling bytes. Row-ISR preemption consumes no polling iterations.

  After DMA, completion restores eight-bit FIFO operation and its interrupt enable; the idle FIFO handler drains residual RX. Main-thread serialization prevents another DMA preparation between window parts. The guard remains an invariant check, not a mechanism for arbitrating concurrent owners.

- **Mid-window failure:** every refusal/give-up sets `blit_lost`. A transfer timeout additionally resets the SPI FSM/FIFOs. The helper immediately stops issuing window parts. Fill and RAM blit release CS immediately; a stream releases it at `end()`, sending no further bytes meanwhile. A subsequent transaction issues a fresh CASET/RASET/RAMWR sequence, replacing any partial address setup. Releasing CS does not repair missing pixels—the owner’s repaint does.

- **Other bus paths:** the only remaining `lcd_window()` caller is the flash-DMA arm. Remaining `tx8()` users are that window, panel initialization, and `set_madctl()`. Initialization follows `spiStart()`; MADCTL quiesces DMA first. Animation uses the same DMA arm and quiesced MADCTL path. SPI1’s raw READ/address phase stays inside its disabled-vector window; ordinary SPID1 transactions quiesce first. I found no new route into polling with DMA prepared or active.

The loss propagation is preserved:

| Changed caller | Failure handling and recovery |
|---|---|
| [Fill:334](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:334) | Returns false with CS high. Menu callbacks return FAILED, immediately end/count the op, and prevent commit pending loss. Dashboard callers use the common loss flag. |
| [Stream begin:374](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:374) | Marks the stream broken but returns true: the stream is open and still requires `end()`. Bytes are dropped while accounting advances; `end()` releases scratch and CS. I found no current board caller of this stream API. |
| [RAM blit:431](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:431) | Skips pixels and releases CS. Even if drawing shadows advance, the pending loss triggers dashboard repair. |

[display_loss():3182](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3182) still dispatches recovery to the current owner: menu invalidation, debug-page invalidation, animation stop, or dashboard damage/restore. Owner changes may consume the old loss because the incoming owner clears and repaints.

Revision 14’s **behavioral scope matches the implementation**, apart from the explanatory corrections above. For the test-board run, check fresh C10 timing and zero unexpected poll failures, especially CPU drawing immediately after DMA, and restore payload-fault coverage before accepting the failure tests.
---

## Dispositions (Warren, 10-24)

Safe to flash, no blocker. Done before the flash:

1. **HC_POLLFAULT no longer reached the pixels: fixed.** It takes a skip
   count (`[.., HC_POLLFAULT, n, mode, skip]`). Skip 0-4 faults one of a
   fill's five window sends, 5 its first payload chunk; both modes are
   kept. The failure tests target each site.
2. **The wrong reason for the DMA window: corrected** in `lcd_bus.c` and the
   plan. `lcd_blit_flash()` has cleared `blit_done` by the time it sends its
   window, so a polled send's entry check would refuse. `Prepare()` doesn't
   write IE; `Fire()` does, after the window.
3. **"Most" of the piece: corrected to a third.** The next C10 run is the
   acceptance.
