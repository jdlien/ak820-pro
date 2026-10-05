/* Host stand-in for QMK's report.h: the three report types the driver names. */
#pragma once
#include <stdint.h>
typedef struct { uint8_t mods; uint8_t reserved; uint8_t keys[6]; } report_keyboard_t;
typedef struct { uint8_t report_id; uint8_t mods; uint8_t bits[30]; } report_nkro_t;
typedef struct { uint8_t buttons; int8_t x, y, v, h; } report_mouse_t;
