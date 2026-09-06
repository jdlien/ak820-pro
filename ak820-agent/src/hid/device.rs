//! The Win32 half: listing interfaces, opening one, and one bounded transfer.
//!
//! Direct `CreateFileW`/`ReadFile`/`WriteFile`, as in `../jdrgb` and
//! `../jdups`, and for the same reason both of those give: **`hidapi`'s
//! enumeration opens every HID device on the machine**, which twice wedged an
//! APC UPS here (`../jdrgb/docs/ups-wedge-incident.md`). Everything below opens
//! exactly the paths [`super::path`] has already decided are ours.
//!
//! ⚠️ Cancellation is the part that is easy to get subtly wrong.
//! `CancelIoEx` *requests* cancellation; it does not deliver it. Until the
//! following `GetOverlappedResult` returns, the kernel may still write into the
//! `OVERLAPPED` and into the read buffer -- and both live on the stack frame
//! that is about to return. So every timeout path here cancels **and then
//! blocks**, and the three-way outcome (completed anyway / genuinely aborted /
//! failed) is distinguished rather than flattened into "timed out". Reporting a
//! transfer that actually completed as a timeout would mean re-sending a write
//! that already went out, or discarding a reply that did arrive.

use std::time::{Duration, Instant};

use windows::core::{HRESULT, PCWSTR};
use windows::Win32::Devices::DeviceAndDriverInstallation::{
    CM_GET_DEVICE_INTERFACE_LIST_PRESENT, CM_Get_Device_Interface_ListW,
    CM_Get_Device_Interface_List_SizeW, CR_BUFFER_SMALL, CR_SUCCESS,
};
use windows::Win32::Devices::HumanInterfaceDevice::{
    GUID_DEVINTERFACE_HID, HIDD_ATTRIBUTES, HIDP_CAPS, HIDP_STATUS_SUCCESS, HidD_FreePreparsedData,
    HidD_GetAttributes, HidD_GetPreparsedData, HidD_SetNumInputBuffers, HidP_GetCaps,
    PHIDP_PREPARSED_DATA,
};
use windows::Win32::Foundation::{
    CloseHandle, ERROR_IO_PENDING, ERROR_OPERATION_ABORTED, GENERIC_READ, GENERIC_WRITE, HANDLE,
    WAIT_OBJECT_0, WAIT_TIMEOUT,
};
use windows::Win32::Storage::FileSystem::{
    CreateFileW, FILE_FLAG_OVERLAPPED, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, ReadFile,
    WriteFile,
};
use windows::Win32::System::IO::{
    CancelIoEx, GetOverlappedResult, GetOverlappedResultEx, OVERLAPPED,
};
use windows::Win32::System::Threading::{CreateEventW, ResetEvent, WaitForSingleObject};

use super::caps::{Identity, Reject};
use super::path;
use super::{Drained, Error};
use crate::proto::{self, Channel, REPORT_LEN, Verdict};

/// How long one report may take to leave. Generous: the board answers in single
/// milliseconds, so a stall here means something is wrong rather than slow.
const WRITE_TIMEOUT_MS: u32 = 1000;

/// How long a whole request may take, matching `ak820ctl`'s `hid_read_timeout`.
/// It is a budget for the *transaction*, not for one read, because a read that
/// returns someone else's report has not answered us.
pub const REQUEST_TIMEOUT: Duration = Duration::from_millis(2000);

/// Per-read slice of that budget.
const READ_SLICE: Duration = Duration::from_millis(250);

/// How long a refused-to-land cancellation is given before the device is
/// declared stuck and its buffer abandoned to the kernel.
///
/// Generous, because reaching it is a permanent decision: the measured idle
/// cancel returns in 3–6 ms, so a second is roughly two hundred times the
/// observed worst case and anything past it is a driver that is not coming
/// back.
const CANCEL_GRACE_MS: u32 = 1000;

/// How long [`Device::drain`] may spend clearing the queue when the caller
/// gave no deadline of its own.
const DRAIN_BUDGET: Duration = Duration::from_millis(250);

