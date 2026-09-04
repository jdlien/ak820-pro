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
27..54    text (2 lines)     28   two 6x14 cells, at 27 and 41
55        gap                 1
56..77    clock              22   Regular-30, CROPPED to its ink
78..81    gap                 4
82..104   lock band          23   20px face
105..127  battery            23   20px face
```

- **A glyph blit paints its WHOLE cell, background included** — no
  transparency, no tinting (colour exists only via `lcd_fill_rect`). Cells
  cannot overlap; two lines cost exactly 2× the cell height.
- **Spacing is judged by INK, not band boundaries** — the 20px cell carries 4
  blank rows above caps and 4 below baseline, so "move a band 1px" is never
  one constant (balancing the lock row took three coupled moves). Measure
  ink-to-ink: icons→text 2, text→clock 2, clock→lock 8, lock→batt 8.
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
  exactly this and made the keyboard untypeable — the owner's bug report was
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

Full-panel diagnostics, nine rows in the 6×14 face, toggled with `Fn`+`D`.
**Tap toggles; hold ~800 ms resets the counters** (fires under the finger, not on
release — see `bt_ui.c` for why that distinction matters).

```
uptime      2m 14s     ISR       73% 3900   ← occupancy + rate; field rate = /18
rowgap      6ms r1     ← worst gap between looks at one key row. THE loss metric
stall   25:0 10:3      ← 25 ms can lose a press; 10 ms is the leading indicator
worst      22ms blit   ← how big, and what caused it (flash/blit/i2c/-)
scan/s         346     BT drop        0     ← non-zero = a keystroke never sent
BT t/o    352 49%      battery 100% min 100 ← min answers "is the % real?"
```

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
not the page. While the restore runs, `display_housekeeping_task()` stands aside
(it gates on `debug_exit_step`); that gate is safe only because the pump is
called from its own site in `housekeeping_task_kb()` — the gate's comment says
why, do not fold the pump into the housekeeping task.

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

- "WIN", not "GUI": the label names the only context where GUI-lock is
  meaningful (Windows fullscreen gaming). Accessor stays `lock_state_gui()`.
- The padlock is drawn from rectangles because glyphs have no colour.
- Fn detection: `FN_LAYER_MASK` in `indicators.c`, built from the shared
  layer enum in `ak820pro.h` (`WINFN`/`MACFN`).

## Battery row

Icon bottom-left (outline + independent fill), percentage right-aligned to
`PANEL_WIDTH - 4`. Green >50%, amber 21-50%, red ≤20%; **charging overrides
with cyan** on outline and fill, plus a 9×14 bolt while actively charging
(`CHRG` low AND `STDBY` high — full-and-plugged-in is "done", no bolt). Fill
rounds up so 3% doesn't read as dead. Redraw triggers on charging state as
well as level. Drawing diagonals: rasterise a polygon and emit horizontal
runs — hand-placed zigzags read as the digit "4".

**Runtime estimate: considered and rejected.** 1% ≈ 1.2 h, RGB swings draw
5-10×, board lives plugged in — it would be confidently wrong. `5C <pct>` is
all the module reports.

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
- Single-line text keeps the adaptive size: ≤ `TEXT_BIG_MAX` (11) chars uses
  the 20px face.
- Icons: `0 none, 1 play, 2 pause, 3 stop` — icon IDs, not "media state".
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

**Host side** (`hostagent/`, outside the QMK clone): `ak820text.py` (dumb
pipe), `nowplaying-macos.sh` (polls Spotify/Music every 3 s; checks
`is running` first so it doesn't launch the app). Installed as a LaunchAgent
(`com.jdlien.ak820pro.nowplaying.plist`, KeepAlive + ThrottleInterval 30; log
`~/Library/Logs/ak820pro-nowplaying.log`). AppleScript needs Automation
permission — under launchd the consent prompt may not surface and queries
silently return empty. AppleScript, not MediaRemote: app-specific (no
browser/YouTube media) but stable across OS versions; a Windows producer
could use SMTC and send the same bytes.

## Clock band format: 24h / 12h / off / date (`Fn`+`C`, persisted)

`Fn`+`C` (`CLK_MODE`, also assignable in VIA) cycles **24h → 12h → off →
date**; the param overlay confirms (`Clock 12h`). Stored in kb_eeconfig as
the fifth byte (`clock_mode+1`, block grown from 4 to 5 with a data-version
bump, 2026-09-01; the enum is append-only because the value is persisted).
Display-only: `rtc/` still keeps the time.

- **date** is `Sep 1, 2026` in the 20px face (the 30px atlas has only
  digits and the colon); 12 cells max, redrawn at midnight. The comma is a
  full 10 px cell — monospace, and the band's diff scheme assumes
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
