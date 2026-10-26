# Settings profiles: plan

Draft 4, 2026-10-25. Written on Buzz from JD's decisions so far.
- Draft 2 took in Warren's check of the menu's internals against `30f1e0cf`
  (eight corrections).
- Draft 3 took in codex's review of draft 2
  ([`review-codex-settings-profiles-plan-2026-10-25.md`](review-codex-settings-profiles-plan-2026-10-25.md)):
  "needs revision before building; JD's scope and UX decisions are fine".
- Draft 4 takes in codex's verify of draft 3
  ([`review-codex-settings-profiles-plan-verify-2026-10-25.md`](review-codex-settings-profiles-plan-verify-2026-10-25.md)):
  Q1, Q5 and the signature resolved, and Q3, Q4 and Q6 partly not.

Every finding is taken; "Review history", at the end, lists where each
went.

Nothing is built. JD's decisions are also recorded in
[`CONFIG-MENU-P1-DESIGN.md`](CONFIG-MENU-P1-DESIGN.md), "Settings profiles".

## What it is

Four slots, each holding a snapshot of the configuration-menu settings, that
the user can load from the menu to switch between setups (home and work, day
and night). A slot can be saved over, renamed and deleted. Keymaps are not
part of it.

**In a profile (v1):**
- the lighting: on/off, effect, hue, saturation, brightness, speed (the
  speed is also the two-tone effects' second colour);
- the screen's backlight level (0-100);
- the lock lights' and the charging light's levels (0-100 each);
- the clock format (the six of Fn+C);
- the battery readout (percent or hours).

**Not in v1:** the power mode (decided: it's easy to toggle on its own), the
keymap, the BT slot (Decided 11), the RGB flags (the menu doesn't expose
them), the RTC period and the battery level (the board's own state, never
the user's).

## Decided

1. **A top-level row**, `Profiles`, with its own icon.
2. **The power mode stays out of v1.**
3. **Fixed slots, no "Save new" row.** An empty slot is the save target: a
   click on it saves the current settings there at once, named `Profile n`,
   with no name prompt.
4. **Names only through an explicit Rename item.** The keyboard is never
   taken over for typing unless the user picks Rename.
5. **A saved slot's page** has a very short summary, then Load, Save current
   here, Rename and Delete. Overwriting and deleting ask first.
6. **The summary uses the menu's icons**, along the lines of
   `[bulb] H:310 S:0% B:100%`. Its exact content is to be worked out on the
   panel.
7. **The icon: a folder,** U+E5FE (`nf-custom-folder_open`). JD: "A place
   where you save stuff." Its wide, tabbed shape is unlike the top level's
   other twelve. The rejected ones: a floppy (anachronistic, and hard to
   draw at 7 px), the bookmark (too like the upright battery), the palette
   (it reads as Lighting) and the heart.
8. **The dev-only live colour palette goes** (`menu.c`'s `pal`, op 27 sub
   13, `scripts/menu_tune.py`): const in dev as in daily. Its 14 B pay for
   this feature's state. JD: "I probably don't need live colour tuning
   anymore."
9. **Page 1's last row.** Bootloader moves to the top of page 2, with
   Diagnostics, Help, About and Exit: the settings stay together on page 1,
   and the bootloader goes with the system items.
10. **The summary goes below the actions** ("The slot page"), as the menu
    places notes today. Its content is still to be worked out on the panel.
11. **Profiles have nothing to do with Bluetooth.** A load never changes
    the connection. If a load also selected a slot, a load meant only for
    the look could drop the computer you're typing on. A slot that won't
    connect would also leave a load half done (P3's failure cases).
12. **Two keys, Next profile and Previous profile, not one per slot.**
    They're custom keycodes, assignable in VIA and unbound by default ("Next
    and previous profile keys", below). JD's Fn+1-4 are F1-F4 (the 65%
    habit), and a key per slot would use four. He may later move the pair
    onto his hue or speed hotkeys, since the menu now changes those.

## Later, not v1

- **A look for each connection:** the reverse of putting the slot in the
  profile. Each link (USB, 2.4G, BT 1-3) could name a profile to load when
  the board switches to it. Then a different look on each computer becomes
  a cue for which one you're typing on, and a load still never reconnects.
  It costs 5 B of EEPROM, one row per link in Connection, and a rule for a
  link whose profile was deleted. It needs JD's word before it's designed.

## Storage

### Where: the top of the emulated EEPROM, out of VIA's macro space

The logical EEPROM is 1024 B (`WEAR_LEVELING_BACKING_SIZE` 2048, logical
half of it). At `30f1e0cf` it holds (codex confirmed the map):

| What | Bytes | Addresses |
|---|---|---|
| QMK's core block (`eeprom_core_t`, packed) | 37 | 0-36 |
| The kb block (`kb_eeconfig`, version 7) | 10 | 37-46 |
| VIA's magic and layout options | 4 | 47-50 |
| The dynamic keymap, 4 x 6 x 15 x 2 | 720 | 51-770 |
| The encoder map, 4 x 1 x 2 x 2 | 16 | 771-786 |
| VIA's macro buffer: the rest | 237 | 787-1023 |

**The profile block takes 914-1023, the top 110 B,** with
`DYNAMIC_KEYMAP_EEPROM_MAX_ADDR` set to 913 (`TOTAL_EEPROM_BYTE_COUNT - 1 -
PROFILE_BLOCK_SIZE`). QMK honours the override
(`quantum/nvm/eeprom/nvm_dynamic_keymap.c:20`).
- **Nothing else moves:** the core, the kb block, VIA's header, the keymap
  and the encoder map keep their addresses, and keymap writes are bounded
  (`nvm_dynamic_keymap.c:140`).
- **The macro buffer shrinks from 237 B to 127 B.** VIA asks the firmware
  for its size (`quantum/via.c:421`), so `via.json` needs no edit.
- **JD's keymap uses no macro keys** (checked against his backup: none of
  the 360 keycodes or the knob's mappings). Other owners' macros migrate as
  "Macros", below, describes.

**What erases the block:**
- **VIA's reset** (`via.c:410`, where enabled) resets VIA's settings, the
  keymaps and the macros. Its macro reset stops at the buffer's end, so the
  profiles survive it.
- **`eeconfig_init`** (`quantum/eeconfig.c:70`) erases the whole EEPROM, and
  the profiles with it. So does a firmware flash.

**Why not a bigger EEPROM:** QMK's wear-leveling layer keeps the whole
logical store in RAM (`wear_leveling.cache`,
`quantum/wear_leveling/wear_leveling.c:162`). Every byte of logical EEPROM
costs a byte of RAM, and the dev build's heap gap is at its 128 B floor.

**Why not the kb block:** `kb_eeconfig` keeps its 10 B in a RAM struct and
writes the struct whole, so 110 B more there is 110 B more RAM. Its version
also resets every field when it changes.

**Reads cost nothing:** `eeprom_read_block` is a `memcpy` from the RAM cache
(`wear_leveling.c:733`). So the summary, the list and the `*` read the slots
directly, with no RAM copy of their own.

### The block's layout

```
offset 0      u8  magic           0xA1 for v1, written by the firmware only;
                                   anything else: unformatted (a fresh flash,
                                   or a restore in progress), read as four
                                   empty slots
offset 1      u8  active slot     0-3, or 0xFF for none
offset 2      4 x record (27 B each)
```

One record:

```
 0  u8  state     0x00 empty; 0x01 saved, format v1; anything else reads as
                  empty. Written LAST when a record is saved.
 1  u8  fields    bit per field present (below); v1 saves 0x7F
 2  u8  rgb_enable
 3  u8  effect    the effect's STABLE id (below), not QMK's mode number
 4  u8  hue       0-255 (shown in degrees)
 5  u8  sat
 6  u8  val
 7  u8  speed
 8  u8  lcd       0-100
 9  u8  locks     0-100
10  u8  charging  0-100
11  u8  clock     enum display_clock_mode, 0-5
12  u8  bview     KB_BATT_VIEW_PERCENT or _HOURS
13  u8  power     only with its fields bit (the live record, below); never
                  in a v1 profile
14  char name[12] ASCII 0x20-0x7E, NUL-padded; an empty name shows as
                  "Profile n"
26  u8  crc8      over bytes 1-25: the body, NOT the state byte
```

**The crc leaves out the state byte,** so a Delete (state to 0x00) or a
save's commit (state to 0x01) never invalidates it. A record is valid when
its state is 0x01 and its crc matches. State 0x00 is empty whatever the
crc. State 0x01 with a bad crc is damaged and reads as empty.

**Field bits:** 0 the lighting (bytes 2-7 together), 1 lcd, 2 locks, 3
charging, 4 clock, 5 bview, 6 the name, 7 power. A record without a field's
bit leaves that setting alone at a load. The mask lets a later version add
a field without a new format, and lets the live record carry the power mode
while profiles don't.

**The active byte is normalized:** an active byte pointing at a slot that
isn't valid reads as None, everywhere it's read.

### The effect's stable id

QMK's mode numbers aren't stable: enabling or disabling an effect at build
time renumbers the ones after it (`quantum/rgb_matrix/rgb_matrix.h:117`). A
check that the number is in today's table can't tell a renumbered effect
from the right one. So:
- the board's effect table (`rgb_effects[]`, the menu's shared table)
  gives each effect a stable id, **append-only**, like the
  `ak820pro_keycodes` enum, and a check script guards it as
  `check_via_sync.py` guards that enum;
- a record stores the id. A load maps it to today's mode number;
- an id the build doesn't have skips the effect alone: the rest of the
  lighting loads, and the flash says so.

## Writes

| Action | What it writes, in order |
|---|---|
| The first write to an unformatted block | the formatting (below), then the action |
| Save (an empty slot, or Save current here) | state 0x00; the body and crc (bytes 1-26); state 0x01; the active byte, deferred |
| Rename | state 0x00; the name and the crc (bytes 14-26); state 0x01 |
| Delete | state 0x00; the active byte to 0xFF if it was active, deferred |
| Load (the menu, or a Next/Previous key) | the setters (below); the active byte, deferred |

**Formatting:** a fresh flash leaves the block unformatted, and it reads as
four empty slots. The first profile write formats it first, in order:
1. the four state bytes to 0x00;
2. the active byte to 0xFF;
3. the magic, 0xA1, last.

Only then does the action run. So the first save is visible, and a stale
byte from before the flash can't show as a record. It happens once a flash,
at the first save. A board whose owner never uses profiles never writes the
block.

- **Every write is small, on exactly those bytes, through
  `wear_leveling_write()` itself,** not the EEPROM wrapper. The wrapper
  discards the write's status (`drivers/eeprom/eeprom_wear_leveling.c:38`),
  and the profile code needs it: a failed write flashes `Save failed` in the
  menu and returns an error over `HC_PROFILES`. `wear_leveling_write()`
  compares against its cache and skips an unchanged range
  (`wear_leveling.c:688`). It writes the whole range when any byte in it
  differs, so the calls stay per-field. (`eeprom_update_block` would also
  put a range-sized VLA copy on the stack, `drivers/eeprom/eeprom_driver.c:52`.)
- **The state byte goes last, in its own call, for a save and a rename
  alike,** after the slot is invalidated first. The wear-leveling log holds
  the body before the commit. A write cut off between them leaves the slot
  empty, never a mix of old and new that a crc8 could pass.
- **The pre-write hook** (`backing_store_pre_write_hook()`, `ak820pro.c:705`)
  drains an in-flight LCD blit first, the historical hang. Each write blinks
  the LEDs dark for a few ms, like every internal-flash write.

### When

**At the click, synchronously,** for every record write the menu makes
(save, rename, delete), on two conditions. The active byte is the
exception: it's always deferred ("Next and previous profile keys").
1. **Never inside a deep sleep's recovery,** checked explicitly:
   `!sleep_recovering()`. A menu session blocks deep sleep
   (`menu/panel_owner.c:57`). But the display's wake can be released before
   the recovery completes (`sleep.c:827`), so a menu could be open while it
   runs. A click then is refused with `Busy, try again`: it can only happen
   in the first passes after a wake. The host's writes have the same gate.
2. **The board's measure, first in P5a:** a complete main-loop pass that
   includes one save, with and without a compaction, against C10's 15 ms
   ceiling (`plans/CONFIG-MENU-BUILD-PLAN.md:1088`).

**If the measure fails,** deferring the write to the 10 Hz housekeeping
doesn't help a compaction: it blocks whichever pass runs it. A compaction
over the 25 ms key-loss bound would already be true of every settings write
today (`kb_eeconfig`, VIA, the RGB flush). It would go in the BACKLOG as a
wear-leveling finding, beyond profiles. For an ordinary write over 15 ms,
the fallback is `kb_eeconfig`'s deferral, with its RAM cost.

### What a power cut can cost

- **Between a save's writes:** that slot, now empty.
- **During a compaction** (`wear_leveling.c:303`): **the whole EEPROM, the
  keymap included.** That's the wear-leveling layer's behaviour today for
  every settings write, not something profiles add. The remedy is the
  backups (below). "At most one slot", as draft 2 said, was wrong.
- **Within a few seconds of a Load:** the setters' writes are deferred
  (`kb_eeconfig`'s settle, `kb_eeconfig.c:58`, and the RGB flush), so a cut
  can keep some of the load's settings and not others. After the reboot
  the `*` shows the mismatch honestly.

## Loading a profile

Load applies the record's fields through the setters the menu already uses
(`menu/menu_glue.c`), with `save` true.

1. **The lighting, in the restore's order** (`menu/menu_edit.c:78`). While
   the matrix is disabled, the mode and HSV setters return early (speed
   doesn't, `quantum/rgb_matrix/rgb_matrix.c:758`). So: enable without
   saving, then the mode (from the stable id), HSV and speed, then the
   enable last at the record's value, saving.
2. **The rest:** `env_lcd_set`, `env_ind_set` for each group,
   `env_clock_set`, `env_batt_hours_set` (`kb_eeconfig`'s deferred write).
3. **The menu's latched model** is set as a choice's commit sets it
   (`model_clock` and the rest). Otherwise `sync_model()` treats the load as
   an external change and retargets.
4. **The active byte,** deferred ("Next and previous profile keys", below).

**What it doesn't touch:**
- **the RGB flags;**
- **the power ladder and the low-battery lights cut,** which sit below the
  user's settings and keep applying. The cut is a scale (`power.c:137`), not
  `rgb_enable`, so a loaded profile never relights keys the cut has turned
  off.

### "Modified"

The top-level row shows the active slot's name, with `*` when the live
settings differ from that slot's record.
- **The comparison is computed in the row's signature,** exactly: the live
  getters (`env_rgb_get`, `env_lcd_level`, `env_ind_level` twice,
  `env_clock_mode`, `env_batt_hours`) against the active record, read from
  the RAM cache. It's a compare, not a hash, so no collisions (the Battery
  page's hash can collide). Codex wants repeated scans benchmarked; that
  goes in P5b's board pass.
- **The result goes in the item signature's spare bit 2,** and the active
  slot's identity in `val`. The name's text isn't in the signature, so every
  profile write (save, rename, delete, a host restore) calls
  `menu_invalidate()`, which repaints the names and summaries.
- **Any change makes the `*`:** Fn+keys, VIA, the menu's editors. The
  ladder's caps don't, because they never touch the user's values.

### Next and previous profile keys

Two custom keycodes, `PROF_NXT` and `PROF_PRV`, **appended** after
`PWR_MODE` in the `ak820pro_keycodes` enum, with matching entries at the end
of `via.json`'s `customKeycodes[]`. Their titles are "Next settings profile"
and "Previous settings profile", and their short names `Prof+` and `Prof-`.
`check_via_sync.py` guards the pairing. **Unbound in the default keymap:**
the owner assigns them in VIA.

- **A press loads the next (or previous) saved slot** after the active one,
  in slot order, skipping empty slots and wrapping round. From no active
  slot, Next loads the first saved one and Previous the last. With one
  saved slot, a press reloads it, which also clears its `*`: a quick way
  back to the profile. With none saved, it loads nothing.
- **The screen names it** in a brief overlay, as Fn+B names the power mode:
  `Profile: Work`, or `No profiles`.
- **The load is the menu's Load:** the same setters, the lighting's order
  and the effect-id check (`effect skipped` in the overlay).
- **On a press, not a release; no repeat.** It's handled on the board and
  nothing goes to the host, over any link.
- **While the menu is open,** the menu follows: its rows' signatures see the
  change. An editor previewing is cancelled first, as for any external
  write (`Cancelled`). Rename captures every key, these two included.
- **Refused while a host restore is open, or inside a deep sleep's
  recovery.** The overlay says `Busy`.
- **The active byte is deferred,** so a run of presses costs one write. The
  press sets a pending value. The 10 Hz housekeeping writes it once it has
  been stable for a settle time, as `kb_eeconfig` does, never inside
  `sleep_recovering()`, with the sleep waiting on it. The setters' own
  writes are deferred already. The pending value is 1 B of the palette's
  RAM. **The menu's own active-byte writes** (Load, Save, Delete) go
  through the same pending value, so the active byte has one writer and
  one rule.

## The menu

**New nodes are appended from 50,** because op 27 sub 5 reports the screen
as 16 + node and the board scripts key on those numbers. **The current
assertion permits 13 (50-62).** Node 64 would alias node 0 in `RK_ITEM`'s
signature (`menu.c:834`). Proposed, 9 or fewer:
- `N_PROFILES`;
- `N_PSLOT0-3`, or one `N_PSLOT` with the slot as its value;
- `N_PLOAD`, `N_PSAVE`, `N_PRENAME`, `N_PDELETE`;
- the summary as `RK_NOTE` rows, not nodes.

**Each page** gets a title in the `T_*` enum and an `MT_I_*` icon
(`menu_text.c` counts them). The flashes and confirm texts that carry a
slot's name (`Loaded`, `Replace Home…?`, `Delete Home?`) are new `T_*`
titles. Their pages invalidate at entry, as `open_about()` does, so a
different name repaints. Text is 20 cells a row in the mono face, and a
split row's cells 0-1 are its icon.

**The page stack grows from 3 frames to 4.** Top, then Profiles, then a
slot's page, then Rename or a confirm, is four deep. `stack[3]` today: the
array at `menu.c:212`, its depth guard at `menu.c:1243`. A frame is 3 B;
the budget allows 4, paid from the palette.
- The alternative is for Rename and the confirms to replace the slot page's
  frame (pop, then push). That needs the slot remembered elsewhere and the
  slot page rebuilt on the way back.

**The top level becomes 13 rows,** so page 2 has 5. `menu_s0_test`'s
scrollbar thumb (75 px for 12 rows) and `menu_p1a_board.py`'s top-level
steps change with it.

### The top level

```
⧉ Profiles        Home*
```

- **The value is the active slot's name,** or `None` when no slot is active
  or the active slot isn't valid.
- **The name is truncated to fit.** `cells2` puts the label left and the
  value right-aligned in 20 cells, and `[icon] Profiles` takes 10. So the
  value gets 8 characters and the `*`, or 9 with no `*`.
- **The Profiles page shows all 12** (`✓ ` + 12 + ` empty` is 20).

### The Profiles page

```
◀ Back
✓ Home
  Work
  Profile 3     empty
  Profile 4     empty
```

- **The active slot** gets the green check box the menu uses for a saved
  option (the slot node joins `is_option()`).
- **Empty slots** are greyed, with `empty` in the value column.
- **A click on an empty slot** saves at once as `Profile n`, makes it
  active, flashes `Saved` and stays on this page.
- **A click on a saved slot** opens its page.

### The slot page

```
◀ Back
Load
Save current here
Rename
Delete
💡 Solid Color   ▸80
   H:310 S:0% B:100%
```

- **The summary goes below the actions,** as non-selectable `RK_NOTE` rows,
  the way the Battery page places its notes (rows 4-6). The cursor indexes
  only the listed rows (`cursor = (cursor + turns) % row_count`), and every
  listed row is selectable, so nothing in the cursor changes.
  - **Summary on top instead** needs a display offset in `row_at` (item i
    at row i + 2) and its own tests (lit rows, the top, paging). Decided:
    below (Decided 10).
  - **Proposed content:** the effect's name and speed on the first row;
    hue (in degrees, as the Hue editor shows it), saturation and
    brightness on the second. A third row (the screen, the indicators, the
    clock) still fits in the 8.
- **Load** commits like a choice: it flashes `Loaded` and pops to the
  Profiles page, where the check moves. If the effect's id isn't in this
  build, it flashes `Loaded, effect skipped` instead.
- **Save current here** goes through the confirm layout (`L_CONFIRM`, as
  Reset counters and Bootloader do): `Replace Home with the current
  settings?`. Then `Saved`.
- **Rename** opens the name editor (below).
- **Delete** confirms (`Delete Home?`), empties the slot and pops to the
  Profiles page.
- **While a host restore is open** (below), these pages pop, and their
  writes are refused with `Busy, try again`.

## Rename

The one place the menu takes typing. The design's promise, that typing
works while the menu is open, holds everywhere else, and the editor's page
says so: `Type a name`, `Enter saves`, `Esc cancels`.

### Three states, in one static byte

The physical matrix going idle isn't enough. One-shot mods and layers,
toggled layers and a tap-hold action queued in QMK's tapping buffer
(`quantum/action_tapping.c:130`) all outlive the keys. So the capture is a
small state machine, `WAIT`, `CAPTURE` and `DRAIN`, in one byte of the
palette's RAM.

- **WAIT** (Rename picked): the editor shows, but nothing is captured yet.
  It moves to CAPTURE at the end of a complete scan in which:
  - the debounced matrix is idle (`matrix_get_row` over the 6 rows, the
    knob's (0,14) masked);
  - QMK's tapping state holds no key and no queued event. That state is
    private (`quantum/action_tapping.c:130`), so P5c adds an accessor,
    `action_tapping_idle()`: the tapping key empty and the waiting buffer's
    head equal to its tail. It's a ninth core file with a local change,
    additive, for CLAUDE.md's list.

  At that move it clears the one-shots: `clear_oneshot_mods()` and
  `reset_oneshot_layer()`. (`clear_oneshot_layer_state()` takes a
  fulfilment mask, `quantum/action_util.c:211`, and isn't the full reset.)
  A one-shot set before Rename doesn't hold WAIT: it's cleared at the move,
  so it can't land on the first key after Rename.
- **CAPTURE:** every key press and release is swallowed in
  `pre_process_record_kb`. The gate sits after `menu_pre_process()`, which
  takes only the knob's (0,14) and the encoder's halves by physical
  identity, and before `pre_process_record_user`. So the knob keeps driving
  the menu. Fn's press is swallowed, so a momentary Fn layer never turns
  on.
- **The knob's handler treats Fn as up throughout Rename,** whatever
  `layer_state` says. `menu_glue.c:288` passes the Fn layer's state to the
  knob's handler, and a keymap that toggles or latches a layer (TG, TO, a
  one-shot layer) can leave it on from before Rename. Without the rule, a
  knob click there would read as Fn+click, the menu's close. It's one rule
  in `menu_physical`'s call, keyed on the Rename node. JD's layout has only
  `MO(1)` and `MO(3)` (checked), but other owners' may toggle.
- **DRAIN:** after the capture ends, for any reason, events are still
  swallowed until the end of a complete scan with the matrix idle. It's
  checked in the housekeeping, after the scan's events, not inside the
  event handler: when several keys come up in the same scan, the matrix
  reads idle at the first release, and ending there would let the others
  through as orphan releases.

**Where the capture ends:** it ends whenever the current node stops being
Rename's while the menu owns the panel. That covers:
- Enter, Esc, the knob's click or hold;
- the idle close;
- `PO_EV_CLOSE`;
- a loss's `MENU_CLEAR` (`screen_open`);
- the bootloader item.

(The slider's Connection follow, `menu.c:1614`, pops only the BT screens
and `N_CONNINFO`. It never closes Rename.)

### Input

- **Characters come from the default layer's keycode** at the event's
  position: `keymap_key_to_keycode(get_highest_layer(default_layer_state),
  key)`. They don't come from the keycode QMK resolved: that goes through
  the source-layer cache (`quantum/quantum.c:258`, inside `action_exec`,
  `quantum/action.c:78`), and a toggled layer would change it.
- **`KC_A-Z`, the digits, space and US punctuation** give ASCII 0x20-0x7E,
  which the mono face has.
- **Shift is read from the debounced matrix** at each event: the positions
  whose default-layer keycode is a Shift. It isn't tracked, and since its
  presses are swallowed, QMK's mods never move.
- **`Backspace`** deletes the last character. The cursor stays at the end.
  Twelve characters at most.
- **The mapping is US QWERTY's**, whatever the host's layout: the board
  sees keycodes, not characters. Worth a line in Help.

### Finishing

- **Enter or the knob's click commits,** with the write at the click
  ("When", above).
- **Esc or the knob's hold (Back) cancels,** and so does a host restore.
- **The idle close:** `menu_long_wait()` gains Rename, which selects the
  180 s limit (`menu.c:1667`, `menu_ops.c:154`) instead of 24 s. Proposed
  beyond codex's check: in CAPTURE, a typed key restarts the menu's idle
  timer, since typing there is input to the menu. Elsewhere, typing still
  never restarts it (C7, on purpose).

**RAM:** the name lives in a third arm of the page union (`pg`, `menu.c:234`,
exactly 12 B: `name[12]`, its length from `strnlen`). The state byte is the
palette's.

## Backup and restore across flashes

A flash erases the EEPROM, and with it the profiles. Without a backup,
every dev flash would wipe them. `flash.sh` already backs up and restores
the keymap and the lighting.

### `HC_PROFILES`, 0x10 on the health channel 0x13

0x10 is free (`hid_protocol.c:490`). The 32-byte report's framing follows
the existing commands (`hid_protocol.c:403`):

| Bytes | Block pages (subs 0-3) | The live record (subs 4-6) |
|---|---|---|
| 0 | `SET_VALUE` | `SET_VALUE` |
| 1 | the channel, 0x13 | the channel, 0x13 |
| 2 | the command, 0x10 | the command, 0x10 |
| 3 | the sub | the sub |
| 4 | the page, 0-4 | the record's first byte, the state (its format) |
| 5 | the token | the record, continued |
| 6-31 | **26 bytes** of the block | to byte 30: **27 bytes**, the whole record |

**So the 110 B block is five pages of 26 B** (4 x 26 + 6). Sub 0, a read,
has no token, and its page carries 26 B too, to keep one page size. The
live record needs no page or token and fits whole.

| Sub | What |
|---|---|
| 0 | Read page p (0-4) of the block |
| 1 | **Begin a restore**, with a host token. It aborts any open restore, writes the magic to 0x00 at once (so a torn restore reads as four empty slots), and opens the transaction |
| 2 | **Write page p**, with the token, straight into the block. The magic's byte (offset 0) is masked: the host never writes it. The page is marked received |
| 3 | **Commit**, with the token. It requires all five pages from this transaction, validates the whole image from the RAM cache (each record's state, crc, ranges; the active byte normalized), writes the active byte, then **writes the magic last, in its own call**. Otherwise it refuses, and the block stays unformatted |
| 4 | Read the **live record**: the current settings as a record, power mode included (`fields` 0xBF). Byte 0, the state, carries the format (0x01, v1), and the record is exactly 27 B. **It cancels an open editor's preview first**, as VIA's lighting reads do (`hid_protocol.c:1392`), so a backup never saves an uncommitted preview |
| 5 | **Apply a live record**, as a Load does. It cancels an open editor's preview first (as an external write does: `Cancelled`) |
| 6 | **Flush:** the deferred `kb_eeconfig` and RGB writes now, outside a recovery. **It cancels an open preview first too:** RGB's forced flush bypasses the normal gate (`quantum/rgb_matrix/rgb_matrix.c:102`) and would otherwise write the preview |

**What the readback proves:** sub 4's readback after a flush confirms the
board's RAM, not the flash. The settings' own writes go through QMK's EEPROM
wrapper, which discards a write's status
(`drivers/eeprom/eeprom_wear_leveling.c:38`). The profile block's writes
report theirs (`wear_leveling_write()`, "Writes", above). For the settings,
the board pass's power cycle after a restore is the durability check.

**The transaction's state, 3 B of the palette's RAM:**
- the token;
- a five-bit page mask and an open bit, in one byte;
- the timeout, a countdown in 10 Hz ticks (50 is 5 s), decremented by the
  housekeeping.
- **While a restore is open,** the menu's profile writes are refused and
  its profile pages pop.
- **A new Begin, or 5 s without a page,** aborts it, and the block stays
  unformatted.
- **No staging buffer:** pages go straight into the block, and the magic,
  cleared at Begin and written last at Commit, is what makes it all or
  nothing.
- **What codex found in draft 2's version:** without the token, the mask
  and the masked magic, individually valid old and new records could pass
  a commit together.

**Firmware without `HC_PROFILES`** answers "unhandled", as a daily build
answers the bootloader jump. The host tool says so and skips the profiles.

### The host side

- **`hostagent/ak820profiles.py dump|restore|show`,** the backup at
  `~/Documents/ak820pro-profiles.json`: the block's bytes, the live record,
  and both decoded for reading (effects by stable id and name).
- **`flash.sh`:**
  - **Before the flash:** it backs up the lighting (VIA's channel, as now)
    and, where the firmware has `HC_PROFILES`, the profiles and the live
    record, fatal unless `--no-profiles`.
  - **After the flash: one authoritative restore of the RGB.** If the new
    firmware has `HC_PROFILES` and the backup has a live record, it applies
    that (sub 5), flushes (sub 6), reads it back (sub 4) and compares, and
    skips `ak820lighting.py`'s restore. Otherwise it restores the lighting
    as now. That way two snapshots never overwrite each other.
  - **This also fixes what every flash has done until now.** It reset the
    screen level, the clock format, the indicators, the readout and the
    power mode. Today's flash put JD's board back in Balanced mid-drain.
- **Versions:** the firmware refuses a block or record format it doesn't
  know, and the host tool translates older ones. Effects travel by stable
  id.
- **Windows:** the daemon reads the board without enumerating HID. A
  Windows `ak820 profiles` comes later. `flash.sh` on MSYS2 has the same
  rule as the keymap's backup.

### Macros

The macro buffer shrinks to 127 B, and `ak820keymap.py`'s backup doesn't
include macros today (`hostagent/ak820keymap.py:154`). In P5a, with the
block:
- **The backup includes the macro buffer** (VIA's macro get-buffer), and the
  restore writes it back.
- **The restore follows the buffer's validity byte**
  (`quantum/dynamic_keymap.h:51`): the last byte non-zero first, then the
  contents, then the last byte zero.
- **A backup whose macros don't fit the new buffer is refused,** with a
  message naming the sizes. The backup file is kept for the owner to trim.

## Budget

| | Cost | Room |
|---|---|---|
| EEPROM | 110 B | 237 B of macro space, so 127 B are left |
| RAM, static | ~9 B: Rename's state 1, the transaction 3, the pending active byte 1, the fourth stack frame 3 (4 allowed) | the palette's 14 B, made const in dev; dev's heap gap stays at its 128 B floor |
| RAM, stack | a 27 B record buffer at a save, a load or a host page (no VLA: the writes call `wear_leveling_write()`) | the stacks' margins (to check) |
| RAM, union | Rename's `name[12]`, a third arm of `pg` | `pg`'s 12 B, unchanged |
| Flash | ~4-6 KB (code, nodes, text, an icon, the effect ids) | dev 54.6 KB free, daily ~79 KB |

## Tests

- **Host:**
  - the record codec: the crc over the body only; the state byte's three
    readings; the active byte's normalization;
  - load's field mask and validation: an unknown effect id, out-of-range
    values, and the lighting's order with the matrix disabled;
  - the stable-id check script: a reorder or removal fails it, and an
    append passes;
  - the menu's new pages in `menu_s0_test`'s style: navigation, the confirm
    paths, the empty-slot save, the `*` and its invalidation, the 13-row
    top level's scrollbar, the 8-character truncation, the four-frame
    stack, `Busy` during a recovery and during a restore;
  - the formatting: the first save on an unformatted block writes the
    states, the active byte and then the magic, and a stale record from
    before it never shows;
  - the Next and Previous keys: slot order, skipping empties, wrapping,
    from no active slot, with one saved slot and with none; refused
    during a restore and a recovery; an editor's preview cancelled
    first; four quick presses costing one active-byte write;
    `check_via_sync.py` passing with the two appended keycodes;
  - Rename's states:
    - WAIT held by a held key and by a queued tap-hold
      (`action_tapping_idle()` false), and not by a one-shot, which the
      move to CAPTURE clears;
    - CAPTURE's swallowing, with characters from the default layer while a
      layer is toggled, and Shift from the matrix;
    - with a toggled Fn layer, a knob click commits and never closes;
    - DRAIN after every kind of close, ending only after a complete scan,
      with two keys released in the same scan;
    - Backspace, the 12-character limit, the 180 s idle, and typing
      restarting it;
  - `HC_PROFILES`:
    - a missing page, a page from another token, a menu write mid-restore,
      the 5 s timeout and a second Begin all leave the block unformatted;
    - the host's magic byte is ignored;
    - a bad crc is refused whole;
    - the framing: five pages of 26 B with the token, and the live record's
      27 B without;
    - subs 4 and 6 with an editor previewing: the preview is cancelled
      first, and neither the backup nor the flush holds it;
    - a failed `wear_leveling_write()` (injected) reports `Save failed` in
      the menu and an error over the command;
    - firmware without the command is skipped;
  - the macro backup and restore: the validity byte, and an oversized
    restore refused.
- **Board:**
  - **first, in P5a:** a complete pass with one save, with and without a
    compaction, against 15 ms;
  - repeated scans of the top level with the `*`'s compare;
  - a board pass in `menu_p1a_board.py`'s style;
  - the flash round trip on Buzz: save four slots, flash, check all four
    and the live settings came back and were read back durable, and check
    the lighting was restored once;
  - Rename over BT and USB: a key held at the open and at the close, and
    closed by the idle timer, by a loss and by the bootloader item.
- **Failure:** a power cut between a save's or a rename's writes (the
  watchdog test hook's reset-during-write) leaves that slot empty, and the
  others intact. A power cycle after a host restore keeps the live
  settings: the durability check for the writes QMK's wrapper doesn't
  report.

## Phases

1. **P5a, storage and backup, no UI:** the block, the codec, the effect
   ids, `HC_PROFILES`, `ak820profiles.py`, the macro backup, `flash.sh`, the
   palette made const. Testable from the host alone, and it brings the
   live-settings restore to every flash at once.
   - **The palette first, on its own commit:** make `pal` const in dev and
     measure the dev heap gap before anything spends it. Only that measure
     proves the ~9 B fit.
2. **P5b, the menu:** the top-level row, the Profiles page, the slot page,
   Load, Save, Delete, the summary, the `*`, the fourth frame, the
   deferred active byte, and the Next and Previous profile keys (appended
   to the keycode enum and `via.json`).
3. **P5c, Rename,** with `action_tapping_idle()` in
   `quantum/action_tapping.c` (a ninth core file with a local change) and
   the knob's Fn-up rule.

Each phase gets codex before its flash, as the menu's phases have.

## Review history

**Codex on draft 2** (2026-10-25,
[`review-codex-settings-profiles-plan-2026-10-25.md`](review-codex-settings-profiles-plan-2026-10-25.md)).
Every finding is taken:

1. **Q1, placement sound.** The VIA reset and `eeconfig_init` difference is
   now under "What erases the block".
2. **Q2, synchronous writes conditional.**
   - The explicit `!sleep_recovering()` gate, for the menu and the host, is
     in "When".
   - The measure is now a complete pass with compaction against 15 ms.
     Deferral doesn't bound compaction.
   - "Only changed bytes" is corrected: the whole range is written, plus
     the VLA's stack copy.
3. **Q3, matrix idle insufficient.**
   - The WAIT, CAPTURE and DRAIN states, settling QMK's tapping and
     one-shot state first.
   - The drain ends after a complete scan.
   - Characters come from the default layer, not the resolved keycode.
   - The state byte is budgeted.
   - The stack grows to four frames.
   - The slider's follow is removed from the closes, since it never closes
     Rename.
4. **Q4, the RGB order.**
   - Enable, then mode, HSV and speed, then enable last.
   - The host's apply cancels a preview.
   - Durability: the flush (sub 6) and the readback. A cut after a Load is
     stated.
   - One authoritative RGB restore in `flash.sh`.
5. **Q5, macro migration.**
   - The macros are backed up and restored, with the validity byte, and an
     oversized restore is refused.
   - Firmware without `HC_PROFILES` is handled.
   - Effects by stable id, since a membership check can't see renumbering.
6. **Q6, transaction state.**
   - The token, the page mask and the masked magic, with the magic
     published last.
   - Menu writes are excluded while a restore is open.
   - A save writes its state byte last, and the crc leaves the state out,
     so Delete keeps it valid.
   - The active byte is normalized.
   - Five pages of 27 B, and the live record framed by its state byte.
   - Losing the whole EEPROM in a cut compaction is stated, as today's
     behaviour.

**The signature.** Node 64 aliases node 0; it doesn't run into `RK_TEXT`.
The current assertion permits 13 additions. The `*` goes in spare bit 2 and
the active slot in `val`, with explicit invalidation for names and
summaries, and the compare benchmarked.

**Codex's verify of draft 3** (2026-10-25,
[`review-codex-settings-profiles-plan-verify-2026-10-25.md`](review-codex-settings-profiles-plan-verify-2026-10-25.md)).
Q1, Q5 and the signature were resolved; Q2 was right to stay conditional on
the measure. Every finding is taken:
- **Q6, Rename protected too:** invalidate, then the name and crc, then the
  state last ("Writes").
- **The formatting** of an unformatted block at the first write: states,
  active byte, then the magic.
- **`HC_PROFILES`' wire layout:** the explicit framing table, five pages of
  26 B with the token, and the live record's 27 B without. The timeout is a
  1 B countdown, so the transaction takes 3 B.
- **Q4:**
  - sub 4's backup and sub 6's flush both cancel a preview first;
  - the readback proves RAM only;
  - the profile writes go through `wear_leveling_write()` for its status,
    and the settings' durability is the board pass's power cycle.
- **Q3:** the tapping accessor `action_tapping_idle()`, a new local core
  change; the one-shots cleared with `clear_oneshot_mods()` and
  `reset_oneshot_layer()`; the test reconciled (a one-shot doesn't hold
  WAIT).
- **The toggled Fn layer:** the knob's handler treats Fn as up throughout
  Rename.
- **Corrections:** `menu.c:212` is the stack's array and 1243 its guard, and
  a frame is 3 B with 4 allowed; the Connection follow also pops
  `N_CONNINFO`; speed doesn't return early while the matrix is disabled.

**Warren's check of draft 1** gave draft 2:
- the node limit;
- the top level's truncation;
- Rename's idle rule, its 12 B arm, the end of capture on every close, and
  the matrix as the key state;
- the `*` in the signature;
- the synchronous writes;
- the summary below the actions;
- the unstaged restore;
- the swallow gate's place.
