/* Host stand-in for loop_acct.h: the driver's one ACCT() scope just runs. */
#pragma once
#define ACCT_CH582 0
#define ACCT(scope, call) do { (void)(scope); call; } while (0)
