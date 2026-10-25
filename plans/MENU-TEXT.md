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

## Built (P1a)

### The title area

| Text                | When                                                                     |
|:--------------------|:-------------------------------------------------------------------------|
| `Configuration`     | the top level's title                                                    |
| `Turn + Click Knob` | the hint: on lists, after 4 s with no knob input, for 1 s in every 5     |
| `Hold to Go Back`   | second hint displayed for 1s after the `Turn + Click` hint               |
| `Saved`             | 1.3 s after a choice is saved                                            |
| `Cancelled`         | 1.3 s after a choice is left without saving, or Reset counters cancelled |
| `Counters reset`    | 1.3 s after Reset counters                                               |

### The top level (title: `Configuration`)

```
Power       Balanced
Clock            24h
Diagnostics        >
Help               >
About              >
Exit
```

- `Exit` and `‹ Back` rows show in light red when not selected.
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

### Lighting (P1b; title: `Lighting`)

```
‹ Back
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

### Screen (P1b; on the top level)

A range: `Off`, then a percentage of its 23 levels (`75%`).

### The editors (P1b)

The range editor: the title (the item's name), a big value in the 20 px
face (10 characters), a bar, then three hints:

```
Turn: change
Click: save
Hold: cancel
```

The hue editor: the title, a colour strip with a marker, the big value
(degrees, `+324` for the second colour), and the same three hints.

### Connection (P3; title: `Connection`)

```
‹ Back
• Bluetooth 1
  Bluetooth 2
  Bluetooth 3
Pair a device      >
```

- The top level's value: `BT 1`, `BT 2`, `BT 3` (2.4G belongs to the
  slider).
- A flash on switching: `Now on BT 1`.
- **Pair a device** (title `Pair a device`): `‹ Back`, `Bluetooth 1`,
  `Bluetooth 2`, `Bluetooth 3`.
- **Pairing** (title `Pairing`), the slot's name, a progress strip, then:

```
On the computer, add
AK820 in Bluetooth
settings.

Click or hold: stop
```

  (for the dongle: `Plug the dongle in` / `and keep it close.`). A flash
  when stopped: `Pairing stopped`.

### Indicators (P2; title: `Indicators`)

```
‹ Back
Lock lights      11%
Charging         Off
```

- Levels shown as `Off` or a percentage of 9 steps.
- `Charging` opens as `Charging light` (the editor's title).

### Battery (P4; on the top level)

A choice: `Percent`, `Hours of use`; the top level's value: `Percent`,
`Hours`.

### Ideas waiting for words

- **A bootloader item** (BACKLOG, the polish phase): what it's for, a click
  to confirm "Enter Bootloader", how to leave without flashing. Maybe not
  needed at all.
