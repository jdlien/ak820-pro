# Power charts and a power calculator page — plan, not started (2026-10-21)

A public page for AK820 Pro owners: what each lighting knob costs, and **how
long a full charge lasts at a given setting while you type nonstop** (the
longest active use the pack gives at that setting), beside standby and a
typical day. A chart with a line per RGB colour (white, red, green, blue) and
one for the screen, against how far each knob is turned, with the deep sleep
and the awake-and-dark floor as baselines. Controls set the knobs, the mode
and the radio; the numbers follow.

It belongs to the "polish for other owners" step in [`BACKLOG.md`](BACKLOG.md)
("Next phase"). Nothing here is built.

**Revision 2**, after codex's review
([`review-codex-power-charts-2026-10-21.md`](review-codex-power-charts-2026-10-21.md);
dispositions at the end). Its verdict on revision 1 was "revise before
building"; the architecture stood, the arithmetic and the claims did not.

## Order and blockers

- **The sweep runs before the daily-use trial's full charge, not during
  it.** It runs on the pack (relay 2 off) for about 2½ hours and uses about
  2-3% of a charge; inside the trial it would spoil R5's drain.
- **Ask the session that holds the board first.** A clock test was running
  on 10-21; the sweep switches relay 2 and changes the lighting, which
  disturbs one.
- **It needs a dev build** for the screen and the stage: `HC_DEVHOOK` ops 4/5
  set the screen, op 6 reads it, op 14 sub 2 holds a stage. None of them
  persist, and the lighting goes over VIA's channel without its SAVE.
  **The sweep never sets the power mode**: `power_set_mode()` writes it to
  EEPROM (`power.c:330`). It holds the ACTIVE stage instead, which ignores
  the mode, the supply and the low cap.
- **GitHub Pages is a repo setting:** ask before turning it on.
- **Found on the way, a firmware item of its own** (`BACKLOG.md`, "The RGB
  model's 82 LEDs"): the board has 81 RGB LEDs, and the per-colour slopes in
  `battery.c` were fitted as if it had 82. The page waits for that fix or
  carries the corrected slopes beside the firmware's, said so.

## One model, the board's own

**The firmware already carries the power model**, and the page computes with
it rather than a second copy (`battery.c` on `ak820pro-jdlien`, the `P_*`
constants near line 575, `model_nj()`):

`P = P_BASE + P_BKL_FULL·duty/48 + P_RGB_A·[any LED lit] + Σ B_c·S_c (+ P_USB on the bench)`

- `P_BASE` 106.9 mW (every light out, no USB data), `P_BKL_FULL` 39.1 mW at
  duty 48, `P_RGB_A` 8.64 mW while any LED is lit, `B_r/g/b` 3.636 / 2.533 /
  2.294 µW per unit of a colour's channel sum, `P_USB` 7.1 mW.
- **`S_c` is summed over `RGB_MATRIX_LED_COUNT`, which is 81** (the
  `rgb_matrix` layout in `keyboard.json`; `config.h:33`). The fit that made
  `B_c` (`scripts/rgb_fit.py:15`) and the simulator's stub
  (`scripts/battery_sim/stubs/quantum.h:50`) use 82, so the slopes are
  ~1.2% low: at full white and screen level 5 the model gives 294.4 mW
  untethered where 82 would give 296.6. The fix is the firmware item above.
- **The colour path, exactly as QMK runs it:** the CIE table
  (`quantum/led_tables.c`) applies to the HSV value **before** `hsv_to_rgb`
  mixes the colour (`quantum/color.c`), not to each RGB channel after.
- **What the board counts:** RGB energy from the committed, capped frames,
  time-weighted, with `P_RGB_A` only during lit time
  (`drivers/led/sn32f2xx.c`, `sn32f2xx_led_drive_take`); the screen from its
  effective duty, its on/off state included; asleep, a flat **13.35 mW**
  whatever the radio (`battery.h`). The page's per-radio sleep (13.25 mW BT,
  13.8 mW 2.4G, measured) and awake 2.4G (+~5 mW, one lights-off reading) are
  extensions of the board's model, labelled as such.
- **The screen's two tables:** level to duty (`graphics/display.c`, 24
  levels, duty 48 at the top), and the `LCD nn%` readout,
  `(level*100 + 11)/23` in integers (`param_overlay.c`; level 5 shows 22%).

### How it is extracted

