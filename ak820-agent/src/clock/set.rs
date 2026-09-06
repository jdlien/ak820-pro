//! The `RTC_SET_TIME_MS` packet and its reply.
//!
//! Fifteen bytes on the wire, exactly as `send_set_ms` in the pinned C lays
//! them out:
//!
//! ```text
//! [0]=0x07 SET_VALUE  [1]=0x10 RTC  [2]=0x03 SET_TIME_MS
//! [3]=year-2000 [4]=month [5]=day [6]=weekday
//! [7]=hour [8]=min [9]=sec
//! [10..11]=ms u16 LE (clamped to 999)
//! [12]=flags (0)
//! [13..14]=sof_bias s16 LE, or 0x7FFF when the bias is unknown
//! ```
//!
//! The meaning is "at the instant this packet was received, true time was
//! `t + ms`" — so the timestamp inside it has to be taken as late as possible
//! and the packet has to leave immediately afterwards. That is why the body is
//! built inside the transport's prepare step, after the pre-drain, and not
//! handed in from outside.
//!
//! The firmware validates every field before touching anything (`hid_protocol.c`,
//! `rtc_ms_payload_valid`): year 2026..2098, a real calendar date, weekday
//! `0..6`, `ms <= 999`, reserved flag bits clear, bias within ±600 or the
//! sentinel. A packet failing any of those comes back as [`SetStatus::Reject`].

use super::host::LocalTime;
use super::PROTO_VERSION;
use crate::proto::REPORT_LEN;

/// ⚠️ The **unknown-bias sentinel**, not a zero bias. Sending `0` would tell
/// the firmware the SOF reference is perfect.
pub const UNKNOWN_BIAS: i16 = 0x7FFF;

/// Milliseconds are clamped here, before the firmware can reject them.
pub const MAX_MS: u32 = 999;

/// The status byte at `[3]` of the reply. The names are the firmware's
/// (`rtc.h`: `RTC_SET_STEPPED`, `_SLEWING`, `_RETRY`, `_REJECT`).
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum SetStatus {
    /// Applied as a step. Not a calibration sample.
    Stepped,
    /// Applied as a slew — the case that prints `(slewing)`, and the only one
    /// the Python learner acts on.
    Slewing,
    /// Busy or stale read; the C retries the whole SET **once**, then fails.
    Retry,
    /// The firmware refused validation. No retry can help.
    Reject,
    /// Not a value this firmware emits. Kept distinct so that the C's literal
    /// `st != 0` gate can be reproduced rather than guessed at.
    Other(u8),
}

impl SetStatus {
    pub fn from_byte(b: u8) -> SetStatus {
        match b {
            0 => SetStatus::Stepped,
            1 => SetStatus::Slewing,
            0xFE => SetStatus::Retry,
            0xFF => SetStatus::Reject,
            other => SetStatus::Other(other),
        }
    }

    pub fn byte(self) -> u8 {
        match self {
            SetStatus::Stepped => 0,
            SetStatus::Slewing => 1,
            SetStatus::Retry => 0xFE,
            SetStatus::Reject => 0xFF,
            SetStatus::Other(b) => b,
        }
    }
}

/// What the board said about the SET.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct SetReply {
    pub status: SetStatus,
    /// `o'`: `target - board_at_receipt` in ms, as the firmware saw it. The
    /// lead learner's whole input.
    pub receipt_offset_ms: i16,
    pub proto: u8,
}

/// Decode a correlated `RTC_SET_TIME_MS` reply.
pub fn decode_reply(report: &[u8]) -> Option<SetReply> {
    if report.len() < REPORT_LEN {
        return None;
    }
    Some(SetReply {
        status: SetStatus::from_byte(report[3]),
        receipt_offset_ms: i16::from_le_bytes([report[4], report[5]]),
        proto: report[11],
    })
}

/// Split a target instant into the whole second the C's `localtime` sees and
/// the millisecond field, **before** clamping.
///
/// Reproduces `time_t ts = (time_t)target; ms = (unsigned)((target - ts) * 1000)`:
/// both conversions truncate, so `.9999` is `999` and never rounds up into
/// the next second.
pub fn split_target(target: f64) -> (i64, u32) {
    let ts = target.trunc();
    let ms = ((target - ts) * 1000.0) as u32;
    (ts as i64, ms)
}

/// The twelve payload bytes after `[SET_VALUE, RTC, SET_TIME_MS]`.
///
/// `year - 2000` goes through the same `unsigned char` conversion as the C, so
/// a pre-2000 year wraps rather than panicking; the firmware rejects it either
/// way.
pub fn body(local: &LocalTime, ms: u32, bias_ppm: Option<i32>) -> [u8; 12] {
    let ms = ms.min(MAX_MS);
    let bias = match bias_ppm {
        Some(b) => (b as i16).to_le_bytes(),
        None => UNKNOWN_BIAS.to_le_bytes(),
    };
    [
        (local.year - 2000) as u8,
        local.month,
        local.day,
        local.weekday,
        local.hour,
        local.minute,
        local.second,
        (ms & 0xFF) as u8,
        (ms >> 8) as u8,
        0, // flags
        bias[0],
        bias[1],
    ]
}

