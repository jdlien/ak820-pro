# The configuration menu: how to build it (draft for review, 2026-10-23)

Status: **a plan, nothing built.** What the menu is, and why each choice was
made, is [`CONFIG-MENU-PLAN.md`](CONFIG-MENU-PLAN.md). How it looks is
[`config-menu-mockup.html`](config-menu-mockup.html), drawn from the board's
own atlases. The mockup is the visual spec until the build, so a change to
the layout or the words goes into it too. This plan covers how it goes into
the firmware, what it costs, the order of work and how it's tested.

Paths are under `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` unless
given otherwise. Line numbers are at `b9555ff3e6`.

## What it builds

- **Opening and closing:** `Fn` plus a knob click opens and closes the menu,
  over the whole panel.
- **The top level:**
  - page one: Lighting, Screen, Connection, Power, Indicators, Clock,
    Battery, Diagnostics;
  - page two: Help, About, Exit.
- **Driving it:**
  - turning moves, wrapping at the ends; lists scroll by page;
  - a click chooses or saves, and a long press goes back or cancels;
  - every list below the top starts with "‹ Back".
- **Settings:** lighting and the screen preview as you turn, and a click
  saves them. Other choices apply on the click.
- **Timeouts:** the lists close after 12 s idle. There's no timeout
  mid-edit, except a backstop (Open, 1).
- **The hint:** "Configuration" gives way to "Turn + Click Knob" for 1 s
  after 4 s idle.
- **About, page two:** the Jackrabbit bunny (27x42) with the credits beside
  him.
- **Display:**
  - text in the small face (Cozette 6x14), 20 columns;
  - the selection is lit text or inverted (Open, 2);
  - values read as the `Fn`-key readouts do: percentages, and hue in
    degrees.
- **Typing works normally while it's open.** Only the knob is captured.

## What the code says, and what it changes

These facts were checked in the source, and each one shapes a choice below.

1. **RAM is full in the dev build.**
   - All 32 KB of SRAM is assigned, and the heap gap is 32 bytes
     (`arm-none-eabi-size -A` on `via-dev-ce229f87c6`). The daily build has
     2,160.
   - The biggest user is the battery log, `log_buf`: 12,960 B, 720 entries
     of 18 B (`battery.c:1352`).
   - **So the menu must reuse RAM it can share, not add it.** Its text grid
     reuses the `Fn`+`D` page's `dbg_text[9][22]` and `dbg_shown` (198 B
     each, `display.c:723-726`), since the two never own the panel together.
   - If more is needed, the log gives 18 B an entry.
2. **The DMA can't read RAM** (`lcd_bus.h:24-26`).
   - A flash glyph is a DMA from the SPI flash at ~0 CPU
     (`lcd_draw_flash_glyph_try`). Anything drawn from RAM is a synchronous
     CPU push: `lcd_blit_ram` (`lcd_bus.c:214-221`) quiesces the bus, sends
     an 11-byte window, then byte-swaps and `spiSend`s 256 pixels at a time
     at 24 MHz.
   - Measured: a 12x12 icon takes 3.4 ms, and the 5x16 AM/PM tile cut a
     transition from 40 ms to 7 ms. Most of the cost is fixed per call.
   - **So coloured text costs CPU, and paying it per glyph is the wrong
     unit.** See "Painting".
3. **The `Fn`+`D` page already owns the panel the way the menu must.**
   - Its flags are `debug_active` and `debug_exit_step`.
   - `display_housekeeping_task` is the single gate for every dashboard
     owner (3357-3427).
   - The pump has the page's branch (2974-2979).
   - Leaving runs a 14-stage restore that only the pump advances
     (1394-1435). That rule is in the warning at 3370-3376.
   - **The menu is a peer of that page:** a `menu_active` flag beside
     `debug_active`, checked wherever `debug_active` is.
4. **Known gaps in that ownership:**
   - **The logos paint over the page.** `display_draw_*_logo` (3429-3457)
     checks only `splash_cleared && !display_paused`, and a Bluetooth slot
     tap calls `display_draw_bluetooth_logo` (`bt_ui.c:128`). The menu's
     Connection section would do exactly that. Gate the logos on both
     owners, which also fixes `Fn`+`D`.
   - **`display_bus_idle` sees only `debug_exit_step`** (2909-2911), not an
     owner's own pending paint.
   - **Overlays post behind the page.** `param_status_task` polls the RGB
     getters (`param_overlay.c:191-263`), so every lighting preview queues a
     readout that would flash up after the menu closes.
