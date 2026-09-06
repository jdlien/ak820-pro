//! What Windows is playing, and what that should put on the LCD.
//!
//! Port of `hostagent/nowplaying-windows.py`. Windows has a real OS-level API
//! for this — `GlobalSystemMediaTransportControlsSessionManager`, "SMTC" — which
//! is what the media flyout on the volume keys reads, so every app that
//! registers a session is visible through one interface, browsers included.
//!
//! ⚠️ An app that does not register an SMTC session is invisible here and no
//! amount of work in this module can change that. `ak820 probe` reports what
//! the API can actually see, per app, which is the answer to "why doesn't
//! <app> show up?".
//!
//! This file is the **pure** half: given facts about the sessions, which one
//! wins and what goes on the two rows. It holds no WinRT types and no clock, so
//! every ranking rule below is a test rather than a thing to try in front of a
//! keyboard. [`worker`] is the half that talks to WinRT.

pub mod worker;

use crate::text::{Icon, Line};

/// The subset of `GlobalSystemMediaTransportControlsSessionPlaybackStatus`
/// that changes what we do.
///
/// `Closed`, `Opened`, `Changing` and `Stopped` all collapse to [`Other`],
/// because they all mean "nothing to show" — an app that is merely open with
/// nothing loaded is not something to put on a keyboard.
///
/// [`Other`]: Status::Other
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Status {
    Playing,
    Paused,
    Other,
}

/// Where a session says it is in the track.
///
/// ⚠️ **Raw 100 ns ticks, not seconds, and that is a correctness fix rather
/// than a style choice.** Python subtracts `timedelta` values — exact integer
/// arithmetic — and only then converts to seconds. Converting each endpoint to
/// `f64` first and subtracting loses the low bits, and the loss lands exactly
/// where it hurts: a 245-second track starting at 11.001 s came out as
/// `244.99999999999997`, which truncates to **244**. An off-by-one on an
/// entirely ordinary track, found by the phase-1 audit.
///
/// Subtracting ticks is exact for any value this protocol can carry, so the
/// truncation below is the only rounding that happens.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct Timeline {
    pub start_ticks: i64,
    pub end_ticks: i64,
    pub position_ticks: i64,
    /// Seconds since `LastUpdatedTime`, or `None` if the session reports none.
    pub age_s: Option<f64>,
}

/// 100 ns ticks per second — WinRT's `TimeSpan` and `DateTime` unit.
pub const TICKS_PER_SEC: i64 = 10_000_000;

/// One SMTC session, already read out of WinRT.
#[derive(Clone, Debug, PartialEq)]
pub struct SessionFacts {
    pub app_id: String,
    pub status: Status,
    /// Already trimmed, still Unicode — folding to ASCII happens later, at the
    /// point where the line budget is applied.
    pub title: String,
    pub artist: String,
    /// `None` when the session exposes no timeline. foobar2000 2.24.6 reports
    /// `0s/0s`, which is a timeline saying nothing rather than no timeline.
    pub timeline: Option<Timeline>,
    /// Whether this is the manager's `GetCurrentSession`.
    pub is_current: bool,
}

/// What to draw, once a session has been chosen.
#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct Snapshot {
    pub icon: Icon,
    pub artist: String,
    pub title: String,
    pub playing: bool,
    pub pos_s: u32,
    pub dur_s: u32,
}

impl Snapshot {
    /// Nothing worth showing: hand the band back to the clock.
    pub fn idle() -> Snapshot {
        Snapshot::default()
    }

    /// Is this the "nothing playing" state?
    pub fn is_idle(&self) -> bool {
        self.icon == Icon::None && self.title.is_empty() && self.artist.is_empty()
    }

    /// The two rows, or `None` when the band should be cleared instead.
    ///
    /// ⚠️ The artist takes the **narrow** row and the title the full-width one.
    /// That is deliberate and matches the macOS agent exactly: the artist is
    /// the less valuable of the two and can afford losing ~2 characters to the
    /// transport icon.
    ///
    /// With no artist the title moves up to row 0 and row 1 is cleared
    /// **explicitly** — sending nothing would leave a previous artist sitting
    /// under a new title, which is worse than either.
    pub fn lines(&self) -> Option<(&str, &str, Icon)> {
        if self.is_idle() {
            return None;
        }
        Some(if self.artist.is_empty() {
            (self.title.as_str(), "", self.icon)
        } else {
            (self.artist.as_str(), self.title.as_str(), self.icon)
        })
    }

