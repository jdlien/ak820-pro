/* Host stand-in for ChibiOS's hal.h / ch.h, for sleep.c and bt_ui.c only.
 * Registers are plain host structs (no hardware is touched). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>

typedef uint16_t systime_t;
typedef uint32_t sysinterval_t;
typedef uint32_t pin_t;
typedef uint32_t ioportid_t;
typedef int32_t  msg_t;

/* pins: port in the high byte, pad in the low byte */
#define PAL_LINE(port, pad) ((pin_t)(((uint32_t)(port) << 8) | (uint32_t)(pad)))
#define PAL_PORT(pin) ((ioportid_t)((pin) >> 8))
#define PAL_PAD(pin)  ((uint32_t)((pin) & 0xFFu))
#define A0 PAL_LINE(0, 0)
#define B0 PAL_LINE(1, 0)
#define C0 PAL_LINE(2, 0)
#define D0 PAL_LINE(3, 0)
#define A4 PAL_LINE(0, 4)
#define A5 PAL_LINE(0, 5)
#define A6 PAL_LINE(0, 6)
#define A7 PAL_LINE(0, 7)
#define A10 PAL_LINE(0, 10)
#define A18 PAL_LINE(0, 18)
#define A19 PAL_LINE(0, 19)
#define B2 PAL_LINE(1, 2)
#define B14 PAL_LINE(1, 14)
#define B15 PAL_LINE(1, 15)
#define B16 PAL_LINE(1, 16)
#define B19 PAL_LINE(1, 19)
#define C1 PAL_LINE(2, 1)
#define C2 PAL_LINE(2, 2)
#define C3 PAL_LINE(2, 3)
#define C4 PAL_LINE(2, 4)
#define C5 PAL_LINE(2, 5)
#define C6 PAL_LINE(2, 6)
#define C7 PAL_LINE(2, 7)
#define C8 PAL_LINE(2, 8)
#define C9 PAL_LINE(2, 9)
#define C14 PAL_LINE(2, 14)
#define D19 PAL_LINE(3, 19)

/* the board's pin map (keyboard.json, config.h) */
#define MATRIX_ROWS 6
#define MATRIX_COLS 15
#define MATRIX_ROW_PINS { B14, B15, B19, D19, A19, A18 }
#define MATRIX_COL_PINS { A4, A5, C0, C1, C2, C3, A6, A7, C4, C5, C6, C7, C14, C8, C9 }
#define ENCODER_A_PINS { B2 }
#define ENCODER_B_PINS { A10 }
#define CHARGE_CHRG_PIN B16

#ifndef ARRAY_SIZE
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#endif

bool gpio_read_pin(pin_t pin);
void gpio_set_pin_input_high(pin_t pin);
void gpio_set_pin_output_push_pull(pin_t pin);
void gpio_write_pin_high(pin_t pin);
void gpio_write_pin_low(pin_t pin);

