# ak820-agent — one Windows daemon for the clock and the LCD text — plan

Status: **PHASE 0 IN PROGRESS, 2026-09-05.** Planned and revised the same day
against [review-codex-ak820d-2026-09-05.md](review-codex-ak820d-2026-09-05.md)
(gpt-6-astra, xhigh), then started.

Built so far, crate at `ak820-agent/`, 46 tests passing:

- `hid::path` — bounded path matching, so discovery narrows to this board
  before opening anything. Test corpus includes the real measured path, the
  board's other collections, its bootloader PID, and the sibling projects' UPS
  and Aura paths as devices that must never match. Also `multi_sz` splitting
  and the two-identical-keyboards check, both decided from strings.
- `proto` — framing, report-id normalization, and `classify`: the whole
  read-side decision as one pure function, which the broadcast finding below
  made mandatory.
- `hid::caps` — the post-open identity check, against the board's five real
  collections.
- `hid::device` — the `CreateFileW` transport: Configuration Manager discovery,
  overlapped I/O, `CancelIoEx` discipline, pre-drain, and the correlate-or-drain
  request loop.
- `flash` — `FC_INFO` only, and deliberately nothing else; provisioning stays
  in `ak820ctl`.

**The phase-0 gate is met** — see [Phase 0 evidence](#phase-0-evidence-2026-09-05).
Next: phase 1 (`text.rs`, `smtc.rs`, `--probe`).

A single Rust binary replacing the two Python host agents **on Windows only**.
macOS keeps its LaunchAgents and its Python, unchanged.

Companion documents, both of which are part of this plan:

- **[AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md)** — the Python scheduler
  and SOF-bias learner.
- **[AK820-AGENT-CLOCK-TRANSACTION.md](AK820-AGENT-CLOCK-TRANSACTION.md)** — `ak820ctl`'s
  clock transaction, where the precision actually lives. **The oracle is Python
  plus the pinned C utility.**

## Why

In order of how much they matter:

1. **One owner for a single-owner interface.** Two processes contend for it
   today, plus `ak820health.py`, plus VIA. That contention has twice been
   mistaken for a firmware fault.
2. **Installation.** Running the agents on Windows today needs MSYS2, two
   venvs, native-python discovery, a `winsdk` wheel, `hidapi.dll` plus a `.pth`
   shim, and a venv whose *name* must contain `mingw64`. Nearly all of it exists
   only to run Python. An owner who takes prebuilt firmware from Releases
   currently **cannot run the agents at all**.
3. **Footprint.** Measured 2026-09-05: **32.7 MB across 4 processes**, 3.1
   CPU-seconds in 25 minutes. A probe binary that actually reads SMTC, built
   with the siblings' size profile, is **117 KB** -- so the target is one
   process well under 1 MB, not the ~4 MB first estimated.

**Not a reason: speed.** These agents are idle. The only runtime win is that
in-process work replaces an `ak820ctl` spawn per sync.

## Scope

**Replaces, on Windows:** `ak820-timekeeper.py`, `nowplaying-windows.py`, and
the per-transaction `ak820ctl` spawn.

**Does not replace:** `ak820ctl`'s flash provisioning (erases first, rare,
interactive — never in an unattended daemon); the diagnostics; the macOS agents.

## Settled

- Windows only. The crate lives in this repo at `ak820-agent/`, because the wire
  protocol is firmware-versioned. Python remains the clock oracle. No tray, no
  icon.

## Methodology: test-first where it pays

Most of this program is pure functions over bytes and timestamps, which is
exactly what deterministic tests are good at. The review's rebuttal of "nothing
in a unit test would catch it" is accepted: **the gate regressions this project
fears most are excellent tests.**

Written test-first, with fixtures before implementation:

- **the whole clock contract** — `board_sod` including the shortened-period
  case, `wrap_day`, min-RTT selection, `U`, SET packet bytes, the lead learner's
  gates and clamps, `0xFE` retry, cache round-trip, and the reported line
  (Python parses it, so it is an interface)
