//! Phase 3a (Windows) and Phase 2 (macOS): deterministic replay of the oracle's
//! own record, on each machine it has run on.
//!
//! Two corpora, both the Python timekeeper's logs, untouched:
//!
//! - `tests/fixtures/ak820pro-timekeeper-2026-09-05.log`: Windows,
//!   2026-09-05 11:36 to 2026-09-06 07:49.
//! - `tests/fixtures/ak820pro-timekeeper-macos-2026-09-16.log`: the Mac, from
//!   the restart onto the current learner (`94a4f3a`, 2026-09-04 11:16) to
//!   2026-09-16 20:00, just before the Rust daemon was installed beside it.
//!   4,166 lines, 1,469 `bias learned`, 605 `bias hold`, no failure lines.
//!
//! Every `bias learned` line names its inputs and its result (`before`,
//! `elapsed`, the old bias, the new one, `P`); every `bias hold` line names the
//! two periods the settled gate compared; every sync line's `before` decided
//! the interval to the next one, and the next one's timestamp shows what was
//! decided. So each log is a replay corpus for the learner's arithmetic, its
//! settled gate and the scheduler's interval choice, with the positive
//! evidence the parity document demands.
//!
//! What a log cannot give: `elapsed` is printed to whole seconds and `before`
//! to one decimal, so the arithmetic is replayed at that precision and a
//! result is accepted if the true elapsed within ±0.5 s could produce it.
//! `ref_state` is not logged; it is assumed 2 where learning fired, which it
//! must have been.
//!
//! ⚠️ **One macOS allowance, stated rather than hidden:** the Mac's timekeeper
//! runs as a `Background` LaunchAgent, at priority 4, and its 15 s loop
//! sometimes wakes late. So a macOS sync may come after the Windows tolerance
//! of `interval + LOOP + 5 s`. Of 2,077 intervals, 11 did (21 to 51 s over).
//! The replay allows at most 1% late and none more than 60 s over. **The early
//! edge, where the decision actually lives, is held exactly on both.**

use ak820_agent::clock::scheduler::{Learn, Reason, Scheduler, StatusRead, SyncResult, SYNC_INTERVAL, SYNC_INTERVAL_FAST, LOOP};

/// One log, and what it must show to count as positive evidence.
struct Corpus {
    name: &'static str,
    log: &'static str,
    min_learned: usize,
    min_holds: usize,
    min_runs: usize,
    min_steps: usize,
    min_learned_in_runs: usize,
    min_intervals: usize,
    min_fast: usize,
    /// Late syncs allowed, as a fraction of intervals, and the most any may be
    /// late beyond the Windows tolerance. Zero on Windows.
    late_fraction: f64,
    late_max_s: f64,
}

const WINDOWS: Corpus = Corpus {
    name: "windows",
    log: include_str!("fixtures/ak820pro-timekeeper-2026-09-05.log"),
    min_learned: 100,
    min_holds: 50,
    min_runs: 5,
    min_steps: 60,
    min_learned_in_runs: 40,
    min_intervals: 150,
    min_fast: 5,
    late_fraction: 0.0,
    late_max_s: 0.0,
};

const MACOS: Corpus = Corpus {
    name: "macos",
    log: include_str!("fixtures/ak820pro-timekeeper-macos-2026-09-16.log"),
    min_learned: 1_400,
    min_holds: 600,
    min_runs: 10,
    min_steps: 2_000,
    min_learned_in_runs: 1_400,
    min_intervals: 2_000,
    min_fast: 30,
    late_fraction: 0.01,
    late_max_s: 60.0,
};

fn status(pnom: u32) -> StatusRead {
    StatusRead {
        pnom,
        offset_ms: 0.0,
        ref_state: 2,
        epoch: 0,
        frames: 0,
        flags: 0,
    }
}

/// `YYYY-MM-DD HH:MM:SS` → seconds, good enough for differences within a day
/// or two.
fn stamp(line: &str) -> Option<f64> {
    let (date, rest) = line.split_at(10);
    let time = &rest[1..9];
    let mut d = date.split('-').map(|x| x.parse::<f64>().ok());
    let mut t = time.split(':').map(|x| x.parse::<f64>().ok());
    let (_y, _m, day) = (d.next()??, d.next()??, d.next()??);
    let (h, mi, s) = (t.next()??, t.next()??, t.next()??);
    Some(day * 86400.0 + h * 3600.0 + mi * 60.0 + s)
}

fn between<'a>(s: &'a str, after: &str, before: &str) -> Option<&'a str> {
    let i = s.find(after)? + after.len();
    let rest = &s[i..];
    let j = rest.find(before)?;
    Some(&rest[..j])
}

