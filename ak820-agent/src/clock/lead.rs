//! The outbound-lead learner.
//!
//! Separate from, and in addition to, the SOF-bias learner that lives in the
//! Python scheduler. This one is `ak820ctl`'s, and it runs once per SET:
//!
//! ```text
//! gate: good && !was_slewing && st != 0 && -500 < best_off < 500
//! e    = o' + best_off              # = lead - delay
//! adj  = clamp(-e / 4, -1, +1)      # at most 1 ms per update
//! lead = clamp(lead + adj, 0, 10)
//! ```
//!
//! The sign argument, from the C's own header: the GET measured
//! `o = board - host`; the firmware reported `o' = target - board_at_receipt`
//! `= lead - delay - o`; so `o' + o = lead - delay`, and moving the lead by a
//! quarter of that converges on the true one-way delay.
//!
//! Each constant is a scar:
//!
//! - **`±500 ms`** — a step (right after a flash, while the clock still drifts
//!   ~10 ms/s) is not a calibration sample, and once **blew the lead to its
//!   clamp**.
//! - **`st != 0`** — only a *slewed* correction on a settled board calibrates.
//! - **`!was_slewing`** — a board mid-slew moves 20 ms/s.
//! - **gain ¼, ±1 ms** — one bad sample cannot move the lead far.

use super::set::SetStatus;
use super::Measurement;

/// The learned lead can never exceed this, whatever the samples say.
pub const MAX_LEAD_MS: f64 = 10.0;
/// One update moves the lead by at most this much.
pub const MAX_STEP_MS: f64 = 1.0;
/// `|best_off|` must be strictly inside this for the sample to calibrate.
pub const CALIBRATION_WINDOW_MS: f64 = 500.0;

/// Does this transaction's measurement qualify as a calibration sample?
///
/// `None` for the measurement is the C's `good == 0`: every GET found the
/// clock unset, so there is no `best_off` to learn from.
pub fn calibrates(measurement: Option<&Measurement>, status: SetStatus) -> bool {
    let Some(m) = measurement else {
        return false;
    };
    !m.was_slewing
        && status != SetStatus::Stepped
        && m.offset_ms > -CALIBRATION_WINDOW_MS
        && m.offset_ms < CALIBRATION_WINDOW_MS
}

/// The lead after this transaction, or `None` when the gate refused to learn
/// from it.
///
/// `Some` even when the adjustment happens to be zero: the gate passed, and a
/// caller reporting "learned from this sample" should say so.
pub fn learn(
    lead_ms: f64,
    measurement: Option<&Measurement>,
    status: SetStatus,
    receipt_offset_ms: f64,
) -> Option<f64> {
    if !calibrates(measurement, status) {
        return None;
    }
    let best_off = measurement.expect("gate passed").offset_ms;
    let e = receipt_offset_ms + best_off;
    // The C clamps with two `if`s each; `clamp` is the same function on
    // finite bounds, and these are constants.
    let adj = (-e / 4.0).clamp(-MAX_STEP_MS, MAX_STEP_MS);
    Some((lead_ms + adj).clamp(0.0, MAX_LEAD_MS))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(offset_ms: f64) -> Measurement {
        Measurement {
            offset_ms,
            rtt_ms: 4.0,
            uncertainty_ms: 1.0,
            was_slewing: false,
            good: 5,
        }
    }

    /// The sign, from the C header's derivation: `o' + o = lead - delay`. A
    /// positive sum means the lead is too long, so it must come down.
    #[test]
    fn a_positive_error_shortens_the_lead() {
        // o' = -10, best_off = +8: e = -2, adj = +0.5
        assert_eq!(learn(2.354, Some(&m(8.0)), SetStatus::Slewing, -10.0), Some(2.854));
        // o' = +6, best_off = +2: e = +8, adj = -2 -> clamped to -1
        assert_eq!(learn(2.354, Some(&m(2.0)), SetStatus::Slewing, 6.0), Some(1.354));
    }

    #[test]
    fn the_gain_is_a_quarter() {
        // e = 1.0 -> adj = -0.25
        assert_eq!(learn(3.0, Some(&m(0.5)), SetStatus::Slewing, 0.5), Some(2.75));
        // e = -0.4 -> adj = +0.1
        let l = learn(3.0, Some(&m(-0.2)), SetStatus::Slewing, -0.2).unwrap();
        assert!((l - 3.1).abs() < 1e-12);
    }

    #[test]
    fn one_update_moves_at_most_one_millisecond() {
        assert_eq!(learn(5.0, Some(&m(100.0)), SetStatus::Slewing, 100.0), Some(4.0));
        assert_eq!(learn(5.0, Some(&m(-100.0)), SetStatus::Slewing, -100.0), Some(6.0));
        // exactly at the clamp boundary: e = ±4 -> adj = ∓1, not clamped
        assert_eq!(learn(5.0, Some(&m(2.0)), SetStatus::Slewing, 2.0), Some(4.0));
    }

    #[test]
    fn the_lead_stays_within_zero_and_ten() {
        assert_eq!(learn(0.2, Some(&m(2.0)), SetStatus::Slewing, 2.0), Some(0.0));
        assert_eq!(learn(9.8, Some(&m(-2.0)), SetStatus::Slewing, -2.0), Some(10.0));
        assert_eq!(learn(0.0, Some(&m(1.0)), SetStatus::Slewing, 1.0), Some(0.0));
    }

    #[test]
    fn a_zero_error_still_counts_as_learned() {
        assert_eq!(learn(2.5, Some(&m(3.0)), SetStatus::Slewing, -3.0), Some(2.5));
    }

    // -- the gates, one at a time -----------------------------------------

    #[test]
    fn no_good_sample_means_nothing_to_learn_from() {
        assert_eq!(learn(2.5, None, SetStatus::Slewing, 0.0), None);
    }

    /// A slewing board moves 20 ms/s and is not measuring the same thing.
    #[test]
    fn a_slewing_burst_does_not_calibrate() {
        let mut s = m(1.0);
        s.was_slewing = true;
        assert_eq!(learn(2.5, Some(&s), SetStatus::Slewing, 0.0), None);
    }

    /// Only a slewed correction calibrates. `st != 0` is the C's literal test,
    /// so an unknown non-zero status passes it, as it would there.
    #[test]
    fn a_step_does_not_calibrate_but_any_other_status_does() {
        assert_eq!(learn(2.5, Some(&m(1.0)), SetStatus::Stepped, 0.0), None);
        assert!(learn(2.5, Some(&m(1.0)), SetStatus::Slewing, 0.0).is_some());
        assert!(learn(2.5, Some(&m(1.0)), SetStatus::Other(2), 0.0).is_some());
    }

    /// ⚠️ The ±500 ms window is strict at both ends, and exists because a
    /// step-sized offset once blew the lead to its clamp.
    #[test]
    fn the_calibration_window_is_strictly_inside_500_ms() {
        assert!(learn(2.5, Some(&m(499.9)), SetStatus::Slewing, 0.0).is_some());
        assert!(learn(2.5, Some(&m(-499.9)), SetStatus::Slewing, 0.0).is_some());
        assert_eq!(learn(2.5, Some(&m(500.0)), SetStatus::Slewing, 0.0), None);
        assert_eq!(learn(2.5, Some(&m(-500.0)), SetStatus::Slewing, 0.0), None);
        assert_eq!(learn(2.5, Some(&m(1524.6)), SetStatus::Slewing, 0.0), None);
    }
}
