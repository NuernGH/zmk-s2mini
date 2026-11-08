/*
 * Ekran 128 × 64 dla 60% na S2 mini (wg szkicu oled-szkic, teksty po angielsku):
 *  1. główny: godzina, warstwa, CPU/GPU (obciążenie + temp.), głośność, tryb gałki;
 *  2. GAME (warstwa z etykietą game_layer aktywna): duże temperatury CPU/GPU;
 *  3. zmiana trybu gałki: na ok. 1,5 s nazwa trybu i kropki;
 *  4. brak danych z PC: tylko warstwa i tryb gałki;
 *  5. porty COM (CON/BAK przełączają widok; nowy port pokazuje się sam na 3 s);
 *  6. ściąga warstwy FN (gdy FN jest najwyższą aktywną warstwą);
 *  7. minutnik i 8. ustawienia (gałka steruje ekranem, PUSH zatwierdza);
 *  9. „TIME UP”, gdy minutnik dobiegnie końca.
 * Pasek u góry: godzina, Caps / Num Lock (A, 1), pozostały czas minutnika, warstwa.
 * Stan sprawdza timer LVGL co 100 ms, więc nic nie dotyka LVGL spoza wątku ekranu.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <lvgl.h>

#include <zephyr/device.h>
#include <zephyr/drivers/display.h>
#include <zmk/display/status_screen.h>
#include <zmk/keymap.h>
#include <zmk/hid_indicators.h>
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
#define MEDIA_POPUP_MS 4000
#define PORT_ROWS 4
#define PC_TIMEOUT_MS CONFIG_S2MINI_STATUS_PC_TIMEOUT_MS

#define GAME_LAYER_NODE DT_NODELABEL(game_layer)

static lv_color_t fg, bg;

enum view {
    VIEW_MAIN,
    VIEW_GAME,
    VIEW_KNOB,
    VIEW_NO_PC,
    VIEW_PORTS,
    VIEW_FN,
    VIEW_TIMER,
    VIEW_SETTINGS,
    VIEW_DONE,
    VIEW_MEDIA,
    VIEW_COUNT
};

#define FN_LAYER_NAME "FN"
#define HID_LED_NUM BIT(0)
#define HID_LED_CAPS BIT(1)

/* Pasek u góry widoku głównego i „bez PC”. */
struct status_bar {
    lv_obj_t *time, *caps, *num, *timer, *layer;
};
static struct status_bar bar_main, bar_no_pc;

static lv_obj_t *views[VIEW_COUNT];

/* 1. główny */
static lv_obj_t *m_knob;
struct meter {
    lv_obj_t *fill, *pct, *temp;
};
static struct meter m_cpu, m_gpu, m_igpu, m_vol;
static lv_obj_t *m_igpu_row[4];
#define METER_X 22
#define METER_W 52

/* 2. GAME */
static lv_obj_t *g_cpu_temp, *g_cpu_load, *g_gpu_temp, *g_gpu_load, *g_time, *g_vol, *g_knob;

/* 3. tryb gałki */
static lv_obj_t *k_name;
#define MAX_DOTS 8
static lv_obj_t *k_dots[MAX_DOTS];

static lv_obj_t *m_wpm;

/* 4. bez PC */
static lv_obj_t *n_knob, *n_wpm;

/* 7. minutnik */
static lv_obj_t *t_state, *t_time, *t_hint;

/* 8. ustawienia */
struct menu_row {
    lv_obj_t *box, *name, *value;
};
static struct menu_row s_rows[S2MINI_SET_COUNT];
static lv_obj_t *s_hint;

/* 9. koniec minutnika */
static lv_obj_t *d_box, *d_title, *d_hint;

/* 10. co gra + sieć */
static lv_obj_t *md_state, *md_title, *md_artist, *md_net;

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

