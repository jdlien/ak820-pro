//! When the lock-LED channel sends a clock frame, type 4 (the plan's "The
//! wireless clock", C3, and codex's review of it): pure, on instants the
//! caller gives, so the sender's thread only asks it.
//!
//! Precedence (review, 11):
//! - After an acquisition: past the media handover, and past the board's
//!   own refusal window after this process's last USB clock sync
//!   ([`OWNER_FLOOR`], the board's window and its slow sleep), whichever is later: a frame inside that
//!   window is refused by the board and wastes ten minutes (review, 9).
//! - Then every [`EVERY`] after the last frame sent whole.
//! - At the wake guess, a frame after [`WAKE_DELAY`](super::sender::WAKE_DELAY),
//!   but never sooner than [`MIN_GAP`] after the last sent.
//! - None while the host's input has been idle
//!   [`HOLD_IDLE`](super::sender::HOLD_IDLE) or more (the sender's hold, as
//!   for text and transport): the board on battery is likely asleep, losing
//!   it, one begun later could run into Lights out's sleep at 60 s, and one
//!   that is awake would hold its deep sleep off through the slew a
//!   correction starts (20 ms a second; the Mac session, 10-20). A frame
//!   held so goes at the wake guess.
//! - A change of the host's UTC offset (DST, a zone change) or a step of its
//!   wall clock against the monotonic one: a frame at once, exempt from the
//!   gap (review, 7).
//! - A frame lost to chance (a deadline, the user's locks) goes again at
//!   once; a failed write after [`RETRY`]. A frame abandoned mid-way may
//!   still have reached the board: harmless, each carries its own time.
//! - A clock frame comes after the text and the transport, and a change of
//!   either cuts it (the sender's control): a track change is never held
//!   behind one.
use std::time::{Duration, Instant};

use crate::clock::host::LocalTime;

/// The period while the channel is granted.
pub const EVERY: Duration = Duration::from_secs(600);
/// No two frames closer than this but for an offset change or a step.
pub const MIN_GAP: Duration = Duration::from_secs(300);
/// After a failed write.
pub const RETRY: Duration = Duration::from_secs(30);
/// The board refuses a clock frame this long after raw HID set its clock
/// (`LOCKCHAN_CLOCK_OWNER_S`), counted from the set in its own seconds,
/// which run slow asleep (~13-16%) and take no credit for it
/// (`rtc_stamp_age_s`): up to ~700 s of real time after a sleep. The first
/// frame waits [`OWNER_FLOOR`] (codex, the clock's verify).
pub const BOARD_OWNER: Duration = Duration::from_secs(600);
pub const OWNER_FLOOR: Duration = Duration::from_secs(735);
/// A wall clock this far from where the monotonic one says it should be has
/// stepped: between steps, and within a frame once its time is taken. Half a
/// second: a clock frame is worth tens of milliseconds, and the two clocks
/// drift ~0.1 ms a second against each other at most.
pub const STEP_SLACK_MS: i64 = 500;
/// The longest a frame can take from its anchor to the board's set: the
/// receiver's 12 s lifetime and its 2 s of retries. An offset change inside
/// this from the anchor would land the board on the old offset's civil time:
/// no frame is built across one (review, 7).
pub const SPAN: Duration = Duration::from_secs(16);

/// Seconds east of UTC that `local` is for `unix_s`: its civil fields read as
/// UTC, less the instant.
pub fn utc_offset_s(local: &LocalTime, unix_s: i64) -> i64 {
    days_from_civil(local.year as i64, local.month as i64, local.day as i64) * 86400
        + local.hour as i64 * 3600
        + local.minute as i64 * 60
        + local.second as i64
        - unix_s
}

/// Days since 1970-01-01 (H. Hinnant's `days_from_civil`).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// After a discontinuity of the host's clock, every frame carries
/// `CLOCK_F_STEPPED` for this long. The channel is one way: a marked frame
/// can be lost, and the board would then close its trim window on the next
/// plain one, learning the step as drift. Past the board's longest window
/// (`RTC_FT_MAX_S`, 3600 of its seconds) with margin for its rate, any plain
/// frame's window spanning the step is too long to trim from (codex, the
/// trim's verify, 2).
pub const QUARANTINE: Duration = Duration::from_secs(3900);

