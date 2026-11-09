//! Now-playing over the 2.4G dongle when the cable is out: the daemon's side
//! of raw81 stage 2 (`plans/RAWHID-24G-DAEMON-PLAN.md`, D5-D8 and revisions
//! 2-4).
//!
//! The agent calls [`Radio::tick`] only when the **USB opener** said `Absent`
//! (R2-5) and `--radio` is on, and [`Radio::usb_present`] whenever the board
//! is on USB, which ends the radio's acquisition. The radio keeps its own
//! state, backoffs and status: nothing here touches the USB presence `Watch`.
//!
//! One tick, in order: the host's input sampled; the idle hold; a silent
//! board's wait for input; the backoff; the dongle (opened per tick, as the
//! board is); the machine-wide lock, held for the acquisition (R3-2), which
//! starts a [`Link`] and its quiet; the probe if the session is unqualified;
//! the hold again, aged by the tick so far; a full text refresh on a new
//! qualification (R2-7); the lock lights revoked; the publisher's text if
//! due; the playback readout if it matters ([`Readout`]). The hold is
//! checked again, aged, before every media request and after a failure that
//! ends the tick. A failed text push leaves the publisher where it was, so
//! the next tick retries, as on USB (D8).
//! After the tick, [`Radio::next_tick`] says when the next one is wanted.
//!
//! **A sleeping board is left alone** (measured 11-09: with music playing and
//! the board idle on 2.4G it averaged ~28 mA against 3.3 asleep). Each radio
//! session costs the board's module a ~5 s blip, twice one coincided with a
//! phantom key wake that lit the board for 3 min, and the firmware clears the
//! host text at a deep sleep's wake anyway. So the radio sends only what the
//! board will keep, three rules:
//!
//! 1. **The hold.** With no input on this machine for [`HOLD_IDLE`] (the
//!    lock-light sender's constant and sources, `Platform::host_input`,
//!    followed across ticks by [`crate::input::Track`]), the radio sends
//!    nothing and ends its acquisition. It is checked as the tick starts,
//!    and again with the idle aged by the tick so far: after the probe,
//!    before each media request (each text line and the readout, all after
//!    the lock lights' revocation), and after a failed request, so a request
//!    that ends past the hold is the tick's last, and its acquisition ends
//!    with it. A poisoned radio keeps its lock and its state.
//!    Input's return starts a new session, whose qualification sends the
//!    whole text. A track change while held waits for that input.
//! 2. **A silent board waits for input.** Silence through the backoff to
//!    [`SILENCE_CAP`] (the board stopped answering: asleep) ends the
//!    acquisition as before, but the next session starts only once this
//!    machine has seen input since that silence, and no sooner than the cap
//!    after it. Input is a change between two samples (the last input's
//!    identity on Windows, an idle that fell on macOS), latched until the
//!    backoff runs out, so a key half a second after the silence counts. A
//!    key on the keyboard wakes it and reaches this machine as input, so the
//!    session after a wake finds it answering. Input from the trackpad or
//!    another keyboard costs at most one probe per cap. A board woken with no
//!    input reaching this machine (its knob, a key on another host) gets no
//!    title until there is: the price of leaving a sleeping board alone.
//! 3. **The readout when it matters** ([`Readout`]): not every tick.
//!
//! With no idle time to read (a platform without one, or a failed read),
//! rules 1 and 2 stand aside and the radio behaves as before them.

use std::time::{Duration, Instant};

use crate::hid::exchange::Wire;
use crate::hid;
use crate::lockchan::sender::HOLD_IDLE;
use crate::logfile::Log;
use crate::media::Publisher;
use crate::platform::RadioGuard;
use crate::raw81::link::{Clock, Failure, Link};
use crate::smtc::Snapshot;
use crate::status::RadioStatus;

/// Silence (no answer with the dongle present: a sleeping board, a board on
/// another mode, a build without stage 2) backs off 1 s, 2 s, 4 s ... to this
/// (R2-7); at the cap the acquisition ends (the lock is released). The next
/// session starts after the cap and, when the idle time can be read, only
/// once this machine has seen input since (rule 2, the module documentation).
pub const SILENCE_CAP: Duration = Duration::from_secs(30);
/// The board's lease on a raw-HID playback readout: 20 s after the last one
/// it ran it hands the band back to the clock (`PLAYBACK_TIMEOUT_MS`,
/// `graphics/display.c`). It advances the position itself in between, from
/// the anchor each readout sets (`graphics/playback.c`).
pub const PLAYBACK_LEASE: Duration = Duration::from_secs(20);
/// A readout's renewal, and one retry a tick after it, land by this after
/// the last one the board confirmed: 2 s inside [`PLAYBACK_LEASE`] for the
/// ticks' own lateness. The renewal goes at the first tick from which
/// waiting one more would put that retry past it ([`Readout::due`]).
pub const PLAYBACK_RENEW_BY: Duration = Duration::from_secs(18);
/// The slowest tick while a confirmed readout's lease runs, whatever the
/// daemon's `--interval` ([`Radio::next_tick`]): the default media interval.
pub const LEASED_TICK: Duration = crate::media::INTERVAL;
/// The first silence's backoff: a lost renewal's retry waits at least this.
const FIRST_BACKOFF: Duration = Duration::from_secs(1);
/// Another session live on the board (D3).
pub const BUSY_BACKOFF: Duration = Duration::from_secs(30);
/// A command the board refuses (a stage-2 board without text on its
/// allow-list) or a reply that is not an answer: not retried soon.
pub const REFUSED_BACKOFF: Duration = Duration::from_secs(600);
/// A stuck handle, as on USB.
pub const ABANDON_BACKOFF: Duration = crate::agent::ABANDON_BACKOFF;
/// The lock could not even be tried.
pub const LOCK_ERROR_BACKOFF: Duration = Duration::from_secs(60);

/// The radio's state, as the status file and the log name it.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum State {
    /// Nothing tried yet, or the board is on USB.
    Off,
    /// No dongle.
    Absent,
    /// Another owner on this machine holds the lock.
    Contended,
    /// A session's quiet, a grace or a rotation.
    Quiet,
    /// The board answers this session.
    Qualified,
    /// No answer.
    Silent,
    /// Another session is live on the board.
    Busy,
    /// The board refused a command, or a reply did not answer it.
    Refused,
    /// The dongle would not open, or a transfer failed.
    Unresponsive,
    /// A stuck handle.
    Abandoned,
    /// The lock file could not be opened.
    LockError,
    /// No input on this machine for [`HOLD_IDLE`]: nothing is sent, and no
    /// session starts, until there is.
    Held,
}

impl State {
    pub fn word(self) -> &'static str {
        match self {
            State::Off => "off",
            State::Absent => "absent",
            State::Contended => "contended",
            State::Quiet => "quiet",
            State::Qualified => "qualified",
            State::Silent => "silent",
            State::Busy => "busy",
            State::Refused => "refused",
            State::Unresponsive => "unresponsive",
            State::Abandoned => "abandoned",
            State::LockError => "lock error",
            State::Held => "held",
        }
    }
}

/// The playback readout as the board last confirmed it, so the radio sends
/// it only when it matters (rule 3): with any text push, on a new
/// qualification (the text goes whole then), on a change of its identity
/// (whether it shows, the duration, the track), on a seek (the position
/// further than `lockchan::SEEK_SLACK_S` from where the last one put it by
/// now), after one the board did not confirm, and, while one shows, to renew
/// the board's lease ([`PLAYBACK_RENEW_BY`]). Not every tick: the board
/// advances the position itself between readouts. A paused, stopped or
/// streaming track has no readout to show (state 0), so nothing to renew.
///
/// USB still sends it every poll, as the Python agent did; this is the
/// radio's alone.
#[derive(Debug, Default)]
struct Readout {
    /// The last one the board confirmed: its lease runs from it.
    confirmed: Option<ReadoutSent>,
    /// What the board shows may differ from `confirmed` (a new
    /// qualification, a send it did not confirm): the next tick sends one.
    unsure: bool,
}

