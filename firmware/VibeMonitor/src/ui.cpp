#include <Arduino.h>
#include "ui.h"
#include "config.h"
#include "icons.h"
#include <lvgl.h>
#include <stdio.h>
#include <string.h>

static lv_obj_t* tabview;
static lv_obj_t* strip_lbl;
static lv_obj_t* footer;
static lv_obj_t* offline_banner;
static lv_obj_t* claude_bar;
static lv_obj_t* claude_lbl;
static lv_obj_t* codex_lbl;
static lv_obj_t* codex_bar;
static AckCb g_ack = NULL;

// Human-friendly reset countdown: ">=1h" -> "4h 47m", "<1h" -> "47m".
static void fmt_reset(uint32_t resetSec, char* out, size_t n) {
    uint32_t mins = resetSec / 60;
    if (mins >= 60) snprintf(out, n, "%luh %lum",
                             (unsigned long)(mins / 60), (unsigned long)(mins % 60));
    else            snprintf(out, n, "%lum", (unsigned long)mins);
}

struct Row {
    lv_obj_t* cont;
    lv_obj_t* badge;     // provider logo image (Claude / Codex)
    lv_obj_t* name;
    lv_obj_t* sym;       // status symbol at end: ! waiting / refresh working / Zzz idle
    char id[40];
    bool waiting;
};
static Row rows[MAX_SESSIONS];

static lv_color_t status_color(SessStatus s) {
    switch (s) {
        case ST_WAITING: return lv_color_hex(C_WAIT);
        case ST_WORKING: return lv_color_hex(C_WORK);
        default:         return lv_color_hex(C_IDLE);
    }
}

static void row_clicked(lv_event_t* e) {
    Row* r = (Row*)lv_event_get_user_data(e);
    if (g_ack && r->id[0]) g_ack(r->id);
}

void ui_set_ack_cb(AckCb cb) { g_ack = cb; }