5. **The knob:**
   - Detents reach `process_record_kb` as press and release records of
     `ENCODER_CW_EVENT`/`ENCODER_CCW_EVENT` (`quantum/encoder.c:38-45`).
     `IS_ENCODEREVENT()` tells them apart, though no board code uses it yet.
   - The press is the plain matrix key (0,14). `Fn` plus the press is
     `KC_MUTE` in both keymaps today; VIA's stored keymap overrides them.
   - `process_record_kb` runs before VIA, RGB and connection processing
     (`quantum/quantum.c:355`). The board's hooks run in order
     (`ak820pro.c:336-512`): the health note, the scroll note, the param
     repeat, the modified consumer, then the switch.
6. **Settings already have their setters:**
   - **RGB:** `_noeeprom` variants to preview and saving variants to save
     (`rgb_matrix.c`).
   - **The screen:** `display_set_brightness` (RAM) and
     `kb_eeconfig_set_lcd_brightness`.
   - **The clock:** `display_set_clock_mode` and
     `kb_eeconfig_set_clock_mode`.
   - **Power:** `power_cycle_mode()` saves as it changes. There's no setter
     for a chosen mode outside the dev hooks (`power.c:322-335`).
   - **Bluetooth slots:** `bt_ui_slot_key` selects, saves and draws the logo
     in one go. The pairing hold is `bt_pair_hold_task`, which calls
     `ch582_enter_pairing()`.
   - **The indicators:** `indicator_set_brightness` sets both locks, and
     neither is persisted. The charging LED is fixed at 0.
7. **The RGB flush writes the whole config if anything is dirty**
   (`quantum/eeconfig.h:177-182`). The board's gate,
   `rgb_matrix_eeprom_flush_allowed()` (`ak820pro.c:689-744`), waits for
   900 ms of stillness.
   - A preview could be persisted if a saving change was still pending when
     the edit began.
   - **So the gate refuses while an edit is open,** and a cancel restores
     the config with `_noeeprom`. Whatever flushes later is then the value
     the user kept.
8. **`kb_eeconfig`:**
   - 7 bytes at data version 4 (`config.h:269-272`). A version bump
     zero-fills the block once.
   - Writes settle for 5 s, and pending writes block deep sleep.
   - Any flash erases the emulated EEPROM anyway, so a bump costs nothing
     new.
9. **Activity:**
   - Knob detents and presses bump QMK's activity
     (`last_encoder_activity_trigger`, `quantum/keyboard.c:742-744`), so
     the ladder doesn't dim or sleep while the menu is used.
   - Lights out lights the screen while `display_debug_active()`
     (`power.c:245-246`). The menu needs the same.
   - A lit backlight blocks deep sleep (`DSB_LIT`, `sleep.c:261`). So a
     menu left open mid-edit keeps the board awake for as long as it
     stays, which is why the backstop exists (Open, 1).
10. **Build identity:** `AK820_BUILD_TOKEN` (`build.sh:37-42`) and
    `QMK_GIT_HASH` in the generated `version.h` give the About page its
    firmware line. `rtc_seconds_since_boot()` gives uptime with the slept
    time included (`timer_read32()` stops in deep sleep).

## Architecture

### The files

- **`menu.c` / `menu.h`, the menu itself.**
  - A static table of items: label, kind (submenu, choice, range, hue,
    action, page) and get/preview/save/cancel functions.
  - The state machine: the stack of lists, the cursor, the edit's old
    value, the timers.
  - A composer that writes the screen into a text grid, with a style per
    row and a list of shapes.
  - It touches no hardware, so the whole of it compiles on the host for
    tests.
- **`menu_settings.c`:** the adapters from the table to the board's setters
  (below).
- **`display.c`:**
  - the `menu_active` owner flag, beside `debug_active`;
  - the pump's menu branch, the open clear and the close restore;
  - the shapes.
- **`lcd_bus.c`:** `lcd_blit_mono()`, the 1-bit glyph path (below).
- **`graphics/res/font_small_mono.h`, generated:** the small face as a 1-bit
  table, made by `scripts/gen_mono_font.py`.
  - The 95 ASCII glyphs are read from the shipped atlas,
    `assets-src/current/Iosevka-Medium-13.png`, so they're the panel's
    glyphs by construction.
  - The extra symbols (`‹ › • ▸ ✓`) come from `assets-src/cozette.bdf`,
    placed the way `mkbdfatlas.py` places the ASCII.
  - One byte a row, 14 bytes a glyph: 1.4 KB of flash for 100 glyphs.
