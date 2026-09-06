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

/// What one poll should put on the wire.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Plan {
    /// The text reports, when the text is due: changed, or keepalive.
    pub text: Option<Vec<(u8, Vec<u8>)>>,
    /// Whether the text differs from what was last pushed successfully — the
    /// Python logs the track only then, not on a keepalive.
    pub changed: bool,
    /// The playback readout. Always.
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::text::{self, Icon};

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
