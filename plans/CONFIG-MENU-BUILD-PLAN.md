# The configuration menu: how to build it (revision 15, 2026-10-24)

**Resume from [`WARREN-STATUS.md`](WARREN-STATUS.md)** (the thread: what is on the board, the next step, the rules).

Status: **S0 built and accepted on the keyboard on gremlin**: A1-A13 pass,
with recorded exceptions (`GREMLIN-RESULTS.md` §10). A7's animation case
wasn't run, and A9 can't tell a refusal from an empty slot, since gremlin's
animation slot is empty. A11's first runs missed the media gate on a slow
SMTC. **Revision 12 was cleared for S1** (codex, 10-24: "ready for S1 to be
built from"); revisions 13 to 15 amend rules from S1's gate runs. Owned by Warren
(gremlin's session) from 10-23.
- **Revision 15** (10-24, from the gate's fourth run, `GREMLIN-RESULTS.md`
  §15: Fn+D entry passed 1,000 ms once, at ~135 glyphs, one per pass):
  **the DMA arm's window is polled too.** `spiSN32FlashDmaPrepare()` runs
  with the panel's CS high (it rewrites SPI0's CTRL0 and toggles SPIEN).
  `lcd_blit_flash()` then asserts CS and sends the window with
  `lcd_window_polled()`, and the pixels follow with no further
  reconfiguration. The window goes before `blit_done` falls, so the entry
  check passes; the arm's counters and saved parameters advance only after
  it succeeds. A window that gives up hands SPID1's vector back
  (`dma_unprepare`, as Abort would after Fire) and `lcd_blit_flash()`
  returns false; the clear and the retry use that.
- **Revision 14** (10-24, from S1's second gate run, `GREMLIN-RESULTS.md`
  §13): **a polled bulk send's window is polled too** (C4). Through `tx8()`
  each of its 11 bytes was a whole `spiSend()`, ~0.2 ms of wall time at
  this ISR load, ~1.8 ms a window: a third of a 512 B piece's 5.4 ms, and
  most of the battery outline's 9.6 ms. The menu's passes run 10-14 ms and
  the gate's longest was 17 ms (four over 15); whether this is enough is
  for the next C10 run to show. The DMA arm keeps its `spiSend()` window:
  `lcd_blit_flash()` has cleared `blit_done` for its own transfer by then,
  so a polled send's entry check would refuse (codex corrected the first
  reason given here).
- **Revision 13** (10-24, from S1's first gate run on the keyboard on
  gremlin, `GREMLIN-RESULTS.md` §12): **a `PARTIAL` slot resumes while its
  own signature is unchanged,** whatever the generation did (C3 rule 2, C4).
  Under revision 8's "same generation and signature", every detent of a spin
  restarted every partial slot. With ops of several pieces (a half row is 4,
  ~40 ms), nothing committed during a 10 s burst of a detent every 50 ms:
  C10's progress rule failed. The signature is the slot's whole target, so
  the pieces sent stay right; a layout change and a loss still invalidate
  every slot. Host test: a detent every 4 passes commits 8 slots in 100
  passes, against 0 under the old rule.
- **Revision 12** folds in codex's verification of revision 11
  ([`review-codex-config-menu-build-plan-rev11-2026-10-24.md`](review-codex-config-menu-build-plan-rev11-2026-10-24.md)),
  its one remaining must-fix: a debug composition is tagged with the
  second it shows, and a second that has elapsed but isn't composed yet
  counts as pending.
- **Revision 11** folds in codex's verification of revision 10
  ([`review-codex-config-menu-build-plan-rev10-2026-10-24.md`](review-codex-config-menu-build-plan-rev10-2026-10-24.md)):
  - the interval's reset names the right bytes, and validation counts come
    from health page 2;
  - the debug page's completion takes the generation before the cause, and
    a loss or page reset makes a new generation;
  - a boot-cleared session token and a health-reset generation replace
    `boot_id`.
- **Revision 10** folds in codex's verification of revision 9
  ([`review-codex-config-menu-build-plan-rev9-2026-10-24.md`](review-codex-config-menu-build-plan-rev9-2026-10-24.md)),
  rewriting C10:
  - the timing is measured over an armed interval, under every owner;
  - the debug page's completion is bound to a composition generation;
  - the counters are validated per field, with sampling brackets and a
    boot id;
  - transitions have their own rule, measured until they complete;
  - a spin's progress counts committed slots, not settled targets.
- **Revision 9** folds in codex's verification of revision 8
  ([`review-codex-config-menu-build-plan-rev8-2026-10-24.md`](review-codex-config-menu-build-plan-rev8-2026-10-24.md)):
  - the op and stop lifecycle: an op is counted and a reached stop latched
    the moment the op ends, before navigation can discard either. That
    closes a real ordering hole in S0's scheduler;
  - "op" and "piece" kept apart throughout;
  - the timing fields and their retained maxima (sub 10);
  - a completion flag for the debug pages, and target counters for spins;
  - every deadline and window of the LED gate given a number (C10).

