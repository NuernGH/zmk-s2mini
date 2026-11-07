/*
 * Ekran 128 × 64 dla 60% na S2 mini (wg szkicu oled-szkic, teksty po angielsku):
 *  1. główny: godzina, warstwa, CPU/GPU (obciążenie + temp.), głośność, tryb gałki;
 *  2. GAME (warstwa z etykietą game_layer aktywna): duże temperatury CPU/GPU;
 *  3. zmiana trybu gałki: na ok. 1,5 s nazwa trybu i kropki;
 *  4. brak danych z PC: tylko warstwa i tryb gałki;
 *  5. porty COM (CON/BAK przełączają widok; nowy port pokazuje się sam na 3 s).
 * Stan sprawdza timer LVGL co 100 ms, więc nic nie dotyka LVGL spoza wątku ekranu.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <lvgl.h>

#include <zmk/display/status_screen.h>
#include <zmk/keymap.h>
#include <s2mini/status.h>

LV_FONT_DECLARE(s2m_font_9);
LV_FONT_DECLARE(s2m_font_11);
LV_FONT_DECLARE(s2m_font_14);
LV_FONT_DECLARE(s2m_font_20);

#define W 128
#define H 64
#define BAR_H 12
#define POPUP_MS 1500
#define PORTS_POPUP_MS 3000
#define PORT_ROWS 4
#define PC_TIMEOUT_MS CONFIG_S2MINI_STATUS_PC_TIMEOUT_MS

#define GAME_LAYER_NODE DT_NODELABEL(game_layer)

static lv_color_t fg, bg;

enum view { VIEW_MAIN, VIEW_GAME, VIEW_KNOB, VIEW_NO_PC, VIEW_PORTS, VIEW_COUNT };

static lv_obj_t *views[VIEW_COUNT];

/* 1. główny */
static lv_obj_t *m_time, *m_layer, *m_knob;
struct meter {
    lv_obj_t *fill, *pct, *temp;
};
static struct meter m_cpu, m_gpu, m_vol;
#define METER_X 22
#define METER_W 52

/* 2. GAME */
static lv_obj_t *g_cpu_temp, *g_cpu_load, *g_gpu_temp, *g_gpu_load, *g_time, *g_vol, *g_knob;

/* 3. tryb gałki */
static lv_obj_t *k_name;
#define MAX_DOTS 8
static lv_obj_t *k_dots[MAX_DOTS];

/* 4. bez PC */
static lv_obj_t *n_layer, *n_knob;

/* 5. porty COM */
static lv_obj_t *p_count, *p_rows[PORT_ROWS];

static lv_obj_t *box(lv_obj_t *parent, int x, int y, int w, int h, bool filled, int border) {
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_bg_color(o, filled ? fg : bg, 0);
    lv_obj_set_style_bg_opa(o, filled ? LV_OPA_COVER : LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_color(o, fg, 0);
    lv_obj_set_style_border_width(o, border, 0);
    lv_obj_set_style_radius(o, 0, 0);
    lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *label(lv_obj_t *parent, const lv_font_t *font, bool inverted, lv_align_t align,
                       int x, int y, const char *text) {
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, inverted ? bg : fg, 0);
    lv_label_set_text(l, text);
    lv_obj_align(l, align, x, y);
    return l;
}

static lv_obj_t *top_bar(lv_obj_t *parent) { return box(parent, 0, 0, W, BAR_H, true, 0); }

static void meter_create(struct meter *m, lv_obj_t *parent, int y, const char *name, bool temp) {
    label(parent, &s2m_font_9, false, LV_ALIGN_TOP_LEFT, 0, y, name);
    box(parent, METER_X, y + 1, METER_W, 8, false, 1);
    m->fill = box(parent, METER_X + 2, y + 3, 0, 4, true, 0);
    m->pct = label(parent, &s2m_font_9, false, LV_ALIGN_TOP_RIGHT, temp ? -27 : 0, y, "");
    m->temp = temp ? label(parent, &s2m_font_9, false, LV_ALIGN_TOP_RIGHT, 0, y, "") : NULL;
}

static void meter_set(struct meter *m, bool valid, int pct, int temp_c, const char *alt) {
    lv_obj_set_width(m->fill, valid ? (METER_W - 4) * pct / 100 : 0);
    if (alt != NULL) {
        lv_label_set_text(m->pct, alt);
    } else if (valid) {
        lv_label_set_text_fmt(m->pct, "%d%%", pct);
    } else {
        lv_label_set_text(m->pct, "--");
    }
    if (m->temp != NULL) {
        if (valid) {
            lv_label_set_text_fmt(m->temp, "%d\xC2\xB0", temp_c);
        } else {
            lv_label_set_text(m->temp, "");
        }
    }
}

static void create_main(lv_obj_t *v) {
    top_bar(v);
    m_time = label(v, &s2m_font_11, true, LV_ALIGN_TOP_LEFT, 2, 0, "");
    m_layer = label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
    meter_create(&m_cpu, v, 15, "CPU", true);
    meter_create(&m_gpu, v, 27, "GPU", true);
    meter_create(&m_vol, v, 39, "VOL", false);
    m_knob = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
}

static void create_game(lv_obj_t *v) {
    box(v, 0, 0, W, 17, true, 0);
    label(v, &s2m_font_14, true, LV_ALIGN_TOP_LEFT, 2, 0, "GAME");
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 3, "WIN x");
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_LEFT, 0, 19, "CPU");
    g_cpu_temp = label(v, &s2m_font_20, false, LV_ALIGN_TOP_LEFT, 0, 27, "");
    g_cpu_load = label(v, &s2m_font_9, false, LV_ALIGN_TOP_RIGHT, -68, 19, "");
    box(v, 63, 19, 1, 29, true, 0);
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_LEFT, 68, 19, "GPU");
    g_gpu_temp = label(v, &s2m_font_20, false, LV_ALIGN_TOP_LEFT, 68, 27, "");
    g_gpu_load = label(v, &s2m_font_9, false, LV_ALIGN_TOP_RIGHT, 0, 19, "");
    box(v, 0, 50, W, 1, true, 0);
    g_time = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
    g_vol = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 34, 0, "");
    g_knob = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_RIGHT, 0, 0, "");
}