    /// `(state, pos, dur)` for the playback readout drawn in place of the clock.
    ///
    /// A zero duration means the app exposes no usable timeline — foobar2000
    /// reports `0s/0s` — and a progress bar of unknown length is worse than
    /// none, so that hands the band back to the clock rather than showing a bar
    /// stuck at zero.
    pub fn playback(&self) -> (bool, u32, u32) {
        if self.playing && self.dur_s != 0 {
            (true, self.pos_s, self.dur_s)
        } else {
            (false, 0, 0)
        }
    }

    /// Does this differ from `other` in a way the LCD would show?
    ///
    /// Position deliberately excluded: it changes every second and the firmware
    /// ticks its own timer between pushes, so treating it as a change would
    /// rewrite the text band constantly for nothing.
    pub fn text_differs(&self, other: &Snapshot) -> bool {
        self.icon != other.icon || self.artist != other.artist || self.title != other.title
    }
}

/// Sort key for a session, or `None` if it is not a candidate at all.
///
/// ⚠️ Lower is better, and the second element matters more than it looks. The
/// system's "current" session is routinely an app that is merely **open with
/// nothing loaded** — Apple Music does this at launch — while the thing
/// actually holding a track is a different session. Taking `current` blindly
/// showed an empty band with foobar2000 paused on a track.
///
/// So: playing beats paused, and only within a status does the system's current
/// session win, which keeps a deliberate foreground choice honoured.
pub fn rank(session: &SessionFacts) -> Option<(u8, u8)> {
    let base = match session.status {
        Status::Playing => 0,
        Status::Paused => 1,
        Status::Other => return None,
    };
    Some((base, u8::from(!session.is_current)))
}

/// The session whose track should be on the panel.
///
/// Ties keep the manager's own ordering: `min_by_key` returns the first of
/// several equal minima, which is what Python's stable sort does too.
pub fn choose(sessions: &[SessionFacts]) -> Option<&SessionFacts> {
    sessions
        .iter()
        .filter(|s| rank(s).is_some())
        .min_by_key(|s| rank(s).expect("filtered"))
}

/// Whole seconds from a tick difference, truncated toward zero and clamped at
/// zero — Python's `max(0, int(delta.total_seconds()))`, without the float.
///
/// Integer division in Rust truncates toward zero, which is what `int()` does,
/// so negative inputs agree too before the clamp takes them to zero.
fn secs(ticks: i64) -> u32 {
    (ticks / TICKS_PER_SEC).clamp(0, u32::MAX as i64) as u32
}

/// The same, for the one value that genuinely is a float: the age of a reading.
fn secs_f(v: f64) -> u32 {
    if !v.is_finite() || v <= 0.0 {
        return 0;
    }
    v.trunc().min(u32::MAX as f64) as u32
}

/// Where the chosen session is in its track.
///
/// ⚠️ The extrapolation is the interesting part. **SMTC updates position on
/// events, not continuously**, so a poll can read a value several seconds stale
/// and the bar would visibly jump backwards on every push. Adding the age of
/// the reading re-asserts the truth instead, and the firmware ticks its own
/// timer in between — which is what makes it read as a running clock rather
/// than a value that lurches once a poll.
///
/// The `0 <= age < 600` gate is what keeps that honest: a negative age means
/// the clocks disagree and a huge one means the timestamp is meaningless (a
/// session reporting a zero `LastUpdatedTime` lands in 1601). Either way,
/// trust the position as read.
fn position(timeline: &Timeline, playing: bool) -> (u32, u32) {
    let dur = secs(timeline.end_ticks.saturating_sub(timeline.start_ticks));
    let mut pos = secs(timeline.position_ticks.saturating_sub(timeline.start_ticks));

    if playing {
        if let Some(age) = timeline.age_s {
            if (0.0..600.0).contains(&age) {
                pos = pos.saturating_add(secs_f(age));
            }
        }
    }
    if dur != 0 {
        pos = pos.min(dur);
    }
    (pos, dur)
}

