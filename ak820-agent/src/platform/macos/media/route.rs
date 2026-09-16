//! From MediaRemote's `now` messages to the neutral [`Snapshot`]. Pure.
//!
//! Three rules, each from the sibling's `MacMediaSessionService.cs`, which has
//! shipped them:
//!
//! - **Rate is the honest playing signal.** A paused player can keep the
//!   session and report `playing` loosely; `rate > 0` is what playback is, and
//!   the `playing` flag decides only when there is no rate.
//! - ⚠️ **Stickiness, 5 s.** macOS sometimes names a *paused* app as current
//!   while another is still playing. Windows ranks sessions itself and puts
//!   playing above paused; here the OS ranks, so a switch from a playing app to
//!   a non-playing different one is ignored for 5 s after the last sign of
//!   playback. Without it the LCD flips to the wrong app.
//! - **Position extrapolates from the player's own clock.** `elapsed` is true
//!   as of `elapsedAt` (Unix seconds); while playing, the position shown is
//!   `elapsed + (now − elapsedAt) × rate`, with the same `0 ≤ age < 600 s`
//!   honesty gate `smtc::position` applies on Windows. This is new work, not
//!   inherited (plan, *The finding that changes the shape*).
//!
//! Text is trimmed exactly as Python's `str.strip()` trims (`text::PY_SPACE`),
//! as the Windows worker does, so an artist of only a stray separator is empty
//! on both platforms and moves the title to the same row.

use std::time::{Duration, Instant};

use super::message::Now;
use crate::smtc::Snapshot;
use crate::text::Icon;

pub const PLAYING_STICKINESS: Duration = Duration::from_secs(5);

/// Readings older than this are not extrapolated from, as on Windows.
const MAX_AGE_S: f64 = 600.0;

fn py_trim(s: &str) -> &str {
    s.trim_matches(|c| crate::text::PY_SPACE.contains(&c))
}

pub fn is_playing(now: &Now) -> bool {
    match now.rate {
        Some(rate) => rate > 0.0,
        None => now.playing,
    }
}

/// What MediaRemote last said, after stickiness.
///
/// ⚠️ **A held message is deferred, not dropped.** MediaRemote sends `now` on
/// change and never repeats it, so a switch ignored for stickiness would
/// otherwise never land: quit Spotify mid-track, the `bundle: null` that
/// follows is held, and the panel shows Spotify playing forever. The sibling
/// drops it (`MacMediaSessionService.cs` `OnHostState`); here the latest held
/// message lands at [`Router::settle`] once the hold runs out, unless something
/// newer was accepted first.
#[derive(Debug, Default)]
pub struct Router {
    current: Option<Now>,
    playing_since: Option<Instant>,
    held: Option<Now>,
}

impl Router {
    /// Take a `now` message, unless stickiness says to hold it. Returns
    /// whether it was taken.
    ///
    /// "Playing" is [`is_playing`] on both sides, rate first. The sibling
    /// counts the incoming `playing` flag alone as playing, so a paused player
    /// reporting the flag loosely could take the band at once; here it waits
    /// out the hold like any other paused app.
    pub fn accept(&mut self, incoming: Now, at: Instant) -> bool {
        let incoming_playing = is_playing(&incoming);
        if let Some(current) = &self.current {
            let different_app = !incoming.bundle.as_deref().unwrap_or("").eq_ignore_ascii_case(current.bundle.as_deref().unwrap_or(""));
            if different_app && !incoming_playing && self.holding(at) {
                self.held = Some(incoming);
                return false;
            }
        }
        if incoming_playing {
            self.playing_since = Some(at);
        }
        self.current = Some(incoming);
        self.held = None;
        true
    }

    fn holding(&self, at: Instant) -> bool {
        self.current.as_ref().is_some_and(|c| is_playing(c) && c.bundle.as_deref().is_some_and(|b| !b.is_empty()))
            && self.playing_since.is_some_and(|t| at.saturating_duration_since(t) < PLAYING_STICKINESS)
    }

    /// Land a held message whose hold has run out. Called every poll. Returns
    /// whether anything changed.
    pub fn settle(&mut self, at: Instant) -> bool {
        if self.held.is_some() && !self.holding(at) {
            self.current = self.held.take();
            return true;
        }
        false
    }

