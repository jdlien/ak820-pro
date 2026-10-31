//! The deep sleep's dev-build records (firmware `sleep.h`), as
//! `scripts/deep_sleep.py` and the bench's slot reader decode them:
//! `HC_DEVHOOK` op 14 sub 4's record (read only: arg 0), and op 24's slots --
//! the wake ring (0-7), the last stray's snapshot (8), the sleep under way
//! kept through a reset (9) and as this boot inherited it (10), and the wake
//! window's interrupt census (11, since 10-31). Pure decoding; the CLI reads.

pub const DEVHOOK: u8 = 0x76;
pub const OP_SLEEP: u8 = 14;
pub const OP_SLOT: u8 = 24;
/// Slots 0..=11 on the firmware since 10-31; older ones answer up to 10.
pub const SLOTS: u8 = 12;
/// `ds_last_t`'s magic: "DSL3" since the census, "DSL2" before it.
pub const MAGIC_DSL3: u32 = 0x4453_4C33;
pub const MAGIC_DSL2: u32 = 0x4453_4C32;

fn u16le(b: &[u8], i: usize) -> u16 {
    u16::from_le_bytes([b[i], b[i + 1]])
}

fn u32le(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes([b[i], b[i + 1], b[i + 2], b[i + 3]])
}

/// `SLEEP_WAKE_*`; 2 is the cap or the backstop.
pub fn reason(r: u8) -> String {
    match r {
        0 => "none".into(),
        1 => "key".into(),
        2 => "cap".into(),
        3 => "strays".into(),
        4 => "blocked".into(),
        5 => "knob".into(),
        6 => "charge".into(),
        r => format!("reason_{r}"),
    }
}

fn names(bits: u32, table: &[(u32, &str)]) -> String {
    let mut out: Vec<String> = table.iter().filter(|(m, _)| bits & m != 0).map(|(_, n)| (*n).to_string()).collect();
    let rest = table.iter().fold(bits, |b, (m, _)| b & !m);
    if rest != 0 {
        out.push(format!("0x{rest:x}"));
    }
    if out.is_empty() { "-".into() } else { out.join(",") }
}

/// `SLEEP_V_*`, the record's and the ring's flags.
pub fn v_flags(f: u8) -> String {
    names(
        f as u32,
        &[(0x01, "pcf"), (0x02, "acq"), (0x04, "usb_sof"), (0x08, "reattach"), (0x10, "usb_20s"),
          (0x20, "pll_ceiling"), (0x40, "slept"), (0x80, "bound")],
    )
}

/// `ds_last_t`'s flags (slot 9 and 10).
pub fn last_flags(f: u8) -> String {
    names(f as u32, &[(0x01, "clk_ceiling"), (0x20, "pll_ceiling"), (0x40, "slept"), (0x80, "returned")])
}

/// USB INSTS (the LLD's `usbhw.h`); bits 0-16 are the endpoints' ACK/NAK.
pub fn insts(v: u32) -> String {
    names(
        v,
        &[(1 << 17, "ERR_TIMEOUT"), (1 << 18, "ERR_SETUP"), (1 << 19, "EP0_OUT_STALL"), (1 << 20, "EP0_IN_STALL"),
          (1 << 21, "EP0_OUT"), (1 << 22, "EP0_IN"), (1 << 23, "EP0_SETUP"), (1 << 24, "EP0_PRESETUP"),
          (1 << 25, "BUS_WAKEUP"), (1 << 26, "SOF"), (1 << 29, "BUS_RESUME"), (1 << 30, "BUS_SUSPEND"),
          (1 << 31, "BUS_RESET")],
    )
}

/// USB CFG's top byte (bits 24-31).
pub fn cfg_top(b: u8) -> String {
    names(
        b as u32,
        &[(0x01, "VREG33DIS_EN"), (0x02, "USBRAM_EN"), (0x04, "DIS_PDEN"), (0x08, "ESD_EN"), (0x10, "SIE_EN"),
          (0x20, "DPPU_EN"), (0x40, "PHY_EN"), (0x80, "VREG33_EN")],
    )
}

/// USB INTEN's top byte (bits 24-31).
pub fn inten_top(b: u8) -> String {
    names(b as u32, &[(0x10, "BUSWK_IE"), (0x20, "USB_IE"), (0x40, "SOF_IE"), (0x80, "BUS_IE")])
}

