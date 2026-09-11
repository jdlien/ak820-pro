# Fable review of the cross-platform agent plan — 2026-09-10

`claude -p`, model **claude-fable-5-1**, `--permission-mode plan` (read-only:
may read and search, cannot modify), `--add-dir
/Users/jdlien/code/streamdeck-now-playing` so it could verify the sibling
project's claims at source rather than trust the plan's summary of them.
Reviewed `plans/AK820-AGENT-CROSSPLATFORM-PLAN.md` at commit `7698c2b`.

Run against **Fable rather than codex**: the codex account hit its GPT-6 usage
limit and produced zero output. Two operational notes for the next run, both of
which cost time here:

- **`codex exec` exits 0 on a usage-limit failure.** The harness recorded
  `exited with code 0` for a run that did no work; the only signal is parsing
  output for `ERROR:`.
- **Both CLIs block on stdin even when the prompt is an argument** — codex
  prints `Reading additional input from stdin...` and waits forever. Use
  `< /dev/null`.

Unlike the codex phase-1/2 runs, this reviewer's shell worked, so it read
sources directly and cites file:line throughout. It did not build, run tests,
or touch hardware.

**Seventeen findings, five High.** The two most consequential were independently
re-verified before acting on them:

- **Finding 1 confirmed.** `fc70de4` in the sibling repo landed **2026-09-10
  17:17**, thirty minutes after this plan's 16:47 mtime, and rewrote 205 lines
  of the helper. The Music.app "exemption" the plan built its router on was a
  loader-lock deadlock in the helper's own constructor, not Apple behaviour —
  `CFRunLoopRun()` from a dylib initializer holds dyld's loader lock, and
  Music's artwork decode needs `dlopen`. MediaRemote now answers for Music like
  everything else. The plan's S1 gate could only pass by reintroducing the bug.
- **Finding 5 confirmed.** This repo's own files state the raw-HID interface is
  **EXCLUSIVE on macOS** and that it "has bitten twice", the second time
  masquerading as a firmware fault (`hostagent/nowplaying-macos.sh:13-17`,
  `hostagent/install-agents.sh:15-16`). CLAUDE.md's "shareable, not exclusive"
  was measured on **Windows** and the plan carried it to macOS unexamined.

Disposition of every finding: to be recorded in the plan itself before any code
is written.

## The report, verbatim

Review complete. Findings below, ranked by severity, with the four owner questions mapped first.

**On the four questions.** Q1 seam: the Windows ranking survives intact, but the trait's failure-policy contract is undefined and the two platforms currently want opposite policies, see finding 9. Q2 MediaRemote: the fallback is real for helper death but wishful for the likeliest revocation shape, and the plan's S1 gate is now inverted by the sibling's own fix, see findings 1, 2 and 7. Q3 clock gate: it cannot see a self-consistent wrong time, see finding 4. Q4 phase 0: as written it cannot fail and cannot be run where the author works, see finding 3.

## Ranked findings

**1. High. S1's gate is inverted by a sibling correction that landed thirty minutes after the plan was saved.**
- Plan lines 114 to 119, 302 and 308 state that Music.app's metadata call never returns and require "the Music.app stale case reproduces".
- The sibling's commit fc70de4 at 17:17 on 2026-09-10 diagnosed that hang as a loader-lock deadlock in the helper's own constructor, since fixed. MediaRemote now answers for Music. See `docs/macos-port-plan.md:97-114`, `nowplaying-mediaremote.m:27-52`, and `MacMediaSessionService.cs:19-27`. The plan file's mtime is 16:47.
- README §14.2 was not touched by that commit and still describes the exemption at `README.md:972-977`, so the plan's two cited sources now contradict each other.
- Consequence: a "reproduces" gate can only pass by reintroducing the deadlock. The router shape in the plan, Music to AppleScript, is not what ships; AppleScript is now the fallback for a stale provider or an unhealthy helper. If the dylib is reimplemented rather than vendored, "the constructor must return" at `nowplaying-mediaremote.m:36-52` must be carried as a load-bearing constraint.

