# Icon only onto white (10-30 17:28)

The battery readout's fourth option, Icon only (JD's idea of 10-27,
[`../../plans/BACKLOG.md`](../../plans/BACKLOG.md), "Icon only"): the
dashboard's text slot left clear, the icon's fill and colours, the bolt and
the bulb kept, and `Low`, `Charge`, `USB` and `No Batt` kept for what an
empty or red bar means. The menu's Battery page gains its row 4; the note
moves under it to row 5, behind the profile summary's grey rule while it
says something ([`../../plans/MENU-TEXT.md`](../../plans/MENU-TEXT.md),
"Battery").

**Build:** `via-dev-5c8c5f5ea8-20261030-172709.bin` (dev, token
`0x5b880dd4`, 240,946 B, heap gap 224 B), the branch `icon-only` on the
mainline `8ec0c8b9b4`. White ran Warren's ds-phase `fcb7ae00b4` before it;
those diagnostics stay on black.

**Host checks, all passing:** `scripts/batt_text_test.c`,
`scripts/menu_s0_test.c` (the page in Small and Large, the rule with and
without a note, the commit and the top level's value), `scripts/profiles_test.c`
(the record's bit 4, its validity, the `*`, the live record),
`scripts/diag_sim/run.sh` (kb_eeconfig's byte 9, every value) and
`scripts/profiles_host_test.py` (the decode, and the restore onto a firmware
from before Icon only and one from before the Font setting, against a fake
board).

## The flash

`flash-white.sh`, its output in `run.log`. White on Buzz's relay cable,
on its pack (relay 2 never touched: the drain), the daemon paused
throughout.

- Data on 17:28:28-17:28:59.
- The board answered `0xf2a645a7` (fcb7ae00b4, as on both boards), so the
  script checked the level too: 47.7%, white's mid-drain one
  (`battery-before.txt`). Power saver, as since ~08:55 10-29.
- flash.sh: the keymap, the lighting, the profiles and the live settings
  backed up to the default files, the battery log dumped
  (`~/Documents/ak820pro-battlogs/log-20261030-172830-preflash.csv`, 165
  entries), flashed, the keymap restored and verified, the profiles and the
  live settings restored and read back ("battery both, font regular, power
  Power saver"), the clock left to the daemon.
- Token after: `0x5b880dd4`. The level read "unknown" 5 s after the boot
  (`battery-after.txt`), before the module's first `5C`; on battery it
  comes straight back.

## What the flash ended on white

Warren's ds-phase build came off white with this flash, and its op 24 slots
weren't read first (codex's note). The battery log dumped at the flash
stands in: 165 entries, 15 min apart without a gap, from 00:20 10-29 to
17:20 10-30. The RAM log restarts at any reset, so white had none from the
10-29 flash to this one (41 h; 113,168 s asleep, 35,332 awake). The 12:49
read had the ring to sleep 31.

## Codex

`../../plans/review-codex-icon-only-2026-10-30.md`, on the diff and the
host tool, run alongside the flash (it finished at 17:29, just after it):
no blocker. Node 63 fits every place a
node is packed; the byte's garbage rule comes before both setters, each
keeping the other's field; older profile records stay valid and the `*`
compares the whole byte; the rule's appearance and removal change the
row's key; the fallbacks go Percent first, then the face, the crcs renewed.
Its one note was the ds-phase slots, above.
