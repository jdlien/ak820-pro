//! The clock scheduler, the SOF-bias learner and the bias seed —
//! `hostagent/ak820-timekeeper.py`'s decisions, ported verbatim from
//! [`AK820-AGENT-CLOCK-PARITY.md`](../../../plans/AK820-AGENT-CLOCK-PARITY.md).
//!
//! **The rule from that document: port the constants and gate conditions
//! verbatim. If a value looks arbitrary, it is not.** Every constant below
//! encodes a failure that took hours to see; the document names four.
//!
//! This is the pure half: given the time, presence, a sync's result and a
//! status read, what to do next. It holds no device and no clock of its own,
//! so every gate is a test. Time is passed in as the Python takes it —
//! **wall time for scheduling and the seed, monotonic for the learner's
//! `elapsed`** — because the Python mixes them and a port that tidied that up
//! would decide differently across a clock step.
//!
//! What the Python does with a decision (write the cache, log a line, spawn
//! `ak820ctl clock --bias`) is the caller's job, and the log lines are
//! reproduced here byte for byte because the log is how the owner reads the
//! learner's health: "the hold log is how you tell the learner is working
//! and declining from the learner is broken".

use super::BoardTime;

/// Main loop period, seconds.
pub const LOOP: f64 = 15.0;
/// Periodic sync once the residual is small.
pub const SYNC_INTERVAL: f64 = 300.0;
/// Periodic sync while the last residual exceeded [`FAST_ABOVE_MS`].
///
/// ⚠️ Must leave the firmware's frequency window a full clean stretch: a
/// slew writes the period register ~3 times and every write restarts the
/// window. At 120 s against a then-128 s window the loop froze at a wrong
/// period and held a +300 ms plateau for six hours on 2026-09-04.
pub const SYNC_INTERVAL_FAST: f64 = 180.0;
/// Threshold selecting the fast interval — compared against the **printed**
/// one-decimal `before`, as Python parses it.
pub const FAST_ABOVE_MS: f64 = 60.0;
/// A loop gap above this means the host slept.
pub const SLEEP_GAP: f64 = 60.0;
/// Continuity needed before a bias *seed* measurement.
pub const BIAS_INTERVAL: f64 = 900.0;
/// Minimum spacing between the two syncs a residual spans. Was 240, longer
/// than the fast interval, so the learner could never fire while the residual
/// was large — the one time it was needed.
pub const LEARN_MIN_ELAPSED: f64 = 90.0;
/// Larger residuals are convergence or a step, not a rate error.
pub const LEARN_MAX_BEFORE: f64 = 400.0;
/// Low gain: each residual carries the ILRC's wander as noise.
pub const LEARN_GAIN: f64 = 0.25;
/// "Period unchanged" tolerance, ticks (~180 ppm): the ILRC wanders ±300 ppm
/// on five-minute scales and the loop follows it a few ticks per window, so
/// strictly unchanged never happens.
pub const LEARN_MAX_DP: i64 = 6;
/// Matches the firmware's own sanity clamp.
pub const BIAS_LIMIT: f64 = 600.0;
/// How long an `enumerated` sync waits for the board to settle after boot.
pub const ENUMERATED_SETTLE: f64 = 2.0;

/// Why a sync is due. First match wins, in this order.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Reason {
    /// Present now, not present last loop.
    Enumerated,
    /// The loop gap says the host slept.
    Wake,
    /// The interval elapsed.
    Periodic,
}

impl Reason {
    pub fn word(self) -> &'static str {
        match self {
            Reason::Enumerated => "enumerated",
            Reason::Wake => "wake",
            Reason::Periodic => "periodic",
        }
    }
}

/// What Python's `read_status()` parsed out of `ak820ctl clock --read`. The
/// whole thing is `None` when that command failed — no reply, or an unset
/// clock — which is how the Python treats it.
#[derive(Clone, Debug, PartialEq)]
pub struct StatusRead {
    pub pnom: u32,
    pub offset_ms: f64,
    pub ref_state: u8,
    pub epoch: u8,
    pub frames: u32,
    pub flags: u8,
}

impl StatusRead {
    /// From a decoded GET reply and the offset computed against it. `None`
    /// for an unset clock, as the C's `--read` exits 1 there.
    pub fn from_board(board: &BoardTime, offset_ms: Option<f64>) -> Option<StatusRead> {
        let offset_ms = offset_ms?;
        Some(StatusRead {
            pnom: board.nominal_period as u32,
            offset_ms,
            ref_state: board.ref_state,
            epoch: board.sof_epoch,
            frames: board.sof_frames_total,
            flags: board.flags,
        })
    }
}

