# Firmware findings, 2026-09-23 — for review

Everything learned on 2026-09-23 while hunting crashes on the AK820 Pro
(SN32F299 Cortex-M0 at 48 MHz, ChibiOS, QMK; one main thread). Written as a
brief for an independent reviewer: what was measured, what was concluded, what
is still unexplained. Measurements are from hardware unless marked otherwise.

**Sources to check claims against** (repository `qmk_firmware-ak820pro/`):

- `keyboards/a_jazz/ak820pro/graphics/lcd_bus.c`: blit arm (`lcd_blit_flash`),
  bounded wait and recovery (`lcd_blit_wait`), `bus_quiesce`, the glyph pump
  entry (`lcd_draw_flash_glyph_try`). The working tree carries uncommitted
  instrumentation under `CONSOLE_ENABLE` / `WDT_TEST_HOOKS`.
- `lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c`:
  the SPI LLD plus the board's flash-to-LCD DMA extension
  (`spiSN32FlashDmaPrepare/Fire/Abort`, `sn32_flash_dma_isr`,
  `SN32_SPI0_HANDLER`). Submodule branch `ak820pro-patches`. The reverted
  dispatch patch is commit `2a17a73b48` there (`git show 2a17a73b48`).
- `lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/UART/hal_serial_lld.c`
  (fix in `c3ca7a9725`), `.../USB/hal_usb_lld.c`,
  `.../SN32F290/hal_efl_lld.c`.
- `keyboards/a_jazz/ak820pro/graphics/display.c`: the glyph queue and clock
  band (`draw_clock`, `queue_line`, the pump).
- `keyboards/a_jazz/ak820pro/watchdog_record.c`, `fault.c`: the fault recorder.
- Reference manual text: `~/code/ajazz-ak820-pro/docs/SN32F299_V1.8_EN.pdf`,
  chapter 13 (SPI), especially 13.7.1 (CTRL0 note 1), 13.7.4 STAT, 13.7.6 RIS,
  13.7.10–13 (DMACTRL, DMACNT, DMAHTCNT, CURCNT).

## A. The fault recorder lost its final write (fixed, `02db293696`)

Terminal records (HardFault, unhandled vector, ChibiOS halt) were committed
into 16 bytes of retained RAM (`.ram7`) as: magic ← 0, payload, magic ←
`FAULT_MAGIC`. The handler then spins until the ~12 s watchdog resets the
chip. **Every record written from a handler came back invalid.** A boot-time
copy of the raw words showed payload written and magic 0. Probes that
wrote RAM *after* the magic made it survive, and the last probe was then
lost instead. `DSB` after the store did not help. One sacrificial store to an
unrelated `.bss` word after the magic fixed it. All seven fault modes then
passed, including a lockup (fault inside HardFault), which the watchdog
recovers.

Conclusion drawn: on this part the last SRAM write before a loop that never
writes RAM again does not survive a watchdog reset. It sits in a posted-write
stage that only a later write drains; reads do not drain it. Implication
noted but not acted on: an ordinary breadcrumb written just before an
interrupts-off spin that never writes RAM could be lost the same way.

## B. The flash→LCD DMA: "never started" blits are clock digits (open)

### The path

A blit (`lcd_blit_flash`) runs these steps:

1. `bus_quiesce()`.
2. `Prepare()`: disable SPI1's NVIC vector, reconfigure SPI0 (CTRL0 = 0,
   8-bit, FRESET, SPIEN), `DMAEN=0`, `DIR=0` (SPI1 RX → SPI0 TX),
   `DMACNT = bytes − 1`, `DMAHTCNT = (bytes − 1) / 2`.
3. `FRESET` SPI1.
4. Panel window command over SPI0 through `spiSend`, 8-bit.
5. `FLASH_CS` low, then READ plus a 3-byte address on SPI1 by register
   polling.
6. `SPI1->IC = 0x3F`.
7. `Fire()`:
   - `SPI0->IC = 0x3F`;
   - `DL = 16-bit` (no FRESET after it, despite CTRL0 note 1);
   - `IE = DMATCIE | DMAHTIE`;
   - clear and enable the SPI0 NVIC vector;
   - `DMAEN = 1`.