`scripts/power_model.py` builds `power.json` **from the exact `deps.lock`
SHA only** (`git show <sha>:<path>`), never a branch head or the working tree:
the coefficients, `E_CAP_MWH`, the LED count, the CIE table, the backlight
table, `LOW_CAP_PM`, `SAVER_VAL`, the ladders and the sleep constant. It
fails closed on a missing or ambiguous definition or a table of the wrong
size. `power.json` carries a schema version and keeps three things apart:

- **the firmware model** (the above, and the SHA it came from);
- **measured evidence and its conditions** (the sweep's points, the drains,
  the sleep hour, the reserve; build, date, pack voltage, radio, tethered or
  not), from the sweep's structured output, not from `summary.txt`'s rounded
  text, with both the raw bench power and the untethered value;
- **scenario assumptions and extrapolations** (the 15% tail, per-radio
  draws, the reserve), each labelled.

### Agreement, in two separate gates

- **Exact arithmetic.** The page's maths must equal the pinned C's. The
  oracle compiles the pinned `color.c`, `led_tables.c` and `battery.c`'s
  model against host stubs with the real LED count (`scripts/battery_sim/`,
  pointed at the SHA instead of the working tree, its stub corrected to 81)
  and prints fixtures the page's tests compare against.
- **Measurement.** The sweep's fit is reported as residuals, repeatability
  and uncertainty, for the total and for each isolated increment, against
  the firmware's constants. A disagreement starts an investigation; it does
  not change a firmware constant by itself. A sweep with USB data attached
  sees `P_BASE + P_USB` together, so the two are not separated by it.

What is known so far: the 10-19 fit's paired state means agree within 0.6%,
single holds within ~0.94%; the current executable model (81 LEDs) within
~0.8% across the RGB sweep's means, and purple, held out, 0.33% low
(211.20 mW against 211.9). The screen is linear in duty (R1, 10-15: 27.33 mA
off to 36.70 at duty 48, both with the bench's USB data).

## The numbers the page gives

`E` = 15,579 mWh, full to the RGB cut (R3, 10-15 to 10-18, with a logger gap
bridged by an estimate: four significant figures, not five). `P` from the
model at the controls, untethered.

### The headline: typing nonstop from full, as a short timeline

> **About 60 hours of nonstop typing to 0%**
> About 45 hours at your brightness, then about 15 automatically dimmed.
> A model estimate for the reference keyboard on this firmware. It assumes
> the dimming starts with 15% of the usable energy left.

(Full white, screen level 5, BT.) The firmware's rules while typing on
battery (`power.c:119`, `power.c:203`):

| Condition | RGB while typing | Screen while typing |
|---|---|---|
| Always on, Balanced, level above 150‰ | as set | as set |
| Power saver | value capped at 128 | as set |
| Any mode but Lights out, level **at or below** 150‰ | value capped at 128 | as set |
| Lights out | off | off, but for 4 s messages and the debug pages |
| After the RGB cut | off | as the mode has it |

So `hours = (1 − f)·E / P(setting) + f·E / P(setting, value ≤ 128)`, with
`f = 0.15` **as a stated assumption**: the gauge as built does not guarantee
that 150‰ means 15% of the energy is left. It ratchets against the voltage
band, holds below it, re-seats after a charge, starts differently after a
reboot, and stops counting down at 10‰ (`battery.c:583`, `:684`, `:1095`;
`docs/battery.md`). The page shows the sensitivity: one point of `f` moves
the full-white figure by ~0.49 h. **R5 should log the pack's energy left
when the low cap actually starts**, so `f` can be measured.

**The cap-inclusive figure has never been measured.** Every logged drain
predates Phase 2's low cap. What the drains do measure is the fixed-state
case, which the page shows as its evidence:

- **Fixed state, the model:** 52.9 h at full white, screen level 5,
  untethered; everything at max on 2.4G 46.6 h (51.7 with the tail); white
  at 128 102.1 h; screen 5 with the RGB off 140.4 h; every light off 145.7 h.
- **Fixed state, measured:** five drains at full white and screen level 5
  ran 50-52 h; R3, logged, 50.39 h with the bench's USB data, ~51.6 h
  untethered. **The model runs ~2.5% long against R3**: R3's mean was
  309 mW (79.6 mA, rising from ~73 to ~90 as the pack fell) against ~301.5
  modelled with the USB data. Typing's own cost is not separated
  (`docs/power.md`), so this gap is not attributed; the page shows it, not
  a correction for it.

**The reserve stays separate and unscaled:** "After 0%, it typed for about
five more hours, observed once, with a dim screen" (5 h 01 min 29 s, run 2,
older firmware; `docs/battery.md`). A scaled figure for other settings
would assume the same reserve energy, converter behaviour and endpoint
under another load, none of them measured; if shown at all, it is labelled
an unvalidated extrapolation.

