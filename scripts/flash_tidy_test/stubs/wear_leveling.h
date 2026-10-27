/* flash_tidy_test's stand-in: quantum/wear_leveling/wear_leveling.h's status and
 * the board's two additions (test.c fakes). */
#pragma once
#include <stdint.h>
typedef enum wear_leveling_status_t {
    WEAR_LEVELING_FAILED,
    WEAR_LEVELING_SUCCESS,
    WEAR_LEVELING_CONSOLIDATED,
} wear_leveling_status_t;
wear_leveling_status_t wear_leveling_consolidate(void);
uint32_t               wear_leveling_log_used(void);
