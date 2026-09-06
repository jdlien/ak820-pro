# ak820-agent clock parity — what the Rust port must not change

Status: **REFERENCE, written 2026-09-05, corrected the same day** against the
Codex review ([review-codex-ak820d-2026-09-05.md](review-codex-ak820d-2026-09-05.md),
findings 2, 3 and 7). Nothing here is a proposal; it is a transcription of what
`hostagent/ak820-timekeeper.py` does today, so a rewrite can be *checked*
against it rather than reasoned about.

> ⚠️ **This is half the contract.** The scheduler and the SOF-bias learner live
> in Python; the precision — five GETs, min-RTT selection, the fraction formula,
> SET packet construction and the outbound-lead learner — lives in
> `ak820ctl.c`. See **[AK820-AGENT-CLOCK-TRANSACTION.md](AK820-AGENT-CLOCK-TRANSACTION.md)**.
> The oracle is Python **plus** the pinned C utility. Reproducing everything
> below perfectly while getting the C half wrong still injects milliseconds on
> every SET.

## Why this document exists

Out of the box this board's clock drifted badly and could only ever be set to
within a few seconds. An always-on clock on a computer-attached device that is
visibly wrong is worse than no clock. The current behaviour is the result of a
lot of measurement, and several constants below exist because a
*reasonable-looking* value failed in a way that took hours to see.

**The rule: port the constants and gate conditions verbatim. If a value looks
arbitrary, it is not — find the comment before changing it.** Separate any
intentional improvement from parity work, and land it *after* parity is proven.

## Constants (verbatim)

| Name | Value | Meaning |
|---|---|---|
| `LOOP` | 15 s | main loop period |
| `SYNC_INTERVAL` | 300 s | periodic sync once the residual is small |
| `SYNC_INTERVAL_FAST` | 180 s | periodic sync while the last residual exceeded `FAST_ABOVE_MS` |
| `FAST_ABOVE_MS` | 60 ms | threshold selecting the fast interval |
| `SLEEP_GAP` | 60 s | loop gap above which the host is assumed to have slept |
| `BIAS_INTERVAL` | 900 s | continuity needed before a bias *seed* measurement |
| `LEARN_MIN_ELAPSED` | 90 s | minimum spacing between the two syncs a residual spans |
| `LEARN_MAX_BEFORE` | 400 ms | larger residuals are convergence or a step, not a rate error |
| `LEARN_GAIN` | 0.25 | low gain: each residual carries ILRC wander as noise |
| `LEARN_MAX_DP` | 6 ticks | "period unchanged" tolerance (~180 ppm) |
| `BIAS_LIMIT` | 600 ppm | matches the firmware's own sanity clamp |

## The four failures these encode

1. **`SYNC_INTERVAL_FAST` must leave the board's frequency window alone.** A
   slew writes the period register ~3 times and **every write restarts the
   frequency window**. At 120 s against the firmware's then-128 s window the
   window *never completed*: the loop froze at a wrong period, the residual
   stayed large, so the interval stayed fast — a self-sustaining trap that held
   a **+300 ms plateau for six hours on 2026-09-04**. Any sync interval must
   exceed the firmware's window plus a slew.
2. **`LEARN_MIN_ELAPSED` was 240 s**, longer than the fast interval, so the
   learner could never fire while the residual was large — the one time it was
   needed.
3. **`LEARN_MAX_DP` 6 with gain 0.25.** The ILRC wanders ±300 ppm on 5-minute
   scales and the loop follows it a few ticks per window, so "period unchanged"
   never strictly happens. A wider gate plus low gain averages the wander out.
4. **The frame-count bias is a SEED ONLY.** It measured **−369..+587 ppm** on a
   controller the phase-0 test pinned at **+78 ±3**; each new value re-steered
   the clock, giving a 5-minute sawtooth of 150–330 ms (2026-09-03).

## Sync triggers

Evaluated every `LOOP`; **first match wins**:

| Reason | Condition |
|---|---|
| `enumerated` | present now, not present last loop |
| `wake` | `now - last_loop > SLEEP_GAP` |
| `periodic` | `now - last_sync >= interval` |

- `enumerated` sleeps **2 s** before syncing, to let the board settle.
- **On a FAILED sync, none of `last_sync`, `interval` or the learner baseline
  update** — but `was_present` updates regardless, so a failed `enumerated` or
  `wake` reason is *not* retried on the next loop.
- Interval after a successful sync:
  `FAST if (before is not None and abs(before) > 60) else 300`.
  ⚠️ **An unknown residual (`before is None`) selects the normal 300 s**, not
  the fast interval.
- Absence clears both the seed state and the learner state.

## The learner

`learn_bias()` runs after every successful sync. It learns only when **all** of:

- `reason == "periodic"` — a non-periodic sync only *establishes* the baseline
- a previous sample exists, and **both** samples have a non-`None` nominal period
- `before is not None`
- `slewing` — `"(slewing)" in out` **and** `"warning:" not in out`
- `abs(before) <= LEARN_MAX_BEFORE`
- `ref_state == 2`
- **settled**: `abs(prev_pnom - pnom) <= LEARN_MAX_DP`
- `elapsed >= LEARN_MIN_ELAPSED`
- **the cache is readable and already contains `b`** — with no existing bias
  there is nothing to adjust, and the seed owns that case

Then:

```
e_slow = -before * 1000.0 / elapsed
b_new  = clamp(b - 0.25 * e_slow, ±600)
```

and success is logged **only if the cache write succeeded**.

Corrections to earlier drafts of this document, all verified against the source:

- A successful **non-periodic** sync establishes `{t, pnom}`, so the **first
  periodic sync after it can learn**. Two periodic syncs are *not* required.
- A **failed status read** stores `pnom = None`, replacing the previous good
  nominal period rather than preserving it — the next sync then cannot be
  "settled" and cannot learn.
- **Time sources are mixed**: scheduling and the seed use wall time
  (`time.time()`); the learner's `elapsed` uses `time.monotonic()`. The learner
  timestamps **before** its status read, so the read's duration is inside
  `elapsed`.
- The **hold log** fires on a *narrower* set than "all gates except settled": it
  requires neither the 90 s elapsed gate nor an existing cached bias.
- `int(round(...))` is **banker's rounding** (ties to even).
- ⚠️ `before` has already been rounded to **one decimal by C** before Python
  compares it against 60 and 400. A merged Rust daemon holding full precision
  **will decide differently at those boundaries** unless it rounds first.

Keep the hold log. It is how you tell "the learner is working and declining"
from "the learner is broken" — observed doing exactly that at 11:54 on
2026-09-05.

## The seed (`bias_step`) — previously omitted

Runs every loop while the board is present, and is **disabled entirely once the
cache has a bias**.

- Reset — and start a fresh measurement — when the cache has no bias *and*
  either the controller id or the SOF epoch changed, or status is unreadable.
- Otherwise accumulate wall-clock duration `H` from `t0`.
- At `H >= BIAS_INTERVAL` (900 s): `F = (frames - f0) mod 2^32`, then
  `b = (F / (1000 * H) - 1) * 1e6`.
- Accept only **strictly** `-600 < b < 600`; send `clock --bias round(b)`, log,
  persist `{cid, b_ppm, t}` to `~/.ak820ctl-bias.json`, then **clear** the
  measurement so the next one starts fresh.

## ⚠️ `HOME`, on Windows

`ak820ctl` keys its cache off `getenv("HOME")` (`ak820ctl.c:225`), falling back
to `"."`. Windows sets no `HOME`; MSYS2 sets a POSIX path a native binary cannot
resolve. **A Rust port owning the cache in-process removes this failure mode
entirely** and should. If it keeps shelling to `ak820ctl`, exporting `HOME` is
mandatory.

## How to verify the port

### Not live shadow mode

An earlier draft proposed running the Rust daemon read-only beside the Python
agent and diffing decisions. The review dismantled it, correctly:

- Independent polling gives the two implementations **different inputs** —
  Python may measure before a correction while Rust reads during the resulting
  slew. It is not a controlled comparison.
- Without sending SET, Rust never observes its own SET result, `o'`, lead
  calibration, or step-versus-slew outcome. **The entire write path stays
  unexercised.**
- Python keeps the clock healthy throughout, so a broken Rust write or
  bias-application path produces no symptom.
- The current logs cannot support the diff anyway: they lack complete gate
  inputs, timestamps, cache state and state transitions.

⚠️ **And a fifth reason, measured 2026-09-05, which is decisive on its own.**
Windows delivers HID input reports to *every* open handle. A Rust process that
held a handle and wrote nothing but flash reads received the Python
timekeeper's **entire clock transaction** — five `RTC_GET_TIME`, the
`RTC_SET_TIME_MS`, the verify GET and the status read.

A foreign `RTC_GET_TIME` reply is a **well-formed `RTC_GET_TIME` reply**: right
channel, right command, protocol version 2, plausible fields. No amount of
request/reply correlation can tell it from the answer to one's own GET, so a
shadow reader can consume the oracle's replies and pair *their* board sample
with *its own* `t0`/`t1` — and the oracle can consume the shadow's. Two live
readers do not merely produce different inputs; **they corrupt each other's
measurements**, silently and in both directions.

