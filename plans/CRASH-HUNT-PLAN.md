# Crash hunt — 2026-09-22

**Goal:** make the next watchdog reset — spontaneous or provoked — say as much
as it can about its cause, and then try to provoke one. This plan does not fix
anything; it narrows where to look.

**Status (2026-09-23, 09:05):** the hang is found and fixed, and the fix
held for a ten-hour hunt (see "Second result"). Earlier status (2026-09-22,
21:20): revised after the codex review
([review-codex-crash-hunt-2026-09-22.md](review-codex-crash-hunt-2026-09-22.md));
dispositions at the end.

- **Part A** — installed (signed agent, 21:05); writing `ak820-health.csv`.
- **Part B** — implemented, not flashed. Host simulation passes under
  ASan/UBSan; daily and instrumented builds pass the new handler checks
  (`via-*-a2c3b1a4e1-dirty-20260922-2113*`). The agent and CLI decode it
  (362 unit tests). An implementation review by codex is running. Hardware
  validation (B6) needs the owner at the keyboard.
- **Part C** — first hunt RUNNING since 21:05 on the v6 daily firmware, 12 h,
  `~/Library/Logs/ak820pro/crash-hunt/20260922-210530/`, agent paused for the
  run. Stop early with `pkill -INT -f crash_hunt.py` (restores and verifies
  settings, resumes the agent).

## ⚠️ First result: the hang reproduced in 13 minutes (21:18:52)

The first hunt, on the v6 daily firmware, hung at 21:18:52; the watchdog reset
it 12 s later and the retained record read **`lcd_transfer within text`**
(last pass uptime 26,197,368 ms). Settings verified intact afterwards. Blit
timeouts had NOT moved (11 all run) and there were no stalls: the loop stopped
while ARMING a transfer, not waiting for one. The owner was typing.

**Mechanism (from the code; the fix build tests it):** the glyph pump arms a
DMA and returns, and on the LAST glyph resets its queue, so `gq_pending()`
reads false while that transfer is still in flight. A synchronous draw later
in the same main-loop pass -- the 10 Hz `draw_text_slot()` band clear here --
called `lcd_blit_flash()`, which never checked `lcd_blit_busy()`.
`spiSN32FlashDmaPrepare()` rewrote SPI0 under the live DMA and stopped it
before its completion ISR could restore SPI0's FIFO-mode interrupt enable, so
the window command's `spiSend()` (ChibiOS, no timeout; `spi_lld_exchange()`
never touches IE) waited for an interrupt that could no longer fire.

