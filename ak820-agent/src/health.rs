//! The health channel (`0x13`): the firmware's counters, decoded and rendered
//! as `hostagent/ak820health.py` decodes and renders them.
//!
//! Four pages, each `[SET_VALUE, HEALTH, command, version, 28 bytes]`, with
//! the 28 bytes laid out in `health.h`. A page exists per command because
//! page 1's payload was already exactly full. ⚠️ **The version byte gates the
//! layout**: page 2 was repacked at version 3, page 3 arrived at 4, page 4 at
//! 5, and the Python refuses to parse an older board rather than silently
//! misread it. So does this.
//!
//! What this is for: the phase-5 gate says enough health reporting must land
//! **before** the clock takeover to detect firmware stalls the daemon's own
//! traffic might add. `count_ge_25ms_nonflash` is the number that matters —
//! a stall of 25 ms or more is the only class that can lose a keystroke, and
//! one not attributed to flash is unexplained. Everything else here is the
//! readout around it.
//!
//! Read-only: `HC_RESET` is deliberately not implemented. The Python's
//! `--reset` exists for experiments; a daemon has no business clearing the
//! evidence that the board reset itself.

use crate::proto::{Channel, REPORT_LEN};

pub const CHANNEL: Channel = Channel::Health;
pub const GET: u8 = 0x01;
pub const CONN: u8 = 0x02;
pub const RTC: u8 = 0x03;
pub const GET2: u8 = 0x04;
/// Not sent by this crate. Named so a reader can see what is being avoided.
pub const RESET: u8 = 0x05;
pub const GET3: u8 = 0x06;
pub const GET4: u8 = 0x07;

/// Why a page could not be decoded.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Error {
    /// Fewer than 32 bytes.
    Short,
    /// The firmware's health protocol version is older than this page's
    /// layout — the Python's `firmware health proto v{n}; page {p} needs v{m}`.
    Version { have: u8, page: u8, need: u8 },
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Short => write!(f, "short health reply"),
            Error::Version { have, page, need } => write!(
                f,
                "firmware health proto v{have}; page {page} needs v{need} -- flash the current build"
            ),
        }
    }
}

impl std::error::Error for Error {}

fn u16_at(r: &[u8], i: usize) -> u16 {
    u16::from_le_bytes([r[i], r[i + 1]])
}

fn u32_at(r: &[u8], i: usize) -> u32 {
    u32::from_le_bytes([r[i], r[i + 1], r[i + 2], r[i + 3]])
}

/// Page 1: `HC_GET`. `struct.unpack_from("<6IHBB", rep, 4)`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Page1 {
    pub version: u8,
    pub blit_timeouts: u32,
    pub tx_sent: u32,
    pub tx_timeouts: u32,
    pub tx_drops: u32,
    pub rx_malformed: u32,
    pub loop_gap_max_ms: u32,
    pub scan_rate: u16,
    pub wdt_consecutive_resets: u8,
    pub flags: u8,
}

impl Page1 {
    pub fn decode(report: &[u8]) -> Result<Page1, Error> {
        if report.len() < REPORT_LEN {
            return Err(Error::Short);
        }
        Ok(Page1 {
            version: report[3],
            blit_timeouts: u32_at(report, 4),
            tx_sent: u32_at(report, 8),
            tx_timeouts: u32_at(report, 12),
            tx_drops: u32_at(report, 16),
            rx_malformed: u32_at(report, 20),
            loop_gap_max_ms: u32_at(report, 24),
            scan_rate: u16_at(report, 28),
            wdt_consecutive_resets: report[30],
            flags: report[31],
        })
    }

    pub fn wdt_fired_last_boot(&self) -> bool {
        self.flags & 1 != 0
    }

    pub fn wdt_degraded(&self) -> bool {
        self.flags & 2 != 0
    }
}

/// What the worst loop gap was attributed to. `LOOP_MARK_*` in the firmware.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Mark {
    None,
    Flash,
    Blit,
    I2c,
    Unknown(u8),
}

impl Mark {
    pub fn from_byte(b: u8) -> Mark {
        match b {
            0 => Mark::None,
            1 => Mark::Flash,
            2 => Mark::Blit,
            3 => Mark::I2c,
            other => Mark::Unknown(other),
        }
    }

