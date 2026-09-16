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
            RunLoop::get().run(move |rl| {
                let d = d;
                IOHIDDeviceRegisterInputReportWithTimeStampCallback(d.0, std::ptr::null_mut(), 0, None, std::ptr::null_mut());
                IOHIDDeviceRegisterRemovalCallback(d.0, None, std::ptr::null_mut());
                IOHIDDeviceUnscheduleFromRunLoop(d.0, rl, kCFRunLoopDefaultMode);
            });
            if self.open.load(Relaxed) {
                IOHIDDeviceClose(self.dev, 0);
            }
            CFRelease(self.dev as CFTypeRef);
            if !self.abandoned.load(Relaxed) {
                drop(Arc::from_raw(self.ctx));
                drop(Box::from_raw(self.buffer));
            }
        }
    }
}

/// The board object this process holds, if any.
static BOARD: Mutex<Option<Arc<Board>>> = Mutex::new(None);

/// An open board, for one interaction. Closes on drop.
pub struct Device {
    board: Arc<Board>,
    outstanding: Outstanding,
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
    Ok(Device { board, outstanding: Outstanding::new() })
}

impl Drop for Device {
    fn drop(&mut self) {
        use std::sync::atomic::Ordering::Relaxed;
        if self.board.open.swap(false, Relaxed) {
            unsafe { IOHIDDeviceClose(self.board.dev, 0) };
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
                        kIOReturnSuccess => Ok(Sent::Yes),
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
