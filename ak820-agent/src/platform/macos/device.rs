#![allow(non_upper_case_globals)]
//! The macOS transport: IOKit, one device object per board arrival, opened per
//! interaction.
//!
//! From spike S2 (`ak820-agent/spikes/s2-iokit`, gate met 2026-09-16), with
//! its measured results carried as design:
//!
//! - **Opened per interaction, never for the process lifetime.** A held open
//!   would lock `ak820health.py` and the other hidapi diagnostics out.
//! - ⚠️ **But the object is long-lived.** Registering an input-report callback
//!   leaks one page (~3.9 KB) per `IOHIDDevice` object, whatever the API
//!   variant, unregistration or buffer size: ~110 MB a day at one object per
//!   interaction. So one object is created per board arrival, its callbacks
//!   registered and scheduled once, and only `IOHIDDeviceOpen`/`Close` happen
//!   per interaction (flat over 9,000 cycles).
//! - A hidapi peer that seizes the device **wins**: a fresh open fails at once
//!   with `kIOReturnExclusiveAccess`, and while we are open our writes fail
//!   within milliseconds with the same code. Both are reported as
//!   [`Error::Open`], which `agent::Watch` reads as **busy**, because that is
//!   what they are — normal and recoverable on macOS, not a fault.
//! - Two non-seizing clients **do** see each other's reports, as on Windows,
//!   so the correlation in `hid::exchange` is as necessary here as there.
//!
//! "Stuck", which the plan asked to be defined for IOKit: a write whose
//! completion callback never arrives — not even with `kIOReturnTimeout` —
//! inside its own timeout plus a grace. The object is then abandoned: its
//! callback context is leaked rather than freed, because a late callback could
//! still name it, and the next open creates a fresh object.

use std::collections::VecDeque;
use std::os::raw::c_void;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use super::discovery::{self, Choice};
use super::runloop::RunLoop;
use super::sys::*;
use crate::hid::exchange::{Outstanding, Sent, Wire};
use crate::hid::{Error, HidTransport, OsError};
use crate::proto::{REPORT_LEN, WIRE_LEN};

/// How long past a write's own timeout its completion may take before the
/// object is declared stuck.
const WRITE_GRACE: Duration = Duration::from_millis(500);

/// IOKit writes each input report into a buffer we lend it for as long as the
/// callback is registered — the object's lifetime here.
const INPUT_BUFFER: usize = 256;

/// Consecutive interactions that wrote and heard nothing before the object is
/// replaced. See [`Deafness`].
const SILENT_LIMIT: u32 = 3;

/// At most this many retirements in any hour (4b audit, F2). Each one leaks a
/// page, and a board answering one request in four would otherwise retire an
/// object every ~12 s, about 30 MB a day. Past the cap the object is kept, and
/// a deaf one simply stays deaf until the hour rolls over.
const RETIREMENTS_PER_HOUR: usize = 6;

/// Whether one more retirement fits in the last hour, recording it if so.
fn retirement_allowed(log: &mut std::collections::VecDeque<Instant>, now: Instant) -> bool {
    while log.front().is_some_and(|t| now.saturating_duration_since(*t) >= Duration::from_secs(3600)) {
        log.pop_front();
    }
    if log.len() >= RETIREMENTS_PER_HOUR {
        return false;
    }
    log.push_back(now);
    true
}

static RETIREMENTS: Mutex<std::collections::VecDeque<Instant>> = Mutex::new(std::collections::VecDeque::new());

/// The cap message is said once per capped spell, not once per interaction:
/// a deaf object past the cap is dropped every 3 s.
static CAP_SAID: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// ⚠️ **An `IOHIDDevice` object can go deaf for good** (measured live
/// 2026-09-16, 20:55:07). After 5 minutes of clean exchanges, every write
/// still completed through the run loop and not one input report arrived
/// for 8 minutes, while the Python timekeeper's `ak820ctl` synced normally and
/// `ak820 info` from a second process got its reply at once. A restart cured
/// it. The likeliest mechanism, not proven: IOKit signals the input queue only
/// on empty-to-non-empty, so a report landing as the object closes can leave
/// it non-empty and never signalled again.
///
/// So interactions that wrote and heard nothing are counted, and after
/// [`SILENT_LIMIT`] in a row the object is retired and the next open makes a
/// fresh one. **Only an object that has heard at least once is retired**: a
/// board that is truly hung makes a fresh object silent too, and replacing
/// objects without bound would leak one page each (S2's measured
/// registration leak) for as long as the hang lasts. One stolen reply (the
/// timekeeper's seize) is a single silent interaction and resets on the next.
#[derive(Debug, Default)]
struct Deafness {
    silent: u32,
    ever_heard: bool,
}

