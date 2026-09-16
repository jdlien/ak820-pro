//! Supervising the perl-hosted MediaRemote helper.
//!
//! The helper is `nowplaying-mediaremote.dylib` loaded into `/usr/bin/perl`,
//! because macOS 15.4 stopped answering MediaRemote for anything but an Apple
//! platform binary. It speaks line-JSON on stdout, reads commands on stdin, and
//! **exits when stdin closes**. The design is the sibling's
//! (`MediaRemoteHost.cs`), with the failure rule the plan's second review
//! settled (finding 3):
//!
//! - **Failed means 60 s without proof of life** — a `now`, `tick` or `command`
//!   line ([`Message::proves_liveness`]). Death and `fatal` do not trip it;
//!   they start that clock, and the restart happens inside it. The helper's
//!   six-timeout `fatal` + `exit(3)` is its *designed* recovery, and failing on
//!   it at once would clear the LCD and repaint it 2 s later.
//! - **A silent live helper is killed**, because the failure MediaRemote
//!   actually produces is a process that stays up and goes quiet. Killing it
//!   turns that into an exit, which is recoverable.
//! - ⚠️ **Silence is judged only once the pipe is drained.** A supervisor frozen
//!   by SIGSTOP (Phase 5a measures exactly that way) or descheduled on a busy
//!   machine wakes to a long gap and a pipe full of ticks. Judging on the clock
//!   alone would kill a healthy helper at every resume. So a kill needs the
//!   clock expired, `FIONREAD` reporting zero unread bytes, and no read
//!   completing during a short settle.
//! - Restart backoff doubles from 2 s to 30 s, and resets only after a run of
//!   2 min. The sibling doubles only on an exception; here any short run
//!   doubles, so a helper that dies at once cannot restart in a tight loop.
//!
//! The reader runs on **its own thread**, for the reason `smtc/worker.rs`
//! gives: nothing a media source does may stall the thread that syncs the
//! clock.

use std::ffi::OsString;
use std::io::{Read, Write};
use std::os::fd::{AsFd, AsRawFd, OwnedFd};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use crate::message::{self, Message};

pub const PERL: &str = "/usr/bin/perl";

/// The knobs, with the plan's values as defaults. Tests shrink them.
#[derive(Clone, Debug)]
pub struct Config {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    /// No proof of life for this long: the source has failed, and a live
    /// helper is killed.
    pub silence_limit: Duration,
    /// How often the watchdog looks.
    pub check_every: Duration,
    /// How long a read must stay absent before silence is believed.
    pub settle: Duration,
    pub restart_min: Duration,
    pub restart_max: Duration,
    /// A run at least this long resets the backoff.
    pub healthy_run: Duration,
    /// A line longer than this is dropped rather than buffered without bound.
    /// Artwork is the only large message, and it is never requested.
    pub max_line: usize,
}

impl Config {
    /// The real helper: the dylib at `dylib`, hosted by `/usr/bin/perl`.
    pub fn mediaremote(dylib: &Path) -> Config {
        // DynaLoader runs the constructor on load; 0x01 is RTLD_LAZY. The sleep
        // keeps perl alive: the constructor must return (dyld holds the loader
        // lock for the whole of an initializer), so perl blocks instead. The
        // loop is for signals, which end a sleep early.
        let quoted = dylib
            .to_string_lossy()
            .replace('\\', "\\\\")
            .replace('\'', "\\'");
        let loader = format!(
            "use DynaLoader; die \"load failed\\n\" unless DynaLoader::dl_load_file('{quoted}', 0x01); sleep 3600 while 1;"
        );
        Config {
            program: PERL.into(),
            args: vec!["-e".into(), loader.into()],
            ..Config::defaults()
        }
    }

    pub fn defaults() -> Config {
        Config {
            program: PathBuf::new(),
            args: Vec::new(),
            silence_limit: Duration::from_secs(60),
            check_every: Duration::from_secs(1),
            settle: Duration::from_millis(250),
            restart_min: Duration::from_secs(2),
            restart_max: Duration::from_secs(30),
            healthy_run: Duration::from_secs(120),
            max_line: 1 << 20,
        }
    }
}

