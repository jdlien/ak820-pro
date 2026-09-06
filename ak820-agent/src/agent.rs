//! The daemon's loop: the now-playing publisher over a real board, presence as
//! a state machine, a bounded log, a status file — and, with `--clock`, the
//! clock loop.
//!
//! # One open per interaction
//!
//! Every board interaction — a media push, a clock transaction, a status
//! read, a health read — is its own short open, closed before the next. The
//! handle is not held across a sleep: holding it gains nothing (the interface
//! is shareable and replies broadcast to every handle) and while VIA is open
//! a held handle's queue fills with VIA's replies. Both text rows go through
//! one open, back to back, so the firmware's ~10 Hz repaint sees them in one
//! tick.
//!
//! # Presence, as one state machine for everything
//!
//! The plan is explicit that an unsuccessful open is **not** absence. So
//! [`Watch`] distinguishes absent, busy, refused, unresponsive and abandoned,
//! and only a *transition* makes a log line. Every interaction reports its
//! outcome to the same `Watch` — media, clock, health alike — and every one
//! consults its backoff, so an abandoned handle (a cancellation that never
//! landed, leaked on purpose) pauses **all** opens for [`ABANDON_BACKOFF`]
//! rather than leaking one per cycle (the phase-1 audit's finding 4, and the
//! phase-3a/4a audit's finding 6, which found the clock bypassing it).
//!
//! # Two schedules, independent
//!
//! The media poll runs every `interval` and the clock loop every
//! [`scheduler::LOOP`], each measured from the **end** of its own work as
//! the Python's `sleep` after the work is. Neither waits on the other's
//! period: with `--interval 120` the clock still ticks every 15 s (finding
//! 14: tied to the media sleep, every sync became a `wake`).
//!
//! # A lost reply and a fresh handle
//!
//! The driver queues per file object, so a reply already queued on a handle
//! disappears with it — but a reply that arrives **after** the next handle
//! opens lands on that one, and a lost clock GET's straggler would then
//! satisfy the next GET (finding 4). So the clock loop remembers that a
//! command went unanswered and, before its next open, resynchronises on the
//! new handle exactly as `exchange::resynchronise` does on an old one: drain,
//! settle, drain, and proceed only if both were empty.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use crate::clock::cache::{Cache, FileCache};
use crate::clock::host::{Host, SystemHost};
use crate::clock::scheduler::{self, Learn, Reason, Scheduler, StatusRead, SyncResult};
use crate::clock::transaction;
use crate::health;
use crate::hid::device::{self, Device, Queue, REQUEST_TIMEOUT};
use crate::hid::exchange::RESYNC_SETTLE;
use crate::hid::{self, path, Drained};
use crate::logfile::{self, Log};
use crate::media::{self, Publisher};
use crate::proto::Channel;
use crate::smtc::worker::MediaWorker;
use crate::smtc::Snapshot;
use crate::status::{self, ClockStatus, HealthStatus, Status};

/// How long opens pause after a cancellation that never landed.
pub const ABANDON_BACKOFF: Duration = Duration::from_secs(60);

/// How long the first cycle waits for the media worker's first poll. It
/// reduces the blink of a `CLEAR` before the first real push to the case of
/// a media broker slower than this; it cannot remove it.
pub const FIRST_POLL_GRACE: Duration = Duration::from_secs(2);

/// How often the health pages are read into the status file.
pub const HEALTH_INTERVAL: Duration = Duration::from_secs(300);

/// The longest the loop sleeps between looking at its schedules.
const SLICE: Duration = Duration::from_millis(500);

/// Where the board is, as far as the last interaction could tell.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Presence {
    /// No interaction has happened yet.
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

    /// Consecutive failed interactions.
    pub fn failures(&self) -> u32 {
        self.failures
    }

    /// Should every open be skipped right now?
    pub fn holding(&self, now: Instant) -> bool {
        self.hold_until.is_some_and(|until| now < until)
    }

    /// What an interaction's outcome means, and a log line if it is a change.
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
    /// One pass, then return — for a check from a terminal.
    pub once: bool,
    /// Run the clock loop too. ⚠️ Phase 4b: only when nothing else owns the
    /// clock, which `ak820 install --clock` arranges by removing the Python
    /// timekeeper's task. Two clock writers corrupt each other's learners.
    pub clock: bool,
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

/// The foreign reports among what a request threw away — arrived while we
/// waited and answered somebody else. Stale reports (queued before we asked)
/// are not counted: they are ours from an earlier request as often as not.
fn foreign(discarded: &[Drained]) -> u64 {
    discarded
        .iter()
        .filter(|d| matches!(d, Drained::Foreign(_)))
        .count() as u64
}

