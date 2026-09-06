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
use windows::Win32::System::TaskScheduler::{
    IRegisteredTask, ITaskFolder, ITaskService, TaskScheduler, TASK_CREATE_OR_UPDATE,
    TASK_LOGON_INTERACTIVE_TOKEN, TASK_STATE_RUNNING,
};
use windows::Win32::System::Variant::VARIANT;

/// The folder `hostagent/install-agents-windows.ps1` registers both agents in.
pub const FOLDER: &str = "\\ak820pro";
/// The Python timekeeper's task — today's owner of the clock.
pub const TIMEKEEPER: &str = "AK820Pro-timekeeper";
/// The Python now-playing agent's task, which the daemon replaces.
pub const NOWPLAYING: &str = "AK820Pro-nowplaying";
/// The daemon's task.
pub const AGENT: &str = "AK820Pro-agent";
pub const AGENT_DESCRIPTION: &str =
    "AK820 Pro: the host agent -- now playing on the keyboard LCD (the clock follows).";

/// What the scheduler says about a registered task.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum State {
    Running,
    /// Not running; carries the raw `TASK_STATE` (ready, disabled, queued,
    /// unknown) for a caller that wants to print it.
    Idle(i32),
}

/// State plus the two things `-Status` printed: when it last ran, and how
/// that ended.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Info {
    pub state: State,
    /// Local time, `YYYY-MM-DD HH:MM:SS`; `None` if it has never run.
    pub last_run: Option<String>,
    /// `0x41301` while running, `0` after a clean exit, an HRESULT otherwise.
    pub last_result: u32,
}

/// The task's state, or `None` when the folder or the task is not registered.
///
/// `Err` means the scheduler could not be asked at all, which is a different
/// thing from "not installed" and is reported as such.
pub fn state(folder: &str, name: &str) -> Result<Option<State>, String> {
    Ok(info(folder, name)?.map(|i| i.state))
}

/// Everything `-Status` showed about one task.
pub fn info(folder: &str, name: &str) -> Result<Option<Info>, String> {
    with_service(|service| {
        let Some(task) = get_task(service, folder, name)? else {
            return Ok(None);
        };
        let st = unsafe { task.State() }.map_err(|e| format!("state of {name}: {e}"))?;
        let last_run = unsafe { task.LastRunTime() }
            .ok()
            .filter(|&t| t != 0.0)
            .and_then(ole_date);
        let last_result = unsafe { task.LastTaskResult() }.unwrap_or(0) as u32;
        Ok(Some(Info {
            state: if st == TASK_STATE_RUNNING {
                State::Running
            } else {
                State::Idle(st.0)
            },
            last_run,
            last_result,
        }))
    })
}

/// Is the Python timekeeper running? `None` when it is not installed.
pub fn timekeeper_running() -> Result<Option<bool>, String> {
    Ok(state(FOLDER, TIMEKEEPER)?.map(|s| s == State::Running))
}

// ---------------------------------------------------------------------------
// Registration, from XML
// ---------------------------------------------------------------------------

/// What a task runs, as whom, and where.
pub struct Definition<'a> {
    pub description: &'a str,
    /// `DOMAIN\user`, as the PowerShell installer spells it.
    pub user: &'a str,
    pub command: &'a str,
    pub arguments: &'a str,
    pub working_directory: &'a str,
}

