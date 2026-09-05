//! What an opened handle has to say about itself before we write to it.
//!
//! Pure, because it is a decision rather than a syscall: [`device`] gathers the
//! numbers from `HidD_GetAttributes` and `HidP_GetCaps`, this decides whether
//! they describe our raw-HID interface.
//!
//! The split matters for the reason [`super::path`] explains: the device path
//! is documented as **opaque**, so matching it chooses what to *open*, and the
//! device itself has to agree before we choose what to *write to*. The board
//! puts four collections behind one VID/PID -- the keyboard, the consumer
//! controls, VIA's own, and ours -- and three of them would accept a write and
//! do something we did not intend with it.
//!
//! [`device`]: super::device

use crate::proto::WIRE_LEN;

/// Everything the driver will tell us about an open collection.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct Identity {
    pub vid: u16,
    pub pid: u16,
    pub usage_page: u16,
    pub usage: u16,
    /// `InputReportByteLength` -- the report plus its leading id.
    pub input_len: u16,
    /// `OutputReportByteLength`, likewise.
    pub output_len: u16,
}

/// Why an opened collection is not the one we came for.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Reject {
    /// The device disagrees with the ids its own path advertised. Either the
    /// path filter is wrong or something moved underneath us; both mean stop.
    Attributes { vid: u16, pid: u16 },
    /// A different collection on the same board: the keyboard, the consumer
    /// controls, VIA's channel. Ours is the QMK raw page.
    Usage { page: u16, usage: u16 },
    /// The right collection could not carry our protocol. A 32-byte command
    /// truncated into a shorter report is a malformed command, not a short one.
    ReportLen { input: u16, output: u16 },
}

impl std::fmt::Display for Reject {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Reject::Attributes { vid, pid } => write!(
                f,
                "the device reports {vid:04X}:{pid:04X}, not what its path claimed"
            ),
            Reject::Usage { page, usage } => write!(
                f,
                "usage page {page:#06X}/{usage:#04X} is another collection, not QMK raw HID \
                 ({:#06X}/{:#04X})",
                super::path::USAGE_PAGE,
                super::path::USAGE
            ),
            Reject::ReportLen { input, output } => write!(
                f,
                "reports are {input}/{output} bytes in/out, not the {WIRE_LEN} this protocol needs"
            ),
        }
    }
}

