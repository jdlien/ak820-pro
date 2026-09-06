//! ak820-agent -- clock sync and now-playing for the AJAZZ AK820 Pro LCD.
//!
//! Windows only, by design: macOS keeps the Python LaunchAgents, which also
//! remain the clock's reference implementation. See plans/AK820-AGENT-PLAN.md.
pub mod clock;
pub mod flash;
pub mod hid;
pub mod proto;
pub mod smtc;
pub mod text;
