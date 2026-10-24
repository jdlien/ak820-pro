# Codex's review of S1's mono text, 2026-10-24

Prompt: [`review-prompt-s1-mono.txt`](review-prompt-s1-mono.txt). Reviewed:
qmk_firmware-ak820pro `gremlin/s1` commit `3f0275ca`, with
`scripts/gen_mono_font.py` and `scripts/menu_s0_test.c`. Model
`gpt-6-astra`, reasoning xhigh, read-only. No blocker for the test flash.

## Dispositions (Warren)

- **1, two software divisions a column in `mt_bits`:** fixed in `158e876d`
  before the flash, since half against full rows is decided by measuring
  these pieces: the cell and glyph column advance a column at a time.
  Followed up by [`review-prompt-s1-mono-fixes.txt`](review-prompt-s1-mono-fixes.txt).
- **2, the boundary test misses late half-row pieces:** fixed in the test:
  it measures the interrupted repaint (`next`) apart from the selection
  change's (`full`) and runs to the longer.
- **3, the font check proves ink, not the RGB565 atlas:** fixed: the
  generator now requires opaque magenta at each marker and opaque pure
  black or white everywhere else. The shipped atlas passes.
- **4, the expansion runs on after a failed full-buffer send:** fixed in
  `158e876d` (break when `stream_broken`). F3's pieces (488 B) couldn't
  reach it.
- **5, the documented host build omits `menu_text.c`:** fixed, with a note
  that the fake `mb_mono` bypasses the stream, whose failure paths the
  board's `menu_s1_fault.py` now covers on F3 (12 mono cases).
