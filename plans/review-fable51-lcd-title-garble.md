claude-fable-5-1

# The song title garble: an independent review (Fable)

Firmware read as committed at `qmk_firmware-ak820pro` `4790208267` (paths below are under
`keyboards/a_jazz/ak820pro/`) and ChibiOS-Contrib `5a1674e905` (`hal_spi_v2_lld.c` is
`os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c`). Both build artifacts in
`ak820pro-builds/out/` were disassembled with the pinned toolchain. Nothing on the board was
touched. Each claim is marked PROVEN (code or artifact I read), INFERRED (follows from evidence
plus reasoning) or ASSUMED (hardware behaviour the repo does not document).

## Summary

- **The panel-side picture is solid and matches H1's step 4:** every glyph's CASET lands its start
  column but not its end column; the end sits at the panel's right edge; the glyph's 112 pixels then
  fill `112 / (128 - x)` rows from the cell's top-left corner. That is the thin band at the top rows
  of each line, its reach to x 127 past the text, the right-hand block on a long line, and the old
  letters surviving beneath (INFERRED from the photos and the layout constants). One refinement:
  in E5 no full-width clear preceded the run, so the panel is not "keeping 127"; an incomplete
  CASET must drive its end column to the edge (ASSUMED panel behaviour H1 needs).
- **H1's SPI-side half is plausible but unproven, and two of its steps do not survive the record.**
  Step 5 is refuted: the dev read at 13:53 shows the sticky `PO_FAIL` mask at 0 and no losses, so
  dev does not *catch* a stray, it simply does not produce one. Step 1's origin (a late word after a
  DMA) cannot reach glyphs 2..n, which follow polled glyphs, not DMAs; H1 needs a per-send trigger
  (O1). The one-byte command sends are immune by construction, which is exactly the pattern needed.
- **The daily/dev split is not in the code.** `spi0_poll_send` compiles to the same instructions in
  both builds (only addresses and two dev-only `bl po_note_fail` differ); `lcd_stream_bytes` and
  `lcd_stream_end` are inlined into `lcd_blit_mono` in the daily with the same semantics. What
  differs is alignment of the RX-pop loop, the interrupt environment, and RAM layout. The dev
  build's clean record also rests on 4.4 minutes of uptime at its read.
- **The fix plan is safe and worth doing, but incomplete:** make completion `tx == n` and
  `TX_EMPTY` and `!BUSY` (an RX over-count can also leave bytes *unpushed*, which `TX_EMPTY` would
  not see); FRESET SPI0's FIFOs in the completion ISR after the DL change, as the manual requires;
  expose the give-up count, which nothing reads today on any build; and prove the fix against a
  deliberately injected early exit before trusting the natural rate.

---

## Part 1. The mechanism, from E1-E8 and the code

### 1.1 The paint path, as proven

- A song glyph is `song_large_glyph()` -> `lcd_blit_mono(g + 1, 1, x, y, 8, 14, 0xFFFF, 0)`
  (`lcd_bus.c:898-905`) -> `lcd_stream_begin()` (`:369-380`: `bus_quiesce()`, then
  `lcd_window_polled()`) -> one `lcd_stream_bytes()` of 224 bytes (`:381-389`; 112 halfwords fit the
  256-halfword scratch, `:414-441`) -> `lcd_stream_end()` drops CS (`:390-398`). PROVEN.
- `lcd_window_polled()` is five polled sends with DC flipped between them: `2A` (1 byte), four
  bytes, `2B`, four bytes, `2C` (`lcd_bus.c:303-316`). The panel coordinates are `x+1 .. x+8` and
  `y+2 .. y+15` (`:304`, `LCD_OFF_X 1`, `LCD_OFF_Y 2`, `:38-39`). PROVEN.
