# The configuration menu's words, for JD's review

Every piece of text the menu shows or will show, gathered 2026-10-24 so JD
can review and edit it (pinned before P1's acceptance:
[`CONFIG-MENU-P1-DESIGN.md`](CONFIG-MENU-P1-DESIGN.md)). **Edit this file
freely**; Warren carries the changes into the code (`menu/menu.c`). Help's
four topics go from this file to the firmware as they are:
`scripts/gen_menu_text.py` reads their fenced blocks (since 10-24) and
refuses a line over 20 characters, or a number (the idle close, Balanced's
sleep) the firmware disagrees with.

- **Built** = on the keyboard on gremlin now (P1a through P5, the settings
  profiles; 10-26).
- **P1d, the art**, Help's More info: built and on JD's board since 23:09
  10-28 (firmware `8ec0c8b9b4`), the section below. Its words are as open to
  edits as the rest.

## The limits every line must fit

- **20 characters a line**, the 6x14 Cozette face. A title is one line.
- **A list row is label + value in 20 characters**, the value
  right-aligned. A row with an icon gives it the first two cells, leaving
  18. A row that opens a page ends in `▶`.
- **Characters:** plain ASCII, plus the face's extras: `◀` (Back), `▶`, the
  green check box (`■` in the listings below: the saved choice), and the
  icons (the top level's, a profile's actions', Bluetooth's states; the
  listings below leave them out). Anything else would need a glyph added.
  Help's topics and a profile's name are plain ASCII only.
- **8 rows a screen** under the title; longer lists and pages scroll a page
  at a time.

```
|....+....|....+....|   <- 20 columns
```

## Built (P1a through P5)

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
| `Try again`         | Bootloader's click, when a key's release couldn't reach the computer over the radio first |
| `Loaded`, `Deleted`, `Renamed` | 1.3 s after a profile's action (P5); `Saved` after its save          |
| `Loaded w/o effect` | a profile whose effect this firmware lacks: the rest loaded              |
| `Full: delete one`  | `+ Save new` with all seven saved                                        |
| `Settings reset`    | 1.3 s after Reset settings (10-27)                                       |
| `Busy, try again`   | a profile's action while the keyboard can't write (a recovery, or a computer restoring the profiles) |
| `Save failed`       | a profile's write failed; no more writes until a restart                 |

### The top level (title: `Configuration`)

```
Lighting           ▶
Screen           52%
Connection      BT 1
Power       Balanced
Indicators         ▶
Clock            24h
Battery      Percent
Profiles      Gaming
Bootloader         ▶
Font       10px bold
Reset settings     ▶
Diagnostics        ▶
Help               ▶
Exit
```

- Each row starts with its icon, its label at the third cell: Lighting the
  bulb, Screen a desktop, Connection the Bluetooth rune, Power the bolt,
  Indicators the sun, Clock a clock, Battery a vertical battery, Profiles a
  folder, Diagnostics a chip, Bootloader a desktop with a download arrow,
  Font a large A and a small one (10-28), Reset settings the anticlockwise
  circle arrow `↺` (10-27), Help `?`, Exit `×`. A heading carries its
  section's icon; the top level's, the wrench.
- Fourteen rows (10-28: Font added, About moved into Diagnostics as System
  info): eight a screen in 8px, page one ending at Profiles, the rest on page
  two; seven a screen in 10px, two pages. Before 10-28, fourteen with About
  and no Font; before 10-27, thirteen; before P5, twelve.
- `Exit` and `◀ Back` rows show in light red when not selected; `▶` marks a
  row that opens a page; the saved option has a squared check.
- Profiles' value is the profile in use: its name (9 characters of it), or
  8 and a `*` once the settings differ from it; `Prof. 3*` for an unnamed
  one that differs; `None` when none is in use.

### Power (title: `Power`)

```
◀ Back
  Always on
■ Balanced
  Power saver
  Lights out
```

The top level's value uses short forms: `Always on`, `Balanced`, `Saver`,
`Lights out`.

### Clock (title: `Clock`)

```
◀ Back
■ 24h:ss    13:45:01
  24h          13:45
  12h:ss  1:45:01 PM
  12h        1:45 PM
  Date  Oct 24, 2026
  Off
```

The options are named as `Fn`+`C` names them (P4, 10-25), and the top
level's value is the option's name: `24h:ss`, `24h`, `12h:ss`, `12h`,
`Date`, `Off`.

### Diagnostics (title: `Diagnostics`)

```
◀ Back
System info        ▶
Health page        ▶
Reset counters     ▶
```

System info is About's page, moved here on 10-28 (the title `System info`,
Diagnostics' icon). Health page opens the existing Fn+D page (its own text,
`graphics/display.c`). The Camera page was removed on 10-28. Dev builds add
Write test.

### Font (10-28; on the top level; title: `Font`)

```
◀ Back
  8px
  10px
■ 10px bold

For the menus and
now playing
```

