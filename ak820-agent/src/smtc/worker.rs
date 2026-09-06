//! The half that talks to WinRT, on a thread of its own.
//!
//! ⚠️ **Why this is a separate thread at all.** An earlier draft of the plan
//! said the daemon "has nothing else to do" while waiting on SMTC. It was
//! wrong: it has a clock loop. A three-second poll interval bounds how *often*
//! we ask, not how long `RequestAsync` or a metadata read takes, and an
//! indefinitely blocked media call on the scheduling thread would stop clock
//! sync, reconnection and shutdown together. Merging the two Python agents into
//! one process is what introduces that coupling, so the thread is what removes
//! it again.
//!
//! The contract with the rest of the daemon is therefore narrow: this thread
//! publishes its **latest completed** snapshot, and nothing else ever blocks on
//! it. A wedged media broker makes the snapshot go stale, which is visible in
//! [`Health`], and costs nothing else.
//!
//! ## ⚠️ Known deviation from the plan: the waits are not bounded
//!
//! The plan asks for a deadline on every operation. `windows-future` 0.3.2
//! offers only `join()`, which blocks until the operation completes, with no
//! timeout — so a genuine deadline needs `SetCompleted` plus an event this
//! thread waits on, and careful lifetime handling for a handler that may fire
//! after we have given up.
//!
//! That is **not** built yet, deliberately, and here is the honest accounting:
//!
//! - What the deadline was *for* — keeping a media stall away from the clock —
//!   is already achieved by this thread existing.
//! - A hang costs one stalled thread and a snapshot that stops updating.
//!   `Health::stale_for` makes that observable rather than silent.
//! - **One worker, for the process lifetime.** No timeout path spawns a
//!   replacement, so the "stranded worker per timeout" failure the plan names
//!   cannot happen here.
//! - Shutdown does not join this thread, so a wedged broker cannot hold the
//!   process open.
//!
//! What it still costs: a permanently wedged broker leaves a thread parked
//! forever, and we cannot tell that apart from "nothing is playing" except by
//! the staleness clock. Revisit if that is ever observed.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use windows::Media::Control::{
    GlobalSystemMediaTransportControlsSession as Session,
    GlobalSystemMediaTransportControlsSessionManager as Manager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
};
use windows::Win32::System::SystemInformation::GetSystemTimePreciseAsFileTime;
use windows::Win32::System::WinRT::{RO_INIT_MULTITHREADED, RoInitialize, RoUninitialize};

use super::{SessionFacts, Snapshot, Status, Timeline};

/// How often to ask SMTC what is playing.
///
/// Three seconds, from the Python agent: one second is wasteful and was
/// measured to make Spotify sluggish.
pub const POLL_INTERVAL: Duration = Duration::from_secs(3);

/// 100-nanosecond ticks per second — WinRT's `TimeSpan` and `DateTime` unit.
const TICKS_PER_SEC: f64 = 10_000_000.0;

/// Trim exactly what Python's `str.strip()` trims.
///
/// ⚠️ Not `str::trim()`. Rust's `char::is_whitespace` follows the Unicode
/// White_Space property; Python's `str.isspace()` additionally accepts the C0
/// separators U+001C..U+001F. The difference decides whether an artist field
/// containing only a stray separator is **empty**, and
/// [`Snapshot::lines`](super::Snapshot::lines) puts the title on the narrow row
/// when the artist is empty and the wide row when it is not. So a control
/// character would silently move the title to a different row with a different
/// budget. The set is generated alongside the fold table.
fn py_trim(s: &str) -> &str {
    s.trim_matches(|c| crate::text::PY_SPACE.contains(&c))
}

/// Initialize WinRT on the current thread as an MTA, for as long as the guard
/// lives.
///
/// ⚠️ Multi-threaded on purpose. An STA needs a message pump to dispatch
/// completions, and a worker thread that blocks in `join()` without one would
/// deadlock against its own callback.
/// ⚠️ Deliberately **not** `Send`. `RoUninitialize` must balance
/// `RoInitialize` **on the same thread**, and without the marker below this
/// compiles and is wrong:
///
/// ```compile_fail
/// # use ak820_agent::smtc::worker::Apartment;
/// let apartment = Apartment::enter().unwrap();
/// std::thread::spawn(move || drop(apartment));   // uninitializes the wrong thread
/// ```
///
/// The `Rc` is never constructed; it is there only because it is the standard
/// way to spell "this type stays where it was made".
pub struct Apartment(std::marker::PhantomData<std::rc::Rc<()>>);

