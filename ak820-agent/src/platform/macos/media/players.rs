//! Which AppleScript-scriptable players are running — from the process table,
//! with **no spawn** and **no Apple event**.
//!
//! Two reasons it must not be `osascript -e 'application "Music" is running'`,
//! which is what `nowplaying-macos.sh` does twice a poll: that is a process
//! spawn, and the S1b canary exists to cross-check MediaRemote *without*
//! bringing spawns back into the idle state (plan, Efficiency). And an
//! AppleScript `tell` to a player that is not running **launches it**.
//!
//! Matched by exact executable path, never by name: a helper or an unrelated
//! binary called `Music` must not count.

use std::os::raw::{c_char, c_int, c_void};

pub const MUSIC: &str = "/System/Applications/Music.app/Contents/MacOS/Music";
pub const SPOTIFY: &str = "/Applications/Spotify.app/Contents/MacOS/Spotify";

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Player {
    Music,
    Spotify,
}

impl Player {
    pub fn app_name(self) -> &'static str {
        match self {
            Player::Music => "Music",
            Player::Spotify => "Spotify",
        }
    }
    pub fn bundle(self) -> &'static str {
        match self {
            Player::Music => "com.apple.Music",
            Player::Spotify => "com.spotify.client",
        }
    }
    pub fn from_bundle(bundle: &str) -> Option<Player> {
        [Player::Music, Player::Spotify]
            .into_iter()
            .find(|p| p.bundle().eq_ignore_ascii_case(bundle))
    }
    pub fn from_path(path: &str) -> Option<Player> {
        match path {
            MUSIC => Some(Player::Music),
            SPOTIFY => Some(Player::Spotify),
            _ => None,
        }
    }
}

extern "C" {
    fn proc_listallpids(buffer: *mut c_void, buffersize: c_int) -> c_int;
    fn proc_pidpath(pid: c_int, buffer: *mut c_void, buffersize: u32) -> c_int;
}

const PROC_PIDPATHINFO_MAXSIZE: usize = 4096;

/// Running players, in a stable order (Spotify first, as the bash agent asks).
pub fn running() -> Vec<Player> {
    let mut pids = vec![0 as c_int; 8192];
    let n =
        unsafe { proc_listallpids(pids.as_mut_ptr() as *mut c_void, (pids.len() * 4) as c_int) };
    let mut found = Vec::new();
    let mut path = vec![0 as c_char; PROC_PIDPATHINFO_MAXSIZE];
    for &pid in pids.iter().take(n.max(0) as usize) {
        if pid <= 0 {
            continue;
        }
        let len = unsafe { proc_pidpath(pid, path.as_mut_ptr() as *mut c_void, path.len() as u32) };
        if len <= 0 {
            continue; // not ours to read, or gone
        }
        let bytes = unsafe { std::slice::from_raw_parts(path.as_ptr() as *const u8, len as usize) };
        if let Some(p) = std::str::from_utf8(bytes).ok().and_then(Player::from_path) {
            if !found.contains(&p) {
                found.push(p);
            }
        }
    }
    found.sort_by_key(|p| match p {
        Player::Spotify => 0,
        Player::Music => 1,
    });
    found
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_exact_executable_counts() {
        assert_eq!(Player::from_path(MUSIC), Some(Player::Music));
        assert_eq!(Player::from_path(SPOTIFY), Some(Player::Spotify));
        assert_eq!(
            Player::from_path("/System/Applications/Music.app/Contents/XPCServices/Helper"),
            None
        );
        assert_eq!(Player::from_path("/usr/local/bin/Music"), None);
    }

    /// Reads the real process table. Opens nothing, sends no Apple event;
    /// asserts only that it returns without error and finds no duplicates.
    #[test]
    fn the_process_table_reads_without_spawning() {
        let r = running();
        let mut d = r.clone();
        d.dedup();
        assert_eq!(r, d);
    }
}
