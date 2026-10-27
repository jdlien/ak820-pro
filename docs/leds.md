# LEDs: interrupt priorities, the RGB field rate, indicators, and the rainbow

Driver: `drivers/led/sn32f2xx.c` (QMK core, carries local commits). The board
is COL2ROW — PWM on the columns, the 18 hardware "rows" (6 key rows × R,B,G)
are the mux.

## ⚠️ Interrupt priority ordering — the single most important tuning fact

The ChibiOS defaults had this inverted and it caused two apparently unrelated
bugs. Set in `mcuconf.h`; on Cortex-M0 a LOWER number is HIGHER priority.

| Prio | Source | Why |
|---|---|---|
| **0** | `SN32_SERIAL_UART2` | CH582F link — the only peripheral where being late LOSES DATA. Its receiver holds about one byte, so it must be served within ~87 µs. 1 until 10-19 (`11cea91370`, `plans/UART-LATENCY-PLAN.md`). |
| 0 | `SN32_ST` (system timer) | Stated in `mcuconf.h`: the stock 8 truncated to 0 in the 2-bit field. It and UART2 cannot pre-empt each other. |
| 1 | `SN32_USB` (driver default) | Up to ~0.085 ms a handler. It shared UART2's level until 10-19, which is why UART2 went to 0. |
| **2** | `SN32_GPT_CT16B3` | Backlight/indicator PWM tick — must be regular or the display flickers. |
| **3** | `SN32_PWM_CT16B0/1/2` | RGB row scan — long and frequent, but µs of LED jitter is invisible. |
| 3 | `SN32_SPI_SPI0` (driver default) | LCD SPI and its flash→LCD DMA completions — shares the row scan's level. |

⚠️ **SPI0 sharing priority 3 with the row scan is load-bearing timing, not
an accident to "fix" in passing.** Equal priorities do not pre-empt each
other, so a DMA interrupt raised while a row ISR runs (~188 µs) waits for it:
the half-transfer handler of a DMA armed from the main loop runs 188–258 µs
after the arm. That window is what exposed a race in the SPI0 handler to
660-byte clock-digit transfers only, until it was fixed (ChibiOS
`c57623d0d2`; `plans/FIRMWARE-FINDINGS-2026-09-23.md`). If SPI0's priority
or the row ISR's length ever changes, the exposed transfer sizes move too.

⚠️ **The same shared level dims the LEDs during CPU-fed SPI0 writes**
(measured on gremlin, 10-23/24). `lcd_fill_rect`, `tx_pixels`
(`lcd_blit_ram`) and the stream go through `spiSend`, which takes SPI0's
RX-FIFO interrupt every ~3 µs at priority 3. A row ISR raised meanwhile
starts late, and because it re-arms at its end, every late start lengthens
the row period. The config menu's fixture repaints cost 18% of the row
refreshes, enough to see the keyboard flicker. The DMA'd glyphs and the
black clears from flash cost nothing (~0.3% for the `Fn`+`D` page and the
restore). The mainline's colour fills are small (the battery outline and
fill, the padlock, the bolt, the AM/PM tiles), so its exposure is brief. A
fix that feeds SPI0's FIFO from the main thread with the interrupt masked
(`gremlin/fill-poll` `f2b107be`, codex cleared it,
`plans/review-codex-spi0-poll-2026-10-24.md` on `warren/config-menu`) cut
that to 1.3%. It is not on the mainline.

What each wrong ordering did (all measured): UART at the bottom → mangled
frames both directions (ACK timeouts, dropped keystrokes, dropped `5B 32` =
the digit-blink bug — one cause chased as two bugs for hours). GPT below the
row scan → 23% of PWM ticks lost (15,385 Hz vs 20,000), backlight flicker
worse when dim. GPT above the UART → tick restored but ACK timeouts tripled.

Result with the correct ordering, measured at the HIGHEST row-ISR rate
(18,800/s): **0.042 ACK timeouts/frame vs 0.38 at stock rate with the
inversion** — the ISR rate was never the fault, only a proxy. **If Bluetooth
regresses, check this table FIRST; do not lower `SPD_STEP`.** Measure over a
sustained typing burst — boot traffic (~0.58/frame) makes a healthy board
look broken.

## RGB field rate — decoupled from the UI steps (2026-08-31)

The SonixQMK driver derived its PWM clock from the product of the UI step
sizes (`HUE_STEP * SAT_STEP * VAL_STEP * SPD_STEP * LED_PROCESS_LIMIT`) — a
wart that made changing a step size silently retune the LED field rate, and
forced two rounds of step-trading. **That coupling is FIXED**:
`SN32F2XX_RGB_PWM_FREQ` (commit cba2c1e19e) pins the PWM clock in config.h at
**4.8 MHz**, and the steps are now free (`SPD_STEP 4`, `HUE_STEP 8`,
`SAT_STEP 32`). Do not re-derive step trades from old notes.

