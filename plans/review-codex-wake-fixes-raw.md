No P1 found. Three P2s:

- **P2 — [indicators.c:237](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:237): the actual restart remains unbounded.** After the bounded reset succeeds, `gptStartContinuousI()` issues another CRST through `CT16B3_ResetTimer()` and spins indefinitely. If that second reset sticks, black still reaches the watchdog with site 66, not 69. **Fix:** bound the reset inside the actual LLD start, or implement a restart that performs only the bounded reset while preserving GPT state and match setup.

- **P2 — [sleep.c:138](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:138): light sleep’s saved mask can become stale.** USB interrupts run between capture and restoration. A subsequent suspend can be undone by restoring the old enabled pair; conversely, a resume followed by another PMU sleep can leave PHY off because the saved mask was zero. **Fix:** snapshot and restore around each actual WFI under the same interrupt mask, or synchronize the saved state with USB transitions. Dev-only.

- **P2 — [watchdog_record.c:77](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c:77): a bootloader round trip can preserve stale terminal evidence.** Following a site-68/69 reset, held Esc can invoke bootmagic **before** `watchdog_boot_check()`. `bootloader_jump()` leaves the retained record intact; a subsequent software-reset exit can accept it as that boot’s failure. **Fix:** invalidate retained terminal evidence, with the sacrificial write, on intentional bootloader entry—including before `ready`. Normal post-init dev jumps and ordinary fault sites do not have this problem.

**P3 / hardware gate — [sleep.c:903](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:903)** (`cfe649c21b7`:642): deep sleep’s locked snapshot correctly preserves the pair, including ACTIVE-with-both-off after stale SOF. However, reconnection is **not proven**. BUS_WAKEUP/RESUME/RESET handlers enable both bits regardless of driver state, but the supplied documentation does not establish that those events arrive with PHY off. Recovery’s D+ toggle does not enable PHY.

Before mainline, demonstrate both bits returning, advancing SOFs and working HID without reset for:

- Cable-out sleep → key wake → wait beyond recovery → plug in.
- Cable insertion waking the sleeping board.
- `uhubctl` reconnection, including ACTIVE/both-off.
- Cable-in host suspend → host resume and keyboard remote wake.

Otherwise, the register alias/write, locked GPT/ISR handling, zero software-reset count, sacrificial-store ordering and IHRC-safe terminal path look sound. Boot still uses its separate, unguarded timer initialization; there is no new pre-capture caller. The merge preserves DS_LAST flags, IDs/assertion and slots 9–11 correctly. The exact dev ELF verifies **128 B** heap gap; daily’s supplied **2336 B** is above the floor.

**Verdict:** **OK to keep `c7bc7bd0db9` on black for controlled validation. Not ready for mainline:** fix the P2s and pass the USB gate.

Command execution was blocked; review used hash-verified Git objects and the existing ELF. Nothing modified; no tests run.