static void create_knob(lv_obj_t *v) {
    box(v, 0, 0, W, H, false, 1);
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_MID, 0, 3, "KNOB");
    k_name = label(v, &s2m_font_20, false, LV_ALIGN_TOP_MID, 0, 13, "");
    for (int i = 0; i < MAX_DOTS; i++) {
        k_dots[i] = box(v, 0, 38, 8, 8, false, 1);
        lv_obj_set_style_radius(k_dots[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_add_flag(k_dots[i], LV_OBJ_FLAG_HIDDEN);
    }
    label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_MID, 0, -3, "press knob: next");
}

static void create_no_pc(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_11, true, LV_ALIGN_TOP_LEFT, 2, 0, "--:--");
    n_layer = label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
    label(v, &s2m_font_11, false, LV_ALIGN_TOP_MID, 0, 15, "no data from PC");
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_MID, 0, 30, "start the app");
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_MID, 0, 40, "on your PC");
    n_knob = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
}

static void create_ports(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 2, 1, "COM PORTS");
    p_count = label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
    for (int i = 0; i < PORT_ROWS; i++) {
        p_rows[i] = label(v, &s2m_font_9, false, LV_ALIGN_TOP_LEFT, 0, 14 + i * 12, "");
        lv_label_set_long_mode(p_rows[i], LV_LABEL_LONG_MODE_CLIP);
        lv_obj_set_width(p_rows[i], W);
    }
}

static void update_ports(void) {
    static char list[PORT_ROWS][S2MINI_PORT_TEXT];
    int64_t age = INT64_MAX;
    int count = -1;

#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    count = s2mini_ports_get(list, PORT_ROWS, &age, NULL);
#endif

    for (int i = 0; i < PORT_ROWS; i++) {
        lv_label_set_text(p_rows[i], "");
    }
    if (count < 0 || age > PC_TIMEOUT_MS) {
        lv_label_set_text(p_count, "");
        lv_label_set_text(p_rows[1], "no data from PC");
        return;
    }
    if (count == 0) {
        lv_label_set_text(p_count, "0");
        lv_label_set_text(p_rows[1], "no COM ports");
        return;
    }
    lv_label_set_text_fmt(p_count, "%d", count);
    for (int i = 0; i < MIN(count, PORT_ROWS); i++) {
        lv_label_set_text(p_rows[i], list[i]);
    }
    if (count > PORT_ROWS) {
        lv_label_set_text_fmt(p_rows[PORT_ROWS - 1], "... +%d more", count - (PORT_ROWS - 1));
    }
}

static bool ports_wanted(void) {
#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    int64_t added_at = 0;
    static char dummy[1][S2MINI_PORT_TEXT];
    s2mini_ports_get(dummy, 0, NULL, &added_at);
    if (added_at != 0 && k_uptime_get() - added_at < PORTS_POPUP_MS) {
        return true;
    }
#endif
    return s2mini_screen_view() == S2MINI_VIEW_PORTS;
}

static bool game_active(void) {
#if DT_NODE_EXISTS(GAME_LAYER_NODE)
    return zmk_keymap_layer_active(DT_NODE_CHILD_IDX(GAME_LAYER_NODE));
#else
    return false;
#endif
}

static const char *layer_name(void) {
    zmk_keymap_layer_index_t index = zmk_keymap_highest_layer_active();
    const char *name = zmk_keymap_layer_name(zmk_keymap_layer_index_to_id(index));
    return (name != NULL && name[0] != '\0') ? name : "?";
}

static const char *knob_name(void) {
    return s2mini_knob_mode_count() > 0 ? s2mini_knob_mode_name(s2mini_knob_mode_index()) : "";
}