/// The task as a Task Scheduler XML document.
///
/// Element for element what `Export-ScheduledTask` produced for the task the
/// PowerShell installer registered — the test below pins that: interactive
/// token, logon trigger for the user, both battery settings off, no execution
/// time limit, restart 999 times at one-minute intervals, ignore new
/// instances, start when available. A document is a string a test can read;
/// a definition built through a dozen COM interfaces is not.
pub fn task_xml(d: &Definition) -> String {
    let user = xml_escape(d.user);
    format!(
        concat!(
            "<?xml version=\"1.0\" encoding=\"UTF-16\"?>\n",
            "<Task version=\"1.3\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">\n",
            "  <RegistrationInfo>\n",
            "    <Description>{description}</Description>\n",
            "  </RegistrationInfo>\n",
            "  <Principals>\n",
            "    <Principal id=\"Author\">\n",
            "      <UserId>{user}</UserId>\n",
            "      <LogonType>InteractiveToken</LogonType>\n",
            "    </Principal>\n",
            "  </Principals>\n",
            "  <Settings>\n",
            "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n",
            "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n",
            "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n",
            "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n",
            "    <RestartOnFailure>\n",
            "      <Count>999</Count>\n",
            "      <Interval>PT1M</Interval>\n",
            "    </RestartOnFailure>\n",
            "    <StartWhenAvailable>true</StartWhenAvailable>\n",
            "    <IdleSettings>\n",
            "      <Duration>PT10M</Duration>\n",
            "      <WaitTimeout>PT1H</WaitTimeout>\n",
            "      <StopOnIdleEnd>true</StopOnIdleEnd>\n",
            "      <RestartOnIdle>false</RestartOnIdle>\n",
            "    </IdleSettings>\n",
            "    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>\n",
            "  </Settings>\n",
            "  <Triggers>\n",
            "    <LogonTrigger>\n",
            "      <UserId>{user}</UserId>\n",
            "    </LogonTrigger>\n",
            "  </Triggers>\n",
            "  <Actions Context=\"Author\">\n",
            "    <Exec>\n",
            "      <Command>{command}</Command>\n",
            "      <Arguments>{arguments}</Arguments>\n",
            "      <WorkingDirectory>{working_directory}</WorkingDirectory>\n",
            "    </Exec>\n",
            "  </Actions>\n",
            "</Task>"
        ),
        description = xml_escape(d.description),
        user = user,
        command = xml_escape(d.command),
        arguments = xml_escape(d.arguments),
        working_directory = xml_escape(d.working_directory),
    )
}

fn xml_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            c => out.push(c),
        }
    }
    out
}

/// Register (or replace) a task in [`FOLDER`] from its XML, to run as the
/// interactive user. Creates the folder if it is missing.
pub fn register(name: &str, xml: &str) -> Result<(), String> {
    with_service(|service| {
        let folder = match unsafe { service.GetFolder(&BSTR::from(FOLDER)) } {
            Ok(f) => f,
            Err(e) if is_missing(&e) => {
                let root = unsafe { service.GetFolder(&BSTR::from("\\")) }
                    .map_err(|e| format!("Task Scheduler root folder: {e}"))?;
                unsafe { root.CreateFolder(&BSTR::from(FOLDER.trim_start_matches('\\')), &VARIANT::default()) }
                    .map_err(|e| format!("creating folder {FOLDER}: {e}"))?
            }
            Err(e) => return Err(format!("Task Scheduler folder {FOLDER}: {e}")),
        };
        unsafe {
            folder.RegisterTask(
                &BSTR::from(name),
                &BSTR::from(xml),
                TASK_CREATE_OR_UPDATE.0,
                &VARIANT::default(),
                &VARIANT::default(),
                TASK_LOGON_INTERACTIVE_TOKEN,
                &VARIANT::default(),
            )
        }
        .map_err(|e| format!("registering {name}: {e}"))?;
        Ok(())
    })
}

/// Start a registered task now, as `Start-ScheduledTask` does.
pub fn start(folder: &str, name: &str) -> Result<(), String> {
    with_service(|service| {
        let task = get_task(service, folder, name)?.ok_or_else(|| format!("{name} is not registered"))?;
        unsafe { task.Run(&VARIANT::default()) }.map_err(|e| format!("starting {name}: {e}"))?;
        Ok(())
    })
}

/// Stop every running instance of a task, as `Stop-ScheduledTask` does. Not
/// an error if it is not running or not registered.
pub fn stop(folder: &str, name: &str) -> Result<(), String> {
    with_service(|service| {
        if let Some(task) = get_task(service, folder, name)? {
            unsafe { task.Stop(0) }.map_err(|e| format!("stopping {name}: {e}"))?;
        }
        Ok(())
    })
}

/// Unregister a task. Not an error if it is not registered.
pub fn delete(folder: &str, name: &str) -> Result<(), String> {
    with_service(|service| {
        let f = match unsafe { service.GetFolder(&BSTR::from(folder)) } {
            Ok(f) => f,
            Err(e) if is_missing(&e) => return Ok(()),
            Err(e) => return Err(format!("Task Scheduler folder {folder}: {e}")),
        };
        match unsafe { f.DeleteTask(&BSTR::from(name), 0) } {
            Ok(()) => Ok(()),
            Err(e) if is_missing(&e) => Ok(()),
            Err(e) => Err(format!("removing {name}: {e}")),
        }
    })
}

