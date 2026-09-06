//! Reading the board's clock, and the arithmetic that turns it into an offset.
//!
//! Port of the measurement half of `time-util-ak820pro/ak820ctl.c`, pinned at
//! `7f92889f` and transcribed in
//! [`AK820-AGENT-CLOCK-TRANSACTION.md`](../../../plans/AK820-AGENT-CLOCK-TRANSACTION.md).
//!
//! ⚠️ **The oracle is Python *plus* this C utility, and most of the precision
//! lives in the C.** A port could reproduce every scheduling decision in the
//! Python parity document perfectly and still inject milliseconds on every
//! sync, because all of the arithmetic below is here rather than there. So this
//! module reproduces the C expression by expression, and where an expression
//! looks wrong, the test next to it says why it is not.
//!
//! ## ⚠️ Correlation cannot make concurrent clock reads safe
//!
//! Measured 2026-09-05: a foreign `RTC_GET_TIME` reply is a **well-formed**
//! `RTC_GET_TIME` reply — right channel, right command, protocol version 2,
//! plausible fields. Nothing in the bytes distinguishes it from the answer to
//! our own GET, so taking one pairs another process's board sample with our
//! timestamps: a wrong offset with a plausible RTT, which can then *win* the
//! minimum-RTT selection precisely because it did not include our round trip.
//!
//! Exactly one process may run clock transactions at a time. That, not the
//! framing, is what makes the clock correct.
//!
//! ## Layout
//!
//! - here: the GET reply, the fraction formula, `wrap_day`, min-RTT selection,
//!   and the `clock --read` rendering
//! - [`host`]: the wall clock and `localtime`, behind a trait
//! - [`set`]: the SET packet and its reply
//! - [`lead`]: the outbound-lead learner
//! - [`cache`]: `$HOME/.ak820ctl-cap`, byte for byte
//! - [`transaction`]: the whole of `ak820ctl clock`, over the fake wire

pub mod cache;
pub mod host;
pub mod lead;
pub mod set;
pub mod transaction;

use crate::proto::{Channel, REPORT_LEN};

pub const CHANNEL: Channel = Channel::Rtc;
pub const GET_TIME: u8 = 0x02;
pub const SET_TIME_MS: u8 = 0x03;

/// The only protocol version this code understands. Anything else means
/// refusing to act rather than guessing at a layout.
pub const PROTO_VERSION: u8 = 2;

/// Seconds in half a day — the wrap point for a same-day offset.
const HALF_DAY: f64 = 43200.0;
const DAY: f64 = 86400.0;

/// A decoded `RTC_GET_TIME` reply.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct BoardTime {
    /// `false` means the board's clock has never been set. Still fine to set.
    pub set: bool,
    pub year: u16,
    pub month: u8,
    pub day: u8,
    pub weekday: u8,
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
    pub proto: u8,
    /// The RTC's sub-second counter.
    pub seccnt: u32,
    /// Period register currently in force. Shortened for one second after a
    /// phase correction.
    pub active_period: u16,
    /// Steady-state period. Zero means "same as active", which is how older
    /// firmware reports it.
    pub nominal_period: u16,
    /// The board is slewing, so it is moving ~20 ms/s and is not a calibration
    /// sample.
    pub slewing: bool,
    /// The whole flags byte, as `clock --read` prints it: bit 0 host-synced,
    /// bit 1 slewing, bit 2 acquisition done, bit 3 PCF backoff, bit 4 stale.
    pub flags: u8,
    /// The offset the firmware saw at its last host set, ms.
    pub last_host_offset_ms: i16,
    /// The SOF bias the firmware is applying, ppm.
    pub bias_in_use_ppm: i16,
    /// The firmware's reference state; `2` is what the Python bias learner
    /// requires before it will learn.
    pub ref_state: u8,
    /// Minutes since the last host set, saturating at 255.
    pub sync_age_min: u8,
    /// Incremented when the SOF reference restarts; the bias seed resets on it.
    pub sof_epoch: u8,
    /// USB frames counted since the epoch began — the bias seed's numerator.
    pub sof_frames_total: u32,
}

