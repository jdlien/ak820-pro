//! `s2` — spike S2: IOKit HID discovery and transport for the AK820 Pro.
//!
//!     s2 list                 every HID service with the board's VID/PID; opens nothing
//!     s2 info [--timing]      FC_INFO, printed exactly as `ak820ctl info` prints it
//!     s2 hold SECS [--seize]  open (non-seizing unless --seize) and hold, to test exclusivity
//!     s2 soak N [--gap-ms M]  N open-exchange-close cycles; RSS, Mach ports and CPU per cycle
//!     s2 poll SECS            ONE open held, an FC_INFO exchange every 250 ms: what a peer's seize does mid-use
//!
//! Read-only against the board: FC_INFO reads the flash id, and the soak's
//! exchange is the text channel's playback readout with state 0 — the exact
//! report the daemon sends every 3 s.
//!
//! ⚠️ **Do not reuse that choice.** Tens of thousands of playback readouts,
//! partly while the bash agent pushed state 1 for music that was playing, most
//! probably caused the 12 non-flash >= 25 ms stalls the board recorded that
//! afternoon (`plans/BACKLOG.md`): each flip is an LCD redraw. A soak must use
//! a RAM-only command (health page 1), and never run while anyone is typing.

mod cf;
mod device;
mod discovery;
mod runloop;
mod sys;

use std::time::{Duration, Instant};

use device::{Arrival, Device, Error, Sent, WIRE_LEN};
use discovery::Choice;

const SET_VALUE: u8 = 0x07;
const ID_UNHANDLED: u8 = 0xFF;

fn frame(channel: u8, command: u8, body: &[u8]) -> [u8; WIRE_LEN] {
    let mut f = [0u8; WIRE_LEN];
    f[1] = SET_VALUE;
    f[2] = channel;
    f[3] = command;
    f[4..4 + body.len()].copy_from_slice(body);
    f
}

/// Open the one raw-HID service, deciding from properties first.
fn find() -> Result<cf::Io, String> {
    let all = discovery::list()?;
    let candidates: Vec<_> = all.iter().map(|(c, _)| c.clone()).collect();
    match discovery::choose(&candidates) {
        Choice::One(id) => Ok(all
            .into_iter()
            .find(|(c, _)| c.registry_id == id)
            .expect("chosen from this list")
            .1),
        Choice::Absent => Err(
            "no AK820 Pro raw-HID interface (0C45:8009, usage 0xFF60/0x61) in the registry".into(),
        ),
        Choice::Ambiguous(ids) => Err(format!(
            "more than one raw-HID interface ({ids:?}); refusing to guess"
        )),
    }
}

/// Discard anything queued, then send and wait for the report that answers.
/// Returns the reply and every discarded report.
fn exchange(
    dev: &mut Device,
    request: &[u8; WIRE_LEN],
    echo_len: usize,
) -> Result<(Arrival, Vec<Arrival>, u64), String> {
    let mut discarded = Vec::new();
    while let Some(stale) = dev
        .read_report(Duration::from_millis(1))
        .map_err(|e| e.to_string())?
    {
        discarded.push(stale);
    }
    let t0 = unsafe { sys::mach_absolute_time() };
    match dev
        .write_report(request, Duration::from_millis(1000))
        .map_err(|e| e.to_string())?
    {
        Sent::Yes => {}
        Sent::TimedOut => return Err("write timed out".into()),
    }
    let deadline = Instant::now() + Duration::from_millis(2000);
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        let Some(a) = dev.read_report(left).map_err(|e| e.to_string())? else {
            return Err(format!(
                "no reply ({} other report(s) arrived)",
                discarded.len()
            ));
        };
        let r = &a.data[1..];
        let ours = a.data[0] == 0
            && r[1] == request[2]
            && r[2] == request[3]
            && (r[0] == SET_VALUE || r[0] == ID_UNHANDLED)
            && r[3..3 + echo_len] == request[4..4 + echo_len];
        if ours {
            if r[0] == ID_UNHANDLED {
                return Err("the firmware does not handle this command".into());
            }
            return Ok((a, discarded, t0));
        }
        discarded.push(a);
    }
}

fn ms(ticks: u64) -> f64 {
    ticks as f64 * sys::ns_per_tick() / 1e6
}

