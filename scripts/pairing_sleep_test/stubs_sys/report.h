#pragma once
#include <stdint.h>
typedef struct { uint8_t mods; uint8_t reserved; uint8_t keys[6]; } report_keyboard_t;
typedef struct { uint8_t report_id; uint8_t mods; uint8_t bits[30]; } report_nkro_t;
typedef struct { int dummy; } report_mouse_t;