    /// The Python's `MARKS.get(mark, mark)`: a name, or the raw number.
    pub fn text(self) -> String {
        match self {
            Mark::None => "none".into(),
            Mark::Flash => "flash".into(),
            Mark::Blit => "blit".into(),
            Mark::I2c => "i2c".into(),
            Mark::Unknown(b) => b.to_string(),
        }
    }
}

/// Page 2: `HC_GET2`, version 3 or later. `"<4I5HBB"`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Page2 {
    pub count_ge_10ms: u32,
    pub count_ge_25ms: u32,
    pub passes: u32,
    pub flash_writes: u32,
    pub flash_gap_max_ms: u16,
    pub blit_gap_max_ms: u16,
    pub i2c_gap_max_ms: u16,
    /// The gate's discriminator: a stall long enough to lose a keystroke and
    /// not attributed to flash.
    pub count_ge_25ms_nonflash: u16,
    pub key_presses: u16,
    pub loop_gap_max_mark: Mark,
}

impl Page2 {
    pub const NEEDS: u8 = 3;

    pub fn decode(report: &[u8]) -> Result<Page2, Error> {
        if report.len() < REPORT_LEN {
            return Err(Error::Short);
        }
        if report[3] < Self::NEEDS {
            return Err(Error::Version {
                have: report[3],
                page: 2,
                need: Self::NEEDS,
            });
        }
        Ok(Page2 {
            count_ge_10ms: u32_at(report, 4),
            count_ge_25ms: u32_at(report, 8),
            passes: u32_at(report, 12),
            flash_writes: u32_at(report, 16),
            flash_gap_max_ms: u16_at(report, 20),
            blit_gap_max_ms: u16_at(report, 22),
            i2c_gap_max_ms: u16_at(report, 24),
            count_ge_25ms_nonflash: u16_at(report, 26),
            key_presses: u16_at(report, 28),
            loop_gap_max_mark: Mark::from_byte(report[30]),
        })
    }
}

/// Page 3: `HC_GET3`, version 4 or later. `"<7H3I2B"`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Page3 {
    /// Per row, `u16`: wraps every ~5 minutes at ~217 samples/s/row.
    pub row_samples: [u16; 6],
    pub row_gap_max_ms: u16,
    pub raw_edges: u32,
    pub consumes: u32,
    pub cooked_changes: u32,
    pub row_gap_max_row: u8,
    pub matrix_rows: u8,
}

impl Page3 {
    pub const NEEDS: u8 = 4;

    pub fn decode(report: &[u8]) -> Result<Page3, Error> {
        if report.len() < REPORT_LEN {
            return Err(Error::Short);
        }
        if report[3] < Self::NEEDS {
            return Err(Error::Version {
                have: report[3],
                page: 3,
                need: Self::NEEDS,
            });
        }
        let mut row_samples = [0u16; 6];
        for (i, r) in row_samples.iter_mut().enumerate() {
            *r = u16_at(report, 4 + 2 * i);
        }
        Ok(Page3 {
            row_samples,
            row_gap_max_ms: u16_at(report, 16),
            raw_edges: u32_at(report, 18),
            consumes: u32_at(report, 22),
            cooked_changes: u32_at(report, 26),
            row_gap_max_row: report[30],
            matrix_rows: report[31],
        })
    }

    /// The rows that exist, with a wrap straddle undone: the rows track each
    /// other to within a count and wrap within a moment of each other, but a
    /// read landing in that moment sees `65535` and `0` and would report a
    /// catastrophic imbalance on a healthy board.
    pub fn samples_unwrapped(&self) -> Vec<u32> {
        let n = (self.matrix_rows as usize).min(6);
        let mut s: Vec<u32> = self.row_samples[..n].iter().map(|&v| v as u32).collect();
        if let (Some(&max), Some(&min)) = (s.iter().max(), s.iter().min()) {
            if max - min > 32768 {
                for v in &mut s {
                    if *v < 32768 {
                        *v += 65536;
                    }
                }
            }
        }
        s
    }
}

/// Page 4: `HC_GET4`, version 5 or later. `"<2I2H4I"`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Page4 {
    pub isr_entries: u32,
    pub isr_ticks_sum: u32,
    /// `0xFFFF` until the first entry.
    pub isr_ticks_min: u16,
    pub isr_ticks_max: u16,
    /// `CH_CFG_ST_FREQUENCY`; the Python falls back to 187500 when zero.
    pub st_freq: u32,
    pub uptime_ms: u32,
    pub row_samples_total: u32,
}

