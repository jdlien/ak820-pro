# Power charts and a power calculator page — plan, not started (2026-10-21)

A public page for AK820 Pro owners: what each lighting knob costs, and **how
long a full charge lasts at a given setting while you type nonstop** (the
longest active use the pack gives at that setting), beside standby and a
typical day. A chart with a line per RGB colour (white, red, green, blue) and
one for the screen, against how far each knob is turned, with the deep sleep
and the awake-and-dark floor as baselines. Sliders set the knobs and the
mode; the numbers follow.

It belongs to the "polish for other owners" step in [`BACKLOG.md`](BACKLOG.md)
("Next phase"). Nothing here is built.

## Order and blockers

- **The sweep runs before the daily-use trial's full charge, not during
  it.** It runs on the pack (relay 2 off) for about 2 hours and uses about
  2% of a charge; inside the trial it would spoil R5's drain.
- **Ask the session that holds the board first.** A clock test was running
  on 10-21; the sweep switches relay 2 and changes the lighting, which
  disturbs one.
- **It needs a dev build** for the screen: `HC_DEVHOOK` ops 4/5 set it, op 6
  reads it, and none of them persist. The lighting goes over VIA's channel
  without its SAVE, so nothing reaches flash.
- **GitHub Pages is a repo setting:** ask before turning it on.

## One model, the board's own

**The firmware already carries the power model**, and the page uses it rather
than a second copy (`battery.c` on `ak820pro-jdlien`, the `P_*` constants
near line 575 and `model_nj()`):

`P = P_BASE + P_BKL_FULL·duty/48 + [any LED lit]·P_RGB_A + Σ B_c·S_c (+ P_USB on the bench)`

- `P_BASE` 106.9 mW (every light out, no USB data), `P_BKL_FULL` 39.1 mW at
  duty 48, `P_RGB_A` 8.64 mW while any LED is lit, `B_r/g/b` 3.636 / 2.533 /
  2.294 µW per unit of a colour's channel sum (82 LEDs × 0-255 drive),
  `P_USB` 7.1 mW.
- `S_c` is the drive after QMK's `hsv_to_rgb` and its CIE table; the screen's
  duty comes from the 24-level table (`docs/display.md`). Both tables are
  copied exactly from the firmware.
- `scripts/power_model.py` reads the constants out of the pinned firmware
  (`git show <deps.lock's commit>:…/battery.c`) into `power.json`. **If the
  board's model and the page ever differ, the board's time-left and the page
  disagree in front of an owner**, so there is one set of numbers and the
  sweep checks it.
- Evidence it holds: the 10-19 per-colour fit is within 0.6% at every step,
  and purple, outside the fit, within 0.2% (`battery.c`'s comment;
  `history/power-bench-2026-10-15/rgb-curve-20261019/`). The screen is linear
  in duty (R1, 10-15: 27.33 mA off to 36.70 at duty 48).

