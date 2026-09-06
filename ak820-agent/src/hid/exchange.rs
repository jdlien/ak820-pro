//! The request loop, lifted off Win32 so it can be tested.
//!
//! Finding 9 of [the phase-0 audit] was that none of the tests deterministically
//! exercised the request loop or the cancellation transitions — the two places
//! this crate's correctness actually lives. Everything below therefore talks to
//! a [`Wire`] rather than to a handle, and [`super::device::Device`] is just one
//! implementation of it. The other is [`tests::Fake`], which can be told to
//! produce a late reply, a flood, a short read, or nothing at all.
//!
//! This is not test scaffolding bolted on: the drain rule and the correlate-or-
//! discard rule are the whole safety argument of the transport, and an argument
//! that cannot be exercised is an argument nobody can check.
//!
//! [the phase-0 audit]: ../../../plans/review-codex-phase0-2026-09-06.md

use std::time::{Duration, Instant};

use super::{Drained, Error};
use crate::proto::{self, Channel, REPORT_LEN, Verdict};

/// Bound on the pre-drain, so a chatty peer cannot hold us in the loop.
///
/// ⚠️ Smaller than the driver's 64-report queue on purpose, and that is exactly
/// why [`Queue`] exists: reaching this limit does **not** mean the queue is
/// empty, and a caller that assumed it did would transmit into a queue that can
/// still answer it with something stale.
pub const DRAIN_LIMIT: usize = 32;

/// How long a pre-drain read waits before concluding the queue is empty.
///
/// Not zero, deliberately. A queued report completes almost immediately, but
/// "almost" is not "before we ask", and a zero wait would cancel reads that
/// were about to hand us the very report we are trying to clear.
pub const DRAIN_READ: Duration = Duration::from_millis(1);

/// How long one report may take to leave.
pub const WRITE_TIMEOUT: Duration = Duration::from_millis(1000);

/// Per-read slice of a request's budget.
pub const READ_SLICE: Duration = Duration::from_millis(250);

/// Whether a write actually went out.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Sent {
    Yes,
    TimedOut,
}

