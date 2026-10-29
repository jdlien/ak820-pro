# Warren's deep-sleep phases on JD's board, and slot 9 across a reset (23:50-23:53 10-28)

`gremlin/ds-phase` (`27d1105dc1`, on `8ec0c8b9b4`), built here as dev:
`via-dev-27d1105dc1-20261028-234114.bin`, token `0xbc3b64c4`, heap gap
184 B. It does two things:
- splits the watchdog record's deep-sleep site into phases (27 awake in
  `deep_sleep()`'s code, 28 asleep, 29 waking from SRAM, 30 restoring,
  31 unlocked);
- keeps the sleep under way in RAM that crt0 doesn't clear (op 24 slot 9),
  with the wake ring and the stray snapshot.

**What `ds-sequence.sh` did** (this folder; relay 2 never touched, the daemon
paused):
1. Flashed the build (flash.sh exit 0, everything restored).
2. Slot 9: no magic, as expected after a firmware that had no slot 9.
3. A 30 s fed armed sleep: the cap, 30 counted, 0 strays, PLL 95 loops.
4. Slot 9: magic, the cap, flags `0xc0` (slept, returned), 30 s,
   `from_boot_before` 0.
5. Re-flashed the same `.bin`, a software reset through the bootloader.
6. Slot 9: **the same sleep, `from_boot_before` 1**. The wake ring's entry
   was kept too.

**The no-init region survives the bootloader**, and so a WDT reset, which
keeps RAM as ram7 shows. A reset inside a sleep will now say where (the
phase), what woke it (the reason and the RIS), when (the counted seconds as
they came) and the strays.
