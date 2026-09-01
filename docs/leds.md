# LEDs: interrupt priorities, the RGB field rate, indicators, and the rainbow

Driver: `drivers/led/sn32f2xx.c` (QMK core, carries local commits). The board
is COL2ROW — PWM on the columns, the 18 hardware "rows" (6 key rows × R,B,G)
are the mux.

## ⚠️ Interrupt priority ordering — the single most important tuning fact

The ChibiOS defaults had this inverted and it caused two apparently unrelated
bugs. Set in `mcuconf.h`; on Cortex-M0 a LOWER number is HIGHER priority.

| Prio | Source | Why |
|---|---|---|
| **1** | `SN32_SERIAL_UART2` | CH582F link — the only peripheral where being late LOSES DATA. |
| **2** | `SN32_GPT_CT16B3` | Backlight/indicator PWM tick — must be regular or the display flickers. |
| **3** | `SN32_PWM_CT16B0/1/2` | RGB row scan — long and frequent, but µs of LED jitter is invisible. |

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

Current math (still true):

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
- More field rate: the next lever is NOT a faster PWM clock alone — the row
  ISR would hit ~37,600/s, past what this M0 has left. Buy headroom first by
  halving the GPT tick to 10 kHz (costs backlight switching rate, no field
  rate).

## CPU budget (measured)

| Row ISR | Matrix scan | Notes |
|---|---|---|
| 2,189/s | 1396 Hz | stock |
| 18,800/s | **~390-400 Hz** | current, field rate 1046 Hz |

~38,800 interrupts/s total with the 20 kHz GPT. Typing feels "nearly
instant" even over BT — latency is dominated by switch travel and debounce.
First thing to back off if typing ever regresses: the PWM clock (field rate),
not anything else.

**The ms timebase runs ~1.2% slow at this load — a saturation canary.** A
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
   *throughout* a held key, and each internal-flash write stalls the row ISR.
   `rgb_matrix_eeprom_flush_allowed()` now also waits for the values to stop
   moving (`RGB_SETTLE_MS` 900) — one write after you settle.
3. **One row at ~18× brightness during masked flash-program windows (fixed
   2026-09-01, hardening):** the `EFLD1.state != FLASH_PGM` guard in the row
   ISR skipped the PWM update but left the previously-selected mux row
   ENERGIZED for the whole masked window. The fix de-selects every row pin in
   that branch (ISR-safe; `sn32f2xx_blank()` is NOT ISR-safe — its
   `pwmDisableChannel` is not I-class). Verified by eye through sweeps and 15
   forced eeconfig writes.

## The rainbow is a GEOMETRY problem, not flicker

R, B, G light in separate time slots (`ROW_CHANNELS 3`), so saccades separate
the fields. Flicker-fusion intuition does not apply: fringe width scales
LINEARLY with field rate, no threshold.

```
field rate   slot gap   fringe @200 deg/s
   121 Hz     2755 µs        33.1'    stock
  1046 Hz      320 µs         3.8'    current
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

Enabled: `solid_color alphas_mods RAINFALL cycle_all cycle_left_right
cycle_up_down rainbow_moving_chevron cycle_pinwheel jellybean_raindrops
typing_heatmap`.

- **Alphas/Mods needed LED FLAGS**: keyboard.json splits 48 alphas from 33
  frame keys (`flags: 5`); without it the effect looks like solid_color.
  **Its second colour is the SPEED value** (`hsv.h += speed`), so `Fn`+`-/=`
  is the second-colour dial and the overlay reports `2nd +180` there.
- **`RAINFALL` is board-local** (`rgb_matrix_kb.inc`): per-LED decay with
  random seeds; speed sets the DROP RATE. It exists because no stock effect
  fades a random key out — `PIXEL_RAIN` is a static scatter,
  `STARLIGHT*` keep the whole board lit. Do not swap it out expecting the
  same look.
- Traps: custom effects are `RGB_MATRIX_CUSTOM_<NAME>` in the enum; reactive
  effects need `RGB_MATRIX_KEYPRESSES` or they compile out **silently**;
  `nm` LIES about whether an effect got built (static + inlined) — the proof
  is a `case RGB_MATRIX_*:` compiling under `-Werror`.

Default: dim warm white (`hue 21, sat 140, val 64` in keyboard.json), though
EEPROM holds whatever was last set.
