//! The lock-LED channel: now-playing to the board over Bluetooth, where there
//! is no raw HID, through the keyboard's LED output report
//! (`plans/LOCK-LED-CHANNEL-PLAN.md`).
//!
//! This module is the **encoder**: a frame as the sequence of LED bytes a host
//! writes, one write each. It is a port of `scripts/lockchan.py`, and that file
//! stays the oracle -- `scripts/lockchan_test.py` proves it against the board's
//! receiver (`lockchan.c`), and `tests/lockchan_parity.rs`, generated from it by
//! `scripts/gen_lockchan_vectors.py`, proves this against it. Never hand-edit
//! the parity file; regenerate it.
//!
//! `user` is the host's real lock state as HID LED bits (Num `0x01`, Caps
//! `0x02`, Scroll `0x04`). Every write keeps its Caps, and the frame ends back
//! on it.

pub mod clock;
pub mod frame;
pub mod policy;
pub mod sender;

/// Which LED bits carry data (the plan's "Profiles").
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Profile {
    /// Num and Scroll, base 3: the only one Windows can write.
    P0 = 0,
    /// Num and bits 3-4, base 7.
    P1 = 1,
    /// Num, Scroll and bits 3-4, base 15.
    P2 = 2,
    /// Bits 3-7, base 31: no light moves. The Mac's.
    P3 = 3,
}

pub const CAPS: u8 = 0x02;
pub const MAX_PAYLOAD: usize = 48;

struct Spec {
    mask: u8,
    bits: &'static [u8],
    base: u32,
    block_bits: u32,
    block_digits: u32,
    trailer: (u8, u8),
}

const fn spec(p: Profile) -> Spec {
    match p {
        Profile::P0 => Spec { mask: 0x05, bits: &[0x01, 0x04], base: 3, block_bits: 19, block_digits: 12, trailer: (0x01, 0x04) },
        Profile::P1 => Spec { mask: 0x19, bits: &[0x01, 0x08, 0x10], base: 7, block_bits: 14, block_digits: 5, trailer: (0x08, 0x10) },
        Profile::P2 => Spec { mask: 0x1D, bits: &[0x01, 0x04, 0x08, 0x10], base: 15, block_bits: 31, block_digits: 8, trailer: (0x08, 0x10) },
        Profile::P3 => Spec { mask: 0xF8, bits: &[0x08, 0x10, 0x20, 0x40, 0x80], base: 31, block_bits: 29, block_digits: 6, trailer: (0x08, 0x10) },
    }
}

/// The profile a frame's header is sent in: P2's header goes in P1.
fn header_profile(p: Profile) -> Profile {
    if p == Profile::P2 { Profile::P1 } else { p }
}

/// The bits a preamble's three transitions flip.
fn preamble(p: Profile) -> u8 {
    match p {
        Profile::P0 => 0x05,
        Profile::P1 | Profile::P2 => 0x18,
        Profile::P3 => 0xE0,
    }
}

/// The fewest base-`base` digits that hold `r` bits.
fn digits_for(base: u32, r: u32) -> u32 {
    let (mut n, mut p) = (0, 1u64);
    while p < 1u64 << r {
        p *= base as u64;
        n += 1;
    }
    n
}

pub fn crc8(data: &[u8]) -> u8 {
    let mut c = 0u8;
    for &b in data {
        c ^= b;
        for _ in 0..8 {
            c = if c & 0x80 != 0 { (c << 1) ^ 0x07 } else { c << 1 };
        }
    }
    c
}

/// CRC-16/CCITT-FALSE.
pub fn crc16(data: &[u8]) -> u16 {
    let mut c = 0xFFFFu16;
    for &b in data {
        c ^= (b as u16) << 8;
        for _ in 0..8 {
            c = if c & 0x8000 != 0 { (c << 1) ^ 0x1021 } else { c << 1 };
        }
    }
    c
}

/// The first `nbits` of `data`, most significant first, as the profile's
/// digits: blocks of the profile's size, the last in the fewest digits that
/// hold what is left.
fn to_digits(data: &[u8], nbits: u32, p: Profile) -> Vec<u8> {
    let s = spec(p);
    let bit = |i: u32| (data[(i / 8) as usize] >> (7 - i % 8)) & 1;
    let (mut out, mut at, mut left) = (Vec::new(), 0u32, nbits);
    while left > 0 {
        let bits = s.block_bits.min(left);
        let mut block = 0u64;
        for _ in 0..bits {
            block = block << 1 | bit(at) as u64;
            at += 1;
        }
        let n = if bits == s.block_bits { s.block_digits } else { digits_for(s.base, bits) };
        let mut ds = vec![0u8; n as usize];
        for d in ds.iter_mut().rev() {
            *d = (block % s.base as u64) as u8;
            block /= s.base as u64;
        }
        out.extend(ds);
        left -= bits;
    }
    out
}