// ---------------------------------------------------------------------------
// The COM plumbing
// ---------------------------------------------------------------------------

/// Initialise COM on this thread, connect to the scheduler, run `f`, and
/// balance the initialisation. Every COM object `f` makes is dropped before
/// `CoUninitialize` because they are locals of `f`.
fn with_service<T>(f: impl FnOnce(&ITaskService) -> Result<T, String>) -> Result<T, String> {
    unsafe {
        // S_FALSE — already initialised on this thread — is fine.
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|e| format!("COM initialisation: {e}"))?;
    }
    let result = (|| {
        let service: ITaskService =
            unsafe { CoCreateInstance(&TaskScheduler, None, CLSCTX_INPROC_SERVER) }
                .map_err(|e| format!("Task Scheduler service: {e}"))?;
        unsafe {
            service.Connect(
                &VARIANT::default(),
                &VARIANT::default(),
                &VARIANT::default(),
                &VARIANT::default(),
            )
        }
        .map_err(|e| format!("Task Scheduler connect: {e}"))?;
        f(&service)
    })();
    unsafe { CoUninitialize() };
    result
}

fn get_task(service: &ITaskService, folder: &str, name: &str) -> Result<Option<IRegisteredTask>, String> {
    let folder: ITaskFolder = match unsafe { service.GetFolder(&BSTR::from(folder)) } {
        Ok(f) => f,
        Err(e) if is_missing(&e) => return Ok(None),
        Err(e) => return Err(format!("Task Scheduler folder {folder}: {e}")),
    };
    match unsafe { folder.GetTask(&BSTR::from(name)) } {
        Ok(t) => Ok(Some(t)),
        Err(e) if is_missing(&e) => Ok(None),
        Err(e) => Err(format!("Task Scheduler task {name}: {e}")),
    }
}

fn is_missing(e: &windows::core::Error) -> bool {
    e.code() == HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0)
        || e.code() == HRESULT::from_win32(ERROR_PATH_NOT_FOUND.0)
}

