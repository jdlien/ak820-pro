/* The song text's budgets and cut, per face (plans/MENU-8X16-PLAN.md, B6):
 * the firmware's graphics/text_fit.c, verbatim. The drawing itself has no
 * host harness (display.c and lcd_bus.c); B8 checks it on the board.
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -fsanitize=address,undefined -I $D/graphics \
 *       scripts/text_fit_test.c $D/graphics/text_fit.c -o tf && ./tf
 */
#include <stdio.h>
#include <string.h>

#include "text_fit.h"

static int fails;

enum { L = TEXT_FACE_LARGE, S = TEXT_FACE_SMALL, R = TEXT_FACE_REGULAR };

/* The host's longest lines (ak820text.py's MAXLEN): 19 for line 0, 21 for 1. */
static const char *const ARTIST19 = "ABCDEFGHIJKLMNOPQRS";
static const char *const TITLE21  = "abcdefghijklmnopqrstu";

static void want(uint8_t exp, uint8_t face, uint8_t line, const char *s, const char *what) {
    uint8_t got = text_fit_len(face, line, s);
    if (got != exp) {
        printf("FAIL %s: face %u line %u \"%s\": %u, wanted %u\n", what, face, line, s ? s : "(null)", got, exp);
        fails++;
    }
}

/* A line of n characters. */
static const char *of(uint8_t n) {
    static char buf[32];
    memset(buf, 'x', n);
    buf[n] = '\0';
    return buf;
}

int main(void) {
    /* 10-28: Regular, the third face, Large's cell and so its budgets. */
    if (text_fit_budget(R, 0) != text_fit_budget(L, 0) || text_fit_budget(R, 1) != text_fit_budget(L, 1)) {
        printf("FAIL Regular's budgets are not Large's\n");
        fails++;
    }
    want(14, R, 0, ARTIST19, "Regular cuts line 0 as Large");
    want(15, R, 1, TITLE21, "Regular cuts line 1 as Large");
    /* The budgets, as display.c derives them from x and the advance. */
    if (text_fit_budget(S, 0) != 19 || text_fit_budget(S, 1) != 21 || text_fit_budget(L, 0) != 14 ||
        text_fit_budget(L, 1) != 15) {
        printf("FAIL the budgets: Small %u/%u, Large %u/%u\n", text_fit_budget(S, 0), text_fit_budget(S, 1),
               text_fit_budget(L, 0), text_fit_budget(L, 1));
        fails++;
    }

    /* Each line at each face's budget: under, exactly at, one over. */
    for (uint8_t face = 0; face < 2; face++)
        for (uint8_t line = 0; line < 2; line++) {
            uint8_t b = text_fit_budget(face, line);
            want((uint8_t)(b - 1), face, line, of((uint8_t)(b - 1)), "one under");
            want(b, face, line, of(b), "exactly at");
            want(b, face, line, of((uint8_t)(b + 1)), "one over");
            want(b, face, line, of(30), "far over");
            want(0, face, line, "", "empty");
            want(1, face, line, "x", "one character");
        }

    /* The host's longest lines: Small shows them whole, Large cuts them. */
    want(19, S, 0, ARTIST19, "Small, the artist whole");
    want(21, S, 1, TITLE21, "Small, the title whole");
    want(14, L, 0, ARTIST19, "Large, the artist cut");
    want(15, L, 1, TITLE21, "Large, the title cut");

    /* A single line is line 0, beside the icon: its budget, title or not.
     * (12 or more characters; 11 or fewer take the 20 px face, which the
     * helper isn't asked about.) */
    want(12, L, 0, "Bohemian Rha", "Large, a single line of 12");
    want(14, L, 0, "Bohemian Rhapsody", "Large, a single line of 17, cut");
    want(17, S, 0, "Bohemian Rhapsody", "Small, a single line of 17");
    want(19, S, 0, TITLE21, "Small, line 0's budget even past the host's");

    /* The same text both ways round: a change of face shows more or less of
     * it, from the same buffer. */
    want(19, S, 0, ARTIST19, "Small after Large");
    want(14, L, 0, ARTIST19, "Large after Small");

    /* Anything but Small is Large, as kb_eeconfig reads garbage; a third line
     * and NULL fit nothing. */
    want(14, 7, 0, ARTIST19, "an unknown face reads Large");
    want(15, 0xFF, 1, TITLE21, "an unknown face reads Large, line 1");
    want(0, S, 2, TITLE21, "line 2");
    want(0, L, 0xFF, TITLE21, "line 255");
    want(0, L, 0, NULL, "NULL");
    if (text_fit_budget(S, 2) != 0 || text_fit_budget(L, 2) != 0) {
        printf("FAIL line 2's budget\n");
        fails++;
    }

    /* Never reads past the budget: a run of exactly 14 with no NUL after it
     * (the sanitizer catches a read past the array). */
    {
        char run[14];
        memset(run, 'y', sizeof run);
        if (text_fit_len(L, 0, run) != 14) {
            printf("FAIL an unterminated run of the budget\n");
            fails++;
        }
    }

    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("text_fit: all checks passed\n");
    return 0;
}
