# Fable audit of macOS 4a, 4b and Phase 2 (`e07fdfa..057b141`)

`claude -p`, model **claude-fable-5-1**, `--permission-mode plan` (read-only),
run 2026-09-16 from about 22:15 while the daemon owned the clock live. The
brief ruled out opening HID, running any `ak820`, `ak820-agent` or `ak820ctl`
binary, `osascript`, perl, and every `launchctl` command except `print` and
`print-disabled`. It asked whether the daemon can be left owning the clock
unattended.

## Disposition

**Verdict accepted: safe overnight.** Every finding was checked at source.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | Med | A failed `--clock` reinstall could restart the old clock-owning daemon **and** the timekeeper; and `put_back` re-bootstrapped the new plist while saying "previous" | **Fixed in two commits.** The first half, counting an already-disabled timekeeper as retired by this run, was found independently while preparing the 22:20 reinstall and fixed in `f5121e5`; the audit read the code before that commit. The rest is fixed now: `put_back` writes the previous plist's text back before bootstrapping it, and never restarts the timekeeper beside a previous daemon that owned the clock |
| 2 | Low | Deaf-object retirement had no rate limit: about 30 MB a day for a board answering one request in four | **Fixed:** at most 6 retirements per hour; past the cap the object is kept and the cap is said once |
| 3 | Low | The stalled-media-thread judgement could never fire at media intervals of 20 s or more | **Fixed:** the threshold is the larger of 20 s and two intervals plus 8 s; test |
| 4 | Low | A check-then-bootout window of about 50 ms on `install --clock`; `ak820ctl`'s cache write is not atomic | **Accepted as benign**, as the audit judged: the SET is one report, and a truncated cache costs a 15-minute reseed |
| 5 | Low | `running_named` read a process-table error as zero processes; hand-run owners are invisible | **Fixed the fail-open:** an error now refuses every ownership check. Hand-run owners stay visible only through `ak820ctl`, as on Windows |
| 6 | Low | SIGTERM can land mid-transaction | **Accepted:** verified benign by the audit (atomic SET, tmp-and-rename cache) |

**Worth recording from the audit's timeline:** both deaf-object episodes began
while another process was opening the device. The first coincided with the
Python timekeeper's `hid.enumerate` every 15 s, and the second with the Phase 2
paired `ak820 clock` and `ak820ctl` reads. That supports, without proving, the
lost-queue-signal theory in `device.rs`.

## The report, verbatim

Audit done. Nothing was modified, opened or spawned beyond `cargo check`, `cargo test`, `cargo clippy`, the Windows-target check, `launchctl print`/`print-disabled`, git, grep, sysctl and ps. All clean: 343 lib tests plus 13 integration tests pass, clippy has zero warnings, the Windows target compiles with tests.

Live facts checked first: the daemon runs with `--clock` under `ProcessType Standard`, spawn type daemon, KeepAlive; the timekeeper and bash labels are `disabled` in launchd's persisted state and not loaded; the daemon was restarted at 22:20:03 during the audit and its first sync was clean. Since it took the clock: 7 syncs, 0 failures, 0 foreign reports.

## Findings

**F1. Medium. A failed `--clock` reinstall over a `--clock` install can start both the old clock-owning daemon and the Python timekeeper.**
Evidence: `install.rs:263-268` sets `retired_timekeeper` whenever the timekeeper plist exists, even when the previous `--clock` install already disabled it, which is every future upgrade. `put_back` (`install.rs:198-223`) then bootstraps the old plist, which still carries `--clock` because `previous` is true, and also enables and bootstraps the timekeeper. The comment at lines 214-215 states the opposite of what the code does. Triggers are any failure at line 270 (an `ak820ctl` alive for 15 s), 273 (a transient launchctl error in `clock_is_ours`) or 290. The daemon's own `clock_is_ours` (`daemon.rs:85-89`) runs tens of milliseconds after its bootstrap and races put_back's enable and bootstrap of the timekeeper. If the daemon checks first, both run. Neither re-checks at runtime.
Consequence: two clock writers, both learners corrupted, each GET able to take the other's reply. The installer does print "the Python timekeeper was started again", so an attentive owner would see it.
Fix: read `is_disabled(TIMEKEEPER)` before disabling and set `retired_timekeeper` only if it was loaded or enabled. In put_back, skip the timekeeper restart when `previous` holds and the old plist text, captured before line 289, passes `plist_owns_clock`. Separately, at line 293 put_back re-bootstraps the new plist rather than the previous daemon, and its message says otherwise.

**F2. Low. The deaf-object retirement has no rate limit.**
Evidence: `device.rs:76-90` resets the count on one heard report, so a fresh object becomes eligible again after a single answer. `device.rs:344` sets only `abandoned`; no `Error::Stuck` reaches `Watch` (`agent.rs:156,164-166`), so opens never pause. Each retirement leaks the registration page from S2 plus ctx and buffer (`device.rs:239-244`).
Consequence: a board answering about one request in four would cost roughly one page per 12 s, about 30 MB a day. Not observed; overnight risk small.
Fix: count retirements and past about ten per hour either stop retiring or report `Abandoned` to `Watch`.
Verified sound around it: retirement only happens in `Device::drop`, one `Device` per board at a time, and every board interaction runs on the one loop thread, so a clock transaction (one `Device` for five GETs, the SET and the verify, `transaction.rs:347-432`) cannot be retired mid-way. Drain-only interactions count for nothing, a drain that heard resets, and a write that timed out before leaving does not set `wrote` (`device.rs:407`, `exchange.rs:397-415`).

