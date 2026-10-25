# The configuration menu's words, for JD's review

Every piece of text the menu shows or will show, gathered 2026-10-24 so JD
can review and edit it (pinned before P1's acceptance:
[`CONFIG-MENU-P1-DESIGN.md`](CONFIG-MENU-P1-DESIGN.md)). **Edit this file
freely**; Warren carries the changes into the code (`menu/menu.c`, and
`scripts/gen_menu_text.py` for Help, which reads its topics from
[`config-menu-mockup.html`](config-menu-mockup.html) today).

- **Built** = on the keyboard on gremlin now (P1a, `5527c898` / `22312b44`).
- **Not built yet** = the mockup's words for later steps (P1b Lighting and
  Screen, P1d the art, P2-P4 Indicators, Connection, Battery). Equally open
  to edits.

## The limits every line must fit

- **20 characters a line**, the 6x14 Cozette face. A title is one line.
- **A list row is label + value in 20 characters**, the value
  right-aligned. A row that opens something ends in `>`.
- **Characters:** plain ASCII, plus five extras the face has: `‹` (Back),
  `›`, `•` (the saved choice), `▸`, `✓`. Anything else would need a glyph
  added.
- **8 rows a screen** under the title; longer lists and pages scroll a page
  at a time.

```
|....+....|....+....|   <- 20 columns
```

## Built (P1a, P1b, the bootloader item, P2a and P3)

### The title area

| Text                | When                                                                     |
|:--------------------|:-------------------------------------------------------------------------|
| `Configuration`     | the top level's title                                                    |
| `Turn + Click Knob` | the hint: on lists, after 4 s with no knob input, for 1 s in every 5     |
| `Hold to Go Back`   | second hint displayed for 1s after the `Turn + Click` hint               |
| `Saved`             | 1.3 s after a choice is saved                                            |
| `Cancelled`         | 1.3 s after a choice is left without saving, or Reset counters cancelled |
| `Counters reset`    | 1.3 s after Reset counters                                               |
| `Now on BT 2`, `Already on BT 2`, `Pairing stopped` | 1.3 s after a slot click, or a stop (P3) |

### The top level (title: `Configuration`)

```
Lighting           ▶
Screen           52%
Connection      BT 1
Power       Balanced
Indicators         ▶
Clock            24h
Diagnostics        ▶
Bootloader         ▶
Help               ▶
About              ▶
Exit
```

- Each row starts with its icon, its label at the third cell: Lighting the
  bulb, Screen a desktop, Connection the Bluetooth rune, Power the bolt,
  Indicators the sun, Clock a clock, Diagnostics a chip, Bootloader a desktop
  with a download arrow, Help `?`, About `i`, Exit `×`. A heading carries its
  section's icon; the top level's, the wrench.
