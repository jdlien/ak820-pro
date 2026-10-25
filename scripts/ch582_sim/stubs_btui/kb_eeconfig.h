/* Host stand-in for kb_eeconfig.h: the saved BT slot, as bt_ui.c uses it. */
#pragma once
#include <stdint.h>
uint8_t kb_eeconfig_get_bt_profile(void);
void    kb_eeconfig_set_bt_profile(uint8_t p);
