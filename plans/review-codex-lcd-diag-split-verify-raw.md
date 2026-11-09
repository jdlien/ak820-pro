**P1: None found. P2: One remains in the interpretation protocol.** The firmware changes pass verification; the calibration supports timing experiments, but does not yet justify identifying a particular guard as the cause.

| Priority | File:line | Finding and failing scenario |
|---|---|---|
| **P2** | [review-prompt-lcd-diag-split-verify.txt:6](/Users/jdlien/code/ak820-pro/plans/review-prompt-lcd-diag-split-verify.txt:6), [lcd_bus.c:400](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:400) | **The sweeps do not control timing changes inside transmission.** Mode 2 samples STAT before incrementing `rx`; old and delay-after increment first. If that earlier sample changes whether another RX entry is drained in the same iteration, mode 2 can behave differently even when its exit predicates never encounter non-idle status. “Mode 2 clean, delay-after still failing beyond its nominal overhead” therefore does **not** establish TX_EMPTY/three-read semantics. The incidental-cycle table records this confound; endpoint delay thresholds do not eliminate it. |
| **P3** | [lcd_diag.py:76](/Users/jdlien/code/ak820-pro/scripts/lcd_diag.py:76), [lcd_diag.py:86](/Users/jdlien/code/ak820-pro/scripts/lcd_diag.py:86) | **Version zero does not necessarily mean pre-split.** `c88bd9a7b1` supports the split and returns `exit_extra`, N and divider, but leaves version zero. Reading it prints “pre-split,” “0 after,” and “n, div … none,” even with nonzero split fields. Label version-zero fields as unversioned/ambiguous, or explicitly exclude that transitional build. The original `old_queued` mislabelling is fixed. |
| **P3** | [lcd_bus.c:1890](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1890) | **Pending is not an acknowledgement that the requested divider is currently held.** Request 7, let a painter apply it, then start a DMA: Prepare resets DIV to zero while pending stays false. A read then reports asked 7, held 0, pending false. The two divider values expose this correctly; document the flag as an outstanding request-change flag, or account for the mismatch when reporting pending. |

The built fixes check out:

- **Instruction preservation:** all seven send functions are byte-for-byte identical to `c88bd9a7b1`, including their literal pools. `lcd_window_polled` differs only at `0x14b8`: its jump-table address changes from `0x306d4` to `0x3070c`; the table contents are identical. The first review’s incidental differences therefore still apply.
- **N = 10:** the ELF’s initializer at `0x20000c02` is `0x0a`. The loop remains `subs; ldr STAT; cmp; bne`, costing nominally `7N − 2` for positive N.
- **Reply layout:** payload offsets 23/24/25 contain version 2, held DIV and pending. These are report offsets 27/28/29 because the payload starts at `data[4]`. Validation still precedes mutation; `zero` preserves mode, N and divider.
- **DMA-safe readback:** at `0x3080`, the handler executes one word load from `SPI0 + 0x08`, then stores its low byte into the reply. It does not read DATA, clear flags, write SPI configuration, or interfere with DMA ownership. The register definition gives DIV as bits 7:0.
- **Host verification:** parser boundary checks and synthetic current/legacy replies passed without loading the hardware transport. The transitional-build and post-DMA outputs reproduce the P3 cases above.

Using the first review’s **nominal, no-wait-state, no-preemption** accounting:

| Comparison with old | N=10 delay variant | Logic variant |
|---|---:|---:|
| Function entry → first DATA store | Before: **+74 cycles** | Full A: **+54** |
| Completed receive loop → return | After: **+80 cycles** | Exit-only: **+61** |

Thus N=10 covers the intended exit-only comparison and A’s prefix. One terminology correction: **+61 is mode 2’s completion overhead**, not all of mode 0’s. The previous full-A totals were 132 versus 49 cycles, or **+83**. Sweeps comparing against full A should extend beyond N=10.

For P2 1, I accept instruction non-isolation as an explicit limitation; assembly is not necessary merely to conduct a useful experiment. The protocol needs these interpretation limits:

- Record empirical **N brackets and failure rates**, with the cycle figures labelled estimates. Flash/peripheral waits and interrupt timing prevent treating `7N − 2` as measured elapsed SN32 cycles.
- Treat N=0 curing the fault, nonmonotonic results, or overlapping timing margins as **inconclusive**. Old failing and delay-after N=0 succeeding cannot exclude mode 4’s four-cycle incidental exit change.
- A logic variant curing the fault beyond both delay controls supports **that compiled variant**, not automatically its guard semantics. In particular, clean mode 4 with zero strays/give-ups provides no evidence that draining or rejecting anything caused the improvement. Stronger attribution needs a suitably matched control or bus capture.

The other P3 dispositions are acceptable. Re-establishing old-mode failure on this ELF before and after the trials addresses the changed CASET/RAMWR gaps; the critical XS→RASET sequence remains unchanged. Measuring SCK directly addresses unverified CLKDIV latching. At a slower divider, also re-establish old-mode failure before using the capture to explain the 24 MHz fault.

All three ELF hashes match their manifests; the current embedded token is `0x6d970a9b`. No build, flash, hardware access or file modification occurred.

**NOT READY for the stated mechanism-attribution rule.** Narrow the protocol’s conclusions as above; the built diagnostic is suitable for collecting the sweep evidence.