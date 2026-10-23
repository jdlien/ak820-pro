# The configuration menu: how to build it (revision 3, 2026-10-23)

Status: **a plan, nothing built.**
- **Revision 2** folded in codex's first review
  ([`review-codex-config-menu-build-plan-2026-10-23.md`](review-codex-config-menu-build-plan-2026-10-23.md)).
- **Revision 3** folds in its verification of revision 2
  ([`review-codex-config-menu-build-plan-verify-2026-10-23.md`](review-codex-config-menu-build-plan-verify-2026-10-23.md)).
  It adds **"The implementation contract"**, the decisions S0 is built from,
  so the implementer doesn't have to discover them while coding.

**The other documents:**
- **The design and its decisions:** [`CONFIG-MENU-PLAN.md`](CONFIG-MENU-PLAN.md).
- **The visual spec:** [`config-menu-mockup.html`](config-menu-mockup.html),
  drawn from the board's own atlases. It stays the spec until the build: a
  change to the layout or the words goes into it too.

Paths are under `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` unless
given otherwise, with line numbers at `b9555ff3e6`.

## What it builds

- **Opening and closing:** `Fn` plus a knob click opens and closes the menu,
  over the whole panel.
- **The top level:**
  - page one: Lighting, Screen, Connection, Power, Indicators, Clock,
    Battery, Diagnostics;
  - page two: Help, About, Exit.
- **Driving it:**
  - turning moves, wrapping at the ends;
  - lists and text pages scroll by page;
  - a click chooses or saves, and a long press goes back or cancels;
  - every list below the top starts with "‹ Back".
- **Two kinds of choice:**
  - **Previewing:** the lighting values, Effect, Lights and the Screen show
    as you turn, and a click saves.
  - **Committing:** Power, Clock, Battery and the Bluetooth slots apply on
    the click.
- **Timeouts:**
  - lists, text pages and committing choices close after 24 s with no knob
    input;
  - a previewing edit has no idle timeout, only a 3-minute backstop.
- **The hint:** the title gives way to "Turn + Click Knob" for 1 s after 4 s
  idle.
- **About, page two:** the Jackrabbit bunny (27x42) with the credits.
- **Display:**
  - text in the small face (Cozette 6x14), 20 columns;
  - the selection as lit text or inverted (Open, 1);
  - values as the `Fn`-key readouts show them, with the effects by the
    readout's names.
- **`Fn`+`D`:** unassigned in the default keymap. Its pages live under
  Diagnostics.
- **Typing works normally while the menu is open.** Only the knob is
  captured.

## What the code says

Checked in the source, then by codex twice. The verified corrections are
folded in.

1. **RAM:**
   - **The dev build's heap gap is 32 B** (`via-dev-ce229f87c6`); the daily
     build's is 2,160.
   - **The battery log** (`log_buf`) is 12,960 B: 720 entries of 18 B, one
     every 15 minutes (`battery.c:1352-1353`).
   - **Two 512 B static buffers:** `tx_pixels()` and `lcd_fill_rect()` each
     keep one (`lcd_bus.c:131-188`). Both are synchronous, used only on the
     main thread, and SPI's ISR reads the source during `spiSend()`.
   - **The stacks are fixed:** interrupt 1,024 B, main 2,048 B.
2. **Drawing from RAM:**
   - The DMA can't read RAM (`lcd_bus.h:24-26`), so anything drawn from RAM
     is a CPU push through `lcd_blit_ram`.
   - A 12x12 tile measured 3.4 ms. How much of that is fixed per call isn't
     known.
3. **Panel ownership:**
   - Today the `Fn`+`D` page and the animation own the panel through flags
     (`display.c:136-148`): `debug_active`, `debug_exit_step` and
     `display_paused`, plus `anim_on` in `lcd_bus.c:1097,1112`.
   - Those flags are checked on several independent paths, which the
     contract's migration table lists.
   - The 14-stage restore (1394-1435) isn't 14 passes, and it doesn't paint
     everything: the battery's bolt, text and bar follow by `batt_dirty`.
   - The pump removes a glyph from its queue when its DMA *starts*.
