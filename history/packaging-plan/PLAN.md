# AK820 Pro — packaging plan (make the workspace the product)

Status: **DONE, 2026-09-01** — all five phases executed the same day; see the
execution record at the end. Restructured the *workspace* repo
(`jdlien/ak820-pro`); touches no firmware source. The three forks keep their
branches exactly where they are.

Goal: **one repo you clone and build.** A cold reader — a stranger with this
keyboard, JD in six months, or an agent opening the repo with no context —
should get from `git clone` to a flashed board without being told anything
that is not in the repo.

## Why now

The work is done and good. The packaging is not, and four measurements say so:

1. **The product is small; the delivery is not.** The entire deviation from
   fpb's base is **55 files, ~12,079 lines**, and all but five of those files
   live in `keyboards/a_jazz/ak820pro/`. Outside the board directory it is
   `sn32f2xx.c/.h`, `wear_leveling_efl.c`, `rgb_matrix.c` (16 lines) and the
   submodule pin. A **1.1 GB QMK fork exists to carry ~650 KB of our code.**
2. **There is no entry point.** Four repos under `jdlien/` plus two of fpb's,
   and nothing says which one you clone first. The one script that claims to
   bootstrap (`ak820pro-builds/ak820pro-mac-setup.sh`) clones *fpb's* old
   branch and hand-applies six `.diff` files — the exact practice
   `history/hardening-plan/phase-0-lockdown.md` abolished. Running it today builds the
   wrong firmware.
3. **A clean clone cannot build.** `env.sh` sets `QMK_HOME` to
   `$AK820_ROOT/qmk_firmware-ak820pro`, which does not exist; the firmware
   clone's submodules are all uninitialized; `chibios-ak820pro-patches.bundle`
   is at `c07bfe95` while the pin is `94b5cb45`.
4. **The repo reads as a lab notebook.** No README on a public repo,
   `CLAUDE.md` as the front door, two large plan folders that are history
   rather than guidance, and 50 `/Users/jdlien` hits across 10 files.

## Non-goals

- **Generalizing for upstream QMK.** Unchanged from `phase-5-publication.md`:
  personal-first, published for same-hardware owners. `UPSTREAM-CONTRIBUTIONS.md`
  stays the separate, deliberate track.
- **Vendoring `time-util-ak820pro`.** fpb ships it with no LICENSE file. A
  GitHub fork is the defensible form; copying it into this repo is not.
- **Mirroring AJAZZ firmware images.** Link the stock v1.13 binary and record
  its SHA256 so a user can verify the download. Do not redistribute it.
- **Touching firmware behaviour.** No board code changes. If a build comes out
  byte-identical before and after this work, that is the desired outcome.

## Decisions taken

| Decision | Why |
|---|---|
| `setup.sh` + `deps.lock`, **not** git submodules | Submodules force `--recurse-submodules` and drag ~700 MB of QMK and ChibiOS history for a ~650 KB payload; shallow submodules are a known footgun. A lock file puts the four SHAs somewhere a human reads, and `build.sh` already verifies pins in exactly this style. |
| ChibiOS patches stay **commits on a fork branch** | Non-negotiable; `history/hardening-plan/phase-0-lockdown.md` moved them off hand-applied diffs for cause. Nothing here reintroduces a `.diff` apply step. |
| The workspace repo stays **public** | Supersedes `phase-5-publication.md`, which concluded it should be private. The goal changed: people clone *this* repo. What survives from phase 5 is the personal-data sweep it required first. |
| Dependency clones live **inside** the repo, gitignored | Already what `env.sh` and all four hostagent scripts assume. Confirmed working 2026-09-01 by moving `time-util-ak820pro/` into place — zero script edits needed. |

## Phases

| Phase | Theme | Risk |
|---|---|---|
| 0 | A clean clone builds | low — scripts only |
| 1 | Portability: no absolute paths | low |
| 2 | The front door: README + doc split | zero |
| 3 | History collapse | zero |
| 4 | Release for the flash-only audience | low |

Phase 0 is load-bearing; 1–4 are independent of each other and can land in any
order once 0 is done.

### Phase 0 — a clean clone builds

The measure of done: on a machine that has never seen this project,
`git clone && ./setup.sh && ./build.sh daily` produces a binary that passes
`build.sh`'s existing structural checks.

- `deps.lock` — four pinned entries (repo, branch, SHA): `jdlien/qmk_firmware`
  @ `ak820pro-jdlien`, `jdlien/ChibiOS-Contrib` @ `ak820pro-patches`,
  `jdlien/time-util-ak820pro` @ `ak820pro-local`, `fpb/SonixFlasherC` @
  `fix_for_macos_tahoe`. Record why each pin exists, especially the
  SonixFlasherC one (`USE_LIBUSB=1`; SonixQMK/main is a regression on Tahoe).
