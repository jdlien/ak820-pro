# Notifications: lights, text and a GIF, over the cable or over BT/2.4G

<img src="../assets-src/notify/claude-octopus-preview.gif" width="192" align="right" alt="the octopus, hopping">

A host can make the board light up and put something on the LCD: a colour
effect over whatever RGB mode is running, plus either two lines in the
host-text band or a **full-screen page** — a GIF from flash, or big
word-wrapped text — that stays until any key is pressed. The key that
dismisses it is swallowed. Firmware: `notify.c`, the page in `display.c`,
raw-HID channel `0x14` in `hid_protocol.c`. Host: `hostagent/ak820notify.py`
(**Linux only**).

The motivating use is [Claude Code](#claude-code): the octopus hops when a turn
finishes, a yellow page says which tool wants permission.

## The hard part: BT/2.4G has no data channel

Over the air the CH582F forwards exactly one thing from host to board: the
keyboard-LED bitmap (`5A <leds>` on the UART, see [wireless.md](wireless.md)).
Raw HID replies were rerouted to USB for that reason; host-to-board raw HID
does not exist without the cable.

So the LEDs are the channel. **Num Lock and Scroll Lock** — this board has
neither key — are data lines; Caps Lock is never touched:

- The host only sends the LED report when it **changes**, so every bit is a
  change: toggling Num sends a `0`, toggling Scroll a `1`, MSB first.
- A report where **both** flipped means reports were coalesced somewhere
  (host LED worker, receiver, UART). The decoder poisons the frame.
- Losing two toggles of the same line is invisible to it; the length check and
  the CRC catch that.
- A frame ends after **400 ms** without a change. The host sends every frame
  **twice**, 500 ms apart, with the same 2-bit sequence number; the second copy
  is dropped as a duplicate (within 15 s).
- The compositor rewrites all three lock LEDs whenever the xkb lock state
  moves. Such a change outside a frame opens a garbage frame that fails the
  check; inside a frame it spoils that copy and the repeat carries it.

Only the receiver's own LED class devices change. The host's lock state and
other keyboards are not affected.

### Measured

2.4G receiver, cable attached only to read the counters (`stats`):

| per bit | frames intact |
|---|---|
| 40, 25, 15, 12, 10, 8 ms | 42 / 42 |
| 6 ms | 0 / 3 (every one "both flipped") |

The host defaults to **10 ms**: "Claude / finished" is 168 bits, ~1.7 s per
copy. Bluetooth takes the same path through the module but has **not** been
measured.

## Frame

Identical on both transports:

```
[0] hdr   seq:2 | effect:3 | page:1 | 0:2
[1] hue   0-255 (QMK scale)
[2] dur   lighting time in 100 ms units; 0 = none, 255 = until dismissed
[3] gif   page mode: slot 1-5, 0 = text
[4] len   text bytes, <= 44
[5..]     ASCII, '\n' forces a line break
[5+len]   CRC-8 (poly 0x07, init 0) over everything before it
```

Effects: `solid`, `blink`, `breathe`, `sweep` (a band left to right). They are
drawn in `rgb_matrix_indicators_advanced_kb`, so they sit on top of any mode,
and RGB is switched on for the duration if it was off.

With the cable the same frame goes in one report:
`[0x07 SET_VALUE][0x14][0x01 NOTIFY_SHOW][frame...]` — text is limited to 23
bytes there. `[0x07][0x14][0x02 NOTIFY_STATS]` returns the decoder counters.
`[0x07][0x14][0x03 NOTIFY_BOOTLOADER]` jumps to the ROM bootloader, but is
compiled only with `-DNOTIFY_RAW_BOOTLOADER`: any process that can open the
raw-HID interface could otherwise drop the board into a state that looks
exactly like a dead keyboard.

## The page

Without the page bit the text goes to the host-text band (2 lines, expires
after 3 minutes like any host text). With it:

- **GIF** — if the slot holds a valid one: full screen, one frame per 100 ms
  tick, looping.
- **Text** — otherwise: word-wrapped into 5 centred lines of 12 in the 20px face.

It follows the Fn+D page's rules, because the same traps apply: the entry clear
goes one 16-row band per main-loop pass, text goes one glyph per pass with the
non-blocking try, and the exit reuses the Fn+D staged dashboard restore. No
step blocks the loop for 25 ms. A second notification replaces the page. Fn+D
and the flash animation refuse to start over it, and it will not start over
them.

The "SCR" lock indicator is no longer drawn: with Scroll Lock as a data line
it flickered on every `1` bit.

### GIF slots

Five slots above the asset image, in the always-writable region:

```
slot n at 0xD80000 + (n-1) * 0x80000
  +0x000  "AKN1", frame count (1-15)
  +0x100  frames: 128x128 RGB565, lo-byte-first, 0x8000 apart
```

`ak820notify.py gif-upload N file.gif` converts (letterboxed on black, thinned
to 15 frames if longer) and writes it with `ak820ctl flash write`. Slot data
survives firmware flashes. Playback is a fixed 100 ms per frame.

## Host setup (Linux)

```sh
sudo groupadd -f ak820 && sudo usermod -aG ak820 "$USER"      # log in again
sudo cp hostagent/linux/70-ak820-notify.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger

./venv/bin/python assets-src/notify/mkoctopus.py               # or bring your own GIF
./venv/bin/python hostagent/ak820notify.py gif-upload 1 assets-src/notify/claude-octopus.gif
./venv/bin/python hostagent/ak820notify.py send "Hello" "world" --page --gif 1 --color orange --dur until
```

`--via auto` (the default) uses the cable when the board is on it, the LEDs
otherwise. The rule's comments cover what it grants and why a group rather than
uaccess.

## Claude Code

`hostagent/claude-code/ak820-claude-hook.sh`, registered for `Stop` and for
`Notification` with matcher `permission_prompt` (the snippet is in the
script's header). The send runs in the background and is serialised with
`flock`, so Claude Code never waits on it and two frames never interleave on the
LEDs.

## Not tested

- Bluetooth (only the 2.4G receiver and the cable).
- JD's panel variant: everything above ran on an fpb-panel board.
- Any host but Linux. The raw-HID half is portable; driving one keyboard's LEDs
  from macOS or Windows is the open question.
