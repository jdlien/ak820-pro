//! `ak820-agent` -- the daemon. Phase 0: a stub.
//!
//! ⚠️ The attribute below is the whole reason this is a separate binary from
//! `ak820.exe`: a PE has exactly one subsystem, and a windows-subsystem image
//! **cannot** flash a console window, whatever spawns it and whether or not
//! anyone remembered `CREATE_NO_WINDOW`. That makes the bug impossible by
//! construction rather than by discipline, which is the only version of that
//! guarantee worth having in something a Scheduled Task starts.
//!
//! It also means stdout is gone. Everything this binary has to say will go to a
//! log, not a stream -- see "Observability" in plans/AK820-AGENT-PLAN.md.
#![windows_subsystem = "windows"]

fn main() {}