**2. High. The AppleScript fallback does not cover the most likely revocation shape.**
- Risk table line 344 says the router "already falls back to AppleScript". It routes on `bundle` and `stale` at `MacMediaSessionService.cs:246-249` and on helper health at `MediaRemoteHost.cs:120-126`.
- An ordinary process on 15.4+ gets an empty dictionary and `isPlaying = NO`, per `macos-port-plan.md:60`. If Apple extends that to perl, the helper stays alive, ticks every 15 s, and emits `bundle: null` forever. Nothing routes anywhere. It is indistinguishable from idle, and for browsers there is no fallback at all.
- Missing gate: MediaRemote refusal must be visible, the same standard G-B applies to TCC. A cheap canary exists: when MediaRemote reports nothing but AppleScript's `player state` says Spotify or Music is playing, log the refusal and switch primary.

**3. High. Phase 0's gate cannot fail as written, and nothing says where it runs.**
- Line 305 gates on test counts. The 305 unit tests never touch Win32 and the count will legitimately change when `host.rs` tests move under `platform/windows/`. CI at `.github/workflows/agent.yml:25-41` runs on windows-latest with no board.
- "Identical" is literally unachievable: `hid::Error::Open { source: windows::core::Error }` at `hid/mod.rs:63-76` must become neutral, so log text changes. The gate should define observable: wire bytes, status-file keys, log grammar, timing statistics.
- The Windows phase-0 evidence was five CLI commands on the board, `AK820-AGENT-PLAN.md:46-48`, and the takeover table at `AK820-AGENT-PLAN.md:265-275`. This phase 0 asks for neither. Reinstalling from the phase-0 build and repeating that table against the pre-refactor log over the same duration is the evidence that could fail.
- The plan never says where Windows builds happen. `.cargo/config.toml` pins static CRT to the msvc target only; cross-compiling from the Mac is unaddressed.
- `agent.rs`, 802 lines, is where all five traits meet and it appears nowhere in the diagram at lines 184 to 196. It holds Windows paths at `agent.rs:193-201` and a Windows error in its tests at `agent.rs:755`.

**4. High. The phase 2 gate cannot see a self-consistent wrong time.**
- Both the GET's residual and the SET's payload go through `host.local()`, at `transaction.rs:174` and `transaction.rs:205-208`. A macOS `local()` off by an hour yields a zero residual and a board an hour wrong. That is exactly the failure line 50 names.
- Windows covered this with two hourly sweeps across 2026 to 2099 against the oracle CRT, `host.rs:294-347`. Those tests cannot compile on macOS and the plan asks for no equivalent against libc `localtime_r`, which is what `ak820ctl.c:159`, `:198` and `:256` call.
- "Captured replies decode identically" never exercises localtime: the oracle's decode mode takes `host_mid_sod` as an argument, `scripts/clock_oracle.c:14`.
- "No worse than Python" compares self-reported residuals. A timestamping bias in the IOKit transport is absorbed by the lead learner and reads as zero. Needed: a libc sweep test, independent reads via the pinned `ak820ctl clock --read` with the daemon paused, a TZ-change test, and a human reading the LCD against a reference clock.
- The replay corpus is the Windows log, `tests/timekeeper_replay.rs:3`. The macOS log exists at 241 KB and is the same script's format, so that half of the gate is achievable.

**5. High. macOS HID access is exclusive for every peer the plan keeps, and the plan never says so.**
- CLAUDE.md's "shareable, not exclusive" was measured on Windows. hidapi on Darwin seizes the device by default, and this repo records it at `nowplaying-macos.sh:13-15` and `install-agents.sh:15-17`. `ak820ctl.c:553` and `ak820text.py` open through hidapi with no non-exclusive call.
- So `ak820health.py`, `ak820keymap.py`, `ak820lighting.py` and provisioning, all kept per line 160, seize the device. The daemon's open fails with `kIOReturnExclusiveAccess` during them, and a seize mid-transaction starves a read into the `unresolved` path. `Presence::Busy` becomes routine.
- Phase 1 should include "a hidapi peer seizes the device during a transaction". Phase 4's "refuses to run beside the Python agents" is load-bearing on macOS in a way it was not on Windows. The sibling proved the arbitration model at `macos-port-plan.md:116-133`.

