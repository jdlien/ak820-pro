//! ak820-agent -- clock sync and now-playing for the AJAZZ AK820 Pro LCD.
//!
//! Windows only, by design: macOS keeps the Python LaunchAgents, which also
//! remain the clock's reference implementation. See plans/AK820-AGENT-PLAN.md.
pub mod agent;
pub mod clock;
pub mod flash;
pub mod hid;
pub mod instance;
pub mod logfile;
pub mod media;
pub mod proto;
pub mod smtc;
pub mod status;
pub mod task;
pub mod text;
pub mod via;

/// `git describe` of the tree this was built from, baked in by `build.rs`.
/// A Releases build says its tag; a development build says
/// `<tag>-<n>-g<hash>[-dirty]`; a tree without git says `unknown`.
pub const GIT_DESCRIBE: &str = env!("AK820_GIT_DESCRIBE");

/// The one line that identifies a binary and what it speaks — printed by
/// `ak820 --version`, and the daemon's first log line. The protocol versions
/// are here because the wire protocol is firmware-versioned: a bug report
/// needs both halves.
pub fn version_line(binary: &str) -> String {
    format!(
        "{binary} {} ({GIT_DESCRIBE}); speaks RTC protocol {}, text channel 0x{:02X}, health channel 0x{:02X}",
        env!("CARGO_PKG_VERSION"),
        clock::PROTO_VERSION,
        proto::Channel::Text.id(),
        proto::Channel::Health.id(),
    )
}
