/* QMK_KEYBOARD_H for the host test. The real LAYOUT_82_ansi is generated
 * from keyboard.json; here the layout is flattened to one row of 82 keys in
 * keymap.c's source order (15+15+15+14+13+10). */
#pragma once
#include "quantum.h"
#define MATRIX_ROWS 1
#define MATRIX_COLS 82
#define LAYOUT_82_ansi(...) { { __VA_ARGS__ } }
