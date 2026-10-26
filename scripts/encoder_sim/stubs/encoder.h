/* Host stand-in for quantum/encoder.h: one knob, as keyboard.json and the
 * generated info_config.h give it (B2, A10, resolution 2). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "gpio.h"
#define ENCODER_A_PINS {B2}
#define ENCODER_B_PINS {A10}
#define ENCODER_RESOLUTION 2
#define NUM_ENCODERS 1
#define NUM_ENCODERS_MAX_PER_SIDE 1
bool encoder_queue_event(uint8_t index, bool clockwise);
