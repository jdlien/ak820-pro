# Codex: the wake's three fixes (2026-10-31)

The review of `gremlin/wake-fixes` `cfe649c21b7` (on the mainline
`8ec0c8b9b4`) and its merge onto black's diagnostics, `gremlin/ds-wake-fixes`
`c7bc7bd0db9` (on `gremlin/ds-phase` `05ef0f5bbc9`), codex (Astra, xhigh,
read-only), with the prompt in
[`review-prompt-wake-fixes.txt`](review-prompt-wake-fixes.txt). The raw
review is [`review-codex-wake-fixes-raw.md`](review-codex-wake-fixes-raw.md).

JD picked the fixes on 10-31 ("I want to try both fixes") after black's 9 h
12 min cable-out sleep ran clean (GREMLIN-RESULTS section 21):

- **F-045** (the audit, [`AUDIT-2026-10-31.md`](AUDIT-2026-10-31.md)): a
  sleep takes USB_CFG's PHY_EN and ESD_EN as the driver left them and puts
  back only those.
- **The CT16B3 wait:** the 20 kHz tick's counter reset at every wake,
  bounded, with its own terminal site (69).
- **F-032:** a deep sleep's clock failure writes a terminal record (68)
  before its software reset, and the boot keeps those two sites under
  SWRSTF.

`c7bc7bd0db9` went onto black at 14:44 10-31 while codex read (token
`0xd26c31c8`). No P1; three P2s, fixed in `70f7c1ea10e`, merged as
`0118d39e67e` and on black from 14:57 (token `0x99bfbbb8`, dev heap gap
128 B, the floor; the daily's 2336 B). Codex's verify
([`review-codex-wake-fixes-verify-raw.md`](review-codex-wake-fixes-verify-raw.md),
prompt [`review-prompt-wake-fixes-verify.txt`](review-prompt-wake-fixes-verify.txt)):
all three fixed, nothing new at any level, the RAM confirmed from the ELFs;
keep `0118d39e67e` on black, and `70f7c1ea10e` is cleared for the mainline
once the hardware gate (4, below) passes.

## Dispositions

1. **P2, the restart's own reset was still unbounded.** A bounded reset
   before `gptStartContinuousI()` left the LLD's CRST spin after it.
   Fixed: `pwm_tick_restartI()` (indicators.c) does what
   `gptStartContinuousI()` and `gpt_lld_start_timer()` do for CT16B3 on
   this part (the state, MR0, the reset, the flags, the match interrupt,
   CEN), with the bounded reset in place of the LLD's. Boot's first start
   stays the LLD's.
2. **P2, the light sleep's copy could go stale** (dev only). Fixed: the
   pair is taken and put back around each WFI in chconf.h's idle hook,
   under its mask; light_task's copy is gone.
3. **P2, a bootloader round trip could keep a stale terminal record.**
   Bootmagic jumps before the boot reads the record, and the bootloader's
   exit is a software reset. Fixed: `bootmagic_reset_eeprom()` (ak820pro.c)
   calls `watchdog_record_forget()` (the magic cleared, with the sacrificial
   write), then QMK's default `eeconfig_disable()`.
4. **P3, the hardware gate.** Codex: reconnection after a wake that leaves
   both bits off is not proven from the documents, and the recovery's D+
   toggle does not set PHY_EN. Before the mainline, show both bits
   returning, SOFs advancing and HID working, with no reset, for:
   - a cable-out sleep, a key wake, past the recovery, then the cable in;
   - the cable's insertion waking the sleeping board;
   - a `uhubctl` reconnection, including ACTIVE with both off;
   - a host suspend with the cable in, the host's resume, and the
     keyboard's remote wake.

   Case 1 passed on black at 15:28 10-31 (GREMLIN-RESULTS section 21):
   both bits off at the wake as the driver left them, then the cable's
   plug-in ~20 s later enumerated and raw HID worked.

   Case 2 passed on black at 21:37 11-01 (GREMLIN-RESULTS section 21):
   the cable's insertion woke the sleeping board on CHRG after 306
   counted s, both bits off at the wake as the driver left them, the
   host's frames inside the recovery (no re-attach), enumerated 2 s
   after the plug-in and the clock synced over raw HID, with no reset.

   Case 4 passed on black at 22:02 11-01 (GREMLIN-RESULTS section 21):
   gremlin's S3 woken by black's key in USB mode on a back port (twice;
   one earlier key did not wake it, unexplained), and by the power
   button with black staying enumerated and the clock syncing over raw
   HID after; no reset in any host sleep. Through gremlin's
   power-switched hub nothing woke the PC, the mouse included. **The
   gate is complete.**

   Case 3 passed on white at 21:03-21:13 11-01, on the row ISR's stage 2
   (`b120a2069c`, v0.3.1's USB and sleep code), in two forms: data on to the
   sleeping board and then a key (no frames in 3 s, the recovery's
   re-attach, enumerated 3.8 s after the wake, the 20 s frames flag
   latched), and data off, a key, data on 30 s later (enumerated in 0.9 s).
   HID was read after each, with no reset (2 sleeps since the boot, 3287 s
   slept against the logger's 3282). The bits are inferred from enumeration
   as in case 1: this build cannot read `CFG`
   ([`../history/wake-case3-20261101/`](../history/wake-case3-20261101/README.md)).
