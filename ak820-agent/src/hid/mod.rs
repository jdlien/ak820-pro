//! Talking to the board, without touching anything that is not the board.
//!
//! Three layers, split so the two that can be tested without hardware are:
//!
//! - [`path`] -- which device-interface paths are ours. Pure string logic; this
//!   is what lets discovery narrow the list **before opening anything**.
//! - [`caps`] -- whether an opened collection is the raw-HID one. Pure.
//! - [`device`] -- the Win32 calls, and the cancellation discipline they need.

pub mod caps;
pub mod device;
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
    /// before our request, whatever it contains.
    Stale { channel: u8, command: u8 },
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
        }
    }
}

impl std::error::Error for Error {}
