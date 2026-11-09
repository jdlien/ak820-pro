//! The host's input, followed across samples: how long since the last input
//! on this machine, and whether there was any between two samples. The
//! radio's hold and its wait after a silence read it (`crate::radio`).
//!
//! The platform reads one [`Reading`] a media tick (`Platform::host_input`),
//! from the same sources the lock-light sender's hold reads:
//!
//! - **Windows**: `GetLastInputInfo`'s `dwTime` (the last input's tick)
//!   against `GetTickCount`, both u32 milliseconds. Input is a change of
//!   `dwTime`, the last input's identity, never a small duration: after 49.7
//!   days without input the wrapping difference comes back round to near
//!   zero, which is no input at all (codex, the radio hold's review, 4).
//!   While `dwTime` holds, the idle grows by the tick counter's own progress.
//! - **macOS**: the HID system's `HIDIdleTime`, a duration. Input is a
//!   reading that fell: short of the last one plus the time between them, by
//!   the monotonic clock, by more than [`READ_JITTER`]. That clock stops
//!   while the Mac sleeps, and `HIDIdleTime` may or may not count the sleep,
//!   so a sleep can only make a reading look older than the clock allows,
//!   never younger: no sleep reads as input. A fall that places the input
//!   before the last sample is still input; it is what input just before a
//!   sleep looks like after the wake if the HID system counts the sleep
//!   (codex, the verify: refusing it held a board until the next input). The
//!   HID system resets the idle only on input or declared user activity, as
//!   the lock-light sender assumes too. While there is none, the idle grows
//!   by the monotonic clock, or follows a reading that runs ahead of it.

use std::time::{Duration, Instant};

/// Two clocks read apart: a macOS reading this far short of the last one
/// plus the time since is not input (the lock-light sender's `TICK_SLACK_MS`).
pub const READ_JITTER: Duration = Duration::from_millis(250);

/// One raw reading of the host's input, as the platform gives it.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Reading {
    /// Windows: `GetLastInputInfo`'s `dwTime` and `GetTickCount`, u32
    /// milliseconds since boot.
    Ticks { last: u32, now: u32 },
    /// macOS: `HIDIdleTime`, how long since the last input.
    Idle(Duration),
}

/// One sample, against the one before it.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct Seen {
    /// How long since the last input.
    pub idle: Duration,
    /// Input since the previous sample. Never on a first sample: with no
    /// history there is nothing to compare.
    pub input: bool,
}

/// The samples' history: the last reading, when, and the idle it gave.
#[derive(Debug, Default)]
pub struct Track {
    prev: Option<(Reading, Instant, Duration)>,
}

impl Track {
    /// Take a sample read at `at`. `None` (unreadable) answers `None` and
    /// forgets the history, so the next readable sample is a first one.
    pub fn observe(&mut self, reading: Option<Reading>, at: Instant) -> Option<Seen> {
        let Some(r) = reading else {
            self.prev = None;
            return None;
        };
        let ms = |v: u32| Duration::from_millis(u64::from(v));
        let seen = match (self.prev, r) {
            (Some((Reading::Ticks { last: was, now: then }, _, idle)), Reading::Ticks { last, now }) => {
                if last == was {
                    Seen { idle: idle + ms(now.wrapping_sub(then)), input: false }
                } else {
                    Seen { idle: ms(now.wrapping_sub(last)), input: true }
                }
            }
            (Some((Reading::Idle(was), then, idle)), Reading::Idle(d)) => {
                let elapsed = at.saturating_duration_since(then);
                if d + READ_JITTER < was + elapsed {
                    Seen { idle: d, input: true }
                } else {
                    Seen { idle: (idle + elapsed).max(d), input: false }
                }
            }
            // A first sample, or a change of source: nothing to compare.
            (_, Reading::Ticks { last, now }) => Seen { idle: ms(now.wrapping_sub(last)), input: false },
            (_, Reading::Idle(d)) => Seen { idle: d, input: false },
        };
        self.prev = Some((r, at, seen.idle));
        Some(seen)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const S: Duration = Duration::from_secs(1);

    fn ticks(last: u32, now: u32) -> Option<Reading> {
        Some(Reading::Ticks { last, now })
    }

    fn idle(d: Duration) -> Option<Reading> {
        Some(Reading::Idle(d))
    }

    #[test]
    fn windows_input_is_a_change_of_the_last_inputs_tick() {
        let t0 = Instant::now();
        let mut t = Track::default();
        assert_eq!(t.observe(ticks(1_000, 41_000), t0), Some(Seen { idle: 40 * S, input: false }), "a first sample");
        assert_eq!(t.observe(ticks(1_000, 44_000), t0 + 3 * S), Some(Seen { idle: 43 * S, input: false }));
        // A key at 46_500: the identity moved.
        assert_eq!(t.observe(ticks(46_500, 47_000), t0 + 6 * S), Some(Seen { idle: S / 2, input: true }));
        assert_eq!(t.observe(ticks(46_500, 50_000), t0 + 9 * S), Some(Seen { idle: 7 * S / 2, input: false }));
    }

    /// 50 days without input: the wrapping difference comes back round to
    /// near zero, and is still no input; the idle keeps growing.
    #[test]
    fn windows_fifty_days_without_input_never_wrap_back_to_fresh() {
        let t0 = Instant::now();
        let mut t = Track::default();
        let last = 5_000u32;
        let mut now = last;
        let hour = 3_600_000u32;
        let mut seen = None;
        for h in 0..=50 * 24 {
            seen = t.observe(ticks(last, now), t0 + Duration::from_secs(3600 * h as u64));
            assert!(!seen.unwrap().input, "hour {h}");
            now = now.wrapping_add(hour);
        }
        // The naive difference: under a day, though 50 days have passed.
        assert!(now.wrapping_sub(hour).wrapping_sub(last) < 86_400_000);
        assert_eq!(seen.unwrap().idle, Duration::from_secs(50 * 86_400));
    }

    /// The tick counter's own rollover with fresh input is ordinary.
    #[test]
    fn windows_the_tick_counters_rollover_is_ordinary() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(ticks(u32::MAX - 10_000, u32::MAX - 5_000), t0);
        let seen = t.observe(ticks(u32::MAX - 500, 1_500), t0 + 6 * S).unwrap();
        assert_eq!(seen, Seen { idle: Duration::from_millis(2_001), input: true });
        let seen = t.observe(ticks(u32::MAX - 500, 4_500), t0 + 9 * S).unwrap();
        assert_eq!(seen, Seen { idle: Duration::from_millis(5_001), input: false });
    }

