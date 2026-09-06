//! The daemon's loop: the now-playing publisher over a real board, presence as
//! a state machine, a bounded log and a status file.
//!
//! This is the phase-4a daemon — media only. The clock loop is deliberately
//! absent: it arrives with phase 3's gates (replay, then the measured
//! takeover), and until then the Python timekeeper owns the clock. See
//! "Staged switch-over" in plans/AK820-AGENT-PLAN.md.
//!
//! # One open per cycle
//!
//! Every three seconds: read the media worker's latest snapshot, decide what
//! is due ([`media::Publisher`]), open the board, write the text reports (if
//! due) and the playback readout, close. The handle is not held across the
//! sleep: holding it gains nothing — the interface is shareable and replies
//! broadcast to every handle — and while VIA is open a held handle's queue
//! fills with VIA's replies. Both text rows go through one open, back to
//! back, so the firmware's ~10 Hz repaint sees them in one tick.
//!
//! # Presence, as a state machine
//!
//! The plan is explicit that an unsuccessful open is **not** absence. So
//! [`Watch`] distinguishes absent (nothing of ours listed), busy (listed but
//! the open failed), refused (opened but not the interface we came for),
//! unresponsive (opened and then a transfer failed) and abandoned (a
//! cancellation never landed). Only a *transition* makes a log line, which is
//! the difference between a readable log and the Python agent's warning
//! every three seconds for as long as the cable is out.
//!
//! An abandoned handle is the one case with a backoff: its buffer, event and
//! handle are leaked on purpose, and reopening every cycle would leak one per
//! cycle — the phase-1 audit's finding 4 — so after one, opens pause for
//! [`ABANDON_BACKOFF`].

use std::path::PathBuf;
use std::time::{Duration, Instant};

use crate::clock::host::SystemHost;
use crate::hid::device::{self, Device, REQUEST_TIMEOUT};
use crate::hid::{self, Drained};
use crate::logfile::{self, Log};
use crate::media::{self, Publisher};
use crate::proto::Channel;
use crate::smtc::worker::MediaWorker;
use crate::smtc::Snapshot;
use crate::status::{self, Status};

/// How long opens pause after a cancellation that never landed.
pub const ABANDON_BACKOFF: Duration = Duration::from_secs(60);

/// How long the first cycle waits for the media worker's first poll, so the
/// first push is the real state rather than a clear followed by the track.
pub const FIRST_POLL_GRACE: Duration = Duration::from_secs(2);

/// Where the board is, as far as the last cycle could tell.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Presence {
    /// No cycle has run yet.
    Unknown,
    /// Opened and answered.
    Present,
    /// Nothing of ours in the Configuration Manager's list: unplugged, or
    /// the slider is not on `cable`.
    Absent,
    /// Listed, but the open failed — another process, or a device mid-reset.
    Busy,
    /// Opened, and not the interface we came for, or more than one board.
    Refused,
    /// Opened, and a transfer then failed or timed out.
    Unresponsive,
    /// A cancellation never completed; that handle is leaked and opens pause.
    Abandoned,
}

impl Presence {
    pub fn word(self) -> &'static str {
        match self {
            Presence::Unknown => "unknown",
            Presence::Present => "present",
            Presence::Absent => "absent",
            Presence::Busy => "busy",
            Presence::Refused => "refused",
            Presence::Unresponsive => "unresponsive",
            Presence::Abandoned => "abandoned",
        }
    }
}

/// The presence state machine. Pure: it is told what happened and says
/// whether that is news.
#[derive(Debug)]
pub struct Watch {
    state: Presence,
    failures: u32,
    hold_until: Option<Instant>,
}

impl Default for Watch {
    fn default() -> Self {
        Watch::new()
    }
}

impl Watch {
    pub fn new() -> Watch {
        Watch {
            state: Presence::Unknown,
            failures: 0,
            hold_until: None,
        }
    }

    pub fn state(&self) -> Presence {
        self.state
    }

    /// Consecutive failed cycles.
    pub fn failures(&self) -> u32 {
        self.failures
    }

