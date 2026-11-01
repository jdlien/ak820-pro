/* The hidapi calls ak820ctl.c makes, for scripts/flash_channel_test: test.c
 * implements them as a device whose raw-HID handler is the firmware's
 * extracted flash channel. */
#pragma once
#include <stddef.h>
#include <wchar.h>

typedef struct hid_device_ hid_device;
struct hid_device_info {
    char                   *path;
    unsigned short          vendor_id, product_id;
    unsigned short          usage_page, usage;
    int                     interface_number;
    struct hid_device_info *next;
};

int                     hid_init(void);
int                     hid_exit(void);
struct hid_device_info *hid_enumerate(unsigned short vendor_id, unsigned short product_id);
void                    hid_free_enumeration(struct hid_device_info *devs);
hid_device             *hid_open_path(const char *path);
int                     hid_write(hid_device *dev, const unsigned char *data, size_t length);
int                     hid_read_timeout(hid_device *dev, unsigned char *data, size_t length, int milliseconds);
const wchar_t          *hid_error(hid_device *dev);
void                    hid_close(hid_device *dev);
