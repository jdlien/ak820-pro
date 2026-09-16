//! `ak820-agent` -- the daemon. The body is per platform:
//! `platform::windows::daemon` and `platform::macos`.
//!
//! ⚠️ The attribute below is the one declared `#[cfg]` in a shared file
//! (plans/AK820-AGENT-CROSSPLATFORM-PLAN.md, *Architecture*), and the whole
//! reason this is a separate binary from `ak820.exe`: a PE has exactly one
//! subsystem, and a windows-subsystem image **cannot** flash a console window,
//! whatever spawns it and whether or not anyone remembered `CREATE_NO_WINDOW`.
//! It must be an inner attribute of the crate root, which is this file.
#![cfg_attr(windows, windows_subsystem = "windows")]

fn main() {
    ak820_agent::platform::daemon_main()
}
