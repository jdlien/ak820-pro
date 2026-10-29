# The configuration menu in two faces, with a Font setting (plan, 2026-10-28)

**Status: on JD's board since 18:22 10-28 (`36fe62ea9c`, token
`0xf9274d6f`); B8 under way. From JD's first look the same evening
(`59b2c9d7b3`, token `0x1765e95a`, flashed 18:44):**
- **The dashboard's spacing.** In Large the song lines looked cramped.
  Terminus Bold's capitals are 10 rows to Cozette's 8 in the same 14-row
  cell, which left 1 blank row between the artist's descenders and the
  title's capitals, and 1 above the clock. Now the line pitch is 15, the
  clock 2 rows down and the lock row 1 down: 2 and 2 in Large (4 and 3 in
  Cozette), and clock to lock to battery 7 and 7. It is one layout for both
  faces; a layout per face was weighed and left out (a live move of the
  clock and lock row, for little gain in Small).
  [docs/display.md](../docs/display.md) has the table.
- **The Font page's values are 8px and 10px**, the capitals' heights, in
  place of Small and Large: JD found both faces small in absolute terms.
  The code keeps `MT_SMALL`/`MT_LARGE` and `ENV_FONT_*`.
- **The Font icon is being workshopped** in ak820-pro-90's 12 px icon
  artifact: the "Aa" placeholder is 16 px wide in Large, wider than every
  other icon (12 at most).
- **JD expected the 12 px greyscale icons in Large.** Built and flashed
  the same evening (`ccfe080920`, 18:59): rows' and titles' icons from
  `graphics/res/icons12_2bpp.h` through `mb_rows`; Back's and a page's
  triangles stay 1-bit. Codex: no findings on either evening commit.
- **JD's decisions for the next build (relayed by ak820-pro-90; built as
  `8b0f47e245`, not yet flashed):** Terminus regular as a third face, the
  Font page's 0.3 s preview (an `ME_FONT` edit, nothing written until the
  click) and a note under it, the face carried in every profile record
  (PR_BVIEW bits 2-3), About in Diagnostics as System info (fourteen top
  rows: two pages of seven in Large), and the Fn+D camera page removed.
  Heap gap 224 B after the camera page's RAM came back. Still open with
  JD: whether About's planned credits page joins Help's More info.
  Flashed 20:19; codex: no findings.
