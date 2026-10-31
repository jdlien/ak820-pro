/* Stand-ins for what ak820pro.c's usb_wakeup_try() block touches. Field types
 * and enum values from lib/chibios/os/hal/include/hal_usb.h (usbstate_t) and
 * the SN32 LLD's USBDriver (status: uint16_t); the host enum from
 * quantum/connection/connection.h. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "timer.h"   /* the real platforms/timer.h */

typedef enum {
  USB_UNINIT = 0, USB_STOP = 1, USB_READY = 2, USB_SELECTED = 3,
  USB_ACTIVE = 4, USB_SUSPENDED = 5
} usbstate_t;
typedef struct { usbstate_t state; uint16_t status; } USBDriver;
extern USBDriver USBD1;
#define USB_DRIVER USBD1          /* tmk_core/protocol/chibios/usb_main.h */
void usbWakeupHost(USBDriver *usbp);

typedef enum {
    CONNECTION_HOST_AUTO,
    CONNECTION_HOST_NONE,
    CONNECTION_HOST_USB,
    CONNECTION_HOST_BLUETOOTH,
    CONNECTION_HOST_2P4GHZ
} connection_host_t;
connection_host_t connection_get_host(void);
