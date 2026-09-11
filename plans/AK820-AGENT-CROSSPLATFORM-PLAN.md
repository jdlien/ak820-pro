# ak820-agent — one daemon for Windows and macOS — plan

**Status: drafted 2026-09-10, reviewed the same day, nothing built.** This plan turns the Windows-only
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

1. **One clock implementation that RUNS, instead of two.** (Strictly there are
   three and always will be: Python and the pinned C remain maintained oracles
   per Settled below. The win is that only one of them *runs*.) `clock/transaction.rs` (1,098),
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
4. **Disk, with a caveat that nearly cancels it.** 43 MB of venv **[measured]**
   against a 117 KB Windows binary **[measured 2026-09-05]** — ⚠️ **but the venv
   stays**, because Scope keeps `ak820health.py`, `ak820keymap.py`,
   `ak820lighting.py` and `setup.sh`. The saving is real only on a clean Mac
   that never had a venv, which is exactly the machine that was not paying the
   43 MB anyway. Keep this justification **last** and weakest, or drop it.

---

## ⚠️ Two corrections to the record, before anyone builds on them

**1. The UPS wedge happened, but not on this machine.** `CLAUDE.md`,
`ak820-agent/Cargo.toml` and `AK820-AGENT-PLAN.md` all say `hid_enumerate`
"wedged a UPS **on this machine**", citing `../jdrgb/docs/ups-wedge-incident.md`.
The owner confirms (2026-09-10) the wedge was real and is not to be confused
with a separate loose-cable fault resolved mid-development of jdups — but it
was **not this Mac**. A one-word fix at each site, not a reason to doubt the
rule. ⚠️ Two refinements from review: the phrase appears at **five** sites, not
three (`Cargo.toml:31`, `hid/device.rs:4-6`, `hid/path.rs:7-12`,
`ak820text.py:135-137`, plus `CLAUDE.md` and the Windows plan), and
`../jdrgb/docs/ups-wedge-incident.md` **is not checked out on this Mac** — only
jdups is. So this correction rests on the owner's recollection, tagged
**[owner statement, document not re-read]**, not on rereading the incident
report.

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
- **It is event-driven**, but not *purely*. MediaRemote pushes change
  notifications; the helper also runs a 30 s backstop publish and a 15 s
  heartbeat (`nowplaying-mediaremote.m:95-98`, `:339`). Those are not process
  spawns, but they are polling, and the plan must not claim otherwise.
- ⚠️ **The "Music.app is exempt" story is WRONG, and this plan was built on it
  for thirty minutes.** Sibling commit `fc70de4` (2026-09-10 **17:17**; this
  plan's first draft was saved **16:47**) diagnosed that hang as **ours, not
  Apple's**: the helper called `CFRunLoopRun()` from the dylib's *constructor*,
  and dyld holds its loader lock for the whole of an initializer — so a
  constructor that never returns blocks every `dlopen` in the process.
  Assembling Music's info decodes its artwork (`MRArtwork setImageData:` →
  ImageIO → `dlopen`), which is exactly the call that could not proceed.
  QuickTime answered because its session carried no artwork. Diagnosed from
  `sample(1)`; see `macos-port-plan.md:97-114`.

  **MediaRemote now answers for Music like everything else.** The router is
  therefore *not* "Music → AppleScript": AppleScript is the **fallback** for a
  stale provider or an unhealthy helper. ⚠️ `README.md` §14.2 was not touched by
  that commit and still describes the old exemption, so the two sources cited
  here **contradict each other** — `macos-port-plan.md` is the current one.

  **The constraint to carry if the dylib is ever reimplemented rather than
  vendored: the constructor must return.** All work belongs on its own queue.
  That is a load-bearing invariant, not a style note.
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
  Windows SMTC ranking has no macOS counterpart. ⚠️ macOS also hands over a
  *paused* app while another is still playing, which the sibling had to absorb
  with **5 s stickiness** (`MacMediaSessionService.cs:52-59`, `:225-240`).
  "Current session or none" without that flips the LCD to the wrong app.
