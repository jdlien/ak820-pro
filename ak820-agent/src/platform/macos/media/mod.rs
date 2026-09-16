//! Phase 3: now-playing on macOS, behind the neutral [`MediaSource`].
//!
//! ```text
//! perl + nowplaying-mediaremote.dylib --line-JSON--> helper::Supervisor
//!                                                        |
//!                                     Engine: route::Router (5 s stickiness)
//!                                             canary::Canary (S1b)
//!                                             applescript fallback
//!                                                        |
//!                                     MediaRemoteSource::latest() --> agent
//! ```
//!
//! **MediaRemote is the source for everything, Music included** (plan, Phase
//! 3; `fc70de4` in the sibling made Music answer). AppleScript is read in three
//! cases only, each logged when it starts and ends:
//!
//! - **Stale:** MediaRemote names Music or Spotify as the owner but will not
//!   describe it. Only that player is asked (the sibling's rule).
//! - **Silent:** the helper has failed, meaning 60 s without proof of life
//!   ([`helper`]). Every running player is asked, because nothing else can be.
//! - **Refused:** the S1b canary saw MediaRemote report nothing while a player
//!   said `playing`, twice. Undone the moment MediaRemote names an app again.
//!
//! In every other state, which is almost every hour, **no Apple event is sent
//! and nothing is spawned**. The canary adds at most one `player state` per
//! 60 s, and only while MediaRemote reports nothing and a player is running.
//!
//! The failure policy is the neutral one, with its input defined here (plan,
//! *`MediaSource`*): a poll fails when the helper has failed and nothing could
//! be read instead, when an AppleScript read that was needed fails, or when
//! Automation consent is refused. A denial is **never** reported as idle (G-B).
//! It stays in `last_error` until an AppleScript read succeeds or MediaRemote
//! names an app again.
//!
//! The snapshot is computed in [`MediaRemoteSource::latest`], at the moment the
//! daemon asks, so the extrapolated position is not up to a poll late.

pub mod applescript;
pub mod canary;
pub mod helper;
mod json;
pub mod message;
pub mod players;
pub mod route;

use std::path::PathBuf;
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use self::applescript::{Asker, Outcome, Reading};
use self::canary::{Canary, Decision, Note, Primary};
use self::helper::{Event, Supervisor};
use self::message::{Message, Now};
use self::players::Player;
use self::route::Router;
use crate::media::{Health, MediaSource};
use crate::smtc::Snapshot;

/// The helper's file name, next to the executable unless [`DYLIB_ENV`] says.
pub const DYLIB: &str = "nowplaying-mediaremote.dylib";
pub const DYLIB_ENV: &str = "AK820_MEDIAREMOTE_DYLIB";

/// How long the first poll waits for the helper's first `now`. Inside the
/// daemon's 2 s `FIRST_POLL_GRACE`, so the first push is the track rather than
/// a CLEAR followed by the track.
const FIRST_NOW_WAIT: Duration = Duration::from_millis(1500);

/// A fallback read happens once a poll, so it must finish inside one.
const TRACK_TIMEOUT: Duration = Duration::from_secs(3);

/// After a stale owner reads as not playing, wait this long before asking it
/// again (audit F9): the helper can say "stale" for as long as an open player
/// has nothing loaded, and a read every poll is the bash agent's spawn rate.
const STALE_NOTHING_BACKOFF: Duration = Duration::from_secs(30);

/// No poll for this long means the media thread has stopped (audit F10). The
/// slowest honest poll is a canary question (5 s) plus a fallback read (3 s).
const STALLED_AFTER: Duration = Duration::from_secs(20);

/// Where the helper dylib is expected.
pub fn dylib_path() -> Option<PathBuf> {
    if let Some(p) = std::env::var_os(DYLIB_ENV) {
        return Some(p.into());
    }
    Some(std::env::current_exe().ok()?.parent()?.join(DYLIB))
}

/// Everything the engine does that is not pure, so tests can stand in.
pub trait World {
    /// Scriptable players running now, from the process table (no spawn).
    fn running(&mut self) -> Vec<Player>;
    fn player_state(&mut self, player: Player) -> Outcome;
    fn track(&mut self, players: &[Player]) -> Reading;
}

