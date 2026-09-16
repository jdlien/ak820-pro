//! The Windows host clock: `GetSystemTimePreciseAsFileTime` and
//! `SystemTimeToTzSpecificLocalTime`, behind `clock::host::Host`.
//!
//! Two sweeps below check that against C runtimes, hourly across the firmware's
//! years: one against the UCRT's `_localtime64_s`, which this test binary
//! links, and one against **`msvcrt.dll`'s `_localtime64`, loaded by name** —
//! because that, per `ak820ctl.exe`'s import table, is the function mingw's
//! `localtime` resolves to, and the phase-2 audit rightly said the UCRT sweep
//! alone was not an oracle comparison. ⚠️ One stated assumption: the CRTs
//! honour a `TZ` environment variable and Win32 does not. Nothing in this
//! project sets one, the Scheduled Task environment has none, and both sweeps
//! would fail loudly on a machine where one is set.

use windows::Win32::Foundation::{FILETIME, SYSTEMTIME};
use windows::Win32::System::SystemInformation::GetSystemTimePreciseAsFileTime;
use windows::Win32::System::Time::{FileTimeToSystemTime, SystemTimeToTzSpecificLocalTime};

use crate::clock::host::{Host, LocalTime};

/// 100 ns ticks between 1601-01-01 (FILETIME's epoch) and 1970-01-01.
const EPOCH_TICKS: i64 = 116_444_736_000_000_000;
const TICKS_PER_SEC: i64 = 10_000_000;

/// The real machine.
pub struct SystemHost;

impl Host for SystemHost {
    fn now(&self) -> f64 {
        let ft = unsafe { GetSystemTimePreciseAsFileTime() };
        let ticks = (((ft.dwHighDateTime as i64) << 32) | ft.dwLowDateTime as i64) - EPOCH_TICKS;
        // Whole seconds plus a fraction, the same shape as the C's
        // `tv_sec + tv_nsec / 1e9`, so the two round identically.
        (ticks / TICKS_PER_SEC) as f64 + (ticks % TICKS_PER_SEC) as f64 / TICKS_PER_SEC as f64
    }

    fn local(&self, unix_secs: i64) -> LocalTime {
        let ticks = unix_secs * TICKS_PER_SEC + EPOCH_TICKS;
        let ft = FILETIME {
            dwLowDateTime: ticks as u32,
            dwHighDateTime: (ticks >> 32) as u32,
        };
        let mut utc = SYSTEMTIME::default();
        let mut local = SYSTEMTIME::default();
        unsafe {
            FileTimeToSystemTime(&ft, &mut utc)
                .expect("the system clock is outside the range Windows can convert");
            SystemTimeToTzSpecificLocalTime(None, &utc, &mut local)
                .expect("the system clock is outside the range Windows can convert");
        }
        LocalTime {
            year: local.wYear as i32,
            month: local.wMonth as u8,
            day: local.wDay as u8,
            weekday: local.wDayOfWeek as u8,
            hour: local.wHour as u8,
            minute: local.wMinute as u8,
            second: local.wSecond as u8,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lt(y: i32, mo: u8, d: u8, wd: u8, h: u8, mi: u8, s: u8) -> LocalTime {
        LocalTime {
            year: y,
            month: mo,
            day: d,
            weekday: wd,
            hour: h,
            minute: mi,
            second: s,
        }
    }

    #[test]
    fn the_system_clock_is_the_unix_epoch_in_seconds() {
        let std_now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        let ours = SystemHost.now();
        assert!((ours - std_now).abs() < 1.0, "{ours} vs {std_now}");
        assert!(SystemHost.now() >= ours);
    }

    /// The CRT's `localtime`, which is what the C oracle calls.
    #[repr(C)]
    #[derive(Default)]
    struct Tm {
        sec: i32,
        min: i32,
        hour: i32,
        mday: i32,
        mon: i32,
        year: i32,
        wday: i32,
        yday: i32,
        isdst: i32,
    }
    extern "C" {
        fn _localtime64_s(tm: *mut Tm, t: *const i64) -> i32;
    }

    fn crt_local(unix_secs: i64) -> LocalTime {
        let mut tm = Tm::default();
        let rc = unsafe { _localtime64_s(&mut tm, &unix_secs) };
        assert_eq!(rc, 0, "_localtime64_s({unix_secs})");
        lt(
            tm.year + 1900,
            (tm.mon + 1) as u8,
            tm.mday as u8,
            tm.wday as u8,
            tm.hour as u8,
            tm.min as u8,
            tm.sec as u8,
        )
    }

    /// ⚠️ Parity with the oracle's `localtime`, on this machine's time zone,
    /// swept hourly across the years the firmware accepts. Every DST
    /// transition in that span is inside the sweep.
    #[test]
    fn local_time_agrees_with_the_crt_across_the_firmwares_years() {
        let start = 1_767_225_600i64; // 2026-01-01T00:00:00Z
        let end = 4_070_908_800i64; // 2099-01-01T00:00:00Z
        let mut t = start;
        let mut checked = 0;
        while t < end {
            assert_eq!(SystemHost.local(t), crt_local(t), "at {t}");
            t += 3600 + 1; // an odd step, so minutes and seconds vary too
            checked += 1;
        }
        assert!(checked > 600_000);
    }

    /// The oracle's own CRT: `ak820ctl.exe` imports `msvcrt.dll!_localtime64`
    /// (its import table, 2026-09-06), so this loads that function by name and
    /// sweeps it the same way. Unlike the UCRT one above, this is the
    /// comparison the word "oracle" was being used for.
    #[test]
    fn local_time_agrees_with_the_oracles_msvcrt_localtime() {
        use windows::core::{s, w};
        use windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryW};

        type Localtime64 = unsafe extern "C" fn(*const i64) -> *const Tm;
        let module = unsafe { LoadLibraryW(w!("msvcrt.dll")) }.expect("msvcrt.dll is inbox");
        let sym = unsafe { GetProcAddress(module, s!("_localtime64")) }.expect("_localtime64");
        let localtime64: Localtime64 = unsafe { std::mem::transmute(sym) };

        let start = 1_767_225_600i64; // 2026-01-01T00:00:00Z
        let end = 4_070_908_800i64; // 2099-01-01T00:00:00Z
        let mut t = start;
        let mut checked = 0;
        while t < end {
            let tm = unsafe { localtime64(&t) };
            assert!(!tm.is_null(), "msvcrt localtime({t}) returned NULL");
            let tm = unsafe { &*tm };
            let theirs = lt(
                tm.year + 1900,
                (tm.mon + 1) as u8,
                tm.mday as u8,
                tm.wday as u8,
                tm.hour as u8,
                tm.min as u8,
                tm.sec as u8,
            );
            assert_eq!(SystemHost.local(t), theirs, "at {t}");
            t += 3600 + 1;
            checked += 1;
        }
        assert!(checked > 600_000);
    }

    #[test]
    fn local_time_of_the_present_is_plausible() {
        let now = SystemHost.now() as i64;
        let l = SystemHost.local(now);
        assert!((2026..=2099).contains(&l.year));
        assert!((1..=12).contains(&l.month));
        assert!((1..=31).contains(&l.day));
        assert!(l.weekday <= 6);
        assert!(l.hour <= 23 && l.minute <= 59 && l.second <= 59);
        let next = SystemHost.local(now + 1);
        assert!(next != l, "one second later is a different time");
    }
}