- Rewrite `setup.sh` from `ak820pro-mac-setup.sh`: idempotent, shallow
  single-branch clones, `make git-submodule`, toolchain + venv + `qmk` CLI,
  builds `ak820ctl` and `sonixflasher`, then **verifies every clone's HEAD
  against `deps.lock` and refuses to continue on a mismatch**.
- Delete `ak820pro-mac-setup.sh` — do not leave a second, wrong bootstrap in
  the tree. Its useful content is the toolchain URL and the brew deps.
- `env.sh`: derive paths from the repo root (it already does) and drop the
  stale comment block pointing at `~/ak820pro`.
- Regenerate `chibios-ak820pro-patches.bundle` at the pinned SHA, or delete it
  and let `jdlien/ChibiOS-Contrib` be the single source. A recovery artefact
  that disagrees with the pin is worse than none.
- The venv needs `hid` **and** the `qmk` CLI. As of 2026-09-01 it has only
  `hid` (installed for the host agents), so `build.sh` still fails on `qmk`.

### Phase 1 — portability

- Template the absolute paths: `hostagent/*.sh`, `hostagent/*.py`, the three
  `com.jdlien.ak820pro.*.plist`, `assets-src/mkbunny.py`. Scripts should
  resolve the repo root from `$0` the way `build.sh` does.
- `hostagent/install-agents.sh`: generate the plists from templates with the
  real path substituted, install to `~/Library/LaunchAgents`, bootstrap them.
  Must install **timekeeper + nowplaying only** — `clocksync` is superseded,
  and running both puts two processes in contention for the exclusive raw-HID
  interface, which the script comments record as having twice masqueraded as a
  firmware fault. Handle the `bootout`/`bootstrap` teardown race (a bounded
  wait on `launchctl print`); a naive back-to-back reload fails with
  `Bootstrap failed: 5: Input/output error`.
- Rename the timekeeper's log from `~/Library/Logs/ak820pro-clocksync.log` to
  `...-timekeeper.log`. The old name reads as evidence the old agent is
  running and directly caused that confusion on 2026-09-01.
- `nowplaying-macos.sh` sends every `osascript` stderr to `/dev/null`, so an
  Automation-permission denial is indistinguishable from "nothing is playing".
  Log the failure at least once. (Also in `plans/BACKLOG.md`.)
- Never edit an installed plist with PlistBuddy: it silently strips the XML
  comments, which are most of those files' value. Regenerate from the template.

### Phase 2 — the front door

- `README.md`, recovery-first, structured for two audiences:
  - **Flash only** (most people): download stock v1.13 first — link +
    SHA256, and state plainly that there is no backup path once it is gone —
    then `Fn`+`Esc`, one flash command, one provisioning command. Mention the
    one-time pin short where it applies.
  - **Build**: `setup.sh`, `build.sh`, `flash.sh`, and the toolchain traps
    (`USE_LIBUSB=1`, the bootloader that looks like a dead board, the EEPROM
    erase on flash).
- Fold the durable parts of `ak820pro-builds/AK820PRO-HANDOFF.md` into the
  README and `docs/`, then retire the handoff: it assumes `~/ak820pro` and
  names the stale fpb branch in four places.
- `CLAUDE.md` keeps the agent-facing conventions (VIA enum append-only rule,
  the warnings, multi-session etiquette) and stops being the front door.
- `docs/` — the six topic docs — is the part of this repo that is already
  right. Leave it alone.

### Phase 3 — history collapse

- `history/hardening-plan/` and `history/clock-sync-plan/` → `history/`, with a short index
  saying what each project was and when it landed. Both are records; neither
  is guidance.
- Keep live and out of `history/`: `plans/BACKLOG.md` and
  `plans/CLOCK-FORMAT-PLAN.md` (the `Fn`+`C` 24 h/12 h/off toggle —
  verified 2026-09-01 as still unimplemented: no clock-format symbols in the
  firmware, nothing in the keycode enum).
- This plan collapses into `history/` with the rest when phase 4 is done.

### Phase 4 — release

- A GitHub release carrying what the flash-only audience needs: `via.bin` for
  **both** LCD variants (`AK820PRO_LCD_VARIANT_FPB` and the JD default),
  `flash_assets.bin`, `via.json`, and checksums for all of it.
- The variant choice is the single most likely "the firmware is broken" report
  from a stranger — an upside-down or inverted panel. Put the symptom → file
  mapping in the release notes, not only in the board readme.
- Reference `fpb/ajazz-ak820-pro` as the hardware citation it is: datasheets,
  `CH582F_PROTOCOL.md`, pinouts, stock images. It is not a component of this
  project and should not be cloned by `setup.sh`.