- Eleven rows (P2a, 10-25, the mockup's order): Help, About and Exit are on
  page two (the scrollbar shows).
- `Exit` and `◀ Back` rows show in light red when not selected; `▶` marks a
  row that opens a page; the saved option has a squared check.
- The full top level will be (the mockup): Lighting, Screen, Connection,
  Power, Indicators, Clock, Battery, Diagnostics, Bootloader, Help, About, Exit.

### Power (title: `Power`)

```
‹ Back
  Always on
• Balanced
  Power saver
  Lights out
```

The top level's value uses short forms: `Always on`, `Balanced`, `Saver`,
`Lights out`.

### Clock (title: `Clock`)

```
‹ Back
• 24h       13:45:01
  24h          13:45
  12h    1:45:01 PM
  12h        1:45 PM
  Date  Oct 24, 2026
  Off
```

The top level's value: `24h`, `12h`, `Date`, `Off`.

### Diagnostics (title: `Diagnostics`)

```
‹ Back
Health page        >
Camera page        >
Reset counters     >
```

Health page and Camera page open the existing Fn+D pages (their own text,
`graphics/display.c`, not part of this review unless you want it).

### Reset counters (title: `Reset counters`)

The question:

```
Clear the health
counters?


Click: reset
Hold: cancel
```

After a click:

```
Counters reset.


Click: back
```

### Bootloader (title: `Bootloader`)

For a firmware update, as `Fn`+`Esc` does (the board shows its bootloader
notice for 1.5 s, then resets into the ROM, where it looks dead until it's
flashed or replugged). The question:

```
For a firmware
update over USB.


Click: enter
Hold: cancel
```

On battery in its reserve (the RGB cut has fired), the click shows instead:

```
Plug in first:
the battery is low.


Click: back
```

### Help (title: `Help`)

```
‹ Back
Using the menu     >
Customizing        >
Shortcuts          >
Pro tips           >
```

(The mockup adds `More info >`, the QR code: not built yet, P1d.)

#### Using the menu

```
Turn: move
Click: choose, save
Hold: back, cancel
Fn+click: close

Auto-closes after
24 seconds idle.
```

#### Customizing

```
Remap keys & knob at
usevia.app over USB

Load via.json from
the repo: Settings,
Show Design tab,
Load Draft
Definition.
```

#### Shortcuts

```
Fn+Q/W/E  BT slot
  hold 2 s: pair
Slider: BT 2.4G USB
Fn+Lt/Rt  hue
Fn+Up/Dn  brightness
Fn+6/7    saturation
Fn+X      lights
Fn+\      effect
Fn+B      power mode
Fn+C      clock
Fn+PgUp/Dn screen
Fn+Esc    bootloader
```

JD: There's a chance we may remove some of these since, for rarely-used shortcuts, we can use the menu now.

#### Pro tips

```
Balanced sleeps
after 20 min idle.
A key wakes it, and
the key still types.

The lights are the
battery's big cost.
Asleep, a night is
about 1%.

2.4G answers faster;
Bluetooth has three
slots.
```

### About (title: `About`), page 1

Filled in when the page opens. The formats, with an example:

```
Firmware 5527c898
dev, 0x69ff475f
Up 1d 1h 54m
Battery 76.7%
Pack 4017 mV
Left 64h of use
Mode Balanced
Link BT 1 connected
```

| Line      | Format                                                                                                                | When unknown |
|:----------|:----------------------------------------------------------------------------------------------------------------------|:-------------|
| Firmware  | `Firmware <8 hex>`, `+` after it for a build from uncommitted source                                                  |              |
| Build     | `<flavour>, 0x<token>`; flavours: `dev`, `daily`, `fpb`, `instr`, `fault`                                             |              |
| Uptime    | `Up <d>d <h>h <m>m`, or `Up <h>h <m>m` under a day                                                                    |              |
| Battery   | `Battery <n.n>%`                                                                                                      | `Battery -`  |
| Pack      | `Pack <mV> mV`                                                                                                        | `Pack -`     |
| Time left | `Left <h>h of use`                                                                                                    | `Left -`     |
| Mode      | `Mode <Always on / Balanced / Power saver / Lights out>`                                                              |              |
| Link      | `Link USB`; `Link 2.4G <state>`; `Link BT <n> <state>`; states: `idle`, `linking`, `pairing`, `connected`, `rejected` |              |

### Lighting (title: `Lighting`)

```
◀ Back
Effect   Alphas/Mods
Brightness       45%
Hue              260
Saturation       89%
Second color    +324
Lights            On
```

- `Second color` shows for the Alphas/Mods effect (its value is the
  offset in degrees, `+324`); every other effect shows `Speed` with a
  percentage instead.
- **Effect** (a choice that previews as you turn): `Solid`, `Alphas/Mods`,
  `Cycle All`, `Cycle L-R`, `Cycle U-D`, `Jellybean`, `Heatmap`,
  `Rainfall`, `Drift`.
- **Lights** (a choice): `Off`, `On`.
- **Brightness, Saturation, Speed** open the range editor; **Hue, Second
  color** the hue editor (both below).

### Screen (on the top level)

A range: `Off`, then `1%` to `100%` (P2b, 10-25: it was a percentage of 23 levels), 1% a detent and 8% a fast turn; `Fn`+`PgUp`/`PgDn` 1% a press, repeating when held.

### The editors

The range editor: the title (the item's name), a big value in the 20 px
face (10 characters), a bar, then three hints:

```
Turn: change
Click: save
Hold: cancel
```

The hue editor: the title, a colour strip with a marker, the big value
(degrees, `+324` for the second colour), and the same three hints.

### Indicators (P2a, 10-25; title: `Indicators`)

```
◀ Back
Lock lights       1%
Charging         Off
```

- Each opens the range editor, titled `Lock lights` or `Charging light`: `Off`,
  then `1%` to `100%`, 1% a detent and 8% a fast turn (JD: "1-100 in 1%
  increments"). While it's open, the LEDs it sets light at the level shown
  (Caps and Win lock both, or the charging light), whatever their state.
- 1% is the old dimmest level, unchanged; the steps are spaced to look even.

### Connection (P3, 10-25; title: `Connection`)

The top level's value is the link: `BT 1`, `BT 2`, `BT 3`, `2.4G` or `USB`.

**Off Bluetooth** (the slider on 2.4G or the cable), JD's words (10-25):

```
Switch to BT mode to
change Bluetooth
settings.

Click: back
```

**On Bluetooth**, a list, the cursor on the current slot:

```
◀ Back
■ Bluetooth 1  Linked
  Bluetooth 2
  Bluetooth 3
Pair a device      ▶
```

- The current slot's word, in six cells: `Linked`, `Trying` (connecting),
  `Pair` (advertising), `Failed`, or none.
- A click on a slot switches to it: the title flashes `Now on BT 2`. On the
  slot you're already linked on (or still connecting on), nothing changes:
  `Already on BT 2`.
- **Pair a device** (title `Pair a device`): `◀ Back`, `Bluetooth 1`,
  `Bluetooth 2`, `Bluetooth 3`. A click starts pairing that slot.
- **Pairing** (title `Pairing`), by what the radio says:

```
Bluetooth 3              On the computer, add
Getting ready...         AK820 5.1-3

Click or hold: stop      Click or hold: stop
```

```
Bluetooth 3 is           Pairing ended.
connected.

Click: back              Click: back
```

```
Pairing didn't           The radio didn't
start. Try again.        confirm pairing.

Click: back              Click or hold: stop
```

  `AK820 5.1-3` is the name the computer lists (the module's own). A flash
  when stopped: `Pairing stopped`. The page stays up to 3 minutes; closing
  the menu leaves pairing running, and the status band shows it.

## Not built yet (the mockup's words)

### About, page 2 (P1d: the bunny beside the first three lines)

```
[bunny] AJAZZ
[bunny] Jackrabbit
[bunny] by JD Lien

github.com/jdlien
  /ak820-pro

QMK Port by fpb
```

### Help > More info (P1d)

The QR code to `https://github.com/jdlien/ak820-pro` (no text in the mockup;
it shows `github.com/jdlien` / `  /ak820-pro` when the QR isn't drawn).

### Battery (P4; on the top level)

A choice: `Percent`, `Hours of use`; the top level's value: `Percent`,
`Hours`.

### Ideas waiting for words

- **A bootloader item** (BACKLOG, the polish phase): what it's for, a click
  to confirm "Enter Bootloader", how to leave without flashing. Maybe not
  needed at all.
