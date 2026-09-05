//! The raw-HID wire protocol, and the reply correlation it requires.
//!
//! Every command is one 32-byte report, `[SET_VALUE][channel][command][..]`.
//! The report id (`0x00`) is prepended on the wire and stripped by the device,
//! so a written buffer is 33 bytes and a read one is 32.
//!
//! ⚠️ **A read must be matched to its request.** Measured on this machine
//! 2026-09-05: Windows delivers HID input reports to *every open handle*, so a
//! process that wrote nothing at all received the echo of another process's
//! text command (`07 12 03 00 01 "WRITERX"`). Ordering cannot correlate a reply
//! to a request -- someone else's reply can arrive between our write and our
//! read -- so a non-matching report must be **drained and discarded**, never
//! consumed as the answer.
//!
//! The same experiment showed it inside a single handle too: a clock GET issued
//! after a text write returned the *text echo*, not the clock reply.
//!
//! `ak820ctl`'s `xfer()` does none of this and returns the first report that
//! arrives. It fails safe only by accident -- a text echo lands a bogus value in
//! `rep[11]` and the protocol-version check refuses to act. `ak820health.py`
//! validates its header and is the model followed here.

/// Report size the firmware expects, excluding the leading report id.
pub const REPORT_LEN: usize = 32;

/// VIA's "custom set value" id, which every one of our channels rides on.
pub const SET_VALUE: u8 = 0x07;
/// Returned when the firmware does not understand the command.
pub const ID_UNHANDLED: u8 = 0xFF;

/// Channels, each owned by a different concern in the firmware.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Channel {
    Rtc = 0x10,
    Flash = 0x11,
    Text = 0x12,
    Health = 0x13,
}

impl Channel {
    pub fn id(self) -> u8 {
        self as u8
    }
}

/// A 33-byte buffer: report id, then the payload, zero padded.
///
/// Panics if the payload cannot fit, which is a programming error rather than a
/// runtime condition -- every command in this protocol is far shorter.
pub fn frame(channel: Channel, command: u8, body: &[u8]) -> [u8; REPORT_LEN + 1] {
    assert!(
        body.len() + 3 <= REPORT_LEN,
        "payload {} bytes exceeds the {REPORT_LEN}-byte report",
        body.len() + 3
    );
    let mut buf = [0u8; REPORT_LEN + 1];
    buf[1] = SET_VALUE;
    buf[2] = channel.id();
    buf[3] = command;
    buf[4..4 + body.len()].copy_from_slice(body);
    buf
}

/// Why a report is not the reply we are waiting for.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Mismatch {
    /// Shorter than a full report: truncated or a different collection.
    TooShort,
    /// The firmware says it does not handle this command.
    Unhandled,
    /// Someone else's traffic, or our own echo on another channel.
    OtherChannel { channel: u8, command: u8 },
    /// Right channel, different command -- e.g. a text echo while we await a set.
    OtherCommand { command: u8 },
}

/// Is `report` the reply to `(channel, command)`?
///
/// Returns `Err(Mismatch)` for anything else so the caller can log what it
/// discarded; a silent drop would hide exactly the cross-talk this exists for.
pub fn match_reply(report: &[u8], channel: Channel, command: u8) -> Result<(), Mismatch> {
    if report.len() < REPORT_LEN {
        return Err(Mismatch::TooShort);
    }
    if report[0] == ID_UNHANDLED {
        return Err(Mismatch::Unhandled);
    }
    if report[0] != SET_VALUE || report[1] != channel.id() {
        return Err(Mismatch::OtherChannel {
            channel: report[1],
            command: report[2],
        });
    }
    if report[2] != command {
        return Err(Mismatch::OtherCommand {
            command: report[2],
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn report(bytes: &[u8]) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[..bytes.len()].copy_from_slice(bytes);
        r
    }

    #[test]
    fn frame_puts_the_report_id_first_and_pads() {
        let f = frame(Channel::Text, 0x03, &[0, 1, b'H']);
        assert_eq!(f.len(), 33);
        assert_eq!(&f[..7], &[0x00, 0x07, 0x12, 0x03, 0x00, 0x01, b'H']);
        assert!(f[7..].iter().all(|&b| b == 0), "tail must be zero padded");
    }

    #[test]
    fn frame_builds_a_clock_get() {
        let f = frame(Channel::Rtc, 0x02, &[]);
        assert_eq!(&f[..4], &[0x00, 0x07, 0x10, 0x02]);
    }

    #[test]
    #[should_panic(expected = "exceeds")]
    fn frame_refuses_an_oversized_payload() {
        frame(Channel::Text, 0x03, &[0u8; 30]);
    }

    #[test]
    fn accepts_the_matching_reply() {
        let r = report(&[0x07, 0x10, 0x02, 0x01]);
        assert_eq!(match_reply(&r, Channel::Rtc, 0x02), Ok(()));
    }

    /// The regression this module exists for, using the bytes actually observed.
    #[test]
    fn rejects_another_processs_text_echo_as_a_clock_reply() {
        let echo = report(&[
            0x07, 0x12, 0x03, 0x00, 0x01, b'W', b'R', b'I', b'T', b'E', b'R', b'X',
        ]);
        assert_eq!(
            match_reply(&echo, Channel::Rtc, 0x02),
            Err(Mismatch::OtherChannel {
                channel: 0x12,
                command: 0x03
            }),
            "a text echo must never be read as a clock reply"
        );
    }

    #[test]
    fn rejects_the_right_channel_with_the_wrong_command() {
        let r = report(&[0x07, 0x10, 0x03, 0x00]);
        assert_eq!(
            match_reply(&r, Channel::Rtc, 0x02),
            Err(Mismatch::OtherCommand { command: 0x03 })
        );
    }

    #[test]
    fn rejects_unhandled_and_short_reports() {
        let unhandled = report(&[ID_UNHANDLED, 0x10, 0x02]);
        assert_eq!(
            match_reply(&unhandled, Channel::Rtc, 0x02),
            Err(Mismatch::Unhandled)
        );
        assert_eq!(
            match_reply(&[0x07, 0x10, 0x02], Channel::Rtc, 0x02),
            Err(Mismatch::TooShort)
        );
    }

    #[test]
    fn health_and_text_replies_do_not_cross() {
        let health = report(&[0x07, 0x13, 0x01, 0x05]);
        assert!(match_reply(&health, Channel::Health, 0x01).is_ok());
        assert!(match_reply(&health, Channel::Text, 0x01).is_err());
    }
}
