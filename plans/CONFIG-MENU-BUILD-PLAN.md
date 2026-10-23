# The configuration menu: how to build it (revision 2, 2026-10-23)

Status: **a plan, nothing built.** Revision 2 folds in codex's review of
revision 1 ([`review-codex-config-menu-build-plan-2026-10-23.md`](review-codex-config-menu-build-plan-2026-10-23.md):
8 must-fix and 7 should-fix, all agreed). What the menu is, and why each
choice was made, is in [`CONFIG-MENU-PLAN.md`](CONFIG-MENU-PLAN.md). How it
looks is [`config-menu-mockup.html`](config-menu-mockup.html), drawn from the
board's own atlases. The mockup is the visual spec until the build, so a
change to the layout or the words goes into it too.

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
  - turning moves, wrapping at the ends; lists and text pages scroll by page;
  - a click chooses or saves, and a long press goes back or cancels;
  - every list below the top starts with "‹ Back".
- **Settings:** lighting and the screen preview as you turn, and a click
  saves them. Other choices apply on the click.
- **Timeouts:** lists and pages close after 24 s with no knob input. An edit
  has no idle timeout, only a 3-minute backstop (decided).
- **The hint:** "Configuration" gives way to "Turn + Click Knob" for 1 s
  after 4 s idle.
- **About, page two:** the Jackrabbit bunny (27x42) with the credits.
- **Display:**
  - text in the small face (Cozette 6x14), 20 columns;
  - the selection as lit text or inverted (Open, 1);
  - values as the `Fn`-key readouts show them: percentages, hue in degrees,
    the effects by the readout's names.
- **Typing works normally while it's open.** Only the knob is captured.

## What the code says

Checked in the source by Claude, then by codex. Each fact shapes a choice
below.

1. **RAM is full in the dev build.**
   - The heap gap is 32 bytes (`via-dev-ce229f87c6`; the daily build has
     2,160).
   - `log_buf` is 12,960 B: 720 entries of 18 B, one every 15 minutes
     (`battery.c:1352-1353`), so it holds 180 h.
   - `tx_pixels()` and `lcd_fill_rect()` each keep a separate static
     512-byte buffer (`lcd_bus.c:131-188`). Both are synchronous and not
     reentrant.
   - The stacks are fixed allocations: freeing BSS grows the heap gap, not
     the stacks.
2. **The DMA can't read RAM** (`lcd_bus.h:24-26`).
   - Anything drawn from RAM is a CPU push: `lcd_blit_ram` quiesces the bus,
     sends an 11-byte window, then byte-swaps and `spiSend`s 256 pixels at a
     time at 24 MHz.
   - A 12x12 tile measured 3.4 ms. How much of that is fixed per call isn't
     known, so a row's cost has to be measured, not inferred.
3. **The `Fn`+`D` page owns the panel through several independent paths,
   not one gate:**
   - housekeeping's early return (3357-3427);
   - the pump's branch (2974-2979);
   - the wake paint (3315);
   - the logos (3429-3457);
   - the animation (`display_paused`);
   - the 14-stage restore, which only the pump advances (1394-1435). It
     isn't 14 passes: its lock stage repeats, its battery stage paints only
     the outline, and queued glyphs can remain after it ends.
   - Its flags are set directly by `display_debug_toggle()` (1174) and dev
     hook op 1. Calling the toggle from Health opens the Camera page, not
     the dashboard.
4. **Known gaps:**
   - The logos paint over the page.
   - `display_bus_idle` sees only `debug_exit_step`.
   - Overlays post from more places than `param_status_task`: the LCD,
     clock and power keys call `display_set_param_status()` directly.
5. **The knob:**
   - Detents arrive as press and release records with `wait_ms(1)` after
     each half, and `encoder.c` drains its queue in one call (30-45). The
     waits stay even if the records are consumed.
   - The press is matrix key (0,14), `KC_MUTE` under `Fn` today.
   - **Action tapping runs before `process_record_kb`, but after
     `pre_process_record_kb`** (`quantum/action.c:133-134`), and a false
     return there drops the event.