- **Rate-aware position extrapolation is new work**, not something inherited
  from `smtc/mod.rs` (`macos-port-plan.md:802-805`).

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
- ⚠️ **Two dependency decisions this plan forces and did not declare.** Both
  must be settled in Phase 0, not discovered later:
  1. **IOKit + CoreFoundation with no crate** means hand-written bindings,
     manual CF ownership, run-loop scheduling and callback lifetimes — the
     hazard class `macos-port-plan.md:492-497` warns about. Either accept a
     crate or record the hand-roll deliberately.
  2. **The crate has no JSON parser** (`status.rs` writes `key=value`). The
     helper speaks line-JSON with escaped Unicode titles. Hand-parsing that is
     a bug source; record either the dependency or the hand-roll **with a fuzz
     corpus**.

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
  agent.rs      the daemon loop: where ALL FIVE traits meet -- 802 lines, MIXED
                                                              (Windows paths :193-201,
                                                               a Windows error in tests :755)
  platform/
    windows/    hid transport, SMTC worker, Scheduled Task, QPC host clock
    macos/      hid transport (IOKit), media router, LaunchAgent, mach host clock
```

Four traits, and nothing else crosses:

| Trait | Windows | macOS |
|---|---|---|
| `HidTransport` | `CreateFile` + overlapped I/O | `IOHIDDevice` open/read/write |
| `HidDiscovery` | `CM_Get_Device_Interface_ListW` (opens nothing) | IORegistry property match (opens nothing). ⚠️ Must also yield a **per-port controller id** for the clock seed's `cid` (`ak820-timekeeper.py:116-121`, `agent.rs:595-597`) — not just VID/PID |
| `MediaSource` | SMTC (`Windows.Media.Control`) | MediaRemote-via-perl, routed, AppleScript fallback |
| `ServiceInstaller` | Scheduled Task (`task.rs`) | LaunchAgent plist |
| `HostClock` | `GetSystemTimePreciseAsFileTime` | `clock_gettime(CLOCK_REALTIME)` + `mach_absolute_time` |

⚠️ **Known Windows-shaped code that is "neutral" only by import.** Each needs a
decision in Phase 0, not a discovery in Phase 1:

| Site | Why it does not port as-is |
|---|---|
| `hid/caps.rs:97-104` | requires input and output lengths == 33 as `HidP_GetCaps` reports them. **IOKit's max report size excludes the report id**, so this pure check rejects the correct device unless the backend compensates. |
| `proto.rs:62-69` | calls the 33-byte frame "what Windows actually moves"; `IOHIDDeviceSetReport` takes the report id as a separate argument. |
| `clock/cache.rs:311-317` | reads `USERPROFILE` first. |
| `hid/mod.rs:100-103`, `exchange.rs:77-84` | the `Stuck` / `Abandoned` model is about `CancelIoEx`. **Say what `Stuck` means on IOKit, or state it is unreachable there.** |
| `bin/ak820.rs` | Windows by meaning throughout (1,057 lines). |
| `bin/ak820-agent.rs:24` | carries `windows_subsystem` — needs a `cfg_attr` in a shared file, which is the one **admitted exception** to the rule below. |

**The rule that makes this safe:** no `#[cfg]` inside shared files, with the
single declared exception of the `windows_subsystem` attribute above. Platform
code lives behind a trait in `platform/`, the way the sibling project settled
it (`macos-port-plan.md` §4, decision "Rejected: `#if WINDOWS` inside shared
files"). A shared file with two platforms' logic interleaved is how the clock
core would quietly diverge again — which is the thing this whole plan exists to
prevent.

### ⚠️ macOS raw HID is EXCLUSIVE — a Windows fact was carried across unchecked

`CLAUDE.md` says the raw-HID interface is "shareable, not exclusive" and that
contention is over *replies*. **That was measured on Windows.** This repo's own
macOS files say the opposite, and say it from experience:

> "The raw HID interface is EXCLUSIVE: a second poller cannot open it and every
> push fails with 'exclusive access and device already open'. This has bitten
> twice, and the second time it masqueraded as a FIRMWARE fault"
> — `hostagent/nowplaying-macos.sh:13-17`, and again in `install-agents.sh:15-16`

hidapi on Darwin seizes the device; `ak820ctl.c` and `ak820text.py` open through
it with no non-exclusive call. **Every tool the Scope section keeps** —
`ak820health.py`, `ak820keymap.py`, `ak820lighting.py` and flash provisioning —
therefore takes the device away from the daemon while it runs. The daemon's open
fails with `kIOReturnExclusiveAccess`, and a seize *mid-transaction* starves a
read into the unresolved path, so `Presence::Busy` becomes routine rather than
exceptional on macOS.

Three consequences this plan must carry:

- **Phase 1 gains a gate:** a hidapi peer seizes the device during a live
  transaction, and the daemon recovers rather than wedging or lying.
- **Phase 4's "refuses to run beside the Python agents" is load-bearing on
  macOS** in a way it never was on Windows. It is not politeness; it is the
  only arbitration there is.
- **`Presence` is not a Windows-shaped state machine here.** Busy must be a
  normal, frequent, recoverable state — not a fault to be reported.

The sibling project hit the same wall from the other side and its arbitration
model is worth reading (`macos-port-plan.md:116-133`); its §14.5 records the
Stream Deck app seizing its own HID device with
`kIOHIDOptionsTypeSeizeDevice`, which is what killed that feature on macOS.

### `MediaSource` must be the *lowest* common denominator, deliberately

SMTC enumerates sessions and ranks them; MediaRemote reports the one the system
picked. **Do not model macOS as a degenerate session list.** Model the trait as
"the current session, or none", implement Windows' ranking *behind* the trait,
and keep the neutral model to what both can honestly answer. Anything else
invents a session list on macOS that does not exist. The pure ranking in
`smtc/mod.rs:144-172` and its captured regression tests move across intact —
`Snapshot` is already the neutral output — so **no Windows behaviour is lost**.

⚠️ **But the trait's FAILURE policy is undefined, and the two platforms want
opposite answers.** On Windows a failed read publishes idle (`agent.rs:274-285`)
— that is phase-0 audit finding 5, deliberate. The sibling's macOS service
deliberately does the reverse and **keeps the last snapshot** on a failed read
(`MacMediaSessionService.cs:404-414`), because a transient MediaRemote miss is
not evidence that playback stopped. `Health` semantics are part of the trait
contract; **this plan must pick one and say why**, rather than letting each
backend decide and calling that portability. Unresolved as of this draft.

---

## Efficiency: the baseline, and targets that can fail

Measured on this Mac, 2026-09-10, with both current agents live:

| | now | target |
|---|---|---|
| Disk, agent runtime | **43 MB** venv + 36 KB `ak820ctl` | **≤ 1 MB** total payload |
| Resident, clock | **11.3 MB** (`python3`) — ⚠️ re-read later as 7.2 MB; RSS drifts widely between samples and is a weak gate | ≤ 5 MB, ⚠️ **undefined once clock and media share one process** — restate as one total |
| Resident, media | 3.2 MB (2× `bash`) + transient `osascript` | see caveat |
| Process spawns, steady state | **8 `osascript` per poll**, poll ≈ 3 s — ⚠️ plus the timekeeper's own: `ioreg -p IOUSB -w0 -l` every 15 s while the cache lacks a bias (`ak820-timekeeper.py:117`) and 2–3 `ak820ctl` per sync | **0 in the good case** — ⚠️ the failure path spawns: six 1.5 s timeouts then helper exit and restart with backoff, so the target must state a **failure-mode spawn rate** too, or it passes only while nothing goes wrong |
| Windows binary | 117 KB **[2026-09-05]** | ⚠️ a **bound** (say ≤ 150 KB), not "no regression" — equality fails trivially on any trait refactor |

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
- ⚠️ **The real macOS analogue of the .NET launch trap is TCC attribution, and
  it was missing.** Automation consent is keyed to the *responsible* process;
  the sibling warns the prompt may not appear for a background-launched one
  (`README.md:979-981`). The existing workaround (`nowplaying-macos.sh:98-99`)
  grants **Terminal**, not the daemon, and does not transfer to a signed
  binary. Worse, **ad-hoc signing changes the cdhash on every rebuild**, so TCC
  identity churns and G-B's revoke test is confounded — S3 must use a stable
  identity. And G-B only fires while the AppleScript path is *in use*: with
  MediaRemote primary, revocation is invisible unless the fallback is forced.
  If anything ever sends Apple events in-process rather than via `osascript`,
  the hardened runtime needs the apple-events entitlement and the
  empty-entitlements hypothesis fails **silently**.
- **Self-contained publish is mandatory** — a .NET framework-dependent publish
  runs from a terminal but not when spawned by a parent with a different
  environment. **Does not apply**: a Rust binary is self-contained by nature.
  This is a genuine simplification over the sibling project.
- **The .NET hardened-runtime entitlements** (`allow-jit`,
  `allow-unsigned-executable-memory`, `disable-library-validation`) exist
  because .NET JITs. **A Rust binary needs none of them** — start from an empty
  entitlements file and add only what is proven necessary. ⚠️ **The "unverified for a non-.NET parent" question was confused and is
  withdrawn**: which dylibs perl may load is governed by **perl's** own
  entitlements, not the loading parent's. What is genuinely on our side is
  narrower — **the dylib must be signed and unquarantined**, and the signing
  identity must be **stable across rebuilds** so TCC does not churn (see the
  attribution note above). That is what **S3** tests.
- Stapling: the sibling could not staple a bare executable and relies on
  Gatekeeper's online check. We can do better, but ⚠️ **not for free**: a
  stapled `.pkg` needs a **Developer ID Installer** certificate, which is
  distinct from the Application identity in `package-macos.sh:29` and is not
  proven to exist on this Apple ID. A **`.dmg` staples with the Application
  cert alone.** A `.pkg` also installs as root while the LaunchAgent is
  per-user, so the user still runs `ak820 install` afterwards — which removes
  most of its advantage. **Recommend `.dmg`**, pending confirmation of which
  certificates exist.

---

## Phases, with gates that can actually fail

Spikes first: **S1 and S2 can each kill or reshape the plan, and both are
cheap.** Do not start Phase 0 until both have answered.

| # | Work | Gate |
|---|---|---|
| **S1** | MediaRemote via perl host, driven from Rust | A **browser** session (YouTube in Chrome) yields title/artist/state to a Rust supervisor over line-JSON; and a **Music.app** session both resolve — ⚠️ *not* "the Music stale case reproduces", which `fc70de4` made unreachable except by reintroducing the deadlock. Every call bounded. **Helper supervision is specified, not assumed**: silence detection, restart backoff, a healthy-run rule and kill-on-silence, mirroring `MediaRemoteHost.cs:67-81`, `:192-207`. The reader lives on **its own thread**, for the reason `smtc/worker.rs:1-11` gives. **If this fails, the media half reduces to porting today's AppleScript and the capability gain evaporates** — the plan is still worth doing for the clock, at much reduced value. |
| **S1b** | Revocation must be *visible* | ⚠️ The likeliest revocation shape is **not** helper death. If Apple extends the 15.4 refusal to perl, the helper stays alive, heartbeats, and emits `bundle: null` forever — indistinguishable from "nothing is playing", and for browsers there is no fallback at all. Gate: a canary cross-checking a null MediaRemote against AppleScript's `player state`, which logs the refusal and switches primary. Without this the AppleScript fallback is wishful for the case most likely to happen. |
| **S2** | IOKit HID discovery + transport | Open **exactly one** device; VID/PID/usage read from the IORegistry with **nothing opened** to decide; `ak820 info` on macOS equals `ak820ctl info` byte for byte — the same gate Windows phase 0 had. **Plus the exclusivity reality**: a hidapi peer (`ak820health.py`) seizes the device mid-transaction and the daemon recovers rather than wedging or reporting a firmware fault. Also resolve the report-id/length mismatch (`caps.rs:97-104`). |
| **S3** | Signing shape | An ad-hoc-signed Rust binary + signed dylib, hosted by perl, runs under the hardened runtime; the minimal entitlement set is established empirically (hypothesis: empty). |
| **0** | Platform seam, no behaviour change | ⚠️ **"Identical" was unfalsifiable as first written**: a test *count* legitimately changes when `host.rs` tests move, and `hid::Error::Open` wraps a `windows::core::Error` (`hid/mod.rs:63-76`) that must become neutral, so log text necessarily changes. **Observable is therefore defined as wire bytes, status-file keys, log grammar and timing statistics** — not strings, not counts. The real gate is the one Windows phase 0 used and this one omitted: **reinstall from the phase-0 build and reproduce the takeover table** (`AK820-AGENT-PLAN.md:265-275`) against the pre-refactor log over the same duration, plus the five CLI commands (`:46-48`). ⚠️ **Where it runs is unspecified and must be settled**: CI is `windows-latest` with no board (`.github/workflows/agent.yml:25-41`), `.cargo/config.toml` pins static CRT to the msvc target only, and cross-compiling from the Mac is unaddressed. `agent.rs` is the file most at risk. |
| **1** | macOS HID transport | S2's gate, now through the real trait, plus wrong-interface rejection, malformed-report rejection, timeout, unplug mid-transaction, and **traced opens showing nothing unrelated was touched** (see [G-A](#g-a--open-nothing-you-did-not-mean-to)). |
| **2** | macOS clock, read then set | Captured replies decode identically to the pinned C **on macOS**; then the scheduler and SOF-bias learner replayed against `ak820-timekeeper.py`'s own macOS log, matching decisions **and next state**, the way phase 3a did on Windows — the macOS timekeeper log exists (241 KB, same format), so that half is achievable. ⚠️ **Fixture parity CANNOT see a self-consistent wrong time**, which is the exact failure this phase exists to prevent: both the GET's residual and the SET's payload go through `host.local()` (`transaction.rs:174`, `:205-208`), so a macOS `local()` off by an hour yields a **zero residual and a board an hour wrong**. Captured-reply decoding never exercises localtime at all — the oracle takes `host_mid_sod` as an argument (`scripts/clock_oracle.c:14`). Windows covered this with hourly sweeps across 2026–2099 against the oracle CRT (`host.rs:294-347`), which cannot compile here. **So this phase also requires**: an hourly-sweep test against libc `localtime_r` (what `ak820ctl.c:159`, `:198`, `:256` call), a TZ-change test, **independent** reads via the pinned `ak820ctl clock --read` with the daemon paused, and a human reading the LCD against a reference clock. "No worse than Python" compares *self-reported* residuals and would absorb a transport timestamping bias into the lead learner as zero. **This is the phase that earns the project.** |
| **3** | macOS media | Router works: **MediaRemote for everything including Music** (post-`fc70de4`), with AppleScript as the fallback for a stale provider or unhealthy helper — not as Music's route. Bounded calls, supervised helper, 5 s stickiness so a paused app does not steal the band. **Plus [G-B](#g-b--a-tcc-revocation-must-be-visible) and the S1b canary.** ⚠️ **The old "byte-identical to what `nowplaying-macos.sh` would have pushed" gate could not fail honestly**: folding parity is already proven at generation time across every scalar, and the genuinely new variable is the *source* — MediaRemote's title/artist and AppleScript's fields can legitimately differ for the same track. Split into (a) folding parity on **identical input**, an existing test, and (b) a **documented source comparison** where each difference is explained rather than counted as a defect. |
| **4** | `install` / `uninstall` / `status` on macOS | LaunchAgent registered, survives logout/login and sleep/wake; **refuses to run beside the Python agents** the way the Windows installer refuses (one clock owner, enforced not intended); rollback to the Python pair proven, not merely described. |
| **5** | Efficiency | The table above, measured, with the memory caveat stated honestly rather than met by redefinition. |
| **6** | Signed release | **Clean-Mac install from Releases with no toolchain, no Python, no Homebrew.** Gatekeeper reports `source=Notarized Developer ID`. Stapled if we ship a `.pkg`/`.dmg`. This is the macOS phase-6b and deserves the same suspicion — v0.1.0 shipped a wrong `INSTALL.txt` and cost a release. ⚠️ **Name the test bed**: Windows had Sandbox, but a fresh macOS *user account* does not reset Gatekeeper's per-file assessment or the binary's TCC state — only a VM is a real clean machine. Unnamed, this gate is an intention. |

**Every phase ends with an external audit**, per the convention in
`AK820-AGENT-PLAN.md`. The gate proves the phase does what it claims; the audit
looks for what nobody thought to claim.

### G-A — open nothing you did not mean to

`hid/path.rs`'s discipline, restated as a gate on both platforms: **the decision
of which device to open is made from properties read without opening.** On
Windows that is `CM_Get_Device_Interface_ListW`; on macOS the IORegistry.
Evidence is a **trace of opens**, not an assertion.

⚠️ **Scope correction: G-A closes nothing on macOS.** Its BACKLOG entry
(`BACKLOG.md:379-398`) is explicitly about **Windows** `hid_enumerate` opening
every device, and this plan argues in its own corrections section that macOS
reads properties without opening — which hidapi's Darwin enumerate also does.
So of the "two named defects" in the Why section, **only G-B is a macOS
defect**; G-A is a Windows-side discipline worth preserving, not a gain. The
justification list overstated by one.

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
| Apple revokes the platform-binary allowance | **High** — removes the capability gain | ⚠️ The fallback only covers helper *death*. The likely shape is a live helper emitting `bundle: null` forever, which reads as idle — gate **S1b** exists for exactly this |
| **macOS raw HID is exclusive** and every kept diagnostic seizes it | **High** — presents as a firmware fault, and has twice | Phase 1 seize gate; Phase 4 refusal is arbitration, not politeness; `Presence::Busy` treated as normal |
| **perl is a deprecated macOS runtime** (since 10.15) | Medium — a *separate* risk from the MediaRemote allowance, and not previously listed | If perl is removed, the host must move to another Apple platform binary; keep the host choice behind one seam in the helper supervisor |
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

## Review disposition — Fable, 2026-09-10

Full report: [`review-fable-crossplatform-2026-09-10.md`](review-fable-crossplatform-2026-09-10.md).
Seventeen findings, five High. Every one is dispositioned; none was waved off.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | High | The Music.app exemption was a loader-lock deadlock in the sibling's own helper, fixed by `fc70de4` **30 min after this plan was saved**; the S1 gate could only pass by reintroducing it | **Accepted, design changed.** Router rewritten — MediaRemote serves Music too, AppleScript is the fallback. S1 and Phase 3 gates rewritten. Constructor-must-return recorded as a load-bearing invariant. Verified independently: `fc70de4` 17:17 vs plan mtime 16:47 |
| 2 | High | AppleScript fallback does not cover the likeliest revocation shape (live helper, `bundle: null` forever) | **Accepted.** New gate **S1b**: a canary cross-checking null MediaRemote against AppleScript `player state`. Risk row rewritten |
| 3 | High | Phase 0's gate cannot fail, and never says where it runs | **Accepted.** "Observable" now defined as wire bytes / status keys / log grammar / timing stats; the Windows takeover-table reproduction is now the real gate; build host flagged unsettled; `agent.rs` added to the diagram |
| 4 | High | Phase 2 cannot see a self-consistent wrong time — both residual and payload go through `host.local()` | **Accepted.** Added libc `localtime_r` hourly sweep, TZ-change test, independent `ak820ctl clock --read` with the daemon paused, and a human LCD check |
| 5 | High | macOS raw HID is **exclusive**; the plan carried a Windows measurement across | **Accepted, new section.** Every kept diagnostic seizes the device. Phase 1 seize gate, Phase 4 refusal reframed as arbitration, `Presence::Busy` normalised, new risk row |
| 6 | Med | G-A closes nothing on macOS; "on this machine" is at five sites not three; the UPS doc is not on this Mac | **Accepted.** Justification list corrected to one macOS defect; correction now tagged **[owner statement, document not re-read]** |
| 7 | Med | "No polling in steady state" is false; "0 spawns" holds only while nothing fails | **Accepted.** 30 s backstop and 15 s heartbeat recorded; efficiency row now demands a failure-mode spawn rate; reader-on-own-thread carried into S1 |
| 8 | Med | More Windows-shaped "neutral" code than `path.rs` | **Accepted.** Table added (`caps.rs` report-id/length, `proto.rs` 33-byte frame, `cache.rs` `USERPROFILE`, `Stuck`/`CancelIoEx`, both bins); `windows_subsystem` declared as the one `#[cfg]` exception |
| 9 | Med | `MediaSource` failure policy undefined; platforms want opposite policies; macOS needs stickiness | **Accepted, left open deliberately.** Both policies recorded with their reasons and marked "this plan must pick"; 5 s stickiness added |
| 10 | Med | Phase 3's parity gate cannot fail honestly | **Accepted.** Split into folding parity on identical input, plus a documented source comparison |
| 11 | Med | TCC attribution is the real analogue of the .NET launch trap; ad-hoc signing churns cdhash | **Accepted.** Added to Install; S3 now requires a stable identity |
| 12 | Med | S3's entitlement question was confused; `.pkg` needs a different certificate | **Accepted.** Question withdrawn (perl's entitlements govern, not ours); recommendation moved from `.pkg` to **`.dmg`** |
| 13 | Med | The disk justification does not survive the keep-list | **Accepted.** Demoted and caveated — the venv stays for the kept diagnostics |
| 14 | Low-Med | Zero-dependency FFI and JSON are undeclared decisions | **Accepted.** Both added to Settled as Phase-0 decisions, JSON with a fuzz corpus |
| 15 | Low | Phase 6 has no defined clean-Mac test bed | **Accepted.** A VM named; a fresh user account explicitly rejected |
| 16 | Low | Efficiency rows that cannot fail | **Accepted.** Binary size now a bound; RSS gate restated as one total; sampling variance noted |
| 17 | Low | Nits: three oracles not two, `cid` in discovery, perl deprecation | **Accepted.** All three carried |

**What the review confirmed as sound**, and is therefore not restated above:
every Windows-side fact checked (117 KB binary, one dependency → 15 packages,
305+9 tests, discovery opening nothing); the 69% arithmetic (4,331/13,814); the
packaging traps as transcribed; the Why section's refusal to claim precision;
and the two-helpers analysis — including that option B is disqualified because
the helper exits when its stdin closes (`nowplaying-mediaremote.m:285`), which
this plan had argued on weaker grounds.

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
