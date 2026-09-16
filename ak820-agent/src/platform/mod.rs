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