- The options name the capitals' height: 8px is Cozette 6x14 (the menu as it
  was); 10px is Terminus regular 8x16, with the page titles and the song's
  title still in bold (JD: "we still judiciously use bold"); 10px bold is
  Terminus Bold 8x16 throughout, the default on a fresh board and after
  Reset settings.
- In 10px the note reads `For the menus` / `and now playing`, and the top
  level shows 10px bold as `Bold` (its row has room for 8).
- A rest of 0.3 s on an option shows the whole menu in it, unsaved; a click
  saves it ("Saved"), Back or a hold puts the saved one back ("Cancelled").
- The face is a profile's setting too: saved with it, loaded with it.

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

### Reset settings (10-27; title: `Reset settings`)

The settings as a flash leaves them, JD's defaults (10-27): the lighting
Solid, a warm white (hue 50, saturation 25%, brightness 75%, speed 40%), the
screen at 60%, both indicator lights at 5%, the clock `24h:ss`, the battery
`Percent`, the power mode `Balanced`. The profiles stay; neither side of the
Win/Mac switch keeps one, nor its settings as left, so a flip changes nothing
until a profile is loaded or saved again. The question:

```
Back to defaults?
Profiles are kept.


Click: reset
Hold: cancel
```

Then `Settings reset` flashes and the page reads:

```
Settings reset.


Click: back
```

`Busy, try again` while the keyboard can't write (a recovery, or a computer
restoring the profiles), nothing changed.

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
◀ Back
Using the menu     ▶
Customizing        ▶
Shortcuts          ▶
Pro tips           ▶
More info          ▶
```

(More info, P1d: the credits and the QR code, at the end of this file.)

#### Using the menu

```
Turn: move
Click: choose, save
Hold: back, cancel
Fn+click: close

Auto-closes after
60 seconds idle.
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

### Help in Large (15 columns)

The same topics wrapped for the Large face (Terminus Bold 8x16: 15 columns,
7 rows; plans/MENU-8X16-PLAN.md), the mock-up's text. The generator reads
each block under its "#### Large: <title>" heading. Small keeps the blocks
above.

#### Large: Menu basics

```
Turn: move
Click: choose
Hold: back
Fn+click: close

Closes after 60
seconds idle.
```

#### Large: Customizing

```
Remap keys and
the knob at
usevia.app over
USB.

Load via.json
from the repo:
Settings, Show
Design tab,
Load Draft
Definition.
```

#### Large: Shortcuts

```
Fn+QWE  BT 1-3
 hold 2 s: pair
Slider  BT 2.4G
        or USB
Fn+Lt/Rt  hue
Fn+Up/Dn bright
Fn+6/7 saturate
Fn+X    lights
Fn+\    effect
Fn+B    power
Fn+C    clock
Fn+PgUp/Dn
        screen
Fn+Esc
    bootloader
```

#### Large: Pro tips

```
Balanced sleeps
after 20 min
idle. A key
wakes it and
still types.

The lights are
the battery's
big cost.
Asleep, a night
is about 1%.

2.4G answers
faster; BT has
three slots.
```

### System info (title: `System info`; About until 10-28), page 1

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
Pair device to BT 1
```

- The current slot's word, in six cells: `Linked`, `Trying` (connecting),
  `Pair` (advertising), `Failed`, or none.
- Its icon in the check box's cells, by the same state (JD, 10-25): the
  check box in green (linked, or none), a grey hourglass (`Trying`), the
  Bluetooth rune in blue (`Pair`), a red circled X (`Failed`). The check box
  is green beside the saved option on every page (JD, 10-25: "green
  everywhere").
- A click on a slot switches to it: the title flashes `Now on BT 2`. On the
  slot you're already linked on (or still connecting on), nothing changes:
  `Already on BT 2`.
- **Pair device to BT 1** pairs the current slot (JD, 10-25), the one its
  row names ("Pair (a )device to BT N": with the "a" it's 21 cells of 20):
  a click goes straight to the Pairing page. Pairing takes over that
  slot, so switch slots first to pair a new device on another.
- **Pairing** (title `Pairing`), by what the radio says:

```
Bluetooth 3              On the device, add
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

### Battery (P4, 10-25; on the top level; title: `Battery`)

A choice: `Percent`, `Hours of use`, `Both` (10-26); the top level's
value: `Percent`, `Hours`, `Both`.

```
◀ Back
■ Percent          85%
  Hours of use    160h
  Both        85% 160h
```

