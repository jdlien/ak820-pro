**P1s block flashing.** The original two traces are repaired when the intervening services commit, but the broader guarantee still fails.

1. **A crossed non-judging service loses its entry evidence.** [rowisr.c:1202](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1202), commit suppression at [rowisr.c:1345](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1345).

   Concrete trace: J establishes a healthy baseline; J+1 and J+2 commit; a 350 ms alias precedes non-judging J+3’s snapshot. After its entry checks, a separate 20 ms silence occurs before step 6. The guard moves the generation, and the crossed handler commits nothing. At the next entry, the deferred judgment ends at J+2, which predates the alias. It accepts that healthy interval and discards the baseline: **one loss, zero frame rejects instead of two losses and one reject**. The parent judged and rejected the alias at J+3, before the second silence.

   **Fix:** retain the latest eligible USB entry snapshot independently of the scheduler’s committed `last_snap`, including entries that subsequently cross or return through the cadence switch. Use that evidence before discarding a USB interval.

2. **An untrusted baseline hides aliases after USB becomes trusted again.** [rowisr.c:693](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:693), cadence gate at [rowisr.c:1229](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1229).

   J establishes `usb_base` while the bus is down. At J+1, USB is active with moving frames and commits a trusted snapshot; this does not change `time_gen`. A 350 ms alias occurs before J+3. J+8 still judges from J’s bus-down baseline, returns `USB_UNTRUSTED`, folds the pending statistics—including the alias’s phantom boundaries—and replaces the baseline. **The alias produces no loss or frame reject.** The parent would reject J+3 against its preceding trusted service.

   **Fix:** establish a usable baseline immediately when frame trust returns, and preserve/close trusted stretches when trust changes. Checking only extension validity and generation does not preserve the per-service detector’s coverage.

**P2 — The silence report can still precede its verdict.** [rowisr_diag.c:258](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:258), misleading verdict at [rowisr_diag.py:368](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:368).

A silence is explicitly allowed inside a row-only hold. If that hold has more than 20 ms remaining after a 350 ms alias, no judging opportunity occurs before the timeout. The report copies the unchanged generation and the host prints “no loss across it”; the rejection arrives after the hold ends.

Also, `jseq0` is read before acquiring the injection’s lock: the code provides no bound of one intervening judgment. The reported final sequence is read after the state copy, so those two observations can disagree.

**Fix:** capture the initial sequence under the injection’s lock, capture the final sequence coherently with the state, and report **pending/timed out**, rather than “no loss,” when the required opportunities have not occurred.

The requested checks, in order:

1. **The specified guard/alias traces pass with committed endpoints.**
   - Guard gap → re-primed non-judging service → alias: immediate reseeding works; the later judgment gives **two losses and one frame reject**.
   - Alias at J+3 → committed J+4 → guard at J+5: deferred judgment rejects J→J+4, drops its pending sums, and gives **two losses and one frame reject**.
   - A pre-sleep alias represented in the retained endpoint is judged at wake, separately from the sleep’s generation loss.
   - An alias represented in a judging entry’s same-generation, VALID `s1` is judged normally.
   - An isolated 358 ms silence rejected by the guard leaves a healthy preceding pending interval: **one loss**, no duplicate frame rejection.
   - A suspend represented in the pending endpoint produces a deferred **bus-event rejection**, separately from the subsequent guard loss.

   There is another accounting difference: **two 350 ms aliases between judging services produce one rejected interval and one loss**, whereas the parent produced two. Endpoint aggregation preserves rejection of that combined interval, not per-silence multiplicity. Preserving those separate counts requires retaining and evaluating the intervening service intervals.

2. **`last_snap` is a safe committed endpoint, but not always the required evidence endpoint.** Its equal/older exclusions work as described. Within the supported bounds, I found no explicit time discard that leaves it deceptively continuous in the same generation: discarded time moves `time_gen`; adoption itself discards nothing. The first P1 is that newer, already-observed evidence need not reach `last_snap`.

3. **Two losses at one entry do not break a control-flow invariant.** `epoch_losses` is diagnostic; nothing branches on its value. Multiple generation bumps remain coalesced by the entry’s single comparison, while the deferred rejection accounts for a separate earlier interval. `seen_gen` needs no update on that deferred path. The “at most one loss per entry” comments at lines 369 and 403 are now inaccurate.

4. **The fresh check and adoption remain sound.** [rowisr.c:1243](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1243) still checks whether another observer invalidated **since `s1`**, regardless of the judged interval’s length. Successful adoption reaches `usb_base` immediately and `last_snap` if `service_commit` executes. A crossed service correctly leaves `last_snap` uncommitted.

5. **The pending-sum machinery is internally consistent, subject to the coverage failures above.** Rejection/unjudged paths clear pending sums; accepted/untrusted paths fold them; the current service goes direct only on those latter verdicts. Reseeding and record reset clear pending sums. The reader exposes only `rec` under its lock. However, the untrusted-baseline P1 demonstrably folds phantom statistics. Also, dropping pending services does not retroactively increment `invalid_services`.

6. **The isolated bench expectations remain unchanged under normal resumption.** [silence_check.sh:59](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/silence_check.sh:59) still expects:
   - 350/700/1,049 ms: one loss and one frame reject.
   - Guard cases: one loss and zero frame rejects.
   - Short cases: zero; 7.9/8.1 ms retain their phase-dependent allowance.
   - Battery cases: own losses 1/0 for 20/350 ms, after subtracting bus-event losses.

   Healthy `usb_checked` growth becomes approximately one eighth, plus deferred judgments. Invalid-service counts are **not** divided by eight: generation invalidity remains per service, while recovery judgments become sparse. The 600 ms delayed read does not depend on the report’s copy timing.

7. **The entry masked section is unchanged in source.** `usb_judge()` has exactly two call sites, both outside that section. A stable non-judging service also executes the baseline/phase branches and the new `direct` branch with pending-statistic updates in `service_commit`; therefore “nothing else” beyond three comparisons and an increment is too strong. Source inspection establishes no measured saving.

8. **Keeping the baseline across sleep and scan-only is otherwise appropriate.** USB judgment does not use scheduler phase, and slot reconstruction is reset across the cadence change. Wake compares retained pre-sleep snapshots, then seeds from the new generation. The remaining problems are the lost non-committed entry evidence and delayed trust reacquisition identified above.

Reviewed HEAD `1dfa597991`, its parent diff, the complete `rowisr.c`, and the referenced records and consumers. No builds, tests, or bench commands were run.