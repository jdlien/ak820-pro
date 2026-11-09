**The best fit is a title accepted into RAM whose painting silently went wrong, leaving the shadow ahead of the panel.** That explains why later transport updates work and identical title refreshes do not repair “Implosion.” I found the mechanism that makes such damage persist, but **not a proven software trigger for the corrupt writes**.

I verified the clean worktree at `4790208267` and its clean, pinned ChibiOS submodule. I read only inside the repository, including both health captures and the photograph. Nothing changed; no build or board test ran.

Two corrections matter:

- The photographed face appears to be the large song face. Its glyphs are **8×14 CPU-polled writes from internal-flash bitmaps**, not asset-flash DMA. Cozette uses DMA. Both paths use `lcd_window_polled`. [lcd_bus.c:898](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:898)
- This revision’s channel clear is **x109–121, y0–23**, followed by the status-font digit at **(109,2)**. The backlog’s geometry is slightly off. Wrapping within that clear window cannot reach x122–127. [display.c:1505](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:1505), [display.c:1550](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:1550)

**Ranked candidates**

1. **Silent SPI0 window/data-framing failure during an accepted title repaint, followed by optimistic shadowing. Best overall fit; trigger unverified.**

   The exact software sequence would be:

   1. Type 1 validates and commits both lines. The setters copy the new strings, renew the title lease and set `text_dirty`. [ch582f_ajazz.c:600](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:600), [display.c:2278](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:2278)
   2. Assuming the existing two-line layout and font, “Tonebox” and the play icon are unchanged. The title becomes the displayed 15-character prefix, `Launch Disinteg`. All nine positions formerly occupied by `Implosion` differ; six more cells are added. **This ordinary transition requires no clear.** [display.c:3316](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3316), [display.c:3203](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3203)
   3. `queue_line` immediately records that new prefix as a valid shadow, **before the glyphs reach the panel**. The pump subsequently consumes one glyph per pass. [display.c:3213](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3213), [display.c:2990](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:2990)
   4. **The hypothesized failure:** SPI0 reports successful sends, but the panel interprets some window commands or pixel bytes incorrectly. Payload then reaches a stale/incorrect window or has incorrect framing. `spi0_poll_send` verifies peripheral receive progress and BUSY completion; it cannot verify what window or pixels the panel accepted. [lcd_bus.c:182](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:182), [lcd_bus.c:303](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:303)
   5. No detected failure means no `blit_lost`. The queue drains, while RAM and the shadow say “Launch…”. Identical refreshes renew `text_stamp` but do not dirty the text. Type 3 updates playback normally. The panel can therefore retain “Implosion” indefinitely while those refreshes continue.

   This explains the old title, correct new duration, persistence and zero health faults together. The x≈92 block is within the new title’s added cells: large-face cell 11 starts at x90, beyond “Implosion”’s last cell at x73.

   **Limits:** one missed window or one bad glyph is insufficient. Preserving all nine old characters requires several writes to miss their intended cells, or another operation to restore them. Every glyph sends its own complete window. Also, the normal title update neither clears nor paints row 41; the full-width stripe requires misaddressing or another drawing operation. I cannot identify a particular earlier clear as its destination.

   A concrete boundary worth instrumenting is the DMA mode handoff: SPI0 changes 8→16 bits with panel CS asserted, then changes 16→8 and resets SPI1 before the callback releases the chip selects. Those operations exist; **extra clocks or framing damage from them are not established**. [hal_spi_v2_lld.c:218](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:218), [hal_spi_v2_lld.c:306](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:306)