4. **Known gaps:**
   - The logos paint over the page.
   - `display_bus_idle` sees only `debug_exit_step`.
   - `display_set_param_status(const char *)` can't tell who posted.
5. **Input:**
   - **Weak mods** are cleared on every press in `action_exec()`, before
     `pre_process_record_quantum()` (`quantum/action.c:95-97`).
   - **The early hook:** `pre_process_record_kb` runs before action tapping
     and combos, and a false return there drops the event (133-134).
   - **The keycode:** `get_record_keycode(record, true)` has already done the
     layer and VIA lookup. A press caches its source layer, and the release
     uses that cache.
   - **Detents** come through the encoder map, two halves each, with a 1 ms
     wait after each. `encoder_handle_queue()` drains its queue of up to 32
     in one call (`quantum/encoder.c:30-45`).
   - **The positions:** the knob press is matrix (0,14), and `D` is (3,3)
     (`keyboard.json`).
   - **`RGB_TRIGGER_ON_KEYDOWN` isn't defined,** so QMK's `RM_*` keys act on
     release.
   - **Not enabled:** combos and tap dance.
6. **Setters:**
   - RGB mode and HSV setters do nothing while RGB is disabled
     (`rgb_matrix.c:605,657`).
   - `power_set_mode()` exists, but only for the dev hooks (`power.c:330-335`).
   - `rgb_mode_short()` is static and built only with `PARAM_OVERLAY`.
   - The CH582's pending-action state (`pa`) is private, and its pairing
     status is optimistic (`ch582f_ajazz.c:179,1530,1587`).
7. **VIA:**
   - `via_command_kb()` is called before VIA dispatches any command
     (`quantum/via.c:286-296`), and a false return lets processing go on.
   - VIA's RGB Save forces a flush (737).
8. **The settings block (`kb_eeconfig`) and the write-attribution table
   (`flash_stats.c`):**
   - The block is 7 bytes at version 4, and a mismatch zeroes the RAM copy
     on read.
   - `flash_stats.c` keeps a per-byte field table, plus 8-bit masks in
     `kb_byte_field[]`, `pending_mask` and the locals `mask` and `m`.
   - Its reply page 1 is full: 16 B of writer totals and six u16 field
     counters. `ak820health.py:309` unpacks it as `<4I6H`.
   - The Rust daemon doesn't implement HC_FLASHW.
   - The diag simulator's EEPROM stub still says six bytes.
9. **Visibility:**
   - The PWM runs in an ISR (`display.c:238`), and `display_set_power()`
     writes the backlight GPIO directly (308).
   - The sleep blockers end at `DSB_CHARGE = 0x2000` (`sleep.c:152-154`).
   - `hostagent/ak820battery.py`'s `SLEEP_DSB` list ends at "charge".
10. **Identity:** `AK820_BUILD_TOKEN`, `QMK_GIT_HASH` (`version.h`) and
    `rtc_seconds_since_boot()`.

## The implementation contract

The decisions S0 is built from. Anything here that turns out to be wrong in
the code is raised before working around it.

### C1. Owner, session and transitions

