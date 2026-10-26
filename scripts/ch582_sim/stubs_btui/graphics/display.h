/* Host stand-in for graphics/display.h: the four calls bt_ui.c makes. */
#pragma once
#include <stdint.h>
void display_draw_bluetooth_logo(void);
void display_draw_2_4_g_logo(void);
void display_draw_usb_logo(void);
void display_set_pair_hint(int16_t pct);
