# Codex audit of ak820-agent phase 2 — 2026-09-06

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read. Two runs on one session
(`01a076c7-a375-7442-b639-cae91dd60f0d`):

1. Launched 06:53 local against commit `cb42eb8`. Stopped after ~109k tokens
   on the owner's Codex usage limit, mid-review, having reported that the
   normal-path arithmetic and packet layout match the C and named three
   boundaries to check next.
2. Resumed with `codex exec resume <id>` after the owner reset the limit,
   against commit `9cee322` (which added the `Outstanding` fix, `7184dd3`),
   told which files had changed. It finished: seven findings and three
   corrections, ~208k tokens in all. **This is the report that counts.**

As in phase 1, its shell could not start (`CreateProcessAsUserW failed`), so it
worked from file reads, executable import tables (which is how it found that
`ak820ctl.exe` links `msvcrt.dll!_localtime64`) and in-memory arithmetic. It
did not run the Rust tests or touch HID.

Disposition of every finding: `AK820-AGENT-PLAN.md`, "Phase 2 audit —
disposition". Note for the next re-run: codex writes its final message to
**stderr** in this configuration; capture both streams.

## The final report (run 2, verbatim)

**I would keep the phase-2 gate open. One P1 remains: the new CLI clock reader can corrupt the running timekeeper’s measurements.** The revised outstanding-command set fixes the earlier overwrite bug.

This review reflects HEAD **9cee322**, including **7184dd3**, against C **7f92889f**. It was read-only. Process launching was blocked; I inspected sources, existing executable imports, and cache bytes, and checked arithmetic in memory. I did not run Rust tests or access HID.

**1. P1 — The diagnostic clock read can contaminate the active clock writer.**  
[ak820.rs:155](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:155), [ak820.rs:169](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:169)

`clock()` opens another shared handle and sends GET without establishing ownership.

Concrete sequence: the Python/C timekeeper is awaiting a measurement GET; the CLI’s GET reply reaches its handle first. The timekeeper accepts that well-formed reply, pairs the CLI’s board sample with its own timestamps, and can select it as the minimum-RTT sample. That affects its SET and learners.

The comment describes the consequence as a wrong diagnostic number. **The interference is bidirectional:** the diagnostic can corrupt the process that writes the clock and cache. The parity document already correctly describes this at [CLOCK-PARITY.md:179](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-CLOCK-PARITY.md:179).

The CLI exposes no SET, which is sound, but that alone does not protect ownership. Route reads through the owner, or enforce exclusive clock operation before issuing them. A mutex used only by Rust would not coordinate the installed Python/C agent.

**2. P2 — Negative board seconds-of-day are accepted where C reports an unset reading.**  
[transaction.rs:167](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:167), [clock/mod.rs:213](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/mod.rs:213)

Concrete GET fields:

```text
set=1, proto=2, time=00:00:00
cnt=100, active_period=33422, nominal_period=32767
```

The shared fraction formula produces `board_sod = -0.016937255859375`.

- C’s [get_offset:286](C:/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:286) returns `-2` whenever `b < 0`.
- Rust checks only the set flag and creates a sample. With host midpoint `0.005`, it reports **−21.9 ms**.

This is reachable during a slowing slew: [rtc.c:467](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:467) can program an active period longer than nominal. Immediately after midnight, its negative fraction makes the total negative.

Consequences include different measurement counts, selection, uncertainty, and CLI output/exit status. Preserve the C’s `b < 0` check when producing the measurement. The current captured fixtures and shortened-period test do not cover this case.

**3. P2 — Preparation can consume the deadline, but the command still transmits.**  
[exchange.rs:333](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:333), [exchange.rs:346](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:346)

`left` is calculated **before** `prepare`, then reused for writing without another deadline check.

Concrete input: a clean fake wire, a 20 ms budget, and a preparation callback that takes 50 ms. Expected under the documented expired-operation contract: no transmission. Actual: the frame is written after expiration, using the old allowance; collection subsequently times out.

The production SET callback also performs `host.local()` and allocation after `t_enc`; the transport adds framing, debt bookkeeping, buffer allocation/copying, and event reset before `WriteFile`. I found no explicit sleep or retry there, but the interim disposition does not establish a bounded interval.

Recheck the deadline after preparation and before transmission, and define the preparation callback’s timing contract. The existing preparation test proves ordering only.

**4. P2 — Verify failures lose the structured error the scheduler needs.**  
[transaction.rs:230](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:230), [transaction.rs:396](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:396)