- **State, in `panel_owner.c`:**
  - **`panel_owner`:** `PANEL_DASH`, `PANEL_DEBUG`, `PANEL_MENU` or
    `PANEL_ANIM`.
  - **`menu_session`:** `SESSION_NONE`, `SESSION_PENDING` (the opener is
    consumed, waiting for a wake's repaint) or `SESSION_OPEN`.
  - **`restore_gen`, `restore_pending`:** a restore is work owned by the
    dashboard, not a fifth owner.
- **The transitions.** Nothing else changes `panel_owner`.

  | From | Event | To | Actions |
  |---|---|---|---|
  | DASH, no session | open (the opener) | MENU, OPEN; or PENDING if the wake hold is on | Supersede any restore. Reset `dbg_text`, `dbg_shown` and the damage state. Suppress param overlays. Visibility override on. Start the band clear. |
  | PENDING | the wake hold released | MENU, OPEN | as above |
  | PENDING | a second opener | DASH, NONE | the pending request cancelled |
  | DASH, no session | `DBG_PAGE` or op 1 | DEBUG (Health) | today's behaviour |
  | DEBUG, no session | `DBG_PAGE` or op 1 | Camera, then DASH and a restore | today's three-step cycle |
  | DEBUG, no session | open | MENU, OPEN | a handoff: reset the buffers and the damage state |
  | MENU, OPEN | Diagnostics > Health or Camera | DEBUG, the session staying OPEN | Reset the buffers. The page clears. |
  | DEBUG, OPEN | a knob click | MENU (at Diagnostics) | Reset the buffers. |
  | DEBUG, OPEN | `DBG_PAGE` or op 1 | Health to Camera, then back to MENU | controlled by the session |
  | MENU or DEBUG, OPEN | close (Exit, `Fn` plus a click, the timeout, the backstop) | DASH, NONE, and a restore (`restore_gen++`) | Cancel an open edit. Re-prime the overlays. Visibility override off. |
  | DASH, no session, no restore | an animation start | ANIM | Start the animation. `anim_active()` must agree with the owner. |
  | ANIM | an animation stop | DASH and a restore | as today |
  | MENU, DEBUG, or a restore pending | an animation start | refused | |
  | ANIM | open | refused | The opener is still consumed, with its release. |

- **Predicates:** distinct and named, never one generic "owned":

  | Predicate | True when | Used by |
  |---|---|---|
  | `dash_paints()` | DASH and no restore pending | housekeeping's dashboard owners, the logos, wake paint |
  | `restoring()` | `restore_pending` | `display_band_busy`, `display_redraw_dashboard` (no restore under a non-DASH owner) |
  | `panel_lit_for_owner()` | DEBUG, or the session OPEN | Lights out's exception (`power.c:246`), not ANIM |
  | `anim_admissible()` | DASH, no session, no restore | `ANIM_TOG` (`ak820pro.c:374`) |

- **Migration checklist.** Each of these existing uses is converted and
  ticked off in S0's code review:
  - `display.c:136-148`: the flags and `display_set_paused()`;
  - `display.c:1170-1220`: the debug query and the toggle;
  - `display.c:1447`: the deferred redraw;
  - `display.c:2601`: band busy;
  - `display.c:2963,2974,2982`: the self-heal and the pump's branches,
    dispatched by owner, each with its own recovery;
  - `display.c:3316,3330`: the wake paint and its completion;
  - `display.c:3362-3377`: housekeeping, where the debug composition stays
    separate;
  - `display.c:3431-3455`: the five logo painters, which update RAM, mark
    themselves stale, and repaint when `dash_paints()` allows;
  - `ak820pro.c:374` and `power.c:246`;
  - `lcd_bus.c:1097,1112`: `anim_on`;
  - `hid_protocol.c:1029`: op 1.
- **`display_restored(gen)`:** true only when:
  - restore `gen`'s stages have ended;
  - `gq` and `lq` are empty, and `!lcd_blit_busy()`, so the last DMA has
    finished;
  - `!batt_dirty`;
  - no logo is stale.

  The restore's own work never waits on this.
- **Overlays:** every `display_set_param_status()` post is dropped while the
  session is PENDING or OPEN, Diagnostics included. Alerts and other state
  keep updating. At close, `param_status_task` re-primes, and the restore's
  text stage calls `conn_status_update()` first.

### C2. Input

- **The hook:** `pre_process_record_kb(keycode, record)` in `ak820pro.c`.
  - Uncaptured events return `pre_process_record_user(keycode, record)`, so
    the default chain is kept.
  - Captured events return false.
- **Identity, never keycodes:**
  - the knob press is the matrix event at (0,14);
  - a detent is an event of type `ENCODER_CW_EVENT` or `ENCODER_CCW_EVENT`
    on encoder 0.
  So a VIA-remapped knob still drives the menu, and `KC_MUTE` and the volume
  codes are never matched.
- **`Fn`** is the `WINFN` or `MACFN` bit in `layer_state` at the knob's
  press. A layer-tap whose layer isn't active yet isn't `Fn`.
- **Capture bits:** one each for the knob press, a clockwise detent and a
  counter-clockwise detent.
  - A captured press sets its bit.
  - Its release is consumed and the bit cleared, **whatever the session or
    owner is by then**. The bits survive close and handoff.
  - A release whose press wasn't captured is forwarded.
- **What capture costs, by design:**
  - Weak mods were already cleared on the press, as for any key.
  - Captured events skip `process_record_kb`'s later effects: they add no
    health key count and send no USB remote wake. Combos and tapping never
    see them.
- **The opener while closed:** a press of (0,14) with `Fn` active.
  - It's captured, and the session goes to OPEN or PENDING by C1's table.
  - Under ANIM it's refused, but still captured, with its release.
- **While the session is open:**
  - **Detents:** captured; a press half queues a turn.
  - **The knob press:** captured.
    - With `Fn` active, it queues a close.
    - Otherwise it starts the hold timer. A release before 600 ms queues a
      click. At 600 ms the menu task queues Back.
    - A release at or after 600 ms that the task hasn't caught queues Back,
      exactly once.
- **Opening also cancels the param repeat.** `modified_consumer_task()`
  keeps running.
- **S0's scope:** the hook is built with `MENU_ENABLE` off, so normal
  firmware never swallows `Fn` plus the knob into an invisible menu before
  P1. Op 27 exercises it in dev builds.
- **Where it runs:** the menu task, `menu_task()`, runs each pass in
  `housekeeping_task_kb`, **before** `display_blit_pump()`. It handles the
  queued events, the timers and the hold, independent of the gated display
  housekeeping. The pump stays at its own site (the warning at
  `display.c:3370-3376`).

### C3. Damage

- **Regions are generated on demand** by the composer for the current
  screen, at most 24, and only their shown state is stored. Each slot keeps
  a 16-bit signature, a 2-bit state (`EMPTY`, `INVALID`, `PARTIAL`,
  `COMMITTED`) and a generation byte: 4 B a slot, 96 B in all.
- **The rules:**
  1. Before a region's first partial write, its slot becomes `INVALID`.
  2. It becomes `COMMITTED`, with the new signature, only after its last
     chunk, with any DMA finished.
  3. A region that isn't `COMMITTED` is repainted even if the new target's
     signature equals its last committed one. That's the A, then partial B,
     then A case.
  4. A region the new screen no longer has, or that moved, gets its old
     rectangle erased (a chunked black fill). Any region that overlaps the
     erase is invalidated.
  5. The hue marker's whole footprint (its line through the strip and its
     triangle below) is one region. Moving it repaints the strip columns it
     covered and erases the rest.
  6. The separator and the scrollbar are regions.
