**P1: None found.** I found no new board-safety blocker for daily use in mode 0 with divider 0.

**P2: Three findings affect diagnostic validity.**

| File:line | Finding and failing scenario |
|---|---|
| [lcd_bus.c:438](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:438), [lcd_bus.c:543](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:543) | **Mode 4 also changes exit timing.** Its compiled send adds two nominal cycles on the successful completion path; its window adds another two before the following DC flip. Thus XS completion→DC-low gains **four cycles**, independently of the entry change. If those cycles accommodate the problematic final byte, mode 4 looks clean for the wrong attributed reason. Other variants also have compiler changes outside their named part, detailed below. |
| [lcd_bus.c:220](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:220), [lcd_bus.c:422](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:422) | **N = 4 does not cover A’s exit overhead.** Mode 2 can cure the fault while mode 3 still garbles simply because mode 3 waits less. That outcome would not distinguish elapsed time from TX_EMPTY/three-idle-read semantics. |
| [lcd_diag.py:69](/Users/jdlien/code/ak820-pro/scripts/lcd_diag.py:69) | **Early diagnostic replies are silently mislabelled.** `bc1b9f42cb` returns `old_queued` in payload bytes 7–8; this script prints it as `exit_extra`. Reading that build can falsely attribute its old-send observation to A’s exit. A capability/version distinction is needed for truthful backward decoding. |

**P3: Notes.**

- [lcd_bus.c:541](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:541): mode 1’s window is **not instruction-equivalent** to the previously failing build. Its changed gaps are shorter, not longer; the critical XS→RASET boundary remains equivalent. Re-establish old-mode reproduction on this ELF before interpreting the other modes.
- [lcd_bus.c:560](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:560): idle-only divider application is sound in software, but live CLKDIV latching is not explicitly established by the allowed reference. If it requires re-latching, a requested slow capture could still run at an unexpected rate.
- [lcd_diag.py:75](/Users/jdlien/code/ak820-pro/scripts/lcd_diag.py:75): `div` reports the **requested** divider, not a register readback or application acknowledgement. Immediately after `div 0`, hardware can still hold the previous divider until the next eligible window.

The six requested checks follow. Cycle counts are **nominal Cortex-M0 instruction estimates**, excluding flash/peripheral wait states and interrupt preemption. Exact elapsed SN32 cycles cannot be established from the ELFs alone.

1. **Source isolation holds; strict compiled isolation does not.**

   Each wrapper specializes `split_send()` completely. None contains a runtime mode test, and window sends use direct `BL`s. At C level, modes 2–6 retain the old parts in order and substitute only their named logic.

   Two qualifications:

   - Mode 2 includes the newly added `exit_extra` bookkeeping, which was absent from the A implementation in `5688b2a975`.
   - Zero counter increments do **not** make accounting free: bounds checks, comparisons, setup and register preservation still execute.

   Compiled differences beyond the named operations include:

   | Mode | Additional emitted differences from mode 1 |
   |---|---|
   | 2 — exit | TX enqueue loses `mov r5,r9`, saving one instruction per byte. The RX loop samples STAT before incrementing `rx`, whereas old increments first. Register allocation adds a return-value move. |
   | 3 — after | Same one-instruction-per-byte TX saving; changed register allocation and return-value move. **N = 0 still adds eight nominal cycles** on the successful completion path. |
   | 4 — entry | Same TX saving; completion path gains two cycles. Window success branches gain two cycles before each of the first four following DC flips. |
   | 5 — before | Same TX saving; BUSY-loop layout and return code make the completion path **two cycles shorter**. N = 0 still adds eight cycles before the first DATA write. |
   | 6 — accounting | Same TX saving; larger register-save/stack frame, additional setup before transmission, different BUSY-loop register setup and larger restoration sequence. |

   The shared window source also compiles differently between variants: after RAMWR, modes 2/3 take two more cycles than current mode 1 before DC-high; modes 4/5/6 take three more. These differences matter to a test operating at this timescale.

2. **Mode 1’s send matches; its window does not.**

   `spi0_poll_send_old` moves from `0x83c` to `0x848`. Its **280 instruction/padding bytes are identical**, including branch encodings. Only RAM addresses in the literal pool change.

   For successful window sends, these are the gaps between instructions, excluding the GPIO store and `BL` themselves:

   | Boundary | Return→DC, previous → current | DC→next `BL`, previous → current |
   |---|---:|---:|
   | Initial DC-low → CASET | — | **8 → 0** |
   | CASET → XS | **5 → 3** | 1 → 1 |
   | XS → RASET | 4 → 4 | 0 → 0 |
   | RASET → YS | 3 → 3 | 1 → 1 |
   | YS → RAMWR | 4 → 4 | 0 → 0 |
   | RAMWR → final DC-high | **9 → 3** | — |

   Specifically:

   - Old `0xb20–0xb2c` performs mode/argument work after DC-low; current `0x126a` is followed immediately by the call at `0x126c`.
   - Old CASET success takes `BNE` at `0xb34`; current success falls through `BEQ` at `0x1272`: **two cycles less**.
   - Old RAMWR returns through `0xbf8 → 0xb7e` and reconstructs the GPIO operands. Current `0x12a8–0x12ae` avoids that: **six cycles less**.
   - After final DC-high, current code also removes the old unconditional branch into the window epilogue: **three cycles less**.

   **The critical four-byte XS return, DC-low and RASET call retain the old instruction sequence and nominal timing.**