- **the SOF-bias learner** — every gate, every boundary, banker's rounding, the
  one-decimal `before`, and the seed's epoch/controller resets
- **wire framing** — report length/ID normalization, header validation, and
  rejecting a *text echo* as a clock reply
- **SMTC snapshot → display** — session ranking, missing metadata, absent
  timeline, Unicode folding, line budgets
- **discovery matching** — accept/reject on a corpus of real and adversarial
  device paths

Integration-tested behind a trait, not test-first: the HID executor, the SMTC
worker, the scheduler. Hardware behaviour is not unit-testable and is gated by
phases 3b/4 instead.

Rust specifics: `#[cfg(test)]` unit tests beside the code; fixtures as byte
arrays in `tests/fixtures/`; the clock replay corpus as a table-driven
integration test; `HidTransport` and `Clock` as traits so the scheduler runs
against fakes with no device and no real time. **A finding about the hardware
gets pinned in a test**, per `../jdups/CLAUDE.md`.

## Architecture

```
ak820-agent/
  Cargo.toml
  src/
    lib.rs
    hid/          discovery (open nothing), transport, serialized executor
    proto.rs      channels, packet builders, reply validation
    clock/        transaction (C contract) + scheduler/learner (Python contract)
    text.rs       line/icon/playback packets, ASCII folding
    smtc.rs       media session worker
    health.rs     counters
    bin/
      ak820-agent.rs   daemon -- windows subsystem
      ak820.rs         CLI    -- console subsystem
```

Two binaries because a PE has one subsystem. `ak820-agent.exe` has **no console
ever**, which makes the console-flash bug impossible by construction rather than
dependent on remembering `CREATE_NO_WINDOW`. `ak820.exe` is a console app so
exit codes and stdout survive.

### Ownership is enforced, not intended

A **single serialized HID executor** inside the daemon, plus a **process
instance mutex**. The plan must answer, and the implementation must handle:

| Case | Behaviour |
|---|---|
| second daemon instance | refused by the named mutex |
| `ak820.exe` while `ak820-agent.exe` runs | routed through the daemon, or refused with a clear message |
| retained C/Python diagnostics | documented as requiring the daemon paused |
| VIA opening before / during / after a transaction | transaction fails cleanly and retries; no wedged state |

⚠️ **Even a one-shot CLI clock SET invalidates the daemon's learner baseline**
if the daemon does not know it happened. That is the reason the CLI cannot just
open the device independently.

**A transaction is the complete logical operation** — the clock
measure/SET/verify sequence, or a text update batch — not one report. Open
before taking transmission-sensitive timestamps and close promptly after.

### Measured 2026-09-05: the interface is NOT exclusive, and replies broadcast

The review was right that "holding it open means VIA can never connect" was
inferred, not established. Tested on this machine, and the result is more
interesting than either answer:

| Experiment | Result |
|---|---|
| Second process opens the same path while another holds it | **succeeds** |
| Second process writes concurrently | **succeeds** |
| Process that wrote **nothing** reads while another process writes | **receives the other process's reply** |

The third row is the important one. A listener that never wrote received
`07 12 03 00 01 57 52 49 54 45 52 58` — the echo of a *different* process's
text command, payload `WRITERX`. **Windows delivers HID input reports to every
open handle.**

Consequences, and they are design-level:

- **Sharing is not the problem; correlation is.** Nothing is gained by holding
  the handle, and holding it is actively worse: while VIA is open the daemon's
  read queue fills with VIA's replies. Short transactions stay the design, now
  for a measured reason rather than an assumed one.
- ⚠️ **Every read must be matched to its request** — channel and command bytes —
  and non-matching reports **drained and discarded**, not consumed as the
  answer. Ordering alone cannot correlate: another process's reply can land
  between our write and our read. This is stronger than the review's
  same-handle echo concern, which was about our own writes.
