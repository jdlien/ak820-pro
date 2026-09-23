//! The health history: one CSV row per successful health read, so the series
//! outlives the status file that each read overwrites.
//!
//! Written for the crash hunt (plans/CRASH-HUNT-PLAN.md, Part A). The watchdog
//! reset of 2026-09-22 left one preceding sample and no way to say whether the
//! blit timeouts and stalls it had accumulated arrived steadily or bunched up
//! just before. Every row here comes from a read the daemon already makes, so
//! the history adds **no board traffic**.
//!
//! Append-only, header when the file is new. A header that no longer matches
//! [`COLUMNS`] rotates the old file to `.1` instead of mixing schemas, and so
//! does passing [`ROTATE_AT`] -- about seventy days of five-minute rows.

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use crate::status::HealthStatus;

/// Beside the daemon's log, whatever `--log` says.
pub const FILE: &str = "ak820-health.csv";

/// Rotate once the file is this large.
pub const ROTATE_AT: u64 = 5_000_000;

/// Counters are cumulative since the board's boot (or its last `HC_RESET`);
/// a drop between rows is a reboot, not a negative rate.
pub const COLUMNS: &[&str] = &[
    "read_at",
    "version",
    "blit_timeouts",
    "tx_sent",
    "tx_timeouts",
    "tx_drops",
    "rx_malformed",
    "loop_gap_max_ms",
    "loop_gap_max_mark",
    "scan_rate",
    "count_ge_10ms",
    "count_ge_25ms",
    "count_ge_25ms_nonflash",
    "passes",
    "flash_writes",
    "flash_gap_max_ms",
    "blit_gap_max_ms",
    "i2c_gap_max_ms",
    "key_presses",
    "wdt_consecutive_resets",
    "wdt_flags",
    "watchdog_record",
    // Page 6, health v7; empty on older firmware.
    "uptime_ms",
    "build_token",
    "msp_free",
    "psp_free",
    "blits_issued",
    "blit_never_started",
    "blit_stalled",
    "blit_irq_lost",
    "blit_unknown",
    "blit_busy_waits",
    "blit_retry_successes",
];

pub fn beside(log: &Path) -> PathBuf {
    log.with_file_name(FILE)
}

pub fn header() -> String {
    COLUMNS.join(",")
}

/// One sample, in [`COLUMNS`] order.
pub fn row(h: &HealthStatus) -> String {
    let fields = [
        h.read_at.clone(),
        h.version.to_string(),
        h.blit_timeouts.to_string(),
        h.tx_sent.to_string(),
        h.tx_timeouts.to_string(),
        h.tx_drops.to_string(),
        h.rx_malformed.to_string(),
        h.loop_gap_max_ms.to_string(),
        h.loop_gap_max_mark.clone(),
        h.scan_rate.to_string(),
        h.count_ge_10ms.to_string(),
        h.count_ge_25ms.to_string(),
        h.count_ge_25ms_nonflash.to_string(),
        h.passes.to_string(),
        h.flash_writes.to_string(),
        h.flash_gap_max_ms.to_string(),
        h.blit_gap_max_ms.to_string(),
        h.i2c_gap_max_ms.to_string(),
        h.key_presses.to_string(),
        h.wdt_consecutive_resets.to_string(),
        h.wdt_flags.to_string(),
        h.record_summary().unwrap_or_default(),
    ];
    let vitals: Vec<String> = match &h.vitals {
        Some(v) => vec![
            v.uptime_ms.to_string(),
            format!("0x{:08x}", v.build_token),
            v.msp_free.to_string(),
            v.psp_free.to_string(),
            v.blits_issued.to_string(),
            v.blit_never_started.to_string(),
            v.blit_stalled.to_string(),
            v.blit_irq_lost.to_string(),
            v.blit_unknown.to_string(),
            v.blit_busy_waits.to_string(),
            v.blit_retry_successes.to_string(),
        ],
        None => vec![String::new(); 11],
    };
    let fields: Vec<String> = fields.into_iter().chain(vitals).collect();
    debug_assert_eq!(fields.len(), COLUMNS.len());
    fields.iter().map(|f| quoted(f)).collect::<Vec<_>>().join(",")
}

