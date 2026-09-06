//! Reading VIA's own lighting values back off the board.
//!
//! ⚠️ **A different protocol that shares the same interface.** Everything in
//! [`crate::proto`] is `[0x07, channel, command]` where the channel is one of
//! ours (`0x10`–`0x13`). VIA's custom-value protocol is `[command_id, channel,
//! value_id]` where the channel is one of *QMK's* (0–4). Our channel numbers
//! were chosen above QMK's precisely so the two can never collide, and that
//! separation is what this module relies on.
//!
//! ## Why this exists
//!
//! `plans/BACKLOG.md` records that any concurrent raw-HID user desyncs VIA
//! persistently — measured, with VIA's own error log. The board still
//! **executes** the commands; VIA only loses the confirmations. So after a
//! desync VIA's UI can disagree with the board, and the documented workaround
//! is to read the values back rather than trust the display.
//!
//! That matters more than it sounds, because `flash.sh` does **not** restore
//! RGB state: every flash reverts the LEDs to `rgb_matrix.default` in
//! `keyboard.json`. Knowing what the board actually holds is what lets that
//! default be kept equal to it.
//!
//! ## ⚠️ Read-only, and deliberately incapable of anything else
//!
//! The only id this module can emit is [`GET_VALUE`]. `id_custom_set_value`
//! (`0x07`) and `id_custom_save` (`0x09`) are named below so a reader knows
//! what is being avoided, and are never sent. Writing lighting is VIA's job;
//! this is a diagnostic.

use std::time::{Duration, Instant};

use crate::hid::exchange::{drain_until, Queue, Wire};
use crate::hid::{Drained, Error};
use crate::proto::{self, REPORT_LEN, WIRE_LEN};

/// `id_custom_get_value`. The only command this module sends.
pub const GET_VALUE: u8 = 0x08;
/// `id_custom_set_value` — named so it is obviously *not* used here.
pub const SET_VALUE_NEVER_SENT: u8 = 0x07;
/// `id_custom_save` — likewise.
pub const SAVE_NEVER_SENT: u8 = 0x09;

/// `id_qmk_rgb_matrix_channel`. QMK's own, not one of ours.
pub const RGB_MATRIX_CHANNEL: u8 = 3;

/// `via.json` declares `menus: ["qmk_rgb_matrix"]`, so these are QMK's stock
/// value ids rather than anything this board invented.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Value {
    Brightness = 1,
    Effect = 2,
    Speed = 3,
    Color = 4,
}

impl Value {
    pub fn id(self) -> u8 {
        self as u8
    }
}

/// What the board says its lighting is.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct Lighting {
    /// `val` in HSV terms, 0–255.
    pub brightness: u8,
    /// Index into the *enabled* effect list — see [`effect_name`].
    pub effect: u8,
    pub speed: u8,
    pub hue: u8,
    pub sat: u8,
}

/// ⚠️ **Index → name, and the indices are not stable across firmware builds.**
///
/// QMK numbers effects by walking `rgb_matrix_effects.inc` in order and
/// skipping every animation not enabled in `keyboard.json`. Enabling or
/// disabling *any* animation therefore renumbers all the ones after it — the
/// same append-only hazard `scripts/check_via_sync.py` guards for custom
/// keycodes, but with no guard here.
///
/// This table mirrors the seven animations enabled in
/// `keyboards/a_jazz/ak820pro/keyboard.json` as of 2026-09-06. If that set
/// changes, this is wrong and the number is the only thing worth trusting.
pub const EFFECT_NAMES: [&str; 8] = [
    "none",
    "solid_color",
    "alphas_mods",
    "cycle_all",
    "cycle_left_right",
    "cycle_up_down",
    "jellybean_raindrops",
    "typing_heatmap",
];

pub fn effect_name(index: u8) -> &'static str {
    EFFECT_NAMES.get(index as usize).copied().unwrap_or("unknown")
}

/// `[report id, GET_VALUE, channel, value id]`, zero padded.
fn frame(value: Value) -> [u8; WIRE_LEN] {
    let mut buf = [0u8; WIRE_LEN];
    buf[1] = GET_VALUE;
    buf[2] = RGB_MATRIX_CHANNEL;
    buf[3] = value.id();
    buf
}

/// Is this report the answer to `value`?
///
/// Same discipline as [`crate::proto::match_reply`], against VIA's layout: a
/// reply names the id, the channel and the value it answers, so anything else
/// on the handle is discarded rather than decoded.
fn is_reply(report: &[u8], value: Value) -> bool {
    report.len() >= 4
        && report[0] == GET_VALUE
        && report[1] == RGB_MATRIX_CHANNEL
        && report[2] == value.id()
}

