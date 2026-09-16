# ak820-agent — one daemon for Windows and macOS — plan

**Status: drafted 2026-09-10, reviewed the same day, finalized 2026-09-16, nothing built.** This plan turns the Windows-only
`ak820-agent/` crate into a cross-platform daemon that replaces the macOS
Python/bash agents as well, closes one named macOS defect (G-B), and ships signed
and notarized. Every open question that gates work is now decided — see
[Finalization](#finalization--2026-09-16) for what was measured and settled
that day, including **the macOS 27.0 upgrade** that landed hours before.

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
capability and G-B, none of which depend on a timing number. The
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
3. **One named macOS defect closes by construction rather than by patch** —
   [G-B](#g-b--a-tcc-revocation-must-be-visible), already in
   [`BACKLOG.md`](BACKLOG.md). This line said "two" until review:
   [G-A](#g-a--open-nothing-you-did-not-mean-to) is a Windows defect and a
   discipline to preserve on macOS, not a macOS gain.
4. **Disk, with a caveat that nearly cancels it.** 43 MB of venv **[measured]**
   against a 117 KB Windows binary **[measured 2026-09-05]** — ⚠️ **but the venv
   stays**, because Scope keeps `ak820health.py`, `ak820keymap.py`,
   `ak820lighting.py` and `setup.sh`. The saving is real only on a clean Mac
   that never had a venv, which is exactly the machine that was not paying the
   43 MB anyway. Keep this justification **last** and weakest, or drop it.

⚠️ **Owner statement, 2026-09-16: the Mac "seems to suffer a lot of overhead"
from the now-playing agent, and fixing that is what the owner most hopes this
port delivers.** That is a priority, and it is recorded as one. **Measured the
same afternoon, and the complaint holds:** while Music plays, the now-playing
agent costs about **30% of one core, continuously** — 19.7% in its own child
processes, plus 8–12% in `tccd`, `launchservicesd`, `trustd` and
`runningboardd` handling its launches. See [Efficiency](#efficiency-the-baseline-and-targets-that-can-fail).
That is Phase 5's "before" column, taken with a script kept for the "after".
Shipping the **media half ahead of the clock** is therefore worth deciding, as
Windows did (now-playing live in 4a, clock in 3b/4b).

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
- **Two dependency decisions this plan forced — DECIDED 2026-09-16:**
  1. **IOKit + CoreFoundation: hand-rolled — CONFIRMED by S2, 2026-09-16.**
     The surface came to 37 functions and 3 statics (`sys.rs`, 225 lines),
     with ownership in two ~40-line RAII wrappers (`cf.rs`) and 27 `unsafe`
     sites outside the declarations. Nothing in it wanted a crate. About
     25 C functions declared in `platform/macos/`, with one small RAII owner
     that `CFRelease`s. The hazard class `macos-port-plan.md:492-497` warns
     about (manual CF ownership, run-loop scheduling, callback lifetimes) is
     the same with or without a crate — a binding crate removes the `extern`
     block, not the lifetimes. **Revisit if S2's ownership code is ugly**; the
     fallback is `objc2-io-kit` + `objc2-core-foundation`, target-gated to
     macOS, recorded here before it is added.
  2. **JSON: hand-rolled flat-object reader, no dependency.** Every message the
     keyboard consumes is one flat object (`hello`, `now`, `tick`, `command`,
     `fatal`; `artwork` is only ever sent on request, and the keyboard never
     requests it). ⚠️ **Build it from captured output, not the protocol
     comment**: the live `now` message on 2026-09-16 carried `elapsedAt`
     (a float Unix time) and `playing`, neither of which the header of
     `nowplaying-mediaremote.m:15-16` lists. Tested against a corpus
     **generated by Python's `json`** — the same oracle pattern as
     `scripts/gen_ascii_fold.py` — covering `\uXXXX` escapes, surrogate
     pairs, NSJSONSerialization's `\/`, and float formatting.
- **Ships publicly, like Windows — DECIDED 2026-09-16.** A notarized, stapled
  **`.dmg`** attached to the same GitHub Release as the Windows zip, **Apple
  Silicon only**, said so in `INSTALL.txt`. Personal-first in the firmware's
  sense (one tested OS, no support promise), but the clean-machine gate stays.

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

Five traits, and nothing else crosses:

| Trait | Windows | macOS |
|---|---|---|
| `HidTransport` | `CreateFile` + overlapped I/O | `IOHIDDevice` open/read/write |
| `HidDiscovery` | `CM_Get_Device_Interface_ListW` (opens nothing) | IORegistry property match (opens nothing): `IOServiceGetMatchingServices` + property reads, then `IOHIDDeviceCreate` on the one chosen service. ⚠️ **Not `IOHIDManagerOpen`** — Apple documents it as opening every device the manager matched, current and future; it is macOS's `hid_enumerate` trap. ⚠️ Must also yield a **per-port controller id** for the clock seed's `cid` (`ak820-timekeeper.py:116-121`, `agent.rs:595-597`) — not just VID/PID; the Python reads `locationID` from `ioreg -p IOUSB`, so the registry property is the same value with no spawn |
| `MediaSource` | SMTC (`Windows.Media.Control`) | MediaRemote-via-perl, routed, AppleScript fallback |
| `ServiceInstaller` | Scheduled Task (`task.rs`) | LaunchAgent plist |
| `HostClock` | `GetSystemTimePreciseAsFileTime` | `clock_gettime(CLOCK_REALTIME)` + `mach_absolute_time` |

⚠️ **Known Windows-shaped code that is "neutral" only by import.** Each needs a
decision in Phase 0, not a discovery in Phase 1:

| Site | Why it does not port as-is |
|---|---|
| `hid/caps.rs:97-104` | requires input and output lengths == 33 as `HidP_GetCaps` reports them. **IOKit's max report size excludes the report id**, so this pure check rejects the correct device unless the backend compensates. **Measured by S2: `MaxInputReportSize` 32, `MaxOutputReportSize` 32.** |
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

⚠️ **Decided 2026-09-16: the daemon opens the board per interaction on macOS,
never for its lifetime.** `BACKLOG.md`'s process-churn entry (`5af84fb`)
suggests holding the interface open for the process lifetime to retire the
`mkdir` lock. On macOS that locks the kept diagnostics out **permanently**:
`ak820health.py` works today only by retrying 12 × 250 ms across the gaps
between the agents' brief opens (`ak820health.py:59-80`). The Windows daemon
already opens per interaction — publish, health and clock each call
`open_board()` (`agent.rs:362`, `:425`, `:498`) — so this is the existing
design carried across, not a new one. The `mkdir` lock's job (one instance)
passes to the daemon's own single-instance guard.

⚠️ **The plan assumed the hidapi peer always wins. MEASURED 2026-09-16 (S2),
and it does — cheaply:**

- A **fresh** non-seizing open while a hidapi peer holds the device fails at
  once with `kIOReturnExclusiveAccess` → `Presence::Busy`.
- A hidapi peer opening **while we are already open** succeeds; from then on
  our **writes fail within milliseconds** with `kIOReturnExclusiveAccess`
  (not silent timeouts), and the same handle recovers the moment the peer
  closes — no reopen needed.
- A seizing open of ours makes the hidapi peer's open fail.
- ⚠️ **Two non-seizing IOKit clients see each other's reports**, exactly as
  Windows handles do: a held handle received another client's `FC_INFO` reply
  and the bash agent's playback echo. So `proto.rs`'s correlation and echo
  rules are required on macOS too, and the daemon and the `ak820` CLI must
  both use them.

So in 4a **the daemon is the side that loses**: when the timekeeper's
`ak820ctl` seizes mid-cycle, the daemon's write fails fast and it retries next
poll. The timekeeper can still lose a race in the opposite order — its
`xfer()` taking the daemon's echo — which is what 4a's gate counts.

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

⚠️ **The trait's FAILURE policy looked like the two platforms wanting opposite
answers.** On Windows a failed read publishes idle (`agent.rs:274-285`) — the
phase-3a/4a audit's finding 5, deliberate. The sibling's macOS service
deliberately does the reverse and **keeps the last snapshot** on a failed read
(`MacMediaSessionService.cs:404-414`), because a transient MediaRemote miss is
not evidence that playback stopped.

**Decided 2026-09-16: one policy, and the platforms define its input, not its
output.** The neutral agent keeps Windows' rule unchanged — **a failed source
publishes idle** — because the reason behind it is platform-free: keeping the
previous track refreshes it every 30 s and never lets the firmware's expiry
take it down. What each backend owns is **what counts as failed**, by its own
mechanics:

- **Windows:** `last_poll_ok` exactly as today. No behaviour change.
- **macOS — one rule, revised after the 2026-09-16 review (finding 3):
  failed means no line read from the helper for 60 s.** Death and `fatal` do
  **not** trip it; they **start** that clock, and the supervisor restarts the
  helper inside it. Until the clock runs out the backend keeps reporting the
  last snapshot, and the 30 s keepalive re-asserts that text well inside the
  firmware's 180 s expiry (`display.c:1684`). 60 s matches the sibling's
  `SilenceLimit` (`MediaRemoteHost.cs:76`, "generous on purpose").
  ⚠️ **Why not "dead or fatal fails at once", as first written:** the helper's
  six-timeout `fatal` + `exit(3)` (`nowplaying-mediaremote.m:125-138`) is its
  *designed* recovery, and the sibling restarts it in 2 s. Failing at once
  turned every such recovery into CLEAR followed 2 s later by two SET_LINEs —
  the double flash `nowplaying-macos.sh`'s comments exist to prevent. And the
  old 30 s silence threshold left ~10 s of margin, because the heartbeat shares
  a queue with calls that can block it for 4.5 s per publish.
  ⚠️ **"A line" means proof of life: `now`, `tick` or `command` — never
  `hello`** (found building S1). `hello` comes from the constructor before
  the queue runs, so a crash loop sends one per restart.
  ⚠️ **Silence is judged from the reader's last read, and never while the pipe
  holds unread bytes.** A daemon frozen by SIGSTOP (the Phase 5a measurement)
  or asleep with the Mac wakes to a long gap and a full pipe; the watchdog
  must let the reader drain before it can call the helper silent, or every
  resume kills a healthy helper.

The sibling's keep-last-snapshot instinct is honoured by that clock, not by
a second policy. The **5 s stickiness** is a different thing — it is about what
"the current session" means on macOS — and lives **inside the macOS backend**,
never in the neutral model.

---

## Efficiency: the baseline, and targets that can fail

Measured on this Mac, 2026-09-10, with both current agents live:

| | now | target |
|---|---|---|
| Disk, agent runtime | **43 MB** venv + 36 KB `ak820ctl` | **≤ 1 MB** total payload |
| Resident, clock | **11.3 MB** (`python3`) — ⚠️ re-read later as 7.2 MB; RSS drifts widely between samples and is a weak gate | ≤ 5 MB, ⚠️ **undefined once clock and media share one process** — restate as one total |
| Resident, media | 3.2 MB (2× `bash`) + transient `osascript` | see caveat |
| **CPU, media agent, while Music plays** | **47.4 CPU-s per 240 s = 19.7% of one core**, in the agent's own children alone (50.6 / 38.4 / 53.2 s over three windows; kernel child accounting, exact) — plus **~20–30 s** more in system daemons that only move while it runs: `tccd` 5.6–12.0, `launchservicesd` 6.9–8.8, `trustd` up to 9.8, `runningboardd` ~5, `launchd` ~2.6 above its paused level. **Roughly 30% of one core, 2.5% of this 12-core Mac, around the clock while music plays** **[measured 2026-09-16]** | **≤ 1% of one core** while playing. The event-driven helper it replaces the polling with measured **0.76 CPU-s in 98 min** (the sibling's perl helper, same Mac, same afternoon, music playing for part of it) |
| Process spawns, steady state | **6–8 `osascript` per poll while playing**, poll = 3 s: **6** with Spotify playing, **7** with Music playing and Spotify closed (the 2026-09-16 measurement), **8** with Spotify open but stopped and Music playing (`nowplaying-macos.sh:110-118`). This row said 8, then 7; the review's finding 9 gave the full case split — ⚠️ plus the timekeeper's own: `ioreg -p IOUSB -w0 -l` every 15 s while the cache lacks a bias (`ak820-timekeeper.py:117`) and 2–3 `ak820ctl` per sync | **Stated per state, because the S1b canary spawns** (decided 2026-09-16): **0** while no AppleScript-scriptable player is running (the idle case, most hours); **≤ 1 per 60 s** while Spotify or Music is running but MediaRemote reports nothing; **0** while MediaRemote reports playback. ⚠️ Plus a **failure-mode rate**: six 1.5 s timeouts then helper exit and restart with backoff — without it the row passes only while nothing goes wrong |
| Windows binary | ⚠️ **`ak820-agent.exe` is 408,576 bytes** at `e8a4c16` and **409,600** after Phase 0 (`a46e770`), from CI's own artifacts **[2026-09-16]**. The 117 KB this row gave was measured on 2026-09-05, before the later phases landed (Phase 0 audit) | a **bound**, not "no regression" — equality fails trivially on any trait refactor: **≤ 450 KB** |

**How the CPU row was measured (2026-09-16, macOS 27.0, Music.app playing),
so Phase 5's "after" can be taken the same way:** `scripts/agent_overhead_macos.py`
alternates five 240 s windows — run, pause, run, pause, run — freezing the
agent with `SIGSTOP` in the pause windows and always `SIGCONT`ing on exit. The
agent's cost is its own `proc_pid_rusage` child CPU, which the kernel
accumulates for every reaped descendant and which matched `ps` to the
hundredth. The daemon costs are `ps` CPU deltas per window, compared across
run and pause, with a resolution floor of ~3–5 s per window (only the top 25
movers were kept). ⚠️ **Two things the method could not measure:**

- **Process launches.** The PID counter moved **1,068–1,604 per minute in
  every window, paused or not**. The paused windows were busier, not quieter:
  six `mdworker` processes were live, and post-upgrade Spotlight and media
  analysis (`mds_stores` 182–384 s, `mediaanalysisd` 94–313 s per window) were
  running the day of the 27.0 install. That noise swamps the agent's
  contribution. The script's own structure gives **about 20 launches per 3 s
  while playing** (7 `osascript`, each in a `$(…)` subshell, 2 `awk`, a
  `date`, a `sleep`, and a venv Python playback push every poll), so roughly
  400 a minute. That figure is **derived from the script, not measured**.
- **WindowServer and Music.** Neither moved measurably. WindowServer ran
  105–124 s per window either way, and Music 11–15 s. The reported
  FocusManager churn may exist, but it is below this method's resolution.

⚠️ **The machine's larger load that day was not the agent.** Spotlight
re-indexing and media analysis after the upgrade ran at **1.25–2.5 cores**
across the same windows. The agent is a steady ~30% of one core. The rest will
settle on its own; the agent's cost will not.

⚠️ **The memory target is the weak one, and the plan should not pretend
otherwise.** The MediaRemote helper is a `/usr/bin/perl` process: the sibling
project's ran at **7.9 MB RSS** on 2026-09-10 and **17.8 MB** on 2026-09-16
after 98 minutes on macOS 27.0 **[measured]**. Rust daemon + perl helper lands near where Python + bash is
today. **The honest claim is disk and CPU, not memory.** The CPU claim is now
**measured, not argued**: about 30% of one core while music plays, against a
helper that used 0.76 CPU-seconds in 98 minutes. The polling becomes a mostly
event-driven push whose spawn rate is zero while idle and bounded by the S1b
canary otherwise.

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
  Gatekeeper's online check. We can do better. **Decided 2026-09-16: `.dmg`.**
  The certificate question is answered **[measured]**: a **Developer ID
  Installer** identity *does* exist on this Apple ID, so a `.pkg` was not
  blocked — it lost on shape. A `.pkg` installs as root while the LaunchAgent
  is per-user, so the user still runs `ak820 install` afterwards, and a `.dmg`
  holding `ak820`, the dylib and `INSTALL.txt` is the step-for-step analogue of
  the Windows zip. A `.dmg` staples with the Application identity alone.
- **Sign by SHA-1, not by name — a nit, not a trap.** `security find-identity
  -v -p codesigning` lists `Developer ID Application: Joseph Lien (A93Q7MKECL)`
  **twice**, but both rows carry the **same** SHA-1 **[measured 2026-09-16]**:
  one certificate visible through two keychains, and the sibling signed by that
  name successfully. Passing the hash removes the question for good.
- ⚠️ **The copy-out path is untested and is where quarantine bites.** `ak820
  install` will copy the binary and dylib out of the mounted `.dmg` into
  `~/Library/Application Support/ak820pro/`. Whether the copies carry
  `com.apple.quarantine`, and whether a LaunchAgent-started daemon's perl child
  then loads the copied dylib **offline**, is Phase 6's gate — not an
  assumption.

---

## Phases, with gates that can actually fail

Spikes first: **S1 and S2 can each kill or reshape the plan, and both are
cheap.** Do not start Phase 0 until both have answered.

**Order — decided 2026-09-16: now-playing first, the clock soon after**, the way
Windows went (4a live before 3b/4b). The measured reason: while Music plays,
the media agent costs ~30% of one core, while the clock agent is cheap and
accurate. The table below keeps its numbers; **build them in this order:**

> **S1 → S2 → S1b, S3 → 0 → 1 → 3 → 4a → 5a** — *now-playing on the daemon,
> Python timekeeper still owns the clock* — **→ 2 → 4b → 5b → 6**

Nothing is skipped, only reordered: Phase 3 needs only Phase 1's HID transport,
not the clock. ⚠️ **Phase 6 (public release) stays last.** A public macOS
release without the clock would tell a clean Mac to leave the clock to a Python
agent it does not have — the exact `INSTALL.txt` mistake that cost Windows
v0.1.1. Until 4b, the daemon runs on this Mac from a local build, **signed
with the Developer ID identity** so TCC does not churn (S3).

| # | Work | Gate |
|---|---|---|
| **S1** | MediaRemote via perl host, driven from Rust | A **browser** session (YouTube in Chrome) yields title/artist/state to a Rust supervisor over line-JSON; and a **Music.app** session both resolve — ⚠️ *not* "the Music stale case reproduces", which `fc70de4` made unreachable except by reintroducing the deadlock. Every call bounded. **Helper supervision is specified, not assumed**: silence detection, restart backoff, a healthy-run rule and kill-on-silence, mirroring `MediaRemoteHost.cs:67-81`, `:192-207`. The reader lives on **its own thread**, for the reason `smtc/worker.rs:1-11` gives. **If this fails, the media half reduces to porting today's AppleScript and the capability gain evaporates** — the plan is still worth doing for the clock, at much reduced value. ✅ **The Apple half is answered on macOS 27.0 (26A428), 2026-09-16**: the sibling's dylib under `/usr/bin/perl` returned `bundle: com.google.Chrome`, title, artist, duration, `rate: 1`, `playing: true` for a YouTube video, and the owner confirmed the Stream Deck plugin showing it live. **The Rust supervisor half is still S1's work.** ⚠️ **S1 implements the revised failure rule** (see `MediaSource`): failed = 60 s with no line read, death and `fatal` start that clock rather than trip it, silence is judged from the reader's last read and never while the pipe holds unread bytes. Gate: SIGSTOP the supervisor for 240 s, resume, and the helper survives. ✅ **MET 2026-09-16** (`ak820-agent/spikes/s1-mediaremote/`, no dependencies): the Rust supervisor read Music.app's track (title, artist, duration, rate, `elapsedAt`) straight from MediaRemote, and a Chrome/YouTube session had answered the same helper that afternoon; frozen 240 s with the real helper and resumed — same helper pid, no kill, clean exit at stop. 19 tests: the flat JSON reader agrees with Python's `json` on **5,013** generated cases (which caught one real difference, `-0`), and six supervision tests through the real binary with a fake helper (designed `fatal` restart never reads as failed; a silent helper is killed and fails; oversized and garbage lines survive; stop closes stdin; frozen-supervisor resume). ⚠️ **One rule the spike added: `hello` is not proof of life.** It is emitted from the dylib's constructor before the helper's queue has run anything, so a helper crash-looping on a wedged MediaRemote sends one every restart; counting it would reset the failure clock forever and refresh a stale track indefinitely. Only `now`, `tick` and `command` count (`message.rs`, `Message::proves_liveness`), and a test pins it. The browser half of the gate is re-confirmed by the owner in S1b's session. |
| **S1b** | Revocation must be *visible* | ⚠️ The likeliest revocation shape is **not** helper death. If Apple extends the 15.4 refusal to perl, the helper stays alive, heartbeats, and emits `bundle: null` forever — indistinguishable from "nothing is playing", and for browsers there is no fallback at all. Gate: a canary cross-checking a null MediaRemote against AppleScript's `player state`, which logs the refusal and switches primary. Without this the AppleScript fallback is wishful for the case most likely to happen. ⚠️ **The canary as first written undid Phase 5** — MediaRemote reports null whenever nothing plays, which is most hours, so cross-checking every null brings `osascript` spawns back into the idle state. **Constrained 2026-09-16**: ask AppleScript **only while Spotify or Music is running**, decided from the process table with **no spawn** (`proc_listpids` / `proc_pidpath`); **at most once per 60 s**; and **never address a player that is not running** — an AppleScript `tell` launches it. ⚠️ Observed the same day on 27.0: with nothing playing, the helper emits `{"playing":false,"bundle":null,"type":"now","stale":false}` — byte-for-byte the shape a refusal would take, which is the whole reason this gate exists. ⚠️ **More limits, from the 2026-09-16 review (finding 4):** bound every `osascript` call with a timeout (the bash has none); never let two canaries overlap; make the primary switch **reversible**, and switch back when MediaRemote reports a non-null bundle again; log each process-table decision. **Verify one false positive before trusting the switch: Spotify Connect.** Spotify can report `player state = playing` while the audio plays on another device, and MediaRemote then rightly reports nothing here. That is not a refusal. 🟡 **LOGIC BUILT 2026-09-16, live half owed** (`spikes/s1-mediaremote/src/{players,applescript,canary}.rs`, 13 tests): player detection by exact executable path from `proc_listallpids` + `proc_pidpath` (**2.7 ms, no spawn**, found Music.app live); `osascript` bounded and killed at its timeout, stdout/stderr/status kept apart, `-1743` classified as **Denied**, never idle; the canary asks only with MediaRemote null **and** a player running, once per 60 s, never overlapping; switches after **two** consecutive discrepancies and restores the moment MediaRemote names a bundle. ⚠️ **Not run live on purpose:** the first Apple event from a new process raises an Automation prompt on the owner's desktop, and the revocation test is a System Settings toggle. **Owed, with the owner:** grant, then revoke Automation mid-run and see `Denied` surface; the Spotify Connect false positive; a browser session through the Rust supervisor. |
| **S2** | IOKit HID discovery + transport | Open **exactly one** device; VID/PID/usage read from the IORegistry with **nothing opened** to decide; `ak820 info` on macOS equals `ak820ctl info` byte for byte — the same gate Windows phase 0 had. **Plus the exclusivity reality, in both directions**: (a) a hidapi peer (`ak820health.py`) seizes the device mid-transaction and the daemon recovers rather than wedging or reporting a firmware fault; (b) the daemon holds a non-seizing open and a hidapi peer tries to seize — record who gets `kIOReturnExclusiveAccess`. Opens are **per interaction** (see the exclusivity section). Discovery via `IOServiceGetMatchingServices`, **never `IOHIDManagerOpen`**. Also resolve the report-id/length mismatch (`caps.rs:97-104`). ⚠️ **Log IOKit's kernel timestamp for every input report beside the userspace `t1`.** The clock contract times from userspace around the exchange (`AK820-AGENT-CLOCK-TRANSACTION.md:90-96`), and so must the port, but IOKit delivers reports through a run-loop callback whose latency differs from hidapi's — measuring the gap here is what stops Phase 2's lead learner absorbing it as zero. **S2 is also the evidence for the hand-rolled IOKit decision** in Settled: count the surface and judge the CF ownership code before Phase 0. ⚠️ **From the 2026-09-16 review (finding 7):** IOKit delivers input reports only through a run-loop or dispatch-queue callback, so each per-interaction open is create, open, schedule, wait, unschedule, close and release — about 28,800 times a day at the 3 s cadence. **Design one persistent reader thread**, then run **10,000 open-exchange-close cycles with the Python agents paused**, and require RSS and the Mach port count to stay flat (one missed release per cycle is a leak Phase 5b would only see after days). **Record CPU per cycle; that is 5a's budget. Also record the seize direction** (see 4a). ✅ **MET 2026-09-16** (`ak820-agent/spikes/s2-iokit/`, hand-rolled FFI, no dependencies), on macOS 27.0 with the Mac's board: **`s2 info` is byte-identical to `ak820ctl info`** (`cmp`); discovery reads three services' properties and opens nothing, choosing the `0xFF60/0x61` one; **IOKit's report sizes are 32 in and 32 out, excluding the report id** — the `caps.rs` mismatch is real and the macOS check must compare against 32; `LocationID` is `0x141400`, the value the Python's `ioreg` parse yields. **Soak, Python agents frozen:** 10,000 open-exchange-close cycles, 0 failures, 0 discarded, Mach ports flat, **0.33 ms CPU per cycle** (5a's budget: ~0.01% of a core at the 3 s cadence), round trip p50 4.6 / p99 6.7 ms. **Userspace timestamping adds p50 0.10, p99 0.32 ms** over IOKit's kernel timestamp — well inside the clock's noise, so the userspace `t0/t1` contract ports as is. ⚠️ **The soak found a leak and changed the design:** registering an input-report callback leaks one page (~3.9 KB) per `IOHIDDevice` object, whatever the API variant, unregistration or buffer size — ~110 MB/day at one object per interaction. **One object per board arrival, callbacks registered and scheduled once, `IOHIDDeviceOpen`/`Close` per interaction**: flat over 9,000 cycles. The review's per-interaction-open rule is intact; only the object is long-lived. |
| **S3** | Signing shape | A Rust binary signed with the **Developer ID Application identity (by SHA-1)** + signed dylib, hosted by perl, runs under the hardened runtime; the minimal entitlement set is established empirically (hypothesis: empty). ⚠️ This row said "ad-hoc-signed" until 2026-09-16, contradicting the Install section: ad-hoc signing changes the cdhash on every rebuild, so TCC identity churns and G-B's revoke test is confounded. ✅ **MET 2026-09-16:** `codesign --force --timestamp --options runtime --sign <SHA-1>` on the s1 binary and a dylib built from the sibling's source with its flags (`clang -dynamiclib -fobjc-arc -O2 -framework Foundation`) — no keychain prompt, strict verify passes, hardened runtime, **empty entitlements**; the signed binary hosted the helper and read Music.app. perl loads the dylib **signed or unsigned** (it has no library validation), so signing the dylib is for distribution, not for loading. ⚠️ **Two findings for Phase 6:** (1) **The signing identifier defaults to the file name** (`Identifier=s1-signed`), and TCC keys consent on the designated requirement, which includes it — so the release must sign with an explicit `--identifier` (e.g. `com.jdlien.ak820`), or a rename churns Automation consent. (2) **A quarantined dylib hangs perl silently** — signed-but-not-notarized and unsigned alike: no `hello`, no stderr, nothing until killed. **It is blocked behind a Gatekeeper dialog on the owner's desktop** — confirmed by the owner's screenshot the same afternoon: *“quarantined-signed.dylib” Not Opened — Apple could not verify … is free of malware*, with **Move to Trash** / **Done**. A daemon would raise that dialog at every helper restart. Under the supervisor that reads as a helper that never proves life: failed at 60 s, killed, restarted, forever. So Phase 6's copy-out test must show a **notarized** dylib loading **with** the quarantine attribute, and `ak820 install` should strip `com.apple.quarantine` from what it copies and say so. |
| **0** | Platform seam, no behaviour change | ⚠️ **"Identical" was unfalsifiable as first written**: a test *count* legitimately changes when `host.rs` tests move, and `hid::Error::Open` wraps a `windows::core::Error` (`hid/mod.rs:63-76`) that must become neutral, so log text necessarily changes. **Observable is therefore defined as wire bytes, status-file keys, log grammar and timing statistics** — not strings, not counts. The real gate is the one Windows phase 0 used and this one omitted: **reinstall from the phase-0 build and reproduce the takeover table** (`AK820-AGENT-PLAN.md:265-275`) against the pre-refactor log over the same duration, plus the five CLI commands (`:46-48`). **Where it runs — settled 2026-09-16:** (1) **the Mac is the dev host**: `cargo check --target x86_64-pc-windows-msvc --all-targets` passes here in 11 s with the target already installed **[measured]** — every Phase 0 commit passes it before push; (2) **Windows `cargo test` stays on CI** (`agent.yml`, `windows-latest`), and a `macos-latest` job is added once the crate builds natively; (3) **the live gate runs on `gremlin.local`**, the Windows machine, against **its own AK820** — a second board, on **`8608c4f6-dirty`**, not the pinned `b89777e0f9` (flashed 2026-09-05 11:21, never moved since; reported by the gremlin session from its artifacts, flash.sh backup and presence log — confirmable by eye, since `b89777` draws a missing battery on the panel). That is fine for a before/after comparison on the same board, with one rule: ⚠️ **do not reflash gremlin's board between the baseline and the phase-0 run**, or the comparison measures firmware. **The baseline is better than the takeover table, and the gate uses it**: the live daemon ran unbroken **2026-09-09 12:49 → 09-15 03:18, 1,614 periodic syncs**, zero warnings, sync failures, board transitions or foreign reports; `|before|` median 5.1, p95 15.2, worst 27.6 ms; bias +17..+70 ppm **[gremlin session's log analysis, 2026-09-16]**. Its binary is `d8ead97`, and `d8ead97..bd20271` touches only `bin/ak820.rs` install wording and `Cargo.toml`, so it *is* today's daemon code. **The gate — revised after the 2026-09-16 review (finding 1), because the first version could not fail.** The comparator `scripts/clock_log_windows.py` (written on gremlin 2026-09-16, stdlib only, committed in `8cf2c8d`) reproduces both columns of the published 3b table exactly, so it is calibrated against the record rather than trusted. Baseline spread across the 32 windows (min / median / max): `|before|` median 3.3 / 5.2 / 6.5 ms, p95 10.3 / 14.4 / 23.9 ms, worst 12.9 / 18.1 / 27.6 ms; bias spread 23 / 34.5 / 49 ppm; zero failed, unmeasured or `[warn]` syncs in every window. **The rule:** run **3 consecutive 50-sync windows** (about 12 h 15 min — overnight). The **deciding statistics** are `|before|` p95 and worst, plus the invariants. **Fail** if any window has a failed, unmeasured or `[warn]` sync, or if **2 or more of the 3** exceed the baseline max on p95 or on worst. **Pass** if none exceeds and bias spread stays at or under 49 ppm. If exactly one exceeds, **extend once** by 3 more windows: then fail if 2 or more of the 6 exceed, otherwise pass. ⚠️ **Why the first version could not fail:** "one window outside `[min, max]` extends the run" named no stopping rule and no failure. Its 6% figure (2/33) held for one statistic on independent windows, but it checked several statistics at once on adjacent 4 h slices of one slowly drifting learner, which are correlated — roughly 15–25% per window. A real p95 regression would have read "extend, extend, extend". ⚠️ **Before Phase 0, the comparator gains a slip column** — `|before|` within 1000 ± 60 ms with a small `after` — so slips are counted mechanically and excluded from p95 and worst, not eyeballed. ⚠️ **Three conditions make that comparison honest:** (a) **match the media state** — that run's media state was `none` throughout, though ⚠️ **not traffic-free**: the daemon still sends a playback request every 3 s and a text keepalive every 30 s and logs neither (`agent.rs:271-300`, `media.rs:63-72`). The 09-06 takeover table had real titles. Run the idle comparison against this baseline, and a playing-media window separately against the takeover table; (b) **pause Windows Update for the run** — both of the last two runs ended in an update restart, and the daemon is a logon task, so the clock went unsynced 9 h and 34 h until the owner logged on; (c) **a whole-second slip is not the refactor's by default** — four with an identical signature are on record, across both boards, both OSes, and both the Python and Rust hosts, including the pre-refactor daemon's `before -1006.4 ms` on 09-08 19:58:51 with no warning line (see `BACKLOG.md`); (d) **the same learner and physical state** (review finding 8): the same cache file, so no `seed` line appears in the run's log (`agent.rs:588-611` seeds only while the cache lacks a bias); the same RGB effect and brightness; the slider on cable. `ak820-timekeeper.py:53-63` records drift moving with LED load and room temperature. ⚠️ **The first commit of Phase 0 is forced**: a native macOS `cargo check` fails immediately in `windows-future` because `windows` is an unconditional dependency (`Cargo.toml:33`); it moves under `[target.'cfg(windows)'.dependencies]`. `agent.rs` is the file most at risk. ⚠️ **The runner on gremlin belongs to `jdlien/photoblaze`**, repo-scoped (service `actions.runner.jdlien-photoblaze.GREMLIN-win`), so `ak820-pro` has none; `jdlien` is a user account, so sharing it would mean a second registration. **Not needed**: GitHub-hosted `windows-latest` runs `cargo test` without a board, and a self-hosted job would run beside the live board, able to open HID against the daemon — `ak820 clock` there would break single ownership. gremlin has **no OpenSSH server**; the cross-session bridge (Remote Control on both ends) is the channel. 🟡 **BUILT 2026-09-16 (`a46e770`), live gate owed on gremlin.** The seam is in: `hid::HidTransport` over `Wire`, `platform::Platform`, `media::MediaSource`, `clock::host::Host`, the Windows code moved under `platform/windows/` with caps, instance, process and task moved verbatim. Windows CI green (`cargo test --locked` and the release build); the Windows all-targets check clean from the Mac; the neutral tests run natively on macOS. **Fable audit, same day** ([`review-fable-phase0-2026-09-16.md`](review-fable-phase0-2026-09-16.md)): **safe to deploy**, seven findings, none blocking the Rust side. Two were in the comparator and are fixed: **`--gate` refuses without `--since`**, because the baseline shares the log file and the gate would otherwise grade it; and **slips now have a rule**, **2 or more across the graded windows FAIL and exactly 1 turns PASS into REVIEW**, because the baseline had none in 1,614 syncs. CI's own artifact confirms `ak820-agent.exe` is still `WINDOWS_GUI` after the `cfg_attr` move. **The live run:** build and install from this commit on gremlin, no reflash, Windows Update paused, media state `none`, then `python scripts/clock_log_windows.py <log> --since "<reinstall time>" --gate 23.9 27.6 49`. |
| **1** | macOS HID transport | S2's gate, now through the real trait, plus wrong-interface rejection, malformed-report rejection, timeout, unplug mid-transaction, and **traced opens showing nothing unrelated was touched** (see [G-A](#g-a--open-nothing-you-did-not-mean-to)). 🟡 **BUILT 2026-09-16, the unplug and the trace owed.** `platform/macos/{sys,cf,runloop,discovery,device,cli}.rs`, from S2's design (one `IOHIDDevice` object per board arrival, `IOHIDDeviceOpen`/`Close` per interaction, one persistent run-loop thread), implementing `Wire` and `HidTransport`, so the shared exchange (correlation, drain budget, resynchronization) is the one Windows runs. **On the Mac's board:** `ak820 info` **byte-identical to `ak820ctl info`**, `ak820 health` matches `ak820health.py`, `ak820 selftest` passes (budget guard, idle drain, recovery). The report sizes are checked against 32/32 with the id excluded. A seize by a hidapi peer maps `kIOReturnExclusiveAccess` to `Error::Open`, which reads as busy, never as a firmware fault; a vanished device maps to `Absent`, and no callback within the budget to `Stuck`. **Owed on hardware:** unplug mid-transaction; the trace of opens. |
| **2** | macOS clock, read then set | Captured replies decode identically to the pinned C **on macOS**; then the scheduler and SOF-bias learner replayed against `ak820-timekeeper.py`'s own macOS log, matching decisions **and next state**, the way phase 3a did on Windows — the macOS timekeeper log exists (241 KB, same format), so that half is achievable. ⚠️ **Fixture parity CANNOT see a self-consistent wrong time**, which is the exact failure this phase exists to prevent: both the GET's residual and the SET's payload go through `host.local()` (`transaction.rs:174`, `:205-208`), so a macOS `local()` off by an hour yields a **zero residual and a board an hour wrong**. Captured-reply decoding never exercises localtime at all — the oracle takes `host_mid_sod` as an argument (`scripts/clock_oracle.c:14`). Windows covered this with hourly sweeps across 2026–2099 against the oracle CRT (`host.rs:294-347`), which cannot compile here. **So this phase also requires**: an hourly-sweep test against libc `localtime_r` (what `ak820ctl.c:159`, `:198`, `:256` call), a TZ-change test, **independent** reads via the pinned `ak820ctl clock --read` with the daemon paused, and a human reading the LCD against a reference clock. "No worse than Python" compares *self-reported* residuals and would absorb a transport timestamping bias into the lead learner as zero. ⚠️ **Parity would also carry a whole-second slip faithfully** (added 2026-09-16): four identical ~1 s slips are on record across both boards, both OSes and both host implementations (`BACKLOG.md`), and firmware or the shared transaction contract are the remaining suspects. If it is the contract, the port reproduces it by design. So this phase **counts slips separately** — never folded into p95 or worst, never read as the port's regression or as the port's fix. ⚠️ **Also this phase (review finding 10):** `ak820 clock`'s refusal while the Python timekeeper runs needs a macOS check — `launchctl print gui/$UID/<timekeeper label>` in place of the Task Scheduler query. **This is the phase that earns the project.** |
| **3** | macOS media | Router works: **MediaRemote for everything including Music** (post-`fc70de4`), with AppleScript as the fallback for a stale provider or unhealthy helper — not as Music's route. Bounded calls, supervised helper, 5 s stickiness so a paused app does not steal the band. **Plus [G-B](#g-b--a-tcc-revocation-must-be-visible) and the S1b canary.** ⚠️ **The old "byte-identical to what `nowplaying-macos.sh` would have pushed" gate could not fail honestly**: folding parity is already proven at generation time across every scalar, and the genuinely new variable is the *source* — MediaRemote's title/artist and AppleScript's fields can legitimately differ for the same track. Split into (a) folding parity on **identical input**, an existing test, and (b) a **documented source comparison** where each difference is explained rather than counted as a defect. 🟡 **BUILT 2026-09-16, the live half owed.** `platform/macos/media/`: S1's supervisor and JSON reader, S1b's canary and bounded `osascript`, and three new pieces. **`route.rs`** holds stickiness and the snapshot rules. **`applescript.rs`** now does the fallback read: one bounded script per poll over the running players only. **`mod.rs`** holds the engine and `MediaRemoteSource`. The engine's I/O sits behind a `World` trait, so every route is a unit test that sends no Apple event: 63 macOS-module tests, 315 in the crate. `Native` implements `Platform` (`MEDIA_API` "MediaRemote"), and `ak820-agent` runs `agent::run::<Native>`. It refuses `--clock` (the Python timekeeper owns the clock until 4b) and holds `$TMPDIR/ak820pro-nowplaying.lock` with its own pid, so it **refused to start beside the running bash agent, verified live**. **Live, no keyboard traffic:** `ak820 probe` read a Chrome/YouTube session through the real helper, paused and then playing. **Decisions made building it:** (1) ⚠️ **a switch held by stickiness is deferred, not dropped**: MediaRemote never repeats a `now`, so the sibling's drop would leave a quit player "playing" on the panel forever. The held message lands at the first poll after the hold. (2) Stickiness judges playing by rate first on both sides; the sibling counted the incoming flag alone. (3) **Position extrapolates by `rate`**: the owner's video reported `rate 1.25`, and the readout matched it. Windows ignores rate. (4) The snapshot is computed in `latest()`, when the daemon asks, not when a `now` arrived. (5) The fallback ranks playing above paused across players, as SMTC does; the bash took the first player that was either. (6) Once switched to AppleScript, the canary stops asking, since only a bundle switches back. (7) A denial fails polls until an AppleScript read succeeds or MediaRemote names an app, and is logged once, not per poll. (8) ⚠️ **The dylib path must be absolute.** `/usr/bin/perl` runs under the hardened runtime, whose dyld refuses a relative path; the helper printed `load failed`, exited 2 and restarted forever (found with `ak820 probe --dylib ../..`). The source canonicalizes it. (9) The log goes to `~/Library/Logs/ak820pro/ak820-agent.log`, the status file to `~/Library/Application Support/ak820pro/`. (10) `Platform::spawn_media` takes the daemon's log, so the helper's restarts are logged; Windows ignores it. **Owed on hardware and with the owner:** a live daemon run (pause the bash agent first); S1b's Automation grant and revoke; Spotify Connect; the documented source comparison against `nowplaying-macos.sh`. |
| **4a** | `install` / `uninstall` / `status` on macOS, **now-playing only** | Mirrors Windows 4a: `ak820 install` (no `--clock`) registers a LaunchAgent that owns now-playing, unloads the `nowplaying-macos.sh` LaunchAgent, and **leaves the Python timekeeper running and owning the clock**. The daemon in this mode runs **no clock transaction of any kind**. Survives logout/login and sleep/wake. ⚠️ **Coexistence is the gate on macOS, not an assumption**: the timekeeper's `ak820ctl` still opens the device every sync, so the two contend exactly as today's two Python agents do. Across ≥ 50 periodic syncs, the timekeeper's own log must show **no more `[rc=N]` failures or unmeasured syncs** than its pre-4a log over the same duration, with its residuals inside that baseline's spread. `scripts/clock_log_windows.py` already parses this log format. Rollback to `nowplaying-macos.sh` proven, not described. ⚠️ **From the 2026-09-16 review (findings 2 and 5):** (i) **The cadence is not today's.** The neutral loop sends a playback readout **every 3 s in every media state** (`media.rs:63-72`, `agent.rs:385`), plus a health open every 300 s. The bash pushes playback only while playing and keepalives every 30 s. So **idle opens rise about tenfold**, and "contend exactly as today's two Python agents do" was wrong. The default keeps the neutral cadence, with no platform divergence, and **states the expected collision rate from S2's measurements**. If the gate fails on collisions, the fix is to send the idle readout only on change plus keepalive — on **both** platforms, which is a Windows behaviour change and needs its own decision. (ii) **Gate the side that loses.** S2 records the seize direction. If a seize evicts the daemon, the timekeeper never logs a failure and its log proves nothing; so also count the **daemon's** push and playback warnings and its `board:` transitions per 50 syncs, and **match the media state** of the baseline, as Phase 0 does. The timekeeper retries a failed sync after 15 s, not a full interval (`ak820-timekeeper.py:273-296`), so a collision costs one `[rc=1]` line, not accuracy. (iii) **The fence has to exist on macOS.** `install-agents.sh` always acts on **both** agents (`:22`, `:50-57`, `:81-93`), and a `bootout` alone leaves the plist, so the bash comes back at the next login (RunAtLoad, KeepAlive) beside the daemon. 4a's install therefore runs `bootout` **plus `launchctl disable`** on the nowplaying label, and the daemon **holds `$TMPDIR/ak820pro-nowplaying.lock` with its own pid**, as the Windows daemon holds the Python's mutex name (`instance.rs:7-12`), so a stray bash exits. Rollback is `enable` plus `bootstrap` of that label alone. Give `install-agents.sh` an `--only` flag for it, because a both-agents reinstall restarts the timekeeper and starts a new run in the very log the gate reads. 🟡 **BUILT 2026-09-16, nothing installed: the install itself is the owner's test.** `platform/macos/{launchd,install}.rs`. `ak820 install [--in-place] [--dylib PATH]` stages the copies (`ak820-agent`, `ak820` and the helper dylib) to `~/Library/Application Support/ak820pro/bin/` as `.new`, strips `com.apple.quarantine`, renders the plist, and **lints it with `plutil` before touching any agent**. It warns when the daemon lacks a Developer ID signature, since TCC consent would churn per rebuild. Then it boots out any previous daemon, `bootout`s **and `disable`s** `com.jdlien.ak820pro.nowplaying`, waits for the shared lock to be released, leaves the timekeeper alone and says so, bootstraps `com.jdlien.ak820pro.agent` (RunAtLoad, KeepAlive, 30 s throttle), and waits for the daemon's status file. Any failure after something stopped **puts an agent back**: the previous daemon, else the bash. `--clock` is refused. **`ak820 uninstall` is the rollback, and performs it**: it removes the daemon's agent, then `enable`s and `bootstrap`s the bash (`--keep-bash-off` skips that). `ak820 status` shows all three labels, including "disabled at login", plus the lock holder, the status file and the log tail; run read-only against this Mac's live launchd, it read the timekeeper and bash as expected. `install-agents.sh` gained **`--only timekeeper|nowplaying`**, **refuses to install nowplaying while the daemon's agent is loaded**, and `enable`s before `bootstrap` so its reinstall works after a `disable`. The plist's `launchctl print` and `print-disabled` parsers are tested against output captured from macOS 27.0. |
| **5a** | Efficiency, media | Right after 4a, `scripts/agent_overhead_macos.py` against the daemon, **with Music playing, the same way the "before" was taken**. ⚠️ **The helper's CPU is counted automatically** as `live_cpu_s`: the kernel's child accounting counts only *reaped* descendants, and the helper lives as long as the daemon, so without it the "after" silently omits the media source's own CPU and flatters the port. The script finds long-lived children afresh at each window edge, so a helper restart mid-window is counted and logged in `live_restarts` instead of aborting the run (a fixed-pid version did; review finding 6). Count the helper from the **run** windows only: SIGSTOP freezes the daemon, not the helper. ⚠️ **Re-take the "before" on a quiet day just before 4a retires the bash.** The first "before" ran during post-upgrade Spotlight indexing, which also kept `trustd` busy, so its knock-on daemon figures would not compare fairly with a quiet "after". Publish **per-daemon run-minus-pause deltas** from the jsonl for both. The CPU row's target is the gate. The spawn row is measured in each of its three states plus the failure mode. |
| **4b** | `install --clock` on macOS | After Phase 2. The daemon takes the clock and the Python timekeeper is retired. **Refuses to run beside it** the way the Windows installer refuses (one clock owner, enforced not intended), stop-confirm-start in both directions per the Windows phase-3a/4a audit's finding 1. Rollback to the Python timekeeper proven, not merely described. |
| **5b** | Efficiency, whole | The table above, measured, with the memory caveat stated honestly rather than met by redefinition. |
| **6** | Signed release | **Clean-Mac install from Releases with no toolchain, no Python, no Homebrew.** Gatekeeper reports `source=Notarized Developer ID`. The `.dmg` is stapled and passes `spctl` **offline**; `ak820 install` copies out of the mounted image, and the LaunchAgent-started daemon's perl child loads the **copied** dylib with the network off — the quarantine path above, proven rather than assumed. This is the macOS phase-6b and deserves the same suspicion — v0.1.0 shipped a wrong `INSTALL.txt` and cost a release. ⚠️ **Name the test bed**: Windows had Sandbox, but a fresh macOS *user account* does not reset Gatekeeper's per-file assessment or the binary's TCC state — only a VM is a real clean machine. Unnamed, this gate is an intention. |

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
mid-run and assert the denial surfaces in `ak820 status` and the log **within
60 s of the next Apple event, with the test forcing one**. A structural claim
("we capture stderr now") does not pass. ⚠️ **Restated 2026-09-16 (review
finding 4):** this said "within one poll interval", which S1b's own limits
made impossible. With MediaRemote healthy the daemon sends **no** Apple events
at all, so a revocation is invisible until something asks. That is by design
and cheap, but the gate has to force the question or it cannot be run.

---

## Risks

| Risk | Severity | Response |
|---|---|---|
| Apple revokes the platform-binary allowance | **High** — removes the capability gain | ⚠️ The fallback only covers helper *death*. The likely shape is a live helper emitting `bundle: null` forever, which reads as idle — gate **S1b** exists for exactly this |
| **macOS raw HID is exclusive** and every kept diagnostic seizes it | **High** — presents as a firmware fault, and has twice | Phase 1 seize gate; Phase 4 refusal is arbitration, not politeness; `Presence::Busy` treated as normal |
| **perl is a deprecated macOS runtime** (since 10.15) | Medium — a *separate* risk from the MediaRemote allowance, and not previously listed | If perl is removed, the host must move to another Apple platform binary; keep the host choice behind one seam in the helper supervisor |
| S1 fails outright | High | Plan still stands on the clock; restate the value honestly rather than proceeding as if unchanged |
| Regressing the live Windows daemon | **High** — it has been in daily use since 2026-09-06 | Phase 0 gate is "no Windows-observable change"; audit before merging the seam |
| Clock parity passes on fixtures but drifts live | High — the failure is a plausible wrong time | Phase 2 replays the *macOS* log, not the Windows one, and — because self-reported residuals cannot see a self-consistent wrong time — adds the libc `localtime_r` sweep, a TZ-change test, independent `ak820ctl clock --read` with the daemon paused, and a human reading the LCD |
| Two MediaRemote helpers on one machine | Low, but wasteful and slightly absurd | [Open question 2](#open-questions--needs-jds-decision) — settled as two helpers, shared code |
| macOS version drift breaks IOKit/MediaRemote | Medium — **and it already happened once mid-plan**: this Mac moved from 26.5.2 to **27.0 (26A428) at 12:27 on 2026-09-16**, six days after the plan was written | **Tested OS pinned at 27.0 (26A428).** MediaRemote-via-perl re-verified on it the same day; IOKit is first measured on it in S2. Re-verify every major release, and **before** trusting a measurement older than the running OS |
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

   **Sequencing, settled 2026-09-16: this gates Phase 3, not the spikes.** As of
   that date the sibling's protocol still has **no version field** (its last
   commit touching the helper is `fc70de4`). S1–S3 consume the sibling's
   **built dylib unchanged**, so nothing is blocked. The sharing *mechanism* —
   submodule, subtree, or a vendored copy with a recorded source commit and a
   drift check — is chosen at the start of Phase 3, together with the sibling
   change that adds the version field.

3. **`.pkg`/`.dmg` or bare binary?** ✅ **Settled 2026-09-16: `.dmg`.** This
   entry recommended `.pkg` even after the review moved the recommendation to
   `.dmg` — the two contradicted each other until finalization. The Installer
   certificate exists, so it was a choice, not a constraint; reasons in
   [Install](#install-signing-and-distribution).

4. **Intel slice?** ✅ **Settled 2026-09-16: Apple Silicon only**, stated in
   `INSTALL.txt`. A universal build is cheap to *produce* but nothing here can
   *test* it, and an untested slice is a promise.

5. **Does this ship publicly?** ✅ **Settled 2026-09-16: yes, like Windows** — a
   `.dmg` on the same GitHub Release, personal-first in support terms. Phase 6
   therefore keeps its clean-machine VM gate at full size.

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

## Finalization — 2026-09-16

Six days after the review, the plan was re-read end to end against the repo
and this Mac as they stood that day, before any spike. Everything below is
also folded in at the site it affects; this section is the index.

**Measured that day:**

| | result |
|---|---|
| **OS** | This Mac moved to **macOS 27.0 (26A428) at 12:27**, hours before finalization. Every macOS fact above that was measured earlier was measured on 26.5.2. `/usr/bin/perl` is still present (5.34.1). |
| **MediaRemote-via-perl on 27.0** | ✅ **Still answers.** The sibling's dylib returned a YouTube session from Chrome with title, artist, duration, `rate` and `playing: true`; the owner confirmed the Stream Deck plugin showing it live. With nothing playing it returned `bundle: null`, the refusal-shaped output S1b guards against. |
| **Helper protocol drift** | The live `now` message carries `elapsedAt` and `playing`, which the `.m` header does not document. No protocol version field yet. |
| **Windows from the Mac** | `cargo check --target x86_64-pc-windows-msvc --all-targets` passes in 11 s. A native macOS check fails in `windows-future`: the `windows` dependency is unconditional. |
| **Certificates** | Developer ID **Installer** exists. The Application identity is listed twice with one SHA-1. |
| **Boards** | One is attached to this Mac, on the pinned `b89777e0f9`. gremlin.local has a second, on **`8608c4f6-dirty`**, with a clean 1,614-sync pre-refactor baseline in its daemon log (09-09 → 09-15, no media). gremlin's only Actions runner is registered to `jdlien/photoblaze`; it has no SSH server. Facts about gremlin come from a Claude session running there, reached over Remote Control, which read files and logs and sent no board traffic. |

**Decided that day** (owner: shipping, board logistics, IOKit; the rest are
defaults recorded without objection):

1. **Ship publicly** as a stapled `.dmg`, Apple Silicon only.
2. **Phase 0's live gate runs on gremlin** against its own board, without
   reflashing it between baseline and phase-0 runs; judged against the spread
   of the 1,614-sync baseline's 50-sync windows, with the media condition
   matched and Windows Update paused. A self-hosted runner for this repo is not
   needed (owner's call if wanted; it would sit beside the live board).
3. **IOKit hand-rolled**, confirmed at the end of S2.
4. **JSON hand-rolled** for flat objects, tested against a Python-`json` corpus
   built from captured helper output.
5. **Media failure policy:** one neutral rule (a failed source publishes idle);
   each backend defines "failed" — on macOS, **60 s with no line read**, which
   death and `fatal` start rather than trip (revised by the second review's
   finding 3; first written as "dead, `fatal`, or silent two heartbeats").
   Stickiness stays in the macOS backend.
6. **Per-interaction opens on macOS**, as on Windows; S2 measures seize
   behaviour in both directions.
7. **The S1b canary is bounded** by player-running checks with no spawn and a
   60 s rate limit; Phase 5's spawn target is stated per state.
8. **Helper sharing gates Phase 3, not the spikes.**

**Contradictions in this document, fixed:** "four traits" over a five-row
table; Open question 3 still recommending `.pkg` after the review moved to
`.dmg` (repeated in `current-status.md`); a risk row pointing at "open question
3" for the helpers, now question 2; S3 saying "ad-hoc-signed" while Install
requires a stable identity; the header and Why list still claiming two macOS
defects; "8 `osascript` per poll" against the backlog's verified "up to 7"; and
the Windows failed-read policy attributed to the phase-0 audit rather than the
phase-3a/4a audit, as `agent.rs:274-277` has it.

9. **Now-playing first, the clock soon after** (owner, after the overhead
   measurement): S1 → S2 → S1b, S3 → 0 → 1 → 3 → 4a → 5a → 2 → 4b → 5b → 6.
   Public release stays last.

**Nothing now gates S1.** Build order is in
[Phases](#phases-with-gates-that-can-actually-fail).

## Review disposition — Fable, 2026-09-16

Full report: [`review-fable-crossplatform-2026-09-16.md`](review-fable-crossplatform-2026-09-16.md).
Scope: only what changed on 2026-09-16. Ten findings, one High. Findings 2, 3
and 6 were re-verified at source before acting on them: `media.rs:63-72` and
`agent.rs:385` send a playback readout every cycle; the timekeeper retries a
failed sync after 15 s; `nowplaying-mediaremote.m:125-138` exits after six
timeouts, and `MediaRemoteHost.cs:67-76` restarts in 2 s with a 60 s silence
limit. **Every finding accepted; none waved off.**

| # | Sev | Finding | Disposition | Due |
|---|---|---|---|---|
| 1 | High | Phase 0's window gate could not fail: no stopping rule, and 6% held for one statistic, not several correlated ones | **Accepted, gate rewritten**: 3 overnight windows, p95 and worst decide, 2-of-3 fails, one extension to 6, invariants must be 0; slip column added to the comparator | before Phase 0 |
| 2 | Med | 4a's baseline is at a different HID cadence (playback every 3 s in every state, tenfold idle opens), and gates only one side of an unmeasured seize direction | **Accepted**: cadence and collision rate stated; the daemon's side gated too; media state matched. Idle readout kept neutral; changing it is a both-platform decision | before 4a |
| 3 | Med | "Dead or fatal fails at once" blanks the LCD on the helper's designed recovery path | **Accepted, design changed**: failed = 60 s with no line read; death and `fatal` start the clock; silence judged only with the pipe drained | **before S1** — done |
| 4 | Med | S1b's limits contradict G-B's "within one poll interval"; G-B untestable while MediaRemote is healthy; Spotify Connect false positive | **Accepted**: G-B restated as "within 60 s of the next Apple event, forced by the test"; S1b bounds each call, prevents overlap, and makes the switch reversible; Spotify Connect to verify | before S1b |
| 5 | Med | No rollback fence on macOS: the installer acts on both agents, `bootout` leaves the plist, the lock is not held | **Accepted**: `bootout` + `disable`, the daemon holds the mkdir lock, `install-agents.sh --only` | before 4a |
| 6 | Med | `--live` took a fixed pid, so a helper restart aborted the measurement; a 240 s SIGSTOP would trip the silence rule at resume; the "before" day's knock-on figures were not like-for-like | **Accepted**: the script discovers long-lived children per window and logs restarts (done); the S1 silence rule drains first (done, finding 3); re-take the "before" on a quiet day before 4a | script done; re-take before 4a |
| 7 | Low | The IOKit per-interaction read path is undesigned and its cost and leak behaviour ungated before 5a | **Accepted**: one persistent reader thread; 10,000-cycle soak with RSS and Mach ports flat; CPU per cycle becomes 5a's budget | in S2 |
| 8 | Low | Phase 0's matched conditions omit the learner cache and the board's thermal state | **Accepted**: same cache (no seed line), same RGB effect and brightness, slider on cable | before Phase 0 |
| 9 | Low | "Up to 7 osascript" is wrong; the maximum is 8 | **Accepted**: 6 / 7 / 8 by case | done |
| 10 | Low | `ak820 clock` refusal and the single-instance guard have no macOS phase; the PID wrap is 99999 | **Accepted**: refusal in Phase 2; the guard is 4a's lock; wrap fixed | done / Phase 2 |

**What the review confirmed as sound**, and is therefore not restated: media-only mode sends no clock transaction (`agent.rs:241-252`, `:302-311`); the comparator parses the Python timekeeper's log; the gremlin binary is today's daemon code; nine Windows-referencing files and no `cfg`; the `elapsedAt` drift; per-interaction opens as the existing Windows design; SIGSTOP as a fair pause; the 19.7% child-CPU figure as exact; one neutral failure policy with backend-defined failure as the right shape; `IOServiceGetMatchingServices`; process-table player detection by exact executable path.

## Phase audits

Every phase ends with an external audit. Each report and its dispositions
live in their own file; this is the index.

| phase | commit | auditor | verdict | record |
|---|---|---|---|---|
| **0** | `a46e770` | Fable 5.1, 2026-09-16 | **Safe to deploy.** 7 findings: 2 Medium in the gate comparator, fixed; 5 Low, 4 fixed and 1 deferred to Phase 2 | [`review-fable-phase0-2026-09-16.md`](review-fable-phase0-2026-09-16.md) |

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
