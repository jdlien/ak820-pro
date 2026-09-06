# Codex audit of ak820-agent phase 1 — 2026-09-06

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read.

Second audit under the standing rule. It reviewed the phase-1 media code and
**re-checked the phase-0 fixes**, which is where two of its findings came from —
a fix that looks right and is not is worse than the original bug, because it
arrives with a test saying otherwise.

Its shell could not start in this session, so it worked from direct file reads
and its own JS sandbox; it verified the fold table against Python independently
rather than taking the fixture's word for it.

⚠️ The transport changed *while* it was reviewing (the `exchange.rs` extraction
and the clock module landed mid-run). It noticed, re-read, and adjusted its line
references — the findings below are against the post-refactor tree.

**Verdict: the phase-1 gate stays open.** Findings 1, 2, 3, 4, 5, 6, 7 and 9 are
fixed; 8 is fixed by construction. Disposition in
[AK820-AGENT-PLAN.md](AK820-AGENT-PLAN.md#phase-1-audit--disposition-2026-09-06).

Verbatim below.

---

**I found serious liveness issues and concrete parity failures. I would keep the phase 1 gate open.**

The transport changed during this review. References below reflect my final read at **11:28 UTC**; I rechecked the affected findings after the extraction into `hid/exchange.rs`.

**1. P1 — A failed session iteration can abort the entire release process.**  
[smtc/worker.rs:141](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:141), [Cargo.toml:56](C:/Users/jdlien/code/ak820-pro/ak820-agent/Cargo.toml:56)

`for session in sessions` invokes `IVectorView::into_iter()`. In the pinned `windows-collections` 0.3.2, that calls **`self.First().unwrap()`**.

Concrete failure: `GetSessions()` succeeds, but obtaining its iterator returns an error. That becomes a panic. With release `panic = "abort"`, the whole process terminates—including the future clock loop. With unwinding enabled, the detached worker instead dies permanently without recording the failure.

Subsequent iterator errors also silently terminate iteration, potentially publishing an incomplete session list as a successful poll.

**Fix:** Traverse using explicitly fallible `First`/`HasCurrent`/`Current`/`MoveNext`, or `Size`/`GetAt`, with a defined error policy. Exercise those failures through a fake. `catch_unwind` alone cannot protect the current release build.

**2. P1 — The shared mutex still allows a media-side stall to block the clock caller.**  
[smtc/worker.rs:218](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:218), [smtc/worker.rs:247](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:247)

The worker holds the mutex while running `e.to_string()` at line 261. This is not necessarily a local string operation: pinned `windows-result` retrieves error text through COM `QueryInterface`, `GetErrorDetails`, and potentially `GetDescription`. Dropping the error also releases its COM object inside that critical section.

Concrete failure: a returned error-info object blocks while supplying its description. The worker holds `state`; the scheduler calls `latest()`; its blocking `lock()` now parks the scheduler indefinitely. The separate thread has ceased to isolate the clock.

Snapshot construction also clones unrestricted metadata while holding this lock.

**Fix:** Construct snapshots, format errors, and release all WinRT objects **before** acquiring the publication lock. For the stated nonblocking caller contract, use a mailbox or `try_lock` with a caller-retained previous snapshot. Poison recovery via `into_inner()` is reasonable, but does not address blocking.

**3. P1 — Phase 0 finding 2 is only partly fixed: unanswered requests still contaminate later transactions.**  
[hid/exchange.rs:199](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:199)

The exhausted-drain refusal works. However, a timeout after transmission records no unresolved-request state.

The original single-owner counterexample still applies:

1. GET A is transmitted and times out.
2. GET B’s pre-drain observes an empty queue.
3. B is transmitted.
4. A’s delayed reply arrives and satisfies B’s channel/command matcher.

That assigns A’s board sample to B’s timestamps. Canceling A’s host read did not cancel its firmware command. Reopening alone cannot establish that no late broadcast remains.

**Fix:** Invalidate the logical clock transaction after an unanswered transmission and require an explicit resynchronization strategy before accepting indistinguishable replies again. A protocol nonce provides a stronger solution. Add the delayed-after-empty-drain case; the 33rd-queued-report test covers a different failure.

**4. P2 — The cancellation leak is bounded per handle, but recovery can accumulate abandoned handles.**  
[hid/device.rs:503](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:503), [hid/exchange.rs:115](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:115), [bin/ak820.rs:174](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:174)

The heap allocation and timeout branch preserve the pending operation’s storage. I found no concrete use-after-free in that path.

However, a stuck cancellation during pre-drain becomes `Queue::Unreadable`, losing `Error::Stuck`. `watch` then drops the device and opens another. If opens continue succeeding while reads cannot cancel, each cycle abandons another buffer, event, and device handle. The comment promising one process-lifetime leak is therefore unsupported.

**Fix:** Preserve `Stuck` through drain results and make abandonment sticky at the executor/recovery boundary. Ordinary reopen logic must not create unlimited replacements after this outcome.

**5. P2 — Converting timestamps to floats before subtracting breaks timeline parity.**  
[smtc/worker.rs:117](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:117), [smtc/mod.rs:187](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/mod.rs:187)

Python subtracts `timedelta` values before converting the difference to seconds. Rust converts each endpoint first.

Concrete examples:

| Start | End | Python duration | Rust duration |
|---|---|---:|---:|
| 11.001 s | 256.001 s | 245 | 244 |
| 0.001 s | 1.001 s | 1 | 0 |

The first Rust subtraction produces `244.99999999999997`; truncation loses a second. The second case disables the playback display because duration becomes zero. Position subtraction has the same defect.

**Fix:** Preserve integer timestamps through subtraction, accounting for the Python projection’s microsecond precision, then truncate and clamp. Do not fix this by rounding all durations: that would introduce other parity failures.

The existing extrapolation order itself is correct: truncate/clamp the base position, add truncated age only for `0 <= age < 600` while playing, then clamp to nonzero duration.

**6. P2 — Reading every app’s metadata introduces stalls and publishes old positions as fresh.**  
[smtc/worker.rs:146](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:146), [smtc/worker.rs:252](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:252)

Python ranks sessions first and fetches metadata/timeline only for the winner. Rust fetches them for every session—including stopped sessions—before choosing.

Concrete failure: Spotify is read first at position 100; an unrelated stopped app then takes 30 seconds to return metadata. The worker publishes Spotify’s old position and sets `updated = now`, so health reports it as fresh. If the unrelated operation never returns, Spotify disappears from all future updates despite remaining healthy.

**Fix:** Separate the exhaustive probe path from production polling. Rank lightweight session facts first, then fetch the winner. Carry the observation time with its timeline rather than treating publication time as observation time.

**7. P2 — Rust trimming differs from Python and can change row selection.**  
[smtc/worker.rs:158](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:158)

Python `strip()` removes U+001C–U+001F; Rust `trim()` does not. Python’s whitespace definition differs from Unicode `White_Space`. [Python’s definition](https://docs.python.org/3/library/stdtypes.html#str.isspace).

Concrete input: artist `"\x1f"`, title `"Track"`.

- Python: artist becomes empty; row 0 receives `Track`, row 1 is cleared.
- Rust: artist remains nonempty; row 0 receives `?`, row 1 receives `Track`.

This is outside the `to_ascii` fixture, so every folding test can pass.

**Fix:** Implement Python-compatible trimming before row selection—currently Rust whitespace plus U+001C–U+001F—and test metadata-to-report behavior.

**8. P2 — Folding parity is tied to an unpinned Python Unicode version, and the fixture conceals missing entries.**  
[scripts/gen_ascii_fold.py:100](C:/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:100), [scripts/gen_ascii_fold.py:193](C:/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:193)

The checked-in table uses Unicode 15.0 from Python 3.12.6. The macOS setup selects an available `python3`, without pinning this version.

Concrete failure: Python 3.14 uses Unicode 16, where U+1CCD6, OUTLINED LATIN CAPITAL LETTER A, folds to `A`. This Rust table drops it. A title containing it therefore produces different bytes across the producers. [Python 3.14 database](https://docs.python.org/3.14/library/unicodedata.html), [Unicode decomposition](https://www.unicode.org/charts/nameslist/n_1CC00.html).

The fixture imports the correct oracle, but chooses its exhaustive inputs from **the generated table’s entries**. Missing entries consequently remove their own test cases. Its few empty-output examples do not establish completeness.

**Fix:** Define the supported Unicode version across producers and enforce it. Verify the table against the oracle over every scalar, including absent keys, independently of the table’s selected corpus. Merely regenerating both files together does not solve the version contract.

**9. P2 — The apartment guard can safely move to the wrong thread.**  
[smtc/worker.rs:70](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:70)

`Apartment(())` automatically implements `Send` and `Sync`, but its destructor must balance initialization on the originating thread.

Concrete misuse permitted by the public safe API:

```rust
let apartment = Apartment::enter()?;
std::thread::spawn(move || drop(apartment)).join().unwrap();
```

This leaves the original thread’s initialization unbalanced and calls `RoUninitialize` on another thread. [Microsoft’s initialization contract](https://learn.microsoft.com/en-us/windows/win32/api/roapi/nf-roapi-roinitialize).

**Fix:** Make the guard explicitly thread-bound, for example with `PhantomData<Rc<()>>`. Current worker and probe usage stays on the correct thread; the exported type fails to enforce that requirement.

The deliberate unbounded `join()` deserves a qualified acceptance. Keeping one detached worker is a reasonable containment policy once findings 1–2 are addressed. **A lifetime-safe bounded completion wait is available in the pinned dependency:** `IAsyncOperation::when()` accepts an owned `Send + 'static` closure. It can send its result into a channel whose receiver uses `recv_timeout`; a late completion simply encounters a dropped receiver. The dependency’s `IntoFuture` implementation also keeps callback state in an `Arc`.

Neither approach bounds synchronous COM invocation, guarantees cancellation, or permits unlimited abandoned operations. Retain the separate worker and cap outstanding operations.

The remaining phase 0 rechecks:

- **Finding 1:** The hardware-field restriction fixes the supplied injection cases; the interface hint is also field-restricted.
- **Finding 3:** The concurrent edit now invokes `on_send` before writing, correcting the defect present when this review began. Building SET payloads after draining remains outstanding.
- **Finding 7:** Entry deadlines, zero-budget refusal and narrowing are corrected. The CLI still uses unchecked deadline addition at [ak820.rs:149](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:149); an extreme `watch` duration can panic. Its short-budget self-test also cannot infer “without transmitting” from `Timeout`, which can occur after transmission.
- **Deferred finding 5:** Text echo correlation is needed when these two-row batches start using the transport; it cannot all wait for phase 5 health decoding.

**The per-codepoint folding scheme itself is sound for a fixed Unicode version.** NFKD ordering moves nonzero-combining-class characters; surviving ASCII characters are starters and retain their order. The current substitutions are context-independent. [Unicode normalization rules](https://www.unicode.org/reports/tr15/). I found no additional defect in fold-before-truncate, the 19/21 budgets, padding, or playback byte order.

This was read-only. I inspected the sources, Python producers, firmware parser and pinned dependencies, and performed in-memory arithmetic and normalization checks. Process launching was blocked, so I could not run Rust/Python tests or hardware checks.
tokens used
197,058
**I found serious liveness issues and concrete parity failures. I would keep the phase 1 gate open.**

The transport changed during this review. References below reflect my final read at **11:28 UTC**; I rechecked the affected findings after the extraction into `hid/exchange.rs`.

**1. P1 — A failed session iteration can abort the entire release process.**  
[smtc/worker.rs:141](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:141), [Cargo.toml:56](C:/Users/jdlien/code/ak820-pro/ak820-agent/Cargo.toml:56)

`for session in sessions` invokes `IVectorView::into_iter()`. In the pinned `windows-collections` 0.3.2, that calls **`self.First().unwrap()`**.

Concrete failure: `GetSessions()` succeeds, but obtaining its iterator returns an error. That becomes a panic. With release `panic = "abort"`, the whole process terminates—including the future clock loop. With unwinding enabled, the detached worker instead dies permanently without recording the failure.

Subsequent iterator errors also silently terminate iteration, potentially publishing an incomplete session list as a successful poll.

**Fix:** Traverse using explicitly fallible `First`/`HasCurrent`/`Current`/`MoveNext`, or `Size`/`GetAt`, with a defined error policy. Exercise those failures through a fake. `catch_unwind` alone cannot protect the current release build.

**2. P1 — The shared mutex still allows a media-side stall to block the clock caller.**  
[smtc/worker.rs:218](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:218), [smtc/worker.rs:247](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:247)

The worker holds the mutex while running `e.to_string()` at line 261. This is not necessarily a local string operation: pinned `windows-result` retrieves error text through COM `QueryInterface`, `GetErrorDetails`, and potentially `GetDescription`. Dropping the error also releases its COM object inside that critical section.

Concrete failure: a returned error-info object blocks while supplying its description. The worker holds `state`; the scheduler calls `latest()`; its blocking `lock()` now parks the scheduler indefinitely. The separate thread has ceased to isolate the clock.

Snapshot construction also clones unrestricted metadata while holding this lock.

**Fix:** Construct snapshots, format errors, and release all WinRT objects **before** acquiring the publication lock. For the stated nonblocking caller contract, use a mailbox or `try_lock` with a caller-retained previous snapshot. Poison recovery via `into_inner()` is reasonable, but does not address blocking.

**3. P1 — Phase 0 finding 2 is only partly fixed: unanswered requests still contaminate later transactions.**  
[hid/exchange.rs:199](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:199)

The exhausted-drain refusal works. However, a timeout after transmission records no unresolved-request state.

The original single-owner counterexample still applies:

1. GET A is transmitted and times out.
2. GET B’s pre-drain observes an empty queue.
3. B is transmitted.
4. A’s delayed reply arrives and satisfies B’s channel/command matcher.

That assigns A’s board sample to B’s timestamps. Canceling A’s host read did not cancel its firmware command. Reopening alone cannot establish that no late broadcast remains.

**Fix:** Invalidate the logical clock transaction after an unanswered transmission and require an explicit resynchronization strategy before accepting indistinguishable replies again. A protocol nonce provides a stronger solution. Add the delayed-after-empty-drain case; the 33rd-queued-report test covers a different failure.

**4. P2 — The cancellation leak is bounded per handle, but recovery can accumulate abandoned handles.**  
[hid/device.rs:503](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:503), [hid/exchange.rs:115](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:115), [bin/ak820.rs:174](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:174)

The heap allocation and timeout branch preserve the pending operation’s storage. I found no concrete use-after-free in that path.

However, a stuck cancellation during pre-drain becomes `Queue::Unreadable`, losing `Error::Stuck`. `watch` then drops the device and opens another. If opens continue succeeding while reads cannot cancel, each cycle abandons another buffer, event, and device handle. The comment promising one process-lifetime leak is therefore unsupported.

**Fix:** Preserve `Stuck` through drain results and make abandonment sticky at the executor/recovery boundary. Ordinary reopen logic must not create unlimited replacements after this outcome.

**5. P2 — Converting timestamps to floats before subtracting breaks timeline parity.**  
[smtc/worker.rs:117](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:117), [smtc/mod.rs:187](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/mod.rs:187)

Python subtracts `timedelta` values before converting the difference to seconds. Rust converts each endpoint first.

Concrete examples:

| Start | End | Python duration | Rust duration |
|---|---|---:|---:|
| 11.001 s | 256.001 s | 245 | 244 |
| 0.001 s | 1.001 s | 1 | 0 |

The first Rust subtraction produces `244.99999999999997`; truncation loses a second. The second case disables the playback display because duration becomes zero. Position subtraction has the same defect.

**Fix:** Preserve integer timestamps through subtraction, accounting for the Python projection’s microsecond precision, then truncate and clamp. Do not fix this by rounding all durations: that would introduce other parity failures.

The existing extrapolation order itself is correct: truncate/clamp the base position, add truncated age only for `0 <= age < 600` while playing, then clamp to nonzero duration.

**6. P2 — Reading every app’s metadata introduces stalls and publishes old positions as fresh.**  
[smtc/worker.rs:146](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:146), [smtc/worker.rs:252](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:252)

Python ranks sessions first and fetches metadata/timeline only for the winner. Rust fetches them for every session—including stopped sessions—before choosing.

Concrete failure: Spotify is read first at position 100; an unrelated stopped app then takes 30 seconds to return metadata. The worker publishes Spotify’s old position and sets `updated = now`, so health reports it as fresh. If the unrelated operation never returns, Spotify disappears from all future updates despite remaining healthy.

**Fix:** Separate the exhaustive probe path from production polling. Rank lightweight session facts first, then fetch the winner. Carry the observation time with its timeline rather than treating publication time as observation time.

**7. P2 — Rust trimming differs from Python and can change row selection.**  
[smtc/worker.rs:158](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:158)

Python `strip()` removes U+001C–U+001F; Rust `trim()` does not. Python’s whitespace definition differs from Unicode `White_Space`. [Python’s definition](https://docs.python.org/3/library/stdtypes.html#str.isspace).

Concrete input: artist `"\x1f"`, title `"Track"`.

- Python: artist becomes empty; row 0 receives `Track`, row 1 is cleared.
- Rust: artist remains nonempty; row 0 receives `?`, row 1 receives `Track`.

This is outside the `to_ascii` fixture, so every folding test can pass.

**Fix:** Implement Python-compatible trimming before row selection—currently Rust whitespace plus U+001C–U+001F—and test metadata-to-report behavior.

**8. P2 — Folding parity is tied to an unpinned Python Unicode version, and the fixture conceals missing entries.**  
[scripts/gen_ascii_fold.py:100](C:/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:100), [scripts/gen_ascii_fold.py:193](C:/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:193)

The checked-in table uses Unicode 15.0 from Python 3.12.6. The macOS setup selects an available `python3`, without pinning this version.

Concrete failure: Python 3.14 uses Unicode 16, where U+1CCD6, OUTLINED LATIN CAPITAL LETTER A, folds to `A`. This Rust table drops it. A title containing it therefore produces different bytes across the producers. [Python 3.14 database](https://docs.python.org/3.14/library/unicodedata.html), [Unicode decomposition](https://www.unicode.org/charts/nameslist/n_1CC00.html).

The fixture imports the correct oracle, but chooses its exhaustive inputs from **the generated table’s entries**. Missing entries consequently remove their own test cases. Its few empty-output examples do not establish completeness.

**Fix:** Define the supported Unicode version across producers and enforce it. Verify the table against the oracle over every scalar, including absent keys, independently of the table’s selected corpus. Merely regenerating both files together does not solve the version contract.

**9. P2 — The apartment guard can safely move to the wrong thread.**  
[smtc/worker.rs:70](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:70)

`Apartment(())` automatically implements `Send` and `Sync`, but its destructor must balance initialization on the originating thread.

Concrete misuse permitted by the public safe API:

```rust
let apartment = Apartment::enter()?;
std::thread::spawn(move || drop(apartment)).join().unwrap();
```

This leaves the original thread’s initialization unbalanced and calls `RoUninitialize` on another thread. [Microsoft’s initialization contract](https://learn.microsoft.com/en-us/windows/win32/api/roapi/nf-roapi-roinitialize).

**Fix:** Make the guard explicitly thread-bound, for example with `PhantomData<Rc<()>>`. Current worker and probe usage stays on the correct thread; the exported type fails to enforce that requirement.

The deliberate unbounded `join()` deserves a qualified acceptance. Keeping one detached worker is a reasonable containment policy once findings 1–2 are addressed. **A lifetime-safe bounded completion wait is available in the pinned dependency:** `IAsyncOperation::when()` accepts an owned `Send + 'static` closure. It can send its result into a channel whose receiver uses `recv_timeout`; a late completion simply encounters a dropped receiver. The dependency’s `IntoFuture` implementation also keeps callback state in an `Arc`.

Neither approach bounds synchronous COM invocation, guarantees cancellation, or permits unlimited abandoned operations. Retain the separate worker and cap outstanding operations.

The remaining phase 0 rechecks:

- **Finding 1:** The hardware-field restriction fixes the supplied injection cases; the interface hint is also field-restricted.
- **Finding 3:** The concurrent edit now invokes `on_send` before writing, correcting the defect present when this review began. Building SET payloads after draining remains outstanding.
- **Finding 7:** Entry deadlines, zero-budget refusal and narrowing are corrected. The CLI still uses unchecked deadline addition at [ak820.rs:149](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:149); an extreme `watch` duration can panic. Its short-budget self-test also cannot infer “without transmitting” from `Timeout`, which can occur after transmission.
- **Deferred finding 5:** Text echo correlation is needed when these two-row batches start using the transport; it cannot all wait for phase 5 health decoding.

**The per-codepoint folding scheme itself is sound for a fixed Unicode version.** NFKD ordering moves nonzero-combining-class characters; surviving ASCII characters are starters and retain their order. The current substitutions are context-independent. [Unicode normalization rules](https://www.unicode.org/reports/tr15/). I found no additional defect in fold-before-truncate, the 19/21 budgets, padding, or playback byte order.

This was read-only. I inspected the sources, Python producers, firmware parser and pinned dependencies, and performed in-memory arithmetic and normalization checks. Process launching was blocked, so I could not run Rust/Python tests or hardware checks.

[exited with code 0]
