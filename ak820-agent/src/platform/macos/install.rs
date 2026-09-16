//! `ak820 install` / `uninstall` / `status` on macOS: Phase 4a, now-playing only.
//!
//! The Windows installer's shape (`windows/cli.rs`), with launchd's mechanics:
//!
//! - **Stage before stopping anything.** Copies land beside their destinations
//!   as `.new` and the plist is linted before any agent is touched, so a full
//!   disk or a bad path leaves whatever was running as it was (the Windows
//!   phase-3a/4a audit's finding 3).
//! - **Retire the bash agent with `bootout` plus `disable`**, and wait for its
//!   lock to be released, before the daemon starts. The daemon takes the same
//!   lock and would refuse beside it.
//! - **Leave the Python timekeeper alone.** It owns the clock until Phase 4b,
//!   and `--clock` is refused. Its `ak820ctl` still seizes the device at each
//!   sync; a busy push logs `[warn]`, and 4a's gate counts those.
//! - **Every failure after something was stopped puts something back:** the
//!   previous daemon if there was one, otherwise the bash agent.
//! - **Strip `com.apple.quarantine`** from what it installs: a quarantined
//!   helper dylib hangs perl behind a Gatekeeper dialog, at every restart (S3).
//!
//! `ak820 uninstall` is the rollback, and does it rather than describing it:
//! the daemon's agent is removed, and the bash agent is enabled and started
//! again (unless `--keep-bash-off`).

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

use super::launchd::{self, AGENT, NOWPLAYING, TIMEKEEPER};
use super::{daemon, instance, media};

const WAIT: Duration = Duration::from_secs(20);

extern "C" {
    fn removexattr(path: *const std::os::raw::c_char, name: *const std::os::raw::c_char, options: i32) -> i32;
}

