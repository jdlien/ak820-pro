//! `ak820` -- the console-subsystem CLI.
//!
//! A console app on purpose, so exit codes and stdout survive the shell that
//! called it. Its sibling `ak820-agent.exe` is windows-subsystem for the
//! opposite reason: a daemon that cannot have a console cannot flash one.
//!
//! Phase 0 is four commands, and their whole job is to make the transport
//! provable: `list` says what discovery found without opening anything,
//! `list --caps` says what those interfaces are, `info` puts one correlated
//! request/reply on the wire and prints an answer that must equal
//! `ak820ctl info`, and `selftest` exercises the cancellation path and then
//! checks the handle still works.

use std::process::ExitCode;

use ak820_agent::flash;
use ak820_agent::hid::device::{self, Device};
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
        "ak820 -- AJAZZ AK820 Pro host tool (phase 0)\n\
         \n\
         \x20 ak820 list           interfaces this board owns; opens nothing\n\
         \x20 ak820 list --caps    ... and what each one says once opened\n\
         \x20 ak820 info           flash id + writable base\n\
         \x20 ak820 selftest       exercise the cancellation path and recover\n\
         \n\
         Provisioning stays in ak820ctl. Nothing here erases or writes flash."
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

    let dev = device::open_board().map_err(|e| e.to_string())?;
    println!("open           : {}", dev.path());

    let at = Instant::now();
    let (info, _) = flash::read_info(&dev).map_err(|e| e.to_string())?;
    println!(
        "baseline       : jedec 0x{:06X} in {:.1} ms",
        info.jedec,
        at.elapsed().as_secs_f64() * 1000.0
    );

    // One millisecond is under the round trip on this board, so the read is
    // still pending when the wait expires. A fast answer is not a failure --
    // it is the "completed between the wait expiring and the cancel landing"
    // branch, and flattening that into a timeout is the bug the branch exists
    // to avoid.
    let at = Instant::now();
    let outcome = dev.request(Channel::Flash, flash::INFO, &[], Duration::from_millis(1));
    let took = at.elapsed().as_secs_f64() * 1000.0;
    match outcome {
        Err(HidError::Timeout { drained }) => println!(
            "cancelled      : timed out in {took:.1} ms, {} report(s) drained",
            drained.len()
        ),
        Ok(_) => println!("cancelled      : answered in {took:.1} ms before the cancel landed"),
        Err(e) => return Err(format!("unexpected failure on the short budget: {e}")),
    }

    // The other half of the three-way outcome, and the one that would hurt if
    // it were wrong. Nothing is queued here, so nothing but the cancellation
    // can complete the read -- if `CancelIoEx` were a no-op against a pending
    // HID read, this would never return, and a daemon would hang on shutdown
    // with a silent board rather than time out.
    let at = Instant::now();
    let leftovers = dev.drain();
    let took = at.elapsed().as_secs_f64() * 1000.0;
    if took > 250.0 {
        return Err(format!(
            "a cancelled read on an idle queue took {took:.1} ms -- cancellation is not landing"
        ));
    }
    println!(
        "idle cancel    : returned in {took:.1} ms, {} report(s) queued",
        leftovers.len()
    );

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
            Drained::Stale { channel, command } => eprintln!(
                "  queued before we asked: channel {channel:#04X} command {command:#04X}"
            ),
            Drained::StaleUnreadable(m) => eprintln!("  queued before we asked: {m:?}"),
            Drained::Foreign(m) => eprintln!("  arrived while waiting: {m:?}"),
        }
    }
}