/// Everything the supervisor has to say, in order, on one channel.
#[derive(Debug)]
pub enum Event {
    Started {
        pid: u32,
    },
    Message(Message),
    Unparseable {
        line: String,
        error: String,
    },
    TooLong {
        bytes: usize,
    },
    Stderr(String),
    /// The watchdog killed a live helper that had stopped proving liveness.
    KilledForSilence {
        pid: u32,
        silent_for: Duration,
    },
    Exited {
        pid: u32,
        code: Option<i32>,
        signal: Option<i32>,
        ran: Duration,
    },
    SpawnFailed(String),
    Restarting {
        after: Duration,
    },
}

/// The failure clock, readable from any thread without the channel.
#[derive(Debug, Default)]
pub struct Liveness {
    /// Nanoseconds after `epoch` of the last proof of life, across restarts.
    /// Zero means none yet; the clock then runs from `epoch`.
    last_proof_ns: AtomicU64,
}

pub struct Supervisor {
    stop: Arc<AtomicBool>,
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    liveness: Arc<Liveness>,
    epoch: Instant,
    silence_limit: Duration,
    thread: Option<JoinHandle<()>>,
}

impl Supervisor {
    pub fn start(config: Config, events: Sender<Event>) -> Supervisor {
        let stop = Arc::new(AtomicBool::new(false));
        let stdin = Arc::new(Mutex::new(None));
        let liveness = Arc::new(Liveness::default());
        let epoch = Instant::now();
        let silence_limit = config.silence_limit;
        let thread = {
            let (stop, stdin, liveness) =
                (Arc::clone(&stop), Arc::clone(&stdin), Arc::clone(&liveness));
            thread::Builder::new()
                .name("mediaremote-supervisor".into())
                .spawn(move || supervise(config, events, stop, stdin, liveness, epoch))
                .expect("spawning a thread")
        };
        Supervisor {
            stop,
            stdin,
            liveness,
            epoch,
            silence_limit,
            thread: Some(thread),
        }
    }

    /// Has the source failed? True once `silence_limit` has passed with no
    /// proof of life, whether the helper is dead, restarting, or alive and
    /// silent — and never merely because it died a moment ago.
    pub fn failed(&self) -> bool {
        self.silent_for() >= self.silence_limit
    }

    /// Time since the last proof of life (or since start, before the first).
    pub fn silent_for(&self) -> Duration {
        let ns = self.liveness.last_proof_ns.load(Ordering::Relaxed);
        self.epoch
            .elapsed()
            .saturating_sub(Duration::from_nanos(ns))
    }

    /// Send one command line. False when there is no helper to send it to.
    pub fn send(&self, command: &str) -> bool {
        let mut guard = self.stdin.lock().unwrap_or_else(|e| e.into_inner());
        match guard.as_mut() {
            Some(pipe) => pipe
                .write_all(format!("{command}\n").as_bytes())
                .and_then(|()| pipe.flush())
                .is_ok(),
            None => false,
        }
    }

    /// Close the helper's stdin — it exits on EOF — and stop restarting it.
    pub fn stop(mut self) {
        self.shutdown();
    }