impl Identity {
    /// Is this the interface we meant to open, and can it carry our protocol?
    ///
    /// Order is deliberate: identity, then collection, then capacity. A wrong
    /// answer to the first makes the other two meaningless, and the message
    /// should name the first thing that was wrong rather than a consequence.
    ///
    /// ⚠️ This prevents a wrong *write*. It cannot un-open a wrong device --
    /// that is [`super::path::matches_device`]'s job, and why that filter is
    /// bounded rather than a substring search.
    pub fn check(&self, vid: u16, pid: u16) -> Result<(), Reject> {
        if self.vid != vid || self.pid != pid {
            return Err(Reject::Attributes {
                vid: self.vid,
                pid: self.pid,
            });
        }
        if self.usage_page != super::path::USAGE_PAGE || self.usage != super::path::USAGE {
            return Err(Reject::Usage {
                page: self.usage_page,
                usage: self.usage,
            });
        }
        let want = WIRE_LEN as u16;
        if self.input_len != want || self.output_len != want {
            return Err(Reject::ReportLen {
                input: self.input_len,
                output: self.output_len,
            });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::super::path::{PID, VID};
    use super::*;

    // Every number below was measured on this board, 2026-09-05, with
    // `ak820 list --caps` -- which opens only paths the path filter already
    // decided are this keyboard's. They are not plausible values; they are the
    // five collections the AK820 Pro actually presents.

    /// MI_01. QMK's vendor page, 33-byte reports in and out.
    fn raw_hid() -> Identity {
        Identity {
            vid: VID,
            pid: PID,
            usage_page: 0xFF60,
            usage: 0x61,
            input_len: 33,
            output_len: 33,
        }
    }

    #[test]
    fn accepts_the_raw_hid_collection() {
        assert_eq!(raw_hid().check(VID, PID), Ok(()));
    }

    /// MI_00. Same board, same path filter, and a write here would type.
    #[test]
    fn rejects_the_boot_keyboard_collection() {
        let kbd = Identity {
            usage_page: 0x01,
            usage: 0x06,
            input_len: 9,
            output_len: 2,
            ..raw_hid()
        };
        assert_eq!(
            kbd.check(VID, PID),
            Err(Reject::Usage {
                page: 0x01,
                usage: 0x06
            }),
            "the collection must be rejected on its usage, before its report size"
        );
    }

    /// MI_02 Col02. Consumer controls -- volume, transport keys.
    #[test]
    fn rejects_the_consumer_collection() {
        let consumer = Identity {
            usage_page: 0x0C,
            usage: 0x01,
            input_len: 3,
            output_len: 0,
            ..raw_hid()
        };
        assert!(matches!(
            consumer.check(VID, PID),
            Err(Reject::Usage { .. })
        ));
    }

    /// MI_02 Col01. System control -- power, sleep, wake.
    #[test]
    fn rejects_the_system_control_collection() {
        let sysctl = Identity {
            usage_page: 0x01,
            usage: 0x80,
            input_len: 3,
            output_len: 0,
            ..raw_hid()
        };
        assert!(matches!(sysctl.check(VID, PID), Err(Reject::Usage { .. })));
    }

    /// ⚠️ MI_02 Col03, and the reason the usage check cannot be skipped in
    /// favour of a report-size one. This is the **NKRO keyboard**, and its
    /// input reports are 32 bytes -- the same size as one of ours minus the id.
    /// A 32-byte report from here sails through `proto::normalize_input`'s
    /// tolerant branch; only the usage page says it is a keyboard.
    #[test]
    fn rejects_the_nkro_keyboard_despite_its_32_byte_reports() {
        let nkro = Identity {
            usage_page: 0x01,
            usage: 0x06,
            input_len: 32,
            output_len: 2,
            ..raw_hid()
        };
        assert_eq!(
            nkro.check(VID, PID),
            Err(Reject::Usage {
                page: 0x01,
                usage: 0x06
            })
        );
    }

    /// The reason post-open checking exists at all: Windows documents these
    /// path strings as opaque, so the device gets the last word on what it is.
    #[test]
    fn rejects_a_device_that_disagrees_with_its_own_path() {
        let impostor = Identity {
            vid: 0x051D,
            pid: 0x0002,
            ..raw_hid()
        };
        assert_eq!(
            impostor.check(VID, PID),
            Err(Reject::Attributes {
                vid: 0x051D,
                pid: 0x0002
            })
        );
    }

    /// Right page, wrong capacity. Refusing beats truncating a 32-byte command
    /// into a report that would still be delivered and still mean something.
    #[test]
    fn rejects_reports_that_cannot_carry_the_protocol() {
        let short = Identity {
            input_len: 17,
            output_len: 17,
            ..raw_hid()
        };
        assert_eq!(
            short.check(VID, PID),
            Err(Reject::ReportLen {
                input: 17,
                output: 17
            })
        );
    }

    #[test]
    fn a_one_way_collection_is_refused_too() {
        let read_only = Identity {
            output_len: 0,
            ..raw_hid()
        };
        assert!(matches!(
            read_only.check(VID, PID),
            Err(Reject::ReportLen { output: 0, .. })
        ));
    }

    /// The messages end up in front of an owner with one keyboard and no
    /// context, so they have to name the actual problem.
    #[test]
    fn rejections_say_what_was_wrong() {
        let msg = Reject::Usage {
            page: 0x01,
            usage: 0x06,
        }
        .to_string();
        assert!(msg.contains("0x0001"), "{msg}");
        assert!(msg.contains("0xFF60"), "{msg}");
    }
}