**The board's own time-left is a different quantity**, and the page says
so: remaining gauge energy over the board's **historical awake average**,
which includes dimmed and dark awake time, excludes deep sleep, has a
time constant growing to 12 hours, leaves out the reserve, and is
unavailable on USB, at an unknown level and after the cut (`battery.c:619`,
`:722`, `:782`). It predicts neither a full charge nor nonstop typing at the
page's controls, and the two can disagree in either direction.

### Standby

Asleep: 48.99 days on BT (13.25 mW), 47.04 days on 2.4G (13.8 mW), both
measured draws; the firmware counts 13.35 mW (48.62 days). Measured 3.2 mA
over an hour (10-18/19). **Always on never deep-sleeps, at any level**
(`power_sleep_wanted()`, `power.c:299`): its standby is the awake-dark
draw.

### A typical day

A pause's cost depends on its length, not only how many there are: a
2-minute pause and an hour-long one walk different distances down the
ladder. So the day is a schedule:

- **Presets** (the office day: 8 h nonstop then away; JD's logged day; a
  stop-start day) and an **editable list** of active stretches and pauses
  with durations.
- **Sleep is the baseline for all 24 hours**, plus each stretch's and each
  pause's increment above it, so every hour is counted once, the last
  absence of the day included.
- Each pause walks the mode's ladder at the measured stage draws (Balanced
  ~66.0 mWh above sleep for a pause long enough to reach sleep, Power saver
  ~6.1, at full white and screen 5). Always on never reaches sleep. The 15%
  tail as above.

### Scope and what is not modelled, said on the page

- **This firmware, on the reference keyboard.** Stock firmware's draw is
  unmeasured (`docs/power.md`).
- **Solid colour only.** Animated effects and **Alphas/Mods** (a static
  two-colour effect whose second hue depends on speed,
  `quantum/rgb_matrix/animations/alpha_mods_anim.h`) get an explicit "not
  modelled" result, with a measured point or two where they exist (the
  `stages` set's Cycle All, compared as a whole-hold average, not one
  `HC_POWER` sample: its SD is ~3.5 mA).
- 2.4G with the lights on: unmeasured, extrapolated.
- `E` at another draw, temperature, ageing, another unit's pack.
- **Fit accuracy is not a runtime error bar.** A 0.6% residual says the
  power model fits; the runtime's uncertainty is the capacity, the cut, the
  load, the unit and the tail, and the page lists them beside the estimate.

## The sweep

A new set in `scripts/current_map.py` (`knobs`), run forward and then
backward, the board held in ACTIVE with op 14 sub 2 and the mode left
alone. Each family isolates one load from a shared floor: **the RGB sweeps
with the screen off, the screen sweep with the RGB off.** The 10-19
`rgb-curve` had the screen at JD's level, so it is rerun, white with the
colours, so all four lines share one pack voltage.

| Family | States |
|---|---|
| Dark reference | RGB off, screen off: at the start, between every family, and at the end |
| Value 0 | once (solid colour, value 0: no LED lit, so `P_RGB_A` should not apply) |
| White | values 1, 16, 32, 48, 64, 128, 160, 192, 224, 240, 255 |
| Red, green, blue | values 1, 16, 48, 64, 128, 192, 240, 255: 8 each |
| Screen (RGB off) | levels 1, 4, 8, 12, 16, 20, 23, and off |
| Held out | purple (hue 191), a partial saturation (hue 0, sat 128), a hue-sector boundary |
| Combined | 3 RGB + screen states, to check the loads add |

About 55 states, ~2½ hours with both passes; the low-end holds (screen
levels 1-4, values 1-48) are longer or repeated, since the smallest screen
step is 0.815 mW against sample SDs of 0.1-0.4 mA (0.7-0.8 in some dark
holds). The points sit where the curves bend, not evenly, and value 1 is the
first lit drive (values 1-3 all give drive 1), so the `P_RGB_A` step shows
at the line's left edge. The passes are compared before they are averaged:
reversal cancels a steady drift, not relaxation after a change or
background activity.

**Each state records** the requested and read-back lighting (VIA channel 3)
and screen (op 6), the stage and cap (op 14's reply, read again after the
next tick), the firmware's token, the interval, the pack voltage, and the
INA228's charge across the hold, into a CSV or JSON at full precision.

