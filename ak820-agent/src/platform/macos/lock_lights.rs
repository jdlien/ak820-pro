//! The lock-LED channel's macOS half: the board's Bluetooth keyboard and its
//! LED output report (`plans/LOCK-LED-CHANNEL-PLAN.md`, "The daemon's sender:
//! design"; the route measured 10-18 with `hostagent/ledprobe/`: 24 of 24
//! frames committed, P3 moving no light).
//!
//! - **The route:** an output report to the BLE keyboard (0C45:FEFE,
//!   transport "Bluetooth Low Energy", usage 1:6), report 2, the buffer the
//!   report ID then the LED byte, as the probe sent it. P3, bits 3-7: macOS's
//!   own lock state never moves.
//! - **Found without opening anything else:** the registry matched on VID/PID
//!   ([`discovery::list_ble`]), never HID enumeration (the UPS incident).
//! - **Input Monitoring:** macOS opens a keyboard only for a process it has
//!   granted ListenEvent. Without it the channel is off and says why; nothing
//!   here asks for it (a consent dialog is the user's to raise, never the
//!   daemon's at night).
//! - **The user's locks:** Caps from the HID system
//!   (`IOHIDGetModifierLockState`), and only while this session is on the
//!   console and unlocked (R4-1); Num and Scroll are 0, macOS keeps neither.
//! - **One write at a time, with a deadline:** `IOHIDDeviceSetReportWithCallback`
//!   scheduled on this thread's run loop, which runs until the completion.
//!   One that does not retire in its deadline is [`WriteError::Stuck`] and
//!   poisons the channel for the process's life (R3-3): its buffer, context
//!   and device are leaked, never freed under IOKit.
//!
//! A [`BleLights`] belongs to the thread that opened it (its run loop): the
//! sender's.
#![allow(non_upper_case_globals)] // matching on IOKit's constants, as device.rs does

use std::cell::Cell;
use std::os::raw::c_void;
use std::time::{Duration, Instant};

use super::cf::{property, Cf, Io, Pool};
use super::discovery::{self, Candidate};
use super::sys::*;
use crate::lockchan::frame::{LockLights, WriteError};
use crate::lockchan::{Profile, CAPS};

/// The BLE keyboard's LED output report (`ledprobe.log`, 10-18: "LED outputs
/// (report 2): num caps scroll").
const REPORT_ID: u8 = 2;
/// IOKit's own deadline for one write, and our wait past it before calling the
/// write stuck. The Mac's BLE writes took 41-322 ms (10-18).
const WRITE_TIMEOUT: Duration = Duration::from_secs(1);
const WRITE_GRACE: Duration = Duration::from_millis(250);
const TRANSPORT: &str = "Bluetooth Low Energy";
/// A data write's limit, not the default 300 ms. The Mac's BLE writes take
/// 88-430 ms, and five of the six frames lost to the 300 ms on 10-20 were a
/// data write of 343-379 ms (`history/lockchan-mac-interference-20261020/`).
/// A write completes at its ATT response, after the board has the byte, so
/// the gap the board sees is at most this plus how far that response trails
/// the arrival: 50 ms is left for it under the receiver's 500. Sent must
/// still always mean committed; `scripts/mac_lockchan_gaps.py` checks it.
const DATA_GAP: Duration = Duration::from_millis(450);

/// The board's keyboard among the BLE device's services: the keyboard
/// collection (usage page 1, usage 6) over BLE. `Err` when more than one.
pub fn choose(candidates: &[Candidate]) -> Result<Option<usize>, String> {
    let ours: Vec<usize> = candidates
        .iter()
        .enumerate()
        .filter(|(_, c)| {
            c.usage_page == Some(1) && c.usage == Some(6) && c.transport.as_deref() == Some(TRANSPORT)
        })
        .map(|(i, _)| i)
        .collect();
    match ours.as_slice() {
        [] => Ok(None),
        [one] => Ok(Some(*one)),
        many => Err(format!("{} BLE keyboard collections listed for the board; refusing to guess", many.len())),
    }
}

