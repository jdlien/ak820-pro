# Phase 4 — Durability niceties

**Theme:** small persistence wins that earlier phases make safe. Last on
purpose: both items write internal flash, which is this board's most
dangerous peripheral, and both benefit from phase 1's watchdog + soak and
phase 2's write-path audit being done first.

Shared constraints for both items:

- All writes go through the normal eeconfig path so
  `backing_store_pre_write_hook()` (drain in-flight LCD blit) covers them.
- **No block-size change needed:** `kb_config_t` is
  `{ uint8_t bt_profile; uint8_t _pad[3]; }` — the three reserved pad bytes
  hold `rtc_period` (u16) + `lcd_brightness` (u8) exactly. Define the
  layout explicitly (with in-band validity sentinels, since the pad's
  existing content on-device must read as "unset") and the versioning
  question disappears. Still append-only if it ever grows past the pad.
- Write **once on settle**, never per adjustment step. Flash wear and the
  historical hang class both scale with write count.
- **Bring `save_bt_profile()` under the same discipline**: it currently
  writes eeconfig immediately on every slot change — mildly inconsistent
  with the settle rule this phase establishes. Route all kb-config
  persistence through one coalescing deferred flush (dirty flag + settle
  timer on the 10 Hz tick) so every field, present and future, gets the
  same write policy. Slot changes are rare, so this is hygiene, not a fix.

## 4.1 Persist the converged RTC divider period

The trim currently re-converges from `RTC_PERIOD_INITIAL 33600` every boot —
a hand-measured, per-unit, temperature-dependent seed that CLAUDE.md marks
as never-upstreamable. Persisting the converged value makes the seed
irrelevant and works on any unit; CLAUDE.md already names this as the
durable fix, "not yet built".

- New field in the kb eeconfig block: `rtc_period` (u16; 0 = unset).
- **Settle definition — do NOT assume monotonic convergence.** The trim only
  measures when accumulated drift reaches the ±2 s threshold, so near lock
  the windows grow very long (that is the design), and quantisation or a
  temperature change can make step sizes non-monotonic — the recorded trace
  (695 → 324 → 232 → 79 → 46) happened to shrink, it isn't guaranteed to. A
  "two consecutive small steps" rule could therefore wait forever in an
  ordinary session. Instead: **persist any accepted, sanity-checked trim**
  after a minimum uptime (e.g. 10 min), whenever it differs from the stored
  value by ≥ a threshold (e.g. 32 ticks). Convergence then persists
  incrementally — each boot starts from the best value seen so far — and
  temperature wander below the threshold causes zero rewrites. Expected
  write rate: a few writes total during initial convergence, then ~never.
- Boot: use stored value if plausible (sanity range ~28,000–40,000; the ILRC
  is spec'd loosely around 32 kHz), else fall back to
  `RTC_PERIOD_INITIAL`. Keep the seed as the fallback, now allowed to be
  the nominal-ish value for a fresh unit.
- Verification: cold boot with a stored value → zero `[rtc]` trim/snap
  events in the first 15 minutes (the 33600-seed boot already demonstrated
  what a good seed looks like); erase the field → confirm convergence path
  still works and re-persists.

Out of scope, recorded so nobody re-derives them: the PCF8563's own ~58 ppm
drift (host cron resync handles it; the trim cannot), the ~±0.5 s phase
quantisation floor, and the per-sync SN32-side phase offset.

## 4.2 Persist the LCD backlight level

`DISPLAY_BRIGHTNESS_DEFAULT` is compile-time because "every kb-eeconfig
write is an internal-flash program/erase, i.e. the thing that wedges this
board" — a decision that **predates** `backing_store_pre_write_hook()` and
the settle-gating. Revisit it now that the write path is guarded:

- New field: `lcd_brightness` (u8, 0–9; sentinel 0xFF = unset → default 5).
- Write on settle only: level unchanged for ~5 s after the last
  `SCR_UP`/`SCR_DN` (the `RGB_SETTLE_MS` pattern already in
  `rgb_matrix_eeprom_flush_allowed`). A whole session of fiddling costs a
  handful of writes.
- Consider the same for the indicator LED levels only if they ever grow a
  runtime adjustment; today they are compile-time and can stay so.

Cost/benefit is honest here: this is a convenience (survive power cycles
without re-dimming), not robustness. If the phase-2 audit leaves any doubt
about the flash-write path, **drop this item** — 4.1 has real value; 4.2 is
optional.

## Execution record (2026-09-01)

Implemented as commit 08aecac174. Deviations from the phase text, all
deliberate: the BT profile write moved into the same coalesced deferred
flush (finding 14) rather than staying immediate; the brightness persist
hooks the user-gesture paths only, because the bootloader splash forces max
brightness through the raw setter and must not clobber the stored level;
the WDT test hook's poke moved to bit 7 of the brightness byte (reads as
unset → self-heals) since the RTC period now owns the old pad byte; and the
trim persist follows the incremental any-sane-value policy (Codex #15),
not a settle detector. Hardware verification is on the checklist. **Accepted regression** (Codex
phase-4 review #2): a BT slot change followed by power loss inside the ~5 s
settle window boots into the previous slot -- the old code persisted the
slot immediately. Judged acceptable: one keypress recovers, and the
uniform write policy is what keeps flash writes rare and guarded.

## 4.3 Documentation close-out (whole plan)

- Update CLAUDE.md: new module map, the WDT and its test procedure, the
  `[health]` baseline numbers, the persisted-fields layout and the
  append-only rule, and prune sections the plan made obsolete (e.g. the
  "not persisted" backlight note, the patch-reapply loop). **Priority
  rewrite: the "RGB field rate — three constants move together" section and
  its step-trading tables** — superseded by `SN32F2XX_RGB_PWM_FREQ`
  pinning the clock (steps are free now; `SPD_STEP` is 4), and a stale
  version of that section is actively dangerous since it instructs exactly
  the kind of compensating step-trades that are no longer needed. Also
  bring the effect list / `rgb_mode_short()` notes current (RAINFALL,
  DRIFT, alphas_mods' speed-as-second-hue readout).
- The findings files and state-table doc stay in `hardening-plan/` as the
  audit record.

## Deliverables

- [ ] `rtc_period` persisted on settle; clean-boot verification both with
      and without a stored value; eeconfig versioning behaviour recorded.
- [ ] `lcd_brightness` persisted (or the item explicitly dropped, with the
      reason recorded here).
- [ ] CLAUDE.md brought current; plan directory left as the record.
