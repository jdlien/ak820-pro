# Project history

Completed projects, kept for their reasoning rather than their instructions.
Each records why a thing is the way it is, what was measured, and which
hypotheses died — the parts that are expensive to rediscover and that git
history alone does not explain.

**These are records, not guidance.** Where one disagrees with `docs/` or with
the code, the code wins and the doc is stale. Live work lives in `plans/`.

| Project | Landed | What it was |
|---|---|---|
| [`hardening-plan/`](hardening-plan/) | 2026-09-01 | Audit + refactor of the QMK port, phases 0–5. Split `ak820pro.c` into modules, added the ~12 s watchdog and health counters, unified the CH582F pending-action machinery, persisted BT slot / LCD brightness / RTC trim, and made build provenance checkable. Includes the concurrency, bounded-wait and input-validation audits, `HARDWARE-CHECKLIST.md` (all verified), and one round of external Codex review. |
| [`clock-sync-plan/`](clock-sync-plan/) | 2026-09-01 | Sub-second clock sync, phases 0–3. Host syncs land within ~3 ms, a USB-SOF frequency loop disciplines the ILRC, offsets slew rather than jump, and a no-host reboot self-acquires to ~±15 ms. Five rounds of Codex review, 52 findings folded in, plus the measured per-phase results. |
| [`packaging-plan/`](packaging-plan/) | 2026-09-01 | Restructured this repo into something you clone and build: `deps.lock` + `setup.sh`, absolute paths templated out, a README for cold readers, and this history split. Touched no firmware source. |

The two documents that are still live were deliberately left out of here:
`plans/BACKLOG.md` (known, accepted or deferred defects) and
`plans/CLOCK-FORMAT-PLAN.md` (the `Fn`+`C` 24 h/12 h/off toggle — designed,
not built).