**6. Medium. The "two named macOS defects" are one macOS defect, and the corrections section undercounts.**
- G-A's BACKLOG entry at `BACKLOG.md:379-398` is explicitly about Windows `hid_enumerate` opening every device. The plan itself argues at lines 74 to 79 that macOS exposes properties without opening, and hidapi's Darwin enumerate reads IORegistry properties. G-A closes nothing on macOS. G-B is real, six getters at `nowplaying-macos.sh:59-84`.
- `../jdrgb/docs/ups-wedge-incident.md` is not on this Mac; only jdups is checked out. The correction rests on the owner's statement and should be tagged that way rather than implying the document was reread.
- "On this machine" appears at five sites, not three: `Cargo.toml:31`, `device.rs:4-6`, `path.rs:7-12`, `ak820text.py:135-137`, plus CLAUDE.md and the Windows plan.

**7. Medium. "No polling in steady state" is false, and "0 spawns" holds only while nothing fails.**
- The helper runs a 30 s backstop publish making three MediaRemote calls, `nowplaying-mediaremote.m:95-98` and `:339`, plus a 15 s heartbeat. Not process spawns, but polling.
- The failure path spawns: six 1.5 s timeouts and the helper exits, `nowplaying-mediaremote.m:88-91`. The sibling restarts with 2 s to 30 s backoff, a 2 min healthy-run rule, and a 60 s silence kill, `MediaRemoteHost.cs:67-81` and `:192-207`. S1 names only "helper death". It must specify silence detection, backoff, and the failure-mode spawn rate, or phase 5's spawn row passes in the good case only.
- Slow-but-alive is bounded: each call is capped at 1.5 s and publishes are serial, so the worst is seconds of lag. The reader must live on its own thread for the reason `smtc/worker.rs:1-11` gives, which the plan does not carry over.

**8. Medium. The seam glosses Windows-shaped "neutral" pieces beyond path.rs.**
- `caps.rs:97-104` requires input and output lengths equal to 33 as `HidP_GetCaps` reports them. IOKit's max report size excludes the report id, so this pure check rejects the right device unless the backend fudges. `proto.rs:62-69` calls the 33-byte frame "what Windows actually moves"; `IOHIDDeviceSetReport` takes the id separately.
- `cache.rs:311-317` reads `USERPROFILE` first. `bin/ak820.rs` is Windows by meaning throughout. `bin/ak820-agent.rs:24` carries `windows_subsystem`, which needs a `cfg_attr` in a shared file, contradicting the absolute rule at line 208.
- The Stuck and Abandoned model at `hid/mod.rs:100-103` and `exchange.rs:77-84` is about `CancelIoEx`. The plan should say what Stuck means on IOKit or state it is unreachable there.
- The 69% figure itself checks out: 4,331 of 13,814 lines import `windows`.

**9. Medium. MediaSource keeps the Windows ranking but the trait's failure contract is undefined.**
- The pure ranking at `smtc/mod.rs:144-172` with its captured regression tests moves intact; `Snapshot` is already the neutral output and `latest()` in the worker is already the pull-shaped trait. No Windows loss there.
- `agent.rs:274-285` encodes finding 5, a failed read publishes idle. The sibling's macOS service deliberately keeps the last snapshot on a failed read, `MacMediaSessionService.cs:404-414`, for the opposite reason. The `Health` semantics are part of the trait and the platforms want opposite policies. The plan must pick.
- macOS hands over a paused app while another plays; the sibling needed 5 s stickiness, `MacMediaSessionService.cs:52-59` and `:225-240`. "Current session or none" without it flips the LCD to the wrong app.
- `ak820 probe` is a Windows-only feature and must be declared so. Rate-aware extrapolation is new work, not "from smtc/mod.rs", per `macos-port-plan.md:802-805`.

**10. Medium. Phase 3's "byte-identical to what nowplaying-macos.sh would have pushed" cannot fail honestly.**
- Folding parity is already proven at generation time across every scalar. The new variable is the source: MediaRemote's title and artist versus AppleScript's fields can legitimately differ for the same track.
- Either the implementer picks agreeing tracks and it cannot fail, or it fails on a non-defect. Split it into folding parity on identical input, already a test, and a documented source comparison with differences explained.