- **B8's redraw times, measured on JD's board at 20:30** (op 27 sub 10's
  repaint_ms, the board's own clock; `history/menu-font-timing-20261028/`).
  JD felt 10px drew a little slower:

  | Step | 10px bold | 10px | 8px |
  |---|---|---|---|
  | Open (top level) | 1,102 ms | 1,100 | 1,125 |
  | Cursor move | 249-255 | 246-253 | 234-237 |
  | To page two | 927 | 927 | 929 |
  | Into the Font page | 942 | 940 | 900 |
  | Back to the top (hold) | 1,027 | 1,047 | 925 |
  | Into Diagnostics | 823 | 843 | 589 |
  | Into System info | 917 | 916 | 981 |
  | The face changed, menu open | 1,104 | 1,088 | 1,108 |

  A cursor move is 6-8% slower in 10px (one more piece a row with an icon,
  as the risk table predicted); a whole page about the same (fewer, taller
  rows). Into Diagnostics is 40% slower in 10px because Small's page-two
  rows that were already blank stay blank and are skipped, where Large's
  seven are full. Bold and regular draw identically. The longest pass was
  18.6 ms in 10px bold and 18.1 in 8px; none of 25 ms or more in any face.
- **10px keeps bold where it marks something (JD, 10-28: "treating
  'regular' as 'we still judiciously use bold'"):** the page titles and the
  song's title are Bold in 10px; the artist, the rows, values and notes
  regular. The selected row stays as it is (the cursor's bar and the yellow
  already mark it). The oracle now runs in all three faces.

**Built 10-28 on the firmware's `menu-8x16` (from `ecb10f0e9b`),
B0-B7, the host checks passing; codex's code review, then B8 on JD's board.**
The plan had three codex reviews
([review-codex-menu-font-switch-2026-10-28.md](review-codex-menu-font-switch-2026-10-28.md)).
What the build found against the plan:
- **The dev build: 233,774 B of flash** (about 26 KB left), **the heap gap
  128 B, the floor: no new static RAM.**
- **The oracle:** the tour (`plans/menu-mockup/tour.c`) against the mock-up
  (`verify.js`) matches 26 of 27 frames in each face. The one difference
  is Diagnostics' dev-only Write test row, as before.
- **The Font page behaves as every choice does:** a click saves, flashes
  "Saved" and goes back up, the top level repainting in the new face.
- **The song text's line 1 is the title, 15 characters in Large; line 0
  the artist, 14.** The helper is `graphics/text_fit.c`; the pseudo font id
  is `0x0816`.
- **The knob turns the host's volume:** no band overlay to test with it;
  B8's overlay step uses Fn+Up or Fn+PgUp.

The survey behind it, with every line the 8x16 face touches:
[menu-8x16-survey-2026-10-28.md](menu-8x16-survey-2026-10-28.md).

## What and why

The menu gains a second face. Today it is Cozette 6x14 (20 columns x 8
rows). The new one is Terminus Bold 8x16 (15 columns x 7 rows). Capitals go
from 8 px to 10 and lowercase from 6 to 7, with a pixel more space between
letters. Terminus Bold won an on-board comparison of six faces (Cozette,
Terminus Bold, Terminus, Spleen, Dina Bold, Dina) on 10-28. It read as the
clearest, and the 15 x 7 menu proved workable, not cramped. Its two-storey
`a` (Cozette's is single-storey) stays.

A **Font** row on the top level switches between them: Small (Cozette, more
on a screen) and Large (Terminus Bold, easier to read). The same setting
picks the face of the dashboard's song title and artist.

The 8x16 layout is already designed: the mock-up
(`plans/config-menu-mockup.html`, built from `core.js`) lays out every page
at 8x16 with the shorter wording that needs. The build makes the firmware do
what the mock-up's 8x16 mode does in Large, and keeps doing what it does
today in Small. The mock-up's 6x14 mode is pixel-exact against the
firmware's host test, so it is the oracle for this build too (B7).

## Decisions

Settled:
- **The new face:** Terminus Bold 8x16 (`ter-u16b.bdf`, Terminus Font 4.49.1,
  SIL OFL 1.1).
- **Both faces stay, switched at run time** by a **Font** row on the top
  level, under Bootloader. Its page offers the two faces.
- **Small is today's menu, unchanged:** its wording, layout and behaviours,
  plus the Font row. Large is the new menu: the 8x16 layout with the
  shorter wording and behaviours of decisions 4-6. The switch is between
  "the original Cozette menu and the new one", in JD's words. The first
  draft shared the 15-column wording between both faces to save flash;
  it's dropped for three reasons:
  - Small would no longer be the original;
  - two sets cost about 1-2 KB of the ~34 KB free, the Large-only strings;
  - the existing host test and the mock-up's 6x14 mode then check Small
    unchanged, so a regression in Small shows as a failure there.
- **The setting also picks the song text's face** (the host text slot's
  title and artist lines).
- **The top level has 15 rows.** In Cozette that's two pages, 8 + 7. In
  Terminus Bold (7 a page) it's 7 + 7 + 1: Exit sits alone on a third
  page. That's accepted for now. Two ways to win it back later, both
  outside this build:
  - Diagnostics only in dev builds, which makes daily and fpb 14 rows,
    exactly two pages;
  - About folded into Help.
- **The icons for this build:** today's 1-bit redraw (`icons16.js`) for
  Terminus Bold, in the face's 44 extra codes, exactly as the mock-up shows
  them; Cozette keeps its own 1-bit set, with the wrench drawn by hand since
  10-28. The greyscale 12 px set is a later, separate change to how icons
  are drawn, for Terminus Bold only (see "After this build").

For JD (the plan proceeds on the recommendation unless he says otherwise):
1. **The Font page's values: Small and Large**, recommended over the
   faces' names, which mean nothing to most owners. The top-level row shows
   the value, as Screen shows its level ("Font  Large"). **Large is the
   default,** and Reset settings puts it back.
2. **The face survives a flash: recommended.** It rides the live record
   that `flash.sh` restores (B5). The alternative is a reset to Large at
   every flash, which JD would meet at every development flash.
3. **The song text's second line (the title): 15 characters from x 2,
   recommended,** keeping today's 2 px margin at the bezel. The
   alternative is 16 from x 0, with the first glyph's ink on the panel's
   first column (Terminus Bold inks column 0 of its cell for most glyphs).
4. **Large's layout: icons and values** (the mock-up's default, and what
   the comparison frames showed). The top level's Power row shows
   its bulb instead of the mode's name. The Profiles row shows the active
   profile's name, or "Profiles" when none is active. The alternatives
   were no row icons, or icons without values.
5. **Large's wording, as the mock-up has it** (Small keeps today's). The
   ones that change meaning most:
   - Reset settings → **Defaults**;
   - Connection → **Link**;
   - Effect → **FX**;
   - Lock lights → **Lock LEDs**;
   - Bluetooth n → **BT n**;
   - Hours of use → **Hours**;
   - Using the menu → **Menu basics**.

   The rest: Second color → 2nd color, Save current here → Save here, Pair
   device to BT n → Pair to BT n, Reset counters → Reset counts, Percent → %,
   and the titles Charging, Rename, Delete, "Turn + Click", "Loaded, no FX"
   and "Full: delete 1". The confirms are reworded to fit. The full list is
   in the survey's section 3.
6. **Large's Clock page shows only the examples** ("13:45:01", "1:45 PM",
   "Off") as each row's label. Label plus example no longer fits 15
   columns.
