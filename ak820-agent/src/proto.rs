//! The raw-HID wire protocol, and the reply correlation it requires.
//!
//! Every command is one 32-byte report, `[SET_VALUE][channel][command][..]`.
//! The report id (`0x00`) is prepended on the wire and stripped by the device,
//! so a written buffer is 33 bytes and a read one comes back 33 bytes with a
//! leading zero -- see [`normalize_input`], which is where that asymmetry is
//! handled once instead of at every call site.
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
//!
//! # ⚠️ Correlation is necessary and **not sufficient**
//!
//! Captured 2026-09-05 while this crate held a handle and wrote nothing but
//! flash reads: eight reports arrived on channel `0x10` -- five `RTC_GET_TIME`,
//! one `RTC_SET_TIME_MS`, then two more GETs. That is the *timekeeper agent's*
//! whole clock transaction, broadcast into our queue.
//!
//! Read what that means carefully, because it is worse than the text-echo case
//! and it is not fixed by anything in this module. A foreign **text** echo is
//! recognisably not a clock reply, so [`match_reply`] discards it. A foreign
//! **`RTC_GET_TIME` reply is a well-formed `RTC_GET_TIME` reply** -- right
//! channel, right command, right protocol version, plausible fields. Nothing in
//! these bytes distinguishes it from the answer to *our* GET. Two processes
//! issuing the same command produce interchangeable replies, and taking theirs
//! means computing an offset from a board sample paired with our timestamps:
//! a silently wrong measurement rather than a detectable error.
//!
//! So this module makes cross-channel confusion impossible, which is what it
//! can do with the wire as it stands. Same-command confusion needs either a
//! single owner of the interface -- the daemon's whole reason for existing --
//! or a nonce in the protocol, which would be a firmware change. Do not read
//! the correlation below as making concurrent clock clients safe.
//!
//! # ⚠️ And it protects us, not them
//!
//! The broadcast is bidirectional. Captured from VIA's own error console the
//! same day: VIA asked `CUSTOM_MENU_SET_VALUE` and received
//! `07 11 01 00 85 60 17 CE` -- **our** `FC_INFO` reply -- which it rejected as
//! "Receiving incorrect response for command". Worse, one injected report
//! desyncs it persistently: every command after that got the *previous*
//! command's echo.
//!
//! Nothing in this module can prevent that; correlation is a read-side defence
//! and the damage is on the other side of the wire. The only mitigation is not
//! transacting while VIA is open -- see the phase-4 proposal in
//! plans/AK820-AGENT-PLAN.md, which uses the drain log as a VIA detector.

/// Report size the firmware expects, excluding the leading report id.
pub const REPORT_LEN: usize = 32;

/// What Windows actually moves for one report: [`REPORT_LEN`] plus the report
/// id. The HID collection carries no report-id item, so the id is always
/// `0x00`, and both `InputReportByteLength` and `OutputReportByteLength` are
/// this.
pub const WIRE_LEN: usize = REPORT_LEN + 1;

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
pub fn frame(channel: Channel, command: u8, body: &[u8]) -> [u8; WIRE_LEN] {
    assert!(
        body.len() + 3 <= REPORT_LEN,
        "payload {} bytes exceeds the {REPORT_LEN}-byte report",
        body.len() + 3
    );
    let mut buf = [0u8; WIRE_LEN];
    buf[1] = SET_VALUE;
    buf[2] = channel.id();
    buf[3] = command;
    buf[4..4 + body.len()].copy_from_slice(body);
    buf
}

/// Why a report is not the reply we are waiting for.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Mismatch {
    /// Not a full report: truncated, or a different collection entirely.
    TooShort,
    /// A numbered report from something else sharing the handle. Ours is
    /// always id `0x00`.
    ReportId(u8),
    /// Not our channel -- someone else's traffic entirely.
    ///
    /// ⚠️ Carries the raw first three bytes rather than naming them, and that
    /// is deliberate. For our own framing they are
    /// `[SET_VALUE, channel, command]`, but a report from **VIA** is
    /// `[command_id, ...]` on VIA's own layout, where byte 1 is a QMK
    /// lighting channel and byte 2 a value id. Calling those "channel" and
    /// "command" in a log invents a channel this firmware does not have --
    /// which is exactly the wrong turn a reader takes at 2 a.m.
    NotOurs { header: [u8; 3] },
    /// Right channel, different command -- e.g. a text echo while we await a set.
    OtherCommand { command: u8 },
    /// Right channel and command, but the leading id is neither `SET_VALUE` nor
    /// `ID_UNHANDLED`. Not a shape this firmware produces.
    BadHeader(u8),
}

