# The LCD: panel, layout, rendering, and what the bands show

The 0.85″ 128×128 GC9107 panel, driven over dual-SPI DMA from external flash.
Code: `graphics/lcd_bus.c` (bus, memory map — authoritative over any prose
doc), `graphics/display.c` (dashboard). Fonts and asset provisioning are in
[fonts-assets.md](fonts-assets.md).

## Panel variant — a compile flag, not an edit

JD's unit is mounted 180° from fpb's and needs inversion on. Default build:
`MADCTL 0x68` + INVON. `AK820PRO_LCD_VARIANT_FPB` (config.h or
`-e EXTRAFLAGS=-DAK820PRO_LCD_VARIANT_FPB`) selects fpb-style panels
(`0xA8`, no INVON). Neither is a "fix" — they are per-unit variants.

Diagnostic that settled the inversion (counterintuitive): the source art is
white-on-black, the board showed black-on-white, and an *asset-free* board
showed solid **white** — the black clear-to-background being inverted. Both
symptoms, one cause. `LCD_OFF_X 1` / `LCD_OFF_Y 2` are controller offsets and
did not need adjusting after the flip; pixels reach every edge.

## Vertical budget — the panel is exactly full

```
0..24     connection strip   25
25..26    gap                 2
27..55    text (2 lines)     29   two 14-row cells, at 27 and 42
56..57    gap                 2
58..79    clock              22   Regular-30, CROPPED to its ink
80..82    gap                 3
83..105   lock band          23   20px face; its last row is the battery's first
105..127  battery            23   20px face
```

- **A glyph blit paints its WHOLE cell, background included** — no
  transparency, no tinting (colour exists only via `lcd_fill_rect`). Cells
  may overlap only where both are blank: the lock band's last row and the
  battery's first, measured from the atlas (no glyph of the 20px face inks
  its cell's top row, and the lock labels are capitals ending at row 18;
  `display.c` asserts both).
- **Spacing is judged by INK, not band boundaries** — the 20px cell carries 4
  blank rows above caps and 4 below baseline, so "move a band 1px" is never
  one constant (balancing the lock row took three coupled moves). Measure
  ink-to-ink: icons→text 2, text→clock 2 (3 in Cozette), clock→lock 7,
  lock→batt 7; between the song lines, descender to capital, 2 (4 in
  Cozette).
- **10-28: the clock down 2, the lock row down 1, the line pitch 14 → 15,**
  for the Large face's song lines (Terminus Bold's capitals are 10 rows to
  Cozette's 8 in the same 14-row cell). Before, Large had 1 blank row
  between the lines and 1 above the clock, and the rhythm below was 8 and 8.
- **Anything drawn must fit inside its band's clear rect.** The 16px padlock
  at `LOCK_Y+3` needs a band ≥ 19 rows; when the band was briefly 17px its
  bottom rows sat outside the clear and stayed lit forever.
- One row of bottom margin and `BATT_X0 5` / right margin 4 are deliberate —
  **the bezel clips the outermost pixels** (panel is recessed).

## How the panel paints: DMA pump, cell diff, glyph queue

The band used to block ~53 ms per two-line repaint on the main loop — enough
to swallow keystrokes once the media poller made it frequent. Two fixes, in
order of importance:

1. **Keep the DMA, drop the wait.** `lcd_draw_flash_glyph_try()` arms one
   glyph and returns; `display_blit_pump()` drives the queue from
   `housekeeping_task_kb()` at main-loop rate (~390 Hz). A line lands in
   ~50 ms wall clock, ~0 ms CPU.
   > ⚠️ One glyph per 10 Hz HOUSEKEEPING tick was tried first: a 20-glyph
   > line takes 2 seconds and visibly crawls. The granularity was never
   > wrong; the clock was.
2. **Do not clear before repainting.** Each band diffs against a shadow of
   what is on the panel and blits only changed cells — `Bright 25%` →
   `Bright 26%` is one glyph, not a wipe and eleven. **The wipe WAS the
   flicker.**

⚠️ **Composing the line in RAM and blitting once is WORSE — do not
re-derive.** `flash_read_bytes()` is a full `spiExchange()` call PER BYTE
(~5.5 KB of them per 12-char line), converting a free DMA transfer into a
CPU-bound loop, plus 5.9 KB of SRAM.

**Glyph queue invariants** (2026-09-01 hardening):

- The 10 Hz housekeeping pass **defers instead of flushing** while glyphs are
  pending (`if (gq_pending()) return;`) — nothing blocks the main loop on the
  panel any more.
- The pump carries the only bounded-wait recovery on the queue path: a 50 ms
  grace, then `lcd_blit_wait()` teardown. Removing that (it looked redundant)
  would let one lost SPI0 completion IRQ park the queue **and** the deferring
  housekeeping forever, with the main loop alive so the watchdog never fires.
  Codex flagged the same hazard independently.
- A band's shadow distinguishes **moved** (font/x/y changed — clear exactly
  the known old run) from **unknown** (`!shadow.valid` — clear the full band
  width). Conflating them caused the stray-`g` bug: `Connecting` →
  `Connected` via an invalidated shadow cleared only the new run's width and
  left the old string's tail on the panel. Fixed + hardware-verified
  2026-09-01.
- `[lcd] blit timeout` on the console is THE health signal: zero under load
  means the pump is not fighting the bus.