/// Whether this process may open a keyboard: TCC's ListenEvent.
pub fn input_monitoring() -> Result<(), String> {
    match unsafe { IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) } {
        kIOHIDAccessTypeGranted => Ok(()),
        kIOHIDAccessTypeDenied => Err("Input Monitoring is off for this program (System Settings, Privacy & \
                                       Security, Input Monitoring)"
            .into()),
        _ => Err("Input Monitoring has not been granted to this program yet".into()),
    }
}

/// This session on the console and its screen unlocked (R4-1): the locks
/// the HID system reports are then this user's, and a frame reaches the
/// keyboard in front of them.
pub fn session_active() -> bool {
    let Some(dict) = Cf::owned(unsafe { CGSessionCopyCurrentDictionary() }) else {
        return false; // no GUI session: a daemon outside the user's login
    };
    let flag = |key: &str| -> Flag {
        let k = Cf::string(key);
        let v = unsafe { CFDictionaryGetValue(dict.as_ptr(), k.as_ptr()) };
        if v.is_null() {
            return Flag::Absent;
        }
        if unsafe { CFGetTypeID(v) } != unsafe { CFBooleanGetTypeID() } {
            return Flag::Malformed;
        }
        Flag::Is(unsafe { CFBooleanGetValue(v) } != 0)
    };
    active(flag("kCGSSessionOnConsoleKey"), flag("CGSSessionScreenIsLocked"))
}

/// A session dictionary's boolean: there, not there, or not a boolean.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Flag {
    Absent,
    Is(bool),
    Malformed,
}

/// On the console, and the screen-lock key absent (as it is when unlocked:
/// `keydrop_test.py`) or false. Anything malformed is not active (codex, the
/// macOS writer's review, P3 5).
fn active(on_console: Flag, locked: Flag) -> bool {
    on_console == Flag::Is(true) && matches!(locked, Flag::Absent | Flag::Is(false))
}

/// The HID system's service, for the Caps state and the idle time.
fn hid_system() -> Option<Io> {
    let matching = unsafe { IOServiceMatching(c"IOHIDSystem".as_ptr()) };
    if matching.is_null() {
        return None;
    }
    // Consumes `matching`.
    let s = unsafe { IOServiceGetMatchingService(0, matching as CFDictionaryRef) };
    (s != 0).then(|| Io(s))
}

/// The HID system's Caps Lock, read through a connection of its own: for
/// `ak820 lockchan check` (BleLights reads it through the one it holds).
pub fn caps() -> Option<bool> {
    let sys = hid_system()?;
    let mut hid: io_connect_t = 0;
    if unsafe { IOServiceOpen(sys.0, mach_task_self_, kIOHIDParamConnectType, &mut hid) } != 0 {
        return None;
    }
    let mut caps = false;
    let kr = unsafe { IOHIDGetModifierLockState(hid, kIOHIDCapsLockState, &mut caps) };
    unsafe { IOServiceClose(hid) };
    (kr == 0).then_some(caps)
}

/// How long since the last input on this machine, any device (the HID
/// system's `HIDIdleTime`, nanoseconds), for the sender's wake guess.
pub fn idle() -> Option<Duration> {
    let sys = hid_system()?;
    let ns = property(sys.0, "HIDIdleTime")?.to_i64()?;
    (ns >= 0).then(|| Duration::from_nanos(ns as u64))
}

/// The completion's slot, written by the callback on this thread's run loop.
struct Done(Cell<Option<IOReturn>>);

unsafe extern "C" fn on_written(
    context: *mut c_void,
    result: IOReturn,
    _sender: *mut c_void,
    _report_type: IOHIDReportType,
    _report_id: u32,
    _report: *mut u8,
    _report_length: CFIndex,
) {
    let done = &*(context as *const Done);
    done.0.set(Some(result));
}

pub struct BleLights {
    dev: IOHIDDeviceRef,
    rl: CFRunLoopRef,
    hid: io_connect_t,
    /// Boxed: IOKit holds pointers to both until a write retires.
    done: Box<Done>,
    buf: Box<[u8; 2]>,
    poisoned: bool,
    pub name: String,
    /// The slowest write's completion, and how many took over 100 ms: for
    /// `ak820 lockchan send` and the gap study (10-20).
    pub slowest: Duration,
    pub over_100ms: u32,
}