**Fix:** every CPU transaction on either bus starts with `bus_quiesce()`,
which waits out a transfer still in flight through the bounded, recovering
`lcd_blit_wait()` and counts it (`blit_busy_waits`, page 6). The first version
guarded only `lcd_blit_flash()`; codex's second pass found the same hole in
the CPU draws (`lcd_fill_rect` -- the Caps padlock, battery fill, icons -- and
`lcd_blit_ram`, the panel command sequences) and in every external-flash
transaction (SPI1's vector is off during a DMA). Those CPU draws give the
owner's 13:13 crash (typing, light load) a plausible path: a lock-indicator or
battery repaint landing while the clock's last glyph is in flight. Plausible,
not shown -- that crash left no record. Each count is an overlap that could have
hung, not necessarily one that would have; a hunt night with counts and no
reset is the proof. A related
fragility remains, not yet addressed: the SPI0 ISR routes to the DMA handler on
the RAW `RIS & 0x30`, and that handler clears every flag including RXFIFOTHIF.

## ✅ Second result: the fix held for ten hours (2026-09-22 23:00 → 09:00)

The v7 daily build (`1b7f781887`) under the same stress: **no reset in 10 h
and 1,960,093 blits**. `blit_busy_waits` reached 7, **every one in the same
30 s window as a never-started blit** -- the predicted overlap, waited out
instead of hanging. All 53 blit timeouts were transfers that never started,
all recovered by one retry; none stalled partway or lost their interrupt.
All 8 non-flash stalls ≥ 25 ms (25–26 ms) came with a never-started recovery.
Deepest stack use: interrupt 464/1024, main 680/2048 bytes. Evidence:
[`history/crash-hunt-2026-09-23-v7/`](../history/crash-hunt-2026-09-23-v7/).

**Next thread:** the DMA that never starts (~5/h under this stress) is now
the root of both the hang and the only stalls left. Why does SPI1->SPI0 DMA
sometimes not start after `Fire()`? `lcd_bus.c` already records that
residue in SPI1's RX FIFO was tested and ruled out (2026-08-30). Secondary,
still unaddressed: the SPI0 ISR's raw-RIS dispatch in chibios-contrib.

## What we know

One spontaneous watchdog reset on 2026-09-22 at about 13:13:50, during ordinary
use with the Rust agent pushing now-playing text every ~3 s
([incident](../history/incident-2026-09-22-wdt/README.md)). The boot's uptime
is unknown: the daemon never recorded it. The last health sample before it
(13:12:15) had accumulated:

| counter | crashed boot | this boot (≈6.5 h, v6 daily) |
|---|---|---|
| `blit_timeouts` | 455 | 11 |
| `count_ge_25ms_nonflash` | 28 | 0 |
| `tx_timeouts` (wireless) | 109,030 | 2,242 |
| worst main-loop gap | 36 ms (blit) | 21 ms (blit) |

**The owner's account (added 21:30):** typing normally; no media playing (the
agent showed a paused track, so LCD traffic was a keep-alive push every 30 s at
most and the clock); a FaceTime call with screen sharing; no Fn features beyond
ordinary layer-1 keys. The agent's log puts the stop at ~13:13:50 (unresponsive
13:13:57, back 13:14:05, a ~12 s watchdog), not at a clock sync (13:12:21) or
a known push. So the reset came under LIGHT load: the hunt's heavy LCD stress
does not reproduce those conditions, and ordinary typing (with Part A
recording) is at least as good a test. The Mac's side is unlikely to matter:
USB polling is the host controller's job, not its CPU's, and QMK's blocking
suspend loop is compiled out (`NO_USB_STARTUP_CHECK`, set by the Bluetooth
build), so a suspended port cannot stop the main loop.

Blit timeouts are **ongoing**, not history. Each is an LCD DMA transfer that
did not complete in time; the recovery aborts through
`spiSN32FlashDmaAbort()` (`graphics/lcd_bus.c:737`). That recovery path has
hung the board before: an earlier version left SPI1 deaf and the board went
silent within two seconds (`lcd_bus.c:735`).

The board's own waits are all bounded (the blit waits, the SPI BUSY spin, the
glyph pump's 50 ms grace). A true ≥12 s stop is more likely one of:

1. a wait inside a ChibiOS driver or the blit recovery;
2. a **hard fault** — ChibiOS's default handler (`vectors.S:1025`) spins
   forever, the watchdog fires, and the breadcrumb names whatever operation
   was running: **indistinguishable from a hang today**;
3. a **stack overflow** — `CH_DBG_ENABLE_STACK_CHECK` is `FALSE`, and the
   main-thread stack (PSP, 2 KB at `0x20000400–0x20000C00`) overflows *down
   into the interrupt stack* (MSP, 1 KB at `0x20000000–0x20000400`), where
   interrupt frames live — silent corruption that faults later;
4. an interrupt that never returns — the row ISR already takes 73% of the CPU.

Part B makes 2 visible and 3 measurable. **It gives no retained evidence for
4** (codex finding 14): a non-faulting ISR that never returns reaches neither
new handler, and the breadcrumb then names an innocent main-loop operation.
The only tell is a record naming an operation that cannot plausibly hang.

## Part A — host health history (agent) — installed

- One CSV row per successful health read, in the existing `Ok(h)` arm of the
  daemon loop (`ak820-agent/src/agent.rs`). **No new board traffic** for pages
  1, 2 and 5 (confirmed by the review); the recovery-triggered read is
  captured automatically.
