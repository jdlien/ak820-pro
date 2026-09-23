# Current status — the crash hunt

Updated 2026-09-22, 23:05. The live plan is
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md); its codex review and every
finding's disposition are linked from it.

## Why

One spontaneous, unexplained watchdog reset on 2026-09-22 at ~13:13
([incident](../history/incident-2026-09-22-wdt/README.md)). The retained
operation breadcrumbs added that afternoon
([WATCHDOG-BREADCRUMBS.md](WATCHDOG-BREADCRUMBS.md)) will name where the main
loop stopped next time. The crash hunt adds what they cannot say (a CPU fault
versus a hang, the PC, stack depth, why blits time out) and tries to provoke
the next reset instead of waiting for it.

## Installed right now

- **Firmware: v7 daily, WITH the hang fix**, flashed 22:59
  (`via-daily-1b7f781887-20260922-225845.bin`, build token `0xebb930f8`,
  ELF and manifest beside it). Keymap and lighting restored from the first
  hunt's verified 21:05 backup (NOT `~/Documents/ak820pro-keymap.json`, which
  is from 2026-09-04 and stale) and verified identical afterwards. First
  readings: health v7; after boot, the interrupt stack had 688 of 1024 bytes
  free and the main stack 1368 of 2048.
- **Agent:** rebuilt and signed with v7 decoding, installed `--clock` at 22:05.
  The history file rotated to `.1` at the schema change; the new
  `ak820-health.csv` has page-6 columns.
- **The agent is PAUSED** while the second hunt runs (below); the hunt
  restores it at exit.

## Running right now: the second hunt, on the FIXED firmware

`scripts/crash_hunt.py --hours 10 --pause-agent`, started 23:00, ends ~09:00
2026-09-23. Output in `~/Library/Logs/ak820pro/crash-hunt/20260922-230010/`.
The v6 firmware hung 13 minutes into the same stress; **hours with no reset
and a nonzero `v_blit_busy_waits` column is the proof of the fix**.

⚠️ **Reading it honestly (added 23:31):** after 30 min and 97,639 blits,
`v_blit_busy_waits` was still **0** -- the guard had not caught one overlap.
One hang in 13 minutes is a thin basis for a rate. So:
- counts > 0 and no reset: the fix is proven;
- 0 and no reset: unproven either way -- the race is rarer than that one
  event suggested;
- a reset with 0: a DIFFERENT mechanism. The prime suspect is the SPI0 ISR
  in chibios-contrib (`hal_spi_v2_lld.c`), which routes to the DMA handler
  on the RAW `RIS & 0x30` whether or not a DMA is in flight, and whose DMA
  handler clears every flag including RXFIFOTHIF -- a stale DMA flag would
  swallow an ordinary `spiSend()`'s interrupt the same way. A fix would route
  on `sn32_dma_busy` and clear only the DMA bits; it lives in the patched
  submodule, so it needs the `ak820pro-patches` branch and the gitlink.
Other readings at 30 min: 3 never-started blit timeouts (all retried), no
stalls >= 25 ms, worst gap 41 ms attributed to flash (consolidations, driven by
the hunt's writes, inside the 60 ms budget), MSP 632 / PSP 1368 bytes free.

**First catch (00:18):** between the 00:17:46 and 00:18:16 readings,
`v_blit_busy_waits` went 0 -> 1 in the SAME window as a never-started blit
(7 -> 8, retry succeeded), and the board carried on. That is the predicted
pairing: the pump armed a transfer that never started, a synchronous draw
arrived inside the ~50 ms before the pump's grace would have recovered it,
and `bus_quiesce()` waited, found it never started, and retried. On v6 the
same coincidence ran `Prepare()` under the stuck transfer -- the 21:18 hang.
One event: corroboration, not proof. At 91 min: 295,803 blits, 8
never-started (all retried), 1 busy-wait, no reset, MSP 616 / PSP 1368 free.

**At 2 h (01:01):** 393,648 blits, 14 never-started (all retried), 3
busy-waits, no reset. Two NON-flash stalls >= 25 ms appeared (00:38, 01:01),
25-26 ms, marked blit -- each in the same 30 s window as a never-started
recovery (one a double: the retry did not start either; one with a busy-wait).
The worst blit-marked gap had been creeping up under this stress without them
(21 -> 24 ms), so a recovery's extra millisecond or two tips an already heavy
synchronous draw past the line; not a new mechanism, and on v6 the busy-wait
case was the hang. Still the keystroke-losing class: watch
`count_ge_25ms_nonflash` in the agent's history under ORDINARY use. The MSP
watermark fell 680 -> 576 free over the two hours as rarer interrupt nestings
turned up (448 of 1024 bytes used at worst); keep watching it. Stop early
with `pkill -f crash_hunt.py` (TERM or INT): it restores and verifies settings
and resumes the agent.

The first hunt (v6, 21:05) was stopped at 22:03. It ignored `pkill -INT` (a
background job inherits SIGINT as ignored), so it was stopped with SIGTERM
and its settings restored from its backup by hand, verified; the script now
handles both signals. Its evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).

