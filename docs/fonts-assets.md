# Fonts, atlases, and provisioning the flash assets

The asset pipeline lives in `time-util-ak820pro/assets/` (`mkraw.py`,
`mkanim.py` — stdlib only, no Pillow) with sources and importers in
`assets-src/`. Copies of the shipped atlases and blob are in
`assets-src/current/` — **there is no way to read assets back off the
board**, so those copies are the originals.

## The two invariants everything else hangs off

1. **`mkraw.py` assigns asset ids by SORTED FILENAME.** Adding, removing or
   renaming a file shifts every later id — which forces a firmware rebuild
   (new `flash_assets.h`) AND a re-provision, applied together, with a
   garbage-panel window in between. This is why two filenames are deliberate
   lies: `sonixqmk.png` is the bunny splash, and `Iosevka-Medium-13.png`
   contains **Cozette**. **Do not "fix" the names.**
2. **`cell_w` is read from the flash index AT RUNTIME**, so changing a
   font's cell size shifts no ids and `flash_assets.h` changes by a comment
   only — the check that authorises skipping a rebuild is the generated
   header coming out byte-identical. What IS compile-time:
   `DISPLAY_TEXT_MAX_L0/_L1` and the hand-written `adv = big ? 10 : 6` in
   `draw_playback()` (the one hand-coded cell width in the tree).

Always diff the generated `flash_assets.h` against
`keyboards/a_jazz/ak820pro/graphics/res/flash_assets.h` before provisioning;
if they disagree, the firmware needs a rebuild or the LCD renders garbage.

## The faces

| Asset (filename) | Really is | Cell | Chars/line | Used for |
|---|---|---|---|---|
| `Iosevka-Medium-13` | **Cozette** (BDF) | 6×14 | 19 / 21 | host text (two lines) |
| `Iosevka-Medium-20` | Iosevka | 10×23 | 12 | status band, digit, battery % |
| `Iosevka-Regular-30` | Iosevka | 15×22 | 8 | clock (**cropped** from 15×34) |

Importers: `assets-src/mkfontatlas.py` renders TTF/OTF (render MONOCHROME
via `getmask(mode="1")`, not antialiased-then-thresholded);
`assets-src/mkbdfatlas.py` imports a BDF bitmap font — no hinting lottery, it
copies pixels a human placed. Both emit fixed cells with a magenta marker at
each cell's top-left; **marker spacing IS the advance** and `mkraw.py` reads
markers from row 0 only.

⚠️ **CHECK `mkraw.py`'s EXIT STATUS.** Hand-editing a glyph can clobber its
marker (`non-uniform glyph advance`); if the failure is swallowed, the STALE
blob gets provisioned and a device-vs-local CRC check still passes — both
sides equally wrong. Confirm the blob's CRC actually **changed** after
regenerating.

## Why the 13px face is Cozette (2026-08-30)

Iosevka kept losing the quantisation lottery at 13px (measured: 2px `j`
stem, lopsided `A`, flat `d` bowl, `l`≈`1` — plus the size-20 `P`, and every
hand-patch died at regeneration). Cozette is hand-drawn at exactly this grid
(6×13); MIT licensed, `assets-src/cozette.bdf` + license committed.

- **The baseline is PINNED to row 9 — load-bearing.** display.c centres text
  on the transport icon by cap-to-baseline ink (`TEXT_FONT_DY 4`,
  `TEXT_BIG_DY 0` — one constant for both misaligns one). `mkbdfatlas.py`
  refuses to clip rather than shave descenders.
- Cell 6×14 (Cozette's own advance); the importer normalises the 1px left
  bearing to col 0.
- ⚠️ **Proportional width was measured and REJECTED**: 73 of 95 glyphs are
  already exactly 5px ink; real titles save 4-12% (one to two characters)
  against a format change spanning the whole pipeline — and it would look
  worse (Cozette's serifed `I` is deliberate; trimmed glyphs get sidebearings
  nobody drew).
- ⚠️ **Do not thicken it**: at ~5px glyph width, three stems + two gaps is
  the minimum — density and weight are the same dial. A real Bold cannot
  rescue it either.

## Legibility ceiling — accepted

13px caps are 8 rows ≈ 1.35 mm ≈ 7.7 arcmin at 60 cm; comfortable reading
wants 16-20. This is physics, not typography — the slot's job is
*recognition* of a known title, which works below reading acuity. The only
lever is the 20px face (drop the artist line host-side, no rebuild), but it
fits 11 chars so most titles fall back anyway.

Iosevka facts worth not re-deriving: **the size-20 capital `P` stem collapse
is Iosevka's hinting, not the toolchain** (only size in 16-26 that does it;
hand-fixed in the shipped atlas; size 19 is worse — every RIGHT stem
collapses). **Iosevka Aile is WIDER than the mono** (10 chars vs 12 at
20px). Size 12 was built and rejected (counters close).

