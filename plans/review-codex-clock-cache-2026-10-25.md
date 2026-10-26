# Codex: the Clock list's one RTC read a second (2026-10-25)

Three rounds, verbatim, then dispositions. The board pass on `22ec0d3d`
(`history/config-menu-p3-20261025/board-22ec0d3d.json`) showed passes to
23.3 ms and Clock settles of 1.18-1.29 s: `clock_sig()` and
`clock_example()` called `rtc_get_time()` (newlib's `localtime_r`) for every
example row on every scan.

1. `plans/review-prompt-clock-cache.txt`: `22ec0d3d..c374004b` (the cache, in
   a union with About's 12 B snapshot).
2. `plans/review-prompt-clock-cache-verify.txt`: `c374004b..c70e2c21` (jump
   signatures, row fields 5 and 6).
3. `plans/review-prompt-clock-cache-verify2.txt`: `c70e2c21..30f1e0cf` (a jump
   invalidates the examples in `menu_tick()`).

## Round 1 (c374004b)

**One P2 display regression should change before flashing:** [menu.c:745](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:745), interacting with `clock_sig()` at line 792.

The cache can hide a distinguishing signature during a host correction. Example: the panel shows **02:07:59**; between edges, the host sets **04:14:59**. Both minute rows retain signature `127`. At the next edge, the cached time becomes **04:15:00**, whose minute signature is also `127`. Those rows therefore keep showing **02:07 until 04:16**, despite the cache refreshing. Previously, scans could observe 04:14’s signature `126` and repaint. The signature compression predates this patch; suppressing that intermediate sample introduces this additional failure case. Notify and invalidate the active Clock cache **and rows** on calendar corrections.

Otherwise:

- **Union lifetime is sound.** Clock’s sole entry resets `have` at [menu.c:1364](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1364). About initializes its snapshot on entry; all snapshot reads are About-only. Neither page has children. Pop, reopen, loss repaint, op 27, stand-ins, `T_SAVED`, and page cuts expose no simultaneous use.
- Normal 16-bit wrap refreshes correctly. Deep sleep is blocked during menu sessions; reopening resets Clock. Validity changes appear at the next sampled edge, with disjoint valid/invalid signatures.
- An edge between signature calculation and painting can select different samples, but [menu_slots.c:265](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265) rechecks before commitment and restarts changed rows. No additional ordinary-tick consistency issue found.

No hardware-safety or BT-specific regression found. I inspected the exact commit blobs and uncommitted tests; I could not rerun builds/tests because process creation was unavailable.

## Round 2 (c70e2c21)

**The specific repro is fixed, but I would not close P2 completely.**

- **P2 — [menu.c:746](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:746):** midnight accepts *any* date. Show `2026-10-25 23:59:59`; host sets `2027-10-24 23:59:59`; next edge reads `2027-10-25 00:00:00`. `clock_follows()` returns true, Date’s signature matches, and **2026 remains displayed until another date change**. Validate the expected next date. The seconds arithmetic and midnight test themselves work for `dt > 1` within the 16-bit elapsed interval.

- **Alternation isn’t an unconditional commitment guarantee — [menu.c:807](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:807):** committed field 6 → sampled field 5 without repainting that row → sampled field 6 collides despite different text. Adjacent jumps that actually commit are safe; jump↔unset is disjoint. Tests settle every sample at [menu_s0_test.c:3568](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3568), missing this interleaving.

- **Entry caveat — [menu.c:1385](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1385):** resetting `have` clears jump history on the first read. Rapid exit/reentry before parent rows repaint can retain an ordinary Clock signature that aliases the new time. Invalidate Clock rows safely at entry.

An ordinary same-second sync adds **no menu RTC read or repaint**; the added comparison runs on the usual refresh ([menu.c:755](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:755)). The cursor-clearing hazard is avoided; the union remains 12 bytes.

No new hardware/BT flash-safety issue found. Exact commit blobs inspected; builds, mutants, and heap measurements weren’t rerun because process creation is blocked.

## Round 3 (30f1e0cf)

**All three prior defects are resolved for eventual repaint.** One qualification remains about “committed equals cache.”

- **Midnight:** [menu.c:745](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:745) correctly requires the next calendar date, including Gregorian leap years.
- **Jumps:** [menu.c:769](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:769) preserves `CK_JUMP` across subsequent reads until invalidation; alternating-signature collisions are eliminated.
- **Re-entry:** [menu.c:1392](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1392) resets the cache and invalidates all five examples, covering the first read too.

**Both invalidation sites are safe.** [menu_slots.c:158](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:158) abandons an affected PARTIAL cursor without reentrant painting, preserves highlight tracking and clear progress, and retains in-flight completion accounting. Reached stops remain latched; pending loss/busy conditions still prevent commitment ([menu_slots.c:269](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:269)).

**Yes, transiently, a committed row can disagree with the cache:** a jump sampled after `menu_tick()` can collide at [menu_slots.c:265](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265), allowing an already-painted PARTIAL row to commit, or an old COMMITTED row to appear settled. Identical time/month/day with a different year demonstrates this. The next tick invalidates it; no persistent alias remains. [menu_ops.c:154](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:154) runs that tick on every continuing Clock pass; early returns leave Clock. Indefinitely omitting it would defeat the guarantee.

No additional dev/BT flash blocker found in the requested range. Exact commit blobs and tests inspected; process creation blocked rerunning builds, mutants, or the reported 128 B heap measurement.

## Dispositions

- **Round 1, P2 (a set between edges aliasing the committed ticks): fixed**,
  in two steps. `c70e2c21` gave a jump's second its own signatures; round 2
  showed they could still collide, so `30f1e0cf` replaced them. A read that
  doesn't follow the last one by the edges counted is a jump (`clock_follows()`).
  `CK_JUMP` holds until `menu_tick()`, outside the scheduler's scans, which
  invalidates the five example rows. Invalidating from inside a signature
  would clear the slot `ms_step()` is painting, so it isn't done there.
  Tests: codex's case; the same case read by a scan and then an ordinary
  second read by a scan; two jumps in a row; a year-only set.
- **Round 1's other points: no change.** The union's lifetime, the 16-bit
  wrap, deep sleep (blocked in a menu session) and a sample split across an
  edge (rechecked before commit) were all found sound.
- **Round 2, P2 (midnight accepting any date): fixed in `30f1e0cf`.**
  `clock_follows()` requires the calendar's next day (month lengths,
  Gregorian leap years). Tests: codex's midnight with a year's set, and five
  ordinary midnights (Oct 31, Dec 31, Feb 28 and Feb 29 2028, Feb 28 2027).
- **Round 2, the alternating signatures not guaranteeing a repaint: fixed in
  `30f1e0cf`** (the invalidation; the signatures are gone).
- **Round 2, a quick re-entry keeping an aliasing signature: fixed in
  `30f1e0cf`.** The Clock's entry invalidates the example rows. Test: a
  re-entry 128 s on, before the top level painted.
- **Round 3, the transient (a jump read after `menu_tick()` lets a row
  settle on an aliasing signature for that pass): accepted.** It lasts one
  pass, since the next `menu_tick()` (each pass while the Clock shows,
  `menu_ops.c:154`) invalidates it. Nothing persists.
- **Mutants:** twelve, each failing `test_clock` (no cache; no fresh read at
  entry; no invalidation at entry; no jump detection; a jump never
  invalidates; a jump not held; midnight takes any date; no leap years; a
  date change never a jump; `l_first` 0; Date not excluded; wide ignored).
  Both builds pass; the dev heap gap stays 128 B. Flashed `30f1e0cf` at
  ~18:50.