**Deep sleep is not part of the sweep.** The page uses the measured
10-18/19 hour (3.17 mA, BT) and the 2.4G figure. Remeasuring needs the
existing hour-long procedure: USB data removed (`uhubctl`; a live USB link
blocks deep sleep, `sleep.c:240`), op 14 sub 4, the sleep's preconditions
met. `P_USB` is never subtracted from a sleep figure.

## The page

No framework, no bundler, no build step:

```
site/power/index.html        the page: HTML and CSS, imports model.js
site/power/model.js          the maths, an ES module with no DOM
site/power/model.test.js     node --test, against the C oracle's fixtures
site/power/power.json        generated, never hand-edited
site/vendor/                 Observable Plot and d3, pinned, with their licences
scripts/power_model.py       pinned firmware + sweep output -> power.json (--check)
.github/workflows/pages.yml  checks on PRs, publishes site/ from main
```

- **`model.js`** is the one implementation of the maths, imported by the
  page and by the tests: QMK's `hsv_to_rgb` and CIE step (the one wheel
  reinvented, ~20 lines of integer maths, so a colour gives the drive the
  board would), the model, the timeline, the day.
- **The tests** compare `model.js` with the oracle on: exact RGB channels,
  CIE before mixing, hue-sector boundaries, values 0 and 1, all 24 screen
  levels, the RGB intercept, 149/150/151‰, every mode, Lights out's lit
  messages, the RGB cut, Always on's refusal to sleep; the fixed-state
  runtime, the cap-inclusive runtime and the board's historical-average
  time-left, each separately; days with short, long, zero and
  maximum-length activity.
- **The chart: Observable Plot,** vendored rather than from a CDN, so the
  page does not depend on one. It draws SVG, and an export button gives
  `docs/power.md` its static image, which GitHub renders, with the units,
  the assumptions and the model's revision written into it.
  - **Panel 1, draw against knob position** (0-100% as you see it: VIA's
    slider for the RGB, the `LCD nn%` readout for the screen). Each curve is
    labelled "other lighting off". Points at the real integer settings, no
    smoothing through levels that do not exist, the first-lit step kept.
    Measured points as dots, the model as the line, the sleep and the
    awake-and-dark floor as rules.
  - **Panel 2, hours against the same positions.**
  - **Your settings:** a marker on each knob's own curve (a combined
    setting has no single x), and a bar splitting the total into the base,
    the screen, the RGB's fixed cost and each colour.
  - A note that equal slider positions are not equal brightness across
    colours; the lines labelled at their ends for colour-blind readers,
    white drawn grey or outlined; a data table for every chart.
- **Controls:** RGB value, hue, saturation, effect (solid, or "not
  modelled"), screen level and on/off, mode, radio; the day's schedule.
  Pre-filled from URL parameters. Lights out greys out the lighting controls.
- **Readout:** total draw (mW, and mA at a stated nominal voltage), the
  timeline, standby, the day; and **what a change saves**, in mW and hours,
  against the settings you came in with (white 255 to 128 saves ~142 mW; a
  maximum screen turned off, 39.1).
- Light and dark through CSS variables.

## Hosting

- **The repo is already public, only unannounced.** Pages from an Actions
  workflow that publishes `site/` alone, not `/docs` from `main`, which
  would put the working notes through Jekyll.
- **CI checks the artifact it publishes.** `power.json` is committed for
  review; on PRs the workflow runs `power_model.py --check` (regenerates and
  rejects drift), the oracle and `node --test`. The firmware clone is
  gitignored, so CI fetches the pinned commit's few files itself (a shallow
  fetch of the SHA), with no firmware build. It deploys only from `main`,
  triggers on `site/`, the generator, the tests, the evidence and
  `deps.lock`, and is tested under the Pages subpath (`/ak820-pro/`), so
  every URL is relative.
- `site/` can later be the owner's front door (the backlog's README for
  strangers), the calculator one page of it.
- A private claude.ai artifact copy for sharing before then.

## Getting the board's settings into the page

**A (first): a command reads them through the existing host transport and
opens the page with them in the URL**,
`…/power/?v=255&h=0&s=0&fx=solid&lcd=5&lcdon=1&mode=balanced`. It carries the
effect and whether the RGB and the screen are on, not only the numbers.

