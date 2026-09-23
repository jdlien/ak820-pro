# Current status — the crash hunt

Updated 2026-09-23, 13:05. The live plan is
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

## Installed right now (14:05)

- **Firmware: the DAILY build at the branch tip**,
  `via-daily-32bb72aa53-20260923-132759.bin`, token `0x3000de57`: v7, the
  lost-write fix and the SPI0 dispatch fix. No test hooks (`HC_PEEK`
  verified refused).
- **A two-hour crash hunt is running on it** (14:02 → ~16:02,
  `~/Library/Logs/ak820pro/crash-hunt/20260923-140219/`): the SPI0 fix's first
  run on hardware. The owner is typing on another keyboard meanwhile.
- **Agent: booted out** since the fault tests. Restore it after the hunt:
  `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist`.
- Keymap and lighting: `~/Documents/ak820pro-{keymap,lighting}.json`
  (refreshed by each flash today) match the verified hunt backup of
  2026-09-22 23:00.

## ✅ The fault recorder works, after a fix (2026-09-23)

All seven `HC_FAULT` modes were verified on hardware. The first runs of
modes 1 and 3 came back invalid: on this chip **the last SRAM write before a
loop that never writes again is lost at the watchdog reset**, and every
handler commits its record and then spins. So the final `FAULT_MAGIC` store
was lost, every time. `DSB` doesn't help; one sacrificial write after it
does (`commit_terminal()`, firmware `02db293696`). The watchdog also **recovers a
locked-up core** (mode 4), with the record intact. Details:
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md), "Third result", and
[`docs/hardware.md`](../docs/hardware.md). ⚠️ The v7 daily build lacks the
fix: a fault on it would record as invalid, so a real crash would read
"unavailable".

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

## Health v7 (Part B) — daily flashed 2026-09-22 22:59; validated 2026-09-23

Daily: `ak820pro-builds/out/via-daily-1b7f781887-20260922-225845.*` (flashed
until the 2026-09-23 fault tests; lacks the lost-write fix above). A
HardFault or an unhandled vector now
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

1. **Flash a daily build with the lost-write fix** and restore the agent.
   The fix is `02db293696`. Do NOT flash `via-daily-32bb72aa53-*`: it
   carries the reverted SPI0 patch.
2. **The DMA that never starts**: the 13:01 hunt found that **all six were
   clock digits** (one 660-byte 15×22 cell, ~5–7% of blits), and none had a
   slow arm (see the plan's "Fourth result",
   [evidence](../history/crash-hunt-2026-09-23-arm-timing/)). An
   instrumented build logging each timeout's source, size, position and the
   blit before it, plus exposure per transfer size, is built but uncommitted:
   `via-instrumented-32bb72aa53-dirty-20260923-140533.bin`. Run it with the
   console captured (`scripts/consolelog.sh`) and a hunt, overnight if the
   owner can spare the keyboard.
3. **SPI0 ISR dispatch: tried and REVERTED.** The fix (`2a17a73b48`) routed
   the SPI0 handler on `sn32_dma_busy` and cleared only the DMA flags it
   read. Its first hunt, on the daily build, gave six "unknown" blit timeouts
   in 21 minutes. Each was a DMA that started and never delivered its
   completion, with a 1.95 s main-loop stall while the wait ran out its long
   bound. The old dispatch gave none in ten hours. Reverted in both
   repositories and pushed (`bf9310ca84`, firmware `7302fc1393`); the hazards
   it aimed at are still open. An instrumented build of it (E1,
   `via-instrumented-32bb72aa53-dirty-20260923-142322`) is being run with the
   console to see how the completion goes missing.
4. Stress the untouched paths: wireless (`tx_timeouts` run at ~35–50% of
   frames in the console just now), RTC I2C, Mac sleep/wake.
5. Keep `deps.lock` on `02db293696` until a better build has survived a hunt.
6. Parked idea (taskmaster task 6): a QR code to the agent installer via a
   jqr.ca redirect.
7. Still outstanding: **reboot the Mac** to prove the agent comes back on its
   own after login.

## Repository notes

Pushed 2026-09-23, all three repositories. Firmware branch `ak820pro-jdlien`:
`02db293696` (the lost-write fix and its test aids), `32bb72aa53` (the SPI0
dispatch fix) and `7302fc1393` (its revert, gitlink `bf9310ca84`, the
pre-patch ChibiOS tree). **`deps.lock` pins `02db293696`**, which never had
the SPI0 patch. The tip's tree equals it apart from `PATCHES.md`. `.taskmaster/` stays untracked, as
before; it now holds task 6, the QR idea. The hunt's raw output stays in
`~/Library/Logs/ak820pro/crash-hunt/`; a snapshot of the 21:18 evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).