Concrete input: measurement and SET succeed, then verification returns `hid::Error::Stuck`.

`run()` returns `Ok(Outcome)` and converts `Stuck` to a string. The caller cannot match the permanent-abandonment condition through the result’s type, although this condition explicitly requires different recovery from an ordinary timeout.

Likewise, reports discarded during a failed verify remain outside `Outcome.drained`; reports accumulated by successful earlier requests disappear entirely when a later measurement or SET returns an error.

Keep failed verification nonfatal for C/Python parity, but retain its typed error and transaction-wide discard accounting. That lets phase 3 preserve the success semantics while handling transport recovery correctly.

**5. P3 — The cache fixtures prove normalized text parity, not identical Windows file bytes.**  
[cache.rs:329](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/cache.rs:329), [clock_oracle.c:74](C:/Users/jdlien/code/ak820-pro/scripts/clock_oracle.c:74)

For `{ proto: 2, lead: 2.354, bias: -25 }`:

- Windows C/Python write `2 2.354 -25\r\n`.
- Rust writes `2 2.354 -25\n`.

The installed cache I read ended in bytes **`0D 0A`**. The harness reads its saved file back using `"r"`, which translates CRLF to LF before constructing the fixture. That translation is documented by [Microsoft’s text-mode contract](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/fopen-wfopen?view=msvc-170).

All three parsers tolerate the difference, so I found no functional interoperability failure here. Nevertheless, the byte-for-byte claim is false. Compare raw file bytes, or declare newline normalization an intentional divergence.

**6. P3 — The localtime sweep compares against a different CRT from the installed oracle.**  
[host.rs:272](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/host.rs:272), [host.rs:294](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/host.rs:294)

I inspected the existing executables’ import tables:

- `ak820ctl.exe`: **`msvcrt.dll!_localtime64`**
- Rust’s clock test executable: **`api-ms-win-crt-time-l1-1-0.dll!_localtime64_s`**

The sweep is useful evidence of Win32/UCRT agreement on this machine’s zone. It does **not** directly establish agreement with the installed mingw oracle.

I found no demonstrated localtime discrepancy within the supported years and stated no-`TZ` environment. Extend the mingw harness to produce localtime results before describing this as an oracle sweep.

**7. P3 — Minimum-RTT selection still omits C’s `1e9` sentinel behavior.**  
[clock/mod.rs:313](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/mod.rs:313), [transaction.rs:258](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:258)

For one good sample with `offset_ms=123` and `rtt_ms=1e9`:

- C leaves `best_off=0`, because `rtt < rtt_min` is false, and prints the verify RTT.
- Rust selects that sample, reports `before=123`, and prints its `1e9` RTT.

This requires an extreme wall-clock discontinuity or suspension, so it is low priority. It remains an undeclared arithmetic divergence despite the corrected `rtt_max` initialization.

There are also three small documentation/test corrections:

- [PLAN.md:742](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-PLAN.md:742) says the cache is unwritten in every listed failure case. A failed verify **does save it**, correctly; [transaction.rs:925](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:925) explicitly asserts that.
- [transaction.rs:333](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:333) promises at most seven requests. A successful `0xFE` retry makes **eight**.
- [exchange.rs:901](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:901), `the_same_lost_command_is_one_debt`, clears all debts between its two losses. It would pass without `note()`’s deduplication check. The implementation itself deduplicates correctly.

What I verified and found sound:

- Revised debts survive unrelated successes and subsequent lost commands; identical requests are refused before preparation/transmission.
- GET/SET framing, complete-report checks, foreign-command rejection, status-tail offsets and signed fields.
- Fraction arithmetic, nominal-zero fallback, ordinary midnight wrap, ordinary min-RTT selection, and corrected negative-RTT maximum initialization.
- SET truncation, millisecond clamp, flags, bias byte order, **`0x7FFF`**, and fresh timestamp on the single `0xFE` retry.
- Lead sign, gain, clamps and gates; finite-value printed rounding and Python-facing `as_reported()` behavior.
- Cache parsing for normal C/Python-produced content, range handling, and temporary-file replacement under single-writer operation.
- Host conversion storage and pointer lifetimes; epoch arithmetic within supported years. Arbitrary extreme `i64` inputs remain unchecked and can overflow or panic.
- No new HID enumeration mechanism, and no CLI route to RTC SET.
- No concrete new cancellation-buffer lifetime defect found.

