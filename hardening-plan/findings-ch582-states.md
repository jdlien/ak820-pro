# CH582F state & pending-action tables (phase 3.2 spec)

Derived 2026-09-01 from `ch582f_ajazz.c` @ acaad04313 and CLAUDE.md's wire
captures. This is the behaviour the unification must preserve EXACTLY —
target: zero behaviour change.

## Concurrent concerns (why one flat enum was rejected)

| Concern | Variable(s) today | Driven by |
|---|---|---|
| Observed link state | `conn_state`, `is_module_connected`, `is_pairing`, `connected_slot`, `host_leds`, `linking_since` | rx 5B/5A frames (+ optimistic writes from user commands) |
| Desired profile | `requested_profile`, `connect_requested`, `usb_mode` | user commands (slider, slot keys) |
| Pending control action | `bounce_pending/time/target`, `select_pending/last_try/tries`, `pairing_pending/last_try/tries` | user commands, rx frames, timers |
| Module liveness | `module_alive` | any rx ACK |
| Frame TX queue | `tx_q`, head/tail, in-flight, stats | independent |

## Observed-state transitions (rx-driven; unchanged by this work)

| Event | From | To | Side effects |
|---|---|---|---|
| `5B 32` | any | CONNECTED | slot = target; clears pending select AND pair |
| `5B 31` | any | PAIRING | clears pending select AND pair (pair now CONFIRMED); LEDs cleared |
| `5B 33/34` | any | LINKING (stamp `linking_since` on entry only) | clears pending SELECT only (module acted; re-select would restart advertising and starve macOS reconnects). Pending PAIR survives — the module ignores `A6 51` mid-attempt, which is the whole reason the pair retry exists |
| `5B 36` | any | REJECTED (persists) | clears NOTHING pending — the timed select retry keeps going |
| `5B 23` | — | unchanged (periodic, ambiguous) | if a select is pending and under budget: re-send NOW (the module just became receptive — clock-only retries kept missing this window) |
| `5A d` (plausible, connected) | CONNECTED | — | adopt LED bits |
| `5A d` (plausible, LINKING ≥ 3 s) | LINKING | CONNECTED | missed-`5B 32` promotion; deliberately does NOT adopt this frame's LED bits |
| `61 0D 0A` | — | — | TX ack: release in-flight frame; sets `module_alive` |
| `5C d≤100` | — | — | battery only; NEVER connection state |

## User-command transitions

| Command | Effect on observed state (optimistic) | Pending action set |
|---|---|---|
| `ch582_set_profile(p)`, not pairing | LINKING, stamp `linking_since` | SELECT(p): send now, tries=1 |
| `ch582_set_profile(p)`, WAS pairing, p is BT1..3 | LINKING | BOUNCE(p): send a DIFFERENT slot now, then after 700 ms become SELECT(p) with tries=1. (Same-slot select while advertising is a measured no-op — 8 sends over 10 s drew zero responses) |
| `ch582_enter_pairing()` | PAIRING (optimistic; retry makes it true) | PAIR: send `A6 51` now, tries=1 (replaces any pending select/bounce) |
| `ch582_cancel_connect()` (USB) | IDLE; `connect_requested=false` | — (NOTE, pre-existing: a pending select is NOT cleared and its timed retries continue to fire, bounded by the try cap, even in USB mode. Harmless — the module ignores it and the cap ends it — preserved as-is for zero-change; worth revisiting later) |

## Pending-action timers

| Kind | Cadence | Budget | Cleared by |
|---|---|---|---|
| SELECT | 1500 ms (`CH582_SELECT_CONFIRM_MS`), plus event-fire on `5B 23` | 8 tries | `5B 31/32/33/34`, supersession, budget |
| PAIR | 400 ms (`CH582_PAIR_RETRY_MS`) | 12 tries (~4.8 s) | `5B 31/32`, supersession, budget |
| BOUNCE | one-shot at 700 ms (`CH582_BOUNCE_MS`) → becomes SELECT | — | supersession |
| Cold-boot select | 500 ms while `connect_requested && !module_alive` | uncapped | `module_alive` |

The cold-boot retry stays a SEPARATE guard, not a pa kind: its lifecycle
(uncapped, until first ACK, fires regardless of what else is pending) is
genuinely different, and folding it in would change edge behaviour.

## Invariants (do-not-break list)

1. A select retry MUST stop on `5B 33/34` — re-selecting an attempting
   module restarts advertising and starves slow macOS reconnects.
2. The bounce MUST name a DIFFERENT slot than the target, and the real
   select must follow as a distinct ordered frame (never coalesced — the
   TX queue's A1/A3 coalescing explicitly excludes 0xA6).
3. Pairing is confirmed by `5B 31`, never by having sent `A6 51`; the
   optimistic PAIRING display state precedes confirmation deliberately.
4. The 5A promotion needs all three gates: plausibility mask, state exactly
   LINKING, ≥ 3 s dwell — and must not adopt the promoting frame's LED bits.
5. `linking_since` is stamped only on LINKING ENTRY (repeated 33/34 frames
   must not restart the promotion window).
6. At most ONE pending action exists at a time (plus the independent
   cold-boot guard); supersession is total, never partial.

## Decisions at this review

- **Unify bounce/select/pair into one `pending_action` struct** with the
  tables above as the transition spec (the phase-3.2 default deliverable).
- **Full transition-table restructure of the observed state: NOT taken.**
  The observed-state switch is already a single readable rx handler whose
  cases match the table above one-to-one; rewriting it buys readability we
  now have for risk we don't need.
- **Host-side pure-model test: NOT taken now.** It requires extracting the
  parser from its hardware calls — a real restructure beyond zero-change.
  Instead the fault-injection shim (below) exercises the same sequences on
  the real parser, deterministically, over raw HID.
- **Fault injection**: instrumented builds gain `[07 13 7D len bytes...]`
  (HC_INJECT) — bytes are fed to the parser AS IF received from the UART,
  before real bytes, letting a host script replay every capture in this
  file (missed `5B 32`, decline sequences, garbage soup) and assert the
  resulting state via the conn-state readout. Drops/corruption are
  composed by the host choosing byte sequences.
