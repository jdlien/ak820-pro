//! The lock-LED channel's sender: a thread of its own, fed by the daemon's
//! loop (`plans/LOCK-LED-CHANNEL-PLAN.md`, the sender design and R2-R4, and
//! codex's implementation review of 10-20).
//!
//! The loop calls [`Handle::set`] with the content each poll, [`Handle::grant`]
//! and [`Handle::revoke`] as the transports change, [`Handle::force`] for a
//! resend reason, and reads [`Handle::status`]. Everything that waits or
//! writes happens on the thread, in [`Core::step`], which is synchronous and
//! tested on a fake clock: the thread is only its loop.
//!
//! Locks: the slot's mutex is never held across a write or a wait (R3-3); the
//! machine-wide owner lock is taken on a grant and held through frames,
//! restores and `restore_pending`, released only with nothing outstanding, and
//! **kept for the life of the process if a write or an open is stuck**.
//!
//! Only the platform value moves to the thread: the lights are opened there
//! and never leave it (the Mac's device is scheduled on the opening thread's
//! run loop), so `LockLights` need not be `Send`.

use std::any::Any;
use std::cell::Cell;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use super::clock::{self as clk, ClockSched};
use super::frame::{self, Abort, Control, Late, Line, LockLights, Outcome, Payload, Time, Why};
use super::policy::{Content, Policy};
use crate::clock::host::LocalTime;

/// Past this without a fresh observation the content becomes CLEAR (R3-7).
pub const STALE_AFTER: Duration = Duration::from_secs(30);
/// The handover's wait after the daemon's last raw-HID media request (R4-2).
pub const HANDOVER: Duration = Duration::from_secs(12);
/// Absent keyboard: the list is read again this often (R3-8).
pub const RELIST: Duration = Duration::from_secs(10);
/// The wake guess: armed past this much input idleness (R3-8, R4).
pub const IDLE_ARM: Duration = Duration::from_secs(30);
/// The wake guess's resend waits this long after the input that fired it.
/// That input is often a media key, and the player takes a few seconds to
/// show its new state in SMTC or MediaRemote: resent at once, the frame
/// carried the old icon over the board's correct guess, wrong until the
/// real change went (JD's test, 10-20; the Mac session's diagnosis).
pub const WAKE_DELAY: Duration = Duration::from_secs(4);
/// No text or transport frame past this much input idleness. A frame into a
/// sleeping board is lost and costs its module's radio ~10 mA for ~10 s (the
/// mainline soak's hour, 10-21). Lights out sleeps at 60 s, the shortest
/// rung, and a frame lasts up to 12 s (the board's lifetime): with the
/// board's keys as the last input, one begun before this ends before the
/// board can sleep. A heuristic, not a bound: the host's last input can be
/// the trackpad's, newer than the board's (codex, the hold's review, 3). At
/// least [`IDLE_ARM`], so the wake guess is armed while anything is held and
/// its fire sends it. The board shows the last title until its 3 min
/// expiry, so a desk left alone keeps it for a while.
pub const HOLD_IDLE: Duration = Duration::from_secs(45);
/// How often a pending restore is tried, and the wake guess and the locks'
/// validity are sampled while the channel is granted.
pub const TICK: Duration = Duration::from_secs(1);

/// What the thread needs from the platform, beyond the lights themselves.
pub trait Platform {
    type Lights: LockLights;
    /// The board's keyboard: `Ok(None)` when not listed.
    fn open(&mut self) -> Result<Option<Self::Lights>, String>;
    /// An open left an operation the kernel still owns (a stuck query): the
    /// channel is poisoned for the life of the process, its lock kept
    /// (implementation review, 6). Default: never.
    fn poisoned(&self) -> bool {
        false
    }
    /// The machine-wide owner lock: `Ok(None)` when another process holds it.
    fn lock(&mut self) -> Result<Option<Box<dyn Any + Send>>, String>;
    /// The last input's tick (`GetLastInputInfo`), and the tick now, if knowable.
    fn input(&self) -> Option<(u32, u32)>;
    /// The wall clock, Unix ms, at a monotonic instant: the clock frame's
    /// time is taken at the anchor's completion, not at whenever the builder
    /// runs (codex, the wireless clock's review, 10). `None`: no clock frames.
    fn wall_ms_at(&self, _at: Instant) -> Option<i64> {
        None
    }
    /// The host's local time for a Unix second, through the USB clock's own
    /// conversion, so the zone and DST match it. `None`: no clock frames.
    fn local(&self, _unix_s: i64) -> Option<LocalTime> {
        None
    }
}

/// The loop's side of the slot.
#[derive(Debug, Default, Clone)]
pub struct Status {
    pub state: &'static str,
    pub frames: u64,
    pub failures: u64,
    /// Frames lost to chance and retried at once (a deadline, a lock change).
    pub retries: u64,
    pub last_sent: Option<Instant>,
    pub last_error: Option<String>,
    /// Lines for the daemon's log, one per change frame sent (not refreshes
    /// or repeats), drained by [`Handle::take_log`].
    pub log: Vec<String>,
    pub restore_pending: bool,
    pub writes: u64,
    /// Clock frames (type 4) sent whole, and the last one's completion.
    pub clock_frames: u64,
    pub clock_last: Option<Instant>,
    /// Why no clock frames go, when the daemon owns the clock but none can.
    pub clock_off: Option<&'static str>,
}

/// What the panel should show, as the loop sees it each poll: the text frame
/// (type 1 or 2, its icon included), the icon on its own, and the playback
/// readout while playing (`lockchan::Playback::of`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Media {
    pub text: Content,
    pub icon: crate::text::Icon,
    pub pb: Option<super::Playback>,
}

impl Media {
    /// From a snapshot, as the daemon's loop builds it.
    pub fn of(snapshot: &crate::smtc::Snapshot) -> Media {
        Media { text: super::content(snapshot), icon: snapshot.icon, pb: super::Playback::of(snapshot) }
    }
}

#[derive(Default)]
struct Slot {
    media: Option<Media>,
    /// Bumped on every different text identity (the lines) and transport
    /// identity (icon, playing, duration): each frame's own generation check,
    /// so A, B, A is two changes, not none (implementation review, 10).
    text_epoch: u64,
    tr_epoch: u64,
    observed: Option<Instant>,
    /// When the media's position was true (codex, play times, P2-2): apart
    /// from `observed`, the staleness clock.
    pos_at: Option<Instant>,
    granted: bool,
    owner_gen: u64,
    force: bool,
    not_before: Option<Instant>,
    /// The daemon owns the clock (`--clock`): clock frames go while granted.
    clock_on: bool,
    /// This process's last USB clock sync: the board refuses a clock frame
    /// for ten minutes after it (the schedule's first frame waits it out).
    usb_clock_last: Option<Instant>,
    stop: bool,
    done: bool,
    status: Status,
}

struct Shared {
    slot: Mutex<Slot>,
    cv: Condvar,
}

/// The daemon loop's handle on the sender.
#[derive(Clone)]
pub struct Handle(Arc<Shared>);

impl Handle {
    pub fn new() -> Handle {
        Handle(Arc::new(Shared { slot: Mutex::new(Slot::default()), cv: Condvar::new() }))
    }

    fn with<R>(&self, f: impl FnOnce(&mut Slot) -> R) -> R {
        let mut s = self.0.slot.lock().unwrap_or_else(|e| e.into_inner());
        let r = f(&mut s);
        self.0.cv.notify_all();
        r
    }

    /// The media now, when the source last observed it, and when its
    /// position was true.
    pub fn set(&self, media: Media, observed: Instant, pos_at: Instant) {
        self.with(|s| {
            let (t, r) = (text_id(&media.text), tr_id(&media));
            match &s.media {
                Some(old) => {
                    if text_id(&old.text) != t {
                        s.text_epoch += 1;
                    }
                    if tr_id(old) != r {
                        s.tr_epoch += 1;
                    }
                }
                None => {
                    s.text_epoch += 1;
                    s.tr_epoch += 1;
                }
            }
            s.media = Some(media);
            s.observed = Some(observed);
            s.pos_at = Some(pos_at);
        });
    }

    /// The channel may send: USB is absent and the radio is not carrying.
    /// `raw_media_last` is the daemon's last raw-HID media completion, if
    /// any; with none in this process (startup), the full wait (R4-2).
    pub fn grant(&self, raw_media_last: Option<Instant>, now: Instant) {
        self.with(|s| {
            if !s.granted {
                s.granted = true;
                s.owner_gen += 1;
                s.force = true;
                s.not_before = Some(raw_media_last.unwrap_or(now) + HANDOVER);
            }
        });
    }

    /// USB or the radio has it: stop between writes (R2-5).
    pub fn revoke(&self) {
        self.with(|s| {
            if s.granted {
                s.granted = false;
                s.owner_gen += 1;
            }
        });
    }

    pub fn force(&self) {
        self.with(|s| s.force = true);
    }

    /// The daemon owns the clock: send clock frames (type 4) while granted.
    pub fn set_clock(&self, on: bool) {
        self.with(|s| s.clock_on = on);
    }

    /// The daemon's clock synced the board over USB at `at`.
    pub fn usb_clock_synced(&self, at: Instant) {
        self.with(|s| s.usb_clock_last = Some(at));
    }

    pub fn stop(&self) {
        self.with(|s| s.stop = true);
    }

    /// Stop, and wait up to `budget` for the thread's one bounded restore and
    /// its exit (R3-3, R4-4); past it, the thread is left detached.
    pub fn stop_and_wait(&self, budget: Duration) -> bool {
        self.stop();
        let deadline = Instant::now() + budget;
        let mut s = self.0.slot.lock().unwrap_or_else(|e| e.into_inner());
        while !s.done {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return false;
            }
            s = self.0.cv.wait_timeout(s, left).unwrap_or_else(|e| e.into_inner()).0;
        }
        true
    }

    pub fn status(&self) -> Status {
        self.with(|s| s.status.clone())
    }

    pub fn granted(&self) -> bool {
        self.with(|s| s.granted)
    }

    /// The change frames sent since the last call, for the daemon's log.
    pub fn take_log(&self) -> Vec<String> {
        self.with(|s| std::mem::take(&mut s.status.log))
    }
}

impl Default for Handle {
    fn default() -> Self {
        Handle::new()
    }
}

/// The text frame's identity: its lines, never its icon (the icon rides in
/// type 3).
fn text_id(text: &Content) -> Content {
    super::text_identity(text.0, &text.1)
}

/// The transport's identity as policy content: icon, playing, duration.
fn tr_id(m: &Media) -> Content {
    let t = super::transport_identity(m.icon, m.pb);
    let mut v = vec![t.icon, t.playing as u8];
    v.extend_from_slice(&t.dur_s.to_be_bytes());
    (super::TYPE_TRANSPORT, v)
}

/// The readout's position at `at`, advanced from when it was true and
/// clamped to a known duration (codex, type-3 sender, 4).
fn pos_at_instant(pb: super::Playback, pos_at: Instant, at: Instant) -> u32 {
    let p = pb.pos_s.saturating_add(at.saturating_duration_since(pos_at).as_secs() as u32);
    if pb.dur_s > 0 { p.min(pb.dur_s) } else { p }
}

/// The transport policy's content: the identity, plus a seek revision, so a
/// seek is a change with its own repeat (codex, type-3 sender, 3).
fn tr_policy_id(m: &Media, seek_rev: u32) -> Content {
    let mut c = tr_id(m);
    c.1.extend_from_slice(&seek_rev.to_be_bytes());
    c
}

/// Whether the readout has jumped from what was picked (`pos` at `at`).
fn seeked(m: &Media, pos_at: Instant, picked: (u32, Instant), now: Instant) -> bool {
    m.pb.is_some_and(|pb| super::is_seek(picked.0, now.saturating_duration_since(picked.1), pos_at_instant(pb, pos_at, now), pb.dur_s))
}

/// What the slot asks for now: the media made idle (CLEAR, no readout) once
/// its observation is stale, and when that happens.
fn current_of(slot: &Slot, now: Instant) -> (Option<(Media, Instant)>, Option<Instant>) {
    let Some(m) = slot.media.clone() else { return (None, None) };
    let pos_at = slot.pos_at.unwrap_or(now);
    match slot.observed {
        Some(o) if now.saturating_duration_since(o) < STALE_AFTER => (Some((m, pos_at)), Some(o + STALE_AFTER)),
        _ => (
            Some((Media { text: (super::TYPE_CLEAR, Vec::new()), icon: crate::text::Icon::None, pb: None }, pos_at)),
            None,
        ),
    }
}