8. Completion arrives as an SPI0 interrupt. `sn32_flash_dma_isr` waits for
   TX empty and not BUSY, sets `DMAEN = 0`, restores 8-bit and
   `IE = RXFIFOTHIE`, re-enables SPI1's vector, and calls `blit_done_cb`
   (sets `blit_done`, raises both CS lines).

`lcd_blit_wait()` runs in two phases:

1. Up to 4,000 spins, treating the transfer as started when
   `DMACNT != programmed || RIS & 0x30`.
2. If it started, up to 1,000,000 more spins (measured as long as 1.95 s).

After that it takes one snapshot under `chSysLock` and classifies the
timeout:

| class | condition |
|---|---|
| never started | `DMACNT == programmed` and no DMA flag |
| IRQ lost | `DMACNT == 0` and DMATCIF set |
| stalled | DMACNT partway |
| unknown | anything else |

It aborts, and a "never started" blit is retried once.

### What was measured

- **Rate.** Under the crash-hunt stress (text pushes every 0.2 s, playback
  flips every 2 s, effect sweeps, keymap and RGB flash writes every 30 s),
  about 5–6 per hour on both daily and instrumented builds. A ten-hour hunt
  recorded 53, all classified "never started" and all recovered by the retry.
  No resets since the 2026-09-22 overlap fix.
- **Arm timing does not matter.** 12% of 194,068 arms had a command phase
  longer than 10 ticks (5.33 µs each). None of the failures did: 0–3 ticks,
  `fire` 0–3 ticks.
- **Only clock digits fail.** One hunt hour counts arms per transfer size:

  | size | what it is | arms | failures |
  |---|---|---|---|
  | 168 B | 6×14 text | 58,493 | 0 |
  | 460 B | 10×23 text | 5,146 | 0 |
  | **660 B** | **15×22 clock face** | **2,989** | **3** |
  | others | 5888 (clock band clear), 3584, 2184, 336, 5060, 1152, 3792, … | ~3,000 | 0 |

  That failure rate on clock digits is about 0.1–0.2%. Across all
  instrumented runs, **13 of 13** failures were clock digits. The failing
  glyphs are the digits '1', '2', '4' and others, at x = 4, 19, 64 and 109,
  so hour digits too, which redraw only on a full band repaint. It is not
  tied to the per-second edge.
- **SPI state just before `Fire()` is always clean.** In every one of more
  than 69,000 arms: SPI0 STAT `0x25` (TX and RX empty), RIS `0x0a`; SPI1
  STAT `0x25`, RIS `0x08`.
- **SPI state at the failure snapshot**, taken ≥ 1 ms after the arm:
  - SPI0 STAT `0x69`: RX FIFO **full**, TX empty, not busy.
  - SPI0 RIS `0x0e` or `0x0f`: RXOVF in some; **no DMAHTIF, no DMATCIF**.
  - SPI1 STAT `0x25` (idle, empty), RIS `0x08`.
- **`DMACNT` never counts down.** At every completion (more than 69,000) it
  reads the programmed value, so "never started" has only ever meant "no DMA
  flag seen within about 1 ms". The flags are cleared by the ISR, which can
  pre-empt the wait before it samples them.
- **`CURCNT` (offset `0x30`, "count from 0 to DMACNT"):**
  - equals the programmed value at every normal completion (69,670 of
    69,670);
  - still holds the previous transfer's final count just before `Fire()`
    (69,672 of 69,673 arms). It is not reset until the engine starts.
- **At the three failures read so far, on the old dispatch (build E3):**

  | failure | `CURCNT` | `DMACTRL` | `pre_cur` before `Fire()` | previous transfer |
  |---|---|---|---|---|
  | 1 | 659 of 659 | 0 | 659 | 660 B clock digit |
  | 2 | 659 of 659 | 0 | 659 | 660 B clock digit |
  | 3 | 659 of 659 | 0 | **167** | a 168 B text glyph |

  In all three `CURCNT` reached full and **`DMAEN` was cleared by the
  hardware**, but neither DMAHTIF nor DMATCIF was pending, and
  `blit_done_cb` never ran.

### Current reading

