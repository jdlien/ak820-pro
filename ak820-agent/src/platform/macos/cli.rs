//! `ak820` on macOS: the read-only commands, over the IOKit transport.
//!
//! Phase 1 of the cross-platform plan. Every command reads the board and
//! **never writes to it**, as on Windows, and the output of each is the
//! Windows CLI's (and so the Python's and `ak820ctl`'s) byte for byte:
//! `ak820 info` against `ak820ctl info` is the phase gate.
//!
//! ⚠️ On macOS hidapi clients (`ak820ctl`, the Python tools and the older
//! Python/bash agents) **seize** the interface; while one of them holds it
//! these commands see `kIOReturnExclusiveAccess`, reported as busy. Retry, or
//! stop that client.
//!
//! ```text
//! ak820 --version
//! ak820 list                 the board's HID services, from the IORegistry; opens nothing
//! ak820 info                 FC_INFO, exactly as `ak820ctl info` prints it
//! ak820 health [--crash] [--stalls] [--rows] [--isr] [--sched [--window SECS]] [--json] [--raw]
//! ak820 lighting             the RGB values the board reports
//! ak820 selftest             budget guard, idle drain, and recovery on one open
//! ak820 clock [--raw] [--anyway]
//!                            the RTC, as `ak820ctl clock --read` prints it; refuses beside a clock owner
//! ak820 probe [--seconds N] [--applescript] [--dylib PATH]
//!                            what MediaRemote reports; touches no keyboard at all
//! ak820 install [--in-place] [--clock] [--radio] [--lockchan] [--dylib PATH]
//!                            the daemon as a LaunchAgent; --clock retires the Python timekeeper (4b);
//!                            --radio carries now-playing over the 2.4G dongle off USB
//! ak820 uninstall [--keep-bash-off] [--keep-timekeeper-off]
//!                            remove it, and start the bash agent (and timekeeper) again
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
        ["lockchan", "check"] => lockchan_check(),
        ["lockchan", "send", artist, title] => lockchan_send(artist, title, 1),
        ["lockchan", "send", "--repeat", n, artist, title] => match n.parse::<u32>() {
            Ok(n) if (1..=500).contains(&n) => lockchan_send(artist, title, n),
            _ => Err("--repeat takes 1-500".into()),
        },
        ["lockchan", "clear"] => lockchan_send("", "", 1),
        ["lockchan", "anchor", n] => match n.parse::<u32>() {
            Ok(n) if (1..=200).contains(&n) => lockchan_anchor(n),
            _ => Err("lockchan anchor takes 1-200 frames".into()),
        },
        _ => {
            eprintln!("usage: ak820 --version | list | info | health [--crash] [--stalls] [--rows] [--isr] [--sched [--window SECS]] [--json] [--raw] | lighting | selftest | clock [--raw] [--anyway] | probe [--seconds N] [--applescript] [--dylib PATH] | install [--in-place] [--clock] [--radio] [--lockchan] [--dylib PATH] | uninstall [--keep-bash-off] [--keep-timekeeper-off] | status | lockchan check | lockchan send [--repeat N] ARTIST TITLE | lockchan clear | lockchan anchor N");
            eprintln!("(install, uninstall and status change LaunchAgents and touch no board; lockchan send and clear write the board's LED report over BLE, a development check; every other command only reads the board)");
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
    use crate::health::{self, Page1, Page2, Page3, Page4, Page7};

    let mut crash_requested = false;
    let (mut stalls, mut rows, mut isr, mut json, mut raw) = (false, false, false, false, false);
    let (mut sched, mut window) = (false, None::<f64>);
    let mut it = flags.iter();
    while let Some(flag) = it.next() {
        match *flag {
            "--crash" => crash_requested = true,
            "--stalls" => stalls = true,
            "--rows" => rows = true,
            "--isr" => isr = true,
            "--sched" => sched = true,
            "--window" => window = Some(health::window_secs(it.next().copied())?),
            w if w.starts_with("--window=") => window = Some(health::window_secs(Some(&w["--window=".len()..]))?),
            "--json" => json = true,
            "--raw" => raw = true,
            other => return Err(format!("health: unknown flag {other}; the flags are --crash --stalls --rows --isr --sched --window SECS --json --raw")),
        }
    }
    if window.is_some() && !sched {
        return Err("health: --window goes with --sched".to_string());
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
    let crash = if p1.version >= health::CrashRecord::NEEDS {
        match health::CrashRecord::decode(&page(health::GET5, 5)?) {
            Ok(c) => Some(c),
            // A newer record format: say so and keep the counters, unless the
            // record is what was asked for (crash-hunt review, finding 6).
            Err(health::Error::RecordFormat(f)) if !crash_requested => {
                eprintln!("note: watchdog record format {f} is newer than this ak820 -- update it");
                None
            }
            Err(e) => return Err(e.to_string()),
        }
    } else if crash_requested {
        return Err(format!("watchdog breadcrumbs need firmware health v6; board has v{}", p1.version));
    } else { None };
    // Page 6 on v7 boards, unasked, as page 5 is on v6: its build token is
    // what symbolizes a fault PC in the record above.
    let p6 = if p1.version >= health::Page6::NEEDS {
        Some(health::Page6::decode(&page(health::GET6, 6)?).map_err(|e| e.to_string())?)
    } else { None };
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
    // Page 7 after page 4, as the Python reads it: once, or with `--window` a
    // pair that far apart, the window's figures from the deltas.
    let p7 = if sched {
        let a = Page7::decode(&page(health::GET7, 7)?).map_err(|e| e.to_string())?;
        match window {
            Some(secs) => {
                let t_a = std::time::Instant::now();
                std::thread::sleep(std::time::Duration::from_secs_f64(secs));
                let b = Page7::decode(&page(health::GET7, 7)?).map_err(|e| e.to_string())?;
                let w = health::sched_window(&a, &b, t_a.elapsed().as_secs_f64());
                Some((b, Some(w)))
            }
            None => Some((a, None)),
        }
    } else {
        None
    };
    if json {
        println!("{}", health::render_json_with_vitals(health::render_json_with_crash(health::render_json_with_sched(health::render_json(&p1, p2.as_ref(), p3.as_ref(), p4.as_ref().map(|(b, r)| (b, r))), p7.as_ref().map(|(p, w)| (p, w.as_ref()))), crash.as_ref()), p6.as_ref()));
    } else {
        print!("{}", health::render_page1(&p1));
        if let Some(p) = &crash { print!("{}", health::render_crash(p)); }
        if let Some(p) = &p6 { print!("{}", health::render_page6(p)); }
        if let Some(p2) = &p2 {
            print!("{}", health::render_page2(p2));
        }
        if let Some(p3) = &p3 {
            print!("{}", health::render_page3(p3, p2.as_ref().map(|p| p.key_presses)));
        }
        if let Some((_, rates)) = &p4 {
            print!("{}", health::render_isr(rates));
        }
        if let Some((p, w)) = &p7 {
            print!("{}", health::render_sched(p, w.as_ref()));
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
        Ok(0) => {}
        Ok(n) => owners.push(format!("{n} ak820ctl process(es) are talking to the board right now")),
        Err(e) => unknown.push(format!("whether an ak820ctl is running ({e})")),
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

/// What the lock-LED channel would use, read only: Input Monitoring, the BLE
/// keyboard's listing (nothing opened), the session, Caps, the idle time.
fn lockchan_check() -> Result<(), String> {
    use super::lock_lights as ll;
    println!("input monitoring   {}", ll::input_monitoring().map(|()| "granted".to_string()).unwrap_or_else(|e| e));
    let listed = super::discovery::list_ble()?;
    for (c, _) in &listed {
        println!(
            "ble service        {:#x}: usage {:?}:{:?}, {:?}, {:?}",
            c.registry_id, c.usage_page, c.usage, c.transport, c.product
        );
    }
    let cands: Vec<_> = listed.iter().map(|(c, _)| c.clone()).collect();
    println!("chosen             {:?}", ll::choose(&cands));
    println!("session active     {}", ll::session_active());
    println!("caps lock          {:?}", ll::caps());
    println!("idle               {:?}", ll::idle());
    Ok(())
}

/// Where a lock-LED frame's anchor lands on the board, in time: the Mac's
/// latency constant for the clock frame (type 4; plans/LOCK-LED-CHANNEL-PLAN.md,
/// "The wireless clock"). scripts/win_lockchan_anchor_jitter.py's method,
/// through the daemon's own writer: for each of `n` short frames (type 9,
/// which the board counts and rejects), the instant its anchor write
/// completed, taken where run_late hands it to a type 4's build, against the
/// board's anchor_ms (devhook op 10, over USB). The board's timer is mapped
/// onto this process's clock through the tightest of 40 op-10 round trips at
/// the start and at the end (the offset and the drift). Needs a dev build,
/// the slider on BT, the cable in for the readback, and the daemon quiet:
/// its raw-HID media pushes drop a frame being assembled (R4-3), so stop it
/// first (`kill -STOP`, then `-CONT`).
fn lockchan_anchor(n: u32) -> Result<(), String> {
    use crate::lockchan::frame::{self, Late, Line};
    use std::cell::Cell;
    use std::time::{Duration, Instant};

    const DEVHOOK: u8 = 0x76;
    const OP_FRAMES: u8 = 10;
    let _owner = super::radio_lock::try_take_lockchan()?
        .ok_or("another sender holds the lock-LED channel (the daemon, or another ak820 lockchan)")?;
    let dev = device::open_board().map_err(|e| e.to_string())?;
    // One op-10 read: the host's midpoint of the exchange, the board's ms in
    // it, the round trip, and the reply.
    let read = || -> Result<(Instant, u32, Duration, [u8; 32]), String> {
        let sent = Cell::new(None);
        let r = dev
            .request_at(Channel::Health, DEVHOOK, &[OP_FRAMES], REQUEST_TIMEOUT, |t| sent.set(Some(t)))
            .map_err(|e| format!("devhook op 10: {e}"))?;
        let recv = Instant::now();
        let rep = r.report;
        if rep[0] == 0xFF || rep[3] != OP_FRAMES {
            return Err(format!("devhook op 10 not answered as itself ({:02X?}): a dev build?", &rep[..4]));
        }
        let rtt = recv - sent.get().unwrap_or(recv);
        Ok((recv - rtt / 2, u32::from_le_bytes([rep[25], rep[26], rep[27], rep[28]]), rtt, rep))
    };
    let best = || -> Result<(Instant, u32, Duration), String> {
        let mut b: Option<(Instant, u32, Duration)> = None;
        for _ in 0..40 {
            let (t, ms, rtt, _) = read()?;
            if b.is_none_or(|x| rtt < x.2) {
                b = Some((t, ms, rtt));
            }
        }
        Ok(b.expect("40 reads"))
    };
    let le32 = |b: &[u8]| u32::from_le_bytes([b[0], b[1], b[2], b[3]]);

    let mut lights = super::lock_lights::BleLights::open()?
        .ok_or("the board's BLE keyboard is not listed (paired, connected, the slider on BT?)")?;
    // Locked, the user's locks are unknown and every frame would come back
    // Unknown without a write (R4-1): say so once instead.
    if !super::lock_lights::session_active() {
        return Err("the screen is locked (or this session is not on the console): no frame can go".into());
    }
    let mut line = Line::default();
    let first = best()?;
    let mut samples: Vec<(Instant, u32)> = Vec::new();
    for i in 0..n {
        let seq = (i & 0xFF) as u8;
        let before = le32(&read()?.3[4..8]);
        let anchor = Cell::new(None);
        let out = frame::run_late(&mut lights, &Wall, &Never, &mut line, || {
            Some(Late {
                kind: 9,
                seq,
                build: Box::new(|at| {
                    anchor.set(Some(at));
                    Some(vec![seq, 1, 2, 3, 4])
                }),
            })
        });
        if out == frame::Outcome::Poisoned {
            std::mem::forget(lights);
            std::mem::forget(_owner);
            return Err("a write did not retire: the channel is poisoned".into());
        }
        std::thread::sleep(Duration::from_millis(600));
        let rep = read()?.3;
        let (frames, anchor_ms) = (le32(&rep[4..8]), le32(&rep[17..21]));
        match anchor.get() {
            Some(at) if out == frame::Outcome::Sent && frames == before.wrapping_add(1) && rep[15] == seq => {
                samples.push((at, anchor_ms));
            }
            _ => println!("{i:3}: {out:?}, not committed (frames {before} -> {frames}, seq {})", rep[15]),
        }
    }
    let last = best()?;

    // Host instants onto board ms, linear between the two tight pairs.
    let rate = last.1.wrapping_sub(first.1) as f64 / last.0.duration_since(first.0).as_secs_f64();
    let lat: Vec<f64> = samples
        .iter()
        .map(|&(at, a)| a.wrapping_sub(first.1) as i32 as f64 - at.duration_since(first.0).as_secs_f64() * rate)
        .collect();
    println!("frames {n}, committed {}, board ms per host s {rate:.3}", lat.len());
    println!("sync rtt ms        {:.2} at the start, {:.2} at the end", first.2.as_secs_f64() * 1e3, last.2.as_secs_f64() * 1e3);
    if lat.is_empty() {
        return Err("no frame committed".into());
    }
    let mean = lat.iter().sum::<f64>() / lat.len() as f64;
    let sd = (lat.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / lat.len() as f64).sqrt();
    let mut sorted = lat.clone();
    sorted.sort_by(f64::total_cmp);
    let pct = |p: f64| sorted[((sorted.len() - 1) as f64 * p).round() as usize];
    println!(
        "board anchor minus host completion, ms: mean {mean:.1}, sd {sd:.1}, min {:.1}, p10 {:.1}, median {:.1}, p90 {:.1}, max {:.1}",
        sorted[0],
        pct(0.1),
        pct(0.5),
        pct(0.9),
        sorted[sorted.len() - 1]
    );
    let each: Vec<String> = lat.iter().map(|x| format!("{x:.1}")).collect();
    println!("each               {}", each.join(" "));
    Ok(())
}

/// The wall clock, for the development senders below (the daemon's executor
/// brings its own).
struct Wall;
impl crate::lockchan::frame::Time for Wall {
    fn now(&self) -> std::time::Instant {
        std::time::Instant::now()
    }
    fn sleep_until(&self, t: std::time::Instant) -> bool {
        std::thread::sleep(t.saturating_duration_since(std::time::Instant::now()));
        true
    }
    fn sleep_through(&self, t: std::time::Instant) {
        std::thread::sleep(t.saturating_duration_since(std::time::Instant::now()));
    }
}

/// Nothing aborts a development frame.
struct Never;
impl crate::lockchan::frame::Control for Never {
    fn abort(&self) -> Option<crate::lockchan::frame::Abort> {
        None
    }
}

/// Lock-LED frames over BLE through the daemon's own executor: the
/// development check of the Mac's route. Empty artist and title send CLEAR.
/// Takes the channel's owner lock for the whole run, so it never interleaves
/// with another sender, and a daemon beside it stays off the channel (the
/// interference study, 10-20: `--repeat N` frames, each titled with its
/// number, one line each and a tally).
fn lockchan_send(artist: &str, title: &str, repeat: u32) -> Result<(), String> {
    use crate::lockchan::frame::{self, Line, Payload};
    use std::time::Instant;

    let _owner = super::radio_lock::try_take_lockchan()?
        .ok_or("another sender holds the lock-LED channel (the daemon, or another ak820 lockchan)")?;
    let snapshot = crate::smtc::Snapshot {
        artist: artist.into(),
        title: title.into(),
        icon: if title.is_empty() { crate::text::Icon::None } else { crate::text::Icon::Play },
        ..Default::default()
    };
    let mut lights = super::lock_lights::BleLights::open()?
        .ok_or("the board's BLE keyboard is not listed (paired, connected, the slider on BT?)")?;
    let mut line = Line::default();
    let mut sent = 0;
    for i in 1..repeat {
        let snap = crate::smtc::Snapshot { title: format!("{title} {i}"), ..snapshot.clone() };
        let (kind, bytes) = crate::lockchan::content(&snap);
        lights.slowest = std::time::Duration::ZERO;
        lights.over_100ms = 0;
        let t0 = Instant::now();
        let out = frame::run(&mut lights, &Wall, &Never, &mut line, || Some(Payload { kind, seq: i as u8, bytes: bytes.clone() }));
        println!(
            "{i:3}: {out:?}, {} writes in {:.2} s, slowest {} ms, {} over 100 ms",
            line.writes,
            t0.elapsed().as_secs_f64(),
            lights.slowest.as_millis(),
            lights.over_100ms
        );
        line.writes = 0;
        if out == frame::Outcome::Poisoned {
            std::mem::forget(lights);
            std::mem::forget(_owner);
            return Err("a write did not retire: the channel is poisoned".into());
        }
        sent += (out == frame::Outcome::Sent) as u32;
    }
    if repeat > 1 {
        println!("{sent} of {} sent before the last", repeat - 1);
    }
    let (kind, bytes) = crate::lockchan::content(&snapshot);
    lights.slowest = std::time::Duration::ZERO;
    lights.over_100ms = 0;
    let t0 = Instant::now();
    let out = frame::run(&mut lights, &Wall, &Never, &mut line, || Some(Payload { kind, seq: 0, bytes: bytes.clone() }));
    println!(
        "{}: type {kind}, {} payload bytes: {out:?}, {} writes in {:.2} s, slowest {} ms, {} over 100 ms{}",
        lights.name,
        bytes.len(),
        line.writes,
        t0.elapsed().as_secs_f64(),
        lights.slowest.as_millis(),
        lights.over_100ms,
        if line.restore_pending { " (restore pending)" } else { "" }
    );
    // A stuck write keeps the owner lock and the device for the life of the
    // process, as the sender does (R3-3); the process ends just after.
    if out == frame::Outcome::Poisoned {
        std::mem::forget(lights);
        std::mem::forget(_owner);
        return Err("a write did not retire: the channel is poisoned".into());
    }
    // "Sent" is every write accepted, not the board's commit, which nothing
    // acknowledges; anything else is a failure to a script (codex, P2 3).
    match (out, line.restore_pending) {
        (frame::Outcome::Sent, false) => Ok(()),
        (_, true) => Err("the lights' restore is pending: the user's locks may be wrong on the board".into()),
        (other, false) => Err(format!("the frame did not go: {other:?}")),
    }
}