/// The SN32F29x's IRQ numbers (`SN32F290.h`).
pub fn irq_name(n: u32) -> String {
    let name = match n {
        0 => "NDT", 1 => "USB", 2 => "LCD", 3 => "I2S0", 4 => "I2S1", 5 => "CMP3", 6 => "SPI0", 7 => "SPI1",
        8 => "UART2", 9 => "UART3", 10 => "I2C0", 11 => "I2C1", 12 => "CMP2", 13 => "UART0", 14 => "UART1",
        15 => "CT16B0", 16 => "CT16B1", 17 => "CT16B2", 18 => "CMP1", 19 => "CT16B3", 20 => "CT16B4",
        21 => "CT16B5", 22 => "EBI", 23 => "RTC", 24 => "ADC", 25 => "WDT", 26 => "LVD", 27 => "CMP0",
        28 => "P3", 29 => "P2", 30 => "P1", 31 => "P0",
        _ => return format!("irq{n}"),
    };
    name.into()
}

/// An IPSR value: 0 none, 15 SysTick, 16 + n an IRQ.
pub fn ipsr_name(e: u8) -> String {
    match e {
        0 => "none".into(),
        15 => "SysTick".into(),
        16..=47 => irq_name(e as u32 - 16),
        e => format!("exception {e}"),
    }
}

fn irq_set(mask: u32) -> String {
    let v: Vec<String> = (0..32).filter(|n| mask & (1 << n) != 0).map(irq_name).collect();
    if v.is_empty() { "-".into() } else { v.join(",") }
}

/// Op 14 sub 4's record (version 2): the last sleep as the page keeps it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Record {
    pub state: u8,
    pub reason: u8,
    pub blocked: u16,
    pub flags: u8,
    pub secs: u32,
    pub strays: u16,
    pub p0: u16,
    pub p2: u16,
    pub p1: u32,
    pub pll_loops: u16,
    pub key_gain: u16,
    pub sleeps: u16,
    pub timed_out: u8,
}

impl Record {
    /// From the whole reply: `[status, channel, command, op, sub, record...]`.
    pub fn decode(report: &[u8]) -> Result<Record, String> {
        if report.len() < 32 {
            return Err("short reply".into());
        }
        if report[3] != OP_SLEEP || report[4] != 4 {
            return Err(format!("a reply to another op ({:02X?})", &report[..6]));
        }
        let o = &report[5..32];
        if o[0] != 2 {
            return Err(format!("sleep record version {}, not 2", o[0]));
        }
        Ok(Record {
            state: o[1],
            reason: o[2],
            blocked: u16le(o, 3),
            flags: o[5],
            secs: u32le(o, 6),
            strays: u16le(o, 10),
            p0: u16le(o, 12),
            p2: u16le(o, 14),
            p1: u32le(o, 16),
            pll_loops: u16le(o, 20),
            key_gain: u16le(o, 22),
            sleeps: u16le(o, 24),
            timed_out: o[26],
        })
    }

    pub fn render(&self) -> String {
        const STEPS: [&str; 7] = ["input", "clock", "gauge", "radio", "supply", "usb", "display"];
        let timed: Vec<&str> = (0..7).filter(|i| self.timed_out & (1 << i) != 0).map(|i| STEPS[i]).collect();
        format!(
            "last sleep: woke on {} after {} counted s; flags {}; strays {}; pins P0 0x{:x} P1 0x{:x} P2 0x{:x}; \
             pll_loops {}; keys gained {}; sleeps this boot {}; blocked 0x{:04x}; timed out {}\n",
            reason(self.reason), self.secs, v_flags(self.flags), self.strays, self.p0, self.p1, self.p2,
            self.pll_loops, self.key_gain, self.sleeps, self.blocked,
            if timed.is_empty() { "-".into() } else { timed.join(",") }
        )
    }
}

/// One op 24 slot's 28 bytes, decoded by its number.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Slot {
    Ring { slot: u8, seq: u16, reason: u8, flags: u8, counted: u32, p0: u32, p1: u32, p2: u32, ms: u32, strays: u16, next: u16 },
    Stray { seq: u16, same_s: u16, first_s: u32, ispr: u32, icsr: u32, flags: u16, last_n: u16, last_ispr: u32, last_icsr: u32 },
    Last { slot: u8, magic: u32, seq: u16, reason: u8, flags: u8, secs: u32, p0: u32, p1: u32, p2: u32, strays: u16, kept: u8, rstst: u8 },
    Census { n_all: u32, n_usb: u32, seen: u32, insts: u32, last: u8, flags: u8, cfg: u8, inten: u8, seq: u16, kept: u8, rstst: u8 },
}