/// Milliseconds for a Win32 timeout argument, clamped rather than truncated.
///
/// ⚠️ `as u32` on a large `u128` wraps, which would turn a long timeout into a
/// short one — the failure that looks like a flaky device.
fn ms(d: Duration) -> u32 {
    d.as_millis().min(u32::MAX as u128) as u32
}

/// How long a pre-drain read waits before concluding the queue is empty.
///
/// Not zero, deliberately. A queued report completes the `ReadFile` almost
/// immediately, but "almost" is not "before we ask", and a zero wait would
/// cancel reads that were about to hand us the stale report we are trying to
/// clear. One millisecond is enough for a report already sitting in the
/// driver's queue and short enough to be free when the queue is empty.
const DRAIN_TIMEOUT_MS: u32 = 1;

/// Bound on the pre-drain, so a chatty peer cannot hold us in the loop.
const DRAIN_LIMIT: usize = 32;

// ---------------------------------------------------------------------------
// Discovery -- reads the PnP database, opens nothing
// ---------------------------------------------------------------------------

/// One HID interface, named but not opened.
#[derive(Clone, Debug)]
pub struct Interface {
    /// NUL-terminated wide path, ready for `CreateFileW`.
    wide: Vec<u16>,
    text: String,
    want: (u16, u16),
}

impl Interface {
    pub fn path(&self) -> &str {
        &self.text
    }
}

/// Every present HID interface whose path names this VID and PID.
///
/// `CM_Get_Device_Interface_ListW` hands back the Configuration Manager's own
/// records -- a NUL-separated, double-NUL-terminated block of paths -- and
/// **opens nothing at all**. That is the whole answer to the UPS incident:
/// deciding which devices are ours is a string question, and only the answer
/// gets a handle.
pub fn interfaces(vid: u16, pid: u16) -> Result<Vec<Interface>, Error> {
    let mut listed = list_hid_paths()?;
    listed.sort();
    let mine = path::candidates(&listed, vid, pid);

    let dupes = path::duplicate_interfaces(&mine);
    if !dupes.is_empty() {
        return Err(Error::Ambiguous(
            dupes.into_iter().map(str::to_string).collect(),
        ));
    }

    Ok(mine
        .into_iter()
        .map(|p| Interface {
            wide: p.encode_utf16().chain(std::iter::once(0)).collect(),
            text: p.to_string(),
            want: (vid, pid),
        })
        .collect())
}

/// How many HID interfaces this machine currently has -- ours and everyone
/// else's.
///
/// Worth being able to print, because it is exactly the number of devices
/// `hidapi`'s enumeration would have **opened** to answer the same question
/// this crate answers by reading strings. On this machine that difference is
/// the one between working and a wedged UPS.
pub fn present_count() -> Result<usize, Error> {
    Ok(list_hid_paths()?.len())
}

/// The Configuration Manager's list of present HID interfaces.
fn list_hid_paths() -> Result<Vec<String>, Error> {
    // Sizing and fetching are two calls, so the list can grow in between. That
    // is exactly what CR_BUFFER_SMALL reports, and retrying is the documented
    // answer -- not a bigger guess.
    for _ in 0..4 {
        let mut len: u32 = 0;
        let cr = unsafe {
            CM_Get_Device_Interface_List_SizeW(
                &mut len,
                &GUID_DEVINTERFACE_HID,
                PCWSTR::null(),
                CM_GET_DEVICE_INTERFACE_LIST_PRESENT,
            )
        };
        if cr != CR_SUCCESS {
            return Err(Error::Discovery(format!("sizing failed (CONFIGRET {})", cr.0)));
        }

        let mut buf = vec![0u16; len as usize];
        let cr = unsafe {
            CM_Get_Device_Interface_ListW(
                &GUID_DEVINTERFACE_HID,
                PCWSTR::null(),
                &mut buf,
                CM_GET_DEVICE_INTERFACE_LIST_PRESENT,
            )
        };
        if cr == CR_BUFFER_SMALL {
            continue;
        }
        if cr != CR_SUCCESS {
            return Err(Error::Discovery(format!("listing failed (CONFIGRET {})", cr.0)));
        }
        return Ok(path::split_multi_sz(&buf));
    }
    Err(Error::Discovery(
        "the interface list kept changing while it was being read".into(),
    ))
}