/// A change frame for the log: the title's lines, or the transport's icon and
/// readout.
fn describe(payload: &Content, m: &Media) -> String {
    let mmss = |s: u32| format!("{}:{:02}", s / 60, s % 60);
    match payload.0 {
        super::TYPE_CLEAR => "lockchan: sent clear".into(),
        super::TYPE_NOW_PLAYING if payload.1.len() >= 2 => {
            let n0 = payload.1[1] as usize;
            let l0 = String::from_utf8_lossy(&payload.1[2..2 + n0.min(payload.1.len() - 2)]);
            let l1 = String::from_utf8_lossy(&payload.1[(2 + n0).min(payload.1.len())..]);
            format!("lockchan: sent title {} - {}", l0, l1)
        }
        super::TYPE_TRANSPORT if payload.1.len() == 6 => {
            let pos = u16::from_be_bytes([payload.1[2], payload.1[3]]) as u32;
            let dur = u16::from_be_bytes([payload.1[4], payload.1[5]]) as u32;
            match m.pb {
                Some(_) => format!("lockchan: sent transport {} {}/{}", m.icon.name(), mmss(pos), mmss(dur)),
                None => format!("lockchan: sent transport {} (no readout)", m.icon.name()),
            }
        }
        k => format!("lockchan: sent type {k}"),
    }
}

/// Which frame a step sends.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Text,
    Transport,
    Clock,
}

/// What a frame picked, for its in-flight checks and its credit.
#[derive(Clone, Copy, Debug)]
struct Picked {
    gen: u64,
    text_epoch: u64,
    tr_epoch: u64,
    /// The picked identity, hashed (`Cell` wants `Copy`).
    id: u64,
    /// A transport's position, and when it was picked.
    pos: Option<u32>,
    at: Instant,
}

fn id_hash(c: &Content) -> u64 {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    c.hash(&mut h);
    h.finish()
}

/// The thread's state: everything [`Core::step`] carries between calls.
pub struct Core<P: Platform> {
    platform: P,
    lights: Option<P::Lights>,
    guard: Option<Box<dyn Any + Send>>,
    owner_seen: u64,
    /// Type 1/2: when the lines change, refresh every 60 s.
    text: Policy,
    /// Type 3: when the icon, playing or duration change, a seek, after
    /// every text frame (type 1 turns the board's playback off), refresh.
    tr: Policy,
    /// The text generation last sent whole: type 3 goes only while a title
    /// is shown (the Mac session: it cannot bring back an icon after a clear).
    text_sent: Option<u64>,
    /// The position the last type 3 picked (sent whole or not) and when, for
    /// the seek check: at every step and at every pick, so a seek during a
    /// transport's warm-up or one that cut it still earns its own revision
    /// and repeat (codex, type-3 verify, 1).
    sent_pos: Option<(u32, Instant)>,
    /// Bumped on every seek detected between frames.
    seek_rev: u32,
    /// The generation of each kind last logged: a change frame logs once.
    logged: [Option<u64>; 2],
    /// Type 4: when a clock frame is due.
    clock: ClockSched,
    /// The lights have no measured latency: no clock frames this process.
    clock_unmeasured: bool,
    line: Line,
    next_open: Option<Instant>,
    armed: Option<u32>,
    /// A text or transport frame was due and [`HOLD_IDLE`] held it: the wake
    /// guess's resend waits its delay.
    held: bool,
    locks_known: bool,
    poisoned: bool,
    seq: u8,
}

/// What the thread does after a step.
#[derive(Debug, PartialEq, Eq)]
pub enum Next {
    /// Sleep until this instant, or a change in the slot.
    WaitUntil(Instant),
    /// Sleep until the slot changes.
    Wait,
    /// The thread ends.
    Exit,
}

/// Whether the frame in flight is still wanted: the slot's stop, its owner
/// generation and its content epoch, read with the lock released before
/// anything else is asked.
struct Ctl<'a> {
    h: &'a Handle,
    owner: u64,
}

impl Ctl<'_> {
    /// Stop or ownership, and the slot's two epochs.
    fn check(&self) -> (Option<Abort>, u64, u64) {
        let s = self.h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
        let a = if s.stop {
            Some(Abort::Stop)
        } else if !(s.granted && s.owner_gen == self.owner) {
            Some(Abort::Revoked)
        } else {
            None
        };
        (a, s.text_epoch, s.tr_epoch)
    }
}

/// A restore needs no ownership: it only puts the user's lights back.
struct Always<'a>(&'a Handle);

impl Control for Always<'_> {
    fn abort(&self) -> Option<Abort> {
        let s = self.0 .0.slot.lock().unwrap_or_else(|e| e.into_inner());
        s.stop.then_some(Abort::Stop)
    }
}

impl<P: Platform> Core<P> {
    pub fn new(platform: P) -> Core<P> {
        Core {
            platform,
            lights: None,
            guard: None,
            owner_seen: 0,
            text: Policy::default(),
            tr: Policy::default(),
            text_sent: None,
            sent_pos: None,
            seek_rev: 0,
            logged: [None, None],
            clock: ClockSched::default(),
            clock_unmeasured: false,
            line: Line::default(),
            next_open: None,
            armed: None,
            held: false,
            locks_known: true,
            poisoned: false,
            seq: 0,
        }
    }


    /// The wake guess: armed after IDLE_ARM of input idleness, fired on any
    /// change of the last input's tick, forwards or backwards.
    fn wake_guess(&mut self, input: Option<(u32, u32)>) -> bool {
        let Some((last, now)) = input else { return false };
        match self.armed {
            Some(a) if a != last => {
                self.armed = None;
                true
            }
            Some(_) => false,
            None => {
                if Duration::from_millis(now.wrapping_sub(last) as u64) >= IDLE_ARM {
                    self.armed = Some(last);
                }
                false
            }
        }
    }

    /// Stuck: the kernel owns a buffer, and so does this process the device.
    fn poison(&mut self, h: &Handle) -> Next {
        self.poisoned = true;
        std::mem::forget(self.lights.take());
        std::mem::forget(self.guard.take());
        self.publish(h, |st| {
            st.state = "poisoned";
            st.failures += 1;
            st.last_error = Some("a write or an open is stuck: the channel is off until the daemon restarts".into());
        });
        Next::Exit
    }

    /// The lights, opened if they are not: `Err(next)` when the step must
    /// wait or exit instead.
    fn ensure_open(&mut self, h: &Handle, now: Instant, for_restore: bool) -> Result<(), Next> {
        if self.lights.is_some() {
            return Ok(());
        }
        if let Some(t) = self.next_open {
            if t > now {
                return Err(Next::WaitUntil(t));
            }
        }
        match self.platform.open() {
            Ok(Some(l)) => {
                self.lights = Some(l);
                self.next_open = None;
                Ok(())
            }
            Ok(None) => {
                self.publish(h, |st| st.state = "absent");
                self.next_open = Some(now + RELIST);
                Err(Next::WaitUntil(now + RELIST))
            }
            Err(e) => {
                if self.platform.poisoned() {
                    return Err(self.poison(h));
                }
                self.publish(h, |st| {
                    st.failures += 1;
                    st.last_error = Some(e);
                });
                // A restore keeps its own one-second schedule, never the
                // payload's backoff or handover (verify, 5).
                let t = if for_restore {
                    now + TICK
                } else {
                    self.text.failed(self.text.generation(), now);
                    self.text.due().unwrap_or(now + RELIST)
                };
                self.next_open = Some(t);
                Err(Next::WaitUntil(t))
            }
        }
    }

