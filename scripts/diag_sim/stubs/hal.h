/* Host stand-in for ChibiOS's hal.h: the ST counter loop_acct.h reads inline
 * (st_lld_get_counter, a static inline in the SN32 port; sim.c supplies it). */
#pragma once
#include "ch.h"
systime_t st_lld_get_counter(void);
