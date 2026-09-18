//! One persistent thread running a CFRunLoop, which every device borrows.
//!
//! The plan's second review (finding 7): IOKit delivers input reports only
//! through a run-loop or dispatch-queue callback, and a per-interaction open
//! happens ~28,800 times a day. A thread per open would be absurd; one thread
//! for the process lifetime is the design.
//!
//! ⚠️ **Scheduling and unscheduling run ON the loop thread**, through a
//! custom run-loop source, never from the calling thread. Report callbacks run
//! on the loop thread too, so once an unschedule job has returned, no callback
//! for that device can be mid-flight — which is what makes freeing its context
//! afterwards sound.

use std::collections::VecDeque;
use std::os::raw::c_void;
use std::sync::mpsc;
use std::sync::{Mutex, OnceLock};
use std::thread;

use crate::sys::*;

type Job = Box<dyn FnOnce() + Send>;

struct Shared {
    jobs: Mutex<VecDeque<Job>>,
}

/// Thread-safe handles to the loop. `CFRunLoopSourceSignal` and
/// `CFRunLoopWakeUp` are documented as callable from any thread.
pub struct RunLoop {
    rl: CFRunLoopRef,
    source: CFRunLoopSourceRef,
    shared: &'static Shared,
}

unsafe impl Send for RunLoop {}
unsafe impl Sync for RunLoop {}

unsafe extern "C" fn perform(info: *mut c_void) {
    let shared = &*(info as *const Shared);
    loop {
        let job = shared
            .jobs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .pop_front();
        match job {
            Some(job) => job(),
            None => break,
        }
    }
}

impl RunLoop {
    /// The process's loop, started on first use.
    pub fn get() -> &'static RunLoop {
        static LOOP: OnceLock<RunLoop> = OnceLock::new();
        LOOP.get_or_init(|| {
            let shared: &'static Shared = Box::leak(Box::new(Shared {
                jobs: Mutex::new(VecDeque::new()),
            }));
            let (tx, rx) = mpsc::channel::<(usize, usize)>();
            thread::Builder::new()
                .name("iokit-runloop".into())
                .spawn(move || unsafe {
                    let mut ctx = CFRunLoopSourceContext {
                        version: 0,
                        info: shared as *const Shared as *mut c_void,
                        retain: None,
                        release: None,
                        copy_description: None,
                        equal: None,
                        hash: None,
                        schedule: None,
                        cancel: None,
                        perform: Some(perform),
                    };
                    let source = CFRunLoopSourceCreate(kCFAllocatorDefault, 0, &mut ctx);
                    let rl = CFRunLoopGetCurrent();
                    CFRunLoopAddSource(rl, source, kCFRunLoopDefaultMode);
                    tx.send((rl as usize, source as usize))
                        .expect("loop handshake");
                    // The source keeps the loop alive for the process lifetime.
                    //
                    // Leak isolation: report and write-completion callbacks run
                    // on THIS thread, and a bare `CFRunLoopRun()` never drains
                    // an autorelease pool, so anything IOKit autoreleases while
                    // delivering accumulates for the life of the process. With
                    // `S2_LOOP_POOL=1` the loop instead runs one source at a
                    // time inside a pool of its own.
                    if std::env::var_os("S2_LOOP_POOL").is_some() {
                        loop {
                            let pool = objc_autoreleasePoolPush();
                            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 10.0, 1);
                            objc_autoreleasePoolPop(pool);
                        }
                    } else {
                        CFRunLoopRun();
                    }
                })
                .expect("spawning the run-loop thread");
            let (rl, source) = rx.recv().expect("loop handshake");
            RunLoop {
                rl: rl as CFRunLoopRef,
                source: source as CFRunLoopSourceRef,
                shared,
            }
        })
    }

    /// Run `f` on the loop thread and wait for its result.
    pub fn run<R: Send + 'static>(&self, f: impl FnOnce(CFRunLoopRef) -> R + Send + 'static) -> R {
        let (tx, rx) = mpsc::channel();
        let rl = self.rl as usize;
        self.shared
            .jobs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push_back(Box::new(move || {
                let _ = tx.send(f(rl as CFRunLoopRef));
            }));
        unsafe {
            CFRunLoopSourceSignal(self.source);
            CFRunLoopWakeUp(self.rl);
        }
        rx.recv()
            .expect("the run-loop thread outlives every caller")
    }
}
