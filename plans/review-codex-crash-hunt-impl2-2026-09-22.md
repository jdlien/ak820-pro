# Codex second pass on the crash-hunt implementation — 2026-09-22

`codex exec` (fresh session), model **gpt-6-astra**, reasoning effort
**xhigh**, read-only sandbox, 174,175 tokens. Reviewing the fixes for the
[first pass](review-codex-crash-hunt-impl-2026-09-22.md) and the hang fix in
`lcd_blit_flash()` after the provoked reset of 21:18. Verbatim below.

**Dispositions:** all six adopted. 1 and 2 (High): the hang fix guarded only
`lcd_blit_flash()`; every CPU transaction on either bus now starts with
`bus_quiesce()` -- `lcd_fill_rect`, `lcd_blit_ram`, the panel command
sequences, and the four helpers every external-flash transaction begins in --
and the counter is renamed `blit_busy_waits` (overlaps caught, not
necessarily hangs prevented). 3: responsibility for the agent is taken before
the bootout. 4: reboots are judged by uptime against wall time, and the stop
limits apply to every recovered sample. 5: a header that cannot be read is an
error, not a fresh file. 6: `--no-flash` restores in RAM and leaves the keymap
alone.

---

The re-arm diagnosis is supported, but **two unguarded bus paths can still hang**.

1. **High — CPU rectangle drawing bypasses the fix.** After the last queued glyph, Caps-on can call [display.c:1608](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1608) → `draw_padlock()` → [lcd_fill_rect():170](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:170) without draining DMA. Battery-fill increases and newly appearing transport icons have equivalent paths. SPI0 still has DMA configuration/interrupt enables; a stuck DMA turns the subsequent `spiSend()` into an indefinite wait. **Fix:** drain at CPU drawing entry points, before window/CS/DC changes. Avoid putting that wait inside `lcd_window()`: DMA preparation itself calls it after clearing `blit_done`.

2. **High — SPI1 flash transactions also bypass the fix.** [anim_toggle():891](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:891) reads the header before draining dashboard DMA; [flash_read_bytes():381](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:381) immediately sends on SPID1, whose NVIC vector DMA preparation disabled. HID JEDEC/status/CRC/program transactions have the same missing exclusion. They can corrupt the transfer or wait indefinitely. **Fix:** drain before each public flash transaction asserts CS, and before animation’s header/MADCTL sequence.

3. **Medium — Original #3 remains partially unfixed.** [crash_hunt.py:394](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:394) calls `pause_agent()` before entering `try` or setting `paused`. An interrupt after successful bootout still skips restoration; an isolated mock reproduced this. **Fix:** enter the outer `try` and establish restoration responsibility before attempting bootout.

4. **Medium — Original #6 can now miss a reboot and bypass the stop limit.** [crash_hunt.py:337](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:337) treats nondecreasing uptime as proof of no reboot and returns before checking reset count. A fresh-boot sample at 3,000 ms followed by recovery at 4,000 ms with count **2** returns “continue,” capturing nothing—confirmed with an isolated mock. **Fix:** enforce degraded/count limits on every recovered sample; use elapsed-time-aware boot detection.

5. **Low — Original #11 still swallows header-read failures.** [history.rs:159](/Users/jdlien/code/ak820-pro/ak820-agent/src/history.rs:159) converts open/read errors—including invalid UTF-8—into “fresh file,” allowing another header/schema to be appended. Rotation errors now propagate correctly. **Fix:** return `Result<Option<String>>`; treat only missing/empty files as fresh.

6. **Low — `--no-flash` still saves during cleanup.** [crash_hunt.py:288](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:288) unconditionally saves RGB and writes the stress key during recovery/exit. **Fix:** pass the option into restoration, restore RGB only in RAM, and skip unstressed keymap writes.

All actual DMA arms converge through the new guard: clear, synchronous drawing, probe, animation frames and retry. Recovery sets `blit_done` before retrying and retains its single-retry limit; I found no new recursion or lock deadlock. RTC accesses and the current `lcd_blit_ram()` caller already drain/defer. The raw-RIS ISR dispatch remains unchanged. Busy counts measure intercepted overlaps, **not necessarily one prevented hang each**.

Original dispositions **1, 2, 4, 5, 7–10 and 12 verified**; **3 and 11 partial**, **6 implemented with the gap above**. Both 21:32 artifact sets match their manifest hashes, contain the guard and correct page-6 mapping, and resolve HardFault to `fault.c:51`.

Read-only source/disassembly, syntax checks and isolated mocks only; no hardware access, builds, or process signals.