impl Apartment {
    pub fn enter() -> windows::core::Result<Apartment> {
        unsafe { RoInitialize(RO_INIT_MULTITHREADED) }?;
        Ok(Apartment(std::marker::PhantomData))
    }
}

impl Drop for Apartment {
    fn drop(&mut self) {
        unsafe { RoUninitialize() };
    }
}

/// Seconds since `DateTime` ticks, measured against the system clock.
///
/// Both are 100 ns units since 1601-01-01 UTC, so this is a subtraction rather
/// than a conversion — no timezone, no epoch arithmetic, nothing to get wrong.
fn age_seconds(last_updated_ticks: i64) -> Option<f64> {
    // A session that has never reported an update leaves this at zero, which
    // would otherwise read as "last updated in 1601" and produce an age of four
    // centuries. The gate in `super::position` would reject that anyway; this
    // says what is meant.
    if last_updated_ticks <= 0 {
        return None;
    }
    let now = unsafe { GetSystemTimePreciseAsFileTime() };
    let now_ticks = ((now.dwHighDateTime as i64) << 32) | now.dwLowDateTime as i64;
    Some((now_ticks - last_updated_ticks) as f64 / TICKS_PER_SEC)
}

fn status_of(session: &Session) -> Status {
    match session.GetPlaybackInfo().and_then(|i| i.PlaybackStatus()) {
        Ok(PlaybackStatus::Playing) => Status::Playing,
        Ok(PlaybackStatus::Paused) => Status::Paused,
        // Closed / Opened / Changing / Stopped, and any read failure: a session
        // we cannot ask is a session with nothing to show.
        _ => Status::Other,
    }
}

fn timeline_of(session: &Session) -> Option<Timeline> {
    let t = session.GetTimelineProperties().ok()?;
    // Raw ticks: the differences are taken as integers, because doing it in
    // floating point loses an off-by-one on ordinary tracks. See `Timeline`.
    Some(Timeline {
        start_ticks: t.StartTime().ok()?.Duration,
        end_ticks: t.EndTime().ok()?.Duration,
        position_ticks: t.Position().ok()?.Duration,
        age_s: t.LastUpdatedTime().ok().and_then(|d| age_seconds(d.UniversalTime)),
    })
}

/// Ask each session only what ranking needs, then fill in the winner.
///
/// ⚠️ Finding 6 of the phase-1 audit, and a parity fix as well as a liveness
/// one. Python fetches metadata and the timeline **only for the session it
/// picks**; reading them for every app means an unrelated stopped application
/// can stall the poll — and while it does, the published snapshot carries a
/// position from before the stall with a *fresh* timestamp on it, so the health
/// report says all is well.
///
/// `try_get_media_properties_async` is the expensive call and it is now made
/// once per poll rather than once per app.
pub fn read_current() -> windows::core::Result<(Option<SessionFacts>, Instant)> {
    let manager = Manager::RequestAsync()?.join()?;
    let current_id = manager
        .GetCurrentSession()
        .and_then(|s| s.SourceAppUserModelId())
        .map(|h| h.to_string())
        .ok();

    let sessions = manager.GetSessions()?;
    let count = sessions.Size().unwrap_or(0);

    // Cheap pass: playback status and identity only, which is all `rank` reads.
    let mut cheap = Vec::with_capacity(count as usize);
    let mut handles = Vec::with_capacity(count as usize);
    for i in 0..count {
        let Ok(session) = sessions.GetAt(i) else {
            continue;
        };
        let app_id = session
            .SourceAppUserModelId()
            .map(|h| h.to_string())
            .unwrap_or_default();
        cheap.push(SessionFacts {
            is_current: current_id.as_deref() == Some(app_id.as_str()) && !app_id.is_empty(),
            status: status_of(&session),
            title: String::new(),
            artist: String::new(),
            timeline: None,
            app_id,
        });
        handles.push(session);
    }

    let Some(winner) = super::choose(&cheap) else {
        return Ok((None, Instant::now()));
    };
    let at = cheap
        .iter()
        .position(|s| std::ptr::eq(s, winner))
        .expect("chosen from this list");

    // Expensive pass: exactly one session. The observation instant is taken
    // here, next to the read, rather than at publication -- a slow call must
    // not make a stale position look fresh.
    let mut facts = cheap.swap_remove(at);
    let session = &handles[at];
    let observed = Instant::now();
    if let Ok(props) = session.TryGetMediaPropertiesAsync().and_then(|op| op.join()) {
        facts.title = py_trim(&props.Title().map(|h| h.to_string()).unwrap_or_default()).to_string();
        facts.artist =
            py_trim(&props.Artist().map(|h| h.to_string()).unwrap_or_default()).to_string();
    }
    facts.timeline = timeline_of(session);
    Ok((Some(facts), observed))
}