**The transfer completes; its interrupts are lost.** The engine counts all
660 bytes and clears DMAEN; SPI0 shifts 330 16-bit words out (which is what
fills and overflows its RX FIFO with junk). But neither the half-transfer nor
the completion flag is raised, or something clears them before anyone
services them. The retry then simply draws the glyph again.

A stale `CURCNT` equal to the new length at enable looked like the trigger
(failures 1 and 2), but failure 3 had a stale 167. And 168-byte text glyphs
follow each other at equal lengths constantly without ever failing. What is
special about 660-byte transfers, or about clock digits, is **unexplained**.

**My unverified hypothesis, for you to test or refute.** Under the old
dispatch the half-transfer ISR reads `RIS` and then writes `IC = 0x3F`. If a
higher-priority ISR pre-empts between those two instructions, DMATCIF can be
raised during the pre-emption and wiped by the `IC` write. That ISR could be
the LED row ISR (~188 µs, 3,876/s, 72.8% CPU; priorities in `docs/leds.md`)
or UART2. The result would be a finished transfer, no flags and no callback,
which is the E3 signature. A 660-byte transfer at 24 MHz takes about 220 µs,
with HT to TC about 110 µs. What this does NOT explain is why other sizes
never fail: 168-byte text, 28 µs from HT to TC, is 20 times more common.

### The SPI0 dispatch patch and its regression (reverted)

The SPI0 handler routes on the **raw** status:

```c
if (!((SPID0.spi->RIS & 0x30U) && sn32_flash_dma_isr())) spi_lld_irq_handler(&SPID0);
```

`sn32_flash_dma_isr()` also always writes `IC = 0x3F`. Two hazards were
seen in that:

- a DMATCIF raised between the RIS read and the clear is wiped unseen;
- a stale DMA flag hijacks an ordinary FIFO interrupt, clears RXFIFOTHIF
  without draining, and re-runs the last callback.

Patch `2a17a73b48` changed two things:

- route on `sn32_dma_busy`; outside a window, clear any DMA flag and run the
  FIFO handler;
- inside a window, clear only the DMA flags read (`IC = RIS & 0x30`).

Its first hunt, on the daily build: **six timeouts in 21 minutes, all
"unknown"**, each with a **1.95 s** stall as phase 2 ran out. An
instrumented build of the patch (E1) then showed four failures:

- all clock digits;
- RIS `0x2f`: **DMATCIF set**, still pending at the snapshot after the
  long wait;
- SPI0 RX full, SPI1 idle, pre-fire state clean.

So with that dispatch a completion flag *was* raised and stayed pending while
`IE` should have held `DMATCIE`, yet the handler never serviced it. Reverted
as `bf9310ca84` (firmware `7302fc1393`). **Why that dispatch left a pending,
enabled DMATCIF unserviced for two seconds is unexplained.** Also unexplained:
why the old dispatch's failures show no flag at all.

### Experiments prepared, not yet run to a result

Toggled at run time on one build (`HC_EXPERIMENT`):

- bit 0: FRESET SPI0 after the switch to 16-bit words, before DMAEN;
- bit 1: draw a 660-byte glyph as two 330-byte halves (same source,
  different length).

## C. SN32 serial LLD: lock nesting that could swap bytes (fixed locally, `c3ca7a9725`, not yet hunted)

`load()` in `hal_serial_lld.c` is only ever the output queue's notify
callback. `oqPutTimeout()` and `oqWriteTimeout()` call it with the system
locked. It locked and unlocked around `oqGetI()` anyway, and on ARMv6-M
`osalSysUnlock()` is `cpsie i`, so interrupts came back on inside the caller's
critical section. Consequence: a THRE interrupt left pending by the lock could
run between `load()` taking byte N and writing it to TH, pull byte N+1 and
write it first, swapping two bytes of a CH582F frame. The fix uses the
I-class calls directly under the caller's lock. It also removes an unmatched
`osalSysUnlockFromISR()` after the TH write in the ISR.

Related: about half of all frames to the CH582F wireless module time out
waiting 10 ms for an ACK (`docs/wireless.md`). Now measured, in wired mode,
where the only traffic is a battery poll every 5 s. ACK latency is timed
from the first send, in 1 ms buckets; the last bucket holds everything at
15 ms or more.

