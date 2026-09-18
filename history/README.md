# Evidence from completed work

Measurements, audit findings and verification records that are expensive to
reproduce and that the topic docs in [`docs/`](../docs/) cite. Kept for the
numbers and the dead hypotheses, not for instructions.

The plans and code reviews that produced them were deleted once the work
landed — they were process, and `git log` still has them (everything up to
`6f7777c`, 2026-09-01) if the reasoning behind a decision is ever needed.

**These are records.** Where one disagrees with `docs/` or with the code, the
code wins and the record is stale. Live work is in [`plans/`](../plans/).

## clock-sync/ — sub-second clock sync (2026-09-01)

Host syncs land within ~3 ms, a USB-SOF frequency loop disciplines the ILRC,
offsets slew rather than jump, and a no-host reboot self-acquires to ~±15 ms.

| File | What it holds |
|---|---|
| `phase-0-facts.md` | Hardware facts established by measurement, referenced by number (F1…) from `docs/clock.md` and `docs/wireless.md` |
| `phase-1-2-results.md` | Measured results: phase-correct set, tick-applied reloads, SOF frequency discipline, slew |
| `phase-3-results.md` | PCF STOP-bit phase write, boot acquisition, persistence |

## hardening/ — audit + refactor of the QMK port (2026-09-01)

| File | What it holds |
|---|---|
| `HARDWARE-CHECKLIST.md` | The verification record — every item confirmed on hardware. `docs/hardware.md` cites this as the basis for calling the work verified |
| `findings-concurrency.md` | Execution contexts enumerated and traced: main loop vs row ISR vs GPT tick vs DMA |
| `findings-bounded-wait.md` | Every unbounded wait in the tree, and what bounds it now |
| `findings-ch582-states.md` | CH582F wire captures and state analysis. `scripts/bt_faults.py` replays these |
| `findings-input-validation.md` | What the firmware trusts from the host and the module, and what it now checks |

## phase0-burst-2026-09-17/ — the cross-platform refactor's Phase 0 gate (2026-09-17)

| File | What it holds |
|---|---|
| `README.md` | Why a burst A/B replaced the overnight gate, what ran, both tables, the thin margin on condition 3, and the paired-offset check |
| `phase0-burst-20260917-101627.txt` | Raw `ak820 clock --raw` output, 50 reads each from `e07fdfa` and `d8ead97`, interleaved on gremlin |
| `burst_ab.ps1` | The run: stop the daemon, alternate the two CLIs, restart |
| `burst_grade.py` | The grader; re-run from here, it gives the same PASS |

## windows-memory-2026-09-18/ — the Windows daemon does not leak (2026-09-18)

The other half of the macOS leak question (`plans/AK820-AGENT-MACOS-LEAK-PLAN.md`):
gremlin's live daemon, sampled 26.7 h after it started, so no warm-up is inside
the window. Growth is bounded at **+0.70 B per HID write**, which excludes the
macOS rate of 48 B/write by about 69×.

| File | What it holds |
|---|---|
| `README.md` | Method, the slope with its 95% CI and r², why a flat line is credible here, and what the measurement does not say |
| `mem-samples-e07fdfa.csv` | 49 samples, 5 min apart: private bytes, working set, handles, threads, CPU, and the daemon's own `smtc_polls` / `clock_syncs` |
| `mem_sample.ps1` | The sampler |
| `mem_slope.py` | The fit; re-run from here, it reproduces the numbers |