/// Ask for one value.
pub fn get(wire: &impl Wire, value: Value, budget: Duration) -> Result<[u8; REPORT_LEN], Error> {
    let deadline = Instant::now()
        .checked_add(budget)
        .ok_or(Error::Timeout { drained: Vec::new() })?;

    let (drained, queue) = drain_until(wire, deadline);
    match queue {
        Queue::Empty => {}
        Queue::Stuck => return Err(Error::Stuck),
        _ => return Err(Error::Dirty { queue, drained }),
    }

    let left = deadline.saturating_duration_since(Instant::now());
    if left.is_zero() {
        return Err(Error::Timeout { drained });
    }
    wire.write_report(&frame(value), left.min(Duration::from_millis(1000)))?;

    let mut discarded: Vec<Drained> = drained;
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err(Error::Timeout { drained: discarded });
        }
        let Some(raw) = wire.read_report(left.min(Duration::from_millis(250)))? else {
            continue;
        };
        let report = match proto::normalize_input(&raw) {
            Ok(r) => r,
            Err(m) => {
                discarded.push(Drained::StaleUnreadable(m));
                continue;
            }
        };
        if is_reply(report, value) {
            let mut out = [0u8; REPORT_LEN];
            out.copy_from_slice(&report[..REPORT_LEN]);
            return Ok(out);
        }
        discarded.push(Drained::Foreign(proto::Mismatch::NotOurs {
            header: [report[0], report[1], report[2]],
        }));
    }
}

/// Read all four lighting values.
///
/// Four separate round trips because VIA's protocol has no batch form; each is
/// individually correlated, so a foreign reply landing between them cannot be
/// mistaken for one of ours.
pub fn read_lighting(wire: &impl Wire) -> Result<Lighting, Error> {
    let budget = Duration::from_millis(2000);
    let brightness = get(wire, Value::Brightness, budget)?[3];
    let effect = get(wire, Value::Effect, budget)?[3];
    let speed = get(wire, Value::Speed, budget)?[3];
    // Colour is the one that answers with two bytes.
    let colour = get(wire, Value::Color, budget)?;
    Ok(Lighting {
        brightness,
        effect,
        speed,
        hue: colour[3],
        sat: colour[4],
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_request_names_the_id_channel_and_value() {
        let f = frame(Value::Color);
        assert_eq!(&f[..4], &[0x00, 0x08, 0x03, 0x04]);
        assert!(f[4..].iter().all(|&b| b == 0));
    }

    /// ⚠️ The safety property of this module: it cannot express a write. If
    /// this ever fails, something has taught it to set or save.
    #[test]
    fn nothing_here_can_emit_a_set_or_a_save() {
        for value in [Value::Brightness, Value::Effect, Value::Speed, Value::Color] {
            let f = frame(value);
            assert_eq!(f[1], GET_VALUE);
            assert_ne!(f[1], SET_VALUE_NEVER_SENT);
            assert_ne!(f[1], SAVE_NEVER_SENT);
        }
    }

    #[test]
    fn a_reply_must_name_the_value_it_answers() {
        let brightness = [0x08, 0x03, 0x01, 86];
        assert!(is_reply(&brightness, Value::Brightness));
        assert!(!is_reply(&brightness, Value::Effect), "wrong value id");

        let ours = [0x07, 0x11, 0x01, 0x00];
        assert!(!is_reply(&ours, Value::Brightness), "our own flash reply");

        let set_echo = [0x07, 0x03, 0x01, 86];
        assert!(
            !is_reply(&set_echo, Value::Brightness),
            "somebody else's SET echo carries the same channel and value"
        );
    }

    /// Our channels sit above QMK's so the two protocols cannot collide. If a
    /// future channel is ever numbered below 5, this is where it shows up.
    #[test]
    fn our_channels_cannot_collide_with_qmks() {
        use crate::proto::Channel;
        for ours in [Channel::Rtc, Channel::Flash, Channel::Text, Channel::Health] {
            assert!(
                ours.id() > 4,
                "{ours:?} overlaps a QMK lighting channel and would be ambiguous"
            );
        }
        assert!(RGB_MATRIX_CHANNEL <= 4);
    }

    #[test]
    fn effect_names_cover_the_enabled_set_and_degrade_gracefully() {
        assert_eq!(effect_name(2), "alphas_mods");
        assert_eq!(effect_name(7), "typing_heatmap");
        assert_eq!(effect_name(99), "unknown");
    }
}
