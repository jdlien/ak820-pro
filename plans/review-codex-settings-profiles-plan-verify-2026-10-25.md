# Codex verify: settings profiles plan, draft 3 (2026-10-25)

Prompt: plans/review-prompt-settings-profiles-plan-verify.txt (committed on
`warren/config-menu` at `b795546`). The plan as committed on main in
`a2e5e24`, checked against the draft 2 review. Firmware: the working tree at
`gremlin/fx-speed`. Run on gremlin for the session on Buzz. Copied verbatim
from Warren's relay. Dispositions: [`SETTINGS-PROFILES-PLAN.md`](SETTINGS-PROFILES-PLAN.md),
draft 4, "Review history".

---

Verified both documents match **a2e5e24**. Draft 3 resolves Q1, Q5 and the signature finding; Q2 is correctly conditional on measurement. **Q3, Q4 and Q6 remain partly unresolved.**

Before P5a, change these:

- **Q6: protect Rename too.** The write table (plans/SETTINGS-PROFILES-PLAN.md:185) invalidates Save, but Rename rewrites name/CRC while state remains valid. CRC8 can accept a torn mixture. Rename also needs invalidate → body/CRC → commit. Excluding state from CRC, Delete's handling, and Save's separate final state write are correct.

- **Define initial formatting.** An unformatted block reads empty, but Save never publishes its magic. Specify initialization of all slot states and active byte before publishing `0xA1`; otherwise first-save either remains invisible or risks exposing stale records. See layout and writes (plans/SETTINGS-PROFILES-PLAN.md:123).

- **Finish HC_PROFILES' wire layout and budget.** `[SET_VALUE, channel, command, sub, page]` leaves 27 bytes; adding a separate token leaves **26**, still five pages. Pack fields explicitly or change page size. The 27-byte live record fits without that extra token. The timeout also needs timestamp/countdown storage beyond the stated two transaction bytes. Existing framing: hid_protocol.c:403.

- **Q4: cancel previews before backup, not merely apply.** Sub 4 still permits saving an uncommitted preview. Existing VIA lighting reads cancel it expressly (hid_protocol.c:1392). Sub 6 must also cancel/refuse previews: RGB's forced flush bypasses the normal gate (quantum/rgb_matrix/rgb_matrix.c:102). Readback verifies RAM; durability depends on successful writes, whose status the current EEPROM wrapper discards (drivers/eeprom/eeprom_wear_leveling.c:38).

- **Q3: specify the tapping accessor and one-shot clearing.** Tapping state and queue indices are private (quantum/action_tapping.c:130); add an idle accessor. `clear_oneshot_layer_state` requires a mask (quantum/action_util.c:211). Reconcile the test saying a one-shot holds WAIT with the rule that clears it upon entering CAPTURE.

- **The plain-click guarantee is false with a toggled Fn layer.** Default-layer character lookup doesn't change `layer_state`; menu/menu_glue.c:288 still passes Fn to the knob handler. Suppress that interpretation during Rename.

Fine as written: default-layer lookup, matrix-derived Shift, housekeeping DRAIN after all scan events, CAPTURE typing restarting idle, four stack frames, stable effect IDs, token/page-mask/masked-magic transaction design, restore-time menu-write exclusion, five-second expiry, sub 5's cancellation, and one authoritative RGB restore. Macro validity ordering matches quantum/dynamic_keymap.h:51.

The cited menu/sleep facts check out, with small corrections: `menu.c:1243` is the depth guard; the array is at 212 (menu.c:212). Frames are three bytes; four is a conservative allocation allowance. Connection-follow also handles `N_CONNINFO`, never Rename. The RGB restore order is right, but **speed does not return early when disabled** (quantum/rgb_matrix/rgb_matrix.c:758). The sleep-recovery gate and complete-pass/compaction measurement remain necessary.

---

**Warren's note:** the toggled-Fn point matters on this board: any keymap
that toggles or latches a layer (TG, TO), other owners' included, leaves the
knob's Fn test, which reads `layer_state`, on. So during Rename,
`menu_pre_process` should treat Fn as up whatever `layer_state` says: one
rule in `menu_physical`'s call, keyed on the Rename node. (JD's own layout
has only `MO(1)` and `MO(3)`, checked on Buzz.)