impl Deafness {
    /// Record one interaction. True means retire the object.
    fn interaction(&mut self, wrote: bool, heard: bool) -> bool {
        if heard {
            self.silent = 0;
            self.ever_heard = true;
            return false;
        }
        if !wrote {
            return false;
        }
        self.silent += 1;
        self.ever_heard && self.silent >= SILENT_LIMIT
    }
}

#[derive(Default)]
struct Inbox {
    reports: VecDeque<Vec<u8>>,
    removed: bool,
    /// (sequence, result) of the last completed write.
    write_done: Option<(u64, IOReturn)>,
    write_seq: u64,
}

struct Shared {
    inbox: Mutex<Inbox>,
    ready: Condvar,
}

unsafe extern "C" fn on_report(
    context: *mut c_void,
    _result: IOReturn,
    _sender: *mut c_void,
    _report_type: IOHIDReportType,
    report_id: u32,
    report: *mut u8,
    report_length: CFIndex,
    _time_stamp: u64,
) {
    let shared = &*(context as *const Shared);
    let payload = std::slice::from_raw_parts(report, report_length.max(0) as usize);
    // Report id first, as Windows hands it back: `proto::normalize_input`
    // strips it, and handles a stray non-zero id as a mismatch.
    let mut data = Vec::with_capacity(1 + payload.len());
    data.push(report_id as u8);
    data.extend_from_slice(payload);
    let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
    inbox.reports.push_back(data);
    shared.ready.notify_all();
}

unsafe extern "C" fn on_removed(context: *mut c_void, _result: IOReturn, _sender: *mut c_void) {
    let shared = &*(context as *const Shared);
    shared.inbox.lock().unwrap_or_else(|e| e.into_inner()).removed = true;
    shared.ready.notify_all();
}

unsafe extern "C" fn on_written(
    context: *mut c_void,
    result: IOReturn,
    _sender: *mut c_void,
    _report_type: IOHIDReportType,
    _report_id: u32,
    _report: *mut u8,
    _report_length: CFIndex,
) {
    let shared = &*(context as *const Shared);
    let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
    let seq = inbox.write_seq;
    inbox.write_done = Some((seq, result));
    shared.ready.notify_all();
}

/// One `IOHIDDevice` object, for as long as the board stays at this registry
/// entry.
struct Board {
    registry_id: u64,
    name: String,
    dev: IOHIDDeviceRef,
    ctx: *const Shared,
    buffer: *mut [u8; INPUT_BUFFER],
    abandoned: std::sync::atomic::AtomicBool,
    open: std::sync::atomic::AtomicBool,
    deafness: Mutex<Deafness>,
}

// The raw pointers are dereferenced only under the inbox mutex, or on the
// run-loop thread, or by IOKit calls documented as usable from any thread.
unsafe impl Send for Board {}
unsafe impl Sync for Board {}

struct SendPtr(*mut c_void);
unsafe impl Send for SendPtr {}

impl Board {
    fn create(service: &super::cf::Io, registry_id: u64, name: String) -> Result<Board, Error> {
        unsafe {
            let dev = IOHIDDeviceCreate(kCFAllocatorDefault, service.0);
            if dev.is_null() {
                return Err(Error::Absent); // the service went away between listing and here
            }
            let ctx = Arc::into_raw(Arc::new(Shared { inbox: Mutex::new(Inbox::default()), ready: Condvar::new() }));
            let buffer = Box::into_raw(Box::new([0u8; INPUT_BUFFER]));
            IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                dev,
                buffer as *mut u8,
                INPUT_BUFFER as CFIndex,
                Some(on_report),
                ctx as *mut c_void,
            );
            IOHIDDeviceRegisterRemovalCallback(dev, Some(on_removed), ctx as *mut c_void);
            let d = SendPtr(dev);
            RunLoop::get().run(move |rl| {
                let d = d;
                IOHIDDeviceScheduleWithRunLoop(d.0, rl, kCFRunLoopDefaultMode);
            });
            Ok(Board {
                registry_id,
                name,
                dev,
                ctx,
                buffer,
                abandoned: false.into(),
                open: false.into(),
                deafness: Mutex::new(Deafness::default()),
            })
        }
    }

    fn shared(&self) -> &Shared {
        unsafe { &*self.ctx }
    }

    fn usable(&self) -> bool {
        use std::sync::atomic::Ordering::Relaxed;
        !self.abandoned.load(Relaxed) && !self.shared().inbox.lock().unwrap_or_else(|e| e.into_inner()).removed
    }
}

