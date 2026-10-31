/* Host stub for verify-014: just enough of QMK + ChibiOS + the SN32 register
 * file for graphics/lcd_bus.c to compile unedited. Every register access the
 * file makes to SPI0/SPI1 DATA and STAT_b goes through model.c, so the
 * polled sends and the raw SPI1 command bytes reach the panel and flash models.
 *
 * The trick: DATA and STAT_b are macros that index a per-access slot. The
 * model resolves each slot at the next access (a slot overwritten = a write;
 * a slot left at the sentinel = a read), which is enough to emulate the RX
 * FIFO handshake spi0_poll_send() and spi1_raw_byte() rely on. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define QK_KB_0 0x7E00

typedef uint32_t pin_t;
#define A13 13u
#define A17 17u
#define B8  (32u + 8u)
#define D14 (96u + 14u)

void gpio_write_pin(pin_t p, int v);
void gpio_set_pin_output(pin_t p);
void wait_ms(uint32_t ms);
#define dprintf(...) ((void)0)

/* --- the SN32 register model -------------------------------------------- */
#define MODEL_SLOTS 64u
#define MODEL_SENTINEL 0xA5A5A5A5u
typedef struct { uint32_t TX_FULL : 1, RX_EMPTY : 1, BUSY : 1; } model_stat_b_t;
typedef struct {
    volatile uint32_t       data_[MODEL_SLOTS];
    volatile model_stat_b_t stat_[MODEL_SLOTS];
    volatile uint32_t STAT, IE, IC, RIS, DMACTRL;
    struct { uint32_t FRESET : 2, DL : 4, SPIEN : 1; } CTRL0_b;
    struct { uint32_t CURCNT : 16; } CURCNT_b;
    struct { uint32_t CNT : 16; } DMACNT_b;
    struct { uint32_t DMAEN : 1, DIR : 1; } DMACTRL_b;
    struct { uint32_t DFETCH_EN : 1; } DFDLY_b;
} model_spi_t;
extern model_spi_t model_spi[2];
uint32_t model_data_acc(void);
uint32_t model_stat_acc(void);
#define SN_SPI0 (&model_spi[0])
#define SN_SPI1 (&model_spi[1])
#define DATA   data_[model_data_acc()]
#define STAT_b stat_[model_stat_acc()]

typedef struct { uint32_t AHBCLKEN; } model_sys1_t;
typedef struct { struct { uint32_t MISO1 : 2, MOSI1 : 2, SCK1 : 2, SEL1 : 2; } SPI_b; } model_pfpa_t;
extern model_sys1_t model_sys1;
extern model_pfpa_t model_pfpa;
#define SN_SYS1 (&model_sys1)
#define SN_PFPA (&model_pfpa)

#define SN32_SPI1_NUMBER 13
#define SN32_SPI_SPI1_IRQ_PRIORITY 3
static inline void nvicClearPending(int n) { (void)n; }
static inline void nvicEnableVector(int n, int p) { (void)n; (void)p; }
static inline void chSysLock(void) {}
static inline void chSysUnlock(void) {}
typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;
uint32_t st_lld_get_counter(void);

/* --- the ChibiOS SPI driver surface lcd_bus.c uses ----------------------- */
typedef enum { SPI_UNINIT = 0, SPI_STOP, SPI_READY, SPI_ACTIVE } spistate_t;
typedef struct { uint32_t ctrl0, ctrl1, clkdiv; } SPIConfig;
typedef struct { spistate_t state; int id; } SPIDriver;
extern SPIDriver SPID0, SPID1;
#define SPI_DATA_LENGTH(n) ((uint32_t)(n) - 1u)
#define SPI_MLSB_MSB 0u
#define SPI_CPOL_LOW 0u
#define SPI_CPHA_FALLING 0u
void spiStart(SPIDriver *d, const SPIConfig *c);
void spiSend(SPIDriver *d, size_t n, const void *tx);
void spiExchange(SPIDriver *d, size_t n, const void *tx, void *rx);
typedef void (*spi_sn32_dma_cb_t)(void);
void spiSN32FlashDmaPrepare(SPIDriver *lcd, SPIDriver *flash, uint32_t len);
void spiSN32FlashDmaFire(SPIDriver *lcd, spi_sn32_dma_cb_t cb);
void spiSN32FlashDmaAbort(SPIDriver *lcd);
uint32_t spiSN32FlashDmaRescues(void);
