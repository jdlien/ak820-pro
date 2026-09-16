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

use super::message::Now;
use super::players::Player;

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

/// Is this stderr the Automation consent refusal?
fn is_denial(stderr: &str) -> bool {
    stderr.contains("-1743")
        || stderr.contains("Not authorized")
        || stderr.contains("not allowed")
        || stderr.contains("not authorised")
}

/// Classify one finished `osascript` run. Pure, so every denial shape is a test.
pub fn classify(status_ok: bool, stdout: &str, stderr: &str) -> Outcome {
    let err = stderr.trim();
    if is_denial(err) {
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
        // "notrunning": the guard found it gone, which agrees with a null
        // MediaRemote exactly as stopped does.
        "stopped" | "notrunning" => Outcome::State(State::Stopped),
        other => Outcome::Failed(format!("unexpected player state {other:?}")),
    }
}

/// What the fallback read found.
#[derive(Clone, Debug, PartialEq)]
pub enum Reading {
    /// A playing or paused track, as a `now` the router's snapshot rules read.
    Track(Now),
    /// No asked player is playing or paused.
    Nothing,
    Denied(String),
    TimedOut,
    Failed(String),
}

/// Field separator in the script's reply: the unit separator, which no title
/// carries, where anything typographic might (the sibling's choice).
const US: char = '\u{1f}';

/// One script that reads every given player, **each guarded on already
/// running**, and answers with the first that is playing, else the first that
/// is paused, else `none`.
///
/// ⚠️ Only players the process table found running may be named here. A
/// guarded `tell` does not launch a player, but compiling a `tell` to an app
/// that is **not installed** raises a "Where is Spotify?" dialog, which is the
/// same class of desktop surprise as the quarantine one S3 found.
///
/// Playing ranks above paused, as SMTC's ranking does on Windows. The bash
/// agent took the first player that was playing *or* paused, so a paused
/// Spotify hid a playing Music; that was an accident of its loop, not a rule.
pub fn track_script(players: &[Player]) -> String {
    let mut s = String::from(
        "on txt(v)\n\tif v is missing value then return \"\"\n\treturn v as text\nend txt\n\
         set US to character id 31\nset pausedOut to \"none\"\n",
    );
    for p in players {
        let app = p.app_name();
        s.push_str(&format!(
            "if application \"{app}\" is running then\n\
             \ttell application \"{app}\"\n\
             \t\tset st to player state as text\n\
             \t\tif st is \"playing\" or st is \"paused\" then\n\
             \t\t\tset t to current track\n\
             \t\t\tset out to \"{app}\" & US & st & US & my txt(name of t) & US & my txt(artist of t) & US & my txt(album of t) & US & my txt(player position) & US & my txt(duration of t)\n\
             \t\t\tif st is \"playing\" then return out\n\
             \t\t\tif pausedOut is \"none\" then set pausedOut to out\n\
             \t\tend if\n\
             \tend tell\n\
             end if\n"
        ));
    }
    s.push_str("return pausedOut\n");
    s
}

/// A number as AppleScript's `as text` wrote it, in either decimal convention:
/// a locale with a decimal comma writes `12,5`.
fn number(field: &str) -> Option<f64> {
    let v: f64 = field.trim().replace(',', ".").parse().ok()?;
    v.is_finite().then_some(v)
}

