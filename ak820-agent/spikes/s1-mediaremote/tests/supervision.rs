//! The supervision rules, against a fake helper, through the real binary.
//!
//! Each test runs `s1 --exec fake_helper.py MODE` with the limits shrunk to
//! fractions of a second and reads its narration. The SIGSTOP test has to be a
//! separate process: it freezes the supervisor itself.

use std::process::{Command, Stdio};
use std::time::Duration;

const S1: &str = env!("CARGO_BIN_EXE_s1");

fn fake() -> String {
    format!("{}/tests/fake_helper.py", env!("CARGO_MANIFEST_DIR"))
}

/// Run to completion; return stdout lines.
fn run(mode: &str, flags: &[&str]) -> Vec<String> {
    let mut args = vec![
        "--exec".to_string(),
        "/usr/bin/python3".into(),
        fake(),
        mode.into(),
    ];
    args.extend(flags.iter().map(|s| s.to_string()));
    let out = Command::new(S1).args(&args).output().expect("running s1");
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(str::to_owned)
        .collect()
}

fn count(lines: &[String], needle: &str) -> usize {
    lines.iter().filter(|l| l.contains(needle)).count()
}

fn health(lines: &[String]) -> Vec<bool> {
    lines
        .iter()
        .filter_map(|l| l.split("failed=").nth(1))
        .map(|r| r.starts_with("true"))
        .collect()
}

const FAST: &[&str] = &[
    "--silence-limit",
    "1.5",
    "--restart-min",
    "0.2",
    "--restart-max",
    "1.0",
    "--healthy-run",
    "30",
    "--check-every",
    "0.05",
    "--settle",
    "0.05",
    "--health-every",
    "0.1",
];

/// `fatal` + exit(3) is the designed recovery: restarted, and never "failed",
/// because the restart lands well inside the silence limit.
#[test]
fn a_fatal_exit_restarts_without_failing() {
    let mut flags = FAST.to_vec();
    flags.extend(["--seconds", "4"]);
    let lines = run("fatal", &flags);
    assert!(count(&lines, "Fatal {") >= 2, "{lines:#?}");
    assert!(count(&lines, "code: Some(3)") >= 2, "{lines:#?}");
    assert!(count(&lines, "Started {") >= 3, "{lines:#?}");
    assert!(
        health(&lines).iter().all(|f| !f),
        "a designed restart must not read as failed:\n{lines:#?}"
    );
    assert_eq!(count(&lines, "KilledForSilence"), 0);
}

/// Alive and silent is the wedge: killed, and "failed" once the limit passes.
#[test]
fn a_silent_helper_is_killed_and_the_source_fails() {
    let mut flags = FAST.to_vec();
    flags.extend(["--seconds", "4"]);
    let lines = run("silent", &flags);
    assert!(count(&lines, "KilledForSilence") >= 1, "{lines:#?}");
    assert!(count(&lines, "signal: Some(9)") >= 1, "{lines:#?}");
    assert!(
        health(&lines).iter().any(|f| *f),
        "silence past the limit must read as failed:\n{lines:#?}"
    );
}

/// ⚠️ The finding this spike added: a crash loop sends `hello` every run, and
/// `hello` must not reset the clock, or a wedged MediaRemote is never "failed".
#[test]
fn a_hello_crash_loop_still_fails_and_backs_off() {
    let mut flags = FAST.to_vec();
    flags.extend(["--seconds", "4"]);
    let lines = run("hello", &flags);
    assert!(count(&lines, "Hello {") >= 3, "{lines:#?}");
    let h = health(&lines);
    assert!(
        h.last() == Some(&true),
        "hello alone must not keep the source alive:\n{lines:#?}"
    );
    // Backoff doubles across short runs: 0.2, 0.4, 0.8, then the 1.0 cap.
    let delays: Vec<&str> = lines
        .iter()
        .filter_map(|l| l.split("after: ").nth(1))
        .collect();
    assert!(delays.len() >= 3, "{lines:#?}");
    assert!(
        delays[0].starts_with("200ms")
            && delays[1].starts_with("400ms")
            && delays[2].starts_with("800ms"),
        "{delays:?}"
    );
}

#[test]
fn garbage_and_oversized_lines_do_not_kill_the_helper() {
    let mut flags = FAST.to_vec();
    flags.extend(["--seconds", "2.5"]);
    let lines = run("garbage", &flags);
    assert_eq!(count(&lines, "Unparseable"), 1, "{lines:#?}");
    assert_eq!(count(&lines, "TooLong"), 1, "{lines:#?}");
    assert_eq!(count(&lines, "Started {"), 1, "{lines:#?}");
    assert!(
        count(&lines, "Tick {") >= 3,
        "the stream resynchronizes after the long line:\n{lines:#?}"
    );
}

/// Stopping closes stdin; the helper leaves on its own with code 0, and
/// nothing is restarted.
#[test]
fn stopping_closes_stdin_and_does_not_restart() {
    let mut flags = FAST.to_vec();
    flags.extend(["--seconds", "1"]);
    let lines = run("tick", &flags);
    assert_eq!(count(&lines, "Started {"), 1, "{lines:#?}");
    assert!(
        count(&lines, "code: Some(0)") == 1 || count(&lines, "signal: Some(9)") == 1,
        "{lines:#?}"
    );
    assert_eq!(count(&lines, "Restarting"), 0, "{lines:#?}");
    assert!(lines.last().unwrap().ends_with("stopped"));
}

/// ⚠️ S1's gate from the second review: freeze the supervisor well past the
/// silence limit, resume, and the helper survives. On resume the pipe is full
/// of ticks, and silence must not be judged until it is drained.
#[test]
fn a_frozen_supervisor_does_not_kill_a_healthy_helper_on_resume() {
    let mut args = vec![
        "--exec".to_string(),
        "/usr/bin/python3".into(),
        fake(),
        "tick".into(),
        "0.1".into(),
    ];
    args.extend(FAST.iter().map(|s| s.to_string()));
    args.extend(["--seconds".into(), "6".into()]);
    let child = Command::new(S1)
        .args(&args)
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let pid = child.id().to_string();
    std::thread::sleep(Duration::from_secs(1));
    assert!(Command::new("kill")
        .args(["-STOP", &pid])
        .status()
        .unwrap()
        .success());
    std::thread::sleep(Duration::from_secs(4)); // > 2x the 1.5 s limit
    assert!(Command::new("kill")
        .args(["-CONT", &pid])
        .status()
        .unwrap()
        .success());
    let out = child.wait_with_output().unwrap();
    let lines: Vec<String> = String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(str::to_owned)
        .collect();
    assert_eq!(
        count(&lines, "KilledForSilence"),
        0,
        "killed a healthy helper on resume:\n{lines:#?}"
    );
    assert_eq!(count(&lines, "Started {"), 1, "{lines:#?}");
}
