# Codex review 6: verifying the configuration menu's build plan, revision 6 (2026-10-23)

The plan verified is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 6, against the fifth review
([`review-codex-config-menu-build-plan-verify4-2026-10-23.md`](review-codex-config-menu-build-plan-verify4-2026-10-23.md))
and its dispositions. The model was gpt-6-astra at xhigh, read-only, run from
gremlin with the firmware at `b9555ff3e6` and the prompt in
[`review-prompt-config-menu-build-plan-verify5.txt`](review-prompt-config-menu-build-plan-verify5.txt).
Codex's answer follows verbatim, then the dispositions. It found no must-fix: S0 is ready to build. Its three
clarifications are folded into revision 6.

---

**Revision 6 is ready to implement S0. All three previous must-fixes are fixed, and I found no new must-fix.** The remaining issues are should-fix clarifications that an implementer can resolve from the contract without changing its architecture.

This is static verification against the supplied source. I read only inside the repository, changed nothing, and ran no builds or hardware tests. “Fixed” means the plan prescribes a workable implementation—not that the implementation or proof already exists.

References below:

- **P:** [CONFIG-MENU-BUILD-PLAN.md](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md)
- **D:** [graphics/display.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c)
- **L:** [graphics/lcd_bus.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c)
- Other firmware paths are relative to `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`.

For resolved findings, the severity shown is the original severity.

**The three must-fixes**

| Finding | Verdict / severity | Verification, failure scenario, and treatment |
|---|---|---|
| Camera loss recovery | **Fixed — original must-fix** | **P:251–258,330,964–968; D:831–855,1000–1014,1162–1192.** The plan now invalidates only the active page and makes Camera dispatch exclusive. After Camera finishes, returning false from `cam_pump_glyph()` cannot enter Health’s renderer. The outer DEBUG branch also returns unconditionally at D:2978, so this does not expose dashboard painting. The frozen-values test that continues pumping catches the original delayed overwrite. **Retain both changes and that test.** |
| Dashboard loss during the self-heal cooldown | **Fixed — original must-fix** | **P:202–222,230–248,964–965; D:2958–2967; L:1016–1023.** Consuming the latch now records damage immediately by moving DONE to damaged RESIDUAL. `display_restored()` becomes false, the existing residual scheduler retains the repair obligation, and damage prevents another DONE before a new generation repairs it. This closes the case where a second loss follows a completed heal within five seconds. **Retain the two-loss test and rate-limit repair starts, as specified.** |
| Deferred/discarded op-27 work without terminal outcomes | **Fixed — original must-fix** | **P:851–875,964–968.** Sub 7 finishes on installation, including WAITING; it no longer waits for a generation that was never started. Discarding injected loss or synthetic input retires its sequence. Sub 6 has an application-completion rule, and busy/bad-argument replies preserve outstanding state. Thus an ownership handoff cannot permanently occupy single-flight. **Implement the common retirement rule on every disposal path, including input supersession and close.** |

The dispositions at the end of round 5 accurately describe these repairs.

**Carried findings that remained open in round 5**

| Carried finding | Verdict / severity | Verification and treatment |
|---|---|---|
| **1 — ownership migration and recovery** | **Fixed for S0 — original must-fix** | **P:189–258,268–349.** The remaining Camera and cooldown exceptions are resolved above. The migration checklist includes the exclusive debug dispatch. Ownership changes still quiesce and replace the old image. **Retain the checklist and owner-specific recovery tests.** |
| **2 — restore completion** | **Fixed — original must-fix** | **P:202–234,248.** RESIDUAL has its own queue/battery/logo executor, and now also retains damage arriving after DONE. This matches the existing queue retirement at DMA arm, D:3000–3023, and incremental battery work, D:1873–1878,1965–2011. **Keep the final idle/loss/damage checks; queue emptiness alone remains insufficient.** |
| **9 — PENDING/startup contradiction** | **Fixed — remaining should-fix** | **P:183,189–198,290.** Both the WAITING definition and startup row now defer only under a non-DASH owner. A startup request during DASH/PENDING runs; cancellation cannot strand DASH in WAITING. **No further correction needed.** |
| **10 — reproducible S0 workload** | **Partly fixed — should-fix** | **P:977–995.** Initial state, 20 ms polling, terminal-outcome pacing and transition recording are supplied. The script remains a planned artifact, and its click allocation is inconsistent; see below. The physical encoder backlog remains correctly deferred to S1, consistent with `quantum/encoder.c:30–45`. |
| **15 — executable op-27 proof** | **Fixed in substance — original must-fix; should-fix details remain** | **P:833–917,936–974.** Terminal outcomes, partial-stop observation, production-state-machine tests and sticky checks now provide a workable proof interface. The unused-argument and completion-predicate clarifications below do not require another protocol design. |

