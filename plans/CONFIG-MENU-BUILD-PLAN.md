# The configuration menu: how to build it (revision 4, 2026-10-23)

Status: **a plan, nothing built.** Owned by Warren (gremlin's session) from
10-23.
- **Revision 2** folded in codex's first review
  ([`review-codex-config-menu-build-plan-2026-10-23.md`](review-codex-config-menu-build-plan-2026-10-23.md)).
- **Revision 3** folded in its verification of revision 2
  ([`review-codex-config-menu-build-plan-verify-2026-10-23.md`](review-codex-config-menu-build-plan-verify-2026-10-23.md)).
  It added **"The implementation contract"**, the decisions S0 is built from,
  so the implementer doesn't have to discover them while coding.
- **Revision 4** folds in the verification of revision 3
  ([`review-codex-config-menu-build-plan-verify2-2026-10-23.md`](review-codex-config-menu-build-plan-verify2-2026-10-23.md)):
  - C1's restore gets phases and an owner for its residual work;
  - pending entry is split from opening;
  - C3 uses fixed slot geometry per layout, with a banded clear on a layout
    change;
  - the knob's input is coalesced, not queued;
  - S0 gets a visible fixture, an armed test mode, the session's visibility
    and sleep blocker, and op 27's exact wire layout.

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

### C1. Owner, session and restore

- **State, in `panel_owner.c`:**
  - **`panel_owner`:** `PANEL_DASH`, `PANEL_DEBUG`, `PANEL_MENU` or
    `PANEL_ANIM`. In S0 the MENU owner's screen is the fixture (S0 below).
  - **`menu_session`:** `SESSION_NONE`, `SESSION_PENDING` (the opener is
    consumed, waiting for a wake's repaint) or `SESSION_OPEN`.
  - **The restore,** work owned by the dashboard, not a fifth owner:
    `restore_gen` (u8), `restore_phase` and `restore_damaged`.
- **The restore's phases:**

  | Phase | Meaning |
  |---|---|
  | `SPLASH` | boot, until the startup callback fires |
  | `WAITING` | the dashboard is known invalid, but another owner or a session holds the panel; nothing runs |
  | `CLEAR` | the banded clear (today's stages 1 to `DBG_CLEAR_BANDS`) |
  | `STAGES` | the components (today's stages after the bands, the lock band one component a pass) |
  | `RESIDUAL` | the battery's `batt_dirty` parts and every stale logo, painted **by the restore**, one a pass, not gated by `dash_paints()`; it ends when `gq` and `lq` are empty and `!lcd_blit_busy()` |
  | `DONE` | the visible dashboard is complete |

  - **A restore is requested** by the startup callback, a close, a
    standalone owner's exit (the Camera page's step back, an animation's
    stop) and the self-heal. If the owner is DASH and the session NONE, it
    **starts**; otherwise the phase becomes `WAITING`, and the owner's exit
    starts it.
  - **Starting** always means `restore_gen++`, `CLEAR` from band 1, the
    queues discarded (as stage 1 does today) and `restore_damaged` false.
    No restore ever resumes an old cursor.
  - **Loss:** a blit given up (`lcd_blit_lost_take()`) during `CLEAR` to
    `RESIDUAL` sets `restore_damaged`. At `RESIDUAL`'s end a damaged
    generation starts a new one instead of reaching `DONE`, no more than
    once in 5 s, as the self-heal is limited today. In `DONE` the self-heal
    requests a restore, as today. Under MENU or DEBUG a loss invalidates
    every region of that owner's screen (C3), and the owner repaints its own
    content.
- **`display_restored(gen)`** is `gen == restore_gen && restore_phase ==
  DONE`. It describes the dashboard now on the panel: a superseded
  generation never becomes true. The restore's own work never waits on it.
- **The transitions.** Nothing else changes `panel_owner` or
  `menu_session`. An event a row doesn't name is a no-op or a refusal,
  never an implicit change of owner.

  | State | Event | Result |
  |---|---|---|
  | DASH, NONE | the opener (`Fn` plus the knob's press) | PENDING (actions P) while the wake hold is on; otherwise MENU, OPEN (actions O) |
  | PENDING | the wake hold released (`display_wake_release()`'s notice) | MENU, OPEN (actions O) |
  | PENDING | a second opener | NONE: the request cancelled, `DSB_MENU` cleared, the overlays re-primed |
  | PENDING | any other knob input | captured and discarded; nothing buffered for a screen not yet open |
  | PENDING | `DBG_PAGE`, op 1, an animation start | refused; the pending request and the wake's work are unchanged |
  | DASH, NONE | `DBG_PAGE` or op 1 | DEBUG (Health), as today |
  | DEBUG, NONE | `DBG_PAGE` or op 1 | Camera, then DASH and a restore: today's three-step cycle |
  | DEBUG, NONE | the opener | MENU, OPEN (actions O): a handoff |
  | MENU, OPEN | Diagnostics > Health or Camera, `DBG_PAGE` or op 1 | an open edit cancelled; DEBUG (Health), the session staying OPEN, returning to Diagnostics; the buffers reset |
  | DEBUG, OPEN | a knob click | MENU, at Diagnostics; the buffers reset |
  | DEBUG, OPEN | `DBG_PAGE` or op 1 | Health to Camera, then MENU at Diagnostics |
  | MENU or DEBUG, OPEN | close (Exit, `Fn` plus a click, the timeout, the backstop) | DASH, NONE (actions C), and a restore started |
  | any | a slider move, a slot change, a charger plug-in, a host title, a clock sync, a lock-light frame, Caps | the underlying state and its RAM copy update, and the dashboard's damage is marked; the owner and session are unchanged. (P3 also supersedes its connection operation.) |
  | OPEN | a wake | not expected: `DSB_MENU` blocks deep sleep. A dev counter records it; if it happens, the session closes (actions C) when the wake hold releases |
  | DEBUG or ANIM, NONE | a wake | the owner is kept; see "the wake" below |
  | DASH, NONE, restore `DONE` | an animation start | the header validated first (an empty slot is a no-op), then ANIM |
  | MENU, DEBUG, a session, or a restore not `DONE` | an animation start | refused |
  | ANIM | an animation stop | always allowed: quiesce, DASH, and a restore started from band 1, which subsumes any `WAITING` request |
  | ANIM | the opener | refused, but captured with its release |
  | not DASH, or a session | the startup callback | `WAITING` |
  | any | a blit lost | as "Loss" above |

- **The actions:**
  - **P, pending:** record the request and its capture; suppress the
    overlays and clear any showing one (`param_status_on`,
    `param_force_kc`); set `DSB_MENU`. No visibility override, no restore
    superseded, no clear: the wake's battery and clock work goes on.
  - **O, open:** a running restore superseded (`WAITING`); `dbg_text`,
    `dbg_shown` and the damage state reset; the overlays suppressed and
    cleared as in P; the param repeat cancelled; the visibility override
    on; `DSB_MENU` set; the opening clear started.
  - **C, close:** an open edit cancelled; the visibility override off;
    `DSB_MENU` cleared; the owner DASH; a restore started; the hold timers
    and gesture state cleared, the capture bits kept (C2). The overlays
    re-prime at the restore's text stage, which calls
    `conn_status_update()` first.
- **The wake:**
  - `display_wake_held()` (new, public) returns the hold.
    `display_wake_release()` posts a notice, which `menu_task()` consumes.
  - `display_wake_repainted()` expects dashboard work only while the owner
    is DASH. Under DEBUG, MENU or ANIM it waits only for the bus to be idle:
    the dashboard is `WAITING`, and the restore at the owner's exit repaints
    the battery and the clock. Today it waits for a `batt_dirty` that a
    gated painter never clears, until `RC_HOLD_MAX_MS`.
- **Predicates:** distinct and named, never one generic "owned":

  | Predicate | True when | Used by |
  |---|---|---|
  | `dash_paints()` | DASH, the session NONE or PENDING, the restore `DONE`; plus today's splash, bus and pass-deferral gates | housekeeping's dashboard owners, the logos, the wake paint |
  | `restoring()` | `CLEAR`, `STAGES` or `RESIDUAL` | the pump's restore dispatch |
  | `display_band_busy()` | the owner isn't DASH, or a session (PENDING included), or `restoring()` | as today's callers |
  | `panel_lit_for_owner()` | DEBUG, or the session OPEN (not ANIM, not PENDING) | Lights out's exception (`power.c:246`) |
  | `anim_admissible()` | DASH, the session NONE, the restore `DONE` | starting only |

  `ANIM_TOG` (`ak820pro.c:374`) becomes: an active animation stops;
  otherwise it starts only if `anim_admissible()`.
- **Migration checklist.** Each existing use is converted and ticked off in
  S0's code review:
  - `display.c:136-148`: the flags and `display_set_paused()`;
  - `display.c:1170-1220`: the debug query and the toggle;
  - `display.c:1395,1433`: the restore cursor's read, advance and end;
  - `display.c:1447`: the deferred redraw (the startup callback);
  - `display.c:2601`: band busy;
  - `display.c:2910`: `display_bus_idle()`;
  - `display.c:2963,2974,2982`: the self-heal and the pump's branches,
    dispatched by owner, each with its own recovery;
  - `display.c:2990,2992,2997`: the restore dispatch, dev and non-dev;
  - `display.c:3316,3330`: the wake paint and its completion;
  - `display.c:3362-3377`: housekeeping, where the debug composition stays
    separate;
  - `display.c:3431-3455`: the five logo painters, which update RAM, mark
    themselves stale, and repaint when `dash_paints()` allows, or in the
    restore's `RESIDUAL`;
  - `ak820pro.c:374` and `power.c:246`;
  - `lcd_bus.c:21`: `display_set_paused()`'s declaration;
  - `lcd_bus.c:1042,1060,1085,1097,1099,1102,1112,1117`: every `anim_on`
    declaration, read and write, and the pause calls;
  - `hid_protocol.c:1029`: op 1.

  These callers keep their meaning, though their spelling may not change:
  `ak820pro.c:431,610`, `lcd_bus.c:405,421`, `sleep.c:246,812` and
  `rtc/rtc.c:1832`.
- **Overlays:** every `display_set_param_status()` post is dropped while the
  session is PENDING or OPEN, Diagnostics included, and an overlay already
  showing is cleared at P or O. Alerts and other state keep updating. At
  close, `param_status_task` re-primes its polling baseline.

### C2. Input

- **The hook:** `pre_process_record_kb(keycode, record)` in `ak820pro.c`.
  - Uncaptured events return `pre_process_record_user(keycode, record)`, so
    the default chain is kept.
  - Captured events return false.
- **What has already run when it's called** (at `b9555ff3e6`):
  1. `action_exec()` has cleared the weak mods on a press, and run any
     one-shot timeout due.
  2. `get_record_keycode(record, true)` has done the layer and VIA lookup,
     caching the source layer on a press.
  3. `pre_process_record_modules()` has run.

  **What a false return skips:** combos (after the hook), tapping, and all
  of `process_record`, `process_record_kb` included. A tick event can still
  advance a tap-hold already pending on another key. So a captured knob
  event never interrupts a pending tap-hold or combo elsewhere.
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
  - A release whose press wasn't captured is forwarded, even if a session
    opened in between.
  - **Release routing runs first,** before any check of the session, the
    owner or `MENU_ENABLE`. Capture is never inferred again from the new
    state.
  - The gesture state is separate from the bits: a close clears the hold
    timer and any gesture, so no Back fires after it, while the bit still
    consumes the release.
- **The input is coalesced, not queued.** A physical event can't be told
  "busy", so capture never depends on room:
  - **Turns:** one `int8_t` net count, saturating at ±64, with a saturating
    `uint8_t` overflow counter.
  - **Click, Back, close:** latched flags, each acted on once.
  - **The opening and closing presses aren't clicks.** Their releases are
    consumed without one.
- **What capture costs, by design:**
  - Weak mods were already cleared on the press, as for any key.
  - Captured events skip `process_record_kb`'s later effects: they add no
    health key count and send no USB remote wake. Combos and tapping never
    see them.
- **The opener while closed:** a press of (0,14) with `Fn` active.
  - It's captured, and the session goes to OPEN or PENDING by C1's table.
  - Under ANIM it's refused, but still captured, with its release.
- **While the session is open:**
  - **Detents:** captured; a press half adds a turn.
  - **The knob press:** captured.
    - With `Fn` active, it latches a close.
    - Otherwise it starts the hold timer. A release before 600 ms latches a
      click. At 600 ms the menu task latches Back.
    - A release at or after 600 ms that the task hasn't caught latches
      Back, exactly once.
- **Opening also cancels the param repeat.** `modified_consumer_task()`
  keeps running.
- **S0's scope:** the hook is built with `MENU_ENABLE` off, so normal
  firmware never swallows `Fn` plus the knob into an invisible menu before
  P1.
  - **The armed test mode (dev builds only):** op 27 sub 6 arms the real
    hook's opener at run time. It's off at boot, never persisted, and
    disarming doesn't drop a release still owed.
  - **What the opener opens in S0:** the fixture.
  - Op 27 injects turns and clicks into the same coalesced input.
- **Where it runs:** the menu task, `menu_task()`, runs each pass in
  `housekeeping_task_kb`, **before** `display_blit_pump()`. It handles the
  queued events, the timers and the hold, independent of the gated display
  housekeeping. The pump stays at its own site (the warning at
  `display.c:3370-3376`).

### C3. Damage

- **Fixed geometry.** Each screen kind (a layout: list, text page, range
  editor, hue editor, About page two, More info, and S0's fixture) has a
  `const` table of slots, each with a fixed rectangle. Nothing moves within
  a layout, so no old rectangle has to be remembered:
  - a list's or text page's slots: the title, the separator, the eight
    rows and the scrollbar. A row's rectangle is x 3-124, so all 20 cells
    and the inverted style's pad pixel at x 3. A short value after a long
    one paints blank cells over it.
  - the hue editor's strip and marker are one slot, the **envelope**,
    x 1-126 and y 20-40: the strip plus the marker's line and triangle at
    either end. Moving the marker repaints the envelope in chunks.
- **A layout change clears.** Opening, or moving to a different screen
  kind, starts a banded clear of the panel, and every slot of the new
  layout becomes `INVALID`.
  - **A clear is never superseded:** navigation during it changes only the
    target, and the clear finishes its bands.
  - Within one layout (a list to another list, a page to the next), slots
    repaint in place and there is no clear.
- **The slot:** `uint16_t signature; uint8_t state; uint8_t gen;`, 4 B
  with a `_Static_assert`; at most 24 slots, 96 B. The states are `EMPTY`,
  `INVALID`, `PARTIAL` and `COMMITTED`. The target is generated on demand by
  the composer; only the shown state is stored.
- **The rules:**
  1. Before a slot's first write, it becomes `PARTIAL` with the target's
     generation.
  2. A `PARTIAL` slot whose target is unchanged (same generation and
     signature) resumes from its chunk cursor. A changed target restarts
     it from chunk 0.
  3. It becomes `COMMITTED`, with the new signature, only after its last
     chunk, with `!lcd_blit_busy()` and no loss. A slot that isn't
     `COMMITTED` is repainted even if the new target's signature equals its
     last committed one. That's the A, then partial B, then A case.
  4. A loss under this owner makes every slot `INVALID` (C1).
  5. The separator and the scrollbar are slots.
- **One chunk cursor:** the slot and the chunk in progress.
- **Navigation regenerates the target,** so pending work is superseded by
  rule 2.
- **Each pass, the painter does one bounded operation:**
  - a half row of text;
  - one chunk of a shape, the hue envelope or the QR code;
  - one band of a layout change's clear;
  - one big-face glyph's arm or completion.
- **Text:** the rows' desired text is `dbg_text`, and their shown text is
  `dbg_shown`. A row's signature covers the text and its style (normal,
  selected, inverted or lit), so a selection change on the same text is
  damage.

### C4. The scratch buffer

- **One static buffer,** `lcd_scratch[512]` in `lcd_bus.c`, replaces
  `tx_pixels`' and `lcd_fill_rect`'s.
- **Today's users, all on the main thread** (codex checked them):
  - `tx_pixels()` through `lcd_blit_ram()`: the AM/PM tile
    (`display.c:601`), the battery slot's tiles (1763), the transport icons
    (2510);
  - `lcd_fill_rect()`: the battery's outline and nub (1927-1933), its fill
    (2010), the padlocks (2067-2071).

  The DMA completion callback (`lcd_bus.c:699`) and the backlight ISR paint
  nothing.
- **Its rules:**
  - acquired, filled and released only on the main thread, never
    reentrantly, and never from a callback or an ISR. SPI's FIFO ISR does
    **read** it during `spiSend()` (`hal_spi_v2_lld.c:96-125`), so the
    caller holds it until `spiSend()` completes;
  - interrupts stay enabled;
  - no pointer to it is kept.
  A debug build asserts acquire and release.
- **The panel-order stream:** `lcd_stream_begin(x, y, w, h)`,
  `lcd_stream_bytes(const uint8_t *panel_order, n)` and `lcd_stream_end()`.
  - **`begin`** validates the rectangle, quiesces the bus, acquires the
    scratch, then sets the inclusive LCD window. `bus_quiesce()` stays out
    of `lcd_window()`: the DMA arm path calls that after marking its own
    transfer busy (`lcd_bus.c:686-688`).
  - **`bytes`:** `n` is in bytes, sent synchronously; the stream knows the
    total it expects (`w * h * 2`).
  - **`end`** completes the sends, deasserts CS and releases the scratch.
  - **Every chunk opens and ends its stream within one pass.** No stream
    stays open across passes, so no other painter can move the window
    under it.
  - Generated pixels (the mono glyphs, the strip, the QR code, a clear)
    are written into the scratch already in panel byte order, through
    `lcd_bus.c`'s own primitives, and sent through the stream.
  - They're never passed back through `tx_pixels()`, which byte-swaps into
    the same scratch.
- **`lcd_blit_mono(bits, cols, x, y, fg, bg)`:**
  1. It quiesces the bus *before* opening its window.
  2. It expands the bits row by row, in raster order, into the scratch.
  3. It streams the result.

### C5. RAM

- **The ceiling:** the menu and every later stage together use at most
  400 B of new static RAM (`.data` and `.bss`), and **the dev build's heap
  gap stays at least 128 B**.
- **`build.sh`'s check,** for every flavour, before the artifact is
  published:
  - the gap is `__heap_end__ - __heap_base__`, read from the `nm_out` it
    already collects. The linker gives the whole remaining region to a
    NOLOAD `.heap` (`rules_memory.ld:309-316`), so `size`'s totals can't be
    subtracted from 32 KB.
  - A missing symbol fails the build. The fixed stacks and the retained
    `.ram7` aren't deducted a second time.
  - Below 128 B, the build fails.
- **Measured on `via-dev-ce229f87c6`** (codex): `.mstack` 1,024 B,
  `.pstack` 2,048, `.data` 2,784, `.bss` 26,864, `.heap` **32**, `.ram7`
  16. The shared scratch gives about 544 B, so the 400 B ceiling leaves
  about 144: the floor holds, with little to spare at the ceiling.
- **The budget,** from `sizeof` estimates, checked against each linked
  build:

  | Item | Bytes |
  |---|---|
  | owner, session, restore gen, phase, damaged, wake notice | 8 |
  | capture bits, gesture, hold timer | 8 |
  | nav stack (3 levels), cursor, top, timers | 24 |
  | edit transaction (an RGB config snapshot, a level, flags) | 16 |
  | region slots (24 x 4) | 96 |
  | chunk cursor, clear cursor | 8 |
  | coalesced input (turns, overflow, latches) | 4 |
  | op 27 state (sequences, armed, a hold's release time) | 12 |
  | P2: `flash_stats` (3 counters, wider masks) | 12 |
  | P3: Bluetooth operation state | 24 |
  | **total** | **~212** |

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
  - **The shared underglow keys** (`UG_*`, the `QK_UNDERGLOW_*` range):
    observed in `process_record_kb` **on press**. `process_underglow()`
    runs them into the RGB-matrix setters on press, because
    `RGB_MATRIX_DISABLE_SHARED_KEYCODES` isn't defined
    (`quantum/process_keycode/process_underglow.c:17`).
  - **The board's `RGBM_*` wrappers, and `param_repeat_step()` before
    each step.**
  - **`SCR_UP` and `SCR_DN`, and dev ops 4 and 5:** these cancel a Screen
    edit.
- **Not writers:** the power ladder's caps and driver scale, the battery's
  RGB cut, deep sleep, `consumer_mod.c` and the lock-light channel change the
  output, not the RGB config. They cancel nothing, and no snapshot restores
  their caps.
- **While an RGB edit is open,** `rgb_matrix_eeprom_flush_allowed()` also
  returns false. QMK's dirty flags are never cleared by hand.
- **The RGB adapter:**
  - Preview, Save and Cancel all set values with RGB enabled inside one call
    (`_noeeprom`, then the saving variant to save), restoring the enabled
    state last.
  - **Lights saves with an explicit `rgb_matrix_enable()` or
    `rgb_matrix_disable()`, never a toggle.**

### C7. Visibility and sleep

- **Built in S0,** with `DSB_MENU`: op 27 and the armed mode make real
  sessions there.
- **`menu_visibility` is a `volatile bool`,** true while the session is
  OPEN, Diagnostics included. PENDING blocks sleep but doesn't light the
  panel. Main code publishes it after the entry's setup; the ISR only reads
  it.
- **One effective-level function,** shared by the PWM ISR,
  `display_backlight_effective()` and `display_set_power()`'s GPIO write.
  It's a pure calculation over local copies of the volatile scalars it
  reads (requested power, level, cap, wake hold, `menu_visibility`). It
  never reads menu structs, timers or transition state, and never changes
  the PWM's phase.
  1. **With the override on:** the panel counts as powered, without changing
     `display_powered`; the cap is lifted; the level is
     `max(requested, 1)`.
  2. **The wake hold is applied last.**

  The requested power and level are never changed by the override.
- **`DSB_MENU = 0x4000`** is set while the session isn't NONE, PENDING
  included. "menu" is appended to `ak820battery.py`'s `SLEEP_DSB` at index
  14. That's the only decoder of the blocker word: `ak820health.py` and the
  daemon don't decode it.
- **Timeouts are 32-bit elapsed times.** Only knob input restarts them:
  hint repaints, host traffic and typing don't. Typing still counts for the
  ladder.

### C8. Screens and coordinates

From the mockup, which stays authoritative:

| Screen kind | Layout |
|---|---|
| list, text page | title row y 0-13; separator y 14 (x 4-123); rows y 15 + 14k, k = 0..7, each row's slot x 3-124 (the inverted style's pad pixel at x 3); scrollbar x 125, y 15-126 |
| range editor | title, separator; big value y 22 (10 cells centred, x 14); bar outline x 13-114, y 51-60; hints y 72, 86, 100 |
| hue editor | title, separator; strip x 4-123, y 22-35; marker line y 20-37 and triangle y 38-40, reaching x 126 at the high end; the envelope slot x 1-126, y 20-40; big value y 44; hints y 72, 86, 100 |
| About page two | the bunny's slices at x 4, rows k..k+2; the credits at x 36, 14 columns |
| More info | the QR code: 29 modules x 3 px plus a 2-module border, 99x99, at x 14, y 22 (`16 + floor((112 - 99) / 2)`, as the mockup computes it) |

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
| Power | the enum | none | `power_set_mode()`, promoted (declaration and body); `build.sh`'s forbidden-symbol list for daily and fpb (lines 146-149) loses `power_set_mode` only | none |
| Clock | displayed 24h / 12h / Date / Off, mapped to the enum's 24H / 12H / OFF / DATE | none | `display_set_clock_mode` + `kb_eeconfig_set_clock_mode` | none |
| Lock lights, Charging light | levels 0-9 | `indicator_set_brightness`, new `indicator_set_charging_brightness` | `kb_eeconfig` bytes 7 and 8 | restore |
| Battery | Percent or Hours | none | `kb_eeconfig` byte 9 | none |

**The indicators** get getters and range validation, and their saved levels
are applied at init. Their stored fields keep 0 as unset, distinct from a
saved Off (`level + 1`).

**The settings block and the write attribution** (P2):
- **The new bytes:** `kb_eeconfig` grows from 7 to 10 bytes at version 5:
  byte 7 is `ind_locks_p1`, 8 is `ind_charging_p1`, 9 is `batt_view`.
  The battery view's encoding is frozen: 0 unset, 1 Percent, 2 Hours; unset
  or invalid means Percent.
- **`flash_stats.c`:**
  - `kb_byte_field[]` grows, and every mask carrier is widened to 16 bits:
    `pending_mask`, the locals `mask` and `m`.
  - Its `_Static_assert` (`flash_stats.c:32`) compares the **element
    count**, not `sizeof`, which a `uint16_t` array would double.
  - **Page 1 is frozen** at its six counters.
  - **A new page 3** carries three u16 counters at offsets 0, 2 and 4; the
    rest of the payload is zero, reserved. Old firmware answers it
    `RTC_UNHANDLED`, which the host shows as "-".
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

- **The request,** 32 bytes as every raw-HID report:
  `[0] 0x07, [1] 0x13, [2] 0x76, [3] 27, [4] sub, [5..] args`, the rest zero.
- **The reply** echoes bytes 1-4. Byte 0 is the status:

  | Status | Meaning |
  |---|---|
  | 0 | accepted (or, for a read, done) |
  | 1 | busy: a hold is still outstanding, or a latch is already set |
  | 2 | a bad argument: out of range, or a sub this state can't take |
  | `RTC_UNHANDLED` | dev hooks off, an unknown sub, or a short report |

  An accepted input gets a sequence number, `accept_seq` (u8, wrapping),
  returned at reply byte 5. `menu_task()` sets `done_seq` when it has
  acted on it. A test polls sub 5 until `done_seq` reaches its number, so
  "accepted" is never taken for "done".
- **The subs:**

  | Sub | Args | Effect |
  |---|---|---|
  | 0 | [5] pattern, [6] n | the fixture's paint (S0 below): pattern 0 is A, 1 is B, 2 is B stopped after n bounded operations, 3 is a layout change. Only while the fixture is open; otherwise status 2. S1 adds its mono patterns from 16 up |
  | 1 | [5] int8 count, within ±16 | turns, added to the coalesced count |
  | 2 | | a click |
  | 3 | [5..6] u16 LE hold ms, 0 meaning 650, within 50-5000 | a hold: a press now and a release `menu_task()` schedules, never `wait_ms`. Busy while one is outstanding |
  | 4 | | `Fn` plus a click: the opener or the closer |
  | 5 | | read the state (below) |
  | 6 | [5] 0 or 1 | disarm or arm the physical test mode (C2) |
  | 7 | | request a dashboard restore, as the startup callback does |
  | 8 | | mark a blit lost, as an exhausted recovery does, for the loss rules |

- **Sub 5's reply,** from byte 5:

  | Byte | Field |
  |---|---|
  | 5, 6 | `accept_seq`, `done_seq` |
  | 7, 8 | owner, session (C1's enum values, in declaration order) |
  | 9, 10, 11 | `restore_gen`, `restore_phase`, `restore_damaged` |
  | 12, 13, 14 | screen id, cursor, an edit flag |
  | 15 | the armed mode |
  | 16, 17 | pending turns (int8), the overflow count |
  | 18 | slots not `COMMITTED` |
  | 19, 20 | `lcd_blit_busy()`, losses seen (u8, saturating) |
  | 21 | the capture bits |
  | 22, 23 | the last paint operation's time, u16 LE in µs (S1) |
  | 24 | the pairing phase (P3) |
  | 25-31 | zero, reserved |

- **The daily and fpb builds** don't compile HC_DEVHOOK at all. `build.sh`
  already enforces that.

## Stages

Each stage gets a codex review of its code before the flash, with every
finding dispositioned. Each goes onto gremlin's board before JD's.

1. **S0, the foundations** (with `MENU_ENABLE` off):
   - C1's owner, session and restore, with the migration checklist done;
   - C2's capture, coalesced input and armed test mode; C3's damage model;
     C4's scratch buffer and stream;
   - C5's budget and the `build.sh` check;
   - C7's visibility override and `DSB_MENU`, since S0 makes real sessions;
   - the logo fix;
   - **the fixture:** the MENU owner's screen in S0, drawn with today's
     primitives (fills and flash-atlas glyphs), with deterministic A and B
     patterns over fixed slots, so ownership, damage and the restore are
     visible on the panel without P1's tree.

   **Proof:**
   - **host tests** (gcc), with a fake framebuffer and success or loss
     completions: the transition table, the restore's phases and loss, the
     damage rules (A, then partial B, then A; a layout change during a
     clear), the capture and release routing;
   - **op 27 on the board:** the transition table's rows, the animation
     refused and stopped, the startup restore (sub 7), an interrupted one, a
     loss (sub 8), a stale logo repaired, and `display_restored(gen)`'s
     timing read from sub 5, not a photo;
   - **the fixture's pixels** after A, partial B and A, checked by photo;
   - **the physical cases, armed (JD's hands):** the knob's presses and
     releases, `Fn` released first, a timeout while held, a hold across a
     close, and a pending tap-hold on another key. The one-shot and the
     MT/LT cases remap the knob in VIA for the test and put it back;
   - the linked RAM of the dev and daily builds, by the new check;
   - `Fn`+`D` and the animation behaving as before;
   - **timing as a measurement under a named workload,** not a universal
     bound: op 27's scripted 500-input session plus five minutes of the
     dashboard with a track playing, with the ge10 and ge25 counts and
     HC_ACCT's ring recorded. ge25 is expected to stay 0. Real spins and the
     encoder drain's backlog are S1's.
2. **S1, the mono paint, measured:**
   - `lcd_blit_mono` and the generated font, with op 27 sub 0's mono
     patterns (16 up) painting on the fixture, under its panel ownership,
     never a second painter over the live dashboard.
   - **The encoder drain:** real spins and a backlog measured; the
     supported workload is named, and a bounded drain (a change to
     `quantum/encoder.c`) decided on those numbers.
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
    a hold across a timeout, a second opener while pending, a forwarded
    press whose release comes after a session opened, and a turn backlog
    past saturation.
  - **The restore:** each phase, a loss in each, a startup request under
    another owner, an animation stop subsuming a waiting request.
  - **The damage model:**
    - A, then partial B, then A;
    - a long value then a short one, the row's blank cells painting over it;
    - the marker moving, the envelope repainted;
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
  - **QMK's processing around a captured knob:** a pending tap-hold on
    another key, and the knob remapped to a one-shot, an MT and an LT for
    the test, then put back.
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
