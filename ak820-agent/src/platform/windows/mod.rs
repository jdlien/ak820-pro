//! Windows: the platform `ak820-agent` shipped on (v0.1.1, 2026-09-06).
//!
//! Everything here moved from the crate root and `hid/` in Phase 0 of the
//! cross-platform plan with **no behaviour change**; the gate for that is a
//! live run on the Windows machine compared against the pre-refactor daemon's
//! own log, not these tests alone.

pub mod caps;
pub mod cli;
pub mod daemon;
pub mod device;
pub mod host;
pub mod instance;
pub mod path;
pub mod process;
pub mod smtc;
pub mod task;

use std::path::PathBuf;
use std::time::Duration;

use crate::hid::{self, OsError};

pub use cli::main as cli_main;
pub use daemon::main as daemon_main;
pub use host::SystemHost;

/// The Win32 error's own code and text, so logs read as they did when
/// `hid::Error` carried `windows::core::Error` directly.
impl From<windows::core::Error> for OsError {
    fn from(e: windows::core::Error) -> OsError {
        OsError::new(e.code().0 as i64, e.to_string())
    }
}

pub struct Native;

impl crate::platform::Platform for Native {
    type Device = device::Device;
    type Media = smtc::MediaWorker;
    type Host = SystemHost;

    const MEDIA_API: &'static str = "SMTC";

    fn host() -> SystemHost {
        SystemHost
    }

    fn open_board() -> Result<device::Device, hid::Error> {
        device::open_board()
    }

    /// `hid_present()`: the Configuration Manager's list, opening nothing.
    fn listed() -> Vec<String> {
        device::interfaces(hid::VID, hid::PID)
            .unwrap_or_default()
            .iter()
            .map(|i| i.path().to_string())
            .collect()
    }

    fn spawn_media(interval: Duration) -> Result<smtc::MediaWorker, String> {
        smtc::MediaWorker::spawn(interval)
    }
}

/// `%LOCALAPPDATA%\ak820pro`: the directory the PowerShell installer put the
/// Python agents' logs in, so the migration reads as one story.
pub fn default_dir() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("USERPROFILE").map(|p| PathBuf::from(p).join("AppData").join("Local")))
        .unwrap_or_else(|| PathBuf::from("."))
        .join("ak820pro")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_default_dir_is_under_local_appdata() {
        let d = default_dir();
        assert!(d.ends_with("ak820pro"));
        assert!(d.is_absolute());
    }

    #[test]
    fn an_os_error_keeps_the_win32_text_and_code() {
        let e = windows::core::Error::from_hresult(windows::core::HRESULT::from_win32(32));
        let text = e.to_string();
        let os: OsError = e.into();
        assert_eq!(os.to_string(), text);
        assert_eq!(os.code, 0x80070020_u32 as i32 as i64);
    }
}
