#pragma once
#include <stdint.h>
#include <stdbool.h>
#define COL2ROW 0
#define ROW2COL 1
#define DIODE_DIRECTION COL2ROW
#define MATRIX_ROWS 6
#define MATRIX_COLS 15
typedef uint16_t matrix_row_t;
#define MATRIX_ROW_SHIFTER ((matrix_row_t)1)
#define MATRIX_COL_PINS { A4, A5, C0, C1, C2, C3, A6, A7, C4, C5, C6, C7, C14, C8, C9 }
void matrix_read_cols_on_row(matrix_row_t current_matrix[], uint8_t current_row);