- **The pump skips the pass that ran the clock's second** (`clock_ticked_this_pass`,
  since `ce229f87c6`, as `pass_deferred` does after a PCF transaction). On
  `36afff30e8` that pass ran the second edge's diff, the pump's first glyph and
  QMK's core together, at 10-13 ms, once every second, so `count_ge_10ms` ticked
  at the clock's cadence
  ([`history/ge10-per-second-20261022/`](../history/ge10-per-second-20261022/README.md)).
  The glyph goes out on the next pass instead, ~5 ms later. On gremlin's board
  the count fell from 0.175 a second to 0.016. Only a pump call after the latch
  skips: the 10 Hz call's latch comes after the pump.

### Blit timeouts: what they were, and how they are read now (2026-09-23)

- **Every "never started" timeout on record was a lost completion.** The
  transfer had finished: `CURCNT` was full and the hardware had cleared
  `DMAEN`. But the SPI0 half-transfer handler read `RIS` and then cleared
  every flag, wiping a DMATCIF raised between the two instructions. Only
  660-byte clock digits were exposed (see `docs/leds.md`, priority table).
  Fixed in ChibiOS `c57623d0d2`, which clears only what was read and then
  re-checks. The first test build ran 580,060 blits under hunt stress with
  no timeout.
- ⚠️ **`DMACNT` never counts down.** It holds the programmed length through
  and after a transfer. Progress is **`CURCNT`**, which runs 0..DMACNT and
  keeps the *previous* transfer's count until the engine starts the next;
  the hardware clears `DMAEN` at completion. `lcd_blit_wait()` detects start,
  progress and completion from those two, and classifies a timeout from them
  (health page 6: never started / stalled / IRQ lost / unknown). Any class
  is repainted once. The repaint re-sends the window, so it is always safe,
  whatever the first attempt did.
- A blit given up after its retry makes the display repaint the whole
  dashboard through the staged Fn+D restore, at most once per 5 s. The
  shadow already claims the glyph was painted, so it would otherwise stay
  missing until its text changed.
- Instrumented builds print per-size arms, timeouts and the SPI0 handler's
  rescues once a minute (`[lcd] sizes`), and `HC_BLITFAULT` (`0x77`) drops
  the completion interrupt of the next n blits to exercise the recovery on
  demand.

### What drawing actually costs (measured 2026-09-03)

Nobody can budget a repaint without these, and their absence cost a full
afternoon. **The setup dominates, not the pixels.** Every blit pays a window
command, a flash read command and a DMA arm, all of which dwarf a glyph's few
hundred bytes.

| operation | data | blocking cost |
|---|---|---|
| one 6×14 glyph, synchronous | 168 B | **~1.6 ms** |
| one 10×23 glyph, synchronous | 460 B | **~2.5 ms** |
| full-screen `lcd_clear_rect` | 32 KB | **~43 ms** |
| one 128×16 clear band | 4 KB | **~5.5 ms** |
| one glyph via the queue | 168 B | **~0 ms CPU** (one pass of latency) |

Two consequences worth internalising:

- **A page of small text is catastrophic synchronously.** 9 rows × 21 columns is
  189 glyphs ≈ **300 ms**, for 32 KB of pixels. The first Fn+D debug page did
  exactly this and made the keyboard untypeable — JD's bug report was
  literally mistyped. Anything drawing in bulk goes through the queue.
- **A big clear is data-bound, and `lcd_clear_rect()` ends in
  `lcd_blit_wait()`.** A full-screen clear parks the main loop for the whole
  transfer, for a DMA that needs no CPU at all. **Clear in bands** — 128×16 per
  main-loop pass keeps every step under the 10 ms leading indicator at identical
  total wire time.

  > ⚠️ Do NOT "fix" this by arming the DMA and returning
  > (`lcd_clear_rect_async`, tried and reverted as `8dc74f7015`). It routes
  > around the pump's stuck-blit recovery and lets a second owner draw over a
  > restore in progress. **It hung the board and tripped the watchdog.** Smaller
  > was available the whole time.

### ⚠️ Not every band is queued — the status band still blocks

The asymmetry that makes the table above a trap. The clock band and the host
text slot queue. **`draw_locks()`, `draw_battery()` and `draw_conn_number()` do
not** — they call `lcd_draw_flash_text()` directly, which is synchronous and
one LCD operation per glyph.

Measured cost, page closed, ~10 Caps Lock presses: `blit_gap_max_ms` **22 ms**,
`count_ge_25ms` **0**. That is *under* the threshold where a press can be lost
(25 ms, the shortest keypress), so it costs latency and never a keystroke. It is
**not** a defect and does not need fixing on those grounds — an earlier
prediction that it "costs a stall on every Caps press" was wrong, and the
measurement is what corrected it.

It used to exceed 25 ms in one place: the **forced** repaint on Fn+D exit, where
`draw_locks(true)` painted every indicator in one pass (~30 ms). **Fixed in
`821431e3e4`:** the restore now paints the lock band one component per pass,
and `draw_battery()` no longer clears its whole strip on every level tick.
Measured after the flash, ~4 min, 682 presses, several Fn+D exits:
`count_ge_25ms_nonflash` **0**, `blit_gap_max_ms` **20** (the unchanged Caps-on
path). See `plans/BACKLOG.md` before touching the band further.