- Keeps the eleven fields the daemon already received and threw away
  (`scan_rate`, `key_presses`, `passes`, `tx_sent`, `tx_drops`,
  `rx_malformed`, `flash_writes`, flash/blit/I²C gap maxima, watchdog flags).
- `ak820-health.csv` beside the log. Header when new; a different header or
  passing 5 MB rotates to `.1` (~70 days at five-minute rows).
- `src/history.rs`, 7 tests. 355 unit tests pass; Windows `cargo check` and
  clippy clean.
- **Done (finding 6):** an unsupported page-5 record format no longer
  discards pages 1–2 (it used to lose every sample for the rest of the boot,
  since the record is frozen). The agent keeps the base telemetry and names
  the format it could not read; `ak820 health` does too unless `--crash` asked
  for the record.
- Page 6 (Part B) will add one request per health read, v7 boards only — the
  only new steady traffic in this plan.

## Part B — firmware: fault capture and vitals (health v7)

### B1. Fault record in the retained RAM

Stay within the existing 16-byte `.ram7` (review Q1 agreed; enlarging is
testable, not unsafe, and can follow if LR/SP turn out to be needed).

- **The handler must not trust MSP (finding 1).** Frame validation alone is
  not enough: a C function's prologue pushes to MSP *before* any validation
  runs, and if MSP is what overflowed, that push faults inside HardFault and
  the M0 locks up. So the naked stub:
  1. keeps EXC_RETURN (LR) and computes the frame pointer (EXC_RETURN bit 2 →
     PSP, else MSP) **in registers only**, with Thumb-1 instructions (`movs`/
     `tst` on registers, no `IT` blocks, no Thumb-2 immediates);
  2. **switches SP to a reserved, aligned emergency stack** (a small array in
     `.bss`, which lies above both stacks and so cannot be reached by either
     overflowing downward);
  3. calls `watchdog_record_fault(frame, exc_return)` and never returns.
- `watchdog_record_fault()` validates the frame (word-aligned, within
  `[__ram0_base__, __ram0_end__ − 32]`) before any load. Unreadable frame →
  PC `0xFFFFFFFF`, exception number `0xFF` ("unknown") — itself evidence of
  stack corruption. The check bounds the *loads*; it cannot validate the
  frame's contents (review Q3).
- From a readable frame: **PC** (`frame[6]`) and the **interrupted exception
  number** (`frame[7] & 0x3F`). 0 means **thread context** — the main thread
  or ChibiOS's idle thread, not necessarily the main loop (finding 4);
  16+n means inside IRQ n.
- **Record layout, per magic (finding 5).** `RECORD_MAGIC` keeps today's
  meaning exactly. `FAULT_MAGIC`: count word = consecutive count (bits 0–7)
  | exception number (bits 8–15), bits 16–31 zero; path word = site
  `WDT_SITE_HARD_FAULT` (23) with the interrupted operation as parent, same
  complement check; last word = PC. Boot validates each magic's own encoding
  and increments only the low byte.
- **Commit protocol:** magic ← 0, then payload, then `FAULT_MAGIC` last —
  the order `watchdog_record_boot()` already uses. A reset part-way leaves no
  magic and so no record, never a PC under the ordinary magic. Tested with
  interrupted writes, not only completed ones.
- **Override `_unhandled_exception`** (the weak target of the unused vectors):
  site `WDT_SITE_UNHANDLED_EXCEPTION` (24), exception number from our own IPSR,
  PC 0 (the `vectors.S` stub reaches it with `bl`, which clobbers EXC_RETURN).
  **NMI is not covered and must not be touched:** this ChibiOS port uses NMI
  for context switching and `NMI_Handler` is a strong symbol in the ELF
  (finding 4). A fault inside NMI escalates straight to lockup.
