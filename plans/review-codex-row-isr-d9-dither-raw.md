Reviewed `7dad75d506..6e7924ac26` and both script diffs. No new P1/P2 defects found. No builds or file changes. Exhaustive arithmetic, four-phase decoding, generator/header equality, and existing ELF inspection passed.

**P1 — must fix**

| File:line | Finding | Failing scenario |
|---|---|---|
| — | None found. | — |

**P2 — should fix**

| File:line | Finding | Failing scenario |
|---|---|---|---|
| — | None introduced by this commit. | — |

**P3 — notes**

| File:line | Finding | Scenario checked / limitation |
|---|---|---|
| [rowisr.c:1189](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1189) | **Encoding and terminal rule hold.** Flags/patterns never reach the match registers as width. | Flagged bases are 0–15, resolving to at most 16 ticks, strictly below either terminal. Ordinary widths—including 2,550 at K=640—bypass masking. Shifts select bits 11–14; bit 15 cannot contribute. Unused bit 14 simply makes phase 3’s increment zero; using it later would remain safe with the same base bound. |
| [rowisr.c:1720](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1720) | **Quarter rounding and carry are correct.** | All 4,096 Q8 inputs below 16 ticks round to the nearest quarter. Fractions 224–255 carry into the base; 15.875 ticks becomes ordinary width 16. From 16 ticks, the existing whole-tick rounding applies. |
| [rowisr.c:1192](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1192), [rowisr.c:1386](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1386), [rowisr.c:1778](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1778) | **D8 counts this field’s driven ticks. Committed-dark detection remains correct.** | Base 3, pattern `0x7` yields `4,4,4,3`: 15 ticks over four admitted fields. Omitted pulses add nothing; intentional zero fields count no omission. Base-zero patterned entries remain committed-lit. Encoded sums are used only for nonzero detection and cannot overflow here. The accepted continuous `lit_ms`/fixed-power-term bias on dither-only frames remains. |
| [rowisr.c:1180](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1180), [rowisr.c:1140](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1140) | **The shift count is hoisted in all three saved ELFs.** RAMTEXT shares the same decoder. | Dev, devprobe and daily compute `11 + (phase & 3)` once, then reuse it across 15 columns. A flagged decode takes **seven Thumb instructions**, including two shifts for the base mask. Dev’s stack allocation and 344-byte heap gap are unchanged. RAMTEXT correctness is source-checked; these artifacts have it disabled. Actual dither-heavy timing and the inherited transition-camera gate remain outstanding. |
| [rowisr.c:1715](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1715), [rowisr.c:1331](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1331) | **Pattern means are correct; synchronization preserves temporal colour modulation.** | Extra ticks occur on phases `{0}`, `{0,2}`, `{0,1,2}` for quarter, half and three-quarter fractions. Channels share phase. Thus red ¼ / blue ¾ produces a mixed field, two blue-only fields, then darkness. Quarter/three-quarter patterns repeat at 111 Hz on this build; invisibility is an eye/camera result, not established by frequency alone. At the supported 267 µs cadence, those repeat at approximately 52 Hz. |
| [curve12.h:6](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/curve12.h:6), [rowisr.c:1713](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1713) | **The log table matches its generator and is nondecreasing. The hue claim needs qualification.** | Repeated `7,7,7,8…` entries are legitimate quantization plateaus. Value 128 targets 2.071% of full light. Quarter rounding bounds absolute width error, not channel-ratio error; preceding fixed-point rounding raises the measured bound slightly above ⅛ tick, to about **0.128 tick**. At K=300, checker purple `(77,36,255)` at v=13 averages `(¼,0,¾)`: its green still disappears. |
| [check_curve12.py:46](/Users/jdlien/code/ak820-pro/scripts/check_curve12.py:46), [rowisr.c:1766](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1766) | **Devprobe’s full-chroma darkness ends at v=4, not approximately 60.** | K=64 gives zero at v=1–3, then ¼ tick at v=4. All three checker-purple channels first light at v=69. Raw probe patterns retain their direct byte-to-tick mapping, so the floor probe is unaffected. |

READY