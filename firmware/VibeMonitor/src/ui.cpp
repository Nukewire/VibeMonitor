#include <Arduino.h>
#include "ui.h"
#include "config.h"
#include "icons.h"
#include "settings.h"
#include <lvgl.h>
#include <stdio.h>
#include <string.h>

// palette shorthand: P().bg etc. -> lv_color_t
static inline lv_color_t pc(uint32_t rgb) { return lv_color_hex(rgb); }
static inline const Palette& P() { return theme_current(); }

static lv_obj_t* scr_root;
static lv_obj_t* tabview;
static lv_obj_t* tab_s;
static lv_obj_t* tab_u;
static lv_obj_t* tab_set;
static lv_obj_t* list_obj;
static lv_obj_t* strip_lbl;
static lv_obj_t* footer;
static lv_obj_t* offline_banner;
static lv_obj_t* claude_bar;
static lv_obj_t* claude_lbl;
static lv_obj_t* claude_ico;
static lv_obj_t* claude_proj;     // projection line under Claude row
static lv_obj_t* codex_lbl;
static lv_obj_t* codex_bar;
static lv_obj_t* codex_ico;
static lv_obj_t* codex_proj;      // projection line under Codex row
static lv_obj_t* week_lbl;        // weekly reset countdown
static lv_obj_t* claude_week_bar;
static lv_obj_t* claude_week_val;
static lv_obj_t* codex_week_bar;
static lv_obj_t* codex_week_val;
static AckCb g_ack = NULL;

// settings-tab widgets
static lv_obj_t* set_bright_lbl;
static lv_obj_t* set_bright_slider;
static lv_obj_t* set_bright_val;
static lv_obj_t* set_theme_lbl;
static lv_obj_t* set_theme_sw;
static lv_obj_t* set_sleep_lbl;
static lv_obj_t* set_sleep_roller;

static const char* SLEEP_OPTS = "Never\n1 min\n5 min\n15 min\n30 min";
static const uint16_t SLEEP_VALS[] = {0, 1, 5, 15, 30};

static uint16_t roller_idx_to_min(uint16_t idx) {
    if (idx >= (sizeof(SLEEP_VALS) / sizeof(SLEEP_VALS[0]))) idx = 0;
    return SLEEP_VALS[idx];
}
static uint16_t min_to_roller_idx(uint16_t m) {
    for (uint16_t i = 0; i < sizeof(SLEEP_VALS) / sizeof(SLEEP_VALS[0]); i++)
        if (SLEEP_VALS[i] == m) return i;
    return 0;
}

// Human-friendly reset countdown: ">=1h" -> "4h 47m", "<1h" -> "47m".
static void fmt_reset(uint32_t resetSec, char* out, size_t n) {
    uint32_t mins = resetSec / 60;
    if (mins >= 60) snprintf(out, n, "%luh %lum",
                             (unsigned long)(mins / 60), (unsigned long)(mins % 60));
    else            snprintf(out, n, "%lum", (unsigned long)mins);
}

// Coarser countdown for the weekly window: ">=1d" -> "3d 4h", else "4h 47m".
static void fmt_long(int sec, char* out, size_t n) {
    if (sec < 0) { strlcpy(out, "--", n); return; }
    uint32_t mins = (uint32_t)sec / 60;
    uint32_t hrs  = mins / 60;
    if (hrs >= 24) snprintf(out, n, "%lud %luh",
                            (unsigned long)(hrs / 24), (unsigned long)(hrs % 24));
    else if (hrs >= 1) snprintf(out, n, "%luh %lum",
                            (unsigned long)hrs, (unsigned long)(mins % 60));
    else snprintf(out, n, "%lum", (unsigned long)mins);
}