/// Read the script's reply. `read_at` is the wall clock (Unix seconds) when it
/// finished, which is what the position was true as of, near enough: the
/// spawn's latency is tens of milliseconds, and the readout shows seconds.
pub fn parse_track(stdout: &str, read_at: f64) -> Result<Option<Now>, String> {
    let line = stdout.trim_end_matches(['\n', '\r']);
    if line == "none" {
        return Ok(None);
    }
    let f: Vec<&str> = line.split(US).collect();
    if f.len() != 7 {
        return Err(format!("unexpected reply: {} fields", f.len()));
    }
    let player = match f[0] {
        "Music" => Player::Music,
        "Spotify" => Player::Spotify,
        other => return Err(format!("unexpected player {other:?}")),
    };
    let playing = match f[1] {
        "playing" => true,
        "paused" => false,
        other => return Err(format!("unexpected player state {other:?}")),
    };
    // ⚠️ UNITS DIFFER BY APP: Music reports duration in seconds, Spotify in
    // MILLISECONDS (nowplaying-macos.sh:75-84). Getting it wrong shows a
    // three-minute track as three seconds, which looks like a firmware bug.
    let duration = number(f[6]).map(|d| match player {
        Player::Spotify => d / 1000.0,
        Player::Music => d,
    });
    Ok(Some(Now {
        bundle: Some(player.bundle().into()),
        stale: false,
        playing,
        title: Some(f[2].into()),
        artist: Some(f[3].into()),
        album: Some(f[4].into()),
        duration,
        elapsed: number(f[5]),
        elapsed_at: Some(read_at),
        rate: Some(if playing { 1.0 } else { 0.0 }),
        artwork: None,
    }))
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

enum Ran {
    Finished { ok: bool, stdout: String, stderr: String },
    TimedOut,
    Failed(String),
}

impl Asker {
    /// `player state` of a player the process table says is running.
    ///
    /// ⚠️ Guarded all the same (audit F6): the table read and this call are
    /// moments apart, and an unguarded `tell` to a player that quit in between
    /// launches it again.
    pub fn player_state(&self, player: Player) -> Outcome {
        let app = player.app_name();
        let script = format!(
            "if application \"{app}\" is not running then return \"notrunning\"\ntell application \"{app}\" to return player state as string"
        );
        match self.run(&script) {
            Ran::Finished { ok, stdout, stderr } => classify(ok, &stdout, &stderr),
            Ran::TimedOut => Outcome::TimedOut,
            Ran::Failed(e) => Outcome::Failed(e),
        }
    }

    /// The fallback read: [`track_script`] over players known to be running.
    pub fn track(&self, players: &[Player]) -> Reading {
        match self.run(&track_script(players)) {
            Ran::Finished { stderr, .. } if is_denial(&stderr) => Reading::Denied(stderr.trim().to_owned()),
            Ran::Finished { ok: false, stderr, .. } => Reading::Failed(match stderr.trim() {
                "" => "osascript failed with no stderr".into(),
                e => e.to_owned(),
            }),
            Ran::Finished { ok: true, stdout, .. } => match parse_track(&stdout, wall_now()) {
                Ok(Some(now)) => Reading::Track(now),
                Ok(None) => Reading::Nothing,
                Err(e) => Reading::Failed(e),
            },
            Ran::TimedOut => Reading::TimedOut,
            Ran::Failed(e) => Reading::Failed(e),
        }
    }

    /// Run one script, killed at the timeout. stdout and stderr are drained on
    /// their own threads, so a chatty script cannot fill a pipe and hang.
    fn run(&self, script: &str) -> Ran {
        let mut child = match Command::new(&self.program)
            .args(["-e", script])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => return Ran::Failed(format!("spawn {}: {e}", self.program.display())),
        };
        let drain = |pipe: Option<Box<dyn Read + Send>>| {
            std::thread::spawn(move || {
                let mut text = String::new();
                if let Some(mut p) = pipe {
                    let _ = p.read_to_string(&mut text);
                }
                text
            })
        };
        let out = drain(child.stdout.take().map(|p| Box::new(p) as Box<dyn Read + Send>));
        let err = drain(child.stderr.take().map(|p| Box::new(p) as Box<dyn Read + Send>));
        let deadline = Instant::now() + self.timeout;
        let status = loop {
            match child.try_wait() {
                Ok(Some(s)) => break s,
                Ok(None) if Instant::now() >= deadline => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Ran::TimedOut;
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => return Ran::Failed(e.to_string()),
            }
        };
        Ran::Finished {
            ok: status.success(),
            stdout: out.join().unwrap_or_default(),
            stderr: err.join().unwrap_or_default(),
        }
    }
}

