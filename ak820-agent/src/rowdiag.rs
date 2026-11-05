//! The row ISR's dev-build records, as `scripts/rowisr_diag.py record` and
//! `scripts/overrun_diag.py status` decode them: `HC_DEVHOOK` op 28 sub 5 (the
//! handler's record: omissions, spurious invocations, epoch losses), op 20 and op
//! 22 (the longest handlers and the UART's overruns) and ops 25 and 26 (the 20 kHz
//! tick's gap monitor and its ring: how long the tick went unserved, and the main
//! loop's scope at the time). Together they say what held the row handler off: the
//! tick sits one priority above it, so a gap at the tick means a mask or a handler
//! above both, and a missed slot with no gap means a holder only the row handler
//! feels: SPI0 at its own priority, or `sn32f2xx_row_irq_hold()`. Pure decoding.

pub const DEVHOOK: u8 = 0x76;
pub const OP_SUMMARY: u8 = 20;
/// Op 20's sub that zeroes the overrun counts and the longest handlers.
pub const SUMMARY_ZERO: u8 = 1;
pub const OP_KIND: u8 = 22;
pub const OP_MON: u8 = 25;
pub const OP_MON_RING: u8 = 26;
pub const OP_ROW: u8 = 28;
pub const SUB_RECORD: u8 = 5;
/// `op 25`'s subs: 0 reads, the rest write the monitor's own state in RAM.
pub const MON_ON: u8 = 1;
pub const MON_OFF: u8 = 2;
pub const MON_ZERO: u8 = 3;
/// `op 26`'s pages; the firmware refuses one past its ring.
pub const MON_RING_PAGES: u8 = 8;

const TICK_HZ: f64 = 187_500.0;
const SCOPES: [&str; 13] = [
    "ch582", "batt", "disp_hk", "pump", "rtc", "rtc_fast", "leds", "health", "eecfg", "edge", "anim", "hk_other",
    "none",
];

fn u16le(b: &[u8], i: usize) -> u16 {
    u16::from_le_bytes([b[i], b[i + 1]])
}

fn u32le(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes([b[i], b[i + 1], b[i + 2], b[i + 3]])
}

/// Timer ticks to milliseconds, as the overrun diagnostic prints them.
pub fn ms(ticks: u16) -> f64 {
    (ticks as f64 * 1000.0 / TICK_HZ * 1000.0).round() / 1000.0
}

fn scope(i: u8) -> String {
    SCOPES.get(i as usize).map_or_else(|| format!("scope_{i}"), |s| (*s).to_string())
}

/// The reply's payload, past its four-byte header.
fn payload(r: &[u8; 32]) -> &[u8] {
    &r[4..]
}

/// Op 28 sub 5.
#[derive(Debug, PartialEq)]
pub struct Record {
    pub omit_run_max: u16,
    pub spurious: u8,
    pub late_omit: u8,
    pub epoch_losses: u8,
    pub invalid_services: u8,
    pub elapsed_min_us: f64,
    pub omit_row: [u8; 18],
    pub elapsed_crossed: u16,
}

pub fn record(r: &[u8; 32]) -> Record {
    let b = payload(r);
    let mut omit_row = [0u8; 18];
    omit_row.copy_from_slice(&b[8..26]);
    Record {
        omit_run_max: u16le(b, 0),
        spurious: b[2],
        late_omit: b[3],
        epoch_losses: b[4],
        invalid_services: b[5],
        elapsed_min_us: (u16le(b, 6) as f64 / 48.0 * 100.0).round() / 100.0,
        omit_row,
        elapsed_crossed: u16le(b, 26),
    }
}

/// Op 20: the overruns and the longest handlers since its reset.
#[derive(Debug, PartialEq)]
pub struct Summary {
    pub oe_obs: u32,
    pub oe_drain: u32,
    pub rx_drop: u32,
    pub uart_prio: u8,
    pub usb_max_ms: f64,
    pub st_max_ms: f64,
    pub ctx_pcf: u16,
    pub ctx_flash: u16,
    pub ctx_none: u16,
}

pub fn summary(r: &[u8; 32]) -> Summary {
    let b = payload(r);
    Summary {
        oe_obs: u32le(b, 0),
        oe_drain: u32le(b, 4),
        rx_drop: u32le(b, 8),
        uart_prio: b[15],
        usb_max_ms: ms(u16le(b, 16)),
        st_max_ms: ms(u16le(b, 18)),
        ctx_pcf: u16le(b, 20),
        ctx_flash: u16le(b, 22),
        ctx_none: u16le(b, 24),
    }
}

/// Op 22 sub 0xFF's UART2 handler maximum.
pub fn uart_max_ms(r: &[u8; 32]) -> f64 {
    ms(u16le(payload(r), 12))
}