    /// The latest accepted message.
    pub fn current(&self) -> Option<&Now> {
        self.current.as_ref()
    }

    /// The owning app of the latest accepted message.
    pub fn bundle(&self) -> Option<&str> {
        self.current.as_ref().and_then(|n| n.bundle.as_deref())
    }

    /// Does the latest accepted message name an owning app?
    pub fn has_bundle(&self) -> bool {
        self.current.as_ref().and_then(|n| n.bundle.as_deref()).is_some_and(|b| !b.is_empty())
    }

    /// The owning app, when it answered MediaRemote's client call but not the
    /// metadata call.
    pub fn stale_owner(&self) -> Option<&str> {
        self.current.as_ref().filter(|n| n.stale).and_then(|n| n.bundle.as_deref())
    }

    /// The snapshot as of `wall_now` (Unix seconds).
    pub fn snapshot(&self, wall_now: f64) -> Snapshot {
        match &self.current {
            Some(now) => snapshot_of(now, wall_now),
            None => Snapshot::idle(),
        }
    }
}

/// Seconds as the protocol carries them: truncated, clamped at zero.
fn secs(v: f64) -> u32 {
    if !v.is_finite() || v <= 0.0 {
        return 0;
    }
    v.trunc().min(u32::MAX as f64) as u32
}

