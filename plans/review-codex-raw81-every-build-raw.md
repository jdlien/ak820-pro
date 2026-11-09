No P1 or P2 findings. One nonblocking P3 exists in the promoted code. The patch is suitable for the requested cherry-pick.

| P1 — file:line | Finding | Scenario |
|---|---|---|
| — | None found. | — |

| P2 — file:line | Finding | Scenario |
|---|---|---|
| — | None found. | — |

| P3 — file:line | Finding | Scenario |
|---|---|---|
| [raw81.c:170](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/raw81.c:170), [ch582f_ajazz.c:904](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:904) | **Expired sessions can briefly become live again.** `have_session` remains set after expiry, while the elapsed counter wraps every **6 h 21 m 46.492 s**. Latch session expiry during regular servicing so the wrap cannot revive it. This already affects dev builds; the commit exposes it to releases. | An always-awake 2.4G board admits a request, then receives no admitted request or link reset for one counter period. A new session arriving in the following one-second interval receives `BUSY`, despite hours of inactivity. A repeated sequence in the old session can similarly receive `STALE`. It recovers after that interval. |

1. **Dev/release separation is sound.** The collector, counters, initialization, elapsed-clock maintenance, forward declaration, dispatch, link-loss cleanup and response handling all remain available without `AK820_DEV_HOOKS`. Both release flavours build the VIA keymap. The handler requires no additional reply hook: it edits the supplied buffer directly.

   Op 17’s fill/clear/stall/hold, op 19, the 5A trace and RX tap remain guarded. The release path does read `r81_hold_resp` and `r91_window_on`, but their independent defaults are respectively **false** and **true**; no dev operation must run to establish them. See [initialization and dispatch](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:975) and [dev-only operations](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1126).

2. **The bulk drain preserves its bytes and exit semantics.** At [the loop](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2030), every consumed byte increments `bytes_processed` exactly once. Collector start, completion, quarantine and muted-real-byte paths use `continue`, so they still exhaust the fetched buffer. The `switch` breaks only leave their switches.

   The sole explicit loop exit follows an empty `RX_TAKE`: its local buffer is exhausted and the underlying immediate read returned zero. Only this sets `drained=true`. The other exit is the 64-byte cap, which conservatively leaves it false even when byte 64 happened to empty the UART queue. Each refill requests only the remaining allowance, so no buffered tail is abandoned.

   `WDT_TEST_HOOKS` injection consumes the same allowance before real bytes. Its producer is main-loop-only, so injections cannot appear midway through a buffered UART chunk. Muting discards and counts real bytes without feeding either parser.

   F-019’s five-millisecond quiet-window expiry remains on the empty-read path. F-031 remains fixed: lifetime is judged after draining, and commit uses the last empty-read age. Finally, `rx_defer` combines `!drained` with either ACK prefix before the pump runs.

3. **Keyboard reports can wait longer; the complete bound includes two deferrals.** The [response window calculation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1106) gives **24 ms** for a reply/receipt pair with an empty output queue, **21 ms** for a receipt alone, and at most **29 ms** with the configured 128-byte queue.

   Under persistent `rx_defer`, [the pump](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1349) can add **50 ms before closing that window, then another 50 ms before starting the A-frame**: up to **129 ms of gating**, plus main-loop service latency. The latter 50-ms start gate already existed in releases. These are timer thresholds, not a hard wall-clock delivery guarantee. Once keyboard frames are queued, another response cannot overtake them.

   **A finite exchange does not leave sleep blocked indefinitely.** Requests dispatch on the next eligible top-level pass; unsent responses expire after 250 ms when the idle pump services them; ACK windows expire with bounded deferral. Response expiry is not serviced while A-frames occupy the queue, but those frames already block sleep. **Continuing host traffic can keep sleep blocked indefinitely**, including repeated requests that produce rejection receipts. A partial collection itself is not a sleep blocker and can be interrupted by sleep.

4. **I found no dispatch bypass of the allow-list.** [raw81_allowed()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/raw81.c:211) permits exactly text commands `01–04`; health commands `01,02,04,06,07`; and `0E` pages `00,21–2A`. The decoded command passes this check before reservation.

   [The board dispatcher](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/hid_protocol.c:1484) has distinct channel predicates, and the allowed handlers have no argument-controlled route into settings, flash, clock writes, injection or bootloader operations. Text changes RAM and deferred display state; the health operations read state. The six padded bytes are zeroed.

   Rejection receipts never invoke the dispatcher. Responses are fixed-length `91` frames, with no second dispatch or USB-send path. The newly supported host capabilities are therefore those text operations and health reads, plus their traffic effects on TX and sleep. The paired dongle remains the trust boundary.

5. **With no `81` traffic, normal BT/cable behaviour is unchanged, but cost is not limited to static RAM.** [Each task pass](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1829) now performs elapsed-clock bookkeeping and collector checks; a virtual timer runs approximately every **174.763 ms** while the system tick runs. The bulk-read object occupies **72 bytes on the 32-bit target’s stack**, before compiler frame allocation, and changes RX locking/copy timing.

   No response window or additional sleep blocker activates without a request. Ordinary `0x81` payload/checksum bytes do not start a collection because boundary tracking excludes them. Corrupted traffic leaving a boundary-eligible `0x81` can now invoke collection/quarantine in BT or cable mode too.

6. **The patch fits `cbd0d2f308`.** Read-only `git apply --check` passed. Its `raw81.c/.h` match the reviewed versions; the relevant driver difference is the dev RX-tap guard, outside the promoted functionality. Nothing requires the row ISR rewrite. The separately reviewed parent’s polled-SPI fix is not required by this patch; its additional health-read counters do not change dispatch safety.

No files changed and no build or firmware tests ran. Verification was source tracing, arithmetic checks and the read-only patch-application check.

READY