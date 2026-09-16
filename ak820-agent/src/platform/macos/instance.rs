//! One now-playing agent at a time, shared with `nowplaying-macos.sh`.
//!
//! The bash agent's lock is a directory, `$TMPDIR/ak820pro-nowplaying.lock`,
//! holding the owner's pid (`nowplaying-macos.sh:19-33`). Taking the **same**
//! lock, with our own pid, is what the plan's Phase 4a asks for: a stray bash
//! started by an old LaunchAgent sees a live pid and exits, as the Windows
//! daemon holds the Python agent's mutex name (`windows/instance.rs`).
//!
//! `mkdir` is atomic, so it is the lock. A stale one (its pid gone) is cleared
//! and retaken once, as the bash does. The directory is removed when the
//! [`Lock`] drops; a daemon killed by a signal leaves it, and the next start
//! finds its pid gone.
//!
//! Two traps from the Phases 1 and 3 audit (F5):
//!
//! - ⚠️ **A lock with no pid file yet is not stale.** The bash writes its pid
//!   *after* `mkdir`, and at login both agents start together. So a missing pid
//!   is waited for (up to [`PID_GRACE`]) before the lock is cleared.
//! - ⚠️ **`$TMPDIR` is not always set.** launchd sets it for agents, but an SSH
//!   shell does not, and the bash then falls back to `/tmp`. So the directory
//!   is `$TMPDIR`, else the per-user temp dir launchd would have given
//!   (`confstr(_CS_DARWIN_USER_TEMP_DIR)`); and a live holder at **any** of
//!   the places a bash could have put it refuses the claim.

use std::io;
use std::os::raw::{c_char, c_int};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

pub const NAME: &str = "ak820pro-nowplaying.lock";

/// How long a lock directory may exist without a pid before it is stale.
pub const PID_GRACE: Duration = Duration::from_secs(2);

const CS_DARWIN_USER_TEMP_DIR: c_int = 65537;

extern "C" {
    fn kill(pid: c_int, sig: c_int) -> c_int;
    fn confstr(name: c_int, buf: *mut c_char, len: usize) -> usize;
}

/// The per-user temp dir, as launchd hands it to agents in `$TMPDIR`.
fn user_temp_dir() -> Option<PathBuf> {
    let mut buf = vec![0u8; 1024];
    let n = unsafe { confstr(CS_DARWIN_USER_TEMP_DIR, buf.as_mut_ptr() as *mut c_char, buf.len()) };
    if n == 0 || n > buf.len() {
        return None;
    }
    buf.truncate(n - 1); // the count includes the NUL
    Some(PathBuf::from(String::from_utf8(buf).ok()?))
}

/// Where this process takes the lock: `$TMPDIR`, else the per-user temp dir,
/// else `/tmp`.
pub fn default_path() -> PathBuf {
    std::env::var_os("TMPDIR")
        .filter(|t| !t.is_empty())
        .map(PathBuf::from)
        .or_else(user_temp_dir)
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join(NAME)
}

/// Every place a bash agent could have put its lock: the primary, the per-user
/// temp dir, and `/tmp` (its fallback with `$TMPDIR` unset).
pub fn all_paths() -> Vec<PathBuf> {
    let mut paths = vec![default_path()];
    for dir in [user_temp_dir(), Some(PathBuf::from("/tmp"))].into_iter().flatten() {
        let p = dir.join(NAME);
        let same = |a: &Path, b: &Path| a == b || matches!((a.parent().and_then(|d| d.canonicalize().ok()), b.parent().and_then(|d| d.canonicalize().ok())), (Some(x), Some(y)) if x == y);
        if !paths.iter().any(|q| same(q, &p)) {
            paths.push(p);
        }
    }
    paths
}

/// The live holder at any of [`all_paths`], with where.
pub fn any_holder() -> Option<(i32, PathBuf)> {
    all_paths().into_iter().find_map(|p| holder(&p).map(|pid| (pid, p)))
}

/// Is `pid` a live process? EPERM means it exists but is not ours.
fn alive(pid: i32) -> bool {
    if pid <= 0 {
        return false;
    }
    let rc = unsafe { kill(pid, 0) };
    rc == 0 || io::Error::last_os_error().raw_os_error() == Some(1)
}

/// The live pid holding the lock at `path`, if any. A lock with no pid file or
/// a dead pid is not held.
pub fn holder(path: &Path) -> Option<i32> {
    read_pid(path).filter(|&pid| alive(pid))
}

fn read_pid(path: &Path) -> Option<i32> {
    std::fs::read_to_string(path.join("pid")).ok().and_then(|s| s.trim().parse::<i32>().ok())
}

#[derive(Debug)]
pub struct Lock {
    path: PathBuf,
}

