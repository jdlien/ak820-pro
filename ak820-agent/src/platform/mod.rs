//! The seam: everything that differs between Windows and macOS, behind traits.
//!
//! Plan: `plans/AK820-AGENT-CROSSPLATFORM-PLAN.md`, *Architecture*. The rule
//! that makes the seam safe is that **no shared file carries a `#[cfg]`** —
//! this file is where the platform is chosen, and the one admitted exception
//! is the `windows_subsystem` attribute on the daemon binary. A shared file
//! with two platforms' logic interleaved is how the clock core would quietly
//! diverge again, which is the thing the whole plan exists to prevent.
//!
//! The traits, and where each lives:
//!
//! | trait | where | Windows | macOS |
//! |---|---|---|---|
//! | `HidTransport` | `crate::hid` | `CreateFile` + overlapped I/O | IOKit, one object per board arrival |
//! | discovery + open | [`Platform`] | Configuration Manager, opens nothing | IORegistry, opens nothing |
//! | `MediaSource` | `crate::media` | SMTC | MediaRemote via perl, AppleScript fallback |
//! | `Host` | `crate::clock::host` | `GetSystemTimePreciseAsFileTime` | `clock_gettime` + `localtime_r` |
//! | service installer | per platform, for now | Scheduled Task | LaunchAgent (Phase 4a) |
//!
//! The installer is not yet a trait because only one implementation exists;
//! Phase 4a writes the second and extracts the shared shape from the two,
//! rather than guessing it from one.

use std::time::Duration;

use crate::clock::host::Host;
use crate::hid::{self, HidTransport};
use crate::logfile::Log;
use crate::media::MediaSource;

/// A held radio owner lock: released when dropped.
pub type RadioGuard = Box<dyn std::any::Any>;

/// What the daemon loop (`crate::agent`) needs from an operating system.
///
/// Implemented by a zero-sized `Native` per platform, and by fakes in tests,
/// so the loop that has run on Windows since 2026-09-06 runs unchanged on
/// macOS rather than being written a second time.
pub trait Platform {
    /// An opened board, for one interaction.
    type Device: HidTransport;
    type Media: MediaSource;
    type Host: Host;

    /// Names the media API in the daemon's first log lines ("SMTC").
    const MEDIA_API: &'static str;

    fn host() -> Self::Host;

    /// Find the board and open it for one interaction. Decides which device
    /// to open from properties read **without opening anything** (G-A).
    fn open_board() -> Result<Self::Device, hid::Error>;

    /// The board's interfaces as the OS lists them, opening nothing: empty
    /// means absent. Joined with `|`, the strings are the clock seed's per-port
    /// controller id, as the Python timekeeper's `cid` is.
    fn listed() -> Vec<String>;

    /// The 2.4G dongle's radio interface, opened for one media tick (raw81
    /// stage 2; `plans/RAWHID-24G-DAEMON-PLAN.md`, D2). A separate opener from
    /// [`Platform::open_board`], used only by the media cycle's radio path, so
    /// the clock and health can never reach the radio. The default: no radio
    /// on this platform yet (macOS: the Mac session's IOKit path).
    ///
    /// ⚠️ The contract: the open sends nothing to the board and leaves no
    /// I/O outstanding. A failed open releases the radio's acquisition, so an
    /// opener that could leave a write in flight would break the quiet that
    /// ownership guarantees (codex's second daemon verify).
    fn open_radio() -> Result<Self::Device, hid::Error> {
        Err(hid::Error::Absent)
    }

    /// The machine-wide radio owner lock (R3-2), taken without blocking:
    /// `Ok(Some)` held until the guard is dropped, `Ok(None)` another owner
    /// holds it. The default: no radio on this platform yet.
    fn radio_lock() -> Result<Option<RadioGuard>, String> {
        Err("the radio is not available on this platform yet".into())
    }

    /// When a snapshot's playback position is true: at the source's last
    /// observation (`true`: Windows, whose `smtc::position` extrapolates to
    /// the read and whose worker caches that read), or when the loop takes the
    /// snapshot (`false`, the default: the Mac's media layer extrapolates to
    /// the snapshot's creation). The lock-LED channel's type 3 advances the
    /// position from this instant, so the wrong one double-counts the age
    /// (codex, play times, P2-2).
    const POSITION_AS_OF_OBSERVATION: bool = false;

    /// The last input on this machine, any device, read raw: the radio's
    /// hold and its wait after a silence (`crate::radio`, rules 1 and 2)
    /// take one reading each media tick and follow them across ticks
    /// (`crate::input::Track`). The same sources the lock-LED sender's hold
    /// and wake guess read (`HIDIdleTime` on macOS, `GetLastInputInfo` on
    /// Windows). `None` when it cannot be read, and the radio behaves as it
    /// did before the hold. The default: none.
    fn host_input() -> Option<crate::input::Reading> {
        None
    }

    /// Has something asked this daemon to stop (Windows: `ak820 install` or
    /// `uninstall` signalling its stop event)? The loop then returns, which
    /// stops the lock-LED sender with its one bounded restore. Default: never.
    fn stop_requested() -> bool {
        false
    }

    /// Start the lock-LED channel's sender thread (`crate::lockchan::sender`)
    /// with this platform's keyboard, owner lock and input tick, if it has
    /// one: now-playing over Bluetooth, where there is no raw HID. The
    /// default: none.
    fn spawn_lockchan() -> Option<Result<crate::lockchan::sender::Handle, String>> {
        None
    }

    /// Start the media source on its own thread. `log` is the daemon's, for a
    /// source with something to say between polls (the macOS helper's
    /// restarts); a source that has nothing to say ignores it.
    fn spawn_media(interval: Duration, log: &Log) -> Result<Self::Media, String>;
}

#[cfg(windows)]
pub mod windows;
#[cfg(windows)]
pub use self::windows::{cli_main, daemon_main, Native, SystemHost};

#[cfg(target_os = "macos")]
pub mod macos;
#[cfg(target_os = "macos")]
pub use self::macos::{cli_main, daemon_main, Native, SystemHost};
