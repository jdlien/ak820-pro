# Current status — where to pick up (written 2026-09-16)

**For a clean session resuming the macOS port of `ak820-agent`.** Read this,
then [`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md).
This file is the state and the entry point; the plan is the design and does not
repeat itself here.

---

## Where it stands

| | state |
|---|---|
| **Windows agent** | **Done.** `ak820-agent` v0.1.1, phases 0–6 met, published, per-phase Codex audits. Owns now-playing **and** the clock on that machine; the Python timekeeper is gone there. |
| **macOS port** | **Planned, reviewed, dispositioned. Nothing built.** Plan drafted 2026-09-10, Fable review the same day (17 findings, 5 High), all dispositioned in `9f5f7d3` — two changed the design. |
| **macOS today** | Still the Python/bash pair: `nowplaying-macos.sh` + `ak820-timekeeper.py`, via LaunchAgents. Working. |
| **Firmware** | `b89777e0f9`, pinned in `deps.lock`, flashed. Unrelated to this work and healthy — see the bottom section. |

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
| **S1** | Can Rust drive the MediaRemote-via-perl helper and get a **browser** (YouTube in Chrome) title/artist/state over line-JSON? | **The capability gain evaporates.** The media half reduces to porting today's AppleScript. The clock case survives, at much reduced value. This is the reason to do the whole project, so test it first. |
| **S1b** | Is a TCC revocation *visible*? | The likeliest revocation shape is **not** helper death — the helper stays alive, heartbeats, and emits `bundle: null` forever, indistinguishable from "nothing is playing". Needs the canary cross-check against AppleScript `player state`. |
| **S2** | IOKit HID: open **exactly one** device, decided from IORegistry properties with nothing opened; `ak820 info` byte-identical to `ak820ctl info` | Same gate Windows phase 0 had. Also resolve the report-id/length mismatch at `hid/caps.rs:97-104`, and prove recovery when a hidapi peer (`ak820health.py`) seizes the device mid-transaction. |
| **S3** | Signing shape: ad-hoc Rust binary + signed dylib under the hardened runtime | Hypothesis is an empty entitlement set; establish empirically. |

**Phase 2 is the one that earns the project**, and it has a trap worth reading
before you get there: fixture parity *cannot* see a self-consistent wrong time.
Both the GET's residual and the SET's payload go through `host.local()`, so a
macOS `local()` off by an hour yields a **zero residual and a board an hour
wrong**. Windows covered this with hourly sweeps 2026–2099 against the oracle
CRT, which cannot compile here. The plan lists the four substitutes.

## Open questions — JD's, and only two gate anything

Full text in the plan's *Open questions* section.

1. "On this machine" wording in three files — trivial, blocks nothing.
2. **Two MediaRemote helpers or one shared? — SETTLED as (A)**, code shaped so a
   broker stays cheap. ⚠️ But see the cross-repo note below.
3. `.pkg`/`.dmg` or bare binary — **affects Phase 6 only.** Recommend `.pkg` for
   stapling.
4. Intel slice — **Phase 6 only.** Recommend Apple Silicon unless universal is free.
5. **Does this ship publicly, or stay personal-first like the firmware?** — this
   one changes the *size* of Phase 6, because it sets how much the install must
   defend against unknown machines. Worth answering before Phase 6 is scoped,
   not before Phase 0 starts.

So: **nothing blocks starting the spikes.** 3–5 can wait until Phase 6 is
planned in detail.

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
4. Only then Phase 0, and settle **where it builds** first — the plan flags this
   as unspecified: CI is `windows-latest` with no board, `.cargo/config.toml`
   pins static CRT to the msvc target only, and cross-compiling from the Mac is
   unaddressed. `agent.rs` is the file most at risk.

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
