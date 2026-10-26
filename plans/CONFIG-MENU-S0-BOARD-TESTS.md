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
| A1 | Op 27's framing through the real dispatcher | dev | an unknown sub (10), and sub 5 | the unknown sub answers `RTC_UNHANDLED` at byte 0; sub 5 answers `0x07` at byte 0 and status 0 at byte 5. The short-report guard (length < 32) can't be reached over USB: `raw_hid_task()` always passes 32 bytes. It is checked by reading the source |
| A2 | The Camera page's exclusive dispatch | dev | op 1 twice (Camera); 10 s to settle; photo 1; sub 8; 30 s of pumping; photo 2 | sub 5: owner DEBUG, losses +1. **Required in photo 2:** the clock line's two colons, which never change, still painted. Health's spaces falling through would blank them. **Conditional:** `V`, `%` and `5C` when photo 1 had them; `@` only when the raw battery report was fresh in both photos, since `cam_compose` drops it otherwise. The live digits are free to change |
| A3 | The dashboard's queues dropped at a handoff | dev | op 27 sub 9, the handoff probe: under a DONE dashboard it queues three glyphs (`gq`) and a one-character lock label (`lq`), then hands the panel to the Fn+D page in the same call | the reply's bytes 7-10: gq and lq both non-zero before, both 0 after. A refused probe (the dashboard not DONE) is inconclusive: wait, and run it again. Then op 1 twice more: the restore reaches DONE with gen + 1, `invariant_fail` 0 |
| A4 | A dashboard wake handed off to Fn+D | dev | **JD's hands:** cable out, slider on BT, Lights out (`Fn`+`B`); wait for the deep sleep; wake it with `Fn`+`D` (DBG_PAGE), so the Fn+D page takes the panel during the wake hold; cable back | the sleep page: the wake's display hold released with SLEEP_RC_DISPLAY's timed-out bit clear (not at `RC_HOLD_MAX_MS`). Whether the dashboard's queues were non-empty at the handoff isn't observable; A3 covers the drop itself |
| A5 | The session blocks sleep; a wake while open can't happen | dev | sub 4 (open); the dev sleep arm (op 14 sub 4) with a short delay. While it's ARMED it samples the current blockers each pass (`ds_blocked`, its reply page). Read that live record **while still ARMED and the session still OPEN**, within the fixture's 24 s idle (the arm gives up only 60 s after its delay, after the fixture has closed itself, so the give-up's record proves nothing). Check sub 5's session OPEN beside it, then cancel the arm. Close, arm again, read a fresh live sample, cancel | DSB_MENU (0x4000, "menu") in the first record, absent from the second. The sleep page's `ds_wanted_blocked` isn't used: it updates only when the ladder wants sleep. The wake-while-open path is unreachable by design (DSB_MENU), so its handling is the host test's (panel_owner.c) and the wiring's (`display_sleep_wake`) |
| A6 | An injected loss dropped at a real ownership boundary | dev | sub 4 (open); sub 8 and op 1 in consecutive reports, repeated until one ends superseded (up to 20 tries) | **An observed `superseded` is required:** that's the boundary dropping the loss. A `done` means the MENU handler took it first, which proves ordinary handling only: inconclusive, and the trial is repeated. After each: the Health page paints whole |
| A7 | A real lost completion, retried and given up, under each owner | **devfault** | HC_BLITFAULT (`[0x07, 0x13, 0x77, N]`) N=1, then N=2, armed and then **triggered** by a known DMA: under the dashboard and the debug pages, the next clock second (their seconds repaint); under the fixture, sub 0 toggling its pattern. Then the animation, if gremlin's slot has frames. **Read with `ak820 health --json`:** `blit_timeouts` (page 1), `vitals.blit_retry_successes` and page 6's `blit_irq_lost`. `ak820health.py --stalls` doesn't fetch page 6 | **Within 3 s of the trigger:** N=1, blit timeouts +1 and retry successes +1, losses unchanged, nothing repainted. N=2, timeouts +2 and op 27's losses +1, then per owner: DASH, the phase back to RESIDUAL damaged, then a new generation to DONE; MENU, every slot repainted (photo against A13's frame); DEBUG, the page repainted whole; ANIM, the animation stops and the dashboard is restored. **An empty animation slot leaves ANIM's case outstanding:** recorded as not run |
| A8 | The startup restore, interrupted | dev | sub 7 under the dashboard; op 1 during its CLEAR (sub 5 polled); op 1 twice more | WAITING under DEBUG, then a fresh restore from band 1 (gen + 1) to DONE. Photo: the dashboard whole |
| A9 | The animation refused under another owner | dev | **JD's hands:** `Fn`+`Delete` with the Fn+D page up, and with the fixture open | nothing happens, and no flash access (blit counters unchanged). Skipped if gremlin's animation slot is empty |
| A10 | The physical release cases, armed | dev | **JD's hands:** sub 6 arms; the knob's presses and releases, `Fn` released first, a timeout while held, a hold across a close, a pending tap-hold on another key, the knob remapped in VIA to a one-shot, an MT and an LT (then put back) | no key stuck or typed, every captured release consumed (sub 5 byte 23 back to 0), the remapped knob still opens the fixture |
| A11 | The workload | dev | `menu_s0_session.py`, ten repeats, then 300 s of the dashboard with a track playing | it exits 0: no failure, ge25 unchanged, `invariant_fail` 0 |
| A12 | RAM and the stacks | dev, daily, devfault | `build.sh`'s gap; `ak820 health` after A11 | the gap at least 128 B in every flavour; the stacks' paint watermarks recorded beside the last night's |
| A13 | A, then partial B, then A, and F2: the pixels | dev | sub 4 (open), wait for `pixels_done`, photo; sub 0 pattern 2 with n = 13, wait for the stopped flag (byte 30), photo; sub 0 pattern 0, wait for `pixels_done`, photo; sub 0 pattern 3 (F2), wait, photo | each photo matches its expected frame from `menu_s0_test frames <dir> 13` (fixture-A, fixture-B-stop13, fixture-A-again, fixture-F2): the same slots in the same colours. The frames draw a glyph's cell as light grey where the photo has the glyph |

**The order:**
1. A1-A3, A5, A6, A8, A11 and A13, with no hands.
2. Then the `devfault` flash for A7.
3. Then JD's session for A4, A9 and A10, one action a message.
4. Then A12.

Results go to [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md).