impl Lock {
    /// Claim `path`, refusing if a live agent holds it or any of `also`.
    pub fn claim_all(path: &Path, also: &[PathBuf]) -> Result<Lock, String> {
        for other in also.iter().filter(|o| o.as_path() != path) {
            if let Some(pid) = holder(other) {
                return Err(format!("another now-playing agent is live as pid {pid} ({})", other.display()));
            }
        }
        Lock::claim(path)
    }

    pub fn claim(path: &Path) -> Result<Lock, String> {
        for attempt in 0..2 {
            match std::fs::create_dir(path) {
                Ok(()) => {
                    let lock = Lock { path: path.to_owned() };
                    std::fs::write(path.join("pid"), format!("{}\n", std::process::id()))
                        .map_err(|e| format!("writing {}: {e}", path.join("pid").display()))?;
                    return Ok(lock);
                }
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists && attempt == 0 => {
                    // No pid yet may be an owner between its mkdir and its
                    // write: wait for one before calling the lock stale.
                    let until = Instant::now() + PID_GRACE;
                    while read_pid(path).is_none() && path.is_dir() && Instant::now() < until {
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    match holder(path) {
                        Some(pid) => {
                            return Err(format!("another now-playing agent is live as pid {pid} ({})", path.display()))
                        }
                        None => {
                            let _ = std::fs::remove_dir_all(path);
                        }
                    }
                }
                Err(e) => return Err(format!("taking {}: {e}", path.display())),
            }
        }
        Err(format!("taking {}: lost a race twice", path.display()))
    }
}

impl Drop for Lock {
    fn drop(&mut self) {
        // Only ours: a lock someone else retook after clearing ours as stale
        // holds their pid.
        let mine = std::fs::read_to_string(self.path.join("pid"))
            .ok()
            .and_then(|s| s.trim().parse::<u32>().ok())
            == Some(std::process::id());
        if mine {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!("ak820-lock-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&p);
        p
    }

    #[test]
    fn a_live_owner_refuses_and_a_drop_releases() {
        let p = scratch("live");
        let held = Lock::claim(&p).unwrap();
        let err = Lock::claim(&p).unwrap_err();
        assert!(err.contains(&format!("pid {}", std::process::id())), "{err}");
        drop(held);
        assert!(!p.exists());
        drop(Lock::claim(&p).unwrap());
    }

    #[test]
    fn a_dead_owner_is_cleared() {
        let p = scratch("stale");
        std::fs::create_dir(&p).unwrap();
        // pid_max on macOS is 99999, so this pid cannot be live.
        std::fs::write(p.join("pid"), "999999\n").unwrap();
        let held = Lock::claim(&p).unwrap();
        assert_eq!(std::fs::read_to_string(p.join("pid")).unwrap().trim(), std::process::id().to_string());
        drop(held);
    }

    /// F5: a lock directory whose pid arrives late is not cleared as stale.
    #[test]
    fn a_pid_written_just_after_mkdir_is_waited_for() {
        let p = scratch("late");
        std::fs::create_dir(&p).unwrap();
        let writer = {
            let p = p.clone();
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(300));
                std::fs::write(p.join("pid"), "1\n").unwrap(); // launchd: always live
            })
        };
        let err = Lock::claim(&p).unwrap_err();
        writer.join().unwrap();
        assert!(err.contains("pid 1"), "{err}");
        let _ = std::fs::remove_dir_all(&p);
    }

    #[test]
    fn a_holder_elsewhere_refuses_the_claim() {
        let mine = scratch("mine");
        let theirs = scratch("theirs");
        std::fs::create_dir(&theirs).unwrap();
        std::fs::write(theirs.join("pid"), "1\n").unwrap();
        assert!(Lock::claim_all(&mine, std::slice::from_ref(&theirs)).unwrap_err().contains("pid 1"));
        assert!(!mine.exists(), "nothing taken on refusal");
        let _ = std::fs::remove_dir_all(&theirs);
    }

    #[test]
    fn the_per_user_temp_dir_and_tmp_are_both_searched() {
        let all = all_paths();
        assert!(all.iter().any(|p| p == Path::new("/tmp").join(NAME).as_path() || p.starts_with("/private/tmp")));
        let user = user_temp_dir().expect("confstr answers on macOS");
        assert!(user.is_dir(), "{}", user.display());
    }

    /// The bash agent's own lock shape is honoured: its pid is a live process.
    #[test]
    fn a_bash_owner_is_respected() {
        let p = scratch("bash");
        std::fs::create_dir(&p).unwrap();
        std::fs::write(p.join("pid"), "1\n").unwrap(); // launchd: always live, never ours
        assert!(Lock::claim(&p).unwrap_err().contains("pid 1"));
        let _ = std::fs::remove_dir_all(&p);
    }
}
