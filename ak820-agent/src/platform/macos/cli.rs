//! `ak820` on macOS: the read-only commands, over the IOKit transport.
//!
//! Phase 1 of the cross-platform plan. Every command reads the board and
//! **never writes to it**, as on Windows, and the output of each is the
//! Windows CLI's (and so the Python's and `ak820ctl`'s) byte for byte:
//! `ak820 info` against `ak820ctl info` is the phase gate.
//!
//! ⚠️ On macOS the Python agents open the interface with hidapi, which
//! **seizes** it; while one of them is mid-push these commands see
//! `kIOReturnExclusiveAccess`, reported as busy. Retry, or pause the agents.
//!
//! ```text
//! ak820 --version
//! ak820 list                 the board's HID services, from the IORegistry; opens nothing
//! ak820 info                 FC_INFO, exactly as `ak820ctl info` prints it
//! ak820 health [--stalls] [--rows] [--isr] [--json] [--raw]
//! ak820 lighting             the RGB values the board reports
//! ak820 selftest             budget guard, idle drain, and recovery on one open
//! ak820 clock [--raw] [--anyway]
//!                            the RTC, as `ak820ctl clock --read` prints it; refuses beside a clock owner
//! ak820 probe [--seconds N] [--applescript] [--dylib PATH]
//!                            what MediaRemote reports; touches no keyboard at all
//! ak820 install [--in-place] [--dylib PATH]
//!                            the daemon as a LaunchAgent, now-playing only (Phase 4a)
//! ak820 uninstall [--keep-bash-off]
//!                            remove it, and start the bash agent again
//! ak820 status               the three agents, the daemon's status file, its log
//! ```
//!
//! `install`, `uninstall` and `status` are the exception to "reads the board and
//! never writes it": they touch no board, but they do change LaunchAgents.

use std::process::ExitCode;

use super::device;
use crate::hid::exchange::REQUEST_TIMEOUT;
use crate::hid::{Drained, HidTransport};
use crate::proto::Channel;

pub fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    let result = match args.as_slice() {
        ["--version"] | ["version"] => {
            println!("{}", crate::version_line("ak820"));
            Ok(())
        }
        ["list"] => list(),
        ["info"] => info(),
        ["health", flags @ ..] => health(flags),
        ["lighting"] => lighting(),
        ["selftest"] => selftest(),
        ["clock", flags @ ..] => clock(flags),
        ["probe", flags @ ..] => probe(flags),
        ["install", flags @ ..] => super::install::install(flags),
        ["uninstall", flags @ ..] => super::install::uninstall(flags),
        ["status"] => super::install::status(),
        _ => {
            eprintln!("usage: ak820 --version | list | info | health [--stalls] [--rows] [--isr] [--json] [--raw] | lighting | selftest | clock [--raw] [--anyway] | probe [--seconds N] [--applescript] [--dylib PATH] | install [--in-place] [--dylib PATH] | uninstall [--keep-bash-off] | status");
            eprintln!("(macOS: read-only commands only so far; see plans/AK820-AGENT-CROSSPLATFORM-PLAN.md)");
            return ExitCode::from(2);
        }
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::FAILURE
        }
    }
}

fn list() -> Result<(), String> {
    let all = device::candidates().map_err(|e| e.to_string())?;
    let chosen = super::discovery::choose(&all);
    println!("{} HID service(s) with VID {:04X} PID {:04X} (nothing opened):", all.len(), crate::hid::VID, crate::hid::PID);
    for c in &all {
        let mark = if chosen == super::discovery::Choice::One(c.registry_id) { "*" } else { " " };
        let sizes = match c.check_sizes() {
            Ok(()) => "ok".to_string(),
            Err(_) => "n/a".to_string(),
        };
        println!(
            "{mark} {}  usage {:#06x}/{:#04x}  reports in {:?} out {:?} ({sizes})  location {}",
            c.name(),
            c.usage_page.unwrap_or(-1),
            c.usage.unwrap_or(-1),
            c.max_input,
            c.max_output,
            c.location_id.map(|l| format!("{l:#010x}")).unwrap_or_else(|| "-".into()),
        );
    }
    Ok(())
}

fn info() -> Result<(), String> {
    let dev = device::open_board().map_err(|e| e.to_string())?;
    let (info, drained) = crate::flash::read_info(&dev).map_err(|e| e.to_string())?;
    println!("flash jedec id : 0x{:06X}", info.jedec);
    println!("writable from  : 0x{:06X} (below this needs unlock, stock assets never)", info.asset_base);
    report_drained(&drained);
    Ok(())
}

