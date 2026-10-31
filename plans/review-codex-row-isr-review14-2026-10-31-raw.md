**READY for stages 0–3 as written. No must-fix findings remain.**

The twelfth and thirteenth reviews’ correction is met in the operative text:

- [D3 step 1](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:500) removes the universal 100 µs allowance and 7.9 ms silence guarantee, uses observation gaps, and qualifies row-only exactness on another observer maintaining validity.
- [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:953) includes measured endpoint offsets and uncertainty, plus phase-varied near-threshold injections with the tick running and independently stopped. Its predictions follow that scoped contract. The withdrawn battery guarantee stays withdrawn.

The register behavior, write keys, control/GPIO masks, STOP clearing CEN, IOEN returning pins to GPIO, I2C direction changes, conditional timing/light arithmetic, and resource figures check out. I independently inspected the saved objects and both named ELFs. No additional running interrupt-side GPIO MODE/CFG writer surfaced.

I found no regression in the accepted matrix-publication, scan-fairness, frame-copy, brightness-calibration, priority, SPI, sleep or bootloader safeguards. The remaining hardware uncertainties—pulse lifecycle, physical colour mapping, baseline energy and settling—have prerequisite measurements before dependent stages can pass. The specified instruments can support those gates once qualified.

**Note — retained consolidation exception:** a complete short press can still disappear during blocked consumption, and the pass can exceed 25 ms. This is an existing, explicitly scoped exception; eliminating it requires separate consolidation/publication work. [Evidence](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:465)

**Stage 4 is sufficiently specified once stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table, 125 µs path.** The 62.5 µs cadence remains an experiment requiring its stated brightness decision and repeated gates.

All inspection stayed inside the repository. No files were modified and no builds ran.