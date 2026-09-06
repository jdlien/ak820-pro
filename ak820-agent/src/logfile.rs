//! A line-per-event log file, because the daemon has no console by
//! construction (`#![windows_subsystem = "windows"]`) and a crash it cannot
//! report is a crash nobody sees.
//!
//! Same shape as the Python agents' logs — `YYYY-MM-DD HH:MM:SS message` —
//! so `%LOCALAPPDATA%\ak820pro\` reads as one story across the migration.
//! Bounded: when the file passes [`ROTATE_AT`] it is renamed to `.1` and a
//! fresh one started, so a daemon that logs a warning every three seconds for
//! a month cannot fill a disk. Every failure to write is swallowed, as the
//! Python does: a log that can take the process down is worse than no log.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::clock::host::{Host, SystemHost};

/// Rotate once the file is this large.
pub const ROTATE_AT: u64 = 1_000_000;

pub struct Log {
    path: PathBuf,
}

impl Log {
    pub fn at(path: impl Into<PathBuf>) -> Log {
        Log { path: path.into() }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Append one timestamped line. Never fails visibly.
    pub fn line(&self, message: &str) {
        let _ = self.try_line(message);
    }

    fn try_line(&self, message: &str) -> std::io::Result<()> {
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        if std::fs::metadata(&self.path).map(|m| m.len() > ROTATE_AT).unwrap_or(false) {
            let mut rotated = self.path.clone().into_os_string();
            rotated.push(".1");
            // A rename can fail with the old `.1` open in a viewer; remove it
            // and try once more. If that fails too the bound is not held for
            // this file — the choice is between an oversized log and lost
            // lines, and lost lines are worse. Stated, not hidden.
            if std::fs::rename(&self.path, &rotated).is_err() {
                let _ = std::fs::remove_file(&rotated);
                let _ = std::fs::rename(&self.path, &rotated);
            }
        }
        let mut file = OpenOptions::new().create(true).append(true).open(&self.path)?;
        writeln!(file, "{} {message}", stamp(&SystemHost))
    }
}

/// `time.strftime('%Y-%m-%d %H:%M:%S')`, local time.
pub fn stamp(host: &impl Host) -> String {
    let now = host.now();
    let lt = host.local(now.trunc() as i64);
    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
        lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clock::host::FakeHost;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ak820-agent-log-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir.join("sub").join("agent.log")
    }

    #[test]
    fn the_stamp_is_the_pythons_strftime() {
        // 2026-08-29T11:06:41Z, a host at UTC
        let host = FakeHost::new(0, [1_787_961_600.0 + 40001.25]);
        assert_eq!(stamp(&host), "2026-08-29 11:06:41");
    }

    #[test]
    fn lines_are_appended_with_a_stamp_and_the_directory_is_created() {
        let log = Log::at(scratch("append"));
        log.line("first");
        log.line("second line");
        let text = std::fs::read_to_string(log.path()).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].ends_with(" first"), "{}", lines[0]);
        assert!(lines[1].ends_with(" second line"));
        // "YYYY-MM-DD HH:MM:SS " is 20 characters
        assert_eq!(lines[0].as_bytes()[4], b'-');
        assert_eq!(lines[0].as_bytes()[10], b' ');
        assert_eq!(lines[0].as_bytes()[13], b':');
        assert_eq!(lines[0].as_bytes()[19], b' ');
    }

    #[test]
    fn a_large_log_is_rotated_once_not_truncated() {
        let log = Log::at(scratch("rotate"));
        std::fs::create_dir_all(log.path().parent().unwrap()).unwrap();
        std::fs::write(log.path(), vec![b'x'; ROTATE_AT as usize + 1]).unwrap();
        log.line("after");
        let mut rotated = log.path().as_os_str().to_owned();
        rotated.push(".1");
        assert_eq!(std::fs::metadata(&rotated).unwrap().len(), ROTATE_AT + 1);
        let fresh = std::fs::read_to_string(log.path()).unwrap();
        assert_eq!(fresh.lines().count(), 1);
        assert!(fresh.ends_with(" after\n"));
    }

    #[test]
    fn an_unwritable_path_does_not_panic() {
        Log::at("Z:\\no\\such\\dir\\agent.log").line("lost, quietly");
    }
}
