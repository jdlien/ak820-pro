Reviewed `703df88a9d` and the uncommitted host/build diffs. Read-only; no builds. **No P1/P2 findings; the original P2 is resolved.**

Remaining P3 comment rot:

- [rowisr_diag.py:59](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:59) and [rowisr_diag.c:174](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:174) still promise “2 ms after,” despite the bounded 2–20 ms wait.
- “Each judges” remains in [rowisr_diag.py:195](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:195), [rowisr_diag.c:193](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:193), [rowisr.c:679](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:679), and [rowisr.h:60](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.h:60). Generation-invalid services also count. [rowisr_diag.py:198](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:198) still says the verdict is “not yet in”; it **may** already be in.
- [rowisr.c:1603](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1603) still derives `b × ms` by cancelling the emission scale. Under the probe, the result is reference-equivalent drive: `b × K_active / K_ref × ms`.

Arithmetic checks out: conversion stays 64-bit; remainder is `<300000` or `<640000`. At 125 µs, probe width 255 represents 54.4 reference units. No remaining accounting uses the active scale; the LUT and terminal assertion correctly do.

Rejection sets `valid1=false`, suppressing validity-dependent commit statistics. A fresh rejection clears `time_valid` until re-prime; an intervening observer may already have re-primed in the race case. Step 6 only checks hardware crossing. The revised sub-8/sub-9 descriptions, final sequence-read comment, and host service labels are sound.

READY