The timer's arithmetic — **NOT the real field rate.** Measured 2026-09-03 at
**215 Hz** (health page 4): `rgb_callback` re-arms the counter at its END, so
its own ~188 µs body sets the period. See "CPU budget" below and
`docs/hardware.md`. **Derived baseline, never measurable again:** before the
2026-09-03 matrix publish fix the ISR scanned a row ~344 times/s instead of
~1,292, which solves (160 µs body, ~84 µs scan, ~70 µs overhead) to ~4,220
ISR/s → **~235 Hz**. The fix cost ~8% of field rate; JD reports no
flicker.

```
field rate = eff_clock / periodticks / 18 rows = 4.8e6 / 255 / 18 = 1046 Hz
```

(vs 121 Hz stock — the DLP-rainbow knob). All 256 brightness levels retained
(`periodticks = 255`).

**Traps if tuned further:**

- `periodticks` is also the `val` ceiling and the driver feeds the raw colour
  byte in as duty — halving it doubles the rendered brightness of every
  STORED val (EEPROM survives a flash). Scale `RGB_MATRIX_DEFAULT_VAL` with
  any ceiling change. Do not spend `periodticks` for field rate — it is the
  dimming granularity the whole exercise preserved.
- Core fix (upstreamable, committed): `periodticks = MAXIMUM_BRIGHTNESS + 1`
  — `pwm_lld_start` writes `period - 1`, so a full-value channel wrote
  `MR = 255` against a counter resetting at 254: a match that never fires,
  blanking the channel at exactly 100%.
- More field rate: the PWM clock is NOT the lever at all. `rgb_callback`
  re-arms the counter at its END, so its period is (body + ~70 µs), and the
  body is 160 µs before it even scans a row — 30 `pwmEnable/DisableChannel`
  calls through the ChibiOS API at ~5 µs each. Measured 2026-09-03: 3,876
  ISR/s, 215 Hz field rate, 72.8% of the CPU (health page 4,
  `ak820health.py --isr`). The only way up is a cheaper ISR body (direct
  register writes instead of the API): a driver rewrite, not a constant.

## CPU budget (measured)

| Row ISR | Matrix scan | Notes |
|---|---|---|
| 2,189/s | 1396 Hz | stock |
| 18,800/s | ~390-400 Hz | what the timer arithmetic predicted — never measured |
| **3,876/s** | **~335 Hz** | **measured 2026-09-03**, health page 4: body 188 µs mean (160 LED-only, 261 with the row scan), **72.8% of CPU**, field rate **215 Hz** |

~38,800 interrupts/s total with the 20 kHz GPT. Typing feels "nearly
instant" even over BT — latency is dominated by switch travel and debounce.
First thing to back off if typing ever regresses: the PWM clock (field rate),
not anything else.