/// Read every session SMTC knows about, metadata and all.
///
/// ⚠️ The **diagnostic** path, for `ak820 probe`, and deliberately separate from
/// [`read_current`]: answering "why doesn't this app show up?" requires asking
/// every app, which is exactly the cost the polling path must not pay.
///
/// Individual failures are absorbed rather than propagated: a session can exist
/// before its metadata arrives, and one unreadable app must not blind us to the
/// others. Only a failure to reach the manager itself is an error.
pub fn read_sessions() -> windows::core::Result<Vec<SessionFacts>> {
    let manager = Manager::RequestAsync()?.join()?;
    let current_id = manager
        .GetCurrentSession()
        .and_then(|s| s.SourceAppUserModelId())
        .map(|h| h.to_string())
        .ok();

    let sessions = manager.GetSessions()?;
    // ⚠️ Indexed rather than iterated. `IVectorView`'s `IntoIterator` panics on
    // an underlying COM failure, and a session list can change under us: an app
    // closing between `Size` and `GetAt` is ordinary, not exceptional. A panic
    // here would take down the worker thread and stop media updates for the
    // life of the process, so a vanished entry is skipped instead.
    let count = sessions.Size().unwrap_or(0);
    let mut out = Vec::with_capacity(count as usize);
    for i in 0..count {
        let Ok(session) = sessions.GetAt(i) else {
            continue;
        };
        let app_id = session
            .SourceAppUserModelId()
            .map(|h| h.to_string())
            .unwrap_or_default();
        let (title, artist) = match session.TryGetMediaPropertiesAsync().and_then(|op| op.join()) {
            Ok(props) => (
                props.Title().map(|h| h.to_string()).unwrap_or_default(),
                props.Artist().map(|h| h.to_string()).unwrap_or_default(),
            ),
            Err(_) => (String::new(), String::new()),
        };
        out.push(SessionFacts {
            is_current: current_id.as_deref() == Some(app_id.as_str()) && !app_id.is_empty(),
            status: status_of(&session),
            // Trimmed here, still Unicode: folding happens at the line budget,
            // and Python trims before it folds too.
            title: py_trim(&title).to_string(),
            artist: py_trim(&artist).to_string(),
            timeline: timeline_of(&session),
            app_id,
        })
    }
    Ok(out)
}

/// One complete read, on the calling thread. For `ak820 probe`.
pub fn poll_once() -> windows::core::Result<Vec<SessionFacts>> {
    let _apartment = Apartment::enter()?;
    read_sessions()
}

/// How the media side is doing, for a degraded-state report.
///
/// "Task running" can coexist with hours of failed reads, so the daemon needs
/// to be able to say more than whether the thread exists.
#[derive(Clone, Debug, Default)]
pub struct Health {
    pub polls: u64,
    pub failures: u64,
    pub last_error: Option<String>,
    /// How long since the snapshot last refreshed. `None` before the first one.
    pub stale_for: Option<Duration>,
}

#[derive(Default)]
struct State {
    snapshot: Snapshot,
    updated: Option<Instant>,
    polls: u64,
    failures: u64,
    last_error: Option<String>,
}

/// A thread polling SMTC, and the latest snapshot it managed to produce.
pub struct MediaWorker {
    state: Arc<Mutex<State>>,
}

impl MediaWorker {
    /// Start polling. The thread is detached deliberately — see the module
    /// header: shutdown must not be able to block on a wedged media broker.
    pub fn spawn(interval: Duration) -> MediaWorker {
        let state = Arc::new(Mutex::new(State::default()));
        let worker = Arc::clone(&state);
        thread::Builder::new()
            .name("ak820-smtc".into())
            .spawn(move || run(worker, interval))
            .expect("spawning the media thread");
        MediaWorker { state }
    }

    /// The most recent snapshot, and how the reads are going.
    ///
    /// Never blocks on the media API: the worst case is returning the previous
    /// snapshot, which is exactly what a stale-but-honest readout should do.
    pub fn latest(&self) -> (Snapshot, Health) {
        let state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        (
            state.snapshot.clone(),
            Health {
                polls: state.polls,
                failures: state.failures,
                last_error: state.last_error.clone(),
                stale_for: state.updated.map(|at| at.elapsed()),
            },
        )
    }
}

