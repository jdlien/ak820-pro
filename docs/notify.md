# Notifications: lights, text and a GIF, over the cable or over BT/2.4G

<img src="../assets-src/notify/claude-octopus-preview.gif" width="192" align="right" alt="the octopus, hopping">

A host can make the board light up and put something on the LCD: a colour
effect over whatever RGB mode is running, plus either two lines in the
host-text band or a **full-screen page** — a GIF from flash, or big
word-wrapped text — that stays until any key is pressed. The key that
dismisses it is swallowed. The host can **close** the page itself, and a page
can be a **question answered on the board** — a permission, a choice, or
checkboxes — with the answer sent back to the host, over BT/2.4G too. Firmware: `notify.c`, the page in `display.c`,
raw-HID channel `0x14` in `hid_protocol.c`. Host: `hostagent/ak820notify.py`
(**Linux only**).

The motivating use is [Claude Code](#claude-code): the octopus hops when a turn
finishes, and a tool permission or an `AskUserQuestion` is answered with the
arrow keys and Enter, without touching the terminal.

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
[0] hdr   seq:2 | effect:3 | page:1 | kind:2   (0 SHOW, 1 CLOSE, 2 ASK)
[1] hue   0-255 (QMK scale)
[2] dur   lighting time in 100 ms units; 0 = none, 255 = until dismissed
[3] gif   SHOW page: slot 1-5, 0 = text.  ASK: flags (below)
[4] len   text bytes, <= 44
[5..]     ASCII, '\n' forces a line break
[5+len]   CRC-8 (poly 0x07, init 0) over everything before it
```

Frames must be at least 400 ms apart on the LED channel, or two of them merge
into one oversized frame that fails the length check (measured: 4 of 5 lost
when sent back to back). The host tool waits 600 ms after its previous send.

Effects: `solid`, `blink`, `breathe`, `sweep` (a band left to right). They are
drawn in `rgb_matrix_indicators_advanced_kb`, so they sit on top of any mode,
and RGB is switched on for the duration if it was off.

With the cable the same frame goes in one report:
`[0x07 SET_VALUE][0x14][0x01 NOTIFY_SHOW][frame...]` — text is limited to 23
bytes there — or, for anything longer, in pieces:
`[0x07][0x14][0x05 NOTIFY_STAGE][offset][n][n bytes]` then
`[0x07][0x14][0x06 NOTIFY_COMMIT][len]`. Each piece states its length because
the report length is always the full 32. `[0x07][0x14][0x02 NOTIFY_STATS]` returns the decoder counters.
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

### Close from the host

`CLOSE` closes the page and ends an until-dismissed effect. The Claude Code
hook sends it when you are clearly back at the computer — a new prompt, a tool
running after you answered in the terminal — and only if a page may be open,
so ordinary tool calls cost nothing.

### Questions

`ASK` is a page with a title, up to two detail lines and up to four options.
Its flags byte: bits 1-0 = number of detail lines, bit 2 = PERM (option 1
answers allow, option 2 deny), bit 3 = MULTI (checkboxes), bits 5-4 = SLOT.

Up to **four questions wait at once** — several Claude Code sessions asking
together. The queue lives on the board, so switching is instant: the title
shows `n/m`, and answering one shows the next. `CLOSE` with bit 7 of the
flags byte drops one slot (bits 5-4) — the host withdrew that question; a
plain `CLOSE` leaves waiting questions alone, and a `SHOW` page arriving
while questions wait only lights up instead of taking the screen.

| key | does |
|---|---|
| arrows | move the cursor (Left/Up back, Right/Down forward) |
| Space | tick / untick (MULTI) |
| Enter | answer |
| Esc | cancel: the question goes back to the computer |
| PgUp / PgDn, Home / End | previous / next question in the queue |
| Fn (layer keys) | pass through, so Fn+U / Fn+O reach PgUp / PgDn |
| anything else | **ignored** — the question stays up |

Ignoring stray keys is deliberate: the first version cancelled on any key,
and while you are typing that is exactly the key most likely to arrive.

The answer has to come back over BT/2.4G too, and besides keystrokes the only
board-to-host path the CH582F carries is a consumer report. So it is one HID
consumer usage, from AL usages nothing binds by default:

| answer | usage | Linux key |
|---|---|---|
| allow | `0x191` AL Finance | `KEY_FINANCE` |
| deny | `0x1AB` AL Spell Check | `KEY_SPELLCHECK` |
| cancel | `0x1BD` AL Info | `KEY_INFO` |
| option 1-4 | `0x1B6` `0x1B7` `0x1B8` `0x1BC` | `KEY_IMAGES` `AUDIO` `VIDEO` `MESSENGER` |

Every answer is preceded by its slot's marker — `0x199` AL Network Chat,
`0x1A7` Documents, `0x1AE` Keyboard Layout, `0x18E` Calendar (`KEY_CHAT`,
`KEY_DOCUMENTS`, `KEY_KEYBOARD`, `KEY_CALENDAR`) — so each waiting asker takes
only its own. A multi-select sends every ticked option — one per 10 Hz tick with a release
in between, so consecutive usages are not merged into one report — then
*allow* as the end marker. `ak820notify.py ask` reads the `MSC_SCAN` value
from the "Consumer Control" input device of the receiver or the board (media
keys only, never typing) and prints `allow`, `deny`, `cancel`, `choice:N`,
`multi:N,M`, `timeout`, or `aborted` when SIGTERM tells it the question was
dealt with at the computer.

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
uaccess. `ask` waits `TIMEOUT` seconds (`~/.config/ak820notify.conf`, default
300).

## Claude Code

`hostagent/claude-code/ak820-claude-hook.sh` (the settings snippet is in its
header):

- **Stop** — the octopus, full screen, orange breathe, until a key.
- **PermissionRequest**, synchronous — the question goes to the board and the
  answer comes back as Claude Code's decision: *Allow / Deny* for a tool, the
  options of an `AskUserQuestion` (a single choice, or checkboxes when
  `multiSelect`). The chosen labels go back as `updatedInput.answers`. No
  answer within `TIMEOUT`: the hook says nothing and Claude asks in the
  terminal as usual. While it waits Claude Code does not show a tool
  permission in the terminal (it does show an `AskUserQuestion`); Esc on the
  board hands it back at once.
- **Notification** `permission_prompt` — the question is in the terminal now:
  a reminder page, skipped if you just cancelled on the board.
- **UserPromptSubmit / PostToolUse / PostToolUseFailure / PermissionDenied /
  SessionEnd** — you are back: a question still waiting on the board is
  aborted, an open page is closed. Only events from the **same session**
  count, and a tool event only if it is the very tool whose permission was
  asked. The first version reacted to any of them: a second Claude Code
  session, or a parallel tool call finishing, aborted the question a second
  before you pressed Enter on a board that was no longer listening.

`ak820notify.py` takes a free slot per question (`busy` if all four are
taken: that one stays in the terminal) and serialises the sends itself,
holding the lock only while sending — never while waiting — so questions
from several sessions wait at the same time. Don't wrap it in another lock:
held across the call, it deadlocks against the one inside.

## Not tested

- Bluetooth (only the 2.4G receiver and the cable).
- JD's panel variant: everything above ran on an fpb-panel board.
- Any host but Linux. The raw-HID half is portable; driving one keyboard's LEDs
  from macOS or Windows is the open question.