- The same experiment showed the echo hazard first-hand within one handle: a
  clock GET issued after a text write returned the **text echo**, not the clock
  reply.

⚠️ `ak820ctl`'s `xfer()` does **no** request/reply matching — it returns the
first report that arrives. It fails *safe* only by accident: a text echo puts a
bogus value in `rep[11]`, and the protocol-version check then refuses to act.
The Rust port must validate properly rather than inherit that luck. `ak820health.py`
already does it correctly (`rep[0] == SET_VALUE && rep[1] == HEALTH_CHANNEL`)
and is the model — though it raises rather than draining and retrying.

### Media must not be able to stall the clock

The earlier claim that the daemon "has nothing else to do" while waiting on SMTC
was wrong — it has a clock loop. A 3-second interval bounds polling *frequency*,
not the duration of `RequestAsync` or metadata retrieval, and an indefinitely
blocked media call would stop clock sync, reconnection and shutdown.

So: a **dedicated SMTC worker thread, initialized MTA**, publishing its latest
completed snapshot to the scheduler. Deadlines on every operation, bounded
outstanding work, and a defined recovery path after session or broker loss —
**without spawning a new stranded worker on every timeout**. `RoInitialize`/
`RoUninitialize` on the right threads.

### Dependency

The `windows` crate, not `windows-sys` as in `../jdrgb` and `../jdups`: SMTC is
WinRT and `windows-sys` has no WinRT projection. Hand-rolled WinRT ABI machinery
is needless risk.

**Measured 2026-09-05** with a throwaway probe that actually reads SMTC, built
with the siblings' size profile (`opt-level="z"`, `lto`, `codegen-units=1`,
`panic="abort"`, `strip`), on rustc 1.97.0 MSVC:

| | |
|---|---|
| Version | **`windows 0.62.2`** — pin it |
| Direct deps | 1; **15 packages total** (`windows-core`, `-future`, `-strings`, `-result`, `-collections`, `-numerics`, `-link`, `-threading`, plus proc-macro machinery) |
| Blocking async spelling | **`.join()`** — `.get()` does **not** exist here; an earlier draft assumed it and does not compile |
| Release binary, SMTC linked **and exercised** | **117 KB** |

117 KB against 32.7 MB of Python settles the size question: the crate is
metadata-driven, so unused APIs cost nothing and there is no reason to mix in
`windows-sys`. The remaining size/footprint work is steady-state private bytes
and handle/thread growth under the SMTC worker, which a one-shot probe cannot
show.

### ⚠️ HID discovery: open nothing you did not mean to

`CM_Get_Device_Interface_ListW` with `GUID_DEVINTERFACE_HID` returns the
Configuration Manager's own path list and **opens nothing**. Handle
`CR_BUFFER_SMALL` with a retry and pass the present-interfaces flag, as the
sibling does. This is what addresses the UPS incident, and it is kept.

But a path match is a **candidate selector, not proof of identity** — Microsoft
documents these symbolic names as opaque. So:

- case-insensitive, **bounded** matching within the hardware-ID portion, not a
  loose substring search; reject unexpected path forms
- after opening a candidate, still verify with `HidD_GetAttributes`, then usage
  page/usage, report lengths, and protocol version before any application write
- decide what happens with **two matching keyboards** (refuse and report, rather
  than pick one)
- post-open checks prevent a wrong *write*; they cannot un-open a wrong device,
  which is why the pre-open filter has to be tight

Test the discovery/open boundary with unrelated devices present, and audit every
path in the codebase that can open a HID handle.

### Presence is a state machine, not a boolean

An unsuccessful open is **not** absence. Treating VIA contention as absence
clears learner continuity and can manufacture a spurious `enumerated` sync when
access returns; conversely a reboot can reuse the same path between polls.
Distinct states: **absent**, **discovered-but-busy**, **open-but-unresponsive**,
**incompatible firmware**. Use device-generation/reset observations where
available.