impl Page4 {
    pub const NEEDS: u8 = 5;

    pub fn decode(report: &[u8]) -> Result<Page4, Error> {
        if report.len() < REPORT_LEN {
            return Err(Error::Short);
        }
        if report[3] < Self::NEEDS {
            return Err(Error::Version {
                have: report[3],
                page: 4,
                need: Self::NEEDS,
            });
        }
        Ok(Page4 {
            isr_entries: u32_at(report, 4),
            isr_ticks_sum: u32_at(report, 8),
            isr_ticks_min: u16_at(report, 12),
            isr_ticks_max: u16_at(report, 14),
            st_freq: u32_at(report, 16),
            uptime_ms: u32_at(report, 20),
            row_samples_total: u32_at(report, 24),
        })
    }
}

/// Python's `round(x, n)` on a float: the exact binary value correctly
/// rounded to `n` decimals, which is what `{:.n}` does too.
pub fn pyround(x: f64, n: usize) -> f64 {
    format!("{x:.n$}").parse().unwrap_or(x)
}

/// Python's `repr()` of a float, for the JSON: shortest round trip, and a
/// trailing `.0` on a whole number. Good for the magnitudes here.
pub fn pyfloat(x: f64) -> String {
    if x.is_finite() && x.fract() == 0.0 && x.abs() < 1e16 {
        format!("{x:.1}")
    } else {
        format!("{x}")
    }
}

/// `isr_rates(a, b, wall_s, rows)`: rates from two page-4 reads, with the
/// board's own timebase as `dt`. `None` where the Python yields `None`.
#[derive(Clone, Debug, PartialEq)]
pub struct IsrRates {
    pub isr_dt_s: f64,
    pub isr_per_s: Option<f64>,
    pub isr_mean_us: Option<f64>,
    pub isr_min_us: Option<f64>,
    pub isr_max_us: f64,
    pub isr_cpu_pct: Option<f64>,
    pub row_samples_per_row_per_s: Option<f64>,
    pub timebase_vs_wall: Option<f64>,
}

pub fn isr_rates(a: &Page4, b: &Page4, wall_s: f64, rows: u32) -> IsrRates {
    let f = if b.st_freq == 0 { 187500.0 } else { b.st_freq as f64 };
    let dt = b.uptime_ms.wrapping_sub(a.uptime_ms) as f64 / 1000.0;
    let de = b.isr_entries.wrapping_sub(a.isr_entries) as f64;
    let dtk = b.isr_ticks_sum.wrapping_sub(a.isr_ticks_sum) as f64;
    let drs = b.row_samples_total.wrapping_sub(a.row_samples_total) as f64;
    let us = 1e6 / f;
    let nz = |x: f64| x != 0.0;
    IsrRates {
        isr_dt_s: pyround(dt, 3),
        isr_per_s: nz(dt).then(|| pyround(de / dt, 1)),
        isr_mean_us: nz(de).then(|| pyround(dtk / de * us, 1)),
        isr_min_us: (b.isr_ticks_min != 0xFFFF).then(|| pyround(b.isr_ticks_min as f64 * us, 1)),
        isr_max_us: pyround(b.isr_ticks_max as f64 * us, 1),
        isr_cpu_pct: nz(dt).then(|| pyround(dtk / f / dt * 100.0, 1)),
        row_samples_per_row_per_s: nz(dt).then(|| pyround(drs / dt / rows as f64, 1)),
        timebase_vs_wall: nz(wall_s).then(|| pyround(dt / wall_s, 4)),
    }
}

// ---------------------------------------------------------------------------
// Rendering, as `ak820health.py` prints it
// ---------------------------------------------------------------------------

fn pybool(b: bool) -> &'static str {
    if b { "True" } else { "False" }
}

/// The ten lines `ak820health.py` always prints.
pub fn render_page1(p: &Page1) -> String {
    let mut out = String::new();
    for (k, v) in [
        ("blit_timeouts", p.blit_timeouts.to_string()),
        ("tx_sent", p.tx_sent.to_string()),
        ("tx_timeouts", p.tx_timeouts.to_string()),
        ("tx_drops", p.tx_drops.to_string()),
        ("rx_malformed", p.rx_malformed.to_string()),
        ("loop_gap_max_ms", p.loop_gap_max_ms.to_string()),
        ("scan_rate", p.scan_rate.to_string()),
        ("wdt_consecutive_resets", p.wdt_consecutive_resets.to_string()),
        ("wdt_fired_last_boot", pybool(p.wdt_fired_last_boot()).to_string()),
        ("wdt_degraded", pybool(p.wdt_degraded()).to_string()),
    ] {
        out.push_str(&format!("{k:<24} {v}\n"));
    }
    out
}