7. **Move the mock-up's source into the repo** (`plans/menu-mockup/`):
   `core.js`, `page.html`, `build.js`, `verify.js`, `mkfont8.js`, `bdf.js`,
   `frames.js`, the icon tools and the font hexes. They live in a session
   scratchpad under `/private/tmp`, which a restart wipes, and the build uses
   `core.js` as its oracle. The licences:
   - Terminus's BDF is OFL 1.1; its notice goes with it;
   - Dina and Spleen are only for the comparison and stay out.

## Does it fit the board?

Measured on `3b6e43ef73`'s build (225,270 B of flash used; the dev build's
heap gap 128 B, exactly `build.sh`'s floor).

| Resource | Free now | This build's cost |
|---|---|---|
| Flash (256 KB less the 2 KB emulated EEPROM) | ~34 KB | ~5-7 KB: Terminus Bold's table 2,256 B (141 glyphs with the Font icon; Cozette's grows 28 B to 1,974), Help and About wrapped twice ~1 KB, the per-face geometry tables a few dozen bytes, the run-time geometry's code 1-2 KB (a guess), the song text's branch a few hundred bytes. The Font test page isn't on the base, so it gives nothing back |
| Static RAM | 128 B gap, at the floor | **0 B, by design** (below) |
| EEPROM | | **no new byte:** two spare bits of an existing one (B5) |
| Asset flash (external) | | **nothing:** the song text draws from the menu's table in internal flash (B6), so no asset is added and no board is re-provisioned |
| Menu nodes (a row's node is 6 bits, `N_COUNT <= 63`) | 2 (`N_COUNT` is 61 on the base, `ecb10f0e9b`; the Font test's `N_FTEST` is only on `font-test`) | 2: `N_FONT` (the row, and its page as a frame) and `N_FOPT` (an option, its face in `val`, as `N_PSLOT` and `N_WROW` carry theirs). **That reaches the cap**; the next node needs the row signature widened |
| The pass budget (no pass of 25 ms or more) | | Terminus Bold is the heavier face: the icon chunk sits exactly at 512 B = `MB_PASS_BYTES`, and rows with an icon take one more piece. The song text's glyph is 224 B sent by the CPU in the pump's pass, where Cozette's is a DMA. Measured in B8 |

Why RAM stays at 0 B:
- **The setting** lives in `kb_eeconfig`'s battery-readout byte, whose
  block is already in RAM.
- **The geometry** is picked per draw from two `const` tables in flash, one
  per face, built from each face's `#define`s.
- **The buffers** are already sized for the larger case: the text buffers
  for 20 columns, the row structures for 8 rows.
- **The song text's queue and shadows** already carry a 16-bit font id per
  glyph and per line; the new face is one more id.
- **About's scrolling** uses the existing `frame_t.top`; `pg` stays 12 B.

If anything does need a byte, a saving comes first: codex's candidate from
P4 is `draw_battery()`'s `last_fw`, `last_txt_x` and `last_txt_w` as
`uint8_t`. `build.sh`'s heap-gap check fails the build below 128 B, so
nothing over the floor can ship by accident.

## The song title and artist in Terminus Bold

**It fits the band's height; each line holds fewer characters.** A bigger
face shows less of a long name, not more.

