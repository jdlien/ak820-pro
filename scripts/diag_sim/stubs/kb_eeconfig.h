/* Host stand-in for kb_eeconfig.h: the RTC period's accessors (sim.c). */
#pragma once
#include <stdint.h>
uint16_t kb_eeconfig_get_rtc_period(void);
void     kb_eeconfig_set_rtc_period(uint16_t period);
