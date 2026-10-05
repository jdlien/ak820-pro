/* Phase 1b, B2: the charging model's tail through battery.c's OWN lookup, for
 * one generated battery_tail.h (plans/BATTERY-GAUGE-REFINE-PLAN.md, "The tail's
 * shape over B1's whole grid", the firmware path). tail_fw_grid.py builds this
 * once per grid point and checks what it prints against tail_grid.py's
 * construction, which is the specification.
 *
 * battery.c is #included VERBATIM, so its static tail_x16(), tail_entry_s(),
 * model_start() and model_advance() are the ones called; the stubs below only
 * satisfy the linker, and none of them is reached by those functions.
 *
 * Output, one line each:
 *   P <BATT_TAIL_N> <BATT_T_TAIL_S> <K_CC> <L_KNEE> <table[N]>
 *   X <tail_x16(s) for s = 0 .. T_TAIL + 3600>
 *   E <tail_entry_s(l0) for l0 = L_KNEE .. 989>
 *   R <l0> <M for s = 0 .. secs>     for each "l0:secs" argument: model_start(l0),
 *                                    then M after each model_advance() */
#include "battery.c"

#include <stdio.h>
#include <stdlib.h>

struct fake_adc fake_adc;
uint32_t timer_read32(void) { return 0; }
uint32_t timer_elapsed32(uint32_t last) { (void)last; return 0; }
bool     gpio_read_pin(int pin) { (void)pin; return true; }
bool     rgb_matrix_is_enabled(void) { return true; }
uint32_t sn32f2xx_led_load(void) { return 0; }
bool     kb_eeconfig_get_batt_level(uint16_t *permille) { (void)permille; return false; }
void     kb_eeconfig_set_batt_level(uint16_t permille) { (void)permille; }
uint32_t ch582_battery_age_ms(void) { return UINT32_MAX; }
bool     ch582_is_usb(void) { return false; }
bool     ch582_is_connected(void) { return false; }
void     display_set_alert(const char *msg) { (void)msg; }
uint8_t  display_backlight_effective(void) { return 0; }
void     power_set_lights_cut(bool cut) { (void)cut; }
bool     power_lights_cut(void) { return false; }

int main(int argc, char **argv) {
    printf("P %u %u %u %u %u\n", (unsigned)BATT_TAIL_N, (unsigned)BATT_T_TAIL_S, (unsigned)BATT_K_CC_PM_PER_H,
           (unsigned)BATT_L_KNEE_PM, (unsigned)batt_tail_x16[BATT_TAIL_N]);
    printf("X");
    for (uint32_t s = 0; s <= BATT_T_TAIL_S + 3600u; s++) printf(" %u", (unsigned)tail_x16(s));
    printf("\nE");
    for (uint32_t l0 = BATT_L_KNEE_PM; l0 < 990u; l0++) printf(" %u", (unsigned)tail_entry_s((uint16_t)l0));
    printf("\n");
    for (int a = 1; a < argc; a++) {
        unsigned l0 = 0, secs = 0;
        if (sscanf(argv[a], "%u:%u", &l0, &secs) != 2) return 2;
        model_start((uint16_t)l0);
        printf("R %u %u", l0, (unsigned)m_pm);
        for (unsigned s = 1; s <= secs; s++) {
            model_advance();
            printf(" %u", (unsigned)m_pm);
        }
        printf("\n");
    }
    return 0;
}