/// Decode a 32-byte `RTC_GET_TIME` reply.
///
/// Byte offsets are the firmware's (`rtc_status_fill`, page 1), and every
/// multi-byte field here is **little-endian** — unlike the flash channel's
/// big-endian ids. The whole report is required: the C reads up to `[31]`.
pub fn decode(report: &[u8]) -> Option<BoardTime> {
    if report.len() < REPORT_LEN {
        return None;
    }
    Some(BoardTime {
        set: report[3] != 0,
        year: 2000 + report[4] as u16,
        month: report[5],
        day: report[6],
        weekday: report[7],
        hour: report[8],
        minute: report[9],
        second: report[10],
        proto: report[11],
        seccnt: u32::from_le_bytes([report[12], report[13], report[14], report[15]]),
        active_period: u16::from_le_bytes([report[16], report[17]]),
        nominal_period: u16::from_le_bytes([report[18], report[19]]),
        slewing: report[20] & 0x02 != 0,
        flags: report[20],
        last_host_offset_ms: i16::from_le_bytes([report[21], report[22]]),
        bias_in_use_ppm: i16::from_le_bytes([report[23], report[24]]),
        ref_state: report[25],
        sync_age_min: report[26],
        sof_epoch: report[27],
        sof_frames_total: u32::from_le_bytes([report[28], report[29], report[30], report[31]]),
    })
}

/// `ak820ctl clock --read`'s stdout for a decoded reply, byte for byte.
///
/// `measured` is `(offset_ms, rtt_ms)` when the clock was set, which is what
/// decides whether the second and third lines are printed; the C prints the
/// `device` line first either way and then says `device clock not set`.
///
/// The Python timekeeper parses this (`read_status`): `nominal`, `offset
/// board-host`, `ref_state`, `sof_epoch`/`sof_frames_total` and `flags`. So the
/// format is an interface, and the phase-2 gate compares this rendering of
/// captured replies against the C's.
pub fn read_lines(board: &BoardTime, measured: Option<(f64, f64)>) -> String {
    let mut out = format!(
        "device {:04}-{:02}-{:02} {:02}:{:02}:{:02}{:+.3}  (cnt {} / period {}, nominal {})\n",
        board.year,
        board.month,
        board.day,
        board.hour,
        board.minute,
        board.second,
        board.fraction_as_printed(),
        board.seccnt,
        board.active_period,
        board.nominal_period
    );
    match measured {
        None => out.push_str("device clock not set\n"),
        Some((offset_ms, rtt_ms)) => {
            out.push_str(&format!(
                "offset board-host {offset_ms:+.1} ms  rtt {rtt_ms:.1} ms  flags 0x{:02x}  ref_state {}  sync_age {} min  last_host_offset {} ms\n",
                board.flags, board.ref_state, board.sync_age_min, board.last_host_offset_ms
            ));
            out.push_str(&format!(
                "sof_epoch {}  sof_frames_total {}  bias_in_use {} ppm\n",
                board.sof_epoch, board.sof_frames_total, board.bias_in_use_ppm
            ));
        }
    }
    out
}

impl BoardTime {
    /// The fraction as `cmd_clock_read` **prints** it, which is not quite
    /// [`BoardTime::fraction`]: the C recomputes it inline without the
    /// `nominal == 0 → active` fallback that `board_sod` applies. On firmware
    /// reporting no nominal period the printed fraction would be nonsense while
    /// the offset on the next line stayed right. This firmware always reports
    /// one, so the two agree; the quirk is reproduced so the lines still match
    /// if that ever changes.
    pub fn fraction_as_printed(&self) -> f64 {
        1.0 - (self.active_period as f64 + 1.0 - self.seccnt as f64)
            / (self.nominal_period as f64 + 1.0)
    }

