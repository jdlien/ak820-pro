# Codex review of the ak820d plan — 2026-09-05

`codex exec`, model **gpt-6-astra**, reasoning effort **xhigh**, read-only
sandbox with full disk read (so it could also read `../jdrgb` and `../jdups`).
186,752 tokens. Reviewing [AK820D-PLAN.md](AK820D-PLAN.md) and
[AK820D-CLOCK-PARITY.md](AK820D-CLOCK-PARITY.md) before any code was written.

The plan documents were renamed to `AK820-AGENT-*.md` after this review; the
paths it cites were correct when it ran. Verbatim below. Findings acted on are tracked in the plan documents; the two
live bugs it found in `hostagent/ak820text.py` (finding 8) were fixed
separately.

---

**The direction is sound, but the clock port is not yet fully specified, and its proposed validation can pass despite a regression.** I would keep Rust, the separate console/daemon binaries, and short HID transactions. The findings below are ranked by severity.

**1. High — The parity document omits the component that actually delivers precise synchronization.**

The Python agent schedules syncs and learns SOF bias. Most of the precision-critical behavior lives in [ak820ctl.c](C:/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:207), which you are also replacing.

That includes:

- Five GETs, selecting the minimum-RTT offset.
- Fractional time computed from **active and nominal periods**, including the shortened period after a phase correction.
- Host midpoint arithmetic, local time, and midnight wrapping.
- SET timestamp construction immediately before transmission.
- A separate outbound-lead learner: initial lead **1.5 ms**, gain **¼**, adjustment limited to **±1 ms**, lead clamped to **0–10 ms**, and calibration excluded while already slewing or outside the strict **±500 ms** gate.
- Protocol negotiation, the unknown-bias sentinel, retrying `0xFE` once, verification, and cache persistence.

Copying every constant in the Python document leaves all of this unspecified. A Rust implementation could reproduce the bias decisions perfectly while injecting several milliseconds—or much more—on every SET.

**Add a second parity contract for `ak820ctl`’s clock transaction before phase 3.** Include packet fixtures, timestamp placement, arithmetic, lead learning, reply/error handling, and cache behavior. The effective oracle is **Python plus the pinned C utility**, not Python alone.

**2. High — Live shadow mode is neither a controlled comparison nor proof of parity.**

The proposed [shadow procedure](C:/Users/jdlien/code/ak820-pro/plans/AK820D-CLOCK-PARITY.md:126) has three fundamental problems:

- Independent polling gives the implementations different inputs. Python may measure before a correction while Rust reads during the resulting slew.
- Without sending SET, Rust cannot observe its own SET result, receipt offset, lead-calibration result, or actual slew/step outcome.
- Python keeps the physical clock healthy. A broken Rust write path or bias-application path remains completely unexercised.

Even the decisions cannot be diffed reliably from the current logs: they lack complete gate inputs, timestamps, cache state, and state transitions.

**Replace phase 3a with deterministic differential replay.** Capture the oracle’s wall and monotonic timestamps, presence observations, raw transaction results, cache contents, and outcomes. Feed identical inputs into both implementations and compare decisions **and next state**, including serialized cache values.

Exercise threshold boundaries, missing data, failed writes, changing periods, cache absence, and rounding ties. Require evidence that learning actually fired; two implementations declining every sample is a vacuous pass.

Keep the real takeover phase. Replay establishes computational parity; hardware runs establish timing and feedback behavior. Neither substitutes for the other. The document’s statement that unit tests cannot catch these regressions is too sweeping: many of the described gate regressions are excellent deterministic tests.

**3. High — The measuring instrument can miss large errors and interfere with the daemon.**

[clock-phase.py](C:/Users/jdlien/code/ak820-pro/hostagent/clock-phase.py:33) detects a seconds transition and reduces the host fraction to the nearest second. Consequently, **a clock approximately 1.016 seconds late can produce the same reported +16 ms phase as one 0.016 seconds late**. It prints board time but does not validate the full date/time.

