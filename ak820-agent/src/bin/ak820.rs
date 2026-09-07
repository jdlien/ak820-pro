//! `ak820` -- the console-subsystem CLI.
//!
//! A console app on purpose, so exit codes and stdout survive the shell that
//! called it. Its sibling `ak820-agent.exe` is windows-subsystem for the
//! opposite reason: a daemon that cannot have a console cannot flash one.
//!
//! ⚠️ **Every command here is read-only.** Nothing writes to the board, and
//! nothing touches flash at all — provisioning stays in `ak820ctl`, which is
//! the only thing that erases.
//!
//! Their job is to make the layers underneath provable: `list` says what
//! discovery found without opening anything, `list --caps` says what those
//! interfaces are, `info` puts one correlated request/reply on the wire and
//! prints an answer that must equal `ak820ctl info`, `selftest` exercises the
//! budget guard and the cancellation path and then checks the handle still
//! works, `watch` narrates presence across an unplug, and `probe` reports what
//! SMTC sees without involving the keyboard at all.

use std::process::ExitCode;

use ak820_agent::flash;
use ak820_agent::hid::device::{self, Device, Queue};
use ak820_agent::hid::path;
use ak820_agent::hid::Drained;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let argv: Vec<&str> = args.iter().map(String::as_str).collect();

    let result = match argv.as_slice() {
        ["list"] => list(false),
        ["list", "--caps"] => list(true),
        ["info"] => info(),
        ["selftest"] => selftest(),
        ["probe"] => probe(),
        ["lighting"] => lighting(),
        ["health", flags @ ..] => health_cmd(flags),
        ["clock", flags @ ..] => clock(flags),
        ["install", flags @ ..] => install(flags),
        ["uninstall"] => uninstall(),
        ["status"] => status(),
        ["--version"] | ["version"] => {
            println!("{}", ak820_agent::version_line("ak820"));
            return ExitCode::SUCCESS;
        }
        ["watch"] => watch(20),
        ["watch", secs] => secs
            .parse()
            .map_err(|_| format!("not a number of seconds: {secs}"))
            .and_then(watch),
        ["--help"] | ["help"] | [] => {
            usage();
            return ExitCode::SUCCESS;
        }
        other => {
            eprintln!("ak820: unknown command {other:?}\n");
            usage();
            return ExitCode::FAILURE;
        }
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("ak820: {message}");
            ExitCode::FAILURE
        }
    }
}

fn usage() {
    println!(
        "ak820 -- AJAZZ AK820 Pro host tool -- reads the board, never writes it\n\
         \n\
         \x20 ak820 install --clock        register the daemon as a per-user task and start it: the\n\
         \x20   [--in-place]               track on the LCD, and with --clock the clock too (leave --clock\n\
         \x20                              off only to keep the repo's Python timekeeper; it replaces the\n\
         \x20                              Python now-playing task either way)\n\
         \x20 ak820 uninstall              stop and remove the daemon's task\n\
         \x20 ak820 status                 the tasks, and what the daemon last did\n\
         \x20 ak820 --version\n\
         \n\
         \x20 ak820 list           interfaces this board owns; opens nothing\n\
         \x20 ak820 list --caps    ... and what each one says once opened\n\
         \x20 ak820 info           flash id + writable base\n\
         \x20 ak820 selftest       exercise the cancellation path and recover\n\
         \x20 ak820 watch [secs]   narrate presence; unplug the cable to see it\n\
         \x20 ak820 probe          what SMTC sees; needs no keyboard\n\
         \x20 ak820 lighting       RGB values read back off the board\n\
         \x20 ak820 health         the firmware's health counters, as ak820health.py prints them\n\
         \x20   [--stalls] [--rows] [--isr] [--json] [--raw]\n\
         \x20 ak820 clock [--raw]  the RTC, as `ak820ctl clock --read` prints it;\n\
         \x20                      refuses while the Python timekeeper task runs (--anyway overrides)\n\
         \n\
         Provisioning stays in ak820ctl: it is the only thing that erases flash.\n\
         Setting the clock stays in the daemon: one owner, or the learner is wrong."
    );
}

/// What discovery found.
///
/// ⚠️ Without `--caps` this opens **nothing at all** -- it is the Configuration
/// Manager's own record of present interfaces, filtered by path. That is the
/// whole point: `hidapi`'s enumeration opens every HID device on the machine to
/// ask what it is, and doing that twice wedged this machine's UPS.
///
/// `--caps` opens the listed paths, and only those: they have already been
/// narrowed to this keyboard's own collections.
fn list(caps: bool) -> Result<(), String> {
    let present = device::present_count().map_err(|e| e.to_string())?;
    let found = device::interfaces(path::VID, path::PID).map_err(|e| e.to_string())?;
    println!(
        "{present} HID interfaces present, {} of them this board's{}",
        found.len(),
        if caps { "; opening only those" } else { "; opening none" }
    );
    if found.is_empty() {
        println!(
            "no interfaces for {:04X}:{:04X}",
            path::VID,
            path::PID
        );
        return Ok(());
    }
    for iface in &found {
        println!("{}", iface.path());
        if caps {
            match iface.identify() {
                Ok(id) => {
                    let verdict = match id.check(path::VID, path::PID) {
                        Ok(()) => "raw HID -- this is the one".to_string(),
                        Err(why) => why.to_string(),
                    };
                    println!(
                        "    {:04X}:{:04X} usage {:#06X}/{:#04X}  reports {}/{} in/out\n    {}",
                        id.vid, id.pid, id.usage_page, id.usage, id.input_len, id.output_len,
                        verdict
                    );
                }
                Err(e) => println!("    could not identify: {e}"),
            }
        }
    }
    Ok(())
}