## Ground rules

- **No firmware behaviour changes in this project.** If board code needs
  editing to make packaging work, that is a finding, not a licence to change it.
- `flash.sh` preserves the VIA keymap across a flash and refuses to proceed if
  the backup fails. Nothing here weakens that.
- Pins stay verifiable. Any step that makes a build's provenance less checkable
  than `build.sh` makes it today is wrong, regardless of convenience.
- Personal-data sweep before anything is announced anywhere: absolute home
  paths, log locations, the LaunchAgent labels. Email in commits is expected
  and fine.

## Open questions

- Does `setup.sh` target macOS only? Everything measured here is Tahoe on
  Apple Silicon; `nowplaying-windows.py` exists but no Windows path is tested.
  Cheapest honest answer is to scope the README to macOS and say so.
- Is `hostagent/` part of the public product or a personal appendix? It is the
  most personal code in the repo and the most useful thing a stranger gets
  after the firmware itself.
- Keep `ak820pro-builds/` at all after phases 0 and 2 consume it, or fold the
  remaining artefacts into `reference/`?

## Execution record (2026-09-01)

All five phases done. No firmware behaviour was changed: both shipped binaries
build from `f7d3d97e11`, the revision that was already on the board.

**Phase 0.** `deps.lock` pins four dependencies by SHA; `setup.sh` replaces
`ak820pro-mac-setup.sh` (deleted) and verifies every clone against it. Proven
end to end — a run that downloaded the 221 MB toolchain, created the venv,
checked all four pins, initialized the submodules and built both host tools,
followed by a clean `./build.sh daily`. Three things only a real run would have
caught:

- `make git-submodule` shells out to the `qmk` CLI, so it cannot run before the
  venv exists. `setup.sh` drives `git submodule update` directly instead.
- **`lib/lufa` is not AVR-only.** The ChibiOS USB stack pulls LUFA's descriptor
  headers through `tmk_core/protocol/chibios/lufa_utils`, and omitting it fails
  at `ak820pro.c` with a missing `HIDClassCommon.h`. It is now in the set.
- The ChibiOS recovery bundle was stale by one commit — it stopped at
  `c07bfe95`, missing `94b5cb45` (the retained-RAM linker change). Regenerated
  against the pin and verified.

`build.sh` moved to the repo root beside `setup.sh` and `flash.sh`, and gained
an `fpb` flavour for the other panel revision — it rejected a second argument,
so the variant build documented in the README could not actually have run.

**Phase 1.** All absolute paths are gone from `hostagent/`, `scripts/` and
`assets-src/`; shell scripts derive the root from `$0`, Python from `__file__`.
The plists are now `.plist.in` templates rendered by `hostagent/install-agents.sh`,
which installs timekeeper + nowplaying only, waits out the `bootout`/`bootstrap`
teardown race, and migrates the old log. The timekeeper logs to
`ak820pro-timekeeper.log`. `nowplaying-macos.sh` gained a startup Automation
probe. The superseded `clocksync` plist was deleted; its one-shot script
survives with a header saying why.

**Phase 2.** `README.md` written for two audiences, recovery-first.
`AK820PRO-HANDOFF.md` and `handoff.html` retired, their durable content folded
into `docs/fonts-assets.md` (flash memory map, provisioning, the GIF slot).
`CLAUDE.md` is now working notes rather than the front door. Writing the README
surfaced a real error: the asset provisioning address was wrong (`0x100000`),
and `FLASH_ASSET_BASE` is `0x0CE0000` — checked against `graphics/lcd_bus.h`.

**Phase 3.** `hardening-plan/` and `clock-sync-plan/` are under `history/` with
an index; `BACKLOG.md` and `CLOCK-FORMAT-PLAN.md` moved to `plans/`. All
cross-references rewritten.

**Phase 4.** `scripts/make-release.sh` builds both panel variants, regenerates
the asset image, **verifies the generated `flash_assets.h` matches the firmware's
committed copy** (same source revision is not sufficient — ids are assigned by
sorted filename), and writes `SHA256SUMS`. The payload is assembled in
`ak820pro-builds/release/`. Nothing has been published: cutting a public release
is JD's call.

**Open questions, answered.** macOS only, and the README says so. `hostagent/`
is part of the public product. `ak820pro-builds/` survives, now holding build
artifacts, the patch bundle and `UPSTREAM-CONTRIBUTIONS.md`.

**Left for JD:** tag and upload the release; the personal-data sweep is done for
code but the `history/` Codex reviews still contain absolute home paths, which
is acceptable for a lab record and worth knowing before pointing anyone at them.
