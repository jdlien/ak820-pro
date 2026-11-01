/* Stub quantum.h for the host test: only what keymaps/via/keymap.c and the
 * real ak820pro.h need. Real QMK headers supply keycodes and keymap_config. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "progmem.h"
#include "keycodes.h"
#include "quantum_keycodes.h"
#include "keycode_config.h"
#include "action.h"
#include "dip_switch.h"
void set_single_persistent_default_layer(uint8_t default_layer);
void host_consumer_send(uint16_t usage);
bool process_record_user(uint16_t keycode, keyrecord_t *record);
bool process_magic(uint16_t keycode, keyrecord_t *record);
