Reviewed `bbf5d6069e` over `bde904e491` and the host diff. No builds or board I/O; host checks used mocked HID.

**P1 — must fix before flashing**

| File:line | Finding and failing scenario |
|---|---|
| — | None found. |

**P2 — should fix**

| File:line | Finding and failing scenario |
|---|---|
| — | None found. |

**P3 — notes**

| File:line | Finding and scenario |
|---|---|
| [rgb_matrix.c:179](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:179), [rowisr.c:1680](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1680), [ak820pro.c:753](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/ak820pro.c:753) | **Q1: raw-byte claim holds.** This branch’s driver is `rgb/rowisr.c`. Both setters bypass HSV/CIE; luminosity multipliers are unity. Indicators run after rendering, subsequent indicator hooks are no-ops, and flush copies the bytes unchanged. The flush-allowed hook gates EEPROM writes only. |
| [power.c:119](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:119), [power.c:213](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:213) | **Measurement conditions:** USB power gives scale 255 with data on or off, provided no forced dark stage or latched cutoff remains. On battery, Saver’s 128 ceiling, DIM’s 64 ceiling and DRIFT’s value cap precede—and are bypassed by—the pattern. Ladder-off/Lights out and low-voltage cutoff still set scale zero; sleep still stops output. Hold ACTIVE for battery measurements with the cutoff clear. RGB must remain enabled with a non-NONE effect. |
| [rowisr_diag.c:411](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:411), [rowisr.c:1698](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1698) | **Q2: bounded cost; sentinel safe.** Once per completed render, thread context makes 81 setter calls versus the previous 81 clears plus one setter. No new lock, allocation or ISR loop. Absolute ≤0.5 ms was not measured. Selector 254 takes its own branch and never becomes an LED index; Q6’s individual-LED path remains intact. |
| [rowisr.c:151](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:151), [rowisr.c:1632](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1632) | **Q3: timing and accounting remain sound.** At K=64, every byte maps exactly to its programmed ticks: 255 is 5.3125 µs, strictly below terminal 1535. Admission retains the whole-window deadline, 4344 ticks/90.5 µs. Maximum row sum is 3825, safely bounded. D8 retains 64-bit arithmetic, remainders and reference K=300: byte 255 represents 54.4 reference units per LED. |
| [rowisr.c:1163](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1163), [rowisr.c:1326](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1326) | **Low-byte measurement caveats:** all LEDs means up to 15 simultaneous columns across six selected colour rows per field. N>0 introduces mux-drive current independent of pulse width; fit the current slope with an intercept. Nominal key-row sampling remains 2.25 ms. Late slots omit a whole row-colour pulse and contribute zero D8 width; they never stretch it. A shared-column witness now sees multiple rows’ pulses—correlate with mux selection. Optical floor remains empirical. |
| [rowisr_diag.c:446](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:446), [rowisr_diag.py:232](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:232), [rowisr_diag.py:393](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:393) | **Q4: protocol/output checks pass.** `all` plus three digit components sends `[254,R,G,B]`; reply `[4]` echoes 254. Text prints “every LED at …”; JSON uses `"led":"all"`; individual indices remain numbers and off remains null. Existing range-validation roughness persists: component 256 opens HID then raises `ValueError` without sending; indices 81–253 are refused by firmware. `off` releases the override; use `all 0 0 0` for a dark baseline. |
| [test-bench.md:376](/Users/jdlien/code/ak820-pro/docs/test-bench.md:376) | **Logger setup:** the documented INA228 is pack-side. With genuine USB power supplying the board, its reading is not a direct LED-load measurement. Measure the current slope on battery with the ladder held; USB data may remain connected. |

READY for a flash of the devprobe flavour.