| ms | 0–2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15+ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| frames | 0 | 2 | 42 | 46 | 18 | 24 | 4 | 3 | 4 | 4 | 2 | 0 | 9 | 129 |

The worst was 40.5 ms. 149 frames were retransmitted, and **23 ACKs arrived
with nothing in flight**. The distribution is **bimodal**: most ACKs come in
4–7 ms, and about 46% take more than 15 ms. The share is the same **before**
the serial fix (94 of 203 slow) and after (129 of 283), so the fix is not
what changes it. The current guess is module wake-up latency, followed by a
retransmit whose second ACK becomes an orphan. Is there a better explanation?
Is a heartbeat reading of `61 0D 0A` (the ACK frame) consistent with the
orphans?

## D. Inventory of unbounded waits (read-only audit)

Main-loop waits with no bound:

- ChibiOS synchronous SPI (`spiSend`/`spiExchange`, `TIME_INFINITE`). Every
  board call goes through `bus_quiesce()` first. The raw-RIS dispatch hazard
  (B) is not covered.
- `sdWrite` to the CH582F UART, which blocks when the 128-byte queue is full.
- The internal-flash program busy-wait, `hal_efl_lld.c:121`. **Interrupts are
  masked** around each 8-byte line.
- USB SRAM access polls, `hal_usb_lld.c:148/154/197/203`, with interrupts
  masked. One path is reachable from the main loop (`usb_lld_start_in` via
  `obqFlush`). `hal_usb_lld.c:741-743` has the same unlock-inside-lock
  pattern as C.
- `debug_pump_glyph` (`display.c`) has no 50 ms fallback, unlike the text
  pump.

## Questions for the reviewer

1. What mechanism explains B? In particular:
   - completed transfers (`CURCNT` full, DMAEN cleared by hardware) with
     neither DMA flag pending under the old dispatch;
   - the same event with DMATCIF pending but never serviced under the
     patched dispatch;
   - why only 660-byte clock-digit transfers.

   Consider the SPI LLD, the board code, the glyph queue and anything else
   that touches SPI0 or its NVIC state while a transfer is in flight. Check
   write-1-to-clear registers written through bitfields
   (`IC_b.RXFIFOTHIC = true` compiles to a read-modify-write), the ISR's
   `IC = 0x3F`, `nvicClearPending` and `nvicEnableVector` in `Fire()`,
   interrupt priorities, and the LED row ISR at 72.8% CPU.
2. Given B, is `lcd_blit_wait()`'s start detection and classification
   sound, and is the retry safe (it can repeat a transfer that did
   complete)? What should it use instead of DMACNT?
3. What fix would you propose for B, and how would you verify it?
4. Is the serial fix (C) correct and complete? Does the USB LLD need the
   same one?
5. Anything else in these paths that is wrong or fragile: the unbounded
   waits in D, the lost-last-write property in A (other places it could
   bite), ISR priority interactions, or the recovery logic itself.

---

## Resolution and review dispositions (2026-09-23, 15:50)

Codex (`gpt-6-astra`, reasoning effort high) reviewed this brief:
[`review-codex-firmware-findings-2026-09-23.md`](review-codex-firmware-findings-2026-09-23.md).

### B is explained: the half-transfer handler erases a completion that races it

Codex corrected one point: the LED row ISR shares SPI0's priority (3), so it
cannot pre-empt the handler between the `RIS` read and the `IC = 0x3F` write
(`mcuconf.h`; `hal_spi_v2_lld.h:108`). No pre-emption is needed, though. The
two instructions are adjacent (`0x169d4`/`0x169d6` in the ELF), and a
DMATCIF raised between them is wiped unseen. Codex confirmed that race. The
size selectivity follows once the equal-priority LED ISR is counted as
**entry latency**:

- The arm runs in the main loop, so no row ISR is active at that moment.
- The next row ISR starts within the ~70 µs gap and runs ~188 µs (160–261).
  Any SPI0 interrupt raised meanwhile waits for it.
- So the half-transfer handler runs **188–258 µs after the arm** whenever HT
  fires before the row ISR ends.
