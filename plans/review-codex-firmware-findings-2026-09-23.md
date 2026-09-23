# Codex review of the 2026-09-23 firmware findings

`codex exec -m gpt-6-astra -c model_reasoning_effort=high -s read-only`, 2026-09-23 ~15:35, against [FIRMWARE-FINDINGS-2026-09-23.md](FIRMWARE-FINDINGS-2026-09-23.md). Verbatim; dispositions are in the findings file.

**The source confirms several defects, but does not establish one mechanism explaining both B signatures.** The strongest findings are the DMA ISR’s blanket flag clear, an unsafe IC bitfield write, invalid timeout classification, and incomplete SPI0 cleanup. The proposed LED-preemption mechanism needs correction: **the LED row ISR and SPI0 both have priority 3**, so the LED ISR cannot preempt SPI0. The serial fix is correct for its stated scope; USB needs an equivalent correction in `usb_lld_start_in()`. Sources: `hal_spi_v2_lld.c:115,257–258`; `lcd_bus.c:898–985`; `mcuconf.h:78–89`; `hal_spi_v2_lld.h:107–108`; `hal_usb_lld.c:744–748`.

I made no changes. I reviewed the working tree, both specified commits, the manual, and the existing ELF’s disassembly. Hardware measurements below are accepted from the brief, not independently reproduced. File references use the supplied repository paths; historical references explicitly name their commit.

**1. What can explain B?**

**[High confidence: verified defect; medium confidence: explanation of E3] The half-transfer handler can erase an unseen completion.**

The precise sequence is:

1. `sn32_flash_dma_isr()` reads RIS with HT set and TC clear.
2. Hardware finishes the transfer before the next IC write.
3. `IC = 0x3F` clears both HT and the newly arrived TC.
4. The branch tests the earlier RIS value, skips completion, and leaves `sn32_dma_busy` true.

That produces the reported finished-engine/no-flags/no-callback state. No preemption is necessary, although preemption widens the window. In the existing ELF, the critical accesses are adjacent instructions at `0x169d4` and `0x169d6`; this confirms a narrow real race, not merely a misleading source expression. Sources: [hal_spi_v2_lld.c:256](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:256), specifically lines 257–259 and 283–286.

**[High confidence] The LED ISR delays entry, but cannot interrupt that read/clear pair.**