/// One `now`, as the LCD should show it at `wall_now`.
pub fn snapshot_of(now: &Now, wall_now: f64) -> Snapshot {
    if now.bundle.as_deref().is_none_or(str::is_empty) {
        return Snapshot::idle();
    }
    let title = py_trim(now.title.as_deref().unwrap_or("")).to_string();
    // No artist: the album, as the sibling does, since MediaRemote reports the
    // two separately and a podcast's album is its show.
    let artist = match py_trim(now.artist.as_deref().unwrap_or("")) {
        "" => py_trim(now.album.as_deref().unwrap_or("")).to_string(),
        a => a.to_string(),
    };
    let playing = is_playing(now);
    if title.is_empty() && artist.is_empty() && !playing {
        return Snapshot::idle(); // an owner with nothing loaded: stopped
    }
    let dur_s = now.duration.map(secs).unwrap_or(0);
    let mut pos = now.elapsed.unwrap_or(0.0);
    if playing {
        if let (Some(at), Some(rate)) = (now.elapsed_at, now.rate.or(Some(1.0))) {
            let age = wall_now - at;
            if (0.0..MAX_AGE_S).contains(&age) {
                pos += age * rate.max(0.0);
            }
        }
    }
    let mut pos_s = secs(pos);
    if dur_s != 0 {
        pos_s = pos_s.min(dur_s);
    }
    Snapshot { icon: if playing { Icon::Play } else { Icon::Pause }, artist, title, playing, pos_s, dur_s }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn track(bundle: &str, title: &str, artist: &str, rate: f64) -> Now {
        Now {
            bundle: Some(bundle.into()),
            playing: rate > 0.0,
            title: Some(title.into()),
            artist: Some(artist.into()),
            duration: Some(244.8),
            elapsed: Some(10.4),
            elapsed_at: Some(1_000.0),
            rate: Some(rate),
            ..Now::default()
        }
    }

    #[test]
    fn a_playing_track_extrapolates_from_the_players_clock() {
        let s = snapshot_of(&track("com.apple.Music", "Eternal Venus Sunset", "A.L.I.S.O.N", 1.0), 1_012.9);
        assert_eq!((s.icon, s.playing, s.pos_s, s.dur_s), (Icon::Play, true, 23, 244));
        assert_eq!((s.artist.as_str(), s.title.as_str()), ("A.L.I.S.O.N", "Eternal Venus Sunset"));
    }

    #[test]
    fn a_paused_track_does_not_extrapolate_and_shows_no_readout() {
        let s = snapshot_of(&track("com.apple.Music", "T", "A", 0.0), 1_500.0);
        assert_eq!((s.icon, s.playing, s.pos_s), (Icon::Pause, false, 10));
        assert_eq!(s.playback(), (false, 0, 0));
    }

    #[test]
    fn rate_decides_over_the_playing_flag() {
        let mut n = track("com.google.Chrome", "T", "A", 0.0);
        n.playing = true; // loose flag, rate 0: paused
        assert!(!is_playing(&n));
        n.rate = None; // no rate: the flag decides
        assert!(is_playing(&n));
    }

    #[test]
    fn stale_or_future_timestamps_are_not_extrapolated() {
        let n = track("x", "T", "A", 1.0);
        assert_eq!(snapshot_of(&n, 1_000.0 + 900.0).pos_s, 10, "older than 600 s");
        assert_eq!(snapshot_of(&n, 990.0).pos_s, 10, "clock says the reading is from the future");
    }

    #[test]
    fn position_is_clamped_to_the_duration() {
        let n = track("x", "T", "A", 1.0);
        assert_eq!(snapshot_of(&n, 1_000.0 + 500.0).pos_s, 244);
    }

    #[test]
    fn no_owner_or_nothing_loaded_is_idle() {
        assert!(snapshot_of(&Now::default(), 0.0).is_idle());
        let empty = Now { bundle: Some("com.apple.Music".into()), ..Now::default() };
        assert!(snapshot_of(&empty, 0.0).is_idle());
    }

    #[test]
    fn a_missing_artist_falls_back_to_the_album_and_text_is_python_stripped() {
        let mut n = track("x", "  Episode 12 \u{1f}", "\u{1c}", 1.0);
        n.album = Some(" The Show ".into());
        let s = snapshot_of(&n, 1_000.0);
        assert_eq!((s.artist.as_str(), s.title.as_str()), ("The Show", "Episode 12"));
    }

    /// The sibling's measured case: macOS names a paused app while another is
    /// still playing. Held for 5 s after the last sign of playback, then let go.
    #[test]
    fn a_paused_app_cannot_steal_the_band_from_a_playing_one_for_five_seconds() {
        let mut r = Router::default();
        let t = Instant::now();
        assert!(r.accept(track("com.spotify.client", "Playing", "A", 1.0), t));
        assert!(!r.accept(track("com.apple.Music", "Paused", "B", 0.0), t + Duration::from_secs(2)));
        assert_eq!(r.snapshot(1_000.0).title, "Playing");
        assert!(r.accept(track("com.apple.Music", "Paused", "B", 0.0), t + PLAYING_STICKINESS));
        assert_eq!(r.snapshot(1_000.0).title, "Paused");
    }

    #[test]
    fn stickiness_never_blocks_a_playing_app_or_the_same_app_pausing() {
        let mut r = Router::default();
        let t = Instant::now();
        r.accept(track("com.spotify.client", "A", "X", 1.0), t);
        assert!(r.accept(track("com.google.Chrome", "B", "Y", 1.0), t + Duration::from_secs(1)), "a playing app takes over at once");
        assert!(r.accept(track("com.google.Chrome", "B", "Y", 0.0), t + Duration::from_secs(2)), "the same app pausing is news");
        assert!(r.snapshot(0.0).icon == Icon::Pause);
    }

    /// Quit the playing app: MediaRemote sends one `bundle: null` and never
    /// repeats it. Held, then landed by `settle` without a second message.
    #[test]
    fn a_held_switch_lands_when_the_hold_runs_out_without_being_resent() {
        let mut r = Router::default();
        let t = Instant::now();
        r.accept(track("com.spotify.client", "A", "X", 1.0), t);
        assert!(!r.accept(Now::default(), t + Duration::from_secs(1)));
        assert!(!r.settle(t + Duration::from_secs(4)), "still inside the hold");
        assert!(r.has_bundle());
        assert!(r.settle(t + PLAYING_STICKINESS));
        assert!(r.snapshot(0.0).is_idle());
        assert!(!r.has_bundle());
        assert!(!r.settle(t + PLAYING_STICKINESS * 2), "nothing left to land");
    }

    /// Something newer accepted during the hold wins; the held one is dropped.
    #[test]
    fn a_newer_accepted_message_discards_the_held_one() {
        let mut r = Router::default();
        let t = Instant::now();
        r.accept(track("com.spotify.client", "A", "X", 1.0), t);
        assert!(!r.accept(track("com.apple.Music", "Paused", "B", 0.0), t + Duration::from_secs(1)));
        assert!(r.accept(track("com.spotify.client", "Next", "X", 1.0), t + Duration::from_secs(2)));
        assert!(!r.settle(t + Duration::from_secs(60)));
        assert_eq!(r.snapshot(0.0).title, "Next");
    }
}