/* Mały wskaźnik w pasku: czarne pole z jasną literą (A = Caps Lock, 1 = Num Lock). */
static lv_obj_t *indicator(lv_obj_t *parent, int x, const char *text) {
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_pos(o, x, 1);
    lv_obj_set_size(o, 9, 10);
    lv_obj_set_style_bg_color(o, bg, 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    label(o, &s2m_font_9, false, LV_ALIGN_CENTER, 0, 0, text);
    lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
    return o;
}

static void status_bar_create(struct status_bar *b, lv_obj_t *parent) {
    top_bar(parent);
    b->time = label(parent, &s2m_font_11, true, LV_ALIGN_TOP_LEFT, 2, 0, "--:--");
    b->caps = indicator(parent, 37, "A");
    b->num = indicator(parent, 47, "1");
    b->timer = label(parent, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 60, 1, "");
    b->layer = label(parent, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
}

static void set_hidden(lv_obj_t *o, bool hidden) {
    if (hidden) {
        lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_clear_flag(o, LV_OBJ_FLAG_HIDDEN);
    }
}

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
    status_bar_create(&bar_main, v);
    /* Wiersze co 10 px: CPU, GPU (karta), IGP (Intel, gdy PC go przysyła), VOL. */
    meter_create(&m_cpu, v, 13, "CPU", true);
    meter_create(&m_gpu, v, 23, "GPU", true);
    uint32_t before = lv_obj_get_child_count(v);
    meter_create(&m_igpu, v, 33, "IGP", false);
    for (uint32_t i = 0; i < 4 && before + i < lv_obj_get_child_count(v); i++) {
        m_igpu_row[i] = lv_obj_get_child(v, before + i);
    }
    meter_create(&m_vol, v, 43, "VOL", false);
    m_knob = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
    m_wpm = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_RIGHT, 0, 0, "");
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
    status_bar_create(&bar_no_pc, v);
    label(v, &s2m_font_11, false, LV_ALIGN_TOP_MID, 0, 15, "no data from PC");
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_MID, 0, 30, "start the app");
    label(v, &s2m_font_9, false, LV_ALIGN_TOP_MID, 0, 40, "on your PC");
    n_knob = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
    n_wpm = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_RIGHT, 0, 0, "");
}

/* Ściąga warstwy FN (zgodna z keymapą s2mini_60.keymap). */
static void create_fn(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 2, 1, "FN LAYER");
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "\\ Studio");
    static const char *const rows[] = {
        "1-= F1-F12   Esc `",
        "IJKL arrows  BS Del",
        "U O PgUp/Dn  P PrtSc",
        "H ; Home/End  G GAME",
    };
    for (int i = 0; i < ARRAY_SIZE(rows); i++) {
        label(v, &s2m_font_9, false, LV_ALIGN_TOP_LEFT, 0, 14 + i * 12, rows[i]);
    }
}

static void create_timer(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 2, 1, "TIMER");
    t_state = label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
    t_time = label(v, &s2m_font_20, false, LV_ALIGN_TOP_MID, 0, 18, "");
    t_hint = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_MID, 0, 0, "");
}

static const char *const setting_names[S2MINI_SET_COUNT] = {"Brightness", "Invert", "Clock",
                                                            "WPM"};

static void create_settings(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 2, 1, "SETTINGS");
    for (int i = 0; i < S2MINI_SET_COUNT; i++) {
        struct menu_row *r = &s_rows[i];
        r->box = box(v, 0, 12 + i * 10, W, 10, false, 0);
        r->name = label(r->box, &s2m_font_9, false, LV_ALIGN_LEFT_MID, 2, 0, setting_names[i]);
        r->value = label(r->box, &s2m_font_9, false, LV_ALIGN_RIGHT_MID, -2, 0, "");
    }
    s_hint = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_MID, 0, 0, "");
}

