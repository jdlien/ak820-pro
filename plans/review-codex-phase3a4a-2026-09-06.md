# Codex audit of ak820-agent phases 3a and 4a — 2026-09-06

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read. One run, session
`01a0770c-542c-7ad3-bb43-4bdb5959ac39`, launched 08:2x local against commit
`b741289` (phase 3a replay, phase 4a self-install and status file, phase 6a
plumbing), ~218k tokens. Scope given: `ak820-agent/src/{agent,task,media,
logfile,status,instance,clock/scheduler}.rs`, both binaries, the replay test
and its fixture, the plan's staged switch-over section, against the Python
`ak820-timekeeper.py` and `nowplaying-windows.py` and the pinned bindings.

As in phases 1 and 2, its shell could not start, so it worked from file reads,
the pinned `windows` crate's bindings and the log fixture. It did not run the
Rust tests, start either agent, or touch HID.

Its verdict — block the 4b takeover, reopen the 3a replay gate, keep 4a open
— was accepted in full: 18 findings, every one fixed, including the daemon-side
ownership check finding 1 asked for "beyond trusting how its flag was supplied". Disposition of every finding: `AK820-AGENT-PLAN.md`, "Phase 3a/4a
audit — disposition".

## The final report (verbatim)

**I found P1 ownership defects. I would block the 4b takeover, reopen the claimed 3a replay gate, and keep 4a open pending the media fixes.**

This review is against **b741289**, with the scoped sources checked against that commit. It was read-only. I cannot launch processes in this sandbox; I did not run Rust tests, start agents, or touch HID. I inspected sources, pinned Windows bindings, the replay data, and existing executable import tables.

**1. P1 — The advertised clock rollback starts a second writer before stopping the first.**  
[ak820.rs:404](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:404), [PLAN.md:242](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-PLAN.md:242)

With Rust running `--clock`, follow the printed PowerShell rollback command. The Python installer registers and starts the timekeeper; Rust continues syncing. The plan explicitly says to remove Rust’s flag **afterwards**. That creates an overlap capable of corrupting measurements and both learners.

The forward transition also stops/deletes Python without verifying process termination, unlike the media transition’s mutex wait. Additionally, the pinned `Stop()` binding converts `S_FALSE` into `Ok(())`, although Microsoft documents that result as inability to stop instances. [Stop contract](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-iregisteredtask-stop).

**Fix:** Make both directions stop-and-confirm-before-start transitions, including any active `ak820ctl` child. The daemon needs an ownership check beyond trusting how its flag was supplied.

**2. P1 — `ak820 clock` fails open when checking the Rust owner.**  
[ak820.rs:233](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:233), [task.rs:113](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/task.rs:113)

The tuple pattern rejects only two successful answers: `Running` and `owns_clock=true`. An error reading either state or XML falls through. If the Python task is absent, the CLI then sends GET without `--anyway`.

There is also a deterministic argument-parsing bypass: registered arguments containing `"--clock"` run the daemon with that flag, but `split_whitespace()` sees the quotes and returns false.

**Expected:** Refuse when ownership cannot be established, and recognize arguments as Windows passes them. **Actual:** A diagnostic GET can enter the running clock transaction.

**3. P1 — A failed reinstall can leave the sole clock owner stopped.**  
[ak820.rs:352](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:352), [ak820.rs:364](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:364)

