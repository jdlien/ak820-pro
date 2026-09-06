# Codex audit of ak820-agent phase 0 — 2026-09-06

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read (so it could also read `../jdrgb` and `../jdups`
and the pinned `windows` bindings). 138,113 tokens.

The first audit under the standing rule in
[AK820-AGENT-PLAN.md](AK820-AGENT-PLAN.md#every-phase-ends-with-an-external-audit).
It reviewed all of `ak820-agent/src/` at commit `ccbe9bd`.

**Verdict: the phase-0 gate is reopened.** Finding 1 was reproduced and fixed
immediately; the disposition of every finding is recorded in the plan under
"Phase 0 audit".

Verbatim below, from the `codex` final message.

---

**I found serious discovery and transaction-contract issues. I would reopen the phase-0 gate before building clock synchronization on this transport.** I did not find a concrete use-after-free in the current serialized transfer path.

**1. P1 — The path filter can select an unrelated device for opening.**  
[hid/path.rs:52](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/path.rs:52)

`matches_device()` searches the entire string. It never verifies the HID path structure or restricts the VID/PID comparison to the hardware-ID field, despite its documentation claiming both.

For example, this passes:

```text
\\?\HID#VID_051D&PID_0002#VID_0C45&PID_8009#{4d1e55b2-f16f-11cf-88cb-001111000030}
```

The hardware ID belongs to the UPS; the matching text appears in the instance field. `open_board()` will attempt to open it when no earlier candidate succeeds, and `list --caps` will attempt to open it regardless. Post-open attribute rejection happens after the forbidden operation.

**Fix:** Parse and validate the expected path structure, compare exact VID/PID tokens exclusively within its hardware-ID field, and reject unexpected forms. Apply the same field restriction to the `MI_01` hint. Add instance-field injection and malformed-prefix cases to the actual candidate-to-open boundary test.

**2. P1 — A capped drain leaves stale replies eligible to answer the next request.**  
[hid/device.rs:446](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:446), [hid/device.rs:413](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:413)

The input queue is configured for 64 reports, but pre-draining stops after 32. `drain()` does not distinguish reaching that limit from establishing an empty queue. `request()` then writes and accepts any remaining report with the matching channel and command.

Concrete scenario: 32 unrelated reports precede an old `RTC_GET_TIME` reply. The drain removes the first 32; the new GET is written; the old reply immediately satisfies it. Its old board sample receives the new request’s timestamps and can win minimum-RTT selection.

There is also a **single-owner** version: request A times out, request B’s pre-drain sees an empty queue, then A’s delayed reply arrives after B is written. Canceling the host read did not cancel the firmware command.

**Fix:** Return explicit drain outcomes—empty, limit reached, failed—and refuse to start a request when queue cleanliness is unresolved. After an unanswered command, invalidate the logical transaction and require an explicit resynchronization strategy before reusing indistinguishable replies. Closing and reopening can still receive a late broadcast reply. Test both the 33rd queued report and delayed completion after timeout.

**3. P1 for phases 2–3 — The API makes the documented clock timestamp placement impossible.**  
[hid/device.rs:375](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:375)

The comment says draining occurs outside the measured interval, but draining happens *inside* `request()`. A caller following the clock contract—`t0; request(GET); t1`—necessarily measures it. There is no timestamp callback or returned transport timestamp.

With an otherwise synchronized clock:

```text
t0 = 0 ms
drain finishes / GET sent = 6 ms
board sample = 8 ms
reply received = 10 ms
```

The caller calculates a midpoint of 5 ms and reports a false **+3 ms offset**. The correct transmission midpoint is 8 ms.

SET is worse: the caller must construct its timestamp-bearing body before entering `request()`, which subsequently drains. A 6 ms drain makes the encoded target approximately 6 ms stale before transmission.

**Fix:** Provide a prepared transaction API that completes draining first, then constructs timestamp-sensitive payloads and captures transmission timestamps immediately around I/O. Return the relevant timestamps with the reply. Put deterministic clock-placement tests around that API.

**4. P1 for daemon liveness — Cancellation has an unlimited completion wait.**  
[hid/device.rs:499](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:499)

After the initial wait expires, `CancelIoEx`’s result is ignored and `GetOverlappedResult(..., true)` waits indefinitely. Delayed cancellation exceeds every advertised budget; cancellation that never completes strands the executor permanently, including during the supposedly cheap pre-drain.

The ordinary cancellation path preserves buffer lifetime, but the comments claiming it cannot become an unbounded shutdown wait are unsupported. Microsoft explicitly states that cancellation is not guaranteed. [Cancellation contract](https://learn.microsoft.com/en-us/windows/win32/fileio/canceling-pending-i-o-operations).

**Fix:** Give cancellation completion a defined grace period and failure policy. To preserve responsiveness afterward, retain the entire pending operation—buffer, `OVERLAPPED`, event and device ownership—in stable owned storage or a bounded worker whose lifetime continues until completion. Report the executor as stuck and supervise recovery without accumulating stranded workers. Returning and freeing the current stack state would introduce the use-after-free this implementation currently avoids.

**5. P2 — Correlation ignores request fields that the firmware actually echoes.**  
[proto.rs:165](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/proto.rs:165)

The matcher sees only channel and command. It cannot distinguish:

- `TEXT_SET_LINE` for line 0 from an echo for line 1 or different text.
- `HC_RTC` page 1 from page 2; the firmware preserves the requested page in byte 3.

If such a foreign or delayed reply arrives first, `request()` returns success immediately. A health decoder can consequently interpret another page’s bytes using the requested page’s layout. Rejecting it afterward loses the opportunity to continue waiting inside this request.

**Fix:** Let each command supply a reply-matching policy. Compare the echoed payload for text and the page selector for paged health requests, and drain mismatches. Clock GET still requires enforced ownership because its replies lack an equivalent discriminator.

**6. P2 — Discovery discards the error needed to classify presence correctly.**  
[hid/device.rs:349](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:349), [hid/device.rs:306](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:306)

`open_board()` overwrites every failure with the next collection’s failure.

For example: opening raw HID fails with `ERROR_SHARING_VIOLATION`; subsequent keyboard collections fail with `ERROR_ACCESS_DENIED`. The caller receives only the final keyboard error and path. A raw-interface disconnect or capability rejection can likewise disappear behind an unrelated collection’s failure.

Additionally, `identify()` converts attribute/preparsed-data failures into `None`, losing their OS errors and ultimately reporting `Incompatible::Silent`. A device disappearing during identification therefore looks incompatible.

**Fix:** Preserve candidate-specific errors and identify which belongs to the raw interface. Prefer identifying board collections with access zero before requesting read/write access, while preserving identification errors. Return structured outcomes that retain busy, disconnect and incompatible distinctions.

**7. P2 — The “whole request” budget starts after an unconditional write.**  
[hid/device.rs:386](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:386)

The deadline is created only after draining and a write with its independent 1,000 ms timeout. Thus:

- A zero budget still transmits the command, then returns `Timeout` without reading.
- A 1 ms budget can spend nearly a second writing before its receive budget starts.
- An unrepresentable duration panics at `Instant::now() + budget`, after transmission.

This becomes consequential when a scheduler passes its remaining time to a state-changing text or clock operation: an expired operation can still modify the board.

The millisecond conversion also narrows to `u32` before clamping, wrapping sufficiently large durations.

**Fix:** Define and enforce the budget at entry, check it before transmission, and use the remaining allowance for each stage. Use checked deadline arithmetic and clamp before narrowing. Apply checked arithmetic to [the CLI watch deadline](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:147) too. Cancellation cleanup requires the separate policy in finding 4.

**8. P2 — Two-board refusal depends on repeated interface strings, rather than physical board identity.**  
[hid/path.rs:92](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/path.rs:92)

`duplicate_interfaces()` detects repeated hardware-ID fields. Two complete keyboards with the tested identical layout are covered; two physical keyboards with disjoint currently present interface fields are not.

For example, during partial enumeration with differing firmware layouts, the candidate list can contain only board A’s `...&MI_01#instanceA#...` and board B’s `...&MI_00#instanceB#...`. Both match, no duplicate is reported, and `open_board()` chooses the first acceptable collection.

**Fix:** Group candidates by physical USB parent using Configuration Manager metadata and refuse multiple parents before opening. Container identity can assist grouping multifunction devices. [Windows USB container identity](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usb-containerids-in-windows). Test partial presence and differing layouts, not just a duplicated `MI_01`.

**9. P2 — The cancellation self-test can pass without proving its claimed branches.**  
[bin/ak820.rs:229](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:229), [hid/device.rs:558](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:558)

A successful short-budget request is labeled as completion before cancellation landed, but the reply may already be queued when `ReadFile` starts. That exercises ordinary completion without cancellation.

The “idle cancel” step also cannot establish its claimed branch: `drain()` can stop on a swallowed error or after 32 completed reads. Neither proves an aborted pending read. Comparing identical `FC_INFO` answers afterward cannot establish reply freshness or detect every lifetime violation.

Of the 49 tests, the two in `hid/device.rs` check frame length and CM listing. None deterministically exercises the request loop or completion/cancellation transitions. The listing test also passes on any `Discovery` error, so a completely broken listing implementation can pass it.

**Fix:** Instrument actual pending/wait/cancel/completion outcomes and require the self-test to report which branches it observed. Add a fake I/O backend and clock covering cancellation races, failed cancellation, delayed completion, drain exhaustion, late same-command replies, foreign-report floods, short transfers and deadline boundaries. Count pending operations and resource ownership through failure paths.

Before clock integration, the ownership boundary should encompass opening, preparation, all measurement GETs, SET and verification. `Device: Send` and its current lack of `Sync` do not prevent separate handles or processes. The named ownership guard and CLI coordination must precede clock use; the SMTC worker should publish snapshots to that owner without independently opening HID.

This was read-only. I inspected the requested documents, all crate sources, both sibling transports and the pinned Windows bindings. Process launching is blocked in this session, so I could not run Rust tests or hardware checks.
tokens used
138,113
**I found serious discovery and transaction-contract issues. I would reopen the phase-0 gate before building clock synchronization on this transport.** I did not find a concrete use-after-free in the current serialized transfer path.

**1. P1 — The path filter can select an unrelated device for opening.**  
[hid/path.rs:52](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/path.rs:52)

`matches_device()` searches the entire string. It never verifies the HID path structure or restricts the VID/PID comparison to the hardware-ID field, despite its documentation claiming both.

For example, this passes:

```text
\\?\HID#VID_051D&PID_0002#VID_0C45&PID_8009#{4d1e55b2-f16f-11cf-88cb-001111000030}
```

The hardware ID belongs to the UPS; the matching text appears in the instance field. `open_board()` will attempt to open it when no earlier candidate succeeds, and `list --caps` will attempt to open it regardless. Post-open attribute rejection happens after the forbidden operation.

**Fix:** Parse and validate the expected path structure, compare exact VID/PID tokens exclusively within its hardware-ID field, and reject unexpected forms. Apply the same field restriction to the `MI_01` hint. Add instance-field injection and malformed-prefix cases to the actual candidate-to-open boundary test.

**2. P1 — A capped drain leaves stale replies eligible to answer the next request.**  
[hid/device.rs:446](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:446), [hid/device.rs:413](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:413)

The input queue is configured for 64 reports, but pre-draining stops after 32. `drain()` does not distinguish reaching that limit from establishing an empty queue. `request()` then writes and accepts any remaining report with the matching channel and command.

Concrete scenario: 32 unrelated reports precede an old `RTC_GET_TIME` reply. The drain removes the first 32; the new GET is written; the old reply immediately satisfies it. Its old board sample receives the new request’s timestamps and can win minimum-RTT selection.

There is also a **single-owner** version: request A times out, request B’s pre-drain sees an empty queue, then A’s delayed reply arrives after B is written. Canceling the host read did not cancel the firmware command.

**Fix:** Return explicit drain outcomes—empty, limit reached, failed—and refuse to start a request when queue cleanliness is unresolved. After an unanswered command, invalidate the logical transaction and require an explicit resynchronization strategy before reusing indistinguishable replies. Closing and reopening can still receive a late broadcast reply. Test both the 33rd queued report and delayed completion after timeout.

**3. P1 for phases 2–3 — The API makes the documented clock timestamp placement impossible.**  
[hid/device.rs:375](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:375)

The comment says draining occurs outside the measured interval, but draining happens *inside* `request()`. A caller following the clock contract—`t0; request(GET); t1`—necessarily measures it. There is no timestamp callback or returned transport timestamp.

With an otherwise synchronized clock:

```text
t0 = 0 ms
drain finishes / GET sent = 6 ms
board sample = 8 ms
reply received = 10 ms
```

The caller calculates a midpoint of 5 ms and reports a false **+3 ms offset**. The correct transmission midpoint is 8 ms.

SET is worse: the caller must construct its timestamp-bearing body before entering `request()`, which subsequently drains. A 6 ms drain makes the encoded target approximately 6 ms stale before transmission.

**Fix:** Provide a prepared transaction API that completes draining first, then constructs timestamp-sensitive payloads and captures transmission timestamps immediately around I/O. Return the relevant timestamps with the reply. Put deterministic clock-placement tests around that API.

**4. P1 for daemon liveness — Cancellation has an unlimited completion wait.**  
[hid/device.rs:499](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:499)

After the initial wait expires, `CancelIoEx`’s result is ignored and `GetOverlappedResult(..., true)` waits indefinitely. Delayed cancellation exceeds every advertised budget; cancellation that never completes strands the executor permanently, including during the supposedly cheap pre-drain.

The ordinary cancellation path preserves buffer lifetime, but the comments claiming it cannot become an unbounded shutdown wait are unsupported. Microsoft explicitly states that cancellation is not guaranteed. [Cancellation contract](https://learn.microsoft.com/en-us/windows/win32/fileio/canceling-pending-i-o-operations).

**Fix:** Give cancellation completion a defined grace period and failure policy. To preserve responsiveness afterward, retain the entire pending operation—buffer, `OVERLAPPED`, event and device ownership—in stable owned storage or a bounded worker whose lifetime continues until completion. Report the executor as stuck and supervise recovery without accumulating stranded workers. Returning and freeing the current stack state would introduce the use-after-free this implementation currently avoids.

**5. P2 — Correlation ignores request fields that the firmware actually echoes.**  
[proto.rs:165](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/proto.rs:165)

The matcher sees only channel and command. It cannot distinguish:

- `TEXT_SET_LINE` for line 0 from an echo for line 1 or different text.
- `HC_RTC` page 1 from page 2; the firmware preserves the requested page in byte 3.

If such a foreign or delayed reply arrives first, `request()` returns success immediately. A health decoder can consequently interpret another page’s bytes using the requested page’s layout. Rejecting it afterward loses the opportunity to continue waiting inside this request.

**Fix:** Let each command supply a reply-matching policy. Compare the echoed payload for text and the page selector for paged health requests, and drain mismatches. Clock GET still requires enforced ownership because its replies lack an equivalent discriminator.

**6. P2 — Discovery discards the error needed to classify presence correctly.**  
[hid/device.rs:349](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:349), [hid/device.rs:306](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:306)

`open_board()` overwrites every failure with the next collection’s failure.

For example: opening raw HID fails with `ERROR_SHARING_VIOLATION`; subsequent keyboard collections fail with `ERROR_ACCESS_DENIED`. The caller receives only the final keyboard error and path. A raw-interface disconnect or capability rejection can likewise disappear behind an unrelated collection’s failure.

Additionally, `identify()` converts attribute/preparsed-data failures into `None`, losing their OS errors and ultimately reporting `Incompatible::Silent`. A device disappearing during identification therefore looks incompatible.

**Fix:** Preserve candidate-specific errors and identify which belongs to the raw interface. Prefer identifying board collections with access zero before requesting read/write access, while preserving identification errors. Return structured outcomes that retain busy, disconnect and incompatible distinctions.

**7. P2 — The “whole request” budget starts after an unconditional write.**  
[hid/device.rs:386](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:386)

The deadline is created only after draining and a write with its independent 1,000 ms timeout. Thus:

- A zero budget still transmits the command, then returns `Timeout` without reading.
- A 1 ms budget can spend nearly a second writing before its receive budget starts.
- An unrepresentable duration panics at `Instant::now() + budget`, after transmission.

This becomes consequential when a scheduler passes its remaining time to a state-changing text or clock operation: an expired operation can still modify the board.

The millisecond conversion also narrows to `u32` before clamping, wrapping sufficiently large durations.

**Fix:** Define and enforce the budget at entry, check it before transmission, and use the remaining allowance for each stage. Use checked deadline arithmetic and clamp before narrowing. Apply checked arithmetic to [the CLI watch deadline](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:147) too. Cancellation cleanup requires the separate policy in finding 4.

**8. P2 — Two-board refusal depends on repeated interface strings, rather than physical board identity.**  
[hid/path.rs:92](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/path.rs:92)

`duplicate_interfaces()` detects repeated hardware-ID fields. Two complete keyboards with the tested identical layout are covered; two physical keyboards with disjoint currently present interface fields are not.

For example, during partial enumeration with differing firmware layouts, the candidate list can contain only board A’s `...&MI_01#instanceA#...` and board B’s `...&MI_00#instanceB#...`. Both match, no duplicate is reported, and `open_board()` chooses the first acceptable collection.

**Fix:** Group candidates by physical USB parent using Configuration Manager metadata and refuse multiple parents before opening. Container identity can assist grouping multifunction devices. [Windows USB container identity](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usb-containerids-in-windows). Test partial presence and differing layouts, not just a duplicated `MI_01`.

**9. P2 — The cancellation self-test can pass without proving its claimed branches.**  
[bin/ak820.rs:229](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:229), [hid/device.rs:558](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:558)

A successful short-budget request is labeled as completion before cancellation landed, but the reply may already be queued when `ReadFile` starts. That exercises ordinary completion without cancellation.

The “idle cancel” step also cannot establish its claimed branch: `drain()` can stop on a swallowed error or after 32 completed reads. Neither proves an aborted pending read. Comparing identical `FC_INFO` answers afterward cannot establish reply freshness or detect every lifetime violation.

Of the 49 tests, the two in `hid/device.rs` check frame length and CM listing. None deterministically exercises the request loop or completion/cancellation transitions. The listing test also passes on any `Discovery` error, so a completely broken listing implementation can pass it.

**Fix:** Instrument actual pending/wait/cancel/completion outcomes and require the self-test to report which branches it observed. Add a fake I/O backend and clock covering cancellation races, failed cancellation, delayed completion, drain exhaustion, late same-command replies, foreign-report floods, short transfers and deadline boundaries. Count pending operations and resource ownership through failure paths.

Before clock integration, the ownership boundary should encompass opening, preparation, all measurement GETs, SET and verification. `Device: Send` and its current lack of `Sync` do not prevent separate handles or processes. The named ownership guard and CLI coordination must precede clock use; the SMTC worker should publish snapshots to that owner without independently opening HID.

This was read-only. I inspected the requested documents, all crate sources, both sibling transports and the pinned Windows bindings. Process launching is blocked in this session, so I could not run Rust tests or hardware checks.

[exited with code 0]
