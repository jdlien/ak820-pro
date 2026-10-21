# Power mode icons and names — on the board (2026-10-19)

An icon for the power mode in the battery row, and friendlier mode names.
Designed with pixel-accurate mockups (the firmware's own geometry and the
shipped Iosevka 20 px atlas). The colours are starting values to try on the
panel, not decisions.

## Status

**On the board since 16:16 10-19: `83d8768c64`** (dev, token `0xcf9da0e0`),
the bulbs as judged on the panel ("On the panel", below). It sits on
`7df85fb89b` (the wider base and its collar) and `26fcafaeca`, the icons
build codex cleared (`61a425a721`, the follow-up `6926a17c80` and a comment
fix, on `7df8a08e96`). The two since `26fcafaeca` change `display.c`'s art
and colours only, plus one more colour index in the rasterizer: the same
tile, the same rect, the same triggers, so they went on without a codex
round. `26fcafaeca` went on at 13:18 and was soaked by the deep-sleep
session: 97 of 100 deep-sleep cycles through the ladder, the three failures
UART overruns, the link's own
([`../history/deep-cycles-20261019-icons/`](../history/deep-cycles-20261019-icons/README.md)).
It carries `7df8a08e96`, battery.c's guard against a historical debit for a
sleep on USB (codex's own fix, reviewed with this branch). The docs name the
modes (display.md's battery row; battery.md, hardware.md, test-bench.md and
CLAUDE.md's Fn line). ⚠️ Local on `ak820pro-jdlien`, not pushed.

- Compiles clean, dev, daily and fpb: +1,016 bytes at `26fcafaeca` (the art
  is 784).
- `scripts/battery_sim` passes against both firmware trees (`ladder.c`
  takes the names from `POWER_HAS_BULB`). Through `BATTERY_SIM_SRC` both
  give 146, the same list line for line; a plain run gives 150 because it
  adds the four pinned-baseline checks (flash 1's `battery.c`, which never
  reads the tree under test), and the variable skips them. New checks
  in `l_modes` and `l_low_cap` catch three mutants of `power_lights_mode()`
  (low ignored, everything Saver when low, Lights out taken to Saver).
- `hostagent/ak820battery.py` prints the new names (display only; the
  indices are unchanged).

Done: codex's review and verify (no must-fix, below); the flash; the gate's
Fn+B part on the pack (below); the shape and colours on the panel; the docs.
Left: nothing for the icons. The bezel clipping the slot when the panel is
seen at an angle is noted, not one for software yet.

## The names

| Now | New | Cells | On battery |
|---|---|---|---|
| Full power | Always on | 9 | never dims, never sleeps |
| Normal power | Balanced | 8 | dim 1 min, lights off 5, screen off and asleep 7 |
| Power saver | Power saver | 11 | dim 30 s, lights off 2 min, screen off and asleep 3 |
| Minimal mode | Lights out | 10 | lights and screen off even typing; asleep after a 30 s pause |

The timings as of this plan; revised 2026-10-20 in
[`POWER-MODES-REVISION-PLAN.md`](POWER-MODES-REVISION-PLAN.md). The names
and the bulbs are unchanged.

All fit the overlay's 11 cells (`TEXT_BIG_MAX`). The names live in:
`power.c` (`mode_names`); `hostagent/ak820battery.py` (`POWER_MODES`); the
overlay checks in `scripts/battery_sim/ladder.c` ("Normal power", "Minimal
mode"); `via.json`'s Fn+B title, which still says "Full / Normal / Saver" and
misses Minimal; the `PWR_MODE` comment in `ak820pro.h`; the docs (CLAUDE.md's
Fn table, battery.md, display.md). The enum identifiers can stay.

## Where the icon goes: the bolt's slot, on battery only

- The slot right of the battery (`draw_bolt_slot`, 12×14 at x 35, y 109) only
  ever holds the charging bolt or the no-pack cross. Both need the cable, so
  **on battery the slot is always empty**.
- **The modes only act on battery** (`power_task`: with the cable in, every
  mode is Always on). An icon on USB would describe something the board is not
  doing.
- So they share the slot: **on battery the mode's icon; on USB the bolt while
  charging, else blank.** Nothing new goes on the screen.
- The mode can still be changed on USB: `power_cycle_mode()` has no battery
  check; it saves the mode and names it in the overlay. The icon appears at
  unplug.
- **Balanced shows its icon.** A blank default would break the ladder of
  bulbs, and blank already means USB.
- **Low battery shows Power saver's icon**, whatever the mode, while the
  lights follow Saver's timings (`LOW_CAP_PM`): the icon says what the board
  is doing.

## The glyphs: one bulb losing its light

As on the board (`83d8768c64`). 13×14 frame, placed at (35, 108): the rays
reach y 108 and x 47, the bulb sits on the battery's bottom row (y 121).
`#` is the outline or the lit glass, `*` the dimmed glass, `=` the collar,
`+` the screw base, `/` the slash.

```
Always on       Balanced        Power saver     Lights out
......#......   .............   .............   .............
.#.........#.   .............   .............   .............
..#.......#..   .............   .............   .//..........
.....###.....   .....###.....   .....###.....   ..//..##.....
...#######...   ...#######...   ...##***##...   ...//...##...
##.#######.##   ...#######...   ...#*****#...   ....//...#...
..#########..   ..#########..   ..#*******#..   ..#..//...#..
..#########..   ..#########..   ..#*******#..   ..#...//..#..
..#########..   ..#########..   ..#*******#..   ..#....//....
...#######...   ...#######...   ...#*****#...   ...#....//...
....#####....   ....#####....   ....#***#....   ....#....//..
....=====....   ....=====....   ....=====....   ....====..//.
....+++++....   ....+++++....   ....+++++....   ....+++++....
.....+++.....   .....+++.....   .....+++.....   .....+++.....
```

Colours, RGB565:

| | `#` | `*` | `=` | `+` | `/` |
|---|---|---|---|---|---|
| Always on, Balanced | white `0xFFFF` | — | grey `0x632C` | light grey `0xB5B6` | — |
| Power saver | white `0xFFFF` | mid grey `0x8410` | grey `0x632C` | light grey `0xB5B6` | — |
| Lights out | slate `0x8D18` | — | dark slate `0x4AAD` | darker slate `0x6BD2` | light grey `0xDEFB` |

- **Power saver's white outline over grey glass** reads as dimmed, and grey
  already means "not in use" on the connection icons.
- **The base is the metal, so it does not change with the light**: the same
  light grey under the three lit or dimmed bulbs, lighter than Saver's glass
  and darker than white. Its top row is a darker collar, which parts the base
  from the glass the way a real bulb's does.
- **Lights out is slate all over**, so the whole bulb looks switched off. On
  the panel the slate reads far less blue than on a monitor, nearer a cool
  grey, so the worry that it would be the only blue on the screen did not
  bite.
- **Lights out is struck through**, the usual mark for "switched off" (a
  muted bell, a hidden eye). Its screen is dark but for a few seconds after a
  message, so the bulb has to read at a glance, and the slash parts it from
  Power saver by shape rather than by fill alone. The slash is 2 px (1 px was
  too faint), from above the glass's top left to beside the collar, stopping
  short of the base; the bulb is cut back a pixel wherever it touches the
  slash at an edge or a corner, so the slash lies over it.

## Colour rules

- ⚠️ **Mid grey `0x8410` was "near-illegible" as 5×7 text on this panel**
  (`COL_AMPM`'s comment, `graphics/display.c`). As Power saver's glass, a
  filled area, it reads fine.
- **Keep yellow, red and amber out of the slot.** Yellow is the bolt's colour
  in the bolt's place; red and amber mean a low battery on this row.
- **No green tint on Power saver's glass.** Green already means a healthy
  battery (the fill beside it) and playing (the transport icon).
- **Greys read darker on the panel than on a monitor**, and the slate less
  blue. Judge colours on the board; a mockup only settles shapes.

## On the panel (10-19)

How the bulbs went from `26fcafaeca` to `83d8768c64`, each step seen on the
board or in the pixel mockup:

1. **First look: the bulb is small and the screw base barely shows.** The
   base was 7 pixels (3 wide, two rows and a tip) of grey `0x8C71` touching
   56 of white glass, so it read as the glass's shading; under the dimmed
   and unlit bulbs it was `0x4228`, near black. Seen at an angle, the cover's
   bezel clips the slot a little.
2. **Two fixes with a black row between glass and base, dropped.** One kept
   the 13×14 frame and gave up a row of glass for the gap; one widened the
   bulb to 15×15. Both looked too squashed to be a bulb.
3. **The original glass with a wider, lighter base, chosen.** The base two
   pixels wider (5, with a 3-pixel tip) in `0xB5B6`, its top row a darker
   collar (`0x632C`) instead of a black gap. Lights out back to the first
   mockup's slate, with a darker slate base and collar. Flashed as
   `7df85fb89b` (15:54).
4. **A struck-through bulb for Lights out.** An X was rejected before it was
   drawn: the slot already shows a red X with no pack. A slash in the
   outline's slate (preview `ea7b7e7e3a`, on the board 16:00) merged with the
   outline where they cross. In white it separated; a black gap around it,
   at its edges only or at its edges and corners, gave it room, and the
   corners won. White then stood out as the brightest pixel of an "off"
   icon.
5. **The slash's shade, picked on the panel.** A preview drew the slashed
   bulb in every mode, one slash shade a mode (`d66c27993a`, 16:08):
   `#DCDCDC`, `#CCCCCC`, `#C0C0C0` and white. `#DCDCDC` (`0xDEFB`) won:
   clearly not white, still well apart from the slate. Flashed as
   `83d8768c64` (16:16).

The previews were on the firmware branch `bulb-slash-preview` only, deleted
10-21; its patches are in
[`../history/firmware-branch-archive-20261021/`](../history/firmware-branch-archive-20261021/README.md).

## Drawing it without a stall

Painting this band has stalled before ("Not every band is queued", and the
bolt's 19 ms runs, display.md), so:

- **The icon is another state of the same RAM tile**, sent with the same one
  `lcd_blit_ram()` as the bolt and the cross. Never runs, never a separate
  clear. Cost should be the bolt's: 11-12 ms passes at a plug-in on flash 2c.
- **The tile grows from 12×14 at (35, 109) to 13×15 at (35, 108)** for the
  rays: 195 pixels against 168. The bolt and the cross move down a row inside
  it to stay where they are.
- **Its triggers mark `BATT_DIRTY_BOLT` and nothing else**: the mode, on
  battery or not, the low cap, plus charging and presence as now. It stays one
  component of `draw_battery()`'s one-per-pass painting, so the Fn+D exit's
  staged restore and the wake's repaint hold need no change.
- **Fn+B paints twice**: the overlay's name in the text band and the slot.
  ⚠️ **They can share a pass** (codex): the battery flag separates battery
  components only. The overlay's glyphs are queued, but its clears (a
  retiring or shortening text) are synchronous, and a lock change can land in
  the same pass too. The tile should cost a few ms (the 12×12 transport icon
  measured 3.4 ms; 390 bytes are ~134 µs on the wire); it is not measured
  yet, and a coincident 20-22 ms Caps paint has little margin.
- **The gate**, with a track playing (display.md): about 20 Fn+B cycles,
  some with Caps and Fn changing in the same moment, plug/unplug cycles on
  the relay, a Fn+D exit and a deep-sleep wake. `count_ge_25ms` stays 0, and
  note `blit_gap_max`. The bench cannot press Fn+B (op 14 sub 1 sets a mode
  without the overlay), so the Fn+B part waits for hands; the soak covers the
  wakes and the plug cycles.
- **Measured on `26fcafaeca`, on the pack (10-19,
  [`../history/fnb-caps-20261019-jd/`](../history/fnb-caps-20261019-jd/README.md)):**
  30 Fn+B presses by hand, the band's FN label changing around each (JD's Fn
  sits where Caps Lock was): **no pass of 25 ms or more**, the worst 20-21 ms
  (`display_hk` 13). Caps Lock toggled from the Mac ~600 times, no Fn+B:
  one pass of exactly 25 ms, on a blit (`blit_gap_max` 25), the CAPS paint
  the lock band's notes already suspected; a control of 199 toggles had none.
  So Fn+B and a Caps change in the same pass were not separated from the
  CAPS paint's own 25 ms; that paint is its own item (current-status.md).
  The deep-sleep soak on this build covered the wakes.

## Codex's review (2026-10-19)

[`review-codex-power-icons-2026-10-19.md`](review-codex-power-icons-2026-10-19.md),
of `61a425a721` with `7df8a08e96`: **no must-fix.** Dispositions:

1. Tile geometry, bounds, colours, the transfer: fine. The bolt and the
   cross land on the same pixels as before.
2. Overlap: fine. Nothing clears only the old 12×14 rect.
3. Note, taken: **a mode change reached the slot at the next RTC second**,
   up to a second after Fn+B's overlay. Fixed in `6926a17c80`: the 10 Hz
   tick calls `draw_battery()` when a bulb is up and `power_lights_mode()`
   has moved (`batt_bulb_stale`). Only a mode change, so supply and CHRG
   edges keep their 1 Hz cadence and an unsmoothed CHRG repaints no faster
   than before. The same fix shrinks the wake's case (the low cap crossed
   after the wake's repaint released the hold) to one tick after the release;
   the hold itself is not extended. CHRG chatter alternating bolt and bulb
   before the supply qualifies: as for bolt and blank before, unchanged.
4. `power_lights_mode()` against `power_task()`: fine; no flapping at the
   low cap, since a known level only holds or falls on battery.
5. Note, taken: the plan's "separate passes" was wrong; corrected above, and
   the gate now includes Caps and Fn changing with Fn+B.
6. Names, VIA, host: fine.
7. `7df8a08e96` is the fix codex proposed and is complete. **Should-fix: a
   battery_sim scenario** that banks a RELAX remainder at the floor, raises
   the level on USB and sleeps across log boundaries, asserting unchanged
   history and zero sleep energy (`s_usb` would pass without the guard).
   Done by the deep-sleep session (outer `4bbf561`): `s_usb_relax_banked`
   banks ~8 pm at the floor, a replug's MODEL session raises the level to 41
   pm, then 2 h asleep on USB; every slept entry keeps the level at the sleep
   and the sleep costs no energy. Passes on `7df8a08e96`; with the guard
   removed all 7 slept entries fail.
8. Build flavours, recoverability: fine.

**The verify**
([`review-codex-power-icons-verify-2026-10-19.md`](review-codex-power-icons-verify-2026-10-19.md)),
of `6926a17c80` and these dispositions: no must-fix. Redraw converges (one
tile per mode change, no stale loop); ownership, Minimal and boot fine.
Notes taken: the comment's "supply and CHRG edges keep 1 Hz" was too
absolute, since a plug-in at the low cap clears it and triggers the 10 Hz
path once (comment made exact in `26fcafaeca`); the wake's case is "the next
eligible tick", gates allowing; **disposition 5 stands, and the Fn+B part of
the gate must be on battery**, with music and Caps/Fn changing, which the
relay soak cannot replace.

## Beside the time left

The deep-sleep build adds hours of use to the row under 10 hours (`18% 6h`,
`99% <1h`), **at most 7 cells, so the text starts at x 54 or later**; the
icon ends at x 47. Keep the row's text to 7 cells on battery: an 8th would
start at x 44, over the icon.

## Considered and dropped

- **A letter in the bulb** (A/B/S/L): a 3×5 letter in a 10 px bulb is a smudge
  at arm's length.
- **Stacked bars**: beside a battery they read as a second battery gauge, and
  do not say whether more bars means more light or more saving.
- **A moon for Lights out**: says the board or the computer is asleep; in
  Lights out you are often typing in the dark.
- **A leaf for Power saver**: the common power-saving icon, but outside the
  bulb family, and once the grey bulb was distinct it had no job left.
- **A fill circle** (full, half, crescent, ring): quiet but abstract.
- **The icon on USB during Fn+B's overlay**, to show what unplugging will
  give: two more slot paints a press, and it would push the bolt out while
  charging. The overlay's name is enough.
- **A black row between glass and base, and a wider 15×15 bulb** (the first
  fixes for the faint base): too squashed to read as a bulb.
- **An X through Lights out's bulb**: it would echo the red no-pack cross in
  the same slot, and read as a fault.
- **A slate or white slash**: slate merged with the outline it crosses;
  white was the brightest pixel in an "off" icon.
