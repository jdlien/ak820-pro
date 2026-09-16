//! S1b: noticing that MediaRemote has stopped answering, when the likeliest
//! shape of that is indistinguishable from "nothing is playing".
//!
//! If Apple extends the 15.4 refusal to perl, the helper stays alive, ticks,
//! and emits `bundle: null` forever. The canary cross-checks a null MediaRemote
//! against AppleScript's `player state`, and **only** under the limits the plan
//! settled (Efficiency row; review finding 4):
//!
//! - only while Spotify or Music is **running**, from the process table
//!   ([`super::players`]) — no spawn in the idle case, and no `tell` that
//!   would launch a player;
//! - at most once per 60 s, and never two at once — and the process table
//!   itself is read at most once per 60 s too (it costs ~2.7 ms), so a canary
//!   with nothing to ask costs nothing per poll;
//! - a switch to AppleScript needs the discrepancy **twice in a row**, and is
//!   **reversible**: the moment MediaRemote names a bundle again, it is primary
//!   again.
//!
//! ⚠️ One known false positive to verify with the owner before trusting the
//! switch: **Spotify Connect**. Spotify can say `playing` while the audio plays
//! on another device, and MediaRemote then rightly reports nothing here.
//!
//! Pure: the caller supplies the facts and the clock, and runs the question.

use std::time::{Duration, Instant};

use super::applescript::{Outcome, State};
use super::players::Player;

pub const MIN_GAP: Duration = Duration::from_secs(60);
pub const CONFIRM: u32 = 2;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Primary {
    MediaRemote,
    AppleScript(Player),
}

#[derive(Debug, PartialEq, Eq)]
pub enum Decision {
    Nothing,
    Ask(Player),
}

/// Things worth a log line and a status-file field.
#[derive(Debug, PartialEq, Eq)]
pub enum Note {
    /// MediaRemote null while a player says playing, `CONFIRM` times running.
    SwitchedToAppleScript { player: Player },
    /// MediaRemote named a bundle again.
    RestoredMediaRemote,
    /// G-B: the Automation consent is missing or revoked. Surfaced, never
    /// collapsed into idle.
    Denied { player: Player, detail: String },
    Failed { player: Player, detail: String },
}

#[derive(Debug)]
pub struct Canary {
    primary: Primary,
    last_checked: Option<Instant>,
    in_flight: Option<Player>,
    streak: u32,
}

impl Default for Canary {
    fn default() -> Self {
        Canary { primary: Primary::MediaRemote, last_checked: None, in_flight: None, streak: 0 }
    }
}

impl Canary {
    pub fn primary(&self) -> Primary {
        self.primary
    }

    /// Called every poll. `mr_has_bundle` is whether the latest `now` named an
    /// owner; `running` reads the process table, and is called at most once
    /// per [`MIN_GAP`].
    pub fn step(
        &mut self,
        mr_has_bundle: bool,
        now: Instant,
        running: impl FnOnce() -> Vec<Player>,
    ) -> (Decision, Option<Note>) {
        if mr_has_bundle {
            self.streak = 0;
            if self.primary != Primary::MediaRemote {
                self.primary = Primary::MediaRemote;
                return (Decision::Nothing, Some(Note::RestoredMediaRemote));
            }
            return (Decision::Nothing, None);
        }
        // Already switched: the fallback is reading the player every poll, and
        // only a bundle from MediaRemote switches back, so there is nothing
        // left to ask.
        if self.primary != Primary::MediaRemote {
            return (Decision::Nothing, None);
        }
        if self.in_flight.is_some() || self.last_checked.is_some_and(|t| now.saturating_duration_since(t) < MIN_GAP) {
            return (Decision::Nothing, None);
        }
        self.last_checked = Some(now);
        let Some(&player) = running().first() else {
            // Nothing scriptable is running: nothing to cross-check, no spawn.
            self.streak = 0;
            return (Decision::Nothing, None);
        };
        self.in_flight = Some(player);
        (Decision::Ask(player), None)
    }

