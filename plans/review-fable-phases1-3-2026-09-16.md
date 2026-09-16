# Fable audit of Phases 1 and 3 on macOS (`e7e0b10`)

`claude -p`, model **claude-fable-5-1**, `--permission-mode plan` (read-only),
`--add-dir` the sibling repo, run 2026-09-16 against `e7e0b10`. The brief ruled
out opening HID, running any `ak820` binary, `osascript`, perl or the helper;
it ran `cargo test`, `clippy` and `check` only. It asked whether the owner can
run `ak820-agent` live in place of the bash agent, with the Python timekeeper
keeping the clock.

## Disposition

**Verdict accepted.** The auditor judged an attended run from Terminal safe,
and an unattended LaunchAgent install unsafe until F1, F2, F4 and F5 changed.
**All four are fixed**, as are F3 and F6–F11. F12 and F13 are instructions for
the live run, not code. Every finding was checked at source first; F3 was
already confirmed live, since `ak820 probe` had shown `elapsedAt` 214 s old
during steady Chrome playback that afternoon.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | Med | The canary could send an Apple event before MediaRemote had answered: at start, and after a helper restart | **Fixed**: the canary runs only once the helper's current run has sent a `now` (reset on `Started`); test |
| 2 | Med | A denial cleared only on a MediaRemote bundle or a fallback read, never on a canary answer | **Fixed**: any `player state` answer clears it; test |
| 3 | Med | The 600 s extrapolation cap froze the readout ten minutes into a long track | **Fixed**: `elapsedAt > 0`, age not negative and under a day, clamped to the duration. The route doc records why macOS differs from Windows; test |
| 4 | Med→High | `Board` teardown unregistered with a NULL buffer, untested while scheduled, then freed the context and buffer | **Fixed**: unregisters with the original buffer and length, as hidapi does, and **never frees** the context or buffer (about 400 B per board arrival). The owed unplug test and slider flip exercise it |
| 5 | Med | Lock: a pid written just after `mkdir` read as stale at login; with `$TMPDIR` unset the bash's lock was not found | **Fixed**: waits up to 2 s for a pid before clearing; falls back to `confstr(_CS_DARWIN_USER_TEMP_DIR)`, then `/tmp`, and refuses if **any** of those holds a live pid. Verified live: `env -u TMPDIR ak820-agent` refused beside the bash agent; tests |
| 6 | Low | The canary's `tell` was unguarded between the process-table read and the call | **Fixed**: guarded, and `notrunning` reads as stopped; test |
| 7 | Low | Stickiness holds 5 s after the last *message*, not the last playback | **Doc corrected**; behaviour kept (sibling parity) |
| 8 | Low | A stale, playing owner with no text drew two empty rows beside a play icon | **Fixed**: no text means idle; a stale repeat of the same non-scriptable app with no text keeps the previous text; tests |
| 9 | Low | The Stale route read every poll with no limit | **Fixed**: after a stale owner reads as not playing, no read for 30 s, or until a new `now` arrives; test |
| 10 | Low | A dead media thread would serve its last view forever | **Fixed**: no poll for 20 s makes `latest()` report a failed source, "the media thread has stopped polling"; test |
| 11 | Low | Two `Log` handles could both rotate the file | **Fixed**: log writes are serialized process-wide |
| 12 | Low | The idle playback readout adds windows in which `ak820ctl`'s seized read can take our echo | **For the live run**: count `[rc=N]` failures in the timekeeper log against its pre-4a baseline, as 4a's gate already requires |
| 13 | Low | First-run Automation prompt against the 3 s and 5 s timeouts | **For the live run**: with F1 fixed, a healthy MediaRemote sends no Apple event. Sign with `scripts/sign-agent-macos.sh` so consent survives rebuilds; expect the prompt to name `ak820-agent` the first time a fallback or canary state occurs |

## The report, verbatim

Audit done. Nothing was modified, opened or spawned beyond `cargo test`, `cargo clippy` and `cargo check` on the crate. All three are clean (315 lib tests plus the integration suites pass; the Windows target checks; four cosmetic clippy warnings).

Live facts I checked on this Mac before judging: the bash agent (pid 1869) and the timekeeper (pid 1850) run as `RunAtLoad`/`KeepAlive` LaunchAgents; the bash lock sits at `$TMPDIR/ak820pro-nowplaying.lock` under `/var/folders/.../T/`; the sibling's dylib carries only `com.apple.provenance`, no quarantine; no dylib sits beside either built binary; the debug daemon is ad-hoc linker-signed.

