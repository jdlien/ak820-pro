# A configuration menu on the knob (draft, 2026-10-22/23)

Status: **an idea for later, written up to discuss. Nothing is built.** JD's
design, with Claude's additions marked as such and the decisions still open at
the end. Prior art: quill4gen7's menu (below). Credit it if we build one.

## Prior art: quill4gen7's menu (read 10-23)

It lives in `keyboards/a_jazz/ak820pro/menu.c` on the `quill-personal` branch
of github.com/quill4gen7/qmk_firmware ("menu impostazioni con Fn + rotella",
09-28, 138 lines).
- **Opened by `Fn` plus a turn of the knob,** not a key.
- **Two items:** "Domande Si/No" (show Claude Code's questions on the board,
  or turn them into notices answered at the terminal) and "Esci" (exit). A
  frame for settings more than a settings menu.
- **Turn or the arrows move.** A knob press, Enter or Space changes the item.
  Esc closes it, and it closes itself after 20 s idle.
- **Every other key is swallowed while it's open,** except releases and
  layer keys. A key held from before the menu must not stick.
- **The bottom row always says "Gira e premi"** ("turn and press").
- **The page:** 12 columns by 5 rows in the big face, drawn as one of its
  notification pages.

**Worth taking:**
- **The opener.** Our encoder map gives the Fn layers the same volume as the
  base layers (`keymaps/default/keymap.c`), so `Fn` plus a turn is free and
  costs no key. It would leave `Fn`+`C` as the clock's quick toggle, or free
  it.
- **Releases and layer keys always pass,** whatever else the menu does with
  keys.
- **A standing hint row,** against JD's flash after a few seconds.

## Why

Every setting the board has is reachable today, but only through a Fn chord
you have to know: `Fn`+arrows, `Fn`+`6`/`7`, `Fn`+`-`/`=`, `Fn`+`PgUp`/`PgDn`,
`Fn`+`Home`, `Fn`+`B`, `Fn`+`C`, and holds of `Fn`+`Q`/`W`/`E`. A menu makes
them discoverable for other owners, shows the value you are changing, and
frees chords.

## JD's design

- **`Fn`+`C` opens it.** "Configuration" shows with a small triangle at the
  selected item. While it is open the knob is the control.
- **Turn** to move through the list, **click** to select a setting, then turn
  to change it and **click again** to save and go back to the list.
- Submenus may need a **"‹ Back"** first item.
- **It closes** after 10-12 s idle, or on the next `Fn`+`C`.
- After a few seconds, flash **"Turn the knob"** over the title so it's clear
  how to drive it.
- **The debug pages move here,** so `Fn`+`D` no longer needs a Fn-layer key.

The tree as JD sketched it:

```
Configuration
> Lighting     -> Effect / Brightness / Hue / Saturation -> value
  Screen       -> Brightness (0 is off), or brightness and on/off, or inside Lighting
  Power        -> Always on / Balanced / Power saver / Lights out
  Indicators   -> Caps Lock / Win Lock / Charging: brightness, on/off each
  Clock        -> Off / 24h / 12h / Date
  Battery left -> Percent / Runtime
```

## Additions (Claude)

**More items:**
- **Lighting -> the effect's second value, named by the effect.** In JD's
  dual-colour effect, `speed` is the second hue (`231` today), so the menu
  says "Second colour" there and "Speed" in effects where it is a speed.
  Show hues as a colour swatch, not a number.
- **Connection -> Bluetooth 1 / 2 / 3, 2.4G, Pair this slot.** Pairing today
  is a 2 s hold of `Fn`+`Q`/`W`/`E`, the least discoverable thing on the
  board.
- **Knob -> Volume / Scroll / Screen brightness.** This is the "knob modes"
  idea, and the menu is where it belongs. The press keeps play/pause.
- **Diagnostics -> Health page / Camera page / Reset counters,** replacing
  `Fn`+`D`'s tap cycle and its hold.
