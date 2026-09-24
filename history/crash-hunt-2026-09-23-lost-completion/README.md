# The DMA "never-start", found and fixed (2026-09-23 afternoon)

All runs used the crash-hunt stress (`scripts/crash_hunt.py`) on instrumented
builds with the console captured. The analysis, Codex's review and every
disposition are in
[`plans/FIRMWARE-FINDINGS-2026-09-23.md`](../../plans/FIRMWARE-FINDINGS-2026-09-23.md).
The arm-timing run that preceded these is in
[`../crash-hunt-2026-09-23-arm-timing/`](../crash-hunt-2026-09-23-arm-timing/).

## The finding

Every "never started" blit timeout on record was a transfer that had
**completed**. `CURCNT` was full and `DMAEN` had been cleared by the hardware,
but the SPI0 half-transfer handler had erased its DMATCIF: it read `RIS` and
then wrote `IC = 0x3F`, and the completion raised between those two adjacent
instructions was lost.

Only 660-byte clock digits were exposed. The arm runs between LED row ISRs,
which share SPI0's priority, so the half-transfer handler runs when the next
row ISR ends, 188–258 µs after the arm. A 660-byte transfer at 24 MHz
completes 220 µs after the arm, inside that span. Fixed in ChibiOS
`c57623d0d2`.

## The runs

| build | token | what it tested | result |
|---|---|---|---|
| E1, `32bb72aa53` + diagnostics | `0xd3421237` | the reverted SPI0 dispatch patch (routes on `sn32_dma_busy`, clears only the flags read) | 4 timeouts in 17 min, all **unknown**, all clock digits: DMATCIF **pending** at the snapshot yet never serviced. The patch kept the late flag but lost its interrupt request |
| E3, `3849e6e393` + CURCNT | `0xf2d38a71` | the old dispatch, with CURCNT recorded | 3 timeouts in 5,123 clock digits, 0 in 108,000 others. At each one: `CURCNT` = 659 of 659 and `DMACTRL` = 0, so the transfer had completed; no flag pending; `pre_cur` 659, 659 and **167**, which rules out a stale count |
| E5, `303db5b608` + diagnostics | `0xdd7eaa31` | the fix (clear only what was read, then re-check DMATCIF/DMAEN), plus the USB and CH582F fixes | **3 hours, 580,060 blits, 0 timeouts.** Rescues on 660 B (417 of 25,244) and 672 B (8 of 1,732) only, none on ~530,000 others: exactly the sizes whose completion falls 188–258 µs after the arm. Keymap and lighting verified at exit |

The reverted patch had cleared only the flags it read, which left the racing
DMATCIF visible. That it still raised no further interrupt is evidence that
an `IC` write also drops the pending request. That is inferred from E1 and
not otherwise verified; the fix's re-check makes the question moot.

## Also measured (E3, E5): the CH582F ACK turnaround

The turnaround is bimodal: 4–7 ms, or over 15 ms (about 48%, worst 36 ms).
The share is the same before and after the serial driver's lock fix, so the
slow half is the module itself. Moving the TX pump after the RX drain cut
orphan ACKs from 23 in 24 minutes (E3) to 1 in 3 hours (E5).

## Files

| file | contents |
|---|---|
| `E1-dispatch-patch.log` | E1's timeout reports, once-a-minute counters and ACK histograms |
| `E3-old-dispatch-curcnt.log` | the same lines for E3 |
| `E5-lost-completion-fix.log` | the same lines for E5 |
| `E5-hunt.out` | the E5 hunt's summary |
