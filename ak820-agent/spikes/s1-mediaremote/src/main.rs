//! `s1` — run the MediaRemote helper under the supervisor and narrate it.
//!
//!     s1 --dylib PATH [--seconds N]
//!     s1 --exec PROGRAM [ARGS...] [--silence-limit S] [--restart-min S] [--healthy-run S] [--seconds N]
//!
//! Prints one line per event, prefixed with seconds since start, plus a
//! `health` line every 5 s with the failure clock. `--exec` runs any program
//! as the helper, which is how the supervision rules are tested without
//! MediaRemote.

use std::path::PathBuf;
use std::sync::mpsc;
use std::time::{Duration, Instant};

use s1::helper::{Config, Event, Supervisor};
use s1::message::Message;

fn secs(v: Option<String>, name: &str) -> Duration {
    let v = v.unwrap_or_else(|| panic!("{name} needs a value"));
    Duration::from_secs_f64(
        v.parse()
            .unwrap_or_else(|_| panic!("{name}: not a number: {v}")),
    )
}

fn main() {
    // `s1 players`: the process-table check the canary uses. No spawn, no
    // Apple event, so it can never raise an Automation prompt.
    if std::env::args().nth(1).as_deref() == Some("players") {
        let started = Instant::now();
        let running = s1::players::running();
        println!(
            "running players: {running:?} ({:.2} ms, no spawn)",
            started.elapsed().as_secs_f64() * 1e3
        );
        return;
    }
    let mut args = std::env::args().skip(1);
    let mut config: Option<Config> = None;
    let mut run_for: Option<Duration> = None;
    let mut overrides: Vec<(String, Duration)> = Vec::new();
    let mut health_every = Duration::from_secs(5);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--dylib" => {
                config = Some(Config::mediaremote(&PathBuf::from(
                    args.next().expect("--dylib PATH"),
                )))
            }
            "--exec" => {
                let program = args.next().expect("--exec PROGRAM");
                let mut c = Config::defaults();
                c.program = program.into();
                // Everything up to the next --flag belongs to the program.
                let rest: Vec<String> = args.by_ref().collect();
                let split = rest
                    .iter()
                    .position(|x| x.starts_with("--"))
                    .unwrap_or(rest.len());
                c.args = rest[..split].iter().map(Into::into).collect();
                let mut tail = rest[split..].iter().cloned();
                while let Some(flag) = tail.next() {
                    if flag == "--seconds" {
                        run_for = Some(secs(tail.next(), "--seconds"));
                    } else {
                        overrides.push((flag.clone(), secs(tail.next(), &flag)));
                    }
                }
                config = Some(c);
                break;
            }
            "--seconds" => run_for = Some(secs(args.next(), "--seconds")),
            flag => overrides.push((flag.to_owned(), secs(args.next(), flag))),
        }
    }
    let mut config = config.expect("usage: s1 --dylib PATH | --exec PROGRAM [ARGS...]");
    for (flag, v) in overrides {
        match flag.as_str() {
            "--silence-limit" => config.silence_limit = v,
            "--restart-min" => config.restart_min = v,
            "--restart-max" => config.restart_max = v,
            "--healthy-run" => config.healthy_run = v,
            "--check-every" => config.check_every = v,
            "--settle" => config.settle = v,
            "--health-every" => health_every = v,
            other => panic!("unknown flag {other}"),
        }
    }

    let start = Instant::now();
    let (tx, rx) = mpsc::channel();
    let sup = Supervisor::start(config, tx);
    let mut next_health = health_every;
    loop {
        let t = start.elapsed();
        if run_for.is_some_and(|limit| t >= limit) {
            break;
        }
        if t >= next_health {
            println!(
                "{:8.3} health failed={} silent_for={:.1}s",
                t.as_secs_f64(),
                sup.failed(),
                sup.silent_for().as_secs_f64()
            );
            next_health += health_every;
        }
        let Ok(event) = rx.recv_timeout(health_every.min(Duration::from_millis(200))) else {
            continue;
        };
        let t = start.elapsed().as_secs_f64();
        match event {
            Event::Message(Message::Now(n)) => println!(
                "{t:8.3} now bundle={} playing={} stale={} title={:?} artist={:?} elapsed={:?} duration={:?} rate={:?} elapsedAt={:?}",
                n.bundle.as_deref().unwrap_or("-"), n.playing, n.stale, n.title.unwrap_or_default(),
                n.artist.unwrap_or_default(), n.elapsed, n.duration, n.rate, n.elapsed_at
            ),
            other => println!("{t:8.3} {other:?}"),
        }
    }
    sup.stop();
    // The supervisor's last words (the helper's exit) arrive during stop().
    for event in rx.try_iter() {
        println!("{:8.3} {event:?}", start.elapsed().as_secs_f64());
    }
    println!("{:8.3} stopped", start.elapsed().as_secs_f64());
}
