/* Host stand-in for the board's ak820pro.h: only the raw-HID leases the
 * driver's dev build asks (hid_protocol.c's, simulated in sim.c). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "quantum.h"
#include "watchdog_record.h"
bool hid_rawhid_media_within(uint32_t now, uint32_t ms);
bool hid_rawhid_clock_within(uint32_t s);
