/* The knob's decoder, drivers/encoder/encoder_quadrature.c compiled VERBATIM
 * on stubs/, driven by a model knob (JD, 10-25: "the first click in any
 * direction doesn't move the menu ... If I reverse direction, the same thing",
 * gone after a reboot).
 *
 * The model: a position in transitions, its pins in Gray order (00, 01, 11,
 * 10), resting at 00 and 11 (two transitions a detent, resolution 2). Every
 * transition is sampled, as the main loop's scan does at a hand's speed,
 * unless a case skips one.
 *
 * Built twice by run.sh: with ENCODER_REST_PINS_EQUAL (the board's config.h),
 * where every case must hold; and without it, where the decoder begun half a
 * detent off must show JD's symptom -- the evidence for the cause. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "encoder.h"

void encoder_driver_init(void);
void encoder_driver_task(void);

static int  up, down, failures;
static int  pos;   /* transitions */
static void (*on_event)(bool);
bool        encoder_queue_event(uint8_t index, bool clockwise) {
    (void)index;
    clockwise ? up++ : down++;   /* the LUT counts 00 -> 01 down: "clockwise" is the position rising */
    if (on_event) on_event(clockwise);
    return true;
}
static uint8_t pins(int p) {
    static const uint8_t gray[4] = {0, 1, 3, 2};   /* A bit 0, B bit 1 */
    return gray[((p % 4) + 4) % 4];
}
static uint8_t pin_state;
void gpio_set_pin_input_high(pin_t pin) { (void)pin; }
bool gpio_read_pin(pin_t pin) { return pin == B2 ? (pin_state & 1) : (pin_state >> 1) & 1; }
void wait_us(uint32_t us) { (void)us; }

#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("  FAIL line %d: ", __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

static void sample(void) {
    pin_state = pins(pos);
    encoder_driver_task();
}
static void step(int d) {   /* one transition, sampled */
    pos += d;
    sample();
}
/* One detent: two transitions; the event, if any, must come with the second
 * (the knob settling), never with the first. */
static int detent(int d) {
    int u = up, w = down;
    step(d);
    int mid = (up - u) + (down - w);
    step(d);
#ifdef ENCODER_REST_PINS_EQUAL
    CHECK(mid == 0, "an event mid-detent (codex: the check let one through)");
#else
    (void)mid;   /* begun off, without the rule, events come mid-detent: part of the symptom */
#endif
    return d > 0 ? up - u : down - w;
}
static void boot(int at, int read_as) {   /* the knob at `at`; the init reads `read_as` */
    pos       = at;
    pin_state = pins(read_as);
    up = down = 0;
    encoder_driver_init();
    sample();   /* the first scan reads the true pins */
}

#ifdef ENCODER_REST_PINS_EQUAL
static void expect_all(void) {
    /* A clean boot: every detent one event, each way, reversals included. */
    boot(0, 0);
    for (int i = 0; i < 5; i++) CHECK(detent(+1) == 1, "up %d", i);
    for (int i = 0; i < 5; i++) CHECK(detent(-1) == 1, "down %d", i);
    for (int i = 0; i < 10; i++) CHECK(detent(i & 1 ? -1 : +1) == 1, "alternating %d", i);
    CHECK(up == 10 && down == 10, "clean: %d up, %d down", up, down);

    /* JD's case: the init read the pins mid-change (01 with the knob at 00).
     * The lone transition into the rest emits nothing, and every detent after
     * it, reversals included, is one event. */
    for (int k = 0; k < 2; k++) {
        boot(0, k ? -1 : 1);
        CHECK(up + down == 0, "the init's lone transition: %d events", up + down);
        for (int i = 0; i < 12; i++) CHECK(detent(i % 3 == 2 ? -1 : +1) == 1, "begun off (%d), detent %d", k, i);
        CHECK(detent(-1) == 1 && detent(+1) == 1 && detent(-1) == 1, "begun off (%d): reversals", k);
    }

    /* A wiggle at rest, and half a detent and back: nothing. Then a detent. */
    boot(2, 2);
    for (int i = 0; i < 6; i++) step(i & 1 ? -1 : +1);
    CHECK(up + down == 0, "a wiggle: %d", up + down);
    step(+1);
    step(-1);
    step(-1);
    step(+1);
    CHECK(up + down == 0, "half a detent each way: %d", up + down);
    CHECK(detent(+1) == 1 && detent(-1) == 1, "then a detent each way");

    /* A fast turn whose middle state the scan missed: that detent is lost (as
     * before), and the next ones are whole (no offset left). */
    boot(0, 0);
    pos += 2;
    sample();
    CHECK(up + down == 0, "a skipped middle: lost");
    CHECK(detent(+1) == 1 && detent(-1) == 1 && detent(-1) == 1, "and whole after it");
}
#else
static void expect_symptom(void) {
    /* Without the rest rule, begun half a detent off: the first detent after
     * each reversal emits nothing. */
    boot(0, 1);
    int got = 0;
    for (int i = 0; i < 3; i++) got += detent(+1);
    int lost_rev = detent(-1) == 0;
    got += detent(-1) + detent(-1);
    int lost_rev2 = detent(+1) == 0;
    CHECK(lost_rev && lost_rev2, "the symptom: a reversal's first detent lost (%d, %d)", lost_rev, lost_rev2);
    /* And clean, without it, nothing is lost: the offset is the cause. */
    boot(0, 0);
    int all = 1;
    for (int i = 0; i < 10; i++) all &= detent(i & 1 ? -1 : +1) == 1;
    CHECK(all, "clean without the rule: every detent");
    (void)got;
}
#endif

int main(void) {
#ifdef ENCODER_REST_PINS_EQUAL
    expect_all();
    printf("%s encoder: the rest rule (ENCODER_REST_PINS_EQUAL)\n", failures ? "FAIL" : "ok  ");
#else
    expect_symptom();
    printf("%s encoder: without the rule, the half-detent offset loses each reversal's first detent\n",
           failures ? "FAIL" : "ok  ");
#endif
    return failures ? 1 : 0;
}