struct Learned {
    before: f64,
    elapsed: f64,
    e_slow_text: String,
    b_old: i32,
    b_new: i32,
    pnom: u32,
    text: String,
}

fn parse_learned(line: &str) -> Option<Learned> {
    let text = line.get(20..)?.to_string();
    Some(Learned {
        before: between(line, "before ", " ms")?.parse().ok()?,
        elapsed: between(line, "over ", " s =")?.parse().ok()?,
        e_slow_text: between(line, "board ", " ppm slow")?.to_string(),
        b_old: between(line, "; b ", " -> ")?.parse().ok()?,
        b_new: between(line, " -> ", " ppm (P")?.parse().ok()?,
        pnom: between(line, "(P ", ")")?.parse().ok()?,
        text,
    })
}

#[test]
fn windows_every_learned_line_is_reproduced_by_the_learner() {
    every_learned_line_is_reproduced_by_the_learner(&WINDOWS);
}

#[test]
fn macos_every_learned_line_is_reproduced_by_the_learner() {
    every_learned_line_is_reproduced_by_the_learner(&MACOS);
}

fn every_learned_line_is_reproduced_by_the_learner(c: &Corpus) {
    let mut fired = 0;
    let mut exact = 0;
    for line in c.log.lines().filter(|l| l.contains("bias learned:")) {
        let l = parse_learned(line).unwrap_or_else(|| panic!("unparsed: {line}"));
        // The elapsed was printed to the second, and `b` is sensitive to it
        // (0.25 * before * 1000 / elapsed^2 per second: up to ~0.5 ppm per
        // half second at the largest residuals). So the check is whether
        // SOME elapsed inside the printed second reproduces BOTH printed
        // values — scanned at 5 ms — and, at the printed elapsed itself, the
        // whole line byte for byte when it does.
        let replay = |elapsed: f64| -> Learn {
            let mut s = Scheduler::new(0.0);
            s.learn(Reason::Periodic, &SyncResult { ok: true, before_ms: Some(0.0), slewing: true }, Some(&status(l.pnom)), Some(l.b_old), 0.0);
            s.learn(
                Reason::Periodic,
                &SyncResult { ok: true, before_ms: Some(l.before), slewing: true },
                Some(&status(l.pnom)),
                Some(l.b_old),
                elapsed,
            )
        };
        let matches = |d: &Learn| match d {
            Learn::Learned { b_new_rounded, e_slow_ppm, .. } => {
                *b_new_rounded == l.b_new && format!("{e_slow_ppm:+.0}") == l.e_slow_text
            }
            other => panic!("did not learn for {line}: {other:?}"),
        };
        let at_printed = replay(l.elapsed);
        if matches(&at_printed) {
            exact += 1;
            assert_eq!(at_printed.log_line().as_deref(), Some(l.text.as_str()));
        } else {
            let mut found = false;
            let mut e = l.elapsed - 0.5;
            while e < l.elapsed + 0.5 {
                if matches(&replay(e)) {
                    found = true;
                    break;
                }
                e += 0.005;
            }
            assert!(found, "not reproduced by any elapsed within the printed second: {line}");
        }
        fired += 1;
    }
    assert!(fired >= c.min_learned, "{}: positive evidence: {fired} learned lines replayed", c.name);
    assert!(exact * 2 >= fired, "{}: {exact} of {fired} exact at the printed elapsed", c.name);
    eprintln!("{}: replayed {fired} learned lines, {exact} exact at the printed elapsed", c.name);
}

#[test]
fn windows_every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced() {
    every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced(&WINDOWS);
}

#[test]
fn macos_every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced() {
    every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced(&MACOS);
}

fn every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced(c: &Corpus) {
    let mut holds = 0;
    let mut unknown_prev = 0;
    for line in c.log.lines().filter(|l| l.contains("bias hold:")) {
        let b: i64 = between(line, " -> ", " since").unwrap().parse().unwrap();
        let before: f64 = between(line, "residual ", " ms").unwrap().parse().unwrap();
        let mut s = Scheduler::new(0.0);
        match between(line, "P ", " -> ").unwrap() {
            // `P None`: the previous sync's status read failed, so nothing
            // could be compared (the macOS log has two; the scheduler's unit
            // test was this path's only evidence before).
            "None" => {
                s.learn(Reason::Periodic, &SyncResult { ok: true, before_ms: Some(0.0), slewing: true }, None, Some(0), 0.0);
                unknown_prev += 1;
            }
            a => {
                let a: i64 = a.parse().unwrap();
                assert!((a - b).abs() > 6, "a hold with |dP| <= 6: {line}");
                s.learn(Reason::Periodic, &SyncResult { ok: true, before_ms: Some(0.0), slewing: true }, Some(&status(a as u32)), Some(0), 0.0);
            }
        }
        let d = s.learn(
            Reason::Periodic,
            &SyncResult { ok: true, before_ms: Some(before), slewing: true },
            Some(&status(b as u32)),
            Some(0),
            300.0,
        );
        assert_eq!(d.log_line().as_deref(), Some(&line[20..]), "{line}");
        holds += 1;
    }
    assert!(holds >= c.min_holds, "{}: {holds} hold lines replayed", c.name);
    eprintln!("{}: replayed {holds} hold lines, {unknown_prev} with no previous period", c.name);
}

