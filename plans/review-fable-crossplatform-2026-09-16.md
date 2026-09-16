# Fable review of the cross-platform plan's 2026-09-16 changes

`claude -p`, model **claude-fable-5-1**, `--permission-mode plan` (read-only),
`--add-dir /Users/jdlien/code/streamdeck-now-playing`, `< /dev/null`, run
2026-09-16 against `91a79a1` plus two uncommitted edits (the `--live` flag in
`scripts/agent_overhead_macos.py` and the Phase 5a row).

**Scope was deliberately narrow:** only what changed that day
(`git diff 9f5f7d3..HEAD -- plans/ scripts/`), not what the
[2026-09-10 review](review-fable-crossplatform-2026-09-10.md) settled. The brief
named eight areas to press on: 4a coexistence under exclusive macOS HID,
per-interaction IOKit opens against the ≤1% target, the media failure policy,
the S1b canary against G-B, Phase 0's statistics, the overhead method,
media-first's hidden dependencies, and anything the day's edits left
contradictory.

Findings 2, 3 and 6 were re-verified at source before acting on them.
Disposition of every finding is in the plan's second *Review disposition*
section.

## The report, verbatim

Review complete. Every claim below was checked against the source it cites, not the plan's paraphrase. Findings settled on 2026-09-10 are not re-reviewed.

## Ranked findings

**1. High. Phase 0's window gate cannot fail as written.**
- **Claim:** "One window outside [min, max] extends the run, does not fail" names no stopping rule and no failure condition. The 6% figure is for one statistic on independent windows; the gate checks about six statistics on autocorrelated windows.
- **Evidence:** Plan line 544 is the gate text. `scripts/clock_log_windows.py:212-229` prints twelve per-window statistics. The 32 baseline windows are consecutive 4 h slices of one slowly drifting learner, so adjacent windows are not independent draws. 2/(n+1) = 6.1% is per statistic. Across median, p95, worst and bias spread it is roughly 15–25% per window before autocorrelation.
- **Consequence:** At about one window per 4 h 10 min, one healthy run in four or five hits "extend", and no number of windows can ever fail the phase. A real p95 regression reads as "extend, extend, extend".
- **Fix:** Run at least 3 windows (overnight). Name the deciding statistics: |before| p95 and worst; failed, unmeasured and warn must be 0; bias spread at or under the baseline max. Fail if 2 of the first 3 windows exceed the baseline max on p95 or worst, or any window has a failed, unmeasured or warn sync. Extend at most once. Add a slip column to the comparator (|before| within 1000 ± 60 ms with a small `after`) so condition (c) is mechanical rather than eyeballed.

**2. Medium. 4a's coexistence gate compares against a baseline taken at a different HID cadence, and measures only one side.**
- **Claim:** The neutral loop opens the board every 3 s in every media state because the playback readout is always sent. Today's macOS agent opens once per 30 s while idle. Which side logs a collision depends on the seize direction S2 has not yet measured.
- **Evidence:** `ak820-agent/src/media.rs:63-72` puts a playback in every Plan and `agent.rs:385` sends it every cycle. `hostagent/nowplaying-macos.sh:139-145` pushes playback only while playing, and line 148 keepalives every 30 s. `agent.rs:313-327` adds a health open every 300 s the Mac never had. Plan line 548 says the two "contend exactly as today's two Python agents do". Plan lines 341-344 admit the seize direction is unmeasured. The timekeeper retries a failed sync 15 s later (`hostagent/ak820-timekeeper.py:273-280` and `:295`), so a collision costs one `[rc=1]` line, and each sync makes 2–3 seizes (lines 187, 169, 234).
- **Consequence:** Idle-state opens rise about tenfold. If a live non-seizing open refuses a seize, the timekeeper's failure rate rises from roughly 1 per 500 syncs to 1 per 50 and a 50-sync gate is a coin flip. If a seize evicts the daemon instead, the timekeeper never logs a failure, the gate passes without measuring coexistence at all, and the daemon eats every collision.
- **Fix:** Record S2's direction in the 4a row and gate the side that loses. Add the daemon's own push and playback warning counts and `board:` transitions per 50 syncs. Match media state, as the Phase 0 row already does. Either skip the idle playback readout on macOS, since a repeated zero is a firmware no-op the bash never sent, or state the tenfold idle cadence and its expected collision rate.