It also timestamps after the HID reply, so its reading includes detection and transport latency. The host’s NTP offset does not calibrate that measurement. The documented **+15.9 ms** baseline therefore does not, by itself, demonstrate sub-10 ms board-to-host synchronization.

Finally, it holds the HID handle throughout sampling. Under the plan’s exclusivity assumption, extending it to an hours-long run would prevent the daemon from synchronizing. If sharing works, its requests still require concurrency validation.

Strengthen phase 3b to require:

- Full calendar/time correctness alongside fractional phase.
- Short, coordinated measurement bursts with uncertainty recorded.
- Measurements throughout each sync interval, not just immediately after correction.
- Actual successful sync/learner counts, bias, nominal period, slew activity, and error distributions.
- An overnight run covering the historical six-hour failure, with media polling and realistic load active.

Declare numerical acceptance limits against a matched Python baseline. “Anything in that neighbourhood” is not a gate.

**4. High — “One owner” is an intention, not an enforced architecture.**

Per-transaction opening is a reasonable default. **Define a transaction as the complete logical operation**: the clock measurement/SET/verification sequence, or the text update batch—not each individual report. Open before taking transmission-sensitive timestamps, and close promptly afterward.

But `FILE_SHARE_READ | FILE_SHARE_WRITE` explicitly permits compatible concurrent opens. Chromium’s current HID implementation uses those flags too. Therefore, “holding it open means VIA can never connect” is not established for Windows merely by observing contention elsewhere. A driver-specific restriction could still exist; test it on this machine. [CreateFile documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew), [Chromium implementation](https://raw.githubusercontent.com/chromium/chromium/main/services/device/hid/hid_service_win.cc).

The plan needs explicit answers for:

- A second daemon instance.
- `ak820.exe` running while the daemon runs.
- Retained C/Python diagnostics and provisioning tools.
- VIA opening before, during, and after a transaction.

Use one serialized HID executor internally and a process-instance mutex. For your CLI, either route commands through the daemon or require a coordinated pause. **Even a serialized one-shot clock SET can invalidate the daemon’s learner baseline** if the daemon does not know it happened.

The wire layer also needs report-length/ID normalization, header validation, and stale-reply handling. The [firmware echoes text commands](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:580); if text and clock operations share an open, unread text replies must never be interpreted as clock replies. One process does not solve that automatically.

**5. High — Blocking SMTC on the scheduling thread couples media failures to clock failure.**

The plan says the daemon “has nothing else to do” while waiting for SMTC. It has a clock loop to run.

A three-second polling interval bounds polling frequency, **not the duration of `RequestAsync` or metadata retrieval**. An indefinitely blocked media call could stop clock sync, reconnection, and shutdown handling. Moving both agents into one process introduces this failure coupling.

I would use a dedicated SMTC worker initialized as an MTA, publishing its latest completed snapshot to the clock/HID scheduler. Give operations deadlines, bound outstanding work, and define recovery after session disappearance or broker failure. Do not spawn another stranded worker every timeout. Initialize and uninitialize WinRT on the relevant threads. [RoInitialize requirements](https://learn.microsoft.com/en-us/windows/win32/api/roapi/nf-roapi-roinitialize).

The **`windows` dependency is the right trade**. Handwritten WinRT ABI machinery would be needless risk. Pin the version: current async conveniences include `.join()` and `.await`; the plan’s `.get()` spelling is version-dependent. [Microsoft’s async documentation](https://github.com/microsoft/windows-rs/blob/master/docs/crates/windows-future.md).

Also, “one dependency” means one **direct** dependency; `windows` has supporting crates. Measure the release binary with SMTC actually linked and exercised, plus steady-state private memory and handle/thread growth. Phase 0 HID-only size tells little about WinRT. Mixing `windows-sys` into the same executable is not a demonstrated size fix. [Crate manifest](https://docs.rs/crate/windows/0.62.2/source/Cargo.toml).

**6. High — The HID safety design is good, but the verification workflow retains the prohibited behavior.**

Configuration Manager discovery followed by filtering **before opening** addresses the specific UPS incident. Keep it. Handle `CR_BUFFER_SMALL` and use the present-interface flag, as the sibling does. [Configuration Manager documentation](https://learn.microsoft.com/en-us/windows/win32/api/cfgmgr32/nf-cfgmgr32-cm_get_device_interface_listw).

However, the assertion that the Python agent already implements the required protection is misleading:

- [Timekeeper presence polling](C:/Users/jdlien/code/ak820-pro/hostagent/ak820-timekeeper.py:93) calls `hid.enumerate` every loop.
- Its Windows controller identification also enumerates.
- [Every C utility invocation](C:/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:536) enumerates—including `clock --bias`.
- `clock-phase.py` and the health diagnostic enumerate.
- `ak820text.py` still enumerates on discovery; caching and deferral reduce frequency, not the scope of devices opened.

Thus, the proposed shadow run leaves the oracle performing precisely the sweep you prohibit. Preserve the clock algorithm as the oracle, but specify a safe Windows discovery adapter or use captured replay inputs. Audit the validation tools before making them part of a safety gate.

The path filter itself is a **candidate selector, not proof of identity**. Microsoft documents these symbolic names as opaque. Another board with the same IDs, another collection on the keyboard, or an unexpected path containing the substring can match. [Device-path documentation](https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdigetdeviceinterfacedetailw).

Require case-insensitive bounded matching in the expected hardware-ID portion, reject unexpected forms, and retain the sibling’s `HidD_GetAttributes` check after opening. Then validate usage, report lengths, and supported protocol before application writes. Decide what happens with two matching keyboards. Post-open checks prevent incorrect writes; they cannot retroactively guarantee that an incorrect candidate was never opened.

Path logging is useful, but it only proves what your logging covers. Test the actual discovery/open boundary with unrelated devices present and audit every HID-open path.

**7. High for clock parity — The eleven constants match; the transcription is incomplete in consequential ways.**

The numeric table is correct. Trigger precedence and the main learner inequalities also match. These details need correction or addition:

| Area | Actual Python behavior |
|---|---|
| Existing bias | Learning additionally requires a readable cache containing `b`; persistence must succeed before it logs success. |
| Baseline updates | Successful nonperiodic syncs establish `{t, pnom}`. The **first periodic sync afterward can learn**; two periodic syncs are not required. |
| Failed sync | Does not update `last_sync`, interval, or learner baseline. `was_present` still updates, so a failed enumeration/wake reason is not automatically retained for retry. |
| Failed status read | After a successful sync, it replaces the baseline with `pnom=None`; it does not preserve the previous good nominal period. |
| Time sources | Scheduling and seed duration use wall time; learner elapsed uses monotonic time. The learner timestamps **before** its status read. |
| Hold logging | The unsettled-period log does **not** require the 90-second elapsed gate or an existing bias. “All gates except settled” is inaccurate. |
| Rounding | Bias uses Python ties-to-even rounding. The residual has already been printed by C to **one decimal place** before Python compares thresholds. |
| Unknown residual | Selects the normal 300-second interval. |

See [learner behavior](C:/Users/jdlien/code/ak820-pro/hostagent/ak820-timekeeper.py:195) and [main-loop transitions](C:/Users/jdlien/code/ak820-pro/hostagent/ak820-timekeeper.py:257).

The **seed algorithm is almost entirely missing**. It resets on controller-ID or SOF-epoch changes and missing status; measures wall-clock duration; subtracts frames modulo \(2^{32}\); accepts only **strictly** `-600 < b < 600`; rounds the result; and clears the measurement afterward. Existing bias disables seeding. [Seed implementation](C:/Users/jdlien/code/ak820-pro/hostagent/ak820-timekeeper.py:227).

Do not silently “improve” these semantics during the port. For example, using full-precision residuals changes the interval decision around 60 ms. Separate intentional fixes from parity work.

**8. Medium — Presence, busy state, and rediscovery backoff need a state machine.**

An unsuccessful open is not equivalent to device absence. Treating VIA contention as absence clears continuity and can manufacture an `enumerated` sync when access returns. Conversely, a reboot can reuse the same path and occur between polls.

Specify distinct states for absent, discovered-but-busy, open-but-unresponsive, and incompatible firmware. Include device-generation/reset observations where available.

The power gate is also weaker than its description: [the Python implementation](C:/Users/jdlien/code/ak820-pro/hostagent/ak820text.py:93) samples AC state only when rediscovery is attempted. It can miss an entire outage while cached opens succeed or backoff suppresses checks. It cannot guarantee a 60-second hold after every mains return.

Its retry sequence is not exactly “30 seconds, then doubling,” either: an unsuccessful initial search doubles the interval before the next attempt; a found candidate resets it before opening succeeds.

For passive Configuration Manager listing, UPS protection comes from avoiding unrelated opens. Do not unnecessarily delay presence knowledge for five minutes to protect an operation that opens nothing. Separate discovery cadence, target-open backoff, and any retained power policy.

**9. Medium — The phases have useful smoke tests, but most are not release gates yet.**

I would revise them as follows:

| Phase | Required change |
|---|---|
| 0 | Add wrong-interface/report rejection, timeout/unplug/cancellation tests, external-open tracing, and VIA coexistence. JEDEC/base only prove one request works. |
| 1 | Use captured media cases: competing sessions, paused/current ranking, missing metadata/timeline, seeks, future/stale timestamps, Unicode, keepalive, partial write failure, and reconnect. |
| 2 | Compare identical captured replies and timestamps. Sequential live clock reads cannot match literally field for field. |
| 3 | Require C-transaction parity, deterministic replay, and measured takeover using the **combined daemon runtime**. |
| 4 | Test migration, restart, suspend/resume, battery operation, rollback, and actual liveness—not merely one registered task. |
| 5 | Move enough health reporting before takeover to detect added firmware stalls. Compare decoding fixtures; live counters naturally change. |

Build the minimal daemon scheduler **before phase 3**. Otherwise phase 3 validates clock code and phase 4 changes its scheduling and failure environment afterward.

Carry over the sibling’s cancellation discipline: `CancelIoEx` requests cancellation; buffers and `OVERLAPPED` must remain alive until completion. A nominal timeout must not become a use-after-free or an unnoticed indefinite shutdown wait. [Cancellation contract](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex).

Also, one open does not mathematically guarantee one LCD repaint. Two reports a millisecond apart can straddle a 100 ms tick. Keep batching as the measured mitigation, but either define an observable acceptance criterion or require firmware staging/commit for a strict atomic-update guarantee.

**10. Medium — Installation, persistence, and supportability remain underspecified.**

The missing deliverables are concrete:

- **Cache migration and ownership:** native path selection, existing lead/bias import, malformed-cache handling, atomic replacement, CLI interaction, and rollback compatibility. Moving in-process does not choose a cache path for you.
- **Task lifecycle:** interactive-user execution, both battery settings, unlimited execution time, restart policy, duplicate prevention, and stopping old processes during migration. The [current installer](C:/Users/jdlien/code/ak820-pro/hostagent/install-agents-windows.ps1:110) already contains requirements the new plan should preserve.
- **Daemon observability:** bounded logs, startup failures, version/protocol identity, last successful clock/media operations, and a degraded-state report. “Task running” can coexist with hours of failed syncs.
- **Release-only installation:** packaged binaries and installer, supported Windows/CPU targets, firmware compatibility, and a clean-machine test without Python/MSYS2. That is a stated primary motivation but has no explicit phase gate.
- **Text normalization:** Python performs punctuation substitution plus NFKD and ASCII filtering. Rust’s standard library does not supply equivalent normalization; choose an implementation and pin representative output fixtures.

Windows-only scope, keeping macOS Python, separate PE subsystems, no tray, and leaving flash provisioning out of the daemon are all sensible. The work needed now is a complete clock transaction contract and validation that cannot succeed merely because Python kept the board healthy.
