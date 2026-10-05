/* Host stand-in for ChibiOS's ch.h: the 16-bit system tick at 187.5 kHz. */
#pragma once
#include <stdint.h>
#define CH_CFG_ST_FREQUENCY 187500
typedef uint16_t systime_t;
typedef uint32_t sysinterval_t;
systime_t chVTGetSystemTimeX(void);
static inline sysinterval_t chTimeDiffX(systime_t a, systime_t b) { return (sysinterval_t)(uint16_t)(b - a); }