#[derive(Debug)]
struct ReadoutSent {
    shown: bool,
    dur_s: u32,
    artist: String,
    title: String,
    /// The position it carried, and the tick it went on.
    pos_s: u32,
    at: Instant,
}

impl Readout {
    /// Due at `now`, ticks coming every `step` (the retry's wait too).
    fn due(&self, s: &Snapshot, now: Instant, step: Duration) -> bool {
        let Some(last) = self.confirmed.as_ref().filter(|_| !self.unsure) else { return true };
        let (shown, pos_s, dur_s) = s.playback();
        if (shown, dur_s) != (last.shown, last.dur_s) || s.artist != last.artist || s.title != last.title {
            return true;
        }
        if !shown {
            return false;
        }
        let since = now.saturating_duration_since(last.at);
        // Renew now if the next tick's renewal could not be retried a tick
        // later by PLAYBACK_RENEW_BY. The tick before this one could, so
        // this renewal's retry lands by it.
        since + 2 * step > PLAYBACK_RENEW_BY || crate::lockchan::is_seek(last.pos_s, since, pos_s, dur_s)
    }

    fn sent(&mut self, s: &Snapshot, now: Instant) {
        let (shown, pos_s, dur_s) = s.playback();
        self.confirmed = Some(ReadoutSent { shown, dur_s, artist: s.artist.clone(), title: s.title.clone(), pos_s, at: now });
        self.unsure = false;
    }

    /// The board's readout is in doubt: the next tick sends one. The lease
    /// of the last confirmed one still runs, and still sets the pace.
    fn unsure(&mut self) {
        self.unsure = true;
    }

    /// Nothing to keep: the acquisition ended, or USB carries the media.
    fn clear(&mut self) {
        *self = Readout::default();
    }

    /// When the board drops the readout it shows, if one shows.
    fn lease_ends(&self) -> Option<Instant> {
        self.confirmed.as_ref().filter(|c| c.shown).map(|c| c.at + PLAYBACK_LEASE)
    }
}

/// Where the log lines go: the daemon's log, or a test's list.
pub trait Sink {
    fn line(&mut self, s: &str);
}

impl Sink for &Log {
    fn line(&mut self, s: &str) {
        Log::line(self, s)
    }
}

impl Sink for Vec<String> {
    fn line(&mut self, s: &str) {
        self.push(s.to_string())
    }
}

/// The radio's side of the daemon.
pub struct Radio {
    link: Option<(Link, RadioGuard)>,
    /// A stuck transfer happened: the lock was leaked on purpose
    /// (`mem::forget`), so only the process's exit releases it, whatever
    /// becomes of this object. The abandoned write may still leave the
    /// kernel, so no other owner may start a session (codex, daemon review,
    /// must-fix 1, and its verify).
    poisoned: bool,
    state: State,
    hold_until: Option<Instant>,
    silence: u32,
    /// The board went silent at the cap: the next session waits for input
    /// on this machine (rule 2). Set only when the input could be read.
    awaiting_input: bool,
    /// Input seen since the silence set [`Radio::awaiting_input`]: latched,
    /// so input inside the backoff counts once it runs out.
    input_seen: bool,
    /// That wait is in the log once per silence, not at every probe.
    silence_noted: bool,
    /// The host's input, followed across ticks.
    input: crate::input::Track,
    /// This tick's idle and when it was read: `None` when unreadable. The
    /// hold's checks inside the tick age it.
    idle_at: Option<(Duration, Instant)>,
    pushed_generation: u64,
    readout: Readout,
    seed: u64,
    pub status: RadioStatus,
    /// Called right before this tick's first media request, so a lower
    /// transport (the lock lights) stops before the radio pushes (codex,
    /// lock-LED implementation review, 4).
    pub before_media: Option<Box<dyn Fn()>>,
    /// When a media request last completed, delivered or not: the lock
    /// lights' handover waits after it (R4-2; implementation review, 5).
    pub last_media_attempt: Option<Instant>,
    /// The daemon's media interval (`--interval`): the pace of its ticks but
    /// while a readout's lease runs ([`Radio::next_tick`]).
    pub interval: Duration,
}

impl Default for Radio {
    fn default() -> Self {
        Radio::new(0x9E37_79B9_7F4A_7C15)
    }
}

impl Radio {
    /// `seed`: any varying number, for the session ids.
    pub fn new(seed: u64) -> Radio {
        Radio {
            link: None,
            poisoned: false,
            state: State::Off,
            hold_until: None,
            silence: 0,
            awaiting_input: false,
            input_seen: false,
            silence_noted: false,
            input: crate::input::Track::default(),
            idle_at: None,
            pushed_generation: 0,
            readout: Readout::default(),
            seed,
            status: RadioStatus { state: State::Off.word().into(), ..RadioStatus::default() },
            before_media: None,
            last_media_attempt: None,
            interval: crate::media::INTERVAL,
        }
    }

    pub fn state(&self) -> State {
        self.state
    }

    /// Is the radio carrying the media now?
    pub fn active(&self) -> bool {
        self.state == State::Qualified
    }

    fn set(&mut self, next: State, why: Option<&str>, log: &mut impl Sink) {
        if next != self.state {
            log.line(&match why {
                Some(w) => format!("radio: {} -> {} ({w})", self.state.word(), next.word()),
                None => format!("radio: {} -> {}", self.state.word(), next.word()),
            });
            self.state = next;
            self.status.state = next.word().into();
        }
    }

    /// End the acquisition: the session and the lock. A new link counts its
    /// qualifications from 1 again, so the next one refreshes the text, and
    /// its readout.
    fn release(&mut self) {
        self.link = None;
        self.pushed_generation = 0;
        self.readout.clear();
        self.status.session = None;
        self.status.qualified = false;
    }

    /// The board is on USB: the radio stands down, releasing the lock
    /// (R2-2), and its backoffs are forgotten (USB presence is new evidence).
    /// A poisoned lock is kept, and the radio stays abandoned.
    pub fn usb_present(&mut self, log: &mut impl Sink) {
        if self.poisoned {
            return;
        }
        self.release();
        self.hold_until = None;
        self.silence = 0;
        self.awaiting_input = false;
        self.silence_noted = false;
        self.set(State::Off, Some("the board is on USB"), log);
    }

    /// How long until the next media tick: the daemon's interval, but no
    /// slower than [`LEASED_TICK`] while a readout the board confirmed shows
    /// and its lease runs, so its renewal and one retry land inside the lease
    /// at any `--interval` (codex, the radio hold's review, 1). Not held, not
    /// on USB (both clear the lease), nor past it: the interval as it is.
    pub fn next_tick(&self, now: Instant) -> Duration {
        match self.readout.lease_ends() {
            Some(end) if now < end => self.interval.min(LEASED_TICK),
            _ => self.interval,
        }
    }

    /// The ticks' spacing while a lease runs, and a lost renewal's retry's
    /// wait: the renewal is timed for it ([`Readout::due`]).
    fn step(&self) -> Duration {
        self.interval.min(LEASED_TICK).max(FIRST_BACKOFF)
    }

    /// The hold engaged (rule 1): the acquisition ends. A quiet or a grace
    /// is the link's own wait and goes with it; a backoff keeps its own
    /// state's name until it runs out, and `held` shows after.
    fn hold(&mut self, idle: Duration, now: Instant, log: &mut impl Sink) {
        self.release();
        if self.state == State::Quiet {
            self.hold_until = None;
        }
        if !self.hold_until.is_some_and(|until| now < until) {
            self.set(State::Held, Some(&format!("{} s without input on this machine", idle.as_secs())), log);
        }
    }