**`draw_battery()` since flash 2c (2026-10-11): one component per main-loop
pass.** It is still synchronous, but what changed is marked (the outline, the
bolt slot, the text, the bar) and each call paints only the first mark. The
text goes in 3-glyph chunks (~2.5 ms a glyph), and a shortening text's clear
takes its own call. The bar is marked by the fill it would paint, not by the
level, which also fixed "Low"'s sliver at 0%. A flag set by the first paint
keeps a second call in the same pass from painting; `display_pass_end()`, the
last thing `housekeeping_task_kb()` does, clears it. Without that flag the
second-edge draw, the 10 Hz tick and the deferred dashboard redraw could land
two or three components in one pass. ⚠️ QMK calls `housekeeping_task_user()`
after it; that hook is empty here, and a keymap that draws there would reopen
the gap (codex, flash 2c).

### Small shapes go in a RAM tile, not in rectangle runs (2026-10-11)

**Every `lcd_fill_rect` run pays an 11-byte window command sent byte by byte**
(`spiSend`), and the ChibiOS call overhead per byte dwarfs the pixels. So a
shape drawn as a dozen runs costs a dozen windows. Rasterize it into a small
RAM tile and send it with one `lcd_blit_ram()` instead: one window, one send,
and the tile paints its own black background, so no clear goes first. Three
measured cases:

| shape | as runs | as one tile |
|---|---|---|
| the 12h `A`/`M` glyph, 5×16 (`draw_ampm`, the first) | ~24 ms | the 12h transition 40 → 7 ms |
| the battery row's bolt slot, 12×14: bolt, no-pack cross or blank (`draw_bolt_slot`, flash 2c; 13×15 with the power mode's bulb since `26fcafaeca`) | a clear and 11 runs (24 for the cross): 19 ms at every plug-in | plug-in passes 24-26 → **11-12 ms** |
| the transport icon, 12×12: play, pause, stop (`draw_text_icon_runs`, flash 2e) | ~9 ms for play, sometimes drawn twice a call | **3.4 ms** |

The plug-in figures are relay-driven bench cycles, three a build
(`history/battery-2026-10-08-partial-charge/plug-events.csv`). The padlock is
still drawn as runs, and the Caps-on paint measured 20 ms: it is the next
candidate if a check ever shows it over 25 ms. The SN32's DMA cannot source
RAM, so `lcd_blit_ram()` is a CPU push: fine at this size, not for big areas.

### ⚠️ A stall that needs a track on screen (2026-10-11)

Two stalls hid from every idle test because both need **the host text slot
showing a track**. With nothing playing there were none. With music, on flash
2c and 2d:
- **the Fn+D page exit** back to the dashboard: 32-33 ms passes. The
  restore's text-slot stage took 28.3 ms;
- **the settings overlay's retirement** (2-3 s after a lighting change): 31 ms
  passes, the text slot in housekeeping 23.1 ms;
- a track appearing stalled too.

Both ended in the text slot's repaint (`draw_text_slot()`). Forced, it
re-cleared a band its callers had just cleared (~8 ms), and it drew the play
icon as runs (~9 ms), twice when a line clear clobbered it. **Flash 2e** sends
the icon as one tile and drops that clear. Measured with a track playing:
**12.7 ms for both, no pass ≥ 25 ms** in three page cycles, two lighting steps
or the track starting. ⚠️ **Test display changes with a track playing.**

### The display probe (dev builds)

`./build.sh dev` compiles in `DPROBE` (`AK820_DEV_HOOKS`): the worst time of
each of the 14 Fn+D restore stages and of each housekeeping sub-draw, held
until reset. `HC_DEVHOOK` (raw HID `0x76`) reads it and resets it, and can
press `Fn`+`D`, so the debug page can be toggled with no hands:
`scripts/devhook.py press | reset | read`. It is what found the stalls above.
Daily and fpb builds carry none of it (`build.sh` fails them if they do).

### ⚠️ `lcd_draw_flash_text_staged()` is declared and does not exist

`lcd_bus.h` declares it and the comments around the host-text band recommend it
by name for exactly the problem above. **There is no definition anywhere in the
tree; calling it is a link error.** The reason is three paragraphs up: composing
in RAM and blitting once was tried and is *worse*, because `flash_read_bytes()`
is a full `spiExchange()` per byte. The prose was kept, the declaration was kept,
the implementation was correctly removed.

This was believed and acted on 2026-09-03 before the link error surfaced. A file
that confidently documents something untrue is worse than one that documents
nothing — if you remove an implementation, remove its declaration and the
comments that send people to it.

## The Fn+D debug page