**The sweep is the model's check, not its source.** `power_model.py` fits the
sweep (`rgb_fit.py`'s method, extended to the screen) and prints each
constant against the firmware's. Inside a tolerance (say 2%) the page ships
the firmware's constants and the measured points as dots; outside it, that is
a firmware constant change, made and reviewed on its own, before the page
ships.

## The numbers the page gives

All from `E` = **15,579 mWh**, full to the RGB cut (R3, 10-15 to 10-18), and
`P` from the model at the sliders, with no USB data.

### Continuous active use: the headline

Hours of typing nonstop from full until the lights go out, then the dark
reserve after them. It follows the firmware's own rules
(`power.c`, `power_task()`'s battery branch):

- **Below 15% (150 permille) every mode, Always on included, takes Power
  saver's stages and caps the lighting's value at 128 while typing.** So the
  last 15% runs at `P(min(v, 128))`:
  `hours = 0.85·E / P(setting) + 0.15·E / P(setting, v capped at 128)`.
- **The mode changes what "typing" lights:**
  - Always on and Balanced: the setting as set (the ladder only acts in
    pauses);
  - Power saver: the value capped at 128 throughout;
  - Lights out: dark while typing, the "every light off, awake" draw (~107
    mW), whatever the sliders say.
- **Then the reserve:** after the RGB cut the board types on with the LEDs
  off. Measured once: **5 h 01 min** at screen level 5 (run 2, 10-02 to
  10-04). The page scales it by the dark draw at the chosen screen level and
  marks it "measured once". The voltage it ends at is unknown
  (`docs/power.md`).
- **The board's own time-left** is the same quantity, "hours of use" at the
  awake average (`battery.c`, `time_left_update()`), but it does not model
  the low cap, so above 15% it reads a little short of this. The page says
  so rather than hiding the difference.

Checks it must reproduce (`docs/power.md`, "Modelled: one state, held" and
the drains):
- full white, screen level 5: ~52 h untethered; the logged drain ran 50.39 h
  with the bench's USB data (~2.3%), ~51.5 h untethered. **Typing costs about
  1% over the held state**, so a held-state model is a fair "typing" figure;
- everything at max on 2.4G: ~46 h; white at 128: ~4 days; lights off: ~6
  days.

### Standby

`E / 13.25 mW` on BT (13.8 on 2.4G): ~49 days asleep. Measured 3.2 mA over
an hour (10-18/19).

### A typical day

`docs/power.md`'s formula, interactive: **days = E / (P_awake × awake h +
P_sleep × asleep h)**, with the mode's pause cost (Balanced ~67 mWh a pause
at full white, Power saver ~6) and the 15% tail as above. Sliders for hours
typed a day and pauses a day. Always on never sleeps above 15%, so its day is
24 lit hours.

### What the page does not model, and says

- Animated effects: one or two measured points (the `stages` set's Cycle
  All), no curve.
- 2.4G with the lights on: unmeasured; the page adds the lights-off ~5 mW and
  marks it.
- Whether `E` depends on the draw: R3 was measured at ~73 mA. At a lower draw
  the pack sags less and may reach the 3.40 V cut slightly later; the page
  uses one `E` and says it was measured at JD's settings.
- Ageing, temperature, another unit's pack.

## The sweep

A new set in `scripts/current_map.py` (`knobs`), run forward and then
backward, 60-90 s holds less the 15 s settle, as the existing sets are, with
the board held in Always on's active stage. Each family isolates one load
from a shared floor: **the RGB sweeps run with the screen off, the screen
sweep with the RGB off.** (The 10-19 `rgb-curve` had the screen at JD's
level, so it is rerun, and white with the colours, so all four lines share
one pack voltage.)

| Family | States |
|---|---|
| RGB off | one state, the floor |
| White, red, green, blue | value 3, 64, 128, 160, 192, 224, 240, 255: 8 each |
| Screen (RGB off) | off, levels 1, 4, 8, 12, 16, 20, 23 |
| Combined | 3 RGB + screen states, to check the loads add |
| Deep sleep | one long hold, forced with op 14 and woken by the relay-1 rig, or the 10-18/19 hour reused |

About 45 states. The points sit where the curves bend, not evenly: both
knobs are perceptually spaced, flat at the bottom and steep at the top.
Value 3 (drive 1 of 255 after the CIE curve) shows the fixed cost of any LED
lit (`P_RGB_A`) as a step at the line's left edge.

The bench has the USB data attached; the fit removes `P_USB` and the page
shows untethered figures.

## The page

No framework and no build step:

```
site/power/index.html     HTML, CSS and plain JS
site/power/power.json     generated, never hand-edited
scripts/power_model.py    firmware constants + sweep summary -> power.json (stdlib)
.github/workflows/pages.yml   publishes site/ alone
```

- **`power.json`** holds the firmware's constants and tables, the low-cap
  threshold and value (150 permille, 128), the modes' rules, `E`, the
  reserve, the sleep draws, the measured points, and where each came from
  (the firmware commit, the sweep's directory, the date, the pack voltage).
- **The one wheel reinvented is QMK's `hsv_to_rgb`** (~20 lines of integer
  maths), so a slider's colour gives the drive the board would compute. Its
  test: each state's drive per mille in the sweep's summary (`led 333`) must
  come out of the page's code.