/// RFC 4180: quote a field holding a comma, quote or line break. The record
/// summary does ("unavailable (reset flags 0x01, consecutive 0)").
fn quoted(field: &str) -> String {
    if field.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", field.replace('"', "\"\""))
    } else {
        field.to_string()
    }
}

/// Append one row, starting or rotating the file first when it needs it.
pub fn append(path: &Path, h: &HealthStatus) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let header = header();
    let fresh = match first_line(path)? {
        None => true,
        Some(line) if line == header => {
            if std::fs::metadata(path).map(|m| m.len() > ROTATE_AT).unwrap_or(false) {
                rotate(path)?;
                true
            } else {
                false
            }
        }
        Some(_) => {
            rotate(path)?;
            true
        }
    };
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    if fresh {
        writeln!(file, "{header}")?;
    }
    writeln!(file, "{}", row(h))
}

/// `None` for a missing or empty file -- the only cases that are "fresh". A
/// file that cannot be read (or is not UTF-8) is an error, not a fresh start:
/// treating it as one appended a second header to it (implementation review,
/// second pass, finding 5).
fn first_line(path: &Path) -> std::io::Result<Option<String>> {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e),
    };
    let mut line = String::new();
    BufReader::new(file).read_line(&mut line)?;
    let line = line.trim_end_matches(['\n', '\r']);
    Ok((!line.is_empty()).then(|| line.to_string()))
}

