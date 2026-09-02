# Phase 3 — Structural refactors

**Theme:** maintainability. Move code, don't change behaviour — except 3.2,
which is the one deliberate behavioural restructure and gets the strictest
gating. Every step: build, `stat` the binary, flash, soak (phase-1 harness),
commit. One step per flash.

**Preserve the comments.** The tree's inline documentation is the product of
hard-won debugging; a move that drops or orphans comments is a regression
even if the code is identical.

## 3.1 Split `ak820pro.c` (1,389 lines) into cohesive modules

Mechanical extraction, one module per commit, no logic changes:

| New file | Moves | ~Lines |
|---|---|---|
| `hid_protocol.c` | `raw_hid_receive` dispatch; `flash_command` + paging state; `text_command`; RTC channel helpers; `via_custom_value_command_kb` | 300 |
| `bt_ui.c` | `bt_pair_hold_task`, arm/disarm handling, `save_bt_profile`/`last_bt_profile`, wireless-mode tracking | 150 |
| `indicators.c` | `pwm_tick_init/cb`, `indicators_tick`, duty tables, `led_update_kb`, lock-state accessors, charge detect | 200 |
| `consumer_mod.c` | `process_modified_consumer`, `modified_consumer_task`, held-mods state | 80 |
| `param_overlay.c` | `param_status_task`, `rgb_mode_short`, `rgb_repeat_*` (hold-to-repeat) | 200 |
| `ak820pro.c` (remains) | init, `process_record_kb` (dispatching to the above), `housekeeping_task_kb`, eeconfig-flush hooks, instruments | 400 |

Rules:

- `process_record_kb` stays one function; extracted handlers are called from
  it (`if (!bt_ui_process_record(kc, rec)) return false;` style), so the
  event flow remains readable top-to-bottom in one place.
- Internal state stays `static` in its new module; anything that must cross
  modules gets a named accessor, not an `extern` variable.
- `housekeeping_task_kb` keeps its explicit call list (it is short and the
  ordering is meaningful — e.g. `conn_status_update` before
  `draw_text_slot`, `rtc_task` gated on `!anim_active()`). No task-table
  indirection; it obscures ordering for zero gain at six calls.
- Keep the `#ifdef PARAM_OVERLAY` compile-out property intact — `config.h`
  documents it as fully removable; a module boundary makes that cleaner
  (`param_overlay.c` conditionally in `rules.mk` `SRC`).
- After each extraction the binary should be near-identical (same section
  sizes ±alignment); a large delta means something changed that shouldn't.

## 3.2 CH582F driver as an explicit state machine

`ch582f_ajazz.c` (794 lines) is correct but accreted: five parallel
pending-flag/timer pairs (`pairing_pending`, `select_pending`,
`bounce_pending`, the 5A-promotion dwell, the cold-boot retry), each added by
a separate incident. The next BT bug will be an interaction between two of
them.

**Not one flat enum.** The driver's concerns are genuinely concurrent, not
mutually exclusive: the *observed* radio state (what `5B` frames report),
the *desired* profile, the *pending control action* (a pairing retry runs
while the UI already optimistically shows PAIRING; the bounce temporarily
selects a different slot while the desired target is unchanged), and the
frame TX queue, which operates independently of all of it. Flattening those
into one enum either explodes combinatorially or silently discards valid
simultaneous conditions. Structure instead as **separate small machines**:

- `observed_link_state` — driven purely by rx frames (`5B`/`5A`), the
  edge-triggered reality plus the promotion heuristic.
- `pending_control_action` — one `{kind, target_slot, deadline, tries}`
  struct replacing the five flag/timer pairs (kinds: none / select /
  pair-retry / bounce-then-select / cold-boot-retry). At most one active;
  supersession rules explicit.
- Desired profile and the TX queue stay what they are, independent.

Sequencing (each its own flash + soak):

