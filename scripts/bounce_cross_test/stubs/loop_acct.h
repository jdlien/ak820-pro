#pragma once
#include <stdbool.h>
#include <stdint.h>
extern bool loop_acct_on;
#define ACCT_NOW() ((uint16_t)0)
#define ACCT(scope, call) call
#define ACCT_CH582 0