| | Cozette 6x14 (today) | Terminus Bold, cropped to 8x14 |
|---|---|---|
| Line 0 (the artist, beside the transport icon, from x 14) | 19 characters | 14 |
| Line 1 (the title, from x 2) | 21 characters | 15 (decision 3) |
| Capitals | 8 px | 10 px |
| Blank rows between a descender and the next line's capitals | 3 (2 to an ascender) | 1 (0 to the top of `" $ ' ^ ~`) |

- **The height.** The band is rows 27-54: two 14-row lines at y 27 and 41,
  with the clock below and nothing spare (`docs/display.md`, the vertical
  budget). Terminus Bold's 16-row cell inks rows 1-14 for every printable
  ASCII character but the backtick (row 0). The host folds the text to
  ASCII. So a crop of rows 1-14 fits the 14-row line with nothing lost but
  the backtick's top. Its capitals sit on the crop's rows 1-10, centre 5.5:
  the same centre as Cozette's (rows 2-9), so the transport icon's
  alignment needs no new offset.
- **The tight spot.** A descender (g j p q y, rows 12-14) above a capital
  leaves 1 blank row; above a quote or an apostrophe, 0. JD looks at it on
  the board first (the Font test page can show a frame of it before
  anything is built).
- **The text is stored whole and cut when drawn.** The host keeps sending
  19 and 21 characters (`MAXLEN` in `ak820text.py`, the daemon's mirror),
  and `text_buf` keeps them all. The draw clamps each line to the face's
  budget, so a change of face shows more or less of the same text without
  the host resending. The host truncates plainly today, with no ellipsis,
  so cutting in the firmware looks the same as cutting in the host. No
  protocol change.
- **The lines' order** is the producer's: `ak820text.py`'s `push_line()`
  and the daemon put the artist on line 0 and the title on line 1, so the
  title has the wider line. `display.c`'s comment calling line 0 the title
  is stale, and B6 corrects it.
- **The single-line case** (no second line, as when there's no artist and
  the title takes line 0; longer than 11 characters, so not the 20 px
  face) uses the active face too, its vertical offset restated per face.
- **The draw, B6:** a pseudo font id for "Terminus Bold, rows 1-14, from
  internal flash". `lcd_draw_flash_glyph_try`, `lcd_font_advance` and
  `lcd_font_height` recognize it and blit the glyph with `lcd_blit_mono`,
  painting the whole 8x14 cell, background included. The glyph queue, its
  one-glyph-a-pass pacing, the shadows and `band_clear`'s invalidation
  work unchanged: they see a font id with an advance of 8 and a height of
  14. Cozette's song text keeps today's atlas path untouched.
- **The pseudo font's contract** (the pump reads false as "busy, retry
  this glyph"):
  - busy: false before anything is touched, the existing
    `lcd_blit_busy()` guard, and the pump retries next pass;
  - drawn: true;
  - a bad rectangle or a failed send: true, the glyph consumed, and the
    loss latched as a failed send already latches it, so the pump's
    existing recovery repaints. `lcd_stream_begin` refuses a rectangle off
    the panel without latching anything, so the pseudo font latches it
    itself. Never false, which would retry it forever.
  - Every position the text slot can ask for is on the panel by
    `_Static_assert` (each line's x plus its budget times 8, and y plus 14),
    so the failure branch is for a fault, not for layout.
- **The table** is defined once, in `menu_text.c`. `lcd_bus.c` reaches it
  through an accessor that names Terminus Bold, not the active face.
- **When the change shows.** The face can change with the menu closed:
  `flash.sh` restores the live record over raw HID after every flash, with
  the dashboard on the panel. So every change goes through `font_set()`
  (B5), which calls `display_text_refont()`. That sets `text_dirty`, so the
  text slot is queued again. `queue_line` already treats a run whose font
  changed as moved and queues every glyph again (the `moved` branch). On
  the same row at the same height, which both song faces are (14 px), it
  clears only the columns the old run covered and the new one doesn't;
  every new glyph paints its whole cell, so that is enough. Glyphs already
  queued keep their own font ids and finish first. With the menu open,
  its close runs the staged restore, which repaints the band anyway.
- **Rejected: a Terminus Bold atlas on the external flash.** It would draw
  exactly as today, but asset ids are assigned by sorted filename. Every
  board would need a re-provision, and a firmware meeting a board without
  the asset would need a fallback. The internal table costs nothing extra:
  the menu already carries it.
- **The other text in that band** (the overlay, the connection status, the
  20 px single line) and the debug and camera pages keep their faces.

## The build

Branch `menu-8x16` in the firmware clone, from `ecb10f0e9b` (Warren's
`gremlin/pcf-unseen`), what the board runs minus the Font test page. If
Warren merges that before B1, it branches from the merge instead. The Font
test page was never on that base, so the board loses it when this build
goes on.

One commit a step below. **Each commit carries its own test changes** (the
expected frames, repaint counts, asserts and bounds checks its code
moves), so the host test passes at every commit, in both faces from B2
on.

**B0. The mock-up learns the Font setting** (it is the oracle, so it leads):
the Font row and page, the switch's re-layout, the 15-row top level's
paging in both faces, and a dashboard preview of the song text in both
faces. `core.js` and `page.html` are shared with ak820-pro-90, so this
waits on a message between the sessions (Coordination).

**B1. The faces.**
- **The source:** `ter-u16b.bdf` goes into `assets-src/` with its licence.
- **The generator:** `scripts/gen_mono_font.py` learns an 8x16 BDF (CW 8,
  CH 16, baseline row 11, no x shift). The atlas cross-check stays for
  Cozette's table only.
- **The extras:** the five at 0x80-0x84 (‹ › • ▸ ✓) are Cozette's centred,
  as `mkfont8.js` does; Terminus has no ▸, and they're only used by the
  fixture. The cursor, 0x87, is rows 0-14. Terminus Bold's icons come from
  the source agreed with ak820-pro-90: today, the template PNG JD edits,
  read 1-bit.
- **The Font icon,** new in both sets: a pair of cells in each table, drawn
  for each face (Cozette's in `DRAWN`, Terminus Bold's in the template).
  The 12 px greyscale set gains a 25th later.
- **The output:** `graphics/res/font_menu_mono.h`, `[141][16]` = 2,256 B,
  beside `font_small_mono.h`, `[141][14]` = 1,974 B: 95 ASCII and 46
  extras each, two more for the Font icon. `menu_text.c`'s extras assert
  goes to 46. Each table is defined once, in `menu_text.c` (the generator
  emits a `static const`, so a second include would be a second copy).
  `mt_bits` takes the active face's table, cell width and mask.

**B2. The geometry, per face** (the survey's sections 1 and 2). Each face
gets its `#define`s and a `const` table built from them, and the code reads
the active face's table. Cozette's numbers are today's; Terminus Bold's:
- **A `MENU_COLS` (15).** It replaces the 23 bare `20`s in menu.c and
  `L_LIST`'s 11. MENU_ROWS becomes 7. The `cells[21]` buffers stay sized
  for Cozette's 20.
