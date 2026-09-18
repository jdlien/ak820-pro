# Current status — where to pick up (written 2026-09-16, updated after Phases 0, 1, 3 and 4a were built the same day)

**For a clean session resuming the macOS port of `ak820-agent`.** Read this,
then [`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md).
This file is the state and the entry point; the plan is the design and does not
repeat itself here. Each phase row in the plan's table carries its own status
line (🟡 built, owed …).

---

## ⚠️ In flight right now — 2026-09-18 11:2x, read this first

**The Elysium daemon is STOPPED.** `launchctl bootout gui/$UID/com.jdlien.ak820pro.agent`
was run at 11:19:15 to give the leak soak the board to itself. The clock free-runs
meanwhile (harmless for minutes; it re-syncs at the next start). **Put it back with:**

```sh
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist
tail -n 5 ~/Library/Logs/ak820pro/ak820-agent.log   # expect a start block and an enumerated sync
```

**Running in the background:** `spikes/s2-iokit/target/release/s2 soak 20000` (task
`buc41x71c`), output buffered until it exits because it is piped through `tail`.

**Why:** the daemon leaks about **1.9 MB of `phys_footprint` a day on macOS**
(2.70 MB at 35 min uptime on 09-17, **4.58 MB at 25 h** on 09-18, over ~29,000 media
polls + 300 clock + 300 health exchanges). ⚠️ **Windows does not leak**: gremlin's
25 h run holds **2.74 MB private bytes after ~60,000 exchanges**, so the cause is in
the **macOS transport**, not the shared code. The last good build is running everywhere;
this is the one remaining engineering defect and it blocks nothing.

**Codex review of the transport** (gpt-6-astra, high effort, read-only) is saved at
`scratchpad/codex-leak.md` in this session's scratchpad. Its three usable findings:

1. **No autorelease pool** on the calling thread or the run-loop thread
   (`device.rs` write submission; `runloop.rs`'s indefinite `CFRunLoopRun()`).
   IOKit's own Objective-C temporaries would then accumulate. Its first-choice fix:
   scoped pools around IOKit calls, and a run loop of `CFRunLoopRunInMode(..., finite, true)`
   with a fresh pool per iteration. **Plausible mechanism, unconfirmed.**
2. ⚠️ **S2's own 56 B/exchange figure is confounded**: `soak()` keeps three `Vec<f64>`
   timing samples per exchange (`spikes/s2-iokit/src/main.rs:279-287`), about 2.4 MB of
   payload over 100,000 exchanges. **Use `isolate exchange` / `isolate open`, which keep
   no samples, for a clean per-exchange number.** The production 1.9 MB/day is
   independent evidence and stands.
3. Two definite small bugs, worth fixing regardless:
   - `cf.rs:17` `(!r.is_null()).then_some(Cf(r))` **builds `Cf(NULL)` eagerly** and drops
     it, so `CFRelease(NULL)` on the NULL path. Use `.then(|| Cf(r))`.
   - `device.rs:256` unregisters the **removal** callback with a NULL context while it was
     registered with `ctx`; Apple's implementation matches by context, so the entry stays.
     Pass the original `ctx`.

**Next steps, in order:** (a) let the soak finish and read it; (b) run
`s2 isolate exchange 20000` and `s2 isolate open 20000` for the unconfounded
per-exchange and per-open numbers; (c) apply fix 3, then test fix 1 if the numbers
still show growth; (d) **restart the daemon** (command above) and confirm a sync;
(e) commit. ⚠️ **Uncommitted:** `spikes/s2-iokit/src/main.rs` now soaks with **health
page 1** (`frame(0x13, 0x01, &[])`, RAM-only) instead of `TEXT_PLAYBACK`, per the
BACKLOG rule from the 09-16 stall incident.

**Everything else is done and running.** Phases 0-5a and 2/4a/4b are met on both
machines; `scripts/package-macos.sh` builds a signed `.dmg` and stops before Apple.
**Owed from JD:** one logout/login on Elysium; the notarize decision (test-notarize
the current `.dmg`, or tag `v0.2.0`, which also fires the Windows CI release); and,
at release, the MacBook Air smoke test (install from the `.dmg`, then lid shut 10 min
for the sleep/wake check that Elysium cannot give — it never sleeps on AC).

## Where it stands

| | state |
|---|---|
| **Windows agent** | **Done.** `ak820-agent` v0.1.1, phases 0–6 met, published, per-phase Codex audits. Owns now-playing **and** the clock on that machine; the Python timekeeper is gone there. |
| **macOS port** | **Spikes S1, S2, S1b (logic) and S3 met; Phases 0, 1, 3 and 4a built, 2026-09-16.** Waiting on hardware tests with the owner (list below). Nothing is installed: the Mac still runs the bash/Python pair. |
| **This Mac's OS** | ⚠️ **macOS 27.0 (26A428), installed 12:27 on 2026-09-16.** Everything the plan measured before that was on 26.5.2. MediaRemote-via-perl works on 27.0, from both the sibling's plugin and this crate's own supervisor. |
| **macOS today** | Still the Python/bash pair: `nowplaying-macos.sh` + `ak820-timekeeper.py`, via LaunchAgents. Working, and costing ~30% of a core while music plays. |
| **Firmware** | `b89777e0f9`, pinned in `deps.lock`, flashed **on the Mac's board**. ⚠️ **gremlin's board (the Windows gate's) is on `8608c4f6-dirty`** and stays there until Phase 0's live gate is done — its baseline was measured on that build. |

## What is built

| step | commit | state |
|---|---|---|
| **S1** MediaRemote supervisor | `ab3a724` | ✅ met: Music.app and Chrome sessions; SIGSTOP 240 s survived; JSON reader agrees with Python on 5,013 cases |
| **S2** IOKit transport | `ab3a724` | ✅ met: `info` byte-identical; 10,000-cycle soak flat after the one-object-per-arrival fix; 0.33 ms CPU per cycle |
| **S1b** canary logic, **S3** signing | `e8a4c16` | ✅ logic built, live half owed; S3 met: Developer ID + hardened runtime + empty entitlements |
| **0** the platform seam | `a46e770` / `e07fdfa` | ✅ **met 2026-09-17.** The overnight gate FAILED as written, confounded by gremlin's environment (a new NVIDIA driver, Sandbox removed). A same-minutes burst A/B of old against new `ak820 clock` then passed all four conditions fixed before the run, one of them by 0.085 ms. The Fable audit was clean |
| **1** macOS HID transport | `e7e0b10` | 🟡 built; `info`/`health`/`selftest` verified on the Mac's board; unplug and open-trace owed |
| **3** macOS media | `e7e0b10` | 🟡 built; `ak820 probe` read a live Chrome session through the real helper; the daemon refused to start beside the bash agent (lock verified live); live daemon run owed |
| **4a** install, now-playing only | `c5bd787` | 🟢 **installed on this Mac 2026-09-16 20:01**, the panel confirmed by the owner (YouTube titles too). Reinstalled 20:50 as `ProcessType Standard`: `Background` ran it at priority 4 and starved HID replies under screen-sharing load (9 timeouts in 45 min). Reinstalled 21:05: the IOKit object can go **deaf for good** (8 min of no replies while `ak820 info` from another process worked), so an object that stops hearing is now replaced after 3 silent interactions; watch `~/Library/Logs/ak820pro/ak820-agent.stdio.log` for the count. Reinstalled 21:30 so a SIGSTOP (5a's method) no longer flashes "none" on resume. **5a MET:** ~36% of a core before, **~0.2% after**. Coexistence gate still collecting: 27 timekeeper syncs, 0 failures by 21:30 |
| **4b** the daemon takes the clock | `d548e3f` | 🟡 **installed 21:48 on 2026-09-16**, the Python timekeeper retired. First sync −1.2 ms, with the bias carried. **The system time-zone change passed both ways without a restart** (+1 h and −1 h, each set within 1.5 ms). Overnight syncs to grade; sleep/wake, login and rollback owed |
| **2** macOS clock | `08ce108`, `d7842d1` | ✅ **met 2026-09-16**; the owner confirmed the LCD against the system clock. Offline: the replay over this Mac's own timekeeper log (1,469 learned, 605 holds, 2,072 carried syncs, 2,077 intervals), time zones against `zoneinfo`, and `ak820 clock` read-only with a fail-closed refusal. Live (21:35): 6/6 captures decode byte-identically through the pinned C, Rust and `ak820ctl` reads agree within 0.7 ms, and 648,672 hours × 3 zones match the C's `localtime()`. A system zone change moves to 4b |

**Tests:** 332 unit tests on macOS, plus the integration suites;
`cargo check --target x86_64-pc-windows-msvc --all-targets` clean from the Mac.

**Audited:** Phases 1 and 3 by Fable ([record](review-fable-phases1-3-2026-09-16.md)).
The verdict was an attended run safe and an unattended install unsafe until
F1, F2, F4 and F5 changed. **All four are fixed**, with six of the eight Low
findings; the other two are instructions for the live run below.

## What needs the owner, in the order it unblocks things

1. **Phase 0 live gate, on gremlin** (its Claude session, over Remote Control).
   Build and install from `main`, no reflash, Windows Update paused, media
   state `none`, the same cache, RGB and slider. Three overnight windows, then
   `python scripts/clock_log_windows.py <log> --since "<reinstall time>" --gate 23.9 27.6 49`.
   `--since` is required now; the baseline shares the log file.
2. **Phases 3 and 4a live, on this Mac.** Build and sign (`cargo build
   --release`, then S3's `codesign` with `--identifier`), then
   `target/release/ak820 install --dylib <the sibling's dylib>`. It retires the
   bash agent and leaves the timekeeper. Watch the panel through play, pause, a
   track change, a switch from Music to Chrome, and quitting the player; then
   logout/login and sleep/wake; `ak820 status` between. **Rollback:
   `ak820 uninstall`**, which starts the bash agent again. ⚠️ The timekeeper's
   `ak820ctl` still seizes the device at each sync; a busy push logs `[warn]`,
   which 4a's coexistence gate counts, not a bug. So are the timekeeper's own
   `[rc=N]` lines (audit F12): the idle readout every 3 s gives its seized read
   more chances to take our echo, and its version check turns that into a
   failed sync, not a wrong one. Count them against its pre-install log. Take
   5a's overhead "after" while it runs. A ten-minute-plus video checks the
   readout past F3's old cap; a slider flip or replug exercises F4's teardown.
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

Then 5a (the overhead "after"), and the clock: 2 → 4b.

## Decisions — all settled 2026-09-16

Full reasoning in the plan's *Finalization* section and at each site.

1. "On this machine" wording at five sites — trivial, still unfixed, blocks
   nothing.
2. **Two MediaRemote helpers, and — revised by the owner 2026-09-16 — a pinned
   copy, not shared code.** `ak820-agent/helper/` vendors the plugin's
   `nowplaying-mediaremote.m` at `fc70de4` (pin and SHA-256 in `UPSTREAM`), with
   one local change: `hello` carries `"protocol": 1`, and the daemon warns on an
   unversioned or foreign helper. `scripts/build-helper-macos.sh` builds it,
   `scripts/sign-agent-macos.sh` signs it, `scripts/check-helper-upstream.sh`
   flags drift. The plugin repo is untouched. Installed on this Mac 22:20.
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
