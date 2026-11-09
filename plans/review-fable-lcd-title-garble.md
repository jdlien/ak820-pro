claude-fable-5-2

# Review: the song title garble on the daily build (Fable)

Independent review of `plans/LCD-TITLE-GARBLE-PLAN.md`. Code read at `qmk_firmware-ak820pro`
`4790208267` and ChibiOS-Contrib `5a1674e905`. Paths are under `keyboards/a_jazz/ak820pro/`
unless they start with `hal_`. Each claim is marked PROVEN (code or a file I read), INFERRED, or
ASSUMED (hardware behaviour the repo does not document). I did not read the other review or the
earlier codex trace.

## Summary

- **What the panel did is clear; why the bus did it is not.** Each glyph's window took its start
  column and its rows but not its end column, so 112 pixels ran from the glyph's corner to the
  right edge. That fits E5, E6 and E7 in detail.
- **H1 gets that geometry right but its bus mechanism does not survive the code.** The exit path
  of `spi0_poll_send()` takes longer than a byte, so one stray echo cannot leave a byte queued. A
  byte that did go out late would trip the next send's entry check and paint nothing. The dev read
  at 13:53 shows no losses, so "dev gives up and repaints" did not happen there.
- **The two builds' compiled paint path is equivalent.** `lcd_window_polled()` disassembles
  identically in both ELFs and the daily's `spi0_poll_send()` matches its source. The compiler is
  not the cause.
- **"Dev is clean" rests on 4.5 minutes of uptime on this commit.** The first thing to do is
  reflash the unmodified daily and confirm the garble returns. If it does not, the cause is board
  state, not build flavour.
- **The fix plan is safe and worth doing, but it is not shown to be sufficient.** It closes a gap
  that H1 needs and that I could not show is ever open. Ship it with counters that can prove or
  kill H1, and add an SPI0 reset at the DMA completion, which the manual asks for.

## Part 1: my reading, before H1

### What the panel received (INFERRED, high confidence)

For every song glyph of a title change, the panel ended up with this window:

- start column right;
- end column at the panel's right edge (x 127);
- rows right, or at least the first row right;
- RAMWR and all 224 data bytes received.

The evidence for it:

- **The band is edge to edge.** The title "Southbound" ends at x 81, yet its band reaches x 127
  across the cleared region (E5). Pixels past the text can only come from a window that extends
  there.
- **Thin at the left, blocky at the right.** 112 pixels into a window `128 - x` wide fill under one
  row at x 14, 2.7 rows at x 86, 4.3 at x 102, 6.2 at x 110 and 11.2 at x 118. Later glyphs
  overwrite earlier ones, which leaves a block from about x 102 to 127. That is E5's artist line.
  The cells follow from `TEXT_X` 14 and an 8 px advance (display.c:2188, lcd_bus.h:81).
- **The title line has no block.** Its last glyph is at x 74 (`TEXT_X2` 2, display.c:144), so its
  window is 54 wide and takes two rows.
- **The old letters survive below.** Only the top one or two rows of each cell are overwritten, so
  "Beacon (fe" stays readable in exactly the ten repainted cells.
- **The top-right speckle (E5, E7) fits too.** A channel digit drawn into a window ending at
  x 127 leaves pixels at x 121-127, which the digit's own clear (x 108-120, display.c:1550) never
  reaches.
- **A lost end row would be invisible.** Every glyph on a line has the same end row, so the same
  fault in RASET cannot be seen.

Every letter is affected because every glyph sends its own window (lcd_bus.c:369-380, 303-316), and
whatever breaks CASET's end column breaks it each time.

### What the code rules out (PROVEN)

- **No polled send gave up during a garbled paint.** A give-up at any of the five window sends
  returns false, sets `stream_broken`, and sends no pixel data (lcd_bus.c:309-313, 378, 387). A
  band needs pixel data. A give-up also sets `blit_lost`, which starts a repair within 5 s
  (display.c:3069, panel_owner.c:226-232, 238-250). The garble in E5 lasted over a minute.
