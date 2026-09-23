# Codex third pass on the crash-hunt implementation — 2026-09-22

`codex exec` (fresh session), model **gpt-6-astra**, reasoning effort
**xhigh**, read-only sandbox, 156,147 tokens. A narrow pass: does
`bus_quiesce()` now cover every CPU transaction on either bus, and are the
[second pass](review-codex-crash-hunt-impl2-2026-09-22.md)'s host findings
closed? Run against firmware `1b7f781887`'s tree and the 21:44 daily ELF.
Verbatim below.

**Dispositions.** Coverage verified for every runtime transaction, including
the inlined guards in the built ELF and no wait between a transfer's
`blit_done = false` and its Fire. **Accepted, not changed (Low):**
`lcd_init()` sets the panel pins before its guard; it runs once at boot,
before any DMA can exist. **Fixed (Medium):** reboot detection measured
elapsed time on the wall clock, so an NTP step could fake a reboot; the hunt
now uses the monotonic clock throughout. **Fixed (Low):** a failed settings
READ no longer triggers a restore (which writes flash, even under
`--no-flash`); the hunt stops and says so. A real mismatch is still
restored: `--no-flash` spares the flash the stress writes, not the repair.

---

1. **Verified for runtime transactions; Low — initialization exception.** CPU draws, command sequences, both animation branches, asset/header reads and HID flash commands reach guards before asserting CS or sending: [lcd_bus.c:177](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:177) (also 217, 228, 352, 359, 374, 382, 658, 888), [hid_protocol.c:183](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:183). No runtime caller pre-asserts CS/DC. Literally “every change” is false: [lcd_init():241](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:241) sets CS/DC before its guard; its current call chain is boot-only. SPI1 setup is likewise one-time and precedes any DMA.

   **Verified:** no guard between `blit_done=false` and Fire ([670](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:670)). Retry re-enters the guard with `blit_done=true`; recursion is bounded, with no self-wait or lock deadlock found ([808](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:808), 839). The specified [ELF](/Users/jdlien/code/ak820-pro/ak820pro-builds/out/via-daily-a2c3b1a4e1-dirty-20260922-214418.elf) matches its manifest hash and preserves these inlined guards; clear→Fire is `0x14da→0x157c`, without another wait.

2. **Verified:** the SN32 HAL/DMA driver directly controls both controllers ([hal_spi_v2_lld.c:62](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:62), 173, 228, 256). Board startup configures SPI0 pin mux ([ak820pro.c:32](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:32)). No additional active panel/flash CS writer found.

3. **Verified #3:** restoration responsibility precedes bootout inside `try/finally` ([crash_hunt.py:422](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:422)); mocked interruption resumes the agent. **Verified #4’s original cases:** elapsed-time comparison and limits on both recovery branches work ([357](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:357), 382).

   **Medium:** `time.time()` remains adjustable: a +6-second host-clock step falsely reports continuously advancing uptime as a reboot ([215](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:215)); reproduced with mocks.

   **Low — #6 remains partially open:** normal cleanup respects `--no-flash`, but any mismatch/read failure reaches unconditional full keymap/lighting restoration ([328](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:328), [282](/Users/jdlien/code/ak820-pro/scripts/crash_hunt.py:282)). Mocked `--no-flash` recovery invoked both restore tools.

4. **Verified #5:** header open/read/UTF-8 errors propagate before append; only missing/empty headers return `None` ([history.rs:136](/Users/jdlien/code/ak820-pro/ak820-agent/src/history.rs:136), [162](/Users/jdlien/code/ak820-pro/ak820-agent/src/history.rs:162)).