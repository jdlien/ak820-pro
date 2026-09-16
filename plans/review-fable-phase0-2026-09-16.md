# Fable audit of Phase 0 (`a46e770`, the platform seam)

`claude -p`, model **claude-fable-5-1**, read-only, run 2026-09-16 against
`a46e770` on a clean extraction of that commit. The brief asked whether the
commit is safe to deploy to gremlin for Phase 0's live gate, and to look for any
Windows behaviour change beyond the plan's definition of observable (wire bytes,
status-file keys, log grammar, timing statistics). It opened no HID device.

## Disposition

**Verdict accepted: safe to deploy.** All three of the auditor's pre-deploy
conditions are met, and every finding is dispositioned. Findings 1, 2, 3 and 5
were reproduced before fixing. Finding 4 was checked against the pre-refactor
source (`windows::core::Error::from_hresult(HRESULT::from_win32(ERROR_OPERATION_ABORTED))`).

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | Med | `--gate` grades the first 3 windows of the whole log, which on gremlin is the baseline | **Fixed**: `--gate` refuses without `--since`, and the verdict names the graded windows' first and last timestamps |
| 2 | Med | The verdict never reads the slip column | **Fixed, and a rule decided**: the baseline had 0 slips in 1,614 syncs, so **2 or more slips across the graded windows FAIL**, and **exactly 1 turns PASS into REVIEW** (read it by hand). One cannot convict the refactor, since four slips are on record from every host. The verdict line prints the count. `--gate` also refuses `--keep-slips` |
| 3 | Low | The extension checked bias spread on windows 1–3 only | **Fixed**: recomputed over all six |
| 4 | Low | The cancelled-write log line lost its `(0x800703E3)` suffix | **Fixed**: the code is back in the text |
| 5 | Low | A neutral test wrote `Z:\no\such\dir\agent.log` into the crate on macOS | **Fixed**: a regular file used as a directory, unwritable everywhere; the stray file removed |
| 6 | Low | The clock cache reads `USERPROFILE` before `HOME` in a shared file | **Deferred to Phase 2**, where the macOS clock is built; correct on both platforms today |
| 7 | Low | The `compile_fail` doctest carried no error code | **Fixed**: `compile_fail,E0277` |

**Pre-deploy condition 3, the PE subsystem, verified from CI's own artifact**
(run 35152152565, the `a46e770` build): `ak820-agent.exe` reads subsystem **2,
`WINDOWS_GUI`**, and `ak820.exe` subsystem **3, `WINDOWS_CUI`**, straight from
the optional header. The `cfg_attr` move did not reopen the console flash.

**Found while checking it:** the plan's efficiency row gave the Windows binary as
117 KB with a ≤ 150 KB bound. CI's builds are **408,576 bytes before Phase 0**
(`e8a4c16`) and **409,600 after**, so Phase 0 added 1 KB. The 117 KB was measured
on 2026-09-05, before the clock and the remaining phases landed. The row is
corrected in the plan, and the bound restated against today's size.

## The report, verbatim

The audit is complete. Nothing opened a HID device and nothing in the repo was modified. Verification ran on a clean extraction of the exact commit in `/tmp/ak820-audit`.

## Findings, most severe first

**1. Medium. `--gate` grades the first three windows of the whole log, and on gremlin that is the baseline.**
- Evidence: `gate_verdict()` in `scripts/clock_log_windows.py` takes `rows[:3]`, and `rows` is every window in the file in order. The daemon log rotates only at 1 MB, so the 09-09 to 09-15 baseline sits in the same file the phase-0 daemon will append to.
- Demonstrated on a synthetic log with a pre-refactor run, a restart, and a post-refactor run. Without `--since`, the verdict printed PASS computed from the pre-refactor windows.
- Consequence: an overnight gate graded without `--since` reports the baseline's own pass as the refactor's.
- Fix: refuse `--gate` unless `--since` is given, or grade only windows after the last process-start line. Print the graded windows' first and last timestamps in the verdict line.

**2. Medium. The verdict never reads the slip column.**
- Evidence: `dirty()` is failed, unmeasured or warned, and `over()` is p95 or worst. The slip count is not consulted. Demonstrated with 21 slips across the three graded windows, against 0 in the 1,614-sync baseline. The verdict printed PASS and said nothing about them.
- The heuristic itself is sound. The 1000 ± 60 with |after| < 60 test fits all four recorded slips in `plans/BACKLOG.md`. It does not hide a systematic one-second error, because the verify GET would read `after` near ±1000, failing the after test, so that sync lands in worst and fails. What it hides is any refactor bug that reproduces the exact signature, such as a transient host clock read off by one second across a single transaction. That is the very contract flaw the backlog hypothesizes.
- Consequence: the statistic the baseline moved most decisively cannot fail the gate at any rate.
- Fix: print total slips in the verdict line. Decide as a plan-text change whether two or more slips across the graded windows fails or needs a human. At minimum print the count.