6. **Setters exist, with catches:**
   - RGB mode and HSV setters return early while RGB is disabled
     (`rgb_matrix.c:605,657`).
   - `power_set_mode()` already exists, dev-only (`power.c:330-335`).
   - `bt_ui_slot_key` selects, saves and draws the logo, and it doesn't
     release the outgoing host's reports, which the slider does
     (`bt_ui.c:55-144`).
   - Pairing goes through the CH582's pending actions. While it's already
     pairing, a select starts a 700 ms cancel-pairing bounce that a
     following `ch582_enter_pairing()` would replace, so the wrong slot
     pairs (`ch582f_ajazz.c:1530`). `ch582_cancel_connect()` isn't a
     pairing cancel.
7. **RGB persistence:**
   - `_noeeprom` never clears an earlier dirty flag, and the flush writes
     the whole config (`quantum/eeconfig.h:177-182`).
   - The board's gate (`rgb_matrix_eeprom_flush_allowed()`) covers the
     deferred flush. VIA's Save forces one past it (`quantum/via.c:737`).
8. **`kb_eeconfig`:**
   - 7 bytes at data version 4. A version mismatch zeroes the RAM copy on
     read (`nvm_eeconfig.c:221-225`); it doesn't migrate.
   - A bigger block moves VIA's keymap storage after it.
   - `flash_stats.c` pins one write-attribution field per byte with a static
     assert (29-35). Its reply page 1 already fills all 28 bytes (128ff), so
     extending its loop would write past the reply.
9. **Activity and visibility are conditional:**
   - Detents bump encoder activity, and the knob press matrix activity.
     Injected events bump neither.
   - Lights out's exception for the `Fn`+`D` page (`power.c:245-246`) only
     lifts the cap. It doesn't override a user level of 0 or a panel turned
     off (`display_powered`).
   - A lit backlight blocks sleep (`DSB_LIT`). A dark one doesn't, and
     `timer_read32()` stops while asleep.
10. **Identity and uptime:** `AK820_BUILD_TOKEN` and `QMK_GIT_HASH` (the
    generated `version.h`); `rtc_seconds_since_boot()` includes slept time.

## Architecture

### The files

- **`menu.c` / `menu.h`, the menu itself, with no hardware access, so it
  all compiles on the host for tests:**
  - **the table of items:** label, kind (submenu, choice, range, hue,
    action, page) and an adapter;
  - **the state machine:** the stack of lists, the cursor, the edit
    transaction, the timers;
  - **the composer:** it builds the screen as a list of regions (below).
- **`menu_settings.c`:** the adapters, with explicit label-to-enum tables.
- **`panel_owner.c` / `.h`:** the owner enum and its transitions.
- **`display.c`:** the painter for the menu's regions, the open clear, and
  the restore.
- **`lcd_bus.c`:**
  - `lcd_blit_mono()`, the 1-bit glyph path;
  - the shared 512-byte scratch buffer;
  - the chunked streams for the hue strip and the QR code.
- **`graphics/res/font_small_mono.h`, generated by
  `scripts/gen_mono_font.py`:**
  - the 95 ASCII glyphs from the shipped atlas
    (`assets-src/current/Iosevka-Medium-13.png`), so they're the panel's
    glyphs by construction;
  - five symbols (`‹ › • ▸ ✓`) from `assets-src/cozette.bdf`, placed as
    `mkbdfatlas.py` places the ASCII, at single-byte codes 0x80-0x84;
  - 14 bytes a glyph, 1.4 KB.
- **`graphics/res/menu_art.h`, generated:**
  - the bunny, 27x42 RGB565 (2,268 B);
  - the QR code's 29x29 modules (106 B), computed at build time, since the
    URL is fixed.
- **`ak820pro.c`:**
  - `pre_process_record_kb`, for the capture (below);
  - the menu's task, once a pass.
- **The health decoders** (`hostagent/ak820health.py`, `ak820-agent`'s
  `health.rs`): the new flash-stats page.

### Who owns the panel

- **One owner at a time:** `panel_owner` takes one of `PANEL_DASH`,
  `PANEL_DEBUG`, `PANEL_MENU` or `PANEL_ANIM`.
- **The only ways to change it:** `panel_enter(owner)`, `panel_leave()` and
  `panel_handoff(from, to)`.
  - `Fn`+`D`, dev hook op 1, the Diagnostics entries and the animation all
    go through them.
  - `display_debug_toggle()` becomes a caller of these, not a setter of
    flags.
- **The paint paths ask one question,** `display_panel_owned()` (anything
  but the dashboard): housekeeping, the pump, the wake paint, the logos,
  `display_band_busy`, `display_redraw_dashboard`, the self-heal and
  `ANIM_TOG`.