- **Navigation regenerates the target,** so pending work is superseded.
- **Each pass, the painter does one bounded operation:**
  - a half row of text;
  - one chunk of a shape, strip, QR code or erase;
  - one band of the open clear;
  - one big-face glyph's arm or completion.
- **Text:** the rows' desired text is `dbg_text`, and their shown text is
  `dbg_shown`. A row's signature covers the text and its style (normal,
  selected, inverted or lit), so a selection change on the same text is
  damage.

### C4. The scratch buffer

- **One static buffer,** `lcd_scratch[512]` in `lcd_bus.c`, replaces
  `tx_pixels`' and `lcd_fill_rect`'s.
- **Its rules:**
  - main thread only, not reentrant;
  - never used from a callback or an ISR, and interrupts stay enabled;
  - held by its caller until `spiSend()` completes, because SPI's ISR reads
    it;
  - no pointer to it is kept.
  A debug build asserts acquire and release.
- **The panel-order stream:** `lcd_stream_begin(x, y, w, h)`,
  `lcd_stream_bytes(const uint8_t *panel_order, n)` and `lcd_stream_end()`.
  - Generated pixels (the mono glyphs, the strip, the QR code, the erase)
    are written into the scratch already in panel byte order, and sent
    through the stream.
  - They're never passed back through `tx_pixels()`, which byte-swaps into
    the same scratch.
- **`lcd_blit_mono(bits, cols, x, y, fg, bg)`:**
  1. It quiesces the bus *before* opening its window.
  2. It expands the bits row by row, in raster order, into the scratch.
  3. It streams the result.