/// The `--stalls` block: a blank line, ten lines, then the verdict.
pub fn render_page2(p: &Page2) -> String {
    let mut out = String::from("\n");
    for (k, v) in [
        ("passes", p.passes.to_string()),
        ("count_ge_10ms", p.count_ge_10ms.to_string()),
        ("count_ge_25ms", p.count_ge_25ms.to_string()),
        ("count_ge_25ms_nonflash", p.count_ge_25ms_nonflash.to_string()),
        ("loop_gap_max_mark", p.loop_gap_max_mark.text()),
        ("flash_writes", p.flash_writes.to_string()),
        ("flash_gap_max_ms", p.flash_gap_max_ms.to_string()),
        ("blit_gap_max_ms", p.blit_gap_max_ms.to_string()),
        ("i2c_gap_max_ms", p.i2c_gap_max_ms.to_string()),
        ("key_presses", p.key_presses.to_string()),
    ] {
        out.push_str(&format!("{k:<24} {v}\n"));
    }
    if p.count_ge_25ms_nonflash != 0 {
        out.push_str(&format!(
            "\n  ** {} UNEXPLAINED stall(s) >= 25 ms -- long enough to lose a keystroke **\n",
            p.count_ge_25ms_nonflash
        ));
    } else if p.count_ge_25ms != 0 {
        out.push_str(&format!(
            "\n  {} stall(s) >= 25 ms, all attributed to flash (wear-levelling consolidation -- understood, bounded)\n",
            p.count_ge_25ms
        ));
    } else {
        out.push_str("\n  no stall >= 25 ms since reset (shorter stalls delay a press, they cannot drop it)\n");
    }
    out
}

/// The `--rows` block. `key_presses` comes from page 2 when it was read.
pub fn render_page3(p: &Page3, key_presses: Option<u16>) -> String {
    let n = (p.matrix_rows as usize).min(6);
    let listed: Vec<String> = p.row_samples[..n].iter().map(|v| v.to_string()).collect();
    let mut out = String::from("\n");
    out.push_str(&format!("{:<24} [{}]\n", "row_samples", listed.join(", ")));
    out.push_str(&format!(
        "{:<24} {}  (row {})\n",
        "row_gap_max_ms", p.row_gap_max_ms, p.row_gap_max_row
    ));
    for (k, v) in [
        ("raw_edges", p.raw_edges),
        ("consumes", p.consumes),
        ("cooked_changes", p.cooked_changes),
    ] {
        out.push_str(&format!("{k:<24} {v}\n"));
    }
    let s = p.samples_unwrapped();
    if let (Some(&max), Some(&min)) = (s.iter().max(), s.iter().min()) {
        let even = max as f64 <= min as f64 * 1.25;
        out.push_str(&format!(
            "\n  spread {min}-{max} ({})  [uint16, wraps every ~5 min -- --reset first for absolute counts]\n",
            if even { "EVEN" } else { "UNEVEN -- some keys looked at less often" }
        ));
    }
    let g = p.row_gap_max_ms;
    if g >= 25 {
        out.push_str(&format!(
            "  ** worst gap {g} ms on row {} -- a keypress can END inside that window and never be seen **\n",
            p.row_gap_max_row
        ));
    } else if g >= 10 {
        out.push_str(&format!("  worst gap {g} ms -- elevated; healthy is single-digit\n"));
    } else {
        out.push_str(&format!(
            "  worst gap {g} ms -- healthy (a 25-80 ms press gets sampled several times)\n"
        ));
    }
    if let Some(k) = key_presses.filter(|&k| k != 0) {
        out.push_str(&format!(
            "  raw_edges {} vs key_presses {k} (expect ~2x: a press and a release are two raw edges)\n",
            p.raw_edges
        ));
    }
    out
}

fn pyopt(v: Option<f64>) -> String {
    v.map_or("None".to_string(), pyfloat)
}

