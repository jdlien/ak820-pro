/* Host stubs for the ChibiOS/SN32 pieces that sleep.c and ch582f_ajazz.c touch.
 * The input queue's semantics follow ChibiOS hal_queues.c (iqPutI, iqGetI,
 * iqResetI); the registers are plain RAM the test drives. Verify-032. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

/* sleep.c's ds_deep_wfi carries section(".ramtext") and long_call (ARM ELF):
 * on Mach-O the section spelling is rejected, so it becomes "used". */
#define section(x) used

typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;
typedef int32_t  msg_t;
typedef uint32_t eventflags_t;
typedef uint32_t eventmask_t;
typedef uint32_t syssts_t;
#define MSG_OK      0
#define MSG_TIMEOUT -1
#define MSG_RESET   -2
#define Q_EMPTY     MSG_TIMEOUT
#define Q_FULL      MSG_TIMEOUT
#define TIME_IMMEDIATE ((sysinterval_t)0)
#define TIME_INFINITE  ((sysinterval_t)-1)
#define EVENT_MASK(eid) ((eventmask_t)1 << (eid))
#define CH_CFG_ST_RESOLUTION 16
#define CH_CFG_ST_FREQUENCY 187500

/* ---- the queues (ChibiOS hal_queues.c, minus the thread wakeups) ---- */
#define SERIAL_BUFFERS_SIZE 128
typedef struct {
    uint8_t *q_buffer, *q_top, *q_wrptr, *q_rdptr;
    size_t   q_counter;
} io_queue_t;
typedef io_queue_t input_queue_t;
typedef io_queue_t output_queue_t;

static inline size_t iqGetFullI(input_queue_t *q) { return q->q_counter; }
static inline bool   iqIsEmptyI(input_queue_t *q) { return q->q_counter == 0; }
static inline bool   iqIsFullI(input_queue_t *q) { return q->q_counter >= (size_t)(q->q_top - q->q_buffer); }
static inline size_t oqGetFullI(output_queue_t *q) { return q->q_counter; }
static inline size_t oqGetEmptyI(output_queue_t *q) { return (size_t)(q->q_top - q->q_buffer) - q->q_counter; }
static inline bool   oqIsEmptyI(output_queue_t *q) { return q->q_counter == 0; }
void  iqResetI(input_queue_t *iqp);
msg_t iqPutI(input_queue_t *iqp, uint8_t b);
msg_t iqGetI(input_queue_t *iqp);

/* ---- the serial driver ---- */
typedef struct { int dummy; } event_source_t;
typedef struct { eventflags_t flags; } event_listener_t;
typedef struct {
    uint32_t speed;
    uint32_t UART_WordLength, UART_StopBits, UART_Parity, UART_FIFOControl, UART_AutoBaudControl,
        UART_Oversampling, UART_HalfDuplexMode;
} SerialConfig;
typedef struct {
    input_queue_t  iqueue;
    output_queue_t oqueue;
    uint8_t        ib[SERIAL_BUFFERS_SIZE];
    uint8_t        ob[SERIAL_BUFFERS_SIZE];
    event_source_t event;
} SerialDriver;
extern SerialDriver SD2;
#define SD_PARITY_ERROR  (1u << 5)
#define SD_FRAMING_ERROR (1u << 6)
#define SD_OVERRUN_ERROR (1u << 7)
#define CHN_INPUT_AVAILABLE (1u << 2)
void   sdStart(SerialDriver *sdp, const SerialConfig *cfg);
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t);
size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n);
#define chnGetEventSource(sdp) (&(sdp)->event)
void         chEvtRegisterMaskWithFlags(event_source_t *s, event_listener_t *l, eventmask_t m, eventflags_t f);
eventflags_t chEvtGetAndClearFlags(event_listener_t *l);