/// Unix seconds, as `elapsedAt` carries them.
pub fn wall_now() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
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
    fn a_player_gone_by_the_time_it_is_asked_reads_as_stopped() {
        assert_eq!(classify(true, "notrunning\n", ""), Outcome::State(State::Stopped));
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

    #[test]
    fn the_script_names_only_the_players_it_is_given_each_guarded() {
        let s = track_script(&[Player::Music]);
        assert!(s.contains("if application \"Music\" is running then"));
        assert!(!s.contains("Spotify"), "an app that is not running must not be compiled against");
        let both = track_script(&[Player::Spotify, Player::Music]);
        assert!(both.find("\"Spotify\"").unwrap() < both.find("\"Music\"").unwrap());
        assert_eq!(both.matches("is running then").count(), 2);
    }

    #[test]
    fn a_spotify_duration_is_milliseconds_and_musics_is_seconds() {
        let us = "\u{1f}";
        let sp = format!("Spotify{us}playing{us}Title{us}Artist{us}Album{us}12.5{us}244000\n");
        let n = parse_track(&sp, 1_000.0).unwrap().unwrap();
        assert_eq!((n.bundle.as_deref(), n.duration, n.elapsed, n.rate), (Some("com.spotify.client"), Some(244.0), Some(12.5), Some(1.0)));
        let mu = format!("Music{us}paused{us}T{us}A{us}B{us}12,5{us}244.8\n");
        let n = parse_track(&mu, 1_000.0).unwrap().unwrap();
        assert_eq!((n.bundle.as_deref(), n.duration, n.elapsed, n.playing), (Some("com.apple.Music"), Some(244.8), Some(12.5), false));
        assert_eq!(n.elapsed_at, Some(1_000.0));
    }

    #[test]
    fn nothing_and_malformed_replies_are_distinct() {
        assert_eq!(parse_track("none\n", 0.0), Ok(None));
        assert!(parse_track("Music\u{1f}playing\u{1f}T", 0.0).is_err());
        assert!(parse_track("", 0.0).is_err());
    }

    /// Empty fields survive the split: an ad with no artist is still a track.
    #[test]
    fn empty_fields_are_kept() {
        let us = "\u{1f}";
        let n = parse_track(&format!("Spotify{us}playing{us}Advertisement{us}{us}{us}0{us}"), 0.0).unwrap().unwrap();
        assert_eq!((n.artist.as_deref(), n.duration), (Some(""), None));
    }

    fn stand_in(name: &str, body: &str) -> (PathBuf, PathBuf) {
        let dir = std::env::temp_dir().join(format!("ak820-as-{name}-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let fake = dir.join("osascript");
        std::fs::write(&fake, body).unwrap();
        std::process::Command::new("chmod").args(["+x", fake.to_str().unwrap()]).status().unwrap();
        (dir, fake)
    }

    #[test]
    fn the_track_read_goes_through_a_stand_in_and_surfaces_denial() {
        let (dir, fake) = stand_in("track", "#!/bin/sh\nprintf 'Music\\037playing\\037T\\037A\\037B\\0373\\037200\\n'\n");
        let asker = Asker { program: fake, timeout: Duration::from_secs(5) };
        assert!(matches!(asker.track(&[Player::Music]), Reading::Track(n) if n.title.as_deref() == Some("T")));
        let _ = std::fs::remove_dir_all(&dir);

        let (dir, fake) = stand_in("tdeny", "#!/bin/sh\necho 'execution error: Not authorized to send Apple events to Music. (-1743)' >&2\nexit 1\n");
        let asker = Asker { program: fake, timeout: Duration::from_secs(5) };
        assert!(matches!(asker.track(&[Player::Music]), Reading::Denied(_)));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
