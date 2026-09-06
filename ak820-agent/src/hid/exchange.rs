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
    /// A cancellation refused to land, so the device is abandoned.
    ///
    /// ⚠️ Distinct from [`Queue::Unreadable`] on purpose. Collapsing the two
    /// loses [`Error::Stuck`], and a caller that reopens on any failure would
    /// then abandon a fresh buffer, event and handle on **every** cycle rather
    /// than once — the phase-1 audit's finding 4. Sticky, and reopening is not
    /// a remedy for it.
    Stuck,
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
            Queue::Stuck => write!(f, "belongs to an abandoned handle"),
        }
    }
}

/// A correlated reply, and what had to be thrown away to reach it.
#[derive(Clone, Debug)]
pub struct Reply {
    pub report: [u8; REPORT_LEN],
    pub drained: Vec<Drained>,
}

/// How long a resynchronisation waits for a late reply to show up.
///
/// Generously more than the 5–18 ms round trip measured on this board, because
/// the cost of waiting is one pause on a path that only runs after something
/// already went wrong, and the cost of not waiting is taking a stale sample.
pub const RESYNC_SETTLE: Duration = Duration::from_millis(250);

/// A command that was **transmitted and never answered**.
///
/// ⚠️ Finding 3 of the phase-1 audit, and the half of finding 2 that refusing a
/// dirty queue does not cover. Cancelling our host-side read does not cancel
/// the firmware's command: the board will still answer it, whenever it gets
/// round to it. So this sequence loses:
///
/// 1. `GET` A is transmitted and times out.
/// 2. `GET` B's pre-drain observes an empty queue — truthfully; A's reply has
///    not arrived yet.
/// 3. B is transmitted.
/// 4. A's reply arrives and satisfies B's channel and command exactly.
///
/// B then gets A's board sample against B's timestamps. There is nothing in the
/// bytes to catch it, so the only defence is remembering that A is unaccounted
/// for and refusing to ask the same question again until it is.
///
/// Per handle, and `Cell` rather than an atomic because a handle is
/// deliberately owned by one thread.
#[derive(Default, Debug)]
pub struct Outstanding(std::cell::Cell<Option<(u8, u8)>>);

impl Outstanding {
    pub fn new() -> Outstanding {
        Outstanding::default()
    }

    /// The command that is unaccounted for, if any.
    pub fn get(&self) -> Option<(u8, u8)> {
        self.0.get()
    }

    fn note(&self, channel: Channel, command: u8) {
        self.0.set(Some((channel.id(), command)));
    }

    fn clear(&self) {
        self.0.set(None);
    }

    /// Would a reply to this command be confusable with the outstanding one?
    fn conflicts(&self, channel: Channel, command: u8) -> bool {
        self.0.get() == Some((channel.id(), command))
    }
}