- **About:** the firmware (sha and token), the build kind, uptime, the
  power mode, the battery (level, pack mV, time left). It's what an owner
  sends with a bug report.
- **Power -> Sleep now:** for leaving the desk on battery. It uses the
  ladder's last stage, so the blockers still apply.
- **The indicators already have levels:** `ind_duty[]` 0-9 in
  `indicators.c`, the locks at 1 (2.1%) and the charging LED at 0 (off).
  Today `indicator_set_brightness()` sets the locks together. The menu can
  offer both levels, with 0 as off. Neither is persisted yet.
- **NKRO** is on in `keyboard.json`. A toggle probably matters only on the
  cable: over the radio the module's report format decides. Leave it out
  unless that checks out otherwise.

**Behaviour:**
- **Live preview, revert on cancel.** Turning applies the value at once: the
  keys show a colour, the screen shows its brightness. Click keeps it. A
  timeout or `Fn`+`C` in the middle of an edit puts the old value back. A
  menu that closes on its own should never leave a half-chosen setting.
- **One flash write per save, not per detent.** Every internal-flash write
  blanks the LEDs for a few ms (`CLAUDE.md`), and it costs wear.
- **Long-press the knob as Back,** beside the "‹ Back" item: the item is the
  discoverable way, the press the quick one.
- **Typing while it's open.** Proposed:
  - the arrows, Enter and Esc drive it and are swallowed (Esc is Back);
  - any other key closes it and types as normal, so nobody types blind
    into a menu.
- **Acceleration on 0-255 values:** fast turning steps by 8-16. Show
  brightness as a percentage and in a bar.
- **Lights out** keeps the screen dark. The menu lights it while open, as
  that mode's messages do.
- **Deep sleep:** the open menu is activity. The timeout closes it long
  before any ladder stage.
- **Values are read fresh when it opens,** since VIA or the host may have
  changed them since.

## How it would be built (notes for the plan)

- **The panel: reuse the `Fn`+`D` page's ownership.** That page owns the
  whole panel while it is active and paints one changed cell per main-loop
  pass through the blit pump. Leaving it goes through the staged restore
  (`debug_exit_step`), which took the page's exit from ~30 ms to under 25.
  A menu on the same path inherits that, and a cursor move is a few cells.
  ⚠️ Drawing to the LCD can eat keystrokes (`CLAUDE.md`): nothing here may
  draw synchronously.
- **The panel is 128x128.** In the 13 px face (14 px lines) that is a title
  and ~7 items; in the 20 px face (10 px a glyph, 12 across), a title and ~4.
  Judge it on the panel.
- **The knob:**
  - Its detents reach QMK through the encoder map as key events, and its
    press is the matrix key (0,14).
  - While the menu is open, intercept both in `process_record_kb` before
    VIA's mapping.
  - `consumer_mod.c`'s held-mod handling for knob spins must not fire.
- **The keycodes:**
  - `CLK_MODE` (`Fn`+`C`) keeps its slot in the append-only enum
    (`check_via_sync.py`). Only its behaviour changes, and the clock format
    moves into the menu.
  - `Fn`+`D`'s keycode keeps working, since VIA keymaps already bind it.
- **The menu is data:** a static table of items (label; submenu, choice,
  range or action; get, set, save). Its state machine is plain C with
  host-side tests, as the lock-light channel has
  (`scripts/lockchan_test.py`, `scripts/lockchan_media_test.c`).
- **Where settings persist:**
  - RGB in QMK's eeconfig;
  - LCD brightness, the clock format and the power mode in `kb_eeconfig`;
  - new fields for the indicator levels, the knob mode and the battery
    display.
- **Codex** reviews the plan and the build, as for every flash.

## A build order

1. **The core:** `Fn`+`C` to open and close, the list, Lighting, Screen,
   Power, Clock, the timeout and revert, the hint.
