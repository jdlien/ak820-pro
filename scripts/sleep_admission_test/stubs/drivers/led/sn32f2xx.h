#pragma once
#include <stdbool.h>
void sn32f2xx_sleep_enterI(void);
void sn32f2xx_sleep_exitI(void);
bool sn32f2xx_led_committed_dark(void);
void sn32f2xx_set_scan_only(bool on);
