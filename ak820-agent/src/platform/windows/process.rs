//! Is a process with a given image name running? Through a Toolhelp
//! snapshot — the process list, nothing else, and in particular no device.
//!
//! Exists for one transition: moving the clock from the Python timekeeper to
//! the daemon. `Stop-ScheduledTask` ends `pythonw.exe`, but the `ak820ctl.exe`
//! it spawned for a transaction is a separate process that finishes on its
//! own — and finishes by **setting the clock**. Starting the daemon's clock
//! loop while that child is still alive is two clock writers, which is the
//! one thing this whole project exists to prevent. So `install --clock`
//! waits for it to be gone (the phase-3a/4a audit's finding 1).

use std::time::{Duration, Instant};

use windows::Win32::Foundation::CloseHandle;
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};

/// How many processes have this image name (case-insensitive).
pub fn running(image: &str) -> Result<usize, String> {
    let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) }
        .map_err(|e| format!("process snapshot: {e}"))?;
    let mut entry = PROCESSENTRY32W {
        dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
        ..Default::default()
    };
    let mut count = 0;
    let mut ok = unsafe { Process32FirstW(snapshot, &mut entry) }.is_ok();
    while ok {
        let name: String = String::from_utf16_lossy(
            &entry.szExeFile[..entry.szExeFile.iter().position(|&c| c == 0).unwrap_or(0)],
        );
        if name.eq_ignore_ascii_case(image) {
            count += 1;
        }
        ok = unsafe { Process32NextW(snapshot, &mut entry) }.is_ok();
    }
    unsafe { CloseHandle(snapshot).ok() };
    Ok(count)
}

/// Wait until no process with this image name is running.
pub fn wait_gone(image: &str, timeout: Duration) -> Result<(), String> {
    let until = Instant::now() + timeout;
    loop {
        let n = running(image)?;
        if n == 0 {
            return Ok(());
        }
        if Instant::now() >= until {
            return Err(format!(
                "{n} {image} process(es) still running after {} s",
                timeout.as_secs()
            ));
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn this_process_is_running_and_a_made_up_one_is_not() {
        let me = std::env::current_exe().unwrap();
        let name = me.file_name().unwrap().to_string_lossy().to_string();
        assert!(running(&name).unwrap() >= 1, "{name}");
        assert_eq!(running("ak820-no-such-process-4f2a.exe").unwrap(), 0);
        wait_gone("ak820-no-such-process-4f2a.exe", Duration::from_millis(10)).unwrap();
    }
}