**3. Medium. The media failure policy blanks the LCD on the helper's designed recovery path and contradicts itself on "dead".**
- **Claim:** "Dead or fatal" fails immediately, but "inside its restart backoff" (which is dead) fails only after 30 s of silence. The six-timeout exit is both dead and fatal, so the daemon publishes idle, the band clears, and 2 s later the track returns.
- **Evidence:** Plan lines 376-379. `nowplaying-mediaremote.m:125-138` exits with `fatal` after six 1.5 s timeouts, and lines 88-91 call that the designed recovery. `MediaRemoteHost.cs:67-68` restarts after 2 s, and line 76 sets the sibling's silence limit at 60 s, "generous on purpose". `agent.rs:274-285` turns failed into idle, which is a CLEAR. `display.c:1684` sets the expiry at 180 s, and `media.rs:35` the keepalive at 30 s. `MacMediaSessionService.cs:404-414` keeps the last snapshot through exactly this. The heartbeat shares gQueue with calls that can block it 4.5 s per publish (`.m:94`, `:98`, `:338-339`), so the worst inter-tick gap is about 20 s and a 30 s threshold leaves about 10 s of margin on a machine that was swapping.
- **Consequence:** Every wedged-MediaRemote recovery paints CLEAR then two SET_LINEs. That is the double flash the bash script's comments exist to avoid. A false silence trip costs the same plus a kill.
- **Fix:** One rule. Failed means no line read from the helper for N seconds, with death and `fatal` starting that clock rather than tripping it. N of 45–60 s is still far inside the 180 s expiry, and the keepalive re-asserts the last text meanwhile. Delete the "helper is dead" clause. S1 implements this, so fix the wording before S1.

**4. Medium. S1b's limits contradict G-B's gate, and G-B is untestable while MediaRemote is healthy.**
- **Claim:** G-B requires a revocation to surface "within one poll interval". S1b asks AppleScript at most once per 60 s, only while Spotify or Music runs, and only when MediaRemote is null. With MediaRemote healthy nothing sends an Apple event, so a revocation is invisible. When the canary does run, the bound is 60 s.
- **Evidence:** Plan lines 581-583 and 541. The earlier review's finding 11 raised "G-B only fires if the AppleScript path is in use". The disposition at plan line 697 addressed only signing.
- **Consequence:** The one macOS defect the plan still claims to close has a gate that cannot be run as written. There is also a false positive: the canary compares null MediaRemote against `player state = playing`, and a client that reports playing without owning a local session would log a "refusal" and "switch primary" with no stated way back. Spotify Connect playback on another device is the case to verify.
- **Fix:** Restate G-B as "surfaces within 60 s of the next Apple event, and the test forces one". In S1b, bound each `osascript` call (the bash has no timeout), never overlap canaries, make the primary switch reversible, and log the process-table decision.

**5. Medium. 4a's rollback fence does not exist on macOS.**
- **Claim:** The installer script cannot install or remove one agent. The 4a row says the daemon "unloads" the nowplaying LaunchAgent without saying how. The only thing that stops the bash running beside the daemon is the bash's own mkdir lock, which the daemon's single-instance guard does not hold.
- **Evidence:** `hostagent/install-agents.sh:22`, `:50-57` and `:81-93` always act on both agents, so a rollback restarts the timekeeper and starts a new run in the log the 4a gate reads (`clock_log_windows.py:53`, `:125-127`). The nowplaying plist has RunAtLoad, KeepAlive and a 30 s throttle. `nowplaying-macos.sh:22-33` keys the lock on a pid. `ak820-agent/src/instance.rs:7-12` shows the Windows daemon holds the Python's mutex name for exactly this reason.
- **Consequence:** A `bootout` alone leaves the plist in place. At the next login launchd starts the bash, its lock is stale, and two writers push the LCD, each seizing the device and breaking the other's opens.
- **Fix:** 4a's install does `bootout` plus `launchctl disable` on the nowplaying label and holds the mkdir lock with its own pid. Rollback is `enable` plus `bootstrap`. Add an `--only` flag to the installer or write the manual rollback into the 4a row.

