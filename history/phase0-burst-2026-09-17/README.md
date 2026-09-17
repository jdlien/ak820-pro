# Phase 0 burst A/B on gremlin (2026-09-17)

The live evidence that closed Phase 0 of
[`plans/AK820-AGENT-CROSSPLATFORM-PLAN.md`](../../plans/AK820-AGENT-CROSSPLATFORM-PLAN.md),
the platform seam. It ran on gremlin (Windows 11, 26200.9457) against that
machine's own AK820, on firmware `8608c4f6-dirty`, with no media playing.

## Why a burst, not the overnight gate

The overnight gate (3 windows of 50 syncs from 2026-09-16 19:38:59) failed as
written. Each window's worst sync exceeded the 09-09 → 09-15 baseline's 27.6 ms:
30.0, 35.6 and 28.7 ms. The p95 stayed inside the baseline in all three. The
environment had moved, though. The **pre-refactor** binary had already done
worse over the three hours before the reinstall (worst 36.6 ms, 3 of 36 syncs
over 27.6), after a new NVIDIA driver was installed and Windows Sandbox was
removed on 09-16. So the owner replaced the planned night of `d8ead97` with an
interleaved burst of the only path the refactor touches: the HID transport and
the host time reads around one exchange. The scheduler, learner, cache and
transaction are byte-identical between the two builds.
The rule below was committed to the plan before the run.

## What ran

`burst_ab.ps1`:

1. Wait for the daemon's periodic sync (10:17:26) and its bias line.
2. `Stop-ScheduledTask \ak820pro\AK820Pro-agent`, and wait for its process to exit (10:17:29.873).
3. Run 50 rounds, 10:17:29.879 → 10:19:13.5. Each round runs `ak820 clock --raw` from both CLIs, about 1 s apart. Odd rounds run NEW first, even rounds OLD first.
   - NEW is the installed `ak820.exe` from `e07fdfa` (`v0.1.1-22-ge07fdfa`).
   - OLD is a saved `ak820.exe` from `d8ead97`, the binary the baseline ran.
4. `Start-ScheduledTask`, always, from a `finally` block. The daemon logged `e07fdfa` at 10:19:13 and an enumerated sync at 10:19:15: before −5.0 ms, after −3.4 ms, rtt 4.6 ms, with no seed line.

The keyboard's clock free-ran for 1 min 44 s. Every CLI output is in
`phase0-burst-20260917-101627.txt`, verbatim, including `--raw`'s report
bytes, `host_mid_sod` and full-precision `rtt_ms`. The scripts' paths are
those of the gremlin session that ran them.

## Result

`python burst_grade.py phase0-burst-20260917-101627.txt` computes these.
rtt is `rtt_ms`, and p95 is `sorted[int(0.95 n)]`. Jitter is the median
|offset[i] − offset[i−1]| over each binary's own consecutive reads, at the
CLI's 0.1 ms offset resolution.

| | e07fdfa (NEW) | d8ead97 (OLD) |
|---|---|---|
| reads | 50 | 50 |
| failed (non-zero exit, `no reply`, no offset) | 0 | 0 |
| discarded reports | 0 | 0 |
| rtt median / p95 / max | 5.079 / 7.345 / 7.616 ms | 5.340 / 6.930 / 7.098 ms |
| offset jitter | 0.40 ms | 0.50 ms |
| offset mean (first → last) | −4.45 ms (+0.8 → −4.3) | −4.38 ms (+1.3 → −4.3) |

| # | Condition (e07fdfa passes only if all hold) | Evaluated | |
|---|---|---|---|
| 1 | failed reads: new ≤ old | 0 ≤ 0 | yes |
| 2 | median rtt within ±0.3 ms | \|5.079 − 5.340\| = 0.262 | yes |
| 3 | rtt p95: new ≤ old + 0.5 ms | 7.345 ≤ 7.430 | yes, by 0.085 ms |
| 4 | offset jitter: new ≤ 1.2 × old + 0.1 ms | 0.40 ≤ 0.70 | yes |

**Verdict: PASS.** Condition 3's margin is thin. With n = 50, the p95 is the
48th value. The rule was fixed before the run, and it was not re-run for
margin.

**Supporting, not deciding.** This check looks for a host-time offset
between the binaries, which is what moving `clock/host.rs` into
`platform/windows/` could have introduced. A least-squares trend was fitted
to both binaries' offsets against `host_mid_sod` (−18.8 ppm, visibly
non-linear because the board was still slewing from the last sync) and
removed. Paired per round, the NEW − OLD residual has mean −0.076 ms,
sd 0.597, n 50, and a 95% CI of −0.242 to +0.090 ms. That is −0.148 ms in
rounds where NEW went first and −0.004 ms where OLD did. No offset is
detectable at the ±0.25 ms level.

CLI rtt (~5.1–5.3 ms) runs above the daemon's (~4.2 ms) for both binaries
alike. Each read is a fresh process and a first exchange on a new handle.
