//! The macOS host clock: `clock_gettime(CLOCK_REALTIME)` and `localtime_r`,
//! which are exactly what `ak820ctl.c`'s `now_s()` and `host_sod()` call
//! (`ak820ctl.c:251-257`), so parity here is by construction rather than by
//! reimplementation.
//!
//! ⚠️ That makes a sweep of this against `localtime_r` tautological, and it is
//! not the Phase 2 gate. Fixture parity cannot see a self-consistent wrong
//! time: both the GET's residual and the SET's payload go through `local()`.
//!
//! So the tests below check the mapping against **Python's `zoneinfo`**, a
//! separate implementation of the conversion, in child processes with `TZ`
//! set. The zones are chosen to break field mappings: a 30-minute DST shift
//! (Lord Howe), +5:45 and +12:45/+13:45 offsets (Kathmandu, Chatham), and
//! Berlin's repeated and skipped hours. A zone change **inside one process**
//! must be followed too, which is the long-running daemon's case. What no unit
//! test can do is change the *system* time zone, which reaches `localtime_r`
//! through `/etc/localtime` rather than `TZ`. That, independent reads through
//! the pinned `ak820ctl clock --read`, and a human reading the LCD against a
//! reference clock stay owed to Phase 2's live half.

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

    fn lt(year: i32, month: u8, day: u8, weekday: u8, hour: u8, minute: u8, second: u8) -> LocalTime {
        LocalTime { year, month, day, weekday, hour, minute, second }
    }

    /// Expected values from Python's `zoneinfo` (weekday 0 = Sunday, as
    /// `tm_wday`), computed 2026-09-16. Edmonton appears only in September:
    /// the tz database already moves Alberta to permanent UTC-6 in 2027, which
    /// is a political fact that could change again, not a property of this
    /// code.
    /// (zone, epoch second, (year, month, day, weekday, hour, minute, second))
    type Case = (&'static str, i64, (i32, u8, u8, u8, u8, u8, u8));
    const ZONES: &[Case] = &[
        ("UTC", 1_789_586_100, (2026, 9, 16, 3, 19, 15, 0)),
        ("America/Edmonton", 1_789_586_100, (2026, 9, 16, 3, 13, 15, 0)),
        ("Australia/Lord_Howe", 1_789_586_100, (2026, 9, 17, 4, 5, 45, 0)),
        ("Australia/Lord_Howe", 1_800_000_000, (2027, 1, 15, 5, 19, 0, 0)),
        ("Asia/Kathmandu", 1_789_586_100, (2026, 9, 17, 4, 1, 0, 0)),
        ("Asia/Kathmandu", 1_800_000_000, (2027, 1, 15, 5, 13, 45, 0)),
        ("Pacific/Chatham", 1_789_586_100, (2026, 9, 17, 4, 8, 0, 0)),
        ("Pacific/Chatham", 1_800_000_000, (2027, 1, 15, 5, 21, 45, 0)),
        ("Europe/Berlin", 1_789_586_100, (2026, 9, 16, 3, 21, 15, 0)),
        ("Europe/Berlin", 1_800_000_000, (2027, 1, 15, 5, 9, 0, 0)),
        // the repeated hour: 02:59:59 CEST, then 02:00:00 CET
        ("Europe/Berlin", 1_792_889_999, (2026, 10, 25, 0, 2, 59, 59)),
        ("Europe/Berlin", 1_792_890_000, (2026, 10, 25, 0, 2, 0, 0)),
        // the skipped hour: 01:59:59 CET, then 03:00:00 CEST
        ("Europe/Berlin", 1_806_195_599, (2027, 3, 28, 0, 1, 59, 59)),
        ("Europe/Berlin", 1_806_195_600, (2027, 3, 28, 0, 3, 0, 0)),
    ];

    /// Run this test's body again in a child with `TZ` set, so no other test's
    /// thread reads the environment while it changes.
    fn in_child(test: &str, zone: &str) {
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args([test, "--exact", "--nocapture", "--test-threads", "1"])
            .env("TZ", zone)
            .env("AK820_TZ_CHILD", zone)
            .output()
            .unwrap();
        let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
        assert!(out.status.success() && text.contains("1 passed"), "child for {zone}:\n{text}");
    }

    #[test]
    fn local_time_matches_zoneinfo_in_awkward_zones() {
        const NAME: &str = "platform::macos::host::tests::local_time_matches_zoneinfo_in_awkward_zones";
        if let Ok(zone) = std::env::var("AK820_TZ_CHILD") {
            for &(z, t, (y, mo, d, wd, h, mi, s)) in ZONES.iter().filter(|(z, ..)| *z == zone) {
                assert_eq!(SystemHost.local(t), lt(y, mo, d, wd, h, mi, s), "{z} at {t}");
            }
            return;
        }
        let mut zones: Vec<&str> = ZONES.iter().map(|(z, ..)| *z).collect();
        zones.dedup();
        for zone in zones {
            in_child(NAME, zone);
        }
    }

    /// The daemon runs for weeks. A zone change while it runs must reach the
    /// next `local()` without a restart: here through `TZ`, in one process.
    #[test]
    fn a_zone_change_inside_one_process_is_followed() {
        const NAME: &str = "platform::macos::host::tests::a_zone_change_inside_one_process_is_followed";
        if std::env::var("AK820_TZ_CHILD").is_ok() {
            let t = 1_789_586_100;
            assert_eq!(SystemHost.local(t).hour, 19, "UTC first");
            // Safe to mutate: a child process running exactly this test, on one thread.
            std::env::set_var("TZ", "Asia/Kathmandu");
            assert_eq!((SystemHost.local(t).day, SystemHost.local(t).hour), (17, 1), "Kathmandu after the change");
            std::env::set_var("TZ", "America/Edmonton");
            assert_eq!((SystemHost.local(t).day, SystemHost.local(t).hour), (16, 13), "Edmonton after the second change");
            return;
        }
        in_child(NAME, "UTC");
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