Full-panel diagnostics, nine rows in the 6×14 face, on `Fn`+`D`. **A tap
toggles dashboard ↔ debug page (inside the menu's session, menu ↔ debug page);
hold ~800 ms resets the counters** (fires under the finger, not on release —
see `bt_ui.c` for why that distinction matters). Raw-HID op 1 does what the
tap does. The menu's Diagnostics page opens the same page as **Health page**.

```
Uptime      2m 14s     ISR       73% 3900   ← occupancy + rate; field rate = /18
Rowgap      6ms r1     ← worst gap between looks at one key row. THE loss metric
Stall   25:0 10:3      ← 25 ms can lose a press; 10 ms is the leading indicator
Worst      22ms blit   ← how big, and what caused it (flash/blit/i2c/-)
Scan/s         346     BT Drop        0     ← non-zero = a keystroke never sent
BT T/O    352 49%      Batt 62@3 3700 3900  ← raw 5C @ age s, pack mV, VDD mV
```

The `Batt` row keeps three readings apart because they mean different things.
`62` is the module's **last raw `5C`**; `@3` is **how many seconds ago** it
arrived (`--` once 20 s stale, since the module would otherwise show its last
value forever). It counts up to ~4 and resets: reports seem to arrive in
bunches of 2-3 about every 5 s (not yet confirmed; [battery.md](battery.md)).
The page recomposes once a second, so the count skips a value now and then. `3700` is the **pack in mV** from
`battery.c`'s trimmed mean of the last 64 reports — `>4036` / `<3161` at the
clamps, which are bounds, not readings. `3900` is **VDD**, which on battery only
says the buck-boost is running.

It exists for **untethered** use. With the cable attached `ak820health.py` reads
all of this and more in any slider position (commit `4b86d95014`); the panel is
the only readout when no host is attached, and `BT → cable` is a brownout reset,
so plugging in to investigate destroys the wireless session's counters.

Rendering follows the rules above: composed in RAM, painted **one changed glyph
per main-loop pass** through `lcd_draw_flash_glyph_try()`, clears banded. It owns
the panel outright while active (`display_housekeeping_task()` returns early), so
the dashboard — including `draw_locks` — does not run and cannot be measured
while the page is up. **The observer suppresses the observed**; measure the
dashboard over the cable with the page closed.

Dismissing it used to cost ~30 ms (`worst 30ms blit`) because the restore
forced every status component in one pass; since `821431e3e4` the lock band is
restored one component per pass and no stage exceeds ~12 ms. Measured: several
dismissals, `stall>25` stays **0**, `worst` **20 ms** — and that 20 is Caps Lock,
not the page. ⚠️ **That held only with no track on screen.** With music
playing the exit was 32-33 ms on flash 2c, until flash 2e's fix (12.7 ms;
"A stall that needs a track on screen", above). The restore's battery stage
now paints only the outline; the rest follows one component a pass.

While the restore runs, `display_housekeeping_task()` stands aside
(it gates on `debug_exit_step`); that gate is safe only because the pump is
called from its own site in `housekeeping_task_kb()` — the gate's comment says
why, do not fold the pump into the housekeeping task.

### The camera page: removed 2026-10-28

From 2026-10-02 a second tap of `Fn`+`D` showed the camera page: the pack in
volts, the level with the time left, the board's clock and the raw `5C`, in
the clock's 15×22 face, big enough for a room camera to film the end of a
battery run. It was removed on 2026-10-28 because the bench's power cut and
the INA228 logger ([test-bench.md](test-bench.md)) replaced filming the
screen. The debug page's `Batt` row still shows the raw `5C`, its age and the
pack in mV.