### C5. RAM

- **The ceiling:** the menu and every later stage together use at most
  400 B of new BSS, and **the dev build's heap gap stays at least 128 B**.
  `build.sh` checks the gap from `arm-none-eabi-size` and fails a build
  below it.
- **The budget,** from `sizeof` estimates, checked against each linked
  build:

  | Item | Bytes |
  |---|---|
  | owner, session, restore gen, pending flags | 8 |
  | capture bits, hold timer | 8 |
  | nav stack (3 levels), cursor, top, timers | 24 |
  | edit transaction (an RGB config snapshot, a level, flags) | 16 |
  | region slots (24 x 4) | 96 |
  | chunk cursor | 8 |
  | the input queue (8 events) | 16 |
  | op 27 state | 8 |
  | P2: `flash_stats` (3 counters, wider masks) | 12 |
  | P3: Bluetooth operation state | 24 |
  | **total** | **~220** |

- **Freed:** the shared scratch frees 512 B, so the dev gap goes from 32 to
  about 544 before the menu's ~220. If the linked build disagrees, take
  entries from `log_buf`: 18 B each, 15 minutes of the log's 180 h.
- **Stacks:** the watermarks are measured after a worst-case session (every
  screen, the strip, the QR code), as well as after a night.

### C6. The edit transaction

- **The conflict domain is the whole RGB config** (for the Screen, the LCD
  level). An external write to it cancels an open edit first, then applies.
- **The writers and where they're seen, with no core file changed:**
  - **VIA:** `via_command_kb()` recognizes the custom set-value and save
    commands on the RGB-matrix channel, cancels an open RGB edit, and
    returns false, so VIA's own processing and reply go on.
  - **`RM_*` keys:** observed in `process_record_kb` on release, since
    `RGB_TRIGGER_ON_KEYDOWN` isn't defined.
  - **The board's `RGBM_*` wrappers and each param repeat step.**
  - **`SCR_UP` and `SCR_DN`:** these cancel a Screen edit.
- **While an RGB edit is open,** `rgb_matrix_eeprom_flush_allowed()` also
  returns false. QMK's dirty flags are never cleared by hand.
- **The RGB adapter:**
  - Preview, Save and Cancel all set values with RGB enabled inside one call
    (`_noeeprom`, then the saving variant to save), restoring the enabled
    state last.
  - **Lights saves with an explicit `rgb_matrix_enable()` or
    `rgb_matrix_disable()`, never a toggle.**

### C7. Visibility and sleep

- **`menu_visibility` is a `volatile bool`,** true for the session's
  lifetime (PENDING excluded, Diagnostics included). The ISR only reads it.
- **One effective-level function,** shared by the PWM ISR,
  `display_backlight_effective()` and `display_set_power()`'s GPIO write:
  1. **With the override on:** the panel counts as powered, without changing
     `display_powered`; the cap is lifted; the level is
     `max(requested, 1)`.
  2. **The wake hold is applied last.**

  The requested power and level are never changed by the override.
- **`DSB_MENU = 0x4000`** is set while the session isn't NONE, PENDING
  included. "menu" is appended to `ak820battery.py`'s `SLEEP_DSB`.
- **Timeouts are 32-bit elapsed times.** Only knob input restarts them:
  hint repaints, host traffic and typing don't. Typing still counts for the
  ladder.

### C8. Screens and coordinates

From the mockup, which stays authoritative:

| Screen kind | Layout |
|---|---|
| list, text page | title row y 0-13; separator y 14 (x 4-123); rows y 15 + 14k, k = 0..7; scrollbar x 125, y 15-126 |
| range editor | title, separator; big value y 22 (10 cells centred, x 14); bar outline x 13-114, y 51-60; hints y 72, 86, 100 |
| hue editor | title, separator; strip x 4-123, y 22-35; marker line y 20-37 and triangle y 38-40; big value y 44; hints y 72, 86, 100 |
| About page two | the bunny's slices at x 4, rows k..k+2; the credits at x 36, 14 columns |
| More info | the QR code: 29 modules x 3 px plus a 2-module border, 99x99, at x 14, y 16 |

The choices, by kind:

| Choice | Kind | Timeout |
|---|---|---|
| Effect, Lights | previewing | the 3-minute backstop |
| the ranges, the hues, the Screen | previewing | the backstop |
| Power, Clock, Battery, the Bluetooth slots | committing on the click | 24 s |

## The settings

| Item | Firmware value | Preview | Save | Cancel |
|---|---|---|---|---|
| Effect | the nine enabled effects, named by one shared table (moved out of `PARAM_OVERLAY`) | `rgb_matrix_mode_noeeprom` | `rgb_matrix_mode` | restore (C6) |
| Brightness, Hue, Saturation | `hsv` | `rgb_matrix_sethsv_noeeprom` | `rgb_matrix_sethsv` | restore |
| Second color (Alphas/Mods) or Speed | `speed`, the hue offset in `ALPHAS_MODS` | `rgb_matrix_set_speed_noeeprom` | `rgb_matrix_set_speed` | restore |
| Lights | enabled | `_noeeprom` enable or disable | explicit `rgb_matrix_enable` or `rgb_matrix_disable` | restore |
| Screen | levels 0-23, 0 = off | the requested level (C7 keeps it visible) | `kb_eeconfig_set_lcd_brightness` | restore |
| Power | the enum | none | `power_set_mode()`, promoted (declaration and body) | none |
| Clock | displayed 24h / 12h / Date / Off, mapped to the enum's 24H / 12H / OFF / DATE | none | `display_set_clock_mode` + `kb_eeconfig_set_clock_mode` | none |
| Lock lights, Charging light | levels 0-9 | `indicator_set_brightness`, new `indicator_set_charging_brightness` | `kb_eeconfig` bytes 7 and 8 | restore |
| Battery | Percent or Hours | none | `kb_eeconfig` byte 9 | none |

**The indicators** get getters and range validation, and their saved levels
are applied at init. Their stored fields keep 0 as unset, distinct from a
saved Off (`level + 1`).

**The settings block and the write attribution** (P2):
- **The new bytes:** `kb_eeconfig` grows from 7 to 10 bytes at version 5:
  byte 7 is `ind_locks_p1`, 8 is `ind_charging_p1`, 9 is `batt_view_p1`.
  Unset means Percent.
- **`flash_stats.c`:**
  - `kb_byte_field[]` grows, and every mask carrier is widened to 16 bits:
    `pending_mask`, the locals `mask` and `m`.
  - **Page 1 is frozen** at its six counters.
  - **A new page 3** carries three u16 counters at offsets 0, 2 and 4. Old
    firmware answers it `RTC_UNHANDLED`, which the host shows as "-".
  - `ak820health.py` reads page 3, and the diag simulator's EEPROM stub
    goes to 10 bytes.
- **What resets:** `flash.sh` backs up and restores the keymap and lighting
  around the flash's erase. **The settings block isn't migrated:** its
  values (the BT slot, the LCD level, the clock format, the saved battery
  level, the power mode) reset at that flash, as they do at every flash.

## Bluetooth (P3, with its own plan and codex round before code)

- **An operation API in `ch582f_ajazz.c`,** extending its pending-action
  machinery, which stays private:
  - `ch582_op_select(slot)` and `ch582_op_pair(slot)` return an id;
  - `ch582_op_status(id)` returns `SELECTING`, `BOUNCING`, `SELECTED`,
    `PAIR_SENT`, `ADVERTISING` (`5B 31` seen), `CONNECTED` (on that slot),
    `FAILED` (retries exhausted) or `SUPERSEDED`.
  - A new request, a slider move, or the `Fn` slot and pair keys supersede
    the operation in progress.
  - Cancelling is defined for every phase, through the documented A6 select
    and bounce path, never `ch582_cancel_connect()`.
- **The report handoff, before any select or pair:**
  1. Wait until all keys are up, bounded at 2 s; otherwise refuse, with a
     message.
  2. Suspend A1 and A3 forwarding.
  3. Send the releases and wait for their delivery to succeed. An idle
     queue isn't success: a frame can leave it by giving up.
  4. Run the operation.
  5. Resume when all keys are up, sending the current report.
  New presses during the transition aren't forwarded to the intermediate
  host. The blocking drain helper isn't used.