/// What a failed request threw away before failing. A timeout's discards are
/// the only evidence of who else was on the wire while we waited.
fn discards_of(e: &hid::Error) -> &[Drained] {
    match e {
        hid::Error::Timeout { drained } | hid::Error::Dirty { drained, .. } => drained,
        _ => &[],
    }
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

    let worker = MediaWorker::spawn(opts.interval)?;
    let mut publisher = Publisher::new();
    let mut watch = Watch::new();
    let mut st = Status {
        version,
        started: logfile::stamp(&SystemHost),
        ..Status::default()
    };
    let mut clock = if opts.clock {
        log.line(&format!(
            "clock loop: syncing every {}s ({}s while the residual exceeds {} ms); cache {}",
            scheduler::SYNC_INTERVAL,
            scheduler::SYNC_INTERVAL_FAST,
            scheduler::FAST_ABOVE_MS,
            FileCache::default_path().display()
        ));
        Some(ClockLoop::new(SystemHost.now()))
    } else {
        None
    };

    // The Python agent read SMTC synchronously, so its first push was the
    // true state; the worker publishes asynchronously. Give the first poll a
    // moment so the first push is not a CLEAR followed by the track.
    let deadline = Instant::now() + FIRST_POLL_GRACE;
    while worker.latest().1.polls == 0 && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }

    let mut next_media = Instant::now();
    let mut next_clock = Instant::now();
    let mut next_health = Instant::now();
    let mut poll_was_ok = true;

    loop {
        let now = Instant::now();
        let mut worked = false;

        if now >= next_media {
            worked = true;
            let (snapshot, health) = worker.latest();
            // A failed read publishes idle, as the Python's `run()` does when
            // `read_state()` raises. Keeping the previous track would refresh
            // it every 30 s and never let the firmware's expiry take it down
            // (the phase-3a/4a audit's finding 5).
            if health.last_poll_ok != poll_was_ok {
                match &health.last_error {
                    Some(e) if !health.last_poll_ok => log.line(&format!("[warn] read_state: {e}")),
                    _ => log.line("read_state: recovered"),
                }
                poll_was_ok = health.last_poll_ok;
            }
            let snapshot = if health.last_poll_ok { snapshot } else { Snapshot::default() };
            if !watch.holding(now) {
                let plan = publisher.plan(&snapshot, now);
                let mut discarded = Vec::new();
                let outcome = cycle(&plan, &snapshot, now, &mut publisher, &log, &mut st, &mut discarded);
                st.foreign_reports += foreign(&discarded);
                if let Some(line) = watch.observe(outcome.as_ref().map(|_| ()), now) {
                    log.line(&line);
                }
            }
            st.smtc_polls = health.polls;
            st.smtc_failures = health.failures;
            st.smtc_last_error = health.last_error;
            st.smtc_stale_s = health.stale_for.map(|d| d.as_secs());
            next_media = Instant::now() + opts.interval;
        }

        if let Some(clock) = clock.as_mut() {
            if now >= next_clock {
                worked = true;
                if !watch.holding(now) {
                    clock.tick(&log, &mut st, &mut watch);
                }
                st.clock = Some(clock.status.clone());
                next_clock = Instant::now() + Duration::from_secs_f64(scheduler::LOOP);
            }
        }

        if now >= next_health && !watch.holding(now) {
            worked = true;
            let mut discarded = Vec::new();
            match read_health(&mut discarded) {
                Ok(h) => st.health = Some(h),
                Err(HealthRead::Hid(e)) => {
                    if let Some(line) = watch.observe(Err(&e), now) {
                        log.line(&line);
                    }
                }
                Err(HealthRead::Decode(e)) => log.line(&format!("[warn] health: {e}")),
            }
            st.foreign_reports += foreign(&discarded);
            next_health = Instant::now() + HEALTH_INTERVAL;
        }

        if worked {
            st.board = watch.state().word().to_string();
            st.updated = logfile::stamp(&SystemHost);
            if let Err(e) = status::write(&opts.status, &st) {
                log.line(&format!("[warn] status file: {e}"));
            }
            if opts.once {
                return Ok(());
            }
        }

        let next = [Some(next_media), clock.as_ref().map(|_| next_clock), Some(next_health)]
            .into_iter()
            .flatten()
            .min()
            .unwrap_or(next_media);
        std::thread::sleep(next.saturating_duration_since(Instant::now()).min(SLICE));
    }
}

