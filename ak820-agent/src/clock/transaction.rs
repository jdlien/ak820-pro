//! The clock transaction — `ak820ctl clock` with no arguments — ported step
//! for step from `time-util-ak820pro/ak820ctl.c` at `7f92889f` and the
//! transcription in `plans/AK820-AGENT-CLOCK-TRANSACTION.md`.
//!
//! Measure (five GETs, keep the minimum round trip), set (with the learned
//! lead, retrying once on `0xFE`), learn the lead from what the board saw at
//! receipt, write the cache, verify with one more GET, and produce the line the
//! Python scheduler parses. Every constant and every gate is the C's.
//!
//! # What runs against what
//!
//! Over [`Wire`] + [`Outstanding`] (the transport, with a scripted fake),
//! [`Host`] (the clock and `localtime`, with scripted instants) and [`Cache`]
//! (the file, in memory). Nothing here touches hardware; the phase-3 gate
//! replays this same function against captured inputs.
//!
//! # ⚠️ Single ownership is part of the contract
//!
//! Correlation rejects a text echo as a clock reply. It cannot reject another
//! process's `RTC_GET_TIME` reply, which is a well-formed `RTC_GET_TIME` reply
//! — see the module header of [`super`]. Exactly one process may run this at a
//! time; a second one silently pairs its board samples with our timestamps.
//!
//! # Where this deliberately differs from the C
//!
//! `xfer()` takes the first report that arrives; [`exchange_prepared`] takes
//! the first report that **answers**. The difference is not academic — it is
//! in the oracle's own log. On 2026-09-05 at 23:20:34 the timekeeper recorded
//!
//! ```text
//! warning: residual +2365966.0 ms exceeds 3U -- lead still calibrating, or a slew is in progress
//! ```
//!
//! That number is `(86400 − 84034.034) × 1000`: a board seconds-of-day of
//! **exactly zero** against a host at 23:20:34.034. An `RTC_SET_TIME_MS`
//! reply has every time field zeroed (`memset(&data[3], 0, 29)` in
//! `hid_protocol.c`), so decoding one as a GET reply yields exactly that. The
//! SET's `xfer()` had consumed a foreign report — the now-playing agent's
//! `TEXT_CLEAR` or `TEXT_PLAYBACK` echo, which carries a zero at `[3]` and so
//! read as "stepped" — and the verify GET then consumed the board's real SET
//! reply, whose channel matched and whose command the C never checks. Two
//! wrong answers, printed with confidence, and nothing learned from either
//! only because `st == 0` happened to close the lead gate. The test
//! `the_oracles_2365966_ms_line_reproduced` pins both halves: what this port
//! does with that traffic, and why the oracle printed what it printed.
//!
//! Also different: a reply carrying `0xFF` in its leading byte — our own
//! command refused as unhandled — aborts here, where the C would read
//! `st = rep[3]` off an echoed request. Unreachable against matching firmware;
//! recorded so nobody restores it as "parity".
//!
//! And the cache is written **after** the verify GET rather than before it.
//! The C saves and then verifies; nothing observes the order, and returning the
//! saved value alongside the outcome is what lets a caller log both.
//!
//! # What a caller inherits
//!
//! A GET that times out leaves an outstanding `RTC_GET_TIME` on the handle,
//! and the next GET — this transaction's or the next one's — is refused until
//! the caller [`resynchronise`]s; a SET that times out does the same for the
//! next SET, after that transaction's GETs have already gone out. This
//! function does not resynchronise itself: whether to spend a quarter second
//! recovering is the scheduler's decision.
//!
//! A verify that fails is not fatal — the SET happened, the cache is written,
//! the line prints `after +0.0` as the C's does — but its error is kept
//! **typed** in the outcome, because [`hid::Error::Stuck`] needs a different
//! recovery from a timeout and a string cannot say which (the phase-2 audit's
//! finding 4). For the same reason, what was discarded on the way accumulates
//! in the caller's `discarded` across the whole transaction, success or
//! failure; a failing request's own discards travel inside its error.
//!
//! [`resynchronise`]: crate::hid::exchange::resynchronise

use std::fmt;
use std::time::Duration;

use super::cache::{Cache, Cap};
use super::host::{self, Host};
use super::lead;
use super::set::{self, SetStatus};
use super::{
    decode, offset_ms, select, BoardTime, Measurement, Sample, CHANNEL, GET_TIME, PROTO_VERSION,
    SET_TIME_MS,
};
use crate::hid::exchange::{exchange_prepared, Outstanding, Wire};
use crate::hid::{self, Drained};
use crate::proto::REPORT_LEN;

/// GETs per measurement burst.
pub const MEASUREMENTS: usize = 5;
/// The SET is sent at most this many times: once, plus one retry on `0xFE`.
pub const SET_ATTEMPTS: usize = 2;

/// Why a transaction produced no outcome. The messages are the C's stderr.
#[derive(Debug)]
pub enum Error {
    /// A GET or SET got no correlated reply, or the handle is unusable. The C's
    /// `rc == -1`: the whole command aborts.
    Hid(hid::Error),
    /// The board reports protocol version 0. The C writes the cache with
    /// `proto 0` and falls back to a whole-second set; the cache write is
    /// reproduced, the legacy set is not — `ak820ctl clock` still does it.
    LegacyFirmware,
    /// Neither 0 nor the version this code speaks. Refuse to act.
    UnknownProtocol(u8),
    /// `0xFF`: the firmware refused validation.
    Rejected,
    /// `0xFE` twice: busy or stale read, both times.
    Busy,
}

impl From<hid::Error> for Error {
    fn from(e: hid::Error) -> Self {
        Error::Hid(e)
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Hid(e) => write!(f, "{e}"),
            Error::LegacyFirmware => write!(
                f,
                "firmware without the sub-second protocol: legacy set -- not ported; ak820ctl clock still does it"
            ),
            Error::UnknownProtocol(v) => {
                write!(f, "unknown RTC protocol version {v} -- refusing to act")
            }
            Error::Rejected => write!(f, "firmware rejected the set (validation)"),
            Error::Busy => write!(f, "firmware busy (stale read) twice -- try again"),
        }
    }
}