- **DC and CS are not corrupted by another writer.** Every pin write is an atomic `BSET` or `BCLR`
  (hal_pal_lld.h:411, 424). The row ISR selects rows the same way (rgb/rowisr.c:963-966), and the
  backlight tick uses `gpio_write_pin` (display.c:295). Nothing in the board directory writes a
  port's `DATA`, `MODE` or `CFG` on ports 1 or 3 at run time.
- **SPI0's configuration after a DMA equals the driver's.** `spicfg` is 8-bit, mode 0, divider 0
  (lcd_bus.c:94-98; hal_spi_v2_lld.h:64-69 give all three mode macros as 0).
  `sn32_flash_dma_config()` sets the same (hal_spi_v2_lld.c:178-190).
- **A completion's RX residue is drained before the main thread runs.** The completion sets
  `IE = 0b0100` (hal_spi_v2_lld.c:318). A non-empty RX then raises the same vector, and the idle
  branch drains up to 16 entries (hal_spi_v2_lld.c:113-118).
- **The compiler did not change the path.** See O6 below.

### Why daily and not dev

I could not find a deterministic cause. What I can say:

- **The compiled paint path is the same** (O6).
- **The flavours differ only around it** (PROVEN):
  - the row ISR's USB detector, about 7 us a slot, dev only (config.h:527-541);
  - the idle hooks: the daily keeps the board default, which writes `PMU_CTRL = 4` at every idle
    entry; dev replaces all three (chconf.h:20-55);
  - dev hooks in the UART, USB and system-timer handlers (halconf.h:48-68);
  - two extra calls in the 20 kHz tick (indicators.c:176-179);
  - `DPROBE()` reads, none of them on the pump's glyph path (display.c:56, 2908, 2473).
- **SPI0's handler shares priority 3 with the row ISR**, so the row ISR's length sets when a DMA
  completion is served. That is a real, flavour-dependent phase shift. I cannot connect it to a
  lost end column.
- **The dev evidence on this commit is thin.** `dev-read-1353.txt` shows `uptime_ms 265712` and
  413 blits. That is under five minutes and a handful of title changes. The "weeks of dev builds"
  ran other commits, without the daily's two days of battery use and deep sleeps behind them.

### Ranked candidates

