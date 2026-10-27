/* The early cleanup's rules (keyboards/a_jazz/ak820pro/flash_tidy.c, built
 * verbatim against the stubs; run.sh): when it consolidates the emulated
 * EEPROM, and when it must not. 10-27, JD: "it totally makes sense to use an
 * interactivity timer ... Someone who hasn't typed for ten minutes is
 * probably not looking closely at their keyboard." */
#include <stdio.h>
#include <string.h>
#include "quantum.h"
#include "wear_leveling.h"
#include "power.h"
#include "flash_tidy.h"

static int fails;
#define CHECK(c)                                                    \
    do {                                                            \
        if (!(c)) {                                                 \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c);     \
            fails++;                                                \
        }                                                           \
    } while (0)

/* The board, faked: a clock, the last key, the log, the LEDs, the supply. */
static uint32_t     fk_now, fk_key;
static uint32_t     fk_log;   /* bytes in use; a consolidation empties it */
static bool         fk_dark, fk_batt, fk_menu, fk_recovering, fk_cut, fk_fail;
static bool         fk_fail_empties;   /* a failed program: the store resets its log all the same */
static power_mode_t fk_mode;
static int          fk_cons;

uint32_t last_input_activity_elapsed(void) { return fk_now - fk_key; }
uint32_t last_input_activity_time(void) { return fk_key; }
uint32_t timer_read32(void) { return fk_now; }
uint32_t wear_leveling_log_used(void) { return fk_log; }
wear_leveling_status_t wear_leveling_consolidate(void) {
    fk_cons++;
    if (fk_fail) {
        if (fk_fail_empties) fk_log = 0;
        return WEAR_LEVELING_FAILED;
    }
    fk_log = 0;
    return WEAR_LEVELING_SUCCESS;
}
bool         sn32f2xx_led_committed_dark(void) { return fk_dark; }
bool         battery_on_battery(void) { return fk_batt; }
bool         display_menu_sleep_blocked(void) { return fk_menu; }
bool         sleep_recovering(void) { return fk_recovering; }
bool         power_lights_cut(void) { return fk_cut; }
power_mode_t power_mode(void) { return fk_mode; }

#define HALF    508u   /* (2048 - 1024 - 8) / 2 */
#define SEC     1000u
#define MIN     60000u

/* A key at `t`, then the clock to `t + idle`, a pass each 10 ms. */
static void key_at(uint32_t t) { fk_key = fk_now = t; }
static void idle_to(uint32_t idle) {
    while (fk_now - fk_key < idle) {
        fk_now += 10u;
        flash_tidy_task();
    }
}
static void reset(void) {
    fk_now = fk_key = 1000u;
    fk_log = HALF;
    fk_dark = fk_batt = fk_menu = fk_recovering = fk_cut = fk_fail = fk_fail_empties = false;
    fk_mode = POWER_MODE_NORMAL;
    fk_cons = 0;
}
static uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }

int main(void) {
    uint8_t pg[28];

    /* Under half the log: nothing, dark and idle as it may be. */
    reset();
    fk_log  = HALF - 1u;
    fk_dark = true;
    idle_to(30 * MIN);
    CHECK(fk_cons == 0);

    /* Dark: at 30 s of no key, not before; once, the log emptied. */
    reset();
    fk_dark = true;
    idle_to(30 * SEC - 10u);
    CHECK(fk_cons == 0);
    idle_to(30 * SEC);
    CHECK(fk_cons == 1 && fk_log == 0);
    idle_to(30 * MIN);
    CHECK(fk_cons == 1);
    flash_tidy_fill(pg);
    CHECK(u16(pg) == 0 && u16(pg + 2) == 1016u && u16(pg + 4) == HALF && u16(pg + 6) == 1 && pg[8] == 0 &&
          pg[9] == 1);

    /* Lit on USB (and on battery in Always on): at 10 min, not before. */
    reset();
    key_at(2 * MIN);
    idle_to(10 * MIN - 10u);
    CHECK(fk_cons == 0);
    idle_to(10 * MIN);
    CHECK(fk_cons == 1);
    flash_tidy_fill(pg);
    CHECK(pg[9] == 2);
    reset();
    fk_batt = true;
    fk_mode = POWER_MODE_FULL;
    key_at(3 * MIN);
    idle_to(10 * MIN);
    CHECK(fk_cons == 1);

    /* Lit on battery in a mode that goes dark: it waits for the dark. */
    for (power_mode_t m = POWER_MODE_NORMAL; m < POWER_MODE_COUNT; m++) {
        reset();
        fk_batt = true;
        fk_mode = m;
        key_at(4 * MIN + m * SEC);   /* a pause of its own: the module keeps its last try */
        idle_to(19 * MIN);
        CHECK(fk_cons == 0);
        fk_dark = true;   /* the ladder's dark stage, on the LEDs */
        fk_now += 10u;
        flash_tidy_task();
        CHECK(fk_cons == 1);
    }

    /* A failure: no retry in the same pause; the next pause tries again. */
    reset();
    fk_dark = true;
    fk_fail = true;
    key_at(5 * MIN);
    idle_to(30 * MIN);
    CHECK(fk_cons == 1 && fk_log == HALF);
    flash_tidy_fill(pg);
    CHECK(pg[8] == 1);
    fk_fail = false;
    key_at(fk_now + 1u);
    idle_to(30 * SEC);
    CHECK(fk_cons == 2 && fk_log == 0);

    /* Never with the menu open, in a wake's recovery or on the reserve; each
     * cleared, the cleanup comes in the same pause. */
    bool *blocks[] = {&fk_menu, &fk_recovering, &fk_cut};
    for (unsigned i = 0; i < sizeof blocks / sizeof blocks[0]; i++) {
        reset();
        fk_dark    = true;
        *blocks[i] = true;
        key_at(6 * MIN + i * SEC);
        idle_to(30 * MIN);
        CHECK(fk_cons == 0);
        *blocks[i] = false;
        fk_now += 10u;
        flash_tidy_task();
        CHECK(fk_cons == 1);
    }

    /* After a success the next pause tries, whatever its key's time (a
     * stored time's low 16 bits would alias 65.536 s apart: codex); after a
     * failure, a key 65.536 s on rearms it all the same. */
    reset();
    fk_dark = true;
    key_at(8 * MIN);
    idle_to(30 * SEC);
    CHECK(fk_cons == 1);
    fk_log = HALF;
    key_at(8 * MIN + 65536u);
    idle_to(30 * SEC);
    CHECK(fk_cons == 2);
    fk_fail = true;
    fk_log  = HALF;
    key_at(10 * MIN);
    idle_to(30 * SEC);
    CHECK(fk_cons == 3);
    fk_fail = false;
    idle_to(5 * MIN);
    CHECK(fk_cons == 3);
    key_at(10 * MIN + 6u * 65536u);   /* the same low 16 bits as the failed pause's */
    idle_to(30 * SEC);
    CHECK(fk_cons == 4 && fk_log == 0);

    /* A failed program empties the log: the key after it is still seen
     * (below the threshold), so a refill late in the next pause, with no
     * key since, is cleaned up (codex). */
    reset();
    fk_dark         = true;
    fk_fail         = true;
    fk_fail_empties = true;
    key_at(12 * MIN);
    idle_to(30 * SEC);
    CHECK(fk_cons == 1 && fk_log == 0);
    fk_fail = false;
    key_at(fk_now + 1u);
    idle_to(5 * MIN);
    fk_log = HALF;   /* a write in the pause: the clock's nightly save, say */
    idle_to(5 * MIN + 10u);
    CHECK(fk_cons == 2 && fk_log == 0);

    /* A key in the 30 s starts the count again. */
    reset();
    fk_dark = true;
    key_at(7 * MIN);
    idle_to(20 * SEC);
    key_at(fk_now);
    idle_to(20 * SEC);
    CHECK(fk_cons == 0);
    idle_to(30 * SEC);
    CHECK(fk_cons == 1);

    if (fails) {
        printf("flash_tidy: %d FAILED\n", fails);
        return 1;
    }
    printf("flash_tidy: all checks passed\n");
    return 0;
}