impl Drop for Board {
    fn drop(&mut self) {
        use std::sync::atomic::Ordering::Relaxed;
        unsafe {
            let d = SendPtr(self.dev);
            // Unregister and unschedule ON the loop thread: once this returns,
            // no callback for this object is running or can run.
            //
            // ⚠️ Unregistered with the SAME buffer and length it was registered
            // with, as hidapi does. The NULL-buffer form was never soaked while
            // the object was scheduled, and whether IOKit detaches on it is
            // unverified (Phases 1 and 3 audit, F4).
            let (buf, ctx) = (SendPtr(self.buffer as *mut c_void), SendPtr(self.ctx as *mut c_void));
            RunLoop::get().run(move |rl| {
                let (d, buf, ctx) = (d, buf, ctx);
                IOHIDDeviceRegisterInputReportWithTimeStampCallback(d.0, buf.0 as *mut u8, INPUT_BUFFER as CFIndex, None, ctx.0);
                // ⚠️ The original context, as with the input-report callback
                // above: IOKit matches a registration by its context, so
                // unregistering with NULL leaves the entry in place (Codex
                // review of the transport, 2026-09-18).
                IOHIDDeviceRegisterRemovalCallback(d.0, None, ctx.0);
                IOHIDDeviceUnscheduleFromRunLoop(d.0, rl, kCFRunLoopDefaultMode);
            });
            if self.open.load(Relaxed) {
                IOHIDDeviceClose(self.dev, 0);
            }
            CFRelease(self.dev as CFTypeRef);
            // ⚠️ `ctx` and `buffer` are deliberately NEVER freed. If IOKit kept
            // any registration past the calls above, the next report would
            // land in freed memory; leaking them costs about 400 B per board
            // arrival (a replug, a slider flip, a `Stuck`), which is nothing
            // against a use-after-free in a daemon that runs for weeks (F4).
            let _ = (self.ctx, self.buffer);
        }
    }
}

/// The board object this process holds, if any.
static BOARD: Mutex<Option<Arc<Board>>> = Mutex::new(None);

/// An open board, for one interaction. Closes on drop.
pub struct Device {
    board: Arc<Board>,
    outstanding: Outstanding,
    /// A write completed in this interaction, and a report was read: what
    /// [`Deafness`] counts.
    wrote: std::sync::atomic::AtomicBool,
    heard: std::sync::atomic::AtomicBool,
}

impl Device {
    pub fn name(&self) -> &str {
        &self.board.name
    }
}

fn os(rc: IOReturn, what: &str) -> OsError {
    OsError::new(rc as i64, format!("{what}: {}", ioreturn_name(rc)))
}

/// The board's services as the registry lists them, opening nothing: every
/// `IOHIDDevice` with the board's VID/PID.
pub fn candidates() -> Result<Vec<discovery::Candidate>, Error> {
    discovery::list().map(|all| all.into_iter().map(|(c, _)| c).collect()).map_err(Error::Discovery)
}

/// `hid_present()` for the clock loop: the port's location id, as the Python
/// timekeeper's `cid` spells it (decimal `locationID`), or nothing when absent.
pub fn listed() -> Vec<String> {
    let Ok(all) = candidates() else { return Vec::new() };
    let mut ids: Vec<String> = all.iter().filter_map(|c| c.location_id).map(|l| l.to_string()).collect();
    ids.dedup();
    if ids.is_empty() && !all.is_empty() {
        ids.push("unknown".into()); // present, port not reported: still present
    }
    ids
}

