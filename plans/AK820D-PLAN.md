# ak820d — one Windows daemon for the clock and the LCD text — plan

Status: **PLANNED 2026-09-05.** Nothing built. Decisions in "Settled" below are
agreed; "Open" are not.

A single Rust binary replacing the two Python host agents **on Windows only**.
macOS keeps its LaunchAgents and its Python, unchanged.

## Why

In order of how much they actually matter:

1. **One owner for a single-owner interface.** The board's raw-HID interface is
   exclusive. Today two independent processes contend for it (timekeeper,
   nowplaying), plus `ak820health.py`, plus VIA. Each opens and closes
   constantly and each has to cope with the others. That contention is already
   documented as having been "twice mistaken for a firmware fault". One process
   owning it removes a whole class of confusion, and lets the clock band and
   text band be written in a known order instead of two processes straddling
   the firmware's ~10 Hz repaint tick.

2. **Installation.** Running the agents on Windows today costs: MSYS2, two
   venvs, native-python discovery, a `winsdk` wheel, `hidapi.dll` plus a `.pth`
   shim for Python 3.8+'s DLL search, and a venv whose *name* must contain
   `mingw64`. Nearly all of that exists only to make Python run. A single
   `.exe` deletes the list. It also closes a real gap: an owner who takes
   prebuilt firmware from Releases currently **cannot run the agents at all**,
   and the clock and now-playing are the features that make this board
   interesting.

3. **Footprint.** Measured 2026-09-05: **32.7 MB across 4 processes** (two
   agents, each with a venv launcher stub), 3.1 CPU-seconds in 25 minutes.
   Target: one process, ~4 MB.

**Not a reason: speed.** These agents are idle — 0.2% of one core, most of it
the 3-second SMTC poll. Nothing here is slow. The only runtime win is that
in-process work replaces an `ak820ctl` spawn per sync, which is the bug class
that flashed a console window and stole focus (fixed in `63905ea`, but fixed
*structurally* by a daemon that never spawns anything).

## Scope

**Replaces, on Windows:** `ak820-timekeeper.py`, `nowplaying-windows.py`, and
the per-transaction `ak820ctl` spawn.

**Does not replace:**

- `ak820ctl`'s **flash provisioning** (`flash write|erase|crc`). It erases
  first, it is rare, and it is interactive. It does not belong in a daemon that
  runs unattended at logon. `ak820ctl` stays exactly as it is.
- The diagnostics: `soak.py`, `bt_faults.py`, `clock-phase.py`,
  `rtc_phase0.py`, `ak820keymap.py`. Ad-hoc scripts are the right shape, and
  `clock-phase.py` is the measuring instrument for phase 3.
- The **macOS** agents. They keep working and the Python timekeeper remains the
  clock's reference implementation — see [AK820D-CLOCK-PARITY.md](AK820D-CLOCK-PARITY.md).

## Settled

- **Windows only.** macOS is different enough (no SMTC; media needs per-app
  AppleScript) that a shared abstraction would buy little and cost the
  single-dependency convention.
- **The crate lives in this repo**, at `ak820d/`. The wire protocol is
  firmware-versioned — channels `0x10`/`0x12`/`0x13`, health page layouts, the
  RTC protocol version — so a firmware change and a daemon change must land
  together. Same reasoning as the index-matched keycode enum that
  `scripts/check_via_sync.py` guards.
- **The Python timekeeper is the oracle** for the clock loop.
- **No tray, no icon.** Unlike `../jdrgb` and `../jdups` this has nothing to
  show. Room is left for a third binary later; nothing is built for it now.

## Conventions inherited from ../jdrgb and ../jdups

- `edition = 2021`; release profile `opt-level = "z"`, `lto = true`,
  `codegen-units = 1`, `panic = "abort"`, `strip = true`.
- **A `lib` plus multiple binaries, because a PE has exactly one subsystem.**
- Every dependency feature gets a comment saying why it is there.
- Comments carry the *why*, especially where the obvious implementation is
  wrong (`../jdups/CLAUDE.md`, "Style").
- Findings about the hardware get pinned in a test, with the comment saying
  they were measured.

## Layout

```
ak820d/
  Cargo.toml
  src/
    lib.rs
    hid.rs        device discovery by path, report read/write
    proto.rs      channels and packet builders (firmware-coupled)
    clock.rs      sync loop + bias learner      <- see the parity doc
    text.rs       line/icon/playback packets, ASCII folding
    smtc.rs       media sessions
    health.rs     counters
    bin/
      ak820d.rs   the daemon  -- windows subsystem
      ak820.rs    the CLI     -- console subsystem
```

- **`ak820d.exe`** — windows subsystem, so it has no console **ever**. That is
  what makes the console-flash class of bug impossible by construction rather
  than dependent on remembering `CREATE_NO_WINDOW` at every call site.
- **`ak820.exe`** — console subsystem. `--probe`, health, one-shot clock/text
  set. A windows-subsystem process gets no stdout from the calling shell and
  the shell does not wait for it, so exit codes and output would be lost —
  the argument `../jdups/Cargo.toml` already makes.

## ⚠️ HID: never enumerate

The single most important constraint in this document.

`hidapi`'s enumeration opens **every HID device on the machine** to read its
attributes; a VID/PID filter is applied afterwards and spares none of them.
`../jdrgb/docs/ups-wedge-incident.md` records that pattern twice wedging an APC
Back-UPS on this machine — every request failing from every process, recoverable
only by physically replugging — while `../jdups` held a latched outage it could
no longer see the end of and came within ~20 minutes of shutting down a machine
whose power was fine. `ak820text.py` was a second source of the same pattern
until `61038c6`.

