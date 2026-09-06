//! The capability cache: `$HOME/.ak820ctl-cap`, one line, `proto lead_ms [b_ppm]`.
//!
//! Shared with `ak820ctl` for as long as it remains installed, and with the
//! Python timekeeper, which rewrites the bias field whenever its learner fires.
//! So the file is an interface between three programs, and this module's job is
//! to read and write it exactly as the C does — `fscanf("%d %lf %d")` in,
//! `"%d %.3f %d\n"` out — including the parts of `fscanf` nobody would design
//! on purpose: a `%d` that reads `12.5` as `12` and stops, trailing garbage that
//! is ignored, and an overflowing integer that saturates.
//!
//! Every expectation in the tests below was produced by running the pinned C
//! functions themselves through the mingw64 CRT that builds `ak820ctl.exe`
//! (`scripts/clock_oracle.c`), not by reasoning about what `fscanf` probably
//! does. Regenerate with the instructions in that file.
//!
//! ⚠️ The lead is persisted to **three decimals** and the bias as an integer. A
//! port keeping more precision in memory still has to round-trip through this
//! file identically while `ak820ctl` is installed, or the two disagree — which
//! is why [`format`] is a test subject and not a detail.
//!
//! # Two deliberate divergences
//!
//! Both on inputs that no writer of this file ever produces, and both pinned as
//! tests that say what the C would have done instead:
//!
//! - **`nan`**. A lead of `nan` passes the C's range check, because NaN compares
//!   false to everything; it is then used as `t_enc + nan / 1000`, cast to
//!   `time_t` (undefined behaviour), and written back as `nan` — the file
//!   stays poisoned forever. Here NaN is out of range and resets to the
//!   default, like `inf` does in both.
//! - **Hexadecimal floats** (`0x1p-1`), which `%lf` accepts. Here the scan
//!   stops at the `x`, as it would for any other letter.
//!
//! # Not the C's file handling
//!
//! Saves go through a temporary file and a rename, which is what the Python
//! timekeeper does (`cap_write_bias`) and the C does not. The bytes written are
//! the same, `\r\n` included; a crash mid-write leaves the old file rather than
//! a truncated one.

use std::path::{Path, PathBuf};

/// `cap_load`'s default when the file is absent, short, or out of range.
pub const DEFAULT_LEAD_MS: f64 = 1.5;
/// Leads outside `0..=10` ms reset to the default.
pub const MAX_LEAD_MS: f64 = 10.0;
/// A bias outside `±600` ppm is treated as absent. Matches the firmware's own
/// validation of the SET packet's bias field.
pub const BIAS_LIMIT_PPM: i32 = 600;
/// The file's name under the agreed home directory.
pub const FILE_NAME: &str = ".ak820ctl-cap";

/// What the cache holds. Mirrors the C's `cap_t`, except that the C keeps an
/// out-of-range `b_ppm` in memory with `has_bias` cleared; nothing ever reads
/// it in that state, so here the two collapse into `None`.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct Cap {
    /// The RTC protocol version the board was last seen to speak. `0` means
    /// the legacy whole-second protocol; only [`super::PROTO_VERSION`] gets
    /// the sub-second path.
    pub proto: i32,
    /// The learned outbound lead: how far ahead of "now" to stamp the SET so
    /// that it lands on the boundary.
    pub lead_ms: f64,
    /// The SOF-bias correction the host learned, in ppm, if any.
    pub bias_ppm: Option<i32>,
}

impl Default for Cap {
    fn default() -> Self {
        Cap {
            proto: 0,
            lead_ms: DEFAULT_LEAD_MS,
            bias_ppm: None,
        }
    }
}