- **`graphics/res/menu_art.h`, generated:**
  - the bunny, 27x42 as RGB565 (2,268 B of flash), drawn in three 14-row
    slices with the About page's rows;
  - the QR code for Help > More info, a 29x29 module bitmap (106 B).

  Both are drawn straight from flash, with no RAM copy. The URL is fixed,
  so the QR code is computed at build time and the firmware needs no
  encoder.
- **`ak820pro.c`:**
  - the input hook, first in `process_record_kb` after the health and
    scroll notes;
  - the menu's task, once a main-loop pass, for the long press, the
    timeouts and the hint.

### Owning the panel

- **The flag:** `menu_active` joins `debug_active` in every gate in fact 3:
  - the early return in `display_housekeeping_task`;
  - the pump's branch;
  - `display_band_busy`;
  - the wake paint;
  - `display_redraw_dashboard`;
  - the self-heal's condition;
  - `ANIM_TOG`.
  The logos are gated too (fact 4). They're one helper,
  `display_panel_owned()`, so a third owner can't be missed.
- **Opening:**
  - Refused while the animation owns the panel (`display_paused`).
  - From the `Fn`+`D` page, it closes that page first.
  - It clears the panel in the page's 128x16 bands, one band a pass, as
    `debug_clear_band` does today.
- **Closing (Exit, `Fn` plus a click, the timeout):**
  - `menu_active` clears, and `debug_exit_step = 1` starts the same staged
    restore.
  - Whatever the host sent meanwhile (titles, the clock, alerts) is in RAM
    and repaints with the dashboard.
  - An alert's 60 s hold kept running while the menu was open. That's
    accepted: the alert was posted, and the menu is short.
- **The overlays:** while the menu is open, `param_status_task` doesn't
  post readouts. It re-primes its last-seen values when the menu closes, so
  the menu's changes never flash up afterwards as overlays.

### Painting: a row a pass, from a 1-bit font

- **The unit is the row, not the glyph.**
  - `lcd_blit_mono(bits, cols, x, y, fg, bg)` opens one window for a whole
    row (up to 21 glyphs, 126x14), expands each glyph's bits into
    `tx_pixels`' existing 512-byte buffer in the two colours, and streams
    it out.
  - So it takes no new RAM, and the window and quiesce cost is paid once a
    row, not once a glyph.
  - **Estimate:** a 120x14 row is 3,360 bytes, ~1.1 ms on the wire at
    24 MHz, plus the expansion and the fixed cost. Roughly 2-4 ms, to be
    measured first (stage S1).
- **The pump paints the first changed row each pass.** The composer marks
  rows dirty against `dbg_shown`, as the debug page marks cells.
  - A cursor move is two rows, about 10 ms of wall time, so it keeps up
    with a fast spin.
  - A full screen (a page turn, opening a submenu) is 9 rows, ~45-60 ms.
  - The mockup's glyph-a-pass figures (0.2 s a move, 0.7 s a screen) were
    the worst case. This is the reason they no longer apply.
- **The budget:** the row's cost plus the ~5 ms average pass must stay
  under 10 ms on most passes and far under 25 ms on all of them.
  - If S1 measures a row over ~4 ms, the pump paints half-rows (10
    columns), or one glyph at a time with the same function.
  - Typing is safe at any of these costs: the matrix is scanned in the row
    ISR, and 25 ms is the line for loss.
- **Shapes:** each is drawn after the row it belongs to, as a small
  `lcd_blit_ram` tile or fill from flash or the stack:
  - the triangle (if chosen), the saved option's dot, the 1 px pad of an
    inverted row;
  - a range's bar, the hue strip and its marker;
  - the bunny's slices, the QR code.
  The hue strip is the largest: 120x14, drawn once when the hue editor
  opens. Its marker is redrawn as two small fills.
- **The big face, for values in an editor,** stays the flash atlas (white
  on black, DMA, ~0 CPU), through `lcd_draw_flash_glyph_try`. A value
  repaints only when it changes.

### Input

The hook is `menu_process_record(keycode, record)`, first in
`process_record_kb` after the two notes, before the param repeat and the
modified consumer:
- **Closed:** a press of (0,14) with `WINFN` or `MACFN` on opens the menu
  and is swallowed, along with its release. Everything else passes.
- **Open:**
  - **Detents** (`IS_ENCODEREVENT`, presses only) turn the menu and are
    swallowed, so no volume changes. The release half of each detent is
    swallowed too.
  - **The knob press (0,14):**
    - its press starts the hold timer;
    - a release before 600 ms is a click;
    - the menu task fires Back at 600 ms while it's still held, and the
      release that follows is swallowed;
    - with `Fn` held, the press closes the menu.
  - **Every other key passes untouched,** including releases of keys held
    from before the menu opened, so typing works and nothing sticks.
