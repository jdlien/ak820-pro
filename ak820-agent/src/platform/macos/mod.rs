//! macOS: being built, phase by phase (plans/AK820-AGENT-CROSSPLATFORM-PLAN.md).
//!
//! Phase 0 gives the crate a macOS half that compiles, so every platform-neutral
//! test runs natively on the Mac. The transport (Phase 1, from spike S2), the
//! clock (Phase 2) and the media source (Phase 3, from spikes S1 and S1b)
//! arrive here in turn.

pub mod host;

use std::process::ExitCode;

pub use host::SystemHost;

/// `ak820` on macOS. Nothing is wired yet; say so rather than pretend.
pub fn cli_main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--version") {
        println!("{}", crate::version_line("ak820"));
        return ExitCode::SUCCESS;
    }
    eprintln!("ak820 on macOS: no commands yet -- the transport lands in Phase 1 of the cross-platform plan");
    ExitCode::from(2)
}

/// `ak820-agent` on macOS. Refuses to run until there is something to run.
pub fn daemon_main() {
    eprintln!("ak820-agent on macOS: not built yet -- see plans/AK820-AGENT-CROSSPLATFORM-PLAN.md");
    std::process::exit(2);
}
