# Codex: the RGB effects' speeds (2026-10-25)

Prompt: `plans/review-prompt-fx-speed.txt`. Diff: qmk_firmware-ak820pro
`30f1e0cf..93e55f78` (branch `gremlin/fx-speed`). Verbatim below, then the
dispositions.

---

**No change is required before flashing gremlin’s C dev build based on this diff.** One non-blocking portability caveat:

- **C++ linkage:** [rgb_matrix.h:202](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.h:202) and [rgb_speed.h:17](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rgb_speed.h:17) lack `extern "C"` guards. Direct C++ callers/overrides need those guards or an enclosing C-linkage include. The current C build is unaffected.

- **Core defaults:** [rgb_matrix.c:314](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:314) preserves both original expressions exactly, including saturation, timer truncation, and result conversion. Results remain byte-identical; machine code and execution time need not. Header prototypes make definitions after the runner includes valid C. [jellybean_raindrops_anim.h:17](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/animations/jellybean_raindrops_anim.h:17) retains left-to-right `&&` short-circuiting: one hook call at iteration zero.

- **Math:** [rgb_speed.c:24](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rgb_speed.c:24) checks out. `257/65536` approximates `1/255`; rounding and interpolation keep the curves within **0.17%** of ideal. Table entries are correctly rounded; indices, shifts, and intermediates are safe. The largest timer product is **9,221,316,257,201,475**, comfortably within `uint64_t`. All 256 speeds are strictly monotonic.

- **Transitions:** [rgb_effects.c:86](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rgb_effects.c:86) safely coalesces missed drops. Re-entry, speed changes, or jumping timers can trigger immediately—or suppress that trigger when the count aliases modulo 256—but cannot cause catch-up bursts or permanent stalls. Frozen sleep pauses progression. **Timer wrap is continuous in the low byte**, because adding `2^32` milliseconds adds exactly `256 × rate` units. Frames exceeding roughly 33.34 ms can lose drops at maximum speed. Speed-change hue jumps remain expected.

- **Integration:** [rgb_effects.c:64](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rgb_effects.c:64) preserves upstream timing for other modes. Repeated per-iteration calculation adds bounded main-loop work; no ISR or interrupt-masking changes. Battery accounting still integrates committed colour drive. VIA, menu percentages, and lighting restore retain the same raw speed byte; restored animation rates intentionally change.

I verified the exact committed blobs and independently checked arithmetic in memory. Process execution was blocked, so C-test/build/link results remain your supplied evidence.

---

## Dispositions

- **C++ linkage (non-blocking): no change.** No QMK header in this tree
  guards its declarations with `extern "C"`, `rgb_matrix.h` included, and
  nothing on this board is C++. If the hooks go upstream, they'd follow
  upstream's convention.
- **Everything else: no change.**
  - The defaults are byte-identical in result.
  - The math stays within 0.17% of the ideal curves, with no overflow.
  - Jellybean's one-byte count coalesces missed drops without bursts, and
    stays continuous across the timer's wrap.
  - Above ~33 ms frames, drops at the top speed can be lost. Frames are
    ~16 ms, so this is noted only.
- Flashed `93e55f78` (token `0x7a73d9a7`) on the keyboard on gremlin at
  ~19:25, for JD to try.