/* ---- the kernel ---- */
extern int g_lock_depth;
void      chSysLock(void);
void      chSysUnlock(void);
#define chSysLockFromISR()   chSysLock()
#define chSysUnlockFromISR() chSysUnlock()
#define osalSysLock()        chSysLock()
#define osalSysUnlock()      chSysUnlock()
syssts_t chSysGetStatusAndLockX(void);
void     chSysRestoreStatusX(syssts_t s);
systime_t chVTGetSystemTimeX(void);
#define chVTGetSystemTime() chVTGetSystemTimeX()
#define chVTTimeElapsedSinceX(t) ((sysinterval_t)(chVTGetSystemTimeX() - (t)))
typedef struct { int dummy; } virtual_timer_t;
typedef void (*vtfunc_t)(void *);
static inline void chVTObjectInit(virtual_timer_t *v) { (void)v; }
static inline void chVTSet(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
static inline void chVTSetI(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
#define TIME_MS2I(ms) ((sysinterval_t)((ms) * 187.5))
#define chThdSleepMilliseconds(ms) ((void)(ms))
uint32_t st_lld_get_counter(void);

/* ---- the SN32F299's registers the two files read and write ---- */
typedef struct { volatile uint32_t FRMNO, CFG; } sn_usb_t;
typedef struct { volatile uint32_t LS, CTRL, RB, II, IE, TH; } sn_uart_t;
typedef struct { volatile uint32_t ADM; } sn_adc_t;
typedef struct { volatile uint32_t DATA, IS, IBS, IEV, IC, IE, RIS; } sn_gpio_t;
typedef struct { volatile uint32_t ISER[1], ICER[1], ISPR[1], ICPR[1]; } nvic_t;
typedef struct { volatile uint32_t ICSR; } scb_t;
typedef struct { volatile uint32_t CTRL; } systick_t;
typedef struct { struct { volatile uint32_t TMRCTRL; } config; } sn_ct16_t;
typedef struct { volatile uint32_t CLKCFG, PLLCTRL, CSST; } sn_sys0_t;
typedef struct { volatile uint32_t LPCTRL; } sn_flash_t;
typedef struct { volatile uint32_t CTRL; } sn_pmu_t;
typedef struct { volatile uint32_t RIS, IC; } sn_rtc_t;
typedef struct { volatile uint32_t CFG, FEED; } sn_wdt_t;
typedef struct { volatile uint32_t STAT, DMACTRL; } sn_spi_t;
extern sn_usb_t g_usb; extern sn_uart_t g_uart2; extern sn_adc_t g_adc;
extern sn_gpio_t g_gpio0, g_gpio1, g_gpio2; extern nvic_t g_nvic; extern scb_t g_scb;
extern systick_t g_systick; extern sn_ct16_t g_ct16b5; extern sn_sys0_t g_sys0;
extern sn_flash_t g_flash; extern sn_pmu_t g_pmu; extern sn_rtc_t g_rtc; extern sn_wdt_t g_wdt;
extern sn_spi_t g_spi0, g_spi1;
#define SN_USB    (&g_usb)
#define SN_UART2  (&g_uart2)
#define SN_ADC    (&g_adc)
#define SN_GPIO0  (&g_gpio0)
#define SN_GPIO1  (&g_gpio1)
#define SN_GPIO2  (&g_gpio2)
#define NVIC      (&g_nvic)
#define SCB       (&g_scb)
#define SysTick   (&g_systick)
#define SN32_ST_TIM (&g_ct16b5)
#define SN_SYS0   (&g_sys0)
#define SN_FLASH  (&g_flash)
#define SN_PMU    (&g_pmu)
#define SN_RTC    (&g_rtc)
#define SN_WDT    (&g_wdt)
#define SN_SPI0   (&g_spi0)
#define SN_SPI1   (&g_spi1)
#define mskCT16_CEN_EN (1u << 0)
#define mskRTC_SECIF   (1u << 0)
#define mskRTC_SECIC   (1u << 0)
#define mskWDT_WDKEY   (0x5AFAu << 16)
#define mskWDT_FV      (0x55AAu)
#define SCB_ICSR_PENDSTCLR_Msk (1u << 25)
#define SCB_ICSR_PENDSTSET_Msk (1u << 26)
#define SysTick_CTRL_CLKSOURCE_Msk (1u << 2)
enum { P0_IRQn = 4, P1_IRQn = 5, P2_IRQn = 6, RTC_IRQn = 7 };
void ds_wfi_hook(void);   /* the test's model of what happens while asleep */
#define __DSB() ((void)0)
#define __WFI() ds_wfi_hook()
void NVIC_SystemReset(void);

/* The internal flash driver's state (EFLD1). */
typedef enum { FLASH_UNINIT = 0, FLASH_STOP, FLASH_READY, FLASH_READ, FLASH_PGM, FLASH_ERASE } flash_state_t;
typedef struct { flash_state_t state; } EFlashDriver;
extern EFlashDriver EFLD1;

/* USB */
typedef struct { int dummy; } USBDriver;
extern USBDriver USBD1;
#define USB_DRIVER USBD1
void usb_lld_connect_bus(USBDriver *u);
void usb_lld_disconnect_bus(USBDriver *u);

/* ---- pins (QMK): port in the high half, pad in the low ---- */
typedef uint32_t pin_t;
typedef uint32_t ioportid_t;
#define PAL_PORT(p) ((ioportid_t)((p) >> 16))
#define PAL_PAD(p)  ((p) & 0xFFFFu)
#define PIN_(port, pad) ((pin_t)(((uint32_t)(port) << 16) | (pad)))
#define A0 PIN_(0, 0)
#define B0 PIN_(1, 0)
#define C0 PIN_(2, 0)
#define A4 PIN_(0, 4)
#define A5 PIN_(0, 5)
#define A6 PIN_(0, 6)
#define A7 PIN_(0, 7)
#define A10 PIN_(0, 10)
#define A18 PIN_(0, 18)
#define A19 PIN_(0, 19)
#define B2 PIN_(1, 2)
#define B14 PIN_(1, 14)
#define B15 PIN_(1, 15)
#define B16 PIN_(1, 16)
#define B19 PIN_(1, 19)
#define C1 PIN_(2, 1)
#define C2 PIN_(2, 2)
#define C3 PIN_(2, 3)
#define C4 PIN_(2, 4)
#define C5 PIN_(2, 5)
#define C6 PIN_(2, 6)
#define C7 PIN_(2, 7)
#define C8 PIN_(2, 8)
#define C9 PIN_(2, 9)
#define C14 PIN_(2, 14)
#define D19 PIN_(3, 19)
bool gpio_read_pin(pin_t p);
void gpio_write_pin_low(pin_t p);
void gpio_write_pin_high(pin_t p);
void gpio_set_pin_output_push_pull(pin_t p);
void gpio_set_pin_input_high(pin_t p);
