//! Phase 5's gate: decoding fixtures match `ak820health.py`.
//!
//! `tests/fixtures/health-capture-2026-09-06.txt` is five raw health replies
//! from this board (`scripts/health_capture.py`: pages 1–4, and page 4 again
//! 2.015 s later) and `health-oracle-2026-09-06.txt` is what `ak820health.py`
//! itself printed for those bytes — its text for `--stalls --rows --isr`, a
//! `----` line, then its `--json` — produced by `scripts/health_oracle.py`,
//! which drives the Python's own functions through a fake device. Sequential
//! live reads cannot match field for field (`tx_sent` moves between them);
//! the same bytes through both decoders can, and must.
//!
//! The capture also recorded the broadcast hazard on the Python side: the
//! first attempt's second page-4 read returned the daemon's playback echo,
//! and `ak820health.py` called it a garbled reply. Its capture script now
//! drains before each read, as this crate's transport always has.

use ak820_agent::health::{self, Page1, Page2, Page3, Page4};

const CAPTURE: &str = include_str!("fixtures/health-capture-2026-09-06.txt");
const ORACLE: &str = include_str!("fixtures/health-oracle-2026-09-06.txt");

fn page(name: &str) -> Vec<u8> {
    let line = CAPTURE
        .lines()
        .find(|l| l.starts_with(&format!("{name} ")))
        .unwrap_or_else(|| panic!("no {name} in the capture"));
    line[name.len() + 1..]
        .split(' ')
        .map(|h| u8::from_str_radix(h, 16).unwrap())
        .collect()
}

fn wall() -> f64 {
    CAPTURE
        .lines()
        .find(|l| l.starts_with("wall "))
        .and_then(|l| l[5..].trim().parse().ok())
        .expect("wall seconds in the capture")
}

#[test]
fn the_rendering_is_the_pythons_byte_for_byte() {
    // Python wrote the fixture on Windows, so its lines end in CRLF; the
    // renderings here are LF, as the Python's in-memory strings were.
    let oracle = ORACLE.replace("\r\n", "\n");
    let (expected_text, expected_json) = oracle.split_once("----\n").expect("the ---- separator");

    let p1 = Page1::decode(&page("page1")).unwrap();
    let p2 = Page2::decode(&page("page2")).unwrap();
    let p3 = Page3::decode(&page("page3")).unwrap();
    let a = Page4::decode(&page("page4")).unwrap();
    let b = Page4::decode(&page("page4b")).unwrap();
    let rates = health::isr_rates(&a, &b, wall(), p3.matrix_rows as u32);

    let text = format!(
        "{}{}{}{}",
        health::render_page1(&p1),
        health::render_page2(&p2),
        health::render_page3(&p3, Some(p2.key_presses)),
        health::render_isr(&rates)
    );
    assert_eq!(text, expected_text);

    let json = health::render_json(&p1, Some(&p2), Some(&p3), Some((&b, &rates)));
    assert_eq!(json, expected_json.trim_end());
}

/// The numbers themselves, so a change to the rendering cannot mask a change
/// to the decoding. These are the board's own counters on 2026-09-06 08:2x.
#[test]
fn the_captured_counters_decode_to_the_pythons_values() {
    let p1 = Page1::decode(&page("page1")).unwrap();
    assert_eq!(p1.version, 5);
    assert_eq!((p1.blit_timeouts, p1.tx_sent, p1.tx_timeouts, p1.tx_drops), (43, 11233, 5565, 0));
    assert_eq!((p1.rx_malformed, p1.loop_gap_max_ms, p1.scan_rate), (1, 105, 375));
    assert!(!p1.wdt_fired_last_boot() && !p1.wdt_degraded());

    let p2 = Page2::decode(&page("page2")).unwrap();
    assert_eq!((p2.count_ge_10ms, p2.count_ge_25ms, p2.count_ge_25ms_nonflash), (101, 14, 12));
    assert_eq!(p2.passes, 21_315_563);
    assert_eq!(p2.loop_gap_max_mark, health::Mark::None);

    let p3 = Page3::decode(&page("page3")).unwrap();
    assert_eq!(p3.row_samples, [15235, 15236, 15236, 15236, 15236, 15236]);
    assert_eq!((p3.row_gap_max_ms, p3.row_gap_max_row, p3.matrix_rows), (15, 2, 6));

    let b = Page4::decode(&page("page4b")).unwrap();
    assert_eq!((b.st_freq, b.isr_ticks_min, b.isr_ticks_max), (187_500, 2, 90));
    let a = Page4::decode(&page("page4")).unwrap();
    let r = health::isr_rates(&a, &b, wall(), 6);
    assert_eq!(r.isr_per_s, Some(3910.0));
    assert_eq!(r.isr_cpu_pct, Some(72.8));
    assert_eq!(r.timebase_vs_wall, Some(1.0035));
}