static void create_done(lv_obj_t *v) {
    d_box = box(v, 0, 0, W, H, true, 0);
    d_title = label(v, &s2m_font_20, true, LV_ALIGN_TOP_MID, 0, 12, "TIME UP");
    d_hint = label(v, &s2m_font_9, true, LV_ALIGN_BOTTOM_MID, 0, -6, "press knob");
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

static void create_media(lv_obj_t *v) {
    top_bar(v);
    label(v, &s2m_font_9, true, LV_ALIGN_TOP_LEFT, 2, 1, "NOW PLAYING");
    md_state = label(v, &s2m_font_9, true, LV_ALIGN_TOP_RIGHT, -2, 1, "");
    md_title = label(v, &s2m_font_14, false, LV_ALIGN_TOP_LEFT, 0, 14, "");
    lv_obj_set_width(md_title, W);
    lv_label_set_long_mode(md_title, LV_LABEL_LONG_MODE_SCROLL_CIRCULAR);
    md_artist = label(v, &s2m_font_11, false, LV_ALIGN_TOP_LEFT, 0, 32, "");
    lv_obj_set_width(md_artist, W);
    lv_label_set_long_mode(md_artist, LV_LABEL_LONG_MODE_SCROLL_CIRCULAR);
    md_net = label(v, &s2m_font_9, false, LV_ALIGN_BOTTOM_LEFT, 0, 0, "");
}

/* Ustawia tekst tylko przy zmianie, bo każde ustawienie restartuje przewijanie. */
static void set_text_if_changed(lv_obj_t *l, const char *text) {
    if (strcmp(lv_label_get_text(l), text) != 0) {
        lv_label_set_text(l, text);
    }
}

/* KB/s → "850K" / "1.2M" / "12M". */
static void fmt_rate(char *out, size_t n, unsigned kbs) {
    if (kbs < 1000) {
        snprintf(out, n, "%uK", kbs);
    } else if (kbs < 10000) {
        snprintf(out, n, "%u.%uM", kbs / 1000, (kbs % 1000) / 100);
    } else {
        snprintf(out, n, "%uM", MIN(kbs / 1000, 999u));
    }
}

static void update_media(const struct s2mini_pc_data *pc, bool have_pc) {
    struct s2mini_media m = {0};
    int64_t age = INT64_MAX;
    bool ok = false;
    char net[40], down[8], up[8];

#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    ok = s2mini_media_get(&m, &age) && age < PC_TIMEOUT_MS;
#endif
    if (!have_pc) {
        set_text_if_changed(md_state, "");
        set_text_if_changed(md_title, "no data from PC");
        set_text_if_changed(md_artist, "");
    } else if (!ok || m.status == S2MINI_MEDIA_NONE || m.title[0] == '\0') {
        set_text_if_changed(md_state, "");
        set_text_if_changed(md_title, "nothing playing");
        set_text_if_changed(md_artist, "");
    } else {
        set_text_if_changed(md_state, m.status == S2MINI_MEDIA_PLAYING ? "PLAY" : "PAUSE");
        set_text_if_changed(md_title, m.title);
        set_text_if_changed(md_artist, m.artist);
    }
    if (have_pc && (pc->flags & S2MINI_PC_NET)) {
        fmt_rate(down, sizeof(down), pc->net_down);
        fmt_rate(up, sizeof(up), pc->net_up);
        snprintf(net, sizeof(net), "down %s/s  up %s/s", down, up);
        set_text_if_changed(md_net, net);
    } else {
        set_text_if_changed(md_net, "");
    }
}

/* Nowy utwór pokazuje okienko „co gra” na kilka sekund. */
static bool media_popup(void) {
#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    struct s2mini_media m;
    int64_t age;
    if (s2mini_media_get(&m, &age) && m.changed_at != 0 &&
        k_uptime_get() - m.changed_at < MEDIA_POPUP_MS) {
        return true;
    }
#endif
    return false;
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

static void fmt_clock(char *out, size_t n, const struct s2mini_pc_data *pc, bool valid,
                      bool clock12) {
    if (!valid || !(pc->flags & S2MINI_PC_TIME)) {
        snprintf(out, n, "--:--");
        return;
    }
    int h = pc->hour;
    if (clock12) {
        h = h % 12;
        h = h == 0 ? 12 : h;
    }
    snprintf(out, n, "%02d:%02d", h, pc->minute);
}

static void fmt_mmss(char *out, size_t n, int ms) {
    int sec = (ms + 999) / 1000;
    if (sec < 0) {
        sec = 0;
    }
    if (sec >= 3600) {
        snprintf(out, n, "%d:%02d:%02d", sec / 3600, (sec / 60) % 60, sec % 60);
    } else {
        snprintf(out, n, "%02d:%02d", sec / 60, sec % 60);
    }
}

static void status_bar_update(struct status_bar *b, const char *clock, const char *layer,
                              const struct s2mini_timer *t) {
    lv_label_set_text(b->time, clock);
    zmk_hid_indicators_t leds = zmk_hid_indicators_get_current_profile();
    set_hidden(b->caps, !(leds & HID_LED_CAPS));
    set_hidden(b->num, !(leds & HID_LED_NUM));
    if (t->state == S2MINI_TIMER_RUNNING || t->state == S2MINI_TIMER_PAUSED) {
        char mmss[8];
        fmt_mmss(mmss, sizeof(mmss), t->remaining_ms);
        lv_label_set_text(b->timer, mmss);
    } else {
        lv_label_set_text(b->timer, "");
    }
    lv_label_set_text(b->layer, layer);
}

static void wpm_update(lv_obj_t *l, bool show_wpm) {
    if (show_wpm) {
        lv_label_set_text_fmt(l, "%d wpm", s2mini_wpm_get());
        return;
    }
    lv_label_set_text(l, "");
}

static void update_timer_view(const struct s2mini_timer *t) {
    char mmss[8];
    switch (t->state) {
    case S2MINI_TIMER_RUNNING:
        fmt_mmss(mmss, sizeof(mmss), t->remaining_ms);
        lv_label_set_text(t_state, "running");
        lv_label_set_text(t_hint, "push: pause");
        break;
    case S2MINI_TIMER_PAUSED:
        fmt_mmss(mmss, sizeof(mmss), t->remaining_ms);
        lv_label_set_text(t_state, "paused");
        lv_label_set_text(t_hint, "push: go  turn: reset");
        break;
    default:
        fmt_mmss(mmss, sizeof(mmss), t->seconds * 1000);
        lv_label_set_text(t_state, "");
        lv_label_set_text(t_hint, "turn: set  push: start");
        break;
    }
    lv_label_set_text(t_time, mmss);
}

static void update_settings_view(const struct s2mini_ui_settings *c) {
    int sel;
    bool editing;
    s2mini_settings_menu_get(&sel, &editing);
    static char bars[S2MINI_BRIGHTNESS_LEVELS + 1];
    for (int i = 0; i < S2MINI_BRIGHTNESS_LEVELS; i++) {
        bars[i] = i < c->brightness ? '|' : '.';
    }
    bars[S2MINI_BRIGHTNESS_LEVELS] = '\0';
    const char *values[S2MINI_SET_COUNT] = {
        bars,
        c->invert ? "on" : "off",
        c->clock12 ? "12h" : "24h",
        c->show_wpm ? "on" : "off",
    };
    for (int i = 0; i < S2MINI_SET_COUNT; i++) {
        bool on = i == sel;
        struct menu_row *r = &s_rows[i];
        lv_obj_set_style_bg_opa(r->box, on ? LV_OPA_COVER : LV_OPA_TRANSP, 0);
        lv_obj_set_style_bg_color(r->box, fg, 0);
        lv_obj_set_style_text_color(r->name, on ? bg : fg, 0);
        lv_obj_set_style_text_color(r->value, on ? bg : fg, 0);
        if (on && editing) {
            lv_label_set_text_fmt(r->value, "< %s >", values[i]);
        } else {
            lv_label_set_text(r->value, values[i]);
        }
    }
    lv_label_set_text(s_hint, editing ? "turn: change  push: save" : "turn: move  push: change");
}

/* Jasność i odwrócenie kolorów idą prosto do sterownika ekranu (wątek ekranu). */
static void apply_display_settings(const struct s2mini_ui_settings *c) {
#if DT_HAS_CHOSEN(zephyr_display)
    static const uint8_t contrast[S2MINI_BRIGHTNESS_LEVELS] = {8, 40, 100, 170, 255};
    static int applied_brightness = -1, applied_invert = -1;
    const struct device *dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_display));
    if (!device_is_ready(dev)) {
        return;
    }
    if (applied_brightness != c->brightness) {
        display_set_contrast(dev, contrast[c->brightness - 1]);
        applied_brightness = c->brightness;
    }
    if (applied_invert != c->invert) {
        display_set_pixel_format(dev, c->invert ? PIXEL_FORMAT_MONO10 : PIXEL_FORMAT_MONO01);
        applied_invert = c->invert;
    }
#endif
}

