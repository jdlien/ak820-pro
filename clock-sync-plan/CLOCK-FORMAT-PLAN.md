# Clock format: 24h / 12h (stacked AM-PM glyph) / off — plan

Status: **PLAN, 2026-09-01.** Not built. A display-only feature; it does
not touch the clock-sync machinery (rtc/*), which sets the time — this
only changes how the clock band draws it.

## Behaviour

`Fn`+`C` cycles **24h → 12h → off → 24h**. Persisted. On each press the
param overlay shows `Clock 24h` / `Clock 12h` / `Clock off` for 2 s.

| Mode | Band shows |
|---|---|
| 24h | `HH:MM:SS` in the 30px clock face (today's behaviour) |
| 12h | `H:MM:SS` (no leading zero) in the 30px face, plus a **6 px-wide stacked `A`/`M` or `P`/`M` glyph** to its right, drawn in dim grey |
| off | band cleared; the playback timer still takes the band while playing (unchanged) |

## Layout numbers (why stacked works)

- Clock band: `CLOCK_Y`, height `CLOCK_BAND_H` 23 (the cropped 30px face
  is 15×22).
- `12:34:56` = 8 glyphs × 15 px = 120 px. Stacked AM/PM = **6 px** (Cozette
  capitals are 5 px of ink + 1 bearing) → 126 px. Hours 1–9 are 7 glyphs
  (105 px) and have room to spare; only 10–12 are tight. Shift the clock
  2 px left in 12h mode so the glyph never sits in the bezel-clipped
  rightmost columns (the panel is recessed; see docs/display.md).
- Two capitals stacked: 7–8 ink rows each + 2-row gap = ~18 of 22 rows;
  centre vertically on the digits' cap height.

## Draw the glyph from rectangles, not an atlas

Do **not** add an atlas file: `mkraw.py` assigns asset ids by sorted
filename, so a new PNG shifts every later id and forces the coordinated
rebuild + re-provision trap (docs/fonts-assets.md). Two 6×14 Cozette cells
stacked would also be 28 rows (a glyph blit paints its whole cell) — too
tall. Instead rasterise `A`, `P`, `M` from the Cozette 5×7 capital shapes
as `lcd_fill_rect` runs, exactly as the padlock (`draw_locks`) and the
battery bolt are drawn — ~12–15 rects per letter, and `lcd_fill_rect` is
the one path that can draw in colour (grey, e.g. RGB565 0x8410), which the
atlases cannot.

## Code map

| File | Change |
|---|---|
| `graphics/display.c` | `draw_clock()`: format by mode; 12h path drops the leading zero, offsets x by −2, draws the stacked glyph via a small `draw_ampm(x, y, is_pm)`; off path clears the band once. The band diff/repaint logic already redraws only changed cells — keep that (the AM/PM glyph changes at most twice a day; guard it on change). |
| `graphics/display.h` | `display_set_clock_mode(uint8_t)` / `display_get_clock_mode()`. |
| `kb_eeconfig.c/.h` | new byte `clock_mode` (0 = 24h default, 1 = 12h, 2 = off). The 4-byte block is fully assigned, so grow `EECONFIG_KB_DATA_SIZE` to 5 — assign-only layout append; a size change resets the kb block once at first boot (a flash wipes it anyway). Go through the existing coalesced deferred flush; no new write path. |
| `ak820pro.h` | **append** `CLK_MODE` to `ak820pro_keycodes` (index-matched to via.json — `check_via_sync.py` enforces). |
| `via.json` | append the matching `customKeycodes[]` entry. |
| `keymaps/via/keymap.c` | `CLK_MODE` on `Fn`+`C`, both Fn layers (`WINFN`, `MACFN`). Note VIA's stored keymap overrides the firmware default — assign it in VIA too, or reset the keymap. |
| `ak820pro.c` (`process_record_kb`) | on press: cycle mode, persist, `display_set_param_status("Clock 12h")`. |
| `param_overlay.c` | nothing new needed if the existing `display_set_param_status` string slot is used directly. |

## Gates (same instruments as the clock-sync work)

- `scripts/build.sh daily` + `instrumented` both clean; `check_via_sync` OK.
- Health unchanged after 10 min typing: `loop_gap_max_ms`, `scan_rate`
  in band, `blit_timeouts` 0, `stale_count` 0 (`rtc_phase0.py status`).
- Visual: 12h at `9:xx`, `10:xx`, `12:xx`; AM→PM rollover at noon (or set
  the clock to 11:59:50 with `ak820ctl clock 2026-09-01T11:59:50` and
  watch — then `ak820ctl clock` to restore); off mode with music playing
  still shows the playback timer.
- The keycode toggles from VIA as well as the Fn layer.

## Non-goals

No change to the sync system, the atlases, or the flash assets. No
per-second work added: the AM/PM glyph is drawn only when it changes.
