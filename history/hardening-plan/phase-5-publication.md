# Phase 5 — Publication (the Jackrabbit goes public)

**Theme:** make the firmware usable by another AK820-Pro owner without
compromising the personal-first design. Decided 2026-08-31: this is a
coherent private project ("JD Bunny Brand" / AJAZZ Jackrabbit) published for
same-hardware owners — NOT a generalized upstream contribution. Audience:
someone with this exact keyboard, cold, with none of the accumulated context.

Runs last (after phase 4), but two items land earlier where noted.

## 5.1 What is public

- **Public:** the QMK fork (`ak820pro-jdlien` branch) + the chibios-contrib
  fork it pins (phase 0's remote does double duty), with the asset pipeline
  (`mkraw.py`, `mkbdfatlas.py`, sources) and hostagent scripts included or
  copied in as examples.
- **Private:** the workspace repo — CLAUDE.md, the plan docs, anything with
  machine-specific absolute paths or personal context. It is the lab
  notebook, not the product.
- Sweep the public tree for personal data before the first push (absolute
  home paths, email in commits is fine/expected, log locations in example
  scripts get placeholder comments).

## 5.2 The one generalization worth making: LCD variant flag

JD's unit is mounted 180° from fpb's and needs INVON; fpb's units need
neither. Same product, at least two hardware revisions — a stranger has real
odds of an upside-down, inverted panel that reads as "broken firmware".

- Compile-time flag in `config.h` (e.g. `LCD_PANEL_VARIANT_JD` /
  `LCD_PANEL_VARIANT_FPB`), defaulting to JD's. Two `#ifdef`s in
  `lcd_bus.c` (MADCTL value, INVON in the init sequence). Zero runtime cost.
- README documents the symptom → flag mapping ("panel upside down and/or
  black-on-white: build with the other variant").
- Can land any time; cheapest during phase 3's display work.

Related, documentation-only: `RTC_PERIOD_INITIAL` is measured on this unit's
ILRC (~±5% part-to-part). Phase 4.1's persisted trim makes it a fallback
seed; the comment and README say "per-unit, yours will differ, the trim
converges and persists".

## 5.3 Public README — recovery-first

Distilled from the handoff + CLAUDE.md, front-loading what a cold user must
know BEFORE flashing:

1. **There is no firmware backup path.** Download the stock v1.13 image
   first (`AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin`, not v1.14 — the PID
   change breaks AJAZZ's own drivers). Once flashed, stock is gone unless
   you have it.
2. **The bootloader looks nearly dead** — a `BOOTLOADER / Awaiting
   firmware / 0C45:7140` splash is shown on entry (held ~1.5 s, then the
   reset drops the backlight to high-Z and the panel goes dark), so
   document: "if you saw the splash, it's waiting for firmware — dark
   screen + no lights is normal in this state." Then the `0x7140` check,
   and re-flash (not power cycle) as the recovery. If the splash still
   reads as too brief on hardware, the hold constant is the only safe
   knob — persisting it via a direct jump to the bootloader was tried
   2026-08-31 and makes flashing unreliable (documented in commit
   6689927483); do not re-derive.
3. The pin-short recovery procedure (photo link, SIM-tool trick, cold-boot
   requirement, latched behaviour) for when `Fn`+`Esc` is gone.
4. macOS Tahoe: SonixFlasherC MUST be built `USE_LIBUSB=1` (the silent-
   failure trap), plus the toolchain list.
5. Asset provisioning: wired mode required, erase-before-write hazard,
   power-cycle after provisioning, firmware-before-assets ordering.
6. VIA setup (draft definition, layer layout), the stock shortcut table.
7. Known post-flash oddities that look like bugs: the stored RGB mode index
   does not shift with the effect enum, so a build with a different effect
   list comes back on a different effect (one-time, re-pick with `Fn`+`\`);
   animation-speed and second-colour readouts are mode-dependent by design.
8. Plain scope statement: "works on my unit; no warranty, no support
   promised; issues and forks welcome."

## 5.4 Licensing and branding

- GPL2+ inherited from QMK — nothing to do; keep source pushes current with
  released binaries.
- Cozette MIT license already committed beside the BDF; add an OFL
  attribution note for the Iosevka-derived atlases.
- One line in the README: the bunny logo is JD's personal mark — build and
  flash freely, don't rebrand with it. Swapping the splash is documented
  anyway (`mkbunny.py` / `mkraw.py`).

## 5.5 What publication does NOT change

Phases 1–3 unchanged — they serve this board first and the public artifact
incidentally (a stranger's unknown unit benefits from the watchdog's
reset-loop escape more than JD does). No VIA database submission, no support
for fpb's other branches, no feature flags beyond 5.2, no generalizing
unit-specific values. Upstream contributions remain the three-item list in
the README ground rules.

## Deliverables

- [ ] Public/private split executed; personal-data sweep done.
- [ ] LCD variant flag + README symptom mapping.
- [ ] Recovery-first public README.
- [ ] License/attribution notes; branding line.

## Execution record (2026-09-01)

Software parts done: the `AK820PRO_LCD_VARIANT_FPB` compile flag (both
variants build; symptom mapping in the readme), the recovery-first
"Jackrabbit fork" section prepended to `keyboards/a_jazz/ak820pro/readme.md`
(stock-image warning, bootloader-looks-dead, Tahoe libusb trap, EEPROM
erase, submodule build, provisioning order, mode-index oddity, attribution
+ bunny-mark line, no-warranty scope), and the companion toolchain made
reachable: `jdlien/time-util-ak820pro` forked and the `ak820pro-local`
branch (ak820ctl edits + the shipped asset sources incl. `flash_assets.bin`)
pushed, alongside the already-public `jdlien/qmk_firmware` and
`jdlien/ChibiOS-Contrib` forks.

Remaining for JD (deliberate):

- Decide whether the WORKSPACE repo (`jdlien/ak820-pro` -- CLAUDE.md, the
  plan, hostagent with absolute paths) stays private; the plan says it
  should. Everything a stranger needs lives in the three public forks.
- A final personal-data eyeball of the public readme/branches before
  announcing anywhere.
- The hardware checklist, which gates calling any of this "verified".
