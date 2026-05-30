#pragma once

#define SCREEN_W      320
#define SCREEN_H      240
#define SCREEN_ROT      1     // landscape, USB on the right

#define BTN_BOOT        0     // hold at power-on => factory reset (clear NVS)

// XPT2046 resistive touch (separate VSPI bus on the CYD)
#define TOUCH_CLK      25
#define TOUCH_MOSI     32
#define TOUCH_MISO     39
#define TOUCH_CS_PIN   33
#define TOUCH_IRQ      36

#define MAX_SESSIONS   24
#define MAX_PROJ_LEN   24
#define POLL_MS      1500
#define HTTP_TIMEOUT_MS 4000

// palette — Claude-CLI dark terminal theme.
// IMPORTANT: these feed LVGL's lv_color_hex(), which expects 24-bit 0xRRGGBB.
#define C_BG      0x141414   // near-black charcoal (screen)
#define C_PANEL   0x2B2B2B   // dark gray (row/card bg)
#define C_FG      0xEDEDED   // off-white (primary text)
#define C_DIM     0x8A8A8A   // gray (secondary text)
#define C_CLAUDE  0xD97757   // Claude warm orange
#define C_CODEX   0xA78BFA   // Codex purple
#define C_WAIT    0xF5A623   // amber  (waiting)
#define C_WAITDK  0x4A3000   // dim amber (waiting flash off-phase)
#define C_WORK    0x4ADE80   // green  (working)
#define C_IDLE    0x8A8A8A   // gray   (idle)
#define C_ACCENT  0xD97757   // accent = Claude orange (tabs, usage bar)
#define C_CRIT    0xE5484D   // red    (offline banner)