fn list() -> Result<(), String> {
    let all = discovery::list()?;
    let candidates: Vec<_> = all.iter().map(|(c, _)| c.clone()).collect();
    let chosen = discovery::choose(&candidates);
    println!(
        "{} HID service(s) with VID 0C45 PID 8009 (nothing opened):",
        candidates.len()
    );
    for c in &candidates {
        let mark = if chosen == Choice::One(c.registry_id) {
            "*"
        } else {
            " "
        };
        println!(
            "{mark} id {:#x}  usage {:#06x}/{:#04x}  max in {:?} out {:?}  location {}  {:?} over {:?}",
            c.registry_id,
            c.usage_page.unwrap_or(-1),
            c.usage.unwrap_or(-1),
            c.max_input,
            c.max_output,
            c.location_id.map(|l| format!("{l:#010x} ({l})")).unwrap_or("-".into()),
            c.product.as_deref().unwrap_or("?"),
            c.transport.as_deref().unwrap_or("?"),
        );
    }
    println!("choice: {chosen:?}");
    Ok(())
}

fn info(timing: bool) -> Result<(), String> {
    let service = find()?;
    let opened = Instant::now();
    let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
    dev.open(false).map_err(|e| e.to_string())?;
    let open_ms = opened.elapsed().as_secs_f64() * 1e3;
    // FC_INFO; retry FS_BUSY a few times, as ak820ctl's fcmd does.
    for _ in 0..8 {
        let (reply, discarded, t0) = exchange(&mut dev, &frame(0x11, 0x01, &[]), 0)?;
        let r = &reply.data[1..];
        if r[3] == 0x01 {
            continue; // FS_BUSY
        }
        if r[3] != 0x00 {
            return Err(format!("flash: status {:#04x}", r[3]));
        }
        let id = (r[4] as u32) << 16 | (r[5] as u32) << 8 | r[6] as u32;
        let base = (r[7] as u32) << 16 | (r[8] as u32) << 8 | r[9] as u32;
        println!("flash jedec id : 0x{id:06X}");
        println!("writable from  : 0x{base:06X} (below this needs unlock, stock assets never)");
        if timing {
            let t1 = unsafe { sys::mach_absolute_time() };
            let w = dev.last_write;
            eprintln!(
                "open {open_ms:.2} ms; discarded {} report(s)",
                discarded.len()
            );
            eprintln!(
                "write call->done {:.3} ms; write done->kernel report {:.3} ms; kernel->callback {:.3} ms; callback->reader {:.3} ms; rtt (t0..t1) {:.3} ms",
                ms(w.done_abs - w.call_abs),
                ms(reply.kernel_abs.saturating_sub(w.done_abs)),
                ms(reply.callback_abs.saturating_sub(reply.kernel_abs)),
                ms(t1.saturating_sub(reply.callback_abs)),
                ms(t1 - t0),
            );
        }
        return Ok(());
    }
    Err("flash: busy after 8 tries".into())
}

fn hold(secs: f64, seize: bool) -> Result<(), String> {
    let service = find()?;
    let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
    dev.open(seize).map_err(|e| e.to_string())?;
    println!(
        "holding the device open ({}) for {secs} s",
        if seize { "SEIZED" } else { "non-seizing" }
    );
    let until = Instant::now() + Duration::from_secs_f64(secs);
    let mut seen = 0;
    while Instant::now() < until {
        match dev.read_report(Duration::from_millis(200)) {
            Ok(Some(a)) => {
                seen += 1;
                println!("  report {:02X?}", &a.data[1..8]);
            }
            Ok(None) => {}
            Err(Error::Removed) => {
                println!("  removed");
                break;
            }
            Err(e) => return Err(e.to_string()),
        }
    }
    println!("released after seeing {seen} report(s) on the held handle");
    Ok(())
}

fn poll(secs: f64) -> Result<(), String> {
    let service = find()?;
    let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
    dev.open(false).map_err(|e| e.to_string())?;
    let start = Instant::now();
    let until = start + Duration::from_secs_f64(secs);
    while Instant::now() < until {
        let t = start.elapsed().as_secs_f64();
        match exchange(&mut dev, &frame(0x11, 0x01, &[]), 0) {
            Ok((_, d, _)) => println!("{t:6.2} ok (discarded {})", d.len()),
            Err(e) => println!("{t:6.2} ERR {e}"),
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Ok(())
}

fn resident_kb() -> u64 {
    let mut buf = [0u64; 64];
    unsafe { sys::proc_pid_rusage(sys::getpid(), 4, buf.as_mut_ptr() as *mut _) };
    // rusage_info_v4: 16-byte uuid, then user, sys, pkg_idle, intr, pageins, wired, resident, footprint
    buf[2 + 6] / 1024
}

/// `phys_footprint`: what the kernel charges us, and what Activity Monitor shows.
fn footprint_kb() -> u64 {
    let mut buf = [0u64; 64];
    unsafe { sys::proc_pid_rusage(sys::getpid(), 4, buf.as_mut_ptr() as *mut _) };
    buf[2 + 7] / 1024
}

/// An autorelease pool held for one cycle, or nothing at all when `on` is false.
struct Pool(*mut std::os::raw::c_void);
impl Pool {
    fn new(on: bool) -> Self {
        Pool(if on {
            unsafe { sys::objc_autoreleasePoolPush() }
        } else {
            std::ptr::null_mut()
        })
    }
}
impl Drop for Pool {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { sys::objc_autoreleasePoolPop(self.0) }
        }
    }
}