1. **Parser/validation fixes from phase 2 land FIRST, separately** — frame
   validation, malformed-frame counter, any resync hardening. Never fold
   them into the behavioral restructure; a clean parser baseline is what
   lets a transition regression be distinguished from a parser one. (Resync
   already exists as a rolling 3-byte window — verify, don't rebuild.)
2. **Unify the five flag/timer pairs into `pending_control_action`** with
   zero behavior change. This is the default deliverable, not a fallback —
   most of the interaction-visibility win at a fraction of the risk.
3. **Only then decide** whether a fuller transition-table restructure of
   `observed_link_state` still buys anything. It may not.

Verification (beyond the ordinary soak):

- Write the state/action tables as a document first
  (`findings-ch582-states.md`), reviewed against CLAUDE.md's BT sections and
  the wire captures — they are effectively the spec, including the traps
  (`A6 <slot>` declined while advertising → bounce via a *different* slot;
  `A6 51` dropped during a connect attempt → retry until `5B 31`; select
  retry MUST stop on `5B 33/34`; `5B 36` persists and means "attempt
  failed"; the 3 s `5A` promotion with its three gates). Behaviour change
  target: **zero**; keep the tx counters and `[ch582]` line.
- **Fault injection, because a green happy-path soak proves little** — the
  whole point of this driver is recovery from rare wire failures that
  ordinary pair/unpair cycles won't reproduce. Add a compile-time shim
  between serial input and parser that can drop, delay, duplicate, and
  corrupt selected frames (`5B 32` dropped, truncated frames, garbage
  bytes), driven by a raw-HID or magic-key control.
- **Host-side model test of the transition logic**: the parser + transition
  reducer is pure (bytes in, state out) — compile it on the host and replay
  the documented wire captures plus fault sequences as a regression suite.
  Costs no MCU time and survives future changes.
- On-hardware matrix: pair/unpair on all three slots, the cancel-pairing
  bounce, an unreachable slot (`5B 36` path), 2.4G mode, media keys over BT
  while LINKING, and a macOS slow directed-advertising reconnect. If any
  regress, revert and retry smaller.

## 3.3 Compile-time enforcement of the invisible couplings

- `_Static_assert(ARRAY_SIZE(bkl_duty) == BKL_MAX_LEVEL + 1, ...)`; same for
  `ind_duty`.
- **enum ↔ `via.json` `customKeycodes[]` index matching:** a build-time
  check — small Python invoked from `rules.mk` (or a manual `scripts/`
  check run by `build.sh`) that parses `via.json`, counts
  `customKeycodes`, and compares against a generated count header or a
  grep of the enum. Failing the build beats a silently corrupted VIA keymap.
- **Fn-layer mask:** move the layer enum (`WINBASE..MACFN`) from `keymap.c`
  into `ak820pro.h` so `ak820pro.c` derives the Fn mask
  (`(1<<WINFN)|(1<<MACFN)`) instead of hand-writing `(1<<1)|(1<<3)`.
  (Keymap-defines-layers is QMK convention, but this board's core code
  already depends on the indices — the coupling exists; name it.)
- Replace the hand-written `adv = big ? 10 : 6` in `draw_playback()` with
  the named cell-width constants used elsewhere (add
  `FONT_SMALL_ADV`/`FONT_BIG_ADV` defines beside `DISPLAY_TEXT_MAX_*`), and
  note that runtime `cell_w` comes from the flash index — the constant must
  match the provisioned atlas, which is exactly why it should have one name.
- `_Static_assert` the vertical layout budget: the y-coordinates in
  `display.c` (`STATUS_Y - LOCK_Y >= lock band min`, bands fit in 128 rows,
  padlock fits its clear rect — the bug that stranded lit pixels).

## 3.4 Text-band arbiter in `display.c`

The band priority chain (pair hint > param overlay > conn status > host
text) is implicit in call ordering and scattered `if` guards across
`conn_status_update`, `display_set_param_status`, `display_set_pair_hint`
and `draw_text_slot`. Make it explicit:

- Each producer writes its own slot (string + active flag + expiry); one
  arbiter function, called once per housekeeping tick, picks the
  highest-priority active slot and owns the dirty-tracking. The arbiter
  feeds the staged glyph-queue path (`lcd_draw_flash_text_staged` + pump +
  cell diff, commit 9dd6300e7b) — it is the natural single entry point for
  that machinery, and no band producer should ever call a blocking draw for
  band text again.
- Fixes-by-construction the class of bug already hit once: same-buffer
  pointer-compare dirty tracking missing a content change (`REJECTED` →
  `PAIRING` rewriting `conn_status_buf` behind an unchanged pointer).
  Arbiter compares (producer, generation), each producer bumps a generation
  counter on any write.
- Behaviour targets stay exactly as documented: hint outranks everything
  while active; `CONNECTED` holds ~3 s then releases; overlay borrows, host
  text returns; wired mode shows nothing from the conn producer.
- **Invariants from the 2026-09-01 shadow-corruption fixes (b75507a600,
  d770b64937) — the arbiter must preserve these:**
  (a) *A shadow may only claim "already painted" for pixels still on the
  panel.* Three owners overlap inside the 14px gutter (icon x0..11, param
  overlay from x4, line 1 from x2); with a diffing renderer, one owner's
  clear landing on another's pixels is PERMANENT damage, not flicker — the
  diff never repaints what it thinks is present. Every clear goes through
  `band_clear()`, which invalidates any overlapping shadow; keep that as
  the single clear path and a fourth owner is covered automatically.
  (b) *Icon-first ordering is load-bearing in both directions* — neither
  pure ordering is safe; the overlap is handled explicitly
  (`icon_clobbered`). Do not "fix" by reordering.
  (c) *The glyph pump stays on the main loop (~390 Hz)*, never the 10 Hz
  tick (measured: 2 s/line at 10 Hz), and composing lines in RAM is
  strictly worse (spi1_rw is a spiExchange per BYTE; 5.9 KB SRAM).

## 3.5 Opportunistic, same files, separate commits

- `display.c` (1,268 lines) splits along the same seams if 3.4 makes it
  natural (`band_text.c`, `band_clock.c`, …) — only if the arbiter work
  already forces the file open; do not split for its own sake.
- Delete dead code found by the phase-2 sweep (e.g. anything orphaned by
  earlier fixes) — each deletion its own commit with the CLAUDE.md tie-in.

## Execution record (2026-09-01)

- **3.1 done** (five commits, one module per commit, both flavors building
  under -Werror after each): bt_ui, kb_eeconfig, consumer_mod,
  param_overlay, indicators, hid_protocol. ak820pro.c: ~1550 → 564 lines.
- **3.3 done**: shared layer enum + derived Fn mask, check_via_sync.py in
  build.sh, named font advances, layout/duty _Static_asserts.
- **3.2 done at the "default deliverable" level**: pending_control_action
  unification (commit c383ae2033), spec'd first in findings-ch582-states.md
  with the do-not-break invariants; the full observed-state table rewrite
  and the host-side pure-model test were considered and NOT taken (decisions
  recorded in the states doc). Fault injection: HC_INJECT + HC_CONN +
  scripts/bt_faults.py replay the wire captures against the real parser.
  One deliberate nuance: PA_BOUNCE survives 5B 31/32 exactly as
  bounce_pending did.
- **3.4 done differently than planned**: the band arbiter as designed
  (per-producer slots + priority picker) already existed after the peer
  session's b75507a600/d770b64937/831cc67703 — conn_status_update is the
  arbiter, band_clear enforces the shadow invariant. What actually remained
  were the audit's blocking paths, now closed (commit ba2d6a2cd4): nothing
  ever blocks on the glyph queue (defer/discard replaces gq_flush), and the
  clock band (clock + playback) rides the queue on a third shadow slot.
  Lock band was already per-slot diffed by the peer; battery/digit stay
  blocking at their measured ~2-6 ms (accepted).
- **3.5**: display.c was NOT split further (the arbiter work didn't force
  it); no dead code found beyond sn32f2xx_blank(), kept deliberately
  (audit C-3).

## Deliverables

- [ ] `ak820pro.c` ≤ ~450 lines, five new modules, per-module commits,
      binary-size parity checks recorded.
- [ ] `findings-ch582-states.md` state/action tables reviewed; parser fixes
      landed separately first; `pending_control_action` unification landed;
      further-restructure decision recorded; fault-injection shim + host
      model test in place; full BT soak matrix green.
- [ ] Static asserts + via.json build check in place; a deliberate mismatch
      fails the build (tested).
- [ ] Band arbiter landed; the documented priority behaviours re-verified on
      hardware.
- [ ] CLAUDE.md file-map table updated for the new layout.