    /// One pass: update from the slot, service a pending restore, and send a
    /// frame if one is due: text first, then the transport.
    pub fn step<T: Time>(&mut self, h: &Handle, time: &T) -> Next {
        if self.poisoned {
            return Next::Exit;
        }
        let now = time.now();
        // One input snapshot for the pass: the wake guess and the clock's
        // idle gate see the same input (codex, the clock's verify, 2).
        let input = self.platform.input();
        let woke = self.wake_guess(input);
        let mut handover_end = None;
        let (granted, owner, stop, stale_at, view, clock_on, usb_clock_last, epochs) = {
            let mut s = h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
            let (view, stale_at) = current_of(&s, now);
            if let Some((m, _)) = &view {
                self.text.set(text_id(&m.text), now);
                self.tr.set(tr_policy_id(m, self.seek_rev), now);
            }
            if std::mem::take(&mut s.force) {
                self.text.force(now);
                self.tr.force(now);
            }
            if woke {
                self.text.force(now + WAKE_DELAY);
                self.tr.force(now + WAKE_DELAY);
                if std::mem::take(&mut self.held) {
                    // Overdue, so the force alone would send it at once,
                    // before a media key's change has shown (WAKE_DELAY).
                    self.text.not_before(now + WAKE_DELAY);
                    self.tr.not_before(now + WAKE_DELAY);
                }
            }
            if let Some(nb) = s.not_before.take() {
                self.text.not_before(nb);
                self.tr.not_before(nb);
                handover_end = Some(nb);
            }
            (s.granted, s.owner_gen, s.stop, stale_at, view, s.clock_on, s.usb_clock_last, (s.text_epoch, s.tr_epoch))
        };
        // A seek: the position is not where the last type 3 said it would be.
        // A change of its own, with the change's repeat (type-3 sender, 3).
        if let (Some((m, pos_at)), Some(sent)) = (&view, self.sent_pos) {
            if seeked(m, *pos_at, sent, now) {
                self.seek_rev = self.seek_rev.wrapping_add(1);
                self.tr.set(tr_policy_id(m, self.seek_rev), now);
                // The new position is the baseline now.
                self.sent_pos = m.pb.map(|pb| (pos_at_instant(pb, *pos_at, now), now));
            }
        }
        if stop {
            // One bounded restore if one is owed and the lights are open,
            // its waits through the stop flag (verify, 1).
            if self.line.restore_pending {
                if let Some(l) = self.lights.as_mut() {
                    if let Err(Outcome::Poisoned) = frame::restore_only(l, time, &Always(h), &mut self.line, true) {
                        return self.poison(h);
                    }
                }
            }
            self.release_all();
            return Next::Exit;
        }
        if granted && owner != self.owner_seen {
            // A new acquisition: the current content again, with its repeat
            // (implementation review, 11); the board's state is unknown.
            self.owner_seen = owner;
            self.text.acquired(now);
            self.tr.acquired(now);
            self.text_sent = None;
            self.sent_pos = None;
            if clock_on {
                self.clock.acquired(handover_end.unwrap_or(now), usb_clock_last);
            }
        }
        // After an acquisition in the same pass, so it cannot replace the
        // wake's delay (verify, 2).
        if woke && clock_on {
            self.clock.woke(now);
        }
        if !granted || !clock_on {
            self.clock.revoked();
        }
        if clock_on && granted {
            // An offset change (DST, a zone) or a wall-clock step: a clock
            // frame at once (review, 7).
            if let Some(w) = self.platform.wall_ms_at(now) {
                if let Some(l) = self.platform.local(w.div_euclid(1000)) {
                    self.clock.observe(now, w, clk::utc_offset_s(&l, w.div_euclid(1000)));
                }
            }
        }

        // The hold (HOLD_IDLE), noted before the returns below, so the wake
        // that ends it waits its delay whichever way the passes before it
        // went (codex, the hold's review, 1); any pass not idle clears it.
        let idle_for =
            |d: Duration| input.is_some_and(|(last, now)| Duration::from_millis(now.wrapping_sub(last) as u64) >= d);
        let hold = idle_for(HOLD_IDLE);
        self.held = hold && [self.text.due(), self.tr.due()].into_iter().flatten().any(|t| t <= now);

        // A pending restore goes first, granted or not, every TICK, until it
        // is confirmed (R3-1; implementation review, 1).
        if self.line.restore_pending {
            if let Err(next) = self.ensure_open(h, now, true) {
                return next;
            }
            let lights = self.lights.as_mut().expect("opened");
            match frame::restore_only(lights, time, &Always(h), &mut self.line, false) {
                Ok(true) => {}
                Ok(false) => {
                    self.publish_counts(h, "restore pending");
                    return Next::WaitUntil(time.now() + TICK);
                }
                Err(Outcome::Poisoned) => return self.poison(h),
                Err(Outcome::Abandoned(Why::Abort(Abort::Stop))) => {
                    // Stopped mid-restore: once more, through the flag.
                    let lights = self.lights.as_mut().expect("opened");
                    if let Err(Outcome::Poisoned) = frame::restore_only(lights, time, &Always(h), &mut self.line, true) {
                        return self.poison(h);
                    }
                    self.release_all();
                    return Next::Exit;
                }
                Err(_) => {
                    self.lights = None;
                    self.publish_counts(h, "restore pending");
                    return Next::WaitUntil(time.now() + TICK);
                }
            }
        }

        if !granted {
            self.release();
            self.publish_counts(h, "off");
            return Next::Wait;
        }

        // Granted: sample the wake guess, the locks' validity and staleness on
        // their own clocks, not only when a frame is due (review, 9).
        if let Some(l) = self.lights.as_mut() {
            if l.user().is_none() {
                self.locks_known = false;
                self.publish_counts(h, "locks unknown");
                return Next::WaitUntil(now + TICK);
            }
            if !self.locks_known {
                // Known again (an unlock, a reconnect): a resend reason.
                self.locks_known = true;
                self.text.force(now);
                self.tr.force(now);
            }
        }
        let wake_at = now + TICK;
        let stale_wait = stale_at.filter(|t| *t > now);
        let soonest = |due: Option<Instant>| {
            [due, Some(wake_at), stale_wait].into_iter().flatten().min().expect("wake_at is always there")
        };
        // Type 3 only while a title is shown: the current text generation sent
        // whole, and a now-playing one.
        let shown = view.as_ref().is_some_and(|(m, _)| m.text.0 == super::TYPE_NOW_PLAYING)
            && self.text_sent == Some(self.text.generation());
        // Neither while the input is idle (HOLD_IDLE): they go at the wake.
        let text_due = if hold { None } else { self.text.due() };
        let tr_due = if shown && !hold { self.tr.due() } else { None };
        // A clock frame after both (review, 11).
        // Held as they are (HOLD_IDLE), so one begun before it likely ends
        // before Lights out's sleep, a heuristic as there: it goes at the
        // wake (the Mac session, the hold).
        let clock_due = if clock_on && !self.clock_unmeasured && !hold { self.clock.due() } else { None };
        let kind = match (text_due, tr_due, clock_due) {
            (Some(t), _, _) if t <= now => Kind::Text,
            (_, Some(t), _) if t <= now => Kind::Transport,
            (_, _, Some(t)) if t <= now => Kind::Clock,
            _ => {
                let due = [text_due, tr_due, clock_due].into_iter().flatten().min();
                let state = if hold && self.held {
                    "held"
                } else if due.is_some() {
                    "waiting"
                } else {
                    "idle"
                };
                self.publish_counts(h, state);
                return Next::WaitUntil(soonest(due));
            }
        };
        if self.guard.is_none() {
            match self.platform.lock() {
                Ok(Some(g)) => self.guard = Some(g),
                Ok(None) => {
                    self.publish(h, |st| {
                        st.state = "lock held elsewhere";
                        st.last_error = Some("another process holds the lock-LED lock".into());
                    });
                    return Next::WaitUntil(now + RELIST);
                }
                Err(e) => {
                    self.publish(h, |st| {
                        st.failures += 1;
                        st.last_error = Some(e);
                    });
                    return Next::WaitUntil(now + RELIST);
                }
            }
        }
        if let Err(next) = self.ensure_open(h, now, false) {
            return next;
        }

        if self.lights.as_mut().expect("opened above").user().is_none() {
            self.locks_known = false;
            self.publish_counts(h, "locks unknown");
            return Next::WaitUntil(now + TICK);
        }
        if !self.locks_known {
            // Known again (an unlock, a reconnect): a resend reason (review, 9).
            self.locks_known = true;
            self.text.force(now);
            self.tr.force(now);
        }

        if kind == Kind::Clock {
            return self.send_clock(h, time, owner, epochs);
        }
        self.publish_counts(h, "sending");
        let seq = self.seq;
        // The newest media is picked after the warm-up and the quiet, and its
        // epochs and identity are what the frame then guards (R4-5; review,
        // 10; verify, 3). A transport frame is also cut by a text change.
        let picked: Cell<Option<Picked>> = Cell::new(None);
        let described: std::cell::RefCell<String> = std::cell::RefCell::new(String::new());
        let new_rev = Cell::new(self.seek_rev);
        let out = {
            struct Picking<'a, T: Time> {
                ctl: Ctl<'a>,
                kind: Kind,
                picked: &'a Cell<Option<Picked>>,
                time: &'a T,
            }
            impl<T: Time> Control for Picking<'_, T> {
                fn abort(&self) -> Option<Abort> {
                    let (a, te, re) = self.ctl.check();
                    if a.is_some() {
                        return a;
                    }
                    let Some(p) = self.picked.get() else { return None };
                    if te != p.text_epoch || (self.kind == Kind::Transport && re != p.tr_epoch) {
                        return Some(Abort::Superseded);
                    }
                    // Still fresh: an identity gone stale mid-frame is
                    // superseded by the idle that replaces it; a transport,
                    // by a seek after its pick too (type-3 sender, 3).
                    let s = self.ctl.h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
                    let now = self.time.now();
                    let view = current_of(&s, now).0;
                    let now_id = view.as_ref().map(|(m, _)| match self.kind {
                        Kind::Text => text_id(&m.text),
                        Kind::Transport | Kind::Clock => tr_id(m),
                    });
                    let seek = self.kind == Kind::Transport
                        && matches!((&view, p.pos), (Some((m, pos_at)), Some(pos)) if seeked(m, *pos_at, (pos, p.at), now));
                    (now_id.map(|c| id_hash(&c)) != Some(p.id) || seek).then_some(Abort::Superseded)
                }
            }
            let ctl = Picking { ctl: Ctl { h, owner }, kind, picked: &picked, time };
            let lights = self.lights.as_mut().expect("opened above");
            let (text, tr) = (&mut self.text, &mut self.tr);
            let (text_sent, last_pos) = (self.text_sent, self.sent_pos);
            let line = &mut self.line;
            frame::run(lights, time, &ctl, line, || {
                let at = time.now();
                let (view, te, re) = {
                    let s = h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
                    (current_of(&s, at).0, s.text_epoch, s.tr_epoch)
                };
                let (m, pos_at) = view?;
                let (gen, id, payload, pos) = match kind {
                    Kind::Clock => return None,
                    Kind::Text => {
                        let id = text_id(&m.text);
                        text.set(id.clone(), at);
                        (text.generation(), id, m.text.clone(), None)
                    }
                    Kind::Transport => {
                        // Still a title the board shows: the text sent whole
                        // is the current one (type-3 sender, 1).
                        text.set(text_id(&m.text), at);
                        if m.text.0 != super::TYPE_NOW_PLAYING || text_sent != Some(text.generation()) {
                            return None;
                        }
                        let id = tr_id(&m);
                        let pos = m.pb.map(|pb| pos_at_instant(pb, pos_at, at));
                        // A seek since the last pick: its own revision here
                        // too, not only at a step (type-3 verify, 1).
                        if let (Some(_), Some(last)) = (pos, last_pos) {
                            if seeked(&m, pos_at, last, at) {
                                new_rev.set(new_rev.get().wrapping_add(1));
                            }
                        }
                        tr.set(tr_policy_id(&m, new_rev.get()), at);
                        (tr.generation(), id, super::transport(m.icon, m.pb, pos.unwrap_or(0)), pos)
                    }
                };
                picked.set(Some(Picked { gen, text_epoch: te, tr_epoch: re, id: id_hash(&id), pos, at }));
                *described.borrow_mut() = describe(&payload, &m);
                Some(Payload { kind: payload.0, seq, bytes: payload.1 })
            })
        };
        let done = time.now();
        let p = picked.get();
        self.seek_rev = new_rev.get();
        if let Some(pp) = p {
            if let Some(pos) = pp.pos {
                self.sent_pos = Some((pos, pp.at));
            }
        }
        let policy = match kind {
            Kind::Text => &mut self.text,
            Kind::Transport | Kind::Clock => &mut self.tr,
        };
        let gen = p.map_or(policy.generation(), |p| p.gen);
        // Credited only if the owner, the epochs and the identity's freshness
        // are all still the frame's (verify, 4).
        let credited = p.is_some_and(|p| {
            let s = h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
            let view = current_of(&s, done).0;
            let id = view.as_ref().map(|(m, _)| match kind {
                Kind::Text => text_id(&m.text),
                Kind::Transport | Kind::Clock => tr_id(m),
            });
            let seek = kind == Kind::Transport
                && matches!((&view, p.pos), (Some((m, pos_at)), Some(pos)) if seeked(m, *pos_at, (pos, p.at), done));
            !seek
                && s.granted
                && s.owner_gen == owner
                && s.text_epoch == p.text_epoch
                && (kind == Kind::Text || s.tr_epoch == p.tr_epoch)
                && id.map(|c| id_hash(&c)) == Some(p.id)
        });
        match out {
            Outcome::Sent if credited => {
                self.seq = self.seq.wrapping_add(1);
                policy.sent(gen, done);
                match kind {
                    Kind::Text => {
                        self.text_sent = Some(gen);
                        // Type 1 turned the board's readout off: the
                        // transport goes right after (the Mac session).
                        self.tr.force(done);
                    }
                    Kind::Transport | Kind::Clock => {}
                }
                let slot = if kind == Kind::Text { 0 } else { 1 };
                let line = (self.logged[slot] != Some(gen)).then(|| described.borrow().clone());
                self.logged[slot] = Some(gen);
                self.publish(h, |st| {
                    st.frames += 1;
                    st.last_sent = Some(done);
                    if let Some(l) = line {
                        st.log.push(l);
                    }
                });
            }
            Outcome::Sent => {}
            Outcome::Unknown => {
                self.locks_known = false;
                self.publish_counts(h, "locks unknown");
                return Next::WaitUntil(done + TICK);
            }
            Outcome::Poisoned => return self.poison(h),
            Outcome::Abandoned(why) => match why {
                Why::Abort(Abort::Superseded) | Why::Abort(Abort::Revoked) => {}
                Why::Abort(Abort::Stop) => {
                    self.release_unless_pending();
                    self.publish_counts(h, "stopped");
                    return Next::Exit;
                }
                Why::Write(e) => {
                    // The handle may be bad: drop it; the next frame reopens.
                    self.lights = None;
                    policy.failed(gen, done);
                    self.publish(h, |st| {
                        st.failures += 1;
                        st.last_error = Some(e);
                    });
                }
                Why::Deadline | Why::UserChanged => {
                    policy.retry(gen, done);
                    self.publish(h, |st| st.retries += 1);
                }
                Why::RestorePending => {}
            },
        }
        self.publish_counts(h, "waiting");
        Next::WaitUntil(done)
    }

    /// A clock frame (type 4): the preamble, then the payload built from the
    /// anchor's completion (`frame::run_late`): the host's wall clock at that
    /// instant plus the lights' measured latency, in local time. Cut by the
    /// owner, a stop, or any change of the text or the transport (review, 11).
    fn send_clock<T: Time>(&mut self, h: &Handle, time: &T, owner: u64, epochs: (u64, u64)) -> Next {
        let now = time.now();
        let Some(latency) = self.lights.as_ref().and_then(|l| l.clock_latency_ms()) else {
            // Unmeasured lights: none for the life of the process (review, 6).
            self.clock_unmeasured = true;
            self.publish(h, |st| st.clock_off = Some("this platform's latency is not measured"));
            return Next::WaitUntil(now);
        };
        self.publish_counts(h, "sending clock");
        let seq = self.seq;
        // `epochs` are the pass's that chose the clock: a change of either
        // from then, while the lock is taken and the lights opened, in the
        // warm-up or after, cuts the frame (implementation review, 4; its
        // verify, 4).
        // The time taken (the anchor, the wall clock then, its offset): from
        // then a step or an offset change cuts the frame (implementation
        // review, 2).
        let taken: Cell<Option<(Instant, i64, i64)>> = Cell::new(None);
        let failed: Cell<Option<Duration>> = Cell::new(None);
        let described: std::cell::RefCell<String> = std::cell::RefCell::new(String::new());
        /// Whether the host's clock still runs on from what was taken.
        fn continuous<P: Platform>(p: &P, taken: (Instant, i64, i64), now: Instant) -> bool {
            let (at, w, off) = taken;
            let Some(wn) = p.wall_ms_at(now) else { return false };
            let expect = w + now.saturating_duration_since(at).as_millis() as i64;
            (wn - expect).abs() <= clk::STEP_SLACK_MS
                && p.local(wn.div_euclid(1000)).is_some_and(|l| clk::utc_offset_s(&l, wn.div_euclid(1000)) == off)
        }
        struct ClockCtl<'a, P: Platform, T: Time> {
            ctl: Ctl<'a>,
            epochs: (u64, u64),
            platform: &'a P,
            time: &'a T,
            taken: &'a Cell<Option<(Instant, i64, i64)>>,
        }
        impl<P: Platform, T: Time> Control for ClockCtl<'_, P, T> {
            fn abort(&self) -> Option<Abort> {
                let (a, te, re) = self.ctl.check();
                if a.is_some() {
                    return a;
                }
                if (te, re) != self.epochs {
                    return Some(Abort::Superseded);
                }
                match self.taken.get() {
                    Some(t) if !continuous(self.platform, t, self.time.now()) => Some(Abort::Superseded),
                    _ => None,
                }
            }
        }
        let platform = &self.platform;
        let ctl = ClockCtl { ctl: Ctl { h, owner }, epochs, platform, time, taken: &taken };
        let lights = self.lights.as_mut().expect("opened by the caller");
        let line = &mut self.line;
        let out = frame::run_late(lights, time, &ctl, line, || {
            let (taken, failed, described) = (&taken, &failed, &described);
            Some(Late {
                kind: super::TYPE_CLOCK,
                seq,
                build: Box::new(move |anchor: Instant| {
                    // Unreadable or unrepresentable: after the retry, not at
                    // once (implementation review, 6).
                    failed.set(Some(clk::RETRY));
                    let w0 = platform.wall_ms_at(anchor)?;
                    let w = w0 + latency as i64;
                    let ws = w.div_euclid(1000);
                    let l = platform.local(ws)?;
                    // No frame across an offset change: the board's civil
                    // arithmetic would land on the old offset (review, 7).
                    let span = clk::SPAN.as_secs() as i64;
                    let later = platform.local(ws + span)?;
                    if clk::utc_offset_s(&l, ws) != clk::utc_offset_s(&later, ws + span) {
                        failed.set(Some(clk::SPAN));
                        return None;
                    }
                    let ms = w.rem_euclid(1000) as u32;
                    let bytes = super::clock_payload(&l, ms)?;
                    failed.set(None);
                    // The baseline is the payload's own conversion: any later
                    // one that disagrees cuts the frame (verify, 1).
                    taken.set(Some((anchor, w0, clk::utc_offset_s(&l, ws))));
                    *described.borrow_mut() = format!(
                        "lockchan: sent clock {:04}-{:02}-{:02} {:02}:{:02}:{:02}.{:03} (latency {:+} ms)",
                        l.year, l.month, l.day, l.hour, l.minute, l.second, ms, latency
                    );
                    Some(bytes)
                }),
            })
        });
        let done = time.now();
        // Credited only with the owner the frame's, and the host's clock
        // continuous from the time it took to the end (implementation
        // review, 2): otherwise the board has a time the host no longer
        // keeps, and the next step sends the right one.
        let continuous_to_end = taken.get().is_some_and(|t| continuous(&self.platform, t, done));
        let credited = continuous_to_end && {
            let s = h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
            s.granted && s.owner_gen == owner
        };
        match out {
            Outcome::Sent if credited => {
                self.seq = self.seq.wrapping_add(1);
                self.clock.sent(done);
                // The clock the frame carried is the scheduler's reference
                // now: a step before its time was taken is not seen again as
                // a reason to resend. From the time it took, not a new
                // sample, which could hide a change after the last check
                // (codex, the clock's second verify, 1).
                if let Some((at, w0, off)) = taken.get() {
                    self.clock.rebase(at, w0, off);
                }
                let line = described.borrow().clone();
                self.publish(h, |st| {
                    st.clock_frames += 1;
                    st.clock_last = Some(done);
                    st.log.push(line);
                });
            }
            Outcome::Sent if !continuous_to_end => self.clock.again(done),
            Outcome::Sent => {}
            Outcome::Unknown => {
                self.locks_known = false;
                self.publish_counts(h, "locks unknown");
                return Next::WaitUntil(done + TICK);
            }
            Outcome::Poisoned => return self.poison(h),
            Outcome::Abandoned(why) => match why {
                Why::Abort(Abort::Superseded) => match failed.get() {
                    // The builder could not: an offset change near (after
                    // it, which observe() then sees), or no time to send.
                    Some(wait) => self.clock.later(done, wait),
                    // A media change or a clock discontinuity cut it: still
                    // due, after what cut it.
                    None => {}
                },
                Why::Abort(Abort::Revoked) | Why::RestorePending => {}
                Why::Abort(Abort::Stop) => {
                    self.release_unless_pending();
                    self.publish_counts(h, "stopped");
                    return Next::Exit;
                }
                Why::Write(e) => {
                    self.lights = None;
                    self.clock.later(done, clk::RETRY);
                    self.publish(h, |st| {
                        st.failures += 1;
                        st.last_error = Some(e);
                    });
                }
                Why::Deadline | Why::UserChanged => {
                    self.clock.again(done);
                    self.publish(h, |st| st.retries += 1);
                }
            },
        }
        self.publish_counts(h, "waiting");
        Next::WaitUntil(done)
    }

    fn release(&mut self) {
        if self.line.restore_pending {
            return; // the lights and the lock stay until the restore is done
        }
        self.release_all();
    }

    /// At exit: whatever is owed, the thread is ending.
    fn release_all(&mut self) {
        self.lights = None;
        self.guard = None;
    }

    fn release_unless_pending(&mut self) {
        self.release();
    }

    fn publish(&self, h: &Handle, f: impl FnOnce(&mut Status)) {
        let mut s = h.0.slot.lock().unwrap_or_else(|e| e.into_inner());
        f(&mut s.status);
        s.status.restore_pending = self.line.restore_pending;
        s.status.writes = self.line.writes;
    }

    fn publish_counts(&self, h: &Handle, state: &'static str) {
        self.publish(h, |st| st.state = state);
    }
}

