#pragma once
#include <stdint.h>
void    display_set_alert(const char *msg);
void    display_set_backlight_cap(uint8_t cap);
uint8_t display_backlight_effective(void);