/// As the log does: rename to `.1`, and if an old `.1` is held open, remove it
/// and try once more. Unlike the log, a failure is an error: appending a new
/// header and new-schema rows to the old file is exactly the mixing rotation
/// exists to prevent (crash-hunt implementation review, finding 11).
fn rotate(path: &Path) -> std::io::Result<()> {
    let mut rotated = path.as_os_str().to_owned();
    rotated.push(".1");
    if std::fs::rename(path, &rotated).is_err() {
        let _ = std::fs::remove_file(&rotated);
        std::fs::rename(path, &rotated)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::health::CrashRecord;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ak820-agent-history-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir.join("sub").join(FILE)
    }

    fn sample() -> HealthStatus {
        HealthStatus {
            read_at: "2026-09-22 13:12:15".into(),
            version: 6,
            blit_timeouts: 455,
            tx_timeouts: 109_030,
            loop_gap_max_ms: 36,
            loop_gap_max_mark: "blit".into(),
            count_ge_25ms_nonflash: 28,
            scan_rate: 326,
            ..HealthStatus::default()
        }
    }

    #[test]
    fn a_row_has_one_field_per_column_in_order() {
        let r = row(&sample());
        let fields: Vec<&str> = r.split(',').collect();
        assert_eq!(fields.len(), COLUMNS.len());
        let at = |name: &str| fields[COLUMNS.iter().position(|c| *c == name).unwrap()];
        assert_eq!(at("read_at"), "2026-09-22 13:12:15");
        assert_eq!(at("blit_timeouts"), "455");
        assert_eq!(at("tx_timeouts"), "109030");
        assert_eq!(at("loop_gap_max_mark"), "blit");
        assert_eq!(at("count_ge_25ms_nonflash"), "28");
        assert_eq!(at("scan_rate"), "326");
        assert_eq!(at("watchdog_record"), "", "no page 5 below v6");
        assert_eq!(at("build_token"), "", "no page 6 below v7");
    }

    #[test]
    fn page6_fills_its_columns() {
        let mut h = sample();
        h.vitals = Some(crate::health::Page6 { uptime_ms: 3_600_000, build_token: 0xAEEF_2602,
            msp_free: 412, psp_free: 1024, blits_issued: 987_654, blit_unknown: 2,
            ..crate::health::Page6::default() });
        let r = row(&h);
        let fields: Vec<&str> = r.split(',').collect();
        assert_eq!(fields.len(), COLUMNS.len());
        let at = |name: &str| fields[COLUMNS.iter().position(|c| *c == name).unwrap()];
        assert_eq!(at("uptime_ms"), "3600000");
        assert_eq!(at("build_token"), "0xaeef2602");
        assert_eq!(at("psp_free"), "1024");
        assert_eq!(at("blits_issued"), "987654");
        assert_eq!(at("blit_unknown"), "2");
    }

    #[test]
    fn a_record_summary_with_a_comma_is_quoted() {
        let mut h = sample();
        h.crash = Some(CrashRecord { valid: false, boot_rstst: 1, format: 1, ..CrashRecord::default() });
        let r = row(&h);
        assert!(r.contains(",\"unavailable (reset flags 0x01, consecutive 0)\","), "{r}");
        assert_eq!(quoted("say \"hi\""), "\"say \"\"hi\"\"\"");
        assert_eq!(quoted("plain"), "plain");
    }

    #[test]
    fn an_unreadable_record_keeps_the_row_and_says_why() {
        let mut h = sample();
        h.crash_format_unsupported = Some(2);
        let r = row(&h);
        assert!(r.starts_with("2026-09-22 13:12:15,6,455,"), "{r}");
        assert!(r.contains(",record format 2 not understood by this agent -- update it,"), "{r}");
    }

    #[test]
    fn a_new_file_gets_the_header_once() {
        let path = scratch("new");
        append(&path, &sample()).unwrap();
        append(&path, &sample()).unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0], header());
        assert_eq!(lines[1], row(&sample()));
    }

    #[test]
    fn a_changed_schema_rotates_instead_of_mixing() {
        let path = scratch("schema");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "read_at,old_column\n2026-09-01 00:00:00,1\n").unwrap();
        append(&path, &sample()).unwrap();
        let mut rotated = path.as_os_str().to_owned();
        rotated.push(".1");
        assert!(std::fs::read_to_string(&rotated).unwrap().starts_with("read_at,old_column\n"));
        let text = std::fs::read_to_string(&path).unwrap();
        assert_eq!(text.lines().next().unwrap(), header());
        assert_eq!(text.lines().count(), 2);
    }

    #[test]
    fn a_large_file_is_rotated_once() {
        let path = scratch("large");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let mut big = header().into_bytes();
        big.push(b'\n');
        big.resize(ROTATE_AT as usize + 1, b'x');
        std::fs::write(&path, &big).unwrap();
        append(&path, &sample()).unwrap();
        let mut rotated = path.as_os_str().to_owned();
        rotated.push(".1");
        assert_eq!(std::fs::metadata(&rotated).unwrap().len(), ROTATE_AT + 1);
        assert_eq!(std::fs::read_to_string(&path).unwrap().lines().count(), 2);
    }

    #[test]
    fn an_unreadable_header_is_an_error_not_a_fresh_file() {
        let path = scratch("binary");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, [0xFF, 0xFE, 0x00, b'\n']).unwrap();
        assert!(append(&path, &sample()).is_err());
        assert_eq!(std::fs::read(&path).unwrap(), [0xFF, 0xFE, 0x00, b'\n'], "left untouched");
    }

    #[test]
    fn an_unwritable_path_is_an_error_not_a_panic() {
        let blocker = std::env::temp_dir().join(format!("ak820-history-blocker-{}", std::process::id()));
        std::fs::write(&blocker, b"a file, not a directory").unwrap();
        assert!(append(&blocker.join(FILE), &sample()).is_err());
        let _ = std::fs::remove_file(&blocker);
    }

    #[test]
    fn it_lives_beside_the_log() {
        let log = Path::new("/some/dir/ak820-agent.log");
        assert_eq!(beside(log), Path::new("/some/dir").join(FILE));
    }
}