- **The F3 fixture stays on Cozette:** its eight rows at a 14 px pitch,
  its 20-cell lines and `TEXT_W`, with Cozette's table, cell and mask
  named explicitly rather than the active face's. `menu_s1_gate.py`'s
  eight rows stay right, and F1's atlas geometry is untouched.
- **The host test's bounds checks come first,** in this commit: the fake
  `mb_mono` and `mb_rows` refuse a rectangle off the panel (today they
  write past the framebuffer), so a leftover 20-column or 8-row layout
  fails instead.
- **`mt_bits`' 0xFC mask** becomes the cell's own (0xFF for Terminus Bold).
  Otherwise columns 6-7 vanish without any failure: 0xFC is the 6-px
  cell's mask, and the host test's own copy has the same 6/0xFC assumption,
  so it changes in the same commit.
- **`HALF_W` stays 60 px** (as `MENU_COLS * MT_CELL_W / 2`), not
  `10 * MT_CELL_W`, which would put the right half off the panel. The
  derived widths follow: SPLIT_W 44, the icon chunk 16, BULB_CHUNK_W 14.
- **The title at y -1:** `text_piece` gets a first-glyph-row offset (its y
  is unsigned). The title's glyph rows 1-15 go to y 0-14, and the separator
  moves to y 15.
- **The positions** from `core.js`'s `geometry()`:
  - rows at y 16 + 16 r, the scrollbar from y 16;
  - the confirms' lines {24, 40, 80, 96}, the info lines {24, 40, 56, 96};
  - the editors' bar at y 56-65, the strip at 24-37, the envelope at
    22-42, the values at y 24 and 48, the hints from y 80 every 16;
  - the profile summary from row 5 in 2 lines, the battery notes from
    row 4;
  - the bulb 1 px down in its row: `BULB_H == ROW_H` becomes
    `BULB_DY + BULB_H <= ROW_H`.
- **The asserts:** each of the 31 is stated for both faces, from each
  face's `#define`s. The ones that fail or sit at a limit (the survey's
  section 2) are restated. Two sit exactly at a limit in Terminus Bold: the
  icon chunk, at 512 B = MB_PASS_BYTES, and the Clock's and the summary's
  rows, at 7 of 7. They get a comment saying so.
- **The uses:** about 150 in `menu.c` read the table instead of a constant
  (`MENU_ROWS` 30, `ROW0` 28, `ROW_H` 17, `MT_CELL_W` 16, `HALF_W` 16, the
  bare `20`s, and the rest). Each stays a compile-time constant where only
  one face reaches it.