## Findings

**F1. Medium. The canary sends an Apple event before MediaRemote has answered.**
Evidence: `media/mod.rs:243-244` gates the canary only on `!helper.failed` and passes `router.has_bundle()`, which is false before the first `now` (`route.rs:113-115`). The media thread polls at 1.5 s regardless (`mod.rs:68,423`), and `canary.rs:100-110` asks immediately when a player is running.
Consequence: every start with Music or Spotify open, and every helper restart whose last state was null, sends `player state` in a state the plan says sends none. The helper usually wins the race, but a cold perl start or one slow MediaRemote call loses it. As a LaunchAgent the first TCC prompt comes from this path, and the 5 s timeout kills osascript under the prompt.
Fix: one condition in `Engine::poll`, run the canary only once `self.router.current().is_some()`.

**F2. Medium. A denial never clears on a successful canary answer.**
Evidence: `mod.rs:287-289` clears `denied` only when MediaRemote names a bundle, `mod.rs:322,328` only when a fallback read returns. `canary.rs:128-131` returns `None` for a plain state answer, so `note_to` never sees it.
Consequence: consent denied while idle, owner re-grants, the next canary answers "paused", and every poll still fails with "Automation denied" (status error, `failures` climbing, no `recovered` line) until something MediaRemote can see plays. The G-B revoke-then-regrant test reads wrong.
Fix: clear `self.denied` after `canary.answered` returns `Outcome::State(_)`.

**F3. Medium. The 600 s extrapolation gate freezes the readout on long tracks.**
Evidence: `route.rs:33,159-164` extrapolates only while age is under 600 s. `elapsed_at` comes from the last `now`, and the helper emits `now` only on change (`nowplaying-mediaremote.m:225-229`; the backstop at `:339` re-emits only a changed line). Inference, not verified: Music and Chrome stamp elapsed at play, pause and seek, and do not tick it.
Consequence: ten minutes into an uninterrupted track the position reverts to the last `elapsed`, often 0:00, and the daemon pushes that every 3 s, resetting the firmware's own timer each time. Windows has the same gate (`smtc/mod.rs:202-215`) but SMTC apps refresh their timestamp; nothing refreshes here.
Fix: verify with `ak820 probe --seconds 700` on a long video; on macOS drop the upper bound and keep the `age >= 0` check and the duration clamp at `:167-169`.

**F4. Medium, High if the assumption is wrong. The Board drop path is untested and frees memory IOKit may still write into.**
Evidence: `device.rs:172-195` unregisters with a NULL buffer, length 0 and `None`, then frees `ctx` and the input buffer. The S2 isolation soak never ran this sequence (`spikes/s2-iokit/src/main.rs:525-548` unschedules and releases with the original buffer still registered). hidapi unregisters with the original buffer pointer. Whether IOKit detaches on a NULL buffer is unverified.
Consequence: this runs on every re-arrival, which includes every slider flip since a flip brown-outs and re-enumerates, and on every `Stuck`. If the registration survives, the next input report lands in freed memory.
Fix: never free `ctx` and `buffer` (a few KB per arrival), or unregister with the same buffer and length as registration. Then run the owed unplug test.

**F5. Medium, scoped to the 4a install. Lock race at login, and a `$TMPDIR`-dependent path.**
Evidence: `instance.rs:57-72` removes the lock directory at once when the pid file is missing; `nowplaying-macos.sh:23-32` writes its pid after `mkdir`; both are `RunAtLoad` agents, so at login they start together. `instance.rs:25-31` uses `$TMPDIR`, which an SSH shell does not set, so the lock goes to `/tmp` and the bash's lock is never seen.
Consequence: two pollers, doubled board traffic, and the bash's `ak820text.py` seizing every 3 s so the daemon reads busy on alternate cycles. The commit's "refused to start beside the bash" holds only from a Terminal.
Fix: on `AlreadyExists` with no readable pid, wait ~200 ms and re-read before clearing; resolve the temp dir with `confstr(_CS_DARWIN_USER_TEMP_DIR)` when `TMPDIR` is unset.

**F6. Low. The canary's `tell` is unguarded.**
`applescript.rs:196-199` has no `is running` guard, and the process-table read and the osascript are consecutive (`mod.rs:244,247`). A player quitting in that window is relaunched. The fallback script guards each `tell` (`applescript.rs:102`). Fix: guard it the same way.