    /// The hold, by this tick's idle aged to now: if it has come, the
    /// acquisition ends and nothing more goes this tick.
    fn held_now(&mut self, clock: &impl Clock, log: &mut impl Sink) -> bool {
        let Some((idle, at)) = self.idle_at else { return false };
        let now = clock.now();
        let aged = idle + now.saturating_duration_since(at);
        if aged < HOLD_IDLE {
            return false;
        }
        self.hold(aged, now, log);
        true
    }

    /// A request failed inside the tick: the failure, then the hold aged to
    /// the failure's end, so one that ends past the hold releases the
    /// acquisition now, not a tick later (codex, the verify, 3). A poisoned
    /// radio keeps its lock and its state.
    fn fail_in_tick(&mut self, f: Failure, now: Instant, clock: &impl Clock, stamp: &impl Fn() -> String, log: &mut impl Sink) {
        self.fail(f, now, stamp, log);
        if !self.poisoned {
            self.held_now(clock, log);
        }
    }

    /// Does this radio hold an acquisition (the lock and a session)?
    pub fn acquired(&self) -> bool {
        self.link.is_some()
    }

    /// One media tick over the radio, and whether the text went out. See the
    /// module documentation. `input`: the host's input, read raw this tick
    /// (`Platform::host_input`); `None` when it cannot be read, and the radio
    /// behaves as before the hold.
    #[allow(clippy::too_many_arguments)]
    pub fn tick<W: Wire>(
        &mut self,
        clock: &impl Clock,
        lock: impl FnOnce() -> Result<Option<RadioGuard>, String>,
        open: impl FnOnce() -> Result<W, hid::Error>,
        publisher: &mut Publisher,
        snapshot: &Snapshot,
        input: Option<crate::input::Reading>,
        stamp: impl Fn() -> String,
        log: &mut impl Sink,
    ) -> bool {
        if self.poisoned {
            return false;
        }
        let now = clock.now();
        let seen = self.input.observe(input, now);
        self.idle_at = seen.map(|s| (s.idle, now));
        if seen.is_some_and(|s| s.input) {
            self.input_seen = true;
        }

        // Rule 1, the hold: nothing goes and no session starts; the
        // acquisition ends, so input's return starts afresh.
        if let Some(s) = seen.filter(|s| s.idle >= HOLD_IDLE) {
            self.hold(s.idle, now, log);
            return false;
        }
        // Rule 2: a board silent at the cap waits for input after it. No
        // input to read: the timer alone, as before.
        if self.awaiting_input {
            match seen {
                Some(_) if !self.input_seen => return false,
                _ => self.awaiting_input = false,
            }
        }
        if self.hold_until.is_some_and(|until| now < until) {
            return false;
        }
        self.hold_until = None;

        let dev = match open() {
            Ok(d) => d,
            Err(e) => {
                self.release();
                let next = match e {
                    hid::Error::Absent => State::Absent,
                    hid::Error::Stuck => {
                        self.hold_until = Some(now + ABANDON_BACKOFF);
                        State::Abandoned
                    }
                    _ => State::Unresponsive,
                };
                self.set(next, Some(&e.to_string()), log);
                return false;
            }
        };

        if self.link.is_none() {
            match lock() {
                Ok(Some(guard)) => {
                    self.seed = self.seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                    // The quiet runs from the moment the lock is held, never
                    // from before the open and the lock (codex, must-fix 2).
                    self.link = Some((Link::new(clock.now(), self.seed ^ nanos()), guard));
                    self.set(State::Quiet, Some("lock taken; a new session waits out its quiet"), log);
                }
                Ok(None) => {
                    self.set(State::Contended, Some("another radio owner on this machine"), log);
                    return false;
                }
                Err(e) => {
                    self.hold_until = Some(now + LOCK_ERROR_BACKOFF);
                    self.set(State::LockError, Some(&e), log);
                    return false;
                }
            }
        }
        let (link, _) = self.link.as_mut().expect("just ensured");

        if !link.qualified() {
            if let Err(f) = link.probe(&dev, clock) {
                self.fail_in_tick(f, now, clock, &stamp, log);
                return false;
            }
            self.silence = 0;
            self.silence_noted = false;
        }
        // The hold again, aged by the probe (codex, review 3): no media
        // request begins after it.
        if self.held_now(clock, log) {
            return false;
        }
        let link = &mut self.link.as_mut().expect("still held").0;
        self.status.session = link.session();
        self.status.sessions = link.sessions;
        if link.generation() != self.pushed_generation {
            publisher.refresh();
            self.readout.unsure();
            self.pushed_generation = link.generation();
        }
        self.set(State::Qualified, Some("the board answers"), log);

        let plan = publisher.plan(snapshot, now);
        // Rule 3: the readout with any text, or when it matters.
        let readout = plan.text.is_some() || self.readout.due(snapshot, now, self.step());
        if !readout {
            self.status.qualified = self.link.as_ref().is_some_and(|(l, _)| l.qualified());
            return false;
        }
        let mut pushed = false;
        if let Some(f) = &self.before_media {
            f();
        }
        // From here every media request is preceded by the hold, aged to its
        // start: after the revocation, between the lines, before the readout.
        if let Some(text) = &plan.text {
            for (command, body) in text {
                if self.held_now(clock, log) {
                    return false;
                }
                let link = &mut self.link.as_mut().expect("held").0;
                let r = link.push(&dev, clock, *command, body);
                self.last_media_attempt = Some(clock.now());
                if let Err(f) = r {
                    self.fail_in_tick(f, now, clock, &stamp, log);
                    return false;
                }
            }
            publisher.text_pushed(snapshot, now);
            pushed = true;
            self.status.pushes += 1;
            self.status.last_push = Some(stamp());
            if plan.changed {
                log.line(&format!("radio: {}", Publisher::describe(snapshot)));
            }
        }
        if self.held_now(clock, log) {
            return pushed;
        }
        let link = &mut self.link.as_mut().expect("held").0;
        let r = link.push(&dev, clock, plan.playback.0, &plan.playback.1);
        self.last_media_attempt = Some(clock.now());
        if let Err(f) = r {
            // Unconfirmed: the next tick sends it again.
            self.readout.unsure();
            self.fail_in_tick(f, now, clock, &stamp, log);
            return pushed;
        }
        self.readout.sent(snapshot, now);
        self.status.qualified = self.link.as_ref().is_some_and(|(l, _)| l.qualified());
        pushed
    }

