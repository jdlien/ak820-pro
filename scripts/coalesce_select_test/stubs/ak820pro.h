#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "quantum.h"
#include "watchdog_record.h"
bool hid_rawhid_media_within(uint32_t now, uint32_t ms);
bool hid_rawhid_clock_within(uint32_t s);
