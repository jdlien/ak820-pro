/* Host stub of the SN32F2xx HAL/CMSIS surface sleep.c touches. Registers are
 * plain structs the test can drive (FRMNO, the USB frame number). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "ch.h"
typedef struct { volatile uint32_t FRMNO, CFG; } host_usb_t;
typedef struct { volatile uint32_t LS, CTRL, RB; } host_uart_t;
typedef struct { volatile uint32_t STAT, DMACTRL; } host_spi_t;
typedef struct { volatile uint32_t CFG, FEED; } host_wdt_t;
typedef struct { volatile uint32_t RIS, IC; } host_rtc_t;
typedef struct { volatile uint32_t ISER[1], ICER[1], ICPR[1]; } host_nvic_t;
typedef struct { volatile uint32_t ADM; } host_adc_t;
typedef struct { volatile uint32_t CTRL; } host_systick_t;
typedef struct { volatile uint32_t ICSR; } host_scb_t;
typedef struct { struct { volatile uint32_t TMRCTRL; } config; } host_ct16_t;
typedef struct { volatile uint32_t IS, IBS, IEV, IC, IE, DATA, RIS; } host_gpio_t;
typedef struct { volatile uint32_t CLKCFG, PLLCTRL, CSST; } host_sys0_t;
typedef struct { volatile uint32_t LPCTRL; } host_flash_t;
typedef struct { volatile uint32_t CTRL; } host_pmu_t;
extern host_usb_t host_usb; extern host_uart_t host_uart2; extern host_spi_t host_spi0, host_spi1;
extern host_wdt_t host_wdt; extern host_rtc_t host_rtc; extern host_nvic_t host_nvic; extern host_adc_t host_adc;
extern host_systick_t host_systick; extern host_scb_t host_scb; extern host_ct16_t host_ct16b5;
extern host_gpio_t host_gpio0, host_gpio1, host_gpio2; extern host_sys0_t host_sys0; extern host_flash_t host_flash;
extern host_pmu_t host_pmu;
#define SN_USB   (&host_usb)
#define SN_UART2 (&host_uart2)
#define SN_SPI0  (&host_spi0)
#define SN_SPI1  (&host_spi1)
#define SN_WDT   (&host_wdt)
#define SN_RTC   (&host_rtc)
#define NVIC     (&host_nvic)
#define SN_ADC   (&host_adc)
#define SysTick  (&host_systick)
#define SCB      (&host_scb)
#define SN32_ST_TIM (&host_ct16b5)
#define SN_GPIO0 (&host_gpio0)
#define SN_GPIO1 (&host_gpio1)
#define SN_GPIO2 (&host_gpio2)
#define SN_SYS0  (&host_sys0)
#define SN_FLASH (&host_flash)
#define SN_PMU   (&host_pmu)
#define mskRTC_SECIF (1u << 0)
#define mskRTC_SECIC (1u << 0)
#define mskWDT_WDKEY (0x5AFAu << 16)
#define mskWDT_FV    0x55AAu
#define mskCT16_CEN_EN (1u << 0)
#define SysTick_CTRL_CLKSOURCE_Msk (1u << 2)
#define SCB_ICSR_PENDSTCLR_Msk (1u << 25)
#define SCB_ICSR_PENDSTSET_Msk (1u << 26)
enum { P0_IRQn = 0, P1_IRQn = 1, P2_IRQn = 2, RTC_IRQn = 3 };
static inline void __DSB(void) {}
static inline void __WFI(void) {}
void NVIC_SystemReset(void);
typedef struct { int dummy; } host_queue_t;
typedef struct { host_queue_t oqueue, iqueue; } SerialDriver;
extern SerialDriver SD2;
bool oqIsEmptyI(host_queue_t *q);
bool iqIsEmptyI(host_queue_t *q);
void iqResetI(host_queue_t *q);
typedef enum { FLASH_UNINIT, FLASH_STOP, FLASH_READY, FLASH_READ, FLASH_PGM, FLASH_ERASE } flash_state_t;
typedef struct { flash_state_t state; } EFlashDriver;
extern EFlashDriver EFLD1;
typedef struct { int dummy; } USBDriver;
void usb_lld_connect_bus(USBDriver *u);
void usb_lld_disconnect_bus(USBDriver *u);