static bool fn_active(void) {
    zmk_keymap_layer_index_t index = zmk_keymap_highest_layer_active();
    const char *name = zmk_keymap_layer_name(zmk_keymap_layer_index_to_id(index));
    return name != NULL && strcmp(name, FN_LAYER_NAME) == 0;
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
    char clock[8];
    struct s2mini_pc_data pc = {0};
    int64_t age = INT64_MAX;
    bool have_pc = false;
    struct s2mini_timer t;
    struct s2mini_ui_settings c;

    s2mini_timer_get(&t);
    s2mini_ui_settings_get(&c);
    apply_display_settings(&c);

#if IS_ENABLED(CONFIG_S2MINI_RAW_HID)
    have_pc = s2mini_pc_data_get(&pc, &age) && age < PC_TIMEOUT_MS;
#endif
    fmt_clock(clock, sizeof(clock), &pc, have_pc, c.clock12);

    /* Minutnik dobiegł końca: cały ekran miga co 0,5 s, aż PUSH albo 30 s. */
    if (t.state == S2MINI_TIMER_DONE) {
        bool lit = (t.done_ms / 500) % 2 == 0;
        lv_obj_set_style_bg_opa(d_box, lit ? LV_OPA_COVER : LV_OPA_TRANSP, 0);
        lv_obj_set_style_text_color(d_title, lit ? bg : fg, 0);
        lv_obj_set_style_text_color(d_hint, lit ? bg : fg, 0);
        show(VIEW_DONE);
        return;
    }

    const char *knob = knob_name();
    int64_t changed = s2mini_knob_mode_changed_at();
    bool popup = s2mini_knob_mode_count() > 0 && changed != 0 &&
                 k_uptime_get() - changed < POPUP_MS;

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

    if (fn_active()) {
        show(VIEW_FN);
        return;
    }

    switch (s2mini_screen_view()) {
    case S2MINI_VIEW_TIMER:
        update_timer_view(&t);
        show(VIEW_TIMER);
        return;
    case S2MINI_VIEW_SETTINGS:
        update_settings_view(&c);
        show(VIEW_SETTINGS);
        return;
    case S2MINI_VIEW_MEDIA:
        update_media(&pc, have_pc);
        show(VIEW_MEDIA);
        return;
    default:
        break;
    }

    if (have_pc && !game_active() && media_popup()) {
        update_media(&pc, have_pc);
        show(VIEW_MEDIA);
        return;
    }

    if (ports_wanted()) {
        update_ports();
        show(VIEW_PORTS);
        return;
    }

    if (!have_pc) {
        status_bar_update(&bar_no_pc, clock, layer_name(), &t);
        lv_label_set_text_fmt(n_knob, "knob: %s", knob);
        wpm_update(n_wpm, c.show_wpm);
        show(VIEW_NO_PC);
        return;
    }

    bool cpu = pc.flags & S2MINI_PC_CPU;
    bool gpu = pc.flags & S2MINI_PC_GPU;
    bool vol = pc.flags & S2MINI_PC_VOLUME;
    bool muted = pc.flags & S2MINI_PC_MUTED;

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
        lv_label_set_text(g_time, clock);
        if (muted) {
            lv_label_set_text(g_vol, "mute");
        } else if (vol) {
            lv_label_set_text_fmt(g_vol, "vol %d%%", pc.volume);
        } else {
            lv_label_set_text(g_vol, "");
        }
        /* Na dole jest mało miejsca: pierwsze 3 litery nazwy trybu, małymi literami. */
        snprintf(buf, sizeof(buf), "knob:%.3s", knob);
        for (char *ch = buf; *ch; ch++) {
            if (*ch >= 'A' && *ch <= 'Z') {
                *ch += 'a' - 'A';
            }
        }
        lv_label_set_text(g_knob, buf);
        show(VIEW_GAME);
        return;
    }

    status_bar_update(&bar_main, clock, layer_name(), &t);
    meter_set(&m_cpu, cpu, pc.cpu_load, pc.cpu_temp, NULL);
    meter_set(&m_gpu, gpu, pc.gpu_load, pc.gpu_temp, NULL);
    bool igpu = pc.flags & S2MINI_PC_IGPU;
    meter_set(&m_igpu, igpu, pc.igpu_load, 0, NULL);
    for (int i = 0; i < 4; i++) {
        if (m_igpu_row[i] != NULL) {
            set_hidden(m_igpu_row[i], !igpu);
        }
    }
    meter_set(&m_vol, vol, muted ? 0 : pc.volume, 0, muted ? "MUTE" : NULL);
    lv_label_set_text_fmt(m_knob, "knob: %s", knob);
    wpm_update(m_wpm, c.show_wpm);
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
    create_fn(views[VIEW_FN]);
    create_timer(views[VIEW_TIMER]);
    create_settings(views[VIEW_SETTINGS]);
    create_done(views[VIEW_DONE]);
    create_media(views[VIEW_MEDIA]);

    update_cb(NULL);
    lv_timer_create(update_cb, 100, NULL);
    return screen;
}