// ---------------------------------------------------------------------------
// The open device
// ---------------------------------------------------------------------------

/// An open HID interface. Closes itself on drop.
///
/// `Send` but **not** `Sync`, and that is the design: the handle may move to
/// whichever thread owns the serialized executor, but the single reused event
/// object means two threads must never have a transfer in flight at once. The
/// raw pointer inside `HANDLE` makes the compiler enforce the second half.
pub struct Device {
    handle: HANDLE,
    /// Set when a cancellation failed to land inside its grace period, after
    /// which the handle can never be used or closed again. `Cell` rather than
    /// an atomic because `Device` is deliberately `!Sync`.
    stuck: std::cell::Cell<bool>,
    /// One manual-reset event, reused by every transfer. The `OVERLAPPED` that
    /// points at it is a local in each call, and nothing outlives an in-flight
    /// transfer -- see the cancel path in [`Device::transfer`].
    event: HANDLE,
    identity: Identity,
    text: String,
}

// Safe because the handles are owned exclusively by this Device and Win32
// handles are process-wide, so moving one between threads is sound.
unsafe impl Send for Device {}

/// A correlated reply, and what had to be thrown away to reach it.
///
/// `drained` is not noise: on this machine it is the direct evidence of another
/// process talking to the same board, and an empty list on a busy machine is
/// itself worth noticing.
#[derive(Clone, Debug)]
pub struct Reply {
    pub report: [u8; REPORT_LEN],
    pub drained: Vec<Drained>,
}

impl Interface {
    /// Open for reading and writing, then make the device confirm what it is.
    ///
    /// Shared read/write, like every other HID client, and **measured on this
    /// machine 2026-09-05**: a second process opening the same path succeeds,
    /// and so does writing concurrently. Exclusivity was never available, so
    /// short transactions plus reply correlation are the design rather than a
    /// consolation for one.
    pub fn open(&self) -> Result<Device, Error> {
        let handle = unsafe {
            CreateFileW(
                PCWSTR(self.wide.as_ptr()),
                (GENERIC_READ | GENERIC_WRITE).0,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_OVERLAPPED,
                None,
            )
        }
        .map_err(|source| Error::Open {
            path: self.text.clone(),
            source,
        })?;

        // Close on every failure below. The device is ours by the time it is
        // open, but a handle left behind on a rejected collection is a handle
        // still receiving that collection's input reports.
        let reject = |why| {
            unsafe { CloseHandle(handle).ok() };
            Err(Error::Incompatible {
                path: self.text.clone(),
                why,
            })
        };

        let identity = match identify(handle) {
            Some(id) => id,
            None => return reject(Reject::Silent),
        };
        if let Err(why) = identity.check(self.want.0, self.want.1) {
            return reject(why);
        }

        // Without this the driver keeps a small input queue and drops reports
        // that arrive while we are not reading. Per file object, so it is our
        // own queue and does not affect VIA's. hidapi does the same.
        unsafe { HidD_SetNumInputBuffers(handle, 64) };

        let event = match unsafe { CreateEventW(None, true, false, PCWSTR::null()) } {
            Ok(e) => e,
            Err(source) => {
                unsafe { CloseHandle(handle).ok() };
                return Err(Error::Io {
                    op: "event",
                    source,
                });
            }
        };

        Ok(Device {
            handle,
            stuck: std::cell::Cell::new(false),
            event,
            identity,
            text: self.text.clone(),
        })
    }

    /// Ask what this collection is without taking access to it.
    ///
    /// Opened with access `0`, which is enough for `HidD_GetAttributes` and the
    /// preparsed data and cannot disturb whatever else has the device. This is
    /// what `ak820 list --caps` uses, so listing never becomes the thing the
    /// path filter exists to prevent.
    pub fn identify(&self) -> Result<Identity, Error> {
        let handle = unsafe {
            CreateFileW(
                PCWSTR(self.wide.as_ptr()),
                0,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                Default::default(),
                None,
            )
        }
        .map_err(|source| Error::Open {
            path: self.text.clone(),
            source,
        })?;
        let got = identify(handle);
        unsafe { CloseHandle(handle).ok() };
        got.ok_or_else(|| Error::Incompatible {
            path: self.text.clone(),
            why: Reject::Silent,
        })
    }
}