**11. Medium. TCC attribution is the real analogue of the .NET launch trap, and it is missing.**
- Lines 277 to 280 dismiss the "runs from a terminal, not when spawned" trap. Automation consent is keyed to the responsible process; the sibling warns the prompt may not appear for a background launch, `README.md:979-981`. The existing workaround at `nowplaying-macos.sh:98-99` grants Terminal, not the daemon, and does not transfer to a signed binary.
- Ad-hoc signing in S3 changes the cdhash on every rebuild, so TCC identity churns and G-B's revoke test is confounded. And G-B only fires if the AppleScript path is in use; with MediaRemote primary, revocation is invisible unless the fallback is forced.
- If anyone sends Apple events in-process rather than via `osascript`, the hardened runtime needs the apple-events entitlement and the empty-entitlements hypothesis fails silently.

**12. Medium. S3's reasoning is confused and the .pkg recommendation assumes a certificate the sibling has not proven.**
- Which dylibs perl may load is governed by perl's entitlements, not the parent's. "Unverified for a non-.NET parent" at line 288 is a non-question. What is on our side: the dylib must be signed and unquarantined.
- A stapled `.pkg` needs a Developer ID Installer certificate, distinct from the Application identity at `package-macos.sh:29`. A `.dmg` staples with the Application cert alone. A `.pkg` also installs as root while the LaunchAgent is per-user, so the user still runs `ak820 install`.

**13. Medium. Disk justification #4 does not survive the "does not replace" list.**
- The 43 MB venv stays for the kept diagnostics and `setup.sh`. The saving exists only on a clean Mac that never had a venv, where it is not a saving. `du -sh venv` confirms 43M.

**14. Low to medium. Zero-dependency FFI and JSON are undeclared decisions.**
- Line 174 forbids new dependencies without a recorded decision. IOKit plus CoreFoundation with no crate means hand-written bindings, manual CF ownership, run-loop scheduling and callback lifetimes, the hazard class at `macos-port-plan.md:492-497`.
- The crate has no JSON parser today; `status.rs` writes key=value. Parsing helper lines with escaped Unicode titles by hand is a bug source. Record either the dependency or the hand-roll with a fuzz corpus.

**15. Low. Phase 6 has no defined clean-Mac test bed.**
- Windows used Sandbox. A fresh macOS user account does not reset Gatekeeper's per-file assessment or the binary's TCC state; a VM does. Name the mechanism or the gate is an intention.

**16. Low. Efficiency rows that cannot fail.**
- "Resident, clock ≤ 5 MB" is undefined once clock and media share a process. RSS drifts widely between readings: python3 reads 7.2 MB now against 11.3 in the table, perl 9.3 against 7.9.
- "Windows binary, no regression" as equality fails trivially on a trait refactor; use a bound.
- The "now" column omits the timekeeper's own spawns: `ioreg -p IOUSB -w0 -l` every 15 s while the cache lacks a bias, `ak820-timekeeper.py:117`, and two or three `ak820ctl` per sync.

**17. Low. Small nits.**
- "One clock implementation instead of two" at line 46 overstates: Python and C remain maintained oracles per lines 170 to 172, so three exist and one runs.
- BACKLOG G-B is at line 174; "all 9 places" counts three non-osascript redirects.
- Perl is a deprecated scripting runtime since 10.15; its removal is a distinct risk from the MediaRemote allowance and is not listed.
- `HidDiscovery` needs a per-port controller id for the seed's `cid`, `ak820-timekeeper.py:116-121` and `agent.rs:595-597`, not just VID and PID.

## What is sound

The Why section's refusal to claim precision is right and well argued. Every Windows-side fact I checked holds: the 117 KB binary and one dependency resolving to 15 packages per `Cargo.toml:24-30`, the 305 plus 9 tests, discovery opening nothing at `device.rs:97-124`, the bash header quote at `nowplaying-macos.sh:4-7`, and the venv size. The packaging traps are transcribed accurately from `package-macos.sh:1-15` and `entitlements.plist`, and reusing the notarytool profile approach is correct. The two-helpers analysis is right: option B is disqualified because the helper exits when its stdin closes, `nowplaying-mediaremote.m:285`, and the artwork-on-demand claim matches `:245-253`. Vendoring the `.m` with a versioned protocol is the correct decision. The `#[cfg]` rule is the right instinct even though the binaries will need one exception.

🎯 **COMPLETED:** Reviewed the cross-platform plan against both codebases and found seventeen issues, five of them high severity.