/// Digit `d` as the set of LED bits a transition flips.
fn mask_of(p: Profile, d: u8) -> u8 {
    let sub = d as u32 + 1;
    spec(p).bits.iter().enumerate().filter(|(i, _)| sub >> i & 1 != 0).fold(0, |m, (_, b)| m | b)
}

fn header(p: Profile, kind: u8, seq: u8, len: u8) -> [u8; 4] {
    let h = [(p as u8) << 4 | kind, seq, len];
    [h[0], h[1], h[2], crc8(&h)]
}

#[derive(Debug, PartialEq, Eq)]
pub enum EncodeError {
    /// More than [`MAX_PAYLOAD`] bytes.
    TooLong(usize),
    /// A type past 15.
    BadType(u8),
}

/// A frame as the LED bytes to write, in order: the preamble, the header, the
/// payload and its CRC-16, and the trailer back to `user`'s Num/Caps/Scroll
/// with bits 3-7 clear.
pub fn encode(payload: &[u8], kind: u8, seq: u8, p: Profile, user: u8) -> Result<Vec<u8>, EncodeError> {
    if payload.len() > MAX_PAYLOAD {
        return Err(EncodeError::TooLong(payload.len()));
    }
    if kind > 15 {
        return Err(EncodeError::BadType(kind));
    }
    let h = header(p, kind, seq, payload.len() as u8);
    let mut body = h.to_vec();
    body.extend_from_slice(payload);
    let crc = crc16(&body);
    let mut body = payload.to_vec();
    body.extend_from_slice(&crc.to_be_bytes());
    let hp = header_profile(p);
    let sections = [(hp, to_digits(&h, 32, hp)), (p, to_digits(&body, body.len() as u32 * 8, p))];

    let start = user & 0x07;
    let mut state = start;
    let mut out = Vec::new();
    for _ in 0..3 {
        state ^= preamble(p);
        out.push(state);
    }
    for (prof, ds) in &sections {
        for &d in ds {
            state ^= mask_of(*prof, d);
            out.push(state);
        }
    }
    let s = spec(p);
    let (ta, tb) = s.trailer;
    let b = start & s.mask;
    let mid = b ^ if state & s.mask == b ^ ta { tb } else { ta };
    out.push((state & !s.mask) | mid);
    out.push((state & !s.mask) | b);
    Ok(out)
}

/// Frame types, version 0 (the plan's R2-9, frozen for the first release).
pub const TYPE_NOW_PLAYING: u8 = 1;
pub const TYPE_CLEAR: u8 = 2;

/// What the panel should show, as a frame's type and payload. This pair is
/// the channel's content identity (codex, sender design, 16): two snapshots
/// that fold and fit to the same bytes are the same content.
///
/// Type 1 is `[icon][n0][line 0][line 1]`, the lines exactly what raw HID's
/// `SET_LINE`s carry (folded to ASCII and fitted, 19 and 21); type 2 (idle) is
/// empty. Any byte the board would refuse becomes `?`, as the firmware's own
/// setter would draw it, so a frame is never rejected whole for one glyph.
pub fn content(snapshot: &crate::smtc::Snapshot) -> (u8, Vec<u8>) {
    use crate::text::{fit, Line};
    let Some((row0, row1, icon)) = snapshot.lines() else {
        return (TYPE_CLEAR, Vec::new());
    };
    let clean = |s: String| -> Vec<u8> {
        s.bytes().map(|b| if (0x20..=0x7E).contains(&b) { b } else { b'?' }).collect()
    };
    let l0 = clean(fit(row0, Line::WithIcon.budget()));
    let l1 = clean(fit(row1, Line::FullWidth.budget()));
    let mut p = vec![icon.id(), l0.len() as u8];
    p.extend(l0);
    p.extend(l1);
    (TYPE_NOW_PLAYING, p)
}

