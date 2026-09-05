# ak820d — one Windows daemon for the clock and the LCD text — plan

Status: **PLANNED 2026-09-05, revised the same day** against
[review-codex-ak820d-2026-09-05.md](review-codex-ak820d-2026-09-05.md)
(gpt-6-astra, xhigh). Nothing built.

A single Rust binary replacing the two Python host agents **on Windows only**.
macOS keeps its LaunchAgents and its Python, unchanged.

Companion documents, both of which are part of this plan:

- **[AK820D-CLOCK-PARITY.md](AK820D-CLOCK-PARITY.md)** — the Python scheduler
  and SOF-bias learner.
- **[AK820D-CLOCK-TRANSACTION.md](AK820D-CLOCK-TRANSACTION.md)** — `ak820ctl`'s
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
   CPU-seconds in 25 minutes. Target: one process, ~4 MB.

**Not a reason: speed.** These agents are idle. The only runtime win is that
in-process work replaces an `ak820ctl` spawn per sync.

## Scope

**Replaces, on Windows:** `ak820-timekeeper.py`, `nowplaying-windows.py`, and
the per-transaction `ak820ctl` spawn.

**Does not replace:** `ak820ctl`'s flash provisioning (erases first, rare,
interactive — never in an unattended daemon); the diagnostics; the macOS agents.

## Settled

- Windows only. The crate lives in this repo at `ak820d/`, because the wire
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
ak820d/
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
      ak820d.rs   daemon -- windows subsystem
      ak820.rs    CLI    -- console subsystem
```

Two binaries because a PE has one subsystem. `ak820d.exe` has **no console
ever**, which makes the console-flash bug impossible by construction rather than
dependent on remembering `CREATE_NO_WINDOW`. `ak820.exe` is a console app so
exit codes and stdout survive.

### Ownership is enforced, not intended

A **single serialized HID executor** inside the daemon, plus a **process
instance mutex**. The plan must answer, and the implementation must handle:

| Case | Behaviour |
|---|---|
| second daemon instance | refused by the named mutex |
| `ak820.exe` while the daemon runs | routed through the daemon, or refused with a clear message |
| retained C/Python diagnostics | documented as requiring the daemon paused |
| VIA opening before / during / after a transaction | transaction fails cleanly and retries; no wedged state |

⚠️ **Even a one-shot CLI clock SET invalidates the daemon's learner baseline**
if the daemon does not know it happened. That is the reason the CLI cannot just
open the device independently.

**A transaction is the complete logical operation** — the clock
measure/SET/verify sequence, or a text update batch — not one report. Open
before taking transmission-sensitive timestamps and close promptly after.

⚠️ **`FILE_SHARE_READ | FILE_SHARE_WRITE` explicitly permits concurrent opens**,
and Chromium's HID service uses the same flags. So "holding it open means VIA
can never connect" is **not established** for Windows; it was inferred from
contention observed elsewhere. **Test it on this machine** and let the result
choose between short transactions and a held handle. Short transactions remain
the default either way.

⚠️ **The firmware echoes text commands** (`hid_protocol.c`). If text and clock
operations ever share an open, an unread text echo must never be decoded as a
clock reply. One process does not solve this automatically: the wire layer needs
report-length/ID normalization, header validation, and stale-reply draining.

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
is needless risk. **Pin the version** — the async spelling is version-dependent
(`.join()` / `.await`, not the `.get()` an earlier draft assumed). "One
dependency" means one *direct* dependency; it has supporting crates.

Measure the release binary **with SMTC linked and exercised**, plus steady-state
private bytes and handle/thread growth. A phase-0 HID-only size says nothing
about WinRT, and mixing in `windows-sys` is not a demonstrated size fix.

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

- Naming: `ak820d` + `ak820` matches the existing `ak820ctl`/`ak820text`/
  `ak820health` family rather than the siblings' `jd*`.
- Whether `ak820.exe` eventually absorbs `ak820ctl`'s clock subcommand, leaving
  the C tool purely for provisioning. Decide before phase 5.
- Config file, or compiled-in constants? Start with none.