/// Find the board, decide from properties, and open it for one interaction.
pub fn open_board() -> Result<Device, Error> {
    use std::sync::atomic::Ordering::Relaxed;

    let all = discovery::list().map_err(Error::Discovery)?;
    let candidates: Vec<_> = all.iter().map(|(c, _)| c.clone()).collect();
    let id = match discovery::choose(&candidates) {
        Choice::One(id) => id,
        Choice::Absent => return Err(Error::Absent),
        Choice::Ambiguous(ids) => return Err(Error::Ambiguous(ids.iter().map(|i| format!("IOHIDDevice {i:#x}")).collect())),
    };
    let (chosen, service) = all.into_iter().find(|(c, _)| c.registry_id == id).expect("chosen from this list");
    if let Err(why) = chosen.check_sizes() {
        return Err(Error::Incompatible { path: chosen.name(), why });
    }

    let mut slot = BOARD.lock().unwrap_or_else(|e| e.into_inner());
    let reuse = slot.as_ref().is_some_and(|b| b.registry_id == id && b.usable());
    if !reuse {
        // Dropping a board that is still open elsewhere in this process
        // cannot happen: `Device` holds its own `Arc`.
        *slot = Some(Arc::new(Board::create(&service, id, chosen.name())?));
    }
    let board = Arc::clone(slot.as_ref().expect("just set"));
    drop(slot);

    if board.open.swap(true, Relaxed) {
        return Err(Error::Open {
            path: board.name.clone(),
            source: OsError::new(kIOReturnExclusiveAccess as i64, "already open in this process"),
        });
    }
    let rc = unsafe { IOHIDDeviceOpen(board.dev, kIOHIDOptionsTypeNone) };
    if rc != kIOReturnSuccess {
        board.open.store(false, Relaxed);
        return Err(Error::Open { path: board.name.clone(), source: os(rc, "IOHIDDeviceOpen") });
    }
    // Reports that arrived while closed belong to nobody.
    board.shared().inbox.lock().unwrap_or_else(|e| e.into_inner()).reports.clear();
    Ok(Device { board, outstanding: Outstanding::new(), wrote: false.into(), heard: false.into() })
}

impl Drop for Device {
    fn drop(&mut self) {
        use std::sync::atomic::Ordering::Relaxed;
        if self.board.open.swap(false, Relaxed) {
            unsafe { IOHIDDeviceClose(self.board.dev, 0) };
        }
        let retire = self
            .board
            .deafness
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .interaction(self.wrote.load(Relaxed), self.heard.load(Relaxed));
        if retire && !self.board.abandoned.load(Relaxed) {
            let stamp = crate::logfile::stamp(&super::host::SystemHost);
            // stderr is the daemon's stdio log under launchd: rare, and worth
            // counting when it happens.
            if retirement_allowed(&mut RETIREMENTS.lock().unwrap_or_else(|e| e.into_inner()), Instant::now()) {
                self.board.abandoned.store(true, Relaxed);
                CAP_SAID.store(false, Relaxed);
                eprintln!(
                    "{stamp} transport: {} replaced after {SILENT_LIMIT} interactions that wrote and heard nothing",
                    self.board.name
                );
            } else if !CAP_SAID.swap(true, Relaxed) {
                eprintln!(
                    "{stamp} transport: {} is deaf, but {RETIREMENTS_PER_HOUR} replacements in an hour is the cap; keeping it",
                    self.board.name
                );
            }
        }
    }
}