/// One media open: the text if due, then the playback readout — the second
/// attempted whether or not the first succeeded, as the Python's two `try`
/// blocks are independent (finding 9). A `Stuck` handle ends the cycle at
/// once; nothing else does.
fn cycle(
    plan: &media::Plan,
    snapshot: &Snapshot,
    now: Instant,
    publisher: &mut Publisher,
    log: &Log,
    st: &mut Status,
    discarded: &mut Vec<Drained>,
) -> Result<(), hid::Error> {
    let dev = device::open_board()?;
    let mut failure: Option<hid::Error> = None;
    if let Some(text) = &plan.text {
        match send(&dev, text, discarded) {
            Ok(()) => {
                publisher.text_pushed(snapshot, now);
                st.media_last_push = Some(logfile::stamp(&SystemHost));
                st.media_last_text = Some(Publisher::describe(snapshot));
                st.media_last_error = None;
                if plan.changed {
                    log.line(&Publisher::describe(snapshot));
                }
            }
            Err(e) => {
                log.line(&format!("[warn] push: {e}"));
                st.media_last_error = Some(e.to_string());
                if matches!(e, hid::Error::Stuck) {
                    return Err(e);
                }
                failure = Some(e);
            }
        }
    }
    match dev.request_echoed(Channel::Text, plan.playback.0, &plan.playback.1, REQUEST_TIMEOUT) {
        Ok(reply) => discarded.extend(reply.drained),
        Err(e) => {
            discarded.extend(discards_of(&e).iter().copied());
            log.line(&format!("[warn] playback: {e}"));
            st.media_last_error = Some(e.to_string());
            if failure.is_none() || matches!(e, hid::Error::Stuck) {
                failure = Some(e);
            }
        }
    }
    match failure {
        None => Ok(()),
        Some(e) => Err(e),
    }
}

/// Write the reports in order through one handle, each correlated on its own
/// echo, keeping every discard whether the batch succeeds or not.
fn send(dev: &Device, reports: &[(u8, Vec<u8>)], discarded: &mut Vec<Drained>) -> Result<(), hid::Error> {
    for (command, body) in reports {
        match dev.request_echoed(Channel::Text, *command, body, REQUEST_TIMEOUT) {
            Ok(reply) => discarded.extend(reply.drained),
            Err(e) => {
                discarded.extend(discards_of(&e).iter().copied());
                return Err(e);
            }
        }
    }
    Ok(())
}

enum HealthRead {
    Hid(hid::Error),
    Decode(health::Error),
}

/// Pages 1 and 2 on one open: the counters that say whether the firmware is
/// stalling, read before the clock takeover can add stalls of its own.
fn read_health(discarded: &mut Vec<Drained>) -> Result<HealthStatus, HealthRead> {
    let dev = device::open_board().map_err(HealthRead::Hid)?;
    let mut page = |command: u8| -> Result<[u8; 32], HealthRead> {
        match dev.request(Channel::Health, command, &[], REQUEST_TIMEOUT) {
            Ok(reply) => {
                discarded.extend(reply.drained);
                Ok(reply.report)
            }
            Err(e) => {
                discarded.extend(discards_of(&e).iter().copied());
                Err(HealthRead::Hid(e))
            }
        }
    };
    let p1 = health::Page1::decode(&page(health::GET)?).map_err(HealthRead::Decode)?;
    let p2 = health::Page2::decode(&page(health::GET2)?).map_err(HealthRead::Decode)?;
    Ok(HealthStatus {
        read_at: logfile::stamp(&SystemHost),
        version: p1.version,
        loop_gap_max_ms: p1.loop_gap_max_ms,
        blit_timeouts: p1.blit_timeouts,
        tx_timeouts: p1.tx_timeouts,
        wdt_consecutive_resets: p1.wdt_consecutive_resets,
        count_ge_25ms: p2.count_ge_25ms,
        count_ge_25ms_nonflash: p2.count_ge_25ms_nonflash,
        count_ge_10ms: p2.count_ge_10ms,
        loop_gap_max_mark: p2.loop_gap_max_mark.text(),
    })
}

// ---------------------------------------------------------------------------
// The clock loop
// ---------------------------------------------------------------------------

/// `ak820-timekeeper.py`'s `main()` body, one iteration per
/// [`scheduler::LOOP`], over the in-process transaction instead of a spawned
/// `ak820ctl`. Every board interaction is one short open.
struct ClockLoop {
    sched: Scheduler,
    cache: FileCache,
    /// Monotonic seconds for the learner's `elapsed`, as `time.monotonic()`.
    epoch: Instant,
    /// A command went out on a handle that is now closed without being
    /// answered. Its reply, if it ever comes, lands on whatever handle is open
    /// then — so the next open resynchronises before trusting the queue.
    unresolved: bool,
    status: ClockStatus,
}

