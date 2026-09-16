#![allow(non_upper_case_globals)]
//! The board: one IOHIDDevice object per arrival, opened per interaction.
//!
//! ⚠️ **Opened per interaction, never for the process lifetime** (plan,
//! exclusivity section): a held open would lock the kept hidapi diagnostics
//! out on macOS. But the **object** is not per interaction, and that is a
//! measured leak, not a style choice:
//!
//! ⚠️ **Registering an input-report callback leaks one page (~3.9 KB) per
//! device object, and nothing gives it back** — measured 2026-09-16 on macOS
//! 27.0 over 2,000-cycle runs: with the timestamped and the plain callback API
//! alike, whether or not the callback is unregistered before close, and with a
//! 32- or 256-byte buffer. Create/open/close/release with no callback: flat.
//! At the daemon's ~28,800 interactions a day, a fresh object per interaction
//! is ~110 MB a day. So the object, its callbacks and its run-loop scheduling
//! are made **once**, when the board is found, and only `IOHIDDeviceOpen` /
//! `IOHIDDeviceClose` happen per interaction: 6,000 such cycles, flat.
//!
//! The shape is the Windows `Wire` trait's — one report out with a bounded
//! write, one report in with a bounded read — so Phase 1 can put this under
//! `hid::exchange` unchanged. Reports come back as 33 bytes with a leading
//! report id of 0, which is what `proto::normalize_input` expects; IOKit hands
//! the callback the 32-byte payload alone.
//!
//! What "Stuck" means here, which the plan asked to be stated: a write whose
//! completion callback never arrives, not even with `kIOReturnTimeout`, inside
//! its own timeout plus a grace. The device is then abandoned: its context is
//! leaked rather than freed, because a late callback could still name it.

use std::collections::VecDeque;
use std::os::raw::c_void;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use crate::cf::Io;
use crate::runloop::RunLoop;
use crate::sys::*;

pub const REPORT_LEN: usize = 32;
pub const WIRE_LEN: usize = 33;

/// One input report, and when each layer saw it.
#[derive(Clone, Debug)]
pub struct Arrival {
    /// Report id 0, then the 32-byte payload.
    pub data: [u8; WIRE_LEN],
    /// IOKit's timestamp: Mach absolute time the kernel took the report.
    pub kernel_abs: u64,
    /// Mach absolute time the callback ran on the loop thread.
    pub callback_abs: u64,
}

