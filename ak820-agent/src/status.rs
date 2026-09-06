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
    /// Seconds since the media snapshot last refreshed; absent before the
    /// first successful poll. Large while `smtc_last_error` is set.
    pub smtc_stale_s: Option<u64>,
    /// Reports that arrived on our handle **while a request was waiting** and
    /// answered someone else — the only direct evidence of another process
    /// talking to the board. Stale reports queued before we asked are not
    /// counted: they are ours from an earlier request as often as not.
    pub foreign_reports: u64,
    /// The clock loop's state, when the daemon runs it (`--clock`).
    pub clock: Option<ClockStatus>,
    /// The firmware's own health counters, read every few minutes: whether
    /// the board is stalling, from the board's point of view.
    pub health: Option<HealthStatus>,
}

/// Health pages 1 and 2, the counters that decide "is the firmware even
/// involved" — `Fn`+`D` on the LCD, `ak820 health` at the terminal, and here
/// so the takeover gate can compare stalls before and after the daemon took
/// the clock.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HealthStatus {
    pub read_at: String,
    pub version: u8,
    pub loop_gap_max_ms: u32,
    pub loop_gap_max_mark: String,
    /// Stalls of 25 ms or more — the threshold below which a press cannot be
    /// lost. Must be 0 on everyday firmware.
    pub count_ge_25ms: u32,
    pub count_ge_25ms_nonflash: u16,
    pub count_ge_10ms: u32,
    pub blit_timeouts: u32,
    pub tx_timeouts: u32,
    pub wdt_consecutive_resets: u8,
}

/// What the clock loop last did — the readout the backlog asked for after
/// "Running" hid thirteen minutes of missed syncs.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ClockStatus {
    pub syncs: u64,
    pub failures: u64,
    pub last_sync: Option<String>,
    /// The log line of the last sync attempt, success or failure.
    pub last_line: Option<String>,
    pub interval_s: u64,
    /// The cache as last read: `lead_ms` to three decimals, and the bias.
    pub lead_ms: String,
    pub bias_ppm: Option<i32>,
    pub last_error: Option<String>,
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
    if let Some(v) = s.smtc_stale_s {
        put("smtc_stale_s", &v.to_string());
    }
    put("foreign_reports", &s.foreign_reports.to_string());
    if let Some(h) = &s.health {
        put("health_read_at", &h.read_at);
        put("health_version", &h.version.to_string());
        put("health_loop_gap_max_ms", &h.loop_gap_max_ms.to_string());
        put("health_loop_gap_max_mark", &h.loop_gap_max_mark);
        put("health_stall_ge_25ms", &h.count_ge_25ms.to_string());
        put("health_stall_ge_25ms_nonflash", &h.count_ge_25ms_nonflash.to_string());
        put("health_stall_ge_10ms", &h.count_ge_10ms.to_string());
        put("health_blit_timeouts", &h.blit_timeouts.to_string());
        put("health_tx_timeouts", &h.tx_timeouts.to_string());
        put("health_wdt_consecutive_resets", &h.wdt_consecutive_resets.to_string());
    }
    match &s.clock {
        None => put("clock", "python timekeeper (not this daemon)"),
        Some(c) => {
            put("clock", "this daemon");
            put("clock_syncs", &c.syncs.to_string());
            put("clock_failures", &c.failures.to_string());
            if let Some(v) = &c.last_sync {
                put("clock_last_sync", v);
            }
            if let Some(v) = &c.last_line {
                put("clock_last_line", v);
            }
            put("clock_interval_s", &c.interval_s.to_string());
            put("clock_lead_ms", &c.lead_ms);
            put(
                "clock_bias_ppm",
                &c.bias_ppm.map_or("unknown".to_string(), |b| b.to_string()),
            );
            if let Some(v) = &c.last_error {
                put("clock_last_error", v);
            }
        }
    }
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
            smtc_stale_s: None,
            foreign_reports: 0,
            clock: None,
            health: None,
        }
    }

    #[test]
    fn the_health_counters_render_with_their_own_prefix() {
        let mut s = sample();
        s.smtc_stale_s = Some(4);
        s.health = Some(HealthStatus {
            read_at: "2026-09-06 08:05:00".into(),
            version: 5,
            loop_gap_max_ms: 105,
            loop_gap_max_mark: "unexplained".into(),
            count_ge_25ms: 12,
            count_ge_25ms_nonflash: 12,
            count_ge_10ms: 30,
            blit_timeouts: 0,
            tx_timeouts: 1,
            wdt_consecutive_resets: 0,
        });
        let text = render(&s);
        assert!(text.contains("smtc_stale_s=4\nforeign_reports=0\nhealth_read_at=2026-09-06 08:05:00\nhealth_version=5\nhealth_loop_gap_max_ms=105\nhealth_loop_gap_max_mark=unexplained\nhealth_stall_ge_25ms=12\nhealth_stall_ge_25ms_nonflash=12\nhealth_stall_ge_10ms=30\nhealth_blit_timeouts=0\nhealth_tx_timeouts=1\nhealth_wdt_consecutive_resets=0\nclock="), "{text}");
    }

    #[test]
    fn renders_one_value_per_line_and_omits_absent_ones() {
        let text = render(&sample());
        assert_eq!(
            text,
            "version=ak820-agent 0.1.0 (v0.1.0)\nstarted=2026-09-06 08:00:00\nupdated=2026-09-06 08:00:03\nboard=present\nmedia_last_push=2026-09-06 08:00:03\nmedia_last_text=play  Artist - Title\nsmtc_polls=2\nsmtc_failures=0\nforeign_reports=0\nclock=python timekeeper (not this daemon)\n"
        );
    }

    #[test]
    fn the_clock_loop_renders_its_own_keys() {
        let mut s = sample();
        s.clock = Some(ClockStatus {
            syncs: 3,
            failures: 1,
            last_sync: Some("2026-09-06 08:05:00".into()),
            last_line: Some("sync (periodic): clock set (sub-second): before +2.9 ms".into()),
            interval_s: 300,
            lead_ms: "2.654".into(),
            bias_ppm: Some(-6),
            last_error: None,
        });
        let text = render(&s);
        assert!(text.contains("clock=this daemon\nclock_syncs=3\nclock_failures=1\nclock_last_sync=2026-09-06 08:05:00\nclock_last_line=sync (periodic): clock set (sub-second): before +2.9 ms\nclock_interval_s=300\nclock_lead_ms=2.654\nclock_bias_ppm=-6\n"), "{text}");
    }

    #[test]
    fn a_newline_in_a_value_cannot_forge_a_line() {
        let mut s = sample();
        s.media_last_error = Some("two\nlines\r\n".into());
        let text = render(&s);
        assert!(text.contains("media_last_error=two lines  \n"));
        assert_eq!(text.lines().count(), 11);
    }

    #[test]
    fn writes_atomically_and_reads_back() {
        let dir = std::env::temp_dir().join(format!("ak820-agent-status-{}", std::process::id()));
        let path = dir.join("agent.status");
        write(&path, &sample()).unwrap();
        let pairs = read(&path).unwrap();
        assert_eq!(pairs[0], ("version".to_string(), "ak820-agent 0.1.0 (v0.1.0)".to_string()));
        assert_eq!(pairs.len(), 10);
        let mut tmp = path.as_os_str().to_owned();
        tmp.push(".tmp");
        assert!(!Path::new(&tmp).exists());
        assert_eq!(read(&dir.join("absent")), None);
    }
}
