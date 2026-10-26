/* Host stand-in for QMK's connection.h: the host switch bt_ui.c calls. */
#pragma once
typedef enum { CONNECTION_HOST_AUTO, CONNECTION_HOST_NONE, CONNECTION_HOST_USB, CONNECTION_HOST_BLUETOOTH } connection_host_t;
void connection_set_host_noeeprom(connection_host_t host);
