//! `ak820` -- the command-line half. The body is per platform:
//! `platform::windows::cli` and `platform::macos`.
fn main() -> std::process::ExitCode {
    ak820_agent::platform::cli_main()
}