/// One report in, one report out — the whole of what the loop needs from a
/// device.
///
/// Deliberately narrow. Everything hard about the Win32 side (overlapped I/O,
/// `CancelIoEx` lifetimes, the stuck-device rule) lives behind these two
/// methods, and everything hard about the *protocol* lives above them.
pub trait Wire {
    fn write_report(&self, data: &[u8], timeout: Duration) -> Result<Sent, Error>;
    /// `Ok(None)` means nothing arrived in time, which is how an empty queue is
    /// distinguished from a full one.
    fn read_report(&self, timeout: Duration) -> Result<Option<Vec<u8>>, Error>;
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

/// A correlated reply, and what had to be thrown away to reach it.
#[derive(Clone, Debug)]
pub struct Reply {
    pub report: [u8; REPORT_LEN],
    pub drained: Vec<Drained>,
}

/// Empty the queue of anything that arrived before we asked, and say whether it
/// actually got empty.
pub fn drain_until(wire: &impl Wire, deadline: Instant) -> (Vec<Drained>, Queue) {
    let mut seen = Vec::new();
    for _ in 0..DRAIN_LIMIT {
        if Instant::now() >= deadline {
            return (seen, Queue::OutOfTime);
        }
        match wire.read_report(DRAIN_READ) {
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

/// Send one command and wait for **its** reply.
///
/// The order of operations is the contract, and each step is there because
/// skipping it produced a real defect:
///
/// 1. **Establish the budget before anything is transmitted.** An expired
///    operation that still writes can set a clock or move the text band after
///    the caller has given up on it.
/// 2. **Drain, and require an empty queue.** A leftover report can carry our own
///    channel and command from an earlier request; nothing in the bytes
///    distinguishes it from a fresh reply.
/// 3. **Write, and tell the caller when.** `on_send` fires between the write
///    completing and the read starting, which is where a clock measurement's
///    `t0` belongs — not before the drain, whose duration is unbounded from the
///    caller's point of view.
/// 4. **Correlate every read**, discarding anything that answered someone else,
///    until the budget runs out.
pub fn exchange(
    wire: &impl Wire,
    channel: Channel,
    command: u8,
    body: &[u8],
    budget: Duration,
    on_send: impl FnOnce(Instant),
) -> Result<Reply, Error> {
    let deadline = Instant::now()
        .checked_add(budget)
        .ok_or(Error::Timeout { drained: Vec::new() })?;
    if budget.is_zero() {
        return Err(Error::Timeout { drained: Vec::new() });
    }

    let (drained, queue) = drain_until(wire, deadline);
    if queue != Queue::Empty {
        return Err(Error::Dirty { queue, drained });
    }

    let left = deadline.saturating_duration_since(Instant::now());
    if left.is_zero() {
        return Err(Error::Timeout { drained });
    }

    let frame = proto::frame(channel, command, body);
    match wire.write_report(&frame, left.min(WRITE_TIMEOUT))? {
        Sent::Yes => on_send(Instant::now()),
        Sent::TimedOut => {
            return Err(Error::Io {
                op: "write",
                source: windows::core::Error::from_hresult(windows::core::HRESULT::from_win32(
                    windows::Win32::Foundation::ERROR_OPERATION_ABORTED.0,
                )),
            })
        }
    }

    collect(wire, channel, command, deadline, drained)
}

/// Read until something answers `(channel, command)` or the deadline passes.
fn collect(
    wire: &impl Wire,
    channel: Channel,
    command: u8,
    deadline: Instant,
    mut drained: Vec<Drained>,
) -> Result<Reply, Error> {
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err(Error::Timeout { drained });
        }
        let Some(buf) = wire.read_report(left.min(READ_SLICE))? else {
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    /// A scripted device. Each `reads` entry is one answer to `read_report`:
    /// `Some(bytes)` is a report, `None` is a timeout, and running off the end
    /// keeps timing out.
    pub struct Fake {
        reads: RefCell<std::collections::VecDeque<Option<Vec<u8>>>>,
        writes: RefCell<Vec<Vec<u8>>>,
        write_result: Sent,
        fail_reads_after: RefCell<Option<usize>>,
        reads_done: RefCell<usize>,
    }

    impl Fake {
        fn new(reads: Vec<Option<Vec<u8>>>) -> Fake {
            Fake {
                reads: RefCell::new(reads.into()),
                writes: RefCell::new(Vec::new()),
                write_result: Sent::Yes,
                fail_reads_after: RefCell::new(None),
                reads_done: RefCell::new(0),
            }
        }
        fn idle() -> Fake {
            Fake::new(vec![])
        }
        fn failing_after(self, n: usize) -> Fake {
            *self.fail_reads_after.borrow_mut() = Some(n);
            self
        }
        fn writes_time_out(mut self) -> Fake {
            self.write_result = Sent::TimedOut;
            self
        }
        fn written(&self) -> Vec<Vec<u8>> {
            self.writes.borrow().clone()
        }
    }

    impl Wire for Fake {
        fn write_report(&self, data: &[u8], _t: Duration) -> Result<Sent, Error> {
            self.writes.borrow_mut().push(data.to_vec());
            Ok(self.write_result)
        }
        fn read_report(&self, _t: Duration) -> Result<Option<Vec<u8>>, Error> {
            let done = {
                let mut d = self.reads_done.borrow_mut();
                *d += 1;
                *d
            };
            if let Some(n) = *self.fail_reads_after.borrow() {
                if done > n {
                    return Err(Error::Stuck);
                }
            }
            Ok(self.reads.borrow_mut().pop_front().flatten())
        }
    }

    /// A wire report: report id 0, then the payload.
    fn report(bytes: &[u8]) -> Option<Vec<u8>> {
        let mut r = vec![0u8; proto::WIRE_LEN];
        r[1..1 + bytes.len()].copy_from_slice(bytes);
        Some(r)
    }

    const INFO_REPLY: &[u8] = &[0x07, 0x11, 0x01, 0x00, 0x85, 0x60, 0x17, 0xCE];
    /// The now-playing agent's echo, measured on this machine.
    const TEXT_ECHO: &[u8] = &[0x07, 0x12, 0x04, 0x00];

    fn budget() -> Duration {
        Duration::from_millis(500)
    }

    // -- the drain contract -----------------------------------------------

    #[test]
    fn an_idle_queue_reports_empty() {
        let (seen, queue) = drain_until(&Fake::idle(), Instant::now() + budget());
        assert!(seen.is_empty());
        assert_eq!(queue, Queue::Empty);
    }

    #[test]
    fn a_queue_that_ends_is_drained_then_empty() {
        let fake = Fake::new(vec![report(TEXT_ECHO), report(TEXT_ECHO), None]);
        let (seen, queue) = drain_until(&fake, Instant::now() + budget());
        assert_eq!(seen.len(), 2);
        assert_eq!(queue, Queue::Empty);
    }

    /// ⚠️ Finding 2 of the audit, made testable. The driver holds 64 reports and
    /// the drain gives up at 32, so this is not a hypothetical bound.
    #[test]
    fn a_queue_longer_than_the_drain_limit_is_reported_as_more_waiting() {
        let fake = Fake::new(vec![report(TEXT_ECHO); DRAIN_LIMIT + 1]);
        let (seen, queue) = drain_until(&fake, Instant::now() + budget());
        assert_eq!(seen.len(), DRAIN_LIMIT);
        assert_eq!(queue, Queue::MoreWaiting, "must NOT claim the queue is empty");
    }

    #[test]
    fn a_failing_read_leaves_the_queue_unestablished() {
        let fake = Fake::new(vec![report(TEXT_ECHO)]).failing_after(1);
        let (_, queue) = drain_until(&fake, Instant::now() + budget());
        assert_eq!(queue, Queue::Unreadable);
    }

    #[test]
    fn an_expired_deadline_stops_the_drain() {
        let fake = Fake::new(vec![report(TEXT_ECHO); 100]);
        let (seen, queue) = drain_until(&fake, Instant::now());
        assert!(seen.is_empty());
        assert_eq!(queue, Queue::OutOfTime);
    }

    // -- the request contract ---------------------------------------------

    #[test]
    fn a_clean_exchange_returns_the_reply() {
        let fake = Fake::new(vec![None, report(INFO_REPLY)]);
        let reply = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
        assert!(reply.drained.is_empty());
        assert_eq!(fake.written().len(), 1);
    }

    /// The measured broadcast hazard, driven end to end: someone else's reply
    /// arrives between our write and ours, and must not be taken as the answer.
    #[test]
    fn a_foreign_reply_is_discarded_and_the_wait_continues() {
        let fake = Fake::new(vec![
            None,                 // drain: queue is empty
            report(TEXT_ECHO),    // then someone else's traffic
            report(TEXT_ECHO),
            report(INFO_REPLY),   // finally ours
        ]);
        let reply = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
        assert_eq!(reply.drained.len(), 2, "both foreign reports must be recorded");
        assert!(matches!(reply.drained[0], Drained::Foreign(_)));
    }

    /// ⚠️ The finding-2 scenario in full: a stale reply carrying **our own**
    /// channel and command sits behind more reports than the drain will clear.
    /// Nothing in its bytes distinguishes it from a fresh answer, so the only
    /// defence is refusing to transmit at all.
    #[test]
    fn a_stale_reply_behind_a_full_queue_is_never_transmitted_into() {
        let mut reads = vec![report(TEXT_ECHO); DRAIN_LIMIT];
        reads.push(report(INFO_REPLY)); // the stale one, still queued
        let fake = Fake::new(reads);

        let err = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
        assert!(
            matches!(err, Error::Dirty { queue: Queue::MoreWaiting, .. }),
            "expected a refusal, got {err:?}"
        );
        assert!(
            fake.written().is_empty(),
            "a request that cannot start clean must not reach the wire"
        );
    }

    /// Finding 7: an expired budget must not change the board.
    #[test]
    fn a_zero_budget_transmits_nothing() {
        let fake = Fake::idle();
        let err = exchange(&fake, Channel::Text, 0x01, &[], Duration::ZERO, |_| {}).unwrap_err();
        assert!(matches!(err, Error::Timeout { .. }));
        assert!(fake.written().is_empty(), "nothing may go out after the budget");
    }

    #[test]
    fn an_unrepresentable_budget_is_refused_rather_than_panicking() {
        let fake = Fake::idle();
        let err = exchange(&fake, Channel::Text, 0x01, &[], Duration::MAX, |_| {}).unwrap_err();
        assert!(matches!(err, Error::Timeout { .. }));
        assert!(fake.written().is_empty());
    }

    #[test]
    fn silence_after_the_write_is_a_timeout_naming_what_was_discarded() {
        let fake = Fake::new(vec![None, report(TEXT_ECHO)]);
        let err = exchange(
            &fake,
            Channel::Flash,
            0x01,
            &[],
            Duration::from_millis(30),
            |_| {},
        )
        .unwrap_err();
        match err {
            Error::Timeout { drained } => {
                assert_eq!(drained.len(), 1, "the foreign report must be reported");
            }
            other => panic!("expected a timeout, got {other:?}"),
        }
        assert_eq!(fake.written().len(), 1, "the command did go out");
    }

    #[test]
    fn a_write_that_times_out_is_an_io_error_not_a_silent_success() {
        let fake = Fake::idle().writes_time_out();
        let err = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
        assert!(matches!(err, Error::Io { op: "write", .. }), "{err:?}");
    }

    /// Our own command refused by the firmware stops the wait; retrying cannot
    /// help.
    #[test]
    fn our_own_unhandled_reply_ends_the_exchange() {
        let fake = Fake::new(vec![None, report(&[0xFF, 0x11, 0x01])]);
        let err = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
        assert!(matches!(
            err,
            Error::Unhandled {
                channel: 0x11,
                command: 0x01
            }
        ));
    }

    /// ... but somebody else's refused command is just more noise.
    #[test]
    fn a_foreign_unhandled_reply_does_not_end_the_exchange() {
        let fake = Fake::new(vec![
            None,
            report(&[0xFF, 0x12, 0x03]),
            report(INFO_REPLY),
        ]);
        let reply = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
    }

    /// ⚠️ The timestamp placement finding 3 is about: `on_send` must fire after
    /// the drain and before the read, or a clock measurement brackets the wrong
    /// interval.
    #[test]
    fn on_send_fires_between_the_drain_and_the_read() {
        let fake = Fake::new(vec![report(TEXT_ECHO), None, report(INFO_REPLY)]);
        let before = Instant::now();
        let mut sent_at = None;
        exchange(&fake, Channel::Flash, 0x01, &[], budget(), |t| sent_at = Some(t)).unwrap();
        let sent_at = sent_at.expect("on_send must fire on a successful write");
        assert!(sent_at >= before);
        assert!(sent_at <= Instant::now());
    }

    #[test]
    fn on_send_never_fires_when_nothing_was_transmitted() {
        let fake = Fake::new(vec![report(TEXT_ECHO); DRAIN_LIMIT + 1]);
        let mut fired = false;
        let _ = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| fired = true);
        assert!(!fired, "a refused request has no transmission instant");
    }

    /// A truncated report is noise, not a short answer.
    #[test]
    fn a_short_read_is_discarded_rather_than_decoded() {
        let fake = Fake::new(vec![None, Some(vec![0x00, 0x07, 0x11]), report(INFO_REPLY)]);
        let reply = exchange(&fake, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
        assert_eq!(reply.drained.len(), 1);
    }

    /// The command really is framed the way the firmware parses it.
    #[test]
    fn the_transmitted_frame_is_the_protocols_frame() {
        let fake = Fake::new(vec![None, report(INFO_REPLY)]);
        exchange(&fake, Channel::Text, 0x03, &[0x01, 0x02], budget(), |_| {}).unwrap_err();
        let sent = &fake.written()[0];
        assert_eq!(sent.len(), proto::WIRE_LEN);
        assert_eq!(&sent[..6], &[0x00, 0x07, 0x12, 0x03, 0x01, 0x02]);
    }
}
