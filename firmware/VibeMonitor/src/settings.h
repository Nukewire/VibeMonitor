#pragma once
#include <stdint.h>

// Runtime-switchable palette. Mirrors the C_* defines in config.h.
// All values are 24-bit 0xRRGGBB (feed straight into lv_color_hex()).
struct Palette {
    uint32_t bg;
    uint32_t panel;
    uint32_t fg;
    uint32_t dim;
    uint32_t claude;
    uint32_t codex;
    uint32_t wait;
    uint32_t waitdk;   // dim "waiting" row tint
    uint32_t work;
    uint32_t idle;
    uint32_t accent;
    uint32_t crit;
};

// ---- theme ----------------------------------------------------------------
const Palette& theme_current();        // active palette
void           theme_set(bool dark);   // swap active palette (does NOT touch NVS)

// ---- backlight (LEDC PWM on TFT_BL) ---------------------------------------
void backlight_init();                 // configure LEDC channel + attach pin
void backlight_set(uint8_t pct);       // 0..100 -> duty (0 turns it fully off)

// ---- settings state + NVS (namespace "vibemon-set") -----------------------
void settings_load();                  // read NVS into RAM (call on boot)
void settings_save();                  // persist current RAM state to NVS

uint8_t  settings_brightness();        // 10..100 (%)
void     settings_set_brightness(uint8_t pct);

bool     settings_dark();              // true = dark theme
void     settings_set_dark(bool dark);

uint16_t settings_sleep_min();         // 0,1,5,15,30 (0 = never sleep)
void     settings_set_sleep_min(uint16_t min);
