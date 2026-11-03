**P1 blocks flashing: a generation change can hide a subsequent aliasing silence.** [rowisr.c:926](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:926), baseline replacement at line 986.

A concrete trace, with USB and SOFs continuously active:

1. Judged service J saves `usb_base` in generation G.
2. A 20 ms silence triggers the guard. A non-judging service counts that loss and commits a valid, re-primed `last_snap` in G+1.
3. Before J+8, another silence of 350 ms aliases the guard. Its returning service has `valid1 == true`; the parent’s per-service judgment would reject it.
4. J+8 finds `s1.gen != usb_base.gen`, skips the USB judgment, and replaces `usb_base` with the post-silence snapshot. The second silence is permanently lost: **one loss instead of two, zero frame rejects instead of one**.

`frm_pending` cannot rescue this: `cont` fails before that condition is reached. Missing baselines after sleep/cadence resets open the same kind of window. Conversely, a later guard rejection can discard an earlier, still-unjudged alias.

**Fix:** restore the parent’s per-service entry snapshot/judgment for this flash candidate. Retaining decimation requires both immediate baseline establishment after recovery and preservation of pending evidence before another generation change discards it; simply copying the new generation into an old baseline is incorrect.

The P2s:

- **Previously accepted slot statistics survive a later USB rejection.** [rowisr.c:980](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:980), [service_commit:839](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:839). A silence returning on a non-judging entry can already contribute its aliased boundary count to `slots_elapsed`/`serviced_valid`, and potentially `latency_max`. The eventual rejection invalidates only the judging service; nothing retracts those contributions. Recovery intervals likewise enter valid statistics between judgments, whereas the parent excluded them as unjudged. **Fix:** defer those interval-dependent statistics until their USB interval is accepted, or retain per-service judgment.

- **A corrupted exit sample can underflow, rather than merely read short.** [rowisr.c:1133](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1133). For six CT16B5 wraps, 2.097152 s, plus 80 µs of handler time, a possible snapshot pair is `dext=15`, `s1.tc=5000`, `sx.tc=2456`. With `slot_ticks=12816`, `boundaries_between()` returns zero: `(3840 + 2544 + 6408) < 12816`. Consequently `el` becomes `(uint32_t)-2544`, or **4,294,964,752**, and enters `elapsed_sum`. The former USB exit judgment rejected this span. **Fix:** calculate the reconstructed duration signed and reject negative results before conversion; restoring USB validation also excludes this case.

- **The report can precede the deferred verdict.** [rowisr_diag.c:254](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:254). Its fixed `wait_ms(2)` does not establish that a USB judgment occurred: scan-only’s eight slots take 5 ms, and a spurious judging invocation postpones the judgment again. The saved report can therefore retain `gen_delta == 0` although sub 6 subsequently records a rejection. **Fix:** capture the post-state after an actual post-injection judgment, with a bounded timeout and an explicit pending outcome.

The remaining checks, in your order:

1. **The modulus arithmetic survives on a continuous interval.** Ordinary time added around the silence advances both clocks equally; it cannot cancel the missing CT16B5 wraps. Within the plan’s 13 s scope, the approximately 49 ms minimum separation remains comfortably outside tolerance. A spurious judging invocation preserves the old baseline, so the longer interval still works provided continuity survives. The failure above is discarded evidence, not the two moduli agreeing again.

   At [rowisr.c:928](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:928), once `cont` and the starting-frame condition hold:
   - Fresh start, stale end: rejected as an event.
   - Changed `ugen`, or bus down at the end: rejected.
   - Both ends stale, with a pending start: unjudged without another loss.
   - Pending start, fresh end: spans compared, including an alias during recovery.
   - Generation changed across entry: comparison skipped; the generation check counts the observed loss. It does **not** account for a separate alias after that loss, as the P1 demonstrates.

2. **The adoption ordering itself is coherent.** `adopt_pending` is cleared at entry, set only by this invocation’s successful invalidation, read by `usb_base`, then consumed by `service_commit`. A crossed path that never commits leaves it set only until the next entry clears it. No stale or prematurely consumed adoption path found.

   After an ordinary committed rejection and re-prime, both baselines carry `adopt_gen`, so the next service’s `valid1` and next judgment’s `cont` can hold. A tick invalidation prevents adoption through the locked `time_gen == s1.gen` check; a later invalidation makes the saved generations mismatch. Sleep, degraded and dev-lock exclusions retain their invalidation rules. All three explicit `have_last = false` sites have matching `have_usb_base = false`; their delayed reseeding is part of the P1.

3. **The removed exit verdict protected duration accounting only.** It did not invalidate time, count losses, change omissions, or control the arm. One isolated silence straddling one invocation introduces at most one corrupted elapsed sample, subject to the underflow P2 above. Subsequent duration differences cancel the extension’s missing offset.

   The next actual judged entry rejects an isolated alias if its baseline remains continuous and eligible. The cadence change additionally affects slot/latency accounting as described above. The unchanged arm still checks pending `RIS`, generation-qualified crossing, and deadline; an interruption before step 6 leaves the match flag to prevent the arm.

4. **The isolated bench cases retain their loss/reject expectations**, assuming a usable baseline before injection:

   | Cases | Losses attributable to silence | Frame rejects |
   |---|---:|---:|
   | 5/7.5 ms; 7.9 ms when observation gap stays below 8 ms | 0 | 0 |
   | Guard cases: 8.1–200 ms, 1,000/2,048/7,000 ms | 1 | 0 |
   | 350/700/1,049 ms on USB | 1 | 1 |
   | Battery 20 ms / 350 ms | 1 / 0 | 0 |

   The script correctly leaves 7.9 and 8.1 ms ungated on exact loss count. Healthy `usb_checked` growth becomes approximately one eighth. Invalid-service counts are **not** divided by eight: guard/re-prime invalidity remains per service, recovery exclusions become sparse, and an ordinary isolated frame rejection still invalidates one judging service. Historical counts of 2–4 after guard cases need not repeat. Aliased missed-slot contributions can now appear before rejection.

   [silence_check.sh:72](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/silence_check.sh:72) gates losses/rejects, not judged or invalid-service counts, and reads after another 600 ms. Sub 7’s mask, spin, markers and cancellation are unchanged; subs 8/9 retain their layout, with the timing limitation above.

5. **Entry masked section:** the only source change between lock and unlock is `take_snapI` versus `take_timeI` selection. Phase increment/reset is outside. Both helpers remain `static inline`; emitted absence of calls cannot be confirmed from source alone.

6. **Host/wire compatibility:** page 7 and sub 6 layouts are unchanged. `rowisr_diag.py usb` prints interval counts without converting them to services; the inspected consumers contain no one-judgment-per-service calculation. Page 7 still exposes per-service statistics, including the validity regression above. Sub 10’s corrected `put16(&data[15], 256u)` matches the decoder.

Read the complete worktree file and parent diff; HEAD matches `1d73bf3ed5`. No builds, tests, or bench commands were run.