/// Op 25.
#[derive(Debug, PartialEq)]
pub struct Mon {
    pub on: bool,
    pub max_ms: f64,
    pub n_128us: u32,
    pub n_197us: u32,
    pub n_347us: u32,
    pub ticks: u32,
    pub max_scope: String,
    pub max_act: u8,
    pub seq: u16,
}

pub fn mon(r: &[u8; 32]) -> Mon {
    let b = payload(r);
    Mon {
        on: b[0] != 0,
        max_ms: ms(u16le(b, 2)),
        n_128us: u32le(b, 4),
        n_197us: u32le(b, 8),
        n_347us: u32le(b, 12),
        ticks: u32le(b, 16),
        max_scope: scope(b[20]),
        max_act: b[21],
        seq: u16le(b, 22),
    }
}

/// One gap of 197 us or longer in op 26's ring.
#[derive(Debug, PartialEq)]
pub struct Gap {
    pub seq: u16,
    pub secs: u32,
    pub gap_ms: f64,
    pub scope: String,
    pub act: u8,
}

/// A page's two slots; an empty slot (sequence and gap both 0) is left out.
pub fn gaps(r: &[u8; 32]) -> Vec<Gap> {
    let b = payload(r);
    (0..2)
        .map(|j| &b[10 * j..10 * j + 10])
        .filter(|e| u16le(e, 0) != 0 || u16le(e, 6) != 0)
        .map(|e| Gap { seq: u16le(e, 0), secs: u32le(e, 2), gap_ms: ms(u16le(e, 6)), scope: scope(e[8]), act: e[9] })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reply(op: u8, fill: &[(usize, &[u8])]) -> [u8; 32] {
        let mut r = [0u8; 32];
        r[..4].copy_from_slice(&[0x02, 0x13, DEVHOOK, op]);
        for (at, bytes) in fill {
            r[4 + at..4 + at + bytes.len()].copy_from_slice(bytes);
        }
        r
    }

    #[test]
    fn record_fields_sit_where_the_bench_reads_them() {
        let row: Vec<u8> = (1..=18).collect();
        let r = reply(OP_ROW, &[(0, &[3, 0, 1, 52, 2, 9]), (6, &[0x80, 0x05]), (8, &row), (26, &[7, 1])]);
        let d = record(&r);
        assert_eq!((d.omit_run_max, d.spurious, d.late_omit, d.epoch_losses, d.invalid_services), (3, 1, 52, 2, 9));
        assert_eq!(d.elapsed_min_us, 29.33); // 1408 ticks at 48 MHz
        assert_eq!(d.omit_row[0], 1);
        assert_eq!(d.omit_row[17], 18);
        assert_eq!(d.elapsed_crossed, 263);
    }

    #[test]
    fn summary_names_the_longest_handlers() {
        // 15 ticks is 80 us at 187.5 kHz, the USB handler's measured maximum.
        let r = reply(OP_SUMMARY, &[(0, &[5, 0, 0, 0]), (15, &[0]), (16, &[15, 0, 3, 0]), (22, &[4, 0])]);
        let s = summary(&r);
        assert_eq!(s.oe_obs, 5);
        assert_eq!(s.uart_prio, 0);
        assert_eq!(s.usb_max_ms, 0.08);
        assert_eq!(s.st_max_ms, 0.016);
        assert_eq!(s.ctx_flash, 4);
    }

    #[test]
    fn uart_max_is_at_the_kind_replys_offset() {
        assert_eq!(uart_max_ms(&reply(OP_KIND, &[(12, &[2, 0])])), 0.011);
    }

    #[test]
    fn monitor_counts_and_scope() {
        let r = reply(
            OP_MON,
            &[(0, &[1]), (2, &[30, 0]), (4, &[9, 0, 0, 0]), (8, &[2, 0, 0, 0]), (16, &[0, 1, 0, 0]), (20, &[1, 0x40]), (22, &[6, 0])],
        );
        let m = mon(&r);
        assert!(m.on);
        assert_eq!(m.max_ms, 0.16);
        assert_eq!((m.n_128us, m.n_197us, m.n_347us, m.ticks), (9, 2, 0, 256));
        assert_eq!(m.max_scope, "batt");
        assert_eq!((m.max_act, m.seq), (0x40, 6));
    }

    #[test]
    fn an_unknown_scope_is_named_not_dropped() {
        assert_eq!(mon(&reply(OP_MON, &[(20, &[200])])).max_scope, "scope_200");
    }

    #[test]
    fn a_ring_page_leaves_out_its_empty_slot() {
        let r = reply(OP_MON_RING, &[(0, &[7, 0, 100, 0, 0, 0, 40, 0, 3, 0x11])]);
        let g = gaps(&r);
        assert_eq!(g.len(), 1);
        assert_eq!(g[0], Gap { seq: 7, secs: 100, gap_ms: 0.213, scope: "pump".into(), act: 0x11 });
    }
}