## The prompt given to run 1

```text
You are auditing phase 2 of `ak820-agent/` in this repository (C:\Users\jdlien\code\ak820-pro), a Rust port of two Python host agents for an AJAZZ AK820 Pro keyboard. This is the third audit under a standing rule: a phase is done when its gate passes AND an independent model has read the code. The previous two audits (plans/review-codex-phase0-2026-09-06.md, plans/review-codex-phase1-2026-09-06.md) each found real P1 bugs, including doc comments asserting properties the code did not have. Read-only; do not modify anything.

SCOPE — new or changed in this phase (commit HEAD, "ak820-agent: the clock transaction, with the C as its own oracle"):
- ak820-agent/src/clock/mod.rs (GET decode incl. the status tail, fraction formula, wrap_day, min-RTT select, and read_lines: the `ak820ctl clock --read` rendering)
- ak820-agent/src/clock/cache.rs (the shared `$HOME/.ak820ctl-cap` file: an fscanf("%d %lf %d") emulation and the "%d %.3f %d" writer)
- ak820-agent/src/clock/set.rs (the RTC_SET_TIME_MS packet and reply)
- ak820-agent/src/clock/lead.rs (the outbound-lead learner)
- ak820-agent/src/clock/host.rs (a Host trait: wall clock + localtime; SystemHost over GetSystemTimePreciseAsFileTime and SystemTimeToTzSpecificLocalTime; a FakeHost)
- ak820-agent/src/clock/transaction.rs (the whole of `ak820ctl clock`: measure, set with 0xFE retry, learn, cache, verify, the reported line, and Outcome::as_reported())
- ak820-agent/src/hid/exchange.rs (new exchange_prepared: body built after the pre-drain, immediately before the write; the scripted Fake promoted to a shared `fake` module)
- ak820-agent/src/hid/device.rs (request_prepared, outstanding())
- ak820-agent/src/bin/ak820.rs (the read-only `clock [--raw]` command)
- scripts/clock_oracle.c (the pinned C functions copied verbatim, compiled with mingw64 gcc, generating the fixtures and a `decode` mode)

THE ORACLE the port must match, and the docs that transcribe it:
- time-util-ak820pro/ak820ctl.c at git 7f92889f: cap_load, cap_save, now_s, host_sod, board_sod, wrap_day, get_offset, send_set_ms, cmd_clock, cmd_clock_read
- hostagent/ak820-timekeeper.py: sync(), cap_read(), cap_write_bias(), read_status() — what Python parses from the C's output
- plans/AK820-AGENT-CLOCK-TRANSACTION.md (the transcription, with a new "Port status" section mapping the eight proof items to tests and listing deliberate divergences)
- plans/AK820-AGENT-CLOCK-PARITY.md (the Python scheduler; NOT ported yet, but the transaction must give it what it needs)
- plans/AK820-AGENT-PLAN.md — read "Phase 2 evidence (2026-09-06)" and the two earlier audit dispositions
- the firmware side: qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c (rtc_ms_payload_valid, rtc_set_ms_command, rtc_read_into) and rtc/rtc.c rtc_status_fill page 1 for the reply layout

LOAD-BEARING CONSTRAINTS — test these rather than rediscover them:
1. Never enumerate HID (hid_enumerate opens every device on the machine and wedged a UPS here). Nothing in this phase may add an open of anything but the board's own raw-HID interface.
2. Validate every read against the request that asked for it: Windows delivers HID input reports to every open handle. Foreign reports must be drained and never taken as an answer.
3. Correlation is NOT sufficient for the clock: a foreign RTC_GET_TIME reply is well-formed. Single ownership is what makes the clock correct. The port must not introduce anything that pretends otherwise, and the CLI must not be able to write to the board.
4. A transmitted-but-unanswered command blocks the next identical one until an explicit resynchronise (Outstanding). The transaction inherits this; check the interaction (e.g. a timed-out GET mid-burst, a timed-out verify).
5. CancelIoEx lifetimes: buffers and OVERLAPPED must outlive a cancelled transfer (unchanged this phase, but host.rs adds new unsafe Win32 calls — check them).
6. The SET packet's timestamp must be taken after the pre-drain and immediately before the write (exchange_prepared). Check that nothing between t_enc and the write can add unbounded time.
7. The cache file is shared with the installed ak820ctl (C) and the Python timekeeper: parse and format must round-trip identically on every file either of them writes. The fixtures were generated by running the C's own functions through the CRT.
8. Python parses the printed line: `before` to ONE decimal (compared against 60 and 400), and `slewing = "(slewing)" in out and "warning:" not in out`. Outcome::as_reported() must reproduce exactly that.
9. 0x7FFF is the unknown-bias sentinel, not zero.
10. `%+.1f`, `%.1f`, `%.2f`, `%.3f` rounding must match the CRT (ties to even on exact binary ties); the tests pin CRT output.

WHAT TO LOOK FOR, in priority order:
- Parity defects: any reachable input on which the port's decision, bytes, cache contents or printed text differ from the C (or from the Python's reading of the C's output), other than the divergences the docs declare deliberately. Check the arithmetic expression by expression (fraction formula, midpoint, wrap_day, U, the lead learner's gates and clamps, split_target's truncation, the ms clamp, the year byte, the flags byte, the bias bytes).
- Doc comments or docs asserting a property the code does not have (the previous audits' most valuable finding class).
- Tests that could pass while the property they name is broken (e.g. a fixture that tests the code against itself, a tolerance that hides a real error, an assertion on the wrong byte).
- host.rs: correctness of the FILETIME/SYSTEMTIME conversions, negative/large inputs, the now() arithmetic, and whether the CRT-parity test is sound (it links _localtime64_s from the MSVC CRT while ak820ctl is mingw-built).
- cache.rs: the fscanf emulation on inputs the C or Python actually write, saturation, whitespace, the atomic save.
- transaction.rs: the order of operations vs cmd_clock; error paths; what Outstanding is left holding after each failure; what `drained` accumulates; anything that could panic in a daemon built with panic=abort.
- The CLI `clock` command: confirm it cannot write anything but RTC_GET_TIME.
- Anything missing that the phase-3 scheduler will need from the transaction and cannot get.

Be concrete: file, line, the input, the expected vs actual behaviour. Rank P1/P2/P3. If you find nothing serious, say so plainly — an audit that always produces findings is one that invents them. You may compare against ../jdrgb and ../jdups (same author's prior Win32 HID code) if useful. End with a short list of what you verified and found sound, so the disposition can record it.
```