impl Wire for Device {
    fn write_report(&self, data: &[u8], timeout: Duration) -> Result<Sent, Error> {
        use std::sync::atomic::Ordering::Relaxed;
        let board = &self.board;
        if board.abandoned.load(Relaxed) {
            return Err(Error::Stuck);
        }
        if data.len() != WIRE_LEN {
            return Err(Error::Io {
                op: "write",
                source: OsError::new(0, format!("a report is {WIRE_LEN} bytes with its id, not {}", data.len())),
            });
        }
        let shared = board.shared();
        let seq = {
            let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
            if inbox.removed {
                return Err(Error::Absent);
            }
            inbox.write_seq += 1;
            inbox.write_done = None;
            inbox.write_seq
        };
        let rc = unsafe {
            IOHIDDeviceSetReportWithCallback(
                board.dev,
                kIOHIDReportTypeOutput,
                data[0] as CFIndex,
                data[1..].as_ptr(),
                REPORT_LEN as CFIndex,
                timeout.as_secs_f64(),
                Some(on_written),
                board.ctx as *mut c_void,
            )
        };
        if rc == kIOReturnExclusiveAccess {
            return Err(Error::Open { path: board.name.clone(), source: os(rc, "write") });
        }
        if rc != kIOReturnSuccess {
            return Err(Error::Io { op: "write", source: os(rc, "IOHIDDeviceSetReportWithCallback") });
        }
        let deadline = Instant::now() + timeout + WRITE_GRACE;
        let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            if let Some((s, result)) = inbox.write_done {
                if s == seq {
                    return match result {
                        kIOReturnSuccess => {
                            self.wrote.store(true, Relaxed);
                            Ok(Sent::Yes)
                        }
                        kIOReturnTimeout => Ok(Sent::TimedOut),
                        kIOReturnExclusiveAccess => {
                            Err(Error::Open { path: board.name.clone(), source: os(result, "write") })
                        }
                        other => Err(Error::Io { op: "write", source: os(other, "write") }),
                    };
                }
            }
            if inbox.removed {
                return Err(Error::Absent);
            }
            let now = Instant::now();
            if now >= deadline {
                board.abandoned.store(true, Relaxed);
                return Err(Error::Stuck);
            }
            inbox = shared.ready.wait_timeout(inbox, deadline - now).unwrap_or_else(|e| e.into_inner()).0;
        }
    }

    fn read_report(&self, timeout: Duration) -> Result<Option<Vec<u8>>, Error> {
        let shared = self.board.shared();
        let deadline = Instant::now() + timeout;
        let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            if let Some(r) = inbox.reports.pop_front() {
                self.heard.store(true, std::sync::atomic::Ordering::Relaxed);
                return Ok(Some(r));
            }
            if inbox.removed {
                return Err(Error::Absent);
            }
            let now = Instant::now();
            if now >= deadline {
                return Ok(None);
            }
            inbox = shared.ready.wait_timeout(inbox, deadline - now).unwrap_or_else(|e| e.into_inner()).0;
        }
    }
}

impl HidTransport for Device {
    fn outstanding(&self) -> &Outstanding {
        &self.outstanding
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_deaf_object_is_retired_after_three_silent_writes() {
        let mut d = Deafness::default();
        assert!(!d.interaction(true, true));
        assert!(!d.interaction(true, false));
        assert!(!d.interaction(true, false));
        assert!(d.interaction(true, false), "third silent interaction in a row");
    }

    /// The timekeeper's seize can steal one reply; that is not deafness.
    #[test]
    fn one_stolen_reply_resets_on_the_next_answer() {
        let mut d = Deafness::default();
        d.interaction(true, true);
        for _ in 0..10 {
            assert!(!d.interaction(true, false));
            assert!(!d.interaction(true, true));
        }
    }

    /// A hung board makes a fresh object silent too: never retire one that
    /// has not heard, or objects leak a page each for as long as it hangs.
    #[test]
    fn an_object_that_never_heard_is_not_retired() {
        let mut d = Deafness::default();
        for _ in 0..100 {
            assert!(!d.interaction(true, false));
        }
    }

    #[test]
    fn retirements_are_capped_per_hour() {
        let mut log = std::collections::VecDeque::new();
        let t = Instant::now();
        for i in 0..RETIREMENTS_PER_HOUR {
            assert!(retirement_allowed(&mut log, t + Duration::from_secs(i as u64)));
        }
        assert!(!retirement_allowed(&mut log, t + Duration::from_secs(60)), "the cap");
        assert!(retirement_allowed(&mut log, t + Duration::from_secs(3600)), "the hour rolled over for the first");
    }

    #[test]
    fn an_interaction_that_wrote_nothing_counts_for_nothing() {
        let mut d = Deafness::default();
        d.interaction(true, true);
        d.interaction(true, false);
        d.interaction(true, false);
        assert!(!d.interaction(false, false));
        assert!(d.interaction(true, false));
    }
}