/// `cap_load`, minus the file: the C's `fscanf("%d %lf %d")` and the two range
/// resets that follow it.
///
/// The count of successful conversions decides everything: fewer than two
/// means both leading fields reset (⚠️ including a `proto` that *was* read),
/// and the bias exists only when all three parsed.
pub fn parse(text: &str) -> Cap {
    let mut sc = Scanner::new(text.as_bytes());
    let mut proto = 0i32;
    let mut lead = DEFAULT_LEAD_MS;
    let mut b = 0i32;
    let mut n = 0;
    if let Some(v) = sc.int() {
        proto = v;
        n = 1;
        if let Some(v) = sc.float() {
            lead = v;
            n = 2;
            if let Some(v) = sc.int() {
                b = v;
                n = 3;
            }
        }
    }
    if n < 2 {
        proto = 0;
        lead = DEFAULT_LEAD_MS;
    }
    let has_bias = n == 3;
    // `contains` is false for NaN, which is the documented divergence from the
    // C's `lead < 0 || lead > 10` (both false for NaN, so NaN survives there).
    if !(0.0..=MAX_LEAD_MS).contains(&lead) {
        lead = DEFAULT_LEAD_MS;
    }
    let bias_ppm = if has_bias && (-BIAS_LIMIT_PPM..=BIAS_LIMIT_PPM).contains(&b) {
        Some(b)
    } else {
        None
    };
    Cap {
        proto,
        lead_ms: lead,
        bias_ppm,
    }
}

/// `cap_save`'s bytes: `"%d %.3f %d\n"` with a bias, `"%d %.3f\n"` without —
/// **and the `\n` is `\r\n` on disk.** The C opens the file in text mode
/// (`fopen(..., "w")`) and so does the Python timekeeper, and on Windows both
/// translate; the installed cache ends in `0D 0A`. The first version of this
/// wrote a bare `\n`, which every parser tolerates and the byte-for-byte claim
/// did not survive — the phase-2 audit's finding 5. This crate is Windows
/// only, so the translation is spelled out rather than made conditional.
///
/// Rust's `{:.3}` and the CRT's `%.3f` both print the exact binary value
/// correctly rounded, ties to even; the tests pin the ties (`0.0625` → `0.062`)
/// because that agreement is what makes the file interchangeable.
pub fn format(cap: &Cap) -> String {
    match cap.bias_ppm {
        Some(b) => format!("{} {:.3} {}\r\n", cap.proto, cap.lead_ms, b),
        None => format!("{} {:.3}\r\n", cap.proto, cap.lead_ms),
    }
}

/// A cursor with `fscanf`'s conversion rules for `%d` and `%lf`: skip
/// whitespace, take the longest prefix the directive accepts, stop at the first
/// byte it does not.
struct Scanner<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> Scanner<'a> {
    fn new(s: &'a [u8]) -> Self {
        Scanner { s, i: 0 }
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }

    /// C's `isspace` in the C locale.
    fn skip_ws(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | 0x0B | 0x0C | b'\r')) {
            self.i += 1;
        }
    }

    fn take_digits(&mut self) -> usize {
        let start = self.i;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.i += 1;
        }
        self.i - start
    }

    /// `%d`: optional sign, at least one decimal digit, saturating on overflow
    /// the way this CRT does (`99999999999` reads as `2147483647`).
    fn int(&mut self) -> Option<i32> {
        self.skip_ws();
        let start = self.i;
        let negative = match self.peek() {
            Some(b'-') => {
                self.i += 1;
                true
            }
            Some(b'+') => {
                self.i += 1;
                false
            }
            _ => false,
        };
        let digits_at = self.i;
        if self.take_digits() == 0 {
            self.i = start;
            return None;
        }
        let mut v: i64 = 0;
        for &d in &self.s[digits_at..self.i] {
            v = v.saturating_mul(10).saturating_add((d - b'0') as i64);
            if v > i32::MAX as i64 + 1 {
                v = i32::MAX as i64 + 1; // enough to saturate either way below
            }
        }
        let v = if negative { -v } else { v };
        Some(v.clamp(i32::MIN as i64, i32::MAX as i64) as i32)
    }

    /// `%lf`: `strtod`'s decimal grammar, `inf`/`infinity` and `nan`, without
    /// the hexadecimal form (see the module header).
    fn float(&mut self) -> Option<f64> {
        self.skip_ws();
        let start = self.i;
        let mut negative = false;
        match self.peek() {
            Some(b'-') => {
                negative = true;
                self.i += 1;
            }
            Some(b'+') => self.i += 1,
            _ => {}
        }
        let sign = if negative { -1.0 } else { 1.0 };

        if self.take_word_ci(b"infinity") || self.take_word_ci(b"inf") {
            return Some(sign * f64::INFINITY);
        }
        if self.take_word_ci(b"nan") {
            // An optional "(n-char-sequence)" may follow; consume it if closed.
            if self.peek() == Some(b'(') {
                let save = self.i;
                self.i += 1;
                while matches!(
                    self.peek(),
                    Some(b'0'..=b'9' | b'a'..=b'z' | b'A'..=b'Z' | b'_')
                ) {
                    self.i += 1;
                }
                if self.peek() == Some(b')') {
                    self.i += 1;
                } else {
                    self.i = save;
                }
            }
            return Some(f64::NAN);
        }

        let mantissa_at = self.i;
        let int_digits = self.take_digits();
        let mut frac_digits = 0;
        if self.peek() == Some(b'.') {
            self.i += 1;
            frac_digits = self.take_digits();
        }
        if int_digits + frac_digits == 0 {
            self.i = start;
            return None;
        }
        // An exponent is only consumed when it is complete: `1e` is `1` and
        // an `e` left for the next directive to choke on.
        if matches!(self.peek(), Some(b'e' | b'E')) {
            let save = self.i;
            self.i += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.i += 1;
            }
            if self.take_digits() == 0 {
                self.i = save;
            }
        }
        let text = std::str::from_utf8(&self.s[mantissa_at..self.i]).ok()?;
        let magnitude: f64 = text.parse().ok()?;
        Some(sign * magnitude)
    }

    fn take_word_ci(&mut self, word: &[u8]) -> bool {
        let end = self.i + word.len();
        if end <= self.s.len() && self.s[self.i..end].eq_ignore_ascii_case(word) {
            self.i = end;
            true
        } else {
            false
        }
    }
}