/// The real one.
pub struct System {
    canary: Asker,
    track: Asker,
}

impl Default for System {
    fn default() -> Self {
        System {
            canary: Asker::default(),
            track: Asker { timeout: TRACK_TIMEOUT, ..Asker::default() },
        }
    }
}

impl World for System {
    fn running(&mut self) -> Vec<Player> {
        players::running()
    }
    fn player_state(&mut self, player: Player) -> Outcome {
        self.canary.player_state(player)
    }
    fn track(&mut self, players: &[Player]) -> Reading {
        self.track.track(players)
    }
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Route {
    MediaRemote,
    Stale(Player),
    Silent,
    Refused(Player),
}

/// What the daemon sees: the effective `now` and how reads are going.
#[derive(Clone, Debug)]
pub struct View {
    pub current: Option<Now>,
    pub polls: u64,
    pub failures: u64,
    pub last_error: Option<String>,
    pub last_poll_ok: bool,
    pub updated: Option<Instant>,
    pub route: Route,
    /// When the engine last polled, for [`MediaRemoteSource::latest`] to
    /// notice a thread that has stopped.
    pub polled_at: Option<Instant>,
}

impl Default for View {
    fn default() -> Self {
        View {
            current: None,
            polls: 0,
            failures: 0,
            last_error: None,
            last_poll_ok: true,
            updated: None,
            route: Route::MediaRemote,
            polled_at: None,
        }
    }
}

/// The helper's side of a poll, as the supervisor reports it.
#[derive(Copy, Clone, Debug)]
pub struct HelperState {
    pub failed: bool,
    pub silent_for: Duration,
}

pub struct Engine {
    router: Router,
    /// `None` with AppleScript off: no canary and no fallback, so no Apple
    /// event can ever be sent (`ak820 probe` without `--applescript`).
    canary: Option<Canary>,
    proof: Option<Instant>,
    /// Has the helper's current run sent a `now`? Until it has, MediaRemote has
    /// not answered, and a null there is not a null to cross-check (audit F1).
    fresh: bool,
    denied: Option<String>,
    /// While a stale owner reads as not playing, no read before this.
    stale_quiet_until: Option<Instant>,
    view: View,
}

impl Engine {
    pub fn new(applescript: bool) -> Engine {
        Engine {
            router: Router::default(),
            canary: applescript.then(Canary::default),
            proof: None,
            fresh: false,
            denied: None,
            stale_quiet_until: None,
            view: View::default(),
        }
    }

    pub fn view(&self) -> &View {
        &self.view
    }

    /// One supervisor event. Returns whether it was a `now`.
    pub fn event(&mut self, event: Event, at: Instant, say: &mut dyn FnMut(String)) -> bool {
        match event {
            Event::Message(m) => {
                if m.proves_liveness() {
                    self.proof = Some(at);
                    if self.view.route == Route::MediaRemote {
                        self.view.updated = Some(at);
                    }
                }
                match m {
                    Message::Now(now) => {
                        self.fresh = true;
                        let (from, to) = (self.router.bundle().map(str::to_owned), now.bundle.clone());
                        if !self.router.accept(now, at) {
                            say(format!(
                                "media: holding a switch to paused {} for up to 5s; {} is still playing",
                                to.as_deref().unwrap_or("(none)"),
                                from.as_deref().unwrap_or("(none)")
                            ));
                        } else {
                            // News from the owner: a stale player that was
                            // quiet may have started, so read it at once.
                            self.stale_quiet_until = None;
                            if self.view.route == Route::MediaRemote {
                                self.view.current = self.router.current().cloned();
                            }
                        }
                        return true;
                    }
                    Message::Fatal { error } => say(format!("[warn] mediaremote: helper fatal: {error}")),
                    _ => {}
                }
            }
            Event::Started { pid } => {
                self.fresh = false;
                say(format!("mediaremote: helper started, pid {pid}"))
            }
            Event::Exited { pid, code, signal, ran } => say(format!(
                "mediaremote: helper pid {pid} exited ({}) after {}s",
                match (code, signal) {
                    (Some(c), _) => format!("code {c}"),
                    (None, Some(s)) => format!("signal {s}"),
                    _ => "unknown".into(),
                },
                ran.as_secs()
            )),
            Event::Restarting { after } => say(format!("mediaremote: restarting the helper in {}s", after.as_secs())),
            Event::KilledForSilence { pid, silent_for } => say(format!(
                "[warn] mediaremote: helper pid {pid} silent for {}s; killed",
                silent_for.as_secs()
            )),
            Event::SpawnFailed(e) => say(format!("[warn] mediaremote: cannot start the helper: {e}")),
            Event::Stderr(line) => say(format!("mediaremote stderr: {line}")),
            Event::Unparseable { line, error } => {
                let clipped: String = line.chars().take(160).collect();
                say(format!("[warn] mediaremote: unparseable line ({error}): {clipped}"))
            }
            Event::TooLong { bytes } => say(format!("[warn] mediaremote: dropped a {bytes}-byte line")),
        }
        false
    }