impl Slot {
    /// `s` is the reply's bytes 4..32.
    pub fn decode(slot: u8, s: &[u8]) -> Result<Slot, String> {
        if s.len() < 28 {
            return Err("short slot".into());
        }
        Ok(match slot {
            0..=7 => Slot::Ring {
                slot,
                seq: u16le(s, 0),
                reason: s[2],
                flags: s[3],
                counted: u32le(s, 4),
                p0: u32le(s, 8),
                p1: u32le(s, 12),
                p2: u32le(s, 16),
                ms: u32le(s, 20),
                strays: u16le(s, 24),
                next: u16le(s, 26),
            },
            8 => Slot::Stray {
                seq: u16le(s, 0),
                same_s: u16le(s, 2),
                first_s: u32le(s, 4),
                ispr: u32le(s, 8),
                icsr: u32le(s, 12),
                flags: u16le(s, 16),
                last_n: u16le(s, 18),
                last_ispr: u32le(s, 20),
                last_icsr: u32le(s, 24),
            },
            9 | 10 => Slot::Last {
                slot,
                magic: u32le(s, 0),
                seq: u16le(s, 4),
                reason: s[6],
                flags: s[7],
                secs: u32le(s, 8),
                p0: u32le(s, 12),
                p1: u32le(s, 16),
                p2: u32le(s, 20),
                strays: u16le(s, 24),
                kept: s[26],
                rstst: s[27],
            },
            11 => Slot::Census {
                n_all: u32le(s, 0),
                n_usb: u32le(s, 4),
                seen: u32le(s, 8),
                insts: u32le(s, 12),
                last: s[16],
                flags: s[17],
                cfg: s[18],
                inten: s[19],
                seq: u16le(s, 20),
                kept: s[26],
                rstst: s[27],
            },
            n => return Err(format!("no slot {n}")),
        })
    }