2. **Indicators, Battery left, Diagnostics (freeing `Fn`+`D`), About.** Battery
   left waits on the time-left row view (`BACKLOG.md`, "Time left on a long
   sleep's wake").
3. **Connection, Knob modes.**

## Decided (JD, 10-23)

- **Opening and closing:** `Fn` plus a knob click opens it, and the same
  closes it from anywhere. Not `Fn` plus a turn ("a bit obscure"), and not
  `Fn`+`C`, which stays the clock's quick toggle. All the menu's actions stay
  on the knob. JD rarely uses the knob otherwise, so its press losing mute
  under `Fn` costs nothing.
- **Exit is the last item,** and turning past either end wraps around.
- **A long press is Back.**
- **A "BT Connection" section:** Bluetooth 1 / 2 / 3, 2.4G, pairing.
- **The debug and camera pages and the counter reset move into the menu**
  (Diagnostics).
- **A Help section,** short pages that read comfortably on the panel:
  - using the menu;
  - customizing with VIA;
  - a few pro tips;
  - "More information", with the GitHub link (a QR code would fit there; see
    `BACKLOG.md`).
- **Typing works normally while it's open.** Only the knob is captured.
- **No timeout while a value is being adjusted.** The idle timeout applies to
  the lists only.
- **The small face** (Cozette 6x14), probably. Judge it on the mockup, then
  the panel.
- **English only.** Localization is out of scope.

**What the panel allows** (`docs/display.md`): a glyph blit paints its whole
cell from the flash atlas, white on black, so text can't be coloured or
inverted. Colour exists only in fills and RAM tiles: the cursor triangle, a
value's bar, a hue strip, a swatch.

## The mockup (10-23)

[`config-menu-mockup.html`](config-menu-mockup.html), published as an artifact
(https://claude.ai/artifact/GYnQqp7oammUs5q7SVtF6N).
- **The screen:** a 128x128 canvas drawn from the shipped atlases
  (`assets-src/current/`), so every glyph is the board's own.
- **It paints like the board:** it diffs glyph cells and paints one glyph a
  main-loop pass, ~215 a second, and drawn shapes at once.
- **Toggles compare** the cursor style, scrolling by line or by page, and
  board speed against instant.

**What it showed about the cursor** (JD asked about coloured or inverted text
instead of the triangle):
- **Space.** The small face gives 20 columns from x 4 to 124. The triangle
  takes one of them (19 left).
  - An indent saves nothing: the selected row still needs the column.
  - An underline (a 1 px fill in the cell's blank bottom rows) takes none.
- **Possible:** coloured or inverted text needs a new font path, not a new
  atlas.
  - A 1-bit copy of Cozette in the MCU's own flash, ~1 KB (95 glyphs x 84
    bits), expanded into a 168-byte RAM tile per glyph in any two colours
    and blitted through the pump.
  - A second atlas in the SPI flash would mean re-provisioning every board
    (asset ids by sorted filename) and ~16 KB.
- **Cost, which decides it:**
  - The triangle and the underline move by redrawing two small shapes, so
    the cursor keeps up with a fast spin.
  - Inverted, yellow or indented rows repaint both rows on every detent, up
    to 40 glyphs: ~0.2 s at board speed, visibly trailing.
  - Scrolling by line repaints all 8 rows, ~0.7 s a step; by page, once a
    page.
  - Opening the menu paints ~150 glyphs, ~0.7 s, unless the pump learns to
    move more than one glyph a pass for RAM tiles.

## Still open

1. **A walk-away during an edit:** with no timeout, an abandoned edit keeps
   the menu open and the board awake. Proposed: a long backstop (~2 min)
   that reverts the value.
2. **The screen:** its own item with brightness 0 as off (proposed), or
   inside Lighting.
3. **`Fn`+`D`:** keep it as a shortcut beside Diagnostics, or free the key.
4. **The knob section** (volume, scroll, screen brightness): in the first
   build, or later.

