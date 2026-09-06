//! The daemon's status file: what it last did, for a reader who can see only
//! that the task is "Running".
//!
//! The backlog records thirteen minutes of missed clock syncs on 2026-09-05
//! during which the Scheduled Task reported Running throughout. Liveness is
//! not health. So the daemon writes this small file atomically every cycle
//! — `key=value` lines, nothing to parse but `=` — and `ak820 status` prints
//! it next to the tasks' states. If the daemon dies, `updated` stops moving,
//! which is the whole point.

use std::path::{Path, PathBuf};

/// One cycle's worth of "what am I doing".
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Status {
    pub version: String,
    pub started: String,
    pub updated: String,
    /// The presence state machine's current state, as a word.
    pub board: String,
    pub media_last_push: Option<String>,
    pub media_last_text: Option<String>,
    pub media_last_error: Option<String>,
    pub smtc_polls: u64,
    pub smtc_failures: u64,
    pub smtc_last_error: Option<String>,
    /// Reports that arrived on our handle and answered someone else — the
    /// only direct evidence of another process talking to the board.
    pub foreign_reports: u64,
}

/// The file's text. One value per line; an absent value is an absent line.
pub fn render(s: &Status) -> String {
    let mut out = String::new();
    let mut put = |k: &str, v: &str| {
        out.push_str(k);
        out.push('=');
        // a value with a newline would forge a line; flatten it
        out.push_str(&v.replace(['\r', '\n'], " "));
        out.push('\n');
    };
    put("version", &s.version);
    put("started", &s.started);
    put("updated", &s.updated);
    put("board", &s.board);
    if let Some(v) = &s.media_last_push {
        put("media_last_push", v);
    }
    if let Some(v) = &s.media_last_text {
        put("media_last_text", v);
    }
    if let Some(v) = &s.media_last_error {
        put("media_last_error", v);
    }
    put("smtc_polls", &s.smtc_polls.to_string());
    put("smtc_failures", &s.smtc_failures.to_string());
    if let Some(v) = &s.smtc_last_error {
        put("smtc_last_error", v);
    }
    put("foreign_reports", &s.foreign_reports.to_string());
    out
}

/// Write atomically: a temporary beside it, then a rename, so a reader never
/// sees half a file.
pub fn write(path: &Path, s: &Status) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".tmp");
    let tmp = PathBuf::from(tmp);
    std::fs::write(&tmp, render(s))?;
    std::fs::rename(&tmp, path)
}

/// The file as `(key, value)` pairs, in order. `None` if it is not there.
pub fn read(path: &Path) -> Option<Vec<(String, String)>> {
    let text = std::fs::read_to_string(path).ok()?;
    Some(
        text.lines()
            .filter_map(|l| l.split_once('='))
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Status {
        Status {
            version: "ak820-agent 0.1.0 (v0.1.0)".into(),
            started: "2026-09-06 08:00:00".into(),
            updated: "2026-09-06 08:00:03".into(),
            board: "present".into(),
            media_last_push: Some("2026-09-06 08:00:03".into()),
            media_last_text: Some("play  Artist - Title".into()),
            media_last_error: None,
            smtc_polls: 2,
            smtc_failures: 0,
            smtc_last_error: None,
            foreign_reports: 0,
        }
    }

    #[test]
    fn renders_one_value_per_line_and_omits_absent_ones() {
        let text = render(&sample());
        assert_eq!(
            text,
            "version=ak820-agent 0.1.0 (v0.1.0)\nstarted=2026-09-06 08:00:00\nupdated=2026-09-06 08:00:03\nboard=present\nmedia_last_push=2026-09-06 08:00:03\nmedia_last_text=play  Artist - Title\nsmtc_polls=2\nsmtc_failures=0\nforeign_reports=0\n"
        );
    }

    #[test]
    fn a_newline_in_a_value_cannot_forge_a_line() {
        let mut s = sample();
        s.media_last_error = Some("two\nlines\r\n".into());
        let text = render(&s);
        assert!(text.contains("media_last_error=two lines  \n"));
        assert_eq!(text.lines().count(), 10);
    }

    #[test]
    fn writes_atomically_and_reads_back() {
        let dir = std::env::temp_dir().join(format!("ak820-agent-status-{}", std::process::id()));
        let path = dir.join("agent.status");
        write(&path, &sample()).unwrap();
        let pairs = read(&path).unwrap();
        assert_eq!(pairs[0], ("version".to_string(), "ak820-agent 0.1.0 (v0.1.0)".to_string()));
        assert_eq!(pairs.len(), 9);
        let mut tmp = path.as_os_str().to_owned();
        tmp.push(".tmp");
        assert!(!Path::new(&tmp).exists());
        assert_eq!(read(&dir.join("absent")), None);
    }
}