impl ClockLoop {
    fn new(now_wall: f64) -> ClockLoop {
        let cache = FileCache::at(FileCache::default_path());
        let cap = cache.load();
        ClockLoop {
            sched: Scheduler::new(now_wall),
            cache,
            epoch: Instant::now(),
            unresolved: false,
            status: ClockStatus {
                interval_s: scheduler::SYNC_INTERVAL as u64,
                lead_ms: format!("{:.3}", cap.lead_ms),
                bias_ppm: cap.bias_ppm,
                ..ClockStatus::default()
            },
        }
    }

    fn mono(&self) -> f64 {
        self.epoch.elapsed().as_secs_f64()
    }

    /// Open the board for a clock interaction, resynchronising first when a
    /// command is unaccounted for.
    fn open(&mut self, log: &Log) -> Result<Device, hid::Error> {
        let dev = device::open_board()?;
        if self.unresolved {
            let (_, first) = dev.drain();
            std::thread::sleep(RESYNC_SETTLE);
            let (late, second) = dev.drain();
            if first == Queue::Stuck || second == Queue::Stuck {
                return Err(hid::Error::Stuck);
            }
            if first != Queue::Empty || second != Queue::Empty {
                return Err(hid::Error::Dirty {
                    queue: second,
                    drained: late,
                });
            }
            self.unresolved = false;
            if !late.is_empty() {
                log.line(&format!(
                    "clock: resynchronised on a fresh handle; {} late report(s) discarded",
                    late.len()
                ));
            }
        }
        Ok(dev)
    }

    /// Could this failure have left a command the board will still answer?
    fn note(&mut self, e: &hid::Error) {
        if matches!(
            e,
            hid::Error::Timeout { .. } | hid::Error::Unresolved { .. } | hid::Error::Io { .. } | hid::Error::Stuck
        ) {
            self.unresolved = true;
        }
    }

    /// One iteration of the Python loop body.
    fn tick(&mut self, log: &Log, st: &mut Status, watch: &mut Watch) {
        let host = SystemHost;
        let wall = host.now();
        // `hid_present()`: the Configuration Manager's list, opening nothing.
        let listed = device::interfaces(path::VID, path::PID).unwrap_or_default();
        let present = !listed.is_empty();

        if let Some(reason) = self.sched.due(wall, present) {
            if reason == Reason::Enumerated {
                std::thread::sleep(Duration::from_secs_f64(scheduler::ENUMERATED_SETTLE));
            }
            let (result, line) = self.sync(reason, log, st, watch);
            log.line(&line);
            self.status.last_line = Some(line);
            self.sched.synced(&result, host.now());
            if result.ok {
                self.status.syncs += 1;
                self.status.last_sync = Some(logfile::stamp(&host));
                self.status.last_error = None;
                // learn_bias: the timestamp is taken BEFORE the status read
                let now_mono = self.mono();
                let status = self.read_status(log, st, watch);
                let cache_bias = self.cache.load().bias_ppm;
                let decision = self.sched.learn(reason, &result, status.as_ref(), cache_bias, now_mono);
                match &decision {
                    Learn::Learned { b_new_rounded, .. } => {
                        let mut cap = self.cache.load();
                        cap.bias_ppm = Some(*b_new_rounded);
                        match self.cache.save(&cap) {
                            Ok(()) => {
                                if let Some(l) = decision.log_line() {
                                    log.line(&l);
                                }
                            }
                            Err(e) => {
                                // the Python raised out of learn_bias() here
                                self.sched.cache_write_failed();
                                log.line(&format!("bias learn error: {e}"));
                            }
                        }
                    }
                    Learn::Hold { .. } => {
                        if let Some(l) = decision.log_line() {
                            log.line(&l);
                        }
                    }
                    Learn::Baseline | Learn::Declined => {}
                }
            } else {
                self.status.failures += 1;
            }
            self.status.interval_s = self.sched.interval() as u64;
        }

        if present {
            // bias_step: the seed, only while the cache has no bias
            let cap = self.cache.load();
            if cap.bias_ppm.is_some() {
                self.sched.seed_step(true, None, "", host.now());
            } else {
                let status = self.read_status(log, st, watch);
                let cid: Vec<&str> = listed.iter().map(|i| i.path()).collect();
                let cid = cid.join("|");
                let step = self.sched.seed_step(false, status.as_ref(), &cid, host.now());
                if let Some(b) = step.bias_to_cache() {
                    let mut cap = self.cache.load();
                    cap.bias_ppm = Some(b);
                    match self.cache.save(&cap) {
                        Ok(()) => {
                            if let Some(l) = step.log_line(&cid) {
                                log.line(&l);
                            }
                        }
                        Err(e) => log.line(&format!("bias step error: {e}")),
                    }
                }
            }
        }

        let cap = self.cache.load();
        self.status.lead_ms = format!("{:.3}", cap.lead_ms);
        self.status.bias_ppm = cap.bias_ppm;
        self.sched.end_loop(present, host.now());
    }

