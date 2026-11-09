//! macOS: being built, phase by phase (plans/AK820-AGENT-CROSSPLATFORM-PLAN.md).
//!
//! Phase 0 gave the crate a macOS half that compiles, so every platform-neutral
//! test runs natively on the Mac. Phase 1 adds the transport, from spike S2:
//! registry discovery that opens nothing, and IOKit with one device object per
//! board arrival. Phase 3 adds the media source, from spikes S1 and S1b, and
//! the daemon runs now-playing on it. The clock (Phase 2) comes next.

mod cf;
pub mod cli;
pub mod daemon;
pub mod device;
pub mod discovery;
pub mod host;
pub mod install;
pub mod instance;
pub mod launchd;
pub mod lock_lights;
pub mod media;
pub mod process;
pub mod radio_lock;
mod runloop;
pub mod stop;
mod sys;

use std::time::Duration;

pub use cli::main as cli_main;
pub use daemon::main as daemon_main;
pub use host::SystemHost;

use crate::hid;
use crate::logfile::Log;

/// The daemon's view of macOS.
pub struct Native;

impl crate::platform::Platform for Native {
    type Device = device::Device;
    type Media = media::MediaRemoteSource;
    type Host = SystemHost;

    const MEDIA_API: &'static str = "MediaRemote";

    fn host() -> SystemHost {
        SystemHost
    }

    fn open_board() -> Result<device::Device, hid::Error> {
        device::open_board()
    }

    /// The board's services from the IORegistry, opening nothing.
    fn listed() -> Vec<String> {
        device::listed()
    }

    fn open_radio() -> Result<device::Device, hid::Error> {
        device::open_radio()
    }

    /// SIGTERM (launchd's bootout) or SIGINT taken (`stop.rs`).
    fn stop_requested() -> bool {
        stop::requested()
    }

    /// The lock-LED channel's sender, on a thread of its own: P3 over the
    /// board's BLE keyboard (`lock_lights.rs`).
    fn spawn_lockchan() -> Option<Result<crate::lockchan::sender::Handle, String>> {
        Some(crate::lockchan::sender::spawn(lock_lights::Mac::default()))
    }

    fn radio_lock() -> Result<Option<crate::platform::RadioGuard>, String> {
        radio_lock::try_take().map(|held| held.map(|l| Box::new(l) as crate::platform::RadioGuard))
    }

    /// The HID system's `HIDIdleTime`, as the lock-LED sender reads it.
    fn host_input() -> Option<crate::input::Reading> {
        lock_lights::idle().map(crate::input::Reading::Idle)
    }

    fn spawn_media(interval: Duration, log: &Log) -> Result<media::MediaRemoteSource, String> {
        let log = Log::at(log.path());
        media::MediaRemoteSource::spawn(
            media::Options { interval, applescript: true, dylib: media::dylib_path() },
            Box::new(move |line| log.line(&line)),
        )
    }
}