## Run 1 transcript (stderr, verbatim; stopped on the usage limit)

```text
Reading additional input from stdin...
OpenAI Codex v0.153.4
--------
workdir: C:\Users\jdlien\code\ak820-pro
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: xhigh
reasoning summaries: none
session id: 01a076c7-a375-7442-b639-cae91dd60f0d
--------
user
You are auditing phase 2 of `ak820-agent/` in this repository (C:\Users\jdlien\code\ak820-pro), a Rust port of two Python host agents for an AJAZZ AK820 Pro keyboard. This is the third audit under a standing rule: a phase is done when its gate passes AND an independent model has read the code. The previous two audits (plans/review-codex-phase0-2026-09-06.md, plans/review-codex-phase1-2026-09-06.md) each found real P1 bugs, including doc comments asserting properties the code did not have. Read-only; do not modify anything.

SCOPE — new or changed in this phase (commit HEAD, "ak820-agent: the clock transaction, with the C as its own oracle"):
- ak820-agent/src/clock/mod.rs (GET decode incl. the status tail, fraction formula, wrap_day, min-RTT select, and read_lines: the `ak820ctl clock --read` rendering)
- ak820-agent/src/clock/cache.rs (the shared `$HOME/.ak820ctl-cap` file: an fscanf("%d %lf %d") emulation and the "%d %.3f %d" writer)
- ak820-agent/src/clock/set.rs (the RTC_SET_TIME_MS packet and reply)
- ak820-agent/src/clock/lead.rs (the outbound-lead learner)
- ak820-agent/src/clock/host.rs (a Host trait: wall clock + localtime; SystemHost over GetSystemTimePreciseAsFileTime and SystemTimeToTzSpecificLocalTime; a FakeHost)
- ak820-agent/src/clock/transaction.rs (the whole of `ak820ctl clock`: measure, set with 0xFE retry, learn, cache, verify, the reported line, and Outcome::as_reported())
- ak820-agent/src/hid/exchange.rs (new exchange_prepared: body built after the pre-drain, immediately before the write; the scripted Fake promoted to a shared `fake` module)
- ak820-agent/src/hid/device.rs (request_prepared, outstanding())
- ak820-agent/src/bin/ak820.rs (the read-only `clock [--raw]` command)
- scripts/clock_oracle.c (the pinned C functions copied verbatim, compiled with mingw64 gcc, generating the fixtures and a `decode` mode)

THE ORACLE the port must match, and the docs that transcribe it:
- time-util-ak820pro/ak820ctl.c at git 7f92889f: cap_load, cap_save, now_s, host_sod, board_sod, wrap_day, get_offset, send_set_ms, cmd_clock, cmd_clock_read
- hostagent/ak820-timekeeper.py: sync(), cap_read(), cap_write_bias(), read_status() — what Python parses from the C's output
- plans/AK820-AGENT-CLOCK-TRANSACTION.md (the transcription, with a new "Port status" section mapping the eight proof items to tests and listing deliberate divergences)
- plans/AK820-AGENT-CLOCK-PARITY.md (the Python scheduler; NOT ported yet, but the transaction must give it what it needs)
- plans/AK820-AGENT-PLAN.md — read "Phase 2 evidence (2026-09-06)" and the two earlier audit dispositions
- the firmware side: qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c (rtc_ms_payload_valid, rtc_set_ms_command, rtc_read_into) and rtc/rtc.c rtc_status_fill page 1 for the reply layout

LOAD-BEARING CONSTRAINTS — test these rather than rediscover them:
1. Never enumerate HID (hid_enumerate opens every device on the machine and wedged a UPS here). Nothing in this phase may add an open of anything but the board's own raw-HID interface.
2. Validate every read against the request that asked for it: Windows delivers HID input reports to every open handle. Foreign reports must be drained and never taken as an answer.
3. Correlation is NOT sufficient for the clock: a foreign RTC_GET_TIME reply is well-formed. Single ownership is what makes the clock correct. The port must not introduce anything that pretends otherwise, and the CLI must not be able to write to the board.
4. A transmitted-but-unanswered command blocks the next identical one until an explicit resynchronise (Outstanding). The transaction inherits this; check the interaction (e.g. a timed-out GET mid-burst, a timed-out verify).
5. CancelIoEx lifetimes: buffers and OVERLAPPED must outlive a cancelled transfer (unchanged this phase, but host.rs adds new unsafe Win32 calls — check them).
6. The SET packet's timestamp must be taken after the pre-drain and immediately before the write (exchange_prepared). Check that nothing between t_enc and the write can add unbounded time.
7. The cache file is shared with the installed ak820ctl (C) and the Python timekeeper: parse and format must round-trip identically on every file either of them writes. The fixtures were generated by running the C's own functions through the CRT.
8. Python parses the printed line: `before` to ONE decimal (compared against 60 and 400), and `slewing = "(slewing)" in out and "warning:" not in out`. Outcome::as_reported() must reproduce exactly that.
9. 0x7FFF is the unknown-bias sentinel, not zero.
10. `%+.1f`, `%.1f`, `%.2f`, `%.3f` rounding must match the CRT (ties to even on exact binary ties); the tests pin CRT output.

WHAT TO LOOK FOR, in priority order:
- Parity defects: any reachable input on which the port's decision, bytes, cache contents or printed text differ from the C (or from the Python's reading of the C's output), other than the divergences the docs declare deliberately. Check the arithmetic expression by expression (fraction formula, midpoint, wrap_day, U, the lead learner's gates and clamps, split_target's truncation, the ms clamp, the year byte, the flags byte, the bias bytes).
- Doc comments or docs asserting a property the code does not have (the previous audits' most valuable finding class).
- Tests that could pass while the property they name is broken (e.g. a fixture that tests the code against itself, a tolerance that hides a real error, an assertion on the wrong byte).
- host.rs: correctness of the FILETIME/SYSTEMTIME conversions, negative/large inputs, the now() arithmetic, and whether the CRT-parity test is sound (it links _localtime64_s from the MSVC CRT while ak820ctl is mingw-built).
- cache.rs: the fscanf emulation on inputs the C or Python actually write, saturation, whitespace, the atomic save.
- transaction.rs: the order of operations vs cmd_clock; error paths; what Outstanding is left holding after each failure; what `drained` accumulates; anything that could panic in a daemon built with panic=abort.
- The CLI `clock` command: confirm it cannot write anything but RTC_GET_TIME.
- Anything missing that the phase-3 scheduler will need from the transaction and cannot get.

Be concrete: file, line, the input, the expected vs actual behaviour. Rank P1/P2/P3. If you find nothing serious, say so plainly — an audit that always produces findings is one that invents them. You may compare against ../jdrgb and ../jdups (same author's prior Win32 HID code) if useful. End with a short list of what you verified and found sound, so the disposition can record it.
codex
I’ll trace the Rust transaction against the pinned C and Python behavior, then check the tests and documentation claims. I’ll keep this read-only and avoid opening any HID device.
2026-09-06T12:53:17.903135Z ERROR codex_core::tools::router: error=exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: CreateProcessAsUserW failed: -1073283067 (Win32 error -1073283067) | cwd=C:\\\\Users\\\\jdlien\\\\code\\\\ak820-pro | cmd=\\\"C:\\\\Program Files\\\\WindowsApps\\\\Microsoft.PowerShell_7.6.5.0_x64__8wekyb3d8bbwe\\\\pwsh.exe\\\" -Command \\\"try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}\\nGet-Location; rg --files -g AGENTS.md -g Cargo.toml -g Cargo.lock -g 'review-codex-phase*.md' -g '*CLOCK*.md' -g 'AK820-AGENT-PLAN.md' -g '*clock_oracle*' -g '*.rs' ak820-agent plans scripts\\\" | env_u16_len=8077 | si_flags=256 | creation_flags=525312\")" }
2026-09-06T12:53:25.731273Z ERROR codex_core::tools::router: error=exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: CreateProcessAsUserW failed: -1073283067 (Win32 error -1073283067) | cwd=C:\\\\Users\\\\jdlien\\\\code\\\\ak820-pro | cmd=\\\"C:\\\\Program Files\\\\WindowsApps\\\\Microsoft.PowerShell_7.6.5.0_x64__8wekyb3d8bbwe\\\\pwsh.exe\\\" -NoProfile -Command \\\"try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}\\nGet-ChildItem -Name\\\" | env_u16_len=8077 | si_flags=256 | creation_flags=525312\")" }
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
codex
Process launching is blocked in this session, but I can read the repository through the file-access tool. I’ll continue with static review and in-memory checks; I can’t claim a fresh Rust test run.
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
codex
The normal-path arithmetic and packet layout match the C so far. I’m checking the less visible boundaries next: whether unresolved requests survive later commands, whether SET preparation can stall after timestamping, and what the CRT fixtures actually prove.
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
ERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 10:02 AM.
ERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 10:02 AM.
tokens used
108,866
```