**B3. The text** (the survey's section 3): the labels, titles, flashes,
the battery notes, the profile summary's new format ("H180 S100 B80" from
cell 0), the confirms and pairing's lines, for Large. Small keeps
today's strings: each text function returns Large's string where it
differs and falls through to today's.
- **Help:** MENU-TEXT.md gains a 15-column block per topic beside today's
  20-column one (the mock-up's `HELP_LINES_W`), and `gen_menu_text.py`
  emits both sets; the active face's pages are read.
- **About** has eight lines: they fit Small's eight rows and scroll in
  Large's seven.
- **Still to word** (the mock-up never modelled them): the pairing's failed
  and unsure lines; About's flavour line for daily, instr and fault builds
  ("daily, 0x%08lx" is 17, over 15); the dev Write test's rows.

**B4. The behaviours the 8x16 mode brought, in Large only** (the survey's
section 4; Small's paths stay as they are):
- **The Power row's bulb at the top level.** `l_first` must compare the
  mode too, or a Fn+B change leaves the old bulb.
- **The Profiles row's active name**, cut to the face's room (11 in
  Terminus Bold).
- **The Clock's examples as labels.** `clock_sig` and `l_first`'s
  right-half repaint are redone: in Terminus Bold the minutes now sit in
  the left half, and 1-9 o'clock's seconds cross x 64, so a
  right-half-only repaint leaves stale digits.
- **About scrolling,** paged like the Help topics, through `frame_t.top`.
- **The paging and the scrollbar's sizes,** which follow the face's rows.

**B5. The Font setting.**
- **Storage:** bit 2 of `kb_eeconfig`'s `batt_view` byte, which holds the
  readout (1-3, 0 unset) in bits 0-1. Bit 2 set means Small, so a zeroed
  byte reads Large, the default. QMK zeroes the block when it initializes
  the EEPROM, which is why every `_p1` field reads 0 as unset. **A byte
  with any of bits 3-7 set is garbage as a whole** (0xFF, an erased
  block): the percent readout and Large. Every reader and writer of the
  byte changes in this commit, through one normalizer, `bv_norm()`: a
  garbage byte becomes 0, the defaults, before anything reads, compares
  or keeps a field of it.
  - `kb_eeconfig_get_batt_view()` reads bits 0-1 of the normalized byte;
  - `kb_eeconfig_set_batt_view()` normalizes, keeps bit 2, compares bits
    0-1, and writes the canonical byte: so setting Hours over 0xFE writes
    0x02 rather than returning early on matching low bits;
  - a new pair, `kb_eeconfig_get_font()` and `_set_font()`, owns bit 2 the
    same way, with `menu_env.h`'s `env_font()` and `env_font_set()` over
    them.
  A firmware from before this build reads a byte with bit 2 set as
  garbage and shows percent: harmless. The live record is the one place
  a downgrade could hurt; see the live record below.
- **One way to change the face, `font_set()`,** used by the Font page, by
  Reset settings and by the live record's restore over raw HID. It saves
  the bit, and when the face changes it calls `menu_refont()` and
  `display_text_refont()` (B6).
- **When the menu re-lays out:** only when the configuration menu itself
  holds the panel: the session is the menu's (`MK_MENU`, not the F3
  fixture's), the panel's owner is `PANEL_MENU`, and the session is
  `SESSION_OPEN`. Anywhere else `menu_refont()` changes nothing: F3's
  layout stays, the panel's owner is never changed, and a session open
  under Diagnostics' debug page rebuilds the menu when it comes back, as it
  already does. No new state.
- **`menu_refont()`, the geometry's transition.** A page push only
  retargets (`show()` calls `ms_retarget()` between list pages, and Reset
  does the same), which keeps the old geometry's slots. So the transition:
  - calls `ms_set_layout()` with the current page's layout in the new
    face (List, Confirm, Range or Hue) and `fresh`, for the banded clear
    and every slot invalidated;
  - keeps each list frame's cursor and re-derives its `top` for the new
    row count (`top = cursor / rows * rows`, as `core.js` pages);
  - puts a Help topic's or About's reading position, which lives in
    `top`, back to the first line: their lines wrap differently per face.
- **The menu:** `N_FONT` on the top level after `N_BOOT`, showing its
  value; its page is Back, Small, Large, with the check box on the active
  one, like the Battery page. It behaves as every choice does: a click on
  an option calls `font_set()`, flashes "Saved" and goes back up, where
  the top level repaints in the new face (the preview); Back or a hold
  before a click changes nothing and says "Cancelled", as any choice's
  does. So nothing is saved that a Back could seem to cancel.
- **Reset settings** puts Large back, through `font_set()`.
- **Profiles: saved profiles and the Win/Mac switch's side records never
  carry the face.** It's a reading preference, not a look, and a profile
  key or a flip of the switch shouldn't change it. The face stays out of
  everything they share with the live record: `prof_capture()`,
  `prof_differs()` (which compares `PR_BVIEW` byte for byte: a face in it
  would put the modified-profile `*` on every profile in Small),
  `body_ok()`'s range check, and `prof_apply()`. Applying a record sets the
  readout through its setter, which keeps the face.
- **The live record carries it** (decision 2), so `flash.sh` keeps it,
  only at its raw-HID edges:
  - the export (`HC_PROFILES` op 4) packs the face into `PR_BVIEW`'s bit 2
    after `prof_capture()`, then takes `PR_CRC` again over the packed
    byte;
  - the import (op 5) checks `PR_CRC` over the record as it came, takes
    the bit out and takes `PR_CRC` again, then runs the shared validation
    (`body_ok()` checks the CRC too) and the apply, then calls
    `font_set()`. Only a record whose fields are `PF_LIVE` sets the face:
    any other record applied over op 5 leaves it alone;
  - `ak820profiles.py` shows the readout and the face apart, and passes
    the bit through;
  - **a downgrade:** firmware from before this build rejects a live record
    whose `PR_BVIEW` has bit 2 set (its range check is 1-3), and op 5
    refuses the whole record, so the screen, clock, indicators and the rest
    would not come back either. So `ak820profiles.py`'s live restore, on
    `PROF_INVALID` from a record with bit 2 set, clears the bit, takes the
    CRC again and sends it once more: the old firmware gets everything but
    the face, which it doesn't have. Its test covers both answers.

  Records written by earlier firmware have bit 2 clear: Large.
- **Its tests, in this commit:**
  - `scripts/diag_sim/kbee.c`, which builds the real `kb_eeconfig.c`: the
    readout and the face set and read in every order, each leaving the
    other alone; 0x00, 0xFF and every garbage byte;
  - `scripts/profiles_test.c`: a saved profile, a profile key and a
    Win/Mac flip all keep the face; Small doesn't put the `*` on an
    unmodified profile; the live record's export and import carry it; a
    record from earlier firmware reads Large;
  - `ak820profiles.py`'s tests: the decode and the pass-through;
  - `menu_s0_test.c`: a change of face on every page that can reach the
    Font page, and under the test from deep stacks (Help mid-topic,
    About scrolled, a profile's confirm, an editor), with every frame's
    cursor and top checked afterwards; a change with the cursor on the
    top level's 15th row; Reset settings from Small; a change while the
    F3 fixture holds the panel, and while the session sits under the
    debug page, neither of which may re-lay out anything.

**B6. The song text** (the section above):
- the pseudo font id in `lcd_bus.c`, with its contract (busy, drawn,
  failed) and the accessor to Terminus Bold's table;
- `display_text_refont()`, which sets `text_dirty`;
- the face read where the text slot's lines are queued, the single-line
  offset per face;
- **the budgets and the cut in a small pure helper,** with a host test of
  its own, as `batt_text.c` has. No host harness builds `display.c` or
  `lcd_bus.c`, so the drawing itself is checked on the board (B8);
- the `_Static_assert`s on the budgets restated per face.
  `DISPLAY_TEXT_MAX_L0` and `_L1` stay 19 and 21: they are the host's
  budget and the buffers';
- `display.c`'s comment on the lines' order corrected (line 0 is the
  artist).

**B7. The checks across the whole build, on the host** (each step's own
tests went in with it):
- **`menu_s0_test.c`: Small's assertions stay as they are,** and Large
  gets its own beside them (the survey's section 5 lists what Large's
  differ in). Small's expected frames change only where the build means
  them to:
  - the Font row shifts page two's rows and the scrollbar (15 rows: the
    thumb 60 px, page two's from y 67);
  - Reset settings from Small puts Large back, so the frames after a
    reset change;
  - every Large-only behaviour (the Power row's bulb, the Profiles row's
    name, the Clock's examples and their repaint, the summary's format,
    Help's and the notes' words) is checked not to reach Small.
  The tour runs once in each face, with the bounds-checking fakes from B2.
- **The tour drivers** (`plans/menu-mockup/tour.c`, `verify.js`) learn the
  Font row's indices, and the oracle's frames are taken again in both
  faces: the 25-of-26 match of today certifies the old Small, not this
  one.
- **The oracle:** `verify.js` replays the host test's tour in both faces
  and compares every frame with `core.js`'s pixel for pixel. 6x14 matches
  25 of 26 today; the one difference is the Write test, which the mock-up
  omits on purpose. Every difference is either a firmware bug or a mock-up
  gap, and is written up either way.
- **The song text's helper:** each line cut at each face's budget, the
  single line, a line exactly at the budget and one over it.
- **The pseudo font's busy and failure paths** have no host harness
  (`lcd_bus.c` is the hardware's). The busy path is the existing
  `lcd_blit_busy()` guard, unchanged; the failure path is checked in the
  build's code review and, on the board, by B8's fault step.
- **The build's checks:** the heap gap at or above 128 B, in dev, daily
  and fpb.

**B8. On the board** (JD's, on battery, mid-drain unless it has ended;
`flash.sh` keeps the settings), in both faces:
- the longest pass on each page, and the count of passes of 25 ms or
  more (`health.c` counts `gap >= 25`), which must stay 0;
- the time to repaint a page after a knob move, and after a change of face;
- **the song text, with a track playing,** in this order:
  1. Small, then Large from the Font page: the band in Large as the menu
     closes;
  2. the same track still playing (no new text from the host), the live
     record restored over raw HID with the menu closed, carrying the
     other face (`ak820profiles.py`'s restore, as `flash.sh` runs it):
     the band redrawn in it within a second, with no stray cells;
  3. that restore again while the text slot is mid-repaint (just after a
     track change);
  4. a title longer than 15 characters and an artist longer than 14, in
     both faces;
  5. the longest pass on the dashboard while the text repaints in Large
     (each glyph is the CPU's, not a DMA);
  6. the cases beside two lines: one line of 12-21 characters (the small
     face), one of 11 or fewer (the 20 px face, which no face change may
     touch), and a change of face with the overlay holding the band (Fn+Up's
     brightness readout; the knob's volume goes to the host and shows
     nothing), which must come back in the new face when the overlay
     retires;
  7. the restore over raw HID just before and just after the dashboard's
     forced text stage, as the board comes back from the menu;
  8. if `scripts/menu_s1_fault.py`'s send-failure injection reaches
     `lcd_blit_mono` on the dashboard, a failed glyph in Large: the line
     must be repainted whole by the pump's recovery, and the loss counted
     once;
- the screens themselves, which JD looks at.

## Risks, and what catches each

| Risk | Caught by |
|---|---|
| Glyph columns 6-7 dropped by the 0xFC mask | the 8x16 oracle compare (B7); a host check on `%`, which inks column 7 |
| A leftover 20 / 8 / 10-cell constant drawing off the panel (the panel refuses it silently, the host fakes overrun) | the bounds-checking fakes (B2); the oracle compare in both faces |
| A constant from one face left in a path the other face reaches | the tour and the oracle run in both faces |
| The icon chunk at exactly 512 B per pass | the assert, plus the host test's `max_pass_bytes`, which stays at or under 512 |
| Rows with an icon go from 9 pieces to 10 in Terminus Bold (the split half paints 5 rows a piece, now 4 pieces); the top-level Power row is 11. Slower page repaints | B8's page-repaint time. If it reads slow, the halves go 58/63 px, which brings split rows back to 9, a one-commit change |
| The bulb piece grows 392 → 448 B; it measured 9.7 ms at 14 rows, so likely about 11 ms (a guess) against the 15 ms pass mark | B8's longest-pass reading on the Power page |
| Stale Clock digits after the move to left-aligned examples | a host check that steps the clock across 9:59:59 → 10:00:00 in 12h:ss, and B7's oracle |
| The top-level bulb not changing after Fn+B | a host check: Fn+B with the menu open on the top level |
| The face bit corrupting the readout, or the readout's writer clearing the face | B5's `kbee.c` checks, against the real `kb_eeconfig.c` |
| A saved profile, a profile key or a Win/Mac flip changing the face; the `*` on every profile in Small; a profile's check rejecting the live record | B5's `profiles_test.c` checks; `ak820profiles.py`'s tests |
| A frame's cursor or top left past the new row count, or the old geometry's slots kept, after a switch | B5's switch checks on every page and from deep stacks |
| The song text left in the old face after a restore with the menu closed and the same track playing | `display_text_refont()` (B6); B8's song-text steps 2 and 3 |
| A line's old cells left beside a narrower face | `queue_line`'s `moved` branch, which clears the old run; B8's steps 1-2 |
| The pseudo font retrying a bad glyph forever | its contract (B6): a failure consumes the glyph |
| A dashboard pass grown by the CPU's glyph | B8's step 5 |
| The menu's node count over 63 | the existing `_Static_assert` |
| RAM over the floor | build.sh's heap-gap check |

## Coordination

- **Warren** owns the menu's code and its plan
  ([CONFIG-MENU-BUILD-PLAN.md](CONFIG-MENU-BUILD-PLAN.md), WARREN-STATUS.md).
  This change touches nearly every page's geometry in `menu.c`, so any menu
  change he has in flight should land first or wait. He's the natural
  second reviewer, and gremlin's board can repeat B8.
- **ak820-pro-90** owns the icons: their source, format and greyscale
  design, and the Font icon in both sets. B1 reads whatever icon source is
  agreed with it. The shared mock-up files (`core.js`, `page.html`,
  `build.js`, `mkfont8.js`, the font hexes) change only after a message
  between the two sessions; B0 is such a change.

## After this build (not in it)

- **The third page's lone Exit:** Diagnostics only in dev builds, or About
  folded into Help (Decisions).
- **A face for the debug and camera pages,** if JD wants them to follow the
  setting.
- **The greyscale set's licence: the concern is acknowledged and set aside
  (10-28).** The set is derived from Font Awesome Pro+ 7.3.1, which is
  commercially licensed. A 2 bpp table built from it will sit in the public
  firmware repo and in released binaries. JD's reasons for going ahead:
  - the icons are tiny bitmaps, some of them modified, derived from the
    artwork;
  - no vector source is shipped;
  - JD holds a Pro licence for his own use.

  For the record, 21 of the 22 Font Awesome picks are also in Font Awesome
  Free (CC BY 4.0). The set's working files stay in
  `~/Documents/ak820pro-icons/` (the template, the set of record
  `tools/icons12.json`, and `tools/icons12.py`).
- **The 12 px set is final (10-28).** Its packed table is
  `~/Documents/ak820pro-icons/tools/icons12_2bpp.h`, made by
  `icons12.py pack`, which checks it against the JSON (24 of 24).
  - The layout: `icons12[24][64]`, 1,536 B. Each icon is a 16x16 cell, 16
    rows top first, 4 bytes a row, with the leftmost pixel in bits 7-6.
  - The icon sits on pixels 1-12, centred on the line between 6 and 7. Back
    and Opens a page sit on 3-10.
  - The `ICON12_*` order is the template's, not the font's 0x80-0xAB codes.
  - For another packing or mapping, change `icons12.json`'s packer, never
    the header by hand.
  - The colours are the 1-bit set's, with level n at n/3 of each RGB565
    channel: white, `MENU_ICON_LIT` on the lit row, `MENU_SAVED`, and
    `link_colour[]`'s Trying and Failed.
- **The greyscale icons** (Terminus Bold's face only; Cozette keeps its
  1-bit set): 16x16 at 4 levels, in a table of their own,
  drawn through `mb_rows`/`lcd_blit_rows` with the colour scaled per level.
  The background is always black, so a level is just a fraction of the
  icon's colour. A 16x16 icon in RGB565 is exactly one 512 B piece. The cost
  to measure is the per-pixel fill against `lcd_blit_mono`. Every icon
  becomes 16 wide, which costs no columns: each 8 px icon is followed by a
  space today. The icon mock-up's ▶ is two cells wide; the plan keeps the ▶'s
  width a single constant so that's a one-line change. That workstream
  writes its own plan, and its 1,536 B of flash comes out of what's left
  after this build.
- **The 10x23 face** (FONT_STATUS, the editors' values) is unchanged; only
  its y moves in Terminus Bold (24 and 48).
