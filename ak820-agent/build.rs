//! Bakes `git describe` into the binaries as `AK820_GIT_DESCRIBE`, so that
//! `ak820 --version` and the daemon's first log line name the exact tree they
//! were built from. A Releases zip is built from a tag, so its describe *is*
//! the tag; a development build says `<tag>-<n>-g<hash>[-dirty]`.
//!
//! Falls back to `unknown` when there is no git — a source tarball, say —
//! rather than failing the build over a version string.

use std::process::Command;

fn main() {
    // Re-run when the checkout moves, not on every build.
    println!("cargo:rerun-if-changed=../.git/HEAD");
    println!("cargo:rerun-if-changed=../.git/refs");
    println!("cargo:rerun-if-changed=../.git/packed-refs");

    let describe = Command::new("git")
        .args(["describe", "--always", "--dirty", "--tags"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=AK820_GIT_DESCRIBE={describe}");
}