- **With the slider off Bluetooth** (`ch582_is_24g()`, `ch582_is_usb()`),
  the section says "Set by the slider".

## Diagnostics, About, Help

- **Health and Camera:** by C1's table.
- **Reset counters:** a confirm screen, then `health_reset()` and
  `display_debug_refresh()`. This replaces `Fn`+`D`'s hold.
- **`Fn`+`D` unassigned** (at the end of P1, once Diagnostics works):
  1. On **JD's board**, the authoritative layout, set matrix (3,3) to
     `KC_NO` on `WINFN` and `MACFN`, over VIA's dynamic-keymap commands.
     It's `KC_NO`, not `KC_TRNS`, which would fall through and type a `d`.
  2. Read the writes back, dump (`ak820keymap.py dump`), and regenerate
     with `keymap_to_c.py <that dump> --write`.
  3. The diff of `keymaps/via/keymap.c` must show exactly those two
     changes, with the encoders and `QK_BOOT` untouched.

  `DBG_PAGE` stays in the enum and in `via.json`, so it can still be
  assigned, and op 1 still opens the page on the bench.
- **About:**
  - page one: the firmware, uptime, the battery ("-" when unknown), the
    mode, the link;
  - page two: the bunny with "Jackrabbit", "by JD Lien" and "QMK port:
    fpb", then the GitHub link.
- **Help:** `const` pages wrapped to 20 columns by the generator. More info
  shows the QR code.

## Generated files

- **`scripts/gen_mono_font.py` → `graphics/res/font_small_mono.h`:**
  - the 95 ASCII glyphs from `assets-src/current/Iosevka-Medium-13.png`;
  - `‹ › • ▸ ✓` from `assets-src/cozette.bdf` at codes 0x80-0x84, placed as
    `mkbdfatlas.py` places the ASCII;
  - 14 B a glyph, 1.4 KB.
- **`scripts/gen_menu_art.py` → `graphics/res/menu_art.h`:**
  - the bunny, 27x42 RGB565, made as the splash is;
  - the QR code's module bitmap (29x29, 106 B).
- **The Help text:** wrapped, and checked to fit, by a test.

## Op 27 (dev builds only)

- **The packet:** `[0x07, 0x13, 0x76, 27, sub, args...]`. A wrong length or
  an unknown sub answers an error and does nothing.

  | Sub | Args | Effect |
  |---|---|---|
  | 0 | x, y, cols, style | S1's test paint, queued through the pump |
  | 1 | signed count, bounded to ±16 | turns |
  | 2 | | a click |
  | 3 | | a hold: a press now, a release scheduled at 600 ms or more, never `wait_ms` |
  | 4 | | `Fn` plus a click |
  | 5 | | read the state |

- **The queue** holds 8 events, and when it's full it answers busy.
- **Replies:** status, owner, session, screen id, cursor, an edit flag, the
  pairing phase (P3), the last paint's time (S1).
- **The daily and fpb builds** don't compile HC_DEVHOOK at all. `build.sh`
  already enforces that.

## Stages

Each stage gets a codex review of its code before the flash, with every
finding dispositioned. Each goes onto gremlin's board before JD's.

1. **S0, the foundations** (with `MENU_ENABLE` off):
   - C1's owner, session and transitions, with the migration checklist done;
   - C2's capture, C3's damage model and C4's scratch buffer and stream;
   - C5's budget and the `build.sh` check;
   - the logo fix.
   **Proof:**
   - the transition table, by op 27 and host tests;
   - the animation refused and stopped, by its rules;
   - the startup restore, and an interrupted one;
   - a stale logo repaired;
   - the physical release cases (the hands-on session);
   - A, then partial B, then A;
   - the linked RAM of the dev and daily builds;
   - `Fn`+`D` and the animation behaving as before;
   - no pass of 25 ms or more over the session.
