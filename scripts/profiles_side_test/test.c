/* The Win/Mac switch moved while the board is off (plans/AUDIT-2026-10-31.md,
 * F-030; first written as the audit's verify-041). Before the fix the boot
 * guessed a move from the last record, so a move toward a side with no
 * profile went unseen and the side left's settings were lost; now the boot
 * takes the side the settings are from the owner byte (PROF_OWNER_ADDR, the
 * audit's review; the default layer first, which codex showed a cut in the
 * flip's countdown or a PDF() key could leave wrong) and a move runs as a
 * live flip.
 *
 * Reuses the project's own fakes: scripts/profiles_test.c is #included with
 * its main() renamed, and the real menu/profiles.c is compiled beside it. A
 * power-off is modelled as the project's own test models a reboot: settle()
 * (the deferred active byte written, kb_eeconfig's 5 s flush done), then
 * prof_test_reset() (profiles.c's RAM; the EEPROM, the owner byte with it,
 * stays) and prof_switch(<switch position>) as dip_switch_init()'s boot
 * reading. scripts/profiles_cut_test cuts inside the flips. */
#define main profiles_test_main
#include "../profiles_test.c"
#undef main

static void sw(bool mac) { prof_switch(mac); }

static void power_cycle_on(bool mac) {
    settle();
    prof_test_reset();
    sw(mac);            /* the boot's reading */
    ticks(1);           /* the boot check */
    ticks(5);
}

/* Windows has profile 0 saved with the screen at 50; the Mac has none. On
 * Windows the screen is set to 33 (unsaved) and left 5 s. */
static void setup(void) {
    reset();
    sw(false);   /* boot on Windows */
    ticks(1);
    fk_lcd = 50;
    CHECK(prof_save(0, NULL) == PROF_OK);
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0xF0);   /* Windows slot 0, the Mac none */
    fk_lcd = 33;                         /* unsaved change on Windows: its `*` */
    settle();
}

int main(void) {
    uint8_t r[PROF_REC];

    /* A: the reference, live flips throughout. */
    setup();
    sw(true); ticks(3);   /* to the Mac (no profile) */
    printf("A live:     arrived on Mac: LCD %u, last record state 0x%02x lcd %u\n", fk_lcd, last_state(), last_lcd());
    fk_lcd = 90;
    sw(false); ticks(3);
    printf("A live:     back on Windows: LCD %u (as left: 33)\n", fk_lcd);
    int a_ok = fk_lcd == 33;

    /* B: moved while off to the Mac, then a live flip back to Windows. */
    setup();
    power_cycle_on(true);          /* unplug in cable mode, move switch to Mac, plug in */
    printf("B off/live: booted on Mac: LCD %u, last record state 0x%02x (0x%02x would be Windows' kept)\n", fk_lcd,
           last_state(), LAST_WIN);
    int b_kept = last_state() == LAST_WIN;
    fk_lcd = 90;
    sw(false); ticks(3);
    printf("B off/live: back on Windows: LCD %u, active %u (as left: 33; 50 is profile 0's saved value)\n", fk_lcd,
           prof_active());
    int b_lcd = fk_lcd;

    /* C: moved while off both ways. */
    setup();
    power_cycle_on(true);
    fk_lcd = 90;                   /* on the Mac */
    power_cycle_on(false);         /* off, move back to Windows, on */
    printf("C off/off:  back on Windows: LCD %u, active %u, star %d (as left: 33; 90 is the Mac's change)\n", fk_lcd,
           prof_active(), prof_active_rec(r) == 0 && prof_differs(r));
    int c_lcd = fk_lcd;

    /* D: contrast. Both sides profiled and the last record holding the Mac's
     * (after a live flip pair): the boot check detects the move. */
    reset();
    sw(false); ticks(1);
    fk_lcd = 50; CHECK(prof_save(0, NULL) == PROF_OK); settle();
    sw(true); ticks(3);
    fk_lcd = 20; CHECK(prof_save(1, NULL) == PROF_OK); settle();
    sw(false); ticks(3);  /* Windows back (50), the Mac's 20 kept */
    fk_lcd = 33; settle();
    power_cycle_on(true);
    printf("D contrast: booted on Mac (Mac has a profile, record holds Mac's): LCD %u, last 0x%02x lcd %u\n", fk_lcd,
           last_state(), last_lcd());
    sw(false); ticks(3);
    printf("D contrast: back on Windows: LCD %u (as left: 33)\n", fk_lcd);
    int d_ok = fk_lcd == 33;

    /* E: the root cause is the empty record, not only the missing profile:
     * both sides on slot 0, the record cleared by a Save of the slot the
     * other side uses (prof_save()'s last_clear()), then moved while off. */
    reset();
    sw(false); ticks(1);
    fk_lcd = 50; CHECK(prof_save(0, NULL) == PROF_OK); settle();
    sw(true); ticks(3);
    CHECK(prof_load(0) == PROF_OK); settle();        /* the Mac on slot 0 too */
    sw(false); ticks(3);                    /* last = the Mac's */
    CHECK(prof_save(0, NULL) == PROF_OK); settle();  /* Windows saves slot 0 again: last cleared */
    CHECK(last_state() == PS_EMPTY);
    fk_lcd = 33; settle();
    power_cycle_on(true);
    printf("E both:     booted on Mac: LCD %u, last 0x%02x (a flip: slot 0's 50 loaded, Windows' 33 kept as 0x%02x)\n",
           fk_lcd, last_state(), LAST_WIN);
    fk_lcd = 90;
    sw(false); ticks(3);
    printf("E both:     back on Windows: LCD %u (as left: 33)\n", fk_lcd);
    int e_lcd = fk_lcd;

    printf("\nlive=%s, B kept=%s B back=%u, C back=%u, D=%s, E back=%u, fake-checks failed=%d\n",
           a_ok ? "33 ok" : "WRONG", b_kept ? "yes" : "NO", b_lcd, c_lcd, d_ok ? "33 ok" : "WRONG", e_lcd, fails);
    bool pass = a_ok && d_ok && b_kept && b_lcd == 33 && c_lcd == 33 && e_lcd == 33 && !fails;
    printf("RESULT: %s\n", pass ? "PASS (a move while off keeps the side left's settings, as a live flip does)" : "FAIL");
    return pass ? 0 : 1;
}