/// Remove the quarantine attribute. `Ok(true)` if there was one.
fn unquarantine(path: &Path) -> Result<bool, String> {
    use std::os::unix::ffi::OsStrExt;
    let c = std::ffi::CString::new(path.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
    let rc = unsafe { removexattr(c.as_ptr(), c"com.apple.quarantine".as_ptr(), 0) };
    if rc == 0 {
        return Ok(true);
    }
    match std::io::Error::last_os_error().raw_os_error() {
        Some(93) => Ok(false), // ENOATTR: never quarantined
        _ => Err(format!("removing the quarantine attribute from {}: {}", path.display(), std::io::Error::last_os_error())),
    }
}

/// Is this binary signed by a Developer ID? TCC keys Automation consent on the
/// designated requirement, so an ad-hoc signature re-asks at every rebuild (S3).
fn developer_id(path: &Path) -> Option<String> {
    let out = Command::new("/usr/bin/codesign").args(["-dv", "--verbose=2"]).arg(path).output().ok()?;
    String::from_utf8_lossy(&out.stderr)
        .lines()
        .find_map(|l| l.strip_prefix("Authority=Developer ID Application: ").map(str::to_owned))
}

fn same_file(a: &Path, b: &Path) -> bool {
    matches!((a.canonicalize(), b.canonicalize()), (Ok(x), Ok(y)) if x == y)
}

fn started_stamp(path: &Path) -> Option<String> {
    crate::status::read(path)?.into_iter().find(|(k, _)| k == "started").map(|(_, v)| v)
}

fn wait_unlocked(timeout: Duration) -> Result<(), String> {
    let until = Instant::now() + timeout;
    while let Some((pid, _)) = instance::any_holder() {
        if Instant::now() >= until {
            return Err(format!("pid {pid} still holds the now-playing lock {} s later", timeout.as_secs()));
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Ok(())
}

pub fn install(flags: &[&str]) -> Result<(), String> {
    let mut in_place = false;
    let mut dylib_flag: Option<PathBuf> = None;
    let mut it = flags.iter();
    while let Some(flag) = it.next() {
        match *flag {
            "--in-place" => in_place = true,
            "--dylib" => dylib_flag = Some(it.next().ok_or("--dylib takes a path")?.into()),
            "--clock" => {
                return Err("install: --clock is not built on macOS yet; the Python timekeeper keeps the clock (plan, Phase 4b)".into())
            }
            other => return Err(format!("install: unknown flag {other}; the flags are --in-place and --dylib PATH")),
        }
    }

    let here = std::env::current_exe().map_err(|e| format!("locating ak820: {e}"))?;
    let here_dir = here.parent().ok_or("ak820 has no parent directory")?.to_path_buf();
    let daemon_src = here_dir.join("ak820-agent");
    if !daemon_src.is_file() {
        return Err(format!("{} must sit beside ak820 (both are built together)", daemon_src.display()));
    }
    let dylib_src = dylib_flag
        .or_else(|| std::env::var_os(media::DYLIB_ENV).map(PathBuf::from))
        .unwrap_or_else(|| here_dir.join(media::DYLIB));
    let dylib_src = dylib_src.canonicalize().map_err(|e| {
        format!(
            "the MediaRemote helper {}: {e}; pass --dylib PATH (build it from ../streamdeck-now-playing)",
            dylib_src.display()
        )
    })?;

    // ---- stage: nothing running is touched yet ----
    let state = daemon::state_dir();
    let logs = daemon::log_dir();
    for d in [&state, &logs] {
        std::fs::create_dir_all(d).map_err(|e| format!("{}: {e}", d.display()))?;
    }
    let (daemon_path, dylib_path, staged) = if in_place {
        (daemon_src.clone(), dylib_src.clone(), Vec::new())
    } else {
        let bin = state.join("bin");
        std::fs::create_dir_all(&bin).map_err(|e| format!("{}: {e}", bin.display()))?;
        let mut staged = Vec::new();
        for (src, name) in [(&daemon_src, "ak820-agent"), (&here, "ak820"), (&dylib_src, media::DYLIB)] {
            let dst = bin.join(name);
            if same_file(src, &dst) {
                continue;
            }
            let tmp = bin.join(format!("{name}.new"));
            std::fs::copy(src, &tmp).map_err(|e| format!("copying to {}: {e}", tmp.display()))?;
            staged.push((tmp, dst));
        }
        (bin.join("ak820-agent"), bin.join(media::DYLIB), staged)
    };
    // In place, the helper is used where it is, so that copy is the one to
    // clear; otherwise only this installer's own copies are touched.
    let in_use = in_place.then_some(dylib_src.as_path());
    for p in staged.iter().map(|(tmp, _)| tmp.as_path()).chain(in_use) {
        if unquarantine(p)? {
            println!("removed the quarantine attribute from {}", p.display());
        }
    }
    let log = logs.join("ak820-agent.log");
    let stdio = logs.join("ak820-agent.stdio.log");
    let beside = daemon_path.parent().map(|d| d.join(media::DYLIB));
    let plist_text = launchd::plist(&launchd::Definition {
        daemon: &daemon_path,
        log: &log,
        stdio: &stdio,
        dylib: (beside.as_deref() != Some(dylib_path.as_path())).then_some(dylib_path.as_path()),
    });
    let plist = launchd::plist_path(AGENT);
    if let Some(dir) = plist.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    // Staged outside ~/Library/LaunchAgents: launchd scans that directory at
    // login, and a failed install must not leave a half-named plist there.
    let plist_new = state.join(format!("{AGENT}.plist.new"));
    std::fs::write(&plist_new, &plist_text).map_err(|e| format!("{}: {e}", plist_new.display()))?;
    let lint = Command::new("/usr/bin/plutil").arg("-lint").arg(&plist_new).output().map_err(|e| format!("plutil: {e}"))?;
    if !lint.status.success() {
        return Err(format!("the generated plist does not lint: {}", String::from_utf8_lossy(&lint.stdout).trim()));
    }
    match developer_id(&daemon_src) {
        Some(who) => println!("ak820-agent is signed by Developer ID Application: {who}"),
        None => println!(
            "⚠️  ak820-agent is not signed with a Developer ID: Automation consent is tied to the\n\
             \x20   signature, so every rebuild asks again. Sign it first (plan, S3):\n\
             \x20   scripts/sign-agent-macos.sh"
        ),
    }

    // ---- from here an agent may be stopped, so failures put one back ----
    let previous = launchd::print(AGENT).is_some() && plist.is_file();
    let bash_plist = launchd::plist_path(NOWPLAYING);
    let put_back = |why: String| -> String {
        let result = if previous {
            launchd::bootstrap(&plist).map(|()| "the previous daemon was started again")
        } else if bash_plist.is_file() {
            launchd::enable(NOWPLAYING)
                .and_then(|()| launchd::bootstrap(&bash_plist))
                .map(|()| "the bash now-playing agent was started again")
        } else {
            return why;
        };
        match result {
            Ok(what) => format!("{why}; {what}"),
            Err(e) => format!("{why}; and putting the previous agent back failed too: {e}"),
        }
    };

    launchd::bootout(AGENT, WAIT)?;
    for (tmp, dst) in &staged {
        if let Err(e) = std::fs::rename(tmp, dst) {
            return Err(put_back(format!("replacing {}: {e}", dst.display())));
        }
    }
    if !staged.is_empty() {
        println!("installed ak820-agent, ak820 and {} in {}", media::DYLIB, daemon_path.parent().unwrap_or(&state).display());
    }

    // The bash agent: bootout AND disable, or it returns at the next login.
    if launchd::print(NOWPLAYING).is_some() {
        if let Err(e) = launchd::bootout(NOWPLAYING, WAIT) {
            return Err(put_back(e));
        }
        println!("stopped {NOWPLAYING}");
    }
    if bash_plist.is_file() {
        if let Err(e) = launchd::disable(NOWPLAYING) {
            return Err(put_back(e));
        }
        println!("disabled {NOWPLAYING}, so it stays off across logins (its plist is left for `ak820 uninstall`)");
    }
    if let Err(e) = wait_unlocked(Duration::from_secs(10)) {
        return Err(put_back(e));
    }

    match launchd::print(TIMEKEEPER) {
        Some(_) => println!("left {TIMEKEEPER} alone: it keeps the clock"),
        None => println!("⚠️  {TIMEKEEPER} is not loaded, and this daemon does not sync the clock yet: nothing will"),
    }

    let status_path = state.join("ak820-agent.status");
    let before = started_stamp(&status_path);
    if let Err(e) = std::fs::rename(&plist_new, &plist) {
        return Err(put_back(format!("writing {}: {e}", plist.display())));
    }
    if let Err(e) = launchd::bootstrap(&plist) {
        return Err(put_back(e));
    }
    println!("started {AGENT} from {}\nlog: {}", plist.display(), log.display());

    let until = Instant::now() + WAIT;
    while started_stamp(&status_path) == before && Instant::now() < until {
        std::thread::sleep(Duration::from_millis(250));
    }
    println!();
    if started_stamp(&status_path) == before {
        println!("(the daemon has not written its status file yet; `ak820 status` in a moment)\n");
    }
    status()
}

pub fn uninstall(flags: &[&str]) -> Result<(), String> {
    let mut restore_bash = true;
    for flag in flags {
        match *flag {
            "--keep-bash-off" => restore_bash = false,
            other => return Err(format!("uninstall: unknown flag {other}; the flag is --keep-bash-off")),
        }
    }
    let plist = launchd::plist_path(AGENT);
    if launchd::print(AGENT).is_some() {
        launchd::bootout(AGENT, WAIT)?;
        println!("stopped {AGENT}");
    } else {
        println!("{AGENT} was not loaded");
    }
    if plist.is_file() {
        std::fs::remove_file(&plist).map_err(|e| format!("{}: {e}", plist.display()))?;
        println!("removed {}", plist.display());
    }
    println!("binaries, log and status left in {} and {}", daemon::state_dir().display(), daemon::log_dir().display());

    let bash_plist = launchd::plist_path(NOWPLAYING);
    if !restore_bash {
        println!("left {NOWPLAYING} as it is (--keep-bash-off)");
    } else if bash_plist.is_file() {
        launchd::enable(NOWPLAYING)?;
        if launchd::print(NOWPLAYING).is_none() {
            launchd::bootstrap(&bash_plist)?;
        }
        println!("enabled and started {NOWPLAYING} again");
    } else {
        println!("no {NOWPLAYING} plist to put back: `hostagent/install-agents.sh --only nowplaying` installs it");
    }
    Ok(())
}

/// The three agents' states, what the daemon last did, and its log's tail.
pub fn status() -> Result<(), String> {
    for label in [AGENT, TIMEKEEPER, NOWPLAYING] {
        let disabled = launchd::is_disabled(label).unwrap_or(false);
        match launchd::print(label) {
            None if disabled => println!("{label:<34} disabled"),
            None => println!("{label:<34} not loaded"),
            Some(s) => println!(
                "{label:<34} {:<12} pid {:<6} last exit {}{}",
                s.state,
                s.pid.map(|p| p.to_string()).unwrap_or_else(|| "-".into()),
                s.last_exit.as_deref().unwrap_or("-"),
                if disabled { "  (disabled at login)" } else { "" }
            ),
        }
    }
    if let Some((pid, path)) = instance::any_holder() {
        println!("now-playing lock held by pid {pid} ({})", path.display());
    }

    let status_path = daemon::state_dir().join("ak820-agent.status");
    println!();
    match crate::status::read(&status_path) {
        None => println!("no status file yet at {}", status_path.display()),
        Some(pairs) => {
            for (k, v) in pairs {
                println!("{k:<18} {v}");
            }
        }
    }
    let log = daemon::log_dir().join("ak820-agent.log");
    if let Ok(text) = std::fs::read_to_string(&log) {
        println!("\nlast lines of {}:", log.display());
        let lines: Vec<&str> = text.lines().collect();
        for line in lines.iter().rev().take(8).rev() {
            println!("  {line}");
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quarantine_is_stripped_and_absence_is_fine() {
        let p = std::env::temp_dir().join(format!("ak820-q-{}", std::process::id()));
        std::fs::write(&p, b"x").unwrap();
        assert_eq!(unquarantine(&p), Ok(false));
        let set = Command::new("/usr/bin/xattr").args(["-w", "com.apple.quarantine", "0081;00000000;test;"]).arg(&p).status().unwrap();
        assert!(set.success());
        assert_eq!(unquarantine(&p), Ok(true));
        assert_eq!(unquarantine(&p), Ok(false));
        let _ = std::fs::remove_file(&p);
    }
}
