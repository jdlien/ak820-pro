/* Host stand-in for QMK's quantum.h, enough for consumer_mod.c. Everything it
 * pulls in is QMK's REAL header (keycodes, LSA(), IS_QK_MODS, the action and
 * action_util APIs, keyrecord_t); only wait_ms is declared by hand because
 * platforms/wait.h drags in ChibiOS. The two timing constants come from the
 * board's config.h via -D in build.sh. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "keycodes.h"
#include "quantum_keycodes.h"
#include "modifiers.h"
#include "action.h"
#include "action_util.h"
#include "timer.h"
void wait_ms(uint32_t ms);
#ifndef MODIFIED_CONSUMER_GAP_MS
#error "MODIFIED_CONSUMER_GAP_MS must come from config.h (build.sh)"
#endif
#ifndef MODIFIED_CONSUMER_HOLD_MS
#error "MODIFIED_CONSUMER_HOLD_MS must come from config.h (build.sh)"
#endif
