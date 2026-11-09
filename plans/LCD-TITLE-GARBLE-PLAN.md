# The song title garble on the daily build (2026-11-09): evidence, hypothesis, fix plan

The stray pixels in `plans/BACKLOG.md` ("Stray white pixels on the screen") turned out to be a
reproducible bug. This file is the brief for the independent reviews (codex on gpt-6-astra, and a
Claude agent on Fable) and the plan the fix follows. The firmware commit is `row-isr` `4790208267`
(`qmk_firmware-ak820pro`). Its ChibiOS-Contrib submodule is at `5a1674e905`. **Read the code as
committed** (`git -C qmk_firmware-ak820pro show 4790208267:<path>`, and
`git -C qmk_firmware-ak820pro/lib/chibios-contrib show 5a1674e905:<path>`), because the working tree
may carry the fix in progress.

## The evidence

- **E1. Daily against dev, the same commit.** The daily build (`via-daily-4790208267-...`, token
  `0x3501ba59`, no extra flags) garbles the song text at nearly every title change, by JD's use
  from about 09:00 to 13:40 11-09. The dev build of the same commit (`via-dev-4790208267-...`, token
  `0x50f8f2d1`, `-DAK820_RAW_BOOTLOADER -DAK820_DEV_HOOKS`) has been on the board since 13:39:54.
  Title changes on it look clean to JD, over Bluetooth. JD ran dev builds with titles for weeks.
  The song face drawn here (below) dates from 10-28, and no daily build painted it before 11-07.
