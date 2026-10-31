#pragma once
typedef enum { CONNECTION_HOST_AUTO = 0, CONNECTION_HOST_NONE, CONNECTION_HOST_USB, CONNECTION_HOST_BLUETOOTH, CONNECTION_HOST_2P4GHZ } connection_host_t;
void connection_set_host_noeeprom(connection_host_t host);
