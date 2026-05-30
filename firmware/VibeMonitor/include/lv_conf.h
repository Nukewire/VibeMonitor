/* Minimal LVGL 8.x config for VibeMonitor. Anything not set here falls back to the
   defaults in lv_conf_internal.h. Enabled via -DLV_CONF_INCLUDE_SIMPLE + -I include. */
#ifndef LV_CONF_H
#define LV_CONF_H

#include <stdint.h>

#define LV_COLOR_DEPTH        16
/* TFT_eSPI pushColors(..., true) does the byte swap, so keep LVGL swap off. */
#define LV_COLOR_16_SWAP      0

#define LV_MEM_SIZE           (40U * 1024U)
#define LV_DISP_DEF_REFR_PERIOD 30
#define LV_TICK_CUSTOM        0          /* we call lv_tick_inc() in loop() */

#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_DEFAULT       &lv_font_montserrat_14

#define LV_USE_LOG            0

#endif /* LV_CONF_H */
