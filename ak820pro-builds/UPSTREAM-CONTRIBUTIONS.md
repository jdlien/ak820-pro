# AK820 Pro — what to contribute upstream

Written 2026-08-29, after a session that fixed Bluetooth throughput, LCD backlight
flicker, the LED field rate, and four wireless state-tracking bugs.

**The headline: the deviation from standard QMK is tiny.** Two core files, 27
lines. Everything else lives in `keyboards/a_jazz/ak820pro/`, which is fpb's
out-of-tree port — exactly where board work belongs.

Three destinations, and the split matters:

| Destination | What goes there |
|---|---|
| **SonixQMK** (`drivers/led/sn32f2xx.c`) | A real bug affecting every SN32 RGB board |
| **chibios-contrib** (SN32 GPT LLD) | `gptStartContinuous()` is broken on this platform |
| **fpb/qmk_firmware** | Board-level fixes: IRQ priorities, CH582F protocol, RTC |

---

## Tier 1 — genuine bugs, minimal, not opinionated

### 1.1 `periodticks + 1` → SonixQMK

`drivers/led/sn32f2xx.c`, one line.

`pwm_lld_start` writes the period match as `period - 1` and `pwm_lld_mr_value` is
identity. So with `periodticks == RGB_MATRIX_MAXIMUM_BRIGHTNESS`, the counter
resets at 254 while a full-value colour channel writes `MR = 255`. **That match
never fires**, the channel never asserts, and the LED goes dark at exactly 100%.

Symptom: colour lurches when brightness reaches maximum, and brief colour flashes
while stepping through it. Costs one extra tick per PWM period (measured field
rate 498 → 496 Hz, i.e. nothing).

**Affects every SN32 board using this driver**, not just this one. Best
value-to-effort ratio of anything here.

### 1.2 SN32 GPT LLD never sets reset-on-match → chibios-contrib

`os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_gpt_lld.c`.

In `gpt_lld_start_timer`, continuous mode sets only `mskCT16_MRnIE_EN(0)` — the
match *interrupt*. One-shot mode sets `mskCT16_MRnIE_EN(0) |
mskCT16_MRnSTOP_EN(0)`. **Neither ever sets `MRnRST_EN`.**

So a continuous GPT fires once and the counter runs away past the match value
instead of restarting. Every `gptStartContinuous()` user on SN32 is affected.

Board-level workaround currently in `pwm_tick_init()`:

```c
SN_CT16B3->MCTRL = CT16_PWM_UNLOCK(SN_CT16B3->MCTRL | mskCT16_MRnRST_EN(0));
```

The proper fix belongs in the LLD. Symptom is deeply misleading — the backlight
blinked at full brightness every few seconds and looked exactly like a brightness
bug.

### 1.3 Interrupt priority ordering → fpb

`keyboards/a_jazz/ak820pro/mcuconf.h`. **Probably the most valuable single change
here for other AK820 Pro owners.** The ChibiOS defaults are inverted, and it is
not unit-specific in any way.

| Prio | Source | Why |
|---|---|---|
| 1 | `SN32_SERIAL_UART2` | CH582F link. The only peripheral where being late means **losing data**. Defaulted to 3. |
| 2 | `SN32_GPT_CT16B3` | Backlight PWM tick. Tiny, but must be *regular* or the display flickers. |
| 3 | `SN32_PWM_CT16B0/1/2` | RGB row scan. Long and frequent, but µs of jitter is invisible on an LED. Defaulted to 2. |

Measured consequences of getting it wrong:

- **UART at the bottom** → row ISR preempts byte servicing. Outbound: ACK
  timeouts, TX queue overflow, dropped keystrokes — *you can out-type the link*.
  Inbound: dropped `5B 32` frames, i.e. the connection-digit blink bug. **Same
  root cause, both directions.**
- **GPT below the row scan** → 23% of ticks lost, measured **15,385 Hz against
  20,000 configured**. Reads as backlight flicker that worsens as it dims.
- **GPT above the UART** (an intermediate wrong fix) → tick restored to 19,997 Hz
  but ACK timeouts tripled, 0.38 → **1.14 per frame**.

After the fix: tick **20,000 Hz ±8**, ACK timeouts **0.042/frame** across a
430-frame typing burst, zero dropped — at the *highest* row-ISR rate (18,800/s),
which previously "broke Bluetooth".

---

## Tier 2 — CH582F protocol fixes → fpb

All four are bug fixes, all verified with logic-level wire traces, none
unit-specific. `bluetooth/ch582f_ajazz.c`.

**The shared root cause is worth stating in any PR:** this protocol has no
acknowledgements, no way to query state, and one-shot announcements. Every
command is fire-and-forget, so a single dropped message strands the firmware with
no recovery path. Each fix has the same shape — treat a command as pending until
the module *demonstrates* it acted.

### 2.1 Media keys silently dead over Bluetooth