fn run(state: Arc<Mutex<State>>, interval: Duration) {
    // If the apartment cannot be entered there is no point looping: every call
    // would fail identically. Record it once and stop.
    let _apartment = match Apartment::enter() {
        Ok(a) => a,
        Err(e) => {
            let message = format!("WinRT unavailable: {e}");
            let mut s = state.lock().unwrap_or_else(|e| e.into_inner());
            s.failures += 1;
            s.last_error = Some(message);
            return;
        }
    };

    loop {
        // ⚠️ Everything expensive happens BEFORE the lock is taken, including
        // formatting the error. `windows::core::Error::to_string` can make COM
        // calls to fetch `IErrorInfo`, and doing that under the mutex would
        // block `latest()` -- which the scheduler calls -- on the very media
        // subsystem this thread exists to stay out of the way of. The WinRT
        // objects are all dropped here too, for the same reason: releasing a
        // COM object is a call.
        let outcome = match read_current() {
            Ok((chosen, observed)) => Ok((
                super::snapshot(chosen.as_slice()),
                observed,
            )),
            Err(e) => Err(e.to_string()),
        };
        {
            let mut s = state.lock().unwrap_or_else(|e| e.into_inner());
            s.polls += 1;
            match outcome {
                Ok((snapshot, observed)) => {
                    s.snapshot = snapshot;
                    // The instant the winner was READ, not the instant we got
                    // the lock. A slow poll must age its own snapshot.
                    s.updated = Some(observed);
                    s.last_error = None;
                }
                Err(message) => {
                    // Keep the previous snapshot. A broker that blinks should
                    // not blank the panel; the staleness clock is what says
                    // something is wrong, and the keepalive will expire the
                    // firmware's text slot if it stays wrong.
                    s.failures += 1;
                    s.last_error = Some(message);
                }
            }
        }
        thread::sleep(interval);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 100 ns ticks, so a second is ten million of them. Getting this wrong by
    /// a factor of ten produces plausible-looking positions.
    #[test]
    fn a_timespan_tick_is_a_hundred_nanoseconds() {
        assert_eq!(TICKS_PER_SEC as i64, 10_000_000);
        assert_eq!((45_000_000_i64 as f64 / TICKS_PER_SEC) as i64, 4);
    }

    /// A session that never reported an update leaves the field at zero, which
    /// is 1601 rather than "just now".
    #[test]
    fn a_zero_timestamp_is_absent_not_ancient() {
        assert_eq!(age_seconds(0), None);
        assert_eq!(age_seconds(-1), None);
    }

    /// A real timestamp from a moment ago reads as a small positive age.
    #[test]
    fn a_recent_timestamp_reads_as_a_small_age() {
        let now = unsafe { GetSystemTimePreciseAsFileTime() };
        let ticks = ((now.dwHighDateTime as i64) << 32) | now.dwLowDateTime as i64;
        let age = age_seconds(ticks).expect("a real timestamp has an age");
        assert!(
            (-1.0..5.0).contains(&age),
            "age of a just-taken timestamp was {age}"
        );
        // And it must land inside the window `super::position` will trust.
        assert!((0.0..600.0).contains(&age.max(0.0)));
    }

    /// ⚠️ The trim mismatch the phase-1 audit found. Rust's `trim` follows
    /// Unicode White_Space; Python's `strip` also takes U+001C..U+001F. An
    /// artist of just a separator is therefore empty to Python and non-empty to
    /// `trim` — and that decides which row the **title** lands on, and so which
    /// character budget it gets.
    #[test]
    fn trimming_matches_pythons_strip_not_rusts() {
        for sep in ['\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}'] {
            let s = sep.to_string();
            assert!(
                !s.trim().is_empty(),
                "precondition: Rust's trim leaves {sep:?}"
            );
            assert!(
                py_trim(&s).is_empty(),
                "but Python strips it, so we must too"
            );
        }
    }

    #[test]
    fn trimming_still_handles_ordinary_whitespace() {
        assert_eq!(py_trim("  Sigur R\u{f3}s \t\n"), "Sigur R\u{f3}s");
        assert_eq!(py_trim("\u{a0}\u{3000}x\u{2009}"), "x");
        assert_eq!(py_trim(""), "");
        assert_eq!(py_trim("   "), "");
        // Inner whitespace is untouched -- only the ends are trimmed.
        assert_eq!(py_trim(" a  b "), "a  b");
    }

    /// The apartment guard must be re-enterable within a process: `probe` uses
    /// it on the main thread and the worker uses it on its own.
    #[test]
    fn the_apartment_can_be_entered_and_left() {
        {
            let _a = Apartment::enter().expect("MTA");
        }
        let _b = Apartment::enter().expect("MTA again after dropping the first");
    }
}
