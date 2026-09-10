# ak820-agent — one daemon for Windows and macOS — plan

**Status: drafted 2026-09-10, nothing built.** This plan turns the Windows-only
`ak820-agent/` crate into a cross-platform daemon that replaces the macOS
Python/bash agents as well, closes two named macOS defects, and ships signed
and notarized. It is written to be reviewed before any code is written.

Companion documents that are part of this plan, not background:
[`AK820-AGENT-PLAN.md`](AK820-AGENT-PLAN.md) (the Windows work this extends,
and the source of every phase-gate convention used here),
[`AK820-AGENT-CLOCK-PARITY.md`](AK820-AGENT-CLOCK-PARITY.md) and
[`AK820-AGENT-CLOCK-TRANSACTION.md`](AK820-AGENT-CLOCK-TRANSACTION.md) (the
clock contract, which does not change), and — new to this plan and load-bearing
for the whole media half — `../streamdeck-now-playing/docs/macos-port-plan.md`
§3.5 and its `README.md` §14.

---

## Why

**The honest case is narrow, and it is worth stating what does *not* justify
this before what does.**

Not justified by deployment. The three things that paid for the Rust rewrite on
Windows — no Python, no MSYS2, no VC++ redistributable — have no macOS
analogue. `setup.sh` builds the venv, macOS ships python3, a LaunchAgent is a
plist. Nobody is blocked today.

**Not justified by precision, and this plan does not claim it.** The macOS
clock is already good: it once drifted seconds per hour — visibly, a second a
minute — and has run accurately for a while now. The historical log
(2026-09-01..09, median drift 88–332 ms/day) measures superseded firmware and a
still-converging SOF loop, not the Python agent's ceiling, and it cannot be read
naively anyway because offsets **slew** rather than jump, so its `after` column
tracks `before` and is not landed precision.

**No soak gates this work.** Proving a few tens of milliseconds either way would
cost days and change no decision — the port is justified by unification,
capability and the two defects, none of which depend on a timing number. The
obligation this leaves is narrower and belongs in Phase 2: **the port must not
make the clock worse**, measured against whatever the Python agent is doing at
the time.

**What does justify it, in order:**

1. **One clock implementation instead of two.** `clock/transaction.rs` (1,098),
   `clock/scheduler.rs` (925), `clock/mod.rs` (740), `clock/cache.rs` (612),
   `clock/set.rs` (263) plus `proto.rs` (416) are platform-neutral logic
   **[measured]**. The same contract exists again in `ak820-timekeeper.py` and
   the pinned `ak820ctl`. Divergence there produces a *plausible-looking wrong
   time* — the failure mode noticed last. This is the prize; everything else is
   secondary.