/// Rank the sessions, then read the winner.
pub fn snapshot(sessions: &[SessionFacts]) -> Snapshot {
    let Some(chosen) = choose(sessions) else {
        return Snapshot::idle();
    };
    let (icon, playing) = match chosen.status {
        Status::Playing => (Icon::Play, true),
        Status::Paused => (Icon::Pause, false),
        Status::Other => return Snapshot::idle(),
    };
    let (pos_s, dur_s) = match &chosen.timeline {
        Some(t) => position(t, playing),
        None => (0, 0),
    };
    Snapshot {
        icon,
        artist: chosen.artist.clone(),
        title: chosen.title.clone(),
        playing,
        pos_s,
        dur_s,
    }
}

/// The reports one snapshot turns into, in the order they must be written.
///
/// ⚠️ Order and batching both matter. The firmware repaints the text band from
/// its ~10 Hz housekeeping tick, so two reports that straddle a tick boundary
/// produce **two** full-band clear-and-redraw cycles — a visible double flash on
/// every track change. Issued back to back through one open they are ~1 ms
/// apart and land in the same tick.
pub fn reports(snapshot: &Snapshot) -> Vec<(u8, Vec<u8>)> {
    use crate::text;
    let mut out = Vec::with_capacity(3);
    match snapshot.lines() {
        None => out.push((text::CLEAR, Vec::new())),
        Some((row0, row1, icon)) => {
            out.push((text::SET_LINE, text::line_body(Line::WithIcon, row0, icon)));
            out.push((text::SET_LINE, text::line_body(Line::FullWidth, row1, icon)));
        }
    }
    let (state, pos, dur) = snapshot.playback();
    out.push((text::PLAYBACK, text::playback_body(state, pos, dur).to_vec()));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session(app: &str, status: Status, current: bool) -> SessionFacts {
        SessionFacts {
            app_id: app.into(),
            status,
            title: format!("{app} title"),
            artist: format!("{app} artist"),
            timeline: None,
            is_current: current,
        }
    }

    #[test]
    fn nothing_at_all_is_idle() {
        assert_eq!(snapshot(&[]), Snapshot::idle());
        assert!(Snapshot::idle().is_idle());
        assert_eq!(Snapshot::idle().lines(), None);
    }

    /// Closed / Opened / Changing / Stopped are all "nothing to show".
    #[test]
    fn only_playing_and_paused_are_candidates() {
        let sessions = [session("idle", Status::Other, true)];
        assert!(choose(&sessions).is_none());
        assert!(snapshot(&sessions).is_idle());
    }

    /// The regression the ranking exists for: the system's current session was
    /// an app merely open with nothing loaded, while foobar2000 held the track.
    #[test]
    fn a_playing_session_beats_the_current_one_that_is_paused() {
        let sessions = [
            session("AppleMusic", Status::Paused, true),
            session("foobar", Status::Playing, false),
        ];
        assert_eq!(choose(&sessions).unwrap().app_id, "foobar");
    }

    /// ... but within a status the foreground choice is still honoured.
    #[test]
    fn the_current_session_wins_among_equals() {
        let sessions = [
            session("Chrome", Status::Playing, false),
            session("Spotify", Status::Playing, true),
        ];
        assert_eq!(choose(&sessions).unwrap().app_id, "Spotify");

        let paused = [
            session("Chrome", Status::Paused, false),
            session("Spotify", Status::Paused, true),
        ];
        assert_eq!(choose(&paused).unwrap().app_id, "Spotify");
    }

    /// No current flag anywhere: the manager's own order decides, and ties must
    /// take the FIRST rather than the last.
    #[test]
    fn ties_keep_the_managers_ordering() {
        let sessions = [
            session("first", Status::Playing, false),
            session("second", Status::Playing, false),
        ];
        assert_eq!(choose(&sessions).unwrap().app_id, "first");
    }

    #[test]
    fn paused_only_still_shows_the_track() {
        let sessions = [session("Spotify", Status::Paused, true)];
        let snap = snapshot(&sessions);
        assert_eq!(snap.icon, Icon::Pause);
        assert!(!snap.playing);
        assert_eq!(snap.title, "Spotify title");
    }

    #[test]
    fn a_session_with_no_metadata_yet_is_not_idle_but_has_no_text() {
        let mut s = session("Spotify", Status::Playing, true);
        s.title = String::new();
        s.artist = String::new();
        let snap = snapshot(&[s]);
        assert_eq!(snap.icon, Icon::Play, "the icon still says something is on");
        assert!(!snap.is_idle(), "an icon alone is worth drawing");
        assert_eq!(snap.lines(), Some(("", "", Icon::Play)));
    }

    // -- timeline ---------------------------------------------------------

    fn playing_with(timeline: Timeline) -> Snapshot {
        let mut s = session("app", Status::Playing, true);
        s.timeline = Some(timeline);
        snapshot(&[s])
    }

    #[test]
    fn position_and_duration_are_relative_to_start() {
        let snap = playing_with(Timeline {
            start_ticks: 10 * TICKS_PER_SEC,
            end_ticks: 250 * TICKS_PER_SEC,
            position_ticks: 40 * TICKS_PER_SEC,
            age_s: None,
        });
        assert_eq!((snap.pos_s, snap.dur_s), (30, 240));
    }

    /// foobar2000 2.24.6 registers a session but reports 0s/0s.
    #[test]
    fn an_empty_timeline_reads_as_no_progress() {
        let snap = playing_with(Timeline {
            start_ticks: 0 * TICKS_PER_SEC,
            end_ticks: 0 * TICKS_PER_SEC,
            position_ticks: 0 * TICKS_PER_SEC,
            age_s: Some(1.0),
        });
        assert_eq!((snap.pos_s, snap.dur_s), (1, 0));
        assert_eq!(snap.playback(), (false, 0, 0), "no duration, no bar");
    }

    #[test]
    fn absent_timeline_is_not_an_error() {
        let snap = snapshot(&[session("app", Status::Playing, true)]);
        assert_eq!((snap.pos_s, snap.dur_s), (0, 0));
        assert_eq!(snap.playback(), (false, 0, 0));
    }

    /// SMTC updates on events, so a stale reading is extrapolated forward.
    #[test]
    fn a_stale_position_is_extrapolated_while_playing() {
        let snap = playing_with(Timeline {
            start_ticks: 0 * TICKS_PER_SEC,
            end_ticks: 300 * TICKS_PER_SEC,
            position_ticks: 100 * TICKS_PER_SEC,
            age_s: Some(4.7),
        });
        assert_eq!(snap.pos_s, 104, "4.7 s truncates to 4, not rounds to 5");
    }

    #[test]
    fn a_paused_position_is_never_extrapolated() {
        let mut s = session("app", Status::Paused, true);
        s.timeline = Some(Timeline {
            start_ticks: 0 * TICKS_PER_SEC,
            end_ticks: 300 * TICKS_PER_SEC,
            position_ticks: 100 * TICKS_PER_SEC,
            age_s: Some(120.0),
        });
        assert_eq!(snapshot(&[s]).pos_s, 100, "paused time does not pass");
    }

    /// Both ends of the gate. A negative age means the clocks disagree; a huge
    /// one means the timestamp is meaningless — a session reporting a zero
    /// LastUpdatedTime lands in 1601.
    #[test]
    fn an_implausible_age_is_not_trusted() {
        for age in [-0.1, -3600.0, 600.0, 1e9] {
            let snap = playing_with(Timeline {
                start_ticks: 0 * TICKS_PER_SEC,
                end_ticks: 300 * TICKS_PER_SEC,
                position_ticks: 100 * TICKS_PER_SEC,
                age_s: Some(age),
            });
            assert_eq!(snap.pos_s, 100, "age {age} must not be applied");
        }
        // ... and the boundaries that ARE trusted.
        for (age, want) in [(0.0, 100), (599.9, 699)] {
            let snap = playing_with(Timeline {
                start_ticks: 0 * TICKS_PER_SEC,
                end_ticks: 1000 * TICKS_PER_SEC,
                position_ticks: 100 * TICKS_PER_SEC,
                age_s: Some(age),
            });
            assert_eq!(snap.pos_s, want);
        }
    }

    #[test]
    fn extrapolation_cannot_run_past_the_end_of_the_track() {
        let snap = playing_with(Timeline {
            start_ticks: 0 * TICKS_PER_SEC,
            end_ticks: 120 * TICKS_PER_SEC,
            position_ticks: 118 * TICKS_PER_SEC,
            age_s: Some(30.0),
        });
        assert_eq!(snap.pos_s, 120, "clamped to the duration, not 148");
    }

    /// A seek backwards, or a session that reports a position before its own
    /// start. Negative is not a position.
    #[test]
    fn a_position_before_the_start_reads_as_zero() {
        let snap = playing_with(Timeline {
            start_ticks: 50 * TICKS_PER_SEC,
            end_ticks: 300 * TICKS_PER_SEC,
            position_ticks: 10 * TICKS_PER_SEC,
            age_s: None,
        });
        assert_eq!(snap.pos_s, 0);
    }

    #[test]
    fn a_backwards_timeline_has_no_duration() {
        let snap = playing_with(Timeline {
            start_ticks: 300 * TICKS_PER_SEC,
            end_ticks: 10 * TICKS_PER_SEC,
            position_ticks: 300 * TICKS_PER_SEC,
            age_s: None,
        });
        assert_eq!(snap.dur_s, 0);
    }

    /// Extreme tick values must saturate rather than overflow. `i64::MIN` is
    /// the interesting one: negating it panics in debug, and
    /// `MAX - MIN` overflows, so both differences go through `saturating_sub`.
    #[test]
    fn extreme_tick_values_are_survivable() {
        let snap = playing_with(Timeline {
            start_ticks: i64::MIN,
            end_ticks: i64::MAX,
            position_ticks: i64::MIN,
            age_s: Some(f64::NAN),
        });
        assert_eq!(snap.pos_s, 0, "position is at the start, so no progress");
        assert_eq!(snap.dur_s, u32::MAX, "an absurd duration clamps, not wraps");

        let snap = playing_with(Timeline {
            start_ticks: i64::MAX,
            end_ticks: i64::MIN,
            position_ticks: 0,
            age_s: None,
        });
        assert_eq!((snap.pos_s, snap.dur_s), (0, 0));
    }

    /// A NaN age must not be applied, and must not panic on the way to being
    /// rejected.
    #[test]
    fn a_nonsense_age_is_ignored() {
        for age in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let snap = playing_with(Timeline {
                start_ticks: 0,
                end_ticks: 300 * TICKS_PER_SEC,
                position_ticks: 100 * TICKS_PER_SEC,
                age_s: Some(age),
            });
            assert_eq!(snap.pos_s, 100, "age {age} must not move the position");
        }
    }

    /// ⚠️ The off-by-one the phase-1 audit found. Converting each endpoint to
    /// `f64` seconds and subtracting gives `244.99999999999997` for this
    /// perfectly ordinary track, which truncates to 244. Python subtracts
    /// `timedelta`s first, so it gets 245; integer ticks get 245 too.
    #[test]
    fn an_ordinary_track_does_not_lose_a_second_to_floating_point() {
        let start = 11_001_000 * 10; // 11.001 s, in ticks
        let snap = playing_with(Timeline {
            start_ticks: start,
            end_ticks: start + 245 * TICKS_PER_SEC,
            position_ticks: start,
            age_s: None,
        });
        assert_eq!(snap.dur_s, 245, "the float path gave 244 here");

        // And the float path really would have: keep the witness in the test
        // so a future "simplification" back to seconds fails rather than
        // silently losing a second again.
        let as_float = (start + 245 * TICKS_PER_SEC) as f64 / 1e7 - start as f64 / 1e7;
        assert_eq!(as_float.trunc() as u32, 244);
    }

    // -- what reaches the panel -------------------------------------------

    #[test]
    fn with_an_artist_it_takes_the_narrow_row() {
        let snap = Snapshot {
            icon: Icon::Play,
            artist: "Sigur Ros".into(),
            title: "Hoppipolla".into(),
            ..Default::default()
        };
        assert_eq!(snap.lines(), Some(("Sigur Ros", "Hoppipolla", Icon::Play)));
    }

    /// ⚠️ Row 1 is cleared explicitly, not just left alone — otherwise a
    /// previous artist sits under a new title.
    #[test]
    fn without_an_artist_the_title_moves_up_and_row_one_is_cleared() {
        let snap = Snapshot {
            icon: Icon::Play,
            title: "Some Podcast".into(),
            ..Default::default()
        };
        assert_eq!(snap.lines(), Some(("Some Podcast", "", Icon::Play)));

        let reports = reports(&snap);
        assert_eq!(reports.len(), 3);
        assert_eq!(reports[1].1, vec![1, 1], "row 1: line, icon, and no text");
    }

    #[test]
    fn idle_clears_the_band_and_hands_back_the_clock() {
        let reports = reports(&Snapshot::idle());
        assert_eq!(reports.len(), 2);
        assert_eq!(reports[0].0, crate::text::CLEAR);
        assert_eq!(reports[1].0, crate::text::PLAYBACK);
        assert_eq!(reports[1].1, vec![0, 0, 0, 0, 0]);
    }

    #[test]
    fn a_playing_track_sends_both_rows_then_the_bar() {
        let snap = Snapshot {
            icon: Icon::Play,
            artist: "A".into(),
            title: "B".into(),
            playing: true,
            pos_s: 61,
            dur_s: 245,
        };
        let reports = reports(&snap);
        assert_eq!(reports.len(), 3);
        assert_eq!(reports[0].1, vec![0, 1, b'A']);
        assert_eq!(reports[1].1, vec![1, 1, b'B']);
        assert_eq!(reports[2].1, vec![1, 0, 61, 0, 245]);
    }

    /// ⚠️ **Captured from this machine, 2026-09-06**, via `ak820 probe` — a
    /// real Apple Music session, paused mid-track. Worth pinning whole because
    /// it exercises four things at once that synthetic cases test separately:
    /// an em dash in real metadata, both line budgets biting, a paused icon,
    /// and a timeline whose reading is minutes stale.
    #[test]
    fn a_captured_apple_music_session_reaches_the_wire_intact() {
        let session = SessionFacts {
            app_id: "AppleInc.AppleMusicWin_nzyj5cx40ttqa!App".into(),
            status: Status::Paused,
            title: "Warriors of the Wasteland".into(),
            artist: "Michael Oakley \u{2014} Prologue".into(),
            timeline: Some(Timeline {
                start_ticks: 0,
                end_ticks: 235 * TICKS_PER_SEC,
                position_ticks: 187 * TICKS_PER_SEC,
                // 331.7 s: inside the 600 s trust window, so the ONLY reason it
                // is not applied is that the session is paused.
                age_s: Some(331.7),
            }),
            is_current: true,
        };
        let snap = snapshot(&[session]);
        assert_eq!(snap.icon, Icon::Pause);
        assert_eq!((snap.pos_s, snap.dur_s), (187, 235));
        assert_eq!(
            snap.playback(),
            (false, 0, 0),
            "paused: the band goes back to the clock"
        );

        let reports = reports(&snap);
        // The em dash transliterates to '-', and the artist fills row 0 exactly.
        assert_eq!(&reports[0].1[2..], b"Michael Oakley - Pr");
        assert_eq!(reports[0].1.len() - 2, Line::WithIcon.budget());
        // The title takes the wider row and is cut two characters later.
        assert_eq!(&reports[1].1[2..], b"Warriors of the Waste");
        assert_eq!(reports[1].1.len() - 2, Line::FullWidth.budget());
    }

    /// Position changing must not count as a text change, or the band would be
    /// rewritten every poll for nothing.
    #[test]
    fn position_alone_is_not_a_text_change() {
        let a = Snapshot {
            title: "T".into(),
            pos_s: 10,
            ..Default::default()
        };
        let b = Snapshot { pos_s: 99, ..a.clone() };
        assert!(!a.text_differs(&b));

        let c = Snapshot { title: "U".into(), ..a.clone() };
        assert!(a.text_differs(&c));
    }

    /// Unicode reaches this layer intact and is folded at the budget, not here
    /// — so a title is compared for change in its original form.
    #[test]
    fn snapshots_hold_unicode_and_fold_only_at_the_wire() {
        let snap = Snapshot {
            icon: Icon::Play,
            artist: "Bj\u{f6}rk".into(),
            title: "J\u{f3}ga".into(),
            ..Default::default()
        };
        let reports = reports(&snap);
        assert_eq!(reports[0].1, vec![0, 1, b'B', b'j', b'o', b'r', b'k']);
        assert_eq!(reports[1].1, vec![1, 1, b'J', b'o', b'g', b'a']);
    }
}
