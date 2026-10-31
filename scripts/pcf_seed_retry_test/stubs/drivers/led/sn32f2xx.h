/* Host stand-in for drivers/led/sn32f2xx.h: the one call rtc.c makes. */
#pragma once
#include <stdbool.h>
bool sn32f2xx_led_committed_dark(void);