    /// One poll: the canary, the route, and the fallback read if one is due.
    pub fn poll(&mut self, at: Instant, helper: HelperState, world: &mut dyn World, say: &mut dyn FnMut(String)) {
        self.view.polls += 1;
        self.view.polled_at = Some(at);
        self.router.settle(at);

        // The canary cross-checks a null MediaRemote, so it only means
        // something while the helper is answering at all, and only once this
        // run of it has said what is playing (F1).
        if let (false, true, Some(canary)) = (helper.failed, self.fresh, self.canary.as_mut()) {
            let (decision, note) = canary.step(self.router.has_bundle(), at, || world.running());
            let mut notes: Vec<Note> = note.into_iter().collect();
            if let Decision::Ask(player) = decision {
                let outcome = world.player_state(player);
                // An answer is proof consent is in place again (F2).
                if matches!(outcome, Outcome::State(_)) {
                    self.denied = None;
                }
                notes.extend(canary.answered(player, outcome));
            }
            for n in notes {
                note_to(&mut self.denied, n, say);
            }
        }

        let applescript = self.canary.is_some();
        let route = if helper.failed {
            Route::Silent
        } else if let Some(p) = self.router.stale_owner().and_then(Player::from_bundle).filter(|_| applescript) {
            Route::Stale(p)
        } else if let Some(Primary::AppleScript(p)) = self.canary.as_ref().map(Canary::primary) {
            Route::Refused(p)
        } else {
            Route::MediaRemote
        };
        if route != self.view.route {
            self.stale_quiet_until = None;
            say(match route {
                Route::MediaRemote => "media: reading MediaRemote again".into(),
                Route::Stale(p) => format!(
                    "media: MediaRemote names {} but will not describe it; reading it over AppleScript",
                    p.app_name()
                ),
                Route::Silent if applescript => format!(
                    "[warn] media: MediaRemote helper silent {}s; reading running players over AppleScript",
                    helper.silent_for.as_secs()
                ),
                Route::Silent => format!("[warn] media: MediaRemote helper silent {}s", helper.silent_for.as_secs()),
                Route::Refused(p) => format!(
                    "[warn] media: reading over AppleScript: MediaRemote reports nothing while {} plays",
                    p.app_name()
                ),
            });
            self.view.route = route;
        }

        let outcome: Result<(), String> = match route {
            Route::MediaRemote => {
                if self.router.has_bundle() {
                    self.denied = None;
                }
                self.view.current = self.router.current().cloned();
                self.view.updated = self.proof;
                match &self.denied {
                    Some(d) => Err(format!("Automation denied: {d}")),
                    None => Ok(()),
                }
            }
            Route::Silent if !applescript => {
                self.view.current = None;
                Err(format!("MediaRemote helper silent {}s", helper.silent_for.as_secs()))
            }
            Route::Stale(_) if self.stale_quiet_until.is_some_and(|until| at < until) => {
                self.view.current = None;
                Ok(())
            }
            Route::Stale(_) | Route::Silent | Route::Refused(_) => {
                let running = world.running();
                let ask: Vec<Player> = match route {
                    Route::Stale(p) => running.into_iter().filter(|r| *r == p).collect(),
                    _ => running,
                };
                if ask.is_empty() {
                    // Nothing that can be asked is running.
                    self.view.current = None;
                    if helper.failed {
                        Err(format!(
                            "MediaRemote helper silent {}s, and no player is running to ask instead",
                            helper.silent_for.as_secs()
                        ))
                    } else {
                        self.view.updated = Some(at);
                        Ok(())
                    }
                } else {
                    match world.track(&ask) {
                        Reading::Track(now) => {
                            self.denied = None;
                            self.view.current = Some(now);
                            self.view.updated = Some(at);
                            Ok(())
                        }
                        Reading::Nothing => {
                            self.denied = None;
                            self.view.current = None;
                            self.view.updated = Some(at);
                            if matches!(route, Route::Stale(_)) {
                                self.stale_quiet_until = Some(at + STALE_NOTHING_BACKOFF);
                            }
                            Ok(())
                        }
                        Reading::Denied(d) => {
                            if self.denied.is_none() {
                                say(denial_line(&d));
                            }
                            self.denied = Some(d.clone());
                            Err(format!("Automation denied: {d}"))
                        }
                        Reading::TimedOut => Err("AppleScript read timed out".into()),
                        Reading::Failed(e) => Err(format!("AppleScript read failed: {e}")),
                    }
                }
            }
        };
        match outcome {
            Ok(()) => {
                self.view.last_poll_ok = true;
                self.view.last_error = None;
            }
            Err(e) => {
                self.view.last_poll_ok = false;
                self.view.failures += 1;
                self.view.last_error = Some(e);
            }
        }
    }
}

fn denial_line(detail: &str) -> String {
    format!(
        "[warn] media: Automation denied ({detail}); grant it under System Settings > Privacy & Security > Automation"
    )
}

fn note_to(denied: &mut Option<String>, note: Note, say: &mut dyn FnMut(String)) {
    match note {
        Note::SwitchedToAppleScript { player } => say(format!(
            "[warn] media: MediaRemote reported nothing twice while {} said playing -- refused, or Spotify Connect",
            player.app_name()
        )),
        Note::RestoredMediaRemote => say("media: MediaRemote names an app again".into()),
        Note::Denied { detail, .. } => {
            if denied.is_none() {
                say(denial_line(&detail));
            }
            *denied = Some(detail);
        }
        Note::Failed { player, detail } => say(format!("media: canary question to {} failed: {detail}", player.app_name())),
    }
}

/// The source the daemon polls.
pub struct MediaRemoteSource {
    view: Arc<Mutex<View>>,
}

pub struct Options {
    pub interval: Duration,
    /// Canary and fallback. Off, nothing sends an Apple event.
    pub applescript: bool,
    pub dylib: Option<PathBuf>,
}

impl MediaRemoteSource {
    /// Start the helper and the engine thread. `say` receives every log line.
    pub fn spawn(opts: Options, mut say: Box<dyn FnMut(String) + Send>) -> Result<MediaRemoteSource, String> {
        let view = Arc::new(Mutex::new(View::default()));
        let (tx, rx) = mpsc::channel();
        // ⚠️ Absolute, always: /usr/bin/perl runs under the hardened runtime,
        // whose dyld refuses a relative path -- the helper prints "load failed"
        // and exits 2, forever (found running `ak820 probe --dylib ../..`).
        let dylib = opts.dylib.as_ref().and_then(|p| std::fs::canonicalize(p).ok());
        let supervisor = match &dylib {
            Some(path) if path.is_file() => Some(Supervisor::start(helper::Config::mediaremote(path), tx.clone())),
            _ => {
                say(format!(
                    "[warn] mediaremote: no helper at {}; set {DYLIB_ENV} or install it beside the executable",
                    opts.dylib.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "(unknown)".into())
                ));
                None
            }
        };
        let shared = Arc::clone(&view);
        thread::Builder::new()
            .name("ak820-media".into())
            .spawn(move || {
                // Held so the channel never disconnects when there is no helper.
                let _tx = tx;
                let mut engine = Engine::new(opts.applescript);
                let mut world = System::default();
                let started = Instant::now();
                let mut next_poll = started + FIRST_NOW_WAIT;
                let mut first = true;
                loop {
                    let now = Instant::now();
                    if now >= next_poll {
                        let helper = match &supervisor {
                            Some(s) => HelperState { failed: s.failed(), silent_for: s.silent_for() },
                            None => HelperState { failed: true, silent_for: started.elapsed() },
                        };
                        engine.poll(Instant::now(), helper, &mut world, &mut *say);
                        *shared.lock().unwrap_or_else(|e| e.into_inner()) = engine.view().clone();
                        first = false;
                        next_poll = Instant::now() + opts.interval;
                        continue;
                    }
                    match rx.recv_timeout(next_poll - now) {
                        Ok(event) => {
                            let was_now = engine.event(event, Instant::now(), &mut *say);
                            if first && was_now {
                                next_poll = Instant::now();
                            }
                            *shared.lock().unwrap_or_else(|e| e.into_inner()) = engine.view().clone();
                        }
                        Err(RecvTimeoutError::Timeout) => {}
                        Err(RecvTimeoutError::Disconnected) => thread::sleep(next_poll.saturating_duration_since(now)),
                    }
                }
            })
            .map_err(|e| format!("spawning the media thread: {e}"))?;
        Ok(MediaRemoteSource { view })
    }

