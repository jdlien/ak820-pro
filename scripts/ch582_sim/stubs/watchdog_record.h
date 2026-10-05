/* Host stand-in: the watchdog's operation scopes do nothing here. */
#pragma once
#include <stdint.h>
enum watchdog_site { WDT_SITE_WIRELESS = 4 };
#define WDT_SCOPE(site) (void)(site)
