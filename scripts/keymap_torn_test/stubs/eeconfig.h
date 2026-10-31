/* Host stub for quantum/eeconfig.h: its size defaults only (the real one pulls
 * in action_layer.h -> keyboard.h). The board sets EECONFIG_KB_DATA_SIZE 10. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#ifndef EECONFIG_KB_DATA_SIZE
#    define EECONFIG_KB_DATA_SIZE 0
#endif
#ifndef EECONFIG_USER_DATA_SIZE
#    define EECONFIG_USER_DATA_SIZE 0
#endif