/// One `bias hold` or `bias learned` line, whichever followed a sync.
enum BiasLine {
    Hold { prev_pnom: u32, pnom: u32 },
    Learned(Learned),
}

/// The log as a sequence: every sync line paired with the bias line that
/// followed it, if one did.
fn sequence(log: &str) -> Vec<(Sync, Option<BiasLine>)> {
    let lines: Vec<&str> = log.lines().collect();
    let mut out = Vec::new();
    for (i, line) in lines.iter().enumerate() {
        let Some(sync) = parse_sync(line) else { continue };
        let bias = lines.get(i + 1).and_then(|next| {
            if next.contains("bias learned:") {
                parse_learned(next).map(BiasLine::Learned)
            } else if next.contains("bias hold:") {
                Some(BiasLine::Hold {
                    prev_pnom: between(next, "P ", " -> ")?.parse().ok()?,
                    pnom: between(next, " -> ", " since")?.parse().ok()?,
                })
            } else {
                None
            }
        });
        out.push((sync, bias));
    }
    out
}

/// ⚠️ The phase-3a/4a audit's finding 8: the per-line replays above rebuild
/// the learner for every line, so state carried from one sync to the next
/// was never checked. This one carries it. Over every run of consecutive
/// periodic syncs that each have a bias line — the only stretches the log
/// records enough of — ONE scheduler is driven through the run: the cache
/// bias it carries must be the `b` each `bias learned` line says it started
/// from, its stored period must be the `P` each hold line says it compared
/// against, and its decisions must be the log's, line for line.
///
/// What the log still cannot give: `ref_state` (assumed 2 on these stretches,
/// where every line shows the learner running), the exact elapsed (the
/// monotonic instants are reconstructed from the wall-clock stamps), and
/// the syncs the Python declined silently, which end a run.
#[test]
fn windows_state_carried_across_consecutive_syncs_matches_the_log() {
    state_carried_across_consecutive_syncs_matches_the_log(&WINDOWS);
}

#[test]
fn macos_state_carried_across_consecutive_syncs_matches_the_log() {
    state_carried_across_consecutive_syncs_matches_the_log(&MACOS);
}

fn state_carried_across_consecutive_syncs_matches_the_log(c: &Corpus) {
    let seq = sequence(c.log);
    let mut runs = 0;
    let mut steps = 0;
    let mut learned = 0;
    let mut i = 0;
    while i < seq.len() {
        // a run: periodic syncs with bias lines, at least three long
        let mut j = i;
        while j < seq.len() && seq[j].0.reason == "periodic" && seq[j].1.is_some() {
            j += 1;
        }
        if j - i >= 3 {
            let mut s = Scheduler::new(0.0);
            // the sync before the run established the baseline; its period
            // is what the run's first bias line compared against
            // the cache bias going in is what the first learned line in the
            // run says it started from -- holds do not touch the cache
            let first_learned = seq[i..j].iter().find_map(|(_, l)| match l {
                Some(BiasLine::Learned(l)) => Some(l.b_old),
                _ => None,
            });
            let (first_pnom, mut bias) = match seq[i].1.as_ref().unwrap() {
                BiasLine::Hold { prev_pnom, .. } => (*prev_pnom, first_learned),
                BiasLine::Learned(l) => (l.pnom, Some(l.b_old)),
            };
            let t0 = seq[i].0.at - 300.0;
            s.learn(Reason::Enumerated, &SyncResult { ok: true, before_ms: Some(0.0), slewing: true }, Some(&status(first_pnom)), bias, 0.0);
            for (sync, line) in &seq[i..j] {
                let line = line.as_ref().unwrap();
                let (pnom, expect_prev) = match line {
                    BiasLine::Hold { prev_pnom, pnom } => (*pnom, Some(*prev_pnom)),
                    BiasLine::Learned(l) => (l.pnom, None),
                };
                if let BiasLine::Learned(l) = line {
                    assert_eq!(bias, Some(l.b_old), "the carried bias differs from the log's at {}", l.text);
                }
                let result = SyncResult { ok: true, before_ms: sync.before, slewing: true };
                s.synced(&result, sync.at);
                let d = s.learn(Reason::Periodic, &result, Some(&status(pnom)), bias, sync.at - t0);
                match (line, &d) {
                    (BiasLine::Hold { .. }, Learn::Hold { prev_pnom, .. }) => {
                        assert_eq!(*prev_pnom, expect_prev, "carried period at {}", sync.at);
                    }
                    (BiasLine::Learned(l), Learn::Learned { b_new_rounded, .. }) => {
                        // the arithmetic is checked per line elsewhere at the
                        // log's precision; here the STATE flows on
                        bias = Some(l.b_new);
                        learned += 1;
                        let _ = b_new_rounded;
                    }
                    (BiasLine::Hold { .. }, other) => panic!("log held at {} but the port {other:?}", sync.at),
                    (BiasLine::Learned(l), other) => panic!("log learned at {} but the port {other:?}", l.text),
                }
                steps += 1;
            }
            runs += 1;
            i = j;
        } else {
            i += 1;
        }
    }
    eprintln!("{}: replayed {runs} runs, {steps} consecutive syncs, {learned} of them learning, with state carried", c.name);
    assert!(runs >= c.min_runs, "{}: {runs} runs", c.name);
    assert!(steps >= c.min_steps, "{}: {steps} sequential steps", c.name);
    assert!(learned >= c.min_learned_in_runs, "{}: {learned} learned steps inside runs", c.name);
}

