//! S1b: noticing that MediaRemote has stopped answering, when the likeliest
//! shape of that is indistinguishable from "nothing is playing".
//!
//! If Apple extends the 15.4 refusal to perl, the helper stays alive, ticks,
//! and emits `bundle: null` forever. The canary cross-checks a null MediaRemote
//! against AppleScript's `player state`, and **only** under the limits the plan
//! settled (Efficiency row; review finding 4):
//!
//! - only while Spotify or Music is **running**, from the process table
//!   ([`crate::players`]) — no spawn in the idle case, and no `tell` that
//!   would launch a player;
//! - at most once per 60 s, and never two at once;
//! - a switch to AppleScript needs the discrepancy **twice in a row**, and is
//!   **reversible**: the moment MediaRemote names a bundle again, it is primary
//!   again.
//!
//! ⚠️ One known false positive to verify with the owner before trusting the
//! switch: **Spotify Connect**. Spotify can say `playing` while the audio plays
//! on another device, and MediaRemote then rightly reports nothing here. The
//! log line says so rather than asserting a refusal.
//!
//! Pure: the caller supplies the facts and the clock, and runs the question.

use std::time::{Duration, Instant};

use crate::applescript::{Outcome, State};
use crate::players::Player;

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

/// Things worth a log line and a status-file key.
#[derive(Debug, PartialEq, Eq)]
pub enum Note {
    /// MediaRemote null while a player says playing, `CONFIRM` times running.
    SwitchedToAppleScript {
        player: Player,
    },
    /// MediaRemote named a bundle again.
    RestoredMediaRemote,
    /// G-B: the Automation consent is missing or revoked. Surfaced, never
    /// collapsed into idle.
    Denied {
        player: Player,
        detail: String,
    },
    Failed {
        player: Player,
        detail: String,
    },
}

#[derive(Debug)]
pub struct Canary {
    primary: Primary,
    last_asked: Option<Instant>,
    in_flight: Option<Player>,
    streak: u32,
}

impl Default for Canary {
    fn default() -> Self {
        Canary {
            primary: Primary::MediaRemote,
            last_asked: None,
            in_flight: None,
            streak: 0,
        }
    }
}

impl Canary {
    pub fn primary(&self) -> Primary {
        self.primary
    }

    /// Called whenever MediaRemote's view or the process table may have
    /// changed. `mr_has_bundle` is whether the latest `now` named an owner.
    pub fn step(
        &mut self,
        mr_has_bundle: bool,
        running: &[Player],
        now: Instant,
    ) -> (Decision, Option<Note>) {
        if mr_has_bundle {
            self.streak = 0;
            if self.primary != Primary::MediaRemote {
                self.primary = Primary::MediaRemote;
                return (Decision::Nothing, Some(Note::RestoredMediaRemote));
            }
            return (Decision::Nothing, None);
        }
        let Some(&player) = running.first() else {
            // Nothing scriptable is running: nothing to cross-check, and no
            // spawn. A null MediaRemote is simply idle here.
            self.streak = 0;
            return (Decision::Nothing, None);
        };
        if self.in_flight.is_some()
            || self
                .last_asked
                .is_some_and(|t| now.saturating_duration_since(t) < MIN_GAP)
        {
            return (Decision::Nothing, None);
        }
        self.in_flight = Some(player);
        self.last_asked = Some(now);
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
            Outcome::TimedOut => Some(Note::Failed {
                player,
                detail: "timed out".into(),
            }),
            Outcome::Failed(detail) => Some(Note::Failed { player, detail }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const M: Player = Player::Music;

    #[test]
    fn idle_with_no_player_running_never_asks() {
        let mut c = Canary::default();
        let t = Instant::now();
        for i in 0..100 {
            assert_eq!(
                c.step(false, &[], t + Duration::from_secs(i * 3)),
                (Decision::Nothing, None)
            );
        }
    }

    #[test]
    fn a_healthy_mediaremote_never_asks() {
        let mut c = Canary::default();
        let t = Instant::now();
        assert_eq!(c.step(true, &[M], t), (Decision::Nothing, None));
        assert_eq!(
            c.step(true, &[M], t + MIN_GAP * 2),
            (Decision::Nothing, None)
        );
    }

    #[test]
    fn asks_at_most_once_a_minute_and_never_overlaps() {
        let mut c = Canary::default();
        let t = Instant::now();
        assert_eq!(c.step(false, &[M], t).0, Decision::Ask(M));
        // still in flight: no second question, however much time passes
        assert_eq!(c.step(false, &[M], t + MIN_GAP * 3).0, Decision::Nothing);
        c.answered(M, Outcome::State(State::Paused));
        assert_eq!(c.step(false, &[M], t + MIN_GAP * 3).0, Decision::Ask(M));
        c.answered(M, Outcome::State(State::Paused));
        assert_eq!(
            c.step(false, &[M], t + MIN_GAP * 3 + Duration::from_secs(59))
                .0,
            Decision::Nothing
        );
    }

    #[test]
    fn a_refusal_switches_after_two_and_restores_the_moment_mediaremote_answers() {
        let mut c = Canary::default();
        let t = Instant::now();
        assert_eq!(c.step(false, &[M], t).0, Decision::Ask(M));
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
        assert_eq!(
            c.primary(),
            Primary::MediaRemote,
            "one discrepancy is not enough"
        );
        assert_eq!(c.step(false, &[M], t + MIN_GAP).0, Decision::Ask(M));
        assert_eq!(
            c.answered(M, Outcome::State(State::Playing)),
            Some(Note::SwitchedToAppleScript { player: M })
        );
        assert_eq!(c.primary(), Primary::AppleScript(M));
        assert_eq!(
            c.step(true, &[M], t + MIN_GAP * 2),
            (Decision::Nothing, Some(Note::RestoredMediaRemote))
        );
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    #[test]
    fn a_pause_between_discrepancies_resets_the_streak() {
        let mut c = Canary::default();
        let t = Instant::now();
        c.step(false, &[M], t);
        c.answered(M, Outcome::State(State::Playing));
        c.step(false, &[M], t + MIN_GAP);
        c.answered(M, Outcome::State(State::Stopped));
        c.step(false, &[M], t + MIN_GAP * 2);
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    /// G-B: a denial is surfaced as a note, never read as idle or as playing.
    #[test]
    fn a_denial_is_surfaced_and_does_not_switch() {
        let mut c = Canary::default();
        let t = Instant::now();
        c.step(false, &[M], t);
        let note = c.answered(M, Outcome::Denied("Not authorized (-1743)".into()));
        assert!(matches!(
            note,
            Some(Note::Denied {
                player: Player::Music,
                ..
            })
        ));
        assert_eq!(c.primary(), Primary::MediaRemote);
    }

    #[test]
    fn an_answer_to_a_question_not_asked_is_ignored() {
        let mut c = Canary::default();
        assert_eq!(c.answered(M, Outcome::State(State::Playing)), None);
    }
}
