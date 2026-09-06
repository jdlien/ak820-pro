//! Talking to the board, without touching anything that is not the board.
//!
//! Three layers, split so the two that can be tested without hardware are:
//!
//! - [`path`] -- which device-interface paths are ours. Pure string logic; this
//!   is what lets discovery narrow the list **before opening anything**.
//! - [`caps`] -- whether an opened collection is the raw-HID one. Pure.
//! - [`device`] -- the Win32 calls, and the cancellation discipline they need.
//! - [`exchange`] -- the request loop over a narrow [`exchange::Wire`] trait, so
//!   the drain and correlation rules can be tested against a scripted fake
//!   instead of only against a keyboard.

pub mod caps;
pub mod device;
pub mod exchange;
pub mod path;

use crate::proto::Mismatch;

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
#[derive(Debug)]
pub enum Error {
    /// Nothing on this machine names our VID/PID. Unplugged, powered down, or
    /// the slider is not on `cable`.
    Absent,
    /// The same interface appeared more than once, which means more than one of
    /// these keyboards. Refuse and report rather than pick one.
    Ambiguous(Vec<String>),
    /// The Configuration Manager would not produce its own list. Nothing was
    /// opened; this is not a statement about the board.
    Discovery(String),
    /// A path we meant to open would not open. Keeps the OS error so a later
    /// caller can tell a sharing conflict from a vanished device.
    Open {
        path: String,
        source: windows::core::Error,
    },
    /// It opened, and it is not the interface we came for.
    Incompatible {
        path: String,
        why: caps::Reject,
    },
    /// A read or write failed outright.
    Io {
        op: &'static str,
        source: windows::core::Error,
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
                path::VID,
                path::PID
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