**F3. Low. The stall judgement is off whenever the media interval is 20 s or more.**
Evidence: `media/mod.rs:543-544` requires the daemon's previous `latest()` within 20 s, but `latest()` runs once per media interval (`agent.rs:263,289`) and `--interval` accepts up to 3600 (`daemon.rs:64`). Above 20 s the dead-thread detection from F10 never fires.
Consequence: none for the owner, who runs 3 s.
Fix: judge against the larger of 20 s and twice the interval, passing the interval into the source.

**F4. Low. Check-then-bootout window on `install --clock`; the C's cache write is not atomic.**
Evidence: `install.rs:257` checks for `ak820ctl` and then boots out; the timekeeper loop (`ak820-timekeeper.py:265-296`) can spawn one in the milliseconds between, and launchd kills the process group after SIGTERM. `ak820ctl.c:243` writes the cache with `fopen(…, "w")`, so a kill mid-write can truncate it. The daemon's loader (`cache.rs:325-330`) then falls back to defaults and reseeds over about 15 minutes. The SET is a single report, so the board is never half-set, and line 270 re-checks for 15 s.
Consequence: about 50 ms in every 300 s per install. Benign.
Fix: none required.

**F5. Low. Hand-run clock owners are invisible, and `running_named` fails open on error.**
Evidence: `daemon.rs:104-131`, `cli.rs:281-321` and `install-agents.sh:88` see the launchd label, the plist text and `ak820ctl` by basename. A timekeeper started from a terminal is invisible between syncs, and so is a hand-run `ak820-agent --clock` to `ak820 clock`. `process.rs:18-21` reads a `proc_listallpids` failure as zero processes. The 8,192-pid buffer cannot truncate on this Mac (`kern.maxproc` is 8000).
Consequence: same shape as Windows, which trusts the task and `ak820ctl.exe`. Parity, not a regression.
Fix: treat a negative return as an error; optionally count `ak820-agent` too.

**F6. Low, verified benign. SIGTERM can land mid-transaction.**
There is no signal handler, so bootout, uninstall and logout can kill the daemon between any of the eight requests. The SET is atomic on the board and the Rust cache save is tmp plus rename (`cache.rs:332-339`). The worst case is one lead or bias learn lost.

## Verified sound

- **Ownership order.** `install` without `--clock` boots the daemon out at line 225 and waits for the label to vanish, which launchd does after the process exits, then starts the no-clock daemon at 292 and only then the timekeeper at 302. `uninstall` removes the daemon before enabling the timekeeper.
- **Fail-closed checks.** `print_checked` distinguishes exit 113 "Could not find service" (verified live) from other errors, and `is_disabled` parses this macOS's `=> disabled` form. An unreadable disabled state in the give-back path starts nothing.
- **Login.** Only the agent loads; `install-agents.sh` refuses before touching anything, and its timekeeper check runs first.
- **The plist.** Standard, KeepAlive, 30 s throttle, 5 s exit timeout, no Nice or low-priority I/O, and the process group dies with the daemon so the perl helper cannot orphan. App Nap does not apply to a non-app launchd agent (inference). Timer coalescing only delays the 500 ms slice; the transaction stamps its own times.
- **Sleep and wake.** Rust's `Instant` on macOS excludes sleep, as the Python's monotonic clock did, so the learner's elapsed semantics match. `due()` uses wall time for the 60 s wake gap and `learn()` returns Baseline on a wake. Not yet exercised live; the plan lists it as owed.
- **The two-poll rule.** Helper restarts cannot defeat it: the shared liveness clock is deliberately not reset per run (`helper.rs:140-142,317-319`).
- **Time zones.** The live system change at 22:08 and 22:11 shows `localtime_r` following `/etc/localtime`, and the one-hour residuals were declined by the 400 ms gate (bias stayed +7). The child-process TZ tests are correctly isolated and honest about what they cannot cover.
- **`ak820 clock`** is read-only and refuses on a loaded timekeeper, a `--clock` daemon, a running `ak820ctl`, or an unanswerable launchctl.
- **Replay corpus.** The early edge is exact, and the late allowance cannot mask a wrong 180-versus-300 s choice in either direction.
- **Windows.** No shared or Windows source changed in the range. The new replay tests are platform-neutral and `lines()` tolerates CRLF.
- **The deafness events** at 20:55 and 21:36 both began while other processes were opening the device: the timekeeper's `hid.enumerate` every 15 s, and the paired `ak820 clock` and `ak820ctl` reads of the Phase 2 live half. Both peers are gone overnight. This is inference from the timeline, not proof of mechanism.

## Verdict

Yes. It is safe to leave the daemon owning the clock unattended overnight. Nothing found can start a second clock writer without someone running an install command or launchctl by hand. Before the next `ak820 install --clock` upgrade, fix F1, or at minimum make sure no `ak820ctl` is running and read the installer's output. Cap F2 before a multi-week run.