    /// `sync()`: one transaction on a fresh handle. Returns what the Python's
    /// `sync()` returns and the log line it writes.
    fn sync(&mut self, reason: Reason, log: &Log, st: &mut Status, watch: &mut Watch) -> (SyncResult, String) {
        let now = Instant::now();
        let mut discarded = Vec::new();
        let outcome = match self.open(log) {
            Ok(dev) => transaction::run(
                &dev,
                dev.outstanding(),
                &SystemHost,
                &self.cache,
                REQUEST_TIMEOUT,
                &mut discarded,
            ),
            Err(e) => Err(transaction::Error::Hid(e)),
        };
        st.foreign_reports += foreign(&discarded);
        match outcome {
            Ok(out) => {
                if let Err(e) = &out.cache_saved {
                    log.line(&format!("[warn] cache: {e}"));
                }
                let seen = match &out.verify_error {
                    Some(e) => {
                        self.note(e);
                        Err(e)
                    }
                    None => Ok(()),
                };
                if let Some(line) = watch.observe(seen, now) {
                    log.line(&line);
                }
                let report = out.report();
                let last = report.lines().last().unwrap_or("").to_string();
                let reported = out.as_reported();
                (
                    SyncResult {
                        ok: true,
                        before_ms: reported.before_ms,
                        slewing: reported.slewing,
                    },
                    scheduler::sync_log_line(reason, &last, 0),
                )
            }
            Err(e) => {
                if let transaction::Error::Hid(h) = &e {
                    self.note(h);
                    discarded.extend(discards_of(h).iter().copied());
                    if let Some(line) = watch.observe(Err(h), now) {
                        log.line(&line);
                    }
                } else if let Some(line) = watch.observe(Ok(()), now) {
                    // the board answered; the firmware declined
                    log.line(&line);
                }
                let text = e.to_string();
                self.status.last_error = Some(text.clone());
                (
                    SyncResult {
                        ok: false,
                        before_ms: None,
                        slewing: false,
                    },
                    scheduler::sync_log_line(reason, &text, 1),
                )
            }
        }
    }

    /// `read_status()`: one GET on a fresh handle; `None` on any failure or
    /// an unset clock, as the Python's `rc != 0` is.
    fn read_status(&mut self, log: &Log, st: &mut Status, watch: &mut Watch) -> Option<StatusRead> {
        let now = Instant::now();
        let got = self
            .open(log)
            .and_then(|dev| transaction::read_once(&dev, dev.outstanding(), &SystemHost, REQUEST_TIMEOUT));
        match got {
            Ok(got) => {
                st.foreign_reports += foreign(&got.drained);
                if let Some(line) = watch.observe(Ok(()), now) {
                    log.line(&line);
                }
                if !got.board.understood() {
                    return None;
                }
                StatusRead::from_board(&got.board, got.sample.map(|s| s.offset_ms))
            }
            Err(e) => {
                self.note(&e);
                st.foreign_reports += foreign(discards_of(&e));
                if let Some(line) = watch.observe(Err(&e), now) {
                    log.line(&line);
                }
                None
            }
        }
    }
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

    /// Foreign reports are counted; stale ones — queued before we asked, as
    /// often ours as anyone's — are not.
    #[test]
    fn only_foreign_reports_count_as_foreign() {
        use crate::proto::Mismatch;
        let d = [
            Drained::Foreign(Mismatch::OtherEcho),
            Drained::Stale { header: [7, 0x12, 4] },
            Drained::Foreign(Mismatch::TooShort),
            Drained::StaleUnreadable(Mismatch::TooShort),
        ];
        assert_eq!(foreign(&d), 2);
        let timeout = hid::Error::Timeout { drained: d.to_vec() };
        assert_eq!(foreign(discards_of(&timeout)), 2);
        assert!(discards_of(&hid::Error::Absent).is_empty());
    }

    #[test]
    fn the_default_dir_is_under_local_appdata() {
        let d = default_dir();
        assert!(d.ends_with("ak820pro"));
        assert!(d.is_absolute());
    }
}