Run the installed `%LOCALAPPDATA%\ak820pro\bin\ak820.exe install --clock`. `daemon_src` and `daemon` identify the same file, but only the CLI copy has a same-path guard. The daemon has already been stopped when the same-file copy is attempted. Windows uses `CopyFileEx` for this operation; this is not a safe no-op. [Rust copy contract](https://doc.rust-lang.org/std/fs/fn.copy.html).

More generally, any subsequent copy, registration, or start failure returns without restoring the previous task. If Rust already owned the clock, Python is absent and nothing resumes syncing.

**Fix:** Skip same-file copies, stage the replacement before stopping the owner, and restore the previous working configuration on failure.

**4. P1 — Closing a handle does not establish that an unanswered firmware command cannot answer the next handle.**  
[agent.rs:178](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:178), [agent.rs:308](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:308)

The comment confuses two cases:

- Reports already buffered in the old file object disappear with that object.
- A response delivered **after the new handle opens** can reach its new queue.

Concrete sequence: GET A transmits and times out; its handle closes; handle B opens and observes an empty pre-drain; B sends GET; A’s delayed response arrives and satisfies B’s matcher. Nothing carries the unresolved-command state across those opens.

A failed verify is particularly relevant because the caller immediately opens another handle for `read_status()`.

**Fix:** Preserve an unresolved clock transaction across reopen until the chosen resynchronization policy establishes recovery. File-object queue isolation alone does not prove the stated guarantee.

**5. P2 — SMTC failures keep stale media alive indefinitely instead of publishing idle.**  
[worker.rs:375](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:375), [agent.rs:423](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:423)

Input: a successful playing snapshot, followed by repeated `RequestAsync` or `GetSessions` failures.

Python’s `run()` substitutes idle, clears text, and disables playback. Rust retains the old snapshot; the daemon refreshes its text every 30 seconds and playback every poll.

The comment claiming firmware expiry will clear it is false: these refreshes prevent expiry. `health.stale_for` is also discarded when writing daemon status.

**Fix:** Publish idle on completed read failures to match Python, and expose snapshot freshness for the separately acknowledged stalled-worker case.

**6. P2 — Clock operations bypass the abandoned-handle backoff.**  
[agent.rs:426](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:426), [agent.rs:437](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:437), [agent.rs:354](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:354)

Only the media cycle consults `Watch::holding()`.

If media returns `Stuck`, the clock can reopen in the same iteration. If clock synchronization returns `Stuck`, it is converted to a string and never reaches `Watch`. A stuck verify remains inside a successful `Outcome` and is ignored; status-read errors disappear through `.ok()?`.

Thus the clock can keep opening and abandoning handles during the promised one-minute pause.

**Fix:** Apply one shared abandonment policy to every board interaction, retaining typed errors through sync and status reads.

**7. P2 — Failed learner cache writes change subsequent decisions differently from Python.**  
[agent.rs:245](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:245), [scheduler.rs:389](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/scheduler.rs:389)

Rust commits the learner baseline before attempting the cache save. Python’s `cap_write_bias()` can raise; that exits `learn_bias()` before its final baseline assignment.

Concrete input: baseline at `t=0`, unchanged period, bias `0`; qualifying residual `+12 ms` at `t=300`, with the cache write failing; another `+12 ms` at `t=600`.

- Python retains the original baseline: elapsed `600`, new bias `+5`.
- Rust uses the failed-write baseline: elapsed `300`, new bias `+10`.

Separately, `ClockLoop::sync()` ignores `Outcome.cache_saved`, so a failed lead-cache save can produce only a successful sync line and cleared `last_error`.

**Fix:** Make baseline commitment reflect the oracle’s write outcome, and log transaction cache-save failures.

**8. P2 — The replay does not satisfy the documented differential-state gate.**  
[timekeeper_replay.rs:89](C:/Users/jdlien/code/ak820-pro/ak820-agent/tests/timekeeper_replay.rs:89), [CLOCK-PARITY.md:190](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-CLOCK-PARITY.md:190)

Each learned line creates a new scheduler, supplies an invented preceding sample with the same period, and injects the logged old bias. State and cache output never flow into the next recorded sample.

A broken learner that establishes its first baseline but never advances it would still pass this replay: every case exercises only its first two calls. Failed cache writes—the preceding finding—are not replayed.

The precision allowances are reasonable for their limited purpose. The 5 ms scan searches within the printed second and checks both rounded outputs. Assuming `ref_state=2` on learned lines is justified, but cannot validate that gate’s negative cases.

The interval replay **does constrain the choice**: its timing allowance cannot hide replacing 180 with 300. I independently counted 171 applicable intervals, including 12 fast intervals; their actual gaps exceed the selected interval by 0–4 seconds.

**Fix:** Retain these useful component checks, but add sequential differential replay comparing resulting state and serialized cache, including failures and missing data.

**9. P2 — A failed text push suppresses the playback push for that poll.**  
[agent.rs:484](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:484)

An ordinary text timeout returns from `cycle()` before playback is attempted. Python catches the text failure and still attempts playback independently.

With repeated text failures and working playback commands, Rust lets the playback display expire. `media.rs` explicitly promises playback “whatever happened above,” which the caller does not implement.

**Fix:** Preserve the text retry state while separately attempting playback when the transport remains usable; retain the special `Stuck` policy.

**10. P2 — The presence error plumbing deferred to phase 4 is still unfixed.**  
[device.rs:354](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:354), [agent.rs:131](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:131)

`open_board()` still returns the last candidate’s failure.

For example, the raw interface opens but fails its capability check; subsequent keyboard collections fail to open. The daemon receives `Open` and reports **busy**, losing the meaningful **refused/incompatible** result. Identification failures also still collapse into `Reject::Silent`.

The `Watch` tests inject already-classified errors, so they do not test this producer-to-consumer boundary. This is the earlier finding explicitly deferred to phase 4, now affecting its live consumer.

**11. P2 — The live text publisher still accepts another row’s echo as its acknowledgement.**  
[proto.rs:165](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/proto.rs:165), [agent.rs:507](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:507)

While awaiting `TEXT_SET_LINE` for row 0, a row-1 echo—or an echo containing different text—passes because only channel and command are compared.

The firmware preserves these request bytes, so this ambiguity is avoidable. The phase-1 audit specifically warned that this could not wait for phase-5 health decoding once two-row publishing went live.

**Fix:** Match the echoed row, icon and text payload; drain mismatches before advancing publisher state.

**12. P2 — `foreign_reports` loses failures and inconsistently counts stale reports.**  
[agent.rs:490](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:490), [agent.rs:504](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:504), [agent.rs:356](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:356)

Concrete cases:

- Row 0 drains foreign reports and succeeds; row 1 fails. `send()` loses row 0’s count.
- A request receives foreign reports and then times out. Its error’s discard list never reaches the status counter.
- Playback succeeds after discarding only pre-existing stale reports. `reply.drained.len()` incorrectly increments the foreign counter.

Consequently, zero does not establish absence of observed foreign traffic, and a positive value does not consistently mean foreign traffic.

**Fix:** Accumulate discards independently of success and classify them consistently.

**13. P2 — External interval input can abort the console-less daemon without logging.**  
[ak820-agent.rs:57](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820-agent.rs:57), [worker.rs:310](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:310)

`--interval inf` and sufficiently large positive numbers pass `secs > 0.0`, then panic in `Duration::from_secs_f64`. This occurs before normal daemon logging or mutex acquisition. A tiny positive value can instead round to zero and produce an effectively continuous polling loop.

Thread creation also uses `.expect("spawning the media thread")`; an OS failure aborts the entire release process without a log entry.

**Fix:** Use fallible duration conversion with a nonzero validated range, and propagate thread-creation errors to the log.

**14. P2 — The media interval controls clock cadence and can disable learning entirely.**  
[agent.rs:438](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:438), [agent.rs:455](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:455)

Run the daemon with `--clock --interval 120`. The clock is examined only after each media sleep. Every subsequent loop gap exceeds 60 seconds, so every sync is classified as `wake`; each merely replaces the learner baseline. Periodic learning never fires.

Even independently of that option, `last_tick` measures from the start of work, whereas Python sleeps 15 seconds after finishing it.

**Fix:** Schedule the clock independently of the media interval and preserve the oracle’s placement of the loop delay.

There are also several **P3** corrections:

- [agent.rs:417](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:417): a first SMTC poll taking more than two seconds still causes the initial idle `CLEAR`. The grace reduces the blink; it does not guarantee the first push is real state.
- [build.rs:13](C:/Users/jdlien/code/ak820-pro/ak820-agent/build.rs:13): watching only Git metadata misses an uncommitted source edit after a clean build. Rebuilt code can retain a clean `git describe` without `-dirty`.
- [logfile.rs:46](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/logfile.rs:46): a persistent rename failure—such as a locked `.1` destination—is ignored while appending continues. Rotation works normally, but the claimed size bound does not survive rotation failure.
- [scheduler.rs:334](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/scheduler.rs:334): normalizing nominal period `0` into `None` preserves gate truthiness but changes the next hold log from Python’s `P 0 -> …` to `P None -> …`.

What I verified and found sound:

- Configuration Manager discovery opens nothing; controller IDs use its sorted paths. Normal handles close before loop and enumeration-settle sleeps.
- The pure scheduler’s constants, trigger precedence, printed-`before` comparisons, arithmetic, banker's rounding, seed wrapping and ordinary missing-status behavior match Python.
- Publisher text state advances only after all text reports succeed; normal change/keepalive decisions and report splitting match.
- The Rust mutex implementation checks `ERROR_ALREADY_EXISTS` correctly, closes rejected/partial claims, and fences the normal Python media instance.
- Task XML matches the pinned settings. Current COM lifetimes and apartment balancing are sound; an empty registration user VARIANT permits the XML principal to supply the account. [Microsoft security-context contract](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks).
- Status replacement and normal log rotation use appropriate file replacement operations. Cargo.lock is committed, workflow working directories apply `crt-static`, and the existing x64 binaries have the intended subsystems with no VC++ runtime DLL imports. Clean-machine execution remains unverified.


## The prompt

```text
You are auditing phases 3a and 4a of `ak820-agent/` in this repository (C:\Users\jdlien\code\ak820-pro), a Rust port of two Python host agents for an AJAZZ AK820 Pro keyboard. This is the fourth audit under a standing rule (a phase is done when its gate passes AND an independent model has read the code). The three previous audits are in plans/review-codex-phase{0,1,2}-2026-09-06.md; each found real P1 bugs, including doc comments asserting properties the code did not have, and a single-slot debt tracker that forgot the first of two lost commands. Read-only; do not modify anything.

SCOPE -- what is new since the phase-2 audit (commits 1e52b93, 89c855a and HEAD):

Phase 4a, LIVE on this machine since 07:53 today (the daemon owns now-playing; the Python timekeeper still owns the clock):
- ak820-agent/src/media.rs -- nowplaying-windows.py's run() loop as a pure state machine (Publisher/Plan)
- ak820-agent/src/agent.rs -- the daemon loop: one open per cycle, presence as a state machine (Watch), the bounded log, the status file, the first-poll grace; AND the phase-4b ClockLoop (below)
- ak820-agent/src/logfile.rs, status.rs, instance.rs (named mutexes: its own AND the Python now-playing agent's name, to fence it out)
- ak820-agent/src/task.rs -- Task Scheduler COM: state/info/arguments, task_xml (pinned against Export-ScheduledTask's output for the PowerShell installer's task), register from XML, start/stop/delete, agent_owns_clock
- ak820-agent/src/bin/ak820-agent.rs -- the windows-subsystem daemon binary (no console: everything goes to the log)
- ak820-agent/src/bin/ak820.rs -- install [--in-place] [--clock], uninstall, status, --version; clock_ownership() now also refuses beside a --clock daemon
- ak820-agent/.cargo/config.toml (static CRT), build.rs (git describe), INSTALL.txt, .github/workflows/agent.yml and release.yml
- ak820-agent/src/smtc/mod.rs -- reports() split into text_reports()/playback_report(); text/mod.rs Icon::name()

Phase 3a (replay gate met) and 4b (wired, NOT switched):
- ak820-agent/src/clock/scheduler.rs -- ak820-timekeeper.py's main()/learn_bias()/bias_step() as a pure state machine
- ak820-agent/tests/timekeeper_replay.rs over tests/fixtures/ak820pro-timekeeper-2026-09-05.log -- the Python timekeeper's own log replayed: 108 learned lines, 59 holds, 171 intervals
- agent.rs ClockLoop -- the daemon's clock loop behind --clock, calling clock::transaction::run per sync on a fresh handle, learn/seed writing the cache

ORACLES the port must match:
- hostagent/nowplaying-windows.py (run(), push_text, the keepalive) and hostagent/ak820text.py (send/push_both/push_playback) for the media loop
- hostagent/ak820-timekeeper.py (main, sync, learn_bias, bias_step, read_status, cap_read/cap_write_bias, controller_id) for the scheduler
- hostagent/install-agents-windows.ps1 for the task definition (the exported XML is pinned in task.rs's test)
- plans/AK820-AGENT-CLOCK-PARITY.md (the scheduler contract, with a new "Port status" section), plans/AK820-AGENT-PLAN.md ("Staged switch-over and packaging", "Phase 4a evidence", "Phase 3a evidence" -- the 3b procedure and acceptance limits)

LOAD-BEARING CONSTRAINTS -- test these rather than rediscover them:
1. Never enumerate HID. Presence is the Configuration Manager's list (device::interfaces), which opens nothing; the controller id for the seed is built from those paths.
2. Validate every read against its request; foreign reports are drained and counted (foreign_reports in the status file).
3. Correlation is NOT sufficient for the clock: exactly one process may run clock transactions. install --clock removes the Python timekeeper's task; install without it must not silently leave zero or two clock owners; `ak820 clock` must refuse beside either owner.
4. A transmitted-but-unanswered command is refused until resynchronise -- per handle. The ClockLoop opens a fresh handle per transaction and per status read; check that this is sound (a closed file object takes its queue with it) and that nothing holds a handle across the 15 s loop or the media sleep.
5. The media loop moves state only on a SUCCESSFUL push (a failed push retries next poll); text on change or every 30 s; playback every poll; first push is the real state (the first-poll grace).
6. One instance: named mutexes Global\ak820pro-agent and Global\ak820pro-nowplaying, claimed before anything else; the daemon exits 2 if held. install waits for the names to be released after stopping tasks (Stop-ScheduledTask ends the process asynchronously -- the first live install hit this).
7. The daemon has NO console (windows subsystem): every failure must reach the log; nothing may panic silently under panic=abort in release. Look for unwrap/expect/indexing on external data in agent.rs, task.rs, status.rs, logfile.rs, the bins.
8. The scheduler must be verbatim: LOOP 15, SYNC_INTERVAL 300/180, FAST_ABOVE 60 (compared against the PRINTED one-decimal before), SLEEP_GAP 60, BIAS_INTERVAL 900, LEARN_MIN_ELAPSED 90, LEARN_MAX_BEFORE 400, gain 0.25, LEARN_MAX_DP 6, BIAS_LIMIT 600 strict for the seed and clamped for the learner; int(round()) is banker's; wall time for scheduling/seed and monotonic for elapsed; the learner timestamps BEFORE the status read; failed sync moves nothing but was_present; absence clears seed and learner; the hold log's narrower condition; `P None`.
9. The task XML must reproduce the PowerShell installer's settings (interactive token, logon trigger, both battery settings, PT0S limit, restart 999/PT1M, IgnoreNew, StartWhenAvailable). RegisterTask is called with TASK_LOGON_INTERACTIVE_TOKEN and an empty userId VARIANT; check that is correct for a per-user task, and that the XML's Principal UserId (DOMAIN\user from env vars) is what the scheduler needs.
10. The status file is written atomically (tmp + rename) every cycle; the log rotates at 1 MB; both must never take the daemon down.

WHAT TO LOOK FOR, in priority order:
- Anything that could put two writers on the board, or none: the install/uninstall state transitions, the mutex handling, the --clock plumbing, agent_owns_clock reading the registered XML.
- Parity defects in media.rs against run()/push_text (including what happens when SMTC read fails: the Python pushes idle), and in scheduler.rs against the Python (every gate, the time sources, the rounding, what happens on the first loop, the enumerated 2 s sleep placement, what `read_status` returning None does to each consumer).
- The replay test's validity: could it pass with a broken learner? Are its precision allowances (the 5 ms elapsed scan, ref_state assumed 2) hiding anything? Does the interval replay actually constrain the choice?
- The ClockLoop's error paths: a transaction that fails mid-way (what state the scheduler sees), cache save failures, a status read that fails, a board that vanishes between the presence check and the open, the enumerated sleep blocking the media loop.
- Presence (Watch): the mapping of hid::Error variants to states, the abandoned-handle backoff, and whether any path reopens a Stuck device every cycle.
- COM/Win32 correctness in task.rs and instance.rs: apartment balance, BSTR/VARIANT lifetimes, error mapping (ERROR_FILE_NOT_FOUND vs others), CreateMutexW's ERROR_ALREADY_EXISTS check, handle leaks.
- The release plumbing: does --locked + a committed Cargo.lock + crt-static actually give the "no VC++ redistributable" property; is anything in the workflows wrong for a windows-latest runner; does build.rs behave on a clean checkout and without git.
- Doc comments or plan text asserting properties the code lacks.

Be concrete: file, line, input, expected vs actual. Rank P1/P2/P3. If you find nothing serious, say so plainly. You may compare with ../jdrgb and ../jdups (same author's prior Win32 code, incl. a jdups-agent daemon). End with a short list of what you verified and found sound. You cannot run processes in this sandbox; say so rather than claiming a test run.

```

## Transcript (stderr, verbatim)

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
session id: 01a0770c-542c-7ad3-bb43-4bdb5959ac39
--------
user
You are auditing phases 3a and 4a of `ak820-agent/` in this repository (C:\Users\jdlien\code\ak820-pro), a Rust port of two Python host agents for an AJAZZ AK820 Pro keyboard. This is the fourth audit under a standing rule (a phase is done when its gate passes AND an independent model has read the code). The three previous audits are in plans/review-codex-phase{0,1,2}-2026-09-06.md; each found real P1 bugs, including doc comments asserting properties the code did not have, and a single-slot debt tracker that forgot the first of two lost commands. Read-only; do not modify anything.

SCOPE -- what is new since the phase-2 audit (commits 1e52b93, 89c855a and HEAD):

Phase 4a, LIVE on this machine since 07:53 today (the daemon owns now-playing; the Python timekeeper still owns the clock):
- ak820-agent/src/media.rs -- nowplaying-windows.py's run() loop as a pure state machine (Publisher/Plan)
- ak820-agent/src/agent.rs -- the daemon loop: one open per cycle, presence as a state machine (Watch), the bounded log, the status file, the first-poll grace; AND the phase-4b ClockLoop (below)
- ak820-agent/src/logfile.rs, status.rs, instance.rs (named mutexes: its own AND the Python now-playing agent's name, to fence it out)
- ak820-agent/src/task.rs -- Task Scheduler COM: state/info/arguments, task_xml (pinned against Export-ScheduledTask's output for the PowerShell installer's task), register from XML, start/stop/delete, agent_owns_clock
- ak820-agent/src/bin/ak820-agent.rs -- the windows-subsystem daemon binary (no console: everything goes to the log)
- ak820-agent/src/bin/ak820.rs -- install [--in-place] [--clock], uninstall, status, --version; clock_ownership() now also refuses beside a --clock daemon
- ak820-agent/.cargo/config.toml (static CRT), build.rs (git describe), INSTALL.txt, .github/workflows/agent.yml and release.yml
- ak820-agent/src/smtc/mod.rs -- reports() split into text_reports()/playback_report(); text/mod.rs Icon::name()

Phase 3a (replay gate met) and 4b (wired, NOT switched):
- ak820-agent/src/clock/scheduler.rs -- ak820-timekeeper.py's main()/learn_bias()/bias_step() as a pure state machine
- ak820-agent/tests/timekeeper_replay.rs over tests/fixtures/ak820pro-timekeeper-2026-09-05.log -- the Python timekeeper's own log replayed: 108 learned lines, 59 holds, 171 intervals
- agent.rs ClockLoop -- the daemon's clock loop behind --clock, calling clock::transaction::run per sync on a fresh handle, learn/seed writing the cache

ORACLES the port must match:
- hostagent/nowplaying-windows.py (run(), push_text, the keepalive) and hostagent/ak820text.py (send/push_both/push_playback) for the media loop
- hostagent/ak820-timekeeper.py (main, sync, learn_bias, bias_step, read_status, cap_read/cap_write_bias, controller_id) for the scheduler
- hostagent/install-agents-windows.ps1 for the task definition (the exported XML is pinned in task.rs's test)
- plans/AK820-AGENT-CLOCK-PARITY.md (the scheduler contract, with a new "Port status" section), plans/AK820-AGENT-PLAN.md ("Staged switch-over and packaging", "Phase 4a evidence", "Phase 3a evidence" -- the 3b procedure and acceptance limits)

LOAD-BEARING CONSTRAINTS -- test these rather than rediscover them:
1. Never enumerate HID. Presence is the Configuration Manager's list (device::interfaces), which opens nothing; the controller id for the seed is built from those paths.
2. Validate every read against its request; foreign reports are drained and counted (foreign_reports in the status file).
3. Correlation is NOT sufficient for the clock: exactly one process may run clock transactions. install --clock removes the Python timekeeper's task; install without it must not silently leave zero or two clock owners; `ak820 clock` must refuse beside either owner.
4. A transmitted-but-unanswered command is refused until resynchronise -- per handle. The ClockLoop opens a fresh handle per transaction and per status read; check that this is sound (a closed file object takes its queue with it) and that nothing holds a handle across the 15 s loop or the media sleep.
5. The media loop moves state only on a SUCCESSFUL push (a failed push retries next poll); text on change or every 30 s; playback every poll; first push is the real state (the first-poll grace).
6. One instance: named mutexes Global\ak820pro-agent and Global\ak820pro-nowplaying, claimed before anything else; the daemon exits 2 if held. install waits for the names to be released after stopping tasks (Stop-ScheduledTask ends the process asynchronously -- the first live install hit this).
7. The daemon has NO console (windows subsystem): every failure must reach the log; nothing may panic silently under panic=abort in release. Look for unwrap/expect/indexing on external data in agent.rs, task.rs, status.rs, logfile.rs, the bins.
8. The scheduler must be verbatim: LOOP 15, SYNC_INTERVAL 300/180, FAST_ABOVE 60 (compared against the PRINTED one-decimal before), SLEEP_GAP 60, BIAS_INTERVAL 900, LEARN_MIN_ELAPSED 90, LEARN_MAX_BEFORE 400, gain 0.25, LEARN_MAX_DP 6, BIAS_LIMIT 600 strict for the seed and clamped for the learner; int(round()) is banker's; wall time for scheduling/seed and monotonic for elapsed; the learner timestamps BEFORE the status read; failed sync moves nothing but was_present; absence clears seed and learner; the hold log's narrower condition; `P None`.
9. The task XML must reproduce the PowerShell installer's settings (interactive token, logon trigger, both battery settings, PT0S limit, restart 999/PT1M, IgnoreNew, StartWhenAvailable). RegisterTask is called with TASK_LOGON_INTERACTIVE_TOKEN and an empty userId VARIANT; check that is correct for a per-user task, and that the XML's Principal UserId (DOMAIN\user from env vars) is what the scheduler needs.
10. The status file is written atomically (tmp + rename) every cycle; the log rotates at 1 MB; both must never take the daemon down.

WHAT TO LOOK FOR, in priority order:
- Anything that could put two writers on the board, or none: the install/uninstall state transitions, the mutex handling, the --clock plumbing, agent_owns_clock reading the registered XML.
- Parity defects in media.rs against run()/push_text (including what happens when SMTC read fails: the Python pushes idle), and in scheduler.rs against the Python (every gate, the time sources, the rounding, what happens on the first loop, the enumerated 2 s sleep placement, what `read_status` returning None does to each consumer).
- The replay test's validity: could it pass with a broken learner? Are its precision allowances (the 5 ms elapsed scan, ref_state assumed 2) hiding anything? Does the interval replay actually constrain the choice?
- The ClockLoop's error paths: a transaction that fails mid-way (what state the scheduler sees), cache save failures, a status read that fails, a board that vanishes between the presence check and the open, the enumerated sleep blocking the media loop.
- Presence (Watch): the mapping of hid::Error variants to states, the abandoned-handle backoff, and whether any path reopens a Stuck device every cycle.
- COM/Win32 correctness in task.rs and instance.rs: apartment balance, BSTR/VARIANT lifetimes, error mapping (ERROR_FILE_NOT_FOUND vs others), CreateMutexW's ERROR_ALREADY_EXISTS check, handle leaks.
- The release plumbing: does --locked + a committed Cargo.lock + crt-static actually give the "no VC++ redistributable" property; is anything in the workflows wrong for a windows-latest runner; does build.rs behave on a clean checkout and without git.
- Doc comments or plan text asserting properties the code lacks.

Be concrete: file, line, input, expected vs actual. Rank P1/P2/P3. If you find nothing serious, say so plainly. You may compare with ../jdrgb and ../jdups (same author's prior Win32 code, incl. a jdups-agent daemon). End with a short list of what you verified and found sound. You cannot run processes in this sandbox; say so rather than claiming a test run.
codex
I’ll read the previous audits, then trace ownership transitions, media and clock parity, and the Windows error paths. I’ll keep this read-only and distinguish code inspection from tests, which I can’t run in this sandbox.
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
The clock ownership checks need closer attention: the installer waits for the media mutexes after stopping tasks, but has no corresponding wait for the Python timekeeper. The daemon’s clock paths also bypass the media presence backoff. I’m tracing the Python subprocess lifetime and scheduler error handling to establish the consequences.
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
mcp: node_repl/js started
web search: 
mcp: node_repl/js (completed)
web search: site.learn.microsoft.com ITaskFolder RegisterTask userId empty VARIANT XML principal interactive token ...
mcp: node_repl/js started
mcp: node_repl/js (completed)
codex
I found a concrete media parity bug: after an SMTC read error, Rust keeps the previous track and the daemon keeps refreshing it. Python publishes idle. The comment saying firmware expiry will clear the stale track is therefore false. I’m checking clock recovery and replay coverage next.
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
mcp: node_repl/js started
mcp: node_repl/js (completed)
web search: 
web search: https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-itaskfolder-registertask
web search: 
web search: site:learn.microsoft.com "RegisterTask" "empty" "context" ...
web search: 
web search: https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks
mcp: node_repl/js started
mcp: node_repl/js (completed)
codex
The replay constrains the arithmetic and the 180/300-second choice, but it rebuilds the learner for each log line. It does not verify state carried across successive syncs or failed cache writes. I also found that the documented rollback starts Python before removing Rust’s clock flag, creating a period with two clock owners.
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
mcp: node_repl/js started
mcp: node_repl/js (completed)
web search: 
web search: https://doc.rust-lang.org/std/fs/fn.copy.html
mcp: node_repl/js started
mcp: node_repl/js (completed)
codex
The existing release binaries have the intended GUI/console subsystems and no VC++ runtime DLL imports. The task XML and COM lifetimes also look sound for the normal per-user path. The main blockers are ownership transitions, recovery after lost replies, and daemon code that drops errors the transport preserves. I’m consolidating the findings with concrete failure sequences.
codex
**I found P1 ownership defects. I would block the 4b takeover, reopen the claimed 3a replay gate, and keep 4a open pending the media fixes.**

This review is against **b741289**, with the scoped sources checked against that commit. It was read-only. I cannot launch processes in this sandbox; I did not run Rust tests, start agents, or touch HID. I inspected sources, pinned Windows bindings, the replay data, and existing executable import tables.

**1. P1 — The advertised clock rollback starts a second writer before stopping the first.**  
[ak820.rs:404](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:404), [PLAN.md:242](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-PLAN.md:242)

With Rust running `--clock`, follow the printed PowerShell rollback command. The Python installer registers and starts the timekeeper; Rust continues syncing. The plan explicitly says to remove Rust’s flag **afterwards**. That creates an overlap capable of corrupting measurements and both learners.

The forward transition also stops/deletes Python without verifying process termination, unlike the media transition’s mutex wait. Additionally, the pinned `Stop()` binding converts `S_FALSE` into `Ok(())`, although Microsoft documents that result as inability to stop instances. [Stop contract](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-iregisteredtask-stop).

**Fix:** Make both directions stop-and-confirm-before-start transitions, including any active `ak820ctl` child. The daemon needs an ownership check beyond trusting how its flag was supplied.

**2. P1 — `ak820 clock` fails open when checking the Rust owner.**  
[ak820.rs:233](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:233), [task.rs:113](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/task.rs:113)

The tuple pattern rejects only two successful answers: `Running` and `owns_clock=true`. An error reading either state or XML falls through. If the Python task is absent, the CLI then sends GET without `--anyway`.

There is also a deterministic argument-parsing bypass: registered arguments containing `"--clock"` run the daemon with that flag, but `split_whitespace()` sees the quotes and returns false.

**Expected:** Refuse when ownership cannot be established, and recognize arguments as Windows passes them. **Actual:** A diagnostic GET can enter the running clock transaction.

**3. P1 — A failed reinstall can leave the sole clock owner stopped.**  
[ak820.rs:352](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:352), [ak820.rs:364](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820.rs:364)

Run the installed `%LOCALAPPDATA%\ak820pro\bin\ak820.exe install --clock`. `daemon_src` and `daemon` identify the same file, but only the CLI copy has a same-path guard. The daemon has already been stopped when the same-file copy is attempted. Windows uses `CopyFileEx` for this operation; this is not a safe no-op. [Rust copy contract](https://doc.rust-lang.org/std/fs/fn.copy.html).

More generally, any subsequent copy, registration, or start failure returns without restoring the previous task. If Rust already owned the clock, Python is absent and nothing resumes syncing.

**Fix:** Skip same-file copies, stage the replacement before stopping the owner, and restore the previous working configuration on failure.

**4. P1 — Closing a handle does not establish that an unanswered firmware command cannot answer the next handle.**  
[agent.rs:178](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:178), [agent.rs:308](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:308)

The comment confuses two cases:

- Reports already buffered in the old file object disappear with that object.
- A response delivered **after the new handle opens** can reach its new queue.

Concrete sequence: GET A transmits and times out; its handle closes; handle B opens and observes an empty pre-drain; B sends GET; A’s delayed response arrives and satisfies B’s matcher. Nothing carries the unresolved-command state across those opens.

A failed verify is particularly relevant because the caller immediately opens another handle for `read_status()`.

**Fix:** Preserve an unresolved clock transaction across reopen until the chosen resynchronization policy establishes recovery. File-object queue isolation alone does not prove the stated guarantee.

**5. P2 — SMTC failures keep stale media alive indefinitely instead of publishing idle.**  
[worker.rs:375](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:375), [agent.rs:423](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:423)

Input: a successful playing snapshot, followed by repeated `RequestAsync` or `GetSessions` failures.

Python’s `run()` substitutes idle, clears text, and disables playback. Rust retains the old snapshot; the daemon refreshes its text every 30 seconds and playback every poll.

The comment claiming firmware expiry will clear it is false: these refreshes prevent expiry. `health.stale_for` is also discarded when writing daemon status.

**Fix:** Publish idle on completed read failures to match Python, and expose snapshot freshness for the separately acknowledged stalled-worker case.

**6. P2 — Clock operations bypass the abandoned-handle backoff.**  
[agent.rs:426](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:426), [agent.rs:437](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:437), [agent.rs:354](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:354)

Only the media cycle consults `Watch::holding()`.

If media returns `Stuck`, the clock can reopen in the same iteration. If clock synchronization returns `Stuck`, it is converted to a string and never reaches `Watch`. A stuck verify remains inside a successful `Outcome` and is ignored; status-read errors disappear through `.ok()?`.

Thus the clock can keep opening and abandoning handles during the promised one-minute pause.

**Fix:** Apply one shared abandonment policy to every board interaction, retaining typed errors through sync and status reads.

**7. P2 — Failed learner cache writes change subsequent decisions differently from Python.**  
[agent.rs:245](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:245), [scheduler.rs:389](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/scheduler.rs:389)

Rust commits the learner baseline before attempting the cache save. Python’s `cap_write_bias()` can raise; that exits `learn_bias()` before its final baseline assignment.

Concrete input: baseline at `t=0`, unchanged period, bias `0`; qualifying residual `+12 ms` at `t=300`, with the cache write failing; another `+12 ms` at `t=600`.

- Python retains the original baseline: elapsed `600`, new bias `+5`.
- Rust uses the failed-write baseline: elapsed `300`, new bias `+10`.

Separately, `ClockLoop::sync()` ignores `Outcome.cache_saved`, so a failed lead-cache save can produce only a successful sync line and cleared `last_error`.

**Fix:** Make baseline commitment reflect the oracle’s write outcome, and log transaction cache-save failures.

**8. P2 — The replay does not satisfy the documented differential-state gate.**  
[timekeeper_replay.rs:89](C:/Users/jdlien/code/ak820-pro/ak820-agent/tests/timekeeper_replay.rs:89), [CLOCK-PARITY.md:190](C:/Users/jdlien/code/ak820-pro/plans/AK820-AGENT-CLOCK-PARITY.md:190)

Each learned line creates a new scheduler, supplies an invented preceding sample with the same period, and injects the logged old bias. State and cache output never flow into the next recorded sample.

A broken learner that establishes its first baseline but never advances it would still pass this replay: every case exercises only its first two calls. Failed cache writes—the preceding finding—are not replayed.

The precision allowances are reasonable for their limited purpose. The 5 ms scan searches within the printed second and checks both rounded outputs. Assuming `ref_state=2` on learned lines is justified, but cannot validate that gate’s negative cases.

The interval replay **does constrain the choice**: its timing allowance cannot hide replacing 180 with 300. I independently counted 171 applicable intervals, including 12 fast intervals; their actual gaps exceed the selected interval by 0–4 seconds.

**Fix:** Retain these useful component checks, but add sequential differential replay comparing resulting state and serialized cache, including failures and missing data.

**9. P2 — A failed text push suppresses the playback push for that poll.**  
[agent.rs:484](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:484)

An ordinary text timeout returns from `cycle()` before playback is attempted. Python catches the text failure and still attempts playback independently.

With repeated text failures and working playback commands, Rust lets the playback display expire. `media.rs` explicitly promises playback “whatever happened above,” which the caller does not implement.

**Fix:** Preserve the text retry state while separately attempting playback when the transport remains usable; retain the special `Stuck` policy.

**10. P2 — The presence error plumbing deferred to phase 4 is still unfixed.**  
[device.rs:354](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/hid/device.rs:354), [agent.rs:131](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:131)

`open_board()` still returns the last candidate’s failure.

For example, the raw interface opens but fails its capability check; subsequent keyboard collections fail to open. The daemon receives `Open` and reports **busy**, losing the meaningful **refused/incompatible** result. Identification failures also still collapse into `Reject::Silent`.

The `Watch` tests inject already-classified errors, so they do not test this producer-to-consumer boundary. This is the earlier finding explicitly deferred to phase 4, now affecting its live consumer.

**11. P2 — The live text publisher still accepts another row’s echo as its acknowledgement.**  
[proto.rs:165](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/proto.rs:165), [agent.rs:507](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:507)

While awaiting `TEXT_SET_LINE` for row 0, a row-1 echo—or an echo containing different text—passes because only channel and command are compared.

The firmware preserves these request bytes, so this ambiguity is avoidable. The phase-1 audit specifically warned that this could not wait for phase-5 health decoding once two-row publishing went live.

**Fix:** Match the echoed row, icon and text payload; drain mismatches before advancing publisher state.

**12. P2 — `foreign_reports` loses failures and inconsistently counts stale reports.**  
[agent.rs:490](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:490), [agent.rs:504](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:504), [agent.rs:356](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:356)

Concrete cases:

- Row 0 drains foreign reports and succeeds; row 1 fails. `send()` loses row 0’s count.
- A request receives foreign reports and then times out. Its error’s discard list never reaches the status counter.
- Playback succeeds after discarding only pre-existing stale reports. `reply.drained.len()` incorrectly increments the foreign counter.

Consequently, zero does not establish absence of observed foreign traffic, and a positive value does not consistently mean foreign traffic.

**Fix:** Accumulate discards independently of success and classify them consistently.

**13. P2 — External interval input can abort the console-less daemon without logging.**  
[ak820-agent.rs:57](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/bin/ak820-agent.rs:57), [worker.rs:310](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/smtc/worker.rs:310)

`--interval inf` and sufficiently large positive numbers pass `secs > 0.0`, then panic in `Duration::from_secs_f64`. This occurs before normal daemon logging or mutex acquisition. A tiny positive value can instead round to zero and produce an effectively continuous polling loop.

Thread creation also uses `.expect("spawning the media thread")`; an OS failure aborts the entire release process without a log entry.

**Fix:** Use fallible duration conversion with a nonzero validated range, and propagate thread-creation errors to the log.

**14. P2 — The media interval controls clock cadence and can disable learning entirely.**  
[agent.rs:438](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:438), [agent.rs:455](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:455)

Run the daemon with `--clock --interval 120`. The clock is examined only after each media sleep. Every subsequent loop gap exceeds 60 seconds, so every sync is classified as `wake`; each merely replaces the learner baseline. Periodic learning never fires.

Even independently of that option, `last_tick` measures from the start of work, whereas Python sleeps 15 seconds after finishing it.

**Fix:** Schedule the clock independently of the media interval and preserve the oracle’s placement of the loop delay.

There are also several **P3** corrections:

- [agent.rs:417](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:417): a first SMTC poll taking more than two seconds still causes the initial idle `CLEAR`. The grace reduces the blink; it does not guarantee the first push is real state.
- [build.rs:13](C:/Users/jdlien/code/ak820-pro/ak820-agent/build.rs:13): watching only Git metadata misses an uncommitted source edit after a clean build. Rebuilt code can retain a clean `git describe` without `-dirty`.
- [logfile.rs:46](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/logfile.rs:46): a persistent rename failure—such as a locked `.1` destination—is ignored while appending continues. Rotation works normally, but the claimed size bound does not survive rotation failure.
- [scheduler.rs:334](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/scheduler.rs:334): normalizing nominal period `0` into `None` preserves gate truthiness but changes the next hold log from Python’s `P 0 -> …` to `P None -> …`.

What I verified and found sound:

- Configuration Manager discovery opens nothing; controller IDs use its sorted paths. Normal handles close before loop and enumeration-settle sleeps.
- The pure scheduler’s constants, trigger precedence, printed-`before` comparisons, arithmetic, banker's rounding, seed wrapping and ordinary missing-status behavior match Python.
- Publisher text state advances only after all text reports succeed; normal change/keepalive decisions and report splitting match.
- The Rust mutex implementation checks `ERROR_ALREADY_EXISTS` correctly, closes rejected/partial claims, and fences the normal Python media instance.
- Task XML matches the pinned settings. Current COM lifetimes and apartment balancing are sound; an empty registration user VARIANT permits the XML principal to supply the account. [Microsoft security-context contract](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks).
- Status replacement and normal log rotation use appropriate file replacement operations. Cargo.lock is committed, workflow working directories apply `crt-static`, and the existing x64 binaries have the intended subsystems with no VC++ runtime DLL imports. Clean-machine execution remains unverified.
tokens used
217,770

```