fn cpu_s() -> f64 {
    let mut buf = [0u64; 64];
    unsafe { sys::proc_pid_rusage(sys::getpid(), 4, buf.as_mut_ptr() as *mut _) };
    (buf[2] + buf[3]) as f64 * sys::ns_per_tick() / 1e9
}

fn mach_ports() -> u32 {
    unsafe {
        let (mut names, mut n, mut types, mut nt) =
            (std::ptr::null_mut(), 0u32, std::ptr::null_mut(), 0u32);
        if sys::mach_port_names(
            sys::mach_task_self_,
            &mut names,
            &mut n,
            &mut types,
            &mut nt,
        ) != 0
        {
            return 0;
        }
        sys::vm_deallocate(sys::mach_task_self_, names as usize, n as usize * 4);
        sys::vm_deallocate(sys::mach_task_self_, types as usize, nt as usize * 4);
        n
    }
}

fn soak(n: u32, gap: Duration) -> Result<(), String> {
    let service = find()?;
    // One object per board arrival; open/close per cycle (see device.rs for
    // the measured leak that forces this). Warm up once so one-time
    // allocations are not counted as growth.
    let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
    dev.open(false).map_err(|e| e.to_string())?;
    let _ = exchange(&mut dev, &frame(0x13, 0x01, &[]), 0);
    dev.close();
    let (rss0, ports0, cpu0, t0) = (resident_kb(), mach_ports(), cpu_s(), Instant::now());
    println!("start: rss {rss0} KB, mach ports {ports0}");
    // ⚠️ Health page 1 (channel 0x13, GET): RAM only on the board. The old
    // choice, TEXT_PLAYBACK state 0, moves the LCD band and is what the
    // 2026-09-16 stall incident blamed (plans/BACKLOG.md).
    let request = frame(0x13, 0x01, &[]); // HC_GET page 1
    let (mut failures, mut discarded, mut worst_ms) = (0u32, 0usize, 0f64);
    // Per exchange: kernel timestamp -> reader wake (what userspace timing adds
    // over IOKit's own), and write done -> kernel reply (the board's turnaround).
    let (mut user_lag, mut board_turn, mut rtt) = (Vec::new(), Vec::new(), Vec::new());
    for i in 1..=n {
        let started = Instant::now();
        let result = dev.open(false).map_err(|e| e.to_string()).and_then(|()| {
            let got = exchange(&mut dev, &request, 0)?;
            let t1 = unsafe { sys::mach_absolute_time() };
            user_lag.push(ms(t1.saturating_sub(got.0.kernel_abs)));
            board_turn.push(ms(got.0.kernel_abs.saturating_sub(dev.last_write.done_abs)));
            rtt.push(ms(t1 - got.2));
            Ok(got)
        });
        dev.close();
        let took = started.elapsed().as_secs_f64() * 1e3;
        worst_ms = worst_ms.max(took);
        match result {
            Ok((_, d, _)) => discarded += d.len(),
            Err(e) => {
                failures += 1;
                if failures <= 5 {
                    println!("  cycle {i}: {e}");
                }
            }
        }
        if i % 1000 == 0 || i == n {
            let cpu = cpu_s() - cpu0;
            println!(
                "{i:>6}: rss {} KB ({:+}), mach ports {} ({:+}), cpu {:.3} ms/cycle, wall {:.2} ms/cycle, worst {worst_ms:.1} ms, failures {failures}, discarded {discarded}",
                resident_kb(),
                resident_kb() as i64 - rss0 as i64,
                mach_ports(),
                mach_ports() as i64 - ports0 as i64,
                cpu / i as f64 * 1e3,
                t0.elapsed().as_secs_f64() * 1e3 / i as f64,
            );
        }
        if !gap.is_zero() {
            std::thread::sleep(gap);
        }
    }
    for (name, v) in [
        ("kernel->reader (userspace lag)", &mut user_lag),
        ("write done->kernel reply", &mut board_turn),
        ("rtt t0..t1", &mut rtt),
    ] {
        v.sort_by(|a, b| a.total_cmp(b));
        if let (Some(first), Some(last)) = (v.first(), v.last()) {
            let q = |f: f64| v[((v.len() - 1) as f64 * f) as usize];
            println!(
                "{name}: min {first:.3}  p50 {:.3}  p95 {:.3}  p99 {:.3}  max {last:.3} ms (n={})",
                q(0.5),
                q(0.95),
                q(0.99),
                v.len()
            );
        }
    }
    Ok(())
}