- **It's keyed on the matrix position and the event type, not the
  keycode,** so a knob that VIA remapped still drives the menu.

### Settings: preview, save, cancel

| Item | Preview while turning | Save on click | Cancel |
|---|---|---|---|
| Effect, Brightness, Hue, Saturation, Speed or Second color, Lights | `rgb_matrix_*_noeeprom` | the saving variant | restore the config with `_noeeprom` |
| Screen | `display_set_brightness`, with a floor of level 1 while the menu is open | `kb_eeconfig_set_lcd_brightness` | restore the level |
| Power, Clock, Battery | none: they don't show while the menu owns the panel | new `power_set_mode(m)` (saves, the same path as `Fn`+`B` without cycling); `display_set_clock_mode` + `kb_eeconfig_set_clock_mode`; the battery row's new field | nothing applied |
| Connection: Bluetooth 1-3 | none | `bt_ui_select_slot(s)`, split out of `bt_ui_slot_key` without its hold arming | none |
| Connection: Pair | none | `bt_ui_pair_slot(s)`: select, then `ch582_enter_pairing()`; the pairing screen shows its state from `ch582_is_pairing()` | click or hold stops it |
| Lock lights, Charging light | `indicator_set_brightness`, and a new `indicator_set_charging_brightness` | new `kb_eeconfig` fields | restore the level |

- **While an edit is open,** `rgb_matrix_eeprom_flush_allowed()` returns
  false (fact 7). Fn-key lighting changes made while the menu is open still
  save as they do today, once the edit has closed.
- **`kb_eeconfig` grows from 7 to 10 bytes, at data version 5:**
  `ind_locks_p1`, `ind_charging_p1` and `batt_view_p1`, with 0 as unset.
  They're applied at init.
- **Connection, with the slider off Bluetooth:** a 2.4G or cable position
  (`ch582_is_24g()`, `ch582_is_usb()`) shows "Set by the slider" and offers
  nothing to pick. `wireless_mode` is static, so these are the getters.
- **Battery** (Percent or Hours) needs the battery row's time-left view
  (`BACKLOG.md`, "Time left on a long sleep's wake"). It's built with that
  work, and the item stays hidden until then.

### Timeouts and power

- **The menu's task:** the lists close after 12 s with no input. The hint
  runs 4 s of title, then 1 s of "Turn + Click Knob", on the top level and
  every list.
- **An edit has no idle timeout.** The backstop (Open, 1) puts the old value
  back and closes after a long idle.
- **Lights out:** `power.c:245` also lights the screen while `menu_active`.
- **Sleep:** an open menu is activity while it's used. Left alone, it closes
  at 12 s and the ladder carries on from the last input.

### Diagnostics, About, Help

- **Diagnostics > Health page / Camera page:**
  - the menu hands the panel to the `Fn`+`D` page
    (`display_debug_open(camera)`, a small entry point beside
    `display_debug_toggle`);
  - a knob click there hands it back to the menu at Diagnostics;
  - `Fn`+`D` still works as today, whether it stays a shortcut or not
    (Open, 3).
- **Diagnostics > Reset counters:** a confirm screen, then `health_reset()`
  and `display_debug_refresh()`, as `dbg_hold_task` does.
- **About:**
  - the firmware: `QMK_GIT_HASH` and `AK820_BUILD_TOKEN`, with dev or daily
    from the build flags;
  - uptime from `rtc_seconds_since_boot()`;
  - the battery: `battery_level_pct()`, `battery_pack_mv()` and
    `battery_time_left_min()`, with "-" for unknown values;
  - the power mode, and the link from `ch582_get_target_slot()` and
    `ch582_is_connected()`;
  - page two: the bunny, "Jackrabbit", "by JD Lien" and "QMK port: fpb",
    then the GitHub link.
  - Text pages scroll by page, as the lists do.
- **Help:**
  - pages of `const` strings, wrapped to 20 columns by the generator, so
    nothing overruns;
  - More info: the QR code from `menu_art.h` and the URL in text.

## RAM and flash