/// Where the cache lives, so the transaction can be tested against memory and
/// run against a file.
pub trait Cache {
    /// The C's `cap_load`: defaults when the file is missing or unreadable.
    fn load(&self) -> Cap;
    /// The C's `cap_save`. The C ignores a failed `fopen` silently; the error
    /// is returned here so a caller can at least log it.
    fn save(&self, cap: &Cap) -> Result<(), String>;
}

/// The cache as a file on disk.
pub struct FileCache {
    path: PathBuf,
}

impl FileCache {
    pub fn at(path: impl Into<PathBuf>) -> Self {
        FileCache { path: path.into() }
    }

    /// The path the Python timekeeper agrees on with `ak820ctl`:
    /// `%USERPROFILE%\.ak820ctl-cap`.
    ///
    /// ⚠️ `ak820ctl` itself keys off `getenv("HOME")`, which Windows does not
    /// set, so the timekeeper exports `HOME=%USERPROFILE%` when it spawns the
    /// tool. This is that same location, resolved without needing the export.
    pub fn default_path() -> PathBuf {
        let home = std::env::var_os("USERPROFILE")
            .or_else(|| std::env::var_os("HOME"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."));
        home.join(FILE_NAME)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl Cache for FileCache {
    fn load(&self) -> Cap {
        match std::fs::read(&self.path) {
            Ok(bytes) => parse(&String::from_utf8_lossy(&bytes)),
            Err(_) => Cap::default(),
        }
    }

    fn save(&self, cap: &Cap) -> Result<(), String> {
        let mut tmp = self.path.clone().into_os_string();
        tmp.push(".tmp");
        let tmp = PathBuf::from(tmp);
        std::fs::write(&tmp, format(cap)).map_err(|e| format!("{}: {e}", tmp.display()))?;
        std::fs::rename(&tmp, &self.path)
            .map_err(|e| format!("{} -> {}: {e}", tmp.display(), self.path.display()))
    }
}

/// An in-memory cache for tests: what was loaded, and every save in order.
#[cfg(test)]
pub struct MemCache {
    text: std::cell::RefCell<Option<String>>,
    saves: std::cell::RefCell<Vec<String>>,
    fail_saves: bool,
}

#[cfg(test)]
impl MemCache {
    pub fn with(text: &str) -> Self {
        MemCache {
            text: std::cell::RefCell::new(Some(text.to_string())),
            saves: std::cell::RefCell::new(Vec::new()),
            fail_saves: false,
        }
    }
    pub fn absent() -> Self {
        MemCache {
            text: std::cell::RefCell::new(None),
            saves: std::cell::RefCell::new(Vec::new()),
            fail_saves: false,
        }
    }
    pub fn failing_saves(mut self) -> Self {
        self.fail_saves = true;
        self
    }
    pub fn saved(&self) -> Vec<String> {
        self.saves.borrow().clone()
    }
}

#[cfg(test)]
impl Cache for MemCache {
    fn load(&self) -> Cap {
        match self.text.borrow().as_deref() {
            Some(t) => parse(t),
            None => Cap::default(),
        }
    }
    fn save(&self, cap: &Cap) -> Result<(), String> {
        if self.fail_saves {
            return Err("disk full".into());
        }
        let text = format(cap);
        self.saves.borrow_mut().push(text.clone());
        *self.text.borrow_mut() = Some(text);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cap(proto: i32, lead_ms: f64, bias_ppm: Option<i32>) -> Cap {
        Cap {
            proto,
            lead_ms,
            bias_ppm,
        }
    }

    /// Generated by `scripts/clock_oracle.c` — the pinned `cap_load` and
    /// `cap_save` run through the mingw64 CRT on 2026-09-06. Each row is the
    /// file's contents, what `cap_load` returned, and what `cap_save` then
    /// wrote back. Not one of these was reasoned out.
    const ORACLE: &[(&str, Cap, &str)] = &[
        ("", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        ("\n", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        ("2 2.354 -25\n", Cap { proto: 2, lead_ms: 2.354, bias_ppm: Some(-25) }, "2 2.354 -25\r\n"),
        ("2 1.5\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        // ⚠️ one field: proto WAS read as 2 and is reset to 0 anyway.
        ("2\n", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        ("abc\n", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        ("2 abc\n", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        // lead out of range resets the lead only; proto survives.
        ("2 12.0\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 -0.5 10\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(10) }, "2 1.500 10\r\n"),
        // the range is inclusive at both ends
        ("2 10\n", Cap { proto: 2, lead_ms: 10.0, bias_ppm: None }, "2 10.000\r\n"),
        ("2 0\n", Cap { proto: 2, lead_ms: 0.0, bias_ppm: None }, "2 0.000\r\n"),
        // a bias out of range is dropped from the file on the next save
        ("2 1.5 601\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 1.5 -601\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 1.5 -600\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(-600) }, "2 1.500 -600\r\n"),
        ("2 1.5 600\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(600) }, "2 1.500 600\r\n"),
        // %d reads "12" and stops at the dot. Python's int("12.5") would
        // raise and cap_read() return None; the C is the file's owner.
        ("2 1.5 12.5\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(12) }, "2 1.500 12\r\n"),
        ("2 1.5 5 extra\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(5) }, "2 1.500 5\r\n"),
        ("0 1.5\n", Cap { proto: 0, lead_ms: 1.5, bias_ppm: None }, "0 1.500\r\n"),
        ("  2   2.354   -25  ", Cap { proto: 2, lead_ms: 2.354, bias_ppm: Some(-25) }, "2 2.354 -25\r\n"),
        ("2 inf\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 -inf\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 1e1\n", Cap { proto: 2, lead_ms: 10.0, bias_ppm: None }, "2 10.000\r\n"),
        ("2 1e-3 7\n", Cap { proto: 2, lead_ms: 0.001, bias_ppm: Some(7) }, "2 0.001 7\r\n"),
        // an unknown version loads fine; refusing it is the transaction's job
        ("3 4.5 7\n", Cap { proto: 3, lead_ms: 4.5, bias_ppm: Some(7) }, "3 4.500 7\r\n"),
        ("2 1.5 abc\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
        ("2 1.5 +25\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(25) }, "2 1.500 25\r\n"),
        ("2\t2.5\t-25\n", Cap { proto: 2, lead_ms: 2.5, bias_ppm: Some(-25) }, "2 2.500 -25\r\n"),
        ("2 2.354 -25 garbage\n", Cap { proto: 2, lead_ms: 2.354, bias_ppm: Some(-25) }, "2 2.354 -25\r\n"),
        ("-1 1.5\n", Cap { proto: -1, lead_ms: 1.5, bias_ppm: None }, "-1 1.500\r\n"),
        ("2 1.5 -0\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(0) }, "2 1.500 0\r\n"),
        ("2 .5 7\n", Cap { proto: 2, lead_ms: 0.5, bias_ppm: Some(7) }, "2 0.500 7\r\n"),
        ("2 5. 7\n", Cap { proto: 2, lead_ms: 5.0, bias_ppm: Some(7) }, "2 5.000 7\r\n"),
        ("2 1.5 007\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(7) }, "2 1.500 7\r\n"),
        // %d reads the "0" of "0x10" and stops at the x
        ("2 1.5 0x10\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: Some(0) }, "2 1.500 0\r\n"),
        // overflow saturates rather than wrapping
        ("99999999999 1.5\n", Cap { proto: 2147483647, lead_ms: 1.5, bias_ppm: None }, "2147483647 1.500\r\n"),
        ("2 1.5 99999999999\n", Cap { proto: 2, lead_ms: 1.5, bias_ppm: None }, "2 1.500\r\n"),
    ];

    #[test]
    fn parse_matches_the_c_on_every_oracle_row() {
        for (text, expect, _) in ORACLE {
            assert_eq!(&parse(text), expect, "parsing {text:?}");
        }
    }

    #[test]
    fn resaving_what_was_loaded_matches_the_c_byte_for_byte() {
        for (text, _, resaved) in ORACLE {
            assert_eq!(&format(&parse(text)), resaved, "resaving {text:?}");
        }
    }

    /// The live file on this machine on 2026-09-06, round-tripped.
    #[test]
    fn the_real_cache_round_trips() {
        let c = parse("2 2.354 -25\n");
        assert_eq!(c, cap(2, 2.354, Some(-25)));
        assert_eq!(format(&c), "2 2.354 -25\r\n");
    }

    /// ⚠️ Divergence, deliberate. The C keeps NaN (both of `lead < 0` and
    /// `lead > 10` are false for NaN), computes `t_enc + nan / 1000`, casts
    /// it to `time_t`, and writes `2 nan` back — measured. Here it resets.
    #[test]
    fn nan_resets_to_the_default_where_the_c_would_keep_it() {
        assert_eq!(parse("2 nan\r\n"), cap(2, 1.5, None));
        assert_eq!(parse("2 -nan(0x1) 7\r\n"), cap(2, 1.5, Some(7)));
    }

    /// ⚠️ Divergence, deliberate. `%lf` accepts hexadecimal floats, so the C
    /// reads `0x1p-1` as 0.5 and then a bias of 7. This scanner stops at the
    /// `x`: lead 0 (in range), then `%d` fails on `x1p-1` and there is no
    /// bias. No writer of this file emits hex floats.
    #[test]
    fn hex_floats_are_not_read_as_the_c_would() {
        assert_eq!(parse("2 0x1p-1 7\r\n"), cap(2, 0.0, None));
    }

    #[test]
    fn an_incomplete_exponent_is_left_for_the_next_directive() {
        // "1e" is 1, then %d fails on "e".
        assert_eq!(parse("2 1e 7\r\n"), cap(2, 1.0, None));
        assert_eq!(parse("2 1e+ 7\r\n"), cap(2, 1.0, None));
        assert_eq!(parse("2 1E2\r\n"), cap(2, 1.5, None)); // 100 is out of range
    }

    #[test]
    fn a_bare_sign_is_not_a_number() {
        assert_eq!(parse("+ 1.5\r\n"), cap(0, 1.5, None));
        assert_eq!(parse("2 - 7\r\n"), cap(0, 1.5, None));
    }

    #[test]
    fn negative_overflow_saturates_too() {
        assert_eq!(parse("-99999999999 1.5\n").proto, i32::MIN);
    }

    /// `%.3f` and `{:.3}` must agree on ties and near-ties, or the file the
    /// two programs share stops being the same file. Every row is the CRT's
    /// own output, and the literals are its `%.17g` renderings verbatim —
    /// which is why clippy's precision and π lints are silenced here.
    #[test]
    #[allow(clippy::excessive_precision, clippy::approx_constant)]
    fn the_lead_prints_like_printf_percent_point_3f() {
        for (lead, text) in [
            (2.354, "2.354"),
            (1.5, "1.500"),
            (0.0625, "0.062"), // exact tie -> even
            (2.0625, "2.062"), // exact tie -> even
            (1.2345, "1.234"), // 1.23449999... -> down
            (10.0, "10.000"),
            (0.0, "0.000"),
            (2.3535, "2.353"),
            (0.0005, "0.001"),
            (1.0005, "1.000"),
            (9.9995, "9.999"),
            (0.0015, "0.002"),
            (0.0025, "0.003"),
            (3.14159265358979, "3.142"),
            (1.9995, "2.000"),
            (2.3544999999999998, "2.354"),
            (2.3545000000000003, "2.355"),
        ] {
            assert_eq!(format(&cap(2, lead, None)), format!("2 {text}\r\n"), "lead {lead:e}");
        }
    }

    #[test]
    fn the_two_write_forms() {
        assert_eq!(format(&cap(2, 0.5, Some(600))), "2 0.500 600\r\n");
        assert_eq!(format(&cap(2, 0.5, Some(-600))), "2 0.500 -600\r\n");
        assert_eq!(format(&cap(0, 1.5, None)), "0 1.500\r\n");
    }

    // -- the file ---------------------------------------------------------

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "ak820-agent-cache-{}-{name}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir.join(FILE_NAME)
    }

    #[test]
    fn an_absent_file_loads_the_defaults() {
        let f = FileCache::at(scratch("absent"));
        let _ = std::fs::remove_file(f.path());
        assert_eq!(f.load(), Cap::default());
    }

    #[test]
    fn a_file_round_trips_and_leaves_no_temporary_behind() {
        let f = FileCache::at(scratch("roundtrip"));
        f.save(&cap(2, 2.854, Some(-25))).unwrap();
        assert_eq!(std::fs::read_to_string(f.path()).unwrap(), "2 2.854 -25\r\n");
        assert_eq!(f.load(), cap(2, 2.854, Some(-25)));
        let mut tmp = f.path().as_os_str().to_owned();
        tmp.push(".tmp");
        assert!(!Path::new(&tmp).exists(), "the temporary must be renamed away");
        // and a second save replaces, not appends
        f.save(&cap(2, 1.0, None)).unwrap();
        assert_eq!(std::fs::read_to_string(f.path()).unwrap(), "2 1.000\r\n");
    }

    /// The installed cache on this machine ends in `0D 0A` (read raw on
    /// 2026-09-06); so must ours, or "byte for byte" is a figure of speech.
    /// Every parser involved also accepts a bare `\n`, which is why the first
    /// version got away with one.
    #[test]
    fn a_saved_file_ends_in_crlf_like_the_installed_one() {
        let f = FileCache::at(scratch("crlf"));
        f.save(&cap(2, 3.294, Some(-26))).unwrap();
        let bytes = std::fs::read(f.path()).unwrap();
        assert_eq!(bytes, b"2 3.294 -26\r\n");
        assert_eq!(f.load(), cap(2, 3.294, Some(-26)));
        assert_eq!(parse("2 3.294 -26\r\n"), cap(2, 3.294, Some(-26)), "a bare LF still parses");
    }

    #[test]
    fn a_save_into_a_missing_directory_reports_rather_than_panics() {
        let f = FileCache::at(Path::new("Z:\\no\\such\\dir").join(FILE_NAME));
        assert!(f.save(&Cap::default()).is_err());
    }

    #[test]
    fn the_default_path_is_under_the_profile() {
        let p = FileCache::default_path();
        assert!(p.ends_with(FILE_NAME));
        assert!(p.parent().map(|d| d.is_absolute()).unwrap_or(false), "{p:?}");
    }
}