    fn shutdown(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        self.stdin.lock().unwrap_or_else(|e| e.into_inner()).take();
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn nanos_since(epoch: Instant) -> u64 {
    // Never zero, so a proof at the very start is not mistaken for "none yet".
    (epoch.elapsed().as_nanos() as u64).max(1)
}

/// Sleep, waking early for `stop`.
fn nap(total: Duration, stop: &AtomicBool) {
    let until = Instant::now() + total;
    while !stop.load(Ordering::Relaxed) {
        let now = Instant::now();
        if now >= until {
            return;
        }
        thread::sleep((until - now).min(Duration::from_millis(50)));
    }
}

fn supervise(
    config: Config,
    events: Sender<Event>,
    stop: Arc<AtomicBool>,
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    liveness: Arc<Liveness>,
    epoch: Instant,
) {
    let mut delay = config.restart_min;
    while !stop.load(Ordering::Relaxed) {
        let started = Instant::now();
        run_once(&config, &events, &stop, &stdin, &liveness, epoch);
        if stop.load(Ordering::Relaxed) {
            return;
        }
        // 2, 4, 8, 16, 30, 30 ... across short runs; back to 2 after a healthy one.
        if started.elapsed() >= config.healthy_run {
            delay = config.restart_min;
        }
        let _ = events.send(Event::Restarting { after: delay });
        nap(delay, &stop);
        delay = (delay * 2).min(config.restart_max);
    }
}

/// `FIONREAD` on macOS: `_IOR('f', 127, int)`.
const FIONREAD: std::os::raw::c_ulong = 0x4004_667f;

extern "C" {
    fn ioctl(fd: std::os::raw::c_int, request: std::os::raw::c_ulong, ...) -> std::os::raw::c_int;
}

/// Bytes waiting in the pipe, or `None` if the kernel will not say.
fn unread_bytes(fd: &OwnedFd) -> Option<usize> {
    let mut n: std::os::raw::c_int = 0;
    let rc = unsafe { ioctl(fd.as_raw_fd(), FIONREAD, &mut n as *mut std::os::raw::c_int) };
    (rc == 0).then_some(n.max(0) as usize)
}

fn run_once(
    config: &Config,
    events: &Sender<Event>,
    stop: &AtomicBool,
    stdin_slot: &Mutex<Option<ChildStdin>>,
    liveness: &Arc<Liveness>,
    epoch: Instant,
) {
    let mut child: Child = match Command::new(&config.program)
        .args(&config.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            let _ = events.send(Event::SpawnFailed(format!(
                "{}: {e}",
                config.program.display()
            )));
            return;
        }
    };
    let pid = child.id();
    let started = Instant::now();
    let _ = events.send(Event::Started { pid });

    let stdout = child.stdout.take().expect("piped");
    let stderr = child.stderr.take().expect("piped");
    // The watchdog's own descriptor for the same pipe, so FIONREAD never races
    // the reader closing its copy at EOF.
    let probe = stdout.as_fd().try_clone_to_owned().ok();
    *stdin_slot.lock().unwrap_or_else(|e| e.into_inner()) = child.stdin.take();

    // Per-run proof clock, for the kill decision: a fresh helper gets a full
    // silence limit. The shared Liveness clock deliberately does NOT reset here.
    let run_proof_ns = Arc::new(AtomicU64::new(nanos_since(epoch)));
    let reads = Arc::new(AtomicU64::new(0));
    let reader = {
        let (events, liveness, run_proof_ns, reads) = (
            events.clone(),
            Arc::clone(liveness),
            Arc::clone(&run_proof_ns),
            Arc::clone(&reads),
        );
        let max_line = config.max_line;
        thread::Builder::new()
            .name("mediaremote-reader".into())
            .spawn(move || {
                read_lines(
                    stdout,
                    max_line,
                    &events,
                    &liveness,
                    &run_proof_ns,
                    &reads,
                    epoch,
                )
            })
            .expect("spawning a thread")
    };
    let stderr_reader = {
        let events = events.clone();
        thread::Builder::new()
            .name("mediaremote-stderr".into())
            .spawn(move || {
                let mut text = String::new();
                let _ = std::io::BufReader::new(stderr).read_to_string(&mut text);
                for line in text.lines().filter(|l| !l.trim().is_empty()) {
                    let _ = events.send(Event::Stderr(line.to_owned()));
                }
            })
            .expect("spawning a thread")
    };

    let mut killed = false;
    loop {
        if let Ok(Some(_)) = child.try_wait() {
            break;
        }
        if stop.load(Ordering::Relaxed) {
            // stdin is already closed by stop(); give the helper a moment to
            // leave on its own, then make sure.
            stdin_slot.lock().unwrap_or_else(|e| e.into_inner()).take();
            let deadline = Instant::now() + Duration::from_secs(2);
            while Instant::now() < deadline {
                if let Ok(Some(_)) = child.try_wait() {
                    break;
                }
                thread::sleep(Duration::from_millis(20));
            }
            let _ = child.kill();
            break;
        }
        thread::sleep(config.check_every);

        let silent = epoch
            .elapsed()
            .saturating_sub(Duration::from_nanos(run_proof_ns.load(Ordering::Relaxed)));
        if silent < config.silence_limit || killed {
            continue;
        }
        // The clock has expired. Believe it only with the pipe drained and no
        // read landing during the settle: see the module note.
        let drained = |fd: &Option<OwnedFd>| fd.as_ref().and_then(unread_bytes) == Some(0);
        if !drained(&probe) {
            continue;
        }
        let before = reads.load(Ordering::Relaxed);
        thread::sleep(config.settle);
        let silent = epoch
            .elapsed()
            .saturating_sub(Duration::from_nanos(run_proof_ns.load(Ordering::Relaxed)));
        if reads.load(Ordering::Relaxed) != before
            || !drained(&probe)
            || silent < config.silence_limit
        {
            continue;
        }
        let _ = events.send(Event::KilledForSilence {
            pid,
            silent_for: silent,
        });
        let _ = child.kill();
        killed = true;
    }

    stdin_slot.lock().unwrap_or_else(|e| e.into_inner()).take();
    let status = child.wait().ok();
    let _ = reader.join();
    let _ = stderr_reader.join();
    let _ = events.send(Event::Exited {
        pid,
        code: status.and_then(|s| s.code()),
        signal: status.and_then(|s| s.signal()),
        ran: started.elapsed(),
    });
}

fn read_lines(
    mut stdout: std::process::ChildStdout,
    max_line: usize,
    events: &Sender<Event>,
    liveness: &Liveness,
    run_proof_ns: &AtomicU64,
    reads: &AtomicU64,
    epoch: Instant,
) {
    let mut buf = Vec::with_capacity(8192);
    let mut chunk = [0u8; 8192];
    let mut discarding = false;
    loop {
        let n = match stdout.read(&mut chunk) {
            Ok(0) | Err(_) => return,
            Ok(n) => n,
        };
        // First thing after the read returns: the watchdog's settle check
        // looks for exactly this.
        reads.fetch_add(1, Ordering::Relaxed);
        let mut rest = &chunk[..n];
        while let Some(nl) = rest.iter().position(|&b| b == b'\n') {
            if discarding {
                discarding = false;
            } else {
                buf.extend_from_slice(&rest[..nl]);
                deliver(&buf, events, liveness, run_proof_ns, epoch);
            }
            buf.clear();
            rest = &rest[nl + 1..];
        }
        if discarding {
            continue;
        }
        buf.extend_from_slice(rest);
        if buf.len() > max_line {
            let _ = events.send(Event::TooLong { bytes: buf.len() });
            buf.clear();
            discarding = true;
        }
    }
}

fn deliver(
    line: &[u8],
    events: &Sender<Event>,
    liveness: &Liveness,
    run_proof_ns: &AtomicU64,
    epoch: Instant,
) {
    let text = String::from_utf8_lossy(line);
    let text = text.trim_end_matches('\r');
    if text.trim().is_empty() {
        return;
    }
    match message::classify(text) {
        Ok(m) => {
            if m.proves_liveness() {
                let now = nanos_since(epoch);
                liveness.last_proof_ns.store(now, Ordering::Relaxed);
                run_proof_ns.store(now, Ordering::Relaxed);
            }
            let _ = events.send(Event::Message(m));
        }
        Err(e) => {
            let _ = events.send(Event::Unparseable {
                line: text.chars().take(200).collect(),
                error: e.to_string(),
            });
        }
    }
}