/// What Python's `sync()` returns: `(ok, before, slewing)`.
///
/// `before` is the **printed** one-decimal value, and `slewing` is
/// `"(slewing)" in out and "warning:" not in out` — take both from
/// [`super::transaction::Outcome::as_reported`], never from the measurement.
#[derive(Clone, Debug, PartialEq)]
pub struct SyncResult {
    pub ok: bool,
    pub before_ms: Option<f64>,
    pub slewing: bool,
}

/// The learner's decision for one sync.
#[derive(Clone, Debug, PartialEq)]
pub enum Learn {
    /// A non-periodic sync only establishes the baseline. Nothing logged.
    Baseline,
    /// Every gate but "settled" passed: the loop is still moving `P`. Logged,
    /// deliberately — see the module header.
    Hold {
        prev_pnom: Option<u32>,
        pnom: u32,
        before_ms: f64,
    },
    /// All gates passed and the cache already holds a bias: the caller writes
    /// `b_new_rounded` back and logs [`Learn::log_line`] **only if the write
    /// succeeded**.
    Learned {
        before_ms: f64,
        elapsed_s: f64,
        e_slow_ppm: f64,
        b_old: i32,
        /// Clamped, unrounded — what the arithmetic produced.
        b_new: f64,
        /// `int(round(b_new))`, ties to even. What the cache gets.
        b_new_rounded: i32,
        pnom: u32,
    },
    /// A gate failed. Python logs nothing here.
    Declined,
}

impl Learn {
    /// The Python's log line for this decision, if it writes one.
    pub fn log_line(&self) -> Option<String> {
        match self {
            Learn::Hold {
                prev_pnom,
                pnom,
                before_ms,
            } => Some(format!(
                "bias hold: P {} -> {pnom} since the last sync (loop still moving); residual {before_ms:+.1} ms not learned",
                match prev_pnom {
                    Some(p) => p.to_string(),
                    None => "None".to_string(),
                }
            )),
            Learn::Learned {
                before_ms,
                elapsed_s,
                e_slow_ppm,
                b_old,
                b_new_rounded,
                pnom,
                ..
            } => Some(format!(
                "bias learned: before {before_ms:+.1} ms over {elapsed_s:.0} s = board {e_slow_ppm:+.0} ppm slow; b {b_old:+} -> {b_new_rounded:+} ppm (P {pnom})"
            )),
            Learn::Baseline | Learn::Declined => None,
        }
    }
}

/// The seed's decision for one loop.
#[derive(Clone, Debug, PartialEq)]
pub enum SeedStep {
    /// The cache has a bias: the seed is disabled entirely, state cleared.
    Disabled,
    /// No status, or an unreadable one: state cleared, nothing measured.
    Reset,
    /// Controller or epoch changed (or first sight): a fresh measurement
    /// starts from this frame count.
    Restarted { epoch: u8, f0: u32 },
    /// Still accumulating continuity.
    Accumulating { h_s: f64 },
    /// `H` reached [`BIAS_INTERVAL`]: measured, and the state cleared for the
    /// next one whether or not `b` was accepted.
    Measured {
        f: u32,
        h_s: f64,
        b_ppm: f64,
        /// Strictly inside ±600. The caller caches `round(b_ppm)` if so.
        accepted: bool,
    },
}

impl SeedStep {
    /// `int(round(b))`, the value `clock --bias` receives.
    pub fn bias_to_cache(&self) -> Option<i32> {
        match self {
            SeedStep::Measured {
                b_ppm,
                accepted: true,
                ..
            } => Some(b_ppm.round_ties_even() as i32),
            _ => None,
        }
    }

