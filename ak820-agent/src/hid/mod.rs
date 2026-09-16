//! Talking to the board, without touching anything that is not the board.
//!
//! The platform-neutral half. What is here is the whole protocol-level safety
//! argument, and it is tested without hardware:
//!
//! - [`exchange`] -- the request loop over a narrow [`exchange::Wire`] trait, so
//!   the drain and correlation rules can be tested against a scripted fake
//!   instead of only against a keyboard.
//! - [`HidTransport`] -- everything a caller asks of an opened board, as
//!   default methods over `Wire`, so a platform supplies only the two raw
//!   report calls and its unanswered-command ledger.
//!
//! The platform halves -- discovery that opens nothing, the open itself, and
//! the transfer with its cancellation discipline -- live under
//! `crate::platform`.

pub mod exchange;

use std::time::{Duration, Instant};

use crate::proto::{Channel, Mismatch};
use exchange::{Outstanding, Queue, Reply, Wire};

/// The board's USB identity: SONiX vendor, the QMK build's product id.
pub const VID: u16 = 0x0C45;
pub const PID: u16 = 0x8009;
/// The raw-HID collection's usage page and usage.
pub const USAGE_PAGE: u16 = 0xFF60;
pub const USAGE: u16 = 0x61;

/// An operating-system error, carried as data so this module names no
/// platform's error type.
///
/// Built from the platform's own error at the boundary, with `message` set to
/// that error's own `Display` text, so a log line reads exactly as it did when
/// this field was a `windows::core::Error`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OsError {
    pub code: i64,
    pub message: String,
}

impl OsError {
    pub fn new(code: i64, message: impl Into<String>) -> OsError {
        OsError { code, message: message.into() }
    }
}

impl std::fmt::Display for OsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for OsError {}

/// An opened board: two raw report calls (the [`Wire`] supertrait) and a
/// ledger of commands sent and never answered. Everything else a caller does
/// with a board is a default method here, over the tested request loop.
pub trait HidTransport: Wire + Sized {
    /// This handle's accounting of unanswered commands, for code that drives
    /// [`exchange`] directly — a whole transaction — rather than one request
    /// at a time through the methods below.
    fn outstanding(&self) -> &Outstanding;

    /// Send one command and wait for **its** reply.
    ///
    /// ⚠️ The loop is the point. Input reports reach every open handle, on
    /// Windows and (measured in S2) between non-seizing IOKit clients on
    /// macOS, so a read can return VIA's answer, or another process's text
    /// echo, or our own echo from an earlier command on another channel. Each
    /// of those is discarded and the wait continues; only a report naming this
    /// channel and command ends it.
    fn request(&self, channel: Channel, command: u8, body: &[u8], budget: Duration) -> Result<Reply, Error> {
        exchange::exchange(self, self.outstanding(), channel, command, body, budget, |_| {})
    }

    /// As [`HidTransport::request`], but the caller is handed the instant the
    /// command actually went onto the wire.
    ///
    /// ⚠️ This exists because the clock contract cannot be expressed without
    /// it. `t0; request(GET); t1` measures the **pre-drain** as well as the
    /// round trip, and the drain is unbounded from the caller's point of view:
    /// a VIA flood can make it several milliseconds. The midpoint of that wider
    /// interval is not the transmission midpoint, so the offset it yields is
    /// wrong by half the drain -- silently, and in the direction that looks
    /// like a real clock error. Finding 3 of the phase-0 audit.
    fn request_at(
        &self,
        channel: Channel,
        command: u8,
        body: &[u8],
        budget: Duration,
        on_send: impl FnOnce(Instant),
    ) -> Result<Reply, Error> {
        exchange::exchange(self, self.outstanding(), channel, command, body, budget, on_send)
    }

    /// As [`HidTransport::request_at`], but the body is built inside the call,
    /// after the drain and immediately before the write — see
    /// [`exchange::exchange_prepared`]. The clock SET needs this: the timestamp
    /// it carries has to be taken as late as possible.
    fn request_prepared(
        &self,
        channel: Channel,
        command: u8,
        budget: Duration,
        prepare: impl FnOnce(Instant) -> Vec<u8>,
    ) -> Result<Reply, Error> {
        exchange::exchange_prepared(self, self.outstanding(), channel, command, budget, prepare)
    }

    /// As [`HidTransport::request`], for a command the firmware answers by
    /// echoing the request: the reply must carry `body` back, or it is another
    /// request's echo and is drained. See [`exchange::exchange_matched`].
    fn request_echoed(&self, channel: Channel, command: u8, body: &[u8], budget: Duration) -> Result<Reply, Error> {
        exchange::exchange_matched(self, self.outstanding(), channel, command, budget, Some(body), |_| {
            body.to_vec()
        })
    }

    /// Empty the driver's queue, and say whether it actually got empty.
    fn drain_until(&self, deadline: Instant) -> (Vec<Drained>, Queue) {
        exchange::drain_until(self, deadline)
    }

    /// Drain with the default allowance, for callers with no deadline of their
    /// own.
    fn drain(&self) -> (Vec<Drained>, Queue) {
        self.drain_until(Instant::now() + exchange::DRAIN_BUDGET)
    }

    /// Every command this handle transmitted and never got an answer to,
    /// oldest first.
    ///
    /// While one is listed, asking that question again is refused: the old
    /// reply is still owed and would be indistinguishable from the new one.
    /// Only [`HidTransport::resynchronise`] retires them.
    fn unanswered(&self) -> Vec<(u8, u8)> {
        self.outstanding().all()
    }