- **ChibiOS halt (finding 14):** `chSysHalt()` spins with interrupts off and
  never reaches HardFault. Hook `CH_CFG_SYSTEM_HALT_HOOK` (defined
  unconditionally in `boards/common/configs/chconf.h:811`, so `#undef` it in
  a board-level `chconf.h` after `#include_next`) to record site
  `WDT_SITE_HALT` (25). With checks and asserts off it is rarely reachable;
  it costs nothing.
- **Spin afterwards; no reset from the handler** (review Q2 agreed). The
  watchdog resets through the existing path and accounting. It does not
  promise recovery before `watchdog_start()` or in degraded mode.
- **Post-build checks** (`build.sh`): the vector table's HardFault entry
  points at our handler, and `_unhandled_exception` is ours, not the weak one.

### B1b. The consecutive-reset count must age out (finding 3)

Today the count is cleared only by a boot that was not a watchdog reset
(`watchdog_record.c:39`). A healthy week in between does not clear it, so
**three spontaneous crashes weeks apart turn the watchdog off for good** —
in everyday use, not just in a hunt. The guard exists to stop a boot loop,
and a boot loop never runs for long. So: once the board has run healthily
for 10 minutes, clear the retained count. Everything else stays as is.

### B2. Stack watermarks

`crt0_v6m.S:198` paints both stacks `0x55555555` at boot (confirmed). On
request, scan each region from its base with bounded volatile reads for the
first changed word: a **paint-based watermark** (finding 10). It can
overstate headroom — a frame that reserves space without writing it, or a
stored value equal to the paint — and says nothing about the idle thread's
working area (not painted). Also a canary word at the bottom of each region:
changed means the region was exhausted. The deep-call test must write its
allocation. The value dies with a reset, which is why Part A's series
matters.

### B3. Blit-timeout breakdown

`lcd_blit_wait()` computes its discriminator before the abort, but the
console message reads the registers **after** `spiSN32FlashDmaAbort()`,
which clears the SPI flags and NVIC pending state (finding 7). Snapshot
DMACNT/RIS/STAT before the abort; count **never started**, **stalled
partway**, **finished with its interrupt lost**, and **unknown/raced**
separately; count retry attempts and retry successes separately
(`blit_retries` counts attempts before their outcome). These tell symptoms
apart; they do not prove three root causes. Also count blits issued, so a
soak can report real exposure (finding 15).

### B4. Page 6 and build identity

`HC_GET6 = 0x09`, health protocol **7**; pages 1–5 unchanged. Byte layout,
little-endian, 28 payload bytes, counters saturating:

| offset | width | field |
|---|---|---|
| 0 | u32 | uptime_ms |
| 4 | u32 | build token |
| 8 | u16 | MSP watermark free bytes (0: bottom canary gone) |
| 10 | u16 | PSP (main thread) watermark free bytes, same rule |
| 12 | u16 | blit timeouts: never started |
| 14 | u16 | blit timeouts: stalled partway |
| 16 | u16 | blit timeouts: finished, IRQ lost |
| 18 | u16 | blit timeouts: unknown/raced |
| 20 | u16 | `blit_busy_waits`: CPU bus transactions that found a DMA in flight and waited (the 21:18 hang, above) |
| 22 | u16 | retry successes |
| 24 | u32 | blits issued |

Stack sizes are fixed by the link and live in the manifest, not on the wire.

**Build identity (findings 11, 12).** The ELF for the firmware on the board
today is already gone: `.build/a_jazz_ak820pro_via.elf` is overwritten by
every build, and the 13:45 instrumented build replaced the 13:43 daily one.
And the artifact name's timestamp is not the embedded `QMK_BUILDDATE`
(13:44:58 inside, `134520` outside). So `build.sh`, under its existing lock,
generates a random 32-bit **build token**, compiles it in, and archives
`<artifact>.elf` plus a manifest (token, flavour and options, git hash and
dirty state, SHA-256 of `.bin` and `.elf`). `scripts/symbolize.sh <pc>`
finds the ELF by the token the board reports, refuses an ambiguous or
missing match, and runs `addr2line -f`.

