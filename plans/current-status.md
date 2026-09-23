# Current status — the crash hunt

Updated 2026-09-23, 09:05. The live plan is
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
- **The agent is running** (restored by the hunt at 09:00:15).

## ✅ The fix held: ten hours, no reset (second hunt, 23:00 → 09:00)

Same stress that hung v6 in 13 minutes: no reset in 10 h and 1,960,093
blits. The guard caught 7 overlaps, **all 7 alongside a DMA that never
started** -- the predicted mechanism. All 53 blit timeouts were never-starts,
all recovered by one retry. All 8 non-flash stalls ≥ 25 ms (25–26 ms) came
with a never-start recovery. Deepest stack use: interrupt 464/1024, main
680/2048. Settings verified at exit; the agent restored itself at 09:00:15
and is writing v7 rows to `ak820-health.csv`. Evidence:
[`history/crash-hunt-2026-09-23-v7/`](../history/crash-hunt-2026-09-23-v7/).

The first hunt (v6, 21:05) was stopped at 22:03. It ignored `pkill -INT` (a
background job inherits SIGINT as ignored), so it was stopped with SIGTERM
and its settings restored from its backup by hand, verified; the script now
handles both signals. Its evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).

**If the keyboard freezes in ordinary use:** leave it connected. The
watchdog brings it back in ~15 s; read `ak820 health --crash` (on v7 a fault
carries its PC: `scripts/symbolize.sh <pc> <token>`). A cold power-off
destroys the record.

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

1. **The DMA that never starts** (~5/h under hunt stress): now the root of the
   hang and of the only 25 ms stalls left. Why does the SPI1->SPI0 transfer
   sometimes not start after `Fire()`? Residue in SPI1's RX FIFO was tested and
   ruled out on 2026-08-30 (`lcd_bus.c`, `spi1_raw_byte`). Watch
   `blit_never_started` and `count_ge_25ms_nonflash` in the agent's history
   under ORDINARY use first: that is the rate that matters.
2. With the owner at the keyboard: flash the **instrumented** v7 build (rebuild
   from `1b7f781887`) and run the plan's B6 checks -- `HC_FAULT` modes 1, 2, 3
   and 5, each read with `ak820 health --crash`, each PC through
   `scripts/symbolize.sh`, a cold reset after every second reset-causing test.
   Mode 4 (lockup) last. Back up keymap and lighting FIRST while QMK runs (the
   `~/Documents` files are stale: 2026-09-04). Then the daily v7 back.
3. Secondary: the SPI0 ISR in chibios-contrib dispatches on the RAW
   `RIS & 0x30` and its DMA handler clears every flag -- route on
   `sn32_dma_busy`, clear only the DMA bits (patched submodule branch + gitlink).
4. Bump `deps.lock` and push both repositories when this is released.
5. Parked idea (taskmaster task 6): a QR code to the agent installer via a
   jqr.ca redirect.
6. Still outstanding: **reboot the Mac** to prove the agent comes back on its
   own after login.

## Repository notes

Committed 2026-09-22 ~21:55, **not pushed**: firmware `1b7f781887` on
`ak820pro-jdlien` in `qmk_firmware-ak820pro`; the agent, tooling and these
documents in this repo. `deps.lock` still pins the firmware at `b89777e0f9`,
as it did through the breadcrumbs work: bump it (and push the firmware
branch first) when this is released. `.taskmaster/` stays untracked, as
before; it now holds task 6, the QR idea. The hunt's raw output stays in
`~/Library/Logs/ak820pro/crash-hunt/`; a snapshot of the 21:18 evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).