- **E2. The transport doesn't matter.** It garbles over Bluetooth (the lock-light channel,
  `lockchan.c`) and over USB raw HID (13:38:16, the cable's title with the daemon running). Both
  paths only set the text slot; the paint is shared.
- **E3. The text arrives, the paint fails.** `Fn`+`D` and back repaints the screen from RAM and
  shows the new title.
- **E4. Health on the daily** (`history/lcd-speckle-20261109/health-1145.txt`, `health-1211.txt`):
  every blit counter is zero since the boot (0 timeouts, 0 lost completions), and no pass took
  25 ms or more. The polled-send give-up count (`spi0_poll_giveups`) can't be read on the daily.
- **E5. The 13:23 photo** (`history/lcd-speckle-20261109/photo-1323.jpg`). The title
  "Lucy In Disguise - Southbound" was sent at 13:22:10 and the transport (0:06/5:00) at 13:22:13.
  - The screen shows the old artist "Volkor X" (row ~27, text from x ~14 after the play icon), the
    old title cut to "Beacon (fe" (row ~42, from x 0) with black after it, and the new 0:59/5:00.
  - A speckled band covers the top one or two rows of each song line, edge to edge. On the artist
    line it grows into a block about x 101-127 and ~8 rows tall. The title line has no block.
  - "Southbound" is ten letters, and the old title survives in exactly ten cells. So the clear past
    the new text's end (a DMA) landed right, and the letters did not.
  - There is also a speckle at the top right beside the channel digit (x ~116-127, rows ~0-5).
- **E6. The 12:06 photo** (`photo-1206.jpg`). A bright line about two rows tall crosses the full
  width at the title line's top (~41-42), and a glyph-sized block sits at x ~92 on the title line.
  The old title is kept, with the new track's time.
- **E7. The first sighting**, that morning, with no photo: a horizontal speckle at the top right,
  above and right of the channel digit.
- **E8. Over USB at 13:38**, JD's words: "a noisy row of pixels about `morgan w`, which is the
  previous song's title, then the title changed to the new song". So over USB the new title did
  paint after a noisy row.

## The paint path (at `4790208267`)

The paths below are under `keyboards/a_jazz/ak820pro/`.

- **The song face** ("10px bold", the default font) is `FONT_SONG_LARGE`. It is 8x14 one-bit glyphs
  in internal flash (`mt_glyph_large`). `graphics/lcd_bus.c` `song_large_glyph()` (~898) calls
  `lcd_blit_mono()` (~412), which calls `lcd_stream_begin()` (~369: `bus_quiesce()` and
  `lcd_window_polled()`), then `lcd_stream_bytes()` (~381), then `lcd_stream_end()`. That is 224
  bytes a glyph, all through `spi0_poll_send()` (~182). `lcd_window_polled()` (~303) is five polled
  sends: `0x2A`, its four parameters, `0x2B`, its four, `0x2C`. DC changes between them.
- **The glyph pump** (`graphics/display.c`, `queue_line()` ~3147, the pump ~2990) draws one glyph a
  pass through `lcd_draw_flash_glyph_try()` (`lcd_bus.c` ~923). That returns false while a DMA is in
  flight (`lcd_blit_busy()`), so a polled glyph often follows a DMA's completion directly. The
  clock's digits and every clear are DMAs.
- **A clear** is `lcd_clear_rect()`, which runs `lcd_blit_flash()` (~1119) of the black frame at
  flash `0x000000`:
  - `spiSN32FlashDmaPrepare()` (8-bit; SPI0's FIFOs reset);
  - the window, polled;
  - `spiSN32FlashDmaFire()` (`hal_spi_v2_lld.c` ~218: `DL = 0xF`, 16-bit words).
- **The completion** is `sn32_flash_dma_isr()` (`hal_spi_v2_lld.c` ~297-337). It waits for
  `TX_EMPTY` and not `BUSY`, then sets `DMAEN = 0`, `DL = 7` (back to 8-bit, the panel still
  selected), restores IE, and calls `blit_done_cb()` (`lcd_bus.c` ~1088), which drops both CS lines
  and sets `blit_done`. It does not reset or drain SPI0's RX FIFO.
- **`spi0_poll_send()`**:
  - The entry check spins briefly on `BUSY`, then gives up (counted, `blit_lost` set, no reset)
    unless `blit_done`, the driver is `READY`, it isn't `BUSY`, and RX is empty.
  - The loop writes while `tx - rx < 8` and the TX FIFO isn't full, and reads RX, counting `rx`,
    until `rx == n`.
  - Then it waits for `BUSY` to clear, drains up to 16 RX entries, and restores IE.
  - It does not wait for `TX_EMPTY` before returning.
- **What dev adds to this path:**
  - `DPROBE()` timer reads around display steps (`display.c` ~36-58);
  - `po_note_fail()` in `POLL_FAIL()`;
  - the scratch buffer's acquire and release checks (~244-265);
  - the stream's open and length checks (`lcd_stream_begin()`, `lcd_stream_end()`);
  - possibly `CONSOLE_ENABLE` code in `lcd_blit_flash()` and `blit_done_cb()` (check the build's
    flags);
  - code layout and inlining differences.

  The rendering rules are the same.
- **Background:** `docs/display.md` (the band layout, the glyph queue, the DMA pump);
  `docs/sn32f299.md` (the MCU's SPI: FIFO depth, `BUSY` and `TX_EMPTY` semantics, if the manual
  gives them); `CLAUDE.md`'s SPI0 warnings (DMACNT never counts down; never write `IC` wider than
  what was read; SPI0 and the RGB row ISR share priority 3);
  `plans/review-codex-lcd-speckle-raw.md` (the morning's trace).

## H1, the working hypothesis (Blackberry, 11-09; unproven)

After a flash-to-panel DMA, a stray byte arrives late in SPI0's RX FIFO, after the next polled
send's entry check has passed.
1. `spi0_poll_send()` counts it as one of its own echoes, so `rx` reaches `n` one byte early.
2. The exit waits only for `BUSY` to clear, not for the TX FIFO to empty, so the send can return
   with its last byte still queued.
3. The caller flips DC, and that byte goes out under the wrong DC.
4. In the CASET parameter send, the last byte is `XE_lo`. The panel takes it as a command and keeps
   the previous window's end column, 127 after a full-width clear. Each glyph's 112 pixels then fill
   `112 / (128 - x)` rows from the glyph's corner: under one row for a glyph at the line's start,
   two at x 72, six at x 110, eleven at x 118. That is the band and the right-hand block of E5.
5. On dev the extra work lets the stray byte land before the entry check, which gives up instead.
   The give-up sets `blit_lost`, the display repaints, and the dev-only sticky `PO_FAIL_SPI0_POLL`
   is set. The result is a correct screen.

Being tested now: a dev read of `PO_FAIL_SPI0_POLL` and the give-up count after title changes. A
set flag supports H1; a clear one sends us elsewhere.

**What H1 still has to answer:**
- **O1.** Every letter on both lines is hit, and each letter sends its own window, so one stray byte
  would cost one letter. What produces a stray before every letter? Or does the misframe chain, each
  early return's last echo becoming the next send's stray? If it chains, why do the one-byte command
  sends (`0x2A`, `0x2B`, `0x2C`) still land as commands, with XS and the rows right?
- **O2.** Where does the stray byte come from? Consider the completion's 16-to-8-bit switch with the
  panel selected, the RX FIFO left unflushed, and the 16-bit words' RX side.
- **O3.** Can `BUSY` read clear between bytes while the TX FIFO still holds one, on this SPI?
- **O4.** What does the GC9107 do with a CASET whose fourth parameter arrives as a command? And what
  do those stray commands do? `XE_lo` is `x1 + LCD_OFF_X`, so some are read commands, such as `0x09`
  (RDDST).
- **O5.** Why did USB paint the new title after a noisy row (E8), while Bluetooth left the old one
  (E5, E6)?
- **O6.** Why is the daily alone exposed? Is timing the whole story, or does the build's code differ
  in a way that matters, such as a missing barrier or a reordering that a dev-only call prevents?

**Alternatives to weigh:**
- the completion dropping CS or switching mode before the panel has the last word;
- a flash read gone wrong in a clear (all-ones);
- the row ISR preempting the polled send at a bad point;
- the compiler, not the timing (O6).

## The fix plan (Blackberry's, in progress)

- `spi0_poll_send()` waits for an empty TX FIFO and not `BUSY` before it returns, then drains RX.
  So no send returns while a byte of it is still queued, and DC never changes under a byte.
- At entry, stale RX bytes are drained and counted instead of failing the send. That count goes in
  health, every build. A stuck `BUSY`, or a DMA in flight, still gives up as now.
- Under consideration: flush SPI0's RX at the DMA completion, before the mode switch or right after
  it.
- The cost bound: the waits are a byte or two at 24 MHz. No pass may reach 25 ms. The give-up paths
  and `blit_lost` repaint stay.
- **Verification:**
  1. A daily build with the fix, flashed on JD's go.
  2. Title changes over Bluetooth and USB, by eye.
  3. The new counter read after them. Non-zero with a clean screen means the guard caught the
     stray bytes.
  4. The health stall counts unchanged.
  5. A codex review of the diff before the flash.
- **Release:** v0.3.0 and v0.3.1 are daily builds with this font as the default. If H1 holds, they
  carry the bug for any owner with now-playing, over USB too. The fix goes into the next release.

## The reviews

- codex, gpt-6-astra at xhigh: `plans/review-codex-lcd-title-garble.md`.
- A Claude agent on Fable: `plans/review-fable-lcd-title-garble.md`.

Each was asked first for its own reading of the evidence and the code, then for a judgment of H1 and
O1-O6, then for one on the fix.

## Where it stands (11-09 evening), and the analyser session

- **Fix A cures it; the bus-level cause is unproven.** On the switchable diagnostic `lcd-diag`
  `5688b2a975` (token `0x8edc1022`; fix A with 4790208267's send kept beside it, raw81 in both modes),
  the old send garbled over BT and A's stayed clean. Over 609 polled windows, with the old send
  among them, nothing refused and no window started with SPI0 busy. No window came closer than
  229 us after a DMA's completion, and the old mode's closest was 1.17 ms. So the fault lies inside
  the old send's completion, not in a busy bus at entry or a DMA's tail. A's own counters (`late`,
  `strays`) read 0, so what A changed works without either guard firing.
- **White stays on `lcd-diag` in A's mode** until the logic analyser arrives (1-2 weeks). Every boot
  and watchdog reset comes up in A. `scripts/lcd_diag.py read|old|new|zero` switches and reads over
  the data line, with the daemon out.
- **The capture:** SCK, MOSI, DC and the panel's CS, triggered on DC rising during CASET's argument
  bytes. In old mode the early-return theory predicts the 4th argument byte (`XE_lo`) still
  clocking after DC has dropped for RASET. Fire a track change and the capture together. The
  presser's F19 key, mapped to next track on the Mac, keeps the board's keymap untouched.
- **The 240 fps camera can't resolve it:** about one camera pixel per panel pixel at the closest
  focus. Its one clip (16:55:46-16:56:38) showed per-change failure in old mode: "Warp Drive"
  painted, "You Can't Hurry Love" didn't, and the old title stayed while the new time showed.
