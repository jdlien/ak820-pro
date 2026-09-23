# First crash hunt — 2026-09-22

The first run of `scripts/crash_hunt.py` (`--hours 12 --pause-agent`),
started 21:05 against the v6 daily firmware
(`via-daily-b89777e0f9-dirty-20260922-134320.bin`, operation breadcrumbs, no
fault records). Plan and analysis:
[`plans/CRASH-HUNT-PLAN.md`](../../plans/CRASH-HUNT-PLAN.md), "First result".

## What happened

**13 minutes in, the board hung and the watchdog reset it.** Lost at 21:18:52,
back at ~21:19:03. The retained record (`capture-01-211903.json`):

```text
lcd_transfer within text; last pass uptime 26197368 ms; reset flags 0x03; consecutive 1
```

The main loop stopped inside `lcd_blit_flash()` (site `lcd_transfer`), called
from the text band's draw (`text`), after 7.3 h of uptime. The owner was
typing (about 380 key presses in the 90 s before the last reading). Blit timeouts did not
move all run (11 before, 11 at the last reading before the hang) and there
were no stalls of 25 ms or more: the loop stopped while **arming** a transfer,
not waiting for one. Keymap, encoders and lighting matched the pre-run backup
afterwards.

**Cause, from the code:** a synchronous draw re-armed the flash→LCD DMA while
the glyph pump's last transfer was still in flight. `Prepare()` rewrote SPI0
under it, SPI0's interrupt enable was left holding only the DMA bits, and the
window command's `spiSend()` -- no timeout -- waited for an interrupt that
could not fire. Fixed in the v7 firmware by `bus_quiesce()` before every CPU
transaction on either bus.

## Files

- `capture-01-211903.json` -- the hunt's capture: the health pages read right
  after the recovery, including the retained record.
- `events-snapshot.log`, `hunt-snapshot.csv` -- the run so far, 30 s health
  readings. Taken at the time in `snapshot-taken-at.txt`; the run continued.
- `run.json` -- the hunt's arguments and the stressed values' originals.

⚠️ The second "WATCHDOG RESET" in `events-snapshot.log` (21:19:40) is **not a
second hang**. It is the same frozen record, re-captured because the script
took "fired last boot and uptime under a minute" as a new reset; that flag
stays set for the whole boot. Fixed in the script since: a reboot is now
judged by uptime against wall time. Its capture is not kept here.