/* registers */
typedef struct { volatile uint32_t FRMNO, CFG; } usb_regs_t;
typedef struct { volatile uint32_t CLKCFG, PLLCTRL, CSST; } sys0_regs_t;
typedef struct { volatile uint32_t DATA, IE, IS, IBS, IEV, IC, RIS; } gpio_regs_t;
typedef struct { volatile uint32_t LS, CTRL, RB; } uart_regs_t;
typedef struct { volatile uint32_t LPCTRL; } flash_regs_t;
typedef struct { volatile uint32_t ADM; } adc_regs_t;
typedef struct { volatile uint32_t FEED, CFG; } wdt_regs_t;
typedef struct { volatile uint32_t STAT, DMACTRL; } spi_regs_t;
typedef struct { volatile uint32_t RIS, IC; } rtc_regs_t;
typedef struct { volatile uint32_t CTRL; } pmu_regs_t;
typedef struct { volatile uint32_t ISER[1], ICER[1], ISPR[1], ICPR[1]; } nvic_regs_t;
typedef struct { volatile uint32_t ICSR; } scb_regs_t;
extern usb_regs_t   host_usb;   extern sys0_regs_t host_sys0;
extern gpio_regs_t  host_gpio0, host_gpio1, host_gpio2;
extern uart_regs_t  host_uart2; extern flash_regs_t host_flash; extern adc_regs_t host_adc;
extern wdt_regs_t   host_wdt;   extern spi_regs_t host_spi0, host_spi1; extern rtc_regs_t host_rtc;
extern pmu_regs_t   host_pmu;   extern nvic_regs_t host_nvic; extern scb_regs_t host_scb;
#define SN_USB   (&host_usb)
#define SN_SYS0  (&host_sys0)
#define SN_GPIO0 (&host_gpio0)
#define SN_GPIO1 (&host_gpio1)
#define SN_GPIO2 (&host_gpio2)
#define SN_UART2 (&host_uart2)
#define SN_FLASH (&host_flash)
#define SN_ADC   (&host_adc)
#define SN_WDT   (&host_wdt)
#define SN_SPI0  (&host_spi0)
#define SN_SPI1  (&host_spi1)
#define SN_RTC   (&host_rtc)
#define SN_PMU   (&host_pmu)
#define NVIC     (&host_nvic)
#define SCB      (&host_scb)
#define mskRTC_SECIF 1u
#define mskRTC_SECIC 1u
enum { P0_IRQn = 0, P1_IRQn = 1, P2_IRQn = 2, RTC_IRQn = 3 };

/* the flash driver */
typedef enum { FLASH_UNINIT = 0, FLASH_STOP, FLASH_READY, FLASH_READ, FLASH_PGM, FLASH_ERASE } flash_state_t;
typedef struct { flash_state_t state; } EFlashDriver;
extern EFlashDriver EFLD1;

/* serial */
typedef struct { int dummy; } output_queue_t;
typedef struct { int dummy; } input_queue_t;
typedef struct { int es; output_queue_t oqueue; input_queue_t iqueue; } SerialDriver;
extern SerialDriver SD2;
bool oqIsEmptyI(output_queue_t *q);
bool iqIsEmptyI(input_queue_t *q);
void iqResetI(input_queue_t *q);

/* kernel */
void chSysLock(void);
void chSysUnlock(void);
systime_t chVTGetSystemTimeX(void);
void chThdSleepMilliseconds(uint32_t ms);
#define TIME_US2I(us) ((sysinterval_t)(((uint64_t)(us) * 187500u + 999999u) / 1000000u))
#define TIME_MS2I(ms) ((sysinterval_t)(((uint64_t)(ms) * 187500u + 999u) / 1000u))
#define __DSB() ((void)0)
#define __ISB() ((void)0)
#define __WFI() ((void)0)
#define __NOP() ((void)0)
#define __disable_irq() ((void)0)
#define __enable_irq() ((void)0)

/* the rest of the deep sleep's registers (compiled, never run here) */
typedef struct { volatile uint32_t CTRL; } systick_regs_t;
extern systick_regs_t host_systick;
#define SysTick (&host_systick)
#define SysTick_CTRL_CLKSOURCE_Msk (1u << 2)
#define SCB_ICSR_PENDSTCLR_Msk (1u << 25)
#define SCB_ICSR_PENDSTSET_Msk (1u << 26)
typedef struct { struct { volatile uint32_t TMRCTRL; } config; } st_tim_t;
extern st_tim_t host_st_tim;
#define SN32_ST_TIM (&host_st_tim)
#define mskCT16_CEN_EN 1u
#define mskWDT_WDKEY (0x5AFAu << 16)
#define mskWDT_FV 0x55AAu
void NVIC_SystemReset(void);
typedef struct { int dummy; } USBDriver;
extern USBDriver USBD1;
#define USB_DRIVER USBD1
void usb_lld_connect_bus(USBDriver *u);
void usb_lld_disconnect_bus(USBDriver *u);
