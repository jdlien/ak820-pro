//! The now-playing loop's decisions, ported from `nowplaying-windows.py`'s
//! `run()` — the media half's oracle, the way `ak820ctl.c` is the clock's.
//!
//! Every poll (3 s) the Python does exactly this:
//!
//! ```text
//! current = (icon, artist, title)
//! if current != last or now - keepalive_at >= 30 s:
//!     push the text  (two SET_LINE, or a CLEAR when there is nothing)
//!     on success: last = current, keepalive_at = now; log the change
//!     on failure: nothing moves, so the next poll tries again
//! push the playback readout, whatever happened above
//! ```
//!
//! Two of those are worth spelling out. `last` starts as nothing, so the first
//! poll always pushes — even a `CLEAR`, which is how a restart takes a stale
//! track off the panel. And the state moves only on a **successful** push:
//! a board that was absent at the moment of a track change gets the new
//! track on the next poll after it returns, not the one after that.
//!
//! The keepalive exists because the firmware expires the host text slot after
//! ~3 min, so a dead agent, a sleeping machine or an unplugged board cannot
//! leave a stale track up; 30 s re-asserts it comfortably inside that.
//!
//! This is the pure part. Talking to the board is [`crate::agent`]'s job.

use std::time::{Duration, Instant};

use crate::smtc::{self, Snapshot};

/// Seconds between polls. "1 s is wasteful and can make Spotify sluggish."
pub const INTERVAL: Duration = Duration::from_secs(3);
/// Re-push unchanged text this often, well inside the firmware's ~3 min
/// expiry of the host text slot.
pub const KEEPALIVE: Duration = Duration::from_secs(30);

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
    /// Did the most recent poll succeed? `true` before the first one, when
    /// the snapshot is the idle default and there is nothing stale to show.
    /// The daemon publishes idle while this is false, as the Python agent
    /// did when `read_state()` raised.
    pub last_poll_ok: bool,
}

/// Where snapshots come from: SMTC on Windows, MediaRemote on macOS.
///
/// Deliberately the lowest common denominator (plan, *`MediaSource` must be the
/// lowest common denominator*): the current session or none, never an invented
/// session list. Ranking, stickiness and what counts as a failed read are each
/// platform's own business; the daemon only ever asks for the latest answer,
/// and never blocks on it.
pub trait MediaSource {
    /// The most recent snapshot, and how the reads are going. Never blocks on
    /// the media API.
    fn latest(&self) -> (Snapshot, Health);
}

/// What one poll should put on the wire.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Plan {
    /// The text reports, when the text is due: changed, or keepalive.
    pub text: Option<Vec<(u8, Vec<u8>)>>,
    /// Whether the text differs from what was last pushed successfully — the
    /// Python logs the track only then, not on a keepalive.
    pub changed: bool,
    /// The playback readout. Always: USB sends it every poll. The radio sends
    /// it only when it matters (`crate::radio`, rule 3).
    pub playback: (u8, Vec<u8>),
}

/// The loop's memory: what the panel is known to show, and when it was last
/// told.
#[derive(Debug, Default)]
pub struct Publisher {
    last: Option<Snapshot>,
    keepalive_at: Option<Instant>,
}

impl Publisher {
    pub fn new() -> Publisher {
        Publisher::default()
    }

    /// Decide this poll. Pure: nothing moves until [`Publisher::text_pushed`].
    pub fn plan(&self, snapshot: &Snapshot, now: Instant) -> Plan {
        let changed = self.last.as_ref().is_none_or(|last| snapshot.text_differs(last));
        let keepalive_due = self
            .keepalive_at
            .is_none_or(|at| now.saturating_duration_since(at) >= KEEPALIVE);
        Plan {
            text: (changed || keepalive_due).then(|| smtc::text_reports(snapshot)),
            changed,
            playback: smtc::playback_report(snapshot),
        }
    }

    /// The text reports went out and were answered. Only now does the state
    /// move; a failed push leaves it where it was, and the next poll retries.
    pub fn text_pushed(&mut self, snapshot: &Snapshot, now: Instant) {
        self.last = Some(snapshot.clone());
        self.keepalive_at = Some(now);
    }

    /// Make the text due on the next plan whatever the keepalive says: the
    /// transport changed, or the radio's session is new (the raw81 daemon
    /// plan, R2-7), and the panel may not show what was last pushed.
    /// `changed` is unaffected, so a refresh is not logged as a new track.
    pub fn refresh(&mut self) {
        self.keepalive_at = None;
    }

    /// What the panel is believed to show, if anything has been pushed.
    pub fn shown(&self) -> Option<&Snapshot> {
        self.last.as_ref()
    }

