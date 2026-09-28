#pragma once
#include <stdint.h>
#include <stdbool.h>
bool kb_eeconfig_get_batt_level(uint16_t *permille);
void kb_eeconfig_set_batt_level(uint16_t permille);