#[derive(Debug)]
pub enum Error {
    Create,
    Open(IOReturn),
    Write(IOReturn),
    Removed,
    Stuck,
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Create => write!(
                f,
                "IOHIDDeviceCreate returned NULL (the service went away?)"
            ),
            Error::Open(rc) => write!(f, "IOHIDDeviceOpen: {}", ioreturn_name(*rc)),
            Error::Write(rc) => write!(f, "write: {}", ioreturn_name(*rc)),
            Error::Removed => write!(f, "the device was removed"),
            Error::Stuck => write!(
                f,
                "a write never completed, not even with a timeout; device abandoned"
            ),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Sent {
    Yes,
    TimedOut,
}

#[derive(Default)]
struct Inbox {
    reports: VecDeque<Arrival>,
    removed: bool,
    /// (sequence, result, callback abs) of the last completed write.
    write_done: Option<(u64, IOReturn, u64)>,
    write_seq: u64,
}

struct Shared {
    inbox: Mutex<Inbox>,
    ready: Condvar,
}

/// IOKit writes each input report into a buffer we lend it for as long as the
/// callback is registered. Raw, not inside `Shared`: it is written through a
/// pointer while `Shared` is only ever shared by reference.
const INPUT_BUFFER: usize = 256;

unsafe extern "C" fn on_report(
    context: *mut c_void,
    _result: IOReturn,
    _sender: *mut c_void,
    _report_type: IOHIDReportType,
    report_id: u32,
    report: *mut u8,
    report_length: CFIndex,
    time_stamp: u64,
) {
    let callback_abs = mach_absolute_time();
    let shared = &*(context as *const Shared);
    let payload = std::slice::from_raw_parts(report, report_length.max(0) as usize);
    let mut data = [0u8; WIRE_LEN];
    data[0] = report_id as u8;
    let n = payload.len().min(REPORT_LEN);
    data[1..1 + n].copy_from_slice(&payload[..n]);
    let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
    inbox.reports.push_back(Arrival {
        data,
        kernel_abs: time_stamp,
        callback_abs,
    });
    shared.ready.notify_all();
}

unsafe extern "C" fn on_removed(context: *mut c_void, _result: IOReturn, _sender: *mut c_void) {
    let shared = &*(context as *const Shared);
    shared
        .inbox
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .removed = true;
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
    let abs = mach_absolute_time();
    let shared = &*(context as *const Shared);
    let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
    let seq = inbox.write_seq;
    inbox.write_done = Some((seq, result, abs));
    shared.ready.notify_all();
}

/// Timings of the last write, in Mach ticks.
#[derive(Clone, Copy, Debug, Default)]
pub struct WriteTiming {
    pub call_abs: u64,
    pub done_abs: u64,
}

pub struct Device {
    dev: IOHIDDeviceRef,
    ctx: *const Shared,
    buffer: *mut [u8; INPUT_BUFFER],
    abandoned: bool,
    is_open: bool,
    pub last_write: WriteTiming,
}

// The raw pointers are only dereferenced under the inbox mutex or on the loop
// thread; the device itself is used from one thread at a time.
unsafe impl Send for Device {}

struct SendPtr(*mut c_void);
unsafe impl Send for SendPtr {}

impl Device {
    /// Make the device object for `service`, register its callbacks and
    /// schedule it — **once per board arrival**. Opens nothing.
    pub fn create(service: &Io) -> Result<Device, Error> {
        unsafe {
            let dev = IOHIDDeviceCreate(kCFAllocatorDefault, service.0);
            if dev.is_null() {
                return Err(Error::Create);
            }
            let shared = Arc::new(Shared {
                inbox: Mutex::new(Inbox::default()),
                ready: Condvar::new(),
            });
            let ctx = Arc::into_raw(shared);
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
            Ok(Device {
                dev,
                ctx,
                buffer,
                abandoned: false,
                is_open: false,
                last_write: WriteTiming::default(),
            })
        }
    }

    /// Open for one interaction. `seize` asks for exclusive access, which is
    /// what hidapi does by default on Darwin; the daemon never seizes. Anything
    /// queued from before is discarded: a closed device's reports belong to
    /// nobody.
    pub fn open(&mut self, seize: bool) -> Result<(), Error> {
        if self.abandoned {
            return Err(Error::Stuck);
        }
        if self.is_open {
            return Ok(());
        }
        let options = if seize {
            kIOHIDOptionsTypeSeizeDevice
        } else {
            kIOHIDOptionsTypeNone
        };
        let rc = unsafe { IOHIDDeviceOpen(self.dev, options) };
        if rc != kIOReturnSuccess {
            return Err(Error::Open(rc));
        }
        self.shared()
            .inbox
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .reports
            .clear();
        self.is_open = true;
        Ok(())
    }

    /// End the interaction. Idempotent.
    pub fn close(&mut self) {
        if self.is_open {
            unsafe { IOHIDDeviceClose(self.dev, 0) };
            self.is_open = false;
        }
    }

    fn shared(&self) -> &Shared {
        unsafe { &*self.ctx }
    }