/// Attributes and capabilities of an already-open handle.
fn identify(handle: HANDLE) -> Option<Identity> {
    let mut attrs = HIDD_ATTRIBUTES {
        Size: std::mem::size_of::<HIDD_ATTRIBUTES>() as u32,
        ..Default::default()
    };
    if !unsafe { HidD_GetAttributes(handle, &mut attrs) } {
        return None;
    }

    let mut pp = PHIDP_PREPARSED_DATA::default();
    if !unsafe { HidD_GetPreparsedData(handle, &mut pp) } {
        return None;
    }
    let mut caps = HIDP_CAPS::default();
    let ok = unsafe { HidP_GetCaps(pp, &mut caps) } == HIDP_STATUS_SUCCESS;
    unsafe { HidD_FreePreparsedData(pp) };
    if !ok {
        return None;
    }

    Some(Identity {
        vid: attrs.VendorID,
        pid: attrs.ProductID,
        usage_page: caps.UsagePage,
        usage: caps.Usage,
        input_len: caps.InputReportByteLength,
        output_len: caps.OutputReportByteLength,
    })
}

/// Find the board's raw-HID interface and open it.
///
/// Refuses rather than chooses when two of these keyboards are attached; see
/// [`path::duplicate_interfaces`].
pub fn open_board() -> Result<Device, Error> {
    let candidates = interfaces(path::VID, path::PID)?;
    if candidates.is_empty() {
        return Err(Error::Absent);
    }

    // Ordered so the raw-HID hint is first, which means the usual case opens
    // exactly one collection. Anything after it gets opened only because the
    // hint was wrong, and the post-open check is what actually decides.
    let mut last = None;
    for iface in candidates {
        match iface.open() {
            Ok(dev) => return Ok(dev),
            Err(e) => last = Some(e),
        }
    }
    Err(last.unwrap_or(Error::Absent))
}

impl Device {
    pub fn identity(&self) -> Identity {
        self.identity
    }

    pub fn path(&self) -> &str {
        &self.text
    }

    /// Send one command and wait for **its** reply.
    ///
    /// ⚠️ The loop is the point. Windows delivers input reports to every open
    /// handle, so a read can return VIA's answer, or another process's text
    /// echo, or our own echo from an earlier command on another channel. Each
    /// of those is discarded and the wait continues; only a report naming this
    /// channel and command ends it.
    pub fn request(
        &self,
        channel: Channel,
        command: u8,
        body: &[u8],
        budget: Duration,
    ) -> Result<Reply, Error> {
        self.request_at(channel, command, body, budget, |_| {})
    }

    /// As [`Device::request`], but the caller is handed the instant the command
    /// actually went onto the wire.
    ///
    /// ⚠️ This exists because the clock contract cannot be expressed without
    /// it. `t0; request(GET); t1` measures the **pre-drain** as well as the
    /// round trip, and the drain is unbounded from the caller's point of view:
    /// a VIA flood can make it several milliseconds. The midpoint of that wider
    /// interval is not the transmission midpoint, so the offset it yields is
    /// wrong by half the drain -- silently, and in the direction that looks
    /// like a real clock error.
    ///
    /// The callback fires **after** draining and immediately before the write
    /// returns, so a caller can take `t0` where the NTP arithmetic actually
    /// needs it. Phase 2 will build the SET side on this; see finding 3 of
    /// `plans/review-codex-phase0-2026-09-06.md`.
    pub fn request_at(
        &self,
        channel: Channel,
        command: u8,
        body: &[u8],
        budget: Duration,
        on_send: impl FnOnce(Instant),
    ) -> Result<Reply, Error> {
        // ⚠️ The budget is checked BEFORE anything is transmitted. An expired
        // operation that still writes can change the board -- set a clock, move
        // the text band -- after the scheduler has given up on it, which is the
        // one outcome a timeout must never produce.
        let deadline = Instant::now()
            .checked_add(budget)
            .ok_or(Error::Timeout { drained: Vec::new() })?;
        if budget.is_zero() {
            return Err(Error::Timeout { drained: Vec::new() });
        }

        // Anything already queued predates our write and cannot be our answer,
        // so clearing it first keeps the budget for reports that might be.
        // Deliberately before the write: this is time spent outside the
        // interval a clock measurement brackets.
        let (mut drained, queue) = self.drain_until(deadline);

        // ⚠️ Finding 2 of the 2026-09-06 audit. A drain that stopped early has
        // NOT established an empty queue, and the reports still in it can carry
        // our own channel and command from an earlier request. Accepting one
        // would pair an old board sample with new timestamps -- the exact
        // silent corruption single ownership exists to prevent -- so a request
        // that cannot start clean does not start.
        if queue != Queue::Empty {
            return Err(Error::Dirty { queue, drained });
        }

        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err(Error::Timeout { drained });
        }