/// `ak820health.py`'s pages, as the Windows CLI prints them.
fn health(flags: &[&str]) -> Result<(), String> {
    use crate::health::{self, Page1, Page2, Page3, Page4};

    let (mut stalls, mut rows, mut isr, mut json, mut raw) = (false, false, false, false, false);
    for flag in flags {
        match *flag {
            "--stalls" => stalls = true,
            "--rows" => rows = true,
            "--isr" => isr = true,
            "--json" => json = true,
            "--raw" => raw = true,
            other => return Err(format!("health: unknown flag {other}; the flags are --stalls --rows --isr --json --raw")),
        }
    }
    let mut drained = Vec::new();
    // One open per page, as the Python's `_txn` opens and closes per read.
    let mut page = |command: u8, n: u8| -> Result<[u8; 32], String> {
        let dev = device::open_board().map_err(|e| e.to_string())?;
        let reply = dev.request(Channel::Health, command, &[], REQUEST_TIMEOUT).map_err(|e| format!("page {n}: {e}"))?;
        drained.extend(reply.drained);
        if raw {
            let hex: Vec<String> = reply.report.iter().map(|b| format!("{b:02X}")).collect();
            println!("page{n} {}", hex.join(" "));
        }
        Ok(reply.report)
    };
    let p1 = Page1::decode(&page(health::GET, 1)?).map_err(|e| e.to_string())?;
    let p2 = if stalls || json { Some(Page2::decode(&page(health::GET2, 2)?).map_err(|e| e.to_string())?) } else { None };
    let p3 = if rows || (isr && json) { Some(Page3::decode(&page(health::GET3, 3)?).map_err(|e| e.to_string())?) } else { None };
    let p4 = if isr {
        let a = Page4::decode(&page(health::GET4, 4)?).map_err(|e| e.to_string())?;
        let t_a = std::time::Instant::now();
        std::thread::sleep(std::time::Duration::from_secs(2));
        let b = Page4::decode(&page(health::GET4, 4)?).map_err(|e| e.to_string())?;
        let rates = health::isr_rates(&a, &b, t_a.elapsed().as_secs_f64(), p3.as_ref().map_or(6, |p| p.matrix_rows as u32));
        Some((b, rates))
    } else {
        None
    };
    if json {
        println!("{}", health::render_json(&p1, p2.as_ref(), p3.as_ref(), p4.as_ref().map(|(b, r)| (b, r))));
    } else {
        print!("{}", health::render_page1(&p1));
        if let Some(p2) = &p2 {
            print!("{}", health::render_page2(p2));
        }
        if let Some(p3) = &p3 {
            print!("{}", health::render_page3(p3, p2.as_ref().map(|p| p.key_presses)));
        }
        if let Some((_, rates)) = &p4 {
            print!("{}", health::render_isr(rates));
        }
    }
    report_drained(&drained);
    Ok(())
}

fn lighting() -> Result<(), String> {
    use crate::via;
    let dev = device::open_board().map_err(|e| e.to_string())?;
    let l = via::read_lighting(&dev).map_err(|e| e.to_string())?;
    println!("effect     : {} ({})", l.effect, via::effect_name(l.effect));
    println!("hue        : {}", l.hue);
    println!("sat        : {}", l.sat);
    println!("brightness : {}", l.brightness);
    println!("speed      : {}", l.speed);
    Ok(())
}

/// The Windows `selftest`, over IOKit: a budget too short to transact must be
/// refused without transmitting; draining an idle queue must come back empty
/// promptly; and the same open must then give the same answer.
///
/// On IOKit a read is a wait on reports the run-loop callback has already
/// queued, so there is no pending kernel read to cancel as there is on
/// Windows. The idle step therefore proves the other thing that matters: an
/// empty queue is observed as `Empty` within its budget, rather than a wait
/// that never returns.
fn selftest() -> Result<(), String> {
    use crate::flash;
    use crate::hid::exchange::Queue;
    use crate::hid::Error as HidError;
    use std::time::{Duration, Instant};

    let dev = device::open_board().map_err(|e| e.to_string())?;
    println!("open           : {}", dev.name());

    let at = Instant::now();
    let (info, _) = flash::read_info(&dev).map_err(|e| e.to_string())?;
    println!("baseline       : jedec 0x{:06X} in {:.1} ms", info.jedec, at.elapsed().as_secs_f64() * 1000.0);

    let at = Instant::now();
    let outcome = dev.request(Channel::Flash, flash::INFO, &[], Duration::from_millis(1));
    let took = at.elapsed().as_secs_f64() * 1000.0;
    match outcome {
        Err(HidError::Timeout { .. }) | Err(HidError::Dirty { .. }) => {
            println!("budget guard   : refused in {took:.1} ms without transmitting")
        }
        Ok(_) => println!("budget guard   : answered in {took:.1} ms, inside the budget"),
        Err(e) => return Err(format!("unexpected failure on the short budget: {e}")),
    }

    let at = Instant::now();
    let (leftovers, queue) = dev.drain();
    let took = at.elapsed().as_secs_f64() * 1000.0;
    if took > 1500.0 {
        return Err(format!("draining an idle queue took {took:.1} ms"));
    }
    println!("idle drain     : returned in {took:.1} ms, queue {queue}, {} report(s) discarded", leftovers.len());
    if queue != Queue::Empty {
        return Err(format!("the idle drain never observed an empty queue (saw: {queue})"));
    }

    let at = Instant::now();
    let (again, drained) = flash::read_info(&dev).map_err(|e| format!("the open did not survive: {e}"))?;
    if again != info {
        return Err(format!("the answer changed: {info:?} then {again:?}"));
    }
    println!(
        "recovered      : same answer in {:.1} ms (budget {} ms)",
        at.elapsed().as_secs_f64() * 1000.0,
        REQUEST_TIMEOUT.as_millis()
    );
    report_drained(&drained);
    println!("ok");
    Ok(())
}

