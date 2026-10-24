# Codex review: the DMA arm's polled window, revision 15 (2026-10-24)

Prompt: [`review-prompt-s1-step6.txt`](review-prompt-s1-step6.txt). Reviewed: `gremlin/s1` `7c157834`. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Safe to flash `7c157834` to gremlin’s test board for this experiment. No blocker found.** I found two diagnostic should-fixes and one documentation note. This is a static-review judgment; a fresh C10 run must establish the timing result.

I compared the commit with parent `9902ff5b`, verified the reviewed sources against Git objects, and checked the pinned ChibiOS driver at `5a1674e9`. All reads stayed inside the workspace. Process execution was unavailable, so I did not build or run tests.

1. **Should-fix — a refused window counts as an issued DMA.**  
   [lcd_bus.c:971](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:971)

   `blit_count`, `blits_issued`, and `size_arms` advance before the window can fail. A refusal therefore increases the soak’s DMA-exposure denominator without reaching `Fire()`. Under `CONSOLE_ENABLE`, `arms_total` does **not** advance, so the two arm counts diverge. The saved parameters also make the next diagnostic’s “previous transfer” describe an attempt that never armed.

   **Fix:** commit issued-arm counters and last-arm bookkeeping after the window succeeds, before `Fire()`. Keep ISR-visible metadata initialized before firing. Count preparation failures separately if wanted.

   This affects diagnostic accuracy, not bus recovery.

2. **Should-fix — a failed retry window leaves the operation’s completion timestamp too early.**  
   [lcd_bus.c:995](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:995), [retry at line 1248](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1248)

   Scenario: an asynchronous menu glyph loses completion; `lcd_blit_wait()` aborts it and records `blit_end_tick16`; its retry then gives up during the polled window. The new early return never updates that timestamp. [settle_ops():79](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:79) consequently ends the operation at the **first abort**, excluding the retry window and cleanup from its latency.

   **Fix:** record the final endpoint after releasing CS and completing `dma_unprepare()` on window failure. That also makes the endpoint consistent with the existing “completed or given up” contract.

   Recovery and loss propagation still work; the defect is timing underreporting.

3. **Note — the ordering documentation is inconsistent and ambiguously worded.**  
   [GREMLIN-RESULTS.md:718](C:/Users/jdlien/code/ak820-pro/plans/GREMLIN-RESULTS.md:718), [revision 15:15](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:15), [lcd_bus.c:989](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:989)

   Section 15 still proposes sending the window **before Prepare**, contrary to the implementation. Revision 15 and the code correctly place it afterward, but “nothing may go out between it and the pixels with CS low” literally contradicts sending the window there.

   **Fix:** state the intended invariant directly: “Run Prepare with panel CS high; then assert CS and send the window and pixels without another Prepare/SPIEN reconfiguration.” Also change “~135 glyphs a pass each” to “~135 glyphs, one per pass.” The claimed speedup remains a measurement to establish.

The four safety questions resolve as follows.

**1. Polling in Prepare’s state is sound.**

[Prepare/configuration:173](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:173) leaves eight-bit, mode-zero SPI0, RX threshold zero, reset FIFOs, and `DMAEN=0`. Loaded counts and `DIR=0` do not move data until DMA is enabled.

`DFETCH_EN` is already enabled by ordinary driver configuration at this clock; it does not remove the need to drain received words. The polled helper does that explicitly, limits outstanding words, and waits for BUSY to clear before changing DC.

The relevant IE difference is safe:

- Polling masks **SPI0** sources; SPI1’s RX-threshold enable—the DMA request gate—remains untouched.
- The pinned [FIFO handler:105](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:105) respects IE and ownership. A pending FIFO interrupt cannot steal polling bytes.
- Success drains RX, clears only RXFIFOTHIC, and restores `IE=4`. It leaves the DMA counts/configuration intact.
- `Fire()` then clears flags/pending state, selects sixteen-bit words, installs DMA interrupt enables, and enables DMA.