Carried **6 and 7 remain fixed as P3 deferrals**, not implemented Bluetooth fixes. **P:772–795** still requires a separate reviewed plan. The existing overwrite of pending selection/bounce work remains visible at `bluetooth/ch582f_ajazz.c:1534,1596,1755`; queue admission at `1501–1513` still does not prove release delivery. Their **must-fix severity belongs to P3**: that plan must supply cancellation destinations, delivery evidence, bounded failure exits and retirement of old retries.

I found no regression in the other previously closed carried findings.

**The remaining round-5 should-fixes and nit**

| Finding | Verdict / severity | Verification, failure addressed, and treatment |
|---|---|---|
| Successful clear result | **Fixed — original must-fix** | **P:474–481; L:207–211.** The wording now correctly identifies the discarded result as the clear’s **own** transfer result. A failed band cannot advance. **Return that boolean through `lcd_clear_rect_ok()` and retain failed-band tests.** |
| HC_DEVHOOK framing | **Fixed — should-fix** | **P:835–850; `hid_protocol.c:1026–1028,1291`; `scripts/devhook.py:43–51`.** Handled replies retain byte 0=`0x07`; status and sequence occupy payload bytes. Existing framing checks therefore accept them. **Use the specified dedicated codec for arguments and payload interpretation.** |
| Preserve `display_band_busy()` tests | **Fixed — should-fix** | **P:321; D:2600–2609.** Only the ownership branch is replaced; pair hints, alerts and parameter overlays remain busy. This prevents a power notice displacing them. **Retain those branches.** |
| Direct Diagnostics Camera selection | **Fixed before P1 — should-fix** | **P:278–281.** Camera is a direct destination; Health remains the destination for `DBG_PAGE`/op 1. **No additional S0 change needed.** |
| Protocol completeness | **Partly fixed — should-fix** | **P:857–917.** Sub-6 completion and partial-stop observation are now specified, alongside numeric fields and placeholders. Treatment of unused pattern arguments remains unstated. **Choose the validation rule below.** |
| `pixels_done` owner scope | **Fixed — should-fix** | **P:877–881.** The bit now describes MENU fixture completion only and is false for DEBUG, DASH and ANIM. It no longer pretends that C3 slots describe Debug’s separate shadows or dashboard residual work. **Make current-target matching explicit as recommended below.** |
| Pattern 2’s observable stop | **Fixed — should-fix** | **P:864,886,915–916.** Its sequence finishes at the stop, after operation `n`’s transfer has completed or failed. Count and stopped state are independently readable. The host can now wait for the actual interruption point before requesting A. **Retain a stable stop until the next sub 0.** |
| Operation counting | **Fixed — should-fix** | **P:706–716.** Counts are logical paint operations, excluding clear bands and wait passes; settled A is required before partial B. Whole-slot repaint under C3 makes the nine-glyph title count consistent even though much of its text is unchanged. **Freeze operation order and colours with the fixture tables.** |
| Workload sequence and pacing | **Partly fixed — should-fix** | **P:977–995.** The required artifact and pacing are concrete, but the named visits require more clicks than allocated. **Correct the mix below and commit the actual array in S0.** |
| Arm/disarm and rejection bookkeeping | **Fixed — should-fix** | **P:443–447,867–875.** Disarming applies the session transition while preserving owed physical releases; rejected mutations do not overwrite the outstanding sequence; boot state is defined. **Exercise these in the single-flight tests.** |
| Close-first wording | **Fixed — nit** | **P:408–413.** Close is checked before turns, which are discarded. The previous reading that could navigate before closing is removed. **No further correction needed.** |
| RAM estimate / fault-build floor | **Fixed — nit** | **P:573–608,957–960.** The floor applies to every flavour and explicitly to devfault. This matters because `WDT_TEST_HOOKS` adds state, including `bluetooth/ch582f_ajazz.c:247–282`. **Use linked allocation as the gate and the documented log reduction if necessary.** |