impl std::error::Error for Error {}

/// One GET, with everything the C's `get_offset` produces and the raw bytes
/// besides.
#[derive(Clone, Debug)]
pub struct Got {
    pub report: [u8; REPORT_LEN],
    pub board: BoardTime,
    /// `None` when the board's clock is unset — the C's `-2`, which is still
    /// fine to set.
    pub sample: Option<Sample>,
    pub rtt_ms: f64,
    pub t0: f64,
    pub t1: f64,
    /// Host local seconds-of-day at `(t0 + t1) / 2`.
    pub host_mid_sod: f64,
    pub drained: Vec<Drained>,
}

/// One `RTC_GET_TIME`: the C's `get_offset`.
///
/// `t0` is taken inside the transport's prepare step — after the pre-drain,
/// immediately before the write — and `t1` after the correlated reply. The
/// host timestamp used against the board's is their **midpoint**.
pub fn read_once(
    wire: &impl Wire,
    outstanding: &Outstanding,
    host: &impl Host,
    budget: Duration,
) -> Result<Got, hid::Error> {
    let mut t0 = 0.0;
    let reply = exchange_prepared(wire, outstanding, CHANNEL, GET_TIME, budget, |_| {
        t0 = host.now();
        Vec::new()
    })?;
    let t1 = host.now();
    let board = decode(&reply.report).expect("a correlated reply is a whole report");
    let rtt_ms = (t1 - t0) * 1000.0;
    let host_mid_sod = host::seconds_of_day(host, (t0 + t1) / 2.0);
    let sample = board.seconds_of_day().map(|sod| Sample {
        offset_ms: offset_ms(sod, host_mid_sod),
        rtt_ms,
        slewing: board.slewing,
    });
    Ok(Got {
        report: reply.report,
        board,
        sample,
        rtt_ms,
        t0,
        t1,
        host_mid_sod,
        drained: reply.drained,
    })
}

/// One `RTC_SET_TIME_MS`: the C's `send_set_ms`.
///
/// `t_enc` is read inside the prepare step, so the packet's timestamp is as
/// close to its transmission as the transport allows. Each call reads a fresh
/// one — the `0xFE` retry sends a new time, not the old packet again.
fn set_once(
    wire: &impl Wire,
    outstanding: &Outstanding,
    host: &impl Host,
    cap: &Cap,
    budget: Duration,
) -> Result<(set::SetReply, Vec<Drained>), hid::Error> {
    let reply = exchange_prepared(wire, outstanding, CHANNEL, SET_TIME_MS, budget, |_| {
        let t_enc = host.now();
        let target = t_enc + cap.lead_ms / 1000.0;
        let (ts, ms) = set::split_target(target);
        set::body(&host.local(ts), ms, cap.bias_ppm).to_vec()
    })?;
    let decoded = set::decode_reply(&reply.report).expect("a correlated reply is a whole report");
    Ok((decoded, reply.drained))
}

/// A completed transaction: every input to the reported line, plus what the
/// line does not say.
#[derive(Clone, Debug)]
pub struct Outcome {
    /// The min-RTT pick, or `None` when every GET found the clock unset (the
    /// C's `good == 0`).
    pub measurement: Option<Measurement>,
    pub status: SetStatus,
    /// `o'`, from the SET reply.
    pub receipt_offset_ms: f64,
    /// How many SETs went out: 1, or 2 after a `0xFE`.
    pub set_attempts: usize,
    /// The cache as saved: `proto 2`, the lead after learning, the bias as it
    /// was.
    pub cap: Cap,
    /// Whether the lead gate passed. The cache is saved either way.
    pub lead_learned: bool,
    pub cache_saved: Result<(), String>,
    /// The verify GET's offset, when it succeeded and found the clock set.
    pub after_ms: Option<f64>,
    /// The verify GET's round trip, when a reply arrived at all.
    pub verify_rtt_ms: Option<f64>,
    /// Why the verify produced nothing, if it did not. Not fatal in the C
    /// either: the line still prints, with `after +0.0`. Typed, so that a
    /// caller can tell an abandoned handle from a silent board.
    pub verify_error: Option<hid::Error>,
}

/// What the Python timekeeper's `sync()` extracts from the printed output.
///
/// Computed **from the text**, by the same rules as the Python — the regex for
/// `before` and the two substring tests for `slewing` — so that a scheduler
/// port decides on the one-decimal value Python would see, not on the
/// full-precision one. ⚠️ That difference matters at the 60 ms and 400 ms
/// thresholds, and the transaction document says to decide it deliberately.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct Reported {
    /// `float(re.search(r"before ([-+\d.]+) ms", out).group(1))`.
    pub before_ms: Option<f64>,
    /// `"(slewing)" in out and "warning:" not in out`.
    pub slewing: bool,
}

impl Outcome {
    /// `good ? best_off : 0.0`.
    pub fn before_ms(&self) -> f64 {
        self.measurement.map_or(0.0, |m| m.offset_ms)
    }

    /// `rtt_min < 1e9 ? rtt_min : rtt2`: the min-RTT sample's round trip, or
    /// the verify's when there was no good sample, or zero when there was no
    /// verify reply either.
    pub fn rtt_ms(&self) -> f64 {
        match self.measurement {
            Some(m) => m.rtt_ms,
            None => self.verify_rtt_ms.unwrap_or(0.0),
        }
    }

    /// `U`, or zero without a good sample.
    pub fn uncertainty_ms(&self) -> f64 {
        self.measurement.map_or(0.0, |m| m.uncertainty_ms)
    }

    /// The C's warning condition: a verified, stepped set whose residual
    /// exceeds `3U + 3`.
    pub fn warns(&self) -> bool {
        match self.after_ms {
            Some(after) if self.measurement.is_some() && self.status == SetStatus::Stepped => {
                let limit = 3.0 * self.uncertainty_ms() + 3.0;
                after > limit || after < -limit
            }
            _ => false,
        }
    }

