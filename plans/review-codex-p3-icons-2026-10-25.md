# Codex on P3's status icons, 10-25

Prompt: `plans/review-prompt-p3-icons.txt`. Firmware `2d8512ae`, tests `3cf6224`.

## Dispositions

- **No must-fix.** Cleared for the flash.

## The review, verbatim

**No must-fix changes found** in `d6483b2b..2d8512ae` for the specified dev flash on the keyboard on gremlin.

- **Scheduler contract:** Content-dependent chunk counts are valid. The signature includes the state, current-slot marker and highlight ([menu.c:623](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:623)). [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265) checks that signature **before** continuing or committing. A changed signature abandons progress; selection resets both chunk and piece to zero, using the new count. Unchanged signatures resume across generations. The existing `maybe_lit` cleanup and admission rules still enforce one highlighted row.

- **Geometry and bounds:** [menu.c:698](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:698) correctly maps split chunks to `[4,16)`, `[16,64)`, `[64,125)`. Together with `[0,4)` they cover the identical footprint exactly once, background included. I independently enumerated all pieces: no gaps or overlaps. The icon sends **336 B**, using **28 B** of bitmap storage; limits are 512 B and 64 B. The largest remaining piece is 488 B. The new assertion at line 692 covers both icon bounds.

- **Font:** [font_small_mono.h:170](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/res/font_small_mono.h:170) appends four cells for two icons, codes `0x9e–0xa1`; all preceding glyphs are unchanged. Both icons match the BDF placement. `129 − 95 = 34` agrees with [menu_text.c:10](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_text.c:10), and unsigned lookup handles them correctly. No conflicting code assignments or additional firmware consumers found.

- **Memory:** The exact dev ELF and binary match their manifest hashes. New tables and glyphs reside in `.rodata`; `.data` and `.bss` are unchanged. Heap gap remains **136 B**, passing [build.sh:209](C:/Users/jdlien/code/ak820-pro/build.sh:209)’s 128 B floor by 8 B.

Reviewed `3cf6224`’s pixel/colour oracles and state checks. They settle between states; the mid-operation conclusion comes from scheduler inspection. C tests were **not rerun** because process creation is blocked.