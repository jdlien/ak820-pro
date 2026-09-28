#pragma once
#include <stdint.h>
#include <stdbool.h>
uint8_t  ch582_get_battery(void);
uint32_t ch582_battery_age_ms(void);
uint16_t ch582_battery_reports(void);
bool     ch582_is_usb(void);
bool     ch582_is_connected(void);