/// Strip the report id Windows prepends, and refuse anything that is not one of
/// our reports.
///
/// ⚠️ Getting this off by one is invisible: every field shifts a byte and still
/// parses as plausible numbers. `hidapi` stripped the id itself when it was
/// zero, which is why the C tool never had to think about it and why a direct
/// Win32 port must.
pub fn normalize_input(raw: &[u8]) -> Result<&[u8], Mismatch> {
    match raw.len() {
        WIRE_LEN if raw[0] == 0 => Ok(&raw[1..]),
        WIRE_LEN => Err(Mismatch::ReportId(raw[0])),
        // A driver reporting 32-byte reports would hand back the payload alone.
        // Not what this board does; accepted rather than silently mangled.
        REPORT_LEN => Ok(raw),
        _ => Err(Mismatch::TooShort),
    }
}

/// Is `report` the reply to `(channel, command)`?
///
/// Takes a report with the id already stripped. Returns `Err(Mismatch)` for
/// anything else so the caller can log what it discarded; a silent drop would
/// hide exactly the cross-talk this exists for.
///
/// ⚠️ Channel and command are checked **before** the leading id, and that order
/// is load-bearing. The firmware's unhandled path sets `data[0] = 0xFF` and
/// echoes the rest of the buffer untouched (`hid_protocol.c`,
/// `raw_hid_receive`), so an `0xFF` report still names the command it refused.
/// Checking `0xFF` first would let *another process's* rejected command abort
/// our wait.
pub fn match_reply(report: &[u8], channel: Channel, command: u8) -> Result<(), Mismatch> {
    if report.len() < REPORT_LEN {
        return Err(Mismatch::TooShort);
    }
    if report[1] != channel.id() {
        return Err(Mismatch::NotOurs {
            header: [report[0], report[1], report[2]],
        });
    }
    if report[2] != command {
        return Err(Mismatch::OtherCommand { command: report[2] });
    }
    match report[0] {
        SET_VALUE | ID_UNHANDLED => Ok(()),
        other => Err(Mismatch::BadHeader(other)),
    }
}

/// What to do with one report that arrived while we were waiting for a reply.
#[derive(Debug, PartialEq, Eq)]
pub enum Verdict<'a> {
    /// Our answer: the 32-byte report, id stripped.
    Reply(&'a [u8]),
    /// Not ours. Discard it and keep waiting -- do **not** take it as the
    /// answer, and do not give up.
    Drain(Mismatch),
    /// Ours, and the firmware says it does not handle this command. Waiting
    /// longer cannot help.
    Unhandled,
}