    /// The answer to the question `step` asked.
    pub fn answered(&mut self, player: Player, outcome: Outcome) -> Option<Note> {
        if self.in_flight != Some(player) {
            return None; // not the question we asked
        }
        self.in_flight = None;
        match outcome {
            Outcome::State(State::Playing) => {
                self.streak += 1;
                if self.streak >= CONFIRM && self.primary == Primary::MediaRemote {
                    self.primary = Primary::AppleScript(player);
                    return Some(Note::SwitchedToAppleScript { player });
                }
                None
            }
            Outcome::State(_) => {
                self.streak = 0; // paused or stopped agrees with a null MediaRemote
                None
            }
            Outcome::Denied(detail) => Some(Note::Denied { player, detail }),
            Outcome::TimedOut => Some(Note::Failed { player, detail: "timed out".into() }),
            Outcome::Failed(detail) => Some(Note::Failed { player, detail }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    const M: Player = Player::Music;
    const POLL: Duration = Duration::from_secs(3);

    /// Idle with nothing running: never asks, and reads the process table at
    /// most once a minute however often it is polled.
    #[test]
    fn idle_never_asks_and_rarely_scans() {
        let mut c = Canary::default();
        let t = Instant::now();
        let scans = Cell::new(0);
        for i in 0..100 {
            let (d, n) = c.step(false, t + POLL * i, || {
                scans.set(scans.get() + 1);
                Vec::new()
            });
            assert_eq!((d, n), (Decision::Nothing, None));
        }
        // 100 polls x 3 s = 300 s: one scan per 60 s
        assert!(scans.get() <= 6, "scanned {} times", scans.get());
    }

    #[test]
    fn a_healthy_mediaremote_never_asks_or_scans() {
        let mut c = Canary::default();
        let t = Instant::now();
        let scanned = Cell::new(false);
        assert_eq!(c.step(true, t, || { scanned.set(true); vec![M] }), (Decision::Nothing, None));
        assert!(!scanned.get());
    }

    #[test]
    fn asks_at_most_once_a_minute_and_never_overlaps() {
        let mut c = Canary::default();
        let t = Instant::now();
        assert_eq!(c.step(false, t, || vec![M]).0, Decision::Ask(M));
        assert_eq!(c.step(false, t + MIN_GAP * 3, || vec![M]).0, Decision::Nothing, "still in flight");
        c.answered(M, Outcome::State(State::Paused));
        assert_eq!(c.step(false, t + MIN_GAP * 3, || vec![M]).0, Decision::Ask(M));
        c.answered(M, Outcome::State(State::Paused));
        assert_eq!(c.step(false, t + MIN_GAP * 3 + Duration::from_secs(59), || vec![M]).0, Decision::Nothing);
    }

    #[test]
    fn a_refusal_switches_after_two_and_restores_the_moment_mediaremote_answers() {
        let mut c = Canary::default();
        let t = Instant::now();
        assert_eq!(c.step(false, t, || vec![M]).0, Decision::Ask(M));
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
        assert_eq!(c.primary(), Primary::MediaRemote, "one discrepancy is not enough");
        assert_eq!(c.step(false, t + MIN_GAP, || vec![M]).0, Decision::Ask(M));
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), Some(Note::SwitchedToAppleScript { player: M }));
        assert_eq!(c.primary(), Primary::AppleScript(M));
        assert_eq!(c.step(true, t + MIN_GAP * 2, || vec![M]), (Decision::Nothing, Some(Note::RestoredMediaRemote)));
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    #[test]
    fn once_switched_it_asks_nothing_more() {
        let mut c = Canary::default();
        let t = Instant::now();
        for i in 0..2 {
            c.step(false, t + MIN_GAP * i, || vec![M]);
            c.answered(M, Outcome::State(State::Playing));
        }
        assert_eq!(c.primary(), Primary::AppleScript(M));
        let scanned = Cell::new(false);
        assert_eq!(c.step(false, t + MIN_GAP * 5, || { scanned.set(true); vec![M] }), (Decision::Nothing, None));
        assert!(!scanned.get());
    }

    #[test]
    fn a_pause_between_discrepancies_resets_the_streak() {
        let mut c = Canary::default();
        let t = Instant::now();
        c.step(false, t, || vec![M]);
        c.answered(M, Outcome::State(State::Playing));
        c.step(false, t + MIN_GAP, || vec![M]);
        c.answered(M, Outcome::State(State::Stopped));
        c.step(false, t + MIN_GAP * 2, || vec![M]);
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    #[test]
    fn a_denial_is_surfaced_and_does_not_switch() {
        let mut c = Canary::default();
        c.step(false, Instant::now(), || vec![M]);
        let note = c.answered(M, Outcome::Denied("Not authorized (-1743)".into()));
        assert!(matches!(note, Some(Note::Denied { player: Player::Music, .. })));
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    #[test]
    fn an_answer_to_a_question_not_asked_is_ignored() {
        let mut c = Canary::default();
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
    }
}
