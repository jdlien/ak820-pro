//! Page 7 (`HC_GET7`, protocol 9, the row handler's record) against
//! `ak820health.py`, as `health_parity.rs` does pages 1-4.
//!
//! `tests/fixtures/health-page7-capture-2026-11-02.txt` holds three page-7
//! replies from white on the row ISR's stage 2 (its header says where each
//! came from) and the window seconds; `health-page7-oracle-2026-11-02.txt` is
//! what `ak820health.py --sched [--window SECS]` printed for them, through
//! `scripts/health_oracle.py`, with the 09-06 page 1 ahead of them: a
//! `#### name` header per case, the text, `----`, the `--json`. Three cases:
//! the scan-only window (no handler sample: the means `None`, no CPU share),
//! the lit-to-scan-only window (both), and one read without a window.

use ak820_agent::health::{self, Page1, Page7};

const CAPTURE: &str = include_str!("fixtures/health-page7-capture-2026-11-02.txt");
const PAGE1: &str = include_str!("fixtures/health-capture-2026-09-06.txt");
const ORACLE: &str = include_str!("fixtures/health-page7-oracle-2026-11-02.txt");

fn field<'a>(text: &'a str, name: &str) -> &'a str {
    text.lines()
        .find(|l| l.starts_with(&format!("{name} ")))
        .unwrap_or_else(|| panic!("no {name} in the capture"))[name.len() + 1..]
        .trim()
}

fn bytes(text: &str, name: &str) -> Vec<u8> {
    field(text, name).split(' ').map(|h| u8::from_str_radix(h, 16).unwrap()).collect()
}

fn page7(name: &str) -> Page7 {
    Page7::decode(&bytes(CAPTURE, name)).unwrap()
}

/// One case's expected text and JSON.
fn case(name: &str) -> (String, String) {
    let oracle = ORACLE.replace("\r\n", "\n");
    let start = oracle.find(&format!("#### {name}\n")).unwrap_or_else(|| panic!("no case {name}"));
    let body = &oracle[start + name.len() + 6..];
    let body = &body[..body.find("#### ").unwrap_or(body.len())];
    let (text, json) = body.split_once("----\n").expect("the ---- separator");
    (text.to_string(), json.trim_end().to_string())
}

fn check(name: &str, p: &Page7, w: Option<&health::SchedWindow>) {
    let p1 = Page1::decode(&bytes(PAGE1, "page1")).unwrap();
    let (text, json) = case(name);
    assert_eq!(format!("{}{}", health::render_page1(&p1), health::render_sched(p, w)), text, "{name}: text");
    let got = health::render_json_with_sched(health::render_json(&p1, None, None, None), Some((p, w)));
    assert_eq!(got, json, "{name}: json");
}

#[test]
fn the_scan_only_window_renders_as_the_python_does() {
    let w = health::sched_window(&page7("page7pre"), &page7("page7scan"), field(CAPTURE, "swall_scan").parse().unwrap());
    assert_eq!((w.win_elapsed_mean_us, w.win_cpu_pct), (None, None));
    check("window_scan_only", &page7("page7scan"), Some(&w));
}

#[test]
fn the_lit_window_renders_as_the_python_does() {
    let w = health::sched_window(&page7("page7lit"), &page7("page7scan"), field(CAPTURE, "swall_lit").parse().unwrap());
    assert_eq!((w.win_elapsed_mean_us, w.win_cpu_pct), (Some(52.6), Some(8.92)));
    check("window_lit", &page7("page7scan"), Some(&w));
}

#[test]
fn one_read_renders_as_the_python_does() {
    check("single", &page7("page7scan"), None);
}

/// The numbers themselves, so a change to the rendering cannot mask one to
/// the decoding.
#[test]
fn the_record_decodes_to_the_pythons_values() {
    let p = page7("page7scan");
    assert_eq!((p.slots_elapsed, p.serviced_valid, p.missed_slots()), (8_390_933, 8_389_747, 1186));
    assert_eq!((p.pulses_emitted, p.pulses_omitted), (5_434_459, 65));
    assert_eq!((p.latency_max_us(), p.elapsed_max_us(), p.elapsed_mean_us()), (104.88, Some(207.83), Some(7.95)));
}

#[test]
fn a_clipped_maximum_and_an_older_board_are_said_so() {
    let mut r = bytes(CAPTURE, "page7scan");
    r[30] = 0xFF;
    r[31] = 0xFF;
    let p = Page7::decode(&r).unwrap();
    assert_eq!(p.elapsed_max_us(), None);
    assert!(health::render_sched(&p, None).contains("elapsed_max_us           >1365 (clipped)\n"));
    let json = health::render_json_with_sched("{}".into(), Some((&p, None)));
    assert!(json.starts_with("{\"slots_elapsed\": ") && json.contains("\"elapsed_max_us\": \">1365 (clipped)\""));
    r[3] = 8;
    assert_eq!(Page7::decode(&r), Err(health::Error::Version { have: 8, page: 7, need: 9 }));
}
