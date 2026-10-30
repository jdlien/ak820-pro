# Warren's ds-phase onto black (10-30 12:43)

Black is gremlin's board, the one with the watchdog reset inside a deep sleep
on 10-28 (`plans/BACKLOG.md`, "A watchdog reset inside a deep sleep"). White
never repeated that reset (`../ds-phase-cableout-20261029/`). So black now
runs the same diagnostic as white: Warren's `fcb7ae00b4` (dev, token
`0xf2a645a7`, `gremlin/ds-phase`). The point is to catch a repeat with deep
sleep's phases in the watchdog record and op 24's slots 9 and 10.

Black came to Buzz on the relay cable (hub `3-1.3.4` port 2), running
`8ec0c8b9b4` dev (token `0xb5f2fdab`) since Gizmo's flash at 23:34 10-28,
with no reset since (`../black-health-20261030/`).

- **The flash:** `flash-black.sh`, log in `run.log`.
  - The daemon was paused 12:43:15-12:43:47, and data was on for the same
    span.
  - The script refused unless the board read `0xb5f2fdab`. It read that at
    12:43:17, and flash.sh ran at once.
  - The keymap, profiles and live settings were backed up to black's own
    files (`~/Documents/ak820pro-black-*.json`) and restored, then read
    back. White's backups were not touched.
  - The battery log went to `~/Documents/ak820pro-battlogs/black/`.
  - The clock was left to the daemon (its status file under 2 min old), so
    `ak820ctl` never ran and nothing enumerated HID.
  - Relay 2 was not touched (white's drain).
- **After:** token `0xf2a645a7`. The ring is empty with `next_seq` 0, and
  slots 9 and 10 have no `DSL2` magic, as a first boot of this build
  leaves them. The watchdog record is empty and `boot_rstst` 0x01 (the
  bootloader's exit). `slots-after-flash.json`, `health-after-flash.txt`.

Next, Warren's run on black: a sleep with the cable fully out, entered right
after the pull with the idle ladder already past, as on 10-28. Then read
slots 9 and 10 and the watchdog record (`ds_slots.py`, as for white).