    fn fail(&mut self, f: Failure, now: Instant, stamp: &impl Fn() -> String, log: &mut impl Sink) {
        if let Some((link, _)) = &self.link {
            self.status.session = link.session();
            self.status.sessions = link.sessions;
            self.status.qualified = link.qualified();
        }
        if let Failure::Waiting { until } = f {
            self.hold_until = Some(until);
            self.set(State::Quiet, Some("a session's quiet or grace"), log);
            return;
        }
        // Kept until the next failure, with its time: a success does not
        // erase it (codex, daemon review, 8).
        self.status.failures += 1;
        self.status.last_error = Some(f.to_string());
        self.status.last_error_at = Some(stamp());
        match f {
            Failure::Waiting { .. } => unreachable!(),
            Failure::Unknown => {
                self.status.silent += 1;
                self.silence += 1;
                let wait = Duration::from_secs(1u64 << (self.silence - 1).min(5)).min(SILENCE_CAP);
                self.hold_until = Some(now + wait);
                let capped = wait >= SILENCE_CAP;
                if capped {
                    self.release();
                }
                self.set(State::Silent, Some("no answer on the radio"), log);
                if capped && self.idle_at.is_some() {
                    // Rule 2: asleep, most likely; no session on the timer,
                    // only after input seen from here on.
                    self.awaiting_input = true;
                    self.input_seen = false;
                    if !std::mem::replace(&mut self.silence_noted, true) {
                        log.line("radio: no answer through the backoff; the next session waits for input on this machine");
                    }
                }
            }
            // Retried next tick, the state unchanged: the board is there.
            // Incomplete (the board ran it) is kept apart from Unknown (it
            // may not have), in the log and the counters (R2-4).
            Failure::Incomplete => {
                self.status.incomplete += 1;
                log.line("radio: incomplete (the board ran a command; its reply was lost)");
            }
            Failure::BadCrc => {}
            Failure::Stale => self.set(State::Quiet, Some("the session went stale; rotating"), log),
            Failure::Busy => {
                self.hold_until = Some(now + BUSY_BACKOFF);
                self.set(State::Busy, Some("another session is live on the board"), log);
            }
            Failure::Forbidden | Failure::Mismatch | Failure::TooLong => {
                let why = f.to_string();
                self.release();
                self.hold_until = Some(now + REFUSED_BACKOFF);
                self.set(State::Refused, Some(&why), log);
            }
            Failure::Hid(hid::Error::Stuck) => {
                // The lock is kept for the process's life and the radio
                // disabled: the abandoned write may still leave the kernel
                // (codex, must-fix 1). A cooldown cannot bound it.
                if let Some((_, guard)) = self.link.take() {
                    std::mem::forget(guard);
                }
                self.poisoned = true;
                self.status.session = None;
                self.status.qualified = false;
                self.set(
                    State::Abandoned,
                    Some("a radio transfer never completed; the radio is off until the daemon restarts"),
                    log,
                );
            }
            Failure::Hid(e) => self.set(State::Unresponsive, Some(&e.to_string()), log),
        }
    }
}

