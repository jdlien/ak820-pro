# Codex's second verify of P3 (after the ACK boundary was backed out), 10-25

Prompt: `plans/review-prompt-p3-verify2.txt`. Line references are to
`a7c19f85`. The response: firmware `ea91b3d0`.

## Dispositions

- **An undelivered select can release the pair onto the old slot (must
  fix):** taken, failing closed as codex proposed, with the driver's state
  machine unchanged. Two read-only facts: `select_tx_failed` (a select
  frame given up or refused by a full queue since `ch582_set_profile()`,
  cleared by an ACKed frame of the requested slot: frames resolve in order)
  and whether a select frame is still queued or in flight.
  `ch582_select_state()` reads pending while one is, and lost on the
  failure, so the menu's pair goes only once every select frame is ACKed
  and none failed. `btui.c`: `target_given_up` (the target's frames never
  ACKed while a stale 5B 32 retires the retry: lost, no pair; then a select
  that gets through, and the pair), `target_refused` (refused by a full
  queue: lost, no pair), and `boot_retry_pending` now expects lost when every
  boot select was given up, until one gets through. Three mutants, each
  caught. A boot whose selects were all given up reads lost in the menu: a
  click on the current slot then re-selects it, which is what it needs.
- **The advertising shortcuts (can wait):** accepted as they are. At open, a
  stale 5B 31 can make the menu skip a pair it should send (the page then
  ends, and a retry sends it); the tick's redundant pair can leave the page
  "unconfirmed" while it advertises (the stop still works). Neither can pair
  a wrong slot.
- **The knob's readout:** as planned: read right after the flash, at rest,
  before JD uses it.

## The review, verbatim

**Yes—one wrong-slot path still needs fixing before this P3 flash.** The rollback restores the stated driver behavior, but FIFO ordering does not establish successful selection.

Static review: changed firmware files match `a7c19f85`; targeted tests match `864d190`. Process execution was unavailable, so I could not rerun them.

- **Must fix before flash: an undelivered select can still release pairing onto the previous slot.** [ch582f_ajazz.c:2060](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2060) accepts a delayed old-slot `5B 32`, retires `PA_SELECT`, and sets `select_acked`. [bt_ui.c:204](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:204) consequently permits pairing. But [ch582f_ajazz.c:1318](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1318) can discard the target frame after every transmission fails, then transmit the queued `A6 51`.

  Concrete path: module remains on BT1; request Pair BT3; delayed BT1 state retires BT3’s select retry; BT3’s UART frame gives up; pairing reaches BT1. No subsequent target select repairs this: `module_alive` disables the cold-boot retry, and `5B 23` reissues only while `PA_SELECT` remains active. A queue-full rejection at **driver line 1517** permits the stronger case: no target transmission at all.

  Keep baseline state-machine retirement, but make the menu’s pairing fail closed on rejection/give-up of its target transaction. [btui.c:195](C:/Users/jdlien/code/ak820-pro/scripts/ch582_sim/btui.c:195) explicitly supplies the target ACK; `bounce_stale` therefore does not test this failure.

The remaining checks:

1. **Driver equivalence: yes**, within the four stated categories. The bounce-end reset, final SELECT/PAIR windows, and genuine `36` retiring `PA_SELECT` look sound. The three getters are observational; their state observations cannot prove target delivery. The menu never fires while selection *reads* pending, but stale frames can end that condition prematurely. Ordinary cold-boot/`23` retries retain the requested target; slot keys and slider events cancel an armed menu pair. I found no separate ordering regression there.

2. **Can wait: advertising shortcuts can misreport or lose an action.** [bt_ui.c:255](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:255) can swallow a new pairing request when an old-slot `31` falsely describes the current target as advertising. Conversely, the tick’s redundant pair clears confirmation; without another `31`, the page can become “unconfirmed” despite actual advertising. Neither adds a wrong-slot mechanism beyond the must-fix above.

3. **Knob diagnostic: correct and read-only.** [menu_ops.c:307](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:307) returns the decoder’s low two state bits through dev-only `env_knob_state()`. The reset rule does not manufacture that reading. Read after settling, preferably at several adjacent detents: `0/3` supports the assumption; `1/2` requires removing the rule. This can be checked after flashing, before normal use.

4. **No additional cable-position flash hazard found.** The linked dev ELF has the stated **136-byte heap gap**, eight bytes above the enforced floor. Recheck the rebuilt artifact after the fix.