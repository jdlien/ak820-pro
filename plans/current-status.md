# Current status — the crash hunt

Updated 2026-09-22, 21:50. The live plan is
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

- **Firmware:** unchanged, the v6 daily build
  (`via-daily-b89777e0f9-dirty-20260922-134320.bin`). Its ELF was overwritten
  by the instrumented build and is gone; v6 records carry no PC, so nothing
  needs it.
- **Agent:** rebuilt with the health history, signed, installed with
  `--clock` at 21:05 (`v0.1.1-58-gc03ecf1-dirty`). It appends one row per
  health read to `~/Library/Logs/ak820pro/ak820-health.csv`.
- **The agent is PAUSED** while the hunt runs (below). The hunt restores it
  at exit; if it does not, `launchctl bootstrap gui/$(id -u)
  ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist`.

## Running right now

`scripts/crash_hunt.py --hours 12 --pause-agent`, started 21:05, detached
(`nohup`), ends ~09:05 on 2026-09-23. Output in
`~/Library/Logs/ak820pro/crash-hunt/20260922-210530/` (`events.log`,
`hunt.csv`, `captures/`, full keymap and lighting backups). The owner may type
during it. Stop early with `pkill -INT -f crash_hunt.py`: it undoes its stress,
compares the board's whole keymap, encoders and lighting against the backup,
and resumes the agent.

**If the keyboard froze:** leave it connected. The watchdog should bring it
back in ~15 s and the hunt captures the record. If it never comes back, read
`ak820 health --crash` once it answers; a cold power-off (cable + unplug
~10 s) destroys the record.

**Do not rebuild `ak820-agent` in release mode while the hunt runs:** it calls
`target/release/ak820` every 30 s, and swapping the file mid-call reads as a
lost board.

## ⚠️ The hunt reproduced the hang at 21:18:52 — and the cause is found

13 minutes in: `lcd_transfer within text`. A synchronous LCD draw re-armed the
flash->LCD DMA while the glyph pump's last transfer was still in flight, which
left SPI0 unable to complete an ordinary `spiSend()`; no timeout, so the
watchdog. Full mechanism and fix in `CRASH-HUNT-PLAN.md` ("First result").
A second codex pass found the same hole in the CPU draws (Caps padlock,
battery fill, icons) and in every external-flash transaction, so the fix is
now `bus_quiesce()` at the start of every CPU transaction on either bus. That
also gives the owner's 13:13 crash (typing, light load) a plausible path. In
the v7 builds from 21:44 (`via-*-a2c3b1a4e1-dirty-20260922-2144*`), not yet
flashed; a narrow third codex pass on the guard's coverage was running at
21:50. The hunt continues on v6 and stops itself at the
next reset (consecutive count 2).

## Built, not flashed: health v7 (Part B)

`ak820pro-builds/out/via-{daily,instrumented}-a2c3b1a4e1-dirty-20260922-2144*`
(`.bin`, `.elf`, `.json` manifest). A HardFault or an unhandled vector now
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
All fixed. The archived
ELFs now carry line info: `scripts/symbolize.sh <pc> <token>` answers with
file:line.

## Next

1. Read the third (narrow) codex pass, fix anything it finds, rebuild.
2. When the hunt ends: rebuild and re-sign the agent (it must decode v7 BEFORE
   the board speaks it; review finding 6), reinstall with `--clock`.
3. With the owner at the keyboard: flash the **instrumented** v7 build and run
   the plan's B6 checks — `HC_FAULT` modes 1, 2, 3 and 5, each read back with
   `ak820 health --crash`, each PC through `scripts/symbolize.sh`, with a cold
   reset after every second reset-causing test (three inside ten minutes would
   switch the watchdog off). Mode 4 (lockup) last: it may need a cold power-off.
   Then flash the **daily** v7, verify keymap, encoders and lighting.
4. Hunt again on the daily v7. The v6 hang came 13 minutes in; hours with no
   reset and a nonzero `blit_busy_waits` (page 6) prove the fix.
5. Parked idea (taskmaster task 6): show a QR code to the agent installer
   (via a jqr.ca redirect) when no agent talks to the board.
6. Still outstanding from before: **reboot the Mac** to prove the agent comes
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