**6. Medium. The "after" measurement aborts or under-reports on helper restarts, and the daemon's silence rule can cause one at every resume.**
- **Claim:** The `--live` flag takes a fixed pid. The helper is designed to restart. A restart inside a window raises at the window's end and aborts the run, and the new helper's CPU is unmeasured. Freezing the daemon for 240 s makes its silence detector see 240 s without a line at resume.
- **Evidence:** `scripts/agent_overhead_macos.py:61-65` raises when the pid is gone, line 133 reads it after the window with no guard, and lines 119-122 send the stop. `nowplaying-mediaremote.m:133-136` is the exit. The uncommitted 5a row is plan line 549. Plan lines 411-418 record that trustd and Spotlight were busy on the "before" day; the "after" will run on a quiet machine, so the knock-on comparison is not like-for-like.
- **Consequence:** The measurement for the owner's stated priority either crashes or flatters the port.
- **Fix:** Resolve live children dynamically per window with `proc_listchildpids`, summing self CPU of every live child and logging a restart. In S1, measure silence from the reader's last read and let the reader drain the pipe before the watchdog judges. Publish per-daemon run-minus-pause deltas from the jsonl.

**7. Low. The IOKit per-interaction read path is not designed, and its cost and leak behaviour are gated nowhere before 5a.**
- **Evidence:** Plan lines 271, 330-339 and 543. IOKit delivers input reports only through a run-loop or dispatch-queue callback, so each open is create, open, schedule, wait, unschedule, close and release, about 28,800 times a day.
- **Consequence:** The 1% target is credible, since Windows already does discovery plus CreateFile per cycle. But one missed release per cycle is a slow leak the 5b memory gate sees only after days.
- **Fix:** S2 adds one persistent reader thread, 10,000 open-exchange-close cycles with RSS and Mach port count flat, and the CPU per cycle recorded as 5a's budget.

**8. Low. Phase 0's matched conditions omit the learner's cache and the board's thermal state.**
- **Evidence:** The earlier review's finding 8 on the cache path. `agent.rs:588-611` seeds only while the cache lacks a bias. `ak820-timekeeper.py:53-63` records drift with LED load and room temperature.
- **Fix:** Add the same cache file (no seed line in the log), the same RGB effect and brightness, and the slider on cable.

**9. Low. "Up to 7 osascript per poll" is the wrong correction. The maximum is 8.**
- **Evidence:** `nowplaying-macos.sh:110-118`. Spotify running but stopped falls through to Music: two running checks, two player-state calls, four getters. Plan line 398 and `BACKLOG.md:451-453` say 7, "verified against the script".
- **Fix:** "Up to 8 with both apps running and Spotify not playing; 6 in the common case."

**10. Low. Small items.** The `ak820 clock` refusal while the timekeeper runs needs a macOS check via `launchctl print`, assigned to no phase. The macOS single-instance guard is assigned to no phase. The overhead script wraps the pid counter at 99998 where macOS wraps at 99999, harmless since the number is declared unusable.

## What is sound

- Media-only mode sends no clock transaction of any kind. Verified at `agent.rs:241-252` and `:302-311`.
- The timekeeper retries a failed sync in 15 s, not a full interval.
- The comparator parses the Python log. Its regexes match the timekeeper's sync, hold and learned line formats.
- The claim that the gremlin binary is today's daemon code holds. The range touches only the manifest, lockfile, INSTALL.txt and the CLI binary.
- Nine files reference the Windows crate and none carries a cfg. The status file's count is right.
- The protocol drift is real. The `now` message carries `elapsedAt` and `playing`, and the header lists neither.
- Per-interaction opens are the existing Windows design, and the health tool's retry loop is as described.
- The `--live` flag adds the right number, and the reasoning that the helper's pause-window CPU is not a baseline is correct. SIGSTOP is a fair pause for the bash agent.
- The 19.7% child-CPU figure is exact kernel accounting and is the defensible "before".
- One neutral failure policy with backend-defined "failed" is the right shape.
- Preferring `IOServiceGetMatchingServices` over the HID manager, and detecting players from the process table by exact executable path, are both sound.

## Verdict

**Nothing blocks starting S1.** Fix finding 3, and the S1 half of finding 6, before S1, since S1 implements the supervisor semantics and both are paragraph edits. Findings 1 and 8 go before Phase 0. Findings 2 and 5 go before 4a. Finding 4 goes before S1b. Finding 7 belongs inside S2. Findings 9 and 10 can wait.

The full review is also at `/Users/jdlien/.claude/plans/you-are-reviewing-a-async-metcalfe.md`.

🎯 **COMPLETED:** Reviewed the finalized cross-platform plan and found ten issues, one of them high severity.