**The S0 merge waits for the drain (agreed with Buzz's session, 10-24).**
The keyboard on Buzz stays on `b9555ff3e6`, with no flash, until its RGB cut
(about 10-31 to 11-02). Then:
1. a daily build of S0 runs on the keyboard on gremlin before `deps.lock`
   moves. Probably S0 plus the LED fix, if revision 8 has cleared it, so
   one hands-on flash covers both: a daily build has no HC_BOOTLOADER, so
   the flash after it needs JD's Fn+Esc;
2. the keyboard on Buzz takes S0 and the LED fix in one flash, with a soak;
3. then `gremlin/config-menu` (a fast-forward from `b9555ff3e6`) merges into
   `ak820pro-jdlien`, `deps.lock` moves, and `warren/config-menu` merges
   into main.

Until then, S1 is built on branches off `gremlin/config-menu` and runs on
the keyboard on gremlin only.
- **Revision 8** folds in codex's review of revision 7
  ([`review-codex-config-menu-build-plan-rev7-2026-10-24.md`](review-codex-config-menu-build-plan-rev7-2026-10-24.md)):
  - `MENU_PASS_BYTES` splits a logical paint op into resumable pieces under
    it, so C9's 27 ops, the stop and the op count stay logical (C4);
  - the budget covers the menu's CPU-fed pixels; DMA clears keep their own
    measured bound;
  - 15 ms is a measured whole-pass target under a named workload, and a
    bounded encoder drain is required if spins break it;
  - the LED gate is executable: a matched-baseline ratio, transition
    windows, and two completion rules;
  - both polling hardening items are taken, with a polling-failure fault
    hook;
  - "Open" 5 is settled (documented, not fixed), and "Open" 3, the menu
    keycode, gets its rule table for P1.
- **Revision 7** folds in what S0's board cases found (10-23/24), for S1:
  - **Colour paints held off the RGB row ISR** (-18% of its refreshes, a
    visible flicker per knob turn). The fix, bulk SPI0 sends polled with the
    FIFO interrupt masked, is prototyped (`gremlin/fill-poll` `f2b107be`,
    -1.3%, JD: "no flicker"). It becomes C4's send rule and S1's first step.
  - **A per-pass byte bound** on every paint, since a polled send runs
    longer in wall time (the worst pass went from 20 to 23 ms).
  - **A row-ISR gate** beside the stall counters.
  - **The cursor's cost is its area, not its style:** the mono blit paints
    every pixel of a cell either way.
  - **C2's Fn judged by `layer_state`** misses inside an undecided tap-hold's
    tapping term; S1 decides.
  - **A menu keycode,** which JD wants, goes to P1.
- **Revision 2** folded in codex's first review
  ([`review-codex-config-menu-build-plan-2026-10-23.md`](review-codex-config-menu-build-plan-2026-10-23.md)).
- **Revision 3** folded in its verification of revision 2
  ([`review-codex-config-menu-build-plan-verify-2026-10-23.md`](review-codex-config-menu-build-plan-verify-2026-10-23.md)).
  It added **"The implementation contract"**, the decisions S0 is built from,
  so the implementer doesn't have to discover them while coding.
- **Revision 6** folds in the verification of revision 5
  ([`review-codex-config-menu-build-plan-verify4-2026-10-23.md`](review-codex-config-menu-build-plan-verify4-2026-10-23.md)).
  **Codex's verification of revision 6 found no must-fix: S0 is ready to
  build**
  ([`review-codex-config-menu-build-plan-verify5-2026-10-23.md`](review-codex-config-menu-build-plan-verify5-2026-10-23.md));
  its three clarifications are folded in here (the workload's click count,
  `pixels_done` against the current target, the unused pattern argument).
  Revision 6 changed:
  - the Camera page's loss recovery invalidates only the page showing, and
    the debug pump's dispatch is exclusive;
  - a loss after `DONE` is remembered at once, and only the repair waits
    out the cooldown;
  - every accepted op 27 mutation has a terminal outcome, deferred and
    discarded ones included;
  - the fixture's partial stop is observable, and the S0 script is a fixed
    sequence.
- **Revision 5** folded in the verification of revision 4
  ([`review-codex-config-menu-build-plan-verify3-2026-10-23.md`](review-codex-config-menu-build-plan-verify3-2026-10-23.md)):
  - the restore's `RESIDUAL` gets its own scheduler and a full `DONE`
    invariant, and leaving DASH invalidates the dashboard;
  - one consumer of a loss, with a handler per owner, the debug pages and
    the animation included;
  - a clear completes only when every band succeeded;
  - the coalesced input's order and precedence;
  - op 27 keeps HC_DEVHOOK's byte 0, runs one mutation at a time, and
    reports completion per kind;
  - S0's fixture (C9), the sticky invariant check, a `devfault` build for a
    real DMA timeout, and the S0 workload script.
- **Revision 4** folded in the verification of revision 3
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
    `restore_gen` (u16), `restore_phase` and `restore_damaged`.
- **The restore's phases:**

  | Phase | Meaning |
  |---|---|
  | `SPLASH` | boot, until the startup callback fires |
  | `WAITING` | the dashboard is known invalid, and an owner other than DASH holds the panel; nothing runs |
  | `CLEAR` | the banded clear (today's stages 1 to `DBG_CLEAR_BANDS`) |
  | `STAGES` | the components (today's stages after the bands, the lock band one component a pass) |
  | `RESIDUAL` | everything the stages left: the queues, the battery's dirty parts and the stale logos, run by the restore's own scheduler (below) |
  | `DONE` | the visible dashboard is complete |

  - **A restore is requested** by the startup callback, a close, a
    standalone owner's exit (the Camera page's step back, an animation's
    stop) and the self-heal. If the owner is DASH (the session NONE or
    PENDING), it **starts**; otherwise the phase becomes `WAITING`, and the
    owner's exit starts it.
  - **Leaving DASH invalidates the dashboard.** Every handoff from DASH to
    DEBUG, MENU or ANIM sets the phase to `WAITING`, from `DONE` too.
    PENDING keeps the owner DASH, so a restore during PENDING runs, and is
    superseded only when PENDING becomes OPEN. Cancelling PENDING leaves
    the dashboard's work as it is: nothing was made to wait.
  - **Starting** always means `restore_gen++`, `CLEAR` from band 1, the
    queues discarded (as stage 1 does today) and `restore_damaged` false.
    No restore ever resumes an old cursor.
- **`RESIDUAL`'s scheduler,** one step a pass, in this order. It runs inside
  the pump's restore dispatch, which today returns before the ordinary
  queue drain (`display.c:2990-3000`), so the restore drains the queues
  itself:
  1. **A transfer in flight:** the bounded busy recovery (`pump_bus_busy`).
     Nothing else this pass.
  2. **A queued label or glyph** (`lq`, then `gq`): one, as the ordinary
     drain does.
  3. **A dirty battery part:** `draw_battery(false)`, one component; it's
     already incremental and doesn't need `dash_paints()`.
  4. **A stale logo:** the two logo regions, the OS logo (from `mac_mode`)
     and the connection row (from `connection_mode`), each one operation.
  5. **A damaged generation:** a new one starts when the 5 s cooldown
     allows; until then the phase stays `RESIDUAL`.
  6. **Otherwise `DONE`.**

  The ordinary dashboard and wake painters stay gated (`dash_paints()`)
  until `DONE`.
- **`DONE`'s invariant,** checked at the transition (C3's sticky check):
  both queues empty, `!lcd_blit_busy()`, no loss latched, `!batt_dirty`, no
  logo stale, `!restore_damaged`.
- **The wake's flags at `DONE`:** the restore painted the battery, so
  `wake_batt_due` is cleared. `wake_clock_due` is cleared only if
  `clock_gen_painted` has reached `wake_clock_target`; a correction that
  came later is left to `wake_paint_step()`, which runs again once
  `dash_paints()` holds. Today `draw_clock()` advances `clock_gen_painted`
  without clearing `wake_clock_due`, and battery work never clears
  `wake_batt_due`.
- **`display_restored(gen)`** is `panel_owner == DASH && gen ==
  restore_gen && restore_phase == DONE`. It describes the dashboard now on
  the panel. `restore_gen` is a u16: a token is meant for the restore it
  was read from, and isn't kept across 65,536 restores.
  The restore's own work never waits on it.
- **Loss,** a transfer given up for good:
  - **One consumer.** The pump calls `lcd_blit_lost_take()` once a pass, at
    its top, and hands the loss to the current owner's handler. Nothing
    else takes it.
  - **At an ownership change,** the bus is quiesced first (bounded), and a
    loss latched by then is consumed and dropped: every new owner starts
    with a full clear (O's clear, the restore's `CLEAR`, the debug page's
    clear band, an animation's whole frames), so nothing of the old
    owner's survives to repair.
  - **The handlers:**

    | Owner | On a loss |
    |---|---|
    | DASH, restore `DONE` | **the damage is recorded at once:** the phase goes back to `RESIDUAL` with `restore_damaged`, so `display_restored()` is false from that pass. The scheduler starts the new generation's `CLEAR` when the 5 s cooldown allows. Only the repair is rate-limited, never the remembering. (Today the cooldown check comes before `lcd_blit_lost_take()`, `display.c:2963`, which is how the loss stays latched; taking it every pass needs this instead) |
    | DASH, restoring | `restore_damaged`; the scheduler starts a new generation at `RESIDUAL`'s end |
    | MENU | every slot `INVALID` (C3); a clear in progress retries its band (C3) |
    | DEBUG | **only the page showing is invalidated:** on Health, `dbg_shown` filled so no cell matches and `dbg_dirty` all set; on Camera, `cam_shown` and `cam_dirty` the same, with Health's grid left blank and clean. Then the clear band restarts. The debug renderers keep their own shadows; they don't move into C3's slots. Their shown cells advance when a DMA starts, which is why a loss has to reset them |
    | ANIM | the animation stops (quiesce, DASH, a restore from band 1) |

  - **The debug pump's dispatch becomes exclusive:** `if (debug_big)
    return cam_pump_glyph();` in place of today's fall-through to the
    Health grid when Camera has nothing to paint (`display.c:840`).
    Otherwise Health's spaces would be painted over Camera. A migration
    item.
  - **The animation's busy recovery.** `anim_task()` returns while
    `!blit_done` (`lcd_bus.c:1116`), and the pump skips it, so a lost
    completion is never given up today. Under ANIM the pump runs the same
    bounded recovery: past the grace, `lcd_blit_wait()` gives up, and the
    loss stops the animation as above.
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
  | MENU, OPEN | Diagnostics > Health, `DBG_PAGE` or op 1 | an open edit cancelled; DEBUG (Health), the session staying OPEN, returning to Diagnostics; the buffers reset |
  | MENU, OPEN | Diagnostics > Camera | as above, but straight to the Camera page |
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
  | an owner other than DASH | the startup callback | `WAITING`. Under DASH (the session NONE or PENDING) it starts |
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
  | `display_band_busy()` | the owner isn't DASH, or a session (PENDING included), or `restoring()`. This replaces only its first test (`display.c:2601`): the pair hint, the alert and a live param overlay still count as busy | as today's callers |
  | `panel_lit_for_owner()` | DEBUG, or the session OPEN (not ANIM, not PENDING) | Lights out's exception (`power.c:246`) |
  | `anim_admissible()` | DASH, the session NONE, the restore `DONE` | starting only |

  `ANIM_TOG` (`ak820pro.c:374`) becomes: an active animation stops;
  otherwise it starts only if `anim_admissible()`.
- **Migration checklist.** Each existing use is converted and ticked off in
  S0's code review:
  - `display.c:136-148`: the flags and `display_set_paused()`;
  - `display.c:840`: the debug pump's dispatch, made exclusive (Loss);
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
  "busy", so capture never depends on room. The state is three bytes:
  - **`turns`:** an `int8_t` net count, saturating at ±64.
  - **`latch`:** one of none, click, Back or close.
  - **`dropped`:** a saturating `uint8_t` count of input thrown away.
- **Its order:**
  - Turns add to `turns` only while `latch` is none. **A latch freezes the
    turns before it:** turns that arrive after it, before `menu_task()`
    has acted, are dropped and counted.
  - **Precedence:** close replaces Back or click; Back replaces click. A
    lower one arriving after a higher one is dropped.
  - **`menu_task()`** checks close first, and then discards the turns.
    Otherwise it applies the frozen turns, then Back or the click, then
    clears both.
  - **Close discards all other input.** At close and at every handoff
    (PENDING to OPEN, MENU to DEBUG and back), `turns` and `latch` are
    cleared. Nothing carries into a new screen or session.
  - **The opening and closing presses aren't clicks.** Their releases are
    consumed without one.
- **Synthetic input (op 27) has its own identity.** It never sets or clears
  the physical capture bits.
  - A synthetic hold while the physical knob is down, captured or
    forwarded, is refused (busy).
  - A physical knob press during a synthetic hold cancels the synthetic one
    (no Back), and the physical press is handled as usual.
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
    disarming doesn't drop a release still owed. **Disarming while a
    session is PENDING or OPEN** cancels or closes it (actions C), and the
    capture bits still owed are kept.
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
  - **A clear completes only when every band succeeded.** Today's
    `lcd_clear_rect()` discards the result of waiting for its own DMA
    (`lcd_bus.c:207-211`), so a band whose transfer was given up would be
    skipped. Clears go through a new `lcd_clear_rect_ok()` that returns
    that result. An idle bus after an exhausted recovery isn't a clear.
    A failed band is retried on the next pass, with the cursor not
    advanced. This rule covers the menu's layout clear, the restore's
    `CLEAR` and the debug page's clear band alike.
  - Within one layout (a list to another list, a page to the next), slots
    repaint in place and there is no clear.
- **The slot:** `uint16_t signature; uint8_t state; uint8_t gen;`, 4 B
  with a `_Static_assert`; at most 24 slots, 96 B. The states are `EMPTY`,
  `INVALID`, `PARTIAL` and `COMMITTED`. The target is generated on demand by
  the composer; only the shown state is stored.
- **The rules:**
  1. Before a slot's first write, it becomes `PARTIAL` with the target's
     generation.
  2. A `PARTIAL` slot whose own signature is unchanged resumes from its
     chunk cursor, even across a retarget that moved other slots (revision
     13). A changed signature restarts it from chunk 0.
  3. It becomes `COMMITTED`, with the new signature, only after its last
     chunk, with `!lcd_blit_busy()` and no loss. A slot that isn't
     `COMMITTED` is repainted even if the new target's signature equals its
     last committed one. That's the A, then partial B, then A case.
  4. A loss under this owner makes every slot `INVALID` (C1).
  5. The separator and the scrollbar are slots.
  6. **A repaint covers the slot's whole footprint,** background included:
     an absent row paints black, an absent scrollbar paints its track
     black, and a row paints its pad pixel at x 3 in either colour.
     **One exception (10-25, the Clock's live examples):** a layout's
     optional `first_chunk(slot, was, now)` may start a `COMMITTED` slot's
     repaint at chunk c > 0, and only when the two signatures' targets agree
     on chunks 0 .. c-1, so those pixels are already the new target's. A
     `PARTIAL` or `INVALID` slot always starts at 0. Skipped chunks are no
     operations: C10's counts and stops see only the chunks sent.
- **One chunk cursor:** the slot and the chunk in progress. Only the slot
  it names may be `PARTIAL` and resume. When the cursor moves to another
  slot, a `PARTIAL` slot it leaves becomes `INVALID` and restarts from
  chunk 0 when it's next chosen.
- **The sticky check.** At every transition to `COMMITTED` (and the
  restore's `DONE`, C1), the code checks its invariant: the slot's last
  chunk sent, `!lcd_blit_busy()`, no loss latched. A violation sets a bit
  in a sticky `invariant_fail` mask, readable by op 27 sub 5 and cleared
  only at boot. A transient early `COMMITTED` or `DONE` that a later
  snapshot would hide is still caught.
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
    reentrantly, and never from a callback or an ISR. The bulk send reads
    it, so the caller holds it until the send returns;
  - interrupts stay enabled; only SPI0's own sources are masked during a
    bulk send (below). `IE = 0` masks all of them, DMA completion included,
    which is safe only because the bus is quiesced and serialized;
  - no pointer to it is kept.
  A debug build asserts acquire and release.
- **Bulk sends are polled (revision 7).** `spiSend()` takes SPI0's RX-FIFO
  interrupt every ~3 us (8 bytes at 24 MHz) at priority 3, beside the RGB
  row ISR, which re-arms at its end: every late start is a longer dark gap
  for every row. S0's fixture repaints cost the LEDs 18% of their row
  refreshes, and JD saw each knob turn flicker the keyboard (A10, A11).
  `spi0_poll_send()` feeds the FIFO from the main thread instead:
  - `SN_SPI0->IE` cleared for the send, at most 8 bytes outstanding;
  - RX drained and RXFIFOTHIC cleared (a literal write) before IE is set
    back, or the idle driver's handler would run its completion code;
  - a bounded spin counted in polling work, so time in the row ISR costs
    none of it;
  - one failure path for a stuck shift or BUSY: the FIFOs reset, a count,
    `PO_FAIL_SPI0_POLL` (0x20) on dev builds, `blit_lost` set so the owner
    repaints, and the operation stopped.

  `lcd_fill_rect`, `tx_pixels` and the stream use it, and since revision 14
  their window too (`lcd_window_polled`: each command byte and its
  parameters a polled send, DC changed only after one returns). Since
  revision 15 the DMA arm's window as well, between `Prepare()` and
  `blit_done` falling. The panel's init and MADCTL stay on `spiSend()`. A
  test build's HC_POLLFAULT takes a skip count, so a fault can land on each
  of a fill's five window sends or on its payload. Callers have quiesced the bus, so no
  DMA is in flight and none can start
  ([`review-codex-spi0-poll-2026-10-24.md`](review-codex-spi0-poll-2026-10-24.md)).
  Prototyped as `gremlin/fill-poll` `f2b107be`: the repaint cost fell from
  -18% to -1.3%.
- **A per-pass byte budget (revisions 7 and 8).** Polled, a send runs longer
  in wall time, because the row ISR now preempts it. The worst pass reached
  24 ms in A11's workload on the prototype (23 ms in the LED test before
  it); the fixture's ops send up to 2,048 bytes (an F2 tile) in one pass.
  - **What it covers:** `MENU_PASS_BYTES` is the menu's synchronous,
    CPU-fed pixel payload per pass: fills, the mono blit and the stream.
    It's the sum of every piece sent in the pass, not a size per piece.
  - **What it doesn't cover:** clears and glyphs stay on flash DMA (a
    128x16 band is 4,096 bytes, followed by a wait). Each gets its own
    measured wall-time bound in S1. If a band ever needs splitting, it gets
    a band sub-cursor: `clear_band` or `po_restore_advance()` moves only
    after every piece of the band succeeded, a failed piece is retried
    without skipping pixels, navigation still finishes a running
    layout-clear sweep, and `PO_CLEAR_BANDS`, `DBG_CLEAR_BANDS`, `MB_BANDS`
    and the probe's indexing stay consistent. The restore's and the
    dashboard's own RAM tiles and fills are audited against the whole-pass
    target too.
  - **Logical ops and their pieces.** C9's 27 logical ops and their stop
    positions stay as they are, so `FX_F1_OPS`, pattern 2's range and the
    reference frames don't change. A piece cursor sits under the slot's op
    cursor:
    - **each piece** is a whole-pixel RGB565 rectangle (rows, or explicit
      horizontal sub-rectangles, respecting a source's stride) that opens
      its window and stream, completes them, releases the scratch and CS,
      and then yields to the main loop;
    - **the slot stays `PARTIAL`** through all its pieces, with its
      signature describing the whole target, style included;
    - **a resume** happens while the slot's own signature is unchanged
      (revision 13; revision 8 also required the same generation, which
      starved a spin). A changed signature, an invalidation (a layout change,
      a loss) or an abandoned cursor discards the piece progress, and the
      slot restarts from its first piece. An op cut by a retarget and
      resumed is counted when it ends, but not timed (its latency's start
      was abandoned);
    - **an op counts once,** when it ends: its last piece returns, or its
      last DMA completes or is given up, or it fails. Pieces, busy retries
      and waiting passes don't count;
    - **the end's bookkeeping comes first** (revision 9). One helper counts
      the op and, in the same step, latches `stopped` if `stop_n` is reached
      with no transfer outstanding. It runs at the op's end, and again at
      the top of `new_target()` and of any loss invalidation, before either
      resets the op state. In S0 a synchronous op bumped `ops` but `stopped`
      latched only on the next `ms_step()`, and navigation in between ran
      `new_target()`, which cancelled the stop that had just been reached
      (`menu_slots.c:48-56,88-93,110-115`);
    - **a stop not yet reached** is superseded by a retarget (its sequence
      ends, `ms_stop_cancelled_take`). **A reached stop** survives
      navigation and losses, and holds a newly requested clear paused. It
      is released by the next sub 0 (`ms_stop_release`), and separately by
      a fresh opening or a return from another owner (`fresh`), which is a
      new screen;
    - **slot progress and clear progress are kept apart:** navigation keeps
      the PARTIAL slot's op and piece cursors while its signature is
      unchanged (revision 13), and discards them only when its signature
      changes, it's invalidated, or its cursor is abandoned. It never
      restarts a clear sweep in progress;
    - **an op cut by a retarget** counts once when it ends, untimed, and a
      glyph still in flight is kept and counted at its DMA's end, untimed
      (revision 13, codex's review). A new op starts a fresh timing origin;
    - **a failed piece** stops the op and leaves the loss to the owner's
      handler (C1). No slot commits over a pending loss.
  - **Not by returning halfway.** No existing synchronous draw function
    returns partway through its rectangle: their callers advance shadows
    and restore state on return. Yielding belongs to the slot scheduler,
    whose completion contract knows about partial work.
  - **Host cases at every piece boundary:** partial B to A, a changed
    selection, a loss, a layout change, a close and reopen, and a stop's
    completion. The existing tests interrupt only between logical ops.
    **And at the final piece's end, just before and just after it:** with
    a failure, with navigation in the same pass, and with a stopped clear.
    C9's 27 ops, its reference frames and its stop positions don't change.
  - **The target, measured, not implied.** N is chosen from measured piece
    costs, so that whole main-loop passes stay at or under 15 ms through
    the named normal-operation workload, including its encoder backlog and
    radio traffic. Zero passes of 25 ms or more. The record keeps the op
    maxima, the whole-pass maxima and the repaint-completion latency.
    Injected faults and their recovery are measured separately. A byte
    count alone guarantees none of this, and neither a byte limit nor a
    pass counter proves lossless input: the physical typing test stays.
- **The panel-order stream:** `lcd_stream_begin(x, y, w, h)`,
  `lcd_stream_bytes(const uint8_t *panel_order, n)` and `lcd_stream_end()`.
  - **`begin`** validates the rectangle, quiesces the bus, acquires the
    scratch, then sets the inclusive LCD window. `bus_quiesce()` stays out
    of `lcd_window()`: the DMA arm path calls that after marking its own
    transfer busy (`lcd_bus.c:686-688`).
  - **`bytes`:** `n` is in bytes, sent synchronously; the stream knows the
    total it expects (`w * h * 2`).
  - **`end`** completes the sends, deasserts CS and releases the scratch.
  - **Every piece opens and ends its stream within one pass** (revision 9's
    words: a logical **op**, a slot's chunk, may span passes; a **piece**
    never does). No stream stays open across passes, so no other painter
    can move the window under it.
  - Generated pixels (the mono glyphs, the strip, the QR code) are written
    into the scratch already in panel byte order, through `lcd_bus.c`'s own
    primitives, and sent through the stream. Clears aren't generated: the
    layout's, the restore's and the debug page's clear bands, and the flash
    glyphs, stay on flash DMA (the budget's exemption, above).
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
  | owner, session, restore gen (u16), phase, damaged, wake notice, cooldown | 12 |
  | the two logos' stale bits, `menu_visibility` | 2 |
  | capture bits, gesture, hold timer, the synthetic hold | 12 |
  | nav stack (3 levels), cursor, top, timers | 24 |
  | edit transaction (an RGB config snapshot, a level, flags) | 16 |
  | region slots (24 x 4) | 96 |
  | chunk cursor, clear cursor, stream bookkeeping | 12 |
  | coalesced input (`turns`, `latch`, `dropped`) | 3 |
  | op 27 state (`last_seq`, `last_state`, armed, the synthetic hold's release time) | 8 |
  | instrumentation (`invariant_fail`, losses seen, the wake-while-open count) | 4 |
  | the fixture (screen, cursor, pattern, the stop's `n`) | 4 |
  | P2: `flash_stats` (3 counters, wider masks) | 12 |
  | P3: Bluetooth operation state | 24 |
  | **total** | **~229** |

- **Freed:** the shared scratch frees 512 B, so the dev gap goes from 32 to
  about 544 before the menu's ~229. If the linked build disagrees, take
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

### C9. S0's fixture

The MENU owner's screen in S0, opened by op 27 sub 4 or, when armed, by
`Fn` plus the knob. It's replaced by P1's tree. It's drawn with today's
primitives: fills through the scratch, and the debug page's flash-atlas
font (`FONT_SMALL`) through `lcd_draw_flash_glyph_try`. No mono path yet:
that's S1.
- **Layout F1** (screen id 1), C8's list geometry:
  - **the title slot:** "FIXTURE A" or "FIXTURE B", 9 glyphs from x 4;
  - **the separator;**
  - **eight row slots,** each painted as two half-row fills (x 3-63 and
    x 64-124) in its pattern's two colours. The cursor's row has its two
    colours swapped, so a selection change is damage;
  - **the scrollbar slot,** its track and a thumb at the top.
  - **A full paint is 27 operations** (9 + 1 + 16 + 1), so pattern 2's `n`
    runs from 1 to 26. Patterns A and B differ in every slot.
  - **What's counted:** completed logical paint operations (a glyph, a
    half-row fill, the separator, the scrollbar), not clear bands or
    passes spent waiting on a transfer.
  - **Pattern 2 needs A settled first** (`pixels_done` with pattern A);
    otherwise it answers status 2. So every partial B is a fresh 27-op
    paint over A.
  - The colours and the scrollbar's construction are fixed in `const`
    tables in S0's first commit, and the host's expected frames come from
    them.
- **Layout F2** (screen id 2): a 4 x 4 grid of 32 x 32 fills, one operation
  each, after the layout's banded clear.
- **The colours:** `const` RGB565 tables in the fixture's file, A, B and
  F2's, chosen so neighbouring slots differ and no slot is black.
- **Its input:**
  - turns move the cursor over the eight rows, wrapping;
  - a click on rows 0-5 toggles A and B;
  - a click on row 6 switches to F2; in F2, any click returns to F1, row 6;
  - **row 7 is Diagnostics:** a click enters DEBUG (Health) with the
    session OPEN, and a click there returns to F1, row 7;
  - Back (the hold) and close end the session;
  - **the 24 s idle timeout** applies. The 3-minute backstop needs an edit,
    so it's P1's.
- **The expected frames** come from the same tables: the host tests compute
  each slot's pixels, and the board's photos are compared with them.

### C10. S1's measurement contract (revisions 9 to 12)

What S1's scripts read, and the numbers they pass or fail on. **Every value
is fixed here, before the measurement**; a value changes only in a plan
revision, never during a run.

- **Op 27 sub 10, timing and targets (dev builds).** Request `[.., 27, 10,
  arm]`; it replies at once (no sequence; byte 5 status). **`arm` 1 starts a
  measurement interval:** it zeroes bytes 6-15, 19 and 24-25 after the
  reply, and issues a new session token (bytes 26-27). Every main-loop pass from then on counts, under **any** owner: the
  dashboard's own work, the restore through DONE after a close or a Fn+D
  exit, the transitions, and everything else. `arm` 0 only reads. Nothing
  else is reset: health's counters, ge10, ge25 and HC_ACCT are never reset
  inside a measured span, and the scripts never call `health_reset()`.
  | Bytes | Field |
  |---|---|
  | 6, 7 | the largest single piece's cost: wall time in µs within its pass, from window to CS release |
  | 8, 9 | the largest logical op latency (bytes 26-27's measure) |
  | 10, 11 | the longest whole main-loop pass in the interval, in µs, any owner |
  | 12, 13 | passes in the interval **over 15,000 µs** |
  | 14, 15 | the longest repaint latency, in ms: a MENU target's creation (`tgen` moved) to `pixels_done` with that target |
  | 16 | `tgen`, the MENU target generation (u8, wrapping) |
  | 17 | MENU targets settled (u8, wrapping): `pixels_done` becoming true for a new `tgen` |
  | 18 | MENU targets superseded (u8, wrapping): a `tgen` that moved on before it settled |
  | 19 | the largest clear band's wall time, in ms: the layout's, the restore's and the debug page's bands |
  | 20 | the debug page showing: 0 none, 1 Health, 2 Camera |
  | 21 | `dbg_gen` (u8, wrapping): it moves each time the page's composition produces a target that differs from the last one composed, the first composition after a page reset included |
  | 22 | `dbg_done_gen` (u8): the last `dbg_gen` whose every cell has been painted, with its final transfer complete and no loss pending |
  | 23 | MENU slots committed (u8, wrapping) |
  | 24, 25 | the passes in the interval (u16, **wrapping**): a summary only. Validation uses health page 2's u32 `passes`, `count_ge_10ms` and `count_ge_25ms`, which `health.c` snapshots together |
  | 26, 27 | the session token (u16): 0 at boot (in RAM cleared at reset); each `arm` 1 sets it to the next value of a boot-cleared counter, skipping 0. It reads 0 after any reboot, so a token that changed, or reads 0, ends the session: the run fails |
  | 28 | the health-reset generation (u8, wrapping): every `health_reset()` moves it. It must not change across a measured interval |
  | 29 | `dbg_sec`: the RTC second (0-59) that the composition `dbg_gen` shows, taken from the same `rtc_get_time()` sample that composes the clock text (not `rtc_get_seconds()`, the free-running edge counter, whose value mod 60 isn't the calendar second); 0xFF before the first composition |
  | 30 | the RTC's current second (0-59), read in the same reply |

  **A1's "unknown sub" check moves from 10 to 31.**
- **The debug page's completion** (`debug_done`, sub 5's byte 31, bit 0)
  holds when all of these are true:
  - the owner is DEBUG;
  - a composition has happened since the page was entered;
  - the page's clear has finished;
  - the grid is clean (`dbg_dirty`, or `cam_dirty` on Camera, is 0);
  - no composition is pending: `dbg_force_recompose` is false, **and** the
    RTC's current second equals `dbg_sec`. A second that has elapsed but
    hasn't been composed is pending, since `draw_debug_page()` finds a new
    second by comparing `sec` with `last_sec`, not through the flag
    (`display.c:840-845`);
  - `dbg_done_gen == dbg_gen`;
  - no transfer is in flight, and no loss is waiting.

  **A page reset and a loss's invalidation each move `dbg_gen`**
  (`display.c:837-845,1216,1232`). So a page being repaired is a new
  generation, and completion is false until the repair is painted, even
  when the composed text didn't change.

  **A script ties a tested update to its completion like this:**
  1. it reads `dbg_gen` **before** the cause;
  2. it makes the cause: an op 1, or a clock second on Camera, whose time
     line changes every second. For a second, it names the expected second
     `S` as byte 30's value plus one (mod 60), and the second's arrival is
     byte 30 reading `S`. A cause that leaves the composed target unchanged
     isn't a tested update;
  3. it waits for `dbg_gen` to move past the value it read, **and, for a
     clock second, for `dbg_sec` to equal `S`**. The composition is tagged
     with the second it shows, so an earlier second's generation can't
     stand in for it;
  4. it waits for `dbg_done_gen` to equal that generation, with
     `debug_done` set and `dbg_sec` still `S`. If the clock moves on to
     `S + 1` first, that sample is discarded and the case retried; three
     discards fail the run.

  A boolean read alone proves nothing. MENU's `pixels_done` keeps its
  current-target meaning.
- **Sampling.** Every read is bracketed by host timestamps, request sent to
  reply matched. A bracket over **25 ms** is discarded and the read retried,
  at most three times; a fourth fails the run. A sample's time is the
  bracket's midpoint, and its uncertainty half the bracket. u8 counters are
  read at least every **100 ms** during activity, which no counter can wrap
  in (the fastest, `tgen`, moves at most once a pass, ~220 a second, so
  fewer than 25 a read).
- **Counters, per field** (the delta across a window is modular: mod 2^32
  for u32, mod 2^16 for u16, mod 2^8 for u8):
  - **`uptime_ms`** (u32, ms): its delta agrees with the host's
    midpoint-to-midpoint time within **2% plus the two samples' half
    brackets**. Otherwise the timebase has failed, and so has the run;
  - **the row ISR's entries** (u32, a count): the rate, entries over the
    board's elapsed seconds, lies between **1,000 and 10,000 a second**;
  - **ge10, ge25 and passes:** a ge delta is no more than the passes'
    delta, and the passes' delta no more than **500 a second** of the
    board's elapsed time;
  - **a reboot** shows as the session token reading 0 or changing; **a
    health reset** shows as the health-reset generation (byte 28) moving.
    Either one fails the run. The plausibility bounds above stay as checks
    of their own, not as the way resets are found.
- **Sustained activity** (5 s windows while an activity runs on, the
  menu's open-and-close excluded): each window's row ISR rate is at least
  **0.98** of the matched baseline. The baseline is three 5 s dashboard
  windows just before, with the same lighting, transport load and
  instrumentation. A ratio over 1.01 fails as a configuration error.
- **Transitions** are exempt from the sustained rule and have their own:
  Fn+D in, Camera, Fn+D out, the menu's open and close, and a layout
  change.
  - **Ten repeats** of each kind.
  - **Each repeat** is measured in successive **500 ms windows** from the
    transition until its observed completion: the restore's DONE with a
    new generation, `debug_done` for the new `dbg_gen`, or `pixels_done`
    for the new `tgen`. Then **one window more**.
  - **The thresholds:** every window is at least **0.95** of a matched
    500 ms baseline, and the mean of all the windows of one kind, across
    its ten repeats, at least **0.98**.
  - **Completion** comes within **1,000 ms** of the transition, else the
    run fails.
- **Paced repaints:** every requested target settles within **1,000 ms**,
  else the run fails.
- **Continuous input** (op 27 sub 1, one detent every 50 ms for 10 s, read
  every 100 ms; the encoder's own backlog is measured separately in S1):
  - **progress:** the committed-slot count (byte 23) rises in every
    500 ms of the burst. Settled whole targets aren't required during the
    burst, since each lives only ~50 ms;
  - **the end:** the final cursor is the sum of the detents, modulo the
    rows; the final target settles within **500 ms** of the last detent;
  - **the books:** targets created (`tgen`'s delta) equal the settled plus
    the superseded, plus at most the one outstanding.
- **Timing:** over the armed interval of the supported workload, byte 10-11
  is at most **15,000 µs**, byte 12-13 is 0, and ge25 doesn't move.
- **Every timeout fails the run,** logged or not. A run that fails any
  check isn't a measurement and isn't reported as one.

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
- **The reply** keeps HC_DEVHOOK's framing. Byte 0 stays `0x07` on every
  handled reply, as the other ops' replies do, and `RTC_UNHANDLED` only for
  dev hooks off, an unknown sub or a short report. Bytes 1-4 are echoed.
  **Op 27's own status is byte 5:**

  | Status | Meaning |
  |---|---|
  | 0 | accepted (a mutation) or done (a read) |
  | 1 | busy: a synthetic mutation is still outstanding, or the physical knob is down for a hold |
  | 2 | a bad argument: out of range, or a sub this state can't take |

  `scripts/devhook.py` and `scripts/current_map.py` treat byte 0 as today, so
  they read op 27's replies unchanged. The tests use a small op 27 codec of
  their own for bytes 5 on.
- **Single flight.** One synthetic mutation is outstanding at a time; any
  other mutation answers busy until it completes. Reads (sub 5) are always
  answered.
  - An accepted mutation gets `seq` (u8, wrapping, never 0), at reply
    byte 6. A test polls sub 5 until `last_seq` equals its number exactly
    and `last_state` is terminal.
  - **When each kind completes** (`last_state` done):

    | Kind | Done when |
    |---|---|
    | turns, click, `Fn` plus a click | `menu_task()` has applied it |
    | a hold | its scheduled release has been processed, or the hold was cancelled (`last_state` cancelled) |
    | a fixture paint, patterns 0, 1 and 3 | the model has its new target; the pixels are reported separately (`pixels_done`) |
    | a fixture paint, pattern 2 | the fixture has stopped after operation `n` (the stopped flag) |
    | a restore request (sub 7) | the request is **installed**: a restore started, or `WAITING` under another owner. The restoration itself is watched through `restore_phase` and `restore_gen` |
    | a loss (sub 8) | the owner's handler has consumed it |
    | arm or disarm (sub 6) | applied, with any session it closed |

  - **Discarded work still ends.** When a boundary throws away an
    outstanding synthetic action (an ownership change dropping an injected
    loss, a handoff clearing the coalesced input, a close), its sequence
    ends as superseded or cancelled. Nothing accepted can block the single
    flight forever.
  - **A busy or bad-argument reply** leaves the outstanding sequence and its
    state unchanged. At boot, `last_seq` is 0 and `last_state` none.

  - **"Applied" isn't "painted":** `pixels_done` means **the MENU fixture's
    pixels are settled**: the owner is MENU, every active slot is
    `COMMITTED` **with the signature of its current target**, no clear is
    running, and no transfer is in flight. A slot left `COMMITTED` with an
    old signature counts as not settled. Byte 21 and pattern 2's "A settled
    first" use the same test. It's
    false under every other owner. DASH's completion is read from
    `restore_phase` and `restore_gen`. The debug pages had none in S0; S1
    adds `debug_done` (byte 31, C10).
- **The subs:**

  | Sub | Args | Effect |
  |---|---|---|
  | 0 | [5] pattern, [6] n | the fixture's paint (S0's fixture, below). Pattern 0 is A, 1 is B, 2 is B stopped after `n` operations (1 to B's count less 1; the stop comes after operation `n`'s transfer has completed or failed, and holds until the next sub 0), 3 is the other layout. Patterns 0, 1 and 3 need `n` = 0, else status 2. Only while the fixture is open; otherwise status 2. S1 adds its mono patterns from 16 up |
  | 1 | [5] int8 count, within ±16, not 0 | turns |
  | 2 | | a click |
  | 3 | [5..6] u16 LE hold ms, 0 meaning 650, within 50-5000 | a hold: a synthetic press now and a release `menu_task()` schedules, never `wait_ms` |
  | 4 | | `Fn` plus a click: the opener or the closer |
  | 5 | | read the state (below) |
  | 6 | [5] 0 or 1 | disarm or arm the physical test mode (C2) |
  | 7 | | request a dashboard restore, as the startup callback does |
  | 8 | | mark a blit lost, as an exhausted recovery does |
  | 9 | | the handoff probe (the board's A3, `CONFIG-MENU-S0-BOARD-TESTS.md`): under a DONE dashboard, queue three glyphs and a lock label, then hand the panel to the Fn+D page in the same call. Bytes 7-10 of the reply: gq and lq before, then after. Refused (state 5) unless the dashboard is DONE |
  | 10 | [5] 0 or 1: arm | S1: timing and targets, read at once with no sequence (C10). Bytes 6-30; `arm` 1 starts a measurement interval, zeroing its maxima and counts after the reply and issuing a new session token |

- **Sub 5's reply,** from byte 5 (byte 5 is the status, 0):

  | Byte | Field |
  |---|---|
  | 6, 7 | `last_seq`; `last_state`: 0 none, 1 pending, 2 done, 3 cancelled, 4 superseded, 5 refused |
  | 8, 9 | owner: 0 DASH, 1 DEBUG, 2 MENU, 3 ANIM; session: 0 NONE, 1 PENDING, 2 OPEN |
  | 10, 11 | `restore_gen`, u16 LE |
  | 12, 13 | `restore_phase`: 0 SPLASH, 1 WAITING, 2 CLEAR, 3 STAGES, 4 RESIDUAL, 5 DONE; `restore_damaged` |
  | 14, 15 | screen id: 0 none, 1 fixture layout F1, 2 fixture layout F2, 16 up for P1's screens; the cursor |
  | 16 | flags: bit 0 armed, 1 an edit open, 2 `pixels_done`, 3 `lcd_blit_busy()`, 4 a clear running, 5 the wake hold, 6 `batt_dirty`, 7 a logo stale |
  | 17 | queues: `gq` entries (low nibble, saturating at 15), `lq` entries (high nibble, saturating) |
  | 18, 19 | `turns` (int8), the latch: 0 none, 1 click, 2 Back, 3 close |
  | 20 | `dropped` |
  | 21 | slots not settled (not `COMMITTED`, or with an old signature) |
  | 22 | losses seen (u8, saturating) |
  | 23 | the capture bits: bit 0 the press, 1 clockwise, 2 counter-clockwise |
  | 24, 25 | `invariant_fail`, u16 LE: bit 0 an early `COMMITTED`, 1 an early `DONE`, 2 a wake while OPEN, the rest reserved |
  | 26, 27 | the last **ended** logical op's latency (revision 9): wall time in µs from its first piece's start to its end (the last piece's return, or its last DMA's completion or give-up), passes between included; u16 LE, saturating at 65535. A failed op updates it; an op abandoned by a retarget doesn't. 0 until S1 |
  | 28 | the pairing phase; 0 until P3 |
  | 29 | the fixture's completed paint operations since its last target (saturating) |
  | 30 | bit 0: the fixture is stopped (pattern 2) |
  | 31 | bit 0 (revision 9): `debug_done`, the debug page's completion (C10); the rest zero, reserved |

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
   - **the fixture** (C9), so ownership, damage and the restore show on the
     panel without P1's tree;
   - **the production code split for the host:** the owner and restore
     (`panel_owner.c`), the input (`menu_input.c`) and the slots
     (`menu_slots.c`) have no ChibiOS calls. They reach the panel through a
     small backend (`lcd_clear_rect_ok`, `lcd_fill_rect`,
     `lcd_draw_flash_glyph_try`, `lcd_blit_busy`, `lcd_blit_lost_take`)
     that the host tests replace with a fake framebuffer. The tests run the
     firmware's own state machines, not a model written again.

   **Proof:**
   - **host tests** (gcc), with the fake framebuffer, success or loss per
     transfer, and expected pixels computed from C9's tables: the
     transition table, the restore's phases and every handler in "Loss",
     the damage rules (A, then partial B at each `n`, then A; a layout
     change during a clear; a band that fails and is retried), the input's
     order and precedence, the capture and release routing, and op 27's
     single flight;
   - **op 27 on the board:** the transition table's rows, the animation
     refused and stopped, the startup restore (sub 7), an interrupted one, a
     loss's handling (sub 8), a stale logo repaired, and `invariant_fail`
     still 0 at the end, which catches an early `DONE` or `COMMITTED` that
     a snapshot would miss;
   - **a real DMA timeout,** on a `devfault` build, whose HC_BLITFAULT
     drops a real completion (`lcd_bus.c:651-659,786-789`). `devfault` is
     the whole dev configuration plus `-DWDT_TEST_HOOKS`, a new `build.sh`
     flavour with dev's structural checks and the heap floor, gremlin only.
     N=1 proves a retry that succeeds; N=2 proves the give-up and each
     owner's handler, the animation's included. Sub 8 only tests the
     handlers;
   - **host tests for the new outcomes:** two losses under five seconds
     apart, the first restore already `DONE` before the second; Camera
     pumped on after its cells finish, with the time and values frozen, so
     an overwrite by Health's grid can't escape; sub 7 under MENU, DEBUG and
     ANIM; an injected loss dropped at an ownership change;
   - **the fixture's pixels** after A, partial B and A, F2, and a loss,
     checked by photo against the host's expected frames;
   - **the physical cases, armed (JD's hands):** the knob's presses and
     releases, `Fn` released first, a timeout while held, a hold across a
     close, and a pending tap-hold on another key. The one-shot and the
     MT/LT cases remap the knob in VIA for the test and put it back;
   - the linked RAM of the dev and daily builds, by the new check;
   - `Fn`+`D` and the animation behaving as before;
   - **timing as a measurement under a named workload,** not a universal
     bound. The workload is `scripts/menu_s0_session.py`, committed with
     S0: a fixed 50-step array, run ten times, 500 op 27 mutations.
     - **It starts** from the dashboard with the session NONE, and opens
       the fixture with sub 4.
     - **Per 50 steps:** 28 turns of ±1 to ±4, 10 clicks on named rows
       (two A/B toggles, two trips to F2 and back, two Diagnostics
       handoffs and returns), 4 holds of 650 ms, 4 `Fn` plus a click, 2
       restores (sub 7) and 2 losses (sub 8). Each step names the screen
       and owner it expects after it. Each 50 ends where it began, the
       fixture open on F1 at row 0, and the last returns to the dashboard
       (session NONE).
     - **Its pacing:** each mutation is sent when the last is terminal,
       polling sub 5 every 20 ms.
     - **It records** every outcome and every transition seen, not just
       what was sent. Then five
     minutes of the dashboard with a track playing. The ge10 and ge25 counts
     and HC_ACCT's ring are recorded, with no counter reset inside the
     measured span. ge25 is expected to stay 0. Real spins and the encoder
     drain's backlog are S1's. The general test list below ("The stall
     counters") is P1's gate, not S0's.
2. **S1, the mono paint, measured:**
   - **First, the polled bulk sends** (C4) merged from `gremlin/fill-poll`,
     with both hardening items:
     - **an entry check** that SPI0 is idle (READY, no DMA, RX empty). It
       never blindly resets a live transaction and strands its owner: it
       takes the established bounded quiesce or abort path, or refuses
       safely as a give-up;
     - **the driver's FIFO dispatch** respects IE and transfer ownership,
       while keeping the DMA dispatch: a chibios-contrib patch, recorded in
       `PATCHES.md`.

     **Proof of the failure path:** a dev or `devfault` hook that fails a
     poll in a middle piece and at the BUSY tail. The loss is latched, the
     bus cleaned up, the owner repaints, and `PO_FAIL_SPI0_POLL` is set.
     HC_BLITFAULT covers DMA completions only.

     **And `MENU_PASS_BYTES`** (C4), applied to the fixture's ops before the
     mono paint builds on them.
   - **C2's Fn stays `layer_state`** ("Open" 5, settled): documented, with
     the A10 tap-hold case recorded as the known miss.
   - `lcd_blit_mono` and the generated font, with op 27 sub 0's mono
     patterns (16 up) painting on the fixture, under its panel ownership,
     never a second painter over the live dashboard.
   - **The encoder drain:** real spins and a backlog are measured, and the
     supported burst and backlog are named. The drain spends its two
     configured 1 ms waits on every detent it dequeues, even when the menu
     captures them, so a backlog can pass 25 ms before any painting. If the
     named workload breaks the whole-pass target, **a bounded drain (a
     change to `quantum/encoder.c`) is required**, or the claim is narrowed
     explicitly.
   - **Measured with HC_ACCT** (wall time, preemption included, not CPU
     time; not scaled again by the row ISR's share): a glyph, a half row, a
     full row, each piece size, and whole passes during real knob spins,
     clock edges and radio traffic. Maxima are kept over the run, since op
     27's last paint duration can miss a slow one between reads.
   - **The clock edge:** MENU suppresses the dashboard's drawing, and the
     pump already skips a pass when the dashboard's clock work ran. Those
     guards stay, and edges are exercised during entry, PENDING, DEBUG and
     the restore.
   - **The bounds:** `MENU_PASS_BYTES` and the DMA clears' bound (C4), and
     the whole pass's target.
   - **Settled on the panel:** the cursor style (Open, 1), and the generated
     glyphs against the flash atlas.
   - **The LEDs, an executable gate:** `scripts/menu_s0_ledrate.py`,
     extended.
     - **The ratio:** activity rate at least 0.98 of a matched baseline,
       taken just before with the same lighting, transport load and
       instrumentation. A rate higher than the baseline sends you to check
       the configuration and the timebase.
     - **Covered:** sustained mono repainting, F2, selection changes, real
       spins with their backlog draining, layout clears, open and close,
       the restore through DONE, and Health and Camera's entry, updates and
       exit.
     - **Transitions measured on their own,** repeated, in short windows,
       or as row-start gaps: a 50 ms stall spread over 5 s is only 1%, so
       the ratio alone can't rule out a flicker. The ISR's duration maximum
       doesn't measure a late start. JD's spin check by eye stays.
     - **The script fails a run** on any of C10's checks: the ratio, the
       transition windows, a settlement or progress miss, ge25, sub 10's
       15 ms count, unusable counters, or a timebase mismatch. Every
       number is C10's.
     - **Completion, two rules:**
       - **for paced repaints,** every requested target settles within its
         deadline;
       - **during continuous spins,** C3 may supersede intermediate
         targets. The input's outcomes are right, the supersessions are
         accounted for, and the final target settles within a bound after
         the input stops. A fine ISR rate with the painting barely moving
         fails the responsiveness gate.
     - **Excluded from the matched comparison:** boot and reset, counter
       resets, intended sleeps and lighting-mode changes, and injected bus
       faults, whose recovery is recorded separately. Ordinary restores,
       Fn+D painting and the encoder's waits stay in.
3. **P1, the menu:** `menu.c` with host tests; Lighting, Screen, Power,
   Clock, Diagnostics, Help, About and Exit; C6 to C8. **The menu keycode**
   ("Open" 3): its C2 amendment, reviewed before code, then appended to the
   enum and `via.json`. Tests: duplicate bindings, held-key remaps, both
   platforms, every session state, and both kinds of held knob.
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
  - **The LEDs (revisions 7 and 8):** S1's executable gate (the ratio of
    at least 0.98, the transition windows, the two completion rules), and
    JD's eye on a knob spin.
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

1. **The cursor: SETTLED, lit text** (JD on the panel, 10-24, the
   fixture's F3: "I'd lean the 'lit' rows instead of inverted"; both
   "decent"). The rows a little dimmer than white (#C8C8C8, RGB565
   `0xCE59`), the selected row pale yellow (#FFF2A0, `0xFF94`). For the
   same footprint its cost doesn't depend on the style: the opaque mono
   blit sends every pixel of a cell either way (measured: GREMLIN-RESULTS
   §19). JD also found the 6x14 face small ("tiny"), and chose to go on
   with it: a larger face is a redesign, in BACKLOG.
2. **Half rows or full rows: SETTLED, half rows**, by measurement (JD, 10-24:
   no visible difference, "do whatever is more efficient"). On `cbb51ac1`
   both keep every pass under 15 ms; half rows have the more headroom
   (the longest pass 13.1-13.5 ms against 13.5-14.5) and repaint only the
   changed half when a value on the right changes; full rows finish a
   cursor move ~10% sooner (158 ms against 165-182), with one window fewer
   a row. They don't halve the total area of a cursor move, which still
   repaints two whole rows.
3. **A menu keycode (JD, 10-24): wanted.** An opener JD can place anywhere in
   VIA, beside Fn+knob, which stays. JD first thought of Fn+C (the clock
   format today), then kept everything on the knob; JD wants the keycode as
   well. **In P1** (codex, revision 7: that's when the real menu exists).
   The C2 amendment, reviewed before code:
   - **The enum:** appended to `ak820pro_keycodes` and via.json's
     `customKeycodes[]` (append only).
   - **Matched by its resolved keycode on the press;** the release goes by
     the event's physical identity. VIA can bind it to several keys, so
     owed releases are per key (a small matrix-position bitmap), not one
     capture bit.
   - **Its press, by state:**

     | State | A menu-key press |
     |---|---|
     | DASH/NONE | opens, or enters PENDING during the wake hold |
     | DEBUG/NONE | hands off to MENU/OPEN |
     | PENDING | cancels the pending request |
     | MENU/OPEN or DEBUG/OPEN | closes the whole session |
     | ANIM | refused, its press and release still captured |

   - **Its release** does nothing: no click, no Back, no second toggle. Owed
     releases are routed before the session, the enable state or the
     current keycode are checked, even after a disarm or a VIA rewrite.
   - **A press while the knob is held** keeps the knob's release ownership:
     a forwarded knob press has its release forwarded, a captured one
     consumed. The open or close clears old gestures and pending input, so
     that release can't click into the new session or fire a late Back.
   - **The knob's identity routing stays authoritative** during a session.
     If the keycode is mapped onto the knob or a detent, the behaviour is
     documented, and one event never takes both routes.
   - **The Fn question ("Open" 5):** a menu keycode on a base layer needs
     no Fn test, and is captured before an unrelated tap-hold resolves. One
     reachable only on the buffered Fn layer can still be missed, because
     the early lookup sees the mapping underneath.
4. **The fixture's fills dim the RGB ~19% while they repaint** (A11,
   `GREMLIN-RESULTS.md` §10). `lcd_fill_rect` runs through SPI0's FIFO
   interrupt, which delays the row ISR. **JD, A10 (10-24): every knob turn
   visibly flickered the keyboard's LEDs** (one cursor move repaints two
   rows). The restore's and the Fn+D page's clears were never part of it:
   they're DMA'd from flash and measured ~0.3%. **Settled:** bulk sends are
   polled (C4), prototyped as `gremlin/fill-poll` `f2b107be` (-18% to
   -1.3%, JD: "no flicker"). Repaints take ~15% longer in wall time for it,
   so the per-pass budget (C4) and S1's LED gate carry it from here.
5. **Fn is judged by `layer_state`, which lags a buffered Fn press** (A10,
   10-24). Within the tapping term of an undecided tap-hold on another key,
   QMK's tapping buffer still holds Fn's press, while C2's capture in
   `pre_process_record_kb` sees the knob at once. Fn+knob then reads as a
   plain knob: its mapped input is forwarded and replayed, and the menu
   doesn't open. On the board that was safe, but under another VIA mapping
   the forwarded press would do whatever that mapping does.

   **Settled (codex, revision 7): accepted and documented.** Fn means an
   active `WINFN` or `MACFN` layer at the early hook, and an unresolved
   layer-tap isn't Fn yet. That keeps QMK's own decision and C2's
   contract. The alternatives were rejected:
   - **A fixed physical Fn position:** the default maps already have
     several Fn keys, and VIA can move or remove them. It would also take a
     tap-hold key as Fn before QMK decides.
   - **Tracking early presses that resolve to `MO(WINFN)` or `MO(MACFN)`:**
     it handles moved keys and both platforms, but needs held-key tracking
     and a policy for other layer actions, and still can't see an
     unresolved `LT`'s hold.
   - **Reading QMK's tapping buffer:** a core patch over a static
     `waiting_buffer`, its indices and `tapping_key`, tied to the tapping
     internals and configuration. A queued Fn press may already be
     released, too.

   The window is the tapping term after a tap-hold key. Neither keyboard's
   keymap has a tap-hold key today.
