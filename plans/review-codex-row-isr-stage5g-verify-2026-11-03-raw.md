**P1 blocks flashing: a recovery baseline can still lose an alias after frames resume and then stop.** The failing branch is [rowisr.c:720](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:720); the trust-return check at [line 1243](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1243) does not handle this transition.

Concrete trace:

1. J establishes a VALID recovery baseline: `bus=1, fresh=0, pending=1`. Therefore `usb_base_trusted=true`.
2. A 350 ms alias precedes J+1. Its entry sees moving frames: `fresh=1, pending=0`, same generation. J+1 commits. The former per-service judgment rejects this interval; this code retains the pending baseline.
3. Before the judging service, frames stop without a bus event. A 5 ms row-only hold lets freshness expire while the tick keeps the extension VALID. Subsequent entries have `bus=1, fresh=0, pending=0`, unchanged `ugen` and generation.
4. J+8 reaches `!b->fresh`, then finds `a->fresh==0` and returns `USB_UNJUDGED`. It drops the sums and replaces the baseline: **no loss and no frame reject for the alias**. The same failure occurs in a deferred judgment ending at a subsequent stale `usb_last`.

This is outside neither the 13-second bound nor the declared “frames stopped before the alias” blind spot: frames were moving through the alias.

**Fix:** close and judge a recovery baseline at the first fresh counted entry, then rebase using the existing verdict/adoption rules. Do not merely discard that interval. Alternatively, preserving cadence requires retaining the intervening fresh evidence so a later stale endpoint cannot mean “no frame seen.”

**P2 — The host can combine two different silence reports.** [rowisr_diag.py:365](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:365) reads sub 8 and sub 9 separately; [report_fill:274](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:274) provides no shared report identity.

An armed silence can finish between those requests. Sub 8 can describe an older pending report with unchanged generation, while sub 9 supplies a newer report’s `judged >= 2`. The host then prints “no loss across it” for the older pending copy. **Fix:** include the same completion sequence in both pages and retry mismatches.

The requested checks otherwise resolve as follows:

1. **Both P1-1 traces pass.** For non-judging J+3, `usb_last` receives its entry before the cross; J+4 counts the guard’s generation move, rejects J→J+3, and drops pending sums: **two losses, one frame reject**. When J+3 itself judges and rejects, it counts the alias and adopts its generation. The later guard causes one additional loss at J+4. Equal baseline/endpoint extensions suppress a second judgment: **two losses, one frame reject**, counted once.

2. **The bus-down trust-return trace passes.** J+1 folds the untrusted stretch, establishes both snapshots and resets phase; J+9 rejects the subsequent alias. A fresh baseline ending with stopped frames rejects as an event; bus-down or changed `ugen` also rejects, including deferred judgments using `usb_last`’s fields. A pending baseline followed by fresh frames stays trusted and compares spans **if the judged endpoint remains fresh**. The P1 above is the missing converse.

3. **The endpoint invariants hold where it is actually judged, with one literal exception.** At [line 1303](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1303), only `usb_base.gen` adopts `adopt_gen`; `usb_last.gen` remains old. Their extensions are equal, so this is safely excluded, and the next continuous entry overwrites `usb_last`. Assigning `usb_last = usb_base` after adoption would make the stated invariant true. I found no stale-baseline consumption through sleep, scan-only, record reset or initialization. The earlier cadence paragraph still incorrectly names committed `last_snap` at lines 520–521.

4. **The discontinuity and trust-return branches are mutually exclusive, discontinuity first.** Folding the genuinely untrusted stretch is appropriate even for phantom boundaries: those pairs had untrusted starts under the former judgment too. The first trusted counted entry immediately ends that stretch. The remaining P1 concerns a *trusted recovery* baseline, not that fold.

5. **For matching report pages, the timing fix is sound.** The initial sequence is captured under the mask before the marker. The final sequence precedes the locked state copy and is a lower bound; thread context cannot observe an unfinished row ISR’s judgment. Two opportunities cover a possible first deferred pre-silence judgment. Counts below two correctly produce `PENDING`, with count and wait.

6. **The ordinary non-judging path has the stated work**, plus the surrounding baseline branches and `direct=false` initialization. With a trusted baseline, short-circuiting avoids evaluating `snap_trusted(&s1)`. The snapshot copy is 20 bytes—five words’ worth—and `service_commit` updates pending sums/maxima. No additional hardware observation or USB judgment runs there; `usb_judge()` still has exactly two call sites outside the entry mask. Source inspection establishes no measured cycle cost.

Reviewed `0b5e547705` over `1dfa597991`, the complete firmware files and the main-tree host changes. No builds, tests, firmware execution or bench commands were run.