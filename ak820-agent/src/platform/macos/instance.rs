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

use std::io;
use std::os::raw::c_int;
use std::path::{Path, PathBuf};

pub const NAME: &str = "ak820pro-nowplaying.lock";

extern "C" {
    fn kill(pid: c_int, sig: c_int) -> c_int;
}

/// Where the bash agent puts it: `${TMPDIR:-/tmp}`.
pub fn default_path() -> PathBuf {
    std::env::var_os("TMPDIR")
        .filter(|t| !t.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join(NAME)
}

/// Is `pid` a live process? EPERM means it exists but is not ours.
fn alive(pid: i32) -> bool {
    if pid <= 0 {
        return false;
    }
    let rc = unsafe { kill(pid, 0) };
    rc == 0 || io::Error::last_os_error().raw_os_error() == Some(1)
}

#[derive(Debug)]
pub struct Lock {
    path: PathBuf,
}

impl Lock {
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
                    let owner = std::fs::read_to_string(path.join("pid"))
                        .ok()
                        .and_then(|s| s.trim().parse::<i32>().ok());
                    match owner {
                        Some(pid) if alive(pid) => {
                            return Err(format!("another now-playing agent is live as pid {pid} ({})", path.display()))
                        }
                        // ⚠️ No pid yet can also be an owner between its mkdir
                        // and its write. The bash has the same window; clearing
                        // it costs at most one duplicate poller, which then
                        // loses on its next start.
                        _ => {
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
