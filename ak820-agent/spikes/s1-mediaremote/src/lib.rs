//! Spikes S1 and S1b of plans/AK820-AGENT-CROSSPLATFORM-PLAN.md.
//!
//! S1: can Rust drive the perl-hosted MediaRemote helper and get a browser's
//! title, artist and state over line-JSON, under the supervision rules the plan
//! settled? S1b: can a MediaRemote refusal — which looks exactly like idle — be
//! made visible, without bringing process spawns back into the idle state?
//!
//! Written in the shape of the macOS media backend's future modules, so the
//! answer moves into the crate in Phases 0 and 3 instead of being rewritten.
pub mod applescript;
pub mod canary;
pub mod helper;
pub mod json;
pub mod message;
pub mod players;