    /// Should this cycle skip opening the board?
    pub fn holding(&self, now: Instant) -> bool {
        self.hold_until.is_some_and(|until| now < until)
    }

    /// What this cycle's outcome means, and a log line if it is a change.
    pub fn observe(&mut self, outcome: Result<(), &hid::Error>, now: Instant) -> Option<String> {
        let next = match outcome {
            Ok(()) => Presence::Present,
            Err(hid::Error::Absent) => Presence::Absent,
            Err(hid::Error::Open { .. }) | Err(hid::Error::Discovery(_)) => Presence::Busy,
            Err(hid::Error::Ambiguous(_)) | Err(hid::Error::Incompatible { .. }) => {
                Presence::Refused
            }
            Err(hid::Error::Stuck) => Presence::Abandoned,
            Err(_) => Presence::Unresponsive,
        };
        if next == Presence::Present {
            self.failures = 0;
        } else {
            self.failures += 1;
        }
        if next == Presence::Abandoned {
            self.hold_until = Some(now + ABANDON_BACKOFF);
        }
        if next == self.state {
            return None;
        }
        let was = self.state;
        self.state = next;
        Some(match outcome {
            Ok(()) => format!("board: {} -> present", was.word()),
            Err(e) => format!("board: {} -> {} ({e})", was.word(), next.word()),
        })
    }
}

/// What the daemon was started with.
pub struct Options {
    pub interval: Duration,
    pub log: PathBuf,
    pub status: PathBuf,
    /// One cycle, then return — for a check from a terminal.
    pub once: bool,
}

/// `%LOCALAPPDATA%\ak820pro`: the directory the PowerShell installer put the
/// Python agents' logs in, so the migration reads as one story.
pub fn default_dir() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("USERPROFILE").map(|p| PathBuf::from(p).join("AppData").join("Local")))
        .unwrap_or_else(|| PathBuf::from("."))
        .join("ak820pro")
}

/// Run until the process is ended (or once, with `once`).
pub fn run(opts: Options) -> Result<(), String> {
    let log = Log::at(&opts.log);
    let version = crate::version_line("ak820-agent");
    log.line(&version);
    log.line(&format!(
        "polling SMTC every {}s (keepalive {}s)",
        opts.interval.as_secs_f64(),
        media::KEEPALIVE.as_secs()
    ));

    let worker = MediaWorker::spawn(opts.interval);
    let mut publisher = Publisher::new();
    let mut watch = Watch::new();
    let mut st = Status {
        version,
        started: logfile::stamp(&SystemHost),
        ..Status::default()
    };

    // The Python agent read SMTC synchronously, so its first push was the
    // true state. The worker publishes asynchronously, and the first live run
    // pushed a CLEAR before its first poll had landed, then the track four
    // seconds later — a blink of the band on every start. So give the first
    // poll a moment; a media broker that takes longer than this is what the
    // worker's health counters are for.
    let deadline = Instant::now() + FIRST_POLL_GRACE;
    while worker.latest().1.polls == 0 && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }

    loop {
        let (snapshot, health) = worker.latest();
        let now = Instant::now();

        if !watch.holding(now) {
            let plan = publisher.plan(&snapshot, now);
            let outcome = cycle(&plan, &snapshot, now, &mut publisher, &log, &mut st);
            if let Some(line) = watch.observe(outcome.as_ref().map(|_| ()), now) {
                log.line(&line);
            }
        }

        st.board = watch.state().word().to_string();
        st.updated = logfile::stamp(&SystemHost);
        st.smtc_polls = health.polls;
        st.smtc_failures = health.failures;
        st.smtc_last_error = health.last_error;
        if let Err(e) = status::write(&opts.status, &st) {
            log.line(&format!("[warn] status file: {e}"));
        }

        if opts.once {
            return Ok(());
        }
        std::thread::sleep(opts.interval);
    }
}