- **State keeps updating while painting is gated:**
  - text slots, playback, alerts, pair hints and the lock-light channel;
  - both glyph queues' contents, the second edge;
  - the logos' RAM state. A gated logo marks itself stale and is repainted
    from state.
- **The shared buffers:** the menu and the `Fn`+`D` page share `dbg_text`
  and `dbg_shown`, and a handoff resets them and their paint state.
- **Diagnostics:** the menu hands the panel to the page. Knob input stays
  the menu's: a click hands the panel back to the menu at Diagnostics.
- **Opening:**
  - Refused while the animation owns the panel, and deferred until a
    wake's repaint has been released (`display_wake_release`).
  - From the `Fn`+`D` page, it's a handoff.
  - An unfinished dashboard restore is superseded.
  - The panel clears in 128x16 bands, one a pass.
- **Closing** (Exit, `Fn` plus a click, the timeout, the backstop):
  - `panel_leave()` starts the staged restore.
  - "Restored" means the restore has ended *and* `gq` and `lq` are drained.
    That's `display_restored()`, used by anything that waits.
  - `conn_status_update()` runs before the restore's text stage, so an
    alert or overlay that expired while the menu was open doesn't flash
    back.
- **Overlays:**
  - `display_set_param_status()` asks the owner. While the menu owns the
    panel, the menu's own previews post nothing.
  - At entry, any pending overlay state and `param_force_kc` are cleared.
  - At exit, `param_status_task` re-primes its last-seen values.

### Painting

- **The unit: half a row by default.** S1 measures the full pass under
  load, and full rows are used only if the numbers allow.
  - `lcd_blit_mono(bits, cols, x, y, fg, bg)` quiesces the bus *before*
    opening its window, then expands the glyphs' bits into the shared
    scratch buffer in raster order and panel byte order, streaming it out,
    with interrupts enabled.
  - A half row is 10 glyphs, 60x14: 1,680 bytes, 0.56 ms on the wire.
  - **Its total cost, and a full row's, are S1's to find.** They include
    the FIFO, the chunk calls, the expansion, and SPI0's shared priority
    with the row ISR.
- **The damage model:** the composer builds the screen as regions, each
  with a signature.
  - **The regions:** a row's text and style; a row's shapes (the triangle
    if chosen, the saved option's dot, the inverted row's 1 px pad); an
    editor's big value; the bar; the hue strip; the marker; the bunny's
    slices; the QR code.
  - **Painting:** the painter diffs the signatures against what's on the
    panel and paints the first damaged region each pass. So a colour
    change on unchanged text is damage too.
  - **A region becomes "shown" only when finished,** and navigating
    regenerates the damage, so stale pending work is superseded.
- **The budget:** each pass does one bounded paint operation: a half row, a
  shape, a strip or QR chunk, or a band of the open clear.
  - Its cost plus the pass's other work must stay under 10 ms on most
    passes and far under 25 ms on all of them.
  - `pass_deferred` and `clock_ticked_this_pass` still skip a pass.
  - The RTC's I2C rules are unchanged: the menu doesn't touch port A, and
    the existing busy checks stay.
- **What that gives, if a half row is ~3 ms:**
  - a cursor move is 4 half rows: ~4 passes, ~30-35 ms;
  - a full screen is 18 half rows plus shapes: ~0.15 s;
  - opening adds the 8-band clear.
  These are estimates for S1 to confirm.
- **Chunked shapes:**
  - The hue strip (120x14) and the QR code (29 modules at 3 px, ~95 px
    square with its quiet zone) are computed per chunk into the shared
    scratch buffer, never as a tile on the stack. A 120x14 RGB565 tile
    would be 3,360 B, more than the whole main stack.
  - Moving the marker repaints the strip columns under its old position.
- **The layout is per screen kind,** matching the mockup:
  - lists and pages: the title at y 0, the separator at y 14, rows from
    y 15;
  - editors: the big value's 23-row cell at y 22, the bar, the hints.