**B (later): the page reads the board over WebHID,** on Pages (https, top
level; the artifact's sandbox probably does not allow WebHID). It is one more
process on the raw-HID interface, so CLAUDE.md's warnings all apply:

- **"Read-only" means a fixed allowlist of read requests.** A query still
  sends a report, and `HC_POWER` rides the SET-value envelope. Every reply is
  checked for its length, command, page, version and field ranges, since
  the page receives the daemon's replies too (VIA went off by one that way).
- The daemon-coexistence tests CLAUDE.md describes, on Windows and macOS;
  whether Chrome seizes the interface on macOS, as hidapi does, is unknown.
- Whether Chrome's device picker opens every HID device, as `hid_enumerate`
  does, is checked against the UPS incident first; VIA has the same
  exposure.
- Chrome or Edge only.
- **Reading the board over USB means it is not on battery**, so the board's
  live time-left is unavailable then. Importing settings and comparing live
  battery figures are separate operations.

**What can be read:** the lighting, from any build (VIA's channel 3); the
mode, stage, level, modelled draw, average and time-left from `HC_POWER`
page 0, on every build. **The screen's level and on/off state only on a dev
build** (op 6). To read them everywhere, a **new `HC_POWER` page** (as page 1
was added for the sleep) rather than a changed page 0: page 0's consumer
`hostagent/ak820battery.py:99` accepts version 1 only, and one byte would
not carry the on/off state anyway.

## Codex's review (10-21): dispositions

Every finding was checked against the source before it was taken; the six
that matter most (81 LEDs, Always on and sleep, `power_set_mode()`
persisting, USB blocking sleep, R3's 79.6 mA, typing's cost unseparated)
were confirmed directly.

| # | Finding | Disposition |
|---|---|---|
| 1 | The headline's checks were fixed-state figures, not the cap-inclusive calculation | **Done.** Two calculations, kept apart; the cap-inclusive one marked never measured |
| 1 | Always on never deep-sleeps, below 15% too | **Done**, confirmed (`power.c:299`) |
| 1 | `<=` 150‰, not "below"; Lights out's lit exceptions | **Done** (the table) |
| 2 | 150‰ is not guaranteed to be 15% of `E` | **Done.** A stated assumption with its sensitivity; R5 to log the energy at the cap's start |
| 3 | 81 LEDs, not 82; the fit and the stub used 82 | **Confirmed.** In the plan; the firmware fix is its own backlog item |
| 3 | CIE before mixing; committed frames; lit-time intercept; LCD on/off; 13.35 mW asleep | **Done** |
| 3 | The 2% gate is the wrong gate | **Done.** Exact arithmetic and measurement agreement gated separately; a miss starts an investigation |
| 4 | Values 0, 1 and more low points; dark references; held-out states; read-backs | **Done**, trimmed for the colours |
| 4 | Sleep: USB blocks it, op 14 sub 4, never subtract `P_USB` | **Done.** The measured hour is reused |
| 4 | Setting the mode persists | **Done**, confirmed: the sweep holds the stage instead |
| 5 | Show the reserve unscaled | **Done** |
| 6 | The board's time-left is not the same quantity | **Done.** Revision 1's "the same quantity, a little short" withdrawn |
| 6 | State the firmware scope; import the effect and on/off states | **Done** |
| 7 | Number audit (R3's draw, the fit's 0.6%, purple, standby per radio, the readout's rounding, pause costs, `E`'s precision, typing's "1%") | **Done**, all taken; the typing claim withdrawn |
| 8 | A day needs pause durations | **Done.** Presets and an editable schedule, sleep as the baseline |
| 8 | The timeline; fit vs runtime uncertainty; savings; per-knob markers; discrete points, tables, SVG metadata | **Done** |
| 9 | `model.js` shared by page and tests | **Done** |
| 9 | Deterministic, fail-closed generation; schema version; model, evidence and assumptions apart | **Done** |
| 9 | A C oracle at the pinned SHA with 81 LEDs | **Done** (the simulator, re-pointed) |
| 9 | CI validates what it publishes; vendored chart library; Pages subpath | **Done** |
| 9 | `HC_POWER`: one byte is not enough, and page 0's version is consumed | **Done.** A new page instead |
| 9 | WebHID: an allowlist, validated replies, coexistence tests; USB means no live time-left | **Done** |

One more, found while checking the model against R3: the model runs ~2.5%
long against the logged drain. Shown on the page, not corrected for.

## Open

- Deep sleep re-measured on 2.4G and BT in one session, or the existing
  figures kept.
- Whether the site carries only the calculator or the owner guide too.
- Whether the firmware's 81-LED fix lands before the page (preferred) or the
  page carries corrected slopes beside the firmware's.