    /// The fraction of the current second that has elapsed.
    ///
    /// ⚠️ **This is not the obvious formula, and the obvious one is wrong.**
    ///
    /// ```text
    /// frac = 1 - ((active + 1) - cnt) / (nominal + 1)
    /// ```
    ///
    /// It is the cycles *remaining* to the next boundary, measured in
    /// **nominal** seconds. In steady state (`active == nominal`) it reduces to
    /// `cnt / (P + 1)`, which is why the naive version looks right — but inside
    /// the **shortened first period after a phase set** the naive
    /// `cnt / (active + 1)` reads the fraction of the *remaining window*
    /// instead of the fraction of a second.
    ///
    /// That mistake is not hypothetical: it produced an "after" residual
    /// growing to **−790 ms across ten syncs**. Port this expression literally.
    pub fn fraction(&self) -> f64 {
        let per = self.active_period as f64;
        // Zero means the firmware does not report a separate nominal period.
        let nominal = if self.nominal_period == 0 {
            self.active_period
        } else {
            self.nominal_period
        } as f64;
        1.0 - (per + 1.0 - self.seccnt as f64) / (nominal + 1.0)
    }

    /// Local seconds-of-day on the board, fractional. `None` if unset — **and
    /// `None` if negative**, which the C's `get_offset` reads the same way
    /// (`board_sod() < 0` → `-2`, "clock unset": skipped, and still fine to
    /// set).
    ///
    /// Negative is reachable, not theoretical: during a slowing slew the
    /// firmware programs an active period *longer* than the nominal one
    /// (`rtc.c`), so the fraction formula goes below zero for a small count,
    /// and at `00:00:00` there is nothing to add it to. The phase-2 audit's
    /// finding 2; the first version checked only the set flag and reported a
    /// −21.9 ms sample the C would have skipped.
    pub fn seconds_of_day(&self) -> Option<f64> {
        if !self.set {
            return None;
        }
        let sod = self.hour as f64 * 3600.0 + self.minute as f64 * 60.0 + self.second as f64
            + self.fraction();
        (sod >= 0.0).then_some(sod)
    }

    /// Is this a version we are willing to act on?
    pub fn understood(&self) -> bool {
        self.proto == PROTO_VERSION
    }
}

/// Fold a seconds-of-day difference into ±half a day.
///
/// ⚠️ Midnight is handled here rather than by date arithmetic, which is why
/// both sides can be plain seconds-of-day. A board at 23:59:59 and a host at
/// 00:00:01 differ by −86398 seconds of day, which is +2 seconds of real time.
///
/// Reproduces the C exactly, including that it applies each correction at most
/// once — a difference outside ±86400 cannot arise from two same-day clocks and
/// is not something to paper over.
pub fn wrap_day(d: f64) -> f64 {
    let mut d = d;
    if d > HALF_DAY {
        d -= DAY;
    }
    if d < -HALF_DAY {
        d += DAY;
    }
    d
}

/// One GET's worth of measurement.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct Sample {
    /// Board minus host, milliseconds. Positive means the board is ahead.
    pub offset_ms: f64,
    pub rtt_ms: f64,
    pub slewing: bool,
}

/// Board minus host, in milliseconds, for one transaction.
///
/// ⚠️ `host_sod_mid` must be the seconds-of-day at the **midpoint** of the
/// transaction, not at either end. This is NTP arithmetic with `T3 == T2`: the
/// board samples its clock somewhere inside our round trip, and the midpoint is
/// the best unbiased estimate of when. Using `t0` or `t1` biases every offset by
/// half the round trip — currently 2.5–9 ms on this board.
pub fn offset_ms(board_sod: f64, host_sod_mid: f64) -> f64 {
    wrap_day(board_sod - host_sod_mid) * 1000.0
}

/// Local seconds-of-day for a `SystemTime`, fractional.
///
/// **Local**, deliberately: the board holds local time, so DST and timezone
/// come from the host and midnight wrap is [`wrap_day`]'s job rather than date
/// arithmetic's.
pub fn host_seconds_of_day(hour: u32, minute: u32, second: u32, subsec: f64) -> f64 {
    hour as f64 * 3600.0 + minute as f64 * 60.0 + second as f64 + subsec
}

/// The pick from a burst of GETs.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct Measurement {
    /// The offset from the sample with the lowest round trip.
    pub offset_ms: f64,
    /// That sample's round trip.
    pub rtt_ms: f64,
    /// `(rtt_max - rtt_min) / 2 + 0.5` — how much of the offset is transport
    /// noise rather than clock error.
    pub uncertainty_ms: f64,
    /// Any sample seeing a slew disqualifies the whole burst from calibrating
    /// the outbound lead: a slewing board moves 20 ms/s and is not a
    /// calibration sample.
    pub was_slewing: bool,
    pub good: usize,
}