What changed with it: the tap toggles instead of cycling; the menu's
Diagnostics page lost its Camera page row; `display_debug_meas()` (op 27
sub 10's page byte) reports 1 for the debug page and 0 otherwise, where 2 was
the camera page; `PO_EV_DIAG_CAMERA` is kept only as a number the panel
owner refuses, and `MENU_DIAG_CAMERA` is never returned. The code (`cam_lines[]` in
`graphics/display.c`) is in the firmware's history before that date. One fact
from it still holds: the clock atlas, cropped for the clock, keeps all 95
ASCII glyphs; the crop cut only descenders.

## Backlight (software PWM, dimmable, persisted)

`PANEL_BKL` (A16) is a plain GPIO. **Hardware PWM on this pin is impossible —
verified in the SN32F299 datasheet; `P0.16`'s only alternate function is a
capture input. Do not re-investigate.** The PWM ticks from CT16B3 (GPTD4) at
20 kHz — see [leds.md](leds.md) for the timer setup and the `MCTRL` gotcha.

- `BKL_PWM_TICKS 48` → 417 Hz switching, floor 2.1%. Levels are perceptually
  spaced: `{0,1,2,3,4,5,6,7,8,9,10,11,12,14,16,18,20,23,26,29,33,37,42,48}`,
  indices 0..23 (was 10 levels until 2026-09-02).
- **Why 24 and not more, and why the period is untouched.** Duty is an integer
  count of ticks, so 48 ticks is 49 possible duties and every level must be a
  distinct one — these 24 are. Steps run 1.09–1.17× above duty 6, against
  1.5–1.78× for the old table. The bottom three (`1→2` +100%, `2→3` +50%,
  `3→4` +33%) **cannot be closed at 48 ticks** — no integer exists between
  them. Doing so needs a longer `BKL_PWM_TICKS`, which lowers the switching
  rate (96 ticks → 1% floor at 208 Hz). **That was rejected deliberately: a
  flicker risk is a worse defect than a coarse first step.**
- **The `Fn`+`PgUp`/`PgDn` readout is the LEVEL INDEX** (`level*100/23`), not
  the duty — level 12 shows `LCD 52%` but is duty 12/48 = 25%. The two numbers
  are meant to diverge; do not "fix" one to match.
- **Hold to sweep.** `SCR_UP`/`SCR_DN` are in the shared hold-to-repeat
  (`param_repeat_*` in `param_overlay.c`, formerly `rgb_repeat_*` — it stopped
  being RGB-only on 2026-09-02). 24 levels is too many to tap through.
- **Persisted since 2026-09-01** via kb_eeconfig's coalesced ~5 s deferred
  flush (safe because every flash program drains in-flight LCD DMA first —
  the old "never persist" rule predated that hook).
  `DISPLAY_BRIGHTNESS_DEFAULT 5` is only the fresh-EEPROM fallback. The
  bootloader splash forces max brightness through the RAW setter, which
  deliberately does not persist.
- A dimmer floor needs a longer period, which lowers the switching rate —
  that is the whole trade at a fixed 20 kHz tick.

## Lock / layer band

`[padlock] CAPS  WIN  FN|SCR` — labels only when active; the board lives in a
dark room. Yellow padlock for *lock* states only (a held Fn layer is not a
lock). Third slot shared: Scroll Lock wins when set, but macOS never sets it,
so in practice it is the Fn indicator. Redraws on the 10 Hz tick so Caps shows
immediately.

- **Scroll Lock shows settled** (flash 2g, every build): a change shows once
  it has held 1.5 s (`SCR_SETTLE_MS`), or at once within 500 ms of the
  board's own `KC_SCRL`, so traffic on the LED report never repaints the
  band. In dev builds a lock-LED frame in progress holds it
  ([`plans/LOCK-LED-CHANNEL-PLAN.md`](../plans/LOCK-LED-CHANNEL-PLAN.md)).
- ⚠️ **The CAPS paint is the suspect for the last passes ≥ 25 ms** (one on
  10-17 and one on 10-18, each in a window that toggled Caps; an inference,
  not measured). To measure with `Fn`+`D`'s probe and a track playing.

- "WIN", not "GUI": the label names the only context where GUI-lock is
  meaningful (Windows fullscreen gaming). Accessor stays `lock_state_gui()`.
- The padlock is drawn from rectangles because glyphs have no colour.
- Fn detection: `FN_LAYER_MASK` in `indicators.c`, built from the shared
  layer enum in `ak820pro.h` (`WINFN`/`MACFN`).

## Battery row

The level comes from `battery.c` — the CH582F's `5C`, a voltmeter on the pack,
through a curve. What it means and how it is estimated:
[battery.md](battery.md). This section is only how it is drawn.

Icon bottom-left (white outline + independent fill), text right-aligned to
`PANEL_WIDTH - 4`. Fill green >50%, amber 21-50%, red ≤20%, rounded up so 3%
doesn't read as dead. **Charging does not recolour anything**: a yellow 9×14
bolt beside the icon carries it (`CHRG` low AND `STDBY` high —
full-and-plugged-in is "done", no bolt), so "15% and charging" stays readable.
The text slot holds one of:

| text | when |
|---|---|
| `85%` (`85.9%` with `BATTERY_SHOW_TENTHS`, a calibration view, off by default) | the level is known |
| `57%` with the bolt, rising | **charging from a known start: the charging model's number**, at most `99%` until the charger terminates, then `100%` |
| `Low`, with a red sliver of fill | level under 0.5% on battery (below ~3.43 V on the fitted curve), or three `5C` reports of 0 in a row |
| `Charge` | charging with the level unknown: no trusted start (a boot on USB, a reboot mid-charge), the model given up (LOST), or the first 60 s before a session qualifies |
| `USB` | on USB, the charger idle, the level unknown (also a short pause in an unknown charge) |
| blank | on battery, the level unknown: after a boot until the first estimate, or for 30 min after unplugging an unknown charge |
| `No Batt`, red cross in the bolt's slot | no pack fitted (`indicators.c`) |

**The bolt's slot shows the power mode on battery (`26fcafaeca`; the bulbs
as now, `83d8768c64`).** The slot right of the icon is one 13×15 RAM tile at
(35, 108) (`draw_bolt_slot`). On USB it holds the bolt while charging, the
cross with no pack, or nothing. On battery it holds the `Fn`+`B` mode as a
bulb: **Always on** lit with rays, **Balanced** lit, **Power saver** a white
outline over grey glass, **Lights out** an unlit slate outline struck through
by a light-grey slash; each has a light-grey screw base under a darker
collar. The bolt and the cross need USB and the modes act only
on battery, so the two never want the slot at once. At 15% or below, while the
low cap holds Always on or Balanced to Power saver's lighting, the slot shows
Power saver's bulb: it shows what the lights are doing
(`power_lights_mode()`, [battery.md](battery.md), "The idle ladder and the
power modes"). On USB the mode can still be changed, and it takes effect at
the unplug. The bulb is marked by `BATT_DIRTY_BOLT` alone, so it stays one
component of the one-per-pass painting below. The 10 Hz tick paints a changed
mode (`batt_bulb_stale`), so the bulb follows `Fn`+`B`'s overlay within a
tenth of a second. Measured on the pack, 30 presses: no pass of 25 ms or
more, the worst 20-21 ms
([`history/fnb-caps-20261019-jd/`](../history/fnb-caps-20261019-jd/README.md)).
The shapes and colours (`COL_BULB_*`) were judged on the panel: greys read
darker there than on a monitor and the slate less blue, so judge them on the
board. Art, colours, the gate and the versions that lost:
[`plans/POWER-MODE-ICONS-PLAN.md`](../plans/POWER-MODE-ICONS-PLAN.md).

**The charging display (Phase 1b, flash 2).** While charging, `5C` reads a
voltage the charge current lifts, so the number is a time model of the charge,
bounded by the voltage: linear at 13.3 points an hour to ~53%, then slowing,
reaching 99% about when the charger terminates. It never falls, never rises
past what the voltage allows, rises at most 0.1 point a second (so it never
skips a value), and steps to 100 at termination (2.6 points on 10-09). The
model, its limits and its measurements: [battery.md](battery.md), "The gauge
as built, Phase 1b".

Never VDD: it showed VDD until the gauge, and on battery VDD is a buck-boost's
output pinned at ~3.90 V. Redraw triggers on the text, the charging state and
presence as well as the level, and repaints only what moved — the old
whole-strip clear plus four synchronous glyphs came to ~20 ms. Since flash 2c
**it paints one component per main-loop pass**, and the bolt slot is one RAM
tile ("Not every band is queued", above): a plug-in costs 11-12 ms passes, not
24-26. Drawing diagonals: rasterise a polygon and emit horizontal runs —
hand-placed zigzags read as the digit "4". The bolt keeps its runs as data and
rasterizes them into the tile.

**Time left, under 10 hours (the deep-sleep build).** On battery, with the
level known and an hour or more of average draw behind it, the row adds the
hours of use left once there are fewer than 10: `18% 6h`, `99% <1h`, at most
7 cells, rounded down. Seven cells right-aligned to `PANEL_WIDTH - 4` start
at x 54, clear of the bulb's slot, which ends at x 47; a longer text would run
into it. "Hours of use" is the awake average's: asleep the board
draws 13.35 mW, an eighth (Lights out) to a twentieth (JD's lights) of its awake
draw, so the sleeps stretch the calendar time and not the number (what it is and how it is counted: [battery.md](battery.md),
"The gauge across a deep sleep"). Above 10 hours the row stays as it was: a
long number there says nothing worth the cells. The tenths view never adds
hours. The menu's Battery page shows time left at any length on the row
instead, with its Hours of use or Both readout (`160h`, `85% 160h`); until
2026-10-28 `Fn`+`D`'s camera page did too. Its Icon only (2026-10-30) leaves
the text slot clear, the hours under 10 included: the bar and its colour
show the level, and `Low`, `Charge`, `USB` and `No Batt` still show.

## At a deep sleep and its wake

The deep sleep is the ladder's last stage (`sleep.c`;
[hardware.md](hardware.md), "Deep sleep"). What the panel does around it:

- **The screen goes off when the board sleeps.** Its dim level is the
  backlight's software PWM, which needs the 20 kHz tick the sleep stops; the
  ladder's screen-off time equals its sleep time (Balanced 20 min, Power
  saver 3, Lights out 1, whose screen is dark already).