    /// The Python's log line, written only when accepted.
    pub fn log_line(&self, cid: &str) -> Option<String> {
        match self {
            SeedStep::Measured {
                f,
                h_s,
                b_ppm,
                accepted: true,
            } => Some(format!(
                "bias: F={f} H={h_s:.1}s b={b_ppm:+.1} ppm (controller {cid}) cached"
            )),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
struct LearnSample {
    t_mono: f64,
    pnom: Option<u32>,
}

#[derive(Clone, Debug, PartialEq)]
struct Seed {
    cid: String,
    epoch: u8,
    t0_wall: f64,
    f0: u32,
}

/// The loop's state — every variable of the Python `main()` and the two
/// dicts it passes around.
#[derive(Clone, Debug, PartialEq)]
pub struct Scheduler {
    last_loop: f64,
    last_sync: f64,
    interval: f64,
    was_present: bool,
    learn: Option<LearnSample>,
    /// What `learn` was before the last [`Scheduler::learn`], so a failed
    /// cache write can put it back — see [`Scheduler::cache_write_failed`].
    learn_before: Option<LearnSample>,
    seed: Option<Seed>,
}

impl Scheduler {
    /// `last_loop = time.time()` at start; `last_sync = 0.0`; the normal
    /// interval; not present.
    pub fn new(now_wall: f64) -> Scheduler {
        Scheduler {
            last_loop: now_wall,
            last_sync: 0.0,
            interval: SYNC_INTERVAL,
            was_present: false,
            learn: None,
            learn_before: None,
            seed: None,
        }
    }

    /// The cache write a [`Learn::Learned`] asked for failed with an I/O
    /// error. In the Python that is `cap_write_bias()` raising inside
    /// `learn_bias()`, which never reaches its final `state["learn"] = …`, so
    /// the baseline stays where it was and the next residual spans both
    /// intervals. Call this and the same happens here (the phase-3a/4a
    /// audit's finding 7).
    pub fn cache_write_failed(&mut self) {
        self.learn = self.learn_before.take();
    }

    pub fn interval(&self) -> f64 {
        self.interval
    }

    pub fn was_present(&self) -> bool {
        self.was_present
    }

    pub fn last_sync(&self) -> f64 {
        self.last_sync
    }

    /// Is a sync due this loop, and why? First match wins. `None` when the
    /// board is absent, because the Python runs a sync only `if present and
    /// reason` — the reason it computed while absent is never acted on.
    pub fn due(&self, now_wall: f64, present: bool) -> Option<Reason> {
        let reason = if present && !self.was_present {
            Some(Reason::Enumerated)
        } else if now_wall - self.last_loop > SLEEP_GAP {
            Some(Reason::Wake)
        } else if now_wall - self.last_sync >= self.interval {
            Some(Reason::Periodic)
        } else {
            None
        };
        reason.filter(|_| present)
    }

    /// After a sync attempt. On success `last_sync` is the time **after** the
    /// transaction (the Python calls `time.time()` again) and the interval is
    /// chosen from the printed `before`: fast when `|before| > 60`, and
    /// ⚠️ the normal interval when `before` is unknown. On failure nothing
    /// moves — not `last_sync`, not the interval, not the learner — so a
    /// failed `enumerated` or `wake` is not retried next loop either, because
    /// `was_present` moves regardless in [`Scheduler::end_loop`].
    pub fn synced(&mut self, result: &SyncResult, now_after_wall: f64) {
        if !result.ok {
            return;
        }
        self.last_sync = now_after_wall;
        self.interval = match result.before_ms {
            Some(before) if before.abs() > FAST_ABOVE_MS => SYNC_INTERVAL_FAST,
            _ => SYNC_INTERVAL,
        };
    }

    /// `learn_bias()`, after a **successful** sync. `now_mono` is taken
    /// **before** the status read, as the Python does, so the read's
    /// duration is inside `elapsed`. `cache_bias` is what `cap_read()` found
    /// in the cache — `None` when the file is unreadable or has no bias, in
    /// which case there is nothing to adjust and the seed owns the case.
    pub fn learn(
        &mut self,
        reason: Reason,
        result: &SyncResult,
        status: Option<&StatusRead>,
        cache_bias: Option<i32>,
        now_mono: f64,
    ) -> Learn {
        // Stored as read — a 0 stays 0, so a later hold line prints `P 0`
        // as the Python's would — and treated as absent by the gates, which
        // is Python truthiness.
        let pnom = status.map(|s| s.pnom);
        let live = |p: Option<u32>| p.filter(|&n| n != 0);
        let ref_state = status.map(|s| s.ref_state);
        let prev = self.learn.take();
        self.learn_before = prev.clone();

        let decision = if reason != Reason::Periodic {
            Learn::Baseline
        } else {
            let settled = match (&prev, live(pnom)) {
                (Some(p), Some(n)) => live(p.pnom)
                    .is_some_and(|pp| (pp as i64 - n as i64).abs() <= LEARN_MAX_DP),
                _ => false,
            };
            let before_ok = result
                .before_ms
                .is_some_and(|b| b.abs() <= LEARN_MAX_BEFORE);
            let common = prev.is_some()
                && live(pnom).is_some()
                && before_ok
                && result.slewing
                && ref_state == Some(2);
            if common && !settled {
                Learn::Hold {
                    prev_pnom: prev.as_ref().and_then(|p| p.pnom),
                    pnom: pnom.expect("common"),
                    before_ms: result.before_ms.expect("common"),
                }
            } else if settled && common {
                let before = result.before_ms.expect("common");
                let elapsed = now_mono - prev.as_ref().expect("settled").t_mono;
                if elapsed >= LEARN_MIN_ELAPSED {
                    let e_slow = -before * 1000.0 / elapsed;
                    match cache_bias {
                        Some(b) => {
                            let b_new = (b as f64 - LEARN_GAIN * e_slow).clamp(-BIAS_LIMIT, BIAS_LIMIT);
                            Learn::Learned {
                                before_ms: before,
                                elapsed_s: elapsed,
                                e_slow_ppm: e_slow,
                                b_old: b,
                                b_new,
                                b_new_rounded: b_new.round_ties_even() as i32,
                                pnom: pnom.expect("common"),
                            }
                        }
                        None => Learn::Declined,
                    }
                } else {
                    Learn::Declined
                }
            } else {
                Learn::Declined
            }
        };

        self.learn = Some(LearnSample {
            t_mono: now_mono,
            pnom,
        });
        decision
    }

    /// `bias_step()`, every loop while the board is present. **Seed only**:
    /// disabled entirely once the cache has a bias, because the frame-count
    /// measurement swung −369..+587 ppm on a controller pinned at +78 ±3 and
    /// each new value re-steered the clock into a five-minute sawtooth.
    pub fn seed_step(
        &mut self,
        cache_has_bias: bool,
        status: Option<&StatusRead>,
        cid: &str,
        now_wall: f64,
    ) -> SeedStep {
        if cache_has_bias {
            self.seed = None;
            return SeedStep::Disabled;
        }
        let Some(st) = status else {
            self.seed = None;
            return SeedStep::Reset;
        };
        match &self.seed {
            Some(s) if s.cid == cid && s.epoch == st.epoch => {
                let h = now_wall - s.t0_wall;
                if h >= BIAS_INTERVAL {
                    let f = st.frames.wrapping_sub(s.f0);
                    let b = (f as f64 / (1000.0 * h) - 1.0) * 1e6;
                    self.seed = None;
                    SeedStep::Measured {
                        f,
                        h_s: h,
                        b_ppm: b,
                        accepted: b > -BIAS_LIMIT && b < BIAS_LIMIT,
                    }
                } else {
                    SeedStep::Accumulating { h_s: h }
                }
            }
            _ => {
                self.seed = Some(Seed {
                    cid: cid.to_string(),
                    epoch: st.epoch,
                    t0_wall: now_wall,
                    f0: st.frames,
                });
                SeedStep::Restarted {
                    epoch: st.epoch,
                    f0: st.frames,
                }
            }
        }
    }

    /// The end of one loop: `was_present` moves regardless of what the sync
    /// did, `last_loop` is stamped **after** everything, and absence clears
    /// both the seed and the learner.
    pub fn end_loop(&mut self, present: bool, now_wall: f64) {
        if !present {
            self.seed = None;
            self.learn = None;
        }
        self.was_present = present;
        self.last_loop = now_wall;
    }
}

/// The log line the Python writes for a sync: the last line of the tool's
/// output, and `[rc=N]` when it failed.
pub fn sync_log_line(reason: Reason, output_last_line: &str, rc: i32) -> String {
    let tail = if rc == 0 { String::new() } else { format!(" [rc={rc}]") };
    let body = if output_last_line.is_empty() { "no output" } else { output_last_line };
    format!("sync ({}): {body}{tail}", reason.word())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(before: f64, slewing: bool) -> SyncResult {
        SyncResult {
            ok: true,
            before_ms: Some(before),
            slewing,
        }
    }

    fn status(pnom: u32, ref_state: u8) -> StatusRead {
        StatusRead {
            pnom,
            offset_ms: 0.0,
            ref_state,
            epoch: 3,
            frames: 1_000_000,
            flags: 0x07,
        }
    }

    // -- triggers ---------------------------------------------------------

    #[test]
    fn a_board_appearing_is_enumerated_and_first() {
        let mut s = Scheduler::new(1000.0);
        assert_eq!(s.due(1015.0, true), Some(Reason::Enumerated));
        s.end_loop(true, 1015.0);
        assert_eq!(s.due(1030.0, true), Some(Reason::Periodic), "last_sync is 0, so periodic is due at once");
    }

    #[test]
    fn nothing_is_due_while_absent_whatever_the_clocks_say() {
        let s = Scheduler::new(1000.0);
        assert_eq!(s.due(5000.0, false), None);
    }

    #[test]
    fn a_loop_gap_over_sixty_seconds_is_a_wake() {
        let mut s = Scheduler::new(1000.0);
        s.end_loop(true, 1000.0);
        s.synced(&ok(1.0, true), 1000.5);
        assert_eq!(s.due(1015.0, true), None);
        assert_eq!(s.due(1061.0, true), Some(Reason::Wake));
        assert_eq!(s.due(1060.0, true), None, "strictly greater than the gap");
    }

    #[test]
    fn periodic_is_at_the_interval_and_first_match_wins() {
        let mut s = Scheduler::new(1000.0);
        s.end_loop(true, 1000.0);
        s.synced(&ok(1.0, true), 1000.5);
        // the loop keeps ticking every 15 s, which is what keeps `wake` quiet
        let mut t = 1001.0;
        while t < 1300.0 {
            assert_eq!(s.due(t, true), None, "at {t}");
            s.end_loop(true, t);
            t += LOOP;
        }
        assert_eq!(s.due(1300.5, true), Some(Reason::Periodic));
        // enumerated beats everything
        s.end_loop(false, 1300.5);
        assert_eq!(s.due(1301.0, true), Some(Reason::Enumerated));
    }

    // -- the interval after a sync -------------------------------------------

    #[test]
    fn a_residual_over_sixty_ms_selects_the_fast_interval() {
        let mut s = Scheduler::new(0.0);
        s.synced(&ok(60.1, true), 10.0);
        assert_eq!(s.interval(), SYNC_INTERVAL_FAST);
        s.synced(&ok(-60.1, true), 20.0);
        assert_eq!(s.interval(), SYNC_INTERVAL_FAST);
        s.synced(&ok(60.0, true), 30.0);
        assert_eq!(s.interval(), SYNC_INTERVAL, "exactly 60 is not over 60");
        assert_eq!(s.last_sync(), 30.0);
    }

    /// ⚠️ An unknown residual selects the normal interval, not the fast one.
    #[test]
    fn an_unknown_residual_selects_the_normal_interval() {
        let mut s = Scheduler::new(0.0);
        s.synced(&ok(100.0, true), 10.0);
        assert_eq!(s.interval(), SYNC_INTERVAL_FAST);
        s.synced(
            &SyncResult {
                ok: true,
                before_ms: None,
                slewing: false,
            },
            20.0,
        );
        assert_eq!(s.interval(), SYNC_INTERVAL);
    }

    /// On a failed sync none of `last_sync`, `interval` or the learner move —
    /// but `was_present` does, so a failed enumerated sync is not retried.
    #[test]
    fn a_failed_sync_moves_nothing_but_presence() {
        let mut s = Scheduler::new(0.0);
        s.synced(&ok(100.0, true), 10.0);
        let before = s.clone();
        s.synced(
            &SyncResult {
                ok: false,
                before_ms: None,
                slewing: false,
            },
            20.0,
        );
        assert_eq!(s, before);
        s.end_loop(true, 20.0);
        assert!(s.was_present());
        assert_eq!(s.due(35.0, true), None, "not enumerated again");
    }

    // -- the learner -------------------------------------------------------

    /// A successful non-periodic sync establishes the baseline, so the first
    /// periodic sync after it can learn. Two periodic syncs are not required.
    #[test]
    fn a_non_periodic_sync_establishes_the_baseline_and_the_next_periodic_learns() {
        let mut s = Scheduler::new(0.0);
        assert_eq!(
            s.learn(Reason::Enumerated, &ok(1.0, true), Some(&status(33420, 2)), Some(-33), 100.0),
            Learn::Baseline
        );
        let d = s.learn(Reason::Periodic, &ok(1.8, true), Some(&status(33420, 2)), Some(-33), 401.0);
        match d {
            Learn::Learned { b_old, b_new_rounded, elapsed_s, .. } => {
                assert_eq!(b_old, -33);
                assert_eq!(elapsed_s, 301.0);
                assert_eq!(b_new_rounded, -32);
            }
            other => panic!("expected learned, got {other:?}"),
        }
    }

    /// The oracle's own line from 2026-09-06 06:09:35, reproduced:
    /// `bias learned: before +1.8 ms over 301 s = board -6 ppm slow; b -33 -> -32 ppm (P 33420)`.
    #[test]
    fn the_learned_line_matches_the_oracles_log() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Enumerated, &ok(0.0, true), Some(&status(33420, 2)), Some(-33), 0.0);
        let d = s.learn(Reason::Periodic, &ok(1.8, true), Some(&status(33420, 2)), Some(-33), 301.0);
        assert_eq!(
            d.log_line().as_deref(),
            Some("bias learned: before +1.8 ms over 301 s = board -6 ppm slow; b -33 -> -32 ppm (P 33420)")
        );
    }

    /// The hold line, from 2026-09-06 06:04:34:
    /// `bias hold: P 33414 -> 33423 since the last sync (loop still moving); residual +15.7 ms not learned`.
    #[test]
    fn a_moving_period_holds_and_logs_it() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33414, 2)), Some(-33), 0.0);
        let d = s.learn(Reason::Periodic, &ok(15.7, true), Some(&status(33423, 2)), Some(-33), 300.0);
        assert_eq!(
            d,
            Learn::Hold {
                prev_pnom: Some(33414),
                pnom: 33423,
                before_ms: 15.7
            }
        );
        assert_eq!(
            d.log_line().as_deref(),
            Some("bias hold: P 33414 -> 33423 since the last sync (loop still moving); residual +15.7 ms not learned")
        );
    }

    #[test]
    fn six_ticks_is_settled_and_seven_is_not() {
        for (dp, expect_learn) in [(6i64, true), (-6, true), (7, false), (-7, false)] {
            let mut s = Scheduler::new(0.0);
            s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(0), 0.0);
            let d = s.learn(
                Reason::Periodic,
                &ok(1.0, true),
                Some(&status((33400 + dp) as u32, 2)),
                Some(0),
                300.0,
            );
            assert_eq!(matches!(d, Learn::Learned { .. }), expect_learn, "dp {dp}");
        }
    }

    /// Each gate, one at a time, against a case that would otherwise learn.
    #[test]
    fn each_gate_declines_on_its_own() {
        let learning = |f: &mut dyn FnMut(&mut Scheduler) -> Learn| {
            let mut s = Scheduler::new(0.0);
            s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(0), 0.0);
            f(&mut s)
        };
        // the control: this learns
        assert!(matches!(
            learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), Some(0), 300.0)),
            Learn::Learned { .. }
        ));
        // not slewing (a step)
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, false), Some(&status(33400, 2)), Some(0), 300.0)), Learn::Declined);
        // |before| > 400
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(400.1, true), Some(&status(33400, 2)), Some(0), 300.0)), Learn::Declined);
        assert!(matches!(learning(&mut |s| s.learn(Reason::Periodic, &ok(400.0, true), Some(&status(33400, 2)), Some(0), 300.0)), Learn::Learned { .. }));
        // ref_state != 2
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 1)), Some(0), 300.0)), Learn::Declined);
        // elapsed < 90
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), Some(0), 89.9)), Learn::Declined);
        assert!(matches!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), Some(0), 90.0)), Learn::Learned { .. }));
        // no bias in the cache: the seed owns it
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), None, 300.0)), Learn::Declined);
        // before unknown
        assert_eq!(
            learning(&mut |s| s.learn(Reason::Periodic, &SyncResult { ok: true, before_ms: None, slewing: true }, Some(&status(33400, 2)), Some(0), 300.0)),
            Learn::Declined
        );
        // status unreadable
        assert_eq!(learning(&mut |s| s.learn(Reason::Periodic, &ok(1.0, true), None, Some(0), 300.0)), Learn::Declined);
    }

    /// ⚠️ The phase-3a/4a audit's finding 7. A failed cache write in the
    /// Python raises out of `learn_bias()` before its final baseline
    /// assignment, so the next residual spans both intervals. Two +12 ms
    /// residuals 300 s apart with the first write failing: the Python learns
    /// over 600 s (bias +5), a port that moved the baseline anyway would
    /// learn over 300 s (bias +10).
    #[test]
    fn a_failed_cache_write_leaves_the_baseline_where_it_was() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(0), 0.0);
        let d = s.learn(Reason::Periodic, &ok(12.0, true), Some(&status(33400, 2)), Some(0), 300.0);
        assert!(matches!(d, Learn::Learned { b_new_rounded: 10, .. }), "{d:?}");
        s.cache_write_failed(); // the save raised: the baseline is still t=0
        let d = s.learn(Reason::Periodic, &ok(12.0, true), Some(&status(33400, 2)), Some(0), 600.0);
        match d {
            Learn::Learned { elapsed_s, b_new_rounded, .. } => {
                assert_eq!(elapsed_s, 600.0);
                assert_eq!(b_new_rounded, 5);
            }
            other => panic!("{other:?}"),
        }
    }

    /// A nominal period of 0 is stored as 0 and printed as `P 0`, while the
    /// gates treat it as absent — Python truthiness, both halves.
    #[test]
    fn a_zero_period_prints_as_zero_and_never_settles() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(0, 2)), Some(0), 0.0);
        let d = s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), Some(0), 300.0);
        assert_eq!(d, Learn::Hold { prev_pnom: Some(0), pnom: 33400, before_ms: 1.0 });
        assert!(d.log_line().unwrap().starts_with("bias hold: P 0 -> 33400 "));
    }

    /// A failed status read stores `pnom = None`, so the next sync cannot be
    /// settled — and the hold line then prints `P None -> ...`, as the Python's
    /// f-string does.
    #[test]
    fn a_failed_status_read_breaks_settledness_and_prints_none() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), None, Some(0), 0.0);
        let d = s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33400, 2)), Some(0), 300.0);
        assert_eq!(
            d,
            Learn::Hold {
                prev_pnom: None,
                pnom: 33400,
                before_ms: 1.0
            }
        );
        assert!(d.log_line().unwrap().starts_with("bias hold: P None -> 33400 "));
    }

    /// The elapsed-time gate is not part of the hold log's condition: a hold
    /// is logged even inside 90 s, and even with no bias cached.
    #[test]
    fn the_hold_log_needs_neither_the_elapsed_gate_nor_a_cached_bias() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), None, 0.0);
        let d = s.learn(Reason::Periodic, &ok(1.0, true), Some(&status(33500, 2)), None, 10.0);
        assert!(matches!(d, Learn::Hold { .. }));
    }

    #[test]
    fn the_bias_is_clamped_and_rounded_to_even() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(599), 0.0);
        // e_slow = -(-400)*1000/100 = +4000 -> b - 1000 -> clamped to -600? no: 599 - 1000 = -401
        let d = s.learn(Reason::Periodic, &ok(-400.0, true), Some(&status(33400, 2)), Some(599), 100.0);
        match d {
            Learn::Learned { b_new, b_new_rounded, e_slow_ppm, .. } => {
                assert_eq!(e_slow_ppm, 4000.0);
                assert_eq!(b_new, -401.0);
                assert_eq!(b_new_rounded, -401);
            }
            other => panic!("{other:?}"),
        }
        // before -400 over 100 s: e_slow = +4000, b - 1000 = -1500 -> clamped
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(-500), 0.0);
        let d = s.learn(Reason::Periodic, &ok(-400.0, true), Some(&status(33400, 2)), Some(-500), 100.0);
        match d {
            Learn::Learned { b_new, b_new_rounded, .. } => {
                assert_eq!(b_new, -600.0, "clamped");
                assert_eq!(b_new_rounded, -600);
            }
            other => panic!("{other:?}"),
        }
        // ties to even: 0.5 -> 0, 1.5 -> 2, -0.5 -> 0
        assert_eq!(0.5f64.round_ties_even(), 0.0);
        assert_eq!(1.5f64.round_ties_even(), 2.0);
        assert_eq!((-0.5f64).round_ties_even(), -0.0);
    }

    // -- the seed ---------------------------------------------------------

    fn frames(epoch: u8, frames: u32) -> StatusRead {
        StatusRead {
            pnom: 33400,
            offset_ms: 0.0,
            ref_state: 2,
            epoch,
            frames,
            flags: 0,
        }
    }

    #[test]
    fn a_cached_bias_disables_the_seed_entirely() {
        let mut s = Scheduler::new(0.0);
        s.seed_step(false, Some(&frames(1, 0)), "c", 0.0);
        assert_eq!(s.seed_step(true, Some(&frames(1, 0)), "c", 100.0), SeedStep::Disabled);
        assert_eq!(s.seed, None);
    }

    #[test]
    fn an_unreadable_status_resets_the_measurement() {
        let mut s = Scheduler::new(0.0);
        s.seed_step(false, Some(&frames(1, 0)), "c", 0.0);
        assert_eq!(s.seed_step(false, None, "c", 100.0), SeedStep::Reset);
        assert_eq!(s.seed_step(false, Some(&frames(1, 500)), "c", 200.0), SeedStep::Restarted { epoch: 1, f0: 500 });
    }

    #[test]
    fn a_controller_or_epoch_change_restarts_from_the_new_frame_count() {
        let mut s = Scheduler::new(0.0);
        assert_eq!(s.seed_step(false, Some(&frames(1, 10)), "c", 0.0), SeedStep::Restarted { epoch: 1, f0: 10 });
        assert_eq!(s.seed_step(false, Some(&frames(1, 20)), "d", 15.0), SeedStep::Restarted { epoch: 1, f0: 20 });
        assert_eq!(s.seed_step(false, Some(&frames(2, 30)), "d", 30.0), SeedStep::Restarted { epoch: 2, f0: 30 });
        assert_eq!(s.seed_step(false, Some(&frames(2, 40)), "d", 45.0), SeedStep::Accumulating { h_s: 15.0 });
    }

    /// The oracle's own line, 2026-09-05 12:12:51:
    /// `bias: F=903989 H=903.5s b=+566.0 ppm (controller …) cached`.
    ///
    /// ⚠️ The printed `H` cannot reproduce `b`: `b` moves ~1,100 ppm per
    /// second of `H`, so the one-decimal `903.5` covers ±55 ppm. The `H`
    /// below is the one that makes the line's `F` and `b` agree (903.478 s),
    /// and it prints as the line's `903.5`. What is verified is the formula
    /// and both renderings, not that `903.5` yields `566.0`.
    #[test]
    fn the_seed_measures_at_900_seconds_and_matches_the_oracles_arithmetic() {
        let mut s = Scheduler::new(0.0);
        s.seed_step(false, Some(&frames(7, 1000)), "c", 100.0);
        assert_eq!(s.seed_step(false, Some(&frames(7, 1000 + 500_000)), "c", 999.0), SeedStep::Accumulating { h_s: 899.0 });
        let step = s.seed_step(false, Some(&frames(7, 1000 + 903_989)), "c", 100.0 + 903.4776);
        match step {
            SeedStep::Measured { f, h_s, b_ppm, accepted } => {
                assert_eq!(f, 903_989);
                assert!((h_s - 903.4776).abs() < 1e-9);
                let expect = (903_989.0 / (1000.0 * 903.4776) - 1.0) * 1e6;
                assert_eq!(b_ppm, expect, "the formula, literally");
                assert!((b_ppm - 566.0).abs() < 0.05, "{b_ppm}");
                assert!(accepted);
            }
            other => panic!("{other:?}"),
        }
        assert_eq!(
            step.log_line("c").as_deref(),
            Some("bias: F=903989 H=903.5s b=+566.0 ppm (controller c) cached")
        );
        assert_eq!(step.bias_to_cache(), Some(566));
        assert_eq!(s.seed, None, "cleared for the next measurement");
    }

    /// `-600 < b < 600`, strictly, and the state is cleared either way. A
    /// value landing exactly on 600.0 is not something floating point
    /// produces from a frame count, in Python or here — both compute the same
    /// doubles — so the boundary is checked one ppm either side.
    #[test]
    fn a_bias_outside_600_is_rejected_and_the_state_cleared_either_way() {
        for (f, accepted) in [(1_000_599u32, true), (1_000_601, false), (999_401, true), (999_399, false)] {
            let mut s = Scheduler::new(0.0);
            s.seed_step(false, Some(&frames(1, 0)), "c", 0.0);
            let step = s.seed_step(false, Some(&frames(1, f)), "c", 1000.0);
            match step {
                SeedStep::Measured { accepted: got, .. } => assert_eq!(got, accepted, "F={f}"),
                other => panic!("{other:?}"),
            }
            assert_eq!(step.bias_to_cache().is_some(), accepted);
            assert_eq!(step.log_line("c").is_some(), accepted);
            assert_eq!(s.seed, None);
        }
    }

    #[test]
    fn the_frame_count_wraps_modulo_2_32() {
        let mut s = Scheduler::new(0.0);
        s.seed_step(false, Some(&frames(1, u32::MAX - 10)), "c", 0.0);
        let step = s.seed_step(false, Some(&frames(1, 900_000 - 11)), "c", 900.0);
        assert!(matches!(step, SeedStep::Measured { f: 900_000, .. }), "{step:?}");
    }

    #[test]
    fn absence_clears_both_learner_and_seed() {
        let mut s = Scheduler::new(0.0);
        s.learn(Reason::Periodic, &ok(0.0, true), Some(&status(33400, 2)), Some(0), 0.0);
        s.seed_step(false, Some(&frames(1, 0)), "c", 0.0);
        s.end_loop(false, 15.0);
        assert_eq!(s.learn, None);
        assert_eq!(s.seed, None);
    }

    #[test]
    fn the_sync_log_line_is_the_pythons() {
        assert_eq!(
            sync_log_line(Reason::Periodic, "clock set (sub-second): before +2.9 ms", 0),
            "sync (periodic): clock set (sub-second): before +2.9 ms"
        );
        assert_eq!(
            sync_log_line(Reason::Enumerated, "no reply from the keyboard", 1),
            "sync (enumerated): no reply from the keyboard [rc=1]"
        );
        assert_eq!(sync_log_line(Reason::Wake, "", 1), "sync (wake): no output [rc=1]");
    }
}
