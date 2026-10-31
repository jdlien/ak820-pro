**All three P2s are fixed in both commits.** References below use `0118d39e67e`.

- **P2-1 — fixed.** [indicators.c:227](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:227) matches the applicable SN32F290/CT16B3 [LLD branch](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_gpt_lld.c:456): `GPT_CONTINUOUS`, keyed `MR0=49`, one bounded CRST, `IC=RIS`, keyed MR0 interrupt, then CEN; MR0RST follows. Header dispatch targets GPTD4/CT16B3 correctly. No second, unbounded reset remains. [gptStopTimerI():248](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/hal/src/hal_gpt.c:248) returns the driver to `GPT_READY`; configuration, prescaler and subsequent stops remain consistent.

- **P2-2 — fixed.** [chconf.h:52](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/chconf.h:52) snapshots and restores PHY_EN|ESD_EN around each WFI, entirely under `__disable_irq()`. USB handlers cannot intervene. `ls_usb_phy` and light_task’s cross-WFI restoration are gone ([sleep.c:92](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:92)).

- **P2-3 — fixed.** [ak820pro.c:54](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:54) provides the strong override: forget, then `eeconfig_disable()`. [bootmagic.c:69](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/bootmagic/bootmagic.c:69) invokes it before jumping. [watchdog_record.c:187](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c:187) clears ready and retained magic, then performs the sacrificial store; the ELF confirms that ordering. No other independent pre-capture bootloader request exists in this build; startup’s magic-word dispatch consumes a prior request.

**New findings:** none at P1/P2/P3. The merge preserves the fixes and DS diagnostics.

**RAM:** hash-verified matching ELFs confirm dev **128 B** (`0x20007f70–0x20007ff0`) and daily **2336 B** (`0x200076d0–0x20007ff0`).

**Verdict:** keep `0118d39e67e` on black for controlled validation. `70f7c1ea10e` is code-approved for mainline **after the existing hardware gate passes**: both bits restored, advancing SOFs and working HID without reset across late plug-in, insertion wake, `uhubctl` reconnect including ACTIVE/both-off, and host resume/remote wake.

Git execution was blocked; verification used hash-verified local Git objects and existing ELFs. Nothing modified; no builds or hardware tests run.