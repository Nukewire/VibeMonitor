#pragma once
#include <lvgl.h>
#include <stdint.h>

void display_init();                              // lv_init + TFT_eSPI + XPT2046 drivers
bool touch_pressed(int16_t* x, int16_t* y);       // mapped screen coords; false if not touched