/// The board's clock, read once and printed as `ak820ctl clock --read` prints
/// it: Phase 2's read half on macOS. There is deliberately no set here.
fn clock(flags: &[&str]) -> Result<(), String> {
    use super::host::SystemHost;
    use crate::clock::{self, transaction};

    let mut raw = false;
    let mut anyway = false;
    for flag in flags {
        match *flag {
            "--raw" => raw = true,
            "--anyway" => anyway = true,
            other => return Err(format!("clock: unknown flag {other}; flags are --raw and --anyway")),
        }
    }
    clock_ownership(anyway)?;

    let dev = device::open_board().map_err(|e| e.to_string())?;
    let got = transaction::read_once(&dev, dev.outstanding(), &SystemHost, REQUEST_TIMEOUT).map_err(|e| e.to_string())?;
    if !got.board.understood() {
        return Err(format!(
            "RTC protocol version {} -- this tool speaks only version {} (ak820ctl clock --read would fall back to its legacy read)",
            got.board.proto,
            clock::PROTO_VERSION
        ));
    }
    print!("{}", clock::read_lines(&got.board, got.sample.map(|s| (s.offset_ms, got.rtt_ms))));
    if raw {
        let hex: Vec<String> = got.report.iter().map(|b| format!("{b:02X}")).collect();
        println!("raw {}", hex.join(" "));
        println!("host_mid_sod {:.17}", got.host_mid_sod);
        println!("rtt_ms {:.17}", got.rtt_ms);
    }
    report_drained(&got.drained);
    if got.sample.is_none() {
        return Err("the board's clock is not set (ak820ctl clock --read exits 1 here too)".into());
    }
    Ok(())
}

/// Refuse beside a clock owner (plan, Phase 2; review finding 10).
///
/// ⚠️ Fails CLOSED, as on Windows: a running owner refuses, and so does not
/// being able to tell. The hazard is not our read failing. It is the owner's
/// `ak820ctl` taking this read's reply as one of its own measurement samples:
/// a well-formed `RTC_GET_TIME` reply no header check can tell apart, which
/// becomes a wrong offset with a plausible round trip.
fn clock_ownership(anyway: bool) -> Result<(), String> {
    use super::launchd::{self, AGENT, TIMEKEEPER};
    let mut owners = Vec::new();
    let mut unknown = Vec::new();
    match launchd::print_checked(TIMEKEEPER) {
        // KeepAlive: loaded means syncing every 5 minutes, running or asleep between.
        Ok(Some(_)) => owners.push(format!(
            "{TIMEKEEPER} is loaded; its ak820ctl could take this read's reply as a measurement sample. \
             Pause it first with `launchctl bootout gui/$UID/{TIMEKEEPER}`; `hostagent/install-agents.sh --only timekeeper` restores it"
        )),
        Ok(None) => {}
        Err(e) => unknown.push(format!("whether {TIMEKEEPER} is loaded ({e})")),
    }
    match launchd::print_checked(AGENT) {
        Ok(Some(_)) => match std::fs::read_to_string(launchd::plist_path(AGENT)) {
            Ok(plist) if plist.contains("<string>--clock</string>") => owners.push(format!(
                "{AGENT} runs with --clock, so this read's reply could become one of its samples; `ak820 status` shows what it sees"
            )),
            Ok(_) => {}
            Err(e) => unknown.push(format!("whether {AGENT} owns the clock ({e})")),
        },
        Ok(None) => {}
        Err(e) => unknown.push(format!("whether {AGENT} is loaded ({e})")),
    }
    match super::process::running_named("ak820ctl") {
        0 => {}
        n => owners.push(format!("{n} ak820ctl process(es) are talking to the board right now")),
    }
    if owners.is_empty() && unknown.is_empty() {
        return Ok(());
    }
    let mut lines = owners;
    lines.extend(unknown.into_iter().map(|u| format!("could not establish {u}")));
    if anyway {
        for line in &lines {
            eprintln!("warning: {line} (--anyway given)");
        }
        return Ok(());
    }
    Err(format!("{}\nor pass --anyway to accept one possibly spoiled sync.", lines.join("\n")))
}