- `spi0_poll_send()` (`lcd_bus.c:182-227`): entry spins on `BUSY` up to 256 iterations, then
  refuses (no reset, `blit_lost` set, counted) unless `blit_done`, `SPID0.state == SPI_READY`,
  `!BUSY`, `RX_EMPTY` (`:188-193`); `IE = 0` (`:194`); pushes while `tx < n`, `tx - rx < 8`,
  `!TX_FULL`, pops and counts every RX word until `rx == n` (`:211-215`); then waits for `!BUSY`
  (`:216-218`); drains up to 16 RX words; `IC = 1u << 2`; `IE = 0b0100` (`:223-225`). Completion is
  decided by the RX count alone; `TX_EMPTY` is never read; `tx == n` is never checked. PROVEN.
- A clear is `lcd_clear_rect_ok()` -> `lcd_blit_flash()` + `lcd_blit_wait()`, synchronous
  (`lcd_bus.c:496-501`). `lcd_blit_flash()` runs `spiSN32FlashDmaPrepare()` (`:1151`), the polled
  window (`:1160`), the SPI1 READ command (`:1190`), `spiSN32FlashDmaFire()` (`:1205`). PROVEN.
- `spiSN32FlashDmaPrepare()` -> `sn32_flash_dma_config()`: `CTRL0 = 0` (SPIEN off), fields, `DL = 7`,
  `FRESET`, `SPIEN = 1`, then `FRESET` again (`hal_spi_v2_lld.c:173-191, 209`). Fire: `IC = 0x3F`,
  `DL = 0xF`, DMA IE bits, `DMAEN = 1` (`:218-228`). Completion (`sn32_flash_dma_isr`,
  `:297-338`): reads `RIS & 0x30`, clears only that; waits `TX_EMPTY && !BUSY` (bounded 200000,
  `:308-309`); `DMAEN = 0`; `DL = 7` **with no FRESET** (`:310-311`); `RXFIFOTH = 0`; `IE = 0b0100`
  (`:317-318`); SPI1 FRESET/IC/vector (`:323-326`); callback drops both CS lines and sets
  `blit_done` (`lcd_bus.c:1088-1102`). PROVEN. The manual says a CTRL0 change while enabled must be
  followed by FRESET (`docs/sn32f299.md:864`, p. 162).
- Between sends, with `IE = 0b0100`, any RX word sets RXFIFOTHIF (threshold 0,
  `hal_spi_v2_lld.c:67-71`) and the SPI0 handler's idle path drains up to 16 words and clears the
  flag (`:112-118`, `state != SPI_ACTIVE`). PROVEN. This matters for O1 below.
- The pump paints one queued glyph per main-loop pass (`display.c:2976-2994`, `:3059-3069`), and
  `lcd_draw_flash_glyph_try()` refuses while a DMA is in flight (`lcd_bus.c:924`). A title change
  in the two-line layout queues line 0 then line 1 in one pass (`display.c:3355-3406`,
  `TS_LINE_A` then `TS_LINE_B`), with any clears run synchronously inside `queue_line()`
  (`:3178-3200`, the tail clear `:3209-3211`), so **only the first glyph of a run follows a DMA;
  glyphs 2..n follow polled glyphs** separated by a full main-loop pass with CS high. PROVEN.
- Layout: `TEXT_Y 27`, `TEXT_X 14`, `TEXT_X2 2`, `TEXT_LINE_H 15`, so line 0's cells start at
  x = 14 + 8k and line 1's at x = 2 + 8k, y 27 and 42 (`display.c:2184-2188, 134, 144`). PROVEN.

### 1.2 What the photos constrain (INFERRED)

Take E5 (`photo-1323.jpg`): new artist "Lucy In Disguise" cut to Large's 14-cell line-0 budget,
cells x = 14..118; new title "Southbound", 10 cells at x = 2..74; old title shadow 15 cells, so the
only clear is the tail x 82..121 at y 42 (`queue_line`'s `old_n > n` path), and no clear reaches
line 0. Suppose each glyph's window were `x+1 .. 128` by `y+2 .. y+15` (end column at the panel's
edge). Then its 112 pixels fill `112 / (128 - x)` rows from the top-left corner:

| line | cell x | rows filled |
|---|---|---|
| title | 2 | 0.9 |
| title | 74 (last) | 2.1 |
| artist | 14 | 1.0 |
| artist | 86 | 2.7 |
| artist | 102 | 4.3 |
| artist | 110 | 6.2 |
| artist | 118 (last) | 11.2 |

