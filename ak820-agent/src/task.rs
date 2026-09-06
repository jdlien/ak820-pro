//! Scheduled Task state, through the Task Scheduler COM API.
//!
//! Exists because of the phase-2 audit's P1. `ak820 clock` reads the board's
//! clock, and its reply reaches **every** open handle — including the Python
//! timekeeper's, whose `ak820ctl xfer()` takes the first report that arrives.
//! A well-formed GET reply of ours becomes one of its five measurement
//! samples, paired with *its* timestamps, and can win its min-RTT selection
//! precisely because it did not include its round trip. The interference is
//! bidirectional, and no mutex of ours can see a Python process. What can:
//! whether the Scheduled Task that runs it is `Running`.
//!
//! The COM API rather than `schtasks /Query`, because that command's output
//! is localized and a parse of it would silently pass on a non-English
//! Windows. This opens no device; it talks to the Task Scheduler service and
//! nothing else. Phase 4's self-installation will use the same API.

use windows::core::{BSTR, HRESULT};
use windows::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED,
};
use windows::Win32::System::TaskScheduler::{ITaskService, TaskScheduler, TASK_STATE_RUNNING};
use windows::Win32::System::Variant::VARIANT;

/// The folder `hostagent/install-agents-windows.ps1` registers both agents in.
pub const FOLDER: &str = "\\ak820pro";
/// The Python timekeeper's task — today's owner of the clock.
pub const TIMEKEEPER: &str = "AK820Pro-timekeeper";
/// The Python now-playing agent's task.
pub const NOWPLAYING: &str = "AK820Pro-nowplaying";

/// What the scheduler says about a registered task.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum State {
    Running,
    /// Not running; carries the raw `TASK_STATE` (ready, disabled, queued,
    /// unknown) for a caller that wants to print it.
    Idle(i32),
}

/// The task's state, or `None` when the folder or the task is not registered.
///
/// `Err` means the scheduler could not be asked at all, which is a different
/// thing from "not installed" and is reported as such.
pub fn state(folder: &str, name: &str) -> Result<Option<State>, String> {
    unsafe {
        // S_FALSE — already initialised on this thread — is fine.
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|e| format!("COM initialisation: {e}"))?;
        // Every COM object is a local of `query`, dropped before this returns.
        let result = query(folder, name);
        CoUninitialize();
        result
    }
}

unsafe fn query(folder: &str, name: &str) -> Result<Option<State>, String> {
    let service: ITaskService = CoCreateInstance(&TaskScheduler, None, CLSCTX_INPROC_SERVER)
        .map_err(|e| format!("Task Scheduler service: {e}"))?;
    service
        .Connect(
            &VARIANT::default(),
            &VARIANT::default(),
            &VARIANT::default(),
            &VARIANT::default(),
        )
        .map_err(|e| format!("Task Scheduler connect: {e}"))?;
    let folder = match service.GetFolder(&BSTR::from(folder)) {
        Ok(f) => f,
        Err(e) if is_missing(&e) => return Ok(None),
        Err(e) => return Err(format!("Task Scheduler folder {folder}: {e}")),
    };
    let task = match folder.GetTask(&BSTR::from(name)) {
        Ok(t) => t,
        Err(e) if is_missing(&e) => return Ok(None),
        Err(e) => return Err(format!("Task Scheduler task {name}: {e}")),
    };
    let st = task
        .State()
        .map_err(|e| format!("Task Scheduler state of {name}: {e}"))?;
    Ok(Some(if st == TASK_STATE_RUNNING {
        State::Running
    } else {
        State::Idle(st.0)
    }))
}

fn is_missing(e: &windows::core::Error) -> bool {
    e.code() == HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0)
        || e.code() == HRESULT::from_win32(ERROR_PATH_NOT_FOUND.0)
}

/// Is the Python timekeeper running? `None` when it is not installed.
pub fn timekeeper_running() -> Result<Option<bool>, String> {
    Ok(state(FOLDER, TIMEKEEPER)?.map(|s| s == State::Running))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A task that does not exist is "not installed", not an error — and
    /// neither is a folder that does not exist.
    #[test]
    fn an_unregistered_task_is_none_not_an_error() {
        assert_eq!(state(FOLDER, "AK820Pro-no-such-task-4f2a").unwrap(), None);
        assert_eq!(state("\\ak820pro-no-such-folder-4f2a", "x").unwrap(), None);
    }

    /// The scheduler can be asked at all, whatever it answers on this machine.
    #[test]
    fn the_scheduler_answers() {
        timekeeper_running().unwrap();
    }

    /// Asking twice on one thread is fine: COM initialisation is balanced.
    #[test]
    fn asking_twice_is_fine() {
        timekeeper_running().unwrap();
        timekeeper_running().unwrap();
    }
}
