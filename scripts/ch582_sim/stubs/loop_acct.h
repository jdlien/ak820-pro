/* Host stand-in for loop_acct.h: the driver's one ACCT() scope just runs, and
 * D2's profile (flash 1c) reads the harness's simulated tick through ACCT_NOW
 * under the harness's runtime flag. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#define ACCT_CH582 0
#define ACCT(scope, call) do { (void)(scope); call; } while (0)
extern bool     loop_acct_on;
uint16_t        sim_tick(void);
#define ACCT_NOW() sim_tick()
#ifndef CH_CFG_ST_FREQUENCY
#define CH_CFG_ST_FREQUENCY 187500
#endif