impl BleLights {
    /// The board's BLE keyboard, opened on this thread: `Ok(None)` when it is
    /// not listed (not paired, not connected, the slider elsewhere).
    pub fn open() -> Result<Option<BleLights>, String> {
        input_monitoring()?;
        let listed = discovery::list_ble()?;
        let cands: Vec<Candidate> = listed.iter().map(|(c, _)| c.clone()).collect();
        let Some(i) = choose(&cands)? else { return Ok(None) };
        let (c, service) = &listed[i];
        let name = format!("{} ({})", c.product.as_deref().unwrap_or("?"), TRANSPORT);
        unsafe {
            let dev = IOHIDDeviceCreate(kCFAllocatorDefault, service.0);
            if dev.is_null() {
                return Err(format!("{name}: IOHIDDeviceCreate returned NULL"));
            }
            let rc = IOHIDDeviceOpen(dev, kIOHIDOptionsTypeNone);
            if rc != kIOReturnSuccess {
                CFRelease(dev as CFTypeRef);
                return Err(format!("{name}: open: {}", ioreturn_name(rc)));
            }
            let mut hid: io_connect_t = 0;
            let kr = match hid_system() {
                Some(sys) => IOServiceOpen(sys.0, mach_task_self_, kIOHIDParamConnectType, &mut hid),
                None => -1,
            };
            if kr != 0 {
                IOHIDDeviceClose(dev, kIOHIDOptionsTypeNone);
                CFRelease(dev as CFTypeRef);
                return Err(format!("the HID system's connection: {}", ioreturn_name(kr)));
            }
            let rl = CFRunLoopGetCurrent();
            IOHIDDeviceScheduleWithRunLoop(dev, rl, kCFRunLoopDefaultMode);
            Ok(Some(BleLights {
                dev,
                rl,
                hid,
                done: Box::new(Done(Cell::new(None))),
                buf: Box::new([REPORT_ID, 0]),
                poisoned: false,
                name,
                slowest: Duration::ZERO,
                over_100ms: 0,
            }))
        }
    }
}

impl LockLights for BleLights {
    fn profile(&self) -> Profile {
        Profile::P3
    }
    /// Zero: a write returns at its completion, and the Mac's BLE takes tens
    /// of milliseconds a write.
    fn spacing(&self) -> Duration {
        Duration::ZERO
    }
    fn data_gap(&self) -> Duration {
        DATA_GAP
    }
    /// Negative: the completion comes after the board has the anchor. The
    /// median of 39 frames through this writer (`ak820 lockchan anchor 40`,
    /// 10-21, `history/lockchan-clock-latency-mac-20261021/`): -13.9 ms,
    /// sd 2.7, p10 -15.8, p90 -11.5.
    fn clock_latency_ms(&self) -> Option<i32> {
        Some(-14)
    }
    fn user(&mut self) -> Option<u8> {
        if !session_active() {
            return None;
        }
        let mut caps = false;
        let kr = unsafe { IOHIDGetModifierLockState(self.hid, kIOHIDCapsLockState, &mut caps) };
        (kr == 0).then(|| if caps { CAPS } else { 0 })
    }
    fn write(&mut self, leds: u8) -> Result<(), WriteError> {
        if self.poisoned {
            return Err(WriteError::Stuck);
        }
        // IOKit autoreleases into the calling thread's pool on every async
        // write (`cf::Pool`); the pool covers the wait for the completion.
        let _pool = Pool::new();
        self.buf[1] = leds;
        self.done.0.set(None);
        let rc = unsafe {
            IOHIDDeviceSetReportWithCallback(
                self.dev,
                kIOHIDReportTypeOutput,
                REPORT_ID as CFIndex,
                self.buf.as_ptr(),
                self.buf.len() as CFIndex,
                // ⚠️ Milliseconds, despite the type (IOHIDDevice.h; device.rs).
                WRITE_TIMEOUT.as_secs_f64() * 1000.0,
                Some(on_written),
                &*self.done as *const Done as *mut c_void,
            )
        };
        if rc != kIOReturnSuccess {
            return Err(WriteError::Failed(format!("{}: write: {}", self.name, ioreturn_name(rc))));
        }
        let t0 = Instant::now();
        let deadline = t0 + WRITE_TIMEOUT + WRITE_GRACE;
        loop {
            if let Some(result) = self.done.0.get() {
                let took = t0.elapsed();
                self.slowest = self.slowest.max(took);
                self.over_100ms += (took > Duration::from_millis(100)) as u32;
                return if result == kIOReturnSuccess {
                    Ok(())
                } else {
                    Err(WriteError::Failed(format!("{}: write: {}", self.name, ioreturn_name(result))))
                };
            }
            let now = Instant::now();
            if now >= deadline {
                self.poisoned = true;
                return Err(WriteError::Stuck);
            }
            let wait = (deadline - now).min(Duration::from_millis(50));
            unsafe { CFRunLoopRunInMode(kCFRunLoopDefaultMode, wait.as_secs_f64(), 1) };
        }
    }
}