| # | Candidate | Confidence | Main objection |
|---|---|---|---|
| 1 | Board or session state, not flavour: something true of the daily's long session (SPI0 or panel state after deep-sleep wakes, for example) that the reflash's power cycle and `lcd_init()` reset cleared | 30% | `Fn`+`D`'s restore painted the same glyphs correctly on the daily (E3) |
| 2 | SPI0 carried un-reset from the DMA completion: `DL` goes 16 to 8 bits while enabled with no `FRESET` (hal_spi_v2_lld.c:311), which the manual forbids (docs/sn32f299.md:864), and a later burst is misframed | 20% | The restore's glyphs and the menu's polled draws run in the same state and look right |
| 3 | Completion-service phase: the daily's shorter row ISR moves the completion handler relative to the engine's end, exposing a race I have not identified | 15% | No specific race found; the tail clear is waited out synchronously (lcd_bus.c:496-501) |
| 4 | A stray RX echo miscounted by the polled send (H1's family) | 15% | The arithmetic in O1, and the entry check |
| 5 | Something else | 20% | |

No candidate explains why the restore's glyphs paint right and a title change's do not. That
contrast is the best lead left. The two differ in what precedes the glyphs: a small tail clear from
flash address 0 for a title change, and full-width band clears plus a polled icon tile for the
restore.

## Part 2: H1 and O1-O6

### Does H1 explain E1-E8?

| Evidence | H1 | Note |
|---|---|---|
| E5, E6 geometry | Yes, with a gap | Step 4's arithmetic matches mine. But it needs the previous end column to be 127, and no full-width clear precedes a title change (see O4) |
| E1, daily only | No | Step 5 says dev gives up and repaints. The dev read shows `losses 0`, `damaged false`, `restore_gen 1` after title changes |
| E2, E3 | Neutral | |
| E4 | Yes | The daily cannot report polled give-ups |
| E7 | Yes | By the same window fault on the channel digit |
| E8 | Not addressed | See O5 |

### Which steps are proven

- **Step 1, a stray counted as an echo: possible by code, source unknown.** The loop counts any RX
  entry (lcd_bus.c:213). The entry check passes only with RX empty (lcd_bus.c:190).
- **Step 2, return with a byte queued: contradicted by timing.** See O1.
- **Step 3, the byte goes out under the wrong DC: follows from step 2 only.**
- **Step 4, the panel keeps the old end column: ASSUMED.** The repo has no GC9107 data.
- **Step 5, dev gives up instead: refuted by the 13:53 read**, if `losses` counts what
  `display_loss()` handles. Worth confirming with the give-up count itself.

### O1. Does the misframe chain?

No, not on this code. PROVEN from the daily ELF's disassembly, assuming `BUSY` is honest during a
shift.

- From the last RX pop to the exit's first `BUSY` read is about 15 instructions (0x68e to 0x6ea).
  From there to the return is about 18 more (0x6ea to 0x62c). This MCU runs 3-5 cycles an
  instruction from flash, by the row ISR's cost diagnostic. So the caller's DC write comes at least
  1.5 us after the pop. A byte is 0.33 us.
- With one stray, the last real byte finishes long before `BUSY` is read. Its echo is in RX by
  then and the exit drain removes it (lcd_bus.c:223). The send returns complete, and nothing
  chains.
- With two or more strays in a 4-byte send, `BUSY` is read mid-shift and the wait holds.
- If a byte did go out after the return, the next send's entry check waits out `BUSY`, finds the
  echo in RX and gives up (lcd_bus.c:189-192). That paints no band.
- The one-byte command sends would break any chain for the same reason.

### O2. Where would a stray come from?

Nowhere I can find. A master's RX fills only while it clocks. After a completion nothing clocks
SPI0 until the next send, and the residue from the 16-bit words is drained in interrupt context
before the main thread resumes (above). ASSUMED: the RX FIFO does not release an entry late after
the `DL` switch. That is the one hardware behaviour that would give H1 a source, and it is what
the `FRESET` in Part 3 removes.

### O3. Can `BUSY` read clear with a byte in the TX FIFO?

Not documented. docs/sn32f299.md:867 names the bit and nothing more. Unknown.

### O4. What does the panel do with a truncated CASET?

Not in the repo; ASSUMED either way. Two points from the code:

- **The "previous end column 127" has no source.** At a title change `queue_line()` clears full
  width only for an unknown shadow (display.c:3193-3196). The tail clear ends at x 121 at most
  (`TEXT_X2` 2 plus 15 cells), and the artist's glyphs end at x 125. So either the panel puts a
  truncated CASET's end at its right edge, or H1's step 4 is wrong about where 127 comes from.
- **The stray commands would not be harmless.** `XE_lo` is `x + 8`. On the title line that is
  0x0A to 0x52 in steps of 8, which includes 0x2A (CASET) at the fifth cell and 0x3A (pixel
  format) at the seventh. On the artist line it is 0x16 to 0x7E, which includes 0x2E (RAMRD) and
  0x36 (MADCTL). If these arrived as commands I would expect cell-specific damage, and E5 shows a
  uniform band.

### O5. Why did USB repaint (E8)?

INFERRED. Over USB the host sends line 0 with `TEXT_SET`, which clears line 1, then line 1
(docs/display.md:556-558). Line 1's arrival changes the layout from one line to two, which
`queue_line()` treats as a moved run and repaints whole (display.c:3183-3192, 3324-3325). So USB
gets a second full paint a moment later, and that one landed. That it landed is itself evidence
the fault is intermittent per paint, not per build.

### O6. Is it the compiler?

No. PROVEN from `via-daily-4790208267-20261105-221019.elf` and
`via-dev-4790208267-20261105-221041.elf`:

- `lcd_window_polled()` is instruction-for-instruction identical in both, and its packed
  parameter words are correct;
- the daily's `spi0_poll_send()` matches the source: the entry check, `IE = 0`, the fill bound of
  8, the RX loop, the `BUSY` wait, the drain of 16, `IC = 4`, `IE = 4`;
- the daily inlines `lcd_stream_bytes()` and `lcd_stream_end()` into `lcd_blit_mono()`; dev calls
  them. The order of operations is the same.

### The one measurement

Count, per polled send, the echoes left over at the exit: the entries the exit drain removes, plus
whether `TX_EMPTY` was clear when the `BUSY` wait ended. Expose both in health on every build, then
change titles on a daily.

- Non-zero with a garbled screen: H1's family is alive.
- Zero with a garbled screen: H1 is dead, and the bus never miscounted.

On the current dev build, read op 27's sticky bits and `lcd_spi0_poll_giveups()` after twenty
title changes. H1's step 5 predicts both non-zero. The 13:53 read already suggests zero.

## Part 3: the fix plan

### Sufficiency

- **For H1 as written: yes.** Waiting for `TX_EMPTY` and not `BUSY` before the return closes
  step 2.
- **For my reading: not shown.** I could not show step 2 ever happens, so the fix may change
  nothing visible. Its counter is what makes it worth flashing.

### Safety

- **No new hang, if the new wait is bounded.** Put the `TX_EMPTY` wait under the same spin limit
  as the `BUSY` wait (lcd_bus.c:216-218), ending in the existing give-up.
- **No pass near 25 ms.** The added wait is a byte or two.
- **No lost completion.** Every caller has quiesced the bus, so no DMA flag is pending.
- **`IC` stays a literal `1u << 2`.** Do not widen it.
- **The entry drain needs care.**
  - Set `IE = 0` before draining, or the idle handler drains the same FIFO concurrently
    (hal_spi_v2_lld.c:112-117).
  - Wait for `TX_EMPTY` and not `BUSY` first. A byte still shifting produces its echo after the
    drain, which is exactly H1's stray.
  - Keep refusing on `!blit_done`, a non-READY driver, or a stuck `BUSY`.
  - It converts a give-up and repaint into a silent continue. If the stray's byte reached the
    panel under the wrong DC, the damage is already done and now nothing repaints it. Count it,
    and consider keeping `blit_lost` for a non-zero drain until the counters say otherwise.

### What else should change

- **Reset SPI0 at the completion.** After the last word is out and `DL` is back to 7, write
  `FRESET`, as the manual requires after a `CTRL0` change while enabled (docs/sn32f299.md:864).
  Do the same in `spiSN32FlashDmaAbort()`. This is the only change that addresses candidate 2 and
  O2's assumption.
- **Drop the panel's CS before the mode switch.** The completion changes `DL` with the panel still
  selected (hal_spi_v2_lld.c:311) and calls the callback that raises CS last (line 335). Raise CS
  first, so any edge the switch or the reset puts on SCK reaches a deselected panel.
- **Add `TX_EMPTY` to the entry check** beside `BUSY` (lcd_bus.c:190).
- **Leave the DMA arm's polled window alone.** It runs straight after `Prepare()`'s reset, and its
  windows are the ones that land.

### The test on the board

1. **Re-establish the fault.** Reflash the unmodified daily and change titles. If it paints clean,
   the cause was session state, and the next step is to find what two days on battery did, not to
   ship a bus fix.
2. **Script the trigger.** Drive titles from the Mac with `hostagent/ak820text.py`, alternating a
   14-character artist with a 10-character title and a shorter pair, so every change repaints both
   lines and runs a tail clear. Thirty changes each over USB and Bluetooth, filmed.
3. **A/B the fix.** The same script on the daily with and without it, in one session, with the new
   counters read after each run.
4. **Provoke H1 deliberately.** On a dev build, add a hook that writes one dummy byte to SPI0's
   `DATA` with CS high just before a glyph's window, after a short adjustable delay, so its echo
   lands after the entry check. The panel ignores the byte, and the echo is H1's stray made to
   order.
   - Unfixed code showing E5's band: H1's chain is real after all.
   - Unfixed code painting clean or giving up: my arithmetic holds and H1 is not the cause.
   - Fixed code: the counter rises by one a glyph and the screen stays clean.
5. **Keep the existing gates.** `count_ge_25ms` and the blit fault counters unchanged, and
   `HC_POLLFAULT` on a devfault build to show the give-up and repaint path still works.

### Release note

Do not describe v0.3.0 and v0.3.1 as carrying this bug until step 1 passes. Neither painted the
song face over Bluetooth, and whether a fresh daily garbles over USB is the open question step 1
answers.