static void show(enum view which) {
    for (int i = 0; i < VIEW_COUNT; i++) {
        if (i == which) {
            lv_obj_clear_flag(views[i], LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_add_flag(views[i], LV_OBJ_FLAG_HIDDEN);
        }
    }
}

static void update_cb(lv_timer_t *timer) {
    char buf[32];
    struct s2mini_pc_data pc = {0};
    int64_t age = INT64_MAX;
    bool have_pc = false;

#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    have_pc = s2mini_pc_data_get(&pc, &age) && age < PC_TIMEOUT_MS;
#endif

    int64_t changed = s2mini_knob_mode_changed_at();
    bool popup = s2mini_knob_mode_count() > 0 && changed != 0 &&
                 k_uptime_get() - changed < POPUP_MS;

    snprintf(buf, sizeof(buf), "%s  USB", layer_name());
    const char *knob = knob_name();

    if (popup) {
        int count = MIN(s2mini_knob_mode_count(), MAX_DOTS);
        int current = s2mini_knob_mode_index();
        int x0 = (W - (count * 16 - 8)) / 2;
        lv_label_set_text(k_name, knob);
        for (int i = 0; i < MAX_DOTS; i++) {
            if (i < count) {
                lv_obj_set_pos(k_dots[i], x0 + i * 16, 38);
                lv_obj_set_style_bg_opa(k_dots[i], i == current ? LV_OPA_COVER : LV_OPA_TRANSP,
                                        0);
                lv_obj_set_style_bg_color(k_dots[i], fg, 0);
                lv_obj_clear_flag(k_dots[i], LV_OBJ_FLAG_HIDDEN);
            } else {
                lv_obj_add_flag(k_dots[i], LV_OBJ_FLAG_HIDDEN);
            }
        }
        show(VIEW_KNOB);
        return;
    }

    if (ports_wanted()) {
        update_ports();
        show(VIEW_PORTS);
        return;
    }

    if (!have_pc) {
        lv_label_set_text(n_layer, game_active() ? "GAME  USB" : buf);
        lv_label_set_text_fmt(n_knob, "knob: %s", knob);
        show(VIEW_NO_PC);
        return;
    }

    bool cpu = pc.flags & S2MINI_PC_CPU;
    bool gpu = pc.flags & S2MINI_PC_GPU;
    bool vol = pc.flags & S2MINI_PC_VOLUME;
    bool muted = pc.flags & S2MINI_PC_MUTED;
    char time_txt[8] = "--:--";
    if (pc.flags & S2MINI_PC_TIME) {
        snprintf(time_txt, sizeof(time_txt), "%02d:%02d", pc.hour, pc.minute);
    }

    if (game_active()) {
        if (cpu) {
            lv_label_set_text_fmt(g_cpu_temp, "%d\xC2\xB0", pc.cpu_temp);
            lv_label_set_text_fmt(g_cpu_load, "%d%%", pc.cpu_load);
        } else {
            lv_label_set_text(g_cpu_temp, "--");
            lv_label_set_text(g_cpu_load, "");
        }
        if (gpu) {
            lv_label_set_text_fmt(g_gpu_temp, "%d\xC2\xB0", pc.gpu_temp);
            lv_label_set_text_fmt(g_gpu_load, "%d%%", pc.gpu_load);
        } else {
            lv_label_set_text(g_gpu_temp, "--");
            lv_label_set_text(g_gpu_load, "");
        }
        lv_label_set_text(g_time, time_txt);
        if (muted) {
            lv_label_set_text(g_vol, "mute");
        } else if (vol) {
            lv_label_set_text_fmt(g_vol, "vol %d%%", pc.volume);
        } else {
            lv_label_set_text(g_vol, "");
        }
        /* Na dole jest mało miejsca: pierwsze 3 litery nazwy trybu, małymi literami. */
        snprintf(buf, sizeof(buf), "knob:%.3s", knob);
        for (char *c = buf; *c; c++) {
            if (*c >= 'A' && *c <= 'Z') {
                *c += 'a' - 'A';
            }
        }
        lv_label_set_text(g_knob, buf);
        show(VIEW_GAME);
        return;
    }

    lv_label_set_text(m_time, time_txt);
    lv_label_set_text(m_layer, buf);
    meter_set(&m_cpu, cpu, pc.cpu_load, pc.cpu_temp, NULL);
    meter_set(&m_gpu, gpu, pc.gpu_load, pc.gpu_temp, NULL);
    meter_set(&m_vol, vol, muted ? 0 : pc.volume, 0, muted ? "MUTE" : NULL);
    lv_label_set_text_fmt(m_knob, "knob: %s", knob);
    show(VIEW_MAIN);
}

lv_obj_t *zmk_display_status_screen(void) {
    lv_obj_t *screen = lv_obj_create(NULL);
    fg = lv_obj_get_style_text_color(screen, LV_PART_MAIN);
    bg = lv_obj_get_style_bg_color(screen, LV_PART_MAIN);
    lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    for (int i = 0; i < VIEW_COUNT; i++) {
        views[i] = box(screen, 0, 0, W, H, false, 0);
    }
    create_main(views[VIEW_MAIN]);
    create_game(views[VIEW_GAME]);
    create_knob(views[VIEW_KNOB]);
    create_no_pc(views[VIEW_NO_PC]);
    create_ports(views[VIEW_PORTS]);

    update_cb(NULL);
    lv_timer_create(update_cb, 100, NULL);
    return screen;
}