/// Type 3, the transport (10-20, "Play times"; the board's
/// `lockchan_media.h`): exactly `[icon][state][pos_hi][pos_lo][dur_hi][dur_lo]`,
/// the shown slot's icon and the playback readout. A new type rather than a
/// bit in type 1, which R2-9 froze (codex, the play-times review, P2 1): a
/// board before it rejects the frame whole and keeps its text. A play/pause or
/// a seek sends only this, ~6 bytes against the title's ~20-40.
pub const TYPE_TRANSPORT: u8 = 3;

/// Type 4, the wireless clock (the plan's "The wireless clock"): raw HID's
/// `RTC_SET_TIME_MS` body after its header, meaning "at this frame's anchor,
/// true local time was this". Flags 0, the bias unknown (no learner).
pub const TYPE_CLOCK: u8 = 4;

/// Type 4's payload for a local time and its milliseconds, or `None` outside
/// what the board accepts (2026-2098, the PCF's year % 100).
/// The type 4 flag: the host's clock stepped (or its offset moved) since its
/// last frame, so the board takes this one's offset as no measure of its rate
/// (the firmware's frame trim, 10-21). A board before it rejects the frame.
pub const CLOCK_F_STEPPED: u8 = 0x01;

pub fn clock_payload(t: &crate::clock::host::LocalTime, ms: u32, stepped: bool) -> Option<Vec<u8>> {
    if !(2026..=2098).contains(&t.year) {
        return None;
    }
    let ms = ms.min(crate::clock::set::MAX_MS) as u16;
    let bias = crate::clock::set::UNKNOWN_BIAS.to_le_bytes();
    Some(vec![
        (t.year - 2000) as u8,
        t.month,
        t.day,
        t.weekday,
        t.hour,
        t.minute,
        t.second,
        ms as u8,
        (ms >> 8) as u8,
        if stepped { CLOCK_F_STEPPED } else { 0 },
        bias[0],
        bias[1],
    ])
}

/// The local time at a Unix instant in milliseconds, through the host's own
/// `localtime` (the USB clock's, so the zone and DST match it).
pub fn local_at(host: &impl crate::clock::host::Host, unix_ms: i64) -> (crate::clock::host::LocalTime, u32) {
    (host.local(unix_ms.div_euclid(1000)), unix_ms.rem_euclid(1000) as u32)
}
/// A position this far from where the last one sent should be by now is a
/// seek: a change to send, not a tick (the policy's).
pub const SEEK_SLACK_S: u32 = 3;

/// A readout to show: only while playing with a known duration, the gate raw
/// HID's `Snapshot::playback` applies (foobar2000 reports pos 0 / dur 0 with
/// no timeline: codex, the play-times review, P2 3). Paused, stopped or a
/// stream, the board shows the clock, as it does over USB.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Playback {
    pub pos_s: u32,
    pub dur_s: u32,
}

impl Playback {
    pub fn of(snapshot: &crate::smtc::Snapshot) -> Option<Playback> {
        if snapshot.lines().is_none() {
            return None;
        }
        let (playing, pos_s, dur_s) = snapshot.playback();
        playing.then_some(Playback { pos_s, dur_s })
    }
}

/// Type 3's payload: the icon, the readout's state, and the position as of
/// the frame's pick (the sender adds the time since it was sampled), clamped
/// to the duration; both saturate at 0xFFFF seconds, as raw HID's do. With no
/// readout, state 0 and zeros: the board shows the clock.
pub fn transport(icon: crate::text::Icon, pb: Option<Playback>, pos_s: u32) -> (u8, Vec<u8>) {
    let sat = |v: u32| v.min(0xFFFF) as u16;
    let (state, pos, dur) = match pb {
        Some(p) => (1u8, sat(if p.dur_s > 0 { pos_s.min(p.dur_s) } else { pos_s }), sat(p.dur_s)),
        None => (0, 0, 0),
    };
    (TYPE_TRANSPORT, vec![icon.id(), state, (pos >> 8) as u8, pos as u8, (dur >> 8) as u8, dur as u8])
}

/// When a title frame must go again: its lines changed. Not its icon, which
/// type 3 carries, so a play/pause does not resend the title (a board before
/// type 3 then shows an old icon until the next refresh of type 1). A CLEAR is
/// its own identity.
pub fn text_identity(kind: u8, payload: &[u8]) -> (u8, Vec<u8>) {
    match kind {
        TYPE_NOW_PLAYING if !payload.is_empty() => (kind, payload[1..].to_vec()),
        _ => (kind, payload.to_vec()),
    }
}