/// Is this a reply we can act on? The C never checks the SET reply's version
/// (it checks the GETs before it); kept available for the caller.
pub fn understood(reply: &SetReply) -> bool {
    reply.proto == PROTO_VERSION
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::{frame, Channel};

    /// 2026-08-29 (a Saturday) 11:06:41 local.
    fn saturday() -> LocalTime {
        LocalTime {
            year: 2026,
            month: 8,
            day: 29,
            weekday: 6,
            hour: 11,
            minute: 6,
            second: 41,
        }
    }

    /// Fixture 4 of the transaction document: known target and lead, with a
    /// negative bias. Byte for byte against the C's `p[15]`.
    #[test]
    fn the_packet_for_a_known_target() {
        let b = body(&saturday(), 252, Some(-25));
        assert_eq!(b, [26, 8, 29, 6, 11, 6, 41, 252, 0, 0, 0xE7, 0xFF]);
        // and framed, it is the C's fifteen bytes behind the report id
        let f = frame(Channel::Rtc, super::super::SET_TIME_MS, &b);
        assert_eq!(
            &f[1..16],
            &[0x07, 0x10, 0x03, 26, 8, 29, 6, 11, 6, 41, 252, 0, 0, 0xE7, 0xFF]
        );
        assert!(f[16..].iter().all(|&x| x == 0));
    }

    #[test]
    fn milliseconds_are_little_endian_and_clamped() {
        let b = body(&saturday(), 999, None);
        assert_eq!(&b[7..9], &[0xE7, 0x03]);
        assert_eq!(&body(&saturday(), 1000, None)[7..9], &[0xE7, 0x03], "1000 clamps to 999");
        assert_eq!(&body(&saturday(), 65535, None)[7..9], &[0xE7, 0x03]);
        assert_eq!(&body(&saturday(), 0, None)[7..9], &[0, 0]);
        assert_eq!(&body(&saturday(), 256, None)[7..9], &[0x00, 0x01]);
    }

    /// ⚠️ The sentinel is not zero. Zero is a *claim* — that the SOF reference
    /// is perfect — and the firmware would act on it.
    #[test]
    fn an_unknown_bias_is_the_sentinel_not_zero() {
        assert_eq!(&body(&saturday(), 0, None)[10..12], &[0xFF, 0x7F]);
        assert_eq!(&body(&saturday(), 0, Some(0))[10..12], &[0x00, 0x00]);
        assert_ne!(
            body(&saturday(), 0, None)[10..12],
            body(&saturday(), 0, Some(0))[10..12]
        );
    }

    #[test]
    fn a_negative_bias_is_twos_complement_little_endian() {
        assert_eq!(&body(&saturday(), 0, Some(-78))[10..12], &[0xB2, 0xFF]);
        assert_eq!(&body(&saturday(), 0, Some(-600))[10..12], &[0xA8, 0xFD]);
        assert_eq!(&body(&saturday(), 0, Some(600))[10..12], &[0x58, 0x02]);
        assert_eq!(&body(&saturday(), 0, Some(-1))[10..12], &[0xFF, 0xFF]);
    }

    #[test]
    fn the_flags_byte_is_zero() {
        assert_eq!(body(&saturday(), 0, Some(1))[9], 0);
    }

    /// The C's `(unsigned char)(tm_year + 1900 - 2000)` wraps for years before
    /// 2000; the firmware's `yy < 26` check then rejects it.
    #[test]
    fn the_year_byte_converts_like_an_unsigned_char() {
        let mut t = saturday();
        t.year = 1999;
        assert_eq!(body(&t, 0, None)[0], 255);
        t.year = 2098;
        assert_eq!(body(&t, 0, None)[0], 98);
    }

    #[test]
    fn split_target_truncates_both_halves() {
        assert_eq!(split_target(40001.252354), (40001, 252));
        assert_eq!(split_target(40001.0), (40001, 0));
        assert_eq!(split_target(40001.9999), (40001, 999));
        assert_eq!(split_target(40001.0009), (40001, 0), "0.9 ms truncates, not rounds");
        assert_eq!(split_target(40001.9995), (40001, 999));
        assert_eq!(split_target(1787961600.0 + 40001.252354).0, 1787961600 + 40001);
    }

    #[test]
    fn statuses_are_the_firmwares_values() {
        assert_eq!(SetStatus::from_byte(0), SetStatus::Stepped);
        assert_eq!(SetStatus::from_byte(1), SetStatus::Slewing);
        assert_eq!(SetStatus::from_byte(0xFE), SetStatus::Retry);
        assert_eq!(SetStatus::from_byte(0xFF), SetStatus::Reject);
        assert_eq!(SetStatus::from_byte(2), SetStatus::Other(2));
        for b in [0u8, 1, 2, 0xFE, 0xFF] {
            assert_eq!(SetStatus::from_byte(b).byte(), b);
        }
    }

    #[test]
    fn the_reply_carries_a_signed_receipt_offset() {
        let mut r = vec![0u8; REPORT_LEN];
        r[..6].copy_from_slice(&[0x07, 0x10, 0x03, 1, 0xF6, 0xFF]);
        r[11] = PROTO_VERSION;
        let d = decode_reply(&r).unwrap();
        assert_eq!(d.status, SetStatus::Slewing);
        assert_eq!(d.receipt_offset_ms, -10);
        assert!(understood(&d));
        r[4] = 0x2C;
        r[5] = 0x01;
        assert_eq!(decode_reply(&r).unwrap().receipt_offset_ms, 300);
    }

    #[test]
    fn a_short_reply_is_nothing() {
        assert!(decode_reply(&[0x07, 0x10, 0x03, 0]).is_none());
    }
}
