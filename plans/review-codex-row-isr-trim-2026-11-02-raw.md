Reviewed `234d2acf8b` and `a47c134079` against `5c0e6249d0`, including the supplied ELF. **No P1 found.** Verification was read-only; no hardware was accessed.

**(a) Correct for the stated detection contract; not exactly equivalent at the tolerance boundary.**

The model includes SOF floor/ceiling quantization, CT16B5 quantization, the old millisecond rounding and ±0.09% relative clock error. **4,875,002 healthy-interval endpoint cases through 13 seconds passed both judgments**, including 267 µs, 625 µs and millisecond hold-offs.

| Silence length, ms | Outcome preserved |
|---|---|
| 5, 7.5 | Exact; no loss |
| 7.9, 8.1 | Observation gap decides; recorded results remain exact / guard |
| 8.5, 20, 100, 200 | Guard rejection |
| 350, 700, 1,049 | USB frame-counter rejection |
| 1,000, 2,048, 7,000 | Guard rejection |

**2,326,362 alias cases produced no acceptance.** Independently, within 13 seconds the closest lost-wrap coincidence is 49.152 ms. Conservatively subtracting clock error and quantization leaves **36.436 ms**, above the maximum new tolerance of **28.389 ms**. The existing off-USB and stopped-SOF exclusions remain unchanged.

Literal parity does fail at [rowisr.c:880](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:880), also at the exit judgment:

| Input `(dext ticks, df frames)` | Old | New |
|---|---|---|
| `(600, 0)` | Accept: 3 ms ≤ 3 | Reject: 600 ticks > 564 |
| `(56157, 296)` | Reject: 4 ms > 3 | Accept: 657 ticks ≤ 672 |

These counterexamples disprove exact equivalence; neither represents a healthy interval under the stated envelope or defeats the scoped silence guarantee.

**(b) Correct, with reduced diagnostic precision and range.**

At [rowisr.c:271](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:271):

- `EPOCH_CONSUMER_MAX = 675,000,000` ticks; doubling gives **1,350,000,000**, safely within `uint32_t`.
- The fold returns **0–192,000 ticks**. Maximum tolerance is **1,318,922 ticks**, also safe.
- HEAD correctly saturates `usb_worst` at **65,535 ticks**, preventing wrap.

The [record conversions:640](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:640) round stored ticks correctly. The largest conversion numerator is **1,350,000,187**; the last rejected span saturates at **65,535 ms**.

Two reporting qualifications: the worst-distance ceiling is now **350 ms**, and discarding the half tick can change its rounded report by 1 ms. For example, `(dext=281, df=3)` reports worst distance **1 ms**, versus the old **2 ms**. Wire units remain correct.

**(c) Correct.**

The [fast path:526](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:526) exactly equals the original rounded division:

| `slot_ticks` | Adjusted `dt` giving 0 | Giving 1 | `2 × slot_ticks` |
|---:|---:|---:|---:|
| 12,816 | 0–6,407 | 6,408–19,223 | 25,632 |
| 30,000 | 0–14,999 | 15,000–44,999 | 60,000 |

At the threshold, the fallback returns 2. Exhaustive small-range comparisons passed. Even allowing the full 16-bit phase difference, the 32-bit branch’s numerator stays below **1,879,128,472**; the existing long-span path remains 64-bit.

**(d) Correct.**

The [initializers and assertion:226](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:226) and [rotation:956](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:956) preserve:

`cur_colour == cur_row % 3` and `key_row == cur_row / 3`.

The configuration is six key rows × three colours. All three start at zero; their only subsequent writes are the adjacent rotation updates. The `17 → 0` wrap is correct. Scan-only and early-return paths preserve them together. A 100,000-rotation check passed.

**(e) Correct for the change and the handler’s five masked sections.**

Only `rowisr.c` changed. The remaining slot behavior, guards, generation handling, admission and commit logic are unchanged.

ELF control-flow inspection found **no external call while masked in any of `Vector90`’s five sections**. No arithmetic-library call occurs directly in `Vector90`; division remains in the two fallback helpers and the unlocked record conversion.

The broader statement “all masked sections contain no call” needs qualification: the unchanged [scan helpers:666](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:666) call `_pal_lld_setpadmode` while masked, at ELF addresses `0x23eba` and `0x23f0e`. This predates these commits.

Sub-6 offsets and units match [scripts/rowisr_diag.py:169](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:169): worst distance and rejected spans are milliseconds; guard gap remains ticks. A synthetic reply passed through the actual decoder correctly.

**READY TO FLASH. No P1 blocks this performance commit.**