#[derive(Debug, Default)]
pub struct ClockSched {
    due: Option<Instant>,
    /// Not before this, whatever the reason: the handover and the board's
    /// window after a USB sync, held apart from `due` so a wake or an offset
    /// change cannot bring a frame inside it (implementation review, 3).
    floor: Option<Instant>,
    last_sent: Option<Instant>,
    offset: Option<i64>,
    wall_ref: Option<(Instant, i64)>,
    /// The last discontinuity: a step, an offset change, or the first
    /// observation (this process cannot know what came before it; the
    /// verify, 3). Frames carry `CLOCK_F_STEPPED` for [`QUARANTINE`] after.
    stepped_at: Option<Instant>,
    /// This process's last USB clock set the board acknowledged: a
    /// phase-correct set from this host's clock, so a discontinuity before
    /// it is behind the board's window.
    usb_set: Option<Instant>,
}

impl ClockSched {
    pub fn due(&self) -> Option<Instant> {
        self.due.map(|d| self.floor.map_or(d, |f| d.max(f)))
    }

    pub fn last_sent(&self) -> Option<Instant> {
        self.last_sent
    }

    /// A frame at `now` carries `CLOCK_F_STEPPED` (the board's frame trim):
    /// within the quarantine of a discontinuity no acknowledged USB set has
    /// followed, or before any observation.
    pub fn host_stepped(&self, now: Instant) -> bool {
        match self.stepped_at {
            None => true,
            Some(s) => now < s + QUARANTINE && self.usb_set.is_none_or(|u| u < s),
        }
    }

    /// The reference the next step check uses, and the offset it saw.
    pub fn wall_ref(&self) -> (Option<(Instant, i64)>, Option<i64>) {
        (self.wall_ref, self.offset)
    }

    /// A frame's build saw the host's clock off its reference at `now`.
    pub fn saw_step(&mut self, now: Instant) {
        self.stepped_at = Some(now);
    }

    /// The board acknowledged this process's USB clock set at `at`.
    pub fn usb_set(&mut self, at: Instant) {
        self.usb_set = Some(self.usb_set.map_or(at, |u| u.max(at)));
    }

    /// A new acquisition: the first frame after the handover (`not_before`)
    /// and the board's refusal window after `usb_clock_last`.
    pub fn acquired(&mut self, not_before: Instant, usb_clock_last: Option<Instant>) {
        let owner_end = usb_clock_last.map(|t| t + OWNER_FLOOR);
        let floor = owner_end.map_or(not_before, |e| e.max(not_before));
        self.floor = Some(floor);
        self.due = Some(floor);
    }

    /// The channel was revoked: nothing is due until the next acquisition.
    pub fn revoked(&mut self) {
        self.due = None;
        self.floor = None;
    }

    /// The wake guess fired at `now`.
    pub fn woke(&mut self, now: Instant) {
        if self.due.is_none() {
            return; // not acquired
        }
        let mut t = now + super::sender::WAKE_DELAY;
        if let Some(s) = self.last_sent {
            t = t.max(s + MIN_GAP);
        }
        // The wake's delay is a lower bound whatever was due (codex, the
        // clock's second verify, 2): one held back by the idle gate, or due
        // a second from now, goes after it, not into the board's wake
        // recovery. Past it, the sooner of the two.
        let earliest = now + super::sender::WAKE_DELAY;
        self.due = self.due.map(|d| d.min(t).max(earliest));
    }

    /// Each step while acquired: the offset now and the wall clock against
    /// the monotonic one. True when either moved (a frame was made due).
    pub fn observe(&mut self, now: Instant, wall_ms: i64, offset_s: i64) -> bool {
        let stepped = self.wall_ref.is_some_and(|(at, w)| {
            let expect = w + now.saturating_duration_since(at).as_millis() as i64;
            (wall_ms - expect).abs() > STEP_SLACK_MS
        });
        let moved = self.offset.is_some_and(|o| o != offset_s);
        if stepped || moved || self.wall_ref.is_none() {
            self.stepped_at = Some(now);
        }
        self.wall_ref = Some((now, wall_ms));
        self.offset = Some(offset_s);
        if (stepped || moved) && self.due.is_some() {
            self.due = Some(now);
            return true;
        }
        false
    }

    /// The host's clock as a frame just carried it: the reference for the
    /// next step check, with nothing scheduled.
    pub fn rebase(&mut self, now: Instant, wall_ms: i64, offset_s: i64) {
        self.wall_ref = Some((now, wall_ms));
        self.offset = Some(offset_s);
    }

    /// Sent whole at `done`.
    pub fn sent(&mut self, done: Instant) {
        self.last_sent = Some(done);
        if self.due.is_some() {
            self.due = Some(done + EVERY);
        }
    }