/// The `--isr` block.
pub fn render_isr(r: &IsrRates) -> String {
    let mut out = String::from("\n");
    for (k, v) in [
        ("isr_per_s", pyopt(r.isr_per_s)),
        ("isr_mean_us", pyopt(r.isr_mean_us)),
        ("isr_min_us", pyopt(r.isr_min_us)),
        ("isr_max_us", pyfloat(r.isr_max_us)),
        ("isr_cpu_pct", pyopt(r.isr_cpu_pct)),
        ("row_samples_per_row_per_s", pyopt(r.row_samples_per_row_per_s)),
        ("timebase_vs_wall", pyopt(r.timebase_vs_wall)),
    ] {
        out.push_str(&format!("{k:<24} {v}\n"));
    }
    out.push_str(
        "\n  period = ISR duration + ~53 us (counter re-armed at ISR end), so isr_mean_us sets the row rate;\n  isr_cpu_pct is the M0 share inside the row ISR -- the ceiling on scanning and the main loop\n",
    );
    out
}

/// `json.dumps(d)`: the dict in the Python's insertion order, its
/// separators, its spellings of booleans, `None` and floats.
pub fn render_json(
    p1: &Page1,
    p2: Option<&Page2>,
    p3: Option<&Page3>,
    p4: Option<(&Page4, &IsrRates)>,
) -> String {
    let mut items: Vec<(String, String)> = vec![
        ("blit_timeouts".into(), p1.blit_timeouts.to_string()),
        ("tx_sent".into(), p1.tx_sent.to_string()),
        ("tx_timeouts".into(), p1.tx_timeouts.to_string()),
        ("tx_drops".into(), p1.tx_drops.to_string()),
        ("rx_malformed".into(), p1.rx_malformed.to_string()),
        ("loop_gap_max_ms".into(), p1.loop_gap_max_ms.to_string()),
        ("scan_rate".into(), p1.scan_rate.to_string()),
        ("wdt_consecutive_resets".into(), p1.wdt_consecutive_resets.to_string()),
        ("flags".into(), p1.flags.to_string()),
        ("version".into(), p1.version.to_string()),
        ("wdt_fired_last_boot".into(), pybool(p1.wdt_fired_last_boot()).to_lowercase()),
        ("wdt_degraded".into(), pybool(p1.wdt_degraded()).to_lowercase()),
    ];
    if let Some(p) = p2 {
        items.extend([
            ("count_ge_10ms".into(), p.count_ge_10ms.to_string()),
            ("count_ge_25ms".into(), p.count_ge_25ms.to_string()),
            ("passes".into(), p.passes.to_string()),
            ("flash_writes".into(), p.flash_writes.to_string()),
            ("flash_gap_max_ms".into(), p.flash_gap_max_ms.to_string()),
            ("blit_gap_max_ms".into(), p.blit_gap_max_ms.to_string()),
            ("i2c_gap_max_ms".into(), p.i2c_gap_max_ms.to_string()),
            ("count_ge_25ms_nonflash".into(), p.count_ge_25ms_nonflash.to_string()),
            ("key_presses".into(), p.key_presses.to_string()),
            (
                "loop_gap_max_mark".into(),
                match p.loop_gap_max_mark {
                    Mark::Unknown(b) => b.to_string(),
                    m => format!("\"{}\"", m.text()),
                },
            ),
        ]);
    }
    if let Some(p) = p3 {
        let rows: Vec<String> = p.row_samples.iter().map(|v| v.to_string()).collect();
        items.extend([
            ("row_samples".into(), format!("[{}]", rows.join(", "))),
            ("row_gap_max_ms".into(), p.row_gap_max_ms.to_string()),
            ("raw_edges".into(), p.raw_edges.to_string()),
            ("consumes".into(), p.consumes.to_string()),
            ("cooked_changes".into(), p.cooked_changes.to_string()),
            ("row_gap_max_row".into(), p.row_gap_max_row.to_string()),
            ("matrix_rows".into(), p.matrix_rows.to_string()),
        ]);
    }
    if let Some((p, r)) = p4 {
        let null = |v: Option<f64>| v.map_or("null".to_string(), pyfloat);
        items.extend([
            ("isr_entries".into(), p.isr_entries.to_string()),
            ("isr_ticks_sum".into(), p.isr_ticks_sum.to_string()),
            ("isr_ticks_min".into(), p.isr_ticks_min.to_string()),
            ("isr_ticks_max".into(), p.isr_ticks_max.to_string()),
            ("st_freq".into(), p.st_freq.to_string()),
            ("uptime_ms".into(), p.uptime_ms.to_string()),
            ("row_samples_total".into(), p.row_samples_total.to_string()),
            ("isr_dt_s".into(), pyfloat(r.isr_dt_s)),
            ("isr_per_s".into(), null(r.isr_per_s)),
            ("isr_mean_us".into(), null(r.isr_mean_us)),
            ("isr_min_us".into(), null(r.isr_min_us)),
            ("isr_max_us".into(), pyfloat(r.isr_max_us)),
            ("isr_cpu_pct".into(), null(r.isr_cpu_pct)),
            ("row_samples_per_row_per_s".into(), null(r.row_samples_per_row_per_s)),
            ("timebase_vs_wall".into(), null(r.timebase_vs_wall)),
        ]);
    }
    let body: Vec<String> = items.iter().map(|(k, v)| format!("\"{k}\": {v}")).collect();
    format!("{{{}}}", body.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn report(command: u8, version: u8, payload: &[u8]) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[0] = 0x07;
        r[1] = 0x13;
        r[2] = command;
        r[3] = version;
        r[4..4 + payload.len()].copy_from_slice(payload);
        r
    }

    fn le32(v: u32) -> [u8; 4] {
        v.to_le_bytes()
    }

    #[test]
    fn page1_decodes_the_documented_layout() {
        let mut p = Vec::new();
        for v in [1u32, 20000, 3, 4, 5, 22] {
            p.extend(le32(v));
        }
        p.extend(375u16.to_le_bytes());
        p.push(2);
        p.push(0b11);
        let d = Page1::decode(&report(GET, 5, &p)).unwrap();
        assert_eq!(d.version, 5);
        assert_eq!((d.blit_timeouts, d.tx_sent, d.tx_timeouts, d.tx_drops), (1, 20000, 3, 4));
        assert_eq!((d.rx_malformed, d.loop_gap_max_ms, d.scan_rate), (5, 22, 375));
        assert_eq!(d.wdt_consecutive_resets, 2);
        assert!(d.wdt_fired_last_boot());
        assert!(d.wdt_degraded());
        assert_eq!(
            render_page1(&d),
            "blit_timeouts            1\ntx_sent                  20000\ntx_timeouts              3\ntx_drops                 4\nrx_malformed             5\nloop_gap_max_ms          22\nscan_rate                375\nwdt_consecutive_resets   2\nwdt_fired_last_boot      True\nwdt_degraded             True\n"
        );
    }

    #[test]
    fn page2_needs_version_3_and_names_the_mark() {
        let mut p = Vec::new();
        for v in [19u32, 0, 123456, 7] {
            p.extend(le32(v));
        }
        for v in [30u16, 22, 4, 0, 54] {
            p.extend(v.to_le_bytes());
        }
        p.push(2);
        p.push(0);
        let d = Page2::decode(&report(GET2, 5, &p)).unwrap();
        assert_eq!((d.count_ge_10ms, d.count_ge_25ms, d.passes, d.flash_writes), (19, 0, 123456, 7));
        assert_eq!((d.flash_gap_max_ms, d.blit_gap_max_ms, d.i2c_gap_max_ms), (30, 22, 4));
        assert_eq!((d.count_ge_25ms_nonflash, d.key_presses), (0, 54));
        assert_eq!(d.loop_gap_max_mark, Mark::Blit);
        assert!(render_page2(&d).ends_with("\n  no stall >= 25 ms since reset (shorter stalls delay a press, they cannot drop it)\n"));
        assert_eq!(
            Page2::decode(&report(GET2, 2, &p)),
            Err(Error::Version { have: 2, page: 2, need: 3 })
        );
        assert_eq!(Mark::from_byte(9).text(), "9");
    }

    #[test]
    fn page2_verdicts() {
        let base = Page2 {
            count_ge_10ms: 0,
            count_ge_25ms: 0,
            passes: 1,
            flash_writes: 0,
            flash_gap_max_ms: 0,
            blit_gap_max_ms: 0,
            i2c_gap_max_ms: 0,
            count_ge_25ms_nonflash: 0,
            key_presses: 0,
            loop_gap_max_mark: Mark::None,
        };
        let flash = Page2 { count_ge_25ms: 3, ..base.clone() };
        assert!(render_page2(&flash).contains("\n  3 stall(s) >= 25 ms, all attributed to flash (wear-levelling consolidation -- understood, bounded)\n"));
        let bad = Page2 { count_ge_25ms: 3, count_ge_25ms_nonflash: 1, ..base };
        assert!(render_page2(&bad).contains("\n  ** 1 UNEXPLAINED stall(s) >= 25 ms -- long enough to lose a keystroke **\n"));
    }

    #[test]
    fn page3_decodes_rows_and_undoes_a_wrap_straddle() {
        let mut p = Vec::new();
        for v in [65535u16, 65534, 1, 65533, 0, 65535, 5] {
            p.extend(v.to_le_bytes());
        }
        for v in [108u32, 200000, 60] {
            p.extend(le32(v));
        }
        p.push(3);
        p.push(6);
        let d = Page3::decode(&report(GET3, 5, &p)).unwrap();
        assert_eq!(d.row_samples, [65535, 65534, 1, 65533, 0, 65535]);
        assert_eq!(d.row_gap_max_ms, 5);
        assert_eq!((d.raw_edges, d.consumes, d.cooked_changes), (108, 200000, 60));
        assert_eq!((d.row_gap_max_row, d.matrix_rows), (3, 6));
        assert_eq!(d.samples_unwrapped(), vec![65535, 65534, 65537, 65533, 65536, 65535]);
        let text = render_page3(&d, Some(54));
        assert!(text.contains("row_samples              [65535, 65534, 1, 65533, 0, 65535]\n"));
        assert!(text.contains("row_gap_max_ms           5  (row 3)\n"));
        assert!(text.contains("\n  spread 65533-65537 (EVEN)  [uint16, wraps every ~5 min -- --reset first for absolute counts]\n"));
        assert!(text.contains("  worst gap 5 ms -- healthy (a 25-80 ms press gets sampled several times)\n"));
        assert!(text.contains("  raw_edges 108 vs key_presses 54 (expect ~2x: a press and a release are two raw edges)\n"));
        assert_eq!(Page3::decode(&report(GET3, 3, &p)), Err(Error::Version { have: 3, page: 3, need: 4 }));
    }

    #[test]
    fn page3_gap_verdicts_and_fewer_rows() {
        let mut p = Vec::new();
        for v in [100u16, 100, 100, 100, 0, 0, 30] {
            p.extend(v.to_le_bytes());
        }
        for v in [0u32, 0, 0] {
            p.extend(le32(v));
        }
        p.push(1);
        p.push(4);
        let d = Page3::decode(&report(GET3, 5, &p)).unwrap();
        let text = render_page3(&d, None);
        assert!(text.contains("row_samples              [100, 100, 100, 100]\n"), "{text}");
        assert!(text.contains("  ** worst gap 30 ms on row 1 -- a keypress can END inside that window and never be seen **\n"));
        assert!(!text.contains("raw_edges 0 vs"));
        let mut e = d.clone();
        e.row_gap_max_ms = 12;
        assert!(render_page3(&e, None).contains("  worst gap 12 ms -- elevated; healthy is single-digit\n"));
    }

    #[test]
    fn page4_and_the_rates_match_the_python_arithmetic() {
        let mut a = Vec::new();
        for v in [1000u32, 200_000] {
            a.extend(le32(v));
        }
        a.extend(30u16.to_le_bytes());
        a.extend(80u16.to_le_bytes());
        for v in [187_500u32, 10_000, 3000, 0] {
            a.extend(le32(v));
        }
        let pa = Page4::decode(&report(GET4, 5, &a)).unwrap();
        let pb = Page4 {
            isr_entries: 1000 + 7752,
            isr_ticks_sum: 200_000 + 273_000,
            isr_ticks_min: 30,
            isr_ticks_max: 80,
            st_freq: 187_500,
            uptime_ms: 12_000,
            row_samples_total: 3000 + 2580,
        };
        let r = isr_rates(&pa, &pb, 2.001, 6);
        assert_eq!(r.isr_dt_s, 2.0);
        assert_eq!(r.isr_per_s, Some(3876.0));
        // 273000 / 7752 * (1e6/187500) = 35.216... * 5.3333 = 187.8
        assert_eq!(r.isr_mean_us, Some(187.8));
        assert_eq!(r.isr_min_us, Some(160.0));
        assert_eq!(r.isr_max_us, 426.7);
        // 273000 / 187500 / 2 * 100 = 72.8
        assert_eq!(r.isr_cpu_pct, Some(72.8));
        assert_eq!(r.row_samples_per_row_per_s, Some(215.0));
        assert_eq!(r.timebase_vs_wall, Some(0.9995));
        let text = render_isr(&r);
        assert!(text.contains("isr_per_s                3876.0\n"), "{text}");
        assert!(text.contains("isr_cpu_pct              72.8\n"));
        assert!(text.ends_with("  isr_cpu_pct is the M0 share inside the row ISR -- the ceiling on scanning and the main loop\n"));
        assert_eq!(Page4::decode(&report(GET4, 4, &a)), Err(Error::Version { have: 4, page: 4, need: 5 }));
    }

    #[test]
    fn rates_yield_none_where_the_python_does() {
        let p = Page4 {
            isr_entries: 0,
            isr_ticks_sum: 0,
            isr_ticks_min: 0xFFFF,
            isr_ticks_max: 0,
            st_freq: 0,
            uptime_ms: 5,
            row_samples_total: 0,
        };
        let r = isr_rates(&p, &p, 0.0, 6);
        assert_eq!(r.isr_dt_s, 0.0);
        assert_eq!(r.isr_per_s, None);
        assert_eq!(r.isr_mean_us, None);
        assert_eq!(r.isr_min_us, None, "0xFFFF means no entry yet");
        assert_eq!(r.isr_max_us, 0.0);
        assert_eq!(r.timebase_vs_wall, None);
        assert!(render_isr(&r).contains("isr_per_s                None\n"));
    }

    #[test]
    fn python_rounding_and_float_spelling() {
        assert_eq!(pyround(2.675, 2), 2.67, "the binary value is below the tie");
        assert_eq!(pyround(0.125, 2), 0.12, "an exact tie goes to even");
        assert_eq!(pyround(3876.24, 1), 3876.2);
        assert_eq!(pyfloat(4.0), "4.0");
        assert_eq!(pyfloat(3876.2), "3876.2");
        assert_eq!(pyfloat(0.9995), "0.9995");
    }

    #[test]
    fn json_is_the_pythons_dict_in_its_order() {
        let p1 = Page1 {
            version: 5,
            blit_timeouts: 0,
            tx_sent: 10,
            tx_timeouts: 0,
            tx_drops: 0,
            rx_malformed: 0,
            loop_gap_max_ms: 20,
            scan_rate: 375,
            wdt_consecutive_resets: 0,
            flags: 0,
        };
        assert_eq!(
            render_json(&p1, None, None, None),
            "{\"blit_timeouts\": 0, \"tx_sent\": 10, \"tx_timeouts\": 0, \"tx_drops\": 0, \"rx_malformed\": 0, \"loop_gap_max_ms\": 20, \"scan_rate\": 375, \"wdt_consecutive_resets\": 0, \"flags\": 0, \"version\": 5, \"wdt_fired_last_boot\": false, \"wdt_degraded\": false}"
        );
        let p2 = Page2 {
            count_ge_10ms: 1,
            count_ge_25ms: 0,
            passes: 9,
            flash_writes: 0,
            flash_gap_max_ms: 0,
            blit_gap_max_ms: 20,
            i2c_gap_max_ms: 0,
            count_ge_25ms_nonflash: 0,
            key_presses: 2,
            loop_gap_max_mark: Mark::Blit,
        };
        let j = render_json(&p1, Some(&p2), None, None);
        assert!(j.ends_with(", \"count_ge_10ms\": 1, \"count_ge_25ms\": 0, \"passes\": 9, \"flash_writes\": 0, \"flash_gap_max_ms\": 0, \"blit_gap_max_ms\": 20, \"i2c_gap_max_ms\": 0, \"count_ge_25ms_nonflash\": 0, \"key_presses\": 2, \"loop_gap_max_mark\": \"blit\"}"), "{j}");
    }

    #[test]
    fn short_reports_are_refused() {
        assert_eq!(Page1::decode(&[0u8; 31]), Err(Error::Short));
        assert_eq!(Page2::decode(&[5u8; 8]), Err(Error::Short));
    }
}