**F7. Low. Stickiness protects only 5 s after the last message, not the last playback.**
`route.rs:79-81,87-90` moves `playing_since` only in `accept()`, and steady playback sends no messages. Two minutes into a track a paused-app handover is accepted at once. Sibling parity (`MacMediaSessionService.cs:227-241`), but the module doc overstates it.

**F8. Low. A stale non-player message renders an empty band with a play icon.**
`route.rs:142-171`: bundle set, no text, playing true is not idle, so two empty `SET_LINE` rows with a play icon go out until the next `now`. Sibling parity. Fix: keep the previous `current` when `stale` and the bundle is not a scriptable player.

**F9. Low. The Stale route has no rate limit.**
`mod.rs:258,301-320` reads once per 3 s poll for as long as the helper says stale, which it does on a metadata timeout or an owner with empty info (`.m:188`). If an open-but-stopped player takes that shape (unmeasured), idle Music costs the bash agent's spawn rate again. Verify with `ak820 probe --seconds 60` and Music open but stopped.

**F10. Low. A dead media thread freezes the last snapshot forever.**
`agent.rs:263-289` never checks that `polls` advances. A panic in the media thread (`helper.rs:167,342,355`) leaves the view frozen and the daemon re-asserting the last track every 30 s in a debug build.

**F11. Low. Two `Log` handles rotate the same file independently.**
`macos/mod.rs:53` creates a second handle; `logfile.rs:41-59` renames per line. Two writers seeing the threshold in the same instant can lose the rotated file. Needs a microsecond coincidence once per MB.

**F12. Low. Idle readout traffic beside the timekeeper's seize.**
`agent.rs:375` pushes the playback readout every poll; the bash did so only while playing. The firmware repaints only on an owner change (`graphics/display.c:357-367`), so it is a round trip with no LCD work. It is 28,800 more daily windows in which `ak820ctl`'s seized read can receive our echo, which its version check rejects, so a failed sync rather than a wrong one. Count those in the timekeeper log during the run.

**F13. Low. First-run Automation prompt versus the 3 s and 5 s timeouts.**
From a Terminal the responsible process is Terminal, which likely already has consent. As a LaunchAgent it is the daemon, whose ad-hoc identity changes per build. Known to the plan; for the live run, pre-grant with `ak820 probe --applescript`.

## Verified sound

- Windows: the diff changes only the `spawn_media` signature and a re-export. The Windows target checks clean.
- `--clock` is refused before the lock is taken (`daemon.rs:78-80`). No clock write path exists on macOS.
- Exchange over IOKit: the report id is prepended so the shared normalizer works, write completions correlate by sequence, unplug mid-write returns `Absent` not `Stuck`, reports queued while closed are cleared at open, and a hidapi seize reads as busy.
- CF ownership follows the Create/Copy rule throughout, the matching dictionary is consumed, iterators and services are released, and no `IOHIDManager` is ever created.
- Run-loop thread: scheduling happens on the loop thread, no job blocks, callbacks take only the inbox mutex.
- Helper supervision: 60 s proof-of-life rule with `hello` excluded, kill only with the pipe drained plus a settle, reader and stderr threads joined and the child reaped every run, backoff 2 to 30 s, and the helper exits on stdin EOF so a daemon killed by any signal orphans nothing.
- AppleScript fallback: only running players are named, each `tell` is guarded, `missing value` and decimal commas are handled, Spotify milliseconds and AppleScript's exponent form for large reals parse, pipes drain on threads, and the timeout kills and reaps.
- Router: a held switch lands at the first poll after the hold and is dropped when something newer arrives.
- Log and status directories are created on write, and the status file is written atomically.

## Verdict

An attended live run from a Terminal is safe: boot out the bash agent, leave the timekeeper alone, set `AK820_MEDIAREMOTE_DYLIB` to the sibling's dylib, and start from a shell where `TMPDIR` is set. Nothing in this code can write the clock, the keymap or the lighting. The worst realistic outcomes are a wrong position after ten minutes (F3), one startup Apple event (F1), and a daemon crash on replug or slider flip (F4), each cured by restarting the daemon.

Unattended install as a LaunchAgent is not safe yet. F1, F2, F4 and F5 must change first, and F3 should be settled before anyone grades the readout.