// ---- terminal-style helpers ----------------------------------------------
static void style_tab_btns(lv_obj_t* tv) {
    lv_obj_t* btns = lv_tabview_get_tab_btns(tv);
    lv_obj_set_style_bg_color(btns, lv_color_hex(C_BG), 0);
    lv_obj_set_style_text_color(btns, lv_color_hex(C_DIM), 0);
    lv_obj_set_style_text_color(btns, lv_color_hex(C_ACCENT), LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_border_color(btns, lv_color_hex(C_ACCENT), LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_text_font(btns, &lv_font_montserrat_14, 0);
}

void ui_init() {
    lv_obj_t* scr = lv_scr_act();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, lv_color_hex(C_BG), 0);
    lv_obj_set_style_text_color(scr, lv_color_hex(C_FG), 0);

    tabview = lv_tabview_create(scr, LV_DIR_TOP, 26);
    lv_obj_set_style_bg_color(tabview, lv_color_hex(C_BG), 0);
    style_tab_btns(tabview);
    lv_obj_t* tab_s = lv_tabview_add_tab(tabview, "SESSIONS");
    lv_obj_t* tab_u = lv_tabview_add_tab(tabview, "USAGE");
    lv_obj_set_style_bg_color(tab_s, lv_color_hex(C_BG), 0);
    lv_obj_set_style_bg_color(tab_u, lv_color_hex(C_BG), 0);
    lv_obj_set_style_pad_all(tab_s, 2, 0);
    lv_obj_set_style_pad_all(tab_u, 6, 0);

    // ---- sessions tab : top usage strip ----
    strip_lbl = lv_label_create(tab_s);
    lv_obj_align(strip_lbl, LV_ALIGN_TOP_LEFT, 2, 0);
    lv_obj_set_style_text_color(strip_lbl, lv_color_hex(C_DIM), 0);
    lv_label_set_text(strip_lbl, "Claude --   Codex --");

    // ---- scrollable list of session rows ----
    lv_obj_t* list = lv_obj_create(tab_s);
    lv_obj_set_size(list, SCREEN_W - 12, 158);
    lv_obj_align(list, LV_ALIGN_TOP_MID, 0, 18);
    lv_obj_set_flex_flow(list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(list, 3, 0);
    lv_obj_set_style_pad_all(list, 3, 0);
    lv_obj_set_style_bg_color(list, lv_color_hex(C_BG), 0);
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
        lv_obj_set_style_bg_color(r->cont, lv_color_hex(C_PANEL), 0);
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
        lv_obj_set_style_text_color(r->name, lv_color_hex(C_FG), 0);
        lv_label_set_text(r->name, "");

        r->sym = lv_label_create(r->cont);
        lv_obj_set_style_text_color(r->sym, lv_color_hex(C_DIM), 0);
        lv_label_set_text(r->sym, "");

        r->id[0] = 0;
        r->waiting = false;
    }

    footer = lv_label_create(tab_s);
    lv_obj_align(footer, LV_ALIGN_BOTTOM_LEFT, 2, 0);
    lv_obj_set_style_text_color(footer, lv_color_hex(C_DIM), 0);
    lv_label_set_text(footer, "");

    // ---- usage tab ----
    lv_obj_t* claude_ico = lv_img_create(tab_u);
    lv_img_set_src(claude_ico, &claude_icon);
    lv_obj_align(claude_ico, LV_ALIGN_TOP_LEFT, 2, 2);
    claude_lbl = lv_label_create(tab_u);
    lv_obj_align(claude_lbl, LV_ALIGN_TOP_LEFT, 26, 4);
    lv_obj_set_style_text_color(claude_lbl, lv_color_hex(C_CLAUDE), 0);
    lv_label_set_text(claude_lbl, "Claude --");

    claude_bar = lv_bar_create(tab_u);
    lv_obj_set_size(claude_bar, SCREEN_W - 56, 16);
    lv_obj_align(claude_bar, LV_ALIGN_TOP_LEFT, 2, 28);
    lv_bar_set_range(claude_bar, 0, 100);
    lv_bar_set_value(claude_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(claude_bar, lv_color_hex(C_PANEL), LV_PART_MAIN);
    lv_obj_set_style_bg_color(claude_bar, lv_color_hex(C_CLAUDE), LV_PART_INDICATOR);
    lv_obj_set_style_radius(claude_bar, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(claude_bar, 4, LV_PART_INDICATOR);

    lv_obj_t* codex_ico = lv_img_create(tab_u);
    lv_img_set_src(codex_ico, &codex_icon);
    lv_obj_align(codex_ico, LV_ALIGN_TOP_LEFT, 2, 56);
    codex_lbl = lv_label_create(tab_u);
    lv_obj_align(codex_lbl, LV_ALIGN_TOP_LEFT, 26, 58);
    lv_obj_set_style_text_color(codex_lbl, lv_color_hex(C_CODEX), 0);
    lv_label_set_text(codex_lbl, "Codex --");

    codex_bar = lv_bar_create(tab_u);
    lv_obj_set_size(codex_bar, SCREEN_W - 56, 16);
    lv_obj_align(codex_bar, LV_ALIGN_TOP_LEFT, 2, 82);
    lv_bar_set_range(codex_bar, 0, 100);
    lv_bar_set_value(codex_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(codex_bar, lv_color_hex(C_PANEL), LV_PART_MAIN);
    lv_obj_set_style_bg_color(codex_bar, lv_color_hex(C_CODEX), LV_PART_INDICATOR);
    lv_obj_set_style_radius(codex_bar, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(codex_bar, 4, LV_PART_INDICATOR);

    // ---- offline banner (top layer) ----
    offline_banner = lv_label_create(lv_layer_top());
    lv_label_set_text(offline_banner, " hub offline ");
    lv_obj_set_style_bg_color(offline_banner, lv_color_hex(C_CRIT), 0);
    lv_obj_set_style_bg_opa(offline_banner, LV_OPA_COVER, 0);
    lv_obj_set_style_text_color(offline_banner, lv_color_hex(C_FG), 0);
    lv_obj_set_style_radius(offline_banner, 4, 0);
    lv_obj_set_style_pad_all(offline_banner, 3, 0);
    lv_obj_align(offline_banner, LV_ALIGN_BOTTOM_MID, 0, -2);
    lv_obj_add_flag(offline_banner, LV_OBJ_FLAG_HIDDEN);
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

            // provider badge: real Claude / Codex logo
            lv_img_set_src(r->badge, is_codex(s->tool) ? &codex_icon : &claude_icon);

            lv_label_set_text(r->name, s->project);
            lv_obj_set_style_text_color(r->name, lv_color_hex(C_FG), 0);

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
                lv_color_hex(r->waiting ? C_WAITDK : C_PANEL), 0);
            lv_obj_set_style_bg_opa(r->cont, LV_OPA_COVER, 0);
            lv_obj_clear_flag(r->cont, LV_OBJ_FLAG_HIDDEN);
        } else {
            r->id[0] = 0;
            r->waiting = false;
            lv_obj_add_flag(r->cont, LV_OBJ_FLAG_HIDDEN);
        }
    }

    char foot[72];
    snprintf(foot, sizeof(foot), "%d working  %d waiting%s",
             work_n, wait_n, (m->total > m->count) ? "  +more" : "");
    lv_label_set_text(footer, foot);

    if (m->claude.ok) {
        int pc = (int)(m->claude.pct * 100 + 0.5f);
        lv_bar_set_value(claude_bar, pc, LV_ANIM_OFF);
        char rs[16];
        fmt_reset(m->claude.resetSec, rs, sizeof(rs));
        char c[56];
        snprintf(c, sizeof(c), "Claude %d%%   resets %s", pc, rs);
        lv_label_set_text(claude_lbl, c);
    } else {
        lv_bar_set_value(claude_bar, 0, LV_ANIM_OFF);
        lv_label_set_text(claude_lbl, "Claude --");
    }
    if (m->codex.ok) {
        int cpc = (int)(m->codex.pct * 100 + 0.5f);
        lv_bar_set_value(codex_bar, cpc, LV_ANIM_OFF);
        char crs[16];
        fmt_reset(m->codex.resetSec, crs, sizeof(crs));
        char cc[56];
        snprintf(cc, sizeof(cc), "Codex %d%%   resets %s", cpc, crs);
        lv_label_set_text(codex_lbl, cc);
    } else {
        lv_bar_set_value(codex_bar, 0, LV_ANIM_OFF);
        lv_label_set_text(codex_lbl, "Codex --");
    }
}