- **Host content expires at the wake**: the host text slot and the playback
  position, which ran on while the board slept and would show stale, until
  a host sends them again.
- **The backlight is held dark at the wake** until the clock band and the
  battery row have repainted from the corrected clock and level, or 500 ms
  after the gauge's step if they cannot (`display_wake_corrected`,
  `display_wake_repainted`, `display_wake_release`). Without the hold the
  first frame lit would show the time the board went to sleep with. The
  clock counts as painted by **generation**, not by a flag: the RTC's
  `clock_gen` moves on every calendar change, and the band's last paint
  records the one it drew (`clock_gen_painted`). With the clock off, the
  playback position up, `Fn`+`D`'s page open or the panel paused, the clock
  is not waited for.
- **While the wake's I²C reads run**, a pass that made a PCF transaction
  defers the blit pump and housekeeping to the next (`display_defer_pass`):
  the two together would exceed the pass budget.
- **After two hours or more asleep**, if time left is under 10 hours, the
  status band says `6h use left` (or `<1h use left`) once, through the same
  gate as other owed notices: a free band and a lit screen, except in
  Lights out, whose screen lights for the message.

## Param overlay (readout of what you just changed)

Shows RGB hue/sat/brightness/speed/effect, RGB on-off, NKRO, and LCD
backlight for 2 s in the text band. `param_overlay.c`; compiles out entirely
via `#define PARAM_OVERLAY` in config.h — keep it that way.

- **POLLED on the 10 Hz tick, not hooked into keycodes** — catches Fn
  hotkeys, custom keycodes, `Fn`+`X` (`RM_TOGG`, QMK builtin, never reaches
  the custom switch) AND VIA changes. A `primed` flag skips the boot pass.
- NKRO is the readout with no other feedback anywhere; it is toggled by
  magic key (both shifts + `N`) which is easy to hit by accident. Both
  shifts + `S` dumps status, `H` lists the magic keys — a mysteriously
  misbehaving key is worth checking against that list.
- Effect names are a local table (10 enabled effects), not
  `rgb_matrix_get_mode_name()` — smaller, readable, band-sized.
