/* The row ISR at the AK820 Pro's 9 empty matrix cells (plans/AUDIT-2026-10-31.md,
 * F-033). drivers/led/sn32f2xx.c's hardware-PWM, COL2ROW path indexed
 * led_state[] with g_led_config's NO_LED (255): 765 bytes into a 243-byte
 * array. In the firmware that lands on the raw-HID IN queue's slot 0, so the
 * last reply's bytes became a phantom colour at those cells: a dark frame
 * energised mux rows and put duty on the empty columns (no light, the row
 * transistors' base current; ~1.3 mA measured on white, 11-01).
 *
 * The real driver file is #included by path (run.sh), never edited, so the
 * test sees its statics. Built with UBSan's bounds check and no recovery:
 * the read itself fails the run. Then the effect, which UBSan cannot see:
 *   A. every LED dark: no mux row energised in a whole field;
 *   B. one LED lit on each row that has an empty cell: the row is energised,
 *      and no empty cell's column carries an enabled duty.
 * Exit 0 = pass. */
#include <stdio.h>
#include <string.h>
#include "rgb_matrix.h"

#include FW_LED_C

/* ---- recording stubs ---- */
PWMDriver    PWMD0, PWMD1, PWMD2;
struct pfpa  pfpa_regs;
EFlashDriver EFLD1 = {FLASH_READY};
static uint8_t pin_level[128];

void gpio_set_pin_output_push_pull(pin_t p) { (void)p; }
void gpio_write_pin_low(pin_t p) { pin_level[p & 127] = 0; }
void gpio_write_pin_high(pin_t p) { pin_level[p & 127] = 1; }
void gpio_set_pin_input(pin_t p) { pin_level[p & 127] = 0; }
void gpio_set_pin_input_high(pin_t p) { (void)p; }
void gpio_set_pin_input_low(pin_t p) { (void)p; }
void pwmStart(PWMDriver *d, const PWMConfig *c) { d->config = c; }
void pwmEnableChannel(PWMDriver *d, uint32_t ch, uint32_t w) { d->mr[ch] = w; d->en[ch] = 1; }
void pwmDisableChannel(PWMDriver *d, uint32_t ch) { d->en[ch] = 0; }
void pwmDisableChannelI(PWMDriver *d, uint32_t ch) { d->en[ch] = 0; }
void pwmEnablePeriodicNotification(PWMDriver *d) { (void)d; }
void pwmDisablePeriodicNotification(PWMDriver *d) { (void)d; }
void pwmEnablePeriodicNotificationI(PWMDriver *d) { (void)d; }
void pwmDisablePeriodicNotificationI(PWMDriver *d) { (void)d; }
uint32_t timer_read32(void) { return 0; }
matrix_row_t raw_matrix[MATRIX_ROWS], matrix[MATRIX_ROWS];
void matrix_read_cols_on_row(matrix_row_t m[], uint8_t r) { m[r] = 0; }

/* keyboard.json's rgb_matrix layout as QMK generates it (the board does not
 * override the weak symbol): the 9 NO_LED cells are (0,14) the knob, (3,12),
 * (4,1), (4,14) and (5,3), (5,4), (5,5), (5,7), (5,8). */
led_config_t g_led_config = {{
    { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, NO_LED },
    { 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 },
    { 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43 },
    { 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, NO_LED, 56, 57 },
    { 58, NO_LED, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, NO_LED },
    { 71, 72, 73, NO_LED, NO_LED, NO_LED, 74, NO_LED, NO_LED, 75, 76, 77, 78, 79, 80 },
}};

/* One field (18 row ISRs): the slots that energised a mux row, and the
 * enabled non-zero duties on empty cells' columns. */
static void run_field(int *energised, int *noled_duties) {
    *energised = *noled_duties = 0;
    for (int i = 0; i < SN32F2XX_RGB_MATRIX_ROWS_HW; i++) {
        PWMD1.config->callback(&PWMD1);
        for (int x = 0; x < SN32F2XX_RGB_MATRIX_ROWS_HW; x++)
            if (pin_level[led_row_pins[x] & 127]) { (*energised)++; break; }
        for (int c = 0; c < SN32F2XX_RGB_MATRIX_COLS; c++) {
            PWMDriver *d  = COL_PWM_DRV(c);
            uint8_t    ch = COL_PWM_CH(c);
            if (g_led_config.matrix_co[current_key_row][c] == NO_LED && d->en[ch] && d->mr[ch])
                (*noled_duties)++;
        }
    }
}

int main(void) {
    int fails = 0, e, n;
    sn32f2xx_init();

    sn32f2xx_set_color_all(0, 0, 0);
    sn32f2xx_flush();
    run_field(&e, &n);
    printf("A. dark frame: %d mux slots energised, %d duties on empty cells (want 0, 0)\n", e, n);
    if (e || n) fails++;

    /* Rows 0, 3, 4 and 5 have empty cells: light the LED beside each. */
    sn32f2xx_set_color(13, 255, 255, 255);   /* (0,13) */
    sn32f2xx_set_color(56, 255, 255, 255);   /* (3,13) */
    sn32f2xx_set_color(70, 255, 255, 255);   /* (4,13) */
    sn32f2xx_set_color(74, 255, 255, 255);   /* (5,6) */
    sn32f2xx_flush();
    run_field(&e, &n);
    printf("B. lit on rows 0, 3, 4, 5: %d mux slots energised, %d duties on empty cells (want 12, 0)\n", e, n);
    if (e != 12 || n) fails++;

    printf("%s\n", fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}
