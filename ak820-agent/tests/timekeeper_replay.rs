//! Phase 3a: deterministic replay of the oracle's own record.
//!
//! `tests/fixtures/ak820pro-timekeeper-2026-09-05.log` is the Python
//! timekeeper's log from this machine, 2026-09-05 11:36 to 2026-09-06 07:49,
//! untouched. Every `bias learned` line names its inputs and its result
//! (`before`, `elapsed`, the old bias, the new one, `P`); every `bias hold`
//! line names the two periods the settled gate compared; every sync line's
//! `before` decided the interval to the next one, and the next one's
//! timestamp shows what was decided. So the log is a replay corpus for the
//! learner's arithmetic, its settled gate and the scheduler's interval
//! choice — with the positive evidence the parity document demands: over a
//! hundred lines where learning actually fired.
//!
//! What the log cannot give: `elapsed` is printed to whole seconds and
//! `before` to one decimal, so the arithmetic is replayed at that precision
//! and a result is accepted if the true elapsed within ±0.5 s could produce
//! it. `ref_state` is not logged; it is assumed 2 where learning fired,
//! which it must have been.

use ak820_agent::clock::scheduler::{Learn, Reason, Scheduler, StatusRead, SyncResult, SYNC_INTERVAL, SYNC_INTERVAL_FAST, LOOP};

const LOG: &str = include_str!("fixtures/ak820pro-timekeeper-2026-09-05.log");

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
fn every_learned_line_is_reproduced_by_the_learner() {
    let mut fired = 0;
    let mut exact = 0;
    for line in LOG.lines().filter(|l| l.contains("bias learned:")) {
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
    assert!(fired >= 100, "positive evidence: {fired} learned lines replayed");
    assert!(exact * 2 >= fired, "{exact} of {fired} exact at the printed elapsed");
    eprintln!("replayed {fired} learned lines, {exact} exact at the printed elapsed");
}

#[test]
fn every_hold_line_is_a_period_move_beyond_six_ticks_and_is_reproduced() {
    let mut holds = 0;
    for line in LOG.lines().filter(|l| l.contains("bias hold:")) {
        let a: i64 = between(line, "P ", " -> ").unwrap().parse().unwrap();
        let b: i64 = between(line, " -> ", " since").unwrap().parse().unwrap();
        let before: f64 = between(line, "residual ", " ms").unwrap().parse().unwrap();
        assert!((a - b).abs() > 6, "a hold with |dP| <= 6: {line}");
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &SyncResult { ok: true, before_ms: Some(0.0), slewing: true }, Some(&status(a as u32)), Some(0), 0.0);
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
    assert!(holds >= 50, "{holds} hold lines replayed");
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
fn the_interval_after_each_sync_matches_when_the_next_one_happened() {
    let syncs: Vec<Sync> = LOG.lines().filter_map(parse_sync).collect();
    let mut checked = 0;
    let mut fast = 0;
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
            gap >= interval - 1.0 && gap < interval + LOOP + 5.0,
            "after before {before:+.1} ms the interval was {interval} s but the next sync came {gap} s later"
        );
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
    assert!(checked >= 150, "{checked} intervals replayed");
    assert!(fast >= 5, "{fast} fast intervals: the log has a stretch above 60 ms");
    eprintln!("replayed {checked} intervals, {fast} of them fast; normal is {SYNC_INTERVAL} s");
}