/// One request, one correlated reply.
///
/// The output is byte-for-byte `ak820ctl info`, so the phase-0 gate is a diff
/// rather than a reading exercise.
fn info() -> Result<(), String> {
    contention_notice();
    let dev: Device = device::open_board().map_err(|e| e.to_string())?;
    let (info, drained) = flash::read_info(&dev).map_err(|e| e.to_string())?;
    println!("flash jedec id : 0x{:06X}", info.jedec);
    println!(
        "writable from  : 0x{:06X} (below this needs unlock, stock assets never)",
        info.asset_base
    );
    report_drained(&drained);
    Ok(())
}

/// One `RTC_GET_TIME`, decoded and printed exactly as `ak820ctl clock --read`
/// prints it, so the two can be compared on a live board.
///
/// **Read-only, and deliberately so.** The SET half of the transaction is
/// implemented in `clock::transaction` and proven against the fake wire; it is
/// not reachable from this CLI. Every command here is read-only, and a
/// one-shot SET from outside the daemon would also invalidate the daemon's
/// lead baseline — the plan routes such requests *through* the daemon, which
/// does not exist yet.
///
/// ⚠️ **The interference runs both ways, and the other way is the one that
/// matters.** Correlation cannot tell another process's GET reply from ours,
/// so with the Python timekeeper running, our reply can land in *its* read —
/// `ak820ctl`'s `xfer()` takes the first report that arrives — and become one
/// of its five measurement samples, paired with its timestamps, able to win its
/// min-RTT selection. That feeds its SET and both learners. A wrong number on
/// *our* screen is the lesser half; the first version of this comment said
/// only that, and the phase-2 audit's P1 corrected it. So this command refuses
/// while the `AK820Pro-timekeeper` task is `Running` (asked of the Task
/// Scheduler, which opens nothing), unless `--anyway` accepts one possibly
/// spoiled sync. Phase 4 replaces this with routing through the daemon.
///
/// `--raw` adds the 32 reply bytes, the host seconds-of-day at the transaction
/// midpoint and the round trip, which is what `scripts/clock_oracle.c decode`
/// takes to produce the C's rendering of the same reply — the phase-2 gate.
fn clock(flags: &[&str]) -> Result<(), String> {
    use ak820_agent::clock::{self, host::SystemHost, transaction};
    use ak820_agent::hid::device::REQUEST_TIMEOUT;

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
    let got = transaction::read_once(&dev, dev.outstanding(), &SystemHost, REQUEST_TIMEOUT)
        .map_err(|e| e.to_string())?;
    if !got.board.understood() {
        return Err(format!(
            "RTC protocol version {} -- this tool speaks only version {} (ak820ctl clock --read would fall back to its legacy read)",
            got.board.proto,
            clock::PROTO_VERSION
        ));
    }
    print!(
        "{}",
        clock::read_lines(&got.board, got.sample.map(|s| (s.offset_ms, got.rtt_ms)))
    );
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

/// `ak820health.py`, over the correlated transport: the health pages, printed
/// as the Python prints them (phase 5's gate is the byte-for-byte parity of
/// that rendering in `tests/health_parity.rs`).
///
/// Read-only — there is no `--reset`; `Fn`+`D` held resets the counters on
/// the board itself, and a reset from the host would be one more thing the
/// takeover comparison could not trust. `--raw` prints each page's 32 bytes
/// as `pageN <hex>`, the form `scripts/health_oracle.py` consumes.
fn health_cmd(flags: &[&str]) -> Result<(), String> {
    use ak820_agent::health::{self, Page1, Page2, Page3, Page4};
    use ak820_agent::hid::device::REQUEST_TIMEOUT;
    use ak820_agent::proto::Channel;

    let (mut stalls, mut rows, mut isr, mut json, mut raw) = (false, false, false, false, false);
    for flag in flags {
        match *flag {
            "--stalls" => stalls = true,
            "--rows" => rows = true,
            "--isr" => isr = true,
            "--json" => json = true,
            "--raw" => raw = true,
            other => {
                return Err(format!(
                    "health: unknown flag {other}; the flags are --stalls --rows --isr --json --raw"
                ))
            }
        }
    }
    contention_notice();

    let mut drained = Vec::new();
    // One open per page, as the Python's `_txn` opens and closes per read:
    // the agents need the interface too, and the `--isr` pair is two seconds
    // apart by design.
    let mut page = |command: u8, n: u8| -> Result<[u8; 32], String> {
        let dev = device::open_board().map_err(|e| e.to_string())?;
        let reply = dev
            .request(Channel::Health, command, &[], REQUEST_TIMEOUT)
            .map_err(|e| format!("page {n}: {e}"))?;
        drained.extend(reply.drained);
        if raw {
            let hex: Vec<String> = reply.report.iter().map(|b| format!("{b:02X}")).collect();
            println!("page{n} {}", hex.join(" "));
        }
        Ok(reply.report)
    };

    let p1 = Page1::decode(&page(health::GET, 1)?).map_err(|e| e.to_string())?;
    let p2 = if stalls || json {
        Some(Page2::decode(&page(health::GET2, 2)?).map_err(|e| e.to_string())?)
    } else {
        None
    };
    let p3 = if rows || (isr && json) {
        Some(Page3::decode(&page(health::GET3, 3)?).map_err(|e| e.to_string())?)
    } else {
        None
    };
    let p4 = if isr {
        let a = Page4::decode(&page(health::GET4, 4)?).map_err(|e| e.to_string())?;
        let t_a = std::time::Instant::now();
        std::thread::sleep(std::time::Duration::from_secs(2));
        let b = Page4::decode(&page(health::GET4, 4)?).map_err(|e| e.to_string())?;
        let wall = t_a.elapsed().as_secs_f64();
        let matrix_rows = p3.as_ref().map_or(6, |p| p.matrix_rows as u32);
        let rates = health::isr_rates(&a, &b, wall, matrix_rows);
        Some((b, rates))
    } else {
        None
    };

    if json {
        println!(
            "{}",
            health::render_json(&p1, p2.as_ref(), p3.as_ref(), p4.as_ref().map(|(b, r)| (b, r)))
        );
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

/// Refuse a clock read beside a running Python timekeeper, unless told to
/// accept the consequence. See [`clock`].
fn clock_ownership(anyway: bool) -> Result<(), String> {
    use ak820_agent::task;
    // ⚠️ Fails CLOSED: a clock owner that is running refuses, and so does not
    // being able to tell. The phase-3a/4a audit's finding 2 found the daemon
    // check failing open on a Task Scheduler error — the one situation in
    // which "I could not check" and "nobody owns it" must not be confused,
    // because the cost of being wrong is a silently corrupted sync.
    let mut owners = Vec::new();
    let mut unknown = Vec::new();
    // The daemon, when it owns the clock, is the same hazard as the Python
    // timekeeper: its transaction would take this read's reply as its own.
    match task::state(task::FOLDER, task::AGENT) {
        Ok(Some(task::State::Running)) => match task::agent_owns_clock() {
            Ok(true) => owners.push(format!(
                "{} is running with --clock, so this read's reply could be taken as one of its own \
                 measurement samples. Use `ak820 status` for what it sees, or stop it first \
                 (Stop-ScheduledTask -TaskPath '{}\\' -TaskName {})",
                task::AGENT,
                task::FOLDER,
                task::AGENT
            )),
            Ok(false) => {}
            Err(e) => unknown.push(format!("whether {} owns the clock ({e})", task::AGENT)),
        },
        Ok(_) => {}
        Err(e) => unknown.push(format!("whether {} is running ({e})", task::AGENT)),
    }
    match task::timekeeper_running() {
        Ok(Some(true)) => owners.push(format!(
            "the {} task is running. Its ak820ctl takes the first report that arrives, so this \
             read's reply can become one of its five measurement samples and corrupt that sync \
             and what it learns. Stop it first \
             (Stop-ScheduledTask -TaskPath '{}\\' -TaskName {})",
            task::TIMEKEEPER,
            task::FOLDER,
            task::TIMEKEEPER
        )),
        Ok(_) => {}
        Err(e) => unknown.push(format!("whether the {} task is running ({e})", task::TIMEKEEPER)),
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
    Err(format!(
        "{}\nor pass --anyway to accept one possibly spoiled sync.",
        lines.join("\n")
    ))
}

/// One line on stderr when the Python timekeeper is running, for the commands
/// that talk to the board on other channels.
///
/// Milder than [`clock_ownership`] on purpose. A flash or lighting reply of
/// ours taken by `ak820ctl` as a clock reply fails its protocol-version check
/// — or, for `FC_INFO`, reads as protocol 0 and provokes one legacy
/// whole-second set. One spoiled sync, self-correcting five minutes later,
/// and the phase-0 measurements were deliberately taken under exactly this
/// contention. Worth saying; not worth refusing.
fn contention_notice() {
    use ak820_agent::task;
    if let Ok(Some(true)) = task::timekeeper_running() {
        eprintln!(
            "note: the {} task is running; a reply of ours landing in its read can spoil one of \
             its syncs",
            task::TIMEKEEPER
        );
    }
}

/// Install the daemon as a per-user Scheduled Task and start it — the "just
/// run it" path of the Releases zip.
///
/// Copies both binaries to `%LOCALAPPDATA%\ak820pro\bin\` so the zip can be
/// deleted afterwards (`--in-place` registers the running location instead,
/// for development), stops and unregisters the Python now-playing task —
/// which the daemon replaces — and leaves the Python timekeeper alone: the
/// clock stays with it until the Rust port passes phase 3's gates. Then it
/// registers `AK820Pro-agent` from the same task definition the PowerShell
/// installer used (`task::task_xml`) and starts it, so nobody has to log out
/// and back in.
///
/// Writes to the Task Scheduler and the profile directory; never to the board.
fn install(flags: &[&str]) -> Result<(), String> {
    use ak820_agent::{agent, instance, task};
    use std::time::Duration;

    let mut in_place = false;
    let mut clock = false;
    for flag in flags {
        match *flag {
            "--in-place" => in_place = true,
            "--clock" => clock = true,
            other => {
                return Err(format!(
                    "install: unknown flag {other}; the flags are --in-place and --clock"
                ))
            }
        }
    }

    let here = std::env::current_exe().map_err(|e| format!("locating ak820.exe: {e}"))?;
    let here_dir = here
        .parent()
        .ok_or("ak820.exe has no parent directory")?
        .to_path_buf();
    let daemon_src = here_dir.join("ak820-agent.exe");
    if !daemon_src.is_file() {
        return Err(format!(
            "{} must sit beside ak820.exe (both come in the same zip)",
            daemon_src.display()
        ));
    }
    let dir = agent::default_dir();
    std::fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;

    // Everything that can fail without consequence happens BEFORE any owner
    // is stopped: the copies are staged beside their destinations, so a full
    // disk or a locked file leaves the running daemon exactly as it was (the
    // phase-3a/4a audit's finding 3). A reinstall from the installed copy —
    // `%LOCALAPPDATA%\ak820pro\bin\ak820 install` — stages nothing.
    let (bin_dir, daemon, staged) = if in_place {
        (here_dir.clone(), daemon_src.clone(), Vec::new())
    } else {
        let bin = dir.join("bin");
        std::fs::create_dir_all(&bin).map_err(|e| format!("{}: {e}", bin.display()))?;
        let mut staged = Vec::new();
        for (src, name) in [(&daemon_src, "ak820-agent.exe"), (&here, "ak820.exe")] {
            let dst = bin.join(name);
            if same_file(src, &dst) {
                continue;
            }
            let tmp = bin.join(format!("{name}.new"));
            std::fs::copy(src, &tmp).map_err(|e| format!("copying to {}: {e}", tmp.display()))?;
            staged.push((tmp, dst));
        }
        (bin.clone(), bin.join("ak820-agent.exe"), staged)
    };

    // From here on an owner may be stopped, so every failure must put one
    // back: the previous registration is restarted, and said so.
    let previous = task::info(task::FOLDER, task::AGENT)?;
    let restore = |why: String| -> String {
        if previous.is_none() {
            return why;
        }
        match task::start(task::FOLDER, task::AGENT) {
            Ok(()) => format!("{why}; the previous daemon was started again"),
            Err(e) => format!("{why}; and starting the previous daemon again failed too: {e}"),
        }
    };

    // A running daemon holds its exe open; stop it before replacing it — and
    // wait until it has actually gone, which the scheduler and its mutex
    // both tell us.
    if previous.is_some() {
        task::stop(task::FOLDER, task::AGENT)?;
        task::wait_stopped(task::FOLDER, task::AGENT, Duration::from_secs(10))?;
        wait_released(instance::AGENT, Duration::from_secs(10))?;
    }
    for (tmp, dst) in &staged {
        if let Err(e) = std::fs::rename(tmp, dst) {
            return Err(restore(format!("replacing {}: {e}", dst.display())));
        }
    }
    if !staged.is_empty() {
        println!("copied ak820-agent.exe and ak820.exe to {}", bin_dir.display());
    }
    if !in_place {
        // Not on PATH, and `%LOCALAPPDATA%` is cmd's spelling: PowerShell
        // reads it as a module name. Say the form that works there.
        println!(
            "the installed CLI is {}\\ak820.exe; from PowerShell: & \"$env:LOCALAPPDATA\\ak820pro\\bin\\ak820.exe\" status",
            bin_dir.display()
        );
    }

    // The Python now-playing agent is what the daemon replaces. The Python
    // timekeeper is not, unless --clock says so.
    if let Err(e) = retire_python(clock, &dir) {
        return Err(restore(e));
    }

    let user = format!("{}\\{}", env_var("USERDOMAIN")?, env_var("USERNAME")?);
    let log = dir.join("ak820-agent.log");
    let arguments = format!(
        "--log \"{}\"{}",
        log.display(),
        if clock { " --clock" } else { "" }
    );
    let xml = task::task_xml(&task::Definition {
        description: task::AGENT_DESCRIPTION,
        user: &user,
        command: &daemon.display().to_string(),
        arguments: &arguments,
        working_directory: &bin_dir.display().to_string(),
    });
    if let Err(e) = task::register(task::AGENT, &xml) {
        return Err(restore(e));
    }
    println!(
        "registered {}\\{} to run {} at logon, as {user}",
        task::FOLDER,
        task::AGENT,
        daemon.display()
    );
    // The status file is the daemon's own account of itself, and the previous
    // daemon's file stays there until the new one writes — after its first
    // pass, which with --clock includes a sync a few seconds in. So wait for
    // a `started` stamp that is not the old one; what prints below is then
    // this daemon's, not its predecessor's (the owner's first `--clock` run
    // printed the old daemon's file, "clock python timekeeper" and all).
    let status_path = dir.join("ak820-agent.status");
    let previous = started_stamp(&status_path);
    task::start(task::FOLDER, task::AGENT)
        .map_err(|e| format!("{e}; it is registered and will start at the next logon"))?;
    println!("started it now; log: {}", log.display());
    let until = std::time::Instant::now() + Duration::from_secs(20);
    while started_stamp(&status_path) == previous && std::time::Instant::now() < until {
        std::thread::sleep(Duration::from_millis(250));
    }
    println!();
    if started_stamp(&status_path) == previous {
        println!(
            "(the daemon has not written its status file yet; what follows is the previous one's -- \
             `ak820 status` in a moment)\n"
        );
    }
    status()
}

/// The `started` stamp in a status file, if there is one.
fn started_stamp(path: &std::path::Path) -> Option<String> {
    ak820_agent::status::read(path)?
        .into_iter()
        .find(|(k, _)| k == "started")
        .map(|(_, v)| v)
}

/// Stop and remove the Python tasks the daemon replaces, and not until each
/// has actually gone.
///
/// ⚠️ Stopping a task ends its process asynchronously. The first live install
/// started the daemon while the Python agent still held the now-playing
/// mutex, and the daemon refused to start exactly as designed. And the
/// timekeeper is worse: its `ak820ctl` child is a separate process that
/// finishes on its own — by **setting the clock** — after `pythonw.exe` is
/// gone. So the scheduler is asked, the mutex is claimed, and for the
/// timekeeper the process list is watched for `ak820ctl.exe` (the phase-3a/4a
/// audit's finding 1). Nothing is deleted until its process is gone: a
/// failure here leaves the task registered and stopped, and says so.
fn retire_python(clock: bool, dir: &std::path::Path) -> Result<(), String> {
    use ak820_agent::{instance, process, task};
    use std::time::Duration;

    if task::info(task::FOLDER, task::NOWPLAYING)?.is_some() {
        task::stop(task::FOLDER, task::NOWPLAYING)?;
        task::wait_stopped(task::FOLDER, task::NOWPLAYING, Duration::from_secs(10))
            .map_err(|e| format!("{e}; it is still registered"))?;
        wait_released(instance::NOWPLAYING, Duration::from_secs(10))?;
        task::delete(task::FOLDER, task::NOWPLAYING)?;
        println!(
            "stopped and removed the Python task {}: the daemon replaces it (its log stays in {})",
            task::NOWPLAYING,
            dir.display()
        );
    } else {
        // not registered, but a hand-started copy would hold the name
        wait_released(instance::NOWPLAYING, Duration::from_secs(10))?;
    }

    // ⚠️ The clock. Exactly one process may run clock transactions; two
    // silently corrupt each other's learners. `--clock` moves ownership to
    // the daemon by removing the Python timekeeper's task; without it, the
    // Python timekeeper is left exactly as it is.
    let timekeeper_registered = task::info(task::FOLDER, task::TIMEKEEPER)?.is_some();
    if clock {
        if timekeeper_registered {
            task::stop(task::FOLDER, task::TIMEKEEPER)?;
            task::wait_stopped(task::FOLDER, task::TIMEKEEPER, Duration::from_secs(10))
                .map_err(|e| format!("{e}; it is still registered and still owns the clock"))?;
            process::wait_gone("ak820ctl.exe", Duration::from_secs(15)).map_err(|e| {
                format!("{e}; the {} task is stopped but still registered", task::TIMEKEEPER)
            })?;
            task::delete(task::FOLDER, task::TIMEKEEPER)?;
            println!(
                "stopped and removed the Python task {}: the daemon takes the clock (--clock)",
                task::TIMEKEEPER
            );
        } else if process::running("ak820ctl.exe")? > 0 {
            return Err(
                "an ak820ctl.exe is running: something else is talking to the clock right now"
                    .into(),
            );
        }
        println!(
            "the daemon syncs the clock (--clock); `ak820 status` shows each sync. To give the\n\
             \x20   clock back to the repo's Python timekeeper, IN THIS ORDER: `ak820 install`\n\
             \x20   (without --clock) first, so the daemon stops writing the clock, THEN\n\
             \x20   `powershell -File hostagent\\install-agents-windows.ps1`. The other order would\n\
             \x20   run two clock writers at once, and that installer refuses it."
        );
    } else if timekeeper_registered {
        println!(
            "left the Python task {} alone: the clock stays with it (pass --clock to move it)",
            task::TIMEKEEPER
        );
    } else {
        println!(
            "⚠️  no Python timekeeper is registered and --clock was not given: nothing will sync\n\
             \x20   the clock. Pass --clock, or reinstall the Python timekeeper."
        );
    }
    Ok(())
}

/// Do two paths name one existing file? `false` when either does not exist.
fn same_file(a: &std::path::Path, b: &std::path::Path) -> bool {
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(x), Ok(y)) => x == y,
        _ => false,
    }
}

fn env_var(name: &str) -> Result<String, String> {
    std::env::var(name).map_err(|_| format!("{name} is not set in the environment"))
}

/// Wait until nobody holds a named mutex — i.e. until the process that did
/// has exited — by claiming it and letting it go. A stopped Scheduled Task's
/// process takes a moment to die; a copy over its exe, or a daemon start that
/// needs its name, has to wait for that moment.
fn wait_released(name: &str, timeout: std::time::Duration) -> Result<(), String> {
    use ak820_agent::instance::Instance;
    let until = std::time::Instant::now() + timeout;
    loop {
        match Instance::claim(&[name]) {
            Ok(held) => {
                drop(held);
                return Ok(());
            }
            Err(_) if std::time::Instant::now() < until => {
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
            Err(e) => {
                return Err(format!(
                    "{e}; it did not exit within {} s of being stopped",
                    timeout.as_secs()
                ))
            }
        }
    }
}

/// Stop and unregister the daemon's task. Binaries and logs stay.
fn uninstall() -> Result<(), String> {
    use ak820_agent::{agent, task};
    if task::info(task::FOLDER, task::AGENT)?.is_none() {
        println!("{}\\{} is not registered", task::FOLDER, task::AGENT);
    } else {
        let owned_clock = task::agent_owns_clock()?;
        task::stop(task::FOLDER, task::AGENT)?;
        task::delete(task::FOLDER, task::AGENT)?;
        println!("stopped and removed {}\\{}", task::FOLDER, task::AGENT);
        if owned_clock {
            println!(
                "⚠️  it owned the clock; nothing syncs it now. Reinstall the Python timekeeper below, or `ak820 install --clock` again."
            );
        }
    }
    println!("binaries and logs left in {}", agent::default_dir().display());
    println!(
        "to put the Python now-playing agent back: powershell -ExecutionPolicy Bypass -File hostagent\\install-agents-windows.ps1"
    );
    Ok(())
}

/// The three tasks' states, then what the daemon last did, then its log's
/// tail. "Running" alone is liveness, not health — the status file is what
/// says whether anything has happened lately.
fn status() -> Result<(), String> {
    use ak820_agent::{agent, status, task};

    for name in [task::AGENT, task::TIMEKEEPER, task::NOWPLAYING] {
        match task::info(task::FOLDER, name)? {
            None => println!("{name:<22} not registered"),
            Some(i) => {
                let state = match i.state {
                    task::State::Running => "Running".to_string(),
                    task::State::Idle(1) => "Disabled".to_string(),
                    task::State::Idle(2) => "Queued".to_string(),
                    task::State::Idle(3) => "Ready".to_string(),
                    task::State::Idle(s) => format!("state {s}"),
                };
                println!(
                    "{name:<22} {state:<9} last run {}  result 0x{:x}",
                    i.last_run.as_deref().unwrap_or("never"),
                    i.last_result
                );
            }
        }
    }

    let dir = agent::default_dir();
    let status_path = dir.join("ak820-agent.status");
    println!();
    match status::read(&status_path) {
        None => println!("no status file yet at {}", status_path.display()),
        Some(pairs) => {
            for (k, v) in pairs {
                println!("{k:<18} {v}");
            }
        }
    }

    let log = dir.join("ak820-agent.log");
    if let Ok(text) = std::fs::read_to_string(&log) {
        println!("\nlast lines of {}:", log.display());
        let lines: Vec<&str> = text.lines().collect();
        for line in lines.iter().rev().take(6).rev() {
            println!("  {line}");
        }
    }
    Ok(())
}

/// Ask the board the same question twice a second and narrate what happens.
///
/// A diagnostic, **not** the presence state machine the plan calls for -- it
/// reopens on any failure rather than distinguishing absent from busy from
/// unresponsive. What it is for is watching a transition happen: unplug the
/// cable while this runs and the sequence of outcomes is the evidence for how
/// a vanishing device actually presents itself, which is the one thing about
/// the transport that cannot be established by reasoning about it.
///
/// It deliberately holds the handle across requests, which the daemon will not
/// do. That is the point: it is the only way to see what an open handle does
/// when the device underneath it goes away.
fn watch(seconds: u64) -> Result<(), String> {
    use std::time::{Duration, Instant};

    contention_notice();
    let until = Instant::now() + Duration::from_secs(seconds);
    let mut held: Option<Device> = None;
    let mut last = String::new();
    let mut repeats = 0usize;

    while Instant::now() < until {
        let line = match held.as_ref() {
            None => match device::open_board() {
                Ok(dev) => {
                    let line = format!("open   {}", dev.path());
                    held = Some(dev);
                    line
                }
                Err(e) => format!("closed {e}"),
            },
            Some(dev) => match flash::read_info(dev) {
                Ok((info, drained)) => {
                    let note = if drained.is_empty() {
                        String::new()
                    } else {
                        format!("  (+{} drained: {drained:?})", drained.len())
                    };
                    format!("ok     jedec 0x{:06X}{note}", info.jedec)
                }
                Err(e) => {
                    held = None; // whatever happened, this handle is finished
                    format!("lost   {e}")
                }
            },
        };

        // Collapse repeats so a transition is legible instead of buried in a
        // hundred identical lines.
        if line == last {
            repeats += 1;
        } else {
            if repeats > 0 {
                println!("       ... x{}", repeats + 1);
            }
            println!("{line}");
            last = line;
            repeats = 0;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    if repeats > 0 {
        println!("       ... x{}", repeats + 1);
    }
    Ok(())
}

/// Every media session Windows can see, and what we would make of them.
///
/// **Touches no keyboard at all** — it is the answer to "why doesn't <app> show
/// up on the LCD?", and the answer is usually that the app registers no SMTC
/// session, which is an app-side plug-in question rather than anything this
/// program can fix.
///
/// It also prints the chosen session and the exact bytes that would go on the
/// wire, so the ranking rules and the ASCII folding can be checked against a
/// real desktop rather than only against fixtures.
fn probe() -> Result<(), String> {
    use ak820_agent::smtc;

    let sessions = smtc::worker::poll_once().map_err(|e| format!("SMTC unavailable: {e}"))?;
    if sessions.is_empty() {
        println!("No SMTC sessions at all. Start playback in an app and re-run.");
        println!("An app that never appears here registers no session, which is an");
        println!("app-side question rather than something this agent can reach.");
        return Ok(());
    }

    println!("{} SMTC session(s):\n", sessions.len());
    for s in &sessions {
        let rank = match smtc::rank(s) {
            Some((0, _)) => "candidate (playing)",
            Some(_) => "candidate (paused)",
            None => "not a candidate",
        };
        println!("  app      : {}{}", s.app_id, if s.is_current { "   <- current session" } else { "" });
        println!("  status   : {:?}  -- {rank}", s.status);
        println!("  title    : {:?}", s.title);
        println!("  artist   : {:?}", s.artist);
        match &s.timeline {
            Some(t) => println!(
                "  timeline : {}s / {}s, updated {}",
                (t.position_ticks - t.start_ticks) / smtc::TICKS_PER_SEC,
                (t.end_ticks - t.start_ticks) / smtc::TICKS_PER_SEC,
                match t.age_s {
                    Some(a) => format!("{a:.1}s ago"),
                    None => "never".into(),
                }
            ),
            None => println!("  timeline : (none reported)"),
        }
        println!();
    }

    let snap = smtc::snapshot(&sessions);
    if snap.is_idle() {
        println!("chosen   : none -- the band would be cleared");
        return Ok(());
    }
    println!("chosen   : {:?} {:?}", snap.icon, snap.title);
    println!("           {} / {} s", snap.pos_s, snap.dur_s);
    println!("\nwhat would go on the wire:");
    for (command, body) in smtc::reports(&snap) {
        let frame = ak820_agent::proto::frame(ak820_agent::proto::Channel::Text, command, &body);
        let hex: Vec<String> = frame[..12].iter().map(|b| format!("{b:02X}")).collect();
        let text: String = body
            .iter()
            .skip(2)
            .map(|&b| if (0x20..0x7F).contains(&b) { b as char } else { '.' })
            .collect();
        println!("  {} ...   {text:?}", hex.join(" "));
    }
    Ok(())
}

/// What the board says its lighting actually is.
///
/// ⚠️ Read-only, and worth having because VIA's display cannot be trusted after
/// a desync -- see `plans/BACKLOG.md`. The board executes the commands it is
/// sent; VIA only loses the confirmations, so its UI can disagree with reality.
///
/// The comparison against `keyboard.json` is the actionable part: `flash.sh`
/// does **not** restore RGB state, so every flash reverts the LEDs to
/// `rgb_matrix.default`. If the board differs from that default, the next flash
/// silently changes the lighting.
fn lighting() -> Result<(), String> {
    use ak820_agent::via;

    contention_notice();
    let dev = device::open_board().map_err(|e| e.to_string())?;
    let l = via::read_lighting(&dev).map_err(|e| e.to_string())?;

    println!("effect     : {} ({})", l.effect, via::effect_name(l.effect));
    println!("hue        : {}", l.hue);
    println!("sat        : {}", l.sat);
    println!("brightness : {}", l.brightness);
    println!("speed      : {}", l.speed);

    // keyboard.json's rgb_matrix.default, as of 2026-09-06.
    const DEFAULT: (u8, &str, u8, u8, u8, u8) = (2, "alphas_mods", 240, 215, 86, 127);
    let (d_effect, d_name, d_hue, d_sat, d_val, d_speed) = DEFAULT;
    let same = l.effect == d_effect
        && l.hue == d_hue
        && l.sat == d_sat
        && l.brightness == d_val
        && l.speed == d_speed;
    println!();
    if same {
        println!("matches keyboard.json's rgb_matrix.default -- a flash would not change it.");
    } else {
        println!(
            "⚠️  keyboard.json's default is effect {d_effect} ({d_name}), hue {d_hue}, sat {d_sat}, val {d_val}, speed {d_speed}."
        );
        println!("   They differ, so the next flash would revert the lighting to that default.");
        println!("   Either set the default to match, or note these values before flashing.");
    }
    Ok(())
}

/// Prove the timeout path cancels cleanly and leaves the handle usable.
///
/// The board answers everything it is asked -- `raw_hid_receive` replies on
/// every branch, including the one for a command it does not understand -- so a
/// natural no-reply needs an unplugged cable or wireless mode, neither of which
/// a program can arrange for itself. What it *can* arrange is a budget shorter
/// than the round trip, and that reaches the same code: a `ReadFile` genuinely
/// pending when `CancelIoEx` fires.
///
/// ⚠️ The third step is the one that matters. A botched cancellation does not
/// announce itself at the timeout; it announces itself later, as a handle that
/// no longer works or a buffer the kernel wrote into after we dropped it. So
/// the test is not "did it time out" but "does the **next** request still get
/// the right answer".
fn selftest() -> Result<(), String> {
    use ak820_agent::hid::device::REQUEST_TIMEOUT;
    use ak820_agent::hid::Error as HidError;
    use ak820_agent::proto::Channel;
    use std::time::{Duration, Instant};

    contention_notice();
    let dev = device::open_board().map_err(|e| e.to_string())?;
    println!("open           : {}", dev.path());

    let at = Instant::now();
    let (info, _) = flash::read_info(&dev).map_err(|e| e.to_string())?;
    println!(
        "baseline       : jedec 0x{:06X} in {:.1} ms",
        info.jedec,
        at.elapsed().as_secs_f64() * 1000.0
    );

    // ⚠️ Finding 7 of the phase-0 audit: an operation whose budget has expired
    // must not still change the board. A millisecond cannot cover even the
    // pre-drain, so this must come back as a refusal — and crucially it must
    // refuse *before* transmitting, not after.
    let at = Instant::now();
    let outcome = dev.request(Channel::Flash, flash::INFO, &[], Duration::from_millis(1));
    let took = at.elapsed().as_secs_f64() * 1000.0;
    match outcome {
        Err(HidError::Timeout { .. }) | Err(HidError::Dirty { .. }) => {
            println!("budget guard   : refused in {took:.1} ms without transmitting")
        }
        // Not a failure of the guard — the board simply answered inside the
        // millisecond, which is the "completed before the cancel landed" branch
        // and must be reported as the answer it is rather than as a timeout.
        Ok(_) => println!("budget guard   : answered in {took:.1} ms, inside the budget"),
        Err(e) => return Err(format!("unexpected failure on the short budget: {e}")),
    }

    // The other half of the three-way outcome, and the one that would hurt if
    // it were wrong. Nothing is queued here, so nothing but the cancellation
    // can complete the read -- if `CancelIoEx` were a no-op against a pending
    // HID read, this would never return, and a daemon would hang on shutdown
    // with a silent board rather than time out.
    let at = Instant::now();
    let (leftovers, queue) = dev.drain();
    let took = at.elapsed().as_secs_f64() * 1000.0;
    if took > 1500.0 {
        return Err(format!(
            "a cancelled read on an idle queue took {took:.1} ms -- cancellation is not landing"
        ));
    }
    // ⚠️ The queue state is the point, not the timing. `Empty` is the only
    // value that proves a read was genuinely aborted rather than satisfied by
    // a report that happened to be waiting -- finding 9 of the phase-0 audit
    // said the old version of this step could not tell those apart.
    println!(
        "idle cancel    : returned in {took:.1} ms, queue {queue}, {} report(s) discarded",
        leftovers.len()
    );
    if queue != Queue::Empty {
        return Err(format!(
            "the idle-cancel step never observed an empty queue (saw: {queue}), so it did not              exercise the abort branch it claims to"
        ));
    }

    let at = Instant::now();
    let (again, drained) = flash::read_info(&dev).map_err(|e| {
        format!("the handle did not survive cancellation: {e}")
    })?;
    if again != info {
        return Err(format!(
            "the answer changed after a cancelled transfer: {info:?} then {again:?}"
        ));
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

/// Say so when reports had to be discarded to reach the answer.
///
/// On stderr and unconditional rather than behind a flag, because this is the
/// measured hazard becoming visible: reports arriving on our handle that
/// answered somebody else. Silence is the normal case and the interesting
/// signal is any noise at all, so there is nothing to opt into.
fn report_drained(drained: &[Drained]) {
    if drained.is_empty() {
        return;
    }
    eprintln!(
        "note: discarded {} report(s) that answered another request:",
        drained.len()
    );
    for d in drained {
        match d {
            Drained::Stale { header: h } => eprintln!(
                "  queued before we asked: {:02X} {:02X} {:02X}",
                h[0], h[1], h[2]
            ),
            Drained::StaleUnreadable(m) => eprintln!("  queued before we asked: {m:?}"),
            Drained::Foreign(m) => eprintln!("  arrived while waiting: {m:?}"),
        }
    }
}