**Retracted 2026-09-03: the ms timebase is NOT slow** — `ak820health.py --isr`
reports `timebase_vs_wall` 1.0001–1.0004; the system timer is a free-running
CT16B5 counter and cannot lose ticks. The note that follows is kept for the
canary logic only. ~~The ms timebase runs ~1.2% slow at this load.~~ A
`[pwmtick]` instrument reading above 20,000 Hz means `timer_read32()` lost
systick interrupts (the timer cannot speed up). Benign today (clock and trim
don't use it; debounce becomes 5.06 ms) — but a rising number is the first
sign the board is out of CPU. Cost scales worse than linearly (M0 ISR
entry/exit dominates).

## The 20 kHz GPT tick (backlight + indicators)

CT16B3 (`GPTD4`), set up in `pwm_tick_init()`. Needs three things; the third
is not obvious:

1. `halconf.h`: `HAL_USE_GPT TRUE`.
2. `mcuconf.h`: `SN32_GPT_USE_CT16B3 TRUE` + priority 2.
3. **`SN_CT16B3->MCTRL = CT16_PWM_UNLOCK(... | mskCT16_MRnRST_EN(0));` after
   `gptStartContinuous()`** — the SN32 GPT LLD never sets reset-on-match, so
   without it the timer fires ONCE and the counter runs away. Symptom: the
   backlight blinks at full brightness every ~4-5 s and is otherwise black —
   looks exactly like a brightness bug and is not one.

This tick decoupled the backlight/indicators from `SPD_STEP` entirely — old
notes describing a three-way coupling describe a dead design.

## Indicator LEDs (Caps D15 / Win Lock C15 / Charging B18)

Plain GPIOs, software-PWM'd on the GPT tick (`indicators.c`), per-LED levels
`ind_duty[] = {0,1,2,3,5,8,12,18,28,48}`. `INDICATOR_BRIGHTNESS_DEFAULT 1`;
`CHARGING_LED_BRIGHTNESS 0` (the battery icon shows charging).

- **`IND_PWM_TICKS 48` → 417 Hz, floor 2.1% — current.** The old 96-tick
  (195 Hz) figure was tuned against a tick silently dropping 23% of its
  interrupts (the priority inversion); with a steady 20 kHz, 48 is
  flicker-free. At these duties the LED is lit one tick per period, so
  dimmer = slower — **if flicker returns, shorten `IND_PWM_TICKS`** rather
  than touching the RGB config.
- `phase < duty` handles both ends: duty 0 never fires, duty == period is
  always on.
- **Caps had to be claimed from QMK core**: `led_update_kb()` returns
  `false` so `led_update_ports()` doesn't drive the pin; the `indicators`
  entry in keyboard.json is KEPT (it defines the pin and inits it as
  output).

## ⚠️ LED glitches during RGB adjustment — three distinct causes, all fixed

All looked like "the LEDs flash wrong while adjusting"; timing and colour
tell them apart. Do not merge them.

1. **One row briefly a WRONG COLOUR (fixed 2026-08-31):** `sn32f2xx_flush()`
   memcpy'd `led_state[]` while the row ISR read it — a torn frame, spatially
   localised to one row (the tell). Now wrapped in `chSysLock()` (~10-16 µs
   vs a 53 µs ISR period). Hold-to-repeat made a long-latent race visible.
2. **A brief DARK flash:** QMK's eeconfig flush is a RATE LIMIT, not a
   debounce — it fires every `RGB_MATRIX_EEPROM_WRITE_DELAY` (750 ms)
   *throughout* a held key, and each internal-flash write blanks the matrix
   (item 3's guard; the account below). This item once said the write "stalls
   the row ISR"; it does not.
   `rgb_matrix_eeprom_flush_allowed()` now also waits for the values to stop
   moving (`RGB_SETTLE_MS` 900) — one write after you settle.
3. **One row at ~18× brightness during a flash program (fixed
   2026-09-01, hardening):** the `EFLD1.state != FLASH_PGM` guard in the row
   ISR skipped the PWM update but left the previously-selected mux row
   ENERGIZED for the whole program operation. The fix de-selects every row pin in
   that branch (ISR-safe; `sn32f2xx_blank()` is NOT ISR-safe — its
   `pwmDisableChannel` is not I-class). Verified by eye through sweeps and 15
   forced eeconfig writes. (This item, and the guard's comment in
   `sn32f2xx.c`, said the row was frozen by "masked" windows: see below.)

### What an internal-flash write does to the LEDs (corrected 2026-10-04)

Codex caught it in the Phase 1b plan review, and `hal_efl_lld.c` confirms it:
**interrupts are NOT masked for the whole write.**

- They are masked only across each **per-line program window**, tens of µs
  (the datasheet: 10 µs typical, 20 µs maximum per 64-bit program). The
  vector table and every ISR live in flash and the M0 has no VTOR, so an
  interrupt inside a program window would fetch its handler from an array
  mid-program: that was a hang.
- **Page erase** (1-2 ms per 1 KB page) is **not masked**: that long would
  starve UART2, the CH582F link, where late means lost data.
- Between those windows the row ISR keeps running. While the flash driver is
  in its program state it **de-selects every row**: item 3's guard. That is
  the whole-board dark blink JD sees, for as long as the write lasts. Its
  length is unmeasured; the longest flash-marked main-loop interval on run 2
  was 7 ms, and that includes the DMA drain before the write.

⚠️ **Never mask interrupts around the whole operation** to hide the blink: the
driver's comment says why (UART2). Make fewer writes instead. Since Phase 1b's
C2 the board makes ~3 a day outside the battery level's milestones
([battery.md](battery.md), "Internal-flash writes"). The LCD's one bright flash
during a write (10-01) has a hypothesis, a page erase freezing the backlight
PWM in its last state, which is untested; no guard is built.

### The blink is the consolidation, and the board now scans through writes (2026-10-27)

A dev build's Diagnostics → **Write test** page compared the two strategies
by eye on JD's Solid near-white
([plans/BACKLOG.md](../plans/BACKLOG.md), "The LED blink at an
internal-flash write"):

| | Blank (item 3's guard) | Scan (straight through) |
|---|---|---|
| One write, Ten writes | nothing | nothing |
| Cleanup (a consolidation) | "a very noticeable flicker" | "a more subtle flicker" |

- **An ordinary write never showed.** The blink JD sees is the
  wear-levelling **consolidation**: the 2 KB backing store erased and the
  1 KB cache programmed back, ~58 ms in one pass, when a write fills the log.
- **The scan through a program is the default since `4ee668eb`**
  (`sn32f2xx_pgm_scan`, `drivers/led/sn32f2xx.h`). Item 3's guard stays
  only for the test page to compare. The scan's row is at most a masked
  window late, 10-20 µs.
- **What scanning leaves is the erase.** Two pages, 1-2 ms each, stall the
  CPU and the row ISR with it ([sn32f299.md](sn32f299.md), p. 251), so
  the selected row holds while the rest go dark. Neither strategy touches it.
- **So the board cleans up early, where nobody sees it**
  (`flash_tidy.c`, since `4ee668eb`). Once the log is half full, it
  consolidates when the committed frame is dark and nothing has been
  pressed for 30 s, or after 10 min without a key on USB or in Always on.
  A full log still consolidates where it fills, now only after half a log
  of writes without a pause. HC_FLASHW page 4 reads the log's fill and the
  cleanups. ⚠️ Every consolidation erases the only copy before writing it
  back, so a power loss inside one loses the settings and the keymap. Half,
  not a quarter, holds the early ones to at most twice the count (codex).

## The rainbow is a GEOMETRY problem, not flicker

R, B, G light in separate time slots (`ROW_CHANNELS 3`), so saccades separate
the fields. Flicker-fusion intuition does not apply: fringe width scales
LINEARLY with field rate, no threshold.

```
field rate   slot gap   fringe @200 deg/s
   121 Hz     2755 µs        33.1'    stock
  1046 Hz      320 µs         3.8'    the timer's arithmetic — never real
   215 Hz     1550 µs        18.6'    MEASURED 2026-09-03 (health page 4)
  4000 Hz       83 µs         1.0'    ~invisible — needs ~4x, past this M0
```

**⚠️ Colour choice is a free 2×, bigger than any achievable frequency
change.** Slot order is R → B → G: white/warm-white spans the full cycle
(worst); **amber (R+G) is the worst two-channel colour** (2 gaps); magenta
(R+B) and cyan halve it; a single saturated channel has NO fringing at all.

If the LEDs ever stop being worth their cost: `ROW_CHANNELS` is a parameter,
but the ISR fires per PWM *period*, not per row — cutting channels 3→1
triples the field rate instead of cutting CPU; cutting CPU needs a slower PWM
clock, which single-colour can then afford. Untested; effects would render
only their red component.

## RGB effects

Enabled (keyboard.json, then the two board-local ones; `Fn`+`\` steps
through them in this order): `solid_color alphas_mods cycle_all
cycle_left_right cycle_up_down jellybean_raindrops typing_heatmap RAINFALL
DRIFT`.

- **Alphas/Mods needed LED FLAGS**: keyboard.json splits 48 alphas from 33
  frame keys (`flags: 5`); without it the effect looks like solid_color.
  **Its second colour is the SPEED value** (`hsv.h += speed`), so `Fn`+`-/=`
  is the second-colour dial and the overlay reports `2nd +180` there.
- **`RAINFALL` is board-local** (`rgb_matrix_kb.inc`): per-LED decay with
  random seeds; speed sets the DROP RATE. It exists because no stock effect
  fades a random key out — `PIXEL_RAIN` is a static scatter,
  `STARLIGHT*` keep the whole board lit. Do not swap it out expecting the
  same look.
- **`DRIFT` is board-local too**: a slow plasma, a scrolling value-noise
  field mapped onto a hand-picked ramp (dark indigo, violet, slate, warm
  grey), weighted dark, so a few soft blobs drift across a mostly dark
  board. Hue rotates the whole ramp and saturation washes it toward grey;
  speed runs from minutes to cross the board to ~7 s. Its palette is cached
  and converted once per hue or saturation change, and **the user's value
  scales the colours after the conversion**, linearly, unlike every other
  effect.
- **The power ladder's ceilings** (the dim's 64, Power saver's 128 while
  typing, [battery.md](battery.md), "The idle ladder and the power modes")
  act in the conversion, `rgb_matrix_hsv_to_rgb`, so every effect is capped
  there, RAINFALL included. DRIFT is the exception: its palette is built
  uncapped and it caps its own value knob instead, so a capped DRIFT looks
  like DRIFT with the knob at the ceiling (`scripts/battery_sim/colour.c`
  checks it frame for frame).
- Traps: custom effects are `RGB_MATRIX_CUSTOM_<NAME>` in the enum; reactive
  effects need `RGB_MATRIX_KEYPRESSES` or they compile out **silently**;
  `nm` LIES about whether an effect got built (static + inlined) — the proof
  is a `case RGB_MATRIX_*:` compiling under `-Werror`.

Default: dim warm white (`hue 21, sat 140, val 64` in keyboard.json), though
EEPROM holds whatever was last set.