- **The chart: Observable Plot,** pinned from a CDN. Its marks are the chart
  as described (a line per colour from the model, dots for the sweep's
  points, rules for the baselines, a dot for "your settings"), and it draws
  SVG: a download button gives `docs/power.md` its static image, which GitHub
  renders. A second panel draws continuous-use hours against the same knob
  positions, since hours are what an owner reads. Chart.js is the lighter
  alternative, but it draws to a canvas, so the repo would get a PNG.
- **The knobs on one axis:** RGB value is 0-255 and the screen 0-23, so the
  x axis is "knob position as you see it, 0-100%": VIA's slider for the RGB,
  the `LCD nn%` readout (`level*100/23`) for the screen.
- **Controls:** RGB value, hue, saturation, screen level, mode, radio; for
  the typical day, hours typed and pauses. Pre-filled from URL parameters.
- **Readout:** draw in mW and mA (at a nominal pack voltage, said), hours of
  continuous use plus the reserve, days of standby, days for the typical day.
- **Presentation:** light and dark through CSS variables; the lines are red,
  green and blue on purpose, so each is labelled at its end for colour-blind
  readers, and white is drawn grey or outlined.
- **Tests,** `node --test` or a stdlib Python harness over the same JS
  maths: the `hsv_to_rgb` fixture above; the "checks it must reproduce" list;
  and the page's continuous-use hours against the board's own arithmetic (a
  replay of `time_left_update()` at a fixed draw, from `scripts/battery_sim/`)
  above 15%.

## Hosting

- **The repo is already public, only unannounced.** Pages from an Actions
  workflow that publishes `site/` alone, not `/docs` from `main`, which would
  put the working notes through Jekyll. `site/` can later be the owner's
  front door (the backlog's README for strangers), the calculator one page
  of it.
- A private claude.ai artifact copy for sharing before then.

## Getting the board's settings into the page

**A (first): a command reads them and opens the page with them in the URL**,
`…/power/?v=255&h=0&s=0&lcd=5&mode=balanced`. Only a tool that already talks
to the board touches HID, and the page stays static.

**B (later): the page reads the board over WebHID,** on Pages (https, top
level; the artifact's sandbox probably does not allow WebHID). It is one more
process on the raw-HID interface, so CLAUDE.md's warnings all apply:

- it receives the daemon's replies, as VIA did when it went off by one, so
  every reply is checked against the command it answers;
- whether Chrome seizes the interface on macOS, as hidapi does, or shares it,
  is unknown and needs a test;
- whether Chrome's device picker opens every HID device, as `hid_enumerate`
  does, is worth checking against the UPS incident; VIA already has the same
  exposure;
- Chrome or Edge only;
- reads only, never a write or a SAVE: on a dev build one wrong write drops
  the board into the bootloader.

**What can be read:** the lighting, from any build (VIA's channel 3); the
mode, stage, level, modelled draw, average and time-left from `HC_POWER`, on
every build, which the page could show beside its own figure. **The screen
level only on a dev build** (op 6). `HC_POWER`'s page 0 uses 27 of its 29
bytes, so one more byte for the level (the reply's version bumped) would make
it readable everywhere: a small firmware change, for when the page wants it.

## Questions for the review

1. Is the continuous-use formula right against the firmware: the 15% tail,
   which modes it touches, what Lights out lights while typing, the screen
   in the low cap, and anything else that changes the draw while typing on
   battery (the RGB cut, the low cap's notice, Minimal's lit messages)?
2. Is "level 150 permille = 15% of `E`" true of the gauge as built, or does
   the tail hold a different share of the energy?
3. Is one model, the firmware's, the right source, and is the refit
   tolerance the right gate? Anything in `model_nj()` the page would get
   wrong by reading constants alone?
4. The sweep: enough states, the right spacing, the shared floor, and the
   holds against the noise in the 10-19 and 10-15 summaries?
5. The reserve scaled by the dark draw from one measurement: fair, or show
   it unscaled?
6. Anything owners will misread in the readout, and anything overstated.

## Open

- Plot or Chart.js, if JD prefers the lighter one.
- Deep sleep re-measured in the sweep's session or the 10-18/19 hour reused.
- Whether the site carries only the calculator or the owner guide too.