    /// Lost to chance: again at once.
    pub fn again(&mut self, done: Instant) {
        if self.due.is_some() {
            self.due = Some(done);
        }
    }

    /// A failed write, or nothing could be built: again after `wait`.
    pub fn later(&mut self, done: Instant, wait: Duration) {
        if self.due.is_some() {
            self.due = Some(done + wait);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clock::host::utc_local;

    fn s(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    #[test]
    fn the_offset_is_the_civil_fields_less_the_instant() {
        let t = 1_792_540_799; // 2026-10-20 23:59:59 UTC
        assert_eq!(utc_offset_s(&utc_local(t), t), 0);
        assert_eq!(utc_offset_s(&utc_local(t - 6 * 3600), t), -6 * 3600);
        assert_eq!(utc_offset_s(&utc_local(t + 5 * 3600 + 1800), t), 5 * 3600 + 1800);
        // Across a year end and a leap day.
        let ny = 1_798_761_600; // 2027-01-01 00:00:00 UTC
        assert_eq!(utc_offset_s(&utc_local(ny - 7 * 3600), ny), -7 * 3600);
        let leap = 1_835_395_200; // 2028-02-29 00:00:00 UTC
        assert_eq!(utc_offset_s(&utc_local(leap + 3600), leap), 3600);
    }

    #[test]
    fn the_first_frame_waits_out_the_handover_and_the_boards_window() {
        let t0 = Instant::now();
        let mut c = ClockSched::default();
        assert_eq!(c.due(), None);
        c.acquired(t0 + s(12), None);
        assert_eq!(c.due(), Some(t0 + s(12)));
        // A USB sync 100 s before: the board refuses until 600 s after it.
        c.acquired(t0 + s(12), Some(t0 - s(100)));
        assert_eq!(c.due(), Some(t0 - s(100) + OWNER_FLOOR));
        // One long ago: the handover alone.
        c.acquired(t0 + s(12), Some(t0 - s(3600)));
        assert_eq!(c.due(), Some(t0 + s(12)));
    }

    #[test]
    fn no_reason_brings_a_frame_inside_the_boards_window() {
        let t0 = Instant::now();
        let w0 = 1_792_540_799_000;
        let mut c = ClockSched::default();
        c.acquired(t0 + s(12), Some(t0));
        let floor = t0 + OWNER_FLOOR;
        c.woke(t0 + s(40));
        assert_eq!(c.due(), Some(floor), "a wake");
        c.observe(t0 + s(50), w0, 0);
        assert!(c.observe(t0 + s(60), w0 + 10_000, 3600));
        assert_eq!(c.due(), Some(floor), "an offset change");
        c.again(t0 + s(70));
        assert_eq!(c.due(), Some(floor), "a loss");
        // Past the floor, the reasons act as before.
        c.sent(floor + s(1));
        c.woke(floor + s(400));
        assert_eq!(c.due(), Some(floor + s(400) + crate::lockchan::sender::WAKE_DELAY));
    }

    #[test]
    fn sent_frames_repeat_every_ten_minutes_and_stop_when_revoked() {
        let t0 = Instant::now();
        let mut c = ClockSched::default();
        c.acquired(t0, None);
        c.sent(t0 + s(3));
        assert_eq!(c.due(), Some(t0 + s(3) + EVERY));
        c.revoked();
        assert_eq!(c.due(), None);
        c.sent(t0 + s(9)); // a frame finishing after the revoke schedules nothing
        assert_eq!(c.due(), None);
    }

    #[test]
    fn a_wake_sends_soon_but_not_inside_the_gap() {
        let t0 = Instant::now();
        let mut c = ClockSched::default();
        c.woke(t0); // not acquired: nothing
        assert_eq!(c.due(), None);
        c.acquired(t0, None);
        c.sent(t0);
        c.woke(t0 + s(400)); // past the gap: after the wake delay
        assert_eq!(c.due(), Some(t0 + s(400) + crate::lockchan::sender::WAKE_DELAY));
        c.sent(t0 + s(405));
        c.woke(t0 + s(500)); // inside it: at the gap's end
        assert_eq!(c.due(), Some(t0 + s(405) + MIN_GAP));
        // Overdue (held back while idle): after the wake delay, not at once.
        c.sent(t0 + s(1000));
        c.woke(t0 + s(2000));
        assert_eq!(c.due(), Some(t0 + s(2000) + crate::lockchan::sender::WAKE_DELAY));
        // Due a second after the wake: the delay still holds.
        c.sent(t0 + s(3000));
        c.woke(t0 + s(3000) + EVERY - s(1));
        assert_eq!(c.due(), Some(t0 + s(3000) + EVERY - s(1) + crate::lockchan::sender::WAKE_DELAY));
    }

    #[test]
    fn an_offset_change_or_a_wall_step_sends_at_once() {
        let t0 = Instant::now();
        let w0 = 1_792_540_799_000;
        let mut c = ClockSched::default();
        c.acquired(t0, None);
        c.sent(t0);
        assert!(!c.observe(t0, w0, -6 * 3600));
        assert!(!c.observe(t0 + s(10), w0 + 10_000 + 400, -6 * 3600)); // drift within the slack
        assert_eq!(c.due(), Some(t0 + EVERY));
        assert!(c.observe(t0 + s(11), w0 + 11_000 + 400 + 1000, -6 * 3600)); // a one-second step
        c.sent(t0);
        assert_eq!(c.due(), Some(t0 + EVERY));
        assert!(c.observe(t0 + s(20), w0 + 20_400, -7 * 3600)); // DST ends
        assert_eq!(c.due(), Some(t0 + s(20)));
        c.sent(t0 + s(22));
        assert!(c.observe(t0 + s(30), w0 + 20_400 + 10_000 + 60_000, -7 * 3600)); // a minute's step
        assert_eq!(c.due(), Some(t0 + s(30)));
        c.revoked();
        assert!(!c.observe(t0 + s(40), w0, 0)); // not acquired: nothing due
        assert_eq!(c.due(), None);
    }

    #[test]
    fn losses_go_again_at_once_and_failures_after_the_retry() {
        let t0 = Instant::now();
        let mut c = ClockSched::default();
        c.acquired(t0, None);
        c.again(t0 + s(2));
        assert_eq!(c.due(), Some(t0 + s(2)));
        c.later(t0 + s(3), RETRY);
        assert_eq!(c.due(), Some(t0 + s(33)));
    }

    #[test]
    fn a_new_process_is_quarantined_until_a_usb_set_or_the_quarantine_ends() {
        let t0 = Instant::now();
        let w0 = 1_792_540_799_000;
        let mut c = ClockSched::default();
        assert!(c.host_stepped(t0), "nothing observed: unknown");
        c.acquired(t0, None);
        c.observe(t0, w0, 0);
        c.observe(t0 + s(10), w0 + 10_000, 0);
        assert!(c.host_stepped(t0 + s(10)), "the first observation starts it");
        assert!(c.host_stepped(t0 + QUARANTINE - s(1)));
        assert!(!c.host_stepped(t0 + QUARANTINE));
        // Or an acknowledged USB set after it ends it at once; one before it
        // does not.
        let mut d = ClockSched::default();
        d.usb_set(t0 - s(1));
        d.observe(t0, w0, 0);
        assert!(d.host_stepped(t0 + s(5)));
        d.usb_set(t0 + s(5));
        assert!(!d.host_stepped(t0 + s(6)));
    }

    #[test]
    fn a_step_or_an_offset_change_marks_frames_for_the_quarantine() {
        let t0 = Instant::now();
        let w0 = 1_792_540_799_000;
        let mut c = ClockSched::default();
        c.acquired(t0, None);
        c.observe(t0, w0, 0);
        c.usb_set(t0 + s(1));
        c.observe(t0 + s(10), w0 + 10_000, 0);
        assert!(!c.host_stepped(t0 + s(10)), "the clock ran true");
        c.observe(t0 + s(20), w0 + 20_000 + STEP_SLACK_MS + 1, 0);
        assert!(c.host_stepped(t0 + s(20)), "a step");
        // Not cleared by a frame sent whole (it may be lost), nor a new
        // acquisition; through the quarantine.
        c.sent(t0 + s(31));
        c.revoked();
        c.acquired(t0 + s(50), Some(t0 + s(45)));
        assert!(c.host_stepped(t0 + s(20) + QUARANTINE - s(1)));
        assert!(!c.host_stepped(t0 + s(20) + QUARANTINE));
        // An offset change, and one the build saw.
        c.observe(t0 + s(40), w0 + 40_000 + STEP_SLACK_MS + 1, 3600);
        assert!(c.host_stepped(t0 + s(40) + QUARANTINE - s(1)));
        c.usb_set(t0 + s(41));
        assert!(!c.host_stepped(t0 + s(42)), "a USB set after it");
        c.saw_step(t0 + s(60));
        assert!(c.host_stepped(t0 + s(60) + QUARANTINE - s(1)));
    }
}
