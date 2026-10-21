**Yes. With the daemon from main HEAD `6d174f45` installed, firmware `01abfe0e` is cleared by this source review for JD’s attended BT test on gremlin. Must-fix 1 is closed; I found no new functional blocker.**

- **Must-fix 1 — closed.** [agent.rs:479](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:479) captures `before` ahead of `clock.tick()`, and line 489 publishes it only when `syncs` increases. A step observed during the tick’s tail remains newer than that timestamp, so [clock.rs:121](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:121) keeps quarantine active. `usb_clock_synced()` still receives completion time at line 486, preserving the conservative refusal delay. This closes the remaining escape from the earlier lost-marked-frame finding.

- **Note — observing while ungranted is sound.** [sender.rs:649](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:649) calls `revoked()` before observing. [clock.rs:150](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:150) clears `due` and `floor`, retaining continuity and quarantine state. `observe()` updates that state but schedules only when `due` already exists. Reacquisition establishes its handover/USB floor normally. Observation performs host-clock reads and conversion; it adds no device traffic.

- **Note — the wake guess remains intact.** It was already sampled on every pass at [sender.rs:579](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:579). The new observation does not touch its armed state or media policies. `woke()` cannot acquire an inactive clock schedule, and any stale schedule is subsequently revoked on an ungranted pass.

- **Note — notification-driven passes remain safe.** Each observation compares against the previous wall/monotonic sample, including elapsed time across gaps. Moreover, [sender.rs:1221](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1221) gives `Next::Wait` a **60-second fallback**, so it is not strictly notification-only. No new one-second polling loop is introduced while ungranted.

- **Should-fix — production lifecycle coverage remains open, as dispositioned.** [lockchan_media_test.c:24](/C:/Users/jdlien/code/ak820-pro/scripts/lockchan_media_test.c:24) still uses a fake setter; line 492 tests the pure lifecycle helpers. The attended hardware invalidation trials remain necessary. This does not block the agreed test.

- **Note — coverage and wording.** The new [sender.rs:2540](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:2540) regression covers observation before grant followed by USB trust. The agent’s timestamp ordering remains inspection-only. Startup trust requires a usable observation before `before`; otherwise quarantine conservatively persists. Also, [sender.rs:239](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:239) still describes `at` as acknowledgement time—the API comment should describe the conservative pre-tick timestamp.

Use the verified [01abfe0e BIN](/C:/Users/jdlien/code/ak820-pro/ak820pro-builds/out/via-dev-01abfe0e-20261021-104337.bin). Keep convergence uninterrupted and awake on BT; run USB/sleep invalidation trials separately.

I compared exact HEAD/parent Git objects and matched the reviewed source and firmware BIN/ELF hashes. Process execution was denied, so `git show HEAD` and native tests could not run; independent JavaScript timing replays passed. Installed-daemon identity was not verified.
---

## Dispositions (gremlin session, 10-21)

Cleared: firmware 01abfe0e with this daemon, for JD's attended BT test on gremlin.
- **Note, the wording of `Handle::usb_clock_set`:** taken. Its doc now says `at` is a pre-SET instant.
- **Should-fix, production lifecycle coverage:** carried, as before. The attended test checks it on the hardware, and the invalidation trials (USB replug, sleep) run separately from the convergence run.
