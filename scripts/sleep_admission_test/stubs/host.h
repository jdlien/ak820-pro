#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "report.h"
typedef struct { uint8_t (*keyboard_leds)(void); } host_driver_t;
void host_set_driver(host_driver_t *d);
void host_raw_hid_send(uint8_t *data, uint8_t length);
bool host_can_send_nkro(void);