fn nanos() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::input::Reading;
    use crate::media::INTERVAL;
    use crate::raw81::fake::{Board, Fake, FakeClock};
    use crate::raw81::link::QUIET;
    use crate::raw81::{ST_BUSY, ST_FORBIDDEN, ST_STALE};
    use crate::smtc::Snapshot;
    use crate::text::Icon;
    use std::cell::Cell;

    /// The probe, a text line, and the playback readout, as the board
    /// receives them: (channel, command).
    const PROBE: (u8, u8) = (0x13, 0x01);
    const LINE: (u8, u8) = (0x12, 0x03);
    const READOUT: (u8, u8) = (0x12, 0x04);

    fn snap() -> Snapshot {
        Snapshot { title: "Radio title".into(), artist: "The Dongle".into(), ..Snapshot::default() }
    }

    /// A track playing at `pos` of `dur`: a readout the board shows.
    fn playing(pos: u32, dur: u32) -> Snapshot {
        Snapshot { icon: Icon::Play, playing: true, pos_s: pos, dur_s: dur, ..snap() }
    }

    struct Rig<'c> {
        c: &'c FakeClock,
        f: Fake<'c>,
        r: Radio,
        p: Publisher,
        log: Vec<String>,
        lock_free: Cell<bool>,
        locks_taken: Cell<u32>,
        dongle: Cell<bool>,
        /// The last input on this machine: the tick's reading (macOS's, an
        /// idle duration) runs from it. `None`: the idle time cannot be read,
        /// as before the hold.
        input: Cell<Option<Instant>>,
        /// The reading fails for now, whatever `input` says.
        unreadable: Cell<bool>,
    }

    impl<'c> Rig<'c> {
        fn new(c: &'c FakeClock, script: &[Board]) -> Rig<'c> {
            Rig {
                c,
                f: Fake::new(c, script),
                r: Radio::new(1),
                p: Publisher::new(),
                log: Vec::new(),
                lock_free: Cell::new(true),
                locks_taken: Cell::new(0),
                dongle: Cell::new(true),
                input: Cell::new(None),
                unreadable: Cell::new(false),
            }
        }

        fn reading(&self) -> Option<Reading> {
            if self.unreadable.get() {
                return None;
            }
            self.input.get().map(|t| Reading::Idle(self.c.now().saturating_duration_since(t)))
        }

        fn tick(&mut self, s: &Snapshot) {
            let lock = || {
                if self.lock_free.get() {
                    self.locks_taken.set(self.locks_taken.get() + 1);
                    Ok(Some(Box::new(()) as RadioGuard))
                } else {
                    Ok(None)
                }
            };
            let f = &self.f;
            let open = || if self.dongle.get() { Ok(f) } else { Err(hid::Error::Absent) };
            let reading = self.reading();
            self.r.tick(self.c, lock, open, &mut self.p, s, reading, || "now".into(), &mut self.log);
        }

        /// [`Rig::tick`], answering whether the text went out.
        fn tick_returns(&mut self, s: &Snapshot) -> bool {
            let lock = || {
                self.locks_taken.set(self.locks_taken.get() + 1);
                Ok(Some(Box::new(()) as RadioGuard))
            };
            let f = &self.f;
            let reading = self.reading();
            self.r.tick(self.c, lock, || Ok(f), &mut self.p, s, reading, || "now".into(), &mut self.log)
        }

        /// A key or the mouse on this machine, now.
        fn input_now(&self) {
            self.input.set(Some(self.c.now()));
        }

        /// The inners the board received, as (channel, command).
        fn sent(&self) -> Vec<(u8, u8)> {
            self.f.got.borrow().iter().map(|(_, _, i)| (i[1], i[2])).collect()
        }

        /// `n` media ticks [`INTERVAL`] apart, the snapshot taken at each
        /// tick's time: what each tick sent.
        fn ticks(&mut self, n: usize, snap: impl Fn(Instant) -> Snapshot) -> Vec<Vec<(u8, u8)>> {
            let mut out = Vec::new();
            for _ in 0..n {
                self.c.advance(INTERVAL);
                let before = self.sent().len();
                self.tick(&snap(self.c.now()));
                out.push(self.sent()[before..].to_vec());
            }
            out
        }

        /// To the first session's qualification: the quiet, then the probe,
        /// the whole text and the readout.
        fn qualify(&mut self, s: &Snapshot) {
            self.tick(s);
            self.c.advance(QUIET);
            self.tick(s);
            assert_eq!(self.r.state(), State::Qualified);
        }
    }

    /// The ticks of `got` (1-based) that sent anything, and what.
    fn sending(got: &[Vec<(u8, u8)>]) -> Vec<(usize, Vec<(u8, u8)>)> {
        got.iter().enumerate().filter(|(_, s)| !s.is_empty()).map(|(i, s)| (i + 1, s.clone())).collect()
    }


    #[test]
    fn nothing_is_sent_in_the_first_quiet_then_probe_text_and_playback() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        assert!(g.sent().is_empty());
        c.advance(Duration::from_secs(1));
        g.tick(&snap());
        assert!(g.sent().is_empty(), "held until the quiet ends");
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Qualified);
        // The probe (health), the two lines, the playback.
        assert_eq!(g.sent(), [(0x13, 0x01), (0x12, 0x03), (0x12, 0x03), (0x12, 0x04)]);
        assert_eq!(g.r.status.pushes, 1);
        assert!(g.log.iter().any(|l| l.contains("radio:") && l.contains("Radio title")), "{:?}", g.log);
    }

    /// A steady track sends nothing on a plain tick: only the readout's lease
    /// renewal (after 12 s at the 3 s tick, so it and one retry land by
    /// [`PLAYBACK_RENEW_BY`]) and the text's keepalive, which carries a
    /// readout. Was
    /// `a_steady_track_sends_only_playback_until_the_keepalive`, which pinned
    /// the readout to every 3 s tick: the traffic this change removes.
    #[test]
    fn a_steady_track_sends_only_the_readouts_renewal_and_the_keepalive() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        let t0 = c.now();
        let at = move |now: Instant| playing(10 + now.duration_since(t0).as_secs() as u32, 300);
        g.qualify(&at(c.now()));
        assert_eq!(g.sent(), [PROBE, LINE, LINE, READOUT]);
        let got = g.ticks(20, at);
        // At 3 s a tick: the renewal at 12 s (ticks 4, 8), the keepalive's
        // text and readout at 30 s (tick 10), and again from there.
        assert_eq!(
            sending(&got),
            [
                (4, vec![READOUT]),
                (8, vec![READOUT]),
                (10, vec![LINE, LINE, READOUT]),
                (14, vec![READOUT]),
                (18, vec![READOUT]),
                (20, vec![LINE, LINE, READOUT]),
            ]
        );
        assert_eq!(g.locks_taken.get(), 1, "the lock is held across ticks");
    }

    /// Paused (or stopped, or a stream): the board shows the clock and holds
    /// no readout to renew, so state 0 goes only with the text.
    #[test]
    fn a_paused_track_sends_its_readout_only_with_the_text() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        let paused = Snapshot { icon: Icon::Pause, pos_s: 42, dur_s: 300, ..snap() };
        g.qualify(&paused);
        let got = g.ticks(20, |_| paused.clone());
        assert_eq!(sending(&got), [(10, vec![LINE, LINE, READOUT]), (20, vec![LINE, LINE, READOUT])]);
    }

    /// The readout's identity: whether it shows, the duration, the track. A
    /// change goes at once, alone when the text has not changed.
    #[test]
    fn a_change_of_state_or_duration_sends_the_readout_at_once() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        let t0 = c.now();
        let pos = move |now: Instant| 10 + now.duration_since(t0).as_secs() as u32;
        g.qualify(&playing(pos(c.now()), 300));
        let mut got = g.ticks(1, |now| playing(pos(now), 300));
        // The player corrects the duration: the readout alone.
        got.extend(g.ticks(2, |now| playing(pos(now), 301)));
        // A stream: still the play icon, so the same text, but no readout to
        // show (state 0 hands the band back to the clock).
        got.extend(g.ticks(2, |now| playing(pos(now), 0)));
        // A pause changes the icon: the text, and its readout with it.
        got.extend(g.ticks(2, |_| Snapshot { icon: Icon::Pause, pos_s: 20, dur_s: 300, ..snap() }));
        assert_eq!(
            sending(&got),
            [(2, vec![READOUT]), (4, vec![READOUT]), (6, vec![LINE, LINE, READOUT])]
        );
    }

    /// A seek (the position further than `SEEK_SLACK_S` from where the last
    /// readout put it by now) sends the readout; drift inside it does not.
    #[test]
    fn a_seek_sends_the_readout_and_drift_inside_the_slack_does_not() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        let t0 = c.now();
        let off = Cell::new(0i64);
        let at = |now: Instant| playing((10 + now.duration_since(t0).as_secs() as i64 + off.get()) as u32, 600);
        g.qualify(&at(c.now()));
        let mut got = g.ticks(1, at);
        off.set(60); // a seek forwards a minute
        got.extend(g.ticks(2, at));
        off.set(58); // two seconds behind: drift, not a seek
        got.extend(g.ticks(1, at));
        off.set(30); // back half a minute
        got.extend(g.ticks(1, at));
        assert_eq!(sending(&got), [(2, vec![READOUT]), (5, vec![READOUT])]);
    }

    /// A readout the board did not confirm goes again on the next tick (the
    /// receipt alone: it ran it, its reply was lost), without the text.
    #[test]
    fn an_unconfirmed_readout_goes_again_next_tick() {
        let c = FakeClock::new();
        let script = [Board::Answer { ms: 20 }, Board::Answer { ms: 20 }, Board::Answer { ms: 20 }, Board::ReceiptOnly];
        let mut g = Rig::new(&c, &script);
        g.qualify(&snap());
        assert_eq!(g.r.status.incomplete, 1);
        let got = g.ticks(3, |_| snap());
        assert_eq!(sending(&got), [(1, vec![READOUT])]);
    }

    /// A playing track for `span` at `interval`, each tick spaced by
    /// [`Radio::next_tick`] as the daemon's loop spaces them: when the board
    /// confirmed a readout (each renews its lease), from the start, and the
    /// failures.
    fn lease_run(interval: Duration, script: &[Board], span: Duration) -> (Vec<Duration>, u64) {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, script);
        g.r.interval = interval;
        let t0 = c.now();
        let at = |now: Instant| playing(10 + now.duration_since(t0).as_secs() as u32, 3_600);
        let mut confirmed = Vec::new();
        while c.now() < t0 + span {
            let (n, failures) = (g.sent().len(), g.r.status.failures);
            g.tick(&at(c.now()));
            if g.sent()[n..].contains(&READOUT) && g.r.status.failures == failures {
                confirmed.push(c.now().duration_since(t0));
            }
            c.advance(g.r.next_tick(c.now()));
        }
        (confirmed, g.r.status.failures)
    }

    /// The board drops a readout 20 s after the last it ran
    /// ([`PLAYBACK_LEASE`]). A playing renewal lost whole (the request and
    /// its one immediate retry unanswered, so the board never ran it) is
    /// recovered on the next tick, a probe and the whole text with its
    /// readout, inside that lease at 3, 5 and 11 s intervals: at 11 s the
    /// daemon ticks every 3 s while the lease runs. The gaps are between
    /// readouts the board confirmed, so each is a lease that held.
    #[test]
    fn a_lost_playing_renewal_recovers_inside_the_boards_lease_at_any_interval() {
        assert_eq!(PLAYBACK_LEASE, Duration::from_millis(20_000), "the firmware's PLAYBACK_TIMEOUT_MS");
        for secs in [3, 5, 11] {
            let mut script = vec![Board::Answer { ms: 20 }; 4];
            script.extend([Board::Silent, Board::Silent]);
            let (confirmed, failures) = lease_run(Duration::from_secs(secs), &script, Duration::from_secs(120));
            assert_eq!(failures, 1, "{secs} s: the one lost renewal");
            assert!(confirmed[0] <= Duration::from_secs(secs + 1), "{secs} s: {confirmed:?}");
            let gaps: Vec<Duration> = confirmed.windows(2).map(|w| w[1] - w[0]).collect();
            assert!(
                gaps.iter().all(|g| *g < PLAYBACK_LEASE - Duration::from_secs(1)),
                "{secs} s: the board's readout lapsed: {confirmed:?}"
            );
            assert!(*confirmed.last().unwrap() > Duration::from_secs(100), "{secs} s: {confirmed:?}");
        }
    }

    /// With nothing lost, the readout never lapses at 11 s either, and its
    /// renewals stay sparse at every interval.
    #[test]
    fn a_steady_readout_never_lapses_at_any_interval() {
        for secs in [3, 5, 11] {
            let (confirmed, failures) = lease_run(Duration::from_secs(secs), &[], Duration::from_secs(120));
            assert_eq!(failures, 0);
            let gaps: Vec<Duration> = confirmed.windows(2).map(|w| w[1] - w[0]).collect();
            assert!(gaps.iter().all(|g| *g < PLAYBACK_LEASE - Duration::from_secs(1)), "{secs} s: {confirmed:?}");
            assert!(confirmed.len() <= 13, "{secs} s: about every 12-15 s, not every tick: {confirmed:?}");
        }
    }

    /// The renewal point follows the ticks' pace: at a 3 s tick (the default,
    /// and any longer interval while a lease runs) after 12 s, so it and one
    /// retry land by [`PLAYBACK_RENEW_BY`]; at half a second (its retry still
    /// waits the first 1 s backoff) after 16 s. And at half a second a lost
    /// renewal is recovered inside the lease too.
    #[test]
    fn the_renewal_point_follows_the_ticks_pace() {
        for (interval, lo, hi) in [(500, 16_000, 17_000), (3_000, 12_000, 15_000), (5_000, 12_000, 15_000), (11_000, 12_000, 15_000)] {
            let (confirmed, _) = lease_run(Duration::from_millis(interval), &[], Duration::from_secs(25));
            let first = confirmed[1] - confirmed[0];
            assert!(
                first > Duration::from_millis(lo) && first <= Duration::from_millis(hi),
                "{interval} ms: the first renewal after {first:?}"
            );
        }
        let mut script = vec![Board::Answer { ms: 20 }; 4];
        script.extend([Board::Silent, Board::Silent]);
        let (confirmed, failures) = lease_run(Duration::from_millis(500), &script, Duration::from_secs(60));
        assert_eq!(failures, 1);
        assert!(confirmed.windows(2).all(|w| w[1] - w[0] < PLAYBACK_LEASE - Duration::from_secs(1)), "{confirmed:?}");
    }

    /// The daemon's tick is its own interval except while a readout the
    /// board confirmed shows and its lease runs: then no slower than 3 s.
    /// Paused, a long interval keeps its pace.
    #[test]
    fn the_tick_quickens_only_while_a_confirmed_readout_shows() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.r.interval = Duration::from_secs(11);
        assert_eq!(g.r.next_tick(c.now()), Duration::from_secs(11), "nothing confirmed yet");
        let paused = Snapshot { icon: Icon::Pause, pos_s: 42, dur_s: 300, ..snap() };
        g.qualify(&paused);
        assert_eq!(g.r.next_tick(c.now()), Duration::from_secs(11), "paused: no readout shows");
        c.advance(Duration::from_secs(11));
        g.tick(&playing(42, 300));
        assert_eq!(g.r.next_tick(c.now()), INTERVAL, "playing: the lease runs");
        assert_eq!(g.r.next_tick(c.now() + PLAYBACK_LEASE), Duration::from_secs(11), "past its lease");
        g.r.usb_present(&mut g.log);
        assert_eq!(g.r.next_tick(c.now()), Duration::from_secs(11), "the board on USB: USB's pace");
        // A short interval is kept as it is.
        let mut h = Rig::new(&c, &[]);
        h.r.interval = Duration::from_millis(500);
        h.qualify(&playing(42, 300));
        assert_eq!(h.r.next_tick(c.now()), Duration::from_millis(500));
    }

    /// The hold: at [`HOLD_IDLE`] of no input on this machine the radio
    /// sends nothing, ends its acquisition (the lock released), and starts
    /// no session, however long it lasts.
    #[test]
    fn the_hold_engages_at_hold_idle_and_sends_nothing() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.input_now();
        g.qualify(&snap());
        // A second short of the hold, the whole tick inside it: the
        // keepalive goes as before. (A tick the hold crosses: the two tests
        // after this one.)
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_secs(1)).duration_since(c.now()));
        let n = g.sent().len();
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [LINE, LINE, READOUT], "short of the hold");
        assert_eq!(g.r.state(), State::Qualified);
        // At the hold exactly: nothing.
        c.advance((input + HOLD_IDLE).duration_since(c.now()));
        let n = g.sent().len();
        g.tick(&snap());
        assert_eq!(g.sent().len(), n);
        assert_eq!(g.r.state(), State::Held);
        assert!(!g.r.acquired(), "the lock is released while held");
        assert!(!g.r.status.qualified);
        assert!(g.log.iter().any(|l| l.starts_with("radio: qualified -> held")), "{:?}", g.log);
        // Five minutes more of ticks, on a new track: no probe, no lock, no
        // text.
        let got = g.ticks(100, |_| Snapshot { title: "Another".into(), ..snap() });
        assert!(sending(&got).is_empty());
        assert_eq!(g.locks_taken.get(), 1);
        assert_eq!(g.r.state(), State::Held);
    }

    /// Input ends the hold: the next tick acquires as at the start (the lock,
    /// a new session's quiet), and its qualification sends the whole text.
    #[test]
    fn input_ends_the_hold_with_a_new_session_and_the_whole_text() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.input_now();
        g.qualify(&snap());
        c.advance(HOLD_IDLE);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Held);
        c.advance(Duration::from_secs(600));
        g.input_now();
        let n = g.sent().len();
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet, "a new session's quiet");
        assert_eq!(g.locks_taken.get(), 2);
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [PROBE, LINE, LINE, READOUT], "the keepalive not due: the whole text anyway");
    }

    /// With no idle time to read (not macOS or Windows, or the read failed),
    /// the radio never holds: the keepalive goes as before.
    #[test]
    fn without_an_idle_time_the_radio_never_holds() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.qualify(&snap());
        let got = g.ticks(100, |_| snap());
        assert_eq!(sending(&got).len(), 10, "a keepalive every 30 s for 300 s");
        assert_eq!(g.r.state(), State::Qualified);
    }

    /// Ticks a silent board from its first session's quiet to the backoff's
    /// cap, where the acquisition ends, and stops there, its 30 s backoff
    /// just begun; the probes it took.
    fn to_the_cap(g: &mut Rig) -> usize {
        g.tick(&snap());
        g.c.advance(QUIET);
        let mut probes = 0;
        loop {
            let before = g.sent().len();
            g.tick(&snap());
            probes += g.sent().len() - before;
            if !g.r.acquired() {
                return probes;
            }
            g.c.advance(g.r.hold_until.map_or(INTERVAL, |u| u.saturating_duration_since(g.c.now())));
            assert!(probes < 20, "never reached the cap");
        }
    }

    /// A board silent through the backoff (asleep): no new session on the
    /// timer alone, while the idle time says nobody has touched this machine.
    /// Before this change it was a new session about every 34 s.
    #[test]
    fn silence_at_the_cap_starts_no_session_on_the_timer_alone() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 64]);
        g.input_now();
        assert_eq!(to_the_cap(&mut g), 6, "1, 2, 4, 8 and 16 s, then the cap");
        assert_eq!(g.r.state(), State::Silent);
        assert!(g.log.iter().any(|l| l.contains("waits for input on this machine")), "{:?}", g.log);
        let n = g.sent().len();
        // 35 ticks, 105 s: still short of the hold, and no input.
        let got = g.ticks(35, |_| snap());
        assert!(sending(&got).is_empty(), "{:?}", sending(&got));
        assert_eq!(g.sent().len(), n);
        assert_eq!(g.locks_taken.get(), 1);
        assert_eq!(g.r.state(), State::Silent);
    }

    /// Input after the board went silent starts a session (a key on the
    /// keyboard wakes it and reaches this machine as input), at most once per
    /// [`SILENCE_CAP`] however busy the input; and no more without new input.
    #[test]
    fn input_after_the_silence_starts_one_session_at_most_once_per_cap() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 64]);
        g.input_now();
        to_the_cap(&mut g);
        // Typing from the next tick on, every tick, until four probes.
        let mut probes_at = Vec::new();
        let mut ticks = 0;
        while probes_at.len() < 4 {
            c.advance(INTERVAL);
            g.input_now();
            let before = g.sent().len();
            g.tick(&snap());
            if g.sent().len() > before {
                assert_eq!(&g.sent()[before..], [PROBE], "probes only, to a board that does not answer");
                probes_at.push(c.now());
            }
            ticks += 1;
            assert!(ticks < 100, "{probes_at:?}");
        }
        assert!(probes_at.windows(2).all(|w| w[1] - w[0] >= SILENCE_CAP), "{probes_at:?}");
        // The typing stops with the last probe (its input came before the
        // silence): no session after it.
        let n = g.sent().len();
        let locks = g.locks_taken.get();
        let got = g.ticks(30, |_| snap());
        assert!(sending(&got).is_empty());
        assert_eq!((g.sent().len(), g.locks_taken.get()), (n, locks));
    }

    /// A key on the sleeping board: it wakes, its key reaches this machine,
    /// and the next session finds it answering. The whole text goes.
    #[test]
    fn a_board_woken_by_its_key_gets_the_whole_text() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 6]);
        g.input_now();
        to_the_cap(&mut g);
        c.advance(SILENCE_CAP);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Silent, "no input yet: no session");
        g.input_now();
        let n = g.sent().len();
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [PROBE, LINE, LINE, READOUT]);
        assert_eq!(g.r.state(), State::Qualified);
    }

    /// The hold and the silence together: a board that went silent, then the
    /// hold, then input: the input both ends the hold and counts as new.
    #[test]
    fn input_after_a_silence_and_a_hold_starts_a_session() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 6]);
        g.input_now();
        to_the_cap(&mut g);
        c.advance(HOLD_IDLE);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Held);
        g.input_now();
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Qualified);
    }

    #[test]
    fn contention_sends_nothing_and_takes_the_lock_when_free() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.lock_free.set(false);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Contended);
        g.lock_free.set(true);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        assert!(g.sent().is_empty());
    }

    /// One key half a second after the board went silent, and none after:
    /// it counts once the backoff runs out (codex, the radio hold's review,
    /// 2: a timestamp gate with a second's slack ignored it for good).
    #[test]
    fn a_key_just_after_the_silence_counts_once_the_backoff_ends() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 6]);
        g.input_now();
        to_the_cap(&mut g);
        let capped = c.now();
        c.advance(Duration::from_millis(500));
        g.input_now();
        let n = g.sent().len();
        // Ticks through the backoff and past it, with no input after that key.
        let mut locks_at = None;
        for _ in 0..15 {
            c.advance(INTERVAL);
            g.tick(&snap());
            if locks_at.is_none() && g.locks_taken.get() == 2 {
                locks_at = Some(c.now());
            }
        }
        let locks_at = locks_at.expect("a session after the backoff");
        assert!(locks_at >= capped + SILENCE_CAP, "not before the backoff ran out");
        assert_eq!(&g.sent()[n..], [PROBE, LINE, LINE, READOUT], "the board answers it whole");
    }

    /// The hold rechecked inside the tick (codex, review 3): a probe whose
    /// reply crosses [`HOLD_IDLE`] qualifies nothing to write to. No text,
    /// no readout, the acquisition released.
    #[test]
    fn a_probe_reply_crossing_the_hold_sends_no_media() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        let calls = std::rc::Rc::new(Cell::new(0u32));
        let k = calls.clone();
        g.r.before_media = Some(Box::new(move || k.set(k.get() + 1)));
        g.input_now();
        g.tick(&snap()); // the lock, the quiet
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_millis(10)).duration_since(c.now()));
        g.tick(&snap()); // the probe's reply comes 20 ms later
        assert_eq!(g.sent(), [PROBE]);
        assert_eq!(g.r.state(), State::Held);
        assert!(!g.r.acquired() && !g.r.status.qualified);
        assert_eq!(calls.get(), 0, "no media request was begun");
        assert!(g.r.last_media_attempt.is_none());
    }

    /// And between the text and its readout: the text went before the hold,
    /// the readout would go after it, so it does not.
    #[test]
    fn the_hold_crossed_during_the_text_holds_its_readout() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.input_now();
        g.qualify(&snap());
        let input = g.input.get().unwrap();
        // The keepalive's tick 30 ms short of the hold; each line takes 20.
        c.advance((input + HOLD_IDLE - Duration::from_millis(30)).duration_since(c.now()));
        let n = g.sent().len();
        assert!(g.tick_returns(&snap()), "the text went");
        assert_eq!(&g.sent()[n..], [LINE, LINE]);
        assert_eq!(g.r.state(), State::Held);
        assert!(!g.r.acquired());
    }

    /// Before each text request too (codex, the verify, 3): a tick 10 ms
    /// short of the hold, its first line taking 21, sends no second line.
    #[test]
    fn a_second_line_that_would_start_past_the_hold_does_not() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.input_now();
        g.qualify(&snap());
        let shown = g.p.shown().cloned();
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_millis(10)).duration_since(c.now()));
        let n = g.sent().len();
        assert!(!g.tick_returns(&snap()), "the text did not go whole");
        assert_eq!(&g.sent()[n..], [LINE]);
        assert_eq!(g.r.state(), State::Held);
        assert!(!g.r.acquired());
        assert_eq!(g.p.shown().cloned(), shown, "the publisher did not move: a session's refresh sends it whole");
    }

    /// And after the revocation callback, which runs before the first media
    /// request: a slow one that takes the tick past the hold sends nothing.
    #[test]
    fn a_revocation_that_ends_past_the_hold_sends_no_media() {
        // The callback needs the clock for good: one leaked fake clock.
        let c: &'static FakeClock = Box::leak(Box::new(FakeClock::new()));
        let mut g = Rig::new(c, &[]);
        g.input_now();
        g.qualify(&snap());
        g.r.before_media = Some(Box::new(move || c.advance(Duration::from_millis(50))));
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_millis(10)).duration_since(c.now()));
        let n = g.sent().len();
        g.tick(&snap());
        assert_eq!(g.sent().len(), n);
        assert_eq!(g.r.state(), State::Held);
        assert!(!g.r.acquired());
    }

    /// A failure that ends the tick past the hold releases the acquisition
    /// at once, not a tick later (codex, the verify, 3): a probe timing out
    /// across it. The silence's 1 s backoff keeps its name until it runs
    /// out, as at the tick's start; `held` after.
    #[test]
    fn a_probe_timeout_crossing_the_hold_releases_the_acquisition() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[Board::Silent]);
        g.input_now();
        g.tick(&snap()); // the lock, the quiet
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_millis(50)).duration_since(c.now()));
        g.tick(&snap()); // the probe waits out its 100 ms deadline
        assert_eq!(g.sent(), [PROBE]);
        assert!(!g.r.acquired(), "released inside the tick");
        assert!(!g.r.status.qualified && g.r.status.session.is_none());
        assert_eq!(g.r.state(), State::Silent);
        c.advance(INTERVAL);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Held);
        assert_eq!(g.sent(), [PROBE]);
    }

    /// The hold ending inside a backoff does not cut it short: no session
    /// until it runs out. A backoff keeps its own state's name through the
    /// hold, and `held` shows once it has run out.
    #[test]
    fn a_hold_ending_inside_a_backoff_waits_the_backoff_out() {
        let c = FakeClock::new();
        // The probe answered, the first line BUSY: 30 s back off.
        let mut g = Rig::new(&c, &[Board::Answer { ms: 20 }, Board::Nak(ST_BUSY)]);
        g.input_now();
        g.tick(&snap());
        let input = g.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_secs(10)).duration_since(c.now()));
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Busy);
        let busy_until = g.r.hold_until.unwrap();
        c.advance(Duration::from_secs(12));
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Busy, "held inside the backoff: its name kept");
        assert!(!g.r.acquired(), "the hold released the lock");
        // Input inside the backoff ends the hold, not the backoff.
        c.advance(Duration::from_secs(6));
        g.input_now();
        let n = g.sent().len();
        g.tick(&snap());
        assert!(c.now() < busy_until);
        assert_eq!((g.sent().len(), g.locks_taken.get()), (n, 1), "nothing before the backoff runs out");
        c.advance(busy_until.duration_since(c.now()));
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        assert_eq!(g.locks_taken.get(), 2);
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [PROBE, LINE, LINE, READOUT]);
        // A backoff that runs out inside the hold shows `held` from then.
        let c = FakeClock::new();
        let mut h = Rig::new(&c, &[Board::Answer { ms: 20 }, Board::Nak(ST_BUSY)]);
        h.input_now();
        h.tick(&snap());
        let input = h.input.get().unwrap();
        c.advance((input + HOLD_IDLE - Duration::from_secs(10)).duration_since(c.now()));
        h.tick(&snap());
        c.advance(BUSY_BACKOFF);
        h.tick(&snap());
        assert_eq!(h.r.state(), State::Held);
    }

    /// The idle time readable, then not, then readable again (codex, review:
    /// the transitions). Unreadable, rules 1 and 2 stand aside at once; a
    /// first readable sample after counts no input, and holds at once if
    /// the idle is past the hold.
    #[test]
    fn the_idle_time_turning_unreadable_and_back() {
        // Held, then unreadable: the next tick acquires, as before the hold.
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.input_now();
        g.qualify(&snap());
        c.advance(HOLD_IDLE);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Held);
        g.unreadable.set(true);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        // Readable again, the idle still past the hold: held at once.
        g.unreadable.set(false);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Held);

        // Silent at the cap, then unreadable: the timer alone, a session at
        // the backoff's end.
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 64]);
        g.input_now();
        to_the_cap(&mut g);
        g.unreadable.set(true);
        c.advance(SILENCE_CAP);
        g.tick(&snap());
        assert_eq!((g.r.state(), g.locks_taken.get()), (State::Quiet, 2));

        // Unreadable at the cap: no wait for input is set up at all, and the
        // idle time turning readable after does not make one.
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &vec![Board::Silent; 64]);
        g.input_now();
        g.unreadable.set(true);
        to_the_cap(&mut g);
        assert!(!g.log.iter().any(|l| l.contains("waits for input")), "{:?}", g.log);
        g.unreadable.set(false);
        c.advance(SILENCE_CAP);
        g.tick(&snap());
        assert_eq!((g.r.state(), g.locks_taken.get()), (State::Quiet, 2));
    }

    #[test]
    fn silence_backs_off_and_releases_at_the_cap() {
        let c = FakeClock::new();
        let silent = vec![Board::Silent; 64];
        let mut g = Rig::new(&c, &silent);
        g.tick(&snap());
        c.advance(QUIET);
        let mut waits = Vec::new();
        for _ in 0..8 {
            let before = g.f.written.borrow().len();
            g.tick(&snap());
            if g.f.written.borrow().len() > before {
                waits.push(g.r.hold_until.map(|u| u.saturating_duration_since(c.now()).as_secs()));
            }
            c.advance(g.r.hold_until.map_or(Duration::from_secs(3), |u| u.saturating_duration_since(c.now())));
        }
        assert_eq!(g.r.state(), State::Silent);
        // Probes only: never text to a board that does not answer.
        assert!(g.sent().iter().all(|&s| s == (0x13, 0x01)));
        assert!(waits.windows(2).all(|w| w[0] <= w[1]), "{waits:?}");
        assert!(g.locks_taken.get() >= 2, "released at the cap, retaken after");
    }

    #[test]
    fn usb_presence_stands_the_radio_down_and_a_new_acquisition_refreshes_the_text() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.tick(&snap());
        c.advance(QUIET);
        g.tick(&snap());
        g.r.usb_present(&mut g.log);
        assert_eq!(g.r.state(), State::Off);
        // The cable out again: a new lock, a new quiet, then the full text even
        // though the keepalive is not due.
        c.advance(Duration::from_secs(3));
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        let n = g.sent().len();
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [(0x13, 0x01), (0x12, 0x03), (0x12, 0x03), (0x12, 0x04)]);
        assert_eq!(g.locks_taken.get(), 2);
    }

    #[test]
    fn no_dongle_is_absent_and_releases() {
        let c = FakeClock::new();
        let mut g = Rig::new(&c, &[]);
        g.tick(&snap());
        c.advance(QUIET);
        g.tick(&snap());
        g.dongle.set(false);
        c.advance(Duration::from_secs(3));
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Absent);
        assert!(g.r.link.is_none());
    }

    #[test]
    fn busy_after_admission_backs_off_and_forbidden_refuses() {
        let c = FakeClock::new();
        let script = [Board::Answer { ms: 20 }, Board::Nak(ST_BUSY)];
        let mut g = Rig::new(&c, &script);
        g.tick(&snap());
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Busy);
        assert!(g.r.hold_until.unwrap() >= c.now() + BUSY_BACKOFF - Duration::from_secs(1));

        let c2 = FakeClock::new();
        let mut h = Rig::new(&c2, &[Board::Answer { ms: 20 }, Board::Nak(ST_FORBIDDEN)]);
        h.tick(&snap());
        c2.advance(QUIET);
        h.tick(&snap());
        assert_eq!(h.r.state(), State::Refused);
        assert!(h.r.link.is_none());
    }

    #[test]
    fn before_media_runs_before_the_first_media_request_and_failures_stamp_the_attempt() {
        let c = FakeClock::new();
        // Probe ok, line 0 ok, line 1 incomplete: the media failed after
        // reaching the board, maybe.
        let script = [Board::Answer { ms: 20 }, Board::Answer { ms: 20 }, Board::ReceiptOnly];
        let mut g = Rig::new(&c, &script);
        let calls = std::rc::Rc::new(Cell::new(0usize));
        let seen = std::rc::Rc::new(Cell::new(usize::MAX));
        {
            let (calls, seen) = (calls.clone(), seen.clone());
            let got = g.f.got.as_ptr();
            g.r.before_media = Some(Box::new(move || {
                calls.set(calls.get() + 1);
                // What had gone out when it ran: the probe only.
                seen.set(unsafe { (*got).len() });
            }));
        }
        g.tick(&snap());
        assert_eq!(calls.get(), 0, "nothing before the quiet ends");
        assert!(g.r.last_media_attempt.is_none());
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(calls.get(), 1);
        assert_eq!(seen.get(), 1, "after the probe, before any media request");
        assert_eq!(g.r.status.pushes, 0, "the push failed");
        assert!(g.r.last_media_attempt.is_some(), "a failed media request still stamps the attempt");
    }

    #[test]
    fn a_failed_text_push_is_retried_next_tick() {
        let c = FakeClock::new();
        // Probe ok, line 0 ok, line 1 incomplete: the publisher does not move.
        let script = [Board::Answer { ms: 20 }, Board::Answer { ms: 20 }, Board::ReceiptOnly];
        let mut g = Rig::new(&c, &script);
        g.tick(&snap());
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.status.pushes, 0);
        let n = g.sent().len();
        c.advance(Duration::from_secs(3));
        g.tick(&snap());
        assert_eq!(&g.sent()[n..], [(0x12, 0x03), (0x12, 0x03), (0x12, 0x04)]);
        assert_eq!(g.r.status.pushes, 1);
    }

    #[test]
    fn stale_rotates_and_the_next_session_refreshes() {
        let c = FakeClock::new();
        let script = [Board::Answer { ms: 20 }, Board::Nak(ST_STALE)];
        let mut g = Rig::new(&c, &script);
        g.tick(&snap());
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Quiet);
        c.advance(QUIET);
        g.tick(&snap());
        assert_eq!(g.r.state(), State::Qualified);
        assert_eq!(g.r.status.sessions, 2);
        assert_eq!(g.locks_taken.get(), 1, "a rotation keeps the lock");
    }
}