impl Drop for BleLights {
    fn drop(&mut self) {
        if self.poisoned {
            // A write IOKit never retired may still use the buffer, the
            // completion slot and the device: leak all three (R3-3).
            std::mem::forget(std::mem::replace(&mut self.done, Box::new(Done(Cell::new(None)))));
            std::mem::forget(std::mem::replace(&mut self.buf, Box::new([0; 2])));
            return;
        }
        unsafe {
            IOHIDDeviceUnscheduleFromRunLoop(self.dev, self.rl, kCFRunLoopDefaultMode);
            IOHIDDeviceClose(self.dev, kIOHIDOptionsTypeNone);
            CFRelease(self.dev as CFTypeRef);
            IOServiceClose(self.hid);
        }
    }
}

/// The sender's platform on macOS.
pub struct Mac {
    start: Instant,
    last: Cell<Option<u32>>,
}

impl Mac {
    pub fn new() -> Mac {
        Mac { start: Instant::now(), last: Cell::new(None) }
    }
}

/// The same as [`Mac::new`]: a `start` left unset would have switched the wake
/// guess off for good (codex, the macOS writer's review, P2 2).
impl Default for Mac {
    fn default() -> Mac {
        Mac::new()
    }
}

/// Now and the idle time as the sender's u32 millisecond ticks, both modulo
/// 2^32: the idle time wraps as the clock does, so a long idle never moves
/// the last input's tick (codex, P3 4: a saturated idle did, after ~49.7 days).
fn ticks(since_start: Duration, idle: Duration) -> (u32, u32) {
    (since_start.as_millis() as u32, idle.as_millis() as u32)
}

/// The last input's tick from "now" and the idle time: a jitter of a few ms
/// between reads is not an input (the sender fires on any change of it), so
/// an estimate within this of the last one keeps the last one.
const TICK_SLACK_MS: u32 = 250;

fn last_tick(prev: Option<u32>, now: u32, idle_ms: u32) -> u32 {
    let est = now.wrapping_sub(idle_ms);
    match prev {
        Some(p) if (est.wrapping_sub(p) as i32).unsigned_abs() <= TICK_SLACK_MS => p,
        _ => est,
    }
}

impl crate::lockchan::sender::Platform for Mac {
    type Lights = BleLights;
    fn open(&mut self) -> Result<Option<BleLights>, String> {
        BleLights::open()
    }
    fn lock(&mut self) -> Result<Option<Box<dyn std::any::Any + Send>>, String> {
        Ok(super::radio_lock::try_take_lockchan()?.map(|l| Box::new(l) as Box<dyn std::any::Any + Send>))
    }
    fn input(&self) -> Option<(u32, u32)> {
        let (now, idle) = ticks(self.start.elapsed(), idle()?);
        let last = last_tick(self.last.get(), now, idle);
        self.last.set(Some(last));
        Some((last, now))
    }

    /// The system clock at `at`: a wall sample bracketed by two monotonic
    /// ones, less the time from `at` to the bracket's middle. A bracket wider
    /// than 2 ms (the thread preempted between the reads) is taken again, at
    /// most four times (codex, type 4's implementation review, 5), as on
    /// Windows.
    fn wall_ms_at(&self, at: std::time::Instant) -> Option<i64> {
        use std::time::{Instant, SystemTime, UNIX_EPOCH};
        for _ in 0..4 {
            let i1 = Instant::now();
            let wall = SystemTime::now().duration_since(UNIX_EPOCH).ok()?;
            let i2 = Instant::now();
            let width = i2.saturating_duration_since(i1);
            if width.as_micros() > 2000 {
                continue;
            }
            let mid = i1 + width / 2;
            let since = mid.saturating_duration_since(at);
            return Some(wall.as_millis() as i64 - since.as_millis() as i64);
        }
        None
    }

