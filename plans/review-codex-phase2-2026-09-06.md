# Codex audit of ak820-agent phase 2 — 2026-09-06 — INCOMPLETE

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read. Launched 06:53 local against commit `cb42eb8`
("ak820-agent: the clock transaction, with the C as its own oracle").

⚠️ **This run delivered no findings.** It stopped after ~109k tokens on the
owner's Codex usage limit (`try again at 10:02 AM`), mid-review. Its last
interim statement, verbatim from the transcript below: *"The normal-path
arithmetic and packet layout match the C so far. I'm checking the less visible
boundaries next: whether unresolved requests survive later commands, whether
SET preparation can stall after timestamping, and what the CRT fixtures
actually prove."* None of those three were reached. As in the phase-1 audit,
its shell could not start (`CreateProcessAsUserW failed`), so it worked from
file reads and its JS sandbox.

Disposition of what *was* said, and the author's interim re-read of the three
named boundaries, is in `AK820-AGENT-PLAN.md`, "Phase 2 audit — disposition".
The phase is **not** done until this has been re-run to completion.

## To re-run

From the repository root, after the quota resets:

```sh
codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh \
  -c 'sandbox_permissions=["disk-full-read-access"]' -s read-only "$(cat PROMPT)"
```

where `PROMPT` is the prompt reproduced below (the transcript shows codex
writes its final message to **stderr**, so capture both streams). Then save
the verbatim output over this file and fill in the disposition table in the
plan.

## The prompt given

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

## Transcript (stderr, verbatim; stdout was empty)

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