    pub fn render(&self) -> String {
        match self {
            Slot::Ring { slot, seq, reason: r, flags, counted, p0, p1, p2, ms, strays, next } => {
                if *seq == 0 && *counted == 0 && *ms == 0 && *r == 0 {
                    return format!("ring[{slot}]  empty (next sleep #{next})\n");
                }
                format!(
                    "ring[{slot}]  sleep #{seq}: woke on {} after {counted} counted s, at {ms} ms uptime; flags {}; \
                     strays {strays}; pins P0 0x{p0:x} P1 0x{p1:x} P2 0x{p2:x}\n",
                    reason(*r), v_flags(*flags)
                )
            }
            Slot::Stray { seq, same_s, first_s, ispr, icsr, flags, last_n, last_ispr, last_icsr } => {
                if *last_n == 0 {
                    return "stray    none kept\n".into();
                }
                format!(
                    "stray    sleep #{seq}: first in counted s {first_s} ({same_s} within it), {last_n} in all; \
                     flags 0x{flags:04x}; ISPR 0x{ispr:08x} ICSR 0x{icsr:08x}; at the latest ISPR 0x{last_ispr:08x} ICSR 0x{last_icsr:08x}\n"
                )
            }
            Slot::Last { slot, magic, seq, reason: r, flags, secs, p0, p1, p2, strays, kept, rstst } => {
                let what = if *slot == 9 { "sleep    " } else { "inherited" };
                let magic_ok = matches!(*magic, MAGIC_DSL3 | MAGIC_DSL2);
                if *magic == 0 {
                    return format!("{what} none (boot RSTST 0x{rstst:02x})\n");
                }
                format!(
                    "{what} #{seq}: {} after {secs} counted s; flags {}; strays {strays}; pins P0 0x{p0:x} P1 0x{p1:x} P2 0x{p2:x}; \
                     {}{}; boot RSTST 0x{rstst:02x}\n",
                    if *r == 0 { "no wake recorded".to_string() } else { format!("woke on {}", reason(*r)) },
                    last_flags(*flags),
                    if *slot == 9 { if *kept != 0 { "inherited through a reset" } else { "this boot's" } }
                    else if *kept != 0 { "kept at this boot" } else { "none at this boot" },
                    if magic_ok { String::new() } else { format!(" (magic 0x{magic:08x}?)") },
                )
            }
            Slot::Census { n_all, n_usb, seen, insts: is, last, flags, cfg, inten, seq, kept: _, rstst } => {
                let state = names(
                    *flags as u32,
                    &[(0x01, "counting"), (0x02, "opened"), (0x04, "closed"), (0x08, "frozen")],
                );
                if *flags == 0 {
                    return format!("census   none (boot RSTST 0x{rstst:02x})\n");
                }
                format!(
                    "census   sleep #{seq} [{state}]: {n_all} handler entries, {n_usb} USB; seen {}; last {}; \
                     USB INSTS {} (0x{is:08x}), CFG {}, INTEN {}\n",
                    irq_set(*seen), ipsr_name(*last), insts(*is), cfg_top(*cfg), inten_top(*inten)
                )
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn slot_bytes(fill: &[(usize, &[u8])]) -> [u8; 28] {
        let mut s = [0u8; 28];
        for (at, b) in fill {
            s[*at..*at + b.len()].copy_from_slice(b);
        }
        s
    }

    #[test]
    fn the_record_decodes_as_deep_sleep_py_does() {
        let mut r = [0u8; 32];
        r[..5].copy_from_slice(&[0x02, 0x13, DEVHOOK, OP_SLEEP, 4]);
        let o = &mut r[5..];
        o[0] = 2;
        o[1] = 2;
        o[2] = 1;
        o[5] = 0x41;
        o[6..10].copy_from_slice(&95u32.to_le_bytes());
        o[12..14].copy_from_slice(&0x0010u16.to_le_bytes());
        o[24..26].copy_from_slice(&7u16.to_le_bytes());
        o[26] = 0b10_0000;
        let rec = Record::decode(&r).unwrap();
        assert_eq!((rec.reason, rec.secs, rec.p0, rec.sleeps), (1, 95, 0x10, 7));
        let text = rec.render();
        assert!(text.contains("woke on key after 95 counted s"), "{text}");
        assert!(text.contains("flags pcf,slept"), "{text}");
        assert!(text.contains("timed out usb"), "{text}");
        r[5] = 1;
        assert!(Record::decode(&r).unwrap_err().contains("version 1"));
        r[3] = 24;
        assert!(Record::decode(&r).unwrap_err().contains("another op"));
    }

    #[test]
    fn a_ring_entry_and_an_empty_one() {
        let s = slot_bytes(&[(0, &12u16.to_le_bytes()), (2, &[5, 0x40]), (4, &270u32.to_le_bytes()),
                             (8, &0x8000u32.to_le_bytes()), (20, &123_456u32.to_le_bytes()), (26, &13u16.to_le_bytes())]);
        let t = Slot::decode(4, &s).unwrap().render();
        assert!(t.starts_with("ring[4]  sleep #12: woke on knob after 270 counted s, at 123456 ms uptime; flags slept"), "{t}");
        assert!(t.contains("P0 0x8000"), "{t}");
        let empty = slot_bytes(&[(26, &3u16.to_le_bytes())]);
        assert_eq!(Slot::decode(1, &empty).unwrap().render(), "ring[1]  empty (next sleep #3)\n");
    }

    #[test]
    fn the_kept_sleep_says_whether_it_came_through_a_reset() {
        let s = slot_bytes(&[(0, &MAGIC_DSL3.to_le_bytes()), (4, &9u16.to_le_bytes()), (6, &[0, 0x40]),
                             (8, &480u32.to_le_bytes()), (26, &[1, 0x03])]);
        let t = Slot::decode(9, &s).unwrap().render();
        assert!(t.starts_with("sleep     #9: no wake recorded after 480 counted s; flags slept;"), "{t}");
        assert!(t.contains("inherited through a reset; boot RSTST 0x03"), "{t}");
        let t10 = Slot::decode(10, &s).unwrap().render();
        assert!(t10.starts_with("inherited #9:") && t10.contains("kept at this boot"), "{t10}");
        let odd = slot_bytes(&[(0, &0x1234_5678u32.to_le_bytes())]);
        assert!(Slot::decode(9, &odd).unwrap().render().contains("(magic 0x12345678?)"));
        assert_eq!(Slot::decode(10, &[0u8; 28]).unwrap().render(), "inherited none (boot RSTST 0x00)\n");
    }

    #[test]
    fn the_census_names_a_usb_storm() {
        // A reset inside the window: frozen, millions of USB entries, the
        // last one USB's (IPSR 17), ERR_TIMEOUT held, PHY_EN on, ESD_EN off.
        let s = slot_bytes(&[(0, &4_000_000u32.to_le_bytes()), (4, &3_999_990u32.to_le_bytes()),
                             (8, &((1u32 << 1) | (1 << 16) | (1 << 8)).to_le_bytes()),
                             (12, &(1u32 << 17).to_le_bytes()), (16, &[17, 0x0A, 0xF0, 0xB0]),
                             (20, &9u16.to_le_bytes()), (26, &[1, 0x03])]);
        let t = Slot::decode(11, &s).unwrap().render();
        assert!(t.starts_with("census   sleep #9 [opened,frozen]: 4000000 handler entries, 3999990 USB; seen USB,UART2,CT16B1; last USB;"), "{t}");
        assert!(t.contains("USB INSTS ERR_TIMEOUT (0x00020000)"), "{t}");
        assert!(t.contains("CFG SIE_EN,DPPU_EN,PHY_EN,VREG33_EN"), "{t}");
        assert!(t.contains("INTEN BUSWK_IE,USB_IE,BUS_IE"), "{t}");
        assert_eq!(Slot::decode(11, &[0u8; 28]).unwrap().render(), "census   none (boot RSTST 0x00)\n");
        assert!(Slot::decode(12, &s).is_err());
    }

    #[test]
    fn names_keep_the_bits_they_do_not_know() {
        assert_eq!(insts(0x3), "0x3");
        assert_eq!(insts(0), "-");
        assert_eq!(ipsr_name(15), "SysTick");
        assert_eq!(ipsr_name(16 + 23), "RTC");
        assert_eq!(ipsr_name(3), "exception 3");
    }
}