`bluetooth_send_keyboard()` sends `0xA1` unconditionally, but
`bluetooth_send_consumer()` was gated on `is_module_connected`. Whenever the
driver was stranded in `LINKING`, typing worked and **the volume knob did
nothing**. That asymmetry is why it read as "Bluetooth mostly works".

Fix: gate on `connect_requested` only, matching the keyboard path.

### 2.2 Missed `5B 32` strands the driver in `LINKING`

`5B 32` is the *only* connected signal and is sent **once**, never re-asserted.
`5B 23` (idle) is emitted both connected and disconnected, so it carries no
information. One lost frame = permanently wrong state.

Fix: promote `LINKING` → `CONNECTED` on a `5A` host-LED frame, gated three ways
(plausible bitmap, state is exactly `LINKING`, and `CH582_5A_PROMOTE_MS` = 3 s
dwell so a real `5B 32` would already have won).

Note the priority fix (1.3) addresses the *cause*; this is the backstop.

### 2.3 `A6 51` ignored while a connect attempt is in flight

Pressing a slot key issues a connect, so hold-to-pair fires straight into that
window and the single `A6 51` is dropped. Symptom: hold 1 s → nothing, 2 s →
nothing, 3 s → works. Reads as a timing threshold and is not one.

Fix: `pairing_pending` resends every `CH582_PAIR_RETRY_MS` (400 ms) up to
`CH582_PAIR_MAX_TRIES` (12), clearing on `5B 31` (confirmed), `5B 32`, or a new
selection.

### 2.4 `A6 <slot>` is a no-op while advertising

**Four hypotheses died here.** Worth reproducing in any PR so nobody re-derives
them:

| # | Hypothesis | Killed by |
|---|---|---|
| 1 | Lost UART frame | The module *replies* — with `5B 23` |
| 2 | Timing; retry until it takes | **8 selects over 10 s drew zero responses** |
| 3 | Retry on the idle event | It emits nothing at all while advertising |
| 4 | **Same-slot select is a no-op; a different slot is required** | Matches every trace |

The module ignores a select for the whole BLE advertising window — minutes.
Naming a *different* slot forces a state change immediately.

Fix — the cancel-pairing bounce. Pressing a slot key while that slot is
advertising sends another slot, waits `CH582_BOUNCE_MS` (700 ms), then sends the
real target. Recovery ~1 s, down from minutes.

⚠️ **Known trade-off, must be documented in the PR:** the bounce slot can briefly
*connect* (observed: `5B 32` on the bounce). Unavoidable — forcing the state
change requires naming another slot, the same exposure the manual workaround has.

### 2.6 `anim_toggle()` blinks the screen on an empty slot

Not a CH582F bug, but the same tier: small, obviously correct, and it affects
**any board whose animation slot was never written** — which is every board that
has not had one provisioned.

`anim_toggle()` paused the dashboard and flipped the panel orientation *before*
checking whether there were any frames, then undid both. `display_set_paused(false)`
forces a full repaint, so an empty slot blanked the whole screen for ~1 s and did
nothing. On this unit the stock header reads zero frames, so that blink was the
only thing `Fn`+`Delete` ever did.

Fix: read the 1-byte header first and return early. Safe there — the dashboard
does SPI1 flash reads constantly (every glyph goes through `lcd_draw_flash_text`).

### 2.5 Hold-to-pair fired on key-UP

`process_record_kb` checked the elapsed time in the *release* handler, so holding
did nothing visible until you let go — contradicting the code's own comment.

Fix: `bt_pair_hold_task()` on the housekeeping tick fires at the threshold while
the key is still down; press/release only arm and disarm.

---

## Tier 3 — real fixes, but check the docs first

### 3.1 RTC divider trim → fpb

`rtc/rtc.c`. **`config.h` and `rtc.h` both claimed this existed. It did not.**
They described calibration that "trims the divider so the clock self-locks on any
hardware"; `rtc_clock_discipline()` only ever called `rtcSetTime()` — a phase
snap. `rtc_lld_set_period()` existed and was never called.

Why it mattered: `SN32_RTC_CLK_SOURCE` is the internal RC oscillator with
`SN32_RTC_PERIOD_DEFAULT 32000` assuming exactly 32 kHz. This unit runs ~34.3 kHz
— ~4% fast, normal for an untrimmed RC. Snapping alone left ±5 minutes of
sawtooth per hour at the stock 3600 s interval.

Three traps, all hit, all worth documenting upstream:

1. **Restarting the measurement window on a phase snap** — the snap fires exactly
   when drift is large, so the trim never survived to take a second sample and
   **never ran once**. Needs a snap-immune window (`rtc_seconds_count` + the
   PCF's absolute time).
2. **Trimming on any nonzero difference** — the reference has 1 s resolution, so
   a 60 s window always shows ±1. It limit-cycled between the two adjacent
   quantised answers forever. Hence `RTC_CAL_MIN_WINDOW_S 300`,
   `RTC_CAL_MIN_DIFF_S 2`.
3. **Applying the full correction** — a quantisation-sized overshoot becomes a
   standing oscillation. Hence half-step damping.

⚠️ **`RTC_PERIOD_INITIAL 33400` must NOT be upstreamed as a default** — it is
this unit's measured RC value. Upstream it as a documented knob, seeded at the
nominal 32000, with a note on how to measure.

### 3.2 `rgb_matrix.c` eeconfig flush — CHECKED 2026-08-29, worth proposing

**Verified against upstream QMK master, not just fpb's fork.** Upstream
`rgb_task_sync()` is byte-identical to fpb's — `eeconfig_flush_rgb_matrix(false)`
— and `RGB_MATRIX_EEPROM_WRITE_DELAY` does not exist upstream at all. **fpb is not
behind**; this is a real deviation, not a stale-fork artifact.

The more interesting finding:

```
EECONFIG_DEBOUNCE_HELPER (quantum/eeconfig.h) generates:
    eeconfig_flush_<name>_task(uint16_t timeout)

Macro users:                    led_matrix, rgb_matrix
Callers of the _task variant:   NONE anywhere in the tree
```

**QMK built the debounce mechanism and never wired it up.** It is dead code
upstream, in both subsystems that use the macro.

That makes this a defensible core proposal with a genuinely safe default:

```c
#ifndef RGB_MATRIX_EEPROM_WRITE_DELAY
#    define RGB_MATRIX_EEPROM_WRITE_DELAY 0
#endif
```

At timeout 0, `timer_elapsed(flush_timer) > 0` is false only within the same
millisecond, so **the default is behaviourally identical to today** and boards opt
in with one define. It also cuts flash wear generally: RGB adjustment currently
writes eeconfig ~8x/second while a key is held, ≤1.3/s at 750 ms.

Pitch it as "wire up the debounce helper that already exists", not as a new
feature. The same one-line change applies to `led_matrix.c`.

**The weak `rgb_matrix_eeprom_flush_allowed()` hook is a separate argument** and
should be a separate PR, or dropped. It defaults permissive so nothing changes for
other boards, and the general case is real — any board whose flash program/erase
stalls instruction fetch (XIP, memory-mapped) has this problem, not just this one.
But it is a harder sell and should not be bundled with the debounce change.

---

## Tier 4 — offer, don't push

Genuinely nice, genuinely opinionated. Worth showing fpb as an *option*, not a
default:

- **LCD dashboard**: battery icon with charging bolt, lock/layer band, three-icon
  connection strip, wireless status band (`Pair with:` / `AK820 5.1-N`,
  `Connecting`, `Link failed` ⟷ `Hold Fn+E 2s`).
- **Backlight dimming**: software PWM on `PANEL_BKL` (A16), 12 perceptually-spaced
  levels. Note hardware PWM on that pin is **impossible** — `P0.16`'s only
  alternate function is `CT16B5_CAP0`, a capture input. Verified in the datasheet.
- **Host text slot**: `TEXT_CHANNEL 0x12`, one raw-HID packet, arbitrary line
  pushed from the host. Plus `hostagent/` producers.
- **LED field rate tuning**: `SPD_STEP 128` → 1046 Hz, which visibly reduces the
  DLP-rainbow artifact. **Only safe with the priority fix (1.3)** and it costs
  matrix scan rate (1396 → ~390 Hz). Propose as a documented option, not a default.

---

## Never upstream

| | Why |
|---|---|
| `MADCTL_DASH` (`0x68`) in `lcd_bus.c` | **This unit's LCD is mounted 180° from fpb's.** Would break his units. |
| `0x21` INVON in the init sequence | Same — this panel inverts, fpb's do not. |
| `RTC_PERIOD_INITIAL 33400` | Per-unit RC measurement, temperature-dependent. |
| RGB default `hue 21, sat 140, val 64` | Personal preference. |
| `DISPLAY_BRIGHTNESS_DEFAULT`, `INDICATOR_BRIGHTNESS_DEFAULT`, `CHARGING_LED_BRIGHTNESS 0` | Personal preference. |
| Bunny splash (`sonixqmk.png`) | JD's personal brand. |
| `keymaps/via/keymap.c` bindings, `via.json` customKeycodes | Personal layout. |

The LCD orientation pair is the dangerous one: they look like general fixes and
are not. If they are ever offered upstream, they need a board-config flag.

---

## Practical notes

- `qmk_firmware-ak820pro/` is a **pristine clone with uncommitted changes** — no
  local commits exist. Contributing means forking, branching, and splitting into
  logical commits.
- The six ChibiOS `.diff` files are applied by hand into `lib/chibios-contrib/`
  and are **not committed**; any `git submodule update` discards them.
- Evidence is unusually good for the CH582F work: wire traces exist for all four
  bugs, which makes for a strong PR. Include them.
- Suggested order: **1.1 first** (smallest, clearest, widest benefit), then 1.3,
  then the CH582F set as one PR with the shared root cause explained up front.