// Build a provider's projection line text + pick its color from the palette.
// Returns the LVGL color to render the label in.
static lv_color_t projection_text(const Usage& u, char* out, size_t n) {
    if (!u.ok) { out[0] = 0; return pc(P().dim); }
    if (u.willExhaust && u.etaClock[0]) {
        snprintf(out, n, "out ~%s", u.etaClock);
        return pc(P().wait);
    }
    if (u.burnPerHr > 0.0f && u.leftoverPct >= 0.0f) {
        int spare = (int)(u.leftoverPct * 100.0f + 0.5f);
        if (spare < 0) spare = 0;
        snprintf(out, n, "%d%% to spare", spare);
        return pc(P().work);
    }
    strlcpy(out, "steady", n);
    return pc(P().dim);
}

static void update_week_bar(const Usage& u, lv_obj_t* bar, lv_obj_t* val) {
    if (u.ok && u.weekPct >= 0.0f) {
        int wp = (int)(u.weekPct * 100 + 0.5f);
        if (wp < 0) wp = 0; else if (wp > 100) wp = 100;
        lv_bar_set_value(bar, wp, LV_ANIM_OFF);
        char b[10];
        snprintf(b, sizeof(b), "wk %d%%", wp);
        lv_label_set_text(val, b);
    } else {
        lv_bar_set_value(bar, 0, LV_ANIM_OFF);
        lv_label_set_text(val, "");
    }
}

struct Row {
    lv_obj_t* cont;
    lv_obj_t* badge;     // provider logo image (Claude / Codex)
    lv_obj_t* name;
    lv_obj_t* sym;       // status symbol at end: ! waiting / refresh working / Zzz idle
    char id[40];
    bool waiting;
    SessStatus status;
    bool active;         // currently shown
};
static Row rows[MAX_SESSIONS];

static lv_color_t status_color(SessStatus s) {
    switch (s) {
        case ST_WAITING: return pc(P().wait);
        case ST_WORKING: return pc(P().work);
        default:         return pc(P().idle);
    }
}

static void row_clicked(lv_event_t* e) {
    Row* r = (Row*)lv_event_get_user_data(e);
    if (g_ack && r->id[0]) g_ack(r->id);
}

void ui_set_ack_cb(AckCb cb) { g_ack = cb; }

// ---- settings callbacks ----------------------------------------------------
static void bright_changed(lv_event_t* e) {
    int v = lv_slider_get_value(set_bright_slider);
    settings_set_brightness((uint8_t)v);
    backlight_set((uint8_t)v);              // apply live
    char b[8]; snprintf(b, sizeof(b), "%d%%", v);
    lv_label_set_text(set_bright_val, b);
}
static void bright_released(lv_event_t* e) {
    settings_save();
}
static void theme_toggled(lv_event_t* e) {
    bool dark = lv_obj_has_state(set_theme_sw, LV_STATE_CHECKED);
    settings_set_dark(dark);
    settings_save();
    ui_apply_theme();
}
static void sleep_changed(lv_event_t* e) {
    uint16_t idx = lv_roller_get_selected(set_sleep_roller);
    settings_set_sleep_min(roller_idx_to_min(idx));
    settings_save();
}

