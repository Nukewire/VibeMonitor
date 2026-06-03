#include <Arduino.h>
#include "display.h"
#include "config.h"
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <SPI.h>

static TFT_eSPI tft = TFT_eSPI();
static SPIClass touchSPI(VSPI);
static XPT2046_Touchscreen ts(TOUCH_CS_PIN, TOUCH_IRQ);

static const uint32_t BUF_LINES = 20;   // 320*20*2 = 12.8KB static DRAM (keeps us under the limit)
static lv_color_t buf1[SCREEN_W * BUF_LINES];
static lv_disp_draw_buf_t draw_buf;
static lv_disp_drv_t disp_drv;
static lv_indev_drv_t indev_drv;

static void flush_cb(lv_disp_drv_t* drv, const lv_area_t* area, lv_color_t* px) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
    tft.startWrite();
    tft.setAddrWindow(area->x1, area->y1, w, h);
    tft.pushColors((uint16_t*)px, w * h, true);
    tft.endWrite();
    lv_disp_flush_ready(drv);
}

bool touch_pressed(int16_t* x, int16_t* y) {
    if (!ts.touched()) return false;
    TS_Point p = ts.getPoint();
    // raw ~0..4095 -> screen. Calibrate these bounds per unit if corners drift.
    int16_t sx = map(p.x, 200, 3900, 0, SCREEN_W);
    int16_t sy = map(p.y, 240, 3800, 0, SCREEN_H);
    *x = constrain(sx, 0, SCREEN_W - 1);
    *y = constrain(sy, 0, SCREEN_H - 1);
    return true;
}

static void touch_read_cb(lv_indev_drv_t* drv, lv_indev_data_t* data) {
    int16_t x, y;
    if (touch_pressed(&x, &y)) {
        data->state = LV_INDEV_STATE_PRESSED;
        data->point.x = x;
        data->point.y = y;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

void display_init() {
    // NOTE: backlight is driven by LEDC PWM (see settings.cpp backlight_init()),
    // not a plain digital HIGH — so we deliberately do NOT touch TFT_BL here.
    tft.init();
    tft.setRotation(SCREEN_ROT);
    tft.fillScreen(TFT_BLACK);

    // Ask the panel what it actually is *after* rotation, so LVGL can never
    // disagree with the hardware (the "portrait / blank bottom third" bug).
    int16_t w = tft.width();
    int16_t h = tft.height();
    Serial.printf("[VibeMonitor] panel after rot %d: %dx%d\n", SCREEN_ROT, w, h);

    touchSPI.begin(TOUCH_CLK, TOUCH_MISO, TOUCH_MOSI, TOUCH_CS_PIN);
    ts.begin(touchSPI);
    ts.setRotation(SCREEN_ROT);

    lv_init();
    lv_disp_draw_buf_init(&draw_buf, buf1, NULL, SCREEN_W * BUF_LINES);

    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = w;
    disp_drv.ver_res = h;
    disp_drv.flush_cb = flush_cb;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    lv_indev_drv_init(&indev_drv);
    indev_drv.type = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = touch_read_cb;
    lv_indev_drv_register(&indev_drv);
}
