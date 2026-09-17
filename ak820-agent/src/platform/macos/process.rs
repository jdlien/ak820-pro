//! Processes by executable name, from the process table: no spawn, no
//! `pgrep`. For the clock's ownership check, which must see a hand-started
//! `ak820ctl` as well as the timekeeper's.

use std::os::raw::{c_char, c_int, c_void};

extern "C" {
    fn proc_listallpids(buffer: *mut c_void, buffersize: c_int) -> c_int;
    fn proc_pidpath(pid: c_int, buffer: *mut c_void, buffersize: u32) -> c_int;
}

const PROC_PIDPATHINFO_MAXSIZE: usize = 4096;

/// How many running processes have an executable whose file name is `name`.
/// Processes whose path cannot be read (another user's) are not counted.
pub fn running_named(name: &str) -> usize {
    let mut pids = vec![0 as c_int; 8192];
    let n = unsafe { proc_listallpids(pids.as_mut_ptr() as *mut c_void, (pids.len() * 4) as c_int) };
    let mut path = vec![0 as c_char; PROC_PIDPATHINFO_MAXSIZE];
    let mut count = 0;
    for &pid in pids.iter().take(n.max(0) as usize) {
        if pid <= 0 {
            continue;
        }
        let len = unsafe { proc_pidpath(pid, path.as_mut_ptr() as *mut c_void, path.len() as u32) };
        if len <= 0 {
            continue;
        }
        let bytes = unsafe { std::slice::from_raw_parts(path.as_ptr() as *const u8, len as usize) };
        if std::str::from_utf8(bytes).ok().and_then(|p| p.rsplit('/').next()) == Some(name) {
            count += 1;
        }
    }
    count
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn this_test_binary_finds_itself_and_not_a_stranger() {
        let me = std::env::current_exe().unwrap();
        let name = me.file_name().unwrap().to_str().unwrap();
        assert!(running_named(name) >= 1);
        assert_eq!(running_named("no-such-process-ak820"), 0);
    }
}
