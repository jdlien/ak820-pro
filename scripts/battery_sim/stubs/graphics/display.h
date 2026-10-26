#pragma once
#include <stdint.h>
#include <stdbool.h>
void    display_set_alert(const char *msg);
void    display_set_param_status(const char *s);
bool    display_message_recent(uint32_t ms);
bool    display_band_busy(void);
bool    display_debug_active(void);
bool    display_panel_lit_for_owner(void);   /* Lights out's exception: Fn+D, or the menu open (S0) */
void    display_set_backlight_cap(uint8_t cap);
uint8_t display_backlight_effective(void);
uint8_t display_backlight_duty(void);