Keep **discovery cadence, target-open backoff, and power policy separate.** For
passive CM listing — which opens nothing — there is no reason to delay presence
knowledge for five minutes; the backoff exists to protect *opens*. (The Python
agent's conflation of these was a real bug, fixed in `b31acd9`.)

## Phases, with gates that can actually fail

Build the **minimal daemon scheduler before phase 3** — otherwise phase 3
validates clock code and phase 4 then changes its scheduling and failure
environment underneath it.

| # | Work | Gate |
|---|---|---|
| 0 | HID discovery, transport, `ak820 info` | Same JEDEC id and writable base as `ak820ctl info`; **plus** wrong-interface and malformed-report rejection, timeout/unplug/cancellation, traced opens showing nothing unrelated was touched, and VIA coexistence measured. |
| 1 | `text.rs`, `smtc.rs`, `--probe` | Captured media fixtures: competing sessions, paused-vs-current ranking, missing metadata, absent timeline, seeks, stale/future timestamps, Unicode, keepalive, partial write failure, reconnect. |
| 2 | Clock read | Identical **captured** replies decode identically. (Sequential live reads cannot match field for field.) |
| 3 | Clock set + learners | C-transaction fixtures pass; deterministic replay matches decisions **and next state**, with evidence learning fired; then measured takeover on the combined daemon runtime. |
| 4 | Daemon + one Scheduled Task | Migration from the two Python tasks, restart, suspend/resume, battery, rollback, and real liveness — not merely a registered task. |
| 5 | Health | Decoding fixtures match `ak820health.py`; enough health reporting lands **before** takeover to detect added firmware stalls. |
| 6 | Release | **Clean-machine install from Releases with no Python and no MSYS2.** This is a stated primary motivation and needs its own gate. |

### Phase 0 evidence (2026-09-05)

All of it on this machine, with **both Python agents running**, so every number
below was taken under the contention the design is about.

| Gate item | Result |
|---|---|
| Same JEDEC id and writable base as `ak820ctl info` | **byte for byte identical**: `flash jedec id : 0x856017` / `writable from  : 0xCE0000`. The base independently equals `FLASH_ASSET_BASE` (`0x0CE0000`) in `graphics/lcd_bus.h`, so the decode is cross-checked against the firmware source as well as against the C tool. `0x856017` is Puya, 64 Mbit — consistent with an asset base 3.12 MB into an 8 MB chip. |
| Wrong-interface rejection | The board presents **five** collections; `ak820 list --caps` opens each and the checker accepts exactly one. Measured usages now replace the guessed fixtures in `hid::caps`. |
| Malformed-report rejection | Report-id, short-read, wrong-header and wrong-channel cases are unit tests over the real byte patterns. |
| Timeout / cancellation | Both branches exercised, below. |
| Traced opens | `33 HID interfaces present, 5 of them this board's; opening none`. `hidapi` would have opened all 33 — including the UPS — to answer the same question. |
| Coexistence | 30/30 consecutive `info` runs correct while both Python agents ran. |

**The board's five collections, measured** (`ak820 list --caps`):

| Interface | Usage | Reports in/out | |
|---|---|---|---|
| `MI_01` | `FF60`/`61` | 33/33 | **ours** |
| `MI_00` | `0001`/`06` | 9/2 | boot keyboard |
| `MI_02&Col01` | `0001`/`80` | 3/0 | system control |
| `MI_02&Col02` | `000C`/`01` | 3/0 | consumer |
| `MI_02&Col03` | `0001`/`06` | **32**/2 | NKRO keyboard |

⚠️ That last row is why the usage-page check cannot be traded for a
report-size one: the NKRO keyboard's input reports are **32 bytes**, the same
size as one of ours with the report id stripped, so they pass
`proto::normalize_input`'s tolerant branch. Only the usage says it is a
keyboard. Pinned as a test.

**The broadcast finding reproduced by the Rust transport.** One of the 30 `info`
runs found two reports already queued on our handle before we had written
anything:

```
note: discarded 2 report(s) that answered another request:
  queued before we asked: channel 0x12 command 0x04
  queued before we asked: channel 0x12 command 0x02
```

Channel `0x12` is text; `0x04` is `TEXT_PLAYBACK` and `0x02` is `TEXT_CLEAR` —
the *now-playing agent's* writes, echoed to a process that had written nothing.
⚠️ Note what `ak820ctl`'s `xfer()` would have done with the first of those as
the answer to `FC_INFO`: `rep[3]` is the playback state byte, so state 0 reads
as `FS_OK`, and it would have printed a **JEDEC id decoded from a track
position**. The protocol-version check that saves the clock path does not exist
here. This is no longer a hypothesis about `xfer()`; the traffic that would
trigger it was captured.

**Cancellation, both branches** (`ak820 selftest`, 8 runs):

- *Completed between the wait expiring and the cancel landing* — a 1 ms budget
  against a ~5–18 ms round trip, 8/8. Reported as the answer it is, not
  flattened into a timeout. Flattening it would mean re-sending a write that
  already went out.
- *Genuinely aborted* — `drain()` on an idle queue, where nothing but the
  cancellation can complete the read. Returns in **3–6 ms**, so `CancelIoEx`
  does land on a pending HID read and a nominal timeout cannot become an
  unbounded shutdown wait. Every request runs this, so the abort path is
  exercised continuously rather than only when something is wrong.
- *Recovery* — the next full request returns the identical answer, which is the
  check that actually matters: a botched cancellation shows up later, as a dead
  handle or a buffer the kernel wrote into after we dropped it.

**Not yet done, and honestly outstanding:** VIA itself has not been opened
against a live transaction (the two Python agents are a stronger concurrency
load but not the same program), and unplug-during-transaction is a physical test
still to run. Round-trip latency is **~5–18 ms**, higher than the single-digit
figure assumed when the request budget was set; not a problem at a 300 s sync
interval, but worth remembering before anything gets built on a tight one.

Carry over the sibling's cancellation discipline: `CancelIoEx` *requests*
cancellation — buffers and `OVERLAPPED` must stay alive until completion, or a
nominal timeout becomes a use-after-free or an unbounded shutdown wait.

⚠️ One open does **not** mathematically guarantee one LCD repaint: two reports a
millisecond apart can still straddle a 100 ms tick. Batching is the measured
mitigation, not a proof. Either define an observable acceptance criterion or add
firmware staging/commit for a real atomic update.

## Still to specify before coding

- **Cache ownership and migration** — native path, importing existing lead/bias,
  malformed-cache handling, atomic replacement, CLI interaction, and rollback
  compatibility with `ak820ctl` while it remains installed.
- **Observability** — bounded logs, startup failures, version/protocol identity,
  last successful clock and media operations, and a degraded-state report.
  "Task running" can coexist with hours of failed syncs.
- **Text normalization** — Python does punctuation substitution plus NFKD and
  ASCII filtering; Rust's std has no NFKD. Choose an implementation and pin
  output fixtures.
- **Task lifecycle** — preserve what `hostagent/install-agents-windows.ps1`
  already gets right: interactive user, both battery settings, unlimited
  execution time, restart policy, duplicate prevention, and stopping the old
  processes during migration.

## Open

- ~~Naming~~ **SETTLED**: package and directory `ak820-agent`, binaries
  `ak820-agent.exe` (daemon) and `ak820.exe` (CLI). "Agent" is already this
  project's own word (README, `install-agents*.ps1`, both Scheduled Task
  names), and `../jdups` already ships a `jdups-agent` binary for exactly this
  role. `ak820d` was dropped: `d`-for-daemon is a Unix idiom in a Windows-only
  program.
- Whether `ak820.exe` eventually absorbs `ak820ctl`'s clock subcommand, leaving
  the C tool purely for provisioning. Decide before phase 5.
- Config file, or compiled-in constants? Start with none.