Each option shows what the dashboard would show on battery now (JD, 10-25:
"preview the percent and hours of use"), live. While the hours can't show,
their row reads `--` and a note under the list says why (JD: "a warning if
it's not going to display yet"):

```
◀ Back
■ Percent          85%
  Hours of use      --
  Both          85% --

Hours show after an
hour on battery:
40 min to go.
```

Warmed up but plugged in: `Hours show only` / `on battery.`

What the dashboard's battery shows (JD, 10-25: "a '160 h' or something like
that all the time there"):

- **Percent:** `85%`; under 10 h of use left, the hours beside it, `18% 6h`
  (`<1h` under an hour).
- **Hours of use:** `160h` (at most `999h`), `<1h` under an hour. Until there's an estimate
  (the first hour on battery after a boot or a flash) it shows the percent.
- **Both** (JD, 10-26: "an option to show hours & percent"): `85% 160h`,
  `18% <1h`. Seven cells fit beside the bulb; eight (`99% 160h`,
  `100% 51h`) close the space up to fit. Nine won't: at `100%` with 100 h
  or more it shows `100%` alone (JD: "only ever show time if we're under
  99% if it gets too tight"). Until there's an estimate, the percent.
- Either way: `USB`, `Charge`, `No Batt` and `Low` as before. The hours
  count awake time only, so they move with what the lights draw.

### Profiles (P5, 10-25 and 10-26; on the top level; title: `Profiles`)

Up to seven saved sets of settings (eight until 10-27: the eighth record now
keeps the other side of the Win/Mac switch as it was left): the lighting, the
screen's level, the lock and charging lights, the clock and the battery
readout (not the power mode).

```
◀ Back
■ Gaming           ▶
  Profile 2        ▶
+ Save new
```

- The profile in use has the check box. One never named is `Profile n`, n
  its slot.
- **+ Save new** saves the settings as a new profile (`Profile n`, the first
  free slot), which becomes the one in use. With all seven saved it reads
  `Full` on the right, greyed, and a click flashes `Full: delete one`.
- Resting on a profile for 0.3 s previews its lighting and screen level;
  leaving the list puts the settings back.
- A click opens the profile's page.

**A profile's page** (title: its name):

```
◀ Back
  Load
  Save current here
  Rename
  Delete
--------------------
  Drift          100%
  H:43 S:100% B:100%
  52%     24h:ss
```

- Each action has its icon in the first two cells: Load a circled left
  arrow, Save a circled right arrow, Rename a pencil, Delete a trashcan.
- Under a grey rule, the summary: the effect and its speed (Alphas/Mods'
  second colour as `+324`), `Lights off`, or `Unknown` for an effect this
  firmware lacks; the bulb, then hue, saturation and brightness; the screen
  icon and its level, the clock icon and its format. `--` for a setting the
  profile doesn't hold.
- **Load** flashes `Loaded` and goes back to the list, the check box moved.

**Save current here** (title: `Save profile`):

```
Replace Gaming
with these settings?


Click: replace
Hold: cancel
```

Then `Saved`, back on the profile's page with its new summary.

**Delete** (title: `Delete profile`):

```
Delete Gaming?



Click: delete
Hold: cancel
```

Then `Deleted`, back on the list.

**Rename** (title: `Rename profile`):

```
Gaming_
Type a name


Enter, click: save
Esc, hold: cancel
```

- While it's open, typing goes to the name, not the computer: up to 12
  characters, Backspace deleting, the cursor `_` at the end. Then
  `Renamed`; an empty name is `Profile n` again.
- The keys type as US QWERTY reads them, through the keyboard's own keymap
  (VIA's remaps count); the keyboard can't know the computer's layout.

**The Next and Previous keys** (`Prof+` and `Prof-` in VIA, unbound by
default): the next or previous saved profile, its name shown in the
dashboard's status band; `No profiles` with none saved, `Busy` when the
keyboard can't load one.

**The Win/Mac switch** (10-27, no words of its own): each side remembers
the last profile loaded or saved on it, and a flip brings the other side
back as it was left, changes included (JD: "don't lose your settings when
switching between mac/windows"), or loads its profile the first time; its
name in the status band as the keys show theirs. A side with no profile
keeps nothing of its own: a flip to it changes nothing. Saving a profile the
other side uses means that side loads it anew.

## Help > More info (P1d, title: `More info`)

About became System info in Diagnostics on 10-28, so the credits that were to
be About's second page went to Help's More info topic instead. Built 10-28
(`8ec0c8b9b4`, `menu/menu.c`'s "More info"): two screens a turn apart, the
scrollbar showing which.

**Screen one, the credits**, with the splash's bunny (27 x 42, its ink in
levels of white) beside the first three lines; the link in blue. 8px (the
text beside the bunny from cell 5):

```
[bunny] AJAZZ
[bunny] Jackrabbit
[bunny] by JD Lien

github.com/jdlien
  /ak820-pro

QMK Port by fpb
```

10px and 10px bold (15 columns and 7 rows: the link on three lines, and no
room for the blank lines; the text beside the bunny from cell 4):

```
[bunny] AJAZZ
[bunny] Jackrabbit
[bunny] by JD Lien
github.com
  /jdlien
  /ak820-pro
QMK Port by fpb
```

**Screen two, the QR code** to `https://github.com/jdlien/ak820-pro`, no
text: version 3-M, 3 px a module, a 2-module white quiet zone, 99 x 99 and
centred under the title. Made by `scripts/gen_menu_art.py` (the QR encoder
and the bunny both), and checked to decode with macOS's two QR readers from
the host test's frames in all three faces.
