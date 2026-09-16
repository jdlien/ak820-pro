//! Spike S1 of plans/AK820-AGENT-CROSSPLATFORM-PLAN.md: can Rust drive the
//! perl-hosted MediaRemote helper and get a browser's title, artist and state
//! over line-JSON, under the supervision rules the plan settled?
//!
//! Written in the shape of the macOS media backend's future modules, so the
//! answer moves into the crate in Phases 0 and 3 instead of being rewritten.
pub mod helper;
pub mod json;
pub mod message;
