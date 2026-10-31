/* Host stand-in for ChibiOS hal.h, just what QMK's real
 * platforms/chibios/drivers/wear_leveling/wear_leveling_efl.c and
 * wear_leveling_efl_config.h use. Types and values match ChibiOS's
 * hal_flash.h (flash_offset_t/flash_sector_t uint32_t, the error enum) and the
 * SN32F290 registry (sn32_registry.h:217-222: 8-byte lines, 256 x 1 KB). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define SN32_FLASH_LINE_SIZE 8U
#define FLASH_SIZE (256u * 1024u)

typedef uint32_t flash_offset_t;
typedef uint32_t flash_sector_t;
typedef enum {
    FLASH_NO_ERROR = 0, FLASH_BUSY_ERASING = 1, FLASH_ERROR_READ = 2, FLASH_ERROR_PROGRAM = 3,
    FLASH_ERROR_ERASE = 4, FLASH_ERROR_VERIFY = 5, FLASH_ERROR_HW_FAILURE = 6, FLASH_ERROR_UNIMPLEMENTED = 7
} flash_error_t;
#define FLASH_ATTR_ERASED_IS_ONE 0x00000001U
#define FLASH_ATTR_MEMORY_MAPPED 0x00000002U
typedef struct {
    uint32_t       attributes;
    uint32_t       page_size;
    flash_sector_t sectors_count;
    const void    *sectors;
    uint32_t       sectors_size;
    uint8_t       *address;
    uint32_t       size;
} flash_descriptor_t;
typedef struct BaseFlash BaseFlash;
typedef struct { int unused; } EFlashDriver;
extern EFlashDriver EFLD1;
typedef int msg_t;
#define HAL_RET_SUCCESS 0
msg_t eflStart(EFlashDriver *e, const void *cfg);
void  eflStop(EFlashDriver *e);
const flash_descriptor_t *flashGetDescriptor(BaseFlash *f);
uint32_t       flashGetSectorSize(BaseFlash *f, flash_sector_t s);
flash_offset_t flashGetSectorOffset(BaseFlash *f, flash_sector_t s);
void          *flashGetOffsetAddress(BaseFlash *f, flash_offset_t o);
flash_error_t  flashStartEraseSector(BaseFlash *f, flash_sector_t s);
flash_error_t  flashWaitErase(BaseFlash *f);
flash_error_t  flashProgram(BaseFlash *f, flash_offset_t off, size_t n, const uint8_t *pp);
void chSysHalt(const char *reason);
