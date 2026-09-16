//! The helper's messages, typed.
//!
//! Protocol source: `nowplaying-mediaremote.m` in ../streamdeck-now-playing.
//! ⚠️ **Built from captured output, not the header comment.** The header lists
//! `now`'s fields without `playing` or `elapsedAt`, and the helper sends both
//! (plan, Settled 2).

use crate::json::{self, Object};

/// What the helper says `now` is.
#[derive(Clone, Debug, PartialEq, Default)]
pub struct Now {
    /// Bundle id of the app that owns the session; `None` when nothing does.
    pub bundle: Option<String>,
    /// The owning app answered the client call but not the metadata call.
    pub stale: bool,
    pub playing: bool,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub album: Option<String>,
    /// Seconds.
    pub duration: Option<f64>,
    /// Seconds into the track, as of `elapsed_at`.
    pub elapsed: Option<f64>,
    /// Unix seconds at which `elapsed` was true, from the player's own clock.
    pub elapsed_at: Option<f64>,
    pub rate: Option<f64>,
    pub artwork: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Message {
    /// From the dylib's constructor, **before** its queue runs. Proves the
    /// process loaded, and nothing about whether MediaRemote answers.
    Hello {
        pid: Option<f64>,
    },
    Now(Now),
    /// Heartbeat, every 15 s, from the helper's serial queue: proof the queue
    /// is draining.
    Tick {
        seq: Option<f64>,
    },
    Command {
        name: String,
        accepted: bool,
    },
    /// The helper is about to exit, and says why.
    Fatal {
        error: String,
    },
    /// Artwork, sent only on request. The keyboard never requests it.
    Artwork,
    /// A well-formed message of a type this build does not know.
    Other {
        kind: Option<String>,
    },
}

impl Message {
    /// Does this line prove the helper's queue is still draining?
    ///
    /// ⚠️ `hello` does **not**. It is emitted from the constructor before the
    /// queue has run anything, so a helper crash-looping on a wedged
    /// MediaRemote sends one every restart. Counting it would reset the
    /// failure clock forever and leave a stale track refreshed on the panel
    /// indefinitely — the exact outcome the neutral failure policy exists to
    /// prevent. `fatal` does not either: it announces the end.
    pub fn proves_liveness(&self) -> bool {
        matches!(
            self,
            Message::Now(_) | Message::Tick { .. } | Message::Command { .. }
        )
    }
}

fn owned(o: &Object, key: &str) -> Option<String> {
    o.str(key).map(str::to_owned)
}

/// Read one line from the helper.
pub fn classify(line: &str) -> Result<Message, json::Error> {
    let o = json::parse_object(line)?;
    Ok(match o.str("type") {
        Some("hello") => Message::Hello { pid: o.num("pid") },
        Some("tick") => Message::Tick { seq: o.num("seq") },
        Some("fatal") => Message::Fatal {
            error: owned(&o, "error").unwrap_or_default(),
        },
        Some("command") => Message::Command {
            name: owned(&o, "name").unwrap_or_default(),
            accepted: o.flag("accepted").unwrap_or(false),
        },
        Some("artwork") => Message::Artwork,
        Some("now") => Message::Now(Now {
            bundle: owned(&o, "bundle"),
            stale: o.flag("stale").unwrap_or(false),
            playing: o.flag("playing").unwrap_or(false),
            title: owned(&o, "title"),
            artist: owned(&o, "artist"),
            album: owned(&o, "album"),
            duration: o.num("duration"),
            elapsed: o.num("elapsed"),
            elapsed_at: o.num("elapsedAt"),
            rate: o.num("rate"),
            artwork: owned(&o, "artwork"),
        }),
        other => Message::Other {
            kind: other.map(str::to_owned),
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_captured_now_types_every_field() {
        let m = classify(r#"{"album":"","stale":false,"elapsedAt":1789586100.2487299,"bundle":"com.google.Chrome","type":"now","title":"iPhone 18 Pro: A Photographer's Review","elapsed":0,"duration":948.14099999999996,"rate":1,"artist":"Tyler Stalman","artwork":"3d89751c57ab860a5adb8374cf27ebeae7752bb9","playing":true}"#).unwrap();
        let Message::Now(now) = m else {
            panic!("{m:?}")
        };
        assert_eq!(now.bundle.as_deref(), Some("com.google.Chrome"));
        assert!(now.playing && !now.stale);
        assert_eq!(
            now.title.as_deref(),
            Some("iPhone 18 Pro: A Photographer's Review")
        );
        assert_eq!(now.artist.as_deref(), Some("Tyler Stalman"));
        assert_eq!(now.album.as_deref(), Some(""));
        assert_eq!(
            (now.duration, now.elapsed, now.rate),
            (Some(948.141), Some(0.0), Some(1.0))
        );
        assert_eq!(now.elapsed_at, Some(1789586100.2487299));
    }

    #[test]
    fn idle_is_a_now_with_no_bundle() {
        let m = classify(r#"{"playing":false,"bundle":null,"type":"now","stale":false}"#).unwrap();
        assert_eq!(m, Message::Now(Now::default()));
    }

    #[test]
    fn only_queue_work_proves_liveness() {
        assert!(!classify(r#"{"type":"hello","pid":1}"#)
            .unwrap()
            .proves_liveness());
        assert!(!classify(r#"{"type":"fatal","error":"x"}"#)
            .unwrap()
            .proves_liveness());
        assert!(classify(r#"{"type":"tick","seq":3}"#)
            .unwrap()
            .proves_liveness());
        assert!(classify(r#"{"type":"now","bundle":null}"#)
            .unwrap()
            .proves_liveness());
        assert!(
            classify(r#"{"type":"command","name":"toggle","accepted":true}"#)
                .unwrap()
                .proves_liveness()
        );
        assert!(!classify(r#"{"type":"future"}"#).unwrap().proves_liveness());
    }
}
