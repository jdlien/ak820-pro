# The configuration menu's S0: the board's acceptance cases

What S0 must show on gremlin's board before it merges
([`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md), S0's proof). The host
tests (`scripts/menu_s0_test.c`) cover the pure modules: the owner, the input,
the slots, the fixture and `menu_ops.c` (the task, op 27, the menu's side of an
owner event). These cases cover what they can't: `display.c`, `lcd_bus.c`,
`sleep.c`, the HID dispatcher, and real DMA. Codex's code reviews asked for
each one ([`review-codex-config-menu-s0-code-2026-10-23.md`](review-codex-config-menu-s0-code-2026-10-23.md)
and its verification).

**The procedure for each case:**
- **Driven by** op 27 (`scripts/menu_s0_session.py`'s codec), op 1, and
  HC_BLITFAULT on the `devfault` build.
- **Read from** op 27 sub 5, the health counters (`ak820health.py --stalls
  --json`) and the sleep page (`ak820battery.py`).
- **Checked by photo** where pixels are the claim.

**Every case passes only if** `invariant_fail` stays 0 and ge25 doesn't move.

| # | Case | Build | How | Passes when |
|---|---|---|---|---|
| A1 | Op 27's framing through the real dispatcher | dev | a short report (length < 32), an unknown sub, sub 5 | the first two answer `RTC_UNHANDLED` at byte 0; sub 5 answers `0x07` at byte 0 and status 0 at byte 5 |
| A2 | The Camera page's exclusive dispatch | dev | op 1 twice (Camera); 10 s to settle; photo 1; sub 8; 30 s of pumping; photo 2 | sub 5: owner DEBUG, losses +1. Photo 2: every static cell (`V`, `:`, `%`, `5C`, `@`) still painted, none blanked by Health's spaces. The live digits are free to change |
| A3 | The dashboard's queues dropped at a handoff | dev | a long host title pushed (`ak820text.py`), and op 1 in the next report | sub 5 right after: gq and lq both 0 (byte 17). After op 1 twice more: the restore reaches DONE with gen + 1; photo: the title painted whole |
| A4 | A dashboard wake handed off to Fn+D | dev | **JD's hands:** cable out, slider on BT, Lights out (`Fn`+`B`); wait for the deep sleep; wake it with `Fn`+`D` (DBG_PAGE), so the Fn+D page takes the panel during the wake hold; cable back | the sleep page: the wake's display hold released with SLEEP_RC_DISPLAY's timed-out bit clear (not at `RC_HOLD_MAX_MS`). Whether the dashboard's queues were non-empty at the handoff isn't observable; A3 covers the drop itself |
| A5 | The session blocks sleep; a wake while open can't happen | dev | sub 4 (open); the sleep page's blockers | "menu" among the blockers (DSB_MENU, `ak820battery.py` index 14), gone after the close. The wake-while-open path is unreachable by design (DSB_MENU), so its handling is the host test's (panel_owner.c) and the wiring's (`display_sleep_wake`) |
| A6 | An injected loss dropped at a real ownership boundary | dev | sub 4 (open); sub 8 and op 1 in consecutive reports | sub 8 ends superseded (the drop) or done (the MENU handler took it first): both are terminal. The Health page paints whole |
| A7 | A real lost completion, retried and given up, under each owner | **devfault** | HC_BLITFAULT N=1, then N=2, under the dashboard, the fixture, Health, Camera, and the animation if gremlin's slot has frames | N=1: a retry succeeds, nothing repainted, losses unchanged. N=2, per owner: DASH, the phase goes back to RESIDUAL damaged, then a new generation to DONE; MENU, every slot repainted (photo matches the host's expected frame); DEBUG, the page repainted whole; ANIM, the animation stops and the dashboard is restored |
| A8 | The startup restore, interrupted | dev | sub 7 under the dashboard; op 1 during its CLEAR (sub 5 polled); op 1 twice more | WAITING under DEBUG, then a fresh restore from band 1 (gen + 1) to DONE. Photo: the dashboard whole |
| A9 | The animation refused under another owner | dev | **JD's hands:** `Fn`+`Delete` with the Fn+D page up, and with the fixture open | nothing happens, and no flash access (blit counters unchanged). Skipped if gremlin's animation slot is empty |
| A10 | The physical release cases, armed | dev | **JD's hands:** sub 6 arms; the knob's presses and releases, `Fn` released first, a timeout while held, a hold across a close, a pending tap-hold on another key, the knob remapped in VIA to a one-shot, an MT and an LT (then put back) | no key stuck or typed, every captured release consumed (sub 5 byte 23 back to 0), the remapped knob still opens the fixture |
| A11 | The workload | dev | `menu_s0_session.py`, ten repeats, then 300 s of the dashboard with a track playing | it exits 0: no failure, ge25 unchanged, `invariant_fail` 0 |
| A12 | RAM and the stacks | dev, daily, devfault | `build.sh`'s gap; `ak820 health` after A11 | the gap at least 128 B in every flavour; the stacks' paint watermarks recorded beside the last night's |

**The order:**
1. A1-A3, A5, A6, A8 and A11, with no hands.
2. Then the `devfault` flash for A7.
3. Then JD's session for A4, A9 and A10, one action a message.
4. Then A12.

Results go to [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md).
