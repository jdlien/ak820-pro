# ak820-agent — the macOS transport's per-exchange growth — plan

**Status: drafted, reviewed by codex, diagnosed, FIXED and deployed on
2026-09-18.** The macOS daemon grew about **1.9 MB of `phys_footprint` a day**
because IOKit autoreleases an `NSValue` onto the calling thread on every HID
write and a Rust thread has no pool to drain it. The fix (`bf7b7f3`) is one
RAII pool guard in `write_report`; F0, a separate 1000x timeout-unit bug, is
fixed in `6d5c9a8`. Both are pushed and installed. **The only thing still open
is the 24 h → 48 h production gate.**

The growth was macOS-specific — ⚠️ **by mechanism, not by comparison**: the
leaked object is an Objective-C `NSValue` allocated inside IOKit, which cannot
exist on the Windows transport. An earlier draft argued macOS-specificity from
gremlin holding 2.74 MB of private bytes "after ~60,000 exchanges"; that
argument is **withdrawn** — the exchange count was roughly double the truth, and
a single endpoint bounds a total rather than a rate, so it excluded nothing.
Windows is being measured properly in parallel, but the macOS diagnosis never
depended on it.

⚠️ **Read [Review record](#review-record--codex-2026-09-18) before trusting any
figure here**, and note that the harness itself was capable of producing
confident numbers from invalid workloads until `2357880`.

The review also found **a production defect unrelated to memory** that is more
consequential than the leak. It is F0 below and should be fixed first.

Companion documents, part of this plan and not background:
[`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md) (the
port this defends, whose Phase 5b this closes) and
[`current-status.md`](current-status.md) (the operational state).

⚠️ **The leak is not urgent.** ~1.15 MB/day is ~400 MB after a year of
uninterrupted uptime on a 96 GB machine. It is worth fixing because it is a real
defect with a real mechanism, not because it threatens anything. F0 is a
different matter.

---

## ⭐ The cause, confirmed 2026-09-18

**`IOHIDDeviceSetReportWithCallback` leaks ~40 B per call. It is the entire
leak.** Measured on the daemon's own path with one call swapped, F0 already
fixed, every workload counted and verified, and footprint sampled every 2,000
cycles so the growth's *shape* is visible rather than inferred from a slope.

`isolate exchange` vs `isolate exchange-sync`, 20,000 cycles × 3 passes each.
Every pass: 20,000 attempted, 20,000 succeeded, 0 timed out, 0 failed.

| | async write | sync write |
|---|---|---|
| pass 1 | +80 KB per 2,000 cycles, ×8 | warm-up, then **flat** |
| pass 2 | +80 KB per 2,000 cycles, ×8 | warm-up, then **flat** |
| pass 3 | +80 KB per 2,000 cycles, ×8 | warm-up, then **flat** |
| steady state | **40 B/cycle, linear, forever** | **2 B/cycle by pass 3** |

The async shape is arithmetically perfect — `+80 KB` per 2,000 cycles, eight
times in a row, in all three passes. The sync shape is flat to the kilobyte for
18,000 consecutive exchanges.

⚠️ **40 B/cycle is an average over page-granular growth**, not a 40-byte
object: +80 KB per 2,000 cycles is five 16 KiB pages, about one page per 400
exchanges. Anyone hunting a 40-byte allocation is hunting the wrong thing.

**Three consequences for the rest of this document:**

- **C2 is confirmed** — properly this time. The earlier 41 B figure came from
  differencing two harness modes that also differed in locking and wakeup
  structure, which the review correctly rejected. This comparison changes only
  the write call.
- **C4 — the "~26 B floor" — never existed.** It was an artefact of the
  `write-sync` mode's 20 ms drain loop. `exchange-sync` reaches a true zero, so
  there is no unexplained remainder. The honest gap in the diagnosis is closed.
- **C5 is ruled out.** With F0 fixed, **zero** writes time out across 60,000
  exchanges and the slope is unchanged, so IOKit's timeout path is not the
  mechanism. Apple frees the async callback state on normal completion; the
  leak is something else on that path, which the allocation census will name.

**What remains is not diagnosis but design.** The async call is what bounds the
write with a timeout and what would supply a completion timestamp, so it cannot
simply be swapped — see
[Risks](#risks--and-what-a-sync-write-would-actually-require).

---

## F0 — the write timeout is 1000x too short, in production, today

⚠️ **This is a correctness bug, not a memory bug, and it is the most important
thing in this document.**

`IOHIDDeviceSetReportWithCallback` takes its timeout as a `CFTimeInterval` —
which is seconds everywhere else in CoreFoundation. It is not seconds here. The
installed SDK header says so explicitly:

> `@param timeout CFTimeInterval containing the timeout in **milliseconds**.`
> — `MacOSX.sdk/.../IOKit.framework/Headers/hid/IOHIDDevice.h:676`

`src/platform/macos/device.rs:423` passes `timeout.as_secs_f64()`. The caller's
value is `WRITE_TIMEOUT = 1000 ms` (`hid/exchange.rs:37`), so we pass `1.0`, and
IOKit reads **1 ms**. Every write the macOS daemon has ever made has had a
one-millisecond deadline instead of a one-second one. The spike has the same bug
at `spikes/s2-iokit/src/device.rs:289`.

**Why it has not been obvious:** the write normally completes in ~0.09 ms
(measured userspace lag p50), comfortably inside even 1 ms, and our own Rust
deadline is the outer bound that actually governs. So the daemon works, and no
write has been observed to time out: across 60,000 counted exchanges after the
fix, **zero** timeouts. The worst observed write was 9.1 ms, so the window is
real but rarely crossed.

⚠️ **RETRACTED, same day.** An earlier version of this section claimed F0 was
"very likely what produced the 9 HID timeouts in 45 minutes during the
`ProcessType Background` incident", and that the scheduler diagnosis had treated
a symptom. **That was wrong, and the original diagnosis stands.** Three checks
against the source and the incident record:

1. Those nine were logged as **"no reply from the keyboard"**, which is
   `Error::Timeout` on the **read** path (`hid/mod.rs:258`). A write that times
   out returns `Error::Io { op: "write" }` and prints `0x800703E3`
   (`hid/exchange.rs:408-414`). Different error, different text; the log says
   which happened.
2. The same 45 minutes saw **the perl helper's calls to a paused Music time out
   and both AppleScript reads time out** — separate processes that a HID write
   deadline cannot reach.
3. Priority 4 explains all three symptoms; F0 explains none of them.

⚠️ **Independently confirmed** by the Windows session against the shared code:
`no reply from the keyboard` is `Error::Timeout` with an empty drain list
(`hid/mod.rs:258-259`), and the only other producer of that exact string in the
tree is a scheduler test (`clock/scheduler.rs:920`). The two failures are
textually distinct in the log, so nine lines reading that string are nine read
timeouts, and nothing else.

The lesson is the one this whole document keeps relearning: a new finding that
*could* explain an old incident is not evidence that it *did*. The claim was
made without checking which error text the incident actually logged, the check
took two minutes, and **the log had already recorded the answer before anyone
looked**.

**Fix:** pass milliseconds. Audit every `CFTimeInterval` at an IOKit HID call
site for the same assumption. ⚠️ Do **not** assume the sibling APIs agree —
`CFRunLoopRunInMode`'s seconds really are seconds; this one API is the outlier,
which is why it went unnoticed.

**Consequences for this plan:** the 1 ms deadline means an unknown fraction of
async writes may have been taking IOKit's timeout path rather than its normal
completion path. Apple's implementation frees the async callback state on normal
completion; whether the timeout path does is unverified. That makes it a
candidate cause in its own right — **C5** below — and it means **every async-arm
measurement in this document was taken under a misconfigured timeout** and must
be retaken after the fix.

---

## What is actually wrong, as far as it is established

`agent.rs:340` calls `P::open_board()` on **every media tick — 3 s** — and the
playback readout goes out every poll whether or not anything changed
(`media.rs:179`, a test that asserts exactly this). That is ~28,800
enumerate + open + exchange + close cycles a day, **plus** text keepalives and
changes, clock transactions and health reads, which have not been counted.
Growth per exchange multiplied by that rate is the daily figure.

**Growth is associated with the exchange, and only with the exchange.** The
other measured paths reach a ceiling and stop. That association is solid; the
mechanism behind it is not.

---

## The measurements

`phys_footprint` from `proc_pid_rusage` (rusage_info_v4 `ri_phys_footprint`),
**not RSS**. The field offset was independently confirmed correct against
`sys/resource.h:289` — 16-byte UUID then seven `u64`s, so `buf[9]`.

Run with `spikes/s2-iokit`'s `isolate` mode, which — unlike `soak` — keeps no
timing sample vectors, the confound the first review caught. The daemon was
booted out so nothing else held the board. Every request is
`frame(0x13, 0x01, &[])` — health page 1, RAM-only, per the BACKLOG rule from
the 09-16 stall incident.

⚠️ **Read these numbers with the caveats in [Harness defects](#harness-defects--fix-before-any-new-baseline).**
In particular the isolate modes discard every operation result, so none of these
figures is known to have measured 20,000 *successful* exchanges.

### Per-cycle cost, 20,000 cycles each

| path | what it does | RSS/cycle | footprint/cycle |
|---|---|---|---|
| `list` | the IORegistry enumeration `open_board()` runs before every open | 18 B | 18 B |
| `create` | `IOHIDDeviceCreate` + `CFRelease`, never opened | 81 B | 42 B |
| `open-bare` | create + open + close + release | 69 B | 30 B |
| `exchange` | one open, then n round trips | 121 B | 69 B |

### Three passes in one process

`create`, 20,000 cycles per pass: **+816 KB, then +0 KB, then +0 KB.**

`exchange`, 20,000 cycles per pass: **+1408 KB (70 B), +896 KB (45 B),
+800 KB (40 B).**

**What this does and does not show.** ⚠️ The earlier draft claimed this test
cleanly separates a leak from allocator retention. **That was too strong.** A
genuine leak can look flat while it consumes existing allocator slack or retains
already-allocated objects; conversely fragmentation, growing caches and deferred
frees can climb for several passes without losing anything permanently. And
70 → 45 → 40 is still *decaying* — it does not demonstrate a steady state.

**"Exactly zero" is nonetheless credible** and is not a saturated measurement:
re-using already-committed pages produces identical footprint values. It is
quantised accounting. ⚠️ On 16 KiB pages, one page over 20,000 cycles is
**0.82 B/cycle**, so the earlier "<= 5 B/cycle resolution floor" was wrong — 5 B
is a chosen tolerance, not a measurement limit.

⚠️ **A lifecycle confound:** each `exchange` pass creates a `Device` and destroys
it before the closing sample (`spikes/s2-iokit/src/main.rs:446`). Anything IOKit
retains until device destruction would be released at every measurement
boundary — while production keeps one `Board` alive for days.

### The arithmetic, with the real write rate

⚠️ **Corrected 2026-09-18.** An earlier draft used 28,800 exchanges/day — the
media poll rate — as the denominator. **The leaked object is one per WRITE, not
one per cycle**, and the write rate is higher:

| source | rate | writes/day |
|---|---|---|
| playback readout, every 3 s poll (`agent.rs:375`) | 1 per cycle | 28,800 |
| text keepalive, every 10th poll (`media.rs:35`, `KEEPALIVE` = 30 s) | 0.1 per cycle | 2,880 |
| clock and health transactions | ~72/h | ~1,730 |
| | | **~33,400** |

At the measured 48 B per write that is **1.60 MB/day**, against **1.88 MB/day**
observed (2.70 MB at 35 min on 09-17, 4.58 MB at 25 h on 09-18). The previous
figure of 1.15 MB/day understated it by using the cycle rate as the write rate.

⚠️ Still not a closed account — the observed window is a single day-one sample
that mixes ramp with leak, and the remainder is unattributed. But 1.60 against
1.88 is corroboration worth the name, where 1.15 was not. The write-rate
correction came from the Windows session, which caught the same error in its own
analysis first.

### What has been ruled out

- **Autorelease pools, on both threads.** `create+pool` and `open-bare+pool` are
  byte-identical to their unpooled twins on the calling thread; a pool drained
  per event on the run-loop thread leaves the exchange steady state at 40 B,
  unchanged (C1). The reviewer independently agreed the refutation is sound — a
  callback running inside a returning iteration is covered by that iteration's
  pool — and did not propose pools inside the callbacks as a next step.
- **Our own Rust in `discovery.rs` / `cf.rs`.** The matching dictionary is
  consumed by `IOServiceGetMatchingServices`; every `Cf` and `Io` releases once
  on drop. Reviewed line by line, and the reviewer concurred.

### ⚠️ What was wrongly ruled out

The earlier draft excluded per-report Rust allocation on the grounds that
`Arrival` is a fixed `[u8; 33]`. **That describes the spike, not production.**
Production's inbox is `VecDeque<Vec<u8>>` and `on_report` allocates a fresh `Vec`
for every report (`src/platform/macos/device.rs:118`, `:144`). Those vectors are
released normally, so this is **not** evidence of a Rust leak — but the exclusion
was unsound and, more importantly, **the spike is not an allocation-faithful
model of production.** Every inference from spike figures to daemon behaviour
inherits that gap.

---

## The candidate causes

### C1 — no autorelease pool on the run-loop thread — ❌ **RULED OUT**

Tested on both threads, no effect on steady state. Was the first review's
top-ranked candidate. Details above.

### C2 — `IOHIDDeviceSetReportWithCallback` — ⚠️ **DOWNGRADED**

`write-async` (67 B/cycle at pass 2) against `write-sync` (26 B/cycle), same
drain, 5,000 cycles × 2 passes.

⚠️ **The earlier draft called this "confirmed, ~41 B/call". It is not.** The two
arms do not differ only in the write call: the async arm adds sequence
bookkeeping, a completion callback, a mutex acquisition, a condvar notification
and potentially several timed waits, and the two share a condvar so callback
ordering changes wakeups and cycle duration. Equal timeout *arguments* do not
make equal work. Apple's published implementation does allocate async callback
state — and explicitly frees it on the normal completion path, which establishes
churn, not a missing free.

The honest statement is **"~41 B/attempt of additional footprint growth on this
async harness path"**, cause unattributed.

### C5 — IOKit's async **timeout** path — ❌ **RULED OUT**

With F0 fixed, **zero** writes timed out across 60,000 counted exchanges and
the 40 B/cycle slope was unchanged. The timeout path is not the mechanism. The
original reasoning is kept below because it was sound before the measurement.

#### (as written before the test)

Falls directly out of F0. Under a 1 ms deadline, some fraction of async writes
take IOKit's timeout path instead of its normal completion path. Apple's code
frees the callback state on normal completion; the timeout path is unverified. If
it leaks, that would explain why the async arm grows and the sync arm does not —
**without** the async API being inherently at fault.

**This is the most promising untested hypothesis**, and it is cheap: fix F0,
re-measure, and see whether the async/sync gap survives. ⚠️ Evidence against:
writes complete in ~0.09 ms typically, so timeouts should be rare, and a rare
event cannot produce a near-constant per-cycle cost. Evidence for: the isolate
modes discard results, so **we do not actually know the timeout rate** in any run
reported here.

### C4 — the ~26 B floor — ❌ **WITHDRAWN: IT NEVER EXISTED**

The earlier draft reported that `write-sync` "still grows 26 B/cycle" and
called it the honest gap in the diagnosis. ⚠️ **It was an artefact of dividing
a one-time warm-up by the cycle count.** With footprint sampled through the
pass instead of only at its ends, `write-sync` is flat:

```
pass 1:  500:+464  1000:+464  1500:+464 ... 5000:+464
pass 2:  500:+176  1000:+176  1500:+176 ... 5000:+176
```

Zero growth across 4,500 consecutive exchanges, twice. `exchange-sync` agrees
over 18,000. ⚠️ **This is the same error the whole per-cycle framing invited**,
and it is why the shape instrumentation now exists: a slope quoted as a
per-operation cost hides whether the growth is ongoing or finished. The
reviewer's insistence on workload validity and the owner's observation that
"40 B is too small to be a real leak" both pointed here.

### C3 — reduce the number of exchanges — ⚠️ **NARROWER THAN CLAIMED**

The earlier draft argued the playback readout is redundant because `route.rs`
extrapolates position host-side. ⚠️ **That conflates computing a new position on
the host with advancing it on the keyboard.** `media.rs:179` is a test asserting
that position 13 is sent after 10 with unchanged text. Suppressing those writes
changes what the LCD shows unless the firmware extrapolates position itself,
which is unestablished.

What survives: **suppressing byte-identical idle/paused payloads** is safe and
worth doing — overnight idle is where uptime accumulates. Suppressing *playing*
updates requires firmware evidence first (does it advance position on its own?
what expiry/keepalive applies?). ⚠️ And rate reduction lowers daily impact while
leaving per-exchange growth untouched, so it cannot be judged by the same gate as
a real fix.

---

## Harness defects — fix before any new baseline

⚠️ **No new measurement should be taken until these are closed.** The reviewer's
first finding was that the harness can produce convincing numbers from invalid
workloads, and it is correct.

1. **The isolate modes discard every result.** `isolate exchange` ignores the
   exchange outcome (`main.rs:450`); `write-async` ignores submission and
   completion; `write-sync` ignores its return code; both drain loops stop
   silently on a read error (`main.rs:605`). A run of 20,000 failures divides
   exactly like a run of 20,000 successes.
2. ⚠️ **The worst false pass:** once a `Device` is abandoned, every later write
   returns `Stuck` immediately (`spikes/s2-iokit/src/device.rs:268`) — and the
   harness keeps dividing memory growth by all iterations, making a broken run
   look clean.
3. **`proc_pid_rusage`'s return value is ignored** (`main.rs:238`). A failed read
   silently yields a zero-filled buffer and a bogus sample.
4. **Count the workload:** attempted writes, accepted submissions, successful
   completions, timeouts, reports received/matched/discarded, elapsed time. An
   unequal or failed workload must **invalidate** a comparison, not quietly
   improve its B/cycle.
5. **`mach_port_names` counts names, not references or queued resources.** The
   flat 37 does **not** establish "heap only, no kernel resources accumulate" —
   that claim is withdrawn.

---

## The fix — decision order

1. **F0 first.** Correct the timeout units in production and in the spike. It is
   a real defect on its own, and every async measurement here was taken under it.
2. **Close the harness defects** above. Then retake the `exchange` and
   `write-async`/`write-sync` baselines with counted, verified-successful
   workloads.
3. **Test C5**: does the async/sync gap survive a correct timeout?
4. **M1 — `exchange-sync`**: `exchange` with `set_report_sync`, 20,000 × 3,
   against the retaken baseline. This tests the daemon's path rather than a
   proxy. ⚠️ Needs the board; the daemon must be booted out and restarted after.
5. **Only then choose.** If a sync write is adopted, it needs the ownership
   design in [Risks](#risks--and-what-a-sync-write-would-actually-require), not a
   bare call swap.

⚠️ **Add an allocation-neutral measurement on the actual production transport**
before concluding anything about the daemon. The spike's `[u8; 33]` inbox and its
one-open-per-pass lifecycle are both unfaithful to production.

---

## Verification gates

⚠️ The earlier draft required all gates for any fix, which would have rejected
its own C3 option — a rate reduction legitimately lowers daily impact while
leaving per-exchange growth alone. **Two separate criteria:**

### Criterion A — growth per exchange removed (for C2/C4/C5 fixes)

1. Steady-state footprint growth **<= 7 B per successful exchange**, derived from
   the 0.2 MB/day budget at 28,800 exchanges/day. Not zero: a residual budget.
2. Measured over **more than three passes**, with intermediate checkpoints, on a
   device **held alive across passes**, sampled both while alive and after
   destruction and quiescence.
3. Every pass' workload counted and verified equal and successful.
4. Supplement footprint with **live-allocation evidence** (allocation stacks, VM
   regions) before claiming a mechanism is localised. Footprint measures impact,
   not a census of live objects.

### Criterion B — daily impact reduced (for C3)

1. Per-exchange growth may be unchanged. Exchanges per day must fall measurably,
   with counts before and after.
2. ⚠️ **No change to what the LCD displays.** Position must still advance on the
   board as it does today, or the firmware's own extrapolation must be
   demonstrated first.

### Both — production confirmation

`phys_footprint` sampled periodically, alongside **process identity and start
time, awake duration, successful exchange count, failures, and board
retirements**. Evaluate growth per successful exchange *and* per day. ⚠️ The
24 h → 48 h window is better than day one but ⚠️ **elapsed time alone proves
nothing** — a daemon asleep, disconnected, backed off or restarting would pass it
trivially. Baseline for the current run: **2,960 KB at 11:59:45 on 2026-09-18**,
build `8a91840`, pid 6460.

### Both — no regression

358 tests green. And ⚠️ **fault-path tests the current gate entirely lacks**: a
permanently blocked write, a late completion, an expired queued request, a
disconnect, and a retry after timeout. 200 healthy exchanges say nothing about
behaviour when a call never returns — which is the entire reason the async write
was chosen.

---

## Risks — and what a sync write would actually require

The async write buys two things, and a replacement must supply both.

**It bounds the write.** `IOHIDDeviceSetReport` can block indefinitely, and the
clock loop cannot afford that. ⚠️ Moving the call onto the existing run-loop
dispatcher does **not** solve it: the caller still blocks at `runloop.rs:97`'s
`rx.recv()`, and a blocked call there would also block input callbacks. ⚠️ **A
watchdog that notices a blocked write cannot cancel it.**

The minimum viable design, per the review:

- One persistent I/O worker owning the device and its request buffer, with the
  callback run loop independent of it.
- A bounded submission queue, at most one operation in flight, an absolute
  deadline covering **queueing and execution**, and an expired queued request
  that never starts.
- On timeout: quarantine that worker and reject further writes. Do **not** free
  its buffer, close concurrently, join it on the clock thread, or spawn unbounded
  replacements.
- Immutable request/generation IDs so late results are discarded.
- ⚠️ This preserves scheduler responsiveness but **cannot recover** from a
  permanently blocked syscall. True recoverability means device ownership in a
  supervised helper process, restarted only after the old owner has exited — and
  staying unavailable rather than ever creating a second writer.
- ⚠️ A timeout does not prove the write never reached the board, so protocol
  resynchronisation is still required.

**It supplies a completion timestamp.** With a sync write, timestamp immediately
before the call and immediately after a successful return **on the worker**,
before any notification or IPC, and keep the input kernel/callback timestamps
separate. That return time is an observation of completion, not a USB wire
timestamp, so the metric must be **rebaselined**, not assumed comparable. ⚠️
Production currently records neither write-completion nor input timestamps
(`device.rs:138`, `:169`), so this metric does not exist there yet.

**Other risks.** Changing the run loop changes callback timing, which the clock's
round-trip measurement rests on. `CFRunLoopRunInMode` with
`returnAfterSourceHandled: true` returns after one source — safe only because
`perform` drains every queued job, which is the kind of thing that stays safe
until someone adds a second source.

---

## Rollback

Confined to `src/platform/macos/`. The last good build is installed and running;
reverting is `git revert` plus a rebuild and reinstall. No firmware, no protocol
and no clock contract is touched. ⚠️ Rollback follows the clock-owner rule: stop
the daemon before the timekeeper starts, never two clock writers.

---

## Review record — codex 2026-09-18

Model gpt-6-astra, high effort, read-only, no binaries run and no HID device
touched. Eight findings, ranked by how much each changes the plan. **Every
factual claim below was independently verified against the SDK headers and the
source before acceptance.**

| # | finding | disposition |
|---|---|---|
| 1 | Harness measures results it discards; timeout units wrong | ✅ **Accepted.** Became F0 and [Harness defects](#harness-defects--fix-before-any-new-baseline). Verified against `IOHIDDevice.h:676` and `exchange.rs:37`. |
| 2 | The 41 B attribution does not hold | ✅ **Accepted.** C2 downgraded to an associated path difference. |
| 3 | Harness != production; the Rust exclusion is wrong for production | ✅ **Accepted.** Verified `device.rs:118`/`:144` — production allocates a `Vec` per report. The exclusion was my error, from reading the spike and writing about production. |
| 4 | Three passes is not the clean discriminator claimed | ✅ **Accepted.** Claim weakened; page-quantisation arithmetic corrected (0.82 B/cycle, not 5). |
| 5 | A sync replacement needs real ownership design | ✅ **Accepted** in full into [Risks](#risks--and-what-a-sync-write-would-actually-require). |
| 6 | Gates need workload validity, fault paths, and split criteria | ✅ **Accepted.** Criteria A and B separated; the "all gates" rule would have rejected C3. |
| 7 | `phys_footprint` is right for impact; the port claim is not | ✅ **Accepted.** Offset independently confirmed. "No kernel resources accumulate" withdrawn. |
| 8 | Host extrapolation != board extrapolation | ✅ **Accepted.** Verified against the test at `media.rs:179`. C3 narrowed to identical idle/paused payloads. |

The reviewer also **confirmed** the C1 refutation as sound and declined to
propose pools-inside-callbacks as a next step.

⚠️ **Nothing in this review was rejected.** That is unusual and worth noting: the
previous review's top-ranked hypothesis was wrong, this one's findings all held
up under checking, and two of them corrected errors of mine — the
production/spike conflation (#3) and the overclaimed discriminator (#4).