- **The op 27 coverage for 16-19:** added to `test_ops`.
- **Measurement gates (the 15 ms pass, stack watermarks, fault behaviour
  on hardware, the panel's appearance):** accepted; they're the flash's
  purpose.

## The review, verbatim

**I found no correctness blocker for the test-board flash of `3f0275ca`.** The stream cleanup, bitmap bounds, slot signatures, and transitions look sound. The avoidable CPU cost deserves attention, but I cannot establish a 15 ms violation from inspection.

All reads stayed inside the workspace. I verified the changed firmware files against the commit’s Git blobs. Process launching was blocked, so I could not run the C suite or Python generator; I independently checked the font data in memory and inspected the existing mono ELF.

Findings that can wait until after the first measurement flash:

1. **`mt_bits` performs two software divisions per text column.**  
   At [menu_text.c:35](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_text.c:35), `/ 6` and `% 6` compile into separate `__aeabi_uidiv` and `__aeabi_uidivmod` calls in the existing ELF.

   A half-row piece processes 60 text columns: **120 division calls**. A full-row piece processes 120: **240 calls**, despite both sending at most 244 pixels. Across one complete row, that becomes 960 versus 1,680 calls. This introduces a CPU-cost difference into the half/full comparison beyond their scheduling and window costs.

   Cheap fix: track the current cell and glyph-column mask incrementally, advancing the glyph pointer every six columns. No RAM lookup table is needed. Mono also adds per-pixel expansion, so it will cost more than an equal-size fill. The fake backend’s constant timing cannot quantify that difference; measure the whole pass.

2. **The “every piece boundary” test misses late half-row boundaries.**  
   [menu_s0_test.c:800](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:800) measures `full` while repainting style `st`, but the style-change and fault cases at lines 812–822 interrupt a repaint of `st + 1`.

   For `st == 1` or `3`, `full` is 72 passes, while the interrupted half-row repaint takes 81. Consequently, the loop misses interruptions during the last row’s pieces, including its second chunk. Measure the interrupted source repaint separately, or use separate boundary loops. The current firmware restart rule handles those cases correctly by inspection.

3. **The font check proves binary ink placement, not arbitrary PNG equivalence.**  
   [gen_mono_font.py:81](C:/Users/jdlien/code/ak820-pro/scripts/gen_mono_font.py:81) discards alpha; line 99 thresholds RGB. Changing white to `(201,201,201)`, making white transparent, or changing a black background pixel to red can leave this check passing while the RGB565 atlas changes.

   This does **not** affect the current asset: I independently found exactly 95 magenta markers, 6,570 black pixels and 1,315 white pixels in an RGB PNG. All 95 glyphs match the BDF at `xshift = -1`; no glyph occupies the marker pixel; all five extras match both BDF and `EXTRA13`.

   Cheap hardening: require opaque black/white pixels, with magenta permitted only at the designated markers. Until then, “pixel for pixel” is stronger than the generator’s general guarantee.

4. **Expansion stops at the next row boundary after a failed full-buffer send.**  
   [lcd_bus.c:407](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:407) does not check `stream_broken` inside the column loop.

   Example: a valid `122 × 4` bitmap, with the first 512-byte payload failing, continues expanding the remaining 110 pixels of that row. It sends no further payload and cleans up correctly. Current F3 pieces are at most 488 bytes, so they cannot trigger this case. Add `if (stream_broken) break;` after the full-buffer send to make the stated immediate-stop behavior true.

5. **The documented host-test build command no longer links.**  
   [menu_s0_test.c:9](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:9) omits `$D/menu/menu_text.c`, now needed for `mt_bits` and `mt_width`.

The requested correctness checks:

- **Stream and scratch:** [lcd_bus.c:364](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:364) acquires scratch once; `lcd_stream_bytes` directly sends the supplied bytes synchronously. Passing `lcd_scratch` therefore causes neither reacquisition nor an overlapping conversion. No pointer survives the send.

  | Path | Result |
  |---|---|
  | Bad rectangle | `begin` returns false before acquiring anything; mono correctly skips `end` |
  | Window failure | `begin` returns true with an open, broken stream; mono skips expansion, zeroes `stream_left`, releases scratch and CS, returns false |
  | Payload failure | Poll sender latches loss; mono discards the remainder, releases scratch and CS, returns false |
  | Success | Exactly `2*w*h` bytes consumed; `end` sees zero remaining |

  Thus give-ups do not falsely raise `PO_FAIL_STREAM`; they raise the polling failure and latch `blit_lost`. The WDT scope covers begin, expansion, sending and cleanup, and GCC cleanup restores it on early returns. Foreground and background both go **high byte first**, matching the fill and RAM paths.

- **Bit order and bounds:** [menu_fixture.c:185](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:185) supplies valid ranges. The left half covers line columns 0–60: pad x3, then cells 0–9 through x63. The right starts at column 61: cell 10 at x64, ending with the trail at x124. Half-row bands are `4+4+4+2`; full-row bands are seven lots of two. The final glyph access is row 13.

  Both forms require only **32 bitmap bytes per piece**. `BITS_MAX == 64` and its assertions cover the configured budget. The cast to `uint8_t` before `glyph()` makes extras and invalid high-byte fallback independent of host/ARM `char` signedness.

- **Slots and transitions:** [menu_fixture.c:146](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:146) gives text slots disjoint slot/style/selection fields. Style changes therefore invalidate a PARTIAL slot’s signature before its old chunk or piece cursor can resume. Every chunk covers its entire share, including background and edges. Separator and scrollbar signatures remain unchanged because their targets remain unchanged.

  `fx_set_mono` uses a layout clear from F1/F2 and a retarget within F3. `fresh=false` preserves an ongoing clear and a reached stop correctly. F3→F2 is correct. Diagnostics returns to **F1, row 7**, preserving the existing C9 behavior; it does not remember F3.

- **Op 27 sub 0:** [menu_ops.c:221](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:221) accepts exactly:

  | Pattern | Preconditions |
  |---|---|
  | 0–1 | MENU/OPEN, F1, `n == 0` |
  | 2 | MENU/OPEN, F1, settled A, `1 <= n <= 26` |
  | 3 | MENU/OPEN, `n == 0`; F1/F3→F2, F2→F1 |
  | 16–19 | MENU/OPEN, `n == 0`; select F3 style |
  | Everything else | Rejected |

  Single-flight checking still precedes mutation. The explicit F1 guard prevents pattern 2 from accepting F3, independently of `fx_pattern()` returning 16–19.

- **Budget and RAM:** Text pieces peak at **488 B**, separator at 240 B, scrollbar’s two fills total 276 B. One piece runs per pass. These satisfy `MB_PASS_BYTES`; they do not prove the wall-time target.

  The existing mono dev ELF has `.data = 2,792 B`, `.bss = 26,648 B`, and a **240 B heap gap**, versus 248 B in the parent dev ELF. That leaves 112 B above C5’s floor. Relative to C5’s recorded baseline and 512-byte scratch saving, the figures imply 304 B of added static RAM, within 400 B.

  `font_small_mono` is exactly **1,400 B in `.rodata` at `0x29460`**; its bytes match the header. The text-pointer tables and F3 layout are also in `.rodata`. Nothing copies the font into RAM. The 64-byte bitmap is stack-local; heap-gap evidence does not establish stack headroom, so C5’s watermark measurement remains necessary.

- **Test independence:** `expect_f3` independently computes final coordinates and glyph pixels, so it meaningfully checks composition and scheduling. It intentionally shares text, colours and font data with firmware, so it cannot validate those inputs independently. More significantly, fake `mb_mono` bypasses **all production stream code**: byte order, CS/scratch release, bad rectangles and multi-buffer failure handling could regress without failing these tests. New patterns 16–19 also lack direct `op27()` coverage; current tests call `fx_set_mono()` instead.

**Before this test flash: no required source fix identified.** I would remove the division-heavy compositor before making the final half/full-row choice. The 15 ms whole-pass bound, stack watermarks, fault behavior on hardware, and panel appearance remain measurement gates—not conclusions supplied by the host tests.
## The follow-up on `158e876d`, verbatim

Prompt: [`review-prompt-s1-mono-fixes.txt`](review-prompt-s1-mono-fixes.txt). No required fix.

**I found no required fix before the test-board flash in `158e876d`.** Both changes preserve correctness.

- **Incremental columns:** [menu_text.c:28](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_text.c:28) matches the old division-based indexing. Starting inside the lead leaves `(cell, gcol)` at `(0, 0)` until text begins. Starting inside text initializes the correct cell and remainder. Starting in—or crossing into—the trail takes the edge branch without dereferencing a glyph. The fixture’s halves cover cells 0–9 and 10–19 respectively, with the appropriate edge pixel; the full band agrees.

- **Glyph reset:** After column 5, `gcol` becomes zero, `cell` advances, and `g` becomes `NULL`. The next text column fetches the next glyph, including the transition from string content to space padding. A band starting midway through a cell also fetches correctly.

- **Failed sends:** [lcd_bus.c:413](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:413) resets `n` before breaking. The outer loop then stops, and the final partial send is skipped. For `122 × 4`, failure of the first 512-byte send leaves `stream_left == 464`; the existing failure cleanup clears that before `lcd_stream_end`, avoiding a false short-stream error while releasing scratch and CS and returning false. Successful and final-partial-send paths remain correct.

I verified the commit blobs and ran independent in-memory comparisons covering all 8-bit cell counts and general band boundaries, plus fixture bitmap and stream-state cases; no mismatches. All file reads stayed inside the workspace. Process launching was blocked, so I did not rerun the C suite.