        let frame = proto::frame(channel, command, body);
        let write_ms = ms(left.min(Duration::from_millis(WRITE_TIMEOUT_MS as u64)));
        match self.transfer(Op::Write(frame.to_vec()), write_ms)? {
            Outcome::Wrote(_) => on_send(Instant::now()),
            Outcome::Read(..) => unreachable!("a write cannot complete as a read"),
            Outcome::TimedOut => {
                return Err(Error::Io {
                    op: "write",
                    source: windows::core::Error::from_hresult(HRESULT::from_win32(
                        ERROR_OPERATION_ABORTED.0,
                    )),
                })
            }
        }

        loop {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return Err(Error::Timeout { drained });
            }
            let Some(buf) = self.read_once(ms(left.min(READ_SLICE)))? else {
                continue;
            };
            match proto::classify(&buf, channel, command) {
                Verdict::Reply(report) => {
                    let mut out = [0u8; REPORT_LEN];
                    out.copy_from_slice(&report[..REPORT_LEN]);
                    return Ok(Reply {
                        report: out,
                        drained,
                    });
                }
                Verdict::Drain(m) => drained.push(Drained::Foreign(m)),
                Verdict::Unhandled => {
                    return Err(Error::Unhandled {
                        channel: channel.id(),
                        command,
                    })
                }
            }
        }
    }

    /// Empty the driver's queue of anything that arrived before we asked, and
    /// **say whether it actually got empty**.
    ///
    /// ⚠️ Finding 2 of the 2026-09-06 audit. The old version returned only what
    /// it discarded, so a caller could not tell "the queue is clean" from "I
    /// gave up after 32 reports". The driver holds 64, so giving up left as
    /// many as 32 in place — and one of those can be a **stale reply carrying
    /// our own channel and command** from an earlier request. The next request
    /// would then be answered by it instantly, pairing an old board sample with
    /// new timestamps. For a clock GET that is a wrong offset with a plausible
    /// RTT: exactly the silent corruption this layer exists to prevent.
    ///
    /// So the outcome is part of the result, and [`Device::request_at`] refuses
    /// to transmit unless it is [`Queue::Empty`].
    pub fn drain_until(&self, deadline: Instant) -> (Vec<Drained>, Queue) {
        let mut seen = Vec::new();
        for _ in 0..DRAIN_LIMIT {
            if Instant::now() >= deadline {
                return (seen, Queue::OutOfTime);
            }
            match self.read_once(DRAIN_TIMEOUT_MS) {
                // A read that times out is the only positive evidence the queue
                // is empty: there was nothing for the kernel to hand back.
                Ok(None) => return (seen, Queue::Empty),
                Ok(Some(buf)) => seen.push(match proto::normalize_input(&buf) {
                    Ok(r) => Drained::Stale {
                        header: [r[0], r[1], r[2]],
                    },
                    Err(m) => Drained::StaleUnreadable(m),
                }),
                Err(_) => return (seen, Queue::Unreadable),
            }
        }
        (seen, Queue::MoreWaiting)
    }

    /// Drain with the default allowance, for callers with no deadline of their
    /// own.
    pub fn drain(&self) -> (Vec<Drained>, Queue) {
        self.drain_until(Instant::now() + DRAIN_BUDGET)
    }

    /// One read, or `Ok(None)` if nothing arrived in time.
    fn read_once(&self, timeout_ms: u32) -> Result<Option<Vec<u8>>, Error> {
        match self.transfer(Op::Read(self.identity.input_len as usize), timeout_ms)? {
            Outcome::Read(mut buf, n) => {
                buf.truncate(n);
                Ok(Some(buf))
            }
            Outcome::Wrote(_) => unreachable!("a read cannot complete as a write"),
            Outcome::TimedOut => Ok(None),
        }
    }

    /// One overlapped transfer, started and finished inside this call.
    ///
    /// ⚠️ The buffer and the `OVERLAPPED` live in a heap [`Pending`], not on
    /// this stack frame, and that is finding 4 of the 2026-09-06 audit.
    /// `CancelIoEx` **requests** cancellation; Microsoft is explicit that it is
    /// not guaranteed. The previous code answered that with a blocking
    /// `GetOverlappedResult`, which is memory-safe but unbounded — a cancel
    /// that never lands parks the executor for good, inside the very function
    /// whose job is to have a deadline.
    ///
    /// So the wait is bounded, and the case that creates is handled rather than
    /// wished away: if the operation is *still* pending after the grace period,
    /// its memory can never be released, because the kernel may write to it at
    /// any later moment. The `Pending` is **leaked deliberately**, the device is
    /// marked stuck, and every later call refuses. Leaking a few dozen bytes
    /// once is the cheap outcome here; freeing them is a use-after-free, and
    /// waiting forever is a hung daemon.
    fn transfer(&self, op: Op, timeout_ms: u32) -> Result<Outcome, Error> {
        if self.stuck.get() {
            return Err(Error::Stuck);
        }
        let name = op.name();
        let mut pending = Box::new(Pending {
            ov: OVERLAPPED {
                hEvent: self.event,
                ..Default::default()
            },
            buf: match &op {
                Op::Write(data) => data.clone(),
                Op::Read(len) => vec![0u8; *len],
            },
        });

        unsafe {
            ResetEvent(self.event).map_err(|source| Error::Io {
                op: "event reset",
                source,
            })?;

            // The kernel keeps writing to these after the call returns, which
            // is what the heap allocation above is for; the slices are rebuilt
            // from raw parts so the borrow does not outlive the statement.
            let ptr = pending.buf.as_mut_ptr();
            let len = pending.buf.len();
            let started = match &op {
                Op::Write(_) => WriteFile(
                    self.handle,
                    Some(std::slice::from_raw_parts(ptr, len)),
                    None,
                    Some(&mut pending.ov),
                ),
                Op::Read(_) => ReadFile(
                    self.handle,
                    Some(std::slice::from_raw_parts_mut(ptr, len)),
                    None,
                    Some(&mut pending.ov),
                ),
            };
            if let Err(source) = started {
                if source.code() != HRESULT::from_win32(ERROR_IO_PENDING.0) {
                    return Err(Error::Io { op: name, source });
                }
            }

            let mut moved: u32 = 0;
            if WaitForSingleObject(self.event, timeout_ms) != WAIT_OBJECT_0 {
                let _ = CancelIoEx(self.handle, Some(&pending.ov));
                return match GetOverlappedResultEx(
                    self.handle,
                    &pending.ov,
                    &mut moved,
                    CANCEL_GRACE_MS,
                    false,
                ) {
                    // Three outcomes, and they are not the same thing. The
                    // transfer may have finished normally in the window between
                    // the wait expiring and the cancel landing; calling that a
                    // timeout would mean re-sending a write that already went
                    // out, or discarding a reply that did arrive.
                    Ok(()) => Ok(op.finish(pending, moved as usize)),
                    Err(source)
                        if source.code() == HRESULT::from_win32(ERROR_OPERATION_ABORTED.0) =>
                    {
                        Ok(Outcome::TimedOut)
                    }
                    Err(source) if source.code() == HRESULT::from_win32(WAIT_TIMEOUT.0) => {
                        // The cancel did not land inside the grace period. The
                        // kernel still owns this buffer, so it has to outlive
                        // us — permanently.
                        self.stuck.set(true);
                        Box::leak(pending);
                        Err(Error::Stuck)
                    }
                    Err(source) => Err(Error::Io { op: name, source }),
                };
            }
            GetOverlappedResult(self.handle, &pending.ov, &mut moved, true)
                .map_err(|source| Error::Io { op: name, source })?;
            Ok(op.finish(pending, moved as usize))
        }
    }
}