SPI0’s default priority is 3, and `Fire()` reapplies it. The board configures all RGB PWM vectors at 3, UART2 at 1, and the backlight GPT at 2. USB also defaults to 1. Thus UART, GPT, and USB deserve preemption instrumentation; the LED ISR principally changes when SPI0 first gets serviced. Sources: `hal_spi_v2_lld.h:107–115`; `hal_spi_v2_lld.c:206`; [mcuconf.h:78](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/mcuconf.h:78); `hal_usb_lld.h:76–77`. Equal-priority handlers do not preempt each other under [ARM’s Cortex-M0 exception rules, §2.3.5](https://www.keil.com/dd/docs/datashts/arm/cortex_m0/r0p0/dui0497a_cortex_m0_r0p0_generic_ug.pdf).

**[High confidence: unsafe access; low confidence: cause of B] The FIFO IC bitfield write is a second flag-loss hazard.**

`spip->spi->IC_b.RXFIFOTHIC = true` compiles in the existing ELF to:

```text
0x16a6a  load IC
0x16a6c  OR 0x04
0x16a6e  store IC
```

It therefore writes back every other bit read from IC. The minimal `sn32_spi_t` view omits the DMA fields, but that does **not** prevent the generated 32-bit write from affecting them. IC is documented as write-only; neither the manual nor the vendor declaration promises useful readback. If its read returns DMA-clear bits as ones, the write clears those flags too. It is incorrect to assert that IC necessarily reads like RIS—the readback behavior must be measured. Sources: `hal_spi_v2_lld.c:115`; `sn32_spi.h:82–91`; `SN32F290.h:3009–3020`; manual `sn32f299.txt:9291–9310`.

Replace this with a literal full-register write, `IC = 1U << 2`. However, **that alone is not a demonstrated explanation**: the old dispatch normally excludes the FIFO handler when DMA flags are visible, and the patched dispatch excludes it throughout `sn32_dma_busy`. Log every FIFO-handler entry during DMA to establish whether this access actually participates. Sources: `hal_spi_v2_lld.c:301–303`; commit `2a17a73b48`, `SN32_SPI0_HANDLER`.

**[High confidence] The patched result does not yet prove an enabled interrupt was ignored.**

The timeout snapshot records RIS, counts, STAT, and—in console builds—DMACTRL. It does **not** record SPI0 IE, NVIC enable/pending, or the pre-lock PRIMASK. RIS explicitly reports flags regardless of IE. Therefore `RIS=0x2f` proves a peripheral completion flag exists, not that NVIC had an eligible pending interrupt for two seconds. Sources: [lcd_bus.c:946](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:946), lines 946–953; manual `sn32f299.txt:9252–9257`.

The patched handler should consume TC whenever it enters with `sn32_dma_busy=true`. If it enters with busy false, it clears TC without completing the blit. Distinguishing **no entry**, **wrong dispatch state**, and **wrong interrupt configuration** is essential. Source: commit `2a17a73b48`, `hal_spi_v2_lld.c:306–323`.

**[High confidence] The obvious NVIC-clear explanation has an ordering problem.**

`nvicEnableVector()` itself clears pending before enabling, so `Fire()` clears pending twice. But both clears precede `DMAEN=1`; ordinarily neither can erase this transfer’s later completion request. There is no post-start SPI0 NVIC clear in the normal HT path. Sources: `hal_spi_v2_lld.c:198–207,256–286`; `nvic.c:102–112,165–167`.

Also, sustained CPU load alone does not explain an eligible interrupt remaining pending while thread-mode code executes a million-loop wait. For a level-sensitive peripheral request, an asserted interrupt is eligible to re-pend after ISR return; a pulse-based implementation has different behavior. The SN32 interrupt-generation implementation therefore matters. Sources: `lcd_bus.c:908–911`; [ARM Cortex-M0 guide, §4.2.7](https://www.keil.com/dd/docs/datashts/arm/cortex_m0/r0p0/dui0497a_cortex_m0_r0p0_generic_ug.pdf).

**[Low confidence: hardware hypothesis] The patch may expose interrupt-request rearming behavior involving uncleared FIFO flags.**

The patch changes more than ownership dispatch: its HT handler stops clearing RX overflow, RX timeout, and FIFO-threshold flags. Meanwhile DMA fills SPI0’s unused RX FIFO. A silicon implementation that requires a shared request latch to deassert/rearm could retain TC in RIS without generating another request after HT. This would fit the patched signature, but **the manual does not establish such behavior**. Sources: original `hal_spi_v2_lld.c:257–258`; commit `2a17a73b48`, replacement `sn32_flash_dma_isr()`; brief `FIRMWARE-FINDINGS-2026-09-23.md:119–142`; manual `sn32f299.txt:9252–9284`.

Test this independently: retain state-based dispatch and observed-DMA-bit clearing, but also clear the non-DMA flags with a literal mask. Never write TC’s clear bit unless TC was observed. Compare against the identical build that leaves non-DMA flags alone. This isolates the patch’s changed clearing behavior from its changed dispatch.

**[Medium confidence: hypothesis] Timing can explain size selectivity without a special 660-byte hardware limit.**

The programmed pairs are:

| Bytes | CNT | HTCNT | Approximate wire duration at 24 MHz |
|---:|---:|---:|---:|
| 168 | 167 | 83 | 56 µs |
| 460 | 459 | 229 | 153 µs |
| 660 | 659 | 329 | 220 µs |

These follow directly from `Prepare()` and the SPI clock configuration. None is near the documented 28-bit count limit. Sources: `hal_spi_v2_lld.c:167,192–193`; manual `sn32f299.txt:9380–9409`.

A row ISR can delay HT servicing until very near TC. Short transfers can instead finish entirely during that delay, so the first RIS read sees both flags and succeeds. Consequently, shorter HT-to-TC spacing does **not** necessarily imply more read/clear failures. This is a plausible timing explanation, not proof of the exclusive 660-byte pattern. Sources: `hal_spi_v2_lld.c:257–259`; `sn32f2xx.c:661–749`; measured durations in `docs/leds.md:71–82`.

Clock glyphs use the same glyph queue and arm routine as text. They have different queue lengths, predecessor transfers, and opportunities for immediate synchronous work after the last queued glyph; these can change timing. I found no verified clock-only SPI0 writer bypassing the current guard. The last-glyph queue reset still occurs before DMA completes, but `bus_quiesce()` now guards subsequent CPU drawing and flash transactions. Sources: `display.c:1029–1057,2192–2214`; `lcd_bus.c:545–565,690–694,737–762,177–187,354–398`.

**2. Is `lcd_blit_wait()` sound, and is retry safe?**

**[High confidence] Start detection and fault classification are unsound.**

With invariant DMACNT, phase 1 detects a visible DMA flag, not transfer startup. The ISR can clear HT before polling observes it; a healthy longer transfer can then exhaust phase 1 before TC. Furthermore, `cnt==0` cannot identify completion for these multi-byte transfers. The brief’s classification table also omits the actual `!started` requirement for “never started.” Sources: `lcd_bus.c:898–913,958,982–985`; brief `FIRMWARE-FINDINGS-2026-09-23.md:123–131`.

Use:

- A per-arm generation and timestamp.
- Latched evidence of current-generation progress: CURCNT changing/resetting, observed HT/TC, or an observed DMAEN transition.
- CURCNT, DMAEN, and TX_EMPTY/BUSY together for completion assessment.
- A wall-clock deadline appropriate to transfer length, rather than CPU-loop counts.

**CURCNT equal to CNT alone is insufficient**, because it can be the previous transfer’s value. If current-generation evidence is unavailable, classify the state as ambiguous rather than claiming “never started.” Sources: `lcd_bus.c:755–757,775–776`; brief `FIRMWARE-FINDINGS-2026-09-23.md:127–138`; manual `sn32f299.txt:9370–9388,9414–9422`.

**[High confidence] `chSysLock()` makes the snapshot ISR-exclusive, not hardware-atomic.**

DMA continues between the individual RIS, count, STAT, and DMACTRL reads. A boundary-crossing snapshot can therefore mix states. Capture pre-lock PRIMASK separately, and use ordered/repeated reads or explicitly tolerate transitions during sampling. Sources: `lcd_bus.c:946–954`; `chcore.h:503–505`.

**[High confidence: display semantics; medium confidence: present implementation] Repainting the same glyph is safe even if it completed or partially completed.**

The retry reissues the original source address, complete panel window, and RAMWR command. It overwrites the same rectangle; it does not resume at the panel’s old write pointer. Thus the comments claiming retry is safe *only because nothing was transferred* are wrong. Sources: `lcd_bus.c:155–160,756,762–769,1005–1012`.

The qualification is hardware cleanup: abort does not reset SPI0’s FIFO/FSM or verify its shifter stopped. A completed, idle transfer followed by retry benefits from `Prepare()` resetting SPI0; a genuinely active abort needs stronger teardown. Sources: `hal_spi_v2_lld.c:188–190,228–251`. CURCNT completion is also not independent proof that exactly 330 correct pixels reached the panel—verify that with SCLK/CS capture.

**3. Fixes and board verification**

**[High confidence: recommended corrections; B root cause still unproven]**

1. **Eliminate IC read/modify/write and clear only observed DMA flags.** Reinstate ownership-based dispatch with instrumentation, and null the callback after consuming it. The current raw-RIS dispatch can act on a stale TC outside DMA and reuse the previous callback. Sources: `hal_spi_v2_lld.c:115,200–207,257–284,301–303`.

2. **Make both mode transitions obey the manual.** Reset SPI0’s FSM/FIFO after changing DL to 16 bits, and after returning to 8 bits once transmission is stopped. The current completion and abort paths restore FIFO interrupts while leaving SPI0 RX residue behind. Sources: `hal_spi_v2_lld.c:203–207,233–240,261–271`; manual `sn32f299.txt:9101–9103,9131–9138`.

3. **Make completion and recovery a shared, once-per-generation operation.** Normal IRQ completion and a polling fallback should use the same teardown. Do not silently call a timed-out shifter wait a success. Restore SPI1, clear stale state, release CS, and publish completion in a defined order. Sources: `hal_spi_v2_lld.c:228–251,261–284`; `lcd_bus.c:700–711,954–962`.

4. **Replace the two spin phases with deadline-based supervision available on every main-loop pass.** This should handle completed-without-callback, stalled, and ambiguous transfers regardless of whether another glyph is queued. Sources: `lcd_bus.c:898–911`; `display.c:2187–2208`.

I would instrument **before deploying the full fix**, preserving a small RAM trace and printing it later:

| Trace point | Required evidence |
|---|---|
| Immediately after DMA enable | Generation, CNT/HTCNT/CURCNT, DMACTRL, IE, NVIC enable/pending |
| Every SPI0 ISR entry | Same registers, busy flag, driver state, timestamp |
| Before/after every IC write | Writer ID, actual write mask, RIS before/after |
| HT handling and ISR exit | CURCNT, DMACTRL, late TC, timestamp |
| Timeout, before recovery | Above plus pre-lock PRIMASK, IPSR/ICSR and CS state |

These fill the specific gaps in `lcd_bus.c:775–792,946–953` and cover the accesses in `hal_spi_v2_lld.c:115,202,234,258`. Avoid reading IC as routine telemetry: instrument the existing RMW’s loaded operand in a diagnostic variant, then remove the RMW.

Run these discriminating experiments:

- **Force the old race:** insert a diagnostic delay after the HT RIS read that crosses TC. The old handler should lose completion; observed-bit clearing should retain it. Location: `hal_spi_v2_lld.c:257–259`.
- **Software-pend SPI0 after capturing a stuck patched transfer.** If completion immediately runs, investigate peripheral request generation/NVIC pending loss. If it does not, inspect enable/mask/dispatch state. Helper: `nvic.c:175`; dispatch: commit `2a17a73b48`.
- **Vary HTCNT while holding the transfer at 660 bytes.** This isolates interrupt timing from source, geometry, and total length. Then sweep nearby even lengths and vary LED phase. Location: `hal_spi_v2_lld.c:192–193`.
- **Test the existing FRESET and split experiments separately.** Splitting also adds a synchronous wait and changes timing, so success would not prove a count-register defect. Location: `lcd_bus.c:555–560,783–789`.
- **Capture SCLK, CS, ISR-entry GPIO, and UART/USB/GPT timing.** This distinguishes completed pixel output from engine-count completion and identifies actual preemptors. Relevant paths: `hal_spi_v2_lld.c:261–284`; `indicators.c:125–128`; `hal_serial_lld.c:269–327`; `hal_usb_lld.c:423–427`.

Use failures per transfer size, and count polling recoveries separately from IRQ completions. An apparent cure that merely hides missing callbacks is not verification. The current per-size statistics count only `BLIT_NEVER_STARTED`, so they undercount other classes. Source: `lcd_bus.c:1002`.

**4. Serial fix, USB, and the ACK observations**

**[High confidence] `c3ca7a9725` correctly fixes the identified lock violation.**

Queue notifications run under the caller’s lock; this is also true of `oqPutI()`, not just the two timeout APIs. ARMv6-M unlock unconditionally enables interrupts. Removing the nested lock/unlock keeps dequeue, TH write, and IE update inside the existing critical section. Removing the unmatched ISR unlock is also correct. Sources: commit `c3ca7a9725`; current `hal_serial_lld.c:303–314,330–348`; `hal_queues.c:492–507,538–563,662–689`; `chcore.h:503–534`.

It is complete for that specific bug, **not a complete serial-driver correctness fix**. Hardware overrun OE is omitted from both the status mask and `set_error()`, and the priority-1 interrupt service loop has no bound. Count hardware overrun separately and measure maximum ISR residency. Sources: `hal_serial_lld.c:249–257,270–327`; `sn32_uart.h:282`.

**[High confidence] USB needs the equivalent fix in `usb_lld_start_in()`.**

`usbStartTransmitI()` is I-class and calls the LLD under its caller’s lock. The LLD unlocks at line 746 before updating endpoint control at 748. A concrete thread path is `obqFlush()` → `obnotify()` → `usbStartTransmitI()`. Remove the redundant inner pair while preserving the caller’s lock through endpoint arming. Sources: [hal_usb_lld.c:732](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:732); `hal_usb.c:507–532`; `hal_buffers.c:833–846`; `usb_driver.c:56–72`.

Do not mechanically remove every USB lock pair: FIFO continuation accesses occur directly in ISR context, and setup reading has a different caller contract. Sources: `hal_usb_lld.c:369–389,683–700`.

**[High confidence: measurement confounder; medium confidence: explains some retries/orphans] ACK latency is measured at parsing, not arrival.**

The first-send timestamp is taken **after** `sdWrite()` returns, and the ACK timestamp is taken when main-loop parsing recognizes the token. The histogram therefore includes scheduling/parser delay and does not directly measure module turnaround. Sources: `ch582f_ajazz.c:501–516,905–921`.

More concretely, `ch582_task()` runs the retransmission pump **before draining RX**. An ACK can already be buffered when the timeout causes an unnecessary retransmission; parsing then acknowledges the original, and a later duplicate becomes an orphan. Drain and parse RX before deciding to retransmit. Sources: `ch582f_ajazz.c:491–497,884–921`.

**[High confidence: protocol vulnerability] An orphan arriving during the next frame is worse than an idle orphan.**

Every `61 0D 0A` pops whichever frame is currently in flight. There is no sequence matching. A delayed duplicate can therefore falsely acknowledge a newer frame. Sources: `ch582f_ajazz.c:512–525,917–921`.

Heartbeat traffic is **consistent** with orphan tokens, but not established by them. Measure RX-byte arrival in the UART ISR and capture both wire directions; run a quiet interval with polling/retries disabled to distinguish unsolicited tokens from delayed responses. Module wake-up latency remains a hypothesis, not the only explanation. Sources: `ch582f_ajazz.c:459–466,875–885`; `hal_serial_lld.c:286–295`.

**5. Other defects and fragilities**

- **[High confidence] SPI0 hand-back leaves stale RX data available to the ordinary FIFO handler.** Neither completion nor abort resets SPI0. Its FIFO handler drains whatever is present and completes on `rxidx >= count`, without checking that a FIFO transaction is active. This permits spurious completion and potentially premature completion of a subsequent CPU transfer. Sources: `hal_spi_v2_lld.c:105–118,233–240,263–271,482–493`.

- **[High confidence] The completion ISR’s bounded wait silently succeeds on exhaustion.** After 200,000 iterations it changes DL, restores interrupts, and calls the callback even if TX is still busy. Report a drain failure and recover explicitly. Source: `hal_spi_v2_lld.c:261–284`.

- **[High confidence] The brief’s unbounded SPI, serial, flash, and USB waits are real.** `spiSend()` uses `TIME_INFINITE`; `sdWrite` does likewise; internal-flash BUSY polling runs inside its interrupt-masked programming window; USB indirect SRAM polls are unbounded, with direct SRAM disabled by default. Sources: `hal_spi_v2.inc:636–646`; `hal_serial.h:268`; `hal_efl_lld.c:118–122,330–337`; `hal_usb_lld.c:148,154,197,203`; `hal_usb_lld.h:90–91`. Timeout handling must actually cancel/reset the operation before caller buffers become invalid.

- **[High confidence] Debug glyph pumping lacks recovery, and ordinary recovery depends on future queued work.** Debug retries busy forever. The normal pump returns immediately for an empty queue, including after arming its last glyph, so its 50 ms recovery is not a universal DMA deadline. Sources: `display.c:741–751,2187–2208,2214`.

- **[High confidence] Display shadows can claim pixels were painted when they were not.** `queue_line()` updates the shadow when enqueueing; drawing failures do not invalidate it, and the pump ignores recovery’s return value. A dropped glyph may remain absent until its text changes or another redraw invalidates the shadow. Sources: `display.c:2293–2305,2207–2209`; `lcd_bus.c:1015`.

- **[High confidence] The LED ISR uses thread-class PWM APIs.** It calls `pwmDisablePeriodicNotification()`, `pwmDisableChannel()`, and `pwmEnableChannel()` from interrupt context. These use thread-class lock/unlock wrappers. Convert to appropriate I-class operations with short ISR locks; do not mask interrupts for the whole roughly 188 µs handler. Sources: `sn32f2xx.c:475,527–533,664`; `hal_pwm.c:184–223,258–269`. This does not make equal-priority LED/SPI handlers preempt each other.

- **[High confidence: behavior; medium confidence: reachable impact] Internal flash programming can erase unrelated sector contents.** Encountering a non-erased eight-byte target causes a whole-sector erase without preserving the other lines. Verify that every caller guarantees erased destinations, or reject that condition rather than silently erasing. Source: `hal_efl_lld.c:290–320`.

- **[High confidence: workaround exists; low confidence: proposed silicon mechanism] Keep the sacrificial retained-record write, but distinguish observation from explanation.** The source commits magic and then writes `write_drain`; ordinary breadcrumb writes have no equivalent. The hardware experiment supports the workaround, but “a posted SRAM stage drained only by another write” remains a hypothesis, especially given the reported ineffective DSB. An interrupts-off, RAM-write-free hang could similarly lose its newest breadcrumb if that property generalizes. Sources: [watchdog_record.c:124](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c:124), lines 124–144 and 98–112; brief `FIRMWARE-FINDINGS-2026-09-23.md:26–43`. Verify across addresses, optimized disassembly, reset types, and an earliest-boot capture before broadening the claim.