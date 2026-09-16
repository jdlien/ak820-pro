//! The macOS host clock: `clock_gettime(CLOCK_REALTIME)` and `localtime_r`,
//! which are exactly what `ak820ctl.c`'s `now_s()` and `host_sod()` call
//! (`ak820ctl.c:251-257`), so parity here is by construction rather than by
//! reimplementation.
//!
//! ⚠️ That makes a sweep of this against `localtime_r` tautological, and it is
//! not the Phase 2 gate. Fixture parity cannot see a self-consistent wrong
//! time: both the GET's residual and the SET's payload go through `local()`.
//! Phase 2 still owes a TZ-change test, independent reads through the pinned
//! `ak820ctl clock --read` with the daemon paused, and a human reading the LCD
//! against a reference clock.

use std::os::raw::{c_char, c_int, c_long};

use crate::clock::host::{Host, LocalTime};

/// `struct tm` on Darwin, which carries `tm_gmtoff` and `tm_zone` after the
/// nine standard fields.
#[repr(C)]
struct Tm {
    tm_sec: c_int,
    tm_min: c_int,
    tm_hour: c_int,
    tm_mday: c_int,
    tm_mon: c_int,
    tm_year: c_int,
    tm_wday: c_int,
    tm_yday: c_int,
    tm_isdst: c_int,
    tm_gmtoff: c_long,
    tm_zone: *const c_char,
}

#[repr(C)]
struct Timespec {
    tv_sec: i64,
    tv_nsec: c_long,
}

const CLOCK_REALTIME: c_int = 0;

extern "C" {
    fn clock_gettime(clock_id: c_int, tp: *mut Timespec) -> c_int;
    fn localtime_r(clock: *const i64, result: *mut Tm) -> *mut Tm;
}

/// The real machine.
#[derive(Copy, Clone, Debug, Default)]
pub struct SystemHost;

impl Host for SystemHost {
    fn now(&self) -> f64 {
        let mut ts = Timespec { tv_sec: 0, tv_nsec: 0 };
        unsafe { clock_gettime(CLOCK_REALTIME, &mut ts) };
        // `(double)ts.tv_sec + ts.tv_nsec / 1e9`, the C's shape exactly.
        ts.tv_sec as f64 + ts.tv_nsec as f64 / 1e9
    }

    fn local(&self, unix_secs: i64) -> LocalTime {
        let mut tm: Tm = unsafe { std::mem::zeroed() };
        let got = unsafe { localtime_r(&unix_secs, &mut tm) };
        assert!(!got.is_null(), "localtime_r({unix_secs}) failed");
        LocalTime {
            year: tm.tm_year + 1900,
            month: (tm.tm_mon + 1) as u8,
            day: tm.tm_mday as u8,
            weekday: tm.tm_wday as u8,
            hour: tm.tm_hour as u8,
            minute: tm.tm_min as u8,
            second: tm.tm_sec as u8,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_system_clock_is_the_unix_epoch_in_seconds() {
        let std_now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
        let ours = SystemHost.now();
        assert!((ours - std_now).abs() < 1.0, "{ours} vs {std_now}");
        assert!(SystemHost.now() >= ours);
    }

    #[test]
    fn local_time_of_the_present_is_plausible() {
        let now = SystemHost.now() as i64;
        let l = SystemHost.local(now);
        assert!((2026..=2099).contains(&l.year));
        assert!((1..=12).contains(&l.month) && (1..=31).contains(&l.day));
        assert!(l.weekday <= 6 && l.hour <= 23 && l.minute <= 59 && l.second <= 59);
        assert!(SystemHost.local(now + 1) != l);
    }

    /// Time zones differ from UTC by whole minutes, so whatever zone this
    /// machine is in, libc's seconds must match the pure UTC calendar's.
    #[test]
    fn minutes_and_seconds_agree_with_the_pure_utc_calendar() {
        for t in (1_767_225_600i64..1_767_225_600 + 86_400 * 3).step_by(3601) {
            let a = SystemHost.local(t);
            let b = crate::clock::host::utc_local(t);
            assert_eq!(a.second, b.second, "at {t}");
        }
    }
}
