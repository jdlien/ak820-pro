No flash-safety blocker found in `1f3c79e9..18faf312`; one minor defect:

- **P3 — stale Both preview:** [menu.c:1091](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1091), hashed at line 1186: with 80%, `left_min=3420`, and average maturity 59→60 minutes, `80% --` and `80% 57h` both produce `0x1768` for unchecked, unselected Both. Hours and the note update; Both remains stale. Invalidate on readiness changes and add this regression.
- [display.c:2120](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2120): positions, vacated clears, interrupted paints and three-glyph budgeting check out.
- [batt_text.c:11](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/batt_text.c:11): 100%, `<1h`, 999h and unavailable-estimate boundaries are correct.
- Menu rows/cursor/commit are consistent. [kb_eeconfig.c:202](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:202) and [profiles.c:98](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:98) preserve older encodings.

Artifact hashes match; ELF confirms 136 B ≥128 B. Native tests weren’t rerun: execution denied.