Reviewed **7edd3997f9** and the main-tree diffs. No builds or file changes. **No P1; two P2s and one P3 remain.**

1. **P2 — `rxtap()` still suppresses malformed/wrong-op replies.** [overrun_diag.py:115](/Users/jdlien/code/ak820-pro/scripts/overrun_diag.py:115), [overrun_diag.py:60](/Users/jdlien/code/ak820-pro/scripts/overrun_diag.py:60).

   `op()` reports both short replies and wrong-op replies as `"unhandled or another op's reply"`, so the substring check accepts both as an unavailable tap. Isolated execution of the actual functions confirmed that a four-byte reply and a full op-20 reply both return `available: False`. Timeout now propagates correctly. Distinguish explicit unsupported-command responses from protocol errors.

2. **P2 — the recorded camera run does not close the transition-validation gate.** [d9_gates.py:60](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/d9_gates.py:60), [d9_gates.py:36](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/d9_gates.py:36), [ROW-ISR-PLAN.md:1099](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1099).

   The run supports the settled-state results: it waits after each change, starts recording, then samples frame ≥300. It therefore cannot establish absence of tearing during hue, brightness or byte/wide transitions. It also does not exercise deterministic chunk interruptions or four-field accounting with forced omissions. Conversion/handler timing remains outstanding; the [plan explicitly owes the warm window](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:2524).

3. **P3 — some superseded descriptions remain.** [ROW-ISR-PLAN.md:1011](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1011) still describes CIE after RGB multiplication, although QMK curves value first. [rowisr.c:1160](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1160) still describes handler table/byte loads, and [rowisr.c:1845](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1845) still claims the flush locks.

The requested firmware checks pass by source trace:

- **Core guard:** fixes both round trips. Boot’s existing sentinel and explicit re-init remain effective; `rgb_last_enable` remains independent. An effect returning `false` finishes rendering and reaches flush, which updates both trackers—no repeated-init loop.
- **Indicator ordering:** ordinary nonzero effects run the hook after their final chunk. Suspend and `NONE` can flush without it, but their buffer is zero, safe under either encoding. A retained block cannot misinterpret those zeros.
- **Release:** clears every render-buffer LED and cancels pending rendering/flushing through re-init. Excluded LEDs remain zero; `NONE` gets its initialized clear/flush. The committed wake-dark frame remains untouched until a subsequent flush.
- **Repeated block call:** one boolean assignment, plus call overhead if not inlined. It neither dirties the frame nor forces conversion; negligible, though not literally zero.

NOT READY