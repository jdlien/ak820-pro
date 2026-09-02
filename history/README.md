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