    /// The log line the Python writes on a change:
    /// `f"{icon:5} {artist} - {title}" if artist else f"{icon:5} {title}"`.
    pub fn describe(snapshot: &Snapshot) -> String {
        let icon = snapshot.icon.name();
        if snapshot.artist.is_empty() {
            format!("{icon:<5} {}", snapshot.title)
        } else {
            format!("{icon:<5} {} - {}", snapshot.artist, snapshot.title)
        }
    }
}

/// How long a pause of the playing track is held back before it is shown.
///
/// Measured on 2026-11-09 with Apple Music: a skip often reports the old
/// track paused for 3-4 s before the next track's `now` arrives (4 of that
/// day's 93 title changes, the gap from the pause frame to the next title
/// 3, 3, 3 and 4 s), so the panel showed a pause nobody pressed. 5 s covers
/// those and delays a real pause by 5 s.
pub const PAUSE_HOLD: Duration = Duration::from_secs(5);

/// Holds back a play-to-pause of the same track for [`PAUSE_HOLD`], so a
/// skip's momentary pause never reaches the panel.
///
/// Only that one transition is held: the same artist and title going from
/// playing to paused. Anything else passes at once: a new track (playing or
/// paused), idle, a resume, and a pause with no playing track before it.
/// While a pause is held the loop publishes the last playing snapshot with
/// its position advanced by the time since it was taken, as if the pause had
/// not happened. If the pause outlasts the hold it passes through as it is.
///
/// ⚠️ The position is advanced from when it was **true** (`pos_at`: the
/// source's observation on Windows, the snapshot's creation on the Mac), not
/// from when the loop took it: a Windows read cached for 6 s would otherwise
/// come back 6 s behind, which the lock-light channel takes for a seek
/// (codex, pause hold, P2).
#[derive(Debug, Default)]
pub struct PauseHold {
    /// The last playing snapshot and when its position was true.
    playing: Option<(Snapshot, Instant)>,
    /// When the held pause was first seen.
    since: Option<Instant>,
}

impl PauseHold {
    pub fn new() -> PauseHold {
        PauseHold::default()
    }