/// When a transport frame must go again: the icon, whether a readout shows,
/// or its duration changed. Never the position, which moves every second: a
/// seek is told apart by [`is_seek`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct TransportIdentity {
    pub icon: u8,
    pub playing: bool,
    pub dur_s: u32,
}

pub fn transport_identity(icon: crate::text::Icon, pb: Option<Playback>) -> TransportIdentity {
    TransportIdentity { icon: icon.id(), playing: pb.is_some(), dur_s: pb.map_or(0, |p| p.dur_s) }
}

/// Whether `now_pos_s` is a seek from a position `sent_pos_s` picked `elapsed`
/// ago: further than SEEK_SLACK_S from where it should have got to, which
/// stops at a known duration (codex, P2 4: 299/300 then 300 at the end is not
/// a seek). `elapsed` runs from the position's sampling, never a frame's
/// completion.
pub fn is_seek(sent_pos_s: u32, elapsed: std::time::Duration, now_pos_s: u32, dur_s: u32) -> bool {
    let mut expect = sent_pos_s as u64 + elapsed.as_secs();
    if dur_s > 0 {
        expect = expect.min(dur_s as u64);
    }
    (now_pos_s as i64 - expect as i64).unsigned_abs() > SEEK_SLACK_S as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_clock_payload_is_raw_hids_ms_body() {
        use crate::clock::host::{utc_local, LocalTime};
        let t = utc_local(1_792_500_000); // 2026-10-19
        let p = clock_payload(&t, 1234, false).unwrap();
        assert_eq!(p.len(), 12);
        assert_eq!(&p[..7], &[26, t.month, t.day, t.weekday, t.hour, t.minute, t.second]);
        assert_eq!(u16::from_le_bytes([p[7], p[8]]), 999, "ms clamped");
        assert_eq!(p[9], 0, "flags");
        assert_eq!(i16::from_le_bytes([p[10], p[11]]), 0x7FFF, "the bias unknown");
        let early = LocalTime { year: 2025, ..t };
        assert!(clock_payload(&early, 0, false).is_none());
        let late = LocalTime { year: 2099, ..t };
        assert!(clock_payload(&late, 0, false).is_none());
        assert_eq!(clock_payload(&t, 0, true).unwrap()[9], CLOCK_F_STEPPED);
    }

    #[test]
    fn the_transport_is_six_bytes_the_icon_state_position_and_duration() {
        use crate::smtc::Snapshot;
        use crate::text::Icon;
        let s = Snapshot {
            artist: "Tonebox".into(),
            title: "Space Legionnaire".into(),
            icon: Icon::Play,
            playing: true,
            pos_s: 61,
            dur_s: 300,
        };
        let pb = Playback::of(&s).expect("playing, a title and a duration");
        assert_eq!(transport(Icon::Play, Some(pb), 63), (TYPE_TRANSPORT, vec![Icon::Play.id(), 1, 0, 63, 0x01, 0x2C]));
        // Clamped to the duration; saturating at 0xFFFF, as raw HID's.
        assert_eq!(transport(Icon::Play, Some(pb), 305).1[2..4], [0x01, 0x2C]);
        let long = Playback { pos_s: 70_000, dur_s: 99_999 };
        assert_eq!(transport(Icon::Play, Some(long), 70_000).1[2..], [0xFF, 0xFF, 0xFF, 0xFF]);
        // Paused: state 0, the clock.
        assert_eq!(transport(Icon::Pause, None, 0), (TYPE_TRANSPORT, vec![Icon::Pause.id(), 0, 0, 0, 0, 0]));
        // The gate: paused, nothing shown, or no known duration (foobar's 0/0).
        assert_eq!(Playback::of(&Snapshot { playing: false, ..s.clone() }), None);
        assert_eq!(Playback::of(&Snapshot { playing: true, ..Snapshot::default() }), None);
        assert_eq!(Playback::of(&Snapshot { pos_s: 0, dur_s: 0, ..s.clone() }), None);
    }

    #[test]
    fn identities_split_the_title_from_the_transport() {
        use crate::text::Icon;
        // The title's: the lines, not the icon.
        assert_eq!(text_identity(1, &[1, 1, b'a', b'b']), text_identity(1, &[2, 1, b'a', b'b']), "a pause is not a title change");
        assert_ne!(text_identity(1, &[1, 1, b'a', b'b']), text_identity(1, &[1, 1, b'a', b'c']));
        assert_ne!(text_identity(1, &[1, 0]), text_identity(TYPE_CLEAR, &[]));
        // The transport's: the icon, the readout, the duration; never the position.
        let p = |pos_s| Some(Playback { pos_s, dur_s: 300 });
        assert_eq!(transport_identity(Icon::Play, p(10)), transport_identity(Icon::Play, p(11)), "a tick");
        assert_ne!(transport_identity(Icon::Play, p(10)), transport_identity(Icon::Pause, None), "a pause");
        assert_ne!(transport_identity(Icon::Play, p(10)), transport_identity(Icon::Play, Some(Playback { pos_s: 10, dur_s: 301 })));
    }

    #[test]
    fn a_seek_is_a_jump_past_the_slack_and_the_end_is_not_one() {
        use std::time::Duration;
        let s = Duration::from_secs;
        assert!(!is_seek(10, s(5), 15, 300), "on time");
        assert!(!is_seek(10, s(5), 18, 300) && !is_seek(10, s(5), 12, 300), "within 3 s");
        assert!(is_seek(10, s(5), 19, 300), "ahead");
        assert!(is_seek(10, s(5), 11, 300), "behind");
        assert!(is_seek(200, s(1), 0, 300), "back to the start");
        // The end of a track: the position stops at the duration (codex, P2 4).
        assert!(!is_seek(299, s(5), 300, 300));
        assert!(!is_seek(299, s(60), 300, 300));
        // No known duration: no clamp.
        assert!(is_seek(299, s(5), 300, 0));
    }

    #[test]
    fn content_is_both_fitted_lines_or_clear() {
        use crate::smtc::Snapshot;
        use crate::text::Icon;
        assert_eq!(content(&Snapshot::default()), (TYPE_CLEAR, vec![]));
        let s = Snapshot {
            artist: "Cosmic Cadet".into(),
            title: "Europa - The Adventure Continues".into(),
            icon: Icon::Play,
            ..Snapshot::default()
        };
        let (t, p) = content(&s);
        assert_eq!(t, TYPE_NOW_PLAYING);
        assert_eq!(p[0], Icon::Play.id());
        let n0 = p[1] as usize;
        assert!(n0 <= 19 && p.len() - 2 - n0 <= 21 && p.len() <= 42);
        assert!(p[2..].iter().all(|b| (0x20..=0x7E).contains(b)));
        // The same bytes raw HID's SET_LINEs carry.
        let (row0, row1, _) = s.lines().unwrap();
        assert_eq!(&p[2..2 + n0], crate::text::fit(row0, 19).as_bytes());
        assert_eq!(&p[2 + n0..], crate::text::fit(row1, 21).as_bytes());
    }

    #[test]
    fn crcs_match_their_check_values() {
        assert_eq!(crc16(b"123456789"), 0x29B1); // CCITT-FALSE's check
        assert_eq!(crc8(b"123456789"), 0xF4); // poly 0x07, init 0
    }

    #[test]
    fn limits_are_refused() {
        assert_eq!(encode(&[0; 49], 1, 0, Profile::P0, 0), Err(EncodeError::TooLong(49)));
        assert_eq!(encode(b"x", 16, 0, Profile::P0, 0), Err(EncodeError::BadType(16)));
        assert!(encode(&[0; 48], 15, 255, Profile::P3, 7).is_ok());
    }

    #[test]
    fn every_write_keeps_caps_and_the_frame_ends_on_the_user() {
        for p in [Profile::P0, Profile::P1, Profile::P2, Profile::P3] {
            for user in 0..8u8 {
                let w = encode(b"Artist - Title", 1, 9, p, user).unwrap();
                assert!(w.iter().all(|&v| v & CAPS == user & CAPS), "{p:?} {user}");
                assert_eq!(*w.last().unwrap(), user);
                // Each write is a change: the receiver ignores repeats.
                let mut prev = user;
                for &v in &w {
                    assert_ne!(v, prev, "{p:?} {user}");
                    prev = v;
                }
            }
        }
    }

    #[test]
    fn p0_touches_only_num_and_scroll() {
        let w = encode(&[0xA5; 48], 2, 3, Profile::P0, 0x02).unwrap();
        assert!(w.iter().all(|&v| v & !0x07 == 0));
    }
}