That is E5 exactly: a one-to-two-row band at the *top* of each line (the window's first rows are
the cell's first rows); edge to edge, because every glyph's data runs to x 127 whatever its x,
which is why the band crosses the freshly cleared black right of "Beacon (fe"; the old letters'
rows 2-14 untouched, so "Volkor X" and exactly ten cells of the old title survive; a block from
about x 100 to 127, four to eleven rows tall, only where a long line's last cells sit; and no block
on the ten-cell title line. E6's two-row stripe at the title line's top is the same figure for a
shorter title. E6's glyph-sized shape at x ~92 is cell 11 of the new title, beyond the old
"Implosion": one glyph whose window landed, so **the fault is per send and intermittent within a
run**, not a mode the whole run is in. E7/E5's residue at x 121-127 beside the channel digit fits
the same figure for a DMA'd digit whose window ran to the edge once, later cleaned only inside its
own 109-121 clear (the backlog's note that x 121-127 is painted only by a full repaint).

So the observed fault, independent of any SPI theory: **CASET's start column arrives; its end
column does not take effect and the panel's column end goes to the right edge; RASET, RAMWR and the
224 data bytes arrive.** The RASET's end row suffering the same loss would be invisible: every cell
on a line shares it, and the data never needs more than 14 rows.

Two points H1 must absorb here:

1. No window with end column 128 preceded E5's glyphs. The tail clear ends at 122 (x 121); the
   digits repainted every second end near x 100; the last full-width clear was the last restore.
   If the panel "kept the previous end column" the artist's band would stop at the previous
   glyph's end, which is *left* of the new start. The band reaches x 127, so the panel must treat
   an incomplete CASET, or `XE < XS`, as "to the end of the line" (ASSUMED; standard-ish for
   ST77xx-class controllers, not documented in the repo).
2. The same `song_large_glyph()` path paints the title cleanly after `Fn`+`D` (E3) and the position
   digits' DMA windows land every second (E5's crisp `0:59/5:00`). Any mechanism has to be
   contextual to the title-change run, or rare enough that only the run's 24 back-to-back glyphs
   show it.

### 1.3 Ranked candidates for the bus-side cause

**C1 (best fit, ~55%): a multi-byte polled send returns one frame early, and that frame goes out
under the next DC.** The code admits it: completion is `rx == n` (`lcd_bus.c:211`); the only guard
after that is `BUSY` (`:216-218`); `TX_EMPTY` is never consulted; the next statement in the caller
is `dc()` (`:309-314`). PROVEN as a path. For the CASET send the straggler is `XE_lo`, read by the
panel as a command (the values are `x+8`: for the title line 0x0A, 0x12 PTLON, 0x1A, 0x22, 0x2A,
0x32, 0x3A COLMOD, ...; for the artist line 0x16, 0x1E, 0x26, 0x2E, 0x36 MADCTL, ...; most undefined
and ignored, a few real), so CASET ends after XS and the end column goes to the edge (ASSUMED
panel behaviour, 1.2). The RASET straggler `YE_lo` is 0x2A (CASET, then starved of parameters by
`2C`) on the artist line and **0x39 (IDMON) on the title line**; the data send's straggler is the
last pixel's low byte, lost at CS high, invisible. The one-byte sends are immune: a single frame has
no inter-frame gap for `BUSY` to read clear in, and a stale word popped before the frame cannot
end the wait before `BUSY` rises (ASSUMED on BUSY's timing). That immunity is precisely the pattern
the photos need (every CASET hit, every command byte landing), which is why I rank this first.

What C1 needs and does not have: a trigger for the first over-count in each send. A word left in
RX from before is refused at entry (`:190`), and between glyphs the handler's idle drain
(`hal_spi_v2_lld.c:113-118`) empties RX, so a stray cannot carry from glyph to glyph. Within a
window the straggler's RX word lands during the next entry spin; the handler normally drains it
within a microsecond, so the entry check is blind to it rather than refusing (PROVEN path;
timing INFERRED), and if it has not landed yet the next send's loop counts it as its own (an
over-count, hence the chain through a window). The first over-count of a glyph still needs either
a word that lands after `RX_EMPTY` was read at entry, or a flag-read race inside the loop (a pop
followed by a stale `RX_EMPTY`), both ASSUMED. The repo itself records that RX publication can
lag `BUSY` on this SPI (`lcd_bus.c:573-576`, measured on SPI1), which makes "a word lands after the
check" at least consistent with what is known.

**C2 (~20%): SPI0 left in an ill-defined FIFO state after a DMA.** Every DMA overflows the sink's
RX FIFO (hundreds of words into eight; the code calls the full FIFO "the junk the panel side
receives", `lcd_bus.c:1014-1016`), and the completion changes DL 16->8 without the FRESET the
manual asks for (`hal_spi_v2_lld.c:311`; `docs/sn32f299.md:864`). The next FRESET is the next
Prepare, so every polled send after a clear runs on a never-reset, post-overflow peripheral
(PROVEN state; its consequences ASSUMED). This would supply C1's missing trigger if the state
makes a word surface late. Against it: the menu's polled draws and the `Fn`+`D` restore's glyphs
run in the same state and land, so the state alone is not sufficient.

**C3 (~10%): a data-prefix fault** (the 224-byte send delivering only its first row or two, then
giving up). Rejected by the edge-to-edge band and the right-hand block, both of which need the
*window* widened and the data complete; and a give-up sets `blit_lost` and repaints within 5 s
(`display.c:3069`, `panel_owner.c:238-256`, `:224-236`), which E5 and E6 did not show.

**C4 (~10%): something outside SPI0** (a panel in a bad mode, a DC glitch, corrupted window
parameters). DC and CS are written by `BSET`/`BCLR` only (`gpio_write_pin` ->
`pal_lld_setpad/clearpad`, contrib `hal_pal_lld.h:411,424`; the row ISR uses `palSetLine`/
`palClearLine`, `rgb/rowisr.c:963,966`), so no read-modify-write can flip them. The window bytes
are stack locals built from constants (`lcd_bus.c:306-307`). E3 rules out a panel mode that
persists. Low.

### 1.4 The three questions

- **Why every letter of a line:** each glyph sends its own window, and under C1 each window's CASET
  loses its last byte, so each of the 24 glyphs smears its own cell to the right edge; the smears
  tile the line and the right-hand block is the last cells' tall smears overlapping (INFERRED).
- **Why the top rows, thin left and blocky right:** the window's first rows are the cell's first
  rows, and the pixel count is fixed at 112 while the window's width is `128 - x` (INFERRED, 1.2).
- **Why the daily and not the dev build of the same commit:** not the code. From the ELFs
  (PROVEN): `spi0_poll_send` is instruction-for-instruction identical (daily at 0x5dc, dev at
  0x6b4; the normalized diff is addresses plus two dev-only `bl po_note_fail`); `lcd_window_polled`
  is identical; in the daily `lcd_stream_bytes` and `lcd_stream_end` are inlined into
  `lcd_blit_mono` (281 lines against dev's 222 plus a 33-line `lcd_stream_bytes`) with the same
  stores, the same `bl spi0_poll_send`, `stream_left = 0` and the CS `BSET` at the end. No barrier
  or ordering difference exists: the register accesses are volatile in both. What does differ:
  (a) alignment, the daily's RX-pop loop sits at 0x68a/0x68e (half-word aligned), the dev's at
  0x768/0x76c (word aligned), so a pop-then-flag-read sequence that phase-locks to the SPI frame
  boundary can straddle a hazard window in one build and not the other (INFERRED; the hazard
  ASSUMED); (b) the interrupt environment, the dev row ISR carries the USB detector
  (`config.h:536-541`, about 7 us a slot) and the dev UART/USB/ST handlers carry `od_*` hooks
  (`halconf.h:48-70`), the dev 20 kHz tick runs `od_tick()` (`indicators.c:275-280`); (c) RAM
  layout. I also note the parent board `chconf.h` writes `PMU_CTRL = 4` at idle entry and 0 at
  leave in the daily while the dev build replaces those hooks (`platforms/chibios/boards/SN_SN32F290/
  configs/chconf.h:29-37`, board `chconf.h:20-53`); with `CORTEX_ENABLE_WFI_IDLE FALSE`
  (`config.h:248`) nothing sleeps and the idle thread never runs during a send, so it cannot be the
  cause, but it is the one semantic daily/dev difference outside instrumentation. Finally, the
  comparison is thin: `dev-read-1353.txt` was taken at 265.7 s of uptime, and the daily's own first
  sighting came on its third day. Treat "dev is immune" as provisional until dev has an hour of
  title changes.

---

## Part 2. H1 and O1-O6

**Does H1 explain E1-E8?** Steps 2-4 explain E5, E6, E7 and the persistence (no detected failure,
so no repaint) well, and are the same figure I derived independently. Step 1 explains only the
first glyph of a run. Step 5 is contradicted by the record. E3 and the crisp digits are not
addressed. E8 is not addressed.

**Which steps are proven, which rest on hardware:**

| H1 step | status |
|---|---|
| 1. a late RX word is counted as an echo, `rx` reaches `n` early | the counting is PROVEN (`lcd_bus.c:213`); the late word's existence and origin ASSUMED |
| 2. exit waits only for `BUSY`, a byte can still be queued | the code is PROVEN (`:216-218`); "BUSY can be clear with a byte queued" ASSUMED (O3) |
| 3. the caller flips DC under that byte | PROVEN (`:309-314`) |
| 4. the panel keeps the previous end column; the 112-pixel figure | the figure INFERRED and confirmed by my own arithmetic; "keeps the previous column" is wrong for E5 (no 128 precedes), it must be "an incomplete CASET ends at the edge", ASSUMED |
| 5. dev catches the stray at entry, gives up, repaints, sets `PO_FAIL_SPI0_POLL` | refuted: `dev-read-1353.txt` op 27 sub 5 `invariant_fail 0`, `losses 0`, `damaged false` after dev title changes; `invariant_fail` is `po_invariant_fail()` (`menu_ops.c:249`, `panel_owner.c:45`), the sticky mask that `PO_FAIL_SPI0_POLL` (`panel_owner.h:120`) would set through `POLL_FAIL()` (`lcd_bus.c:157, 179`). Dev produced no give-ups. |

**O1 (every letter; chaining; the one-byte sends).** One stray cannot do it: glyphs 2..n follow
polled glyphs across a full pass with CS high, and the idle handler drains RX in that gap
(`hal_spi_v2_lld.c:113-118`), so nothing carries between glyphs; the trigger must recur inside each
glyph's CASET send. Within a window a chain is possible: the straggler shifts during the next
send's entry spin (`lcd_bus.c:189`); if its RX word has landed the send refuses (visible as a
give-up, which the dev did not record), if the handler drained it the send starts clean, and only
if it lands after the `RX_EMPTY` read does the next send over-count. The one-byte commands survive
a chain because a single frame has no inter-frame gap and `BUSY` rises within the push-to-check
latency (ASSUMED). So the data pattern (CASET hit, commands intact, RASET's loss invisible, the
data send's loss invisible) is consistent with a one-frame early exit of *multi-byte* sends, and
H1's job is to find what starts it in each CASET. A per-send flag-read race (C1) or the post-DMA
FIFO state (C2) are the candidates; neither is shown.

**O2 (where the stray comes from).** Not from the DMA's own junk: the completion restores
RXFIFOTHIE (`hal_spi_v2_lld.c:318`) and the handler drains it before the main thread resumes
(`:112-118`), and glyphs 2..n do not follow a DMA at all. The 16-to-8 switch happens after
`TX_EMPTY && !BUSY` (`:308-311`), so no word is in flight at that moment; whether the switch and the
preceding RX overflow leave the FIFO's bookkeeping consistent is ASSUMED unknown, and the manual's
FRESET rule (`docs/sn32f299.md:864`) is not followed there (PROVEN). If a stray exists it is more
likely a *state* (C2) than a *word*.

**O3 (BUSY clear between bytes with TX non-empty).** Undocumented: the manual names the bit only
(`docs/sn32f299.md:867`). The driver's own single-frame idiom waits on `RX_EMPTY`, not `BUSY`
(`hal_spi_v2_lld.c:618-623`), and the board code records that a `BUSY`-only wait can return before
the RX word is published (`lcd_bus.c:573-576`). So RX lags `BUSY` on this silicon (measured, SPI1);
whether `BUSY` drops in the FIFO reload gap is the open question. Answer it by measurement, not by
reading.

**O4 (the panel's reaction).** Not in the repo (ASSUMED throughout). Two consequences are testable
by eye if H1 holds: the RASET straggler on the title line is 0x39, IDMON, which puts a GC9107-class
controller into 8-colour idle mode and nothing in `lcd_init()` or the restore sends IDMOFF (0x38)
(`lcd_bus.c:537-556`), so after a garbled title line the stock top-row icons' grey shading and any
dark-green battery fill should collapse to two levels until a panel reset; and the title cell at
x 10 sends 0x12, PTLON, harmless at the default partial area. If the greys survive a garble, the
RASET's last byte is *not* being read as a command, which would weaken H1's generic "last byte
under the wrong DC". The brief's `0x09` applies to a cell at x 1, which no line uses.

**O5 (USB repainted, Bluetooth did not).** The daemon sends `SET_LINE` (0x03) per line
(`ak820-agent/src/text/mod.rs:29`), so both lines normally arrive before one 10 Hz tick and paint
once, like Bluetooth; a second paint needs either a layout change (`moved`, with its own clears) or
a loss and the 5 s repair (`display.c:3069`, `panel_owner.c:224-236`). H1 does not explain E8; a
give-up over USB that did not happen over Bluetooth is the simplest reading, and the daily cannot
show it. The fix plan's entry counter would.

**O6 (daily alone).** Answered in 1.4: the machine code of the hot path is the same, so it is
timing or environment, and the dev record is short. "A missing barrier" is excluded.

**The single board measurement.** A build that *counts, without changing behaviour*, in
`spi0_poll_send()`: (a) exits where `rx == n` was reached while `TX_EMPTY` read clear, before the
`BUSY` wait; (b) RX words drained at exit beyond `n`; (c) RX words present at entry after the
`BUSY` spin; all three in health on every build. Flash it as a daily, play title changes, read. A
non-zero (a) that tracks garbled runs confirms H1's steps 1-2 on the board; zero (a) with garbles
refutes the SPI-side half and sends the hunt to the wire (a logic analyser on SCK, MOSI, DC and CS
at a title change is then the decisive instrument). The dev read of the `PO_FAIL` mask has already
been taken and is 0, so step 5 is settled. Note the brief overstates what dev exposes: nothing at
`4790208267` calls `lcd_spi0_poll_giveups()` (`lcd_bus.c:156` has no caller), so the give-up count
is unreadable on every build; only the sticky bit is.

---

## Part 3. The fix plan

**Sufficient for H1?** The exit wait for `TX_EMPTY && !BUSY` removes steps 2-3 for any byte that is
*queued*: no DC change under it, the panel sees `XE_lo` as a parameter, the window lands. It also
closes the same hazard at the DMA arm, where the `2C` send's straggler would otherwise meet Fire()'s
DL = 0xF (`lcd_bus.c:1160` then `:1205`). Provided `TX_EMPTY` is honest (ASSUMED), yes.

**Sufficient for the mechanism as I read it?** Not quite. Completion by RX count has a second
failure the plan misses: with `tx - rx < 8` as the only push gate (`lcd_bus.c:212`), an over-count
can end the loop while `tx < n`, with bytes never pushed. `TX_EMPTY` is then true and the fix is
blind to it. On a 224-byte send that drops the last pixels silently; on a 4-byte send it cannot
happen (all four are pushed at once), so it is not E5's fault, but it is the same class. Make
completion `tx == n && TX_EMPTY && !BUSY`, treat RX pops as a drain that never shortens the send,
and keep the existing iteration bound (`n * 64 + 1000`, `:196`) over the whole thing. That removes
every "a stray word ends the send early" path at once, whatever the stray's origin, which is the
right posture while the origin is unknown. If instead the trigger is on the panel or the wire, the
plan changes nothing and its counters will say so.

**Safety.**
- No new hang: every added wait must share the existing spin bound and fall into `poll_give_up(true)`
  as now (`:214-222`). A `TX_EMPTY` that never asserts then costs one bounded spin and a repaint.
- No pass of 25 ms or more: the added wait is at most one or two frames, 0.3-0.7 us a send, six
  sends a glyph, one glyph a pass. Nothing measurable.
- No lost completion: the plan touches no DMA flag; the completion's `IC = ris` stays
  (`hal_spi_v2_lld.c:298-299`). If an RX flush is added there, clear RXFIFOTHIF only after reading
  RIS and only if set, with a literal `1u << 2` write as the driver already does (`:116, :132`);
  never `IC = 0x3F` on that path. An FRESET in the ISR is safe only after the existing
  `TX_EMPTY && !BUSY` wait (`:308-309`), which it already has.
- The entry change (drain and count instead of refusing) is sound: `!blit_done`, `BUSY` after the
  spin and `state != SPI_READY` still refuse, so a DMA in flight or a stuck shift behaves as today;
  a stale word was never a reason to abandon a glyph. It also turns the blind spot in O1 into a
  counter.

**What else should change.**
- The completion's teardown: after `TX_EMPTY && !BUSY` and the `DL = 7` write, `FRESET` SPI0's
  FIFOs (the manual's rule for a CTRL0 change while enabled, and it clears the post-overflow RX
  state) before `IE = 0b0100`; then the narrow RXFIFOTHIF clear above. The callback and its CS drops
  stay last.
- The entry check: as planned, plus report the drained-at-entry count and the straggler count in
  health on every build, and give `spi0_poll_giveups` a reader (today it has none).
- The DMA arm's polled window: covered by the exit wait; add the `tx == n` condition so Fire()
  can never follow a window with a byte unpushed.
- Keep `spi1_raw_byte()` out of scope; its measured note (`lcd_bus.c:578-592`) says not to
  re-derive it.

**The board test.** The pump's loss path is `display.c:3069` -> `display_loss()` (`:3050-3058`) ->
`po_loss()` (`panel_owner.c:238-256`); every step below leaves it in place.
1. *Diagnose first, one flash:* the counting-only daily from Part 2, an hour of title changes over
   Bluetooth and USB, the counters read. This tells us whether the SPI side is even the place.
2. *Provoke it deliberately:* extend the `WDT_TEST_HOOKS` poll-fault machinery
   (`lcd_bus.c:161-175, 199-221`) with a mode that, for the next N sends, ends the RX loop at
   `rx == n - 1` and skips the `BUSY` wait **without** giving up, aimed at song-glyph CASET sends
   (`lcd_test_poll_fault_skip` already selects a window part). Without the fix this must reproduce
   E5's band and right-hand block on demand, which proves the panel-side half of H1 deterministically
   and independently of the natural rate. With the fix in, the same injection must paint cleanly,
   which proves the fix against the mechanism rather than against a quiet afternoon.
3. *The fix build, natural use:* title changes by eye on both transports; the straggler and
   entry counters (non-zero with a clean screen is the win the plan names); health's `count_ge_25ms`
   and the stall counts unchanged; no new give-ups; the menu, the `Fn`+`D` page and the position
   digits unchanged.
4. *The side prediction:* after any garble on an unfixed build, look for the idle-mode colour
   collapse (O4); after the fix, confirm the greys are intact.
5. *codex on the diff before the flash*, as planned; and the release note should say which builds
   carried the song face as default (v0.3.0 and v0.3.1, USB now-playing only, since Bluetooth
   now-playing reached the daily at `4790208267`).