- Priority: pair hint > RGB readout > link state > host text.
- ⚠️ **Its retirement repaints the host text**, and with a track showing that
  cost 31 ms passes until flash 2e (now 12.7 ms; "A stall that needs a track
  on screen", above). Test overlay changes with music playing.

## Wireless status overlay (words for the blinking digit)

Firmware-owned words in the text band, `conn_status_update()`:

| State | Shown |
|---|---|
| `PAIRING`, BT | `Pair with:` ⟷ `AK820 5.1-1` (the exact advertised name, alternating 1.5 s) |
| `PAIRING`, 2.4G | `Pairing 2.4G` |
| `LINKING` | `Connecting` |
| `CONNECTED` | `Connected` — ~3 s, then the band is released |
| `REJECTED` | `Link failed` ⟷ `Hold Fn+W` (the single key for the failed slot) |
| wired | nothing — the module's state is stale in USB mode |

- The remedy shows for `REJECTED` only, deliberately not for a long
  `LINKING` — that state is ambiguous with the dropped-`5B 32` display bug,
  and the advice would tear down a working link.
- **Dirty-tracking gotcha (was a real bug):** the shared buffer means a
  change of *state* must mark dirty as well as a change of *slot* — a pointer
  compare alone leaves the previous message up.
- The overlay borrows the band and hands it back; a track title is displaced
  for seconds, never lost. It gets 12 characters (no icon gutter); host text
  effectively 11 at 20px.

## Alert slot

`display_set_alert()` puts a firmware-owned warning in the band for 60 s
(below the pair hint in priority). First user: the watchdog reset notice
(`WDT reset x1`) — a recovery the user would otherwise never know happened.
See [hardware.md](hardware.md).

## Host text slot (two lines, pushed over raw HID)

Channel `0x12`: `TEXT_SET` (0x01, line 0 + clears line 1), `TEXT_CLEAR`
(0x02), `TEXT_SET_LINE` (0x03, `[line][icon][ASCII…]`), `TEXT_PLAYBACK`
(0x04). One line per packet — 32 raw-HID bytes leave ~27 for text, and that
constraint is what let the design skip offsets/commits/framing. Torn updates
are harmless; the producer polls every 3 s.

- **The two lines have different budgets**: line 0 sits beside the 14px
  transport-icon gutter → 19 chars; line 1 starts at `TEXT_X2` → 21.
  `DISPLAY_TEXT_MAX_L0/_L1` in display.h, mirrored by `MAXLEN` in
  `hostagent/ak820text.py`. The producer puts the ARTIST on line 0 and the
  TITLE on line 1 (title gets the wider line).
- **The menu's Font setting picks the face** (10-28,
  [`plans/MENU-8X16-PLAN.md`](../plans/MENU-8X16-PLAN.md)). Small is Cozette
  6×14 from the flash atlas, as above. Large, the default, is Terminus Bold
  cropped to 8×14 (its rows 1-14, everything ASCII inks but the backtick's
  top). It draws from the menu's own table in internal flash through a
  pseudo font id, `LCD_FONT_SONG_LARGE` (0x0816), which `lcd_bus.c` sends
  by `lcd_blit_mono`, a glyph a pass as the queue paces. So no asset is
  added and no board is re-provisioned. Large gives the artist 14 characters
  and the title 15. The third face (10-28), Terminus regular, is the same
  cell from its own table through `LCD_FONT_SONG_REGULAR` (0x0817), with
  Large's budgets. The menu calls the three 8px, 10px and 10px bold. In
  10px only the artist is regular: the title (line 1, or line 0 alone) stays
  Bold, as the menu's page titles do.
  - **The text is kept whole and cut when drawn** (`graphics/text_fit.c`):
    the host still sends 19 and 21, and a change of face shows more or less
    of the same text without a resend.
  - **A change of face repaints the lines** (`display_text_refont()` sets
    `text_dirty`; `queue_line` treats the new font id as a moved run). That
    holds even with the menu closed, as when `flash.sh` restores the live
    settings.
  - Since the 10-28 spacing (line 1 at y 42, the clock 2 rows down), a
    descender above the next line's capitals leaves two blank rows in
    Large, four in Cozette.
- Single-line text keeps the adaptive size: ≤ `TEXT_BIG_MAX` (11) chars uses
  the 20px face, whatever the Font setting.
- Icons: `0 none, 1 play, 2 pause, 3 stop` — icon IDs, not "media state".
  Each is a 12×12 RAM tile sent in one transfer since flash 2e (it was
  `lcd_fill_rect` runs, ~9 ms for play).
- Non-ASCII becomes `?` in firmware; the host transliterates first.
- **Expires after 3 min** (`DISPLAY_TEXT_TIMEOUT_MS`) so a dead agent leaves
  a blank slot, not last night's track.
- **Optimistic play/pause**: `KC_MEDIA_PLAY_PAUSE` flips the icon
  immediately; the next host poll overwrites with truth. Returns `true` (the
  key must reach the host) and does not touch the liveness stamp.
- **NOT A BUG: a track from hours ago is usually correct** — the producer
  pushes on `paused` too, so an open player keeps reporting its last track.
  The expiry only fires when nothing refreshes the slot.
- No scrolling, deliberately: a marquee would keep the flash→LCD DMA busy at
  10 Hz — the same resource the eeconfig-write freeze was about.

**Host side** (outside the QMK clone): the producer is the Rust daemon
`ak820-agent` on both platforms, polling every 3 s and re-pushing unchanged
text every 30 s. On Windows it reads SMTC, the OS media-session API, so
browsers appear too. On macOS (JD's Mac since 2026-09-16) it reads
MediaRemote, macOS's private now-playing framework, through a helper dylib
hosted by `/usr/bin/perl` (`ak820-agent/helper/`), so browsers appear there
too; it falls back to AppleScript for Music and Spotify when MediaRemote
reports nothing for a running player. Its text packets are
byte-identical to `hostagent/ak820text.py`'s (`scripts/gen_ascii_fold.py`
checks the folding). The older producers stay in `hostagent/` as the fallback:
`ak820text.py` (dumb pipe) driven by `nowplaying-macos.sh` (AppleScript
against Spotify/Music only, LaunchAgent `com.jdlien.ak820pro.nowplaying`, log
`~/Library/Logs/ak820pro-nowplaying.log`; under launchd the Automation consent
prompt may not surface and queries silently return empty) or by
`nowplaying-windows.py` (SMTC).

## Clock band format: 24h / 12h / off / date (`Fn`+`C`, persisted)

