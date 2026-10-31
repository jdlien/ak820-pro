#pragma once
#include "quantum.h"

#define MODEL_FB_W 192
#define MODEL_FB_H 192
extern uint16_t model_fb[MODEL_FB_H][MODEL_FB_W];
extern uint8_t  model_flash[];
extern uint8_t  model_hiz;
extern uint32_t model_erase_us, model_program_us;
typedef struct {
    uint32_t ignored_cmds, ignored_reads, erases, programs;
    uint32_t dma_transfers, dma_from_busy_chip, aborts;
} model_flash_stats_t;
extern model_flash_stats_t model_fstats;
void     model_reset(void);
void     model_advance_us(uint32_t us);
uint32_t model_now_us(void);
bool     model_flash_wip(void);