2. **Type 1 lost/rejected, type 3 applied to the old slot, plus independent pixel corruption. Definitely reachable, but a poor complete explanation of the duration.**

   Yes to A. Losing an LED transition, a Caps change, CRC/range/trailer failure, timeout or link reset can discard type 1. A later frame starts independently. The sequence byte is recorded, not used to bind transport to a title. [lockchan.c:164](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/lockchan.c:164), [lockchan.c:138](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/lockchan.c:138)

   After successful framing, media validation or the **10-second raw-HID ownership lease** can still reject the title. That lease could expire between type 1 and type 3. Type 3 then checks only that *some* title lease remains; it has no title identifier. [ch582f_ajazz.c:568](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:568)

   The supplied title itself is valid: seven artist bytes, 21 title bytes, printable ASCII, 30-byte payload. There is no content-length reason to reject it. [lockchan_media.c:32](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/lockchan_media.c:32)

   **The timing problem is substantial:**

   - Only type 1 renews the title’s **180-second awake-time lease**.
   - Type 3 does not renew it.
   - Playback lasts at most **135 seconds**, further limited to the title lease remaining. [display.c:2374](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:2374), [ch582f_ajazz.c:582](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:582)

   Consequently, the single 12:02:50 transport cannot alone sustain the readout until 12:06:37. Further transport reception is needed under normal continuous operation. Keeping old **RAM** text for that interval also needs additional circumstances beyond one lost new title.

   The host source repeats changes after two seconds and refreshes every 60 seconds; **those repeats and refreshes are omitted from its ordinary change log**. Thus 11:46:07 is not necessarily the last transmission of “Implosion,” and 12:02:47 is not necessarily the only transmission of “Launch…”. [policy.rs:20](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/policy.rs:20), [sender.rs:944](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:944)

   This candidate explains a temporary title/time mismatch without display corruption. It cannot generate the junk itself, and sustained failure through refreshes is harder to reconcile than candidate 1.

3. **Bad flash-source data or an abnormal DMA tail/completion. Plausible for the first speckle; weak as the common cause.**

   The source-command sequence writes READ/address bytes using a BUSY-only drain, with no returned error or payload validation. A bad source transaction could therefore clock incorrect bytes through a DMA that completes normally. Clears use the black frame at address zero. [lcd_bus.c:593](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:593), [lcd_bus.c:1187](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1187), [lcd_bus.c:491](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:491)

   Another silent possibility is an abnormal completion accepted as successful: the handler accepts DMATC, or its rescue observes DMAEN clear, without requiring `CURCNT` to equal the programmed count. Short-completion checking exists only as console diagnostics and does not itself latch a repaint. [hal_spi_v2_lld.c:297](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:297), [lcd_bus.c:1088](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1088)

   But there is no demonstrated source fault, premature completion or extra tail here. **Delaying the completion ISR alone does not establish extra pixels:** the handler waits for TX empty and BUSY clear before teardown.

   A flash-source-only failure also cannot directly corrupt the large song glyph payloads. A permanently damaged black frame should tend to reproduce damage on later clears, which makes the successful Fn+D cleanup evidence against that narrower explanation.

**What the staged paint and failure paths actually protect**

The normal sequence is `TS_ICON_CLEAR → TS_ICON_DRAW → TS_LINE_A → TS_LINE_B → TS_ICON_FIX`. Two-line layouts paint line 0 then line 1; other layouts retire line 1 first to avoid clearing over the new larger line 0. Each pass permits one heavy clear/icon step. [display.c:3355](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3355)

`queue_line` distinguishes unchanged cells, moved runs and unknown contents. Unknown contents cause a full-width clear at that line’s y/height; shortened strings clear their tail. `band_clear` invalidates intersecting shadows. These are software bookkeeping guarantees, dependent on successful physical writes. [display.c:2907](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:2907), [display.c:3173](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3173)

**I found no detected-window-failure path that proceeds with payload into the old window:**

- A DMA window failure returns before `Fire()`, releases panel CS and unprepares SPI1. [lcd_bus.c:1160](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1160)
- A CPU stream window failure sets `stream_broken`; subsequent payload is suppressed. Although `lcd_stream_begin` returns true for this case, the large-glyph path checks `stream_broken` and latches loss. [lcd_bus.c:369](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:369), [lcd_bus.c:420](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:420)
- Detected failures can temporarily leave optimistic shadows, but `blit_lost` causes owner recovery, including a full dashboard restore. Its five-second cooldown delays repair rather than forgetting damage. [display.c:3067](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3067), [panel_owner.c:215](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/panel_owner.c:215)

| Failure | Visible in the supplied daily health counters? | Repair |
|---|---|---|
| DMA timeout, including missing completion | Yes: timeout/class/retry | Retry; exhausted failure requests restore |
| Polled window/payload give-up | **No**: separate diagnostic, dev access only | Stops payload and sets `blit_lost` |
| Wrong window/data despite peripheral success | No | None automatically |
| Lock-channel framing/media rejection | No | Later title reception |
| Glyph queue overflow | No reported counter here | Invalid shadow and another paint requested |

