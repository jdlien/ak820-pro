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

/// Initialize WinRT on the current thread as an MTA, for as long as the guard
/// lives.
///
/// ⚠️ Multi-threaded on purpose. An STA needs a message pump to dispatch
/// completions, and a worker thread that blocks in `join()` without one would
/// deadlock against its own callback.
pub struct Apartment(());

impl Apartment {
    /// `RO_E_CHANGED_MODE` means somebody already initialized this thread with
    /// a different model. That is not our failure and not ours to undo, so the
    /// guard records that it must not uninitialize.
    pub fn enter() -> windows::core::Result<Apartment> {
        unsafe { RoInitialize(RO_INIT_MULTITHREADED) }?;
        Ok(Apartment(()))
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
    let secs = |v: windows::Foundation::TimeSpan| v.Duration as f64 / TICKS_PER_SEC;
    Some(Timeline {
        start_s: secs(t.StartTime().ok()?),
        end_s: secs(t.EndTime().ok()?),
        position_s: secs(t.Position().ok()?),
        age_s: t.LastUpdatedTime().ok().and_then(|d| age_seconds(d.UniversalTime)),
    })
}

/// Read every session SMTC knows about.
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
    let mut out = Vec::with_capacity(sessions.Size().unwrap_or(0) as usize);
    for session in sessions {
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
            title: title.trim().to_string(),
            artist: artist.trim().to_string(),
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
            let mut s = state.lock().unwrap_or_else(|e| e.into_inner());
            s.failures += 1;
            s.last_error = Some(format!("WinRT unavailable: {e}"));
            return;
        }
    };

    loop {
        let result = read_sessions();
        {
            let mut s = state.lock().unwrap_or_else(|e| e.into_inner());
            s.polls += 1;
            match result {
                Ok(sessions) => {
                    s.snapshot = super::snapshot(&sessions);
                    s.updated = Some(Instant::now());
                    s.last_error = None;
                }
                Err(e) => {
                    // Keep the previous snapshot. A broker that blinks should
                    // not blank the panel; the staleness clock is what says
                    // something is wrong, and the keepalive will expire the
                    // firmware's text slot if it stays wrong.
                    s.failures += 1;
                    s.last_error = Some(e.to_string());
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
