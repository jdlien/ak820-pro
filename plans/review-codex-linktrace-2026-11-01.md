# Codex: the link trace, black's measurement build (2026-11-01)

The review of `gremlin/linktrace` (`qmk_firmware-ak820pro`): `b5c2268296b`,
the link trace in `bluetooth/ch582f_ajazz.c`, on `34f02ab50e0`, a cherry-pick
of the audit's F-002 (QMK Command off, which `build.sh` now requires), on
black's `gremlin/ds-wake-fixes` `0118d39e67e`. Codex (Astra, xhigh,
read-only), with the prompt in
[`review-prompt-linktrace.txt`](review-prompt-linktrace.txt); the raw review is
[`review-codex-linktrace-raw.md`](review-codex-linktrace-raw.md).

**What it is for:** over BT on Windows, a key that wakes the board after a
long sleep is lost, because the host dropped the BLE link during the sleep
and the link comes back about a second after the wake (GREMLIN-RESULTS section 21).
JD wants the key held for up to ~1.5 s and then sent, or dropped as today
past that. Before the hold is designed, this build records what the module
does. After each deep sleep's wake, it keeps the link's and the TX queue's
first 52 events, each with its ms from the wake, in the RX tap's ring, with
no RAM of its own (the dev heap gap stays at 128 B). It records frame types
and times only. `ak820 sleep` reads it (`ak820-agent`, `dc1ae76`).

It went onto black at 22:28 11-01 while codex read (token `0x1157913e`). No
P1. Verdict: suitable for the measurement, no reflash needed.

## Dispositions

1. **P2, the bench's reader misdecodes the trace.** `scripts/devhook.py
   rxtap` takes the wake's timer for a byte count. A `stop` then drops mode 2
   to 0 and keeps the trace. Fixed: both `rxtap` reads and `rxtap stop`
   refuse while the trace holds the ring and point at `ak820 sleep`, which
   decodes `slot / 4` records and only reads (op 15 with arg 0). `rxtap arm`
   still takes the ring.
2. **P3, a report's identity is inferred.** A press and its release are
   both `A1`. `ACKED` names the queue's head as it popped, an orphan ACK is
   not seen, and an ACK is the module's, not the host's delivery. Taken: the
   measurement is one isolated key, a press and a release with nothing else
   typed for a few seconds, and the host's side is JD's report of whether it
   typed.
3. **P3, the capture's limits.** `SENT` is stamped before `sdWrite` and a
   `5B` at the parser, not at its arrival. The ring stops at the wake and 51
   events, so a full ring without a `5B 32` does not show the link stayed
   down. Taken: the ordering is read to a few ms, which is enough for a
   ~1.5 s hold. With one isolated key the ring stays far from full.