/// One open, the due reports, close.
fn cycle(
    plan: &media::Plan,
    snapshot: &Snapshot,
    now: Instant,
    publisher: &mut Publisher,
    log: &Log,
    st: &mut Status,
) -> Result<(), hid::Error> {
    let dev = device::open_board()?;
    if let Some(text) = &plan.text {
        match send(&dev, text) {
            Ok(foreign) => {
                publisher.text_pushed(snapshot, now);
                st.media_last_push = Some(logfile::stamp(&SystemHost));
                st.media_last_text = Some(Publisher::describe(snapshot));
                st.media_last_error = None;
                st.foreign_reports += foreign;
                if plan.changed {
                    log.line(&Publisher::describe(snapshot));
                }
            }
            Err(e) => {
                log.line(&format!("[warn] push: {e}"));
                st.media_last_error = Some(e.to_string());
                return Err(e);
            }
        }
    }
    match dev.request(Channel::Text, plan.playback.0, &plan.playback.1, REQUEST_TIMEOUT) {
        Ok(reply) => {
            st.foreign_reports += reply.drained.len() as u64;
            Ok(())
        }
        Err(e) => {
            log.line(&format!("[warn] playback: {e}"));
            st.media_last_error = Some(e.to_string());
            Err(e)
        }
    }
}

/// Write the reports in order through one handle; count what had to be
/// discarded on the way, which is the only direct evidence of another
/// process on the board.
fn send(dev: &Device, reports: &[(u8, Vec<u8>)]) -> Result<u64, hid::Error> {
    let mut foreign = 0u64;
    for (command, body) in reports {
        let reply = dev.request(Channel::Text, *command, body, REQUEST_TIMEOUT)?;
        foreign += reply
            .drained
            .iter()
            .filter(|d| matches!(d, Drained::Foreign(_)))
            .count() as u64;
    }
    Ok(foreign)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn now() -> Instant {
        Instant::now()
    }

    #[test]
    fn the_first_observation_is_always_news() {
        let mut w = Watch::new();
        assert_eq!(w.observe(Ok(()), now()), Some("board: unknown -> present".into()));
        assert_eq!(w.state(), Presence::Present);
    }

    /// The point of the machine: a steady state makes no lines, a change makes
    /// one, and coming back makes one more.
    #[test]
    fn only_transitions_make_log_lines() {
        let mut w = Watch::new();
        w.observe(Ok(()), now());
        assert_eq!(w.observe(Ok(()), now()), None);
        let line = w.observe(Err(&hid::Error::Absent), now()).unwrap();
        assert!(line.starts_with("board: present -> absent ("), "{line}");
        assert_eq!(w.observe(Err(&hid::Error::Absent), now()), None);
        assert_eq!(w.observe(Err(&hid::Error::Absent), now()), None);
        assert_eq!(w.failures(), 3);
        assert_eq!(w.observe(Ok(()), now()), Some("board: absent -> present".into()));
        assert_eq!(w.failures(), 0);
    }

    /// An open that failed is busy, not absent — the plan's presence rule.
    #[test]
    fn a_failed_open_is_busy_not_absent() {
        let mut w = Watch::new();
        let open = hid::Error::Open {
            path: "x".into(),
            source: windows::core::Error::from_hresult(windows::core::HRESULT::from_win32(32)),
        };
        w.observe(Err(&open), now());
        assert_eq!(w.state(), Presence::Busy);
        let timeout = hid::Error::Timeout { drained: vec![] };
        w.observe(Err(&timeout), now());
        assert_eq!(w.state(), Presence::Unresponsive);
        w.observe(Err(&hid::Error::Ambiguous(vec![])), now());
        assert_eq!(w.state(), Presence::Refused);
    }

    /// An abandoned handle pauses opens, so a wedged driver costs one leaked
    /// handle per minute rather than one per cycle.
    #[test]
    fn an_abandoned_handle_holds_opens_for_a_minute() {
        let mut w = Watch::new();
        let t = now();
        assert!(!w.holding(t));
        w.observe(Err(&hid::Error::Stuck), t);
        assert_eq!(w.state(), Presence::Abandoned);
        assert!(w.holding(t + Duration::from_secs(59)));
        assert!(!w.holding(t + ABANDON_BACKOFF));
    }

    #[test]
    fn the_default_dir_is_under_local_appdata() {
        let d = default_dir();
        assert!(d.ends_with("ak820pro"));
        assert!(d.is_absolute());
    }
}