    /// The reported line, byte for byte.
    pub fn line(&self) -> String {
        format!(
            "clock set (sub-second): before {:+.1} ms, after {:+.1} ms, rtt {:.1} ms, U ~{:.1} ms, lead now {:.2} ms, bias {}{}",
            self.before_ms(),
            self.after_ms.unwrap_or(0.0),
            self.rtt_ms(),
            self.uncertainty_ms(),
            self.cap.lead_ms,
            if self.cap.bias_ppm.is_some() { "sent" } else { "unknown" },
            if self.status == SetStatus::Slewing { " (slewing)" } else { "" },
        )
    }

    /// Everything the C prints on success: the line, then the warning when it
    /// applies. This is the text the Python side parses.
    pub fn report(&self) -> String {
        let mut out = self.line();
        if self.warns() {
            out.push_str(&format!(
                "\nwarning: residual {:+.1} ms exceeds 3U -- lead still calibrating, or a slew is in progress",
                self.after_ms.unwrap_or(0.0)
            ));
        }
        out
    }

    /// What Python would make of [`Outcome::report`].
    pub fn as_reported(&self) -> Reported {
        let out = self.report();
        let before_ms = out.find("before ").and_then(|i| {
            let rest = &out[i + "before ".len()..];
            let end = rest.find(" ms")?;
            rest[..end].parse().ok()
        });
        Reported {
            before_ms,
            slewing: out.contains("(slewing)") && !out.contains("warning:"),
        }
    }
}

impl fmt::Display for Outcome {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.report())
    }
}

/// `cmd_clock(NULL, 0)`: the whole transaction.
///
/// `budget` is per request, as the C's `hid_read_timeout` is; a transaction is
/// at most eight of them — five GETs, a SET and its one retry, the verify.
///
/// `discarded` collects every report thrown away by a request that succeeded,
/// across the whole transaction, whichever way it ends. It is the caller's
/// because a failed transaction has discards too, and they are the only
/// direct evidence that another process is talking to the same board.
pub fn run(
    wire: &impl Wire,
    outstanding: &Outstanding,
    host: &impl Host,
    cache: &impl Cache,
    budget: Duration,
    discarded: &mut Vec<Drained>,
) -> Result<Outcome, Error> {
    let mut cap = cache.load();
    let drained = discarded;

    // Measure: five GETs, keep the min-RTT sample. No reply aborts; an
    // unexpected version stops the burst; an unset clock is skipped and the
    // set still happens.
    let mut samples = Vec::with_capacity(MEASUREMENTS);
    let mut proto = 0u8;
    for _ in 0..MEASUREMENTS {
        let got = read_once(wire, outstanding, host, budget)?;
        drained.extend(got.drained);
        proto = got.board.proto;
        if proto != PROTO_VERSION {
            break;
        }
        if let Some(sample) = got.sample {
            samples.push(sample);
        }
    }
    if proto == 0 {
        cap.proto = 0;
        let _ = cache.save(&cap);
        return Err(Error::LegacyFirmware);
    }
    if proto != PROTO_VERSION {
        return Err(Error::UnknownProtocol(proto));
    }
    let measurement = select(&samples);

    // Set, with the calibrated lead; retry once on 0xFE.
    let mut attempts = 0;
    let reply = loop {
        attempts += 1;
        let (reply, more) = set_once(wire, outstanding, host, &cap, budget)?;
        drained.extend(more);
        if reply.status != SetStatus::Retry || attempts >= SET_ATTEMPTS {
            break reply;
        }
    };
    match reply.status {
        SetStatus::Reject => return Err(Error::Rejected),
        SetStatus::Retry => return Err(Error::Busy),
        _ => {}
    }
    let receipt_offset_ms = reply.receipt_offset_ms as f64;

    // Learn the outbound lead from what the board saw at receipt, then write
    // the cache with proto 2 whether or not the lead moved.
    let learned = lead::learn(cap.lead_ms, measurement.as_ref(), reply.status, receipt_offset_ms);
    if let Some(lead_ms) = learned {
        cap.lead_ms = lead_ms;
    }
    cap.proto = PROTO_VERSION as i32;

    // Verify. Failure here is reported, not fatal.
    let (after_ms, verify_rtt_ms, verify_error) = match read_once(wire, outstanding, host, budget)
    {
        Ok(got) => {
            drained.extend(got.drained);
            (got.sample.map(|s| s.offset_ms), Some(got.rtt_ms), None)
        }
        Err(e) => (None, None, Some(e)),
    };

    let cache_saved = cache.save(&cap);
    Ok(Outcome {
        measurement,
        status: reply.status,
        receipt_offset_ms,
        set_attempts: attempts,
        cap,
        lead_learned: learned.is_some(),
        cache_saved,
        after_ms,
        verify_rtt_ms,
        verify_error,
    })
}

#[cfg(test)]
mod tests {
    use super::super::cache::MemCache;
    use super::super::host::FakeHost;
    use super::*;
    use crate::hid::exchange::fake::{report, Fake};
    use crate::hid::exchange::DRAIN_LIMIT;
    use crate::proto::WIRE_LEN;

    /// 2026-08-29T00:00:00Z, a Saturday. The fake host sits at UTC so the
    /// SET packet's fields can be checked without a time zone.
    const DAY: f64 = 1_787_961_600.0;