3. **Delay costs and coverage.**

   Both discarded-read loops emit:

   ```asm
   subs counter, #1
   ldr  scratch, [SPI0, #12]
   cmp  counter, #0
   bne  loop
   ```

   With a two-cycle load and three-cycle taken branch, this costs **7N − 2 cycles for N > 0**, excluding setup. N = 4 therefore costs **26 cycles ≈ 0.542 µs** for the loop alone.

   Comparing complete relevant paths in the current ELF:

   | Mode | Function entry through first DATA store | Completed receive loop through return |
   |---|---:|---:|
   | Old | 82 | 49 |
   | Exit | 81 | 110 |
   | After, N=4 | 81 | 87 |
   | Entry | 108 | 51 |
   | Before, N=4 | 114 | 47 |
   | Accounting | 101 | 76 |
   | Full A | 136 | 132 |

   These assume immediate entry-idle success, complete accounting and empty cleanup; they exclude time spent waiting for bytes.

   Consequently:

   - **Named entry-only change:** approximately **+26 cycles / 0.542 µs** before the first DATA write. Before-N=4 adds **32 cycles / 0.667 µs**, so it covers that specialized variant’s net prefix.
   - **Full A’s actual prefix:** +54 cycles currently, +57 in the previous ELF. Before-N=4 does **not** cover that complete prefix.
   - **A’s exit logic itself:** approximately **+50 cycles** in the previous ELF and **+60 cycles** currently over the old BUSY wait, including its non-firing checks.
   - Exit-only’s complete completion path adds **61 cycles / 1.271 µs**; after-N=4 adds **38 cycles / 0.792 µs**. **Default N does not cover the exit side.**

4. **Divider isolation/restoration holds; hardware live-write semantics remain unverified.**

   [Prepare’s configuration](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:173) disables/reconfigures SPI0, writes DIV 0, resets and enables it. The [DMA window marker](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1432) excludes that entire window from divider application, including failure cleanup.

   Painter application requires `blit_done`, TX empty, RX empty and BUSY clear, before CS/DC changes. Only main-thread code starts another transaction, so ISR preemption does not create a competing DMA arm.

   A nonzero request is reapplied after Prepare resets DIV. Returning to zero sets `poll_div_pending`, which remains set until an eligible write. **Default zero/false causes no CLKDIV write.**

   [docs/sn32f299.md:864](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:864) places the enabled-change/FRESET warning in the **CTRL0** entry; the CLKDIV entry gives only the divider formula. That warrants caution, but does **not explicitly establish a CLKDIV-specific reset requirement or an idle-write guarantee**. I did not access the external manual.

5. **Current validation/layout and script decoding hold, with the older-build exception above.**

   The HID handler requires 32 bytes before calling `lcd_diag_op`. Validation rejects subcommands above 4, modes above 6 and dividers above 15 **before mutation**. N accepts the full byte range.

   Payload offsets relative to `data[4]` match the script:

   | Offset | Field |
   |---|---|
   | 0 | mode |
   | 1, 3, 5, 7, 9 | five little-endian 16-bit counters |
   | 11 | 16-bit minimum gap |
   | 13, 17 | 32-bit window counts |
   | 21, 22 | N, requested divider |
   | 23–27 | zero |

   `zero` clears counters and the pending DMA observation, preserving mode/N/divider.

   Parser boundary checks and synthetic reply decoding passed without importing the real device transport. With `5688b2a975`, read/new/old/zero work; unsupported modes and subcommands are rejected. Its unused fields appear as zero, so printed `n=0` is not evidence of supported delay configuration. Earlier `old_queued` builds have the confirmed semantic collision.

6. **Daily mode 0 appears suitable, but the split cannot yet support exclusive causal attribution.**

   No new unbounded path, DMA ownership violation, persistent setting write or unsafe default-divider operation was established. Mode 0 retains A’s guards; the new `exit_extra` check changes its timing even when the counter stays zero.

   For interpretation, a clean screen accompanied by give-ups can reflect recovery/repainting, and changing mode does not force every existing glyph to repaint. Nonzero divider settings also intentionally change the experiment’s timing. Those conditions must remain visible alongside the visual result.

Both ELF hashes match their manifests. Review was read-only; no build, flash, hardware access or file modification occurred.

**NOT READY** for the claimed isolated split experiment.