// ---- terminal-style helpers ----------------------------------------------
static void style_tab_btns(lv_obj_t* tv) {
    lv_obj_t* btns = lv_tabview_get_tab_btns(tv);
    lv_obj_set_style_bg_color(btns, pc(P().bg), 0);
    lv_obj_set_style_text_color(btns, pc(P().dim), 0);
    lv_obj_set_style_text_color(btns, pc(P().accent), LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_border_color(btns, pc(P().accent), LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_text_font(btns, &lv_font_montserrat_14, 0);
}

void ui_init() {
    lv_obj_t* scr = lv_scr_act();
    scr_root = scr;
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, pc(P().bg), 0);
    lv_obj_set_style_text_color(scr, pc(P().fg), 0);

    tabview = lv_tabview_create(scr, LV_DIR_TOP, 26);
    lv_obj_set_style_bg_color(tabview, pc(P().bg), 0);
    style_tab_btns(tabview);
    tab_s   = lv_tabview_add_tab(tabview, "SESSIONS");
    tab_u   = lv_tabview_add_tab(tabview, "USAGE");
    tab_set = lv_tabview_add_tab(tabview, "SETTINGS");
    lv_obj_set_style_bg_color(tab_s, pc(P().bg), 0);
    lv_obj_set_style_bg_color(tab_u, pc(P().bg), 0);
    lv_obj_set_style_bg_color(tab_set, pc(P().bg), 0);
    lv_obj_set_style_pad_all(tab_s, 2, 0);
    lv_obj_set_style_pad_all(tab_u, 6, 0);
    lv_obj_set_style_pad_all(tab_set, 6, 0);

    // ---- sessions tab : top usage strip ----
    strip_lbl = lv_label_create(tab_s);
    lv_obj_align(strip_lbl, LV_ALIGN_TOP_LEFT, 2, 0);
    lv_obj_set_style_text_color(strip_lbl, pc(P().dim), 0);
    lv_label_set_text(strip_lbl, "Claude --   Codex --");

    // ---- scrollable list of session rows ----
    lv_obj_t* list = lv_obj_create(tab_s);
    list_obj = list;
    lv_obj_set_size(list, SCREEN_W - 12, 158);
    lv_obj_align(list, LV_ALIGN_TOP_MID, 0, 18);
    lv_obj_set_flex_flow(list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(list, 3, 0);
    lv_obj_set_style_pad_all(list, 3, 0);
    lv_obj_set_style_bg_color(list, pc(P().bg), 0);
    lv_obj_set_style_border_width(list, 0, 0);
    lv_obj_set_scrollbar_mode(list, LV_SCROLLBAR_MODE_AUTO);

    for (int i = 0; i < MAX_SESSIONS; i++) {
        Row* r = &rows[i];
        r->cont = lv_obj_create(list);
        lv_obj_set_size(r->cont, lv_pct(100), 26);
        lv_obj_set_flex_flow(r->cont, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(r->cont, LV_FLEX_ALIGN_START,
                              LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_pad_hor(r->cont, 5, 0);
        lv_obj_set_style_pad_ver(r->cont, 2, 0);
        lv_obj_set_style_pad_column(r->cont, 6, 0);
        lv_obj_set_style_radius(r->cont, 5, 0);
        lv_obj_set_style_border_width(r->cont, 0, 0);
        lv_obj_set_style_bg_color(r->cont, pc(P().panel), 0);
        lv_obj_set_style_bg_opa(r->cont, LV_OPA_COVER, 0);
        lv_obj_add_flag(r->cont, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(r->cont, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_event_cb(r->cont, row_clicked, LV_EVENT_CLICKED, r);

        // provider badge — the real Claude / Codex logo (18x18 image)
        r->badge = lv_img_create(r->cont);
        lv_img_set_src(r->badge, &claude_icon);   // set per-row in ui_update

        r->name = lv_label_create(r->cont);
        lv_obj_set_flex_grow(r->name, 1);
        lv_label_set_long_mode(r->name, LV_LABEL_LONG_DOT);
        lv_obj_set_style_text_color(r->name, pc(P().fg), 0);
        lv_label_set_text(r->name, "");

        r->sym = lv_label_create(r->cont);
        lv_obj_set_style_text_color(r->sym, pc(P().dim), 0);
        lv_label_set_text(r->sym, "");

        r->id[0] = 0;
        r->waiting = false;
        r->status = ST_IDLE;
        r->active = false;
    }

    footer = lv_label_create(tab_s);
    lv_obj_align(footer, LV_ALIGN_BOTTOM_LEFT, 2, 0);
    lv_obj_set_style_text_color(footer, pc(P().dim), 0);
    lv_label_set_text(footer, "");

    // ---- usage tab ----
    claude_ico = lv_img_create(tab_u);
    lv_img_set_src(claude_ico, &claude_icon);
    lv_obj_align(claude_ico, LV_ALIGN_TOP_LEFT, 2, 2);
    claude_lbl = lv_label_create(tab_u);
    lv_obj_align(claude_lbl, LV_ALIGN_TOP_LEFT, 26, 4);
    lv_obj_set_style_text_color(claude_lbl, pc(P().claude), 0);
    lv_label_set_text(claude_lbl, "Claude --");

    claude_bar = lv_bar_create(tab_u);
    lv_obj_set_size(claude_bar, SCREEN_W - 56, 16);
    lv_obj_align(claude_bar, LV_ALIGN_TOP_LEFT, 2, 26);
    lv_bar_set_range(claude_bar, 0, 100);
    lv_bar_set_value(claude_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(claude_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(claude_bar, pc(P().claude), LV_PART_INDICATOR);
    lv_obj_set_style_radius(claude_bar, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(claude_bar, 4, LV_PART_INDICATOR);

    // Claude projection line (compact, smaller font)
    claude_proj = lv_label_create(tab_u);
    lv_obj_align(claude_proj, LV_ALIGN_TOP_LEFT, 26, 44);
    lv_obj_set_style_text_font(claude_proj, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(claude_proj, pc(P().dim), 0);
    lv_label_set_text(claude_proj, "");

    codex_ico = lv_img_create(tab_u);
    lv_img_set_src(codex_ico, &codex_icon);
    lv_obj_align(codex_ico, LV_ALIGN_TOP_LEFT, 2, 64);
    codex_lbl = lv_label_create(tab_u);
    lv_obj_align(codex_lbl, LV_ALIGN_TOP_LEFT, 26, 66);
    lv_obj_set_style_text_color(codex_lbl, pc(P().codex), 0);
    lv_label_set_text(codex_lbl, "Codex --");

    codex_bar = lv_bar_create(tab_u);
    lv_obj_set_size(codex_bar, SCREEN_W - 56, 16);
    lv_obj_align(codex_bar, LV_ALIGN_TOP_LEFT, 2, 88);
    lv_bar_set_range(codex_bar, 0, 100);
    lv_bar_set_value(codex_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(codex_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(codex_bar, pc(P().codex), LV_PART_INDICATOR);
    lv_obj_set_style_radius(codex_bar, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(codex_bar, 4, LV_PART_INDICATOR);

    // Codex projection line (compact, smaller font)
    codex_proj = lv_label_create(tab_u);
    lv_obj_align(codex_proj, LV_ALIGN_TOP_LEFT, 26, 106);
    lv_obj_set_style_text_font(codex_proj, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(codex_proj, pc(P().dim), 0);
    lv_label_set_text(codex_proj, "");

    // Weekly reset countdown — key signal, shown once for the window.
    week_lbl = lv_label_create(tab_u);
    lv_obj_align(week_lbl, LV_ALIGN_TOP_LEFT, 2, 132);
    lv_obj_set_style_text_font(week_lbl, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(week_lbl, pc(P().dim), 0);
    lv_label_set_text(week_lbl, "");

    // Weekly utilization bars — below the reset countdown; color identifies provider.
    claude_week_bar = lv_bar_create(tab_u);
    lv_obj_set_size(claude_week_bar, 190, 8);
    lv_obj_align(claude_week_bar, LV_ALIGN_TOP_LEFT, 2, 152);
    lv_bar_set_range(claude_week_bar, 0, 100);
    lv_bar_set_value(claude_week_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(claude_week_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(claude_week_bar, pc(P().claude), LV_PART_INDICATOR);
    lv_obj_set_style_radius(claude_week_bar, 3, LV_PART_MAIN);
    lv_obj_set_style_radius(claude_week_bar, 3, LV_PART_INDICATOR);
    claude_week_val = lv_label_create(tab_u);
    lv_obj_align(claude_week_val, LV_ALIGN_TOP_LEFT, 196, 150);
    lv_obj_set_style_text_font(claude_week_val, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(claude_week_val, pc(P().claude), 0);
    lv_label_set_text(claude_week_val, "");

    codex_week_bar = lv_bar_create(tab_u);
    lv_obj_set_size(codex_week_bar, 190, 8);
    lv_obj_align(codex_week_bar, LV_ALIGN_TOP_LEFT, 2, 167);
    lv_bar_set_range(codex_week_bar, 0, 100);
    lv_bar_set_value(codex_week_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(codex_week_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(codex_week_bar, pc(P().codex), LV_PART_INDICATOR);
    lv_obj_set_style_radius(codex_week_bar, 3, LV_PART_MAIN);
    lv_obj_set_style_radius(codex_week_bar, 3, LV_PART_INDICATOR);
    codex_week_val = lv_label_create(tab_u);
    lv_obj_align(codex_week_val, LV_ALIGN_TOP_LEFT, 196, 165);
    lv_obj_set_style_text_font(codex_week_val, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(codex_week_val, pc(P().codex), 0);
    lv_label_set_text(codex_week_val, "");

    // ---- settings tab ----
    // Brightness
    set_bright_lbl = lv_label_create(tab_set);
    lv_obj_align(set_bright_lbl, LV_ALIGN_TOP_LEFT, 2, 2);
    lv_obj_set_style_text_color(set_bright_lbl, pc(P().fg), 0);
    lv_label_set_text(set_bright_lbl, "Brightness");

    set_bright_val = lv_label_create(tab_set);
    lv_obj_align(set_bright_val, LV_ALIGN_TOP_RIGHT, -2, 2);
    lv_obj_set_style_text_color(set_bright_val, pc(P().dim), 0);
    lv_label_set_text(set_bright_val, "100%");

    set_bright_slider = lv_slider_create(tab_set);
    lv_obj_set_size(set_bright_slider, SCREEN_W - 36, 12);
    lv_obj_align(set_bright_slider, LV_ALIGN_TOP_MID, 0, 24);
    lv_slider_set_range(set_bright_slider, 10, 100);
    lv_slider_set_value(set_bright_slider, settings_brightness(), LV_ANIM_OFF);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().accent), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().accent), LV_PART_KNOB);
    lv_obj_add_event_cb(set_bright_slider, bright_changed, LV_EVENT_VALUE_CHANGED, NULL);
    lv_obj_add_event_cb(set_bright_slider, bright_released, LV_EVENT_RELEASED, NULL);
    {
        char b[8]; snprintf(b, sizeof(b), "%d%%", settings_brightness());
        lv_label_set_text(set_bright_val, b);
    }

    // Theme (Dark <-> Light)
    set_theme_lbl = lv_label_create(tab_set);
    lv_obj_align(set_theme_lbl, LV_ALIGN_TOP_LEFT, 2, 50);
    lv_obj_set_style_text_color(set_theme_lbl, pc(P().fg), 0);
    lv_label_set_text(set_theme_lbl, "Theme: Dark");

    set_theme_sw = lv_switch_create(tab_set);
    lv_obj_align(set_theme_sw, LV_ALIGN_TOP_RIGHT, -2, 46);
    lv_obj_set_style_bg_color(set_theme_sw, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_theme_sw, pc(P().accent), LV_PART_INDICATOR | LV_STATE_CHECKED);
    if (settings_dark()) lv_obj_add_state(set_theme_sw, LV_STATE_CHECKED);
    lv_obj_add_event_cb(set_theme_sw, theme_toggled, LV_EVENT_VALUE_CHANGED, NULL);

    // Sleep
    set_sleep_lbl = lv_label_create(tab_set);
    lv_obj_align(set_sleep_lbl, LV_ALIGN_TOP_LEFT, 2, 84);
    lv_obj_set_style_text_color(set_sleep_lbl, pc(P().fg), 0);
    lv_label_set_text(set_sleep_lbl, "Sleep after");

    set_sleep_roller = lv_roller_create(tab_set);
    lv_roller_set_options(set_sleep_roller, SLEEP_OPTS, LV_ROLLER_MODE_NORMAL);
    lv_roller_set_visible_row_count(set_sleep_roller, 3);
    lv_obj_set_width(set_sleep_roller, 100);
    lv_obj_align(set_sleep_roller, LV_ALIGN_TOP_RIGHT, -2, 80);
    lv_roller_set_selected(set_sleep_roller, min_to_roller_idx(settings_sleep_min()), LV_ANIM_OFF);
    lv_obj_set_style_bg_color(set_sleep_roller, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_text_color(set_sleep_roller, pc(P().fg), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_sleep_roller, pc(P().accent), LV_PART_SELECTED);
    lv_obj_set_style_text_color(set_sleep_roller, pc(P().bg), LV_PART_SELECTED);
    lv_obj_add_event_cb(set_sleep_roller, sleep_changed, LV_EVENT_VALUE_CHANGED, NULL);

    // ---- offline banner (top layer) ----
    offline_banner = lv_label_create(lv_layer_top());
    lv_label_set_text(offline_banner, " hub offline ");
    lv_obj_set_style_bg_color(offline_banner, pc(P().crit), 0);
    lv_obj_set_style_bg_opa(offline_banner, LV_OPA_COVER, 0);
    lv_obj_set_style_text_color(offline_banner, pc(P().fg), 0);
    lv_obj_set_style_radius(offline_banner, 4, 0);
    lv_obj_set_style_pad_all(offline_banner, 3, 0);
    lv_obj_align(offline_banner, LV_ALIGN_BOTTOM_MID, 0, -2);
    lv_obj_add_flag(offline_banner, LV_OBJ_FLAG_HIDDEN);

    ui_apply_theme();
}

// Re-apply every theme-dependent style to existing widgets. Cheaper and less
// jarring than rebuilding the screen; preserves widget state and scroll pos.
void ui_apply_theme() {
    lv_label_set_text(set_theme_lbl, settings_dark() ? "Theme: Dark" : "Theme: Light");

    lv_obj_set_style_bg_color(scr_root, pc(P().bg), 0);
    lv_obj_set_style_text_color(scr_root, pc(P().fg), 0);

    lv_obj_set_style_bg_color(tabview, pc(P().bg), 0);
    style_tab_btns(tabview);
    lv_obj_set_style_bg_color(tab_s, pc(P().bg), 0);
    lv_obj_set_style_bg_color(tab_u, pc(P().bg), 0);
    lv_obj_set_style_bg_color(tab_set, pc(P().bg), 0);

    // sessions tab
    lv_obj_set_style_text_color(strip_lbl, pc(P().dim), 0);
    lv_obj_set_style_bg_color(list_obj, pc(P().bg), 0);
    lv_obj_set_style_text_color(footer, pc(P().dim), 0);
    for (int i = 0; i < MAX_SESSIONS; i++) {
        Row* r = &rows[i];
        if (r->active) {
            lv_obj_set_style_bg_color(r->cont, pc(r->waiting ? P().waitdk : P().panel), 0);
            lv_obj_set_style_text_color(r->name, pc(P().fg), 0);
            lv_obj_set_style_text_color(r->sym, status_color(r->status), 0);
        } else {
            lv_obj_set_style_bg_color(r->cont, pc(P().panel), 0);
            lv_obj_set_style_text_color(r->name, pc(P().fg), 0);
            lv_obj_set_style_text_color(r->sym, pc(P().dim), 0);
        }
    }

    // usage tab
    lv_obj_set_style_text_color(claude_lbl, pc(P().claude), 0);
    lv_obj_set_style_bg_color(claude_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(claude_bar, pc(P().claude), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(claude_week_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(claude_week_bar, pc(P().claude), LV_PART_INDICATOR);
    lv_obj_set_style_text_color(claude_week_val, pc(P().claude), 0);
    lv_obj_set_style_text_color(codex_lbl, pc(P().codex), 0);
    lv_obj_set_style_bg_color(codex_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(codex_bar, pc(P().codex), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(codex_week_bar, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(codex_week_bar, pc(P().codex), LV_PART_INDICATOR);
    lv_obj_set_style_text_color(codex_week_val, pc(P().codex), 0);
    // projection lines are recolored on next poll; default to dim for the swap
    lv_obj_set_style_text_color(claude_proj, pc(P().dim), 0);
    lv_obj_set_style_text_color(codex_proj, pc(P().dim), 0);
    lv_obj_set_style_text_color(week_lbl, pc(P().dim), 0);

    // settings tab
    lv_obj_set_style_text_color(set_bright_lbl, pc(P().fg), 0);
    lv_obj_set_style_text_color(set_bright_val, pc(P().dim), 0);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().accent), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(set_bright_slider, pc(P().accent), LV_PART_KNOB);
    lv_obj_set_style_text_color(set_theme_lbl, pc(P().fg), 0);
    lv_obj_set_style_bg_color(set_theme_sw, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_theme_sw, pc(P().accent), LV_PART_INDICATOR | LV_STATE_CHECKED);
    lv_obj_set_style_text_color(set_sleep_lbl, pc(P().fg), 0);
    lv_obj_set_style_bg_color(set_sleep_roller, pc(P().panel), LV_PART_MAIN);
    lv_obj_set_style_text_color(set_sleep_roller, pc(P().fg), LV_PART_MAIN);
    lv_obj_set_style_bg_color(set_sleep_roller, pc(P().accent), LV_PART_SELECTED);
    lv_obj_set_style_text_color(set_sleep_roller, pc(P().bg), LV_PART_SELECTED);

    // offline banner
    lv_obj_set_style_bg_color(offline_banner, pc(P().crit), 0);
    lv_obj_set_style_text_color(offline_banner, pc(P().fg), 0);
}

void ui_set_offline(bool offline) {
    if (offline) lv_obj_clear_flag(offline_banner, LV_OBJ_FLAG_HIDDEN);
    else         lv_obj_add_flag(offline_banner, LV_OBJ_FLAG_HIDDEN);
}

static bool is_codex(const char* tool) { return tool[0] == 'c' && tool[1] == 'o'; }

void ui_update(const StateModel* m) {
    char strip[64];
    char cstr[12], xstr[12];
    if (m->claude.ok) snprintf(cstr, sizeof(cstr), "%d%%", (int)(m->claude.pct * 100 + 0.5f));
    else              strlcpy(cstr, "--", sizeof(cstr));
    if (m->codex.ok)  snprintf(xstr, sizeof(xstr), "%d%%", (int)(m->codex.pct * 100 + 0.5f));
    else              strlcpy(xstr, "--", sizeof(xstr));
    snprintf(strip, sizeof(strip), "Claude %s   Codex %s", cstr, xstr);
    lv_label_set_text(strip_lbl, strip);

    int wait_n = 0, work_n = 0;
    for (int i = 0; i < MAX_SESSIONS; i++) {
        Row* r = &rows[i];
        if (i < m->count) {
            const Session* s = &m->sessions[i];
            strlcpy(r->id, s->id, sizeof(r->id));
            r->waiting = (s->status == ST_WAITING);
            r->status  = s->status;
            r->active  = true;

            // provider badge: real Claude / Codex logo
            lv_img_set_src(r->badge, is_codex(s->tool) ? &codex_icon : &claude_icon);

            lv_label_set_text(r->name, s->project);
            lv_obj_set_style_text_color(r->name, pc(P().fg), 0);

            // calm status symbol at the end (no flashing):
            //   waiting -> "!"   working -> circular refresh   idle -> "Zzz"
            if (s->status == ST_WAITING) {
                lv_label_set_text(r->sym, "!");
                wait_n++;
            } else if (s->status == ST_WORKING) {
                lv_label_set_text(r->sym, LV_SYMBOL_REFRESH);
                work_n++;
            } else {
                lv_label_set_text(r->sym, "Zzz");
            }
            lv_obj_set_style_text_color(r->sym, status_color(s->status), 0);

            // waiting rows get a static dark-amber tint so they stand out
            // without strobing; others use the normal panel bg.
            lv_obj_set_style_bg_color(r->cont,
                pc(r->waiting ? P().waitdk : P().panel), 0);
            lv_obj_set_style_bg_opa(r->cont, LV_OPA_COVER, 0);
            lv_obj_clear_flag(r->cont, LV_OBJ_FLAG_HIDDEN);
        } else {
            r->id[0] = 0;
            r->waiting = false;
            r->status = ST_IDLE;
            r->active = false;
            lv_obj_add_flag(r->cont, LV_OBJ_FLAG_HIDDEN);
        }
    }

    char foot[72];
    snprintf(foot, sizeof(foot), "%d working  %d waiting%s",
             work_n, wait_n, (m->total > m->count) ? "  +more" : "");
    lv_label_set_text(footer, foot);

    if (m->claude.ok) {
        int pct = (int)(m->claude.pct * 100 + 0.5f);
        lv_bar_set_value(claude_bar, pct, LV_ANIM_OFF);
        char rs[16];
        fmt_reset(m->claude.resetSec, rs, sizeof(rs));
        char c[56];
        snprintf(c, sizeof(c), "Claude %d%%   resets %s", pct, rs);
        lv_label_set_text(claude_lbl, c);

        char pj[24];
        lv_color_t pjc = projection_text(m->claude, pj, sizeof(pj));
        lv_label_set_text(claude_proj, pj);
        lv_obj_set_style_text_color(claude_proj, pjc, 0);
    } else {
        lv_bar_set_value(claude_bar, 0, LV_ANIM_OFF);
        lv_label_set_text(claude_lbl, "Claude --");
        lv_label_set_text(claude_proj, "");
    }
    if (m->codex.ok) {
        int cpc = (int)(m->codex.pct * 100 + 0.5f);
        lv_bar_set_value(codex_bar, cpc, LV_ANIM_OFF);
        char crs[16];
        fmt_reset(m->codex.resetSec, crs, sizeof(crs));
        char cc[56];
        snprintf(cc, sizeof(cc), "Codex %d%%   resets %s", cpc, crs);
        lv_label_set_text(codex_lbl, cc);

        char pj[24];
        lv_color_t pjc = projection_text(m->codex, pj, sizeof(pj));
        lv_label_set_text(codex_proj, pj);
        lv_obj_set_style_text_color(codex_proj, pjc, 0);
    } else {
        lv_bar_set_value(codex_bar, 0, LV_ANIM_OFF);
        lv_label_set_text(codex_lbl, "Codex --");
        lv_label_set_text(codex_proj, "");
    }

    update_week_bar(m->claude, claude_week_bar, claude_week_val);
    update_week_bar(m->codex,  codex_week_bar,  codex_week_val);

    // Weekly reset — prefer whichever provider reports it (claude first).
    int wsec = (m->claude.ok && m->claude.weekResetSec >= 0) ? m->claude.weekResetSec
             : (m->codex.ok  && m->codex.weekResetSec  >= 0) ? m->codex.weekResetSec
             : -1;
    if (wsec >= 0) {
        char wf[16];
        fmt_long(wsec, wf, sizeof(wf));
        char wl[40];
        snprintf(wl, sizeof(wl), "week resets in %s", wf);
        lv_label_set_text(week_lbl, wl);
    } else {
        lv_label_set_text(week_lbl, "");
    }
}