### B5. Rust

Decode page-5 format 2 and page 6, name sites 23–25, print
`hard_fault at pc 0x… in thread|irq N within <op>`. The one-time recovery log
line carries PC and exception number. **The decoder upgrade ships before the
v7 firmware** (finding 6).

### B6. Validation

- **Host C simulation** (extends the existing ASan/UBSan harness): both
  magics, count-word encodings and corruption rejection, frame validation at
  every boundary, format-2 wire layout, interrupted fault-record writes,
  count ageing.
- **Instrumented build, test hook `HC_FAULT = 0x7F`** beside `HC_STALL`.
  ⚠️ Each of modes 1–4 is a watchdog reset, and three inside ten minutes reach
  degraded mode (watchdog OFF for that boot). The firmware refuses modes 1–4
  while degraded, and the procedure **cold-resets (cable out ~10 s) after
  every second test**, so the lockup test never runs without a watchdog
  (implementation review, finding 2). Read each record before the cold reset:
  it destroys it.
  - mode 1: `udf` in thread context → `hard_fault`, thread, parent
    `test_fault` (the hook's own scope), PC symbolized to `hid_protocol.c`;
  - mode 2: fault **inside an ISR** (a test-build-only handler on an unused
    IRQ, pended from the hook) → exception 16+n, which exercises the MSP path;
  - mode 3: enable and pend an unused IRQ with no handler →
    `unhandled_exception` with that vector;
  - mode 4 (costs a cold power-off if it fails): fault **inside HardFault**
    itself → lockup. Answers whether the watchdog recovers a locked-up core
    here. Sonix specifies an ILRC-clocked watchdog independent of interrupt
    delivery and ARM says reset exits lockup; neither says so for this part.
- Watermarks: stable across reads; the deep-call hook moves PSP's.
- Flash daily v7; verify keymap, encoders and lighting restored, as for v6.

## Part C — the crash hunt — running

`scripts/crash_hunt.py` (a separate script: `soak.py` stays the five-minute
pass/fail gate for firmware changes). What it does:

- **Stress:** text on both lines every 0.2 s; playback-state flips every
  2 s (the band handoff that drove the S2 soaks to 216 blit timeouts); an RGB
  effect sweep every 20 s **without saving**; one keymap flip and one RGB save
  per 30 s; a liveness ping every 0.1 s.
- **Measurement only through the Rust CLI** (`ak820 health --rows --isr
  --crash --json` every 30 s, handle closed first): one decoder, and uptime,
  ISR stats and the retained record are all in the CSV.
- **A lost board is the event, not the end:** wait up to 120 s, capture the
  record **before** touching anything else, and continue. Stop at 2
  consecutive watchdog resets (a third turns the watchdog off, finding 3),
  refuse to start degraded.
- `--pause-agent` boots the agent out for the run and restores it at exit
  (the clock re-converges). VIA must be closed.

**Done (findings 2, 9, 13, 15):**

- **A full backup before any stress** with `ak820keymap.py dump` and
  `ak820lighting.py dump` into the run directory, never overwritten. After
  every recovery: capture, restore the stress key, then **compare the whole
  keymap, encoders and lighting against the backup**. A reset during a
  wear-levelling consolidation (erase, then rewrite) can leave a bad checksum,
  and a bad checksum clears the logical EEPROM (`wear_leveling.c:234`,
  `:303`). A mismatch stops the hunt, restores from the backup, and verifies.
  The kb datablock (BT slot, LCD brightness, clock format, RTC period) has no
  backup tool; its loss is reported, not repaired.
- **The RGB save is synchronous** (`via.c:737` →
  `eeconfig_force_flush_rgb_matrix()`), not the deferred, settle-gated flush
  `soak.py`'s docstring describes. Check the save's acknowledgment.
- **Stricter replies:** check each VIA reply's echoed selector bytes, not just
  the command byte.
- **Record the exposure:** the stress configuration and counts of text
  pushes, playback flips, keymap flips and RGB saves, next to the board's own
  blit count (B4).
- **Controls:** a quiet high-rate night constrains the production failure
  only weakly (finding 15). Part A's history under ordinary use is the
  control; a hunt night is compared against it, not judged alone.

**Flash wear (finding 8).** The wear-levelled EEPROM is a 2 KB backing store
for 1 KB of logical data; its 1,016-byte log holds 127 eight-byte entries of at
most five data bytes each, and a consolidation erases both sectors. The
8-byte RGB config costs two entries per save. At the hunt's cadence: ~2,880
entries and ~23 erases per sector a night. Endurance per codex's citation of
the SN32F297 manual v1.8, p.264: **20k erase/program cycles minimum, 100k
typical** (not independently checked) — roughly 870 nights at the minimum.
`flash_writes` counts unlock-hook calls, not entries.

**Expectation:** one crash in several days of real use. A quiet night proves
little; a night with a record gives us its location.

On enumeration (finding 13): `crash_hunt.py` is macOS-only and opens the board
through `ak820health.open_device()`, which enumerates. CLAUDE.md's ban comes
from Windows, where `hid_enumerate` opens every device and wedged a UPS. On
macOS hidapi reads IOKit properties without opening devices, and `soak.py`,
`flash.sh`'s backup tools and `ak820keymap.py` already do this routinely. The
script refuses to run anywhere but macOS.

## Later, not in this plan

- USB suspend/resume churn (`pmset sleepnow` + wake loop). The pending
  Mac-reboot test of the agent is one data point.
- Fuzzing the CH582F parser through `HC_INJECT` (instrumented;
  `bt_faults.py` already replays captures through it).
- Raw-HID fuzzing with a strict allow-list — VIA's channel includes bootloader
  jump and EEPROM reset, and the asset channel's flash write erases first.
- Retained evidence of an ISR livelock (finding 14): e.g. the watchdog in
  interrupt mode at top priority, capturing the preempted PC before a
  software reset. A real design change; only if the evidence points there.

## Review dispositions

| # | sev | finding | disposition |
|---|---|---|---|
| 1 | High | C recorder uses MSP before validating | **Adopted:** register-only stub, emergency stack in `.bss`, Thumb-1; ISR-context test (B1, B6) |
| 2 | High | restore misses a consolidation interrupted by a reset | **Adopted:** full backup, whole-state compare after each recovery, stop on mismatch (C) |
| 3 | High | the consecutive count never ages out | **Adopted** in the hunt (stop at 2, refuse degraded) **and in firmware** (B1b) — it is an everyday flaw |
| 4 | Med | NMI belongs to ChibiOS; exception 0 is thread, not main loop | **Adopted;** verified `NMI_Handler` is strong in the ELF (B1) |
| 5 | Med | packed count needs migration and commit protocol | **Adopted** (B1) |
| 6 | Med | old decoder drops the whole sample on format 2 | **Adopted:** tolerant decode (A), decoder before firmware (B5) |
| 7 | Med | console discriminator is read after the abort | **Adopted** (B3); also an existing console bug |
| 8 | Med | wear budget confused writes with entries | **Adopted:** figures corrected (C) |
| 9 | Med | VIA RGB save is synchronous | **Adopted;** verified `via.c:737` (C) |
| 10 | Med | watermark is not minimum SP | **Adopted:** labelled, canaries, bounded reads (B2) |
| 11 | Med | page 6 needs a byte layout | **Adopted** (B4) |
| 12 | Med | artifact names do not identify the build | **Adopted:** token + manifest (B4) |
| 13 | Med | reconnect enumerates HID; weak reply matching | **Reply matching adopted** (C). **Enumeration declined** for this macOS-only script, reasons above |
| 14 | Med | no retained evidence of an ISR livelock | **Claim narrowed** (What we know); halt hook adopted (B1); ISR evidence deferred (Later) |
| 15 | Low | text rate is not exposure | **Adopted:** exposure counts, Part A as control (B3, C) |
