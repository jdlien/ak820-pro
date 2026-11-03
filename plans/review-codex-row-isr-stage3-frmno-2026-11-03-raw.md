**READY TO FLASH — for the controlled dev flash on white. No new P1 found at `67a4ccf2b3`.** The guarantee remains conditional on this unit’s measured tear duration.

1. **Read-spacing reasoning is sound under that model.** In [frmno_read()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:296), samples separated by at least twelve cycles cannot both occupy one ≤6-cycle torn state. At a byte carry, the intermediate value differs from both settled endpoints, so agreement returns a settled value.

   On disagreement, the update was already underway or completed by read 2; read 3 is beyond its torn window. A high-byte completion between reads 2 and 3 therefore yields the settled **new** value. If the entire update first starts after read 2, reads 1 and 2 agreed and the function already returns the settled **old** value. Both are acceptable. All current calls are masked, so ordinary preemption cannot stretch the sequence across another SOF. Bus resets still rely on the existing bus-event/trust checks.

   Qualification: 48 “other” steps represent roughly **24 tear encounters**. Their frequency estimates duration; it does not establish a hard maximum.

2. **Cost is bounded, but twelve nops are not a measured twelve-cycle wall-time cost.**

   | Path | Normal helper calls | Added nops |
   |---|---:|---:|
   | RGB slot: entry tracker + exit read | 2 | 24 |
   | 20 kHz tick: tracker | 1 | 12 |
   | Each `frm_staleI()` invocation | 1 additional | 12 |

   Disagreement doubles the padding **per helper call** to 24 nops. Entry, exit, or tick invalidation paths can execute both a stale read and their regular read: up to **48 added nops in that section**. The arm section gains padding only on its stale path, up to 24.

   At 48 MHz, the normal padding represents an ideal **0.25 µs/tick and 0.5 µs/RGB slot**, about **0.69 percentage points of CPU** combined. Flash fetch delays and changed code layout prevent treating those figures as measured upper bounds.

   The [plan’s 5 µs ceiling](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:794) specifically concerns step 6. Its normal path gains no FRMNO padding. Entry and exit remain bounded; no new external masked call or loop appears. **This review does not certify the absolute masked-time ceiling**—that remains a measurement gate.

3. **Keep this construction for this flash.** A nonzero-low-byte fast path could avoid most duplicate reads, but requires the stronger assumption that every possible torn value has low byte zero, including reset/resynchronization behavior. Shorter padding would reduce the empirical margin. Neither provides the same confidence from the available evidence.

4. **Scope confirmed:** the complete commit-range diff changes only this helper’s comment, the macro, and its two invocations. Both saved ELFs contain the intended spacing; masked `bl` targets remain local handler tails. Minor count correction: **1,621 versus 1,475 are disassembly rows including literal pools**; executable instruction counts are 1,501 versus 1,364.

Read-only source and saved-ELF inspection only. No builds, tests, file changes, or board access.