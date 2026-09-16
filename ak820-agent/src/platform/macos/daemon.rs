//! `ak820-agent` on macOS: now-playing only (plan, build order: Phase 3, then
//! 4a). The Python timekeeper owns the clock until Phase 2 and 4b, so this
//! **refuses `--clock`** rather than accept a flag it cannot honour.
//!
//! ```text
//! ak820-agent [--log PATH] [--status PATH] [--interval SECS] [--once]
//! ```
//!
//! The log is `~/Library/Logs/ak820pro/ak820-agent.log`, where Console.app
//! looks; the status file is `~/Library/Application Support/ak820pro/`.
//! A LaunchAgent (Phase 4a) sends stdout nowhere, so everything worth saying,
//! including a refusal to start, goes to the log.

use std::path::PathBuf;
use std::time::Duration;

use super::instance::{self, Lock};
use crate::logfile::Log;
use crate::{agent, media};

fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."))
}

pub fn log_dir() -> PathBuf {
    home().join("Library/Logs/ak820pro")
}

pub fn state_dir() -> PathBuf {
    home().join("Library/Application Support/ak820pro")
}

pub fn main() {
    let mut opts = agent::Options {
        interval: media::INTERVAL,
        log: log_dir().join("ak820-agent.log"),
        status: state_dir().join("ak820-agent.status"),
        once: false,
        clock: false,
    };

    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        let value = args.get(i + 1);
        match (args[i].as_str(), value) {
            ("--log", Some(v)) => {
                opts.log = v.into();
                i += 2;
            }
            ("--status", Some(v)) => {
                opts.status = v.into();
                i += 2;
            }
            ("--interval", Some(v)) => {
                match v.parse::<f64>() {
                    Ok(secs) if secs.is_finite() && (0.5..=3600.0).contains(&secs) => {
                        opts.interval = Duration::from_secs_f64(secs)
                    }
                    _ => bail(&opts.log, &format!("bad --interval {v} (0.5 to 3600 seconds)")),
                }
                i += 2;
            }
            ("--once", _) => {
                opts.once = true;
                i += 1;
            }
            ("--clock", _) => {
                opts.clock = true;
                i += 1;
            }
            (other, _) => bail(&opts.log, &format!("unknown argument {other:?}")),
        }
    }

    // After parsing, so the refusal lands in the log `--log` named, whatever
    // the argument order.
    if opts.clock {
        bail(&opts.log, "not starting: --clock is not built on macOS yet; the Python timekeeper owns the clock");
    }

    let _held: Lock = match Lock::claim_all(&instance::default_path(), &instance::all_paths()) {
        Ok(held) => held,
        Err(e) => bail(&opts.log, &format!("not starting: {e}")),
    };

    let log = opts.log.clone();
    if let Err(e) = agent::run::<super::Native>(opts) {
        Log::at(&log).line(&format!("stopped: {e}"));
        std::process::exit(1);
    }
}

fn bail(log: &std::path::Path, message: &str) -> ! {
    Log::at(log).line(message);
    eprintln!("{message}");
    std::process::exit(2)
}