2. **S1, the mono paint, measured:**
   - `lcd_blit_mono` and the generated font, with op 27 sub 0 painting
     under its own panel ownership. A test paint is a short menu-owned
     screen, never a second painter over the live dashboard.
   - **Measured separately with HC_ACCT's ticks:** the CPU time of a glyph,
     a half row and a full row, and whole passes during real knob spins,
     clock edges and radio traffic.
   - **The bounds:** the renderer's per-pass budget, and the whole pass's
     bound. If spins exceed it through the encoder drain, a bounded drain
     (a change to `quantum/encoder.c`) is weighed then.
   - **Settled on the panel:** the cursor style (Open, 1), and the generated
     glyphs against the flash atlas.
3. **P1, the menu:** `menu.c` with host tests; Lighting, Screen, Power,
   Clock, Diagnostics, Help, About and Exit; C6 to C8.
   **Exit gates:**
   - real VIA Set and Save packets mid-edit;
   - real `RM_*` keys: the wake rig's key remapped to `RM_VALU` for the
     test, then put back;
   - a Save with RGB disabled, and Lights saved;
   - visibility starting from Screen Off and from level 0;
   - the session lasting through Diagnostics;
   - persistence across a reboot after a settled save and after a cancel;
   - the hands-on session;
   - then `Fn`+`D` unassigned.
4. **P2, the indicators and the settings block:**
   - `kb_eeconfig` version 5, the widened masks, page 3, `ak820health.py`
     and the simulator.
   **Proof:** the old pages byte-identical; each new field's write
   attributed to it; unset, zero and invalid values booting correctly.
5. **P3, Bluetooth,** after its own plan and codex round.
   **Proof:**
   - driver tests for select, bounce, pair and cancel;
   - transport tests for A1 and A3 delivery and failure, with new presses
     during a transition;
   - on a designated test slot and host.
6. **P4, Battery,** with the time-left row view, using byte 9. Unknown
   estimates and sleep and wake are tested.
7. **Docs:**
   - `docs/display.md`;
   - `README.md` and the Help pages;
   - `CLAUDE.md`'s shortcuts and its "read `Fn`+`D` first" advice, which
     becomes Diagnostics > Health page; the same in `docs/hardware.md`.

## Testing

- **Host (gcc, as `scripts/lockchan_media_test.c` is built):**
  - **The transition table:** every row, with the refusals.
  - **The state machine:** wrap, Back, the cursor's opening position, page
    scrolling, click, a hold at 599, 600 and 601 ms, Cancel, the timeouts
    per kind, the backstop.
  - **The edit transaction:** an external write cancelling; a forced save;
    RGB starting off; Lights.
  - **The capture table:** the release after a close, `Fn` released first,
    a hold across a timeout, a second opener while pending.
  - **The damage model:**
    - A, then partial B, then A;
    - a long value then a short one, with the old footprint erased;
    - the marker moving;
    - a selection change on unchanged text;
    - the golden region lists per screen, taken from the mockup.
  - **Fit:** every label, value and Help line within 20 columns.
- **On the board, on gremlin's first, driven by op 27 plus the hands-on
  session:**
  - **The stall counters:** no pass of 25 ms or more over a scripted
    500-input session, including the strip, the QR code, a restore with a
    track playing, a wake and real spins. Counter resets are kept out of
    measured sessions.
  - **Typing while it's open:** presses, releases and modifier state,
    through the wake rig and the F19 listener.
  - **Persistence:** by reboot, after the cases in P1's gates.
  - **Pixels:** a selection-only change, an interrupted paint, and a
    restore's final DMA, checked by photo.
  - **Ownership:** a host title, a clock sync, a lock-light frame, a Caps
    press, a slider move, a slot change, a charger plug-in, a wake, the
    startup restore, the Diagnostics handoff, and a DMA recovery.
  - **Power:**
    - Lights out lights the menu;
    - `DSB_MENU` holds only through the session;
    - sleep tests cut the USB data as well as VBUS (`DSB_USB`).
  - **Bluetooth:** on a designated test slot, kept out of the settings
    sweep.
  - **RAM and stacks** after the worst-case session.
  - **The bench's supply procedure** throughout.

## Open

1. **The cursor: lit text or inverted.** Settled on the panel in S1.
2. **Half rows or full rows:** S1's measurements decide.