    /// A GET reply at 2026-08-29, `per == pnom == 999` so a count of `n` is a
    /// fraction of `n / 1000`.
    fn get_reply(set: bool, (h, m, s): (u8, u8, u8), cnt: u32, flags: u8) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[..12].copy_from_slice(&[0x07, 0x10, 0x02, set as u8, 26, 8, 29, 6, h, m, s, PROTO_VERSION]);
        r[12..16].copy_from_slice(&cnt.to_le_bytes());
        r[16..18].copy_from_slice(&999u16.to_le_bytes());
        r[18..20].copy_from_slice(&999u16.to_le_bytes());
        r[20] = flags;
        r[25] = 2;
        r
    }

    fn set_reply(status: u8, receipt_offset_ms: i16) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[..4].copy_from_slice(&[0x07, 0x10, 0x03, status]);
        r[4..6].copy_from_slice(&receipt_offset_ms.to_le_bytes());
        r[11] = PROTO_VERSION;
        r
    }

    /// The now-playing agent's `TEXT_CLEAR` echo, as measured on this machine.
    const TEXT_CLEAR_ECHO: &[u8] = &[0x07, 0x12, 0x02, 0x00];

    /// One clean request per reply: the pre-drain's empty read, then the reply.
    fn script(replies: &[Vec<u8>]) -> Vec<Option<Vec<u8>>> {
        let mut reads = Vec::new();
        for r in replies {
            reads.push(None);
            reads.push(report(r));
        }
        reads
    }

    fn budget() -> Duration {
        Duration::from_millis(500)
    }

    /// Five GETs at 11:06:40 with round trips 4, 6, **2**, 5, 7 ms and offsets
    /// +8.0, +9.0, **+8.0**, +7.5, +8.5 ms; a slewed SET reporting `o' = −10`;
    /// a verify at 11:06:41 reading +1.0 ms.
    fn happy_replies() -> Vec<Vec<u8>> {
        vec![
            get_reply(true, (11, 6, 40), 10, 0),
            get_reply(true, (11, 6, 40), 112, 0),
            get_reply(true, (11, 6, 40), 209, 0),
            get_reply(true, (11, 6, 40), 310, 0),
            get_reply(true, (11, 6, 40), 412, 0),
            set_reply(1, -10),
            get_reply(true, (11, 6, 41), 303, 0),
        ]
    }

    /// Two instants per GET, one per SET, in the order the transaction asks.
    fn happy_host() -> FakeHost {
        FakeHost::new(
            0,
            [
                40000.000, 40000.004, // GET 1: rtt 4
                40000.100, 40000.106, // GET 2: rtt 6
                40000.200, 40000.202, // GET 3: rtt 2, the pick
                40000.300, 40000.305, // GET 4: rtt 5
                40000.400, 40000.407, // GET 5: rtt 7
                40001.250, // SET: t_enc
                40001.300, 40001.304, // verify: rtt 4
            ]
            .map(|t| DAY + t),
        )
    }

    const HAPPY_LINE: &str = "clock set (sub-second): before +8.0 ms, after +1.0 ms, rtt 2.0 ms, U ~3.0 ms, lead now 2.85 ms, bias sent (slewing)";

    #[test]
    fn a_clean_transaction_end_to_end() {
        let wire = Fake::new(script(&happy_replies()));
        let host = happy_host();
        let cache = MemCache::with("2 2.354 -25\n");

        let mut discarded = Vec::new();
        let out = run(&wire, &Outstanding::new(), &host, &cache, budget(), &mut discarded).unwrap();

        // Seven commands: five GETs, one SET, one verify GET.
        let written = wire.written();
        assert_eq!(written.len(), 7);
        for w in &written[..5] {
            assert_eq!(&w[..4], &[0x00, 0x07, 0x10, 0x02]);
        }
        assert_eq!(&written[6][..4], &[0x00, 0x07, 0x10, 0x02]);
        assert_eq!(host.unused(), 0, "every scripted instant was consumed");
        assert_eq!(wire.unread(), 0);

        // The SET packet: t_enc + 2.354 ms lead = 11:06:41.252, bias -25.
        assert_eq!(
            &written[5][..16],
            &[0x00, 0x07, 0x10, 0x03, 26, 8, 29, 6, 11, 6, 41, 252, 0, 0, 0xE7, 0xFF]
        );
        assert_eq!(written[5].len(), WIRE_LEN);

        // The measurement: min-RTT sample, U from the spread. Tolerances are
        // a microsecond: an f64 near 1.8e9 seconds resolves 240 ns, and the
        // C's arithmetic has the same grain.
        let m = out.measurement.unwrap();
        assert_eq!(m.good, 5);
        assert!((m.rtt_ms - 2.0).abs() < 1e-3);
        assert!((m.offset_ms - 8.0).abs() < 1e-3, "{}", m.offset_ms);
        assert!((m.uncertainty_ms - 3.0).abs() < 1e-3);
        assert!(!m.was_slewing);

        // The set and the lead: e = -10 + 8 = -2, adj = +0.5.
        assert_eq!(out.status, SetStatus::Slewing);
        assert_eq!(out.receipt_offset_ms, -10.0);
        assert_eq!(out.set_attempts, 1);
        assert!(out.lead_learned);
        assert!((out.cap.lead_ms - 2.854).abs() < 1e-3);
        assert_eq!(out.cap.proto, 2);
        assert_eq!(out.cap.bias_ppm, Some(-25));
        assert_eq!(cache.saved(), vec!["2 2.854 -25\r\n".to_string()]);
        assert_eq!(out.cache_saved, Ok(()));

        // The verify.
        assert!((out.after_ms.unwrap() - 1.0).abs() < 1e-3);
        assert!(out.verify_error.is_none());
        assert!(discarded.is_empty());

        // And the line, byte for byte.
        assert_eq!(out.line(), HAPPY_LINE);
        assert_eq!(out.report(), HAPPY_LINE, "no warning on a slewed set");
        assert_eq!(out.to_string(), HAPPY_LINE);
        assert_eq!(
            out.as_reported(),
            Reported {
                before_ms: Some(8.0),
                slewing: true
            }
        );
    }

    /// The exact line from the oracle's log, reproduced by the formatter:
    /// `2026-09-06 06:14:35 sync (periodic): clock set (sub-second): before
    /// +8.4 ms, after +8.6 ms, rtt 4.0 ms, U ~1.8 ms, lead now 2.35 ms, bias
    /// sent (slewing)`.
    #[test]
    fn the_line_matches_one_the_oracle_actually_logged() {
        let out = Outcome {
            measurement: Some(Measurement {
                offset_ms: 8.42,
                rtt_ms: 3.96,
                uncertainty_ms: 1.8,
                was_slewing: false,
                good: 5,
            }),
            status: SetStatus::Slewing,
            receipt_offset_ms: -9.0,
            set_attempts: 1,
            cap: Cap {
                proto: 2,
                lead_ms: 2.354,
                bias_ppm: Some(-25),
            },
            lead_learned: true,
            cache_saved: Ok(()),
            after_ms: Some(8.55),
            verify_rtt_ms: Some(4.1),
            verify_error: None,
        };
        assert_eq!(
            out.line(),
            "clock set (sub-second): before +8.4 ms, after +8.6 ms, rtt 4.0 ms, U ~1.8 ms, lead now 2.35 ms, bias sent (slewing)"
        );
    }

    /// `%+.1f`, `%.1f` and `%.2f` against the CRT's own output
    /// (`scripts/clock_oracle.c`), including the ties, because Python parses
    /// the result and compares it against 60 and 400.
    #[test]
    fn the_formats_round_like_printf() {
        for (v, plus1, plain1, plain2) in [
            (0.0, "+0.0", "0.0", "0.00"),
            (-0.04, "-0.0", "-0.0", "-0.04"),
            (-0.05, "-0.1", "-0.1", "-0.05"),
            (0.05, "+0.1", "0.1", "0.05"),
            (0.15, "+0.1", "0.1", "0.15"),
            (0.25, "+0.2", "0.2", "0.25"),
            (0.35, "+0.3", "0.3", "0.35"),
            (0.45, "+0.5", "0.5", "0.45"),
            (2.5, "+2.5", "2.5", "2.50"),
            (60.04, "+60.0", "60.0", "60.04"),
            (60.05, "+60.0", "60.0", "60.05"),
            (60.06, "+60.1", "60.1", "60.06"),
            (400.04, "+400.0", "400.0", "400.04"),
            (400.05, "+400.1", "400.1", "400.05"),
            (-400.05, "-400.1", "-400.1", "-400.05"),
            (999.95, "+1000.0", "1000.0", "999.95"),
            (1042.5, "+1042.5", "1042.5", "1042.50"),
            (12.25, "+12.2", "12.2", "12.25"),
            (12.35, "+12.3", "12.3", "12.35"),
            (0.125, "+0.1", "0.1", "0.12"),
            (0.375, "+0.4", "0.4", "0.38"),
            (3.0625, "+3.1", "3.1", "3.06"),
        ] {
            assert_eq!(format!("{v:+.1}"), plus1, "{v:e} with %+.1f");
            assert_eq!(format!("{v:.1}"), plain1, "{v:e} with %.1f");
            assert_eq!(format!("{v:.2}"), plain2, "{v:e} with %.2f");
        }
        for (lead, text) in [
            (2.354, "2.35"),
            (2.355, "2.35"),
            (2.345, "2.35"),
            (1.125, "1.12"),
            (1.135, "1.14"),
            (0.005, "0.01"),
            (0.015, "0.01"),
            (0.025, "0.03"),
            (10.0, "10.00"),
        ] {
            assert_eq!(format!("{lead:.2}"), text, "lead {lead:e}");
        }
    }

    /// ⚠️ The one-decimal coupling. Python compares the *printed* `before`
    /// against 60 and 400: a residual of 60.04 ms prints as `+60.0` and does
    /// not select the fast interval, 60.06 does. A scheduler port must use
    /// `as_reported()`, not the measurement.
    #[test]
    fn python_sees_the_rounded_before_not_the_measured_one() {
        let mut out = Outcome {
            measurement: Some(Measurement {
                offset_ms: 60.04,
                rtt_ms: 4.0,
                uncertainty_ms: 1.0,
                was_slewing: false,
                good: 5,
            }),
            status: SetStatus::Slewing,
            receipt_offset_ms: 0.0,
            set_attempts: 1,
            cap: Cap::default(),
            lead_learned: false,
            cache_saved: Ok(()),
            after_ms: Some(0.0),
            verify_rtt_ms: Some(4.0),
            verify_error: None,
        };
        assert_eq!(out.as_reported().before_ms, Some(60.0));
        out.measurement.as_mut().unwrap().offset_ms = 60.06;
        assert_eq!(out.as_reported().before_ms, Some(60.1));
        out.measurement.as_mut().unwrap().offset_ms = -400.05;
        assert_eq!(out.as_reported().before_ms, Some(-400.1));
    }

    /// Every GET finds the clock unset: still set, nothing to learn from,
    /// `before +0.0`, and the cache is written with proto 2 anyway.
    #[test]
    fn an_unset_clock_is_set_without_learning() {
        let mut replies: Vec<Vec<u8>> = (0..5).map(|_| get_reply(false, (0, 0, 0), 0, 0)).collect();
        replies.push(set_reply(0, 0));
        replies.push(get_reply(true, (11, 6, 41), 303, 0));
        let wire = Fake::new(script(&replies));
        let host = happy_host();
        let cache = MemCache::absent();

        let out = run(&wire, &Outstanding::new(), &host, &cache, budget(), &mut Vec::new()).unwrap();
        assert!(out.measurement.is_none());
        assert_eq!(out.status, SetStatus::Stepped);
        assert!(!out.lead_learned);
        assert_eq!(out.cap.lead_ms, 1.5, "the default lead, untouched");
        assert_eq!(out.cap.bias_ppm, None);
        assert_eq!(cache.saved(), vec!["2 1.500\r\n".to_string()]);
        // the bias byte pair is the sentinel
        assert_eq!(&wire.written()[5][14..16], &[0xFF, 0x7F]);
        assert_eq!(
            out.line(),
            "clock set (sub-second): before +0.0 ms, after +1.0 ms, rtt 4.0 ms, U ~0.0 ms, lead now 1.50 ms, bias unknown"
        );
        assert!(!out.warns(), "no good sample, so no warning either");
    }

    /// `0xFE` once: the SET is rebuilt with a fresh `t_enc` and sent again.
    #[test]
    fn a_stale_read_retries_the_set_once_with_a_fresh_timestamp() {
        let mut replies = happy_replies();
        replies.insert(5, set_reply(0xFE, 0));
        let wire = Fake::new(script(&replies));
        let host = FakeHost::new(
            0,
            [
                40000.000, 40000.004, 40000.100, 40000.106, 40000.200, 40000.202, 40000.300,
                40000.305, 40000.400, 40000.407, //
                40001.250, // first SET: 11:06:41.252
                40001.750, // second SET: 11:06:41.752
                40001.800, 40001.804,
            ]
            .map(|t| DAY + t),
        );
        let cache = MemCache::with("2 2.354 -25\n");

        let out = run(&wire, &Outstanding::new(), &host, &cache, budget(), &mut Vec::new()).unwrap();
        assert_eq!(out.set_attempts, 2);
        let written = wire.written();
        assert_eq!(written.len(), 8);
        let ms_of = |w: &Vec<u8>| u16::from_le_bytes([w[11], w[12]]);
        assert_eq!(ms_of(&written[5]), 252, "first attempt's ms");
        assert_eq!(ms_of(&written[6]), 752, "second attempt carries a new t_enc");
        assert_eq!(out.status, SetStatus::Slewing);
        assert_eq!(cache.saved().len(), 1);
    }

    /// `0xFE` twice: fail, exactly two SETs, no verify, nothing saved.
    #[test]
    fn a_stale_read_twice_fails_without_a_third_attempt() {
        let mut replies = happy_replies();
        replies[5] = set_reply(0xFE, 0);
        replies.insert(6, set_reply(0xFE, 0));
        let wire = Fake::new(script(&replies));
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::Busy), "{err}");
        assert_eq!(err.to_string(), "firmware busy (stale read) twice -- try again");
        let sets = wire.written().iter().filter(|w| w[3] == SET_TIME_MS).count();
        assert_eq!(sets, 2);
        assert_eq!(wire.written().len(), 7, "five GETs and two SETs, no verify");
        assert!(cache.saved().is_empty());
    }

    /// `0xFF`: fail at once, no retry, nothing saved.
    #[test]
    fn a_rejected_set_is_not_retried() {
        let mut replies = happy_replies();
        replies[5] = set_reply(0xFF, 0);
        let wire = Fake::new(script(&replies));
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::Rejected));
        assert_eq!(err.to_string(), "firmware rejected the set (validation)");
        assert_eq!(wire.written().len(), 6);
        assert!(cache.saved().is_empty());
    }

    /// Protocol 0 on the first GET: the burst stops, the cache is written with
    /// `proto 0` exactly as the C does, and the legacy set is left to the C.
    #[test]
    fn legacy_firmware_writes_proto_zero_and_declines() {
        let mut legacy = get_reply(true, (11, 6, 40), 10, 0);
        legacy[11] = 0;
        let wire = Fake::new(script(&[legacy]));
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::LegacyFirmware));
        assert_eq!(wire.written().len(), 1, "one GET, then the burst stops");
        assert_eq!(cache.saved(), vec!["0 2.354 -25\r\n".to_string()]);
    }

    #[test]
    fn an_unknown_protocol_is_refused_without_touching_anything() {
        let mut odd = get_reply(true, (11, 6, 40), 10, 0);
        odd[11] = 3;
        let wire = Fake::new(script(&[odd]));
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::UnknownProtocol(3)));
        assert_eq!(err.to_string(), "unknown RTC protocol version 3 -- refusing to act");
        assert_eq!(wire.written().len(), 1);
        assert!(cache.saved().is_empty());
    }

    /// A GET with no reply aborts the whole command — and leaves the handle
    /// owing an answer, which the caller must resynchronise.
    #[test]
    fn a_silent_get_aborts_and_leaves_a_debt() {
        let replies = happy_replies();
        let mut reads = script(&replies[..2]);
        reads.push(None); // GET 3's drain is clean, and then nothing arrives
        let wire = Fake::new(reads);
        let outstanding = Outstanding::new();
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &outstanding, &happy_host(), &cache, Duration::from_millis(30), &mut Vec::new())
            .unwrap_err();
        assert!(matches!(err, Error::Hid(hid::Error::Timeout { .. })), "{err}");
        assert_eq!(wire.written().len(), 3);
        assert_eq!(outstanding.all(), vec![(0x10, GET_TIME)]);
        assert!(cache.saved().is_empty());
    }

    /// One slewing sample in the burst: the lead is not learned, but the cache
    /// is still written with proto 2 — "regardless of whether the lead moved".
    #[test]
    fn a_slewing_sample_blocks_learning_but_not_the_cache_write() {
        let mut replies = happy_replies();
        replies[1][20] = 0x02;
        let wire = Fake::new(script(&replies));
        let cache = MemCache::with("2 2.354 -25\n");

        let out = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap();
        assert!(out.measurement.unwrap().was_slewing);
        assert!(!out.lead_learned);
        assert_eq!(out.cap.lead_ms, 2.354);
        assert_eq!(cache.saved(), vec!["2 2.354 -25\r\n".to_string()]);
        assert!(out.line().ends_with("lead now 2.35 ms, bias sent (slewing)"));
    }

    /// A stepped set: no learning, no `(slewing)`, and the warning when the
    /// residual exceeds `3U + 3`. Python then reads `slewing = False` even
    /// though nothing else about the line changed.
    #[test]
    fn a_step_with_a_large_residual_warns_and_python_reads_no_slew() {
        let mut replies = happy_replies();
        replies[5] = set_reply(0, 0);
        // verify at 11:06:41.315 against a midpoint of .302: +13.0 ms, over
        // the 3U + 3 = 12.0 limit
        replies[6] = get_reply(true, (11, 6, 41), 315, 0);
        let wire = Fake::new(script(&replies));
        let host = FakeHost::new(
            0,
            [
                40000.000, 40000.004, 40000.100, 40000.106, 40000.200, 40000.202, 40000.300,
                40000.305, 40000.400, 40000.407, 40001.250, 40001.300, 40001.304,
            ]
            .map(|t| DAY + t),
        );
        let cache = MemCache::with("2 2.354 -25\n");

        let out = run(&wire, &Outstanding::new(), &host, &cache, budget(), &mut Vec::new()).unwrap();
        assert_eq!(out.status, SetStatus::Stepped);
        assert!(!out.lead_learned);
        assert!((out.after_ms.unwrap() - 13.0).abs() < 1e-3);
        assert!(out.warns());
        assert_eq!(
            out.report(),
            "clock set (sub-second): before +8.0 ms, after +13.0 ms, rtt 2.0 ms, U ~3.0 ms, lead now 2.35 ms, bias sent\n\
             warning: residual +13.0 ms exceeds 3U -- lead still calibrating, or a slew is in progress"
        );
        assert_eq!(
            out.as_reported(),
            Reported {
                before_ms: Some(8.0),
                slewing: false
            }
        );
        // just inside the limit: no warning
        let mut quiet = out.clone();
        quiet.after_ms = Some(12.0);
        assert!(!quiet.warns());
        quiet.after_ms = Some(-12.0);
        assert!(!quiet.warns());
        quiet.after_ms = Some(-12.01);
        assert!(quiet.warns());
    }

    /// An unknown non-zero status passes the C's `st != 0` gate and learns,
    /// but only `1` prints `(slewing)`.
    #[test]
    fn an_unknown_status_learns_but_does_not_say_slewing() {
        let mut replies = happy_replies();
        replies[5] = set_reply(2, -10);
        let wire = Fake::new(script(&replies));
        let cache = MemCache::with("2 2.354 -25\n");

        let out = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap();
        assert_eq!(out.status, SetStatus::Other(2));
        assert!(out.lead_learned);
        assert!(out.line().ends_with("bias sent"));
        assert!(!out.as_reported().slewing);
    }

    /// The verify GET failing is not fatal: the line prints `after +0.0`, the
    /// error is carried, and the handle owes an answer.
    #[test]
    fn a_failed_verify_still_reports_the_set() {
        let replies = happy_replies();
        let mut reads = script(&replies[..6]);
        reads.push(None); // the verify's drain, then silence
        let wire = Fake::new(reads);
        let outstanding = Outstanding::new();
        let cache = MemCache::with("2 2.354 -25\n");

        let out = run(&wire, &outstanding, &happy_host(), &cache, Duration::from_millis(30), &mut Vec::new()).unwrap();
        assert_eq!(out.after_ms, None);
        assert_eq!(out.verify_rtt_ms, None);
        assert!(matches!(out.verify_error, Some(hid::Error::Timeout { .. })), "{:?}", out.verify_error);
        assert_eq!(outstanding.all(), vec![(0x10, GET_TIME)]);
        assert_eq!(
            out.line(),
            "clock set (sub-second): before +8.0 ms, after +0.0 ms, rtt 2.0 ms, U ~3.0 ms, lead now 2.85 ms, bias sent (slewing)"
        );
        assert!(!out.warns());
        assert_eq!(cache.saved().len(), 1, "the cache is written regardless");
    }

    /// No good sample and a verify with a reply: the printed `rtt` is the
    /// verify's (`rtt_min < 1e9 ? rtt_min : rtt2`).
    #[test]
    fn without_a_good_sample_the_printed_rtt_is_the_verifys() {
        let mut replies: Vec<Vec<u8>> = (0..5).map(|_| get_reply(false, (0, 0, 0), 0, 0)).collect();
        replies.push(set_reply(0, 0));
        replies.push(get_reply(true, (11, 6, 41), 303, 0));
        let wire = Fake::new(script(&replies));
        let out = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::absent(), budget(), &mut Vec::new()).unwrap();
        assert!((out.rtt_ms() - 4.0).abs() < 1e-3);
        // and with no verify reply either, zero
        let mut reads = script(&replies[..6]);
        reads.push(None);
        let wire = Fake::new(reads);
        let out = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::absent(), Duration::from_millis(30), &mut Vec::new()).unwrap();
        assert_eq!(out.rtt_ms(), 0.0);
    }

    /// The C ignores the verify reply's protocol version; so does this.
    #[test]
    fn the_verifys_protocol_version_is_not_checked() {
        let mut replies = happy_replies();
        replies[6][11] = 0;
        let wire = Fake::new(script(&replies));
        let out = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::absent(), budget(), &mut Vec::new()).unwrap();
        assert!(out.after_ms.is_some());
    }

    /// A failed cache write is reported, not fatal — and the outcome still
    /// carries the lead that should have been saved.
    #[test]
    fn a_failed_cache_write_is_reported() {
        let wire = Fake::new(script(&happy_replies()));
        let cache = MemCache::with("2 2.354 -25\n").failing_saves();
        let out = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap();
        assert_eq!(out.cache_saved, Err("disk full".into()));
        assert!((out.cap.lead_ms - 2.854).abs() < 1e-3);
    }

    /// A SET with no reply aborts too, and leaves a SET debt: the next
    /// transaction's five GETs are a different question and go through, but
    /// its SET is refused until the handle is resynchronised — so a lost SET
    /// cannot be followed by one whose reply might be the old one's.
    #[test]
    fn a_silent_set_leaves_a_debt_that_refuses_the_next_set() {
        let replies = happy_replies();
        let mut reads = script(&replies[..5]);
        reads.push(None); // the SET's drain, then silence
        let wire = Fake::new(reads);
        let outstanding = Outstanding::new();
        let cache = MemCache::with("2 2.354 -25\n");

        let err = run(&wire, &outstanding, &happy_host(), &cache, Duration::from_millis(30), &mut Vec::new())
            .unwrap_err();
        assert!(matches!(err, Error::Hid(hid::Error::Timeout { .. })), "{err}");
        assert_eq!(outstanding.all(), vec![(0x10, SET_TIME_MS)]);
        assert!(cache.saved().is_empty(), "nothing is learned from a set that got no answer");

        let again = Fake::new(script(&happy_replies()));
        let err = run(&again, &outstanding, &happy_host(), &cache, budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::Hid(hid::Error::Unresolved { command: SET_TIME_MS, .. })), "{err}");
        assert_eq!(again.written().len(), 5, "the GETs went out; the SET was refused");
        assert!(cache.saved().is_empty());

        // and once resynchronised, the same script runs clean
        let quiet = Fake::new(vec![None, None]);
        crate::hid::exchange::resynchronise(&quiet, &outstanding, budget()).unwrap();
        let third = Fake::new(script(&happy_replies()));
        assert!(run(&third, &outstanding, &happy_host(), &cache, budget(), &mut Vec::new()).is_ok());
    }

    /// The phase-2 audit's finding 4: a verify that fails with the one error
    /// reopening cannot fix must say so in a type, not a string. The set
    /// happened and the cache is written, as the C would; the scheduler then
    /// needs to know the handle is gone for good.
    #[test]
    fn a_stuck_verify_keeps_its_typed_error() {
        // five GETs and the SET are twelve reads; the verify's first read
        // (its pre-drain) is where the cancellation fails to land
        let wire = Fake::new(script(&happy_replies())).stuck_after(12);
        let cache = MemCache::with("2 2.354 -25\n");
        let out = run(&wire, &Outstanding::new(), &happy_host(), &cache, budget(), &mut Vec::new()).unwrap();
        assert!(matches!(out.verify_error, Some(hid::Error::Stuck)), "{:?}", out.verify_error);
        assert_eq!(out.after_ms, None);
        assert_eq!(cache.saved().len(), 1);
        assert!(out.line().contains("after +0.0 ms"));
    }

    /// Discards from requests that succeeded survive a later failure: they
    /// are the only direct evidence of another process on the board, and a
    /// failed transaction is exactly when that evidence matters.
    #[test]
    fn discards_accumulate_across_a_failed_transaction() {
        let replies = happy_replies();
        let mut reads = vec![None, report(TEXT_CLEAR_ECHO), report(&replies[0])]; // GET 1, with an echo
        reads.push(None);
        reads.push(report(&replies[1])); // GET 2 clean
        reads.push(None); // GET 3: silence
        let wire = Fake::new(reads);
        let mut discarded = Vec::new();
        let err = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::absent(), Duration::from_millis(30), &mut discarded)
            .unwrap_err();
        assert!(matches!(err, Error::Hid(hid::Error::Timeout { .. })));
        assert_eq!(discarded.len(), 1, "GET 1's echo is still on record");
        assert!(matches!(discarded[0], Drained::Foreign(_)));
    }

    /// A dirty queue refuses the request before anything is sent, and the
    /// transaction reports it rather than measuring through it.
    #[test]
    fn a_flooded_queue_refuses_before_the_first_get() {
        let wire = Fake::new(vec![report(TEXT_CLEAR_ECHO); DRAIN_LIMIT + 1]);
        let err = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::absent(), budget(), &mut Vec::new()).unwrap_err();
        assert!(matches!(err, Error::Hid(hid::Error::Dirty { .. })), "{err}");
        assert!(wire.written().is_empty());
    }

    /// ⚠️ The oracle's 2026-09-05 23:20:34 line, in two halves.
    ///
    /// **What the port does.** The now-playing agent's `TEXT_CLEAR` echo lands
    /// between our SET and its reply. It is drained, the real SET reply is
    /// taken, and the verify then gets the real verify reply: a sane line.
    ///
    /// **What the oracle did.** `xfer()` returned the echo as the SET reply
    /// (`rep[3] == 0`: "stepped", `o' = 0`), and the board's real SET reply —
    /// same channel, command unchecked — as the verify. Decoding a SET reply as
    /// a GET reads a set clock at 00:00:00 with `cnt = per = pnom = 0`: a
    /// seconds-of-day of exactly zero, which against a host at 23:20:34.034
    /// is `+2365966.0 ms`. That is the logged number, to the decimal.
    #[test]
    fn the_oracles_2365966_ms_line_reproduced() {
        // the port
        let replies = happy_replies();
        let mut reads = script(&replies[..5]);
        reads.push(None);
        reads.push(report(TEXT_CLEAR_ECHO));
        reads.push(report(&replies[5]));
        reads.extend(script(&replies[6..]));
        let wire = Fake::new(reads);
        let mut discarded = Vec::new();
        let out = run(&wire, &Outstanding::new(), &happy_host(), &MemCache::with("2 2.354 -25\n"), budget(), &mut discarded).unwrap();
        assert_eq!(discarded.len(), 1, "the echo was discarded, not decoded");
        assert!(matches!(discarded[0], Drained::Foreign(_)));
        assert_eq!(out.line(), HAPPY_LINE);

        // the oracle
        let board = decode(&set_reply(1, -10)).unwrap();
        assert!(board.set, "the slewing status reads as `set`");
        assert_eq!(board.seconds_of_day(), Some(0.0));
        let host_sod = 23.0 * 3600.0 + 20.0 * 60.0 + 34.0 + 0.034;
        let after = offset_ms(0.0, host_sod);
        assert_eq!(format!("{after:+.1}"), "+2365966.0");
        // and the echo it took as the SET reply: a "step" with o' = 0, which
        // is why nothing was learned from it
        let mut echo = vec![0u8; REPORT_LEN];
        echo[..4].copy_from_slice(TEXT_CLEAR_ECHO);
        assert_eq!(set::decode_reply(&echo).unwrap().status, SetStatus::Stepped);
    }
}
