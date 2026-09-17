//! LaunchAgents: the plist the daemon runs under, and `launchctl`.
//!
//! The macOS half of what `windows/task.rs` is. Three labels matter:
//!
//! | label | what |
//! |---|---|
//! | [`AGENT`] | this daemon |
//! | [`NOWPLAYING`] | `nowplaying-macos.sh`, which the daemon replaces |
//! | [`TIMEKEEPER`] | `ak820-timekeeper.py`, which keeps the clock until Phase 4b |
//!
//! ⚠️ **Retiring the bash agent is `bootout` plus `disable`** (plan, Phase 4a,
//! review finding 5). `bootout` alone leaves the plist, and `RunAtLoad` brings
//! the bash back at the next login beside the daemon. `disable` persists across
//! logins, and rollback is `enable` plus `bootstrap` of that one label.
//!
//! ⚠️ `bootout` returns before teardown finishes, and bootstrapping a service
//! that is still being SIGTERMed fails with "Bootstrap failed: 5: Input/output
//! error" (`install-agents.sh`, `wait_gone`). Wait for it to go.

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

pub const AGENT: &str = "com.jdlien.ak820pro.agent";
pub const NOWPLAYING: &str = "com.jdlien.ak820pro.nowplaying";
pub const TIMEKEEPER: &str = "com.jdlien.ak820pro.timekeeper";

extern "C" {
    fn getuid() -> u32;
}

pub fn domain() -> String {
    format!("gui/{}", unsafe { getuid() })
}

pub fn plist_path(label: &str) -> PathBuf {
    let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    home.join("Library/LaunchAgents").join(format!("{label}.plist"))
}

/// What the daemon's plist says.
pub struct Definition<'a> {
    pub daemon: &'a Path,
    pub log: &'a Path,
    /// Where launchd sends stdout and stderr: only a panic ever lands there.
    pub stdio: &'a Path,
    /// Set when the helper is not beside the daemon (`--in-place` builds).
    pub dylib: Option<&'a Path>,
}

fn xml(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}

/// The plist, generated whole. ⚠️ Never edited in place: PlistBuddy strips
/// comments (CLAUDE.md), and a reinstall writes it again anyway.
///
/// ⚠️ **`ProcessType` is `Standard`.** The first live install copied the bash
/// agent's `Background`, and launchd then ran every thread of the daemon, of
/// its perl helper and of every `osascript` at **priority 4**. In the first 45
/// minutes on 2026-09-16, with high-performance screen sharing encoding, that
/// gave nine "no reply from the keyboard" timeouts (one reply arrived seconds
/// late), MediaRemote reporting a paused Music "stale" because the helper's
/// calls timed out, and both AppleScript reads timing out. The board's own
/// counters showed its loop never stalled past 36 ms. The daemon idles at 0%
/// CPU, so normal priority costs nothing; it only stops the scheduler starving
/// it under load.
pub fn plist(def: &Definition) -> String {
    let path = |p: &Path| xml(&p.display().to_string());
    let env = match def.dylib {
        Some(d) => format!(
            "\n    <key>EnvironmentVariables</key>\n    <dict>\n        <key>{}</key>\n        <string>{}</string>\n    </dict>\n",
            super::media::DYLIB_ENV,
            path(d)
        ),
        None => String::new(),
    };
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Written by `ak820 install`; rewritten by the next one. -->
    <key>Label</key>
    <string>{AGENT}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{daemon}</string>
        <string>--log</string>
        <string>{log}</string>
    </array>
{env}
    <key>RunAtLoad</key>
    <true/>

    <!-- The daemon runs until killed, so any exit is a failure; 30 s between
         restarts, as the bash agent had, so a refusal cannot spin. -->
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>{stdio}</string>
    <key>StandardErrorPath</key>
    <string>{stdio}</string>

    <!-- Standard, NOT Background: Background runs every thread at priority 4,
         and on a busy Mac that starved HID replies past the 2 s timeout, the
         helper's MediaRemote calls and osascript (measured 2026-09-16). -->
    <key>ProcessType</key>
    <string>Standard</string>
</dict>
</plist>
"#,
        daemon = path(def.daemon),
        log = path(def.log),
        stdio = path(def.stdio),
    )
}

/// A service's state, from `launchctl print`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Service {
    pub state: String,
    pub pid: Option<u32>,
    pub last_exit: Option<String>,
}

/// Read `launchctl print gui/UID/label`'s top-level fields. Pure.
pub fn parse_print(text: &str) -> Service {
    let mut service = Service { state: "unknown".into(), pid: None, last_exit: None };
    // Top-level fields are indented by exactly one tab; nested dicts repeat
    // `state = ...` deeper, and those are not the service's.
    for line in text.lines() {
        let Some(rest) = line.strip_prefix('\t') else { continue };
        if rest.starts_with('\t') {
            continue;
        }
        if let Some((k, v)) = rest.split_once(" = ") {
            match k {
                "state" => service.state = v.to_string(),
                "pid" => service.pid = v.parse().ok(),
                "last exit code" => service.last_exit = Some(v.to_string()),
                _ => {}
            }
        }
    }
    service
}

/// Is `label` listed as disabled by `launchctl print-disabled`? Pure.
pub fn parse_disabled(text: &str, label: &str) -> bool {
    let needle = format!("\"{label}\" => ");
    text.lines()
        .filter_map(|l| l.trim().strip_prefix(&needle))
        .any(|v| v == "disabled" || v == "true")
}