unsafe extern "C" fn noop_report(
    _: *mut std::os::raw::c_void,
    _: sys::IOReturn,
    _: *mut std::os::raw::c_void,
    _: sys::IOHIDReportType,
    _: u32,
    _: *mut u8,
    _: sys::CFIndex,
    _: u64,
) {
}
unsafe extern "C" fn noop_old(
    _: *mut std::os::raw::c_void,
    _: sys::IOReturn,
    _: *mut std::os::raw::c_void,
    _: sys::IOHIDReportType,
    _: u32,
    _: *mut u8,
    _: sys::CFIndex,
) {
}
unsafe extern "C" fn noop_removal(
    _: *mut std::os::raw::c_void,
    _: sys::IOReturn,
    _: *mut std::os::raw::c_void,
) {
}

/// Leak isolation: which step of a cycle grows RSS.
fn isolate(what: &str, n: u32, passes: u32) -> Result<(), String> {
    // "create+pool" is "create" with an autorelease pool held for each cycle.
    let pooled = what.ends_with("+pool");
    let what = what.strip_suffix("+pool").unwrap_or(what);
    let service = find()?;
    let rss0 = resident_kb();
    let foot0 = footprint_kb();
    let request = frame(0x13, 0x01, &[]); // HC_GET page 1: RAM only, see soak()
    // Pass 2 tells a leak from allocator retention: freed-but-held pages are
    // reused by the next pass, a leak is not.
    for pass in 1..=passes {
        let (rss_a, foot_a) = (resident_kb(), footprint_kb());
        match what {
            // the IORegistry enumeration `open_board` runs before every open
            "list" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    let _ = discovery::list()?;
                }
            }
            // create + release only, never opened
            "create" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // create + open + close + release, no callbacks, no run loop
            "open-bare" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // the full Device open/drop (callbacks + schedule/unschedule), no exchange
            "open" => {
                let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    dev.open(false).map_err(|e| e.to_string())?;
                    dev.close();
                }
            }
            // one open, n exchanges
            "exchange" => {
                let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
                dev.open(false).map_err(|e| e.to_string())?;
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    let _ = exchange(&mut dev, &request, 0);
                }
            }
            // schedule + unschedule on the loop thread, no callbacks
            "sched" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        let p = d as usize;
                        runloop::RunLoop::get().run(move |rl| {
                            sys::IOHIDDeviceScheduleWithRunLoop(p as _, rl, sys::kCFRunLoopDefaultMode)
                        });
                        runloop::RunLoop::get().run(move |rl| {
                            sys::IOHIDDeviceUnscheduleFromRunLoop(
                                p as _,
                                rl,
                                sys::kCFRunLoopDefaultMode,
                            )
                        });
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // input-report callback registered and unregistered, never scheduled
            "cb" => {
                let mut buf = [0u8; 256];
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                            d,
                            buf.as_mut_ptr(),
                            256,
                            Some(noop_report),
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                            d,
                            std::ptr::null_mut(),
                            0,
                            None,
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // timestamped callback registered, closed WITHOUT unregistering
            "cb-noun" => {
                let mut buf = [0u8; 256];
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                            d,
                            buf.as_mut_ptr(),
                            256,
                            Some(noop_report),
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // the older, un-timestamped callback API
            "cb-old" => {
                let mut buf = [0u8; 256];
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceRegisterInputReportCallback(
                            d,
                            buf.as_mut_ptr(),
                            256,
                            Some(noop_old),
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceRegisterInputReportCallback(
                            d,
                            std::ptr::null_mut(),
                            0,
                            None,
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // the report buffer sized to the device's MaxInputReportSize (32), not 256
            "cb-32" => {
                let mut buf = [0u8; 32];
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                            d,
                            buf.as_mut_ptr(),
                            32,
                            Some(noop_report),
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                            d,
                            std::ptr::null_mut(),
                            0,
                            None,
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // ONE device object, callback registered and scheduled ONCE; open/close per cycle
            "cb-once" => {
                let mut buf = [0u8; 256];
                unsafe {
                    let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                    sys::IOHIDDeviceRegisterInputReportWithTimeStampCallback(
                        d,
                        buf.as_mut_ptr(),
                        256,
                        Some(noop_report),
                        std::ptr::null_mut(),
                    );
                    let p = d as usize;
                    runloop::RunLoop::get().run(move |rl| {
                        sys::IOHIDDeviceScheduleWithRunLoop(p as _, rl, sys::kCFRunLoopDefaultMode)
                    });
                    for _ in 0..n {
                        let _p = Pool::new(pooled);
                        let rc = sys::IOHIDDeviceOpen(d, 0);
                        assert_eq!(rc, 0, "open: {}", sys::ioreturn_name(rc));
                        sys::IOHIDDeviceClose(d, 0);
                    }
                    runloop::RunLoop::get().run(move |rl| {
                        sys::IOHIDDeviceUnscheduleFromRunLoop(p as _, rl, sys::kCFRunLoopDefaultMode)
                    });
                    sys::CFRelease(d as sys::CFTypeRef);
                }
            }
            // writes only through the async call, reads drained, on one open device
            "write-async" => {
                let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
                dev.open(false).map_err(|e| e.to_string())?;
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    let _ = dev.write_report(&request, Duration::from_millis(1000));
                    while let Ok(Some(_)) = dev.read_report(Duration::from_millis(20)) {}
                }
            }
            // the same with the synchronous IOHIDDeviceSetReport
            "write-sync" => {
                let mut dev = Device::create(&service).map_err(|e| e.to_string())?;
                dev.open(false).map_err(|e| e.to_string())?;
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe { dev.set_report_sync(&request) };
                    while let Ok(Some(_)) = dev.read_report(Duration::from_millis(20)) {}
                }
            }
            // removal callback only
            "removal" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    unsafe {
                        let d = sys::IOHIDDeviceCreate(sys::kCFAllocatorDefault, service.0);
                        sys::IOHIDDeviceOpen(d, 0);
                        sys::IOHIDDeviceRegisterRemovalCallback(
                            d,
                            Some(noop_removal),
                            std::ptr::null_mut(),
                        );
                        sys::IOHIDDeviceRegisterRemovalCallback(d, None, std::ptr::null_mut());
                        sys::IOHIDDeviceClose(d, 0);
                        sys::CFRelease(d as sys::CFTypeRef);
                    }
                }
            }
            // run-loop jobs only
            "runloop" => {
                for _ in 0..n {
                    let _p = Pool::new(pooled);
                    runloop::RunLoop::get().run(|_| ());
                }
            }
            other => return Err(format!("unknown step {other}")),
        }
        let (rss_b, foot_b) = (resident_kb(), footprint_kb());
        if passes > 1 {
            println!(
                "  pass {pass}: rss {:+} KB ({:+.3}/cycle), footprint {:+} KB ({:+.3}/cycle)",
                rss_b as i64 - rss_a as i64,
                (rss_b as f64 - rss_a as f64) / n as f64,
                foot_b as i64 - foot_a as i64,
                (foot_b as f64 - foot_a as f64) / n as f64,
            );
        }
    }
    let (rss1, foot1) = (resident_kb(), footprint_kb());
    println!(
        "{what:>10}{:<5} x{n}: rss {rss0} -> {rss1} KB ({:+.3} KB/cycle),          footprint {foot0} -> {foot1} KB ({:+.3} KB/cycle), mach ports {}",
        if pooled { "+pool" } else { "" },
        (rss1 as f64 - rss0 as f64) / n as f64,
        (foot1 as f64 - foot0 as f64) / n as f64,
        mach_ports()
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let a: Vec<&str> = args.iter().map(String::as_str).collect();
    let result = match a.as_slice() {
        ["list"] => list(),
        ["info"] => info(false),
        ["info", "--timing"] => info(true),
        ["hold", secs] => hold(secs.parse().expect("seconds"), false),
        ["hold", secs, "--seize"] => hold(secs.parse().expect("seconds"), true),
        ["isolate", what, n] => isolate(what, n.parse().expect("count"), 1),
        ["isolate", what, n, passes] => {
            isolate(what, n.parse().expect("count"), passes.parse().expect("passes"))
        }
        ["poll", secs] => poll(secs.parse().expect("seconds")),
        ["soak", n] => soak(n.parse().expect("count"), Duration::ZERO),
        ["soak", n, "--gap-ms", g] => soak(
            n.parse().expect("count"),
            Duration::from_millis(g.parse().expect("ms")),
        ),
        _ => Err(
            "usage: s2 list | info [--timing] | hold SECS [--seize] | soak N [--gap-ms M]".into(),
        ),
    };
    if let Err(e) = result {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