/// Choose the sample to trust from a burst.
///
/// **Minimum round trip wins**, which is the standard NTP heuristic and the
/// right one here: transport delay can only ever *add* to the measured trip, so
/// the quickest exchange is the one least contaminated by it. Averaging would
/// fold every scheduling hiccup into the answer.
pub fn select(samples: &[Sample]) -> Option<Measurement> {
    let mut best: Option<Sample> = None;
    // Zero, as the C initialises it — not negative infinity. The two differ
    // only when every round trip is negative, which a wall-clock step during
    // the burst can produce, and then the C's `U` is what the oracle prints.
    let mut rtt_max = 0.0f64;
    let mut was_slewing = false;
    let mut good = 0usize;

    for s in samples {
        good += 1;
        was_slewing |= s.slewing;
        if s.rtt_ms > rtt_max {
            rtt_max = s.rtt_ms;
        }
        if best.is_none_or(|b| s.rtt_ms < b.rtt_ms) {
            best = Some(*s);
        }
    }

    let best = best?;
    Some(Measurement {
        offset_ms: best.offset_ms,
        rtt_ms: best.rtt_ms,
        uncertainty_ms: (rtt_max - best.rtt_ms) / 2.0 + 0.5,
        was_slewing,
        good,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A GET reply built field by field, so a test says what it is varying.
    fn reply(
        set: bool,
        (h, m, s): (u8, u8, u8),
        cnt: u32,
        active: u16,
        nominal: u16,
        slewing: bool,
    ) -> Vec<u8> {
        let mut r = vec![0u8; 32];
        r[0] = 0x07;
        r[1] = 0x10;
        r[2] = 0x02;
        r[3] = set as u8;
        r[4] = 26; // 2026
        r[5] = 9;
        r[6] = 6;
        r[7] = 0;
        r[8] = h;
        r[9] = m;
        r[10] = s;
        r[11] = PROTO_VERSION;
        r[12..16].copy_from_slice(&cnt.to_le_bytes());
        r[16..18].copy_from_slice(&active.to_le_bytes());
        r[18..20].copy_from_slice(&nominal.to_le_bytes());
        r[20] = if slewing { 0x02 } else { 0 };
        // the status tail, page 1 of rtc_status_fill
        r[21..23].copy_from_slice(&(-7i16).to_le_bytes()); // last_host_offset
        r[23..25].copy_from_slice(&(-25i16).to_le_bytes()); // bias in use
        r[25] = 2; // ref_state
        r[26] = 4; // sync_age_min
        r[27] = 3; // sof_epoch
        r[28..32].copy_from_slice(&123_456_789u32.to_le_bytes());
        r
    }

    #[test]
    fn decodes_every_field() {
        let b = decode(&reply(true, (13, 45, 7), 1234, 32767, 32768, false)).unwrap();
        assert!(b.set);
        assert_eq!((b.year, b.month, b.day), (2026, 9, 6));
        assert_eq!((b.hour, b.minute, b.second), (13, 45, 7));
        assert_eq!(b.proto, PROTO_VERSION);
        assert_eq!(b.seccnt, 1234);
        assert_eq!(b.active_period, 32767);
        assert_eq!(b.nominal_period, 32768);
        assert!(!b.slewing);
        assert!(b.understood());
        assert_eq!(b.flags, 0);
        assert_eq!(b.last_host_offset_ms, -7);
        assert_eq!(b.bias_in_use_ppm, -25);
        assert_eq!(b.ref_state, 2);
        assert_eq!(b.sync_age_min, 4);
        assert_eq!(b.sof_epoch, 3);
        assert_eq!(b.sof_frames_total, 123_456_789);
    }

    #[test]
    fn a_short_report_decodes_to_nothing() {
        assert!(decode(&[0u8; 20]).is_none());
        assert!(decode(&[0u8; 31]).is_none(), "the C reads up to [31]");
        assert!(decode(&[]).is_none());
    }

    #[test]
    fn the_signed_tail_fields_are_signed() {
        let mut r = reply(true, (0, 0, 0), 0, 1, 1, false);
        r[21..23].copy_from_slice(&1042i16.to_le_bytes());
        r[23..25].copy_from_slice(&(-600i16).to_le_bytes());
        let b = decode(&r).unwrap();
        assert_eq!(b.last_host_offset_ms, 1042);
        assert_eq!(b.bias_in_use_ppm, -600);
    }

    /// The `--read` rendering the Python timekeeper parses, for a synthetic
    /// reply. Captured replies are compared against the C harness in
    /// `read_lines_match_the_c_for_captured_replies`.
    #[test]
    fn read_lines_render_like_the_c() {
        let b = decode(&reply(true, (13, 45, 7), 1234, 32767, 32768, true)).unwrap();
        let text = read_lines(&b, Some((-5.64, 4.02)));
        assert_eq!(
            text,
            "device 2026-09-06 13:45:07+0.038  (cnt 1234 / period 32767, nominal 32768)\n\
             offset board-host -5.6 ms  rtt 4.0 ms  flags 0x02  ref_state 2  sync_age 4 min  last_host_offset -7 ms\n\
             sof_epoch 3  sof_frames_total 123456789  bias_in_use -25 ppm\n"
        );
        let unset = decode(&reply(false, (0, 0, 0), 0, 32767, 32768, false)).unwrap();
        assert_eq!(
            read_lines(&unset, None),
            "device 2026-09-06 00:00:00+0.000  (cnt 0 / period 32767, nominal 32768)\n\
             device clock not set\n"
        );
    }

    /// ⚠️ **The phase-2 gate: identical captured replies decode identically.**
    ///
    /// Three consecutive `RTC_GET_TIME` replies captured with
    /// `ak820 clock --raw` on 2026-09-06 06:45:52–54, with the host midpoint
    /// and round trip that command printed, rendered by the pinned C
    /// (`scripts/clock_oracle.c decode`, which is `cmd_clock_read` verbatim).
    /// The Rust rendering of the same 32 bytes must match to the byte. The
    /// fourth row is the board's SET reply decoded as a GET reply — the bytes
    /// behind the oracle's `+2365966.0 ms` line; see `transaction`.
    ///
    /// The host values are `--raw`'s `{:.17}` output verbatim, so that the C
    /// and this test parse the identical decimal; hence the precision lint.
    #[test]
    #[allow(clippy::excessive_precision)]
    fn read_lines_match_the_c_for_captured_replies() {
        const CAPTURED: &[(&str, f64, f64, &str)] = &[
            (
                "07 10 02 01 1A 09 06 07 06 2D 34 02 5B 1F 00 00 8B 82 8B 82 05 0A 00 E6 FF 02 01 B5 37 C5 E9 02",
                24352.23825216293334961,
                4.14156913757324219,
                "device 2026-09-06 06:45:52+0.240  (cnt 8027 / period 33419, nominal 33419)\n\
                 offset board-host +1.9 ms  rtt 4.1 ms  flags 0x05  ref_state 2  sync_age 1 min  last_host_offset 10 ms\n\
                 sof_epoch 181  sof_frames_total 48874807  bias_in_use -26 ppm\n",
            ),
            (
                "07 10 02 01 1A 09 06 07 06 2D 35 02 E1 23 00 00 8B 82 8B 82 05 0A 00 E6 FF 02 01 B5 1F C9 E9 02",
                24353.27172446250915527,
                5.23328781127929688,
                "device 2026-09-06 06:45:53+0.275  (cnt 9185 / period 33419, nominal 33419)\n\
                 offset board-host +3.1 ms  rtt 5.2 ms  flags 0x05  ref_state 2  sync_age 1 min  last_host_offset 10 ms\n\
                 sof_epoch 181  sof_frames_total 48875807  bias_in_use -26 ppm\n",
            ),
            (
                "07 10 02 01 1A 09 06 07 06 2D 36 02 F7 29 00 00 8B 82 8B 82 05 0A 00 E6 FF 02 01 B5 07 CD E9 02",
                24354.31800699234008789,
                6.66928291320800781,
                "device 2026-09-06 06:45:54+0.321  (cnt 10743 / period 33419, nominal 33419)\n\
                 offset board-host +3.4 ms  rtt 6.7 ms  flags 0x05  ref_state 2  sync_age 1 min  last_host_offset 10 ms\n\
                 sof_epoch 181  sof_frames_total 48876807  bias_in_use -26 ppm\n",
            ),
            (
                "07 10 03 01 F6 FF 00 00 00 00 00 02 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
                84034.034,
                4.0,
                "device 2246-255-00 00:00:00+0.000  (cnt 0 / period 0, nominal 0)\n\
                 offset board-host +2365966.0 ms  rtt 4.0 ms  flags 0x00  ref_state 0  sync_age 0 min  last_host_offset 0 ms\n\
                 sof_epoch 0  sof_frames_total 0  bias_in_use 0 ppm\n",
            ),
            // The phase-2 audit's finding 2: 00:00:00, count 100, active
            // period 33422 against a nominal 32767 -- a negative fraction the
            // C reports as unset.
            (
                "07 10 02 01 1A 09 06 00 00 00 00 02 64 00 00 00 8E 82 FF 7F 00 00 00 00 00 00 00 00 00 00 00 00",
                0.005,
                4.0,
                "device 2026-09-06 00:00:00-0.017  (cnt 100 / period 33422, nominal 32767)\n\
                 device clock not set\n",
            ),
        ];
        for (hex, host_mid_sod, rtt_ms, expect) in CAPTURED {
            let raw: Vec<u8> = hex
                .split(' ')
                .map(|h| u8::from_str_radix(h, 16).unwrap())
                .collect();
            let board = decode(&raw).unwrap();
            let measured = board
                .seconds_of_day()
                .map(|sod| (offset_ms(sod, *host_mid_sod), *rtt_ms));
            assert_eq!(&read_lines(&board, measured), expect, "reply {hex}");
        }
    }

    /// The printed fraction skips `board_sod`'s zero-nominal fallback. Pinned
    /// so the rendering keeps matching the C rather than being "fixed".
    #[test]
    fn the_printed_fraction_keeps_the_cs_quirk() {
        let b = decode(&reply(true, (0, 0, 0), 9000, 32767, 0, false)).unwrap();
        assert!((b.fraction() - 9000.0 / 32768.0).abs() < 1e-12);
        assert!((b.fraction_as_printed() - (1.0 - (32768.0 - 9000.0))).abs() < 1e-9);
        let same = decode(&reply(true, (0, 0, 0), 9000, 32767, 32767, false)).unwrap();
        assert_eq!(same.fraction(), same.fraction_as_printed());
    }

    #[test]
    fn an_unset_clock_has_no_seconds_of_day() {
        let b = decode(&reply(false, (0, 0, 0), 0, 32767, 0, false)).unwrap();
        assert!(!b.set);
        assert_eq!(b.seconds_of_day(), None);
    }

    #[test]
    fn the_slewing_bit_is_bit_one() {
        assert!(decode(&reply(true, (0, 0, 0), 0, 1, 1, true)).unwrap().slewing);
        let mut r = reply(true, (0, 0, 0), 0, 1, 1, false);
        r[20] = 0x01; // some other flag must NOT read as slewing
        assert!(!decode(&r).unwrap().slewing);
        r[20] = 0x03;
        assert!(decode(&r).unwrap().slewing);
    }

    /// In steady state the formula reduces to `cnt / (P + 1)`, which is the
    /// version everyone expects.
    #[test]
    fn in_steady_state_the_fraction_is_the_obvious_one() {
        let p = 32767u16;
        for cnt in [0u32, 1, 8192, 16384, 32767] {
            let b = decode(&reply(true, (0, 0, 0), cnt, p, p, false)).unwrap();
            let expected = cnt as f64 / (p as f64 + 1.0);
            assert!(
                (b.fraction() - expected).abs() < 1e-12,
                "cnt {cnt}: {} vs {expected}",
                b.fraction()
            );
        }
    }

    /// ⚠️ The regression the formula exists for. Inside the shortened first
    /// period after a phase set, the naive `cnt / (active + 1)` reads the
    /// fraction of the remaining window rather than of a second — the mistake
    /// that produced an "after" residual growing to −790 ms across ten syncs.
    #[test]
    fn inside_a_shortened_period_the_naive_fraction_would_be_wrong() {
        let (cnt, active, nominal) = (8000u32, 16383u16, 32767u16);
        let b = decode(&reply(true, (0, 0, 0), cnt, active, nominal, false)).unwrap();

        let correct = 1.0 - (active as f64 + 1.0 - cnt as f64) / (nominal as f64 + 1.0);
        assert!((b.fraction() - correct).abs() < 1e-12);

        let naive = cnt as f64 / (active as f64 + 1.0);
        assert!(
            (b.fraction() - naive).abs() > 0.2,
            "the two formulas must disagree here, or this test proves nothing"
        );
    }

    /// Older firmware reports no separate nominal period; zero means "same as
    /// active", not "divide by one".
    #[test]
    fn a_zero_nominal_period_means_use_the_active_one() {
        let p = 32767u16;
        let with_zero = decode(&reply(true, (0, 0, 0), 9000, p, 0, false)).unwrap();
        let explicit = decode(&reply(true, (0, 0, 0), 9000, p, p, false)).unwrap();
        assert_eq!(with_zero.fraction(), explicit.fraction());
    }

    /// The phase-2 audit's finding 2, with its exact fields: a lengthened
    /// active period just after midnight makes the seconds-of-day negative,
    /// and the C reads that as unset. So does this now. The C harness prints
    /// `device clock not set` for these bytes — pinned in
    /// `read_lines_match_the_c_for_captured_replies`.
    #[test]
    fn a_negative_seconds_of_day_is_read_as_unset_like_the_c() {
        let b = decode(&reply(true, (0, 0, 0), 100, 33422, 32767, false)).unwrap();
        assert!(b.set);
        assert!((b.fraction() - -0.016937255859375).abs() < 1e-12);
        assert_eq!(b.seconds_of_day(), None);
        // one second later the same fraction is a fine reading
        let later = decode(&reply(true, (0, 0, 1), 100, 33422, 32767, false)).unwrap();
        assert!((later.seconds_of_day().unwrap() - (1.0 - 0.016937255859375)).abs() < 1e-12);
        // and exactly zero is set, not negative -- the oracle's 2365966 case
        let zero = decode(&reply(true, (0, 0, 0), 0, 0, 0, false)).unwrap();
        assert_eq!(zero.seconds_of_day(), Some(0.0));
    }

    #[test]
    fn seconds_of_day_adds_the_fraction_to_the_clock() {
        let p = 32767u16;
        let b = decode(&reply(true, (13, 45, 7), 16384, p, p, false)).unwrap();
        let expect = 13.0 * 3600.0 + 45.0 * 60.0 + 7.0 + 16384.0 / 32768.0;
        assert!((b.seconds_of_day().unwrap() - expect).abs() < 1e-9);
    }

    // -- wrap_day ---------------------------------------------------------

    #[test]
    fn small_differences_pass_through_unchanged() {
        for d in [0.0, 1.5, -1.5, 43200.0, -43200.0] {
            assert_eq!(wrap_day(d), d);
        }
    }

    /// The case it exists for: a board just after midnight and a host just
    /// before it are two seconds apart, not almost a day.
    #[test]
    fn midnight_wraps_both_ways() {
        // board 00:00:01, host 23:59:59
        let board = 1.0;
        let host = 86399.0;
        assert!((wrap_day(board - host) - 2.0).abs() < 1e-9);
        // and the other direction
        assert!((wrap_day(host - board) + 2.0).abs() < 1e-9);
    }

    #[test]
    fn the_wrap_boundary_is_exactly_half_a_day() {
        assert_eq!(wrap_day(43200.0), 43200.0);
        assert!((wrap_day(43200.1) - (43200.1 - 86400.0)).abs() < 1e-9);
        assert_eq!(wrap_day(-43200.0), -43200.0);
        assert!((wrap_day(-43200.1) - (-43200.1 + 86400.0)).abs() < 1e-9);
    }

    // -- offset -----------------------------------------------------------

    #[test]
    fn offset_is_board_minus_host_in_milliseconds() {
        assert!((offset_ms(100.020, 100.000) - 20.0).abs() < 1e-9);
        assert!((offset_ms(100.000, 100.020) + 20.0).abs() < 1e-9);
    }

    #[test]
    fn offset_wraps_across_midnight_too() {
        assert!((offset_ms(0.5, 86399.5) - 1000.0).abs() < 1e-6);
    }

    // -- selection --------------------------------------------------------

    fn sample(off: f64, rtt: f64) -> Sample {
        Sample {
            offset_ms: off,
            rtt_ms: rtt,
            slewing: false,
        }
    }

    #[test]
    fn no_samples_is_no_measurement() {
        assert_eq!(select(&[]), None);
    }

    /// Transport delay can only add to a round trip, so the quickest exchange
    /// is the least contaminated — not the average.
    #[test]
    fn the_lowest_round_trip_wins() {
        let m = select(&[
            sample(10.0, 9.0),
            sample(3.0, 4.0),
            sample(25.0, 30.0),
            sample(8.0, 7.0),
        ])
        .unwrap();
        assert_eq!(m.offset_ms, 3.0, "the min-RTT sample's offset, not a mean");
        assert_eq!(m.rtt_ms, 4.0);
        assert_eq!(m.good, 4);
    }

    /// `U = (rtt_max - rtt_min) / 2 + 0.5`, straight from the C.
    #[test]
    fn uncertainty_is_half_the_spread_plus_a_half() {
        let m = select(&[sample(0.0, 4.0), sample(0.0, 30.0)]).unwrap();
        assert!((m.uncertainty_ms - ((30.0 - 4.0) / 2.0 + 0.5)).abs() < 1e-9);
    }

    #[test]
    fn one_sample_has_only_the_floor_of_uncertainty() {
        let m = select(&[sample(7.0, 5.0)]).unwrap();
        assert_eq!(m.uncertainty_ms, 0.5);
    }

    /// ⚠️ One slewing sample poisons the whole burst for lead calibration. A
    /// slewing board moves 20 ms/s, so it is not measuring the same thing.
    #[test]
    fn any_slewing_sample_flags_the_whole_burst() {
        let mut slewed = sample(1.0, 5.0);
        slewed.slewing = true;
        let m = select(&[sample(1.0, 4.0), slewed, sample(1.0, 6.0)]).unwrap();
        assert!(m.was_slewing, "even though the min-RTT sample was not slewing");
        assert_eq!(m.rtt_ms, 4.0, "but it is still the sample we trust");
    }

    /// The round trip is a wall-clock difference in both the C and the port,
    /// so a clock step backwards mid-burst yields a negative one. The C's
    /// `rtt_max` starts at zero, so its `U` is `(0 - rtt_min) / 2 + 0.5`;
    /// starting from negative infinity would print a different `U`.
    #[test]
    fn a_negative_round_trip_measures_u_against_zero_like_the_c() {
        let m = select(&[sample(1.0, -3.0), sample(2.0, -1.0)]).unwrap();
        assert_eq!(m.rtt_ms, -3.0);
        assert!((m.uncertainty_ms - ((0.0 - -3.0) / 2.0 + 0.5)).abs() < 1e-9);
    }

    /// ⚠️ A declared divergence — the phase-2 audit's finding 7. The C starts
    /// `rtt_min` at `1e9` and takes a sample only if `rtt < rtt_min`, so a
    /// burst whose every round trip is at least 1e9 ms (eleven days) counts as
    /// `good` yet selects nothing: `best_off` stays 0 and the printed rtt is
    /// the verify's. Here such a sample is selected. Reaching it needs an
    /// eleven-day wall-clock jump inside one GET, and matching it would push
    /// a sentinel through `Measurement`'s public type. On record, not ported.
    #[test]
    fn an_eleven_day_round_trip_is_selected_where_the_c_would_skip_it() {
        let m = select(&[sample(123.0, 1e9)]).unwrap();
        assert_eq!(m.offset_ms, 123.0, "the C would report before +0.0 here");
        assert_eq!(m.rtt_ms, 1e9);
    }

    /// Ties keep the first, matching the C's strict `<` comparison.
    #[test]
    fn an_rtt_tie_keeps_the_earlier_sample() {
        let m = select(&[sample(11.0, 5.0), sample(22.0, 5.0)]).unwrap();
        assert_eq!(m.offset_ms, 11.0);
    }
}