Thus **zero blit counters do not exclude polled failures**, but a detected polled failure alone should not leave minutes of persistent damage. The 1,004 counted blits also exclude the large-face CPU glyph writes. [lcd_bus.c:176](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:176), [lcd_bus.c:1465](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1465), [display.c:2944](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:2944)

**C: a setter can arrive between stages or during an outstanding DMA, but I found no inconsistency from that.**

`ch582_task`, raw-HID dispatch and display housekeeping execute on the main thread. The media setters modify RAM; they do not send window commands, reset queues or retain pointers into the incoming frame. A setter cannot interrupt a synchronous polled glyph. [main.c:48](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/main.c:48), [hid_protocol.c:407](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/hid_protocol.c:407)

A change between staged calls leaves `text_dirty` set. The current sequence finishes, then another sequence reconciles the new state. Queued glyphs contain copied character/font/coordinates. Housekeeping defers while either glyph queue remains nonempty; subsequent bus operations quiesce any last DMA still in flight. [display.c:3299](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3299), [display.c:3417](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:3417), [lcd_bus.c:1078](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1078)

Raw HID uses those same setters and can deliver the two lines in separate reports, so this interleaving was already possible. A permanently wedged shared glyph queue also conflicts with the continuing playback display.

**D: daily changes exposure and timing, not these rendering rules.**

- `DPROBE` adds timer reads/bookkeeping in dev; daily executes the same wrapped drawing statement. [display.c:36](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/display.c:36)
- `ROWISR_USB_DETECT` is enabled in dev and absent in daily, changing row-handler duration and interrupt alignment. [config.h:527](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/config.h:527)
- Dev drains RX through a bulk buffer; daily performs a channel read per byte. Both retain the 64-byte processing cap. This can change reception timing, but does not create a second display owner. [ch582f_ajazz.c:2045](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2045)
- Dev includes raw81 interception/dispatch and diagnostics. The promoted lock-channel media parser and setters are common to both flavours. [ch582f_ajazz.c:2103](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2103)

The older lost-completion race is fixed in the inspected driver. Atomic GPIO writes and the row mux masks provide no basis for blaming a GPIO read-modify-write collision. “First seen in daily” supports investigating timing, but does not identify a daily-only rendering defect.

**E: the most discriminating checks**

These are proposed checks; I performed none.

- **On the existing daily build, pause host media sends and immediately use Fn+D/back after photographing the fault.** If “Launch…” appears without receiving another title, RAM already held it: reception loss is eliminated for that occurrence. If “Implosion” returns, inspect the reception/ownership side. An expired slot may instead disappear.
- **Resend the exact expected two lines through USB raw HID, with the same icon.** If RAM already contains them, the setters ordinarily request no text repaint. If the original title was lost, this changes RAM and requests one. Follow with a string that changes every displayed cell to force a real repaint. Observe the 10-second raw-HID lease before subsequently testing Bluetooth.
- **Controlled Bluetooth frames:** establish title A, omit or deliberately corrupt title B, then send B’s valid type 3. This should reproduce the temporary A/B mismatch. Keep the board awake and verify expiry. Separately alternate short/long titles with the same artist/icon to isolate glyph painting from layout clears.
- **Existing daily reads:** `HC_LINK` supplies UART overrun/framing/parity counters; ordinary `rx_malformed` is not a lock-frame acceptance counter. Flash CRC commands can check the black frame for persistent source damage. Neither reads panel contents. [hid_protocol.c:858](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/hid_protocol.c:858), [hid_protocol.c:307](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/hid_protocol.c:307)
- **Smallest useful firmware diagnostic:** expose RAM title text through a narrow read-only command, reusing existing `display_get_text_line`; its current host endpoint is dev-only. Add shadow text/validity, `text_dirty`, `ts_step`, queue position and the poll-give-up count if the RAM title is new. Per-type accepted/rejected counts and last accepted type-1 sequence would distinguish receipt from painting without enabling all dev timing changes. [hid_protocol.c:1301](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/hid_protocol.c:1301)

I could not verify the event’s RAM title, shadows, exact accepted frame sequence, font setting, panel window registers or wire waveform. The host log outside this repository was not accessed. The photo and health records establish damage and continued operation, not which SPI transaction caused it.

**Single best candidate: silently misdirected or misframed SPI0 title writes, with the new title already accepted and its optimistic shadow preventing repair.**