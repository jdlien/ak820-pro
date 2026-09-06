//! The host's clock and its `localtime`, behind a trait so the transaction can
//! run against scripted instants.
//!
//! Two calls of the C's are reproduced here, and both are wall-clock:
//!
//! - `now_s()` — `CLOCK_REALTIME` as fractional seconds. Both ends of a GET and
//!   the SET's `t_enc` come from this; so does the round trip. ⚠️ That means
//!   the RTT is a *wall-clock* difference, as in the oracle, and a wall-clock
//!   step during a GET would produce the same nonsense in both. Using a
//!   monotonic clock for the RTT would be an improvement; it is not parity.
//! - `host_sod()` — `localtime()` of the whole second, plus the fraction. The
//!   board holds **local** time, so DST and timezone come from the host, and
//!   midnight wrap is [`super::wrap_day`]'s job rather than date arithmetic's.
//!
//! [`SystemHost`] uses `GetSystemTimePreciseAsFileTime` for the first and
//! `SystemTimeToTzSpecificLocalTime` for the second. Two sweeps below check
//! that against C runtimes, hourly across the firmware's years: one against
//! the UCRT's `_localtime64_s`, which this test binary links, and one against
//! **`msvcrt.dll`'s `_localtime64`, loaded by name** — because that, per
//! `ak820ctl.exe`'s import table, is the function mingw's `localtime` resolves
//! to, and the phase-2 audit rightly said the UCRT sweep alone was not an
//! oracle comparison. ⚠️ One stated assumption: the CRTs honour a `TZ`
//! environment variable and Win32 does not. Nothing in this project sets one,
//! the Scheduled Task environment has none, and both sweeps would fail loudly
//! on a machine where one is set.

#[cfg(test)]
use std::cell::{Cell, RefCell};
#[cfg(test)]
use std::collections::VecDeque;

use windows::Win32::Foundation::{FILETIME, SYSTEMTIME};
use windows::Win32::System::SystemInformation::GetSystemTimePreciseAsFileTime;
use windows::Win32::System::Time::{FileTimeToSystemTime, SystemTimeToTzSpecificLocalTime};

/// `struct tm`, with the fields this protocol sends. Weekday is `0` for
/// Sunday, as in both `tm_wday` and `SYSTEMTIME::wDayOfWeek`.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct LocalTime {
    pub year: i32,
    pub month: u8,
    pub day: u8,
    pub weekday: u8,
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
}

/// What the transaction needs from the machine it runs on.
pub trait Host {
    /// Seconds since the Unix epoch, fractional. The C's `now_s()`.
    fn now(&self) -> f64;
    /// The C's `localtime()` for a whole epoch second.
    ///
    /// Infallible, as the C treats it: `localtime` returns `NULL` only for a
    /// second Windows cannot place in a calendar, and the C dereferences the
    /// result unchecked. A host whose clock is there cannot sync anything.
    fn local(&self, unix_secs: i64) -> LocalTime;
}

/// The C's `host_sod(t)`: local seconds-of-day for a fractional epoch instant.
///
/// `(time_t)t` truncates, so the fraction added back is `t - trunc(t)`.
pub fn seconds_of_day(host: &impl Host, t: f64) -> f64 {
    let whole = t.trunc();
    let lt = host.local(whole as i64);
    super::host_seconds_of_day(lt.hour as u32, lt.minute as u32, lt.second as u32, t - whole)
}

/// Civil date for an epoch second, in UTC. Pure, and the fake host's
/// `localtime`; also what a reader can check [`SystemHost`] against by hand.
pub fn utc_local(unix_secs: i64) -> LocalTime {
    let days = unix_secs.div_euclid(86400);
    let sod = unix_secs.rem_euclid(86400);
    // Howard Hinnant's civil_from_days.
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z.rem_euclid(146097);
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    LocalTime {
        year: y as i32,
        month: m as u8,
        day: d as u8,
        // 1970-01-01 was a Thursday.
        weekday: (days + 4).rem_euclid(7) as u8,
        hour: (sod / 3600) as u8,
        minute: (sod % 3600 / 60) as u8,
        second: (sod % 60) as u8,
    }
}

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

/// A host with scripted instants and a fixed UTC offset, for tests.
///
/// Each `now()` hands out the next scripted value; once they run out, the last
/// one repeats, so a test that scripts too few instants still terminates and
/// fails on its assertions rather than panicking here.
#[cfg(test)]
pub struct FakeHost {
    nows: RefCell<VecDeque<f64>>,
    last: Cell<f64>,
    utc_offset_s: i64,
    calls: Cell<usize>,
}

#[cfg(test)]
impl FakeHost {
    pub fn new(utc_offset_s: i64, nows: impl IntoIterator<Item = f64>) -> FakeHost {
        let nows: VecDeque<f64> = nows.into_iter().collect();
        let last = nows.back().copied().unwrap_or(0.0);
        FakeHost {
            nows: RefCell::new(nows),
            last: Cell::new(last),
            utc_offset_s,
            calls: Cell::new(0),
        }
    }

    /// How many instants have been handed out.
    pub fn calls(&self) -> usize {
        self.calls.get()
    }

    /// Instants scripted but never asked for — a test that expected more
    /// requests than happened can see it.
    pub fn unused(&self) -> usize {
        self.nows.borrow().len()
    }
}

#[cfg(test)]
impl Host for FakeHost {
    fn now(&self) -> f64 {
        self.calls.set(self.calls.get() + 1);
        match self.nows.borrow_mut().pop_front() {
            Some(t) => {
                self.last.set(t);
                t
            }
            None => self.last.get(),
        }
    }

    fn local(&self, unix_secs: i64) -> LocalTime {
        utc_local(unix_secs + self.utc_offset_s)
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
    fn civil_dates_at_known_instants() {
        assert_eq!(utc_local(0), lt(1970, 1, 1, 4, 0, 0, 0));
        assert_eq!(utc_local(-1), lt(1969, 12, 31, 3, 23, 59, 59));
        assert_eq!(utc_local(951_782_400), lt(2000, 2, 29, 2, 0, 0, 0));
        assert_eq!(utc_local(1_787_961_600 + 40001), lt(2026, 8, 29, 6, 11, 6, 41));
        assert_eq!(utc_local(1_788_652_800), lt(2026, 9, 6, 0, 0, 0, 0));
        assert_eq!(utc_local(4_102_444_800), lt(2100, 1, 1, 5, 0, 0, 0));
    }

    #[test]
    fn weekdays_cycle_every_seven_days() {
        for k in 0..14 {
            assert_eq!(utc_local(k * 86400).weekday, ((k + 4) % 7) as u8);
        }
    }

    #[test]
    fn seconds_of_day_keeps_the_fraction() {
        let h = FakeHost::new(0, []);
        let day = 1_787_961_600.0;
        assert!((seconds_of_day(&h, day + 40000.25) - 40000.25).abs() < 1e-9);
        assert!((seconds_of_day(&h, day + 86399.999) - 86399.999).abs() < 1e-6);
        // and an offset host is offset
        let h = FakeHost::new(-6 * 3600, []);
        assert!((seconds_of_day(&h, day + 40000.25) - (40000.25 - 21600.0)).abs() < 1e-9);
    }

    #[test]
    fn the_fake_hands_out_its_script_then_repeats_the_last() {
        let h = FakeHost::new(0, [1.0, 2.0]);
        assert_eq!(h.now(), 1.0);
        assert_eq!(h.now(), 2.0);
        assert_eq!(h.now(), 2.0);
        assert_eq!(h.calls(), 3);
        assert_eq!(h.unused(), 0);
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
