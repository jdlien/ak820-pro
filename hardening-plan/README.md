# AK820 Pro firmware hardening plan

Audit + refactor plan for the QMK port in `qmk_firmware-ak820pro/` (branch
`ak820pro-jdlien`). Goal: fewer latent bugs, smaller blast radius when one
fires, easier modification — without regressing anything that is measured and
working, and without exceeding what the SN32F299 (Cortex-M0, 48 MHz) has left.

## Why now

Features are done and stable-ish. The bugs hit so far cluster into four
classes, which predict where the remaining ones live:

1. **Cross-context races** — main loop vs. row ISR vs. GPT tick vs. DMA
   (the eeconfig/blit hang, the stuck `blit_done` flag, the LED frame copy).
   This class produces "dead until power cycle".
2. **Edge-triggered state with no recovery** — the CH582F driver's whole
   history (missed `5B 32`, dropped `A6 51`, advertising decline). Every fix
   is a heuristic timer bolted onto an implicit state machine.
3. **Invisible couplings** — enum ↔ `via.json` index matching, the Fn-layer
   bitmask, `adv = big ? 10 : 6`, asset ids by sorted filename. These corrupt
   silently instead of crashing.
4. **Fragile build provenance** — six hand-applied ChibiOS diffs that one
   `git submodule update` destroys; a shared binary output path.

## Phases

| Phase | File | Theme | Risk |
|---|---|---|---|
| 0 | `phase-0-lockdown.md` | Commit everything; patches → forked submodule; build script | near zero |
| 1 | `phase-1-observability-recovery.md` | Watchdog; unified health counters; soak harness | low |
| 2 | `phase-2-audits.md` | Concurrency / bounded-wait / input-validation audits | zero (read-only until findings) |
| 3 | `phase-3-refactors.md` | Split `ak820pro.c`; CH582F state machine; static asserts; band arbiter | moderate |
| 4 | `phase-4-durability.md` | Persist RTC trim; persist backlight level | low |
| 5 | `phase-5-publication.md` | Public release for other AK820-Pro owners | low |

Ordering is deliberate: 0 makes the tree safe to work in, 1 makes failures
visible and survivable *before* the riskier phase-3 changes, 2 feeds findings
into 3.

Externally reviewed 2026-08-31 by Codex CLI; all 16 findings verified and
folded into the phase files — see `review-codex-2026-08-31.md` for the
verbatim findings and what each changed.

## Ground rules (apply to every phase)

- **One change per flash.** The 2026-08-30 incident (three changes in one
  build, nothing to bisect) is the process failure to never repeat.
- **Reproduce first, bisect second.** Never fix and revert in the same step.
- **Soak between changes** using the phase-1 harness once it exists; before
  then, the timestamped `qmk console` log recipe from CLAUDE.md.
- **Do not re-litigate documented decisions.** The tree is full of
  load-bearing weirdness with measurements behind it (the 2 s pair hold,
  misnamed asset files, the colon shift). Refactors move code; they do not
  revisit decisions. When in doubt CLAUDE.md wins — but **verify its RGB
  sections against `git log` first**: the freq-product coupling it documents
  at length was fixed by `SN32F2XX_RGB_PWM_FREQ` (commit cba2c1e19e), which
  pins the PWM clock and freed the step sizes (`SPD_STEP` is now 4, not
  128). Commit messages are the fresher record until CLAUDE.md is brought
  current (phase 4.3).
- **Personal-first (decided 2026-08-31):** this firmware is built for JD's
  own board, open source on his own fork — do not spend effort generalizing
  for upstream. Prefer the simple board-local implementation. The only
  contributions worth making are cheap and universal: the sn32f2xx
  periodticks and GPT MCTRL core-driver fixes, the
  `SN32F2XX_RGB_PWM_FREQ` decoupling (fixes the driver's freq-derived-from-
  UI-step-sizes wart for every SonixQMK board, default preserves old
  behaviour), the `SN32F2XX_RGB_OUTPUT_ACTIVE_LEVEL` teardown-polarity
  finding (the `sn32f2xx_blank()` workaround), WDG LLD findings, and CH582F
  protocol corrections as issues/writeups on fpb's repo. Never upstream
  unit-specific values (`RTC_PERIOD_INITIAL`, MADCTL/INVON).
- **`stat` the binary before flashing** — the output path
  `$QMK_HOME/a_jazz_ak820pro_via.bin` is shared; confirm the timestamp is
  your build.
- Liveness probe is always `ak820ctl info` (raw-HID round trip), never USB
  enumeration. Bootloader (`0x7140`) looks exactly like a dead board — check
  it before declaring a hang.

## Explicit non-goals

- No big-bang rewrite; no "modernisation" of documented oddities.
- No chasing the ~1.2% ms-timebase slowdown or more LED field rate — the M0
  is at its comfortable ceiling and the current balance is measured.
- No new features until the plan completes (the plan itself adds a watchdog
  and two persisted settings; that is the lot).