    /// The USB clock's own `localtime_r`, so the zone and DST match it.
    fn local(&self, unix_s: i64) -> Option<crate::clock::host::LocalTime> {
        use crate::clock::host::Host;
        Some(super::host::SystemHost.local(unix_s))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_data_gap_leaves_50_ms_under_the_receivers_limit() {
        use crate::lockchan::frame::RECEIVER_GAP;
        assert!(DATA_GAP > crate::lockchan::frame::DATA_GAP);
        assert!(DATA_GAP + Duration::from_millis(50) <= RECEIVER_GAP);
    }

    fn cand(page: i64, usage: i64, transport: &str) -> Candidate {
        Candidate {
            usage_page: Some(page),
            usage: Some(usage),
            transport: Some(transport.into()),
            ..Default::default()
        }
    }

    #[test]
    fn only_the_ble_keyboard_collection_is_chosen() {
        let c = [cand(12, 1, TRANSPORT), cand(1, 6, TRANSPORT), cand(1, 2, TRANSPORT)];
        assert_eq!(choose(&c), Ok(Some(1)));
        assert_eq!(choose(&[cand(1, 6, "USB")]), Ok(None), "the cable's keyboard is raw HID's, not ours");
        assert_eq!(choose(&[]), Ok(None));
        assert!(choose(&[cand(1, 6, TRANSPORT), cand(1, 6, TRANSPORT)]).is_err(), "two: refuse to guess");
    }

    #[test]
    fn a_session_is_active_only_on_the_console_and_surely_unlocked() {
        use Flag::*;
        assert!(active(Is(true), Absent), "unlocked: the key is absent");
        assert!(active(Is(true), Is(false)));
        assert!(!active(Is(true), Is(true)), "locked");
        assert!(!active(Is(true), Malformed), "a lock flag of another type is not unlocked");
        assert!(!active(Is(false), Absent), "another user on the console");
        assert!(!active(Absent, Absent));
        assert!(!active(Malformed, Absent));
    }

    #[test]
    fn both_constructors_arm_the_wake_guess() {
        assert!(Mac::default().start.elapsed() < Duration::from_secs(5));
        assert!(Mac::new().last.get().is_none());
    }

    #[test]
    fn a_long_idle_wraps_with_the_clock_and_never_moves_the_last_input() {
        // 60 days without input: past u32's 49.7 days of milliseconds.
        let day = Duration::from_secs(86_400);
        let start_idle = 60 * day;
        let mut prev = None;
        let mut firsts = Vec::new();
        for step in 0..5u64 {
            let since = 60 * day + Duration::from_millis(step * 500);
            let idle = start_idle + Duration::from_millis(step * 500);
            let (now, idle_ms) = ticks(since, idle);
            let last = last_tick(prev, now, idle_ms);
            prev = Some(last);
            firsts.push(last);
        }
        assert!(firsts.windows(2).all(|w| w[0] == w[1]), "the last input's tick held: {firsts:?}");
    }

    #[test]
    fn idle_jitter_is_not_an_input_and_a_real_input_is() {
        // Idle 40 s at tick 100_000: last input at 60_000.
        let a = last_tick(None, 100_000, 40_000);
        assert_eq!(a, 60_000);
        // A read later, rounding a ms either way: the same last input.
        assert_eq!(last_tick(Some(a), 100_501, 40_500), a);
        assert_eq!(last_tick(Some(a), 100_502, 40_503), a);
        // A key: idle back near zero, the last input jumps forwards.
        assert_eq!(last_tick(Some(a), 101_000, 20), 100_980);
        // Across the tick's wrap.
        let w = last_tick(None, 10, 40_000);
        assert_eq!(w, 10u32.wrapping_sub(40_000));
        assert_eq!(last_tick(Some(w), 12, 40_001), w);
    }
}