## Run 2 transcript (stderr, verbatim; the resume prompt is its first user turn)

```text
OpenAI Codex v0.153.4
--------
workdir: C:\Users\jdlien\code\ak820-pro
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: xhigh
reasoning summaries: none
session id: 01a076c7-a375-7442-b639-cae91dd60f0d
--------
user
Continue the phase-2 audit from where you stopped (the usage limit interrupted you). You had established that the normal-path arithmetic and packet layout match the C, and you named three boundaries to check next: whether unresolved requests survive later commands, whether SET preparation can stall after timestamping, and what the CRT fixtures actually prove. Since you stopped, the code moved -- re-read these files before judging them: (1) commit 7184dd3 changed hid/exchange.rs so that Outstanding is a SET of unanswered (channel, command) debts rather than a single slot -- a lost GET followed by a lost SET previously forgot the GET; now note() adds, a command's own reply forgets only itself, and only resynchronise() clears all; Device::unanswered() returns the list; tests two_consecutive_lost_commands_are_both_remembered and the_same_lost_command_is_one_debt were added, plus clock/transaction.rs test a_silent_set_leaves_a_debt_that_refuses_the_next_set. (2) clock/mod.rs select() now initialises rtt_max to 0.0 as the C does, with a test. (3) clock/host.rs states the TZ assumption in its header. (4) commit 9cee322 added plans/AK820-AGENT-PLAN.md 'Phase 2 evidence' and 'Phase 2 audit -- disposition' sections and plans/AK820-AGENT-CLOCK-TRANSACTION.md 'Port status'; the disposition records the author's interim re-read of your three boundaries -- treat it as a starting point to verify, not as settled. Then finish the audit as originally asked: concrete findings with file, line, input, expected vs actual, ranked P1/P2/P3; say plainly if nothing serious remains; end with the list of what you verified and found sound. Read-only; do not modify anything.
codex
I’ll re-read the changed files and verify the interim disposition against the code, then finish the remaining edge-case checks. The audit remains read-only, with no HID access.
codex
The revised debt set fixes the overwritten-request bug, and `rtt_max = 0.0` now matches the C. I found another reachable parity edge: a lengthened slew period just after midnight can produce negative board seconds-of-day. The C treats that as an unset reading; Rust currently accepts it as a sample.
web search: 
web search: site.learn.microsoft.com SystemTimeToTzSpecificLocalTime localtime64_s TZ time zone ...
web search: 
web search: https://raw.githubusercontent.com/mingw-w64/mingw-w64/master/mingw-w64-crt/misc/clock_gettime.c
web search: 
web search: https://raw.githubusercontent.com/mingw-w64/mingw-w64/master/mingw-w64-libraries/winpthreads/src/clock.c
codex
The CLI still has a bidirectional ownership problem: its GET reply can reach the running Python/C timekeeper and corrupt a sync measurement, even though the CLI exposes no SET command. I also confirmed that the installed C cache uses CRLF, while Rust writes LF; the oracle harness’s text-mode read hides that byte difference.
codex
The remaining checks confirm a gap in the prepared API’s deadline handling: it calculates the write allowance before calling `prepare` and never checks it again. I’m finishing the report with that issue, the midnight case, and the limits of the CRT evidence. The updated debt-retention fix looks sound.
codex
**I would keep the phase-2 gate open. One P1 remains: the new CLI clock reader can corrupt the running timekeeper’s measurements.** The revised outstanding-command set fixes the earlier overwrite bug.

This review reflects HEAD **9cee322**, including **7184dd3**, against C **7f92889f**. It was read-only. Process launching was blocked; I inspected sources, existing executable imports, and cache bytes, and checked arithmetic in memory. I did not run Rust tests or access HID.

**1. P1 — The diagnostic clock read can contaminate the active clock writer.**  
[ak820.rs:155](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:155), [ak820.rs:169](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:169)

`clock()` opens another shared handle and sends GET without establishing ownership.

Concrete sequence: the Python/C timekeeper is awaiting a measurement GET; the CLI’s GET reply reaches its handle first. The timekeeper accepts that well-formed reply, pairs the CLI’s board sample with its own timestamps, and can select it as the minimum-RTT sample. That affects its SET and learners.

The comment describes the consequence as a wrong diagnostic number. **The interference is bidirectional:** the diagnostic can corrupt the process that writes the clock and cache. The parity document already correctly describes this at [CLOCK-PARITY.md:179](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-CLOCK-PARITY.md:179).

The CLI exposes no SET, which is sound, but that alone does not protect ownership. Route reads through the owner, or enforce exclusive clock operation before issuing them. A mutex used only by Rust would not coordinate the installed Python/C agent.

**2. P2 — Negative board seconds-of-day are accepted where C reports an unset reading.**  
[transaction.rs:167](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:167), [clock/mod.rs:213](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/mod.rs:213)

Concrete GET fields:

```text
set=1, proto=2, time=00:00:00
cnt=100, active_period=33422, nominal_period=32767
```

The shared fraction formula produces `board_sod = -0.016937255859375`.

- C’s [get_offset:286](C:/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:286) returns `-2` whenever `b < 0`.
- Rust checks only the set flag and creates a sample. With host midpoint `0.005`, it reports **−21.9 ms**.

This is reachable during a slowing slew: [rtc.c:467](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:467) can program an active period longer than nominal. Immediately after midnight, its negative fraction makes the total negative.

Consequences include different measurement counts, selection, uncertainty, and CLI output/exit status. Preserve the C’s `b < 0` check when producing the measurement. The current captured fixtures and shortened-period test do not cover this case.

**3. P2 — Preparation can consume the deadline, but the command still transmits.**  
[exchange.rs:333](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:333), [exchange.rs:346](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:346)

`left` is calculated **before** `prepare`, then reused for writing without another deadline check.

Concrete input: a clean fake wire, a 20 ms budget, and a preparation callback that takes 50 ms. Expected under the documented expired-operation contract: no transmission. Actual: the frame is written after expiration, using the old allowance; collection subsequently times out.

The production SET callback also performs `host.local()` and allocation after `t_enc`; the transport adds framing, debt bookkeeping, buffer allocation/copying, and event reset before `WriteFile`. I found no explicit sleep or retry there, but the interim disposition does not establish a bounded interval.

Recheck the deadline after preparation and before transmission, and define the preparation callback’s timing contract. The existing preparation test proves ordering only.

**4. P2 — Verify failures lose the structured error the scheduler needs.**  
[transaction.rs:230](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:230), [transaction.rs:396](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:396)

Concrete input: measurement and SET succeed, then verification returns `hid::Error::Stuck`.

`run()` returns `Ok(Outcome)` and converts `Stuck` to a string. The caller cannot match the permanent-abandonment condition through the result’s type, although this condition explicitly requires different recovery from an ordinary timeout.

Likewise, reports discarded during a failed verify remain outside `Outcome.drained`; reports accumulated by successful earlier requests disappear entirely when a later measurement or SET returns an error.

Keep failed verification nonfatal for C/Python parity, but retain its typed error and transaction-wide discard accounting. That lets phase 3 preserve the success semantics while handling transport recovery correctly.

**5. P3 — The cache fixtures prove normalized text parity, not identical Windows file bytes.**  
[cache.rs:329](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/cache.rs:329), [clock_oracle.c:74](C:/Users/jdlien/code/ak820-pro/scripts/clock_oracle.c:74)

For `{ proto: 2, lead: 2.354, bias: -25 }`:

- Windows C/Python write `2 2.354 -25\r\n`.
- Rust writes `2 2.354 -25\n`.

The installed cache I read ended in bytes **`0D 0A`**. The harness reads its saved file back using `"r"`, which translates CRLF to LF before constructing the fixture. That translation is documented by [Microsoft’s text-mode contract](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/fopen-wfopen?view=msvc-170).

All three parsers tolerate the difference, so I found no functional interoperability failure here. Nevertheless, the byte-for-byte claim is false. Compare raw file bytes, or declare newline normalization an intentional divergence.

**6. P3 — The localtime sweep compares against a different CRT from the installed oracle.**  
[host.rs:272](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/host.rs:272), [host.rs:294](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/host.rs:294)

I inspected the existing executables’ import tables:

- `ak820ctl.exe`: **`msvcrt.dll!_localtime64`**
- Rust’s clock test executable: **`api-ms-win-crt-time-l1-1-0.dll!_localtime64_s`**

The sweep is useful evidence of Win32/UCRT agreement on this machine’s zone. It does **not** directly establish agreement with the installed mingw oracle.

I found no demonstrated localtime discrepancy within the supported years and stated no-`TZ` environment. Extend the mingw harness to produce localtime results before describing this as an oracle sweep.

**7. P3 — Minimum-RTT selection still omits C’s `1e9` sentinel behavior.**  
[clock/mod.rs:313](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/mod.rs:313), [transaction.rs:258](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:258)

For one good sample with `offset_ms=123` and `rtt_ms=1e9`:

- C leaves `best_off=0`, because `rtt < rtt_min` is false, and prints the verify RTT.
- Rust selects that sample, reports `before=123`, and prints its `1e9` RTT.

This requires an extreme wall-clock discontinuity or suspension, so it is low priority. It remains an undeclared arithmetic divergence despite the corrected `rtt_max` initialization.

There are also three small documentation/test corrections:

- [PLAN.md:742](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-PLAN.md:742) says the cache is unwritten in every listed failure case. A failed verify **does save it**, correctly; [transaction.rs:925](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:925) explicitly asserts that.
- [transaction.rs:333](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:333) promises at most seven requests. A successful `0xFE` retry makes **eight**.
- [exchange.rs:901](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/exchange.rs:901), `the_same_lost_command_is_one_debt`, clears all debts between its two losses. It would pass without `note()`’s deduplication check. The implementation itself deduplicates correctly.

What I verified and found sound:

- Revised debts survive unrelated successes and subsequent lost commands; identical requests are refused before preparation/transmission.
- GET/SET framing, complete-report checks, foreign-command rejection, status-tail offsets and signed fields.
- Fraction arithmetic, nominal-zero fallback, ordinary midnight wrap, ordinary min-RTT selection, and corrected negative-RTT maximum initialization.
- SET truncation, millisecond clamp, flags, bias byte order, **`0x7FFF`**, and fresh timestamp on the single `0xFE` retry.
- Lead sign, gain, clamps and gates; finite-value printed rounding and Python-facing `as_reported()` behavior.
- Cache parsing for normal C/Python-produced content, range handling, and temporary-file replacement under single-writer operation.
- Host conversion storage and pointer lifetimes; epoch arithmetic within supported years. Arbitrary extreme `i64` inputs remain unchecked and can overflow or panic.
- No new HID enumeration mechanism, and no CLI route to RTC SET.
- No concrete new cancellation-buffer lifetime defect found.
tokens used
208,218
```
