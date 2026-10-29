# Codex's review of the Font setting plan (2026-10-28)

The plan: [MENU-8X16-PLAN.md](MENU-8X16-PLAN.md), as revised for the Font
setting (both faces, switched at run time, and the song text's face).
Reviewer: codex (`gpt-6-astra`, reasoning high, read-only), with the prompt
asking for feasibility, design correctness, gaps and contradictions against
the code in `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` (the
`font-test` checkout, `ecb10f0e9b` plus the Font test page).

**Verdict: "Not ready as written. Once these findings are addressed, the
plan is ready to build."** Every finding was checked against the code and
accepted; the plan is revised for each (dispositions below the review).

## The review, verbatim

Firmware references below are relative to `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`.

1. **P1 — The face can change while the dashboard owns the panel.**  
   B5 restores the face through the live record, but `menu/profiles.c:769–779` accepts that record over raw HID without requiring an open menu. `hostagent/ak820profiles.py:264–270` exercises this path. Meanwhile, `graphics/display.c:3487` skips text rendering unless `text_dirty` is set. Reading the face only when queuing a line therefore leaves unchanged song text in the old face.

   **Change the plan:** every effective face change must notify the display and, when open, the menu. Preserve queued glyphs’ original font IDs and schedule the new text through the existing staged path. Test live restore with the menu closed, unchanged text, and a repaint already in progress. The menu-close test cannot cover this.

2. **P1 — Reset needs the same geometry transition as the Font option; ordinary page pushes do not clear.**  
   B5 describes “the staged path a page push uses,” but choice-page entry calls `show(false, false, ...)`, which only retargets (`menu/menu.c:1868–1872`, `2091–2092`). Reset also only retargets after applying defaults (`menu/menu.c:2449–2459`). Neither operation clears old geometry or recomputes ancestor frames’ paging.

   **Change the plan:** explicitly call the appropriate per-face layout through `ms_set_layout`, whose banded clear and slot invalidation are implemented at `menu/menu_slots.c:121–137`. Use one geometry-transition routine for Font selection, successful Reset, and external live restores. Keep list cursors and recompute their tops; handle Help/About scrolling separately because their position lives in `top`, not `cursor` (`menu/menu.c:2403–2410`).

3. **P2 — B5’s profile reader/writer inventory is incomplete.**  
   `prof_differs()` captures `PF_LIVE` and compares `PR_BVIEW` byte-for-byte against saved records (`menu/profiles.c:316–325`). Adding the face bit to that shared capture would make Small falsely produce the modified-profile `*`.

   Validation is also shared: `body_ok()` checks the entire byte, and both saved-record validation and raw-HID live apply use it (`menu/profiles.c:119–135`, `772`). There is no independent existing live validator whose check can simply be masked. The Win/Mac records use `PF_SIDE` and the same capture/apply machinery (`menu/profiles.c:540–546`). Host decoding indexes the unmasked byte (`hostagent/ak820profiles.py:290–291`).

   **Change the plan:** specify live-only face packing, readout-only profile comparison, context-appropriate validation, and face-preserving saved-profile/`PF_SIDE` application. Mask the readout before its setter and apply the face only for live restoration. Update host decoding to show the readout and face separately. Test profile keys and Win/Mac flips as well as menu loads.

4. **P2 — B2 does not finish adapting the F3 fixture.**  
   Replacing its `TEXT_W` literal is insufficient. F3 still uses eight rows, a 14-pixel pitch, and a 20-cell `mt_line_t` (`menu/menu_fixture.h:17`; `menu/menu_fixture.c:33–41`, `173–187`). With 16-row glyphs, adjacent rows overlap and the eighth reaches pixel row 128. The survey identifies this, but B2 only explicitly schedules the width fix.

   **Change the plan:** either keep F3 explicitly on Cozette or adapt its row count, pitch, title, separator, strings, navigation and layout descriptor together. Update the board drivers’ eight-row assumption too (`scripts/menu_s1_gate.py:47`), while retaining F1’s atlas geometry.

5. **P2 — The branch/B7 sequence is contradictory and can break B5’s build.**  
   The current enum has `N_FTEST = 61`, hence `N_COUNT = 62`, with an assertion requiring `N_COUNT <= 63` (`menu/menu.c:55–58`). Adding two nodes before removing `N_FTEST` makes 64. Conversely, branching from `ecb10f0e9b` as specified at `plans/MENU-8X16-PLAN.md:182–185` already excludes the page B7 proposes removing.

   **Change the plan:** choose one baseline explicitly. Remove the test page before B5 when starting from `font-test`, or drop B7 when starting from `ecb10f0e9b`.

6. **P2 — The promised test ordering and coverage do not match the named harness.**  
   The plan promises passing tests in both faces from B2, but postpones most geometry-dependent expectations and bounds checks until B8. Existing expectations directly encode old geometry and repaint counts (`scripts/menu_s0_test.c:3663–3682`, `3722–3748`).

   More importantly, that executable does not compile `kb_eeconfig.c`, `display.c`, or `lcd_bus.c`; its battery setting is a separate fake variable (`scripts/menu_s0_test.c:9–20`, `1341–1344`). It cannot establish byte preservation or dashboard queue/shadow correctness.

   **Change the plan:** move prerequisite assertions, bounds checks and expected-frame updates into their corresponding implementation commits. Put persistence tests in `scripts/diag_sim/kbee.c`, which compiles the real settings implementation, and update `scripts/profiles_test.c` alongside B5. Name a concrete harness or board procedure exercising the real dashboard rendering paths for B6.

7. **P2 — The pseudo-font branch needs an explicit completion/failure contract.**  
   The glyph pump interprets `false` as “busy; retry this glyph” (`graphics/display.c:3076–3078`). `lcd_blit_mono()` instead returns false for an invalid rectangle or failed transfer (`graphics/lcd_bus.c:403–414`, `440–444`). Forwarding its result directly could indefinitely retry a bad rectangle, which does not latch a display loss.

   **Change the plan:** retain the busy guard before entering the pseudo-font branch (`graphics/lcd_bus.c:834`), distinguish deferral from a consumed failed operation, and route failures through existing loss recovery. Explicitly budget the synchronous expansion/send of an 8×14 glyph—224 pixel bytes—within the whole dashboard pass. Add busy-DMA, transfer-failure and owner-transition checks; menu byte-budget assertions do not test this integration.

8. **P2 — The font cost omits the new icon and leaves table sharing unspecified.**  
   The existing face already contains 139 glyphs, including 44 extras (`graphics/res/font_small_mono.h:19`, `52`). Adding the proposed two-cell Font icon makes **141 glyphs / 46 extras**: Terminus becomes **2,256 B**, and Cozette becomes **1,974 B**, rather than 2,224 B and 1,946 B. The extras assertion also needs updating (`menu/menu_text.c:10`).

   The generator emits a `static const` definition (`scripts/gen_mono_font.py:318`). Including an equivalent generated header independently in both `menu_text.c` and `lcd_bus.c` does not guarantee one linked table.

   **Change the plan:** correct the counts and require one table definition, shared through an accessor or external declaration. The pseudo-font accessor must select Terminus explicitly, independently of the currently selected menu face.

9. **P3 — The song-title and artist budgets are reversed in the plan.**  
   `plans/MENU-8X16-PLAN.md:133–134` identifies line 0 as title and line 1 as artist. The producers put **artist on line 0 and title on line 1** (`hostagent/nowplaying-windows.py:194–197`; `hostagent/ak820text.py:294–297`).

   **Change the plan:** describe the Large budgets as artist 14, title 15; when artist is absent, title moves to line 0. Make the dashboard oracle use that ordering.

10. **P3 — “Erased” and “zeroed” do not imply the same face.**  
    B5 says a set bit means Small but also says an erased byte reads Large (`plans/MENU-8X16-PLAN.md:271–274`). A raw erased byte is `0xFF`, whose bit 2 is set. QMK’s initialized block is zero-filled (`config.h:268–270`).

    **Change the plan:** say “zero-initialized reads Large” and explicitly define invalid/reserved-bit handling. Include `0xFF` in the real settings tests; the current test already treats it as garbage (`scripts/diag_sim/kbee.c:128–133`).

**Verdict:** Not ready as written. Once these findings are addressed, the plan is ready to build, with B9 still required to establish actual timing.

## Dispositions

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | P1 | The face can change while the dashboard owns the panel (the live record over raw HID) | **Accepted.** Checked: `profiles.c`'s raw-HID apply needs no open menu, and `flash.sh` uses it after every flash. Every change of face now goes through one routine, `font_set()` (B5). It saves the bit, re-lays out the menu if it is open, and calls `display_text_refont()`, which sets `text_dirty`. `queue_line` already treats a changed font as a moved run: it clears the old cells and repaints every glyph (`display.c`, the `moved` branch). Glyphs already queued keep their own font ids and finish. Checked on the board in B9: the live restore with the menu closed and the same text playing |
| 2 | P1 | Reset, and the Font option, need a geometry transition; a page push only retargets | **Accepted.** Checked: `show()` calls `ms_retarget()` for a list-to-list move, and Reset only retargets. B5 now has one transition, `menu_refont()`, used by the Font option, Reset settings and the live restore when the menu is open. It calls `ms_set_layout()` with the new face's layout and `fresh`, for the banded clear and every slot invalidated. It re-derives each list frame's `top` from its cursor, and puts Help's and About's reading position back to their first line, since their lines wrap differently per face |
| 3 | P2 | B5's list of the byte's readers and writers is incomplete (`prof_differs`, the shared `body_ok`, `PF_SIDE`, the host's decode) | **Accepted.** The face never enters the shared capture, compare or validation. It is packed into the live record only by the raw-HID export, before the record's check byte is taken, and taken out by the raw-HID import before the shared validation; applied after. Saved and side records apply the readout through its setter, which keeps the face. `ak820profiles.py` shows the readout and the face apart. `profiles_test.c` covers the profile keys, the Win/Mac flip and the modified-profile `*` |
| 4 | P2 | The F3 fixture is left half-adapted | **Accepted: F3 stays on Cozette,** its table and geometry named explicitly, not the active face's. `menu_s1_gate.py`'s eight rows stay right |
| 5 | P2 | The baseline and B7 contradict each other | **Accepted.** The branch is from `ecb10f0e9b`, which never had the Font test page, so B7 is dropped. There `N_COUNT` is 61, and the two new nodes make 63, the cap. The board loses the Font test page when this build goes on |
| 6 | P2 | The tests' order, and the harness can't see the settings byte or the dashboard | **Accepted.** Each step's commit carries its own test changes. The settings byte is tested in `scripts/diag_sim/kbee.c`, which builds the real `kb_eeconfig.c`, and the profiles in `scripts/profiles_test.c`, both in B5's commit. No host harness builds `display.c` or `lcd_bus.c`, so the song text's budgets and cut go into a small pure helper with its own host test (as `batt_text.c` is), and the drawing is checked on the board in B9 by a named procedure |
| 7 | P2 | The pseudo font needs a contract: busy, done and failed | **Accepted.** Busy returns false before anything is touched (the existing guard), and the pump retries. A bad rectangle or a failed send consumes the glyph and is reported the way a lost blit already is, never retried forever. The glyph is 224 B, sent by the CPU in the pump's pass, which B9 measures |
| 8 | P2 | The table sizes leave out the Font icon, and the table must be one definition | **Accepted.** 141 glyphs (46 extras): Terminus Bold's table 2,256 B and Cozette's 1,974 B, with `menu_text.c`'s extras assert raised. Each table is defined once, in `menu_text.c`, and `lcd_bus.c` reaches Terminus Bold's through an accessor that names the face, not the active one |
| 9 | P3 | The song text's lines are the other way round | **Accepted.** Checked: `ak820text.py`'s `push_line()` and the Mac's producer put the artist on line 0 and the title on line 1, and `display.c`'s comment calling line 0 the title is stale (B6 fixes it). In Large, the artist gets 14 characters and the title 15 |
| 10 | P3 | Erased and zeroed bytes don't read the same | **Accepted.** A zeroed byte reads Large with the percent readout. A byte with any of bits 3-7 set (0xFF, an erased block) is garbage as a whole: percent and Large. `kbee.c` tests 0xFF |


## The second look, verbatim

Codex was given the revised plan and the dispositions above, and asked
whether each fix holds against the code and what the revisions broke.

Firmware references below use `font-test` commit `3b6e43ef73`, relative to `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`. The checkout changed during review; I changed no files.

1. **fixed** — `text_dirty` suffices: both lines reach `queue_line()`, changed font IDs force repainting, staged work preserves dirty, and overlay release dirties again; unchanged 20 px text correctly stays unchanged.
2. **fixed** — Click, raw-HID and Reset execute outside slot painting; `ms_set_layout(..., true)` abandons partial slots, preserves outstanding DMA bookkeeping and restarts the banded clear safely (`menu/menu_slots.c:121`). See the dispatch qualification in 13.
3. **fixed** — Export recomputes the packed CRC; import checks it before unpacking and recomputes before `body_ok()`; exact `PR_FIELDS == PF_LIVE` confines face application. `flash.sh:307` → `ak820profiles.py:439` → `apply_live():265` really uses op 5.
4. **fixed** — Explicitly keeping F3’s table, mask and geometry on Cozette addresses its complete rendering path.
5. **fixed** — The selected base excludes Font test: 61 nodes plus two reaches 63.
6. **fixed** — Tests move with their implementation commits; real settings tests, profile tests and board rendering checks are now correctly distinguished.
7. **not fixed** — The busy/success/failure contract is corrected, but the requested busy-DMA, failure and owner-transition verification is still absent from B8.
8. **fixed** — Counts include the Font icon, each table has one definition, and the dashboard accessor explicitly selects Terminus.
9. **fixed** — Artist/title ordering and the 14/15 budgets match the producers.
10. **not fixed** — Invalid-byte reads are defined, but preserving raw bit 2 and comparing only bits 0–1 contradict invalid-as-a-whole semantics when writing; see 12.

11. **P1 — A Small-face backup cannot restore its live settings onto older firmware.**  
    Evidence: `plans/MENU-8X16-PLAN.md:319` describes only a percent-readout downgrade consequence; `menu/profiles.c:127` rejects packed values 5–7, and `:772` rejects the entire op 5 record before applying anything. `hostagent/ak820profiles.py:264` sends the record unchanged; its geometry conversion only handles the profile block (`:149`, `:439`).  
    **Plan should say:** define downgrade compatibility explicitly—detect support and strip the face/recompute CRC for older targets, or refuse before flashing with a documented recovery path. Otherwise the screen, clock, indicators and other live settings fail to restore too.

12. **P2 — Invalid-byte setters need normalization before preservation and comparison.**  
    Evidence: plan `:311–316`; the existing setter repairs invalid storage by replacing the whole byte (`kb_eeconfig.c:207`). Under the revised prescription, `0xFE` reads Percent/Large, but setting Hours can return early because its low bits already equal 2. Preserving raw bit 2 while repairing `0xFF` can instead turn Large into Small.  
    **Plan should say:** normalize an invalid byte to the defined default pair before either setter compares or preserves fields; write a canonical valid result. Test setters starting from every invalid byte, including matching-low-bits cases.

13. **P2 — “Menu open” needs an explicit owner/session/kind gate.**  
    Evidence: plan `:323–329`; `menu/menu_ops.c:23–30` distinguishes configuration-menu and fixture sessions, while both share the slot scheduler (`:65–72`). `SESSION_OPEN` also survives entry into Diagnostics (`menu/panel_owner.c:113`).  
    **Plan should say:** install the current page’s new layout only for `MK_MENU` + `PANEL_MENU` + `SESSION_OPEN`; select List/Confirm/Range/Hue appropriately. Do not replace F3’s layout or change panel ownership. Debug return already rebuilds the menu; a dashboard restore uses its forced text stage, or retained dirty state after that stage. Add raw-HID tests across these states. No additional static state is needed.

14. **P2 — B8 does not verify the pseudo-font’s new failure path.**  
    Evidence: plan `:173–180` promises recovery, but `:406–424` tests successful rendering only. `graphics/lcd_bus.c:369` rejects a rectangle without latching loss; send failures do latch it. Consumption occurs at `graphics/display.c:3076–3081`, recovery at `:3136–3155`.  
    **Plan should say:** explicitly latch loss on rejected pseudo-font blits and verify busy leaves the glyph untouched, failure consumes it and schedules repair, and owner changes safely discard/rebuild queued work. Exercise unchanged single-line text, the 20 px case, overlay ownership, and restores before/after the forced text stage—not only two-line track changes.

15. **P3 — The claimed old-run clearing behavior is inaccurate.**  
    Evidence: plan `:187–189`, `:442`; `graphics/display.c:3271–3281` clears only vacated columns when old/new y and height match, regardless of font ID. Both song faces are 14 px high.  
    **Plan should say:** changed font IDs requeue every glyph; full-cell painting overwrites overlapping pixels, and clearing removes only uncovered old pixels. The current behavior is sufficient.

16. **P3 — The timing gate must include exactly 25 ms.**  
    Evidence: plan `:110`, `:408` says “over 25 ms”; `health.c:159` counts `gap >= 25`.  
    **Plan should say:** zero passes **≥25 ms**, matching the hard constraint and counter.

**Verdict: not ready to build.**

## Dispositions of the second look

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 7 | | The pseudo font's failure path isn't verified | **Accepted, with 14 below.** |
| 10 | | Invalid bytes vs the setters | **Accepted, with 12 below.** |
| 11 | P1 | A backup taken in Small can't restore onto older firmware: op 5 refuses the whole live record | **Accepted.** Checked: `profiles.c`'s range check is 1-3 and op 5 refuses the record outright. `ak820profiles.py`'s live restore now retries once with the bit cleared and the CRC taken again when the board answers `PROF_INVALID` to a record with bit 2 set. The older firmware gets every setting but the face. Tested both ways |
| 12 | P2 | The setters must normalize an invalid byte before keeping or comparing fields | **Accepted.** One normalizer, `bv_norm()`: a byte with any of bits 3-7 set becomes 0 before any read, compare or keep, and the setters write the canonical byte. `kbee.c` tests every setter from every invalid byte, matching low bits included |
| 13 | P2 | "Menu open" needs the session, owner and kind gate | **Accepted.** `menu_refont()` acts only for `MK_MENU`, `PANEL_MENU` and `SESSION_OPEN`, and installs the current page's layout (List, Confirm, Range or Hue). F3's layout and the panel's owner are never touched. Host tests cover a change under F3 and under the debug page |
| 14 | P2 | B8 doesn't verify the pseudo font's failure path | **Accepted in part.** The pseudo font latches the loss itself for a refused rectangle, since `lcd_stream_begin` doesn't. `_Static_assert`s keep every text slot position on the panel, so the branch is for a fault, and no host harness runs `lcd_bus.c`. The failure branch is checked in the build's code review, not on the board. B8 adds the cases named: the single line in both faces, the 20 px line, the overlay holding the band, and a restore before and after the forced text stage |
| 15 | P3 | The old run's clearing was described wrongly | **Accepted.** On the same row and height only the uncovered columns are cleared; full-cell glyphs make that enough. Reworded |
| 16 | P3 | The timing gate is >= 25 ms | **Accepted.** "Passes of 25 ms or more" throughout |


## The third look, verbatim

Codex was given the plan as revised for the second look, with one change
since: Small became today's menu unchanged.

“Fixed” below means fixed **in the plan**, checked against `ecb10f0e9b`. Firmware paths are relative to `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`.

**7. P2 — Not fixed: busy-path verification remains missing.** The contract now matches `graphics/lcd_bus.c:834` and `graphics/display.c:3076`, but B8 tests no deliberate busy-DMA deferral; require verification that the queued glyph remains untouched until the bus is free.

**10. P3 — Fixed.** Plan `:325–340` now distinguishes zeroed and invalid bytes and normalizes before preservation/comparison, addressing the existing whole-byte setter at `kb_eeconfig.c:207`.

**11. P1 — Fixed.** Plan `:391–397` specifies a single stripped-bit/recomputed-CRC retry, compatible with rejection before application at `menu/profiles.c:772` and the host’s `apply_live()` at `hostagent/ak820profiles.py:264`.

**12. P2 — Fixed.** Plan `:331–340` requires canonical writes after normalization, including the matching-low-bits `0xFE` case; this preserves the repair behavior of `kb_eeconfig.c:207`.

**13. P2 — Fixed.** Plan `:348–364` gates on kind, owner and session; `menu/menu_ops.c:65` dispatches fixture/menu separately, and `menu/menu.c:1806` rebuilds the stack on debug return.

**14. P2 — Not fixed: send-failure recovery is still untested.** Rectangle rejection is addressed, but static geometry assertions do not cover transfer failure (`graphics/lcd_bus.c:386`). Require a pseudo-font failure/recovery case using the existing injection mechanism (`scripts/menu_s1_fault.py:75`); code inspection alone does not verify consumption and subsequent repair.

**15. P3 — Fixed.** Plan `:200–205` correctly describes vacated-column clearing plus full-cell overwriting, matching `graphics/display.c:3271`.

**16. P3 — Fixed.** Plan `:448–449` now requires zero passes **≥25 ms**, matching `health.c:159`.

**17. P2 — “Small unchanged” conflicts with the prescribed test updates.**  
Evidence: [plan:434](/Users/jdlien/code/ak820-pro/plans/MENU-8X16-PLAN.md:434) still directs updates from [survey:342](/Users/jdlien/code/ak820-pro/plans/menu-8x16-survey-2026-10-28.md:342), which prescribes replacing expectations with Large’s wording and behavior. Existing Small checks include top-level values (`scripts/menu_s0_test.c:1929`), Clock labels (`:3663`) and right-half-only repaint counts (`:3723`).

**Plan should say:** retain those assertions for Small; add separate Large expectations. Explicitly guard Power’s bulb, Profiles’ replacement label, Clock formatting/repaint logic, summary formatting, and Help/battery-note changes. Restrict Small’s expected differences to the declared exceptions:

- Font insertion shifts page-two indices; its scrollbar changes even on page one. With 15 items, Small’s thumb is **60 px**, and page two’s thumb starts at **y67**, replacing the assertion at `scripts/menu_s0_test.c:1965`.
- Successful Reset switches to Large, so the existing Small post-reset frames at `:4835` and `:4851` must change intentionally.
- Update both tour drivers and regenerate the oracle frames: `plans/menu-mockup/verify.js:9` still hardcodes the old indices. The old 25/26 comparison cannot certify the revised Small menu.

**18. P2 — Font’s Back/hold behavior is unspecified after an immediate save.**  
Evidence: [plan:365](/Users/jdlien/code/ak820-pro/plans/MENU-8X16-PLAN.md:365) makes Font Battery-like but keeps its page open after saving. Existing choice handling flashes **“Cancelled”** on Back (`menu/menu.c:2014`) and hold (`:2407`), although the new face has already been persisted.

**Plan should say:** Font saves immediately; Back/hold retain it and leave without “Cancelled.” Special-case Font without changing existing Small choice behavior, and test selecting a face followed by both exits.

**Verdict: not ready to build.**

## Dispositions of the third look

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 7 | P2 | The busy path isn't verified | **Accepted as a review check.** The busy path is the existing `lcd_blit_busy()` guard, unchanged, before anything is touched; no host harness runs `lcd_bus.c`. Checked in the build's code review |
| 14 | P2 | Send-failure recovery is untested | **Accepted.** B8 adds a fault step with `menu_s1_fault.py`'s injection, if it reaches `lcd_blit_mono` on the dashboard; the code review checks the branch either way |
| 17 | P2 | "Small unchanged" conflicts with the test updates the survey prescribes | **Accepted.** B7 now keeps Small's assertions and adds Large's beside them. Small's frames change only where the build means them to: the Font row on page two and the scrollbar (thumb 60 px, page two from y 67), and Reset settings putting Large back. Tests check that no Large-only behaviour reaches Small. The tour drivers learn the Font row, and the oracle's frames are taken again in both faces |
| 18 | P2 | Back and hold after the Font page's immediate save | **Accepted, by design.** The Font page behaves as every choice does: a click saves, flashes "Saved" and goes back up, and the top level repaints in the new face. A Back or a hold before a click changes nothing and says "Cancelled". There's no state in which a saved face sits under a "Cancelled" |

Not run a fourth time on the plan: the build's code review comes next,
before the flash.

## Fourth look: the evening commits on the board (59b2c9d7b3, the spacing; ccfe080920, the icons in four greys), verbatim

No P1/P2/P3 correctness findings in either commit.

- **Lock/battery overlap is safe.** Both local 20px atlases have a blank row 0 across all 95 glyphs; every lock-label character ends at cell row 18. Lock clears reach row 105, but battery shapes start at 108 or below, and battery text paints black at 105. Queued draws and staged restores preserve this. [display.c:2201](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2201)
- **Text and clock remain contained.** Two-line cells occupy 27–40 and 42–55; single-line cells occupy 30–52 or 36–49. Playback/date cells end at 80, before locks begin at 83. Vacated-cell clears and overlay retirement preserve the required ordering; the updated debug-restore comment is accurate. [display.c:3455](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3455)
- **Menu scheduling remains consistent.** Title signatures restart changed or interrupted titles; icon-free messages repaint the former icon area. Profiles, confirms, editors and `l_first` handle the extra chunk correctly. Small and F3 retain their rendering paths. [menu.c:1499](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1499)
- **Icon bounds and colours check out.** Pieces are 512/510 bytes; source accesses stay within each 64-byte icon. `MB_PANEL` matches the backend, and exhaustive channel checks confirm nearest rounding. Added static tables are const; the rendering context is automatic. [menu.c:1600](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1600)

I ran read-only atlas and arithmetic checks. I relied on your reported host/oracle passes; hardware pass timing was not measured.

OK to keep on the board.
No findings, so nothing to disposition.

## Fifth look: 8b0f47e245 (Terminus regular, the Font preview, the face in profiles, System info, the camera page removed), verbatim

No P1/P2/P3 correctness findings in `8b0f47e245`.

The preview exits, profile applications, and refont gate preserve the saved face and layout consistency. I found no stale camera-state references or defects in Regular’s song-text handling, note rows, or Diagnostics indices.

Static review only; I relied on your reported passing tests. On-device timing was not remeasured.

**Verdict: OK to flash.**
No findings, so nothing to disposition. Flashed at 20:19 on JD's go, before this came back.

## Sixth look: fbc6c4a1fd (10px keeps bold titles and the song title), verbatim

No P1/P2/P3 findings.

All menu titles—including confirm/editor titles, flashes, and title hints—use Bold; other text keeps its existing face. Song redraws, refont, shadow/moved handling, and overlay release preserve the correct weight and clear stale pixels. Separate HID packets can briefly expose the previous line-1 state, but its update retains `text_dirty` and corrects line 0.

Verdict: `fbc6c4a1fd` is correct on static review; no hardware validation performed.
No findings. Flashed 20:39, before it came back.

## Seventh look: 8ec0c8b9b4 (Help's More info, P1d: the credits beside the bunny and the QR code), verbatim

No correctness findings in `8ec0c8b9b4`.

Static review found consistent chunk/piece counts, maximum payloads of **512 pixel bytes** and **36 bitmap bytes**, and distinct RK_MORE signatures with bit 0 clear. Repaint coverage, navigation, font/profile transitions, node 9 reuse, and the QR encoder showed no bugs.

Tests were not rerun.

OK to keep on the board.

No findings. Flashed 23:09, before it came back.
