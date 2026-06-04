#include "settings.h"
#include "config.h"
#include <Arduino.h>
#include <Preferences.h>

// ---------------------------------------------------------------------------
// Palettes. The dark palette reuses the original C_* values from config.h so
// the existing calm Claude-terminal look is byte-for-byte unchanged. The light
// palette keeps the same accent hues (Claude orange / Codex purple) but on a
// light background with dark text, contrast nudged where needed for legibility.
// ---------------------------------------------------------------------------
static const Palette PAL_DARK = {
    /* bg     */ C_BG,
    /* panel  */ C_PANEL,
    /* fg     */ C_FG,
    /* dim    */ C_DIM,
    /* claude */ C_CLAUDE,
    /* codex  */ C_CODEX,
    /* wait   */ C_WAIT,
    /* waitdk */ C_WAITDK,
    /* work   */ C_WORK,
    /* idle   */ C_IDLE,
    /* accent */ C_ACCENT,
    /* crit   */ C_CRIT,
};

static const Palette PAL_LIGHT = {
    /* bg     */ 0xF4F2EE,   // warm off-white paper
    /* panel  */ 0xE2DED7,   // light gray card
    /* fg     */ 0x1C1C1C,   // near-black text
    /* dim    */ 0x6B6B6B,   // mid gray secondary text
    /* claude */ 0xB85A2E,   // darker Claude orange (contrast on light)
    /* codex  */ 0x6D4FD0,   // darker Codex purple
    /* wait   */ 0xB8740F,   // amber, darkened for light bg
    /* waitdk */ 0xF3E2BD,   // pale amber waiting-row tint
    /* work   */ 0x1E9E52,   // green, darkened for light bg
    /* idle   */ 0x6B6B6B,   // gray
    /* accent */ 0xB85A2E,   // accent = darker Claude orange
    /* crit   */ 0xC62828,   // red
};

static const Palette* g_palette = &PAL_DARK;

const Palette& theme_current() { return *g_palette; }

void theme_set(bool dark) { g_palette = dark ? &PAL_DARK : &PAL_LIGHT; }

// ---------------------------------------------------------------------------
// Backlight — LEDC PWM on TFT_BL (GPIO 21). Replaces the plain digital HIGH so
// brightness is adjustable. ~5 kHz, 8-bit resolution.
//
// ESP32 Arduino core 3.x replaced ledcSetup()/ledcAttachPin(channel) with the
// pin-centric ledcAttach(pin, freq, bits) + ledcWrite(pin, duty). We support
// both so the firmware builds on either core.
// ---------------------------------------------------------------------------
static const uint32_t BL_FREQ = 5000;
static const uint8_t  BL_BITS = 8;

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void backlight_init() {
    ledcAttach(TFT_BL, BL_FREQ, BL_BITS);
}
void backlight_set(uint8_t pct) {
    if (pct > 100) pct = 100;
    uint32_t duty = (uint32_t)pct * 255 / 100;   // 8-bit duty
    ledcWrite(TFT_BL, duty);
}
#else
static const uint8_t BL_CH = 0;
void backlight_init() {
    ledcSetup(BL_CH, BL_FREQ, BL_BITS);
    ledcAttachPin(TFT_BL, BL_CH);
}
void backlight_set(uint8_t pct) {
    if (pct > 100) pct = 100;
    uint32_t duty = (uint32_t)pct * 255 / 100;   // 8-bit duty
    ledcWrite(BL_CH, duty);
}
#endif

// ---------------------------------------------------------------------------
// Settings state + NVS.
// ---------------------------------------------------------------------------
static Preferences  prefs;
static const char*  NS = "vibemon-set";

static uint8_t  s_brightness = 100;   // %
static bool     s_dark       = true;
static uint16_t s_sleep_min  = 0;     // minutes, 0 = never

static uint8_t clamp_bright(uint8_t v) {
    if (v < 10)  return 10;
    if (v > 100) return 100;
    return v;
}

// snap to one of the supported sleep options
static uint16_t snap_sleep(uint16_t v) {
    static const uint16_t opts[] = {0, 1, 5, 15, 30};
    uint16_t best = 0; uint32_t bestd = 0xFFFFFFFF;
    for (uint16_t o : opts) {
        uint32_t d = (v > o) ? (uint32_t)(v - o) : (uint32_t)(o - v);
        if (d < bestd) { bestd = d; best = o; }
    }
    return best;
}

void settings_load() {
    prefs.begin(NS, true);
    s_brightness = clamp_bright(prefs.getUChar("bright", 100));
    s_dark       = prefs.getBool("dark", true);
    s_sleep_min  = snap_sleep(prefs.getUShort("sleep", 0));
    prefs.end();
    theme_set(s_dark);
}

void settings_save() {
    prefs.begin(NS, false);
    prefs.putUChar("bright", s_brightness);
    prefs.putBool("dark", s_dark);
    prefs.putUShort("sleep", s_sleep_min);
    prefs.end();
}

uint8_t settings_brightness() { return s_brightness; }
void settings_set_brightness(uint8_t pct) { s_brightness = clamp_bright(pct); }

bool settings_dark() { return s_dark; }
void settings_set_dark(bool dark) { s_dark = dark; theme_set(dark); }

uint16_t settings_sleep_min() { return s_sleep_min; }
void settings_set_sleep_min(uint16_t min) { s_sleep_min = snap_sleep(min); }