- At 24 MHz a transfer completes `bytes / 3` µs after the arm. The race needs
  TC inside the span when the HT handler runs: **168 B (TC at 56 µs) and
  460 B (153 µs) never** qualify; **660 B (220 µs) does**; large clears (TC
  at 1.9 ms) never do.

With a read-to-clear window of roughly 100 ns against ~70 µs of jitter, the
model predicts about 1 loss per 700 clock digits. Measured: between 1 in 500
and 1 in 1,700.

The same race explains the patched build's signature, given one inference.
That patch cleared only the bits read, so the late DMATCIF stayed visible,
yet no interrupt followed. So the `IC` write evidently also drops the pending
request. The inference is supported by E1 and not otherwise verified.

**Fix** (ChibiOS `c57623d0d2`, firmware `4762ef03a8`, unpushed until
hunted):

- Clear only the DMA flags read.
- Then, while a transfer is ours, treat DMATCIF now set, or DMAEN already
  cleared by the hardware, as the completion. Count these as rescues
  (`spiSN32FlashDmaRescues()`).
- Run the callback once per arm.
- Clear RXFIFOTHIF with a literal write.

First minute of the E4 hunt: `660:132/0/4`, that is 132 clock-digit arms,
0 timeouts and 4 rescues; every other size 0 and 0. Rescues exceed the old
loss rate because the re-check also catches completions that would have
raised their own interrupt a moment later.

### Dispositions

| # | Codex finding | Disposition |
|---|---|---|
| 1 | HT handler's blanket `IC = 0x3F` erases a racing TC | **Fixed** (`c57623d0d2`); hunt E4 running |
| 2 | `IC_b.RXFIFOTHIC = true` is a read-modify-write on a write-1-to-clear register | **Fixed** (literal write, same commit) |
| 3 | Patched-build signature not proven to be "enabled but ignored"; IE, NVIC and PRIMASK not captured | Accepted; the rescue re-check covers it whichever it was |
| 4 | `lcd_blit_wait()` start detection and classification unsound (DMACNT is static; flags cleared by the ISR) | Accepted. Recovery is safe: a retry repaints the whole window, so the comments claiming "safe only because nothing was transferred" are wrong. Reclassify with CURCNT, DMAEN and a per-arm generation. **Open** |
| 5 | The snapshot is ISR-exclusive, not hardware-atomic | Accepted; affects diagnostics only. **Open** |
| 6 | Mode transitions skip the FRESET required by CTRL0 note 1; hand-back leaves SPI0 RX residue for the FIFO handler | Accepted as hygiene. The junk interrupt tail-chains before the thread resumes, so no premature completion was found in practice. FRESET at hand-back is **open**, as is the `HC_EXPERIMENT` bit-0 test |
| 7 | Completion ISR's 200,000-iteration drain succeeds silently when exhausted | Accepted. **Open** (count it) |
| 8 | Serial fix `c3ca7a9725` correct for its scope; OE not counted; unbounded ISR loop | Fix kept; OE counting **open** |
| 9 | USB `usb_lld_start_in()` has the same unlock-inside-lock | **Fixed** (`c212e20dd2`, firmware `303db5b608`); in build E5 |
| 10 | CH582F pump retransmits before draining RX; a late duplicate ACK pops the next frame | **Fixed**: the pump now runs after the RX drain (uncommitted, in E5). No sequence number exists in the protocol, so the reorder is the mitigation |
| 11 | ACK latency is measured at parse time, not arrival | Accepted; the histogram is an upper bound |
| 12 | Debug-page glyph pump has no recovery; the text pump's 50 ms recovery depends on further queued work | **Open** |
| 13 | `queue_line()` marks the shadow painted at enqueue; a dropped glyph stays missing until its text changes | **Open**; matters only when recovery fails |
| 14 | LED ISR calls thread-class PWM APIs | Accepted; functionally benign on this port. **Open**, low priority |
| 15 | Internal-flash program silently erases the whole sector when a target line is not blank | **Open**: verify every wear-levelling path writes only erased lines |
| 16 | The lost-last-write explanation is a hypothesis; the workaround is supported | Agreed; wording kept as "evidently" |
