//! One AppleScript question, bounded, with the denial surfaced.
//!
//! G-B, the one macOS defect this port closes: `nowplaying-macos.sh` sends
//! `osascript` stderr to `/dev/null`, so Automation consent revoked mid-run is
//! silent. Here stdout, stderr and the exit status come back separately and a
//! denial is its own outcome, never "nothing is playing".
//!
//! ⚠️ Bounded (review finding 4): the bash has no timeout at all, and an
//! AppleScript call to a hung app blocks forever.

use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::players::Player;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum State {
    Playing,
    Paused,
    Stopped,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Outcome {
    State(State),
    /// Automation consent is missing or was revoked: errAEEventNotPermitted (-1743).
    Denied(String),
    /// The call did not finish in time and was killed.
    TimedOut,
    /// Anything else: the text, for the log.
    Failed(String),
}

/// Classify one finished `osascript` run. Pure, so every denial shape is a test.
pub fn classify(status_ok: bool, stdout: &str, stderr: &str) -> Outcome {
    let err = stderr.trim();
    if err.contains("-1743")
        || err.contains("Not authorized")
        || err.contains("not allowed")
        || err.contains("not authorised")
    {
        return Outcome::Denied(err.to_owned());
    }
    if !status_ok {
        return Outcome::Failed(if err.is_empty() {
            "osascript failed with no stderr".into()
        } else {
            err.to_owned()
        });
    }
    match stdout.trim() {
        "playing" => Outcome::State(State::Playing),
        "paused" => Outcome::State(State::Paused),
        "stopped" => Outcome::State(State::Stopped),
        other => Outcome::Failed(format!("unexpected player state {other:?}")),
    }
}

/// How to run it; `program` is overridable so tests never send an Apple event.
#[derive(Clone, Debug)]
pub struct Asker {
    pub program: PathBuf,
    pub timeout: Duration,
}

impl Default for Asker {
    fn default() -> Self {
        Asker {
            program: "/usr/bin/osascript".into(),
            timeout: Duration::from_secs(5),
        }
    }
}

impl Asker {
    /// `player state` of a player **already known to be running** — the caller
    /// checks the process table first, because a `tell` launches the app.
    pub fn player_state(&self, player: Player) -> Outcome {
        let script = format!(
            "tell application \"{}\" to player state as string",
            player.app_name()
        );
        let mut child = match Command::new(&self.program)
            .args(["-e", &script])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => return Outcome::Failed(format!("spawn {}: {e}", self.program.display())),
        };
        let deadline = Instant::now() + self.timeout;
        let status = loop {
            match child.try_wait() {
                Ok(Some(s)) => break s,
                Ok(None) if Instant::now() >= deadline => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Outcome::TimedOut;
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => return Outcome::Failed(e.to_string()),
            }
        };
        let (mut out, mut err) = (String::new(), String::new());
        if let Some(mut o) = child.stdout.take() {
            let _ = o.read_to_string(&mut out);
        }
        if let Some(mut e) = child.stderr.take() {
            let _ = e.read_to_string(&mut err);
        }
        classify(status.success(), &out, &err)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_revoked_consent_is_a_denial_not_idle() {
        let err = "execution error: Not authorized to send Apple events to Music. (-1743)";
        assert!(matches!(classify(false, "", err), Outcome::Denied(_)));
        assert!(matches!(classify(true, "", "-1743"), Outcome::Denied(_)));
    }

    #[test]
    fn states_and_failures_are_distinct() {
        assert_eq!(
            classify(true, "playing\n", ""),
            Outcome::State(State::Playing)
        );
        assert_eq!(
            classify(true, "paused\n", ""),
            Outcome::State(State::Paused)
        );
        assert_eq!(
            classify(true, "stopped\n", ""),
            Outcome::State(State::Stopped)
        );
        assert!(matches!(
            classify(
                false,
                "",
                "execution error: Music got an error: Can't get player state. (-1728)"
            ),
            Outcome::Failed(_)
        ));
        assert!(matches!(classify(true, "", ""), Outcome::Failed(_)));
    }

    /// Bounded: a stand-in that never answers is killed at the timeout.
    #[test]
    fn a_hung_call_is_killed_at_the_timeout() {
        let dir = std::env::temp_dir().join(format!("s1b-hang-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let fake = dir.join("osascript");
        std::fs::write(&fake, "#!/bin/sh\nsleep 30\n").unwrap();
        std::process::Command::new("chmod")
            .args(["+x", fake.to_str().unwrap()])
            .status()
            .unwrap();
        let asker = Asker {
            program: fake,
            timeout: Duration::from_millis(300),
        };
        let started = Instant::now();
        assert_eq!(asker.player_state(Player::Music), Outcome::TimedOut);
        assert!(started.elapsed() < Duration::from_secs(3));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_denying_stand_in_surfaces_as_denied() {
        let dir = std::env::temp_dir().join(format!("s1b-deny-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let fake = dir.join("osascript");
        std::fs::write(&fake, "#!/bin/sh\necho 'execution error: Not authorized to send Apple events to Music. (-1743)' >&2\nexit 1\n").unwrap();
        std::process::Command::new("chmod")
            .args(["+x", fake.to_str().unwrap()])
            .status()
            .unwrap();
        let asker = Asker {
            program: fake,
            timeout: Duration::from_secs(5),
        };
        assert!(matches!(
            asker.player_state(Player::Music),
            Outcome::Denied(_)
        ));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