    /// The effective `now`, unextrapolated, for `ak820 probe`.
    pub fn current(&self) -> Option<Now> {
        self.view.lock().unwrap_or_else(|e| e.into_inner()).current.clone()
    }

    /// The effective route, for `ak820 probe`.
    pub fn route(&self) -> Route {
        self.view.lock().unwrap_or_else(|e| e.into_inner()).route
    }
}

impl MediaSource for MediaRemoteSource {
    fn latest(&self) -> (Snapshot, Health) {
        let v = self.view.lock().unwrap_or_else(|e| e.into_inner()).clone();
        health_of(v, Instant::now(), applescript::wall_now())
    }
}

/// The daemon's answer from one view. ⚠️ A thread that stopped polling, by a
/// panic or a wedge, is a failed source (F10): otherwise its last view is
/// served forever, and the keepalive re-asserts a track that is long over.
fn health_of(v: View, now: Instant, wall: f64) -> (Snapshot, Health) {
    let stalled = v.polled_at.is_some_and(|at| now.saturating_duration_since(at) >= STALLED_AFTER);
    let snapshot = match &v.current {
        Some(n) => route::snapshot_of(n, wall),
        None => Snapshot::idle(),
    };
    (
        snapshot,
        Health {
            polls: v.polls,
            failures: v.failures,
            last_error: if stalled { Some("the media thread has stopped polling".into()) } else { v.last_error },
            stale_for: v.updated.map(|at| now.saturating_duration_since(at)),
            last_poll_ok: v.last_poll_ok && !stalled,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use applescript::State;

    #[derive(Default)]
    struct Fake {
        running: Vec<Player>,
        state: Option<Outcome>,
        reading: Option<Reading>,
        scans: u32,
        asked: Vec<Player>,
        read: Vec<Vec<Player>>,
    }

    impl World for Fake {
        fn running(&mut self) -> Vec<Player> {
            self.scans += 1;
            self.running.clone()
        }
        fn player_state(&mut self, player: Player) -> Outcome {
            self.asked.push(player);
            self.state.clone().expect("the test did not expect a canary question")
        }
        fn track(&mut self, players: &[Player]) -> Reading {
            self.read.push(players.to_vec());
            self.reading.clone().expect("the test did not expect a fallback read")
        }
    }

    const OK: HelperState = HelperState { failed: false, silent_for: Duration::from_secs(1) };
    const FAILED: HelperState = HelperState { failed: true, silent_for: Duration::from_secs(61) };

    fn now_msg(bundle: Option<&str>, title: &str, rate: f64) -> Event {
        Event::Message(Message::Now(Now {
            bundle: bundle.map(Into::into),
            playing: rate > 0.0,
            title: bundle.map(|_| title.into()),
            artist: bundle.map(|_| "Artist".into()),
            rate: bundle.map(|_| rate),
            ..Now::default()
        }))
    }

    fn quiet() -> impl FnMut(String) {
        |_| {}
    }

    fn track(player: Player, title: &str) -> Reading {
        Reading::Track(Now {
            bundle: Some(player.bundle().into()),
            playing: true,
            title: Some(title.into()),
            rate: Some(1.0),
            ..Now::default()
        })
    }

    /// The everyday case: MediaRemote describes the track, and nothing is
    /// scanned, asked or spawned.
    #[test]
    fn a_healthy_mediaremote_costs_no_scan_and_no_apple_event() {
        let mut e = Engine::new(true);
        let mut w = Fake::default();
        let t = Instant::now();
        assert!(e.event(now_msg(Some("com.google.Chrome"), "Video", 1.0), t, &mut quiet()));
        for i in 0..100 {
            e.poll(t + Duration::from_secs(3 * i), OK, &mut w, &mut quiet());
        }
        assert_eq!((w.scans, w.asked.len(), w.read.len()), (0, 0, 0));
        let v = e.view();
        assert!(v.last_poll_ok);
        assert_eq!(v.current.as_ref().and_then(|n| n.title.as_deref()), Some("Video"));
        assert_eq!((v.polls, v.route), (100, Route::MediaRemote));
    }

    #[test]
    fn a_stale_music_owner_is_read_over_applescript_alone() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Spotify, Player::Music], reading: Some(track(Player::Music, "Song")), ..Fake::default() };
        let t = Instant::now();
        let stale = Event::Message(Message::Now(Now { bundle: Some("com.apple.Music".into()), stale: true, ..Now::default() }));
        e.event(stale, t, &mut quiet());
        let mut lines = Vec::new();
        e.poll(t, OK, &mut w, &mut |l| lines.push(l));
        assert_eq!(w.read, vec![vec![Player::Music]], "Spotify is running but is not the owner");
        assert_eq!(e.view().route, Route::Stale(Player::Music));
        assert_eq!(e.view().current.as_ref().and_then(|n| n.title.as_deref()), Some("Song"));
        assert!(lines.iter().any(|l| l.contains("will not describe it")));

        // MediaRemote describes it again: back, and the fallback stops.
        e.event(now_msg(Some("com.apple.Music"), "Song", 1.0), t, &mut quiet());
        e.poll(t + Duration::from_secs(3), OK, &mut w, &mut quiet());
        assert_eq!((e.view().route, w.read.len()), (Route::MediaRemote, 1));
    }

    #[test]
    fn a_silent_helper_reads_running_players_and_fails_only_with_none() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Music], reading: Some(track(Player::Music, "Song")), ..Fake::default() };
        let t = Instant::now();
        e.poll(t, FAILED, &mut w, &mut quiet());
        assert!(e.view().last_poll_ok, "AppleScript answered for the helper");
        assert_eq!(e.view().route, Route::Silent);

        w.running.clear();
        e.poll(t + Duration::from_secs(3), FAILED, &mut w, &mut quiet());
        let v = e.view();
        assert!(!v.last_poll_ok);
        assert!(v.current.is_none());
        assert!(v.last_error.as_deref().unwrap().contains("silent 61s"));
        assert_eq!(v.failures, 1);
    }

    /// Before 60 s of silence the helper has not failed: the last track stays,
    /// and nothing is read instead. That is the designed-restart window.
    #[test]
    fn a_helper_restarting_inside_the_clock_keeps_the_last_track() {
        let mut e = Engine::new(true);
        let mut w = Fake::default();
        let t = Instant::now();
        e.event(now_msg(Some("com.spotify.client"), "Song", 1.0), t, &mut quiet());
        e.event(Event::Exited { pid: 1, code: Some(3), signal: None, ran: Duration::from_secs(9) }, t, &mut quiet());
        e.poll(t + Duration::from_secs(20), HelperState { failed: false, silent_for: Duration::from_secs(20) }, &mut w, &mut quiet());
        assert!(e.view().last_poll_ok);
        assert_eq!(e.view().current.as_ref().and_then(|n| n.title.as_deref()), Some("Song"));
        assert_eq!(w.read.len(), 0);
    }

    /// G-B: a denial surfaces as a failed poll with the reason, never as idle,
    /// and clears when MediaRemote names an app again.
    #[test]
    fn a_canary_denial_is_surfaced_and_cleared_by_mediaremote() {
        let mut e = Engine::new(true);
        let mut w = Fake {
            running: vec![Player::Music],
            state: Some(Outcome::Denied("Not authorized to send Apple events to Music. (-1743)".into())),
            ..Fake::default()
        };
        let t = Instant::now();
        e.event(now_msg(None, "", 0.0), t, &mut quiet());
        let mut lines = Vec::new();
        e.poll(t, OK, &mut w, &mut |l| lines.push(l));
        assert_eq!(w.asked, vec![Player::Music]);
        assert!(!e.view().last_poll_ok);
        assert!(e.view().last_error.as_deref().unwrap().contains("-1743"));
        assert_eq!(lines.iter().filter(|l| l.contains("Automation denied")).count(), 1);

        // Stays failed between questions, without another log line.
        e.poll(t + Duration::from_secs(3), OK, &mut w, &mut |l| lines.push(l));
        assert!(!e.view().last_poll_ok);
        assert_eq!(lines.iter().filter(|l| l.contains("Automation denied")).count(), 1);

        e.event(now_msg(Some("com.google.Chrome"), "Video", 1.0), t, &mut quiet());
        e.poll(t + Duration::from_secs(6), OK, &mut w, &mut quiet());
        assert!(e.view().last_poll_ok);
    }

    #[test]
    fn two_discrepancies_switch_to_applescript_and_a_bundle_switches_back() {
        let mut e = Engine::new(true);
        let mut w = Fake {
            running: vec![Player::Spotify],
            state: Some(Outcome::State(State::Playing)),
            reading: Some(track(Player::Spotify, "Song")),
            ..Fake::default()
        };
        let t = Instant::now();
        e.event(now_msg(None, "", 0.0), t, &mut quiet());
        e.poll(t, OK, &mut w, &mut quiet());
        assert_eq!(e.view().route, Route::MediaRemote);
        e.poll(t + canary::MIN_GAP, OK, &mut w, &mut quiet());
        assert_eq!(e.view().route, Route::Refused(Player::Spotify));
        assert_eq!(e.view().current.as_ref().and_then(|n| n.title.as_deref()), Some("Song"));

        e.event(now_msg(Some("com.spotify.client"), "Song", 1.0), t, &mut quiet());
        e.poll(t + canary::MIN_GAP * 2, OK, &mut w, &mut quiet());
        assert_eq!(e.view().route, Route::MediaRemote);
    }

    #[test]
    fn quitting_the_playing_app_goes_idle_at_the_next_poll_after_the_hold() {
        let mut e = Engine::new(true);
        let mut w = Fake::default();
        let t = Instant::now();
        e.event(now_msg(Some("com.spotify.client"), "Song", 1.0), t, &mut quiet());
        e.event(now_msg(None, "", 0.0), t + Duration::from_secs(1), &mut quiet());
        e.poll(t + Duration::from_secs(3), OK, &mut w, &mut quiet());
        assert!(e.view().current.as_ref().is_some_and(|n| n.bundle.is_some()), "held");
        e.poll(t + Duration::from_secs(6), OK, &mut w, &mut quiet());
        assert!(e.view().current.as_ref().is_some_and(|n| n.bundle.is_none()), "landed without a second message");
    }

    #[test]
    fn a_failed_fallback_read_fails_the_poll() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Music], reading: Some(Reading::TimedOut), ..Fake::default() };
        e.poll(Instant::now(), FAILED, &mut w, &mut quiet());
        assert!(!e.view().last_poll_ok);
        assert_eq!(e.view().last_error.as_deref(), Some("AppleScript read timed out"));
    }

    /// `ak820 probe` without `--applescript`: whatever MediaRemote does, no
    /// scan, no question, no read.
    #[test]
    fn with_applescript_off_no_apple_event_is_possible() {
        let mut e = Engine::new(false);
        let mut w = Fake { running: vec![Player::Music], ..Fake::default() };
        let t = Instant::now();
        let stale = Event::Message(Message::Now(Now { bundle: Some("com.apple.Music".into()), stale: true, ..Now::default() }));
        e.event(stale, t, &mut quiet());
        e.poll(t, OK, &mut w, &mut quiet());
        e.event(now_msg(None, "", 0.0), t, &mut quiet());
        e.poll(t + canary::MIN_GAP, OK, &mut w, &mut quiet());
        e.poll(t + canary::MIN_GAP * 2, FAILED, &mut w, &mut quiet());
        assert_eq!((w.scans, w.asked.len(), w.read.len()), (0, 0, 0));
        assert!(!e.view().last_poll_ok);
    }

    /// F1: a null from before this helper run has spoken is not a null to
    /// cross-check, at start or after a restart.
    #[test]
    fn no_canary_question_before_the_helpers_first_now() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Music], state: Some(Outcome::State(State::Paused)), ..Fake::default() };
        let t = Instant::now();
        e.poll(t, OK, &mut w, &mut quiet());
        assert_eq!((w.scans, w.asked.len()), (0, 0), "no now yet");
        e.event(now_msg(None, "", 0.0), t, &mut quiet());
        e.poll(t + Duration::from_secs(3), OK, &mut w, &mut quiet());
        assert_eq!(w.asked.len(), 1);
        e.event(Event::Started { pid: 2 }, t, &mut quiet());
        e.poll(t + canary::MIN_GAP * 2, OK, &mut w, &mut quiet());
        assert_eq!(w.asked.len(), 1, "restarted, and not yet answered");
    }

    /// F2: consent re-granted while idle is seen at the next question, not
    /// only when something MediaRemote can describe plays.
    #[test]
    fn a_denial_clears_when_the_canary_is_answered_again() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Music], state: Some(Outcome::Denied("(-1743)".into())), ..Fake::default() };
        let t = Instant::now();
        e.event(now_msg(None, "", 0.0), t, &mut quiet());
        e.poll(t, OK, &mut w, &mut quiet());
        assert!(!e.view().last_poll_ok);
        w.state = Some(Outcome::State(State::Paused));
        e.poll(t + canary::MIN_GAP, OK, &mut w, &mut quiet());
        assert!(e.view().last_poll_ok);
        assert!(e.view().last_error.is_none());
    }

    /// F9: a stale owner with nothing playing is not read every poll.
    #[test]
    fn a_stale_owner_that_is_not_playing_is_read_at_most_every_thirty_seconds() {
        let mut e = Engine::new(true);
        let mut w = Fake { running: vec![Player::Music], reading: Some(Reading::Nothing), ..Fake::default() };
        let t = Instant::now();
        let stale = Event::Message(Message::Now(Now { bundle: Some("com.apple.Music".into()), stale: true, ..Now::default() }));
        e.event(stale, t, &mut quiet());
        for i in 0..20 {
            e.poll(t + Duration::from_secs(3 * i), OK, &mut w, &mut quiet());
            assert!(e.view().last_poll_ok);
        }
        // 60 s of polls: at 0, 30 and 60 s at most
        assert!(w.read.len() <= 3, "read {} times", w.read.len());
    }

    /// F10: a view nobody has refreshed for 20 s is a failed source.
    #[test]
    fn a_stopped_media_thread_reads_as_failed() {
        let t = Instant::now();
        let v = View { polled_at: Some(t), current: Some(Now { bundle: Some("x".into()), title: Some("T".into()), ..Now::default() }), ..View::default() };
        assert!(health_of(v.clone(), t + Duration::from_secs(5), 0.0).1.last_poll_ok);
        let (_, h) = health_of(v, t + STALLED_AFTER, 0.0);
        assert!(!h.last_poll_ok);
        assert_eq!(h.last_error.as_deref(), Some("the media thread has stopped polling"));
    }

    #[test]
    fn hello_is_not_proof_of_life_but_tick_is() {
        let mut e = Engine::new(true);
        let t = Instant::now();
        e.event(Event::Message(Message::Hello { pid: Some(1.0) }), t, &mut quiet());
        assert!(e.proof.is_none());
        e.event(Event::Message(Message::Tick { seq: Some(1.0) }), t, &mut quiet());
        assert_eq!(e.proof, Some(t));
    }
}
