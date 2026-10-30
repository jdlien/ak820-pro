/* The battery readout's text (P4, plans/CONFIG-MENU-P1-DESIGN.md; Both, JD
 * 10-26; Icon only, 10-30): the firmware's graphics/batt_text.c, verbatim, over the design's
 * table.
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -I $D/graphics scripts/batt_text_test.c $D/graphics/batt_text.c -o bt && ./bt
 */
#include <stdio.h>
#include <string.h>

#include "batt_text.h"

static int fails;

enum { P = BATT_VIEW_PERCENT, H = BATT_VIEW_HOURS, B = BATT_VIEW_BOTH, I = BATT_VIEW_ICON };

static void want(const char *exp, uint8_t pct, bool on_batt, uint16_t left, bool ready, uint8_t view) {
    char out[BATT_TEXT_MAX + 1];
    memset(out, 'x', sizeof out);
    batt_level_text(out, pct, on_batt, left, ready, view);
    if (strcmp(out, exp) != 0 || strlen(out) > BATT_TEXT_MAX) {
        printf("FAIL pct %u batt %d left %u ready %d view %u: \"%s\", wanted \"%s\"\n", pct, on_batt, left, ready, view,
               out, exp);
        fails++;
    }
}

int main(void) {
    const uint16_t NONE = 0xFFFFu;
    /* Percent: today's rules. */
    want("85%", 85, true, 9600, true, P);    /* 160 h: the percent alone */
    want("85%", 85, true, 600, true, P);     /* 10 h: not under 10 */
    want("18% 9h", 18, true, 599, true, P);  /* under 10 h: rounded down */
    want("18% 6h", 18, true, 380, true, P);
    want("2% 1h", 2, true, 60, true, P);
    want("2% <1h", 2, true, 59, true, P);
    want("2% <1h", 2, true, 0, true, P);
    want("18%", 18, true, 380, false, P);    /* no mature average */
    want("18%", 18, false, 380, true, P);    /* not on battery */
    want("18%", 18, true, NONE, true, P);    /* no estimate */
    want("100%", 100, true, NONE, false, P);
    want("100% 9h", 100, true, 540, true, P);   /* seven cells, the slot's most at full spacing */
    want("100% <1h", 100, true, 30, true, P);   /* eight, its space closed up (it was cut to "100% <1" before Both) */
    want("85%", 85, true, 9600, true, 0);       /* unset or garbage: percent */
    want("18% 6h", 18, true, 380, true, 7);
    /* Hours (JD, 10-25): "160h" all the time on battery. */
    want("160h", 85, true, 9600, true, H);
    want("160h", 85, true, 9659, true, H);       /* rounded down */
    want("10h", 40, true, 600, true, H);
    want("6h", 18, true, 380, true, H);          /* under 10 h: the hours alone */
    want("1h", 2, true, 60, true, H);
    want("<1h", 2, true, 59, true, H);
    want("<1h", 1, true, 0, true, H);
    want("999h", 100, true, 0xFFFEu, true, H);   /* the estimate's ceiling, 1092 h, shown as three digits */
    want("999h", 100, true, 60000u, true, H);
    want("998h", 100, true, 59880u, true, H);
    /* Hours, no estimate yet: the percent. */
    want("85%", 85, true, 9600, false, H);       /* the first hour after a boot */
    want("85%", 85, true, NONE, true, H);
    want("85%", 85, false, 9600, true, H);       /* USB: draw_battery() shows "USB" before this */
    /* Both (JD, 10-26): the level and the hours, all the time on battery. */
    want("85% 160h", 85, true, 9600, true, B);   /* eight cells: draw_battery() closes the space */
    want("99% 160h", 99, true, 9659, true, B);
    want("62% 31h", 62, true, 1860, true, B);
    want("18% 6h", 18, true, 380, true, B);
    want("2% <1h", 2, true, 59, true, B);
    want("100% 51h", 100, true, 3060, true, B);
    want("100% 99h", 100, true, 5999, true, B);
    want("100%", 100, true, 6000, true, B);      /* "100% 100h" is nine: the level alone (JD) */
    want("100%", 100, true, 9600, true, B);
    want("99% 999h", 99, true, 0xFFFEu, true, B);
    want("5% 999h", 5, true, 60000u, true, B);
    want("85%", 85, true, 9600, false, B);       /* no estimate yet: the percent */
    want("85%", 85, true, NONE, true, B);
    want("85%", 85, false, 9600, true, B);
    /* Icon only (10-30): nothing, ready or not, under 10 h, on USB. */
    want("", 85, true, 9600, true, I);
    want("", 18, true, 380, true, I);
    want("", 2, true, 59, true, I);
    want("", 85, true, NONE, false, I);
    want("", 100, false, 9600, true, I);
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("batt_text: all checks passed\n");
    return 0;
}
