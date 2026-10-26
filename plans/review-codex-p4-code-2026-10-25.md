# Codex: P4, Battery (2026-10-25)

Prompt: `plans/review-prompt-p4-code.txt`. Diff: qmk_firmware-ak820pro `b99d5405..d56980c9`, and the uncommitted tests. Verbatim below; dispositions at the end.

---

**No must-fix found before the planned dev flash.**

- **Settings and EEPROM:** [config.h:271](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:271) correctly sets size **10**, version **7**. [kb_eeconfig.c:187](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:187) implements byte 9’s frozen encoding, invalid→Percent, and deferred writes. The resulting addresses are VIA **47–50**, keymap **51–770**, encoders **771–786**, macros **787–1023**. That leaves **237 macro bytes**, satisfying the dynamic-keymap limit within **1,024 logical bytes / 2,048 backing bytes**.

- **Restore and BT:** [ak820keymap.py:108](C:/Users/jdlien/code/ak820-pro/hostagent/ak820keymap.py:108) restores using keymap-relative commands; encoders use their dedicated command. [ak820lighting.py:122](C:/Users/jdlien/code/ak820-pro/hostagent/ak820lighting.py:122) uses value/save commands. Neither depends on EEPROM addresses. [ch582f_ajazz.c:735](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:735) keeps raw-HID replies over USB with the slider on BT. The erase makes migration unnecessary.

- **Attribution:** [flash_stats.c:33](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:33) and its other mask carriers preserve bit `0x100`; both assertions are correct. Page 1 remains unchanged; page 3 contains three little-endian u16s followed by zeros. [ak820health.py:332](C:/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:332) correctly decodes P2a’s reserved third field as zero and pre-P2a’s unhandled page as `None`.

- **Menu:** [menu.c:49](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:49) has the requested twelve-row order. Appended IDs, choices, commit, icon/title, and four-bit value signature agree. Paging and scrollbar derive their counts; pops retain cursor/page; Diagnostics return finds its row dynamically. The updated host and board tests use the correct indices. The remaining “eleven rows” comment is harmless.

- **Readout:** [display.c:1954](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1954) preserves the previous percent rules and state fallbacks. Staged restoration forces repaint; second-tick recomposition plus string comparison catches hour boundaries. Formatting remains bounded to seven cells.

- **RAM:** ELF comparison confirms exactly **4 bytes of added objects**, producing the stated **128-byte gap** after alignment. No unnecessary new static state. Optional later saving: [display.c:1929](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1929)’s `last_fw`, `last_txt_x`, and `last_txt_w` fit `uint8_t`; measure the linked gain before relying on it.

Static review and existing ELF inspection completed; process execution was blocked, so I did not rerun your passing tests.
---

## Dispositions

- No must-fix: flashed as `d56980c9`.
- The stale "eleven rows" comment (menu.c above `top_rows`): to be corrected with the next firmware change.
- The optional saving (`draw_battery()`'s `last_fw`, `last_txt_x`, `last_txt_w` as `uint8_t`): noted for when dev RAM is next needed (a faster average for the hours readout, if JD wants one); measured then.
- The tests codex could not run: `menu_s0_test` (both ways), `batt_text_test`, and the diag sim with its golden against `781d071f` all pass.
