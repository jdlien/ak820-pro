**READY TO FLASH.** The recovery-alias P1 is fixed. One P2 remains concerning strict per-slot event accounting.

**P2 — A temporary freshness loss can disappear before judgment.** At [rowisr.c:1277](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1277), a fresh baseline does not force judgment when an intermediate entry becomes stale. A concrete trace:

- J is fresh; a 5 ms row-only hold lets freshness expire without a bus event or generation change.
- Non-judging J+1 sees `fresh=0`.
- Frames resume before J+2, with the host’s current frame number.
- J+8 sees fresh frames and agreeing spans: **zero event rejections**, whereas the per-slot code rejected at J+1.

**Fix:** force the same judgment block when a fresh, trusted baseline reaches a non-fresh entry, or retain that event evidence until judgment. This is an additional event-accounting difference beyond the declared two-alias concession.

The requested checks:

1. **Recovery trace passes.** J+1 judges the pending→fresh interval, rejects the span mismatch, adopts the bumped generation, counts **one loss and one frame reject**, and rebases fresh. [Lines 1311–1315](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1311) now give both snapshots the adopted generation. If freshness remains expired at J+9, its fresh→stale judgment rejects as an event. The original deferred recovery-baseline failure is closed: a fresh counted entry would already have forced judgment and rebasing.

2. **Branch and phase interactions pass.** Discontinuity runs first and judges against retained `usb_last`. A pending baseline ending non-fresh returns `UNJUDGED` when neither bus-down nor changed `ugen` takes precedence. Pending baselines are trusted, so trust-return does not intercept the forced judgment. Phase resets to zero; the next ordinary judgment is eight counted services later. First-fresh coinciding with the eighth executes the block once. On ordinary fresh baselines, `!usb_base.fresh` short-circuits the added condition; source inspection establishes no cycle measurement.

3. **Per-slot equivalence remains qualified.** Besides multiplicity and the P2 above, rejection attribution is aggregated: an alias followed by stopped frames can produce one event rejection instead of separate span/event rejections. Pending statistics also drop the whole rejected interval, including healthy services within it. A frame first observed between entries is handled at the next eligible entry, just as in the per-slot code.

4. **Report pairing passes under the documented single-host-process rule.** [report_fill](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:274) puts the same `sil_done` at sub 8 `[31]` and sub 9 `[18]`. Report handling and silence completion run serially in the main loop, so a page cannot read a partially replaced `sil_rep`. [The host](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:365) tries three complete pairs and warns on exhaustion. On exhaustion it still emits the mismatched data, with `pages_match=false` in JSON. I found no additional mixing path within that execution model.

Reviewed `4f19e6c31f`, the complete `rowisr.c`, diagnostic/report code, host changes, and both earlier reviews. No builds, tests, firmware execution, or bench commands were run.