2. **A capability gain on macOS that is real, not cosmetic.** See
   [the finding](#the-finding-that-changes-the-shape) — browser media becomes
   visible for the first time.
3. **Two named defects close by construction rather than by patch.** Both are
   already in [`BACKLOG.md`](BACKLOG.md); see [G-A](#g-a--open-nothing-you-did-not-mean-to)
   and [G-B](#g-b--a-tcc-revocation-must-be-visible).
4. **Disk.** 43 MB of venv **[measured]** against a 117 KB Windows binary
   **[measured 2026-09-05]**.

---

## ⚠️ Two corrections to the record, before anyone builds on them

**1. The UPS wedge happened, but not on this machine.** `CLAUDE.md`,
`ak820-agent/Cargo.toml` and `AK820-AGENT-PLAN.md` all say `hid_enumerate`
"wedged a UPS **on this machine**", citing `../jdrgb/docs/ups-wedge-incident.md`.
The owner confirms (2026-09-10) the wedge was real and is not to be confused
with a separate loose-cable fault resolved mid-development of jdups — but it
was **not this Mac**. A one-word fix at each site, not a reason to doubt the
rule.

The rule is also stronger than that anecdote. `hid_enumerate` opens every HID
device, and on **Windows** that is a `CreateFile` per device. On **macOS** the
IORegistry exposes VID/PID/usage *without* opening anything — which is what
`ioreg` does, and is consistent with the incident having been on the Windows
side. [G-A](#g-a--open-nothing-you-did-not-mean-to) is written to stand on that
engineering argument alone, so it holds regardless.

**2. "69% platform-neutral" was an overcount.** Files are classified neutral by
*import* (no `use windows::`), but `hid/path.rs` parses Windows device paths
and SetupAPI multi-sz strings — neutral by import, Windows by meaning. Treat
69% as optimistic. The clock core genuinely is portable; the HID layer is less
portable than the number suggests, and `path.rs` is a **pattern to
reimplement against IOKit, not code to reuse.**

---

## The finding that changes the shape

**macOS now-playing is not limited to AppleScript, and this repo's own sibling
project proves it in production.**

`nowplaying-macos.sh` uses AppleScript against Spotify and Music by deliberate
choice, and its own header says MediaRemote "would also catch browser media
(YouTube)" but was avoided. The consequence is that **browser media has never
been visible on the AK820's LCD on macOS.**

`../streamdeck-now-playing` solved this on 2026-09-09 and ships it signed and
notarized. The mechanism, from its `README.md` §14.2 and
`src/NowPlaying.Media.Mac/native/nowplaying-mediaremote.m`:

- macOS 15.4 stopped answering `MRMediaRemoteGetNowPlayingInfo` for ordinary
  processes — the callback fires and the dictionary is empty. **Re-measured on
  26.5.2: still empty** **[measured, sibling project]**.
- It still answers an **Apple platform binary**. So the metadata comes from a
  small Objective-C dylib loaded into `/usr/bin/perl` via `DynaLoader`, run
  from a constructor, speaking **line-JSON** over pipes to a supervising
  parent. Verified there: 0 keys in-process, full metadata + transport commands
  + change notifications when hosted by perl **[measured]**.
- **It is event-driven.** MediaRemote *pushes* change notifications. No polling
  at all in steady state.
- **One app is exempt and forced a router.** With Music.app owning the session,
  `GetNowPlayingClient` and `IsPlaying` answer but `GetNowPlayingInfo` never
  calls back — measured out to thirty seconds. So the service reads the owning
  bundle id first and sends **Music → AppleScript, everything else →
  MediaRemote**, with every MediaRemote call bounded (1.5 s there) and a
  fallback to Music if the helper is lost entirely.
- Prior art cited: `ungive/mediaremote-adapter`, and a fastfetch `osascript` +
  `MRNowPlayingRequest` variant **[unverified]**.

**This closes a capability gap I previously called unclosable in any language.
That was wrong.** It is the single most interesting thing available to this
project and it is already de-risked next door.

**What it costs, and these are not small:**

- A bundled signed dylib plus a supervised `/usr/bin/perl` child — so "one
  static binary, no dependencies" is **not** achievable on macOS for the media
  half.
- Dependence on an undocumented allowance Apple can revoke at any point
  release. The design must degrade to AppleScript, not break.
- It exposes the **system-selected** session, not an enumerable session list.
  Windows SMTC ranking has no macOS counterpart; the ranking code in
  `smtc/mod.rs` is partly Windows-semantic even though it imports nothing.

**Approaches the sibling project ruled out, so this one need not re-litigate
them:** `MPNowPlayingInfoCenter` / `MPRemoteCommandCenter` (publish/receive for
*your own* app), MusicKit `SystemMusicPlayer` (Music.app only), reflection into
private internals (does not bypass server-side authorization), CoreAudio taps
and virtual output devices (consent and routing burden, samples carry no
metadata), Spotify Web API (OAuth, network, five-user dev cap). A browser
extension remains viable but is product-sized. `kAudioHardwarePropertyProcess
ObjectList` can support an honest "Chrome: audio active" but **must never be
promoted into a playing state** — noted here only so a later reader does not
rediscover it as a good idea.

---

## Scope

**Replaces on macOS:** `ak820-timekeeper.py`, `nowplaying-macos.sh`, the
`install-agents.sh` LaunchAgent pair, and the per-transaction `ak820ctl` spawn.

**Keeps on Windows:** everything the current daemon does, unchanged in
behaviour. This plan must not regress a working system that has been live since
2026-09-06.

**Does not replace, either platform:** `ak820ctl`'s flash provisioning (erases
first, rare, interactive — never in an unattended daemon); `ak820keymap.py`,
`ak820health.py`, `ak820lighting.py` as diagnostics; the firmware.

**Non-goals:** a tray icon or menu-bar item; a GUI; Linux; browser-extension
media; Windows behaviour changes of any kind.

### Settled

- The crate stays at `ak820-agent/` — the wire protocol is firmware-versioned
  and belongs beside the firmware.
- **Python remains the clock oracle**, on both platforms, exactly as today. The
  C utility remains pinned. Parity is proven against them, never assumed.
- macOS support is **Apple Silicon first**; an Intel slice only if it is free.
- No new *direct* Rust dependency without an explicit decision recorded here.
  The Windows half resolves 15 packages from one direct dependency; that
  discipline is the reason the binary is 117 KB.

---

## Architecture: where the platform seam goes

The seam already half-exists. Formalise it as traits, implement twice.

```
ak820-agent/src/
  clock/        transaction, scheduler, cache, set, lead   -- NEUTRAL, unchanged
  proto.rs      framing, correlation, validation           -- NEUTRAL, unchanged
  text/         folding, budgets, fold_table (generated)   -- NEUTRAL, unchanged
  health.rs     page decode                                -- NEUTRAL, unchanged
  media/        snapshot model, expiry, position ticking   -- NEUTRAL (from smtc/mod.rs)
  hid/          discovery policy, caps checking            -- NEUTRAL policy...
                                                              ...Windows path parsing MOVES OUT
  platform/
    windows/    hid transport, SMTC worker, Scheduled Task, QPC host clock
    macos/      hid transport (IOKit), media router, LaunchAgent, mach host clock
```

Four traits, and nothing else crosses:

| Trait | Windows | macOS |
|---|---|---|
| `HidTransport` | `CreateFile` + overlapped I/O | `IOHIDDevice` open/read/write |
| `HidDiscovery` | `CM_Get_Device_Interface_ListW` (opens nothing) | IORegistry property match (opens nothing) |
| `MediaSource` | SMTC (`Windows.Media.Control`) | MediaRemote-via-perl, routed, AppleScript fallback |
| `ServiceInstaller` | Scheduled Task (`task.rs`) | LaunchAgent plist |
| `HostClock` | `GetSystemTimePreciseAsFileTime` | `clock_gettime(CLOCK_REALTIME)` + `mach_absolute_time` |

**The rule that makes this safe:** no `#[cfg]` inside shared files. Platform
code lives behind a trait in `platform/`, the way the sibling project settled
it (`macos-port-plan.md` §4, decision "Rejected: `#if WINDOWS` inside shared
files"). A shared file with two platforms' logic interleaved is how the clock
core would quietly diverge again — which is the thing this whole plan exists to
prevent.

### `MediaSource` must be the *lowest* common denominator, deliberately

SMTC enumerates sessions and ranks them; MediaRemote reports the one the system
picked. **Do not model macOS as a degenerate session list.** Model the trait as
"the current session, or none", implement Windows' ranking *behind* the trait,
and keep the neutral model to what both can honestly answer. Anything else
invents a session list on macOS that does not exist.

---

## Efficiency: the baseline, and targets that can fail

Measured on this Mac, 2026-09-10, with both current agents live:

| | now | target |
|---|---|---|
| Disk, agent runtime | **43 MB** venv + 36 KB `ak820ctl` | **≤ 1 MB** total payload |
| Resident, clock | **11.3 MB** (`python3`) | ≤ 5 MB |
| Resident, media | 3.2 MB (2× `bash`) + transient `osascript` | see caveat |
| Process spawns, steady state | **8 `osascript` per poll**, poll ≈ 3 s | **0** |
| Windows binary | 117 KB **[2026-09-05]** | no regression |

⚠️ **The memory target is the weak one, and the plan should not pretend
otherwise.** The MediaRemote helper is a `/usr/bin/perl` process: the sibling
project's is running on this machine right now at **7.9 MB RSS**
**[measured]**. Rust daemon + perl helper lands near where Python + bash is
today. **The honest claim is disk and CPU, not memory.** The CPU claim is
strong: 8 subprocess spawns every 3 s becomes an event-driven push with zero
steady-state spawns.

⚠️ **And there would then be two MediaRemote helpers on this machine** — one for
the Stream Deck plugin, one for the keyboard. ~16 MB of perl to read one
system-selected session twice. See [Open questions](#open-questions--needs-jds-decision).

---

## Install, signing and distribution

**Windows:** unchanged. `ak820 install` / `uninstall` / `status`, Scheduled
Task under `\ak820pro\`, zip from CI on a `v*` tag.

**macOS:** the same three verbs, backed by a LaunchAgent. The install must
work from a downloaded archive with **no toolchain, no Python, no Homebrew** —
the macOS equivalent of the phase-6b gate that forced v0.1.1 on Windows.

Signing and notarization follow `../streamdeck-now-playing/build/` exactly,
which is proven on this Apple ID:

- `notarize-setup.sh` stores an app-specific password as a **notarytool
  keychain profile**, once. The password is never an argv (readable via `ps`),
  never written to disk, never echoed — `expect(1)` drives notarytool's secure
  prompt. **Reuse this script's approach verbatim; do not invent a second
  credential path.**
- `package-macos.sh` signs with a `Developer ID Application` identity
  (env-overridable), notarizes, staples.

Three traps carried over, two of which do **not** apply to us and should be
recorded as such so nobody re-derives them:

- ⚠️ **A quarantine attribute anywhere in the payload is fatal**, and presents
  as a silent termination with no log. Strip xattrs after building. **Applies
  to us.**
- **Self-contained publish is mandatory** — a .NET framework-dependent publish
  runs from a terminal but not when spawned by a parent with a different
  environment. **Does not apply**: a Rust binary is self-contained by nature.
  This is a genuine simplification over the sibling project.
- **The .NET hardened-runtime entitlements** (`allow-jit`,
  `allow-unsigned-executable-memory`, `disable-library-validation`) exist
  because .NET JITs. **A Rust binary needs none of them** — start from an empty
  entitlements file and add only what is proven necessary. ⚠️ **Open:** whether
  loading our signed dylib into `/usr/bin/perl` needs anything at all on
  *our* side. perl is Apple-signed with its own hardened runtime; the sibling
  project does this successfully, so the answer is probably "nothing", but it
  is unverified for a non-.NET parent. **Spike S3.**
- Stapling: the sibling could not staple a bare executable and relies on
  Gatekeeper's online check. **We can do better** — ship a `.pkg` or `.dmg`,
  which *can* be stapled, and offline installs then work. Decide in Phase 6.

---

## Phases, with gates that can actually fail

Spikes first: **S1 and S2 can each kill or reshape the plan, and both are
cheap.** Do not start Phase 0 until both have answered.

| # | Work | Gate |
|---|---|---|
| **S1** | MediaRemote via perl host, driven from Rust | A **browser** session (YouTube in Chrome) yields title/artist/state to a Rust supervisor over line-JSON; the Music.app stale case reproduces; every call bounded; helper death degrades to AppleScript rather than hanging. **If this fails, the media half reduces to porting today's AppleScript and the capability gain evaporates** — the plan is still worth doing for the clock, at much reduced value. |
| **S2** | IOKit HID discovery + transport | Open **exactly one** device; VID/PID/usage read from the IORegistry with **nothing opened** to decide; `ak820 info` on macOS equals `ak820ctl info` byte for byte — the same gate Windows phase 0 had. |
| **S3** | Signing shape | An ad-hoc-signed Rust binary + signed dylib, hosted by perl, runs under the hardened runtime; the minimal entitlement set is established empirically (hypothesis: empty). |
| **0** | Platform seam, no behaviour change | Windows behaviour identical; **all 305 unit tests + 9 integration tests still pass**; `hid/path.rs` moved to `platform/windows/` with its tests; the neutral core compiles for `aarch64-apple-darwin` with a stub backend. **Gate fails if any Windows-observable behaviour changes.** |
| **1** | macOS HID transport | S2's gate, now through the real trait, plus wrong-interface rejection, malformed-report rejection, timeout, unplug mid-transaction, and **traced opens showing nothing unrelated was touched** (see [G-A](#g-a--open-nothing-you-did-not-mean-to)). |
| **2** | macOS clock, read then set | Captured replies decode identically to the pinned C **on macOS**; then the scheduler and SOF-bias learner replayed against `ak820-timekeeper.py`'s own macOS log, matching decisions **and next state**, the way phase 3a did on Windows. Plus a **no-worse-than-Python** check on live drift over a normal working day — not a soak, just evidence the port did not regress it. **This is the phase that earns the project.** |
| **3** | macOS media | Router works: browser via MediaRemote, Music via AppleScript, bounded calls, helper-loss fallback. **Plus [G-B](#g-b--a-tcc-revocation-must-be-visible).** Text reaching the LCD is byte-identical to what `nowplaying-macos.sh` would have pushed for the same track (folding parity). |
| **4** | `install` / `uninstall` / `status` on macOS | LaunchAgent registered, survives logout/login and sleep/wake; **refuses to run beside the Python agents** the way the Windows installer refuses (one clock owner, enforced not intended); rollback to the Python pair proven, not merely described. |
| **5** | Efficiency | The table above, measured, with the memory caveat stated honestly rather than met by redefinition. |
| **6** | Signed release | **Clean-Mac install from Releases with no toolchain, no Python, no Homebrew.** Gatekeeper reports `source=Notarized Developer ID`. Stapled if we ship a `.pkg`/`.dmg`. This is the macOS phase-6b and deserves the same suspicion — v0.1.0 shipped a wrong `INSTALL.txt` and cost a release. |

**Every phase ends with an external audit**, per the convention in
`AK820-AGENT-PLAN.md`. The gate proves the phase does what it claims; the audit
looks for what nobody thought to claim.

### G-A — open nothing you did not mean to

`hid/path.rs`'s discipline, restated as a gate on both platforms: **the decision
of which device to open is made from properties read without opening.** On
Windows that is `CM_Get_Device_Interface_ListW`; on macOS the IORegistry.
Evidence is a **trace of opens**, not an assertion. Note this gate stands on
its own engineering merit and does **not** depend on the UPS incident, which
may be misattributed (see the corrections section near the top of this file).

### G-B — a TCC revocation must be visible

`BACKLOG.md` (line 173): `nowplaying-macos.sh` sends `osascript` stderr to
`/dev/null` in all 9 places, so Automation permission **revoked while running**
is silent until restart — the agent just looks like nothing is playing.

The rewrite kills this by construction: Rust's `Command` hands back stdout,
stderr and exit status separately; discarding stderr would take deliberate
effort. **The gate is behavioural, not structural:** revoke Automation consent
mid-run and assert the denial surfaces in `ak820 status` and the log within one
poll interval. A structural claim ("we capture stderr now") does not pass.

---

## Risks

| Risk | Severity | Response |
|---|---|---|
| Apple revokes the platform-binary allowance | **High** — removes the capability gain | Router already falls back to AppleScript; ship that path live from day one, not as dead code |
| S1 fails outright | High | Plan still stands on the clock; restate the value honestly rather than proceeding as if unchanged |
| Regressing the live Windows daemon | **High** — it has been in daily use since 2026-09-06 | Phase 0 gate is "no Windows-observable change"; audit before merging the seam |
| Clock parity passes on fixtures but drifts live | High — the failure is a plausible wrong time | Phase 2 replays the *macOS* log, not the Windows one, and adds a live no-worse-than-Python check |
| Two MediaRemote helpers on one machine | Low, but wasteful and slightly absurd | [Open question 3](#open-questions--needs-jds-decision) |
| macOS version drift breaks IOKit/MediaRemote | Medium | Pin the tested OS in the plan the way `26.5.2` is pinned next door; re-verify per major release |
| Scope creep into a menu-bar app | Medium | Named a non-goal above |

---

## Open questions — needs JD's decision

1. **The "on this machine" wording, in three files.** The UPS wedge is real;
   only its location is wrong (`CLAUDE.md`, `ak820-agent/Cargo.toml`,
   `AK820-AGENT-PLAN.md`). A one-word fix each, worth doing when one of those
   files is next open — not worth a commit of its own, and not blocking
   anything here. G-A does not rest on it.

2. **Two MediaRemote helpers, or one shared?** ⚠️ **Settled as (A), with the
   code shaped so (C) stays cheap** — recorded here because it is the one place
   this plan touches another project.

   | | A: two helpers | B: consume the plugin's | C: unified broker |
   |---|---|---|---|
   | Memory | ~16 MB perl | ~8 MB | ~8 MB |
   | Coupling | none | **severe** | moderate |
   | Things to install | 2 | 1 | **3** |
   | Blast radius when Apple breaks it | 2 fixes | 1 | 1 |
   | Work | small | medium | **large** |

   **(B) is disqualified, not merely worse.** The plugin's helper is a *child
   process of a Stream Deck plugin* on its parent's pipes — not an endpoint
   anything can attach to. The Stream Deck app owns its lifecycle, so quitting
   Stream Deck would silently kill now-playing on the keyboard. Making it
   attachable means building (C).

   **(C)'s real argument is not memory** — 8 MB is noise. It is that this
   approach rests on an *undocumented Apple allowance*, so when a point release
   breaks it you want one place to fix. Against that: a third installable with
   its own LaunchAgent, signing and notarization; a socket protocol needing
   versioning, reconnect and backpressure; a bootstrapping question (who
   installs it, what if both try); and it makes one component a hard dependency
   of two working systems. The flip side of "one place to fix" is "one place to
   break both."

   **The decision rests on separating *sharing the code* from *sharing the
   process*.** The expensive, fragile asset is the MediaRemote knowledge, not
   the perl process. Vendor the `.m` helper and its line-JSON protocol as a
   shared component with a **versioned protocol definition**, built into both
   projects. That captures nearly all of (C)'s maintenance benefit at almost
   none of its cost, and if a third consumer appears, promotion to a broker is
   lifecycle work over a protocol that already exists.

   Two facts support this. The protocol is **already** multi-consumer shaped:
   artwork is announced by sha1 and fetched on demand, so the keyboard never
   asks and carries no cost for a feature it does not want. And both consumers
   need a local fallback regardless (helper death → AppleScript), which removes
   most of (C)'s reliability upside.

   ⚠️ **Requires a decision in the sibling repo**, not just this one: the `.m`
   file and its protocol would move to a shared location and gain a version
   field. That is a change to a signed, notarized, working product.

3. **`.pkg`/`.dmg` (staplable, offline) or bare binary (online Gatekeeper
   check)?** The sibling had no choice; we do. Recommend `.pkg` for the
   stapling alone.

4. **Intel slice?** Recommend Apple Silicon only unless a universal binary is
   free, and say so in `INSTALL.txt` rather than letting it fail obscurely.

5. **Does this ship publicly, or is it personal-first like the firmware?** It
   changes how much the install has to defend against unknown machines, and
   therefore the size of Phase 6.

---

## References

- [`AK820-AGENT-PLAN.md`](AK820-AGENT-PLAN.md) — the Windows daemon; every
  phase-gate convention here comes from it
- [`AK820-AGENT-CLOCK-PARITY.md`](AK820-AGENT-CLOCK-PARITY.md),
  [`AK820-AGENT-CLOCK-TRANSACTION.md`](AK820-AGENT-CLOCK-TRANSACTION.md) — the
  clock contract, unchanged by this plan
- [`BACKLOG.md`](BACKLOG.md) — G-A (line ~379) and G-B (line ~173)
- `../streamdeck-now-playing/docs/macos-port-plan.md` §3.5 — the media
  approaches, including everything already ruled out
- `../streamdeck-now-playing/README.md` §14 — what shipped, and §14.6 for the
  packaging traps
- `../streamdeck-now-playing/src/NowPlaying.Media.Mac/native/nowplaying-mediaremote.m`
  — the helper, its line-JSON protocol and the Music.app `stale` case
- `../streamdeck-now-playing/build/{notarize-setup.sh,package-macos.sh}` — the
  credential and signing path to reuse
- `ungive/mediaremote-adapter` — prior art for the hosted-MediaRemote approach
  **[unverified]**