## The clock atlas crop

`Iosevka-Regular-30` was 15×34; the clock draws only `0-9:` which use
neither ascender nor descender rows, so 12 blank rows were cropped
(2026-08-30) — freeing 12 panel rows and 34 KB of blob. It was a crop, not a
re-render (glyphs pixel-identical). Consequences:

- **The colon is hand-shifted UP 3 rows** (Iosevka positions it for
  lowercase; clock faces centre it between digits — both centres now 10.5).
  Re-apply after any regeneration, and re-paint the magenta marker.
- ⚠️ Descenders (`g p q y`) are clipped — harmless while only the clock uses
  `FONT_CLOCK`; regenerate at full cell if general text ever needs this size.
- A glyph moved INSIDE its cell is assets-only (header byte-identical —
  confirm rather than assume, and confirm the blob CRC changed).

Remaining easy win: the clock font stores 95 glyphs to draw eleven —
subsetting would reclaim ~86 KB of the ~199 KB blob.

## Provisioning — the traps, in the order they bite

1. **`ak820ctl flash write` ERASES ALL 48 SECTORS FIRST.** A write that
   fails after starting leaves the panel blank (only the battery icon
   survives — it is drawn from rectangles, everything else comes from
   flash). The firmware prints the recovery command. **Verify raw HID
   responds (`ak820ctl info`) BEFORE starting** — if it can't answer, the
   erase still happens.
2. **"No reply" causes**: a browser holding the interface exclusively
   (usevia.app — closing the tab in one browser does not help if it is open
   in another), or the cable simply not connected. The slider position no
   longer matters: raw-HID replies return over USB in any mode since board
   commit 4b86d95014 (2026-08-29) — the historical "Bluetooth mode" cause
   (replies silently discarded via the BT driver's no-op `send_raw_hid`) is
   fixed. Console alive + raw HID silent is NOT the hang; the hang kills
   both. Do not reflash firmware to fix a blank panel — provisioning needs
   QMK *running*.
3. **Do not touch the mode slider during a write** — it re-points the host
   driver mid-transfer (seen dying at 84%); the board is fine, re-run the
   write.
4. **Provision AFTER flashing firmware, not before.** Both orders have a
   mismatch window; firmware-first confines it to one obviously-broken
   element instead of a whole panel of garbage that reads as a dead board.
   Either way `ak820ctl info` is the liveness probe.
5. **Power-cycle after every provision, before judging the panel.** The
   index is parsed into RAM once at boot; a post-boot provision leaves flash
   new and RAM stale — and `flash crc` reads the flash, so **a CRC match
   does not mean the board is rendering the new assets**. (Worked example:
   the Cozette swap — stale `cell_w=7` skewed every glyph and every later
   asset moved 2,660 B.) Cold boot = slider to `cable`, unplug ~10 s.
6. Assets load at boot — watch for `[assets] index ok, N entries`.

Local CRC check:

```sh
python3 -c "import zlib;print(hex(zlib.crc32(open('assets/flash_assets.bin','rb').read())))"
```

## The boot splash (JD's bunny)

Source `assets-src/bunny-source.png` (612×792 RGBA, black ink on
transparency — the alpha IS the shape). Regenerate with
`assets-src/mkbunny.py` (stdlib; reuses `mkraw.decode_png`), then
`mkraw.py --flash`, diff the header, provision. The two non-obvious steps:
**invert** (panel draws on black) and **trim to the alpha bbox BEFORE
scaling** (the artboard margin cost 22% of size). Downsample by area
average — nearest-neighbour shreds the ear strokes. 0.640 aspect: **do not
stretch it.** Original fpb splash kept at
`assets-src/sonixqmk-original-splash.png`. There is also a bootloader splash
(shown for the few ms before a flash).