    #[test]
    fn macos_an_idle_growing_with_the_clock_is_no_input_within_the_jitter() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(idle(10 * S), t0);
        assert_eq!(t.observe(idle(13 * S), t0 + 3 * S), Some(Seen { idle: 13 * S, input: false }));
        // Read 200 ms early against the clock: jitter, not input.
        let seen = t.observe(idle(16 * S - Duration::from_millis(200)), t0 + 6 * S).unwrap();
        assert!(!seen.input);
        assert_eq!(seen.idle, 16 * S, "the clock's progress, not the short reading");
    }

    #[test]
    fn macos_a_fall_after_the_last_sample_is_input() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(idle(40 * S), t0);
        assert_eq!(t.observe(idle(S), t0 + 3 * S), Some(Seen { idle: S, input: true }));
        // Typing at the last sample and just after it still shows, once the
        // fall clears the jitter.
        assert_eq!(t.observe(idle(S / 2), t0 + 6 * S), Some(Seen { idle: S / 2, input: true }));
    }

    /// Input just before the Mac slept, read after its wake (codex, the
    /// verify's new P3). The monotonic clock stops while the Mac sleeps;
    /// whether `HIDIdleTime` counts that sleep or not, a fall is input. Here
    /// 200 s idle, a key a second later, 20 s asleep, a sample 3 awake
    /// seconds after the first.
    #[test]
    fn macos_input_before_a_sleep_counts_after_the_wake() {
        let t0 = Instant::now();
        // The HID system counting the sleep: 2 awake seconds since the key
        // and the 20 asleep.
        let mut t = Track::default();
        t.observe(idle(200 * S), t0);
        assert_eq!(t.observe(idle(22 * S), t0 + 3 * S), Some(Seen { idle: 22 * S, input: true }));
        // Or not counting it: 2 s.
        let mut t = Track::default();
        t.observe(idle(200 * S), t0);
        assert_eq!(t.observe(idle(2 * S), t0 + 3 * S), Some(Seen { idle: 2 * S, input: true }));
    }

    /// A sleep with no input before it: no input after the wake either way,
    /// and the idle the larger count.
    #[test]
    fn macos_a_sleep_without_input_is_no_input() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(idle(200 * S), t0);
        assert_eq!(t.observe(idle(223 * S), t0 + 3 * S), Some(Seen { idle: 223 * S, input: false }), "sleep counted");
        let mut t = Track::default();
        t.observe(idle(200 * S), t0);
        assert_eq!(t.observe(idle(203 * S), t0 + 3 * S), Some(Seen { idle: 203 * S, input: false }), "not counted");
    }

    /// A reading that runs ahead of the clock (the Mac's own sleep, counted
    /// by the HID system and not by the monotonic clock) is taken.
    #[test]
    fn macos_a_reading_ahead_of_the_clock_is_taken() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(idle(40 * S), t0);
        assert_eq!(t.observe(idle(3_640 * S), t0 + 3 * S), Some(Seen { idle: 3_640 * S, input: false }));
    }

    #[test]
    fn an_unreadable_sample_forgets_the_history() {
        let t0 = Instant::now();
        let mut t = Track::default();
        t.observe(idle(40 * S), t0);
        assert_eq!(t.observe(None, t0 + 3 * S), None);
        // Readable again: a first sample, whatever it shows.
        assert_eq!(t.observe(idle(S), t0 + 6 * S), Some(Seen { idle: S, input: false }));
        assert_eq!(t.observe(None, t0 + 9 * S), None);
        assert_eq!(t.observe(ticks(0, 5_000), t0 + 12 * S), Some(Seen { idle: 5 * S, input: false }));
    }
}