    /// Write one 33-byte report (id first), bounded by `timeout`.
    pub fn write_report(
        &mut self,
        data: &[u8; WIRE_LEN],
        timeout: Duration,
    ) -> Result<Sent, Error> {
        if self.abandoned {
            return Err(Error::Stuck);
        }
        let seq = {
            let mut inbox = self
                .shared()
                .inbox
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            inbox.write_seq += 1;
            inbox.write_done = None;
            inbox.write_seq
        };
        let call_abs = unsafe { mach_absolute_time() };
        let rc = unsafe {
            IOHIDDeviceSetReportWithCallback(
                self.dev,
                kIOHIDReportTypeOutput,
                data[0] as CFIndex,
                data[1..].as_ptr(),
                REPORT_LEN as CFIndex,
                timeout.as_secs_f64(),
                Some(on_written),
                self.ctx as *mut c_void,
            )
        };
        if rc != kIOReturnSuccess {
            return Err(Error::Write(rc));
        }
        let deadline = Instant::now() + timeout + Duration::from_millis(500);
        // Borrow the context through the raw pointer, not through `self`, so
        // the outcome can be recorded on `self` below.
        let shared: &Shared = unsafe { &*self.ctx };
        let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
        let outcome = loop {
            if let Some((s, result, done_abs)) = inbox.write_done {
                if s == seq {
                    break Ok((result, done_abs));
                }
            }
            if inbox.removed {
                break Err(Error::Removed);
            }
            let now = Instant::now();
            if now >= deadline {
                break Err(Error::Stuck);
            }
            inbox = shared
                .ready
                .wait_timeout(inbox, deadline - now)
                .unwrap_or_else(|e| e.into_inner())
                .0;
        };
        drop(inbox);
        match outcome {
            Ok((result, done_abs)) => {
                self.last_write = WriteTiming { call_abs, done_abs };
                match result {
                    kIOReturnSuccess => Ok(Sent::Yes),
                    kIOReturnTimeout => Ok(Sent::TimedOut),
                    other => Err(Error::Write(other)),
                }
            }
            Err(Error::Stuck) => {
                self.abandoned = true;
                Err(Error::Stuck)
            }
            Err(e) => Err(e),
        }
    }

    /// Leak isolation only: the synchronous write, no timeout.
    pub unsafe fn set_report_sync(&self, data: &[u8; WIRE_LEN]) -> IOReturn {
        IOHIDDeviceSetReport(self.dev, kIOHIDReportTypeOutput, data[0] as CFIndex, data[1..].as_ptr(), REPORT_LEN as CFIndex)
    }

    /// The next report, or `None` if nothing arrives inside `timeout`.
    pub fn read_report(&self, timeout: Duration) -> Result<Option<Arrival>, Error> {
        let deadline = Instant::now() + timeout;
        let shared = self.shared();
        let mut inbox = shared.inbox.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            if let Some(a) = inbox.reports.pop_front() {
                return Ok(Some(a));
            }
            if inbox.removed {
                return Err(Error::Removed);
            }
            let now = Instant::now();
            if now >= deadline {
                return Ok(None);
            }
            inbox = shared
                .ready
                .wait_timeout(inbox, deadline - now)
                .unwrap_or_else(|e| e.into_inner())
                .0;
        }
    }
}

impl Drop for Device {
    fn drop(&mut self) {
        unsafe {
            let d = SendPtr(self.dev);
            // Unregister and unschedule on the loop thread: after this returns
            // no callback for this device can be running or can run.
            RunLoop::get().run(move |rl| {
                let d = d;
                IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                    d.0,
                    std::ptr::null_mut(),
                    0,
                    None,
                    std::ptr::null_mut(),
                );
                IOHIDDeviceRegisterRemovalCallback(d.0, None, std::ptr::null_mut());
                IOHIDDeviceUnscheduleFromRunLoop(d.0, rl, kCFRunLoopDefaultMode);
            });
            if self.is_open {
                IOHIDDeviceClose(self.dev, 0);
            }
            CFRelease(self.dev as CFTypeRef);
            if !self.abandoned {
                drop(Arc::from_raw(self.ctx));
                drop(Box::from_raw(self.buffer));
            }
        }
    }
}
