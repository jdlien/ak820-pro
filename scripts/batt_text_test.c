/* The battery readout's text (P4, plans/CONFIG-MENU-P1-DESIGN.md): the
 * firmware's graphics/batt_text.c, verbatim, over the design's table.
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -I $D/graphics scripts/batt_text_test.c $D/graphics/batt_text.c -o bt && ./bt
 */
#include <stdio.h>
#include <string.h>

#include "batt_text.h"

static int fails;

static void want(const char *exp, uint8_t pct, bool on_batt, uint16_t left, bool ready, bool hours) {
    char out[BATT_TEXT_MAX + 1];
    memset(out, 'x', sizeof out);
    batt_level_text(out, pct, on_batt, left, ready, hours);
    if (strcmp(out, exp) != 0 || strlen(out) > BATT_TEXT_MAX) {
        printf("FAIL pct %u batt %d left %u ready %d hours %d: \"%s\", wanted \"%s\"\n", pct, on_batt, left, ready, hours,
               out, exp);
        fails++;
    }
}

int main(void) {
    const uint16_t NONE = 0xFFFFu;
    /* Percent: today's rules. */
    want("85%", 85, true, 9600, true, false);    /* 160 h: the percent alone */
    want("85%", 85, true, 600, true, false);     /* 10 h: not under 10 */
    want("18% 9h", 18, true, 599, true, false);  /* under 10 h: rounded down */
    want("18% 6h", 18, true, 380, true, false);
    want("2% 1h", 2, true, 60, true, false);
    want("2% <1h", 2, true, 59, true, false);
    want("2% <1h", 2, true, 0, true, false);
    want("18%", 18, true, 380, false, false);    /* no mature average */
    want("18%", 18, false, 380, true, false);    /* not on battery */
    want("18%", 18, true, NONE, true, false);    /* no estimate */
    want("100%", 100, true, NONE, false, false);
    want("100% 9h", 100, true, 540, true, false);   /* seven cells, the slot's most */
    want("100% <1", 100, true, 30, true, false);    /* eight cut to seven, as before P4 */
    /* Hours (JD, 10-25): "160h" all the time on battery. */
    want("160h", 85, true, 9600, true, true);
    want("160h", 85, true, 9659, true, true);       /* rounded down */
    want("10h", 40, true, 600, true, true);
    want("6h", 18, true, 380, true, true);          /* under 10 h: the hours alone */
    want("1h", 2, true, 60, true, true);
    want("<1h", 2, true, 59, true, true);
    want("<1h", 1, true, 0, true, true);
    want("1092h", 100, true, 0xFFFEu, true, true);  /* the estimate's ceiling: five cells */
    /* Hours, no estimate yet: the percent. */
    want("85%", 85, true, 9600, false, true);       /* the first hour after a boot */
    want("85%", 85, true, NONE, true, true);
    want("85%", 85, false, 9600, true, true);       /* USB: draw_battery() shows "USB" before this */
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("batt_text: all checks passed\n");
    return 0;
}