/// An OLE automation date — days since 1899-12-30, already in local time,
/// which is what `IRegisteredTask::LastRunTime` returns — as text.
///
/// Plain arithmetic rather than `VariantTimeToSystemTime`: the value is a
/// day count with a fraction, and the civil-date helper the clock uses
/// turns a second count into a date. 25569 is 1899-12-30 to 1970-01-01.
fn ole_date(date: f64) -> Option<String> {
    if !date.is_finite() || date < 0.0 {
        return None;
    }
    let days = date.floor();
    let secs = ((date - days) * 86400.0).round() as i64;
    let unix = (days as i64 - 25569) * 86400 + secs;
    let lt = crate::clock::host::utc_local(unix);
    Some(format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
        lt.year, lt.month, lt.day, lt.hour, lt.minute, lt.second
    ))
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

    /// `Export-ScheduledTask -TaskPath '\ak820pro\' -TaskName 'AK820Pro-nowplaying'`
    /// on 2026-09-06, for the task the PowerShell installer registered — with
    /// the service's own additions taken out: the `<URI>` it adds, and the
    /// principal's account name, which it had resolved to a SID. Everything
    /// the installer set is here, element for element and in the service's
    /// own order.
    const EXPORTED: &str = "<?xml version=\"1.0\" encoding=\"UTF-16\"?>\n\
<Task version=\"1.3\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">\n\
\x20 <RegistrationInfo>\n\
\x20   <Description>AK820 Pro: push the currently playing track to the keyboard LCD.</Description>\n\
\x20 </RegistrationInfo>\n\
\x20 <Principals>\n\
\x20   <Principal id=\"Author\">\n\
\x20     <UserId>GREMLIN\\jdlien</UserId>\n\
\x20     <LogonType>InteractiveToken</LogonType>\n\
\x20   </Principal>\n\
\x20 </Principals>\n\
\x20 <Settings>\n\
\x20   <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n\
\x20   <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n\
\x20   <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n\
\x20   <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n\
\x20   <RestartOnFailure>\n\
\x20     <Count>999</Count>\n\
\x20     <Interval>PT1M</Interval>\n\
\x20   </RestartOnFailure>\n\
\x20   <StartWhenAvailable>true</StartWhenAvailable>\n\
\x20   <IdleSettings>\n\
\x20     <Duration>PT10M</Duration>\n\
\x20     <WaitTimeout>PT1H</WaitTimeout>\n\
\x20     <StopOnIdleEnd>true</StopOnIdleEnd>\n\
\x20     <RestartOnIdle>false</RestartOnIdle>\n\
\x20   </IdleSettings>\n\
\x20   <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>\n\
\x20 </Settings>\n\
\x20 <Triggers>\n\
\x20   <LogonTrigger>\n\
\x20     <UserId>GREMLIN\\jdlien</UserId>\n\
\x20   </LogonTrigger>\n\
\x20 </Triggers>\n\
\x20 <Actions Context=\"Author\">\n\
\x20   <Exec>\n\
\x20     <Command>C:\\Users\\jdlien\\code\\ak820-pro\\venv-win\\Scripts\\pythonw.exe</Command>\n\
\x20     <Arguments>&quot;C:\\Users\\jdlien\\code\\ak820-pro\\hostagent\\nowplaying-windows.py&quot; --log C:\\Users\\jdlien\\AppData\\Local\\ak820pro\\ak820pro-nowplaying.log</Arguments>\n\
\x20     <WorkingDirectory>C:\\Users\\jdlien\\code\\ak820-pro</WorkingDirectory>\n\
\x20   </Exec>\n\
\x20 </Actions>\n\
</Task>";

    /// The XML this builds for the Python task's own values is the document
    /// the scheduler exported for it. That is the parity test for the
    /// installer: same principal, trigger, battery settings, time limit,
    /// restart policy, instance policy, and start-when-available.
    #[test]
    fn the_xml_is_what_the_scheduler_exported_for_the_powershell_task() {
        let xml = task_xml(&Definition {
            description: "AK820 Pro: push the currently playing track to the keyboard LCD.",
            user: "GREMLIN\\jdlien",
            command: "C:\\Users\\jdlien\\code\\ak820-pro\\venv-win\\Scripts\\pythonw.exe",
            arguments: "\"C:\\Users\\jdlien\\code\\ak820-pro\\hostagent\\nowplaying-windows.py\" --log C:\\Users\\jdlien\\AppData\\Local\\ak820pro\\ak820pro-nowplaying.log",
            working_directory: "C:\\Users\\jdlien\\code\\ak820-pro",
        });
        assert_eq!(xml, EXPORTED);
    }

    #[test]
    fn xml_special_characters_are_escaped() {
        let xml = task_xml(&Definition {
            description: "a & b <c>",
            user: "D\\u",
            command: "C:\\x y\\ak820-agent.exe",
            arguments: "--log \"C:\\a & b\\log\"",
            working_directory: "C:\\x y",
        });
        assert!(xml.contains("<Description>a &amp; b &lt;c&gt;</Description>"));
        assert!(xml.contains("<Arguments>--log &quot;C:\\a &amp; b\\log&quot;</Arguments>"));
    }

    /// 1899-12-30 is day 0; 2026-09-06 is day 46271; a half day is noon.
    #[test]
    fn ole_dates_are_days_since_1899_with_a_fraction() {
        assert_eq!(ole_date(0.0).as_deref(), Some("1899-12-30 00:00:00"));
        assert_eq!(ole_date(25569.0).as_deref(), Some("1970-01-01 00:00:00"));
        assert_eq!(ole_date(46271.0).as_deref(), Some("2026-09-06 00:00:00"));
        assert_eq!(ole_date(46271.5).as_deref(), Some("2026-09-06 12:00:00"));
        // 23:00:23, the Python tasks' last start
        assert_eq!(ole_date(46270.0 + (23.0 * 3600.0 + 23.0) / 86400.0).as_deref(), Some("2026-09-05 23:00:23"));
        assert_eq!(ole_date(f64::NAN), None);
    }
}