`Fn`+`C` (`CLK_MODE`, also assignable in VIA) cycles **24h → 12h → off →
date**; the param overlay confirms (`Clock 12h`). Stored in kb_eeconfig as
the fifth byte (`clock_mode+1`, block grown from 4 to 5 with a data-version
bump, 2026-09-01; the enum is append-only because the value is persisted).
Display-only: `rtc/` still keeps the time.

- **date** is `Sep 1, 2026` in the 20px face; 12 cells max, redrawn at
  midnight. (This note once said the 30px atlas has only digits and the colon.
  It holds all 95 ASCII glyphs, but the crop to the clock's ink cut every
  descender, so `Sep` would lose its `p`'s tail: `display.c`, at `CLOCK_Y`.)
  The comma is a full 10 px cell — monospace, and the band's diff scheme assumes
  `x + i×advance`, so per-glyph kerning is deliberately not attempted. A
  two-line time+date mode was considered and **does not fit**: a 20px cell
  (23 rows) over a 13px cell (14 rows) is 37 rows in a 23-row band.
- **A format change relayouts, it does not wipe.** The first version forced
  a whole-band clear and the digits arrived one per main-loop pass — a
  visible black flash (the wipe-was-the-flicker lesson again). Now
  `queue_line`'s *moved* path clears only the columns the old run vacates
  when the row and face are unchanged, so the old digits stay up until each
  cell is overwritten; what remains is a ~30 ms left-to-right ripple. Only
  an owner change (playback) still clears the band whole, and that single
  clear now marks the slot known-empty (`shadow_mark_empty`) instead of
  letting the unknown path clear the full width a second time.

- **12h** drops the leading zero (`H:MM:SS`, 7 cells for 1-9, 8 for 10-12)
  and adds a **6 px stacked `A`/`M` or `P`/`M`** in light grey (`#CCCCCC`, a hair off white: mid grey was near-illegible at 5×7) right of the
  digits: 1 px bearing + 5 px ink, two 5×7 capitals with a 2-row gap,
  centred on the digits' 22 rows. That is how it fits: 8 cells + glyph is
  126 of 128 columns, and the layout sits 2 px left of centre so the ink
  stays out of the bezel-clipped columns 126-127.
- **The letters are rasterised from 5×7 bitmaps into one 5×16 RAM tile
  and pushed with a single `lcd_blit_ram`**: the atlases cannot draw grey,
  and a new atlas PNG would shift asset ids (fonts-assets.md). Two stacked
  6×14 Cozette cells would also be 28 rows in a 22-row face. ⚠️ The first
  version drew them as ~28 `lcd_fill_rect` runs like the padlock, and the
  profiled build put that at **~24 ms for 160 pixels** — every rectangle
  pays an 11-byte window command sent byte by byte through `spiSend`. The
  tile is one window and one send; the 12h transition went from 40 ms to
  7 ms. Prefer a RAM tile over rectangle runs for anything bigger than the
  padlock.
- **The glyph is outside the glyph queue's shadow**, so it keeps its own
  (`ampm`: x, letter). It is cleared before it moves (7↔8 cells at 9:59:59
  → 10:00:00), flips (noon, midnight) or goes away — a handful of times a
  day; the per-second path never touches it. Its clear never invalidates
  the clock run's shadow because the glyph starts exactly where the run
  ends and the overlap test is half-open. Every whole-band clear goes
  through `clock_band_clear()` so the two shadows cannot disagree.
- **off** clears the band once; the playback timer still takes it while
  playing. A forced clock-band repaint (mode or owner change) now paints on
  the next 10 Hz tick instead of waiting for the second edge.

## Playback position (replaces the clock while playing)

`2:34/18:45` in the clock band from `TEXT_PLAYBACK`
(`[state][pos16][dur16]`, whole seconds). The firmware advances the timer on
the 1 Hz tick; the host re-asserts absolute position each poll. Only the
PLAYING state takes the band; the media key **freezes** it immediately
(`display_playback_key()`) — position doesn't change while paused, so the
held value stays correct. Expires after 20 s (`PLAYBACK_TIMEOUT_MS`). Font
drops to 13px only past an hour (`H:MM:SS` doesn't fit at 20px); the 20px
cell borrows one row from the gap below — `CLOCK_BAND_H 23` must cover
everything either owner draws.

⚠️ **Duration units differ by app: Music reports SECONDS, Spotify
MILLISECONDS.** Wrong handling shows a 3-min track as 3 s and looks exactly
like a firmware bug. ⚠️ Browser media is invisible (no scripting
dictionary); the only route is the private MediaRemote framework,
deliberately not used.

## The animation slot (stock, orphaned, empty)

`Fn`+`Delete` (`ANIM_TOG`) plays full-screen frames from external flash
(`ANIM_BASE 0x540000`, 32 KB stride, 100 ms/frame, ceiling 244 frames).
While running it owns the SPI bus — dashboard suspended, RTC polling stopped
(the bit-banged RTC I2C shares port A with the flash SPI pins).

On this board the header reads **zero frames** (probed via `flash crc`:
header CRC = CRC of 256 zero bytes, with orphaned stock frame data below it),
so it is a no-op — `anim_toggle()` reads the header BEFORE pausing the
dashboard (it used to blink the screen black for ~1 s doing nothing). There
is NO validation beyond the zero count; a bad header paints garbage.
Provision with `mkanim.py` (GIF → blob) if ever wanted; the region is below
`FLASH_ASSET_BASE`, so `ak820ctl` needs `--unlock` to write it.