- **RAM:**
  - The text grid reuses `dbg_text` and `dbg_shown`.
  - The rest of the state (the stack of 3 levels, the cursor, the edit's
    old value, the timers, the row-dirty mask) is about 40 B.
  - In the dev build that's more than its 32-byte heap gap. Take 3 entries
    from `log_buf` (54 B; 720 to 717 entries, 59.75 h of the log at 5 min
    instead of 60 h) unless S1 finds RAM elsewhere.
  - The daily build has room either way.
  - Stack: the mono blit expands into `tx_pixels`' static buffer, so no
    stack grows. Recheck the watermarks (interrupt 568 B free, main 968 B
    free) after the build.
- **Flash:** the code is a few KB, the font 1.4 KB and the art 2.4 KB,
  against ~97 KB free in the dev build.

## Stages

Each stage is reviewed by codex before its flash, every finding is
dispositioned, and it goes onto gremlin's board before JD's.

1. **S1, the spike: `lcd_blit_mono` and its cost.**
   - Build the function and the generated font. Add a dev hook (HC_DEVHOOK
     op 27, sub 0) that paints a test row in chosen colours and reports the
     row's time from `timer_read32` ticks.
   - Measure a full row, a half row and one glyph, on the dashboard's idle
     panel.
   - That decides the row as the unit, and checks the generated glyphs
     against the flash atlas on the panel: they should be identical.
   - Settle the cursor style (Open, 2) on the real panel at the same time,
     with both colour sets.
2. **P1, the core:**
   - `menu.c` with host tests, the owner flag and its gates (the logo fix
     included), opening, closing and the restore, the input hook, the
     timeouts and the hint;
   - Lighting, Screen, Power, Clock and Exit.
   - Dev hook op 27, subs 1-4, injects turn, click, hold and `Fn` + click,
     so the bench can drive the menu without hands. The wake rig can't
     turn a knob.
3. **P2, the rest:**
   - Connection, with the `bt_ui` split; Indicators, with the
     `kb_eeconfig` bump;
   - Diagnostics and the page handoff; About; Help, with the QR code.
4. **P3, Battery:** with the time-left row view, when that's built.
5. **Docs:**
   - `docs/display.md`: the owner, the mono path;
   - `README.md` and the Help pages: the menu in place of the chords;
   - `CLAUDE.md`'s shortcut list.

## Testing

- **Host (gcc, as `scripts/lockchan_media_test.c` is built):**
  - **`menu.c`'s state machine:** wrap-around, Back, opening on the first
    real item or the current value, page scrolling, a click, a long press,
    Cancel restoring the old value, the 12 s timeout in lists only, the
    backstop.
  - **The composer:** checked against golden text grids, one per screen,
    taken from the mockup's strings.
  - **Fit:** every label and value in the table fits 20 columns, and every
    Help line 20, checked from the table itself.
- **On the board, driven by op 27, on gremlin's board first:**
  - **The stall counters:** no pass of 25 ms or more over a scripted session
    of 500 inputs, which opens every screen and edits every value.
    `count_ge_10ms` during menu use is reported against the idle rate.
    HC_ACCT's ring names any slow pass.
  - **Typing while it's open:** key presses through the wake rig all reach
    the host. The F19 listener counts them.
  - **Persistence:**
    - after a save, a power cycle keeps the value;
    - after a cancel, the health page's flash-write counter hasn't moved,
      so no preview was written;
    - the RGB config read back over VIA's channel (`ak820lighting.py
      show`) equals what was saved.
  - **Ownership:**
    - a host title, a clock sync, a lock-light frame, a Caps press, a
      slider move, a BT slot change and a charger plug-in while the menu is
      open: none of them paints over it;
    - after Exit the dashboard comes back whole.
  - **Power:** Lights out lights the menu. An open menu blocks sleep only
    while it's open. After the timeout the ladder runs from the last input.
  - **RAM and stacks:** the size of each build, and the watermarks after a
    night.
  - **A VIA-remapped knob** still drives the menu.

## Open

1. **The backstop for an abandoned edit.** Proposed: 2 minutes, then put the
   old value back and close. Without one, an edit left open keeps the
   backlight on and the board awake on battery.
2. **The cursor: lit text or inverted.** Settle it on the panel in S1. Both
   use the mono path and cost the same.
3. **`Fn`+`D`:** keep it as a shortcut beside Diagnostics, or free the key
   (JD's call).
4. **Rows or half-rows:** S1's measurement decides.

## Side fixes this work makes

- `display_draw_*_logo` is gated on the panel's owner (fact 4). This also
  fixes the `Fn`+`D` page being painted over by a slot tap or a slider move.
- Stale comments: `kb_eeconfig.h:10` ("5 bytes", now 7) and `config.h:438-440`
  (the LCD brightness, "Not persisted", which it is).