- **The big face** (an editor's value) stays a flash-atlas DMA. A failed
  blit is retried by the menu's own damage model, not the dashboard's
  self-heal.

### Input: capture through the matching release

- **The hook is `pre_process_record_kb`,** which runs before action tapping
  (fact 5). So a VIA tap-hold, mod-tap or one-shot on the knob never sees
  the menu's events, and weak mods and one-shots are untouched.
- **A capture table** holds one bit for the knob press, plus the detents,
  which are handled on press with their release always swallowed while
  captured.
  - When the menu consumes a press, the bit is set, and **the matching
    release is consumed whatever the owner or `Fn` state is by then**:
    after `Fn` plus a click closes the menu, after a long Back at the top,
    after a timeout during a hold.
  - A release whose press was forwarded is forwarded.
  - Opening consumes the press and its release, which is never read as a
    click in the new menu.
- **The knob press while open:**
  - **A click:** a release before 600 ms.
  - **Back:** the menu task fires it at 600 ms while held. A release at or
    after 600 ms that the task hasn't caught yet fires Back then, exactly
    once.
  - **`Fn` held:** the press closes the menu (the `WINFN` or `MACFN` layer
    bit).
- **Detents while open:** turns on the press half, and both halves
  consumed. Closed, they're ordinary volume.
- **Everything else passes**, ordinary held keys and modifiers included.
  Nothing calls `clear_keyboard()` on open or close.
- **Opening also:**
  - cancels the param repeat, so a held lighting key can't keep changing a
    value under an edit;
  - leaves `modified_consumer_task()` running, so a consumer burst begun
    before opening still releases its mods.

### Settings: the edit transaction

- **The rule: any external write to the setting being edited cancels the
  edit first, then applies.** The writers are:
  - the `Fn` lighting keys and the param repeat;
  - VIA's lighting set and its Save, which forces a flush;
  - the LCD keys.

  Each calls `menu_external_write(setting)`. So a VIA Save can never
  persist a preview, and a cancel can't erase a change made meanwhile.
  QMK's dirty flags are never cleared by hand; a change pending from before
  the edit flushes as it would have.
- **While an RGB edit is open,** `rgb_matrix_eeprom_flush_allowed()` also
  returns false. That covers the deferred path. The rule above covers the
  forced one.
- **RGB with the lights off:** mode and HSV setters do nothing while
  disabled (fact 6).
  - The adapter sets values with RGB enabled inside one call (`_noeeprom`),
    restoring the enabled state last.
  - A cancel restores in that order too.
  - While the lights are off, the Lighting screen notes it, and edits still
    save.

| Item | Firmware value | Preview | Save | Cancel |
|---|---|---|---|---|
| Effect | the firmware's nine, by `rgb_mode_short()`'s names | `rgb_matrix_mode_noeeprom` | `rgb_matrix_mode` | restore (the order above) |
| Brightness, Hue, Saturation | `hsv` | `rgb_matrix_sethsv_noeeprom` | `rgb_matrix_sethsv` | restore |
| Second color (Alphas/Mods) or Speed | the `speed` byte, the hue offset in `ALPHAS_MODS` | `rgb_matrix_set_speed_noeeprom` | `rgb_matrix_set_speed` | restore |
| Lights | enabled | `_noeeprom` toggle | the saving toggle | restore |
| Screen | levels 0-23, 0 = off | the requested level (the override keeps it visible) | `kb_eeconfig_set_lcd_brightness` | restore |
| Power | the enum | none (it doesn't show while the menu owns the panel) | `power_set_mode()`, promoted from dev-only | none |
| Clock | display order 24h / 12h / Date / Off, mapped to the enum's 24H / 12H / OFF / DATE | none | `display_set_clock_mode` + `kb_eeconfig_set_clock_mode` | none |
| Lock lights, Charging light | levels 0-9 | `indicator_set_brightness`, new `indicator_set_charging_brightness` | new `kb_eeconfig` fields | restore |
| Battery | Percent / Hours | none | a new `kb_eeconfig` field | none |

- **The indicators get getters and range validation.** Their stored fields
  keep 0 as unset, distinct from a saved Off.

### Bluetooth: its own stage

- **Selecting a slot:** `bt_ui_select_slot(s)`, split out of
  `bt_ui_slot_key`.
  - It first releases and settles the outgoing keyboard (A1) and consumer
    (A3) reports, as the slider does with `clear_keyboard()`.
  - It waits while any other key is held, so a press can't go to one host
    and its release to another.
  - Typing across a host switch is not promised.
- **Pairing:** an asynchronous operation in `bt_ui.c`, with states
  requested, selecting, advertising, connected and failed.
  - It keeps the select and bounce sequence before `A6 51`, so the
    intended slot pairs.
  - The pairing screen shows those states, not `ch582_is_pairing()` alone.
  - **Cancelling** (a click, a hold, `Fn` plus a click, the backstop, a
    slider move) goes through the documented A6 path in
    `docs/wireless.md`, never `ch582_cancel_connect()`.
- **With the slider off Bluetooth** (`ch582_is_24g()`, `ch582_is_usb()`),
  the section says "Set by the slider" and offers nothing.

### Visibility, timeouts and sleep: one session

- **The visibility override:** while the menu is open, the panel is
  powered, Lights out's cap is lifted, and a requested level of 0 shows at
  level 1.
  - The requested level, 0 included, is kept separately and is what a save
    stores.
  - The override applies in the PWM path and in
    `display_backlight_effective()`. It respects the wake hold and comes off
    on every exit.
- **A session blocker:** `DSB_MENU` blocks deep sleep while the menu is
  open. The timeouts bound it, so a forgotten menu can't keep a board awake
  for long.
- **Timeouts, per screen kind:**
  - **Lists, text pages, About, Help, confirm screens:** 24 s with no knob
    input.
  - **Edits:** no idle timeout. The backstop, at 3 minutes, cancels (the
    old value comes back) and closes.
  - **Pairing:** until it ends or fails, under the same 3-minute backstop.
  - **Diagnostics pages shown from the menu:** the backstop, so an open
    page can't hold a board awake forever. (`Fn`+`D`'s page opened directly
    keeps today's behaviour.)
  - The timers are 32-bit elapsed times.
- **What counts:**
  - only knob input restarts the menu's timers. Hint repaints and host
    traffic don't, and neither does typing;
  - typing still counts as activity for the ladder.
- **After closing,** the ladder runs from the last input.

### Diagnostics, About, Help

- **Health and Camera pages:** a handoff to `PANEL_DEBUG`, opened on the
  chosen page (`display_debug_open(page)`); a knob click hands back.
- **Reset counters:** a confirm screen, then `health_reset()` and
  `display_debug_refresh()`.
- **About:**
  - page one: the firmware (`QMK_GIT_HASH`, `AK820_BUILD_TOKEN`, dev or
    daily), uptime from `rtc_seconds_since_boot()`, the battery's level,
    pack and time left ("-" when unknown), the power mode, the link;
  - page two: the bunny's three slices with "Jackrabbit", "by JD Lien" and
    "QMK port: fpb", then the GitHub link.
- **Help:** `const` pages wrapped to 20 columns by the generator. More info
  shows the QR code.

## RAM and flash

- **RAM:**
  - **First, share the scratch buffer:** `tx_pixels`' and
    `lcd_fill_rect`'s 512 B buffers become one. That frees 512 B, and the
    mono blit, the strip and the QR code use the same buffer.
  - **The menu's own state is a budgeted table, filled in S0 from the
    build's map:** the navigation (the stack of 3, the cursor, the timers),
    the capture table, the edit transaction's snapshot, the region
    signatures and paint progress, the pairing state, the diagnostics
    return.
  - The text grid reuses `dbg_text` and `dbg_shown`.
  - **If more is needed:** `log_buf` gives 18 B an entry, and each entry is
    15 minutes of the log's 180 h.
  - **Stacks:** new call frames still use them. Measure the watermarks
    after a worst-case session (every screen, the strip, the QR code), not
    only after a night.
- **Flash:** a few KB of code, the font 1.4 KB and the art 2.4 KB, against
  ~97 KB free in the dev build.
- **EEPROM:**
  - `kb_eeconfig` grows from 7 to 10 bytes at version 5: the indicator
    levels and the battery view.
  - `flash_stats.c`'s `kb_byte_field` and masks grow with it, and the new
    fields' counters go on a new reply page, with the host decoders
    updated.
  - The block's growth moves VIA's storage. So the build that grows it
    goes on with `flash.sh`, which backs up and restores the keymap and
    lighting around the flash's erase. That's the workflow every flash
    already uses.

## Stages

Each stage gets a codex review of its code before its flash, with every
finding dispositioned. Each goes onto gremlin's board before JD's.

1. **S0, the foundations**, with no visible menu yet:
   - the shared scratch buffer, and the RAM budget table from the map;
   - the owner enum and its transitions, with `Fn`+`D`, op 1 and the
     animation moved onto them;
   - the logo fix and the other gates;
   - the capture table in `pre_process_record_kb`;
   - the paint scheduler and its damage model.
   **Proof:** `Fn`+`D` and the animation behave as before (the
   release-matrix runs), and the logo fix works.
2. **S1, the mono paint, measured under load:**
   - `lcd_blit_mono`, the generated font;
   - op 27's test-paint sub, queued through the pump, never painted in the
     HID handler.
   - **Measured** with HC_ACCT's tick counter, over whole passes with the
     dashboard live (a track playing, the clock ticking): a glyph, a half
     row, a full row.
   - **That decides the unit,** and checks the generated glyphs against the
     flash atlas on the panel.
   - **The cursor style** (Open, 1) is settled on the real panel, with both
     colour sets.
3. **P1, the menu:** `menu.c` with host tests, then Lighting, Screen, Power,
   Clock, Help, About and Exit, the visibility override, `DSB_MENU`, the
   timeouts and the hint.
4. **P2, Indicators:** with the `kb_eeconfig` and `flash_stats` changes and
   the decoders.
5. **P3, Bluetooth:** selection with the report handoff, then pairing as an
   asynchronous operation.
6. **P4, Battery:** with the time-left row view, when that's built.
7. **Docs:**
   - `docs/display.md`: the owner, the mono path, the damage model;
   - `README.md` and the Help pages: the menu in place of the chords;
   - `CLAUDE.md`'s shortcut list.

## Testing

- **Host (gcc, as `scripts/lockchan_media_test.c` is built):**
  - **The state machine:** wrap-around, Back, opening on the first real
    item or the current value, page scrolling, click, a long press at 599,
    600 and 601 ms, Cancel, the 24 s timeout in lists and pages only, the
    backstop.
  - **The edit transaction:** an external write cancels the edit; a forced
    save mid-edit; RGB starting off.
  - **The capture table:** the matching release after a close, `Fn`
    released first, a hold across a timeout.
  - **The composer:** golden region lists per screen, taken from the
    mockup's strings; a style change on unchanged text counts as damage.
  - **Fit:** every label, value and Help line within 20 columns.
- **Op 27** (dev-only):
  - validated lengths and subs, bounded counts and coordinates;
  - asynchronous: inputs are queued for the menu's task, and a scheduled
    hold, never `wait_ms`;
  - a readable state reply: the owner, the screen, the cursor, the edit,
    the pairing state.

  It tests the model, not QMK's path. So beside it:
- **One short hands-on session** for what only the real knob can show:
  - the closing release;
  - `Fn` released first;
  - held keys and modifiers across opening and closing;
  - the 600 ms boundary;
  - a consumer burst;
  - the param repeat cancelling;
  - a VIA tap-hold on the knob.
  The wake rig can't turn a knob, so this needs hands.
- **On the board, on gremlin's first:**
  - **The stall counters:** no pass of 25 ms or more over a scripted
    session of 500 inputs. That includes the strip, the QR code, the
    restore with a track playing, and a wake. HC_ACCT's ring names any slow
    pass, and `count_ge_10ms` is reported against the idle rate.
  - **Typing while it's open:** presses *and releases* through the wake
    rig, checked with the F19 listener and the modifier state.
  - **Persistence, by reboot:** a value survives a reboot after a settled
    save. After a cancel, the reboot shows the old one. The cases include a
    change pending from before the edit, a VIA Save mid-edit, and RGB
    starting off.
  - **Pixels:** a selection-only change, and an interrupted paint, checked
    by photo. The camera page exists for filming.
  - **Ownership:** a host title, a clock sync, a lock-light frame, a Caps
    press, a slider move, a slot change and a charger plug-in while it's
    open; a wake; the startup restore; the `Fn`+`D` handoff; a DMA
    recovery. After Exit the dashboard comes back whole.
  - **Power:** Lights out lights the menu. `DSB_MENU` holds only while it's
    open. Sleep tests cut the USB data as well as VBUS (`DSB_USB`).
  - **Bluetooth, on a designated test slot and host:** select with a key
    held, pairing, and its cancellations. A pairing bounce can route input
    elsewhere, so it isn't mixed into the settings sweep.
  - **RAM and stacks** after the worst-case session.
  - **The bench's supply procedure** throughout: a slider flip can brown
    out the board and erase the session's evidence.

## Open

1. **The cursor: lit text or inverted.** Settled on the panel in S1. Both
   use the mono path and cost the same.
2. **`Fn`+`D`:** keep it as a shortcut beside Diagnostics, or free the key
   (JD's call).
3. **Half rows or full rows:** S1 decides.