So a concurrent live comparison would be measuring interference, not parity.
Replay is not the better method here, it is the only sound one. See
[AK820-AGENT-PLAN.md](AK820-AGENT-PLAN.md#️-the-finding-that-changes-a-design-assumption-correlation-is-not-sufficient).

### 3a — deterministic differential replay

Capture from the oracle: wall **and** monotonic timestamps, presence
observations, raw transaction results, cache contents before and after, and
outcomes. Feed **identical recorded inputs** to both implementations and compare
**decisions and resulting state**, including the serialized cache bytes.

Cases that must appear in the corpus:

- every threshold boundary — 60 ms, 400 ms, 90 s, 6 ticks, ±600 ppm, ±500 ms
- rounding ties (banker's rounding) and the one-decimal `before`
- missing data: `before is None`, unreadable status, `pnom = None`
- a failed sync, and a failed cache write
- a changing nominal period across samples
- cache absent, cache short, cache with out-of-range values
- seed: epoch change, controller change, `b` exactly ±600 (must reject)

⚠️ **Require positive evidence that learning actually fired.** Two
implementations that decline every sample agree perfectly and prove nothing.

This is also where the earlier claim that "nothing in a unit test would catch
it" was too sweeping — most of the above **are** deterministic tests, and the
port should be written test-first against them.

### 3b — measured takeover

Replay proves computation; only hardware proves timing and feedback. Stop the
Python task, run the Rust daemon, and measure — but note what the instrument
does and does not tell you.

⚠️ **`clock-phase.py` has three limits, all relevant:**

1. It recovers the **sub-second phase**, reducing the host fraction to the
   nearest second. A clock **1.016 s** late reports the same **+16 ms** as one
   0.016 s late. It prints board time but does not validate the full
   date/time — so it cannot detect a whole-second or date error at all.
2. It timestamps **after** the HID reply, so its reading includes detection and
   transport latency. The host's NTP offset does not calibrate that out. The
   recorded **+15.9 ms** baseline therefore does **not** by itself demonstrate
   sub-10 ms board-to-host sync.
3. It **holds the HID handle for the whole sampling run**, so an hours-long run
   would starve the daemon.

Phase 3b therefore requires:

- full calendar/date/time correctness checked alongside fractional phase
- short, coordinated measurement bursts, with uncertainty recorded
- samples spread **across** the sync interval, not only just after a correction
- counts of successful syncs and learner firings, plus bias, nominal period,
  slew activity and an error distribution
- an overnight run that covers the historical six-hour failure mode, with media
  polling and realistic load active
- **numeric acceptance limits against a matched Python baseline.** "Anything in
  that neighbourhood" is not a gate.

### The oracle's own tooling is not safe to run as-is

⚠️ The review's sharpest catch: the oracle still performs the very HID sweep the
plan forbids. `hid.enumerate` is called by the timekeeper's presence poll **every
loop**, by its Windows `controller_id()`, by `clock-phase.py`, by
`ak820health.py`, and by **every `ak820ctl` invocation including
`clock --bias`**. `ak820text.py`'s caching reduced the *frequency* but not the
*scope* of devices opened.

So a long validation run against the oracle re-introduces the risk. Either give
the Python side a safe discovery adapter, or drive validation from **captured
replay inputs** rather than live oracle runs. Audit any tool before it becomes
part of a safety gate.

## Keep the oracle

`hostagent/ak820-timekeeper.py` stays in the repo and installable on Windows
until the Rust daemon has run clean for a week. It is the reference
implementation, macOS uses it regardless, and it is the only thing that can
settle "did the port change this, or did the hardware?"

## Port status (2026-09-06)

Everything above is ported verbatim in `ak820-agent/src/clock/scheduler.rs`
— constants, the three triggers in their order, the interval rule with the
unknown-residual case, the learner's every gate including the narrower hold
condition and the `P None` print, the seed's reset/restart/measure and its
strict `±600`, banker's rounding via `f64::round_ties_even`, and the mixed
time sources (wall for scheduling and the seed, monotonic for `elapsed`,
taken before the status read). One unit test per gate and boundary.

**3a, the replay, is met** against this machine's own timekeeper log
(`ak820-agent/tests/timekeeper_replay.rs` over
`tests/fixtures/ak820pro-timekeeper-2026-09-05.log`): all 108 `bias learned`
lines reproduced — 98 byte-identical at the printed elapsed, the other ten
within the half-second the whole-second print hides — all 59 `bias hold`
lines byte-identical, and all 171 interval choices confirmed by when the
next sync actually happened. That is the positive evidence this document
asks for. What the log cannot give, the test states: `ref_state` is assumed
2 where learning fired, and `elapsed` is replayed at printed precision.

**3b, the measured takeover, is open** and is the owner's: `ak820 install
--clock`, the procedure and limits in the plan's "Phase 3a evidence".

Two divergences from the Python, both already recorded for the C side: the
cache is parsed by the C's `fscanf` rules, so a bias written as `12.5` reads
as `12` where Python's `cap_read()` would return `None` and decline to learn;
and the `--bias` persistence file `~/.ak820ctl-bias.json` is not written —
nothing reads it.