/// Wall-clock time whose sleeps end early on a stop.
struct Wall<'a>(&'a Handle);

impl Time for Wall<'_> {
    fn now(&self) -> Instant {
        Instant::now()
    }
    fn sleep_until(&self, t: Instant) -> bool {
        let s = self.0 .0.slot.lock().unwrap_or_else(|e| e.into_inner());
        if s.stop {
            return false;
        }
        let wait = t.saturating_duration_since(Instant::now());
        let (s, _) = self.0 .0.cv.wait_timeout_while(s, wait, |s| !s.stop).unwrap_or_else(|e| e.into_inner());
        !s.stop
    }
    fn sleep_through(&self, t: Instant) {
        std::thread::sleep(t.saturating_duration_since(Instant::now()));
    }
}

/// Start the sender thread. Only `platform` moves to it.
pub fn spawn<P: Platform + Send + 'static>(platform: P) -> Result<Handle, String> {
    let h = Handle::new();
    let theirs = h.clone();
    std::thread::Builder::new()
        .name("ak820-lockchan".into())
        .spawn(move || {
            let mut core = Core::new(platform);
            let time = Wall(&theirs);
            loop {
                let next = core.step(&theirs, &time);
                let s = theirs.0.slot.lock().unwrap_or_else(|e| e.into_inner());
                // A stop that came between the step and this lock: step again
                // at once, which exits (codex, verify 2).
                if s.stop && next != Next::Exit {
                    continue;
                }
                match next {
                    Next::Exit => break,
                    Next::Wait => {
                        // Until something in the slot changes, or a minute.
                        let _ = theirs.0.cv.wait_timeout(s, Duration::from_secs(60));
                    }
                    Next::WaitUntil(t) => {
                        let wait = t.saturating_duration_since(Instant::now());
                        if !wait.is_zero() {
                            let _ = theirs.0.cv.wait_timeout(s, wait);
                        }
                    }
                }
            }
            theirs.with(|s| s.done = true);
        })
        .map_err(|e| format!("spawning the lock-LED thread: {e}"))?;
    Ok(h)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::lockchan::frame::WriteError;
    use crate::lockchan::Profile;
    use std::cell::RefCell;
    use std::rc::Rc;


    impl Handle {
        /// A text frame and no readout, its icon from the payload.
        fn set_text(&self, text: Content, observed: Instant) {
            let icon = match text.1.first() {
                Some(1) if text.0 == super::super::TYPE_NOW_PLAYING => crate::text::Icon::Play,
                Some(2) if text.0 == super::super::TYPE_NOW_PLAYING => crate::text::Icon::Pause,
                _ => crate::text::Icon::None,
            };
            self.set(Media { text, icon, pb: None }, observed, observed);
        }
    }

    struct FakeTime(Cell<Instant>);
    impl Time for FakeTime {
        fn now(&self) -> Instant {
            self.0.get()
        }
        fn sleep_until(&self, t: Instant) -> bool {
            if t > self.0.get() {
                self.0.set(t);
            }
            true
        }
        fn sleep_through(&self, t: Instant) {
            self.sleep_until(t);
        }
    }

    /// What the fake keyboard does, shared with the test.
    #[derive(Default)]
    struct Kb {
        writes: Vec<(Instant, u8)>,
        user: u8,
        unknown: bool,
        fail: bool,
        stuck: bool,
        /// Called after each write with its index: the test's hook to change
        /// the slot mid-frame.
        hook: Option<Box<dyn FnMut(usize)>>,
        /// Type 4: the lights' latency; the wall clock as (instant, Unix ms)
        /// at the rig's start; the local offset, and a change of it at a
        /// Unix second (DST).
        latency: Option<i32>,
        wall: Option<(Instant, i64)>,
        offset_s: i64,
        offset_change: Option<(i64, i64)>,
        /// `local` calls so far, and an offset that takes effect from a
        /// given call on (a zone change between two conversions).
        local_calls: usize,
        offset_from_call: Option<(usize, i64)>,
        /// Called at each open (a change while the lights are opened).
        open_hook: Option<Box<dyn FnMut()>>,
        /// A wall step that lands after this many more `wall_ms_at` calls.
        wall_step_after: Option<(usize, i64)>,
    }

    struct Lights {
        kb: Rc<RefCell<Kb>>,
        t: Rc<FakeTime>,
    }
    impl LockLights for Lights {
        fn profile(&self) -> Profile {
            Profile::P0
        }
        fn spacing(&self) -> Duration {
            Duration::from_millis(16)
        }
        fn clock_latency_ms(&self) -> Option<i32> {
            self.kb.borrow().latency
        }
        fn user(&mut self) -> Option<u8> {
            let k = self.kb.borrow();
            (!k.unknown).then_some(k.user)
        }
        fn write(&mut self, v: u8) -> Result<(), WriteError> {
            {
                let k = self.kb.borrow();
                if k.stuck {
                    return Err(WriteError::Stuck);
                }
                if k.fail {
                    self.t.0.set(self.t.0.get() + Duration::from_secs(1));
                    return Err(WriteError::Failed("gone".into()));
                }
            }
            self.t.0.set(self.t.0.get() + Duration::from_millis(1));
            let i = {
                let mut k = self.kb.borrow_mut();
                k.writes.push((self.t.0.get(), v));
                k.writes.len() - 1
            };
            let hook = self.kb.borrow_mut().hook.take();
            if let Some(mut f) = hook {
                f(i);
                self.kb.borrow_mut().hook = Some(f);
            }
            Ok(())
        }
    }

    struct Plat {
        kb: Rc<RefCell<Kb>>,
        t: Rc<FakeTime>,
        present: bool,
        opens: usize,
        open_stuck: bool,
        input: Rc<Cell<Option<(u32, u32)>>>,
    }
    unsafe impl Send for Plat {}
    impl Platform for Plat {
        type Lights = Lights;
        fn open(&mut self) -> Result<Option<Lights>, String> {
            self.opens += 1;
            let hook = self.kb.borrow_mut().open_hook.take();
            if let Some(mut f) = hook {
                f();
                self.kb.borrow_mut().open_hook = Some(f);
            }
            if self.open_stuck {
                return Err("query: Stuck".into());
            }
            Ok(self.present.then(|| Lights { kb: self.kb.clone(), t: self.t.clone() }))
        }
        fn poisoned(&self) -> bool {
            self.open_stuck
        }
        fn lock(&mut self) -> Result<Option<Box<dyn Any + Send>>, String> {
            Ok(Some(Box::new(())))
        }
        fn input(&self) -> Option<(u32, u32)> {
            self.input.get()
        }
        fn wall_ms_at(&self, at: Instant) -> Option<i64> {
            {
                let mut k = self.kb.borrow_mut();
                if let Some((n, d)) = k.wall_step_after {
                    if n == 0 {
                        let (t, w) = k.wall.unwrap();
                        k.wall = Some((t, w + d));
                        k.wall_step_after = None;
                    } else {
                        k.wall_step_after = Some((n - 1, d));
                    }
                }
            }
            let (t0, w0) = self.kb.borrow().wall?;
            Some(w0 + at.duration_since(t0).as_millis() as i64)
        }
        fn local(&self, unix_s: i64) -> Option<LocalTime> {
            let mut k = self.kb.borrow_mut();
            k.local_calls += 1;
            if let Some((n, o)) = k.offset_from_call {
                if k.local_calls >= n {
                    k.offset_s = o;
                    k.offset_from_call = None;
                }
            }
            let off = match k.offset_change {
                Some((at, o)) if unix_s >= at => o,
                _ => k.offset_s,
            };
            Some(crate::clock::host::utc_local(unix_s + off))
        }
    }

    struct Rig {
        core: Core<Plat>,
        h: Handle,
        t: Rc<FakeTime>,
        kb: Rc<RefCell<Kb>>,
        input: Rc<Cell<Option<(u32, u32)>>>,
    }

    fn rig() -> Rig {
        let t = Rc::new(FakeTime(Cell::new(Instant::now())));
        let kb = Rc::new(RefCell::new(Kb::default()));
        let input = Rc::new(Cell::new(None));
        let p = Plat { kb: kb.clone(), t: t.clone(), present: true, opens: 0, open_stuck: false, input: input.clone() };
        Rig { core: Core::new(p), h: Handle::new(), t, kb, input }
    }

    fn title(s: &str) -> Content {
        let mut p = vec![1u8, s.len() as u8];
        p.extend_from_slice(s.as_bytes());
        (super::super::TYPE_NOW_PLAYING, p)
    }

    /// Step until the core rests past `until`, advancing fake time.
    fn run_until(r: &mut Rig, until: Instant) -> Next {
        for _ in 0..10_000 {
            match r.core.step(&r.h, &*r.t) {
                Next::WaitUntil(w) if w <= until => {
                    r.t.sleep_until(w);
                }
                other => return other,
            }
        }
        panic!("no rest");
    }

    /// Decode what the board would have committed from the writes (the
    /// encoder's inverse is the receiver's job; here the last frame's bytes
    /// are matched against the encoder's output).
    fn sent(r: &Rig, c: &Content, user: u8) -> bool {
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|w| w.1).collect();
        (0..=255u8).any(|seq| {
            let e = crate::lockchan::encode(&c.1, c.0, seq, Profile::P0, user).unwrap();
            w.windows(e.len()).any(|x| x == &e[..])
        })
    }

    fn granted(r: &mut Rig, c: Content) -> Instant {
        let t0 = r.t.now();
        r.h.set_text(c, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        t0
    }

    #[test]
    fn nothing_goes_until_granted_then_after_the_handover_wait() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set_text(title("A"), t0);
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Wait);
        assert!(r.kb.borrow().writes.is_empty());
        r.h.grant(None, t0);
        assert!(matches!(r.core.step(&r.h, &*r.t), Next::WaitUntil(_)));
        assert!(r.kb.borrow().writes.is_empty(), "no history: the full 12 s wait");
        r.h.set_text(title("A"), t0 + HANDOVER);
        r.t.0.set(t0 + HANDOVER);
        run_until(&mut r, t0 + HANDOVER + Duration::from_secs(1));
        assert!(sent(&r, &title("A"), 0));
        assert_eq!(r.h.status().frames, 1);
        assert_eq!(r.h.status().state, "waiting", "not left at sending");
    }

    #[test]
    fn stale_content_becomes_clear_on_its_own_schedule() {
        let mut r = rig();
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(5));
        assert!(sent(&r, &title("A"), 0));
        // No more observations: CLEAR goes at the staleness, not at the
        // 60 s refresh.
        run_until(&mut r, t0 + STALE_AFTER + Duration::from_secs(6));
        assert!(sent(&r, &(super::super::TYPE_CLEAR, vec![]), 0));
    }

    #[test]
    fn a_newer_content_mid_frame_supersedes_it_and_goes_next() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let h = r.h.clone();
        let t = r.t.clone();
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                h.set_text(title("Bravo"), t.now());
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert!(!sent(&r, &title("Alpha"), 0), "A was abandoned");
        assert!(sent(&r, &title("Bravo"), 0));
    }

    #[test]
    fn a_b_a_is_two_changes_not_none() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let h = r.h.clone();
        let t = r.t.clone();
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                h.set_text(title("Bravo"), t.now());
                h.set_text(title("Alpha"), t.now());
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(20));
        // The first Alpha was cut off at write 20 (the old byte comparison
        // saw no change and finished it): the next write is the restore,
        // after the recovery wait. Alpha then went whole.
        let w = r.kb.borrow().writes.clone();
        assert!(w[21].0 - w[20].0 >= frame::RECOVERY, "write 21 is the restore, {:?} after", w[21].0 - w[20].0);
        assert!(sent(&r, &title("Alpha"), 0));
        assert!(r.h.status().frames >= 1);
    }

    #[test]
    fn a_title_going_stale_mid_frame_is_cut_off_for_its_clear() {
        let mut r = rig();
        let t0 = r.t.now();
        // Observed 28 s ago: fresh when picked (~1 s in), stale ~1 s into the
        // frame, which runs ~3.5 s.
        r.h.set_text(title("A rather long title to take time"), t0 - STALE_AFTER + Duration::from_secs(2));
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(10));
        assert!(!sent(&r, &title("A rather long title to take time"), 0), "never committed whole");
        assert!(sent(&r, &(super::super::TYPE_CLEAR, vec![]), 0));
    }

    #[test]
    fn a_stop_with_a_restore_owed_restores_once_through_the_flag() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let (h, kb) = (r.h.clone(), r.kb.clone());
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                h.revoke();
                kb.borrow_mut().unknown = true;
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(5));
        assert!(r.core.line.restore_pending);
        let n = r.kb.borrow().writes.len();
        r.kb.borrow_mut().unknown = false;
        r.h.stop();
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        assert_eq!(r.kb.borrow().writes.len(), n + 1, "the one restore at the stop");
        assert!(!r.core.line.restore_pending);
    }

    #[test]
    fn poison_keeps_the_guard_alive() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;
        struct Counted(Arc<AtomicUsize>);
        impl Drop for Counted {
            fn drop(&mut self) {
                self.0.fetch_add(1, Ordering::SeqCst);
            }
        }
        let drops = Arc::new(AtomicUsize::new(0));
        let mut r = rig();
        granted(&mut r, title("Alpha"));
        r.core.guard = Some(Box::new(Counted(drops.clone())));
        r.kb.borrow_mut().stuck = true;
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        drop(r);
        assert_eq!(drops.load(Ordering::SeqCst), 0, "forgotten, never dropped");
    }

    #[test]
    fn a_revoke_mid_frame_stops_before_the_next_write_and_restores() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let h = r.h.clone();
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                h.revoke();
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(20));
        let w = r.kb.borrow().writes.clone();
        assert_eq!(w.len(), 22, "write 21 is the restore, nothing of the frame after 20");
        assert_eq!(w[21].1, 0x00);
        assert!(w[21].0 - w[20].0 >= frame::RECOVERY);
        assert!(r.core.guard.is_none() && r.core.lights.is_none(), "released once restored");
    }

    #[test]
    fn a_pending_restore_is_retried_every_second_even_when_revoked() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let (h, kb) = (r.h.clone(), r.kb.clone());
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                h.revoke();
                kb.borrow_mut().unknown = true; // the session locks
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(10));
        assert!(r.core.line.restore_pending);
        assert!(r.core.guard.is_some(), "the lock stays while a restore is owed");
        let n = r.kb.borrow().writes.len();
        r.kb.borrow_mut().unknown = false; // unlocked
        let t1 = r.t.now();
        run_until(&mut r, t1 + Duration::from_secs(3));
        let w = r.kb.borrow().writes.clone();
        assert_eq!(w.len(), n + 1, "one restore write");
        assert!(!r.core.line.restore_pending);
        assert!(r.core.guard.is_none(), "released after");
    }

    #[test]
    fn a_failed_write_waits_the_recovery_from_its_own_end() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        let kb = r.kb.clone();
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == 20 {
                kb.borrow_mut().fail = true;
            }
        }));
        r.core.step(&r.h, &*r.t);
        // Write 21 failed after 1 s; the handle was dropped and nothing more
        // was written in that step.
        assert_eq!(r.kb.borrow().writes.len(), 21);
        assert!(r.core.lights.is_none());
        assert!(r.h.status().failures >= 1);
        let _ = t0;
    }

    #[test]
    fn a_stuck_write_or_open_poisons_and_keeps_the_lock() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        r.kb.borrow_mut().stuck = true;
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        assert_eq!(r.h.status().state, "poisoned");
        assert!(r.core.guard.is_none(), "forgotten, not dropped");
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        let _ = t0;

        let mut r = rig();
        granted(&mut r, title("Alpha"));
        r.core.platform.open_stuck = true;
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        assert_eq!(r.core.platform.opens, 1, "never retried");
        assert_eq!(r.h.status().state, "poisoned");
    }

    #[test]
    fn locks_unknown_hold_the_frame_and_their_return_resends() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        run_until(&mut r, t0 + Duration::from_secs(5));
        let n = r.kb.borrow().writes.len();
        r.kb.borrow_mut().unknown = true;
        let t1 = r.t.now();
        run_until(&mut r, t1 + Duration::from_secs(5));
        assert_eq!(r.kb.borrow().writes.len(), n, "nothing while unknown");
        assert_eq!(r.h.status().state, "locks unknown");
        r.kb.borrow_mut().unknown = false;
        let t2 = r.t.now();
        r.h.set_text(title("Alpha"), t2);
        run_until(&mut r, t2 + Duration::from_secs(6));
        assert!(r.kb.borrow().writes.len() > n + 20, "resent on their return, before the 60 s refresh");
    }

    #[test]
    fn the_wake_guess_resends_on_new_input_after_idleness() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        r.input.set(Some((1000, 1000)));
        // The title, its transport, and both repeats settle first.
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        r.input.set(Some((1000, 40_000))); // 39 s idle: armed
        let t1 = r.t.now();
        r.h.set_text(title("Alpha"), t1);
        run_until(&mut r, t1 + Duration::from_secs(2));
        assert_eq!(r.kb.borrow().writes.len(), n);
        r.input.set(Some((40_500, 40_500))); // a key
        let t2 = r.t.now();
        r.h.set_text(title("Alpha"), t2);
        run_until(&mut r, t2 + Duration::from_secs(6));
        assert!(r.kb.borrow().writes.len() > n + 20);
    }

    /// Steps through `secs` in 10 s strides, observing afresh at each with
    /// `observe`, so the media never goes stale (STALE_AFTER).
    fn observe_through(r: &mut Rig, secs: u64, mut observe: impl FnMut(&Handle, Instant)) {
        let end = r.t.now() + Duration::from_secs(secs);
        while r.t.now() < end {
            let t = r.t.now();
            observe(&r.h, t);
            let to = (t + Duration::from_secs(10)).min(end);
            run_until(r, to);
            r.t.sleep_until(to);
        }
    }

    #[test]
    fn nothing_goes_while_the_input_is_idle_and_the_held_change_after_the_wake() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        r.input.set(Some((1000, 1000)));
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32))); // idle: held
        // Observed afresh throughout: past Alpha's 60 s refresh, then a change.
        observe_through(&mut r, 60, |h, t| h.set_text(title("Alpha"), t));
        observe_through(&mut r, 30, |h, t| h.set_text(title("Bravo"), t));
        assert_eq!(r.kb.borrow().writes.len(), n, "neither the refresh nor the change while idle");
        assert_eq!(r.h.status().state, "held");
        // A key, with nothing observed anew: the wake guess fires, and the
        // held change waits its delay.
        r.input.set(Some((200_000, 200_000)));
        let t2 = r.t.now();
        run_until(&mut r, t2 + WAKE_DELAY - Duration::from_millis(500));
        assert_eq!(r.kb.borrow().writes.len(), n, "not before the wake delay");
        run_until(&mut r, t2 + WAKE_DELAY + Duration::from_secs(10));
        assert!(sent(&r, &title("Bravo"), 0), "the held change after the wake");
    }

    #[test]
    fn locks_unknown_through_the_hold_still_give_its_wake_the_delay() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        r.input.set(Some((1000, 1000)));
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        // The session locks first; the input then goes idle past the hold,
        // and Alpha's refresh falls due behind both (codex, the hold's
        // review, 1).
        r.kb.borrow_mut().unknown = true;
        let t1 = r.t.now();
        run_until(&mut r, t1 + Duration::from_secs(5));
        assert_eq!(r.h.status().state, "locks unknown");
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32 + 60_000)));
        observe_through(&mut r, 70, |h, t| h.set_text(title("Alpha"), t));
        assert_eq!(r.kb.borrow().writes.len(), n);
        // Unlocked: the locks known again and a key, in the same pass.
        r.kb.borrow_mut().unknown = false;
        r.input.set(Some((300_000, 300_000)));
        let t2 = r.t.now();
        run_until(&mut r, t2 + WAKE_DELAY - Duration::from_millis(500));
        assert_eq!(r.kb.borrow().writes.len(), n, "not at once on the unlock");
        run_until(&mut r, t2 + WAKE_DELAY + Duration::from_secs(10));
        assert!(r.kb.borrow().writes.len() > n + 20, "the refresh after the delay");
    }

    #[test]
    fn the_hold_begins_at_hold_idle_not_before() {
        let mut r = rig();
        let t0 = granted(&mut r, title("Alpha"));
        r.input.set(Some((1000, 1000)));
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        // A second short of the hold: the change goes at once.
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32 - 1000)));
        let t1 = r.t.now();
        r.h.set_text(title("Bravo"), t1);
        run_until(&mut r, t1 + Duration::from_secs(10));
        assert!(r.kb.borrow().writes.len() > n + 20);
        assert!(sent(&r, &title("Bravo"), 0));
    }

    // --- type 3, the transport -------------------------------------------

    use crate::lockchan::Playback;
    use crate::text::Icon;

    fn playing(lines: &str, icon: Icon, pos_s: u32, dur_s: u32) -> Media {
        let (_, text) = title(lines);
        let mut text1 = text.clone();
        text1[0] = icon.id();
        Media { text: (super::super::TYPE_NOW_PLAYING, text1), icon, pb: (icon == Icon::Play).then_some(Playback { pos_s, dur_s }) }
    }

    /// Every type-3 frame in the writes, as (icon, state, pos, dur), for any
    /// position up to `max_pos`.
    fn transports(r: &Rig, icon: Icon, dur: u32, max_pos: u32) -> Vec<u32> {
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|w| w.1).collect();
        let mut found = vec![];
        for pos in 0..=max_pos {
            let (k, b) = crate::lockchan::transport(icon, Some(Playback { pos_s: pos, dur_s: dur }), pos);
            if (0..=255u8).any(|seq| {
                let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).any(|x| x == &e[..])
            }) {
                found.push(pos);
            }
        }
        found
    }

    fn paused_transport_sent(r: &Rig) -> bool {
        let (k, b) = crate::lockchan::transport(Icon::Pause, None, 0);
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|w| w.1).collect();
        (0..=255u8).any(|seq| {
            let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap();
            w.windows(e.len()).any(|x| x == &e[..])
        })
    }

    #[test]
    fn a_playing_title_sends_its_text_then_its_transport_with_the_position_at_the_pick() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(8));
        assert!(sent(&r, &playing("Alpha", Icon::Play, 0, 0).text, 0), "the title");
        let pos = transports(&r, Icon::Play, 300, 140);
        assert!(!pos.is_empty(), "a transport followed");
        // Picked a few seconds after t0: the position moved with the clock.
        assert!(pos[0] > 100 && pos[0] < 110, "{pos:?}");
    }

    #[test]
    fn a_pause_sends_only_the_transport() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Pause, 115, 300), t1, t1);
        run_until(&mut r, t1 + Duration::from_secs(3));
        let new = r.kb.borrow().writes.len() - n;
        assert!(paused_transport_sent(&r), "the pause went as type 3");
        // A type 3 is short; a whole title would be far more writes.
        assert!(new > 10 && new < 90, "{new} writes after the pause");
    }

    #[test]
    fn a_seek_sends_the_transport_at_once() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        let t1 = r.t.now();
        // Jumped to 200 s: far from 100 + 15.
        r.h.set(playing("Alpha", Icon::Play, 200, 300), t1, t1);
        run_until(&mut r, t1 + Duration::from_secs(4));
        assert!(r.kb.borrow().writes.len() > n, "something went at once");
        assert!(transports(&r, Icon::Play, 300, 210).iter().any(|p| *p >= 200), "the new position");
    }

    #[test]
    fn a_seek_while_idle_is_held_and_its_transport_goes_after_the_wake() {
        let mut r = rig();
        let t0 = r.t.now();
        r.input.set(Some((1000, 1000)));
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32))); // idle: held
        // Jumped to 200 s at t1, and observed playing on from there.
        let t1 = r.t.now();
        observe_through(&mut r, 60, |h, t| h.set(playing("Alpha", Icon::Play, 200, 300), t, t1));
        assert_eq!(r.kb.borrow().writes.len(), n, "no transport while idle");
        assert_eq!(r.h.status().state, "held");
        r.input.set(Some((200_000, 200_000)));
        let t2 = r.t.now();
        run_until(&mut r, t2 + WAKE_DELAY - Duration::from_millis(500));
        assert_eq!(r.kb.borrow().writes.len(), n, "not before the wake delay");
        run_until(&mut r, t2 + WAKE_DELAY + Duration::from_secs(15));
        // Picked after the wake: the position from the latest observation,
        // 200 plus the ~64 s since, not the one before the hold.
        let pos = transports(&r, Icon::Play, 300, 300);
        assert!(pos.iter().any(|p| *p >= 260), "{pos:?}");
    }

    #[test]
    fn no_transport_follows_a_clear() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(Media { text: (super::super::TYPE_CLEAR, vec![]), icon: Icon::None, pb: None }, t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(8));
        assert!(sent(&r, &(super::super::TYPE_CLEAR, vec![]), 0));
        let (k, b) = crate::lockchan::transport(Icon::None, None, 0);
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|w| w.1).collect();
        let t3 = (0..=255u8).any(|seq| {
            let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap();
            w.windows(e.len()).any(|x| x == &e[..])
        });
        assert!(!t3, "no type 3 after a clear");
    }

    #[test]
    fn the_position_ticking_is_not_a_change() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        // The loop's polls: the position moving with the clock.
        for i in 1..=20u64 {
            let t = t0 + Duration::from_secs(15 + i);
            r.t.0.set(r.t.now().max(t));
            r.h.set(playing("Alpha", Icon::Play, 115 + i as u32, 300), t, t);
            run_until(&mut r, t);
        }
        assert_eq!(r.kb.borrow().writes.len(), n, "nothing sent for a ticking position");
    }

    #[test]
    fn the_end_of_a_track_is_not_a_seek() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 280, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(15));
        let n = r.kb.borrow().writes.len();
        // The track plays to its end at t0 + 20, and the source then sits at
        // 300/300, its snapshot's position ageing from that instant: no
        // seek, no frames (old code: 304 against 300 after a few polls).
        let end = t0 + Duration::from_secs(20);
        for i in 0..20u64 {
            let t = t0 + Duration::from_secs(16 + i);
            r.t.0.set(r.t.now().max(t));
            if t < end {
                r.h.set(playing("Alpha", Icon::Play, 280 + 16 + i as u32, 300), t, t);
            } else {
                r.h.set(playing("Alpha", Icon::Play, 300, 300), t, end);
            }
            run_until(&mut r, t);
        }
        assert_eq!(r.kb.borrow().writes.len(), n);
    }

    #[test]
    fn a_seek_gets_the_change_repeat() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 250, 300), t1, t1);
        run_until(&mut r, t1 + Duration::from_secs(10));
        // The seek and its repeat 2 s later: two type 3s at or past 250
        // (old code: one, then the 60 s refresh).
        let n = transports(&r, Icon::Play, 300, 270).iter().filter(|p| **p >= 250).count();
        assert!(n >= 2, "{n}");
    }

    #[test]
    fn a_title_change_during_a_transports_warm_up_sends_no_transport_for_it() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        let (h, t) = (r.h.clone(), r.t.clone());
        let n0 = r.kb.borrow().writes.len();
        // A pause, then (during the transport's warm-up) a new title.
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Pause, 120, 300), t1, t1);
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == n0 {
                h.set(playing("Bravo", Icon::Play, 0, 200), t.now(), t.now());
            }
        }));
        run_until(&mut r, t1 + Duration::from_secs(20));
        // Bravo's title went before any Bravo transport.
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|w| w.1).collect();
        let find = |c: &Content| {
            (0..=255u8).find_map(|seq| {
                let e = crate::lockchan::encode(&c.1, c.0, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).position(|x| x == &e[..])
            })
        };
        let title_at = find(&playing("Bravo", Icon::Play, 0, 0).text).expect("Bravo's title");
        let mut any = false;
        for pos in 0..30 {
            if let Some(at) = find(&crate::lockchan::transport(Icon::Play, Some(Playback { pos_s: pos, dur_s: 200 }), pos)) {
                assert!(at > title_at, "a Bravo transport before its title");
                any = true;
            }
        }
        assert!(any, "Bravo's transport went, after its title");
    }

    #[test]
    fn a_seek_mid_transport_cuts_it() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        let (h, t) = (r.h.clone(), r.t.clone());
        let n0 = r.kb.borrow().writes.len();
        // A seek to 200 starts a transport; 10 writes into it, a seek to 50:
        // title, icon, playing and duration unchanged, only the position
        // (codex, type-3 verify, 2: the old code finished this frame).
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 200, 300), t1, t1);
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == n0 + 10 {
                h.set(playing("Alpha", Icon::Play, 50, 300), t.now(), t.now());
            }
        }));
        r.core.step(&r.h, &*r.t);
        let w = r.kb.borrow().writes.clone();
        // Write n0+11 is the restore after the recovery wait: the frame was cut.
        assert!(w.len() > n0 + 11);
        assert!(w[n0 + 11].0 - w[n0 + 10].0 >= frame::RECOVERY);
    }

    #[test]
    fn a_media_key_that_wakes_waits_for_the_players_new_state() {
        let mut r = rig();
        let t0 = r.t.now();
        r.input.set(Some((1000, 1000)));
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        r.input.set(Some((1000, 40_000))); // idle: armed
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 120, 300), t1, t1);
        run_until(&mut r, t1 + Duration::from_millis(500));
        let n = r.kb.borrow().writes.len();
        // The play/pause key: input, but the player still says playing.
        r.input.set(Some((40_500, 40_500)));
        let t2 = r.t.now();
        run_until(&mut r, t2 + Duration::from_secs(2));
        assert_eq!(r.kb.borrow().writes.len(), n, "nothing in the first 2 s (old code: resent at once, the old icon)");
        // The player shows paused 2 s after the key.
        let t3 = r.t.now();
        r.h.set(playing("Alpha", Icon::Pause, 122, 300), t3, t3);
        run_until(&mut r, t3 + Duration::from_secs(8));
        assert!(paused_transport_sent(&r), "the pause went");
        // And no play-icon transport after the key.
        let w: Vec<u8> = r.kb.borrow().writes[n..].iter().map(|w| w.1).collect();
        for pos in 115..135 {
            let (k, b) = crate::lockchan::transport(Icon::Play, Some(Playback { pos_s: pos, dur_s: 300 }), pos);
            let hit = (0..=255u8).any(|seq| {
                let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).any(|x| x == &e[..])
            });
            assert!(!hit, "a play-icon transport at {pos} after the key");
        }
    }

    #[test]
    fn a_seek_during_a_transports_warm_up_still_gets_its_repeat() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        // Seek A to 200; let it go, so its 2 s repeat is next.
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 200, 300), t1, t1);
        run_until(&mut r, t1 + Duration::from_millis(1500));
        let (h, t) = (r.h.clone(), r.t.clone());
        let n0 = r.kb.borrow().writes.len();
        // During the repeat's warm-up (its first write), seek B to 50.
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == n0 {
                h.set(playing("Alpha", Icon::Play, 50, 300), t.now(), t.now());
            }
        }));
        let t2 = r.t.now();
        run_until(&mut r, t2 + Duration::from_secs(10));
        // B went, and again 2 s later: two transports near 50 (old code: one,
        // then the 60 s refresh).
        let n = transports(&r, Icon::Play, 300, 70).iter().filter(|p| (50..=60).contains(*p)).count();
        assert!(n >= 2, "{n} transports for seek B");
    }

    #[test]
    fn a_seek_back_to_the_last_picked_number_is_still_a_seek() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        // The source keeps reporting a steady playback until the transport's
        // 60 s refresh; during that refresh's warm-up it seeks back to exactly
        // the number the last transport picked (codex, type-3 verify 2, 1:
        // numeric equality skipped the elapsed-time check, and the pick then
        // made it the baseline, so the step saw nothing either).
        let (last, at) = r.core.sent_pos.expect("a transport was picked");
        let mut t = r.t.now();
        while t < at + Duration::from_secs(55) {
            t += Duration::from_secs(1);
            r.t.0.set(r.t.now().max(t));
            let pos = last + t.saturating_duration_since(at).as_secs() as u32;
            r.h.set(playing("Alpha", Icon::Play, pos, 300), t, t);
            run_until(&mut r, t);
        }
        // The refresh is the title, then its transport: the hook fires on the
        // transport's first warm-up write, after the step before it saw no seek.
        let n0 = r.kb.borrow().writes.len();
        let text = playing("Alpha", Icon::Play, 0, 0).text;
        let text_len = crate::lockchan::encode(&text.1, text.0, 0, Profile::P0, 0).unwrap().len();
        let at_tr = n0 + 2 + text_len;
        let (h, tt) = (r.h.clone(), r.t.clone());
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == at_tr {
                h.set(playing("Alpha", Icon::Play, last, 300), tt.now(), tt.now());
            }
        }));
        let t1 = r.t.now();
        run_until(&mut r, t1 + Duration::from_secs(20));
        // The seek back went, and its change repeat 2 s later.
        let w: Vec<u8> = r.kb.borrow().writes[n0..].iter().map(|w| w.1).collect();
        let hits = (last..=last + 8)
            .filter(|pos| {
                let (k, b) = crate::lockchan::transport(Icon::Play, Some(Playback { pos_s: *pos, dur_s: 300 }), *pos);
                (0..=255u8).any(|seq| {
                    let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap();
                    w.windows(e.len()).any(|x| x == &e[..])
                })
            })
            .count();
        let all: Vec<u32> = (0..400u32).filter(|pos| { let (k, b) = crate::lockchan::transport(Icon::Play, Some(Playback { pos_s: *pos, dur_s: 300 }), *pos); (0..=255u8).any(|seq| { let e = crate::lockchan::encode(&b, k, seq, Profile::P0, 0).unwrap(); w.windows(e.len()).any(|x| x == &e[..]) }) }).collect();
        let titles = sent(&r, &playing("Alpha", Icon::Play, 0, 0).text, 0);
        assert!(hits >= 2, "{hits} transports for the seek back to {last}; all after: {all:?}; title seen {titles}; frames {}", r.h.status().frames);
    }

    #[test]
    fn a_seek_on_the_final_write_withholds_the_credit() {
        let mut r = rig();
        let t0 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 100, 300), t0, t0);
        r.h.grant(Some(t0 - HANDOVER), t0);
        run_until(&mut r, t0 + Duration::from_secs(20));
        let frames0 = r.h.status().frames;
        // A seek starts a transport; its last write's completion sees
        // another seek: written whole, but not credited.
        let t1 = r.t.now();
        r.h.set(playing("Alpha", Icon::Play, 200, 300), t1, t1);
        // Learn the transport's length from a dry encode: warm-up 2 + frame.
        let (k, b) = crate::lockchan::transport(Icon::Play, Some(Playback { pos_s: 200, dur_s: 300 }), 200);
        let len = crate::lockchan::encode(&b, k, 0, Profile::P0, 0).unwrap().len();
        let n0 = r.kb.borrow().writes.len();
        let (h, t) = (r.h.clone(), r.t.clone());
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if i == n0 + 2 + len - 1 {
                h.set(playing("Alpha", Icon::Play, 30, 300), t.now(), t.now());
            }
        }));
        r.core.step(&r.h, &*r.t);
        assert_eq!(r.kb.borrow().writes.len(), n0 + 2 + len, "the whole frame went");
        assert_eq!(r.h.status().frames, frames0, "but was not credited");
    }

    #[test]
    fn absent_relists_every_10_s() {
        let mut r = rig();
        r.core.platform.present = false;
        let t0 = granted(&mut r, title("Alpha"));
        assert_eq!(r.core.step(&r.h, &*r.t), Next::WaitUntil(t0 + RELIST));
        assert_eq!(r.h.status().state, "absent");
        assert_eq!(r.core.step(&r.h, &*r.t), Next::WaitUntil(t0 + RELIST));
        assert_eq!(r.core.platform.opens, 1);
    }

    #[test]
    fn stop_exits_and_releases() {
        let mut r = rig();
        r.h.stop();
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Exit);
        assert!(r.core.guard.is_none());
    }

    // ---- Type 4, the clock (the plan's "The wireless clock", C3) ----

    /// 2026-10-20 21:00:00 UTC, the rig's wall clock at its start.
    const W0: i64 = 1_792_530_000_000;

    fn clock_rig(latency: Option<i32>) -> Rig {
        let r = rig();
        {
            let mut k = r.kb.borrow_mut();
            k.latency = latency;
            k.wall = Some((r.t.now(), W0));
            k.offset_s = -6 * 3600;
        }
        r.h.set_clock(true);
        r
    }

    /// The clock frames sent whole: for each write that could be an anchor,
    /// the payload the sender would have built from it, found in the writes.
    fn clock_frames(r: &Rig, latency: i32) -> Vec<(usize, Vec<u8>)> {
        clock_frames_on(r, latency, 0)
    }

    /// As [`clock_frames`], on the rig's wall clock less `shift_ms`: the
    /// clock as it was before a test stepped it.
    fn clock_frames_on(r: &Rig, latency: i32, shift_ms: i64) -> Vec<(usize, Vec<u8>)> {
        let w = r.kb.borrow().writes.clone();
        let p = &r.core.platform;
        let mut found = Vec::new();
        for (i, (at, _)) in w.iter().enumerate() {
            let wall = p.wall_ms_at(*at).unwrap() - shift_ms + latency as i64;
            let l = p.local(wall.div_euclid(1000)).unwrap();
            let Some(b) = super::super::clock_payload(&l, wall.rem_euclid(1000) as u32) else { continue };
            let vals: Vec<u8> = w.iter().map(|x| x.1).collect();
            for seq in 0..=255u8 {
                let e = crate::lockchan::encode(&b, super::super::TYPE_CLOCK, seq, Profile::P0, 0).unwrap();
                // Anchored at write i: the preamble's third write.
                if i >= 2 && vals.len() >= i - 2 + e.len() && vals[i - 2..i - 2 + e.len()] == e[..] {
                    found.push((i, b.clone()));
                }
            }
        }
        found
    }

    #[test]
    fn no_clock_frame_without_the_clock_or_a_measured_latency() {
        // Not the clock's owner: none, whatever the lights.
        let mut r = clock_rig(Some(38));
        r.h.set_clock(false);
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert!(sent(&r, &title("A"), 0));
        assert_eq!(r.h.status().clock_frames, 0);
        assert!(clock_frames(&r, 38).is_empty());
        // The owner, but lights with no measured latency: none, and said so.
        let mut r = clock_rig(None);
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert!(sent(&r, &title("A"), 0), "the media still goes");
        assert_eq!(r.h.status().clock_frames, 0);
        assert!(r.h.status().clock_off.is_some());
    }

    #[test]
    fn a_clock_frame_follows_the_title_with_the_anchors_time_plus_the_latency() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1, "one frame, matched at exactly one anchor");
        // Local time, the offset applied: 15:00 and some seconds.
        let b = &f[0].1;
        assert_eq!((b[0], b[1], b[2], b[4]), (26, 10, 20, 15));
        assert_eq!((b[9], b[10], b[11]), (0, 0xFF, 0x7F), "flags 0, the bias unknown");
        // After the title, which went first.
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|x| x.1).collect();
        let e = crate::lockchan::encode(&title("A").1, title("A").0, 0, Profile::P0, 0).unwrap();
        let title_at = w.windows(e.len()).position(|x| x == &e[..]).expect("the title");
        assert!(title_at < f[0].0);
        assert!(r.h.take_log().iter().any(|l| l.starts_with("lockchan: sent clock 2026-10-20 15:00:")));
    }

    #[test]
    fn clock_frames_repeat_every_ten_minutes() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        let first = r.h.status().clock_last.unwrap();
        run_until(&mut r, first + clk::EVERY - Duration::from_secs(1));
        assert_eq!(r.h.status().clock_frames, 1, "not before ten minutes");
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(10));
        assert_eq!(r.h.status().clock_frames, 2);
    }

    #[test]
    fn the_first_clock_frame_waits_out_the_boards_window_after_a_usb_sync() {
        let mut r = clock_rig(Some(38));
        r.h.usb_clock_synced(r.t.now() - Duration::from_secs(100));
        let t0 = granted(&mut r, title("A"));
        let open = t0 - Duration::from_secs(100) + clk::OWNER_FLOOR;
        run_until(&mut r, open - Duration::from_secs(1));
        assert!(sent(&r, &title("A"), 0), "the media does not wait");
        assert_eq!(r.h.status().clock_frames, 0);
        run_until(&mut r, open + Duration::from_secs(10));
        assert_eq!(r.h.status().clock_frames, 1);
    }

    #[test]
    fn a_track_change_cuts_a_clock_frame_and_goes_first() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(3));
        assert!(sent(&r, &title("A"), 0));
        assert_eq!(r.h.status().clock_frames, 0, "the clock not yet");
        // Thirty writes into the clock frame itself (not the transport
        // before it), Bravo.
        let (h, t) = (r.h.clone(), r.t.clone());
        let cut: Rc<Cell<Option<usize>>> = Rc::new(Cell::new(None));
        let (start, c2) = (Rc::new(Cell::new(None::<usize>)), cut.clone());
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if c2.get().is_some() || h.status().state != "sending clock" {
                return;
            }
            let s0 = *start.get().get_or_insert(i);
            start.set(Some(s0));
            if i == s0 + 30 {
                h.set_text(title("Bravo"), t.now());
                c2.set(Some(i));
            }
        }));
        run_until(&mut r, t0 + Duration::from_secs(30));
        let n = cut.get().expect("a clock frame was under way") - 30;
        assert!(sent(&r, &title("Bravo"), 0));
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1, "the clock went whole once, after");
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|x| x.1).collect();
        let bravo_at = (0..=255u8)
            .find_map(|seq| {
                let e = crate::lockchan::encode(&title("Bravo").1, title("Bravo").0, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).position(|x| x == &e[..])
            })
            .expect("Bravo");
        assert!(bravo_at > n + 30 && bravo_at < f[0].0, "Bravo, then the clock");
    }

    #[test]
    fn no_clock_frame_is_built_across_an_offset_change() {
        // Where the first clock frame anchors, on this deterministic rig.
        let mut dry = clock_rig(Some(38));
        let t = granted(&mut dry, title("A"));
        run_until(&mut dry, t + Duration::from_secs(20));
        let a = clock_frames(&dry, 38)[0].0;
        let at = dry.kb.borrow().writes[a].0;
        let anchor_s = (dry.core.platform.wall_ms_at(at).unwrap() + 38) / 1000;
        // The offset changes 5 s after that anchor: inside SPAN of it.
        let mut r = clock_rig(Some(38));
        let change = anchor_s + 5;
        r.kb.borrow_mut().offset_change = Some((change, -5 * 3600));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(60));
        assert_eq!(r.h.status().clock_frames, 1, "one, after the change");
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1);
        assert_eq!(f[0].1[4], 16, "the new offset's hour: 16:00, not 15:00");
        let anchor = r.kb.borrow().writes[f[0].0].0;
        assert!(r.core.platform.wall_ms_at(anchor).unwrap() / 1000 >= change, "anchored after the change");
    }

    #[test]
    fn an_offset_change_while_granted_sends_at_once() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        // DST two minutes on, well inside the ten.
        r.kb.borrow_mut().offset_change = Some((W0 / 1000 + 120, -5 * 3600));
        run_until(&mut r, t0 + Duration::from_secs(150));
        assert_eq!(r.h.status().clock_frames, 2);
    }

    #[test]
    fn a_revoke_stops_clock_frames_and_a_grant_restarts_them() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        r.h.revoke();
        run_until(&mut r, t0 + clk::EVERY + Duration::from_secs(60));
        assert_eq!(r.h.status().clock_frames, 1, "none while revoked");
        let t1 = r.t.now();
        r.h.set_text(title("A"), t1);
        r.h.grant(Some(t1 - HANDOVER), t1);
        run_until(&mut r, t1 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 2, "again after the new acquisition");
    }

    #[test]
    fn no_clock_frame_while_the_input_is_idle_then_one_after_the_wake() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        let first = r.h.status().clock_last.unwrap();
        // Idle from a minute in, through the ten-minute mark.
        r.input.set(Some((1000, 1000 + 61_000)));
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(60));
        assert_eq!(r.h.status().clock_frames, 1, "held back while idle");
        // A key: the wake guess fires; the frame goes after its delay.
        let t1 = r.t.now();
        r.input.set(Some((900_000, 900_000)));
        run_until(&mut r, t1 + crate::lockchan::sender::WAKE_DELAY - Duration::from_millis(500));
        assert_eq!(r.h.status().clock_frames, 1, "not before the wake delay");
        run_until(&mut r, t1 + crate::lockchan::sender::WAKE_DELAY + Duration::from_secs(10));
        assert_eq!(r.h.status().clock_frames, 2);
    }

    #[test]
    fn the_clock_is_held_from_hold_idle_as_the_media_is() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        let first = r.h.status().clock_last.unwrap();
        // 50 s idle across the refresh: past the hold, short of Lights out's
        // sleep, where a frame begun could still run into it.
        r.input.set(Some((1000, 1000 + 50_000)));
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(30));
        assert_eq!(r.h.status().clock_frames, 1, "held at 50 s idle");
        // Exactly at the hold: still held.
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32)));
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(40));
        assert_eq!(r.h.status().clock_frames, 1, "held at HOLD_IDLE");
        // A millisecond short of it: the refresh goes.
        r.input.set(Some((1000, 1000 + HOLD_IDLE.as_millis() as u32 - 1)));
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(70));
        assert_eq!(r.h.status().clock_frames, 2, "sent short of the hold");
    }

    #[test]
    fn a_clock_held_at_fifty_seconds_goes_at_the_wake() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        let first = r.h.status().clock_last.unwrap();
        r.input.set(Some((1000, 1000 + 50_000)));
        run_until(&mut r, first + clk::EVERY + Duration::from_secs(30));
        assert_eq!(r.h.status().clock_frames, 1, "held at 50 s idle");
        // A key: the frame after the wake delay, not before.
        let t1 = r.t.now();
        r.input.set(Some((900_000, 900_000)));
        run_until(&mut r, t1 + WAKE_DELAY - Duration::from_millis(500));
        assert_eq!(r.h.status().clock_frames, 1, "not before the wake delay");
        run_until(&mut r, t1 + WAKE_DELAY + Duration::from_secs(10));
        assert_eq!(r.h.status().clock_frames, 2);
    }

    /// A hook that fires once, `k` writes into the first clock frame (its
    /// warm-up's first write is 0).
    fn in_clock(r: &Rig, k: usize, f: impl FnOnce(&Handle, &Rc<RefCell<Kb>>) + 'static) -> Rc<Cell<Option<usize>>> {
        let fired: Rc<Cell<Option<usize>>> = Rc::new(Cell::new(None));
        let (h, kb, done) = (r.h.clone(), Rc::downgrade(&r.kb), fired.clone());
        let start: Cell<Option<usize>> = Cell::new(None);
        let mut f = Some(f);
        r.kb.borrow_mut().hook = Some(Box::new(move |i| {
            if done.get().is_some() || h.status().state != "sending clock" {
                return;
            }
            let s0 = *start.get().get_or_insert(i);
            start.set(Some(s0));
            if i == s0 + k {
                if let (Some(f), Some(kb)) = (f.take(), kb.upgrade()) {
                    f(&h, &kb);
                }
                done.set(Some(i));
            }
        }));
        fired
    }

    #[test]
    fn a_track_change_in_a_clock_frames_warm_up_goes_first() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        let t = r.t.clone();
        let fired = in_clock(&r, 0, move |h, _| h.set_text(title("Bravo"), t.now()));
        run_until(&mut r, t0 + Duration::from_secs(30));
        let at = fired.get().expect("a clock frame began");
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|x| x.1).collect();
        let bravo_at = (0..=255u8)
            .find_map(|seq| {
                let e = crate::lockchan::encode(&title("Bravo").1, title("Bravo").0, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).position(|x| x == &e[..])
            })
            .expect("Bravo");
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1);
        assert!(at < bravo_at && bravo_at < f[0].0, "the clock's warm-up, Bravo, then the clock");
    }

    #[test]
    fn a_wall_step_during_a_clock_frame_cuts_it_and_the_next_has_the_new_time() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        // Thirty writes in: past the anchor, mid-payload; the wall clock
        // jumps a minute.
        let fired = in_clock(&r, 30, |_, kb| {
            let mut k = kb.borrow_mut();
            let (at, w) = k.wall.unwrap();
            k.wall = Some((at, w + 60_000));
        });
        run_until(&mut r, t0 + Duration::from_secs(30));
        let at = fired.get().expect("a clock frame began");
        // Matched on the stepped clock: the one frame whole is after the step.
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1);
        assert!(f[0].0 > at);
        assert_eq!(r.h.status().clock_frames, 1);
        // And the frame with the old time never went whole: cut, not only
        // left uncredited.
        assert!(clock_frames_on(&r, 38, 60_000).is_empty(), "the stale frame was finished");
    }

    #[test]
    fn a_wall_step_after_a_clock_frames_last_write_is_not_credited() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        // Learn the clock frame's length from a dry rig, then step the wall
        // at its very last write.
        let mut dry = clock_rig(Some(38));
        let td = granted(&mut dry, title("A"));
        run_until(&mut dry, td + Duration::from_secs(20));
        let (anchor, b) = clock_frames(&dry, 38)[0].clone();
        let len = crate::lockchan::encode(&b, super::super::TYPE_CLOCK, 0, Profile::P0, 0).unwrap().len();
        let k = 2 + (len - 1); // the warm-up's 2, then the frame's last
        let _ = anchor;
        in_clock(&r, k, |_, kb| {
            let mut k = kb.borrow_mut();
            let (at, w) = k.wall.unwrap();
            k.wall = Some((at, w - 5_000));
        });
        run_until(&mut r, t0 + Duration::from_secs(40));
        // The first went whole but was not credited; another went at once.
        assert_eq!(r.h.status().clock_frames, 1);
        assert_eq!(clock_frames(&r, 38).len(), 1, "matched on the stepped clock: the resend");
    }

    #[test]
    fn a_negative_latency_is_applied() {
        let mut r = clock_rig(Some(-120));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(clock_frames(&r, -120).len(), 1);
        assert!(clock_frames(&r, 38).is_empty());
    }

    #[test]
    fn a_time_the_board_cannot_take_backs_off() {
        let mut r = clock_rig(Some(38));
        // 2100-01-01: past the board's range, clock_payload refuses.
        r.kb.borrow_mut().wall = Some((r.t.now(), 4_102_444_800_000));
        let t0 = granted(&mut r, title("A"));
        run_until(&mut r, t0 + Duration::from_secs(8));
        let n = r.kb.borrow().writes.len();
        // To 24 s: inside the retry from the first attempt (~3 s), and before
        // the title goes stale (30 s) and its clear is sent.
        run_until(&mut r, t0 + Duration::from_secs(24));
        assert_eq!(r.kb.borrow().writes.len(), n, "no attempt inside the retry");
        assert_eq!(r.h.status().clock_frames, 0);
    }

    #[test]
    fn a_zone_change_between_the_builders_conversions_cuts_the_frame() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        // At the anchor's write (the warm-up's 2, the preamble's 3rd), the
        // zone changes from the builder's third conversion on: after the
        // payload's two (its time and SPAN on).
        in_clock(&r, 4, |_, kb| {
            let mut k = kb.borrow_mut();
            k.offset_from_call = Some((k.local_calls + 3, -5 * 3600));
        });
        run_until(&mut r, t0 + Duration::from_secs(30));
        assert_eq!(r.h.status().clock_frames, 1);
        let new = clock_frames(&r, 38);
        assert_eq!(new.len(), 1, "one frame whole, on the new zone");
        assert_eq!(new[0].1[4], 16);
        r.kb.borrow_mut().offset_s = -6 * 3600;
        assert!(clock_frames(&r, 38).is_empty(), "the old zone's frame never finished");
    }

    #[test]
    fn a_wake_in_the_pass_of_a_grant_still_waits_the_delay() {
        let mut r = clock_rig(Some(38));
        let t0 = r.t.now();
        r.h.set_text(title("A"), t0);
        // Idle and armed, not granted.
        r.input.set(Some((1000, 1000 + 61_000)));
        assert_eq!(r.core.step(&r.h, &*r.t), Next::Wait);
        // A key, and the grant (its handover long past), in one pass.
        r.input.set(Some((70_000, 70_000)));
        r.h.grant(Some(t0 - HANDOVER), t0);
        r.core.step(&r.h, &*r.t);
        assert!(r.core.clock.due().unwrap() >= t0 + WAKE_DELAY, "the acquisition kept the wake's delay");
        // The media's acquisition sends the title at once (its own rule);
        // the clock waits the wake's delay.
        run_until(&mut r, t0 + Duration::from_secs(20));
        assert_eq!(r.h.status().clock_frames, 1);
        let f = clock_frames(&r, 38);
        let (first, _) = r.kb.borrow().writes[f[0].0 - 4];
        assert!(first >= t0 + WAKE_DELAY, "the clock frame began {:?} after the wake", first - t0);
    }

    #[test]
    fn a_track_change_while_the_lights_open_goes_before_the_clock() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        // The title first; then, with the clock due next, the lights closed
        // so its pass opens them, and the change lands in that open.
        let mut fired = false;
        for _ in 0..1000 {
            // The title and its transport both sent: the clock is next.
            let now = r.t.now();
            let clock_next = r.core.clock.due().is_some_and(|d| d <= now)
                && r.core.text.due().map_or(true, |d| d > now)
                && r.core.tr.due().map_or(true, |d| d > now);
            if !fired && clock_next && r.h.status().clock_frames == 0 {
                r.core.lights = None;
                let (h, t) = (r.h.clone(), r.t.clone());
                let mut once = true;
                r.kb.borrow_mut().open_hook = Some(Box::new(move || {
                    if std::mem::take(&mut once) {
                        h.set_text(title("Bravo"), t.now());
                    }
                }));
                fired = true;
            }
            match r.core.step(&r.h, &*r.t) {
                Next::WaitUntil(w) if w <= t0 + Duration::from_secs(30) => {
                    r.t.sleep_until(w);
                }
                _ => break,
            }
        }
        assert!(fired);
        let w: Vec<u8> = r.kb.borrow().writes.iter().map(|x| x.1).collect();
        let bravo_at = (0..=255u8)
            .find_map(|seq| {
                let e = crate::lockchan::encode(&title("Bravo").1, title("Bravo").0, seq, Profile::P0, 0).unwrap();
                w.windows(e.len()).position(|x| x == &e[..])
            })
            .expect("Bravo");
        let f = clock_frames(&r, 38);
        assert_eq!(f.len(), 1);
        assert!(bravo_at < f[0].0, "Bravo before the clock");
    }

    #[test]
    fn a_step_after_the_final_check_is_still_seen_and_resent() {
        let mut r = clock_rig(Some(38));
        let t0 = granted(&mut r, title("A"));
        let mut dry = clock_rig(Some(38));
        let td = granted(&mut dry, title("A"));
        run_until(&mut dry, td + Duration::from_secs(20));
        let (_, b) = clock_frames(&dry, 38)[0].clone();
        let len = crate::lockchan::encode(&b, super::super::TYPE_CLOCK, 0, Profile::P0, 0).unwrap().len();
        // At the frame's last write: the final continuity check's sample sees
        // the old clock, every later one a minute on.
        in_clock(&r, 2 + len - 1, |_, kb| kb.borrow_mut().wall_step_after = Some((1, 60_000)));
        run_until(&mut r, t0 + Duration::from_secs(40));
        assert_eq!(r.h.status().clock_frames, 2, "credited, then the step seen and resent");
        assert_eq!(clock_frames(&r, 38).len(), 1, "the resend carries the stepped clock");
    }
}

