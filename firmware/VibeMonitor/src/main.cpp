#include <Arduino.h>
#include <lvgl.h>
#include <WiFi.h>
#include "config.h"
#include "display.h"
#include "model.h"
#include "net.h"
#include "ui.h"
#include "provisioning.h"

static Provision prov;
static StateModel state;
static uint32_t last_poll = 0;
static uint32_t last_tick = 0;

static void on_ack(const char* id) {
    net_ack(id);
    last_poll = 0;   // force a refresh on the next loop so the cleared row updates fast
}

// Draw a centered wrapped message and pump LVGL a few times so it reaches the panel
// even if we're about to block (provisioning / WiFi connect).
static void show_message(const char* msg) {
    lv_obj_clean(lv_scr_act());
    lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(C_BG), 0);
    lv_obj_t* l = lv_label_create(lv_scr_act());
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(l, SCREEN_W - 24);
    lv_obj_set_style_text_color(l, lv_color_hex(C_FG), 0);
    lv_label_set_text(l, msg);
    lv_obj_align(l, LV_ALIGN_CENTER, 0, 0);
    for (int i = 0; i < 25; i++) { lv_timer_handler(); delay(10); }
}

void setup() {
    Serial.begin(115200);
    delay(150);
    Serial.println("[VibeMonitor] boot");

    display_init();
    last_tick = millis();

    pinMode(BTN_BOOT, INPUT_PULLUP);
    if (digitalRead(BTN_BOOT) == LOW) {
        Serial.println("[VibeMonitor] BOOT held -> factory reset");
        prov_clear();
    }

    prov_load(&prov);
    if (!prov.complete) {
        Serial.println("[VibeMonitor] no config -> captive portal");
        show_message("Setup mode\n\nJoin WiFi:\n  VibeMonitor-setup\n\nthen open the page to\nenter WiFi + hub info.");
        prov_portal(&prov);
        ESP.restart();
    }

    show_message("Connecting WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);            // disable modem sleep -> stops intermittent dropouts
    WiFi.begin(prov.ssid, prov.pass);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
        lv_timer_handler();
        delay(100);
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("[VibeMonitor] WiFi OK ip="); Serial.println(WiFi.localIP());
    } else {
        Serial.println("[VibeMonitor] WiFi FAILED (will keep retrying via /state)");
    }

    net_config(prov.host, prov.port, prov.token);
    Serial.printf("[VibeMonitor] hub %s:%u\n", prov.host, prov.port);

    ui_init();
    ui_set_ack_cb(on_ack);
    last_tick = millis();
}

void loop() {
    static uint8_t fail_streak = 0;
    static const uint8_t OFFLINE_AFTER = 3;   // only show "offline" after N misses in a row

    uint32_t now = millis();
    lv_tick_inc(now - last_tick);
    last_tick = now;

    if (now - last_poll >= POLL_MS) {
        last_poll = now;

        // auto-recover WiFi if it dropped, so we don't get stuck offline
        if (WiFi.status() != WL_CONNECTED) {
            WiFi.reconnect();
        }

        bool ok = net_fetch_state(&state);
        if (ok) {
            fail_streak = 0;
            ui_set_offline(false);
            ui_update(&state);
        } else {
            if (fail_streak < 255) fail_streak++;
            if (fail_streak >= OFFLINE_AFTER) ui_set_offline(true);
            // keep showing the last good state until we're confidently offline
        }
    }

    lv_timer_handler();
    delay(5);
}
