# Current status — where to pick up (written 2026-09-16, updated after Phases 0, 1 and 3 were built the same day)

**For a clean session resuming the macOS port of `ak820-agent`.** Read this,
then [`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md).
This file is the state and the entry point; the plan is the design and does not
repeat itself here. Each phase row in the plan's table carries its own status
line (🟡 built, owed …).

---

## Where it stands

| | state |
|---|---|
| **Windows agent** | **Done.** `ak820-agent` v0.1.1, phases 0–6 met, published, per-phase Codex audits. Owns now-playing **and** the clock on that machine; the Python timekeeper is gone there. |
| **macOS port** | **Spikes S1, S2, S1b (logic) and S3 met; Phases 0, 1 and 3 built, 2026-09-16.** Waiting on hardware tests with the owner (list below). Nothing is installed: the Mac still runs the bash/Python pair. |
| **This Mac's OS** | ⚠️ **macOS 27.0 (26A428), installed 12:27 on 2026-09-16.** Everything the plan measured before that was on 26.5.2. MediaRemote-via-perl works on 27.0, from both the sibling's plugin and this crate's own supervisor. |
| **macOS today** | Still the Python/bash pair: `nowplaying-macos.sh` + `ak820-timekeeper.py`, via LaunchAgents. Working, and costing ~30% of a core while music plays. |
| **Firmware** | `b89777e0f9`, pinned in `deps.lock`, flashed **on the Mac's board**. ⚠️ **gremlin's board (the Windows gate's) is on `8608c4f6-dirty`** and stays there until Phase 0's live gate is done — its baseline was measured on that build. |

## What is built

| step | commit | state |
|---|---|---|
| **S1** MediaRemote supervisor | `ab3a724` | ✅ met: Music.app and Chrome sessions; SIGSTOP 240 s survived; JSON reader agrees with Python on 5,013 cases |
| **S2** IOKit transport | `ab3a724` | ✅ met: `info` byte-identical; 10,000-cycle soak flat after the one-object-per-arrival fix; 0.33 ms CPU per cycle |
| **S1b** canary logic, **S3** signing | `e8a4c16` | ✅ logic built, live half owed; S3 met: Developer ID + hardened runtime + empty entitlements |
| **0** the platform seam | `a46e770` | 🟡 built; Windows CI green; **Fable audit: safe to deploy** ([record](review-fable-phase0-2026-09-16.md)), comparator fixes in the next commit; **live gate on gremlin owed** |
| **1** macOS HID transport | this commit | 🟡 built; `info`/`health`/`selftest` verified on the Mac's board; unplug and open-trace owed |
| **3** macOS media | this commit | 🟡 built; `ak820 probe` read a live Chrome session through the real helper; the daemon refused to start beside the bash agent (lock verified live); live daemon run owed |

**Tests:** 315 unit tests on macOS (63 in `platform::macos`), plus the
integration suites; `cargo check --target x86_64-pc-windows-msvc --all-targets`
clean from the Mac.

## What needs the owner, in the order it unblocks things

1. **Phase 0 live gate, on gremlin** (its Claude session, over Remote Control).
   Build and install from `main`, no reflash, Windows Update paused, media
   state `none`, the same cache, RGB and slider. Three overnight windows, then
   `python scripts/clock_log_windows.py <log> --since "<reinstall time>" --gate 23.9 27.6 49`.
   `--since` is required now; the baseline shares the log file.
2. **Phase 3 live daemon run, on this Mac.** Pause the bash now-playing agent
   (`launchctl bootout gui/$UID/com.jdlien.ak820pro.nowplaying`, which leaves the
   timekeeper alone), then run
   `AK820_MEDIAREMOTE_DYLIB=<the sibling's dylib> ak820-agent --log <scratch>`
   in a terminal and watch the panel through play, pause, a track change, a
   switch from Music to Chrome, and quitting the player. Restore the bash with
   `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.jdlien.ak820pro.nowplaying.plist`.
   ⚠️ The timekeeper's `ak820ctl` still seizes the device each sync; a busy
   write logs `[warn]`, which is 4a's coexistence gate to count, not a bug.
3. **S1b live, with the owner at the desktop:** `ak820 probe --applescript`
   with Music playing and the helper refused (or simulated), grant the
   Automation prompt, then revoke it in System Settings and see
   `Automation denied` surface. **Spotify Connect:** play on another device and
   see whether the canary switches.
4. **Phase 1 on hardware:** unplug the board mid-transaction
   (`ak820 selftest` in a loop) and see it recover; a trace of opens.
5. **Board stall counters:** re-read `count_ge_25ms_nonflash` after an hour of
   normal use (`BACKLOG.md`, "Stalls during the S2 transport soaks").
6. **The leak comparison**, re-run with a RAM-only command (health page 1) and
   **not while anyone types**: the S2 soak's ~40 B per exchange over 100k.

Then 4a (LaunchAgent install, now-playing only) and 5a (the overhead "after").

## Decisions — all settled 2026-09-16

Full reasoning in the plan's *Finalization* section and at each site.

1. "On this machine" wording at five sites — trivial, still unfixed, blocks
   nothing.
2. **Two MediaRemote helpers, shared code** (A). Gates **Phase 3**, not the
   spikes: the sibling's protocol still has no version field, and S1–S3 use its
   built dylib unchanged. ⚠️ See the cross-repo note below.
3. **Ships publicly** as a stapled **`.dmg`**, **Apple Silicon only**. (This
   file said `.pkg` until finalization, contradicting the plan's review
   disposition. The Installer certificate does exist; `.dmg` won on shape.)
4. **Phase 0 builds on the Mac** (`cargo check --target
   x86_64-pc-windows-msvc` passes in 11 s), tests on CI, and its **live gate
   runs on `gremlin.local`** against that machine's own AK820 — do not reflash
   it between the baseline and the phase-0 run. The baseline already exists:
   1,614 clean periodic syncs, 09-09 → 09-15, **with media state `none`** (steady keepalive traffic still flowed) — match
   that condition, and pause Windows Update for the run. gremlin has no SSH;
   reach its Claude session over Remote Control (on at both ends).
5. **Dependencies:** IOKit hand-rolled (confirmed at the end of S2); JSON
   hand-rolled for flat objects, tested against a Python-`json` corpus.
6. **Media failure policy:** a failed source publishes idle, on both platforms;
   each backend defines "failed". On macOS that is **60 s with no line read
   from the helper**; death and `fatal` start that clock rather than trip it,
   so the helper's designed restart does not blank the LCD.
7. **The S1b canary** asks AppleScript only while Spotify or Music is running,
   checked with no spawn, at most once per 60 s, each call bounded, never
   overlapping, with a reversible switch. G-B's gate is therefore "surfaces
   within 60 s of the next Apple event, forced by the test".
8. **Whole-second clock slips: deferred by the owner.** Four are on record
   (`BACKLOG.md`), with none in about 3,270 syncs since 09-10. The clock "stays
   in perfect sync with the system clock almost all the time", so it is good
   enough for now; perfect it later. Phases 0 and 2 count slips separately so
   the port is neither blamed nor credited for them.
9. **The owner's main hope for the port is the Mac's now-playing overhead,
   and it is real — measured 2026-09-16:** about **30% of one core,
   continuously, while Music plays**. That is 47 CPU-seconds per 4 minutes in
   the agent's own children, plus `tccd`, `launchservicesd`, `trustd` and
   `runningboardd` busy only while it runs. The event-driven MediaRemote helper
   used 0.76 CPU-seconds in 98 minutes. `scripts/agent_overhead_macos.py` took
   the "before" and takes the "after".
10. **Now-playing first, the clock soon after** — decided by the owner, the
    way Windows went. Build order: **S1 → S2 → S1b, S3 → 0 → 1 → 3 → 4a → 5a →
    2 → 4b → 5b → 6.** In 4a the daemon owns now-playing and the Python
    timekeeper keeps the clock; the gate is that the timekeeper's own log
    shows no more sync failures than before. The public release stays last.

**Reviewed again 2026-09-16** (Fable, today's changes only): ten findings, one
High, all accepted — see the plan's second *Review disposition*. Two changed
what S1 builds: **the macOS failure rule is now "60 s with no line read"**, with
death and `fatal` starting that clock rather than tripping it, and silence is
never judged while the pipe holds unread bytes. Phase 0's gate was rewritten
so it can fail. Due before 4a: the idle cadence and seize direction, and the
`launchctl disable` fence. Due in S2: a 10,000-cycle open/close soak.

So: **nothing blocks starting the spikes**, and nothing unanswered blocks
Phase 0 once S1 and S2 are in.

## ⚠️ The decision that touches another product

Question 2's resolution vendors the `.m` MediaRemote helper and its line-JSON
protocol out of `~/code/streamdeck-now-playing` into a shared component with a
**versioned protocol field**. That is a change to a **signed, notarized, working
product**, and it needs a decision *in that repo*, not just this one.

The reasoning, so it is not re-litigated: the expensive, fragile asset is the
MediaRemote knowledge, not the perl process. Sharing the *code* captures nearly
all the maintenance benefit of a unified broker at almost none of its cost.
Consuming the plugin's existing helper is **disqualified, not merely worse** —
it is a child process on a Stream Deck plugin's pipes, so quitting Stream Deck
would silently kill now-playing on the keyboard.

## Corrections already folded in — do not rediscover these

- **The Music.app exemption is gone.** Sibling commit `fc70de4` fixed a
  loader-lock deadlock **30 minutes after this plan was first saved**.
  MediaRemote now serves Music like everything else; AppleScript is the
  *fallback*, not Music's route. The S1 and Phase 3 gates were rewritten. The
  old gate could only have passed by reintroducing the deadlock.
- **G-A closes nothing on macOS.** Its BACKLOG entry is about *Windows*
  `hid_enumerate` opening every device; macOS reads properties without opening
  anyway. So of the "two named defects" in the plan's Why section, **only G-B is
  a macOS gain** — the justification list overstated by one. G-A survives as a
  discipline worth keeping, not a benefit to claim.
- **Cost is not a justification.** The plan's Why section rules it out
  explicitly. The verified churn numbers in [`BACKLOG.md`](BACKLOG.md) (6–8
  `osascript` spawns per 3 s interval while playing, a fresh venv Python per push) are
  supporting evidence only. The case is unification, capability, and G-B.

## Conventions a fresh session needs

- **`deps.lock` pins the firmware and `setup.sh` enforces it.** Never let the
  pin name a build that has not been flashed and verified. Bump it in the same
  commit as the measurement that verified it.
- **The firmware repo's `origin` is fpb's fork and rejects pushes.** Use
  `git push jdlien ak820pro-jdlien`.
- **Multiple sessions share this checkout.** Claim files over SendMessage before
  editing, and never `git add -A` — a teammate's uncommitted work sits in the
  same tree. See `docs/hardware.md`'s two-sessions section.
- **`flash.sh` cannot dump the keymap if the board is ALREADY in the
  bootloader** — it silently restores a stale backup. Let it dump first.
- The board is healthy and unrelated to this work: `count_ge_25ms_nonflash` 0
  across a 13-hour overnight with 6,845 keypresses. If that changes, read
  `docs/hardware.md`'s keystroke-loss section — `Fn`+`D` answers it on the panel
  with no host attached.