fn launchctl(args: &[&str]) -> Result<String, String> {
    let out = Command::new("/bin/launchctl")
        .args(args)
        .output()
        .map_err(|e| format!("launchctl: {e}"))?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    } else {
        let err = String::from_utf8_lossy(&out.stderr);
        let text = if err.trim().is_empty() { String::from_utf8_lossy(&out.stdout).into_owned() } else { err.into_owned() };
        Err(format!("launchctl {}: {}", args.join(" "), text.trim()))
    }
}

/// The loaded service, or `None` when launchd does not know the label.
pub fn print(label: &str) -> Option<Service> {
    launchctl(&["print", &format!("{}/{label}", domain())]).ok().map(|t| parse_print(&t))
}

pub fn is_disabled(label: &str) -> Result<bool, String> {
    Ok(parse_disabled(&launchctl(&["print-disabled", &domain()])?, label))
}

pub fn bootstrap(plist: &Path) -> Result<(), String> {
    launchctl(&["bootstrap", &domain(), &plist.display().to_string()]).map(|_| ())
}

/// Unload, and wait until launchd no longer knows the label.
pub fn bootout(label: &str, timeout: Duration) -> Result<(), String> {
    if print(label).is_none() {
        return Ok(());
    }
    let _ = launchctl(&["bootout", &format!("{}/{label}", domain())]);
    let until = Instant::now() + timeout;
    while print(label).is_some() {
        if Instant::now() >= until {
            return Err(format!("{label} was still loaded {} s after bootout", timeout.as_secs()));
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Ok(())
}

pub fn disable(label: &str) -> Result<(), String> {
    launchctl(&["disable", &format!("{}/{label}", domain())]).map(|_| ())
}

pub fn enable(label: &str) -> Result<(), String> {
    launchctl(&["enable", &format!("{}/{label}", domain())]).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    const PRINTED: &str = "gui/501/com.jdlien.ak820pro.nowplaying = {\n\tactive count = 1\n\tpath = /Users/x/Library/LaunchAgents/com.jdlien.ak820pro.nowplaying.plist\n\ttype = LaunchAgent\n\tstate = running\n\n\tprogram = /bin/bash\n\tpid = 1869\n\tlast exit code = (never exited)\n\n\tspawn type = daemon (3)\n\tendpoints = {\n\t\tstate = active\n\t}\n}\n";

    /// The shape captured from this Mac on 2026-09-16 (macOS 27.0): a nested
    /// `state = active` must not overwrite the service's `state = running`.
    #[test]
    fn a_captured_print_reads_state_pid_and_exit() {
        let s = parse_print(PRINTED);
        assert_eq!(s, Service { state: "running".into(), pid: Some(1869), last_exit: Some("(never exited)".into()) });
    }

    #[test]
    fn a_stopped_service_has_no_pid() {
        let s = parse_print("gui/501/x = {\n\tstate = not running\n\tlast exit code = 2\n}\n");
        assert_eq!((s.state.as_str(), s.pid, s.last_exit.as_deref()), ("not running", None, Some("2")));
    }

    #[test]
    fn disabled_is_read_per_label() {
        let text = "\tdisabled services = {\n\t\t\"com.docker.helper\" => enabled\n\t\t\"com.jdlien.ak820pro.nowplaying\" => disabled\n\t}\n";
        assert!(parse_disabled(text, NOWPLAYING));
        assert!(!parse_disabled(text, "com.docker.helper"));
        assert!(!parse_disabled(text, AGENT));
        assert!(parse_disabled("\t\t\"com.jdlien.ak820pro.nowplaying\" => true\n", NOWPLAYING), "older macOS spelling");
    }

    #[test]
    fn the_plist_escapes_paths_and_sets_the_helper_only_when_asked() {
        let p = plist(&Definition {
            daemon: Path::new("/Users/a&b/bin/ak820-agent"),
            log: Path::new("/Users/a&b/Library/Logs/ak820pro/ak820-agent.log"),
            stdio: Path::new("/tmp/stdio.log"),
            dylib: None,
        });
        assert!(p.contains("<string>/Users/a&amp;b/bin/ak820-agent</string>"));
        assert!(!p.contains("EnvironmentVariables"));
        assert!(p.contains(&format!("<string>{AGENT}</string>")));
        assert!(p.contains("<key>ProcessType</key>\n    <string>Standard</string>"), "Background starves it");

        let p = plist(&Definition {
            daemon: Path::new("/x/ak820-agent"),
            log: Path::new("/x/log"),
            stdio: Path::new("/x/stdio"),
            dylib: Some(Path::new("/y/nowplaying-mediaremote.dylib")),
        });
        assert!(p.contains("<key>AK820_MEDIAREMOTE_DYLIB</key>\n        <string>/y/nowplaying-mediaremote.dylib</string>"));
    }

    /// `plutil -lint` is what `install-agents.sh` trusts; hold the generated
    /// plist to it. Reads a temp file, loads nothing.
    #[test]
    fn the_plist_lints() {
        let path = std::env::temp_dir().join(format!("ak820-plist-{}.plist", std::process::id()));
        std::fs::write(
            &path,
            plist(&Definition {
                daemon: Path::new("/x/ak820-agent"),
                log: Path::new("/x/l"),
                stdio: Path::new("/x/s"),
                dylib: Some(Path::new("/y/d.dylib")),
            }),
        )
        .unwrap();
        let ok = Command::new("/usr/bin/plutil").arg("-lint").arg(&path).status().unwrap().success();
        let _ = std::fs::remove_file(&path);
        assert!(ok);
    }
}
