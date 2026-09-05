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
    WAIT_OBJECT_0,
};
use windows::Win32::Storage::FileSystem::{
    CreateFileW, FILE_FLAG_OVERLAPPED, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, ReadFile,
    WriteFile,
};
use windows::Win32::System::IO::{CancelIoEx, GetOverlappedResult, OVERLAPPED};
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
const READ_SLICE_MS: u32 = 250;

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
        // Anything already queued predates our write and cannot be our answer,
        // so clearing it first keeps the budget for reports that might be.
        // Deliberately before the write: for a clock transaction this is time
        // spent outside the measured interval.
        let mut drained = self.drain();

        let frame = proto::frame(channel, command, body);
        match self.transfer(Op::Write(&frame), WRITE_TIMEOUT_MS)? {
            Outcome::Done(_) => {}
            Outcome::TimedOut => {
                return Err(Error::Io {
                    op: "write",
                    source: windows::core::Error::from_hresult(HRESULT::from_win32(
                        ERROR_OPERATION_ABORTED.0,
                    )),
                })
            }
        }

        let deadline = Instant::now() + budget;
        let mut buf = vec![0u8; self.identity.input_len as usize];
        loop {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return Err(Error::Timeout { drained });
            }
            let slice = (left.as_millis() as u32).min(READ_SLICE_MS).max(1);
            let n = match self.transfer(Op::Read(&mut buf), slice)? {
                Outcome::Done(n) => n,
                Outcome::TimedOut => continue,
            };
            match proto::classify(&buf[..n], channel, command) {
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

    /// Empty the driver's queue of anything that arrived before we asked.
    ///
    /// Errors are swallowed on purpose: a failure to drain is not a failure of
    /// the request that follows, and the request loop discards stragglers
    /// anyway. What this buys is that the discards happen off the clock.
    ///
    /// ⚠️ This is also, incidentally, the proof that a cancelled read cannot
    /// hang. On an idle queue the first read here has nothing to complete it,
    /// so `CancelIoEx` is the only thing that can, and the call still returns
    /// in about [`DRAIN_TIMEOUT_MS`]. Every request runs it, so the abort path
    /// is exercised continuously rather than only when something goes wrong --
    /// which is what stops "a nominal timeout became an unbounded shutdown
    /// wait" from being a thing that could quietly become true.
    pub fn drain(&self) -> Vec<Drained> {
        let mut seen = Vec::new();
        let mut buf = vec![0u8; self.identity.input_len as usize];
        for _ in 0..DRAIN_LIMIT {
            match self.transfer(Op::Read(&mut buf), DRAIN_TIMEOUT_MS) {
                Ok(Outcome::Done(n)) => {
                    seen.push(match proto::normalize_input(&buf[..n]) {
                        Ok(r) => Drained::Stale {
                            channel: r[1],
                            command: r[2],
                        },
                        Err(m) => Drained::StaleUnreadable(m),
                    });
                }
                _ => break,
            }
        }
        seen
    }

    /// One overlapped transfer, started and finished inside this call.
    ///
    /// The `OVERLAPPED` lives on this stack frame, so the one thing that must
    /// never happen is returning while the kernel could still write to it. On a
    /// timeout that means `CancelIoEx` **and then** a blocking
    /// `GetOverlappedResult`: cancellation is a request, and the I/O is only
    /// certainly finished once that returns.
    fn transfer(&self, op: Op, timeout_ms: u32) -> Result<Outcome, Error> {
        unsafe {
            ResetEvent(self.event).map_err(|source| Error::Io {
                op: "event reset",
                source,
            })?;

            let mut ol = OVERLAPPED {
                hEvent: self.event,
                ..Default::default()
            };

            // Named before the match, which consumes `op`: a read needs its
            // buffer by `&mut`, and casting that away to keep the name would be
            // writing through a shared reference.
            let name = op.name();
            let started = match op {
                Op::Write(buf) => WriteFile(self.handle, Some(buf), None, Some(&mut ol)),
                Op::Read(buf) => ReadFile(self.handle, Some(buf), None, Some(&mut ol)),
            };
            if let Err(source) = started {
                if source.code() != HRESULT::from_win32(ERROR_IO_PENDING.0) {
                    return Err(Error::Io { op: name, source });
                }
            }

            let mut moved: u32 = 0;
            if WaitForSingleObject(self.event, timeout_ms) != WAIT_OBJECT_0 {
                let _ = CancelIoEx(self.handle, Some(&ol));
                // Blocking, deliberately, and not optional: until this returns
                // the kernel may still write to `ol` and to the caller's
                // buffer, and both die with this stack frame.
                return match GetOverlappedResult(self.handle, &ol, &mut moved, true) {
                    // Three outcomes, and they are not the same thing. The
                    // transfer may have finished normally in the window between
                    // the wait expiring and the cancel landing; calling that a
                    // timeout would mean re-sending a write that already went
                    // out, or discarding a reply that did arrive.
                    Ok(()) => Ok(Outcome::Done(moved as usize)),
                    Err(source)
                        if source.code()
                            == HRESULT::from_win32(ERROR_OPERATION_ABORTED.0) =>
                    {
                        Ok(Outcome::TimedOut)
                    }
                    Err(source) => Err(Error::Io { op: name, source }),
                };
            }
            GetOverlappedResult(self.handle, &ol, &mut moved, true)
                .map_err(|source| Error::Io { op: name, source })?;
            Ok(Outcome::Done(moved as usize))
        }
    }
}

/// A transfer that finished, or one that ran out of time. A timeout is not an
/// error here because only the caller knows what it means: for a read inside
/// [`Device::request`] it is simply "nothing yet", for a write it is a fault.
enum Outcome {
    Done(usize),
    TimedOut,
}

enum Op<'a> {
    Write(&'a [u8]),
    Read(&'a mut [u8]),
}

impl Op<'_> {
    fn name(&self) -> &'static str {
        match self {
            Op::Write(_) => "write",
            Op::Read(_) => "read",
        }
    }
}

impl Drop for Device {
    fn drop(&mut self) {
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