/// Account for an unanswered command, so the handle can be used again.
///
/// Drains, waits [`RESYNC_SETTLE`] for a straggler, then drains again, and
/// requires **both** passes to end with an empty queue. Anything discarded is
/// returned, because a late reply arriving here is the evidence that the
/// refusal was doing real work.
///
/// This is deliberately a separate, explicit step rather than something
/// `exchange` does quietly: a caller that has just lost a measurement should
/// decide whether to spend a quarter second recovering, and a clock scheduler
/// wants to know it happened.
pub fn resynchronise(
    wire: &impl Wire,
    outstanding: &Outstanding,
    budget: Duration,
) -> Result<Vec<Drained>, Error> {
    let deadline = Instant::now()
        .checked_add(budget)
        .ok_or(Error::Timeout { drained: Vec::new() })?;

    let (mut seen, queue) = drain_until(wire, deadline);
    if queue == Queue::Stuck {
        return Err(Error::Stuck);
    }
    if queue != Queue::Empty {
        return Err(Error::Dirty { queue, drained: seen });
    }

    // Give the board time to produce the straggler, then check again.
    let settle = RESYNC_SETTLE.min(deadline.saturating_duration_since(Instant::now()));
    std::thread::sleep(settle);

    let (more, queue) = drain_until(wire, deadline);
    seen.extend(more);
    match queue {
        Queue::Empty => {
            outstanding.clear();
            Ok(seen)
        }
        Queue::Stuck => Err(Error::Stuck),
        _ => Err(Error::Dirty { queue, drained: seen }),
    }
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
            // Stuck is preserved rather than flattened: it is the one read
            // failure that reopening cannot fix.
            Err(Error::Stuck) => return (seen, Queue::Stuck),
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
/// 3. **Write, and tell the caller when.** `on_send` fires immediately before
///    the write, matching where `ak820ctl` takes `t0` — after the drain, whose
///    duration is unbounded from the caller's point of view, and not after the
///    write, which would shift every offset relative to the oracle.
/// 4. **Correlate every read**, discarding anything that answered someone else,
///    until the budget runs out.
pub fn exchange(
    wire: &impl Wire,
    outstanding: &Outstanding,
    channel: Channel,
    command: u8,
    body: &[u8],
    budget: Duration,
    on_send: impl FnOnce(Instant),
) -> Result<Reply, Error> {
    // ⚠️ Before anything else: has this exact question already been asked and
    // left unanswered? If so its reply is still coming, and it would satisfy
    // this request's matcher perfectly. See `Outstanding`.
    if outstanding.conflicts(channel, command) {
        return Err(Error::Unresolved {
            channel: channel.id(),
            command,
        });
    }
    let deadline = Instant::now()
        .checked_add(budget)
        .ok_or(Error::Timeout { drained: Vec::new() })?;
    if budget.is_zero() {
        return Err(Error::Timeout { drained: Vec::new() });
    }

    let (drained, queue) = drain_until(wire, deadline);
    match queue {
        Queue::Empty => {}
        // An abandoned handle is not a dirty queue; it is a dead device, and
        // saying so is what stops a caller reopening in a loop.
        Queue::Stuck => return Err(Error::Stuck),
        _ => return Err(Error::Dirty { queue, drained }),
    }

    let left = deadline.saturating_duration_since(Instant::now());
    if left.is_zero() {
        return Err(Error::Timeout { drained });
    }

    let frame = proto::frame(channel, command, body);
    // ⚠️ **Before** the write, not after it, and this is parity rather than
    // preference. `ak820ctl` takes `t0` immediately before `hid_write` and `t1`
    // after the read returns, then uses the midpoint. Timestamping write
    // *completion* instead would be arguably closer to the moment of
    // transmission — and would shift every offset this port produces relative
    // to the oracle by half the write, straight into the lead learner. A
    // deliberate improvement to the measurement is a separate change from
    // reproducing it.
    on_send(Instant::now());
    // From here on the board has the command, whatever happens to our read, so
    // the handle owes an answer until one arrives.
    outstanding.note(channel, command);
    match wire.write_report(&frame, left.min(WRITE_TIMEOUT))? {
        Sent::Yes => {}
        Sent::TimedOut => {
            // Cancelled before it left, so nothing is owed. Treating a write
            // that never went out as outstanding would refuse the next attempt
            // for no reason.
            outstanding.clear();
            return Err(Error::Io {
                op: "write",
                source: windows::core::Error::from_hresult(windows::core::HRESULT::from_win32(
                    windows::Win32::Foundation::ERROR_OPERATION_ABORTED.0,
                )),
            });
        }
    }

    let answered = collect(wire, channel, command, deadline, drained);
    if answered.is_ok() {
        outstanding.clear();
    }
    answered
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
        fail_with_stuck: RefCell<bool>,
        reads_done: RefCell<usize>,
    }

    impl Fake {
        fn new(reads: Vec<Option<Vec<u8>>>) -> Fake {
            Fake {
                reads: RefCell::new(reads.into()),
                writes: RefCell::new(Vec::new()),
                write_result: Sent::Yes,
                fail_reads_after: RefCell::new(None),
                fail_with_stuck: RefCell::new(false),
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
        /// Fail with the one error reopening cannot fix.
        fn stuck_after(self, n: usize) -> Fake {
            *self.fail_reads_after.borrow_mut() = Some(n);
            *self.fail_with_stuck.borrow_mut() = true;
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
                    return Err(if *self.fail_with_stuck.borrow() {
                        Error::Stuck
                    } else {
                        Error::Io {
                            op: "read",
                            source: windows::core::Error::from_hresult(
                                windows::core::HRESULT(-1),
                            ),
                        }
                    });
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

    /// ⚠️ Finding 4 of the phase-1 audit: a stuck cancellation must not be
    /// flattened into a generic read failure. A caller that reopens on any
    /// failure would otherwise abandon a fresh buffer, event and handle on
    /// every cycle, rather than once.
    #[test]
    fn an_abandoned_handle_is_distinguishable_from_a_bad_read() {
        let fake = Fake::idle().stuck_after(0);
        let (_, queue) = drain_until(&fake, Instant::now() + budget());
        assert_eq!(queue, Queue::Stuck, "must not collapse into Unreadable");

        let fake = Fake::idle().stuck_after(0);
        let err = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
        assert!(
            matches!(err, Error::Stuck),
            "a dead device is not a dirty queue: {err:?}"
        );
        assert!(fake.written().is_empty());
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
        let reply = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
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
        let reply = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
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

        let err = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
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
        let err = exchange(&fake, &Outstanding::new(), Channel::Text, 0x01, &[], Duration::ZERO, |_| {}).unwrap_err();
        assert!(matches!(err, Error::Timeout { .. }));
        assert!(fake.written().is_empty(), "nothing may go out after the budget");
    }

    #[test]
    fn an_unrepresentable_budget_is_refused_rather_than_panicking() {
        let fake = Fake::idle();
        let err = exchange(&fake, &Outstanding::new(), Channel::Text, 0x01, &[], Duration::MAX, |_| {}).unwrap_err();
        assert!(matches!(err, Error::Timeout { .. }));
        assert!(fake.written().is_empty());
    }

    #[test]
    fn silence_after_the_write_is_a_timeout_naming_what_was_discarded() {
        let fake = Fake::new(vec![None, report(TEXT_ECHO)]);
        let err = exchange(
            &fake,
            &Outstanding::new(),
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
        let err = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
        assert!(matches!(err, Error::Io { op: "write", .. }), "{err:?}");
    }

    /// Our own command refused by the firmware stops the wait; retrying cannot
    /// help.
    #[test]
    fn our_own_unhandled_reply_ends_the_exchange() {
        let fake = Fake::new(vec![None, report(&[0xFF, 0x11, 0x01])]);
        let err = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap_err();
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
        let reply = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
    }

    /// ⚠️ What timestamp placement (finding 3) is about: `on_send` must fire
    /// after the drain — whose duration the caller cannot see — and before the
    /// write, which is where `ak820ctl` takes `t0`. A caller that brackets the
    /// drain measures an interval whose midpoint is not the transmission
    /// midpoint, and reports a false offset of half the drain.
    #[test]
    fn on_send_fires_after_the_drain_and_before_the_write() {
        // A drain with something in it, so the two instants are separable.
        let fake = Fake::new(vec![report(TEXT_ECHO), None, report(INFO_REPLY)]);
        let entered = Instant::now();
        let mut sent_at = None;
        exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |t| sent_at = Some(t)).unwrap();
        let sent_at = sent_at.expect("on_send must fire when a command goes out");
        assert!(sent_at >= entered);
        assert!(sent_at <= Instant::now());
    }

    /// The write is issued after the callback, so a caller's `t0` cannot
    /// include it. Ordering is asserted through the fake rather than by
    /// reading the code.
    #[test]
    fn nothing_is_written_before_on_send_fires() {
        let fake = Fake::new(vec![None, report(INFO_REPLY)]);
        let mut written_when_called = None;
        exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {
            written_when_called = Some(fake.written().len());
        })
        .unwrap();
        assert_eq!(
            written_when_called,
            Some(0),
            "the command must still be unsent when the caller takes t0"
        );
    }

    #[test]
    fn on_send_never_fires_when_nothing_was_transmitted() {
        let fake = Fake::new(vec![report(TEXT_ECHO); DRAIN_LIMIT + 1]);
        let mut fired = false;
        let _ = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| fired = true);
        assert!(!fired, "a refused request has no transmission instant");
    }

    /// ⚠️ Finding 3 of the phase-1 audit, reproduced. This is the sequence the
    /// exhausted-drain refusal does **not** catch, because at step 2 the queue
    /// genuinely is empty — the late reply simply has not arrived yet.
    #[test]
    fn a_late_reply_cannot_answer_the_next_identical_request() {
        let outstanding = Outstanding::new();

        // 1. GET A goes out and times out with nothing to show for it.
        let a = Fake::new(vec![None]);
        let err = exchange(
            &a,
            &outstanding,
            Channel::Rtc,
            0x02,
            &[],
            Duration::from_millis(20),
            |_| {},
        )
        .unwrap_err();
        assert!(matches!(err, Error::Timeout { .. }));
        assert_eq!(
            outstanding.get(),
            Some((0x10, 0x02)),
            "the board still owes an answer to a command it received"
        );

        // 2-4. GET B would find an empty queue, transmit, and be satisfied by
        // A's straggler. It must be refused before any of that.
        let b = Fake::new(vec![None, report(&[0x07, 0x10, 0x02, 0x01])]);
        let err = exchange(&b, &outstanding, Channel::Rtc, 0x02, &[], budget(), |_| {}).unwrap_err();
        assert!(
            matches!(err, Error::Unresolved { channel: 0x10, command: 0x02 }),
            "expected a refusal, got {err:?}"
        );
        assert!(
            b.written().is_empty(),
            "nothing may go out while an identical question is unanswered"
        );
    }

    /// A different question is not confusable with the outstanding one, so it
    /// is allowed through — refusing everything would make one lost reply
    /// disable the whole handle.
    #[test]
    fn an_unrelated_command_is_still_allowed() {
        let outstanding = Outstanding::new();
        let a = Fake::new(vec![None]);
        let _ = exchange(
            &a,
            &outstanding,
            Channel::Rtc,
            0x02,
            &[],
            Duration::from_millis(20),
            |_| {},
        );
        assert!(outstanding.get().is_some());

        let b = Fake::new(vec![None, report(INFO_REPLY)]);
        let reply = exchange(&b, &outstanding, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
    }

    /// Resynchronising accounts for the straggler and reopens the handle to the
    /// question it was refusing.
    #[test]
    fn resynchronising_clears_the_debt_and_reports_what_arrived() {
        let outstanding = Outstanding::new();
        let a = Fake::new(vec![None]);
        let _ = exchange(
            &a,
            &outstanding,
            Channel::Rtc,
            0x02,
            &[],
            Duration::from_millis(20),
            |_| {},
        );

        // The straggler turns up during the settle, then the queue is empty.
        let late = Fake::new(vec![None, report(&[0x07, 0x10, 0x02, 0x01]), None]);
        let seen = resynchronise(&late, &outstanding, Duration::from_secs(2)).unwrap();
        assert_eq!(seen.len(), 1, "the late reply is evidence, not noise");
        assert_eq!(outstanding.get(), None);

        let b = Fake::new(vec![None, report(&[0x07, 0x10, 0x02, 0x09])]);
        assert!(exchange(&b, &outstanding, Channel::Rtc, 0x02, &[], budget(), |_| {}).is_ok());
    }

    /// A resync that cannot establish a clean queue leaves the debt in place
    /// rather than clearing it hopefully.
    #[test]
    fn a_failed_resync_does_not_clear_the_debt() {
        let outstanding = Outstanding::new();
        let a = Fake::new(vec![None]);
        let _ = exchange(
            &a,
            &outstanding,
            Channel::Rtc,
            0x02,
            &[],
            Duration::from_millis(20),
            |_| {},
        );

        let noisy = Fake::new(vec![report(TEXT_ECHO); DRAIN_LIMIT + 1]);
        assert!(resynchronise(&noisy, &outstanding, Duration::from_secs(2)).is_err());
        assert_eq!(
            outstanding.get(),
            Some((0x10, 0x02)),
            "an unproven queue does not settle a debt"
        );
    }

    /// A successful exchange owes nothing afterwards.
    #[test]
    fn a_completed_exchange_leaves_no_debt() {
        let outstanding = Outstanding::new();
        let fake = Fake::new(vec![None, report(INFO_REPLY)]);
        exchange(&fake, &outstanding, Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(outstanding.get(), None);
    }

    /// A write that never left owes nothing either — the board never saw it.
    #[test]
    fn a_write_that_never_left_owes_nothing() {
        let outstanding = Outstanding::new();
        let fake = Fake::idle().writes_time_out();
        let _ = exchange(&fake, &outstanding, Channel::Flash, 0x01, &[], budget(), |_| {});
        assert_eq!(outstanding.get(), None);
    }

    /// A truncated report is noise, not a short answer.
    #[test]
    fn a_short_read_is_discarded_rather_than_decoded() {
        let fake = Fake::new(vec![None, Some(vec![0x00, 0x07, 0x11]), report(INFO_REPLY)]);
        let reply = exchange(&fake, &Outstanding::new(), Channel::Flash, 0x01, &[], budget(), |_| {}).unwrap();
        assert_eq!(&reply.report[..8], INFO_REPLY);
        assert_eq!(reply.drained.len(), 1);
    }

    /// The command really is framed the way the firmware parses it.
    #[test]
    fn the_transmitted_frame_is_the_protocols_frame() {
        let fake = Fake::new(vec![None, report(INFO_REPLY)]);
        exchange(&fake, &Outstanding::new(), Channel::Text, 0x03, &[0x01, 0x02], budget(), |_| {}).unwrap_err();
        let sent = &fake.written()[0];
        assert_eq!(sent.len(), proto::WIRE_LEN);
        assert_eq!(&sent[..6], &[0x00, 0x07, 0x12, 0x03, 0x01, 0x02]);
    }
}