**Non-blocking corrections I recommend**

1. **Should-fix — the 50-step workload allocates eight clicks to ten clicks’ worth of visits.**  
   **Location: P:982–985.**

   Two A/B toggles require two clicks; two F2 round trips require four; two Diagnostics round trips require four. That totals **ten**, not eight. A literal eight-click script cannot perform all the named visits.

   **Suggested fix:** use **28 turns + 10 clicks + 4 holds + 4 Fn-clicks + 2 restores + 2 losses = 50**, or reduce the named visits. Commit the explicit array with expected states, and define setup, repeat-boundary state and the final return to DASH. This is a workload-definition correction, not a defect in the owner/input contract.

2. **Should-fix — spell out “committed for the current target” in `pixels_done`.**  
   **Locations: P:484–497,513–523,877–881.**

   C3 stores the shown signature. If an implementation leaves an old slot marked COMMITTED until the painter visits it, merely checking state bytes can report completion after a target change or between changed slots.

   **Suggested fix:** require each active slot to be COMMITTED **and match its current desired target**, or invalidate changed slots before publishing the target. Apply the same interpretation to byte 21 and pattern 2’s settled-A precondition.

   I classify this as a clarification because the contract already requires that the fixture’s **pixels are settled** and treats target/style changes as damage. It does not need a new state-machine decision.

3. **Should-fix — freeze unused pattern-argument handling.**  
   **Location: P:884–886.**

   Pattern 2 defines `n`; patterns 0, 1 and 3 do not say whether a nonzero `n` is ignored or rejected. Different clients can consequently disagree on valid requests.

   **Suggested fix:** require `n=0` for patterns 0, 1 and 3, returning status 2 otherwise. Add codec tests. This does not affect valid zero-filled requests.

The RAM table also has a small stale description at **P:599**: “the restore it waits on” no longer describes sub 7. Updating that wording and accounting explicitly for the fixture counter/stop state is a **nit**; the linked floor already controls correctness.

**S0’s implementation and proof**

The changed mechanisms are compatible:

- Exclusive Camera dispatch preserves clear-first behavior and cannot fall through into another painter.
- DONE → damaged RESIDUAL retains the repair obligation without falsely completing during cooldown.
- Op-27 installation completion permits subsequent commands while restoration continues; discarded work frees single-flight.
- Pattern 2’s terminal stop removes the previous observation race. Bytes **29–30 fit**, with byte 31 still reserved.
- The counting rule supports the A → partial B → A proof without counting clear or polling passes.
- `devfault` combines the actual dev configuration with the fault mechanism at **L:651–659,786–789**. **N=1** reaches retry success; **N=2** reaches give-up and owner recovery through **L:1006–1017**. It proves lost-completion recovery, not every possible hardware fault.
- Production state machines, fake framebuffer checks, sticky transition checks and the separate physical tests provide a workable proof strategy.

**S0 is now buildable and provable from this contract. Implementation can begin without another must-fix planning round.** The script, linked RAM measurements and hardware evidence remain S0 deliverables.
---

## Dispositions (Warren, gremlin, 10-23)

No must-fix: S0 starts from revision 6. Codex's corrections are taken
into revision 6 itself:

| Finding | Disposition |
|---|---|
| The workload's clicks (should-fix) | **Agreed.** The named visits need ten clicks: the mix is now 28 turns, 10 clicks, 4 holds, 4 `Fn` plus a click, 2 restores and 2 losses. Each 50 ends with the fixture on F1 at row 0, and the last returns to the dashboard. The array itself is an S0 deliverable. |
| `pixels_done` against the current target (should-fix) | **Agreed.** A slot counts as settled only when `COMMITTED` with its current target's signature. Byte 21 and pattern 2's "A settled first" use the same test. |
| Unused pattern arguments (should-fix) | **Agreed.** Patterns 0, 1 and 3 need `n` = 0, else status 2. The codec tests cover it. |
| The RAM table's wording (nit) | **Agreed.** Op 27's row now names the synthetic hold's release time; the fixture's count and stop are in its own row. |
| Carried 6 and 7 | Agreed: P3's plan owns them. |
