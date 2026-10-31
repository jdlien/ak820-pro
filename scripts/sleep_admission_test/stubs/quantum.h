#pragma once
#include "fw_hal_stub.h"
#include "report.h"
#include "host.h"
#ifndef ARRAY_SIZE
#    define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#endif
#define MATRIX_ROWS 6
#define MATRIX_COLS 15
typedef uint16_t matrix_row_t;
matrix_row_t matrix_get_row(uint8_t row);
#define MATRIX_ROW_PINS { B14, B15, B19, D19, A19, A18 }
#define MATRIX_COL_PINS { A4, A5, C0, C1, C2, C3, A6, A7, C4, C5, C6, C7, C14, C8, C9 }
#define ENCODER_A_PINS { B2 }
#define ENCODER_B_PINS { A10 }
#define CHARGE_CHRG_PIN B16
#define CH582_SERIAL_DRIVER SD2
uint16_t timer_read(void);
uint32_t timer_read32(void);
uint16_t timer_elapsed(uint16_t last);
uint32_t timer_elapsed32(uint32_t last);
void     wait_ms(uint32_t ms);
uint32_t last_encoder_activity_time(void);
