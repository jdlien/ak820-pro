//! The flash channel -- **reads only**.
//!
//! `ak820ctl` keeps provisioning. That is a deliberate boundary, not an
//! oversight: `ak820ctl flash write` **erases first**, it is rare and
//! interactive, and an unattended daemon has no business holding a command that
//! can destroy the LCD assets. Nothing here erases, programs or unlocks, and
//! nothing here should grow the ability to.
//!
//! What is here is `FC_INFO`, because it is the cheapest question the board can
//! answer that proves the whole path works: discovery found the right
//! interface, the framing is right, the reply was correlated to the request,
//! and the answer matches a second implementation. That makes it the phase-0
//! gate.

use crate::hid::device::{Device, Reply, REQUEST_TIMEOUT};
use crate::hid::{Drained, Error as HidError};
use crate::proto::Channel;

/// `FC_INFO` -- JEDEC id and the address writes are allowed from.
pub const INFO: u8 = 0x01;

/// The status byte every flash reply carries in `data[3]`.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Status {
    Ok,
    /// The chip is busy. The firmware never blocks on it -- a synchronous erase
    /// would stall the matrix scan -- so it says so and the host re-sends.
    Busy,
    /// Write floor, locked, or the animation owns the SPI bus.
    Refused,
    BadArg,
    /// A CRC is still running; send `FC_CRC_NEXT`.
    More,
    Unknown(u8),
}

impl Status {
    pub fn from_byte(b: u8) -> Status {
        match b {
            0x00 => Status::Ok,
            0x01 => Status::Busy,
            0x02 => Status::Refused,
            0x03 => Status::BadArg,
            0x04 => Status::More,
            other => Status::Unknown(other),
        }
    }
}

impl std::fmt::Display for Status {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Status::Ok => write!(f, "ok"),
            Status::Busy => write!(f, "busy"),
            Status::Refused => write!(
                f,
                "refused (write floor / locked / animation running)"
            ),
            Status::BadArg => write!(f, "bad argument"),
            Status::More => write!(f, "in progress"),
            Status::Unknown(b) => write!(f, "unknown status {b:#04X}"),
        }
    }
}

/// What `FC_INFO` reports.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct Info {
    /// Manufacturer, memory type, capacity -- three bytes, as the chip returns
    /// them to the `0x9F` command.
    pub jedec: u32,
    /// Writes below this are refused unless unlocked, and the stock LCD assets
    /// are never writable at all.
    pub asset_base: u32,
}

#[derive(Debug)]
pub enum Error {
    Hid(HidError),
    /// The board answered our command and refused it.
    Flash(Status),
}

impl From<HidError> for Error {
    fn from(e: HidError) -> Self {
        Error::Hid(e)
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Hid(e) => write!(f, "{e}"),
            Error::Flash(s) => write!(f, "flash: {s}"),
        }
    }
}

impl std::error::Error for Error {}

/// Decode an `FC_INFO` reply.
///
/// Both fields are 24-bit **big-endian**, which is how the SPI chip clocks the
/// id out and how the firmware copies it through. Every other multi-byte field
/// in this protocol is little-endian, so this one is the exception worth
/// keeping a test on.
pub fn decode_info(report: &[u8]) -> Result<Info, Status> {
    let be24 = |b: &[u8]| ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
    match Status::from_byte(report[3]) {
        Status::Ok => Ok(Info {
            jedec: be24(&report[4..7]),
            asset_base: be24(&report[7..10]),
        }),
        other => Err(other),
    }
}

/// Ask the board what its flash is.
///
/// Retries `FS_BUSY` a few times because the firmware returns it rather than
/// blocking. `ak820ctl` retries this up to 2000 times, which is right for a
/// streaming write against a chip mid-erase; `FC_INFO` only reads a register,
/// so a short bound is the honest one here.
///
/// Returns what had to be discarded alongside the answer, accumulated across
/// retries. Dropping it would throw away the only direct evidence that another
/// process is talking to the same board.
pub fn read_info(dev: &Device) -> Result<(Info, Vec<Drained>), Error> {
    let mut discarded = Vec::new();
    for _ in 0..8 {
        let Reply { report, drained } =
            dev.request(Channel::Flash, INFO, &[], REQUEST_TIMEOUT)?;
        discarded.extend(drained);
        match decode_info(&report) {
            Ok(info) => return Ok((info, discarded)),
            Err(Status::Busy) => continue,
            Err(other) => return Err(Error::Flash(other)),
        }
    }
    Err(Error::Flash(Status::Busy))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::REPORT_LEN;

    fn reply(bytes: &[u8]) -> Vec<u8> {
        let mut r = vec![0u8; REPORT_LEN];
        r[..bytes.len()].copy_from_slice(bytes);
        r
    }

    /// The asset base is not a guess: `FLASH_ASSET_BASE` in
    /// `graphics/lcd_bus.h` is `0x0CE0000`, and the firmware sends its low
    /// three bytes.
    #[test]
    fn decodes_the_asset_base_the_firmware_sends() {
        let r = reply(&[0x07, 0x11, 0x01, 0x00, 0xEF, 0x40, 0x18, 0xCE, 0x00, 0x00]);
        let info = decode_info(&r).unwrap();
        assert_eq!(info.asset_base, 0x0CE_0000);
        assert_eq!(info.jedec, 0xEF_4018);
    }

    /// Big-endian, unlike every other multi-byte field on this wire. Read the
    /// other way round, `0xEF4018` becomes `0x1840EF` and still looks like a
    /// JEDEC id.
    #[test]
    fn the_fields_are_big_endian() {
        let r = reply(&[0x07, 0x11, 0x01, 0x00, 0x01, 0x02, 0x03, 0x0A, 0x0B, 0x0C]);
        let info = decode_info(&r).unwrap();
        assert_eq!(info.jedec, 0x01_0203);
        assert_eq!(info.asset_base, 0x0A_0B0C);
    }

    #[test]
    fn a_refusal_is_not_an_answer() {
        let r = reply(&[0x07, 0x11, 0x01, 0x02, 0xEF, 0x40, 0x18]);
        assert_eq!(decode_info(&r), Err(Status::Refused));
    }

    #[test]
    fn busy_is_distinguishable_so_it_can_be_retried() {
        let r = reply(&[0x07, 0x11, 0x01, 0x01]);
        assert_eq!(decode_info(&r), Err(Status::Busy));
    }

    #[test]
    fn status_bytes_map_to_the_firmwares_names() {
        for (byte, text) in [
            (0x00u8, "ok"),
            (0x01, "busy"),
            (0x03, "bad argument"),
            (0x04, "in progress"),
        ] {
            assert_eq!(Status::from_byte(byte).to_string(), text);
        }
        assert!(Status::from_byte(0x02).to_string().starts_with("refused"));
        assert_eq!(Status::from_byte(0x77), Status::Unknown(0x77));
    }
}