/// The whole read-side decision in one place: normalize, correlate, classify.
///
/// This is what the transport loop drives. Keeping it a pure function over
/// bytes is what lets every cross-talk case be tested without a device.
pub fn classify<'a>(raw: &'a [u8], channel: Channel, command: u8) -> Verdict<'a> {
    let report = match normalize_input(raw) {
        Ok(r) => r,
        Err(m) => return Verdict::Drain(m),
    };
    match match_reply(report, channel, command) {
        Err(m) => Verdict::Drain(m),
        Ok(()) if report[0] == ID_UNHANDLED => Verdict::Unhandled,
        Ok(()) => Verdict::Reply(report),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A 32-byte report as the firmware sees it.
    fn report(bytes: &[u8]) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[..bytes.len()].copy_from_slice(bytes);
        r
    }

    /// The same report as Windows hands it back: report id 0 in front.
    fn wire(bytes: &[u8]) -> Vec<u8> {
        let mut r = vec![0u8; WIRE_LEN];
        r[1..1 + bytes.len()].copy_from_slice(bytes);
        r
    }

    #[test]
    fn frame_puts_the_report_id_first_and_pads() {
        let f = frame(Channel::Text, 0x03, &[0, 1, b'H']);
        assert_eq!(f.len(), WIRE_LEN);
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
            Err(Mismatch::NotOurs {
                header: [0x07, 0x12, 0x03]
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
    fn a_short_report_is_never_a_reply() {
        assert_eq!(
            match_reply(&[0x07, 0x10, 0x02], Channel::Rtc, 0x02),
            Err(Mismatch::TooShort)
        );
    }

    /// Our own command coming back refused: correlated, and fatal rather than
    /// something to keep waiting through.
    #[test]
    fn our_own_unhandled_reply_is_fatal() {
        let unhandled = report(&[ID_UNHANDLED, 0x10, 0x02]);
        assert_eq!(match_reply(&unhandled, Channel::Rtc, 0x02), Ok(()));
        assert_eq!(classify(&unhandled, Channel::Rtc, 0x02), Verdict::Unhandled);
    }

    /// Why the id check comes last. The firmware echoes the buffer and only
    /// overwrites `data[0]`, so someone else's refused command still carries
    /// their channel -- and must be drained, not mistaken for ours failing.
    #[test]
    fn another_processs_unhandled_echo_is_drained_not_fatal() {
        let theirs = wire(&[ID_UNHANDLED, 0x12, 0x03]);
        assert_eq!(
            classify(&theirs, Channel::Rtc, 0x02),
            Verdict::Drain(Mismatch::NotOurs {
                header: [ID_UNHANDLED, 0x12, 0x03]
            })
        );
    }

    #[test]
    fn health_and_text_replies_do_not_cross() {
        let health = report(&[0x07, 0x13, 0x01, 0x05]);
        assert!(match_reply(&health, Channel::Health, 0x01).is_ok());
        assert!(match_reply(&health, Channel::Text, 0x01).is_err());
    }

    #[test]
    fn normalize_strips_the_report_id() {
        let w = wire(&[0x07, 0x10, 0x02, 0x63]);
        assert_eq!(normalize_input(&w).unwrap()[..4], [0x07, 0x10, 0x02, 0x63]);
    }

    /// A numbered report from another collection sharing the handle. Ours is
    /// always id 0, so a non-zero id is by definition not our traffic.
    #[test]
    fn normalize_rejects_a_foreign_report_id() {
        let mut w = wire(&[0x07, 0x10, 0x02]);
        w[0] = 0x05;
        assert_eq!(normalize_input(&w), Err(Mismatch::ReportId(0x05)));
    }

    #[test]
    fn normalize_rejects_a_short_read() {
        assert_eq!(normalize_input(&[0u8; 8]), Err(Mismatch::TooShort));
        assert_eq!(normalize_input(&[]), Err(Mismatch::TooShort));
    }

    /// The point of `classify`: it takes the wire form, not a stripped one.
    #[test]
    fn classify_takes_the_wire_form() {
        let w = wire(&[0x07, 0x11, 0x01, 0x00, 0xEF, 0x40, 0x18]);
        assert!(matches!(
            classify(&w, Channel::Flash, 0x01),
            Verdict::Reply(r) if r[4] == 0xEF
        ));
    }

    /// The measured cross-talk, end to end through the classifier.
    #[test]
    fn classify_drains_the_measured_text_echo() {
        let echo = wire(&[
            0x07, 0x12, 0x03, 0x00, 0x01, b'W', b'R', b'I', b'T', b'E', b'R', b'X',
        ]);
        assert_eq!(
            classify(&echo, Channel::Rtc, 0x02),
            Verdict::Drain(Mismatch::NotOurs {
                header: [0x07, 0x12, 0x03]
            })
        );
    }

    /// ⚠️ Captured from VIA's own error log, 2026-09-05. VIA rides the same
    /// `0x07` id we do -- our channels were chosen to sit above QMK's lighting
    /// channels precisely so the byte after it separates us -- and this is what
    /// its custom-menu traffic looks like arriving on our handle. Byte 1 is a
    /// QMK lighting channel, not one of ours, so it drains.
    #[test]
    fn classify_drains_vias_custom_menu_traffic() {
        // CUSTOM_MENU_SET_VALUE on the RGB matrix channel, value id 1.
        let via_set = wire(&[0x07, 0x03, 0x01, 0xA9]);
        assert_eq!(
            classify(&via_set, Channel::Flash, 0x01),
            Verdict::Drain(Mismatch::NotOurs {
                header: [0x07, 0x03, 0x01]
            })
        );
        // CUSTOM_MENU_SAVE -- a different leading id entirely.
        let via_save = wire(&[0x09, 0x03]);
        assert_eq!(
            classify(&via_save, Channel::Flash, 0x01),
            Verdict::Drain(Mismatch::NotOurs {
                header: [0x09, 0x03, 0x00]
            })
        );
    }

    /// The other direction, and the one VIA actually complained about: this is
    /// **our** FC_INFO reply, which VIA received and rejected as
    /// "Receiving incorrect response for command". Nothing in this crate can
    /// stop that -- the fix is not transacting while VIA is open.
    #[test]
    fn our_own_reply_is_what_via_saw() {
        let ours = wire(&[0x07, 0x11, 0x01, 0x00, 0x85, 0x60, 0x17, 0xCE]);
        assert!(matches!(
            classify(&ours, Channel::Flash, 0x01),
            Verdict::Reply(_)
        ));
    }

    /// Neither 0x07 nor 0xFF on our own channel and command: not a shape the
    /// firmware emits, so it is noise rather than an answer.
    #[test]
    fn classify_refuses_an_unrecognised_header() {
        let odd = wire(&[0x42, 0x10, 0x02]);
        assert_eq!(
            classify(&odd, Channel::Rtc, 0x02),
            Verdict::Drain(Mismatch::BadHeader(0x42))
        );
    }
}