    /// Account for an unanswered command so the handle can be used again.
    fn resynchronise(&self, budget: Duration) -> Result<Vec<Drained>, Error> {
        exchange::resynchronise(self, self.outstanding(), budget)
    }
}

/// A report thrown away on the way to an answer, and why.
///
/// Kept rather than silently dropped, and the two cases kept apart, because
/// they mean different things about the machine. A `Foreign` report is the
/// measured broadcast hazard firing live -- another process's reply arriving on
/// our handle between our write and our read. A `Stale` one only says the queue
/// was not empty when we started.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Drained {
    /// Already queued when we wrote, so it answers something that happened
    /// before our request, whatever it contains. Raw first three bytes, for
    /// the reason [`Mismatch::NotOurs`] gives: a foreign report's bytes are
    /// not a channel and a command.
    Stale { header: [u8; 3] },
    /// Queued before our write, and not one of our reports at all.
    StaleUnreadable(Mismatch),
    /// Arrived while we were waiting, and answered someone else.
    Foreign(Mismatch),
}

/// Everything that can go wrong between "is the keyboard there" and "here is
/// its answer".
///
/// The variants are deliberately finer-grained than the code needs today,
/// because [`plans/AK820-AGENT-PLAN.md`] requires presence to be a state
/// machine rather than a boolean: **an unsuccessful open is not absence**.
/// Collapsing "busy" into "gone" is what clears the clock learner's continuity
/// and then manufactures a spurious sync when access returns.
///
/// [`plans/AK820-AGENT-PLAN.md`]: https://github.com/jdlien/ak820-pro
#[derive(Debug, Clone)]
pub enum Error {
    /// Nothing on this machine names our VID/PID. Unplugged, powered down, or
    /// the slider is not on `cable`.
    Absent,
    /// The same interface appeared more than once, which means more than one of
    /// these keyboards. Refuse and report rather than pick one.
    Ambiguous(Vec<String>),
    /// The platform would not produce its own device list (the Configuration
    /// Manager, the IORegistry). Nothing was opened; this is not a statement
    /// about the board.
    Discovery(String),
    /// A path we meant to open would not open. Keeps the OS error so a later
    /// caller can tell a sharing conflict from a vanished device.
    Open {
        path: String,
        source: OsError,
    },
    /// It opened, and it is not the interface we came for. `why` is the
    /// platform's own account of the mismatch, already rendered.
    Incompatible {
        path: String,
        why: String,
    },
    /// A read or write failed outright.
    Io {
        op: &'static str,
        source: OsError,
    },
    /// The budget ran out with no correlated reply. `drained` is what did
    /// arrive, which is the difference between a silent board and a busy line.
    Timeout { drained: Vec<Drained> },
    /// The firmware answered, naming our own command, and said it does not
    /// handle it. Retrying cannot help; this is a version mismatch.
    Unhandled { channel: u8, command: u8 },
    /// The driver's queue could not be established as empty, so the request was
    /// **not sent**.
    ///
    /// ⚠️ Refusing is the point. A leftover report can carry our own channel
    /// and command from an earlier request, and there is nothing in the bytes
    /// to tell it from a fresh reply — so sending anyway risks answering a new
    /// question with an old measurement.
    Dirty {
        queue: exchange::Queue,
        drained: Vec<Drained>,
    },
    /// The same command was transmitted earlier and never answered, so its
    /// reply is still owed and would be indistinguishable from this one's.
    ///
    /// Call `resynchronise` to account for it. Refusing is the point: see
    /// [`exchange::Outstanding`].
    Unresolved { channel: u8, command: u8 },
    /// A cancellation did not complete inside its grace period, so this device
    /// has an operation the kernel still owns. Its buffer, event and handle are
    /// leaked deliberately and it can never be used again.
    Stuck,
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Absent => write!(
                f,
                "no AK820 Pro ({:04X}:{:04X}) is present -- check the cable and that the \
                 slider is on `cable`",
                VID,
                PID
            ),
            Error::Ambiguous(paths) => {
                write!(f, "{} matching interfaces, so more than one of these keyboards is attached; refusing to guess:", paths.len())?;
                for p in paths {
                    write!(f, "\n  {p}")?;
                }
                Ok(())
            }
            Error::Discovery(why) => write!(f, "could not list HID interfaces: {why}"),
            Error::Open { path, source } => write!(f, "could not open {path}: {source}"),
            Error::Incompatible { path, why } => write!(f, "{path}: {why}"),
            Error::Io { op, source } => write!(f, "HID {op} failed: {source}"),
            Error::Timeout { drained } if drained.is_empty() => {
                write!(f, "no reply from the keyboard")
            }
            Error::Timeout { drained } => write!(
                f,
                "no reply from the keyboard; {} report(s) arrived that answered someone else \
                 ({drained:?})",
                drained.len()
            ),
            Error::Unhandled { channel, command } => write!(
                f,
                "the firmware does not handle command {command:#04X} on channel {channel:#04X} \
                 -- flashed from a different tree?"
            ),
            Error::Dirty { queue, drained } => write!(
                f,
                "not sent: the reply queue {queue} after discarding {} report(s), so a stale \
                 reply could have answered it",
                drained.len()
            ),
            Error::Unresolved { channel, command } => write!(
                f,
                "command {command:#04X} on channel {channel:#04X} was sent earlier and never                  answered; its reply would be indistinguishable from this one's, so the handle                  must be resynchronised first"
            ),
            Error::Stuck => write!(
                f,
                "a cancelled HID operation never completed; this handle is abandoned"
            ),
        }
    }
}

impl std::error::Error for Error {}