    /// What to publish at `now` in place of `snapshot`, whose position was
    /// true at `pos_at`, and, while a pause is held, when the hold ends (the
    /// loop takes its next look then). A held snapshot's position is true at
    /// `now`.
    pub fn filter(&mut self, snapshot: Snapshot, pos_at: Instant, now: Instant) -> (Snapshot, Option<Instant>) {
        if snapshot.playing {
            self.playing = Some((snapshot.clone(), pos_at));
            self.since = None;
            return (snapshot, None);
        }
        let same_track = self
            .playing
            .as_ref()
            .is_some_and(|(p, _)| !snapshot.is_idle() && p.artist == snapshot.artist && p.title == snapshot.title);
        if !same_track {
            self.playing = None;
            self.since = None;
            return (snapshot, None);
        }
        let until = *self.since.get_or_insert(now) + PAUSE_HOLD;
        if now >= until {
            self.playing = None;
            self.since = None;
            return (snapshot, None);
        }
        let Some((p, at)) = &self.playing else { return (snapshot, None) };
        let mut held = p.clone();
        let ran = now.saturating_duration_since(*at).as_secs().min(u32::MAX as u64) as u32;
        held.pos_s = held.pos_s.saturating_add(ran);
        if held.dur_s != 0 {
            held.pos_s = held.pos_s.min(held.dur_s);
        }
        (held, Some(until))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::text::{self, Icon};

    /// The hold with the position true when the loop takes the snapshot, as
    /// on the Mac.
    fn f(h: &mut PauseHold, s: Snapshot, now: Instant) -> (Snapshot, Option<Instant>) {
        h.filter(s, now, now)
    }

    /// The held position runs from when the playing position was true, not
    /// from when the loop took it: a Windows read cached 6 s comes back 6 s
    /// on, not 1 (codex, pause hold, P2).
    #[test]
    fn the_held_position_runs_from_when_it_was_true() {
        let mut h = PauseHold::new();
        let start = t0();
        h.filter(track("A", "T", true, 100, 300), start, start + Duration::from_secs(6));
        let at = start + Duration::from_secs(7);
        let (s, _) = h.filter(track("A", "T", false, 101, 300), at, at);
        assert_eq!(s.pos_s, 107);
    }

    /// A skip's momentary pause: held, the old track still playing with its
    /// position advanced, then the new track passes at once.
    #[test]
    fn a_skips_momentary_pause_is_held_and_the_next_track_passes() {
        let mut h = PauseHold::new();
        let start = t0();
        let (s, until) = f(&mut h, track("A", "T", true, 100, 300), start);
        assert_eq!((s, until), (track("A", "T", true, 100, 300), None));
        let at = start + Duration::from_secs(3);
        let (s, until) = f(&mut h, track("A", "T", false, 101, 300), at);
        assert_eq!(s, track("A", "T", true, 103, 300), "held: still playing, position advanced");
        assert_eq!(until, Some(at + PAUSE_HOLD));
        let (s, until) = f(&mut h, track("B", "U", true, 0, 200), at + Duration::from_secs(3));
        assert_eq!((s, until), (track("B", "U", true, 0, 200), None));
    }

    /// A real pause shows once it outlasts the hold, and stays shown.
    #[test]
    fn a_real_pause_shows_after_the_hold() {
        let mut h = PauseHold::new();
        let start = t0();
        f(&mut h, track("A", "T", true, 10, 300), start);
        let paused = track("A", "T", false, 12, 300);
        let first = start + Duration::from_secs(2);
        assert!(f(&mut h, paused.clone(), first).0.playing);
        assert!(f(&mut h, paused.clone(), first + PAUSE_HOLD - Duration::from_millis(1)).0.playing);
        assert_eq!(f(&mut h, paused.clone(), first + PAUSE_HOLD), (paused.clone(), None));
        assert_eq!(f(&mut h, paused.clone(), first + PAUSE_HOLD * 3), (paused, None), "no second hold");
    }

    /// The hold is timed from the pause's first sighting, not renewed by
    /// each poll that still sees it.
    #[test]
    fn the_hold_runs_from_the_first_sighting() {
        let mut h = PauseHold::new();
        let start = t0();
        f(&mut h, track("A", "T", true, 10, 300), start);
        let paused = track("A", "T", false, 12, 300);
        let first = start + Duration::from_secs(1);
        let (_, u1) = f(&mut h, paused.clone(), first);
        let (_, u2) = f(&mut h, paused, first + Duration::from_secs(3));
        assert_eq!((u1, u2), (Some(first + PAUSE_HOLD), Some(first + PAUSE_HOLD)));
    }

    /// A resume inside the hold passes, and a later pause gets a hold of its
    /// own.
    #[test]
    fn a_resume_ends_the_hold_and_a_later_pause_is_held_afresh() {
        let mut h = PauseHold::new();
        let start = t0();
        f(&mut h, track("A", "T", true, 10, 300), start);
        f(&mut h, track("A", "T", false, 11, 300), start + Duration::from_secs(1));
        let resumed = track("A", "T", true, 12, 300);
        assert_eq!(f(&mut h, resumed.clone(), start + Duration::from_secs(2)), (resumed, None));
        let later = start + Duration::from_secs(60);
        assert_eq!(f(&mut h, track("A", "T", false, 70, 300), later).1, Some(later + PAUSE_HOLD));
    }

    /// Only the same track's play-to-pause is held: a new track that arrives
    /// paused, a pause with nothing playing before it, and idle all pass.
    #[test]
    fn only_the_same_tracks_pause_is_held() {
        let start = t0();
        let mut h = PauseHold::new();
        let cold = track("A", "T", false, 10, 300);
        assert_eq!(f(&mut h, cold.clone(), start), (cold, None), "nothing was playing");
        f(&mut h, track("A", "T", true, 10, 300), start);
        let other = track("B", "U", false, 0, 200);
        assert_eq!(f(&mut h, other.clone(), start + Duration::from_secs(1)), (other, None), "a new track");
        let mut h = PauseHold::new();
        f(&mut h, track("A", "T", true, 10, 300), start);
        let idle = Snapshot::idle();
        assert_eq!(f(&mut h, idle.clone(), start + Duration::from_secs(1)), (idle, None), "idle");
        let after = track("A", "T", false, 12, 300);
        assert_eq!(f(&mut h, after.clone(), start + Duration::from_secs(2)), (after, None), "idle broke the run");
    }

    /// The held position stops at a known duration, and a stream's (no
    /// duration) runs on.
    #[test]
    fn the_held_position_is_clamped_to_the_duration() {
        let start = t0();
        let mut h = PauseHold::new();
        f(&mut h, track("A", "T", true, 298, 300), start);
        assert_eq!(f(&mut h, track("A", "T", false, 299, 300), start + Duration::from_secs(4)).0.pos_s, 300);
        let mut h = PauseHold::new();
        f(&mut h, track("A", "T", true, 298, 0), start);
        assert_eq!(f(&mut h, track("A", "T", false, 299, 0), start + Duration::from_secs(4)).0.pos_s, 302);
    }

    fn track(artist: &str, title: &str, playing: bool, pos: u32, dur: u32) -> Snapshot {
        Snapshot {
            icon: if playing { Icon::Play } else { Icon::Pause },
            artist: artist.into(),
            title: title.into(),
            playing,
            pos_s: pos,
            dur_s: dur,
        }
    }

    fn t0() -> Instant {
        Instant::now()
    }

    /// `last` starts as nothing, so the very first poll pushes — even idle,
    /// which is a `CLEAR`. That is how a restart takes a stale track down.
    #[test]
    fn the_first_poll_always_pushes_even_idle() {
        let p = Publisher::new();
        let plan = p.plan(&Snapshot::idle(), t0());
        assert_eq!(plan.text, Some(vec![(text::CLEAR, vec![])]));
        assert!(plan.changed);
        assert_eq!(plan.playback, (text::PLAYBACK, text::playback_body(false, 0, 0).to_vec()));
    }

    #[test]
    fn a_track_is_two_rows_and_a_readout() {
        let p = Publisher::new();
        let snap = track("Artist", "Title", true, 42, 300);
        let plan = p.plan(&snap, t0());
        assert_eq!(
            plan.text,
            Some(vec![
                (text::SET_LINE, text::line_body(text::Line::WithIcon, "Artist", Icon::Play)),
                (text::SET_LINE, text::line_body(text::Line::FullWidth, "Title", Icon::Play)),
            ])
        );
        assert_eq!(plan.playback, (text::PLAYBACK, text::playback_body(true, 42, 300).to_vec()));
    }

    /// Unchanged text inside the keepalive window is not re-sent; the
    /// playback readout goes every poll regardless.
    #[test]
    fn unchanged_text_is_not_resent_but_playback_is() {
        let mut p = Publisher::new();
        let snap = track("A", "T", true, 10, 100);
        let start = t0();
        p.text_pushed(&snap, start);
        let later = track("A", "T", true, 13, 100); // position moved, text did not
        let plan = p.plan(&later, start + Duration::from_secs(3));
        assert_eq!(plan.text, None);
        assert!(!plan.changed);
        assert_eq!(plan.playback, (text::PLAYBACK, text::playback_body(true, 13, 100).to_vec()));
    }

    /// At 30 s the same text is pushed again, and it is not a "change".
    #[test]
    fn the_keepalive_repushes_at_thirty_seconds() {
        let mut p = Publisher::new();
        let snap = track("A", "T", true, 10, 100);
        let start = t0();
        p.text_pushed(&snap, start);
        assert_eq!(p.plan(&snap, start + Duration::from_millis(29_999)).text, None);
        let plan = p.plan(&snap, start + KEEPALIVE);
        assert!(plan.text.is_some());
        assert!(!plan.changed, "a keepalive is not logged as a track change");
    }

    /// A change is pushed at once, whatever the keepalive clock says.
    #[test]
    fn a_change_is_pushed_immediately() {
        let mut p = Publisher::new();
        let start = t0();
        p.text_pushed(&track("A", "T", true, 0, 100), start);
        let plan = p.plan(&track("A", "T2", true, 3, 100), start + Duration::from_secs(3));
        assert!(plan.text.is_some());
        assert!(plan.changed);
        // pause is a change too: the icon differs
        let plan = p.plan(&track("A", "T", false, 3, 100), start + Duration::from_secs(3));
        assert!(plan.changed);
    }

    /// ⚠️ A failed push moves nothing, so the next poll pushes again. Without
    /// this a track change during an unplug would be lost until the keepalive.
    #[test]
    fn a_failed_push_is_retried_next_poll() {
        let mut p = Publisher::new();
        let start = t0();
        p.text_pushed(&track("A", "T", true, 0, 100), start);
        let new = track("A", "T2", true, 3, 100);
        let plan = p.plan(&new, start + Duration::from_secs(3));
        assert!(plan.changed);
        // ... the push fails: text_pushed is NOT called ...
        let again = p.plan(&new, start + Duration::from_secs(6));
        assert!(again.text.is_some());
        assert!(again.changed, "still a change, still logged when it finally lands");
        p.text_pushed(&new, start + Duration::from_secs(6));
        assert_eq!(p.plan(&new, start + Duration::from_secs(9)).text, None);
    }

    #[test]
    fn going_idle_clears_the_band_once() {
        let mut p = Publisher::new();
        let start = t0();
        p.text_pushed(&track("A", "T", true, 0, 100), start);
        let plan = p.plan(&Snapshot::idle(), start + Duration::from_secs(3));
        assert_eq!(plan.text, Some(vec![(text::CLEAR, vec![])]));
        assert!(plan.changed);
        p.text_pushed(&Snapshot::idle(), start + Duration::from_secs(3));
        assert_eq!(p.plan(&Snapshot::idle(), start + Duration::from_secs(6)).text, None);
    }

    /// The Python's log line, both shapes, with the icon left-justified to 5.
    #[test]
    fn describe_matches_the_python_log_line() {
        assert_eq!(Publisher::describe(&track("Artist", "Title", true, 0, 0)), "play  Artist - Title");
        assert_eq!(Publisher::describe(&track("", "Title", false, 0, 0)), "pause Title");
        assert_eq!(Publisher::describe(&Snapshot::idle()), "none  ");
    }
}
