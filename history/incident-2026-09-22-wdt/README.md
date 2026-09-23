# Watchdog recovery — 2026-09-22

User reported a keyboard freeze followed by `WDT reset x1` and recovery.
Times below are local (America/Edmonton).

## Evidence

- Host health sample at **13:12:15**, preserved in `agent-status-initial.txt`:
  watchdog count 0; 455 LCD blit timeouts; 28 non-flash stalls >=25 ms;
  worst main-loop gap 36 ms, attributed to blit; 109,030 wireless TX
  timeouts. These are accumulated counters, not events timed to the crash.
- Host log at **13:13:57**: playback request timed out and presence changed
  from present to unresponsive. Another timeout at **13:14:02**.
- Host log at **13:14:05**: presence changed from unresponsive to present.
  This brackets observed host failures, not the full hang duration.
- One read-only health capture after recovery, using
  `ak820-agent/target/release/ak820 health --stalls --rows --isr --json`,
  is transcribed from the successful command output in `health-after-reset.json`.
  It confirms `wdt_fired_last_boot=true`, consecutive reset count 1,
  and `wdt_degraded=false`. Uptime was about 136 seconds. Since reboot:
  zero LCD blit timeouts, zero >=25 ms stalls, worst loop gap 16 ms,
  worst row sampling gap 10 ms, and 10 wireless TX timeouts.

## The owner's account

Given at 21:30 the same day: typing normally, no media playing, on a FaceTime
call with screen sharing, not using Fn features beyond the ordinary layer-1
keys. The agent's status agrees that playback was paused (`media_last_text`
begins `pause`), so LCD traffic was light: the clock, plus a keep-alive push
every 30 s at most.

## Interpretation and limits

The watchdog actually reset the board; this was not only a host-side loss of
access. Firmware normally kicks it from housekeeping, with a hardware timeout
of approximately 12 seconds. The reset indicates that servicing stopped long
enough to expire it. Recovery is confirmed and the watchdog remains enabled.

The LCD timeout count is a useful lead, but does not establish what caused this
hang or when those timeouts occurred. Post-reset health counters describe only
the new boot and cannot clear the preceding boot of faults.

Current watchdog code preserves a magic word and reset count in `.ram7`, plus
captures the hardware reset flags at boot. It does not preserve a fault PC,
stack trace, or last-executing-operation record. Ordinary health counters are
RAM state reinitialized on reset. The host status is overwritten periodically;
the pre-reset sample was saved before its next refresh.

For a future occurrence, retained operation breadcrumbs across watchdog resets
would help identify the stuck subsystem. An instrumented build with a host
console capture could also record preceding stalls, although a permanent hang
may prevent the final operation from emitting a log. No firmware or agent
settings were changed during this investigation.

## Follow-up: diagnostic firmware installed

On the same day, new retained-operation diagnostics were implemented and
hardware-verified with one intentional watchdog reset. The keyboard correctly
reported `test_stall within raw_hid` and the updated agent saved it once with
the preceding health sample. Resetting health counters did not erase it.
The daily firmware and signed agent are now installed, with original keymap,
encoder and RGB settings verified after restoration. The intentional test
must not be counted as a second spontaneous failure.

See [validation artifacts](validation/) and
[implementation / hardware results](../../plans/WATCHDOG-BREADCRUMBS.md).
