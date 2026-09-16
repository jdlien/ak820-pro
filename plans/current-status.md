# Current status — where to pick up (written 2026-09-16, updated after finalization the same day)

**For a clean session resuming the macOS port of `ak820-agent`.** Read this,
then [`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md).
This file is the state and the entry point; the plan is the design and does not
repeat itself here.

---

## Where it stands

| | state |
|---|---|
| **Windows agent** | **Done.** `ak820-agent` v0.1.1, phases 0–6 met, published, per-phase Codex audits. Owns now-playing **and** the clock on that machine; the Python timekeeper is gone there. |
| **macOS port** | **Planned, reviewed, dispositioned, finalized. Nothing built.** Plan drafted 2026-09-10, Fable review the same day (17 findings, 5 High), all dispositioned in `9f5f7d3` — two changed the design. **Finalized 2026-09-16**: every gating question decided, see the plan's *Finalization* section. |
| **This Mac's OS** | ⚠️ **macOS 27.0 (26A428), installed 12:27 on 2026-09-16.** Everything the plan measured before that was on 26.5.2. MediaRemote-via-perl re-verified on 27.0 the same afternoon — it still answers. |
| **macOS today** | Still the Python/bash pair: `nowplaying-macos.sh` + `ak820-timekeeper.py`, via LaunchAgents. Working. |
| **Firmware** | `b89777e0f9`, pinned in `deps.lock`, flashed **on the Mac's board**. Unrelated to this work and healthy — see the bottom section. ⚠️ **gremlin's board (the Windows gate's) is on `8608c4f6-dirty`** and stays there until Phase 0's live gate is done — its baseline was measured on that build. |

**The crate is unconditionally Windows right now.** There is no `cfg(target_os)`
anywhere in `ak820-agent/src`, and nine files reference `windows::` directly:
`agent.rs`, `task.rs`, `process.rs`, `instance.rs`, `smtc/worker.rs`,
`hid/{mod,device,exchange}.rs`, `clock/host.rs`. That list *is* the Phase 0
platform-seam job, measured rather than estimated.

## Do not start with Phase 0

The plan is explicit and it is the single most important thing on this page:
**S1 and S2 can each kill or reshape the plan, and both are cheap. Do not start
Phase 0 until both have answered.**

| spike | question it settles | what a failure means |
|---|---|---|
| **S1** | Can Rust drive the MediaRemote-via-perl helper and get a **browser** (YouTube in Chrome) title/artist/state over line-JSON? ✅ **The Apple half is answered on 27.0**: the sibling's dylib under perl returned a Chrome/YouTube session with `playing: true`. **The Rust supervisor half is the work.** Parse from captured output — the live `now` carries `elapsedAt`, which the `.m` header does not list. | **The capability gain evaporates.** The media half reduces to porting today's AppleScript. The clock case survives, at much reduced value. This is the reason to do the whole project, so test it first. |
| **S1b** | Is a TCC revocation *visible*? | The likeliest revocation shape is **not** helper death — the helper stays alive, heartbeats, and emits `bundle: null` forever, indistinguishable from "nothing is playing". Needs the canary cross-check against AppleScript `player state`. |
| **S2** | IOKit HID: open **exactly one** device, decided from IORegistry properties with nothing opened (`IOServiceGetMatchingServices`, **never `IOHIDManagerOpen`**); `ak820 info` byte-identical to `ak820ctl info` | Same gate Windows phase 0 had. Also resolve the report-id/length mismatch at `hid/caps.rs:97-104`; measure seize behaviour **in both directions** (the plan had assumed the hidapi peer always wins); log IOKit's kernel report timestamp beside userspace `t1`. Opens are **per interaction**. S2 is also the evidence for hand-rolling IOKit. |
| **S3** | Signing shape: Rust binary signed with the **Developer ID Application identity, by SHA-1** (not ad-hoc — ad-hoc churns TCC identity every rebuild) + signed dylib under the hardened runtime | Hypothesis is an empty entitlement set; establish empirically. |

**Phase 2 is the one that earns the project**, and it has a trap worth reading
before you get there: fixture parity *cannot* see a self-consistent wrong time.
Both the GET's residual and the SET's payload go through `host.local()`, so a
macOS `local()` off by an hour yields a **zero residual and a board an hour
wrong**. Windows covered this with hourly sweeps 2026–2099 against the oracle
CRT, which cannot compile here. The plan lists the four substitutes.

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
   each backend defines "failed" (macOS: helper dead, `fatal`, or silent two
   heartbeats).
7. **The S1b canary** asks AppleScript only while Spotify or Music is running,
   checked with no spawn, at most once per 60 s.

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
  explicitly. The verified churn numbers in [`BACKLOG.md`](BACKLOG.md) (7
  `osascript` spawns per 3 s interval, a fresh venv Python per push) are
  supporting evidence only. The case is unification, capability, and G-B.

## A suggested first session

1. Read the plan end to end. It is long because it was reviewed hard; the
   dispositions carry most of the load.
2. Answer **S1** first — it is the cheapest thing that can kill the project's
   main justification. A Rust supervisor, the sibling's perl helper, YouTube in
   Chrome, and a title on stdout.
3. Then **S2**, then S1b and S3 in either order.
4. Only then Phase 0. Its first commit is forced: `windows` is an unconditional
   dependency, so a native macOS build fails in `windows-future` until it moves
   under `[target.'cfg(windows)'.dependencies]`. gremlin's baseline is already
   in hand (see decision 4); do not reflash that board or let Windows Update
   restart it mid-run. `agent.rs` is the file most at risk.
5. Then **1 → 3 → 4a → 5a**: now-playing moves to the daemon while the Python
   timekeeper keeps the clock, and `scripts/agent_overhead_macos.py` takes the
   "after" with Music playing. The clock (**2 → 4b**) follows soon after.

Every phase ends with an external audit, per the convention in
`AK820-AGENT-PLAN.md`: the gate proves the phase does what it claims, the audit
looks for what nobody thought to claim.

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
