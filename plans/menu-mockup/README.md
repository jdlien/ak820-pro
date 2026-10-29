# The configuration menu's mock-up

The source of `plans/config-menu-mockup.html`, moved here from a session
scratchpad on 10-28 (plans/MENU-8X16-PLAN.md, decision 7). `core.js` is the
menu as the firmware draws it, in both faces: Small (Cozette 6x14) and Large
(Terminus Bold 8x16). It is the oracle the firmware's frames are compared
with.

- `node build.js ../config-menu-mockup.html` inlines `core.js`, the faces
  and the big-digit atlases into `page.html` and writes the mock-up.
- `font6x14.hex` and `f-termb.hex` are written by `scripts/gen_mono_font.py`,
  with the firmware's headers: Small's from Cozette, Large's by `mkfont8.js`
  from `terminus/ter-u16b.bdf` (SIL OFL 1.1, `terminus/OFL.TXT`) and the
  icons redrawn for 8x16 (`icons16.js`). `icons_png.py` exports those icons
  as a PNG to edit by hand and reads them back.
- `tour.c` drives the firmware's host test through every page and writes
  each frame; `verify.js` replays the same inputs through `core.js` and
  compares pixel for pixel. Build and run lines are in `tour.c`'s header.
  The one expected difference is Diagnostics in a dev build, whose Write
  test row the mock-up leaves out.
- `frames.js` and `sheet.js` make the Font test page's frames and contact
  sheets; `iconsheet.js` the icons' sheet.