/// A transfer's buffer and `OVERLAPPED`, on the heap so they can outlive the
/// call that started them when a cancellation refuses to land.
struct Pending {
    ov: OVERLAPPED,
    buf: Vec<u8>,
}

/// What the pre-drain established about the driver's queue.
///
/// ⚠️ Only [`Queue::Empty`] is safe to start a request on. Every other value
/// means "there may still be a report in there that would answer the command I
/// am about to send", and such a report is indistinguishable from a real reply.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Queue {
    /// A read timed out with nothing to hand back. The only positive evidence.
    Empty,
    /// [`DRAIN_LIMIT`] reports came out and more may remain.
    MoreWaiting,
    /// The deadline passed mid-drain.
    OutOfTime,
    /// A read failed, so nothing was established either way.
    Unreadable,
}

impl std::fmt::Display for Queue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Queue::Empty => write!(f, "empty"),
            Queue::MoreWaiting => {
                write!(f, "still held reports after {DRAIN_LIMIT} were discarded")
            }
            Queue::OutOfTime => write!(f, "could not be cleared within the budget"),
            Queue::Unreadable => write!(f, "could not be read"),
        }
    }
}

/// A transfer that finished, or one that ran out of time. A timeout is not an
/// error here because only the caller knows what it means: for a read inside
/// [`Device::request_at`] it is simply "nothing yet", for a write it is a fault.
enum Outcome {
    /// Bytes written. Not inspected: a short HID write is not a thing the class
    /// driver does, and the report length is fixed by the descriptor.
    Wrote(#[allow(dead_code)] usize),
    Read(Vec<u8>, usize),
    TimedOut,
}

/// What to transfer. Owns its data, because [`Device::transfer`] has to be able
/// to hand ownership to the kernel indefinitely — see its `Pending` note.
enum Op {
    Write(Vec<u8>),
    Read(usize),
}

impl Op {
    fn name(&self) -> &'static str {
        match self {
            Op::Write(_) => "write",
            Op::Read(_) => "read",
        }
    }

