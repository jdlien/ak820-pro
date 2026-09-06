//! `ak820-agent` -- the daemon.
//!
//! ⚠️ The attribute below is the whole reason this is a separate binary from
//! `ak820.exe`: a PE has exactly one subsystem, and a windows-subsystem image
//! **cannot** flash a console window, whatever spawns it and whether or not
//! anyone remembered `CREATE_NO_WINDOW`. That makes the bug impossible by
//! construction rather than by discipline, which is the only version of that
//! guarantee worth having in something a Scheduled Task starts.
//!
//! It also means stdout is gone. Everything this binary has to say goes to
//! the log, including why it refused to start; `ak820 status` reads it back.
//!
//! Phase 4a: now-playing only. The clock loop is not here yet — see "Staged
//! switch-over" in plans/AK820-AGENT-PLAN.md — and the Python timekeeper owns
//! the clock until it is.
//!
//! ```text
//! ak820-agent [--log PATH] [--status PATH] [--interval SECS] [--once] [--clock]
//! ```
//!
//! `--clock` runs the clock loop as well. `ak820 install --clock` is the only
//! thing that should pass it, because it also removes the Python timekeeper's
//! task: two clock writers silently corrupt each other's learners.
#![windows_subsystem = "windows"]

use std::time::Duration;

use ak820_agent::instance::{self, Instance};
use ak820_agent::logfile::Log;
use ak820_agent::{agent, media, process, task};

fn main() {
    let dir = agent::default_dir();
    let mut opts = agent::Options {
        interval: media::INTERVAL,
        log: dir.join("ak820-agent.log"),
        status: dir.join("ak820-agent.status"),
        once: false,
        clock: false,
    };

    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        let value = |i: usize| -> Option<&String> { args.get(i + 1) };
        match args[i].as_str() {
            "--log" if value(i).is_some() => {
                opts.log = value(i).unwrap().into();
                i += 2;
            }
            "--status" if value(i).is_some() => {
                opts.status = value(i).unwrap().into();
                i += 2;
            }
            "--interval" if value(i).is_some() => {
                // Bounded and finite: `inf` or 1e300 would panic inside
                // Duration and a tiny value would poll continuously — either
                // way with no console to say so.
                match value(i).unwrap().parse::<f64>() {
                    Ok(secs) if secs.is_finite() && (0.5..=3600.0).contains(&secs) => {
                        opts.interval = Duration::from_secs_f64(secs)
                    }
                    _ => bail(
                        &opts.log,
                        &format!("bad --interval {} (0.5 to 3600 seconds)", value(i).unwrap()),
                        2,
                    ),
                }
                i += 2;
            }
            "--once" => {
                opts.once = true;
                i += 1;
            }
            "--clock" => {
                opts.clock = true;
                i += 1;
            }
            other => bail(&opts.log, &format!("unknown argument {other:?}"), 2),
        }
    }

    // Ownership is enforced, not intended: one of us, and not the Python
    // now-playing agent either, whose mutex name this also takes.
    let _held: Instance = match Instance::claim(&[instance::AGENT, instance::NOWPLAYING]) {
        Ok(held) => held,
        Err(e) => bail(&opts.log, &format!("not starting: {e}"), 2),
    };

    // ⚠️ The clock's ownership is not the flag's word alone (the phase-3a/4a
    // audit's finding 1). `ak820 install --clock` removes the Python
    // timekeeper's task before registering this one with `--clock`; if that
    // task is nonetheless registered — the PowerShell installer was re-run —
    // it will write the clock at the next logon if it is not doing so now,
    // and two writers corrupt each other's learners. Refusing to start is
    // the safe failure; not being able to ask is treated the same way.
    if opts.clock {
        match task::info(task::FOLDER, task::TIMEKEEPER) {
            Ok(None) => {}
            Ok(Some(_)) => bail(
                &opts.log,
                &format!(
                    "not starting: --clock was given but the Python task {} is still registered; \
                     `ak820 install --clock` removes it, or run without --clock",
                    task::TIMEKEEPER
                ),
                2,
            ),
            Err(e) => bail(&opts.log, &format!("not starting: cannot establish who owns the clock ({e})"), 2),
        }
        match process::running("ak820ctl.exe") {
            Ok(0) => {}
            Ok(n) => bail(
                &opts.log,
                &format!("not starting: {n} ak820ctl.exe process(es) are talking to the clock"),
                2,
            ),
            Err(e) => bail(&opts.log, &format!("not starting: cannot list processes ({e})"), 2),
        }
    }

    if let Err(e) = agent::run(opts) {
        std::process::exit(bail_code(&e));
    }
}

fn bail(log: &std::path::Path, message: &str, code: i32) -> ! {
    Log::at(log).line(message);
    std::process::exit(code)
}

fn bail_code(e: &str) -> i32 {
    let _ = e;
    1
}