fn report_drained(drained: &[Drained]) {
    if drained.is_empty() {
        return;
    }
    eprintln!("note: discarded {} report(s) that answered another request:", drained.len());
    for d in drained {
        match d {
            Drained::Stale { header: h } => eprintln!("  queued before we asked: {:02X} {:02X} {:02X}", h[0], h[1], h[2]),
            Drained::StaleUnreadable(m) => eprintln!("  queued before we asked: {m:?}"),
            Drained::Foreign(m) => eprintln!("  arrived while waiting: {m:?}"),
        }
    }
}

/// Run the media source for a while and print what the daemon would publish.
///
/// Touches no keyboard. ⚠️ **Sends no Apple event unless `--applescript`**:
/// the canary and the fallback both stay off, because the first Apple event
/// from a new binary raises an Automation prompt on the desktop.
fn probe(flags: &[&str]) -> Result<(), String> {
    use super::media::{self, MediaRemoteSource};
    use crate::media::{MediaSource, Publisher};
    use std::time::{Duration, Instant};

    let mut seconds = 10u64;
    let mut applescript = false;
    let mut dylib = media::dylib_path();
    let mut it = flags.iter();
    while let Some(flag) = it.next() {
        match *flag {
            "--seconds" => {
                seconds = it
                    .next()
                    .and_then(|v| v.parse().ok())
                    .filter(|s| (1..=86_400).contains(s))
                    .ok_or("--seconds takes 1 to 86400")?
            }
            "--applescript" => applescript = true,
            "--dylib" => dylib = Some(it.next().ok_or("--dylib takes a path")?.into()),
            other => return Err(format!("unknown flag {other:?}")),
        }
    }
    let started = Instant::now();
    let stamp = move || format!("{:7.2}s", started.elapsed().as_secs_f64());
    println!(
        "helper: {}; AppleScript {}",
        dylib.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "(none)".into()),
        if applescript { "ON (canary and fallback)" } else { "off" }
    );
    let source = MediaRemoteSource::spawn(
        media::Options { interval: crate::media::INTERVAL, applescript, dylib },
        Box::new(move |line| println!("{:7.2}s {line}", started.elapsed().as_secs_f64())),
    )?;
    let mut last: Option<(String, bool, Option<String>)> = None;
    while started.elapsed() < Duration::from_secs(seconds) {
        std::thread::sleep(Duration::from_millis(500));
        let (snap, health) = source.latest();
        let shown = if snap.is_idle() { "idle -- the band would be cleared".to_string() } else { Publisher::describe(&snap) };
        let key = (shown.clone(), health.last_poll_ok, health.last_error.clone());
        if last.as_ref() != Some(&key) {
            println!(
                "{} {shown}{}  [route {:?}, polls {}, failures {}{}]",
                stamp(),
                if snap.playing { format!("  ({}s / {}s)", snap.pos_s, snap.dur_s) } else { String::new() },
                source.route(),
                health.polls,
                health.failures,
                health.last_error.map(|e| format!(", error: {e}")).unwrap_or_default()
            );
            last = Some(key);
        }
    }
    if let Some(n) = source.current() {
        let wall = super::media::applescript::wall_now();
        println!(
            "{} raw: bundle {:?}, rate {:?}, playing {}, elapsed {:?} as of {} (duration {:?})",
            stamp(),
            n.bundle.as_deref().unwrap_or(""),
            n.rate,
            n.playing,
            n.elapsed,
            n.elapsed_at.map(|at| format!("{:.2}s ago", wall - at)).unwrap_or_else(|| "never".into()),
            n.duration
        );
    }
    let (snap, health) = source.latest();
    println!(
        "{} end: {}  [polls {}, failures {}, fresh {}]",
        stamp(),
        if snap.is_idle() { "idle".to_string() } else { format!("{} ({}s / {}s)", Publisher::describe(&snap), snap.pos_s, snap.dur_s) },
        health.polls,
        health.failures,
        health.stale_for.map(|d| format!("{}s ago", d.as_secs())).unwrap_or_else(|| "never".into())
    );
    Ok(())
}