So, following `../jdrgb/src/hid.rs`:

1. `CM_Get_Device_Interface_ListW` with `GUID_DEVINTERFACE_HID` returns the
   Configuration Manager's own NUL-separated path list. **This opens nothing.**
2. Narrow by matching `vid_0c45&pid_8009` as **text** in those paths.
3. Open only those candidates — never a device belonging to anything else —
   and confirm usage page `0xFF60` / usage `0x61` via `HidD_GetPreparsedData` +
   `HidP_GetCaps`. Prefer the `&mi_01` candidate first, which is where this
   firmware puts raw HID (measured), so the usual case opens exactly one.
4. Cache the path; reopen by path. Re-derive only when an open fails, and
   rate-limit that, for the reason in `ak820text.py`'s `open_device()`.

**Two refinements from ../jdups (2026-09-05), already implemented in the Python
agent and required here too:**

- **Back the retry off exponentially**, 30 s doubling to a 300 s ceiling, not a
  flat cadence. A held device is a *persistent* condition; jdups changed its own
  reopen loop for the same reason.
- **Gate re-enumeration on `GetSystemPowerStatus`.** jdups' measurements of both
  2026-08-03 wedges put them within seconds of **mains returning**, while the
  UPS was transferring back and Windows' battery driver was querying it too —
  enumeration on steady mains has never hurt it. So the rule is not "stop while
  on battery", which would release at exactly the wrong instant: hold off while
  `ACLineStatus == 0` **and for 60 s after it returns to 1**. One syscall, no
  device I/O. `255` is "unknown" (a desktop with no battery) and must not be
  treated as offline. This matters because a power blip can itself make the
  board re-enumerate, invalidating the cached path and otherwise sending us
  walking every HID interface at the worst possible moment.

**Open the device per transaction, not for the daemon's lifetime,** and with
`FILE_SHARE_READ | FILE_SHARE_WRITE`. Holding it open would mean VIA can never
connect while the daemon runs, which is a worse experience than the contention
it would remove.

## Dependency: `windows`, not `windows-sys` — a deliberate deviation

Both sibling projects use `windows-sys` as their single dependency. This one
cannot: `windows-sys` is raw Win32 FFI with **no WinRT projection**, and SMTC
(`Windows.Media.Control`) is WinRT. Hand-rolling `RoActivateInstance` plus
`IAsyncOperation` completion handlers through raw FFI is possible and
genuinely unpleasant.

The proposal is therefore **one dependency, the `windows` crate**, which is a
superset: it provides both the Win32 surface (`Devices::HumanInterfaceDevice`,
`Devices::DeviceAndDriverInstallation`, `Storage::FileSystem`) and the WinRT
namespace. Still a single dependency, still no `hidapi`, just a different crate
than the siblings picked — and for a reason that does not apply to them.

Worth confirming binary size once phase 0 links; if the `windows` crate proves
heavy, the fallback is `windows-sys` for HID plus `windows` for SMTC only.

## Phases, each with a gate

| # | Work | Gate |
|---|---|---|
| 0 | Skeleton, `hid.rs`, `ak820 info` | Reports the same JEDEC id (`0x856017`) and writable base (`0xCE0000`) as `ak820ctl info`. Opens no device that is not the keyboard — verified by path logging. |
| 1 | `text.rs` + `smtc.rs`, `ak820 --probe` | `--probe` matches `nowplaying-windows.py --probe`. LCD output indistinguishable from the Python agent, including the no-double-flash single-open behaviour. |
| 2 | `clock.rs` read-only | `ak820 clock --read` matches `ak820ctl clock --read` field for field. |
| 3 | Clock set, slew, learner | The parity doc's shadow-mode A/B, then a measured run. **This is the risky phase.** |
| 4 | `ak820d.exe` + one Scheduled Task | Replaces both Python tasks. `-Status` shows one task. Footprint measured against the 32.7 MB baseline. |
| 5 | `health.rs` in the CLI | Matches `ak820health.py` on all four pages. |

Phases 0–2 are safe: they read, or they write only the text band. Phase 3 is
the one that can regress something JD spent real effort getting right.

## Risks

- **The clock loop.** Its constants are scar tissue with dates attached. See
  the parity doc; it is the reason that document exists.
- **WinRT async from Rust.** SMTC's API is `IAsyncOperation`-based. The Python
  agent gets `asyncio` for free; Rust needs the `windows` crate's `.get()`
  blocking form or a small executor. Prefer blocking — the daemon polls at 3 s
  and has nothing else to do.
- **Two implementations of the media logic** (Python on macOS, Rust on
  Windows) can drift. Accepted: the display contract is documented in both, and
  macOS's producer is AppleScript-based anyway, so they were never shared code.
- **Retiring the Python agents on Windows** loses accumulated edge-case
  behaviour around sleep/wake and re-enumeration. Keep the Python tasks
  installable and documented as the fallback until phase 4 has run for a week.

## Open

- Binary/crate naming: `ak820d` + `ak820` reads consistently with the existing
  `ak820ctl` / `ak820text` / `ak820health` family. The `jd*` convention of the
  sibling repos was not followed because those are standalone tools and these
  live beside firmware-coupled siblings. Say if you would rather have `jdak820`.
- Whether `ak820.exe` should eventually absorb `ak820ctl`'s clock subcommand,
  leaving the C tool purely for flash provisioning. Not in scope for phase 4;
  worth deciding before phase 5.
- Config file, or compiled-in constants? The Python agents have none. Start with
  none.
