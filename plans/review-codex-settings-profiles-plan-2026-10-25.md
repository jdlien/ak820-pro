# Codex review: settings profiles plan, draft 2 (2026-10-25)

Run by Warren on gremlin: read-only, inside the repo, against the firmware at
`gremlin/fx-speed` (`30f1e0cf` plus the effects' speeds, which touch nothing
here), with `plans/CONFIG-MENU-P1-DESIGN.md`'s "Settings profiles" for
context. The prompt asked the plan's six questions, a check of its facts
against the code (the EEPROM map, the `MAX_ADDR` override, the wear-leveling
cache, the sleep block, the pre-write hook, the node limit, `pg`, the idle
rule, the `pre_process` order, the free HC code), and four more: the crc over
a torn wear-leveling write, the active byte after a Delete, the `*` in a
signature against `row_sig`'s ranges, and `flash.sh`'s lighting restore as a
second writer beside the live record. Copied verbatim from Warren's relay.
Dispositions: [`SETTINGS-PROFILES-PLAN.md`](SETTINGS-PROFILES-PLAN.md),
draft 3, "Review history".

---

Draft 2 needs revision before building. JD's scope and UX decisions are fine.

1. **Q1, EEPROM placement is sound.** The map is correct: core 0–36 (37 B), kb 37–46 (10), VIA 47–50 (4), keys 51–770 (720), encoders 771–786 (16), macros 787–1023 (237). See quantum/nvm/eeprom/nvm_eeprom_eeconfig_internal.h:13, keyboards/a_jazz/ak820pro/config.h:271, quantum/nvm/eeprom/nvm_dynamic_keymap.c:20. The override is honoured: maximum 913, profiles 914–1023, macros 127 B; nothing else moves. VIA queries capacity (quantum/via.c:421); its definition needs no size edit. Keymap writes are bounded (nvm_dynamic_keymap.c:140). VIA reset (via.c:410), if enabled, resets VIA/keymaps/macros; eeconfig_init (quantum/eeconfig.c:70) erases everything. Document that distinction.

2. **Q2, synchronous writes remain conditional.** Sessions block sleep (menu/panel_owner.c:57), and the hook drains DMA (ak820pro.c:705). However, display wake release can precede recovery completion (sleep.c:827): explicitly gate menu/HID writes on `!sleep_recovering()`. Measure complete passes including compaction against C10's 15 ms ceiling (plans/CONFIG-MENU-BUILD-PLAN.md:1088). Deferral alone does not bound compaction. The RAM cache (quantum/wear_leveling/wear_leveling.c:162) and memcpy reads (wear_leveling.c:733) are real. "Only changed bytes" is false: update_block (drivers/eeprom/eeprom_driver.c:52) writes the whole differing block; its VLA adds another record-sized stack copy.

3. **Q3, matrix idle is insufficient.** The proposed hook position (ak820pro.c:342) is correct; QMK resolves/caches the active source layer beforehand (quantum/quantum.c:258), already inside action_exec (quantum/action.c:78). That is not necessarily the base layer. One-shots, toggled layers and queued tap-hold actions (quantum/action_tapping.c:130) survive physical idle. Specify WAIT/CAPTURE/DRAIN, settle pre-existing QMK state, and finish draining after the complete scan, preventing simultaneous releases escaping. Budget that state. `pg` is 12 B (menu.c:234); joining `menu_long_wait` (menu.c:1667) correctly selects 180 seconds of knob inactivity (menu_ops.c:154). But Rename/confirm exceeds `stack[3]` (menu.c:1243); replace a frame or budget another. Slider following (menu.c:1614) currently exits BT screens, not Rename.

4. **Q4, fix RGB ordering.** Temporarily enable, apply mode/HSV/speed, then set enable last, as existing restoration does (menu/menu_edit.c:78); disabled mode/HSV setters return early. Cancel previews before host dump/apply. Disconnect alone cannot split an already received handler, but power loss can split the independent deferred stores (kb flush, kb_eeconfig.c:58). Specify durability/readback. Choose one authoritative RGB restore: flash.sh already restores lighting (flash.sh:254), potentially overwriting the live record with another snapshot. Omitting flags and preserving power caps (power.c:137) are fine.

5. **Q5, provide macro migration.** Keymap backup (hostagent/ak820keymap.py:154) omits macro contents. Export them, reject oversized restores, and rebuild their trailing validity byte (quantum/dynamic_keymap.h:51). Unformatted→empty is fine; handle firmware lacking HC_PROFILES. Version/map effect identities: membership cannot detect numeric renumbering (quantum/rgb_matrix/rgb_matrix.h:117).

6. **Q6, no staging is viable; no transaction state is not.** Mask incoming magic; require all pages from one transaction and a whole-image check; exclude intervening menu/host mutations; publish magic separately last. Otherwise individually valid old/new records can pass. CRC8 can accept torn mixtures: invalidate records before rewriting, commit last. Interrupted compaction (wear_leveling.c:303) can lose the entire EEPROM, contradicting "at most one slot"; the entire request reaches cache before logging (wear_leveling.c:692). Normalize active to None for invalid/deleted slots; define empty-record CRC handling because Delete changes CRC-covered state. 0x10 is free (hid_protocol.c:490), but separate sub/page bytes leave 27 payload bytes: five pages unless packed. Define live-record version framing.

**Signature correction:** node 64 aliases node 0 (menu.c:834), not RK_TEXT; the current assertion permits 13 additions. Encode modified in spare bit 2 and active identity in `val`; explicitly invalidate names/summaries. Battery's hash is not collision-free. Cheap comparisons are plausible; benchmark repeated scans.

---

**Warren's notes on it:**
- The signature correction is Warren's to own: `(1<<14) | node<<8` at node 64
  sets bit 14 again, so it aliases node 0. The limit of 64 stands; the reason
  given in draft 2 was wrong. Codex counts 13 additions under the current
  assertion, not 14.
- `stack[3]` was missed in Warren's check: Top, Profiles, a slot's page, then
  Rename or a confirm is four deep. Either Rename and the confirms replace
  the slot page's frame, or the stack grows to 4 frames (3 B a frame, 4
  aligned).
- Q3's state machine needs RAM Warren had said it didn't: WAIT, CAPTURE and
  DRAIN won't fit inside a 12 B name arm, and a byte in `pg` won't do. The
  palette's 14 B (JD's okay) is the place.
- Compaction losing the whole EEPROM on a power cut is the wear-leveling
  layer's behaviour today for every settings write; the plan should say so
  rather than "at most one slot".