**If the keyboard freezes:** leave it connected. The watchdog brings it back
in ~15 s and the hunt captures the record -- on v7 a fault also carries its PC
(`scripts/symbolize.sh <pc> <token>`). A cold power-off destroys the record.

**Do not rebuild `ak820-agent` in release mode while a hunt runs:** it calls
`target/release/ak820` every 30 s.

## ⚠️ The hunt reproduced the hang at 21:18:52 — and the cause is found

13 minutes in: `lcd_transfer within text`. A synchronous LCD draw re-armed the
flash->LCD DMA while the glyph pump's last transfer was still in flight, which
left SPI0 unable to complete an ordinary `spiSend()`; no timeout, so the
watchdog. Full mechanism and fix in `CRASH-HUNT-PLAN.md` ("First result").
A second codex pass found the same hole in the CPU draws (Caps padlock,
battery fill, icons) and in every external-flash transaction, so the fix is
now `bus_quiesce()` at the start of every CPU transaction on either bus. That
also gives the owner's 13:13 crash (typing, light load) a plausible path. A
narrow third codex pass verified the guard covers every runtime transaction
([review](review-codex-crash-hunt-impl3-2026-09-22.md)). Committed as
firmware `1b7f781887`; flashed 22:59 (see above).

## Health v7 (Part B) — flashed 22:59 (daily); instrumented tests pending

Daily: `ak820pro-builds/out/via-daily-1b7f781887-20260922-225845.*` (flashed).
Instrumented, for the B6 tests: rebuild from `1b7f781887` (`./build.sh
instrumented`) rather than use the pre-commit `-dirty` 21:44 one. A HardFault or an unhandled vector now
writes a terminal record with the PC and the interrupted context, and a ChibiOS
halt records its caller. The record's consecutive-reset count clears after 10
healthy minutes, so three spread-out crashes can no longer switch the watchdog
off for good. Page 6 adds stack watermarks, the blit-timeout breakdown and a
build token that `scripts/symbolize.sh` resolves to the archived ELF.
Host simulation passes under ASan/UBSan; the Rust side decodes all of it (364
unit tests). Codex reviewed the implementation twice: no High and twelve
Medium/Low issues the first time
([review-codex-crash-hunt-impl-2026-09-22.md](review-codex-crash-hunt-impl-2026-09-22.md)),
two High (the unguarded bus paths above) and four smaller the second
([review-codex-crash-hunt-impl2-2026-09-22.md](review-codex-crash-hunt-impl2-2026-09-22.md)).
All fixed; the third pass left two small hunt-script fixes, also done. The archived
ELFs now carry line info: `scripts/symbolize.sh <pc> <token>` answers with
file:line.

## Next

1. Read the second hunt's result (`events.log`, `hunt.csv`) in the morning.
2. With the owner at the keyboard: flash the **instrumented** v7 build and run
   the plan's B6 checks -- `HC_FAULT` modes 1, 2, 3 and 5, each read back with
   `ak820 health --crash`, each PC through `scripts/symbolize.sh`, with a cold
   reset after every second reset-causing test (three inside ten minutes would
   switch the watchdog off). Mode 4 (lockup) last: it may need a cold
   power-off. Then flash the daily v7 back. Back up the keymap and lighting
   FIRST, while QMK runs (`flash.sh` does it unless the board is already in the
   bootloader, when it falls back to the files in `~/Documents` -- stale).
3. Bump `deps.lock` and push both repositories when this is released.
4. Parked idea (taskmaster task 6): show a QR code to the agent installer
   (via a jqr.ca redirect) when no agent talks to the board.
5. Still outstanding from before: **reboot the Mac** to prove the agent comes
   back on its own after login (now-playing and the clock).

## Repository notes

Committed 2026-09-22 ~21:55, **not pushed**: firmware `1b7f781887` on
`ak820pro-jdlien` in `qmk_firmware-ak820pro`; the agent, tooling and these
documents in this repo. `deps.lock` still pins the firmware at `b89777e0f9`,
as it did through the breadcrumbs work: bump it (and push the firmware
branch first) when this is released. `.taskmaster/` stays untracked, as
before; it now holds task 6, the QR idea. The hunt's raw output stays in
`~/Library/Logs/ak820pro/crash-hunt/`; a snapshot of the 21:18 evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).