    /// Take the completed buffer back out of its heap home.
    fn finish(&self, pending: Box<Pending>, moved: usize) -> Outcome {
        match self {
            Op::Write(_) => Outcome::Wrote(moved),
            Op::Read(_) => Outcome::Read(pending.buf, moved),
        }
    }
}

impl Drop for Device {
    fn drop(&mut self) {
        // ⚠️ A stuck device has an operation the kernel still owns, pointing
        // at a buffer and an event we deliberately leaked. Closing the handle
        // would complete that I/O on our terms rather than the driver's, so the
        // handle and the event are leaked too. One process-lifetime leak of two
        // handles beats a race with the kernel over freed memory.
        if self.stuck.get() {
            return;
        }
        unsafe {
            CloseHandle(self.event).ok();
            CloseHandle(self.handle).ok();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The wire length the protocol assumes, asserted where the buffers are
    /// actually sized. A device claiming otherwise is refused in `caps`, so
    /// these two constants must not drift apart.
    #[test]
    fn a_frame_is_one_wire_report() {
        assert_eq!(proto::frame(Channel::Flash, 0x01, &[]).len(), proto::WIRE_LEN);
    }

    /// Discovery must open nothing, and must survive a machine with no board.
    /// Both are true here: this walks the Configuration Manager's records.
    #[test]
    fn listing_interfaces_never_fails_for_lack_of_a_board() {
        match interfaces(0xFFFF, 0xFFFF) {
            Ok(found) => assert!(found.is_empty(), "0xFFFF:0xFFFF cannot exist"),
            Err(Error::Discovery(_)) => {}
            Err(e) => panic!("unexpected error listing interfaces: {e}"),
        }
    }
}