struct Sync {
    at: f64,
    reason: &'static str,
    before: Option<f64>,
}

fn parse_sync(line: &str) -> Option<Sync> {
    let reason = if line.contains("sync (periodic)") {
        "periodic"
    } else if line.contains("sync (enumerated)") {
        "enumerated"
    } else if line.contains("sync (wake)") {
        "wake"
    } else {
        return None;
    };
    let before = between(line, "before ", " ms").and_then(|b| b.parse().ok());
    Some(Sync {
        at: stamp(line)?,
        reason,
        before,
    })
}

/// The interval each sync selected, replayed against when the next periodic
/// sync actually happened: at the first 15-second loop tick on or after
/// `last_sync + interval`.
#[test]
fn windows_the_interval_after_each_sync_matches_when_the_next_one_happened() {
    the_interval_after_each_sync_matches_when_the_next_one_happened(&WINDOWS);
}

#[test]
fn macos_the_interval_after_each_sync_matches_when_the_next_one_happened() {
    the_interval_after_each_sync_matches_when_the_next_one_happened(&MACOS);
}

fn the_interval_after_each_sync_matches_when_the_next_one_happened(c: &Corpus) {
    let syncs: Vec<Sync> = c.log.lines().filter_map(parse_sync).collect();
    let mut checked = 0;
    let mut fast = 0;
    let mut late = 0;
    for pair in syncs.windows(2) {
        let (this, next) = (&pair[0], &pair[1]);
        if next.reason != "periodic" {
            continue; // an enumeration or a wake pre-empted the interval
        }
        let Some(before) = this.before else {
            continue; // the warning line: its `before` is not in the log
        };
        let mut s = Scheduler::new(0.0);
        s.synced(&SyncResult { ok: true, before_ms: Some(before), slewing: true }, this.at);
        let interval = s.interval();
        let gap = next.at - this.at;
        assert!(
            gap >= interval - 1.0,
            "{}: after before {before:+.1} ms the interval was {interval} s but the next sync came EARLY, {gap} s later",
            c.name
        );
        if gap >= interval + LOOP + 5.0 {
            // A late loop wake, not a decision: see the module note.
            assert!(
                gap < interval + LOOP + 5.0 + c.late_max_s,
                "{}: after before {before:+.1} ms the interval was {interval} s but the next sync came {gap} s later",
                c.name
            );
            late += 1;
        }
        // the loop was ticking every 15 s in between, so `wake` stays quiet
        // and the board was present throughout
        s.end_loop(true, this.at + interval - 10.0);
        assert_eq!(s.due(this.at + interval - 1.0, true), None);
        assert_eq!(s.due(this.at + interval, true), Some(Reason::Periodic));
        if interval == SYNC_INTERVAL_FAST {
            fast += 1;
        }
        checked += 1;
    }
    assert!(checked >= c.min_intervals, "{}: {checked} intervals replayed", c.name);
    assert!(fast >= c.min_fast, "{}: {fast} fast intervals: the log has a stretch above 60 ms", c.name);
    assert!(
        late as f64 <= c.late_fraction * checked as f64,
        "{}: {late} of {checked} intervals ran late",
        c.name
    );
    eprintln!("{}: replayed {checked} intervals, {fast} of them fast, {late} late; normal is {SYNC_INTERVAL} s", c.name);
}
