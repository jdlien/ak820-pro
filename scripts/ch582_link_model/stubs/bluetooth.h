/* Host stand-in for QMK's drivers/bluetooth/bluetooth.h (same prototypes). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "report.h"
void    bluetooth_init(void);
void    bluetooth_task(void);
bool    bluetooth_is_connected(void);
bool    bluetooth_can_send_nkro(void);
uint8_t bluetooth_keyboard_leds(void);
void    bluetooth_send_keyboard(report_keyboard_t *report);
void    bluetooth_send_nkro(report_nkro_t *report);
void    bluetooth_send_mouse(report_mouse_t *report);
void    bluetooth_send_consumer(uint16_t usage);
void    bluetooth_send_system(uint16_t usage);
void    bluetooth_send_raw_hid(uint8_t *data, uint8_t length);