No new FRESET occurs on the successful window path. The historical missing FRESET at the eight-to-sixteen-bit transition remains unchanged; this patch neither resolves nor newly introduces that known concern.

**2. Moving `blit_done=false` is safe with the current serialization.**

Every arm and relevant busy reader runs on the main thread. The animation cannot re-enter `blit_arm()`, and RTC/internal-flash work cannot run midway through this synchronous window. The DMA callback paints nothing; the preceding transfer has been quiesced before metadata changes.

Thus `blit_done=true` during preparation does not admit another current caller. It becomes false before the flash READ and `Fire()`, so a real completion cannot be overwritten by a later false store.

The WDT scope still covers the whole function, including preparation/window failure; its cleanup attribute handles early returns. Console command/fire timing retains its previous scope, excluding the panel window. The counter exception is finding 1.

**CS remains high during Prepare**, then goes low inside `lcd_window_polled()`, exactly preserving the relevant ordering.

**3. The give-up path restores usable buses.**

[dma_unprepare():939](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:939) restores SPI1’s FIFO, flags, pending state, vector, and priority. FLASH_CS has not been asserted yet. SPID1’s driver state was never changed.

SPI0 remains eight-bit with DMA disabled. A polling timeout resets its FSM/FIFOs and restores FIFO IE; its counts are inert and overwritten by the next Prepare. Ordinary `spiSend()` initializes its own transfer indices.

`sn32_dma_flash` remains set, but **that alone does not activate anything**: `sn32_dma_busy` remains false, no new callback was installed, and no DMA ran to generate completion flags. The next Prepare overwrites the pointer. Clearing it through an LLD-owned cancellation API would improve encapsulation, but I found no current failure caused by retaining it.

Caller handling is sufficient:

| Caller | Window-failure behavior |
|---|---|
| `lcd_clear_rect_ok` | Returns false immediately; no false successful clear. |
| `lcd_blit_wait` retry | Short-circuits the wait and returns false; polling already set `blit_lost`. |
| Glyph try | Still returns true and consumes the glyph. Pending loss prevents menu/debug completion and triggers invalidation/repaint. |
| Image/synchronous glyph | Ignores the boolean; the idle wait returns immediately. Loss remains pending for owner recovery. |
| Animation `blit_arm` | Ignores the boolean; owner loss handling stops animation and restores the dashboard. |
| Probe | Ignores it, performs an idle wait, releases both CS lines, and preserves the loss flag. |

The ignored booleans therefore do **not** silently discard recovery. [display_loss():3196](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3196) dispatches the necessary owner action.

**4. Test-board acceptance should cover the newly prepared failure path.**

Exercise both fault modes at all five DMA-window sends, then verify a SPI1 read, SPI0 CPU draw, and subsequent DMA succeed. Include a lost completion followed by a retry-window failure to cover finding 2. Run fresh C10 timing and check for unexpected poll failures. The earlier fill-window tests do not by themselves exercise `dma_unprepare()`.
---

## Dispositions (Warren, 10-24)

Safe to flash, no blocker; the four safety questions resolved in the
change's favour. Done before the flash:

1. **A refused window counted as an issued DMA: fixed.** `blit_count`,
   `blits_issued` and the console's arm bookkeeping, and the saved
   transfer parameters, advance only after the window succeeds.
2. **A failed retry window's early endpoint: fixed.** The give-up path
   stamps `blit_end_tick16` after `cs(1)` and `dma_unprepare()`.
3. **The wording: fixed.** The code comment and revision 15 now say Prepare
   runs with the panel's CS high, then the window asserts CS, and the
   window and pixels follow with no further reconfiguration. §15 of the
   results says "after Prepare", and "~135 glyphs, one per pass".

**The board's failure-path tests** (HC_POLLFAULT at each of the five DMA
window sends in both modes, then a SPI1 read, a CPU draw and a DMA; and a
lost completion followed by a failing retry window) are on the list in
`WARREN-STATUS.md`, to run on the devfault build after the gate.
