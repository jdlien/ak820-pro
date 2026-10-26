/* Host test for keyboards/a_jazz/ak820pro/rgb_speed.c, the RGB effects'
 * speed curves (JD, 10-25). Build and run, mingw64's gcc first on PATH:
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -I $D scripts/rgb_speed_test.c $D/rgb_speed.c -o rst && ./rst */
#include <math.h>
#include <stdio.h>

#include "rgb_speed.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* A hue cycle's length in seconds, and a drop's interval: 2^32 / rate ms and
 * 2^24 / rate ms. */
static double cycle_s(const rgb_speed_curve_t *c, int s) { return 4294967296.0 / rgb_speed_rate(c, (uint8_t)s) / 1000.0; }
static double drop_s(int s) { return 16777216.0 / rgb_speed_rate(&RGB_SPEED_JELLYBEAN, (uint8_t)s) / 1000.0; }
static int near(double v, double want, double tol) { return fabs(v - want) <= want * tol; }

/* Each curve: monotonic, and every step of 1 the same ratio, within 0.5%. */
static void curve_ok(const rgb_speed_curve_t *c, double ratio) {
    double step = pow(ratio, 1.0 / 255.0);
    for (int s = 1; s < 256; s++) {
        uint32_t a = rgb_speed_rate(c, (uint8_t)(s - 1)), b = rgb_speed_rate(c, (uint8_t)s);
        CHECK(b >= a);
        if (s % 3 == 0) {   /* the 8.8 octaves move in steps of ~6/256, so compare across three */
            double r = (double)rgb_speed_rate(c, (uint8_t)s) / rgb_speed_rate(c, (uint8_t)(s - 3));
            CHECK(near(r, step * step * step, 0.005));
        }
    }
}

int main(void) {
    /* Cycle All: 10 min at 0, 10 s at 255; the menu's 1% (speed 3) ~9.5 min,
     * 50% (128) ~77 s; upstream's were 65 s, 2 s and 1 s. */
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_ALL, 0), 600.0, 0.002));
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_ALL, 255), 10.0, 0.005));
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_ALL, 3), 572.0, 0.01));
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_ALL, 128), 77.0, 0.01));
    curve_ok(&RGB_SPEED_CYCLE_ALL, 60.0);
    /* Cycle L-R and U-D: 2 min to 2 s. */
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_SWEEP, 0), 120.0, 0.002));
    CHECK(near(cycle_s(&RGB_SPEED_CYCLE_SWEEP, 255), 2.0, 0.005));
    curve_ok(&RGB_SPEED_CYCLE_SWEEP, 60.0);
    /* Jellybean: a drop every 2 s to 30 a second. */
    CHECK(near(drop_s(0), 2.0, 0.002));
    CHECK(near(1.0 / drop_s(255), 30.0, 0.005));
    curve_ok(&RGB_SPEED_JELLYBEAN, 60.0);

    /* The phase: 64-bit, so no overflow at the timer's top; a hue cycle at
     * speed 0 wraps the low byte once in its 10 minutes. */
    uint32_t r = rgb_speed_rate(&RGB_SPEED_CYCLE_SWEEP, 255);
    CHECK(rgb_speed_phase(0xFFFFFFFFu, r) == (uint32_t)(((uint64_t)0xFFFFFFFFu * r) >> 24));
    r = rgb_speed_rate(&RGB_SPEED_CYCLE_ALL, 0);
    CHECK((uint8_t)rgb_speed_phase(0, r) == 0 && rgb_speed_phase(600000u, r) >= 255u && rgb_speed_phase(600000u, r) <= 256u);
    /* At 60 frames a second, Jellybean's count moves at most once a frame
     * (the hook keeps only its low byte). */
    r = rgb_speed_rate(&RGB_SPEED_JELLYBEAN, 255);
    for (uint32_t ms = 0; ms < 100000u; ms += 16u) CHECK(rgb_speed_phase(ms + 16u, r) - rgb_speed_phase(ms, r) <= 1u);

    printf("Cycle All %.0f s / %.0f s / %.1f s; L-R, U-D %.0f s / %.1f s; Jellybean %.2f s / %.0f a second\n",
           cycle_s(&RGB_SPEED_CYCLE_ALL, 0), cycle_s(&RGB_SPEED_CYCLE_ALL, 128), cycle_s(&RGB_SPEED_CYCLE_ALL, 255),
           cycle_s(&RGB_SPEED_CYCLE_SWEEP, 0), cycle_s(&RGB_SPEED_CYCLE_SWEEP, 255), drop_s(0), 1.0 / drop_s(255));
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("rgb_speed: all checks passed\n");
    return 0;
}