**3. Low. The extension path checks bias spread on windows 1 to 3 only.**
- Evidence: `spread_ok` is computed over the first three windows and reused for the six-window PASS.
- Fix: recompute it over all six before the final return.

**4. Low. The cancelled-write log message lost its `(0x800703E3)` suffix.**
- Evidence: the pinned windows-result crate renders `Error` as `message (0xCODE)`, so the old line ended in `(0x800703E3)`. The new text in `hid/exchange.rs` carries no code, and nothing reads the `code` field on the new error type.
- Consequence: grammar is intact, so this is inside the plan's definition, but the code is now kept nowhere visible.
- Fix: append the code to the message text. One line.

**5. Low. A neutral test encodes a Windows path and litters the crate on macOS.**
- Evidence: the unwritable-path test in `src/logfile.rs` writes to `Z:\no\such\dir\agent.log`. On macOS that is a valid relative filename. The test exercises the writable path, and the stray file now exists untracked in the crate directory with three lines from three runs.
- Fix: create a regular file in a temp dir and use it as a directory component, which is unwritable on every OS.

**6. Low. The clock cache reads `USERPROFILE` before `HOME` in a shared file.**
- Unchanged by this commit and identical on Windows. On macOS it works by fallthrough, correct by accident rather than by the seam. Phase 2 work, not now.

**7. Low. The `compile_fail` doctest carries no error code.**
- The path in `src/platform/windows/smtc.rs` is valid today, so it fails for the intended reason. A future path break would also pass. It runs only on CI's Windows job and is invisible on macOS. Fix: add `E0277` to the fence.

Noted, not findings: the Win32 error conversion now formats the system message eagerly at construction rather than at display, on the error path only. The device listing allocates strings per clock tick where it used to borrow. Both are negligible.

## Verified unchanged

- Daemon loop order in `agent.rs`: media cycle, clock tick, health, status write. The diff is purely platform substitutions and no line moved.
- Log grammar: the polling line still reads `polling SMTC every ...` through the constant, the board transition lines, every warn prefix, and the sync and bias lines are untouched.
- Clock seed `cid`: the same interface list joined with `|`, same function, same constants re-exported.
- Status-file keys untouched. Request timeout and drain budget moved with the same values. Exit codes, `bail`, argument parsing and `default_dir` are verbatim.
- Error semantics: the `Reject` type is matched only inside its own module and the device module. The `why` field is only ever rendered and renders identically. No code or HRESULT comparison on the new error type exists anywhere. The five HRESULT comparisons in the device and task modules happen before conversion. Presence classifies by variant only. A new test pins the display text equality.
- Trait defaults: identical bodies to the old device methods, same exchange functions and arguments, static dispatch through the same `Wire` impl.
- Tests: 305 before, 306 on Windows after. The host tests split four neutral and four Windows, the default-dir test moved, one OsError test was added. The native run on the exact commit passed 255 unit tests plus the three integration suites. The Windows all-targets check on the exact commit is clean with zero warnings. `Cargo.lock` is unchanged so the locked CI build holds.
- Moved with zero diff: caps, instance, process, task. The Windows host file is the old implementation plus its four tests verbatim.
- Seam rule: no `#[cfg]` in shared files beyond test gating and the declared attribute on the daemon binary. The macOS `struct tm` includes the two Darwin trailing fields, so it is laid out correctly. The macOS stubs refuse honestly with exit 2.
- Slip exclusion and the published baseline: worst max is 27.6 ms in every one of the 32 windows, so no reading near 1000 ms existed and the 32 / 23.9 / 27.6 figures are unchanged under the new default.

## Verdict

Yes, safe to deploy for the live gate. The Rust side carries no Windows behaviour change beyond the one admitted string. Before the gate result is read, three things must happen:

1. Run `--gate` only with `--since` set to the reinstall time, or fix finding 1 first.
2. Print the slip count in the verdict and decide the slip rule.
3. Confirm the built daemon executable's PE subsystem is still GUI. The attribute is now behind `cfg_attr`, `cargo check` does not link, and a console flashing at logon is the exact bug the separate binary exists to prevent.

Findings 3 to 7 are housekeeping for the next commit, not blockers.
