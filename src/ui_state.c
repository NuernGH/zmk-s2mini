/*
 * Minutnik i ustawienia ekranu sterowane gałką.
 *
 * Widok TIMER: obrót ustawia czas (do 5 min co 15 s, do 1 h co minutę, do 3 h co 5 min) (gdy minutnik stoi), PUSH = start / pauza.
 * Widok SETTINGS: obrót wybiera pozycję, PUSH wchodzi w zmianę wartości (obrót zmienia),
 * kolejne PUSH zatwierdza i zapisuje w pamięci płytki.
 * Gdy minutnik dobiegnie końca, ekran miga „TIME UP” do PUSH albo przez 30 s.
 *
 * Stan zmieniają zachowania (kolejka systemowa), a czyta wątek ekranu, więc wszystko
 * idzie przez spinlock.
 * SPDX-License-Identifier: MIT
 */

#include <errno.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/logging/log.h>

#include <s2mini/status.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define TIMER_MIN_S 15
#define TIMER_MAX_S (3 * 3600)
#define TIMER_DEFAULT_S (25 * 60)
#define DONE_SHOW_MS 30000

static struct k_spinlock lock;

static struct s2mini_ui_settings cfg = {
    .brightness = 3,
    .invert = 0,
    .clock12 = 0,
    .show_wpm = 1,
};

static struct {
    enum s2mini_timer_state state;
    int seconds; /* ustawiony czas */
    int64_t end_at;    /* RUNNING: kiedy koniec */
    int remaining_ms;  /* PAUSED */
    int64_t done_at;   /* DONE: kiedy minął czas */
} tmr = {.state = S2MINI_TIMER_IDLE, .seconds = TIMER_DEFAULT_S};

static int menu_sel;
static bool menu_edit;

/* Wołane pod blokadą: RUNNING → DONE po czasie, DONE → IDLE po DONE_SHOW_MS. */
static void timer_refresh_locked(int64_t now) {
    if (tmr.state == S2MINI_TIMER_RUNNING && now >= tmr.end_at) {
        tmr.state = S2MINI_TIMER_DONE;
        tmr.done_at = tmr.end_at;
    }
    if (tmr.state == S2MINI_TIMER_DONE && now - tmr.done_at > DONE_SHOW_MS) {
        tmr.state = S2MINI_TIMER_IDLE;
    }
}

void s2mini_timer_get(struct s2mini_timer *out) {
    int64_t now = k_uptime_get();
    k_spinlock_key_t key = k_spin_lock(&lock);
    timer_refresh_locked(now);
    out->state = tmr.state;
    out->seconds = tmr.seconds;
    out->remaining_ms = 0;
    out->done_ms = 0;
    if (tmr.state == S2MINI_TIMER_RUNNING) {
        out->remaining_ms = (int)(tmr.end_at - now);
    } else if (tmr.state == S2MINI_TIMER_PAUSED) {
        out->remaining_ms = tmr.remaining_ms;
    } else if (tmr.state == S2MINI_TIMER_DONE) {
        out->done_ms = (int)(now - tmr.done_at);
    }
    k_spin_unlock(&lock, key);
}

void s2mini_ui_settings_get(struct s2mini_ui_settings *out) {
    k_spinlock_key_t key = k_spin_lock(&lock);
    *out = cfg;
    k_spin_unlock(&lock, key);
}

void s2mini_settings_menu_get(int *selected, bool *editing) {
    k_spinlock_key_t key = k_spin_lock(&lock);
    *selected = menu_sel;
    *editing = menu_edit;
    k_spin_unlock(&lock, key);
}

static bool timer_done_now(void) {
    struct s2mini_timer t;
    s2mini_timer_get(&t);
    return t.state == S2MINI_TIMER_DONE;
}

bool s2mini_ui_knob_captured(void) {
    int v = s2mini_screen_view();
    return v == S2MINI_VIEW_TIMER || v == S2MINI_VIEW_SETTINGS;
}

bool s2mini_ui_push_captured(void) { return s2mini_ui_knob_captured() || timer_done_now(); }

static int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

/*
 * Jeden krok gałki minutnika: do 5 min co 15 s, do godziny co minutę, dalej co 5 min.
 * Krok w dół liczy się od strony niższego zakresu, żeby wracać po tych samych wartościach.
 */
static int timer_step(int sec, int dir) {
    int probe = dir > 0 ? sec : sec - 1;
    int step = probe < 5 * 60 ? 15 : (probe < 3600 ? 60 : 300);
    int next = dir > 0 ? sec + step : sec - step;
    /* wyrównanie do siatki kroku */
    next = dir > 0 ? next - next % step : ((next + step - 1) / step) * step;
    return clampi(next, TIMER_MIN_S, TIMER_MAX_S);
}

static void setting_change_locked(int item, int delta) {
    switch (item) {
    case S2MINI_SET_BRIGHTNESS:
        cfg.brightness = clampi(cfg.brightness + delta, 1, S2MINI_BRIGHTNESS_LEVELS);
        break;
    case S2MINI_SET_INVERT:
        cfg.invert = !cfg.invert;
        break;
    case S2MINI_SET_CLOCK:
        cfg.clock12 = !cfg.clock12;
        break;
    case S2MINI_SET_WPM:
        cfg.show_wpm = !cfg.show_wpm;
        break;
    default:
        break;
    }
}

static void settings_store(void) {
#if IS_ENABLED(CONFIG_SETTINGS)
    struct s2mini_ui_settings copy;
    s2mini_ui_settings_get(&copy);
    int err = settings_save_one("s2mini/ui", &copy, sizeof(copy));
    if (err) {
        LOG_WRN("s2mini: zapis ustawień ekranu nie wyszedł (%d)", err);
    }
#endif
}

void s2mini_ui_knob(int delta) {
    int view = s2mini_screen_view();
    int64_t now = k_uptime_get();
    k_spinlock_key_t key = k_spin_lock(&lock);
    timer_refresh_locked(now);

    if (view == S2MINI_VIEW_TIMER) {
        /* Czas da się zmienić, gdy minutnik stoi (zmiana w pauzie zaczyna od nowa). */
        if (tmr.state != S2MINI_TIMER_RUNNING) {
            /* Przyspieszanie: szybkie kroki w tę samą stronę (co < 150 ms) mnożą skok, do ×8. */
            static int64_t last_at;
            static int last_dir, streak;
            int dir = delta > 0 ? 1 : -1;
            if (dir == last_dir && now - last_at < 150) {
                streak++;
            } else {
                streak = 0;
            }
            last_dir = dir;
            last_at = now;
            int mult = MIN(1 + streak / 3, 8);
            for (int i = 0; i < (delta > 0 ? delta : -delta) * mult; i++) {
                tmr.seconds = timer_step(tmr.seconds, delta > 0 ? 1 : -1);
            }
            tmr.state = S2MINI_TIMER_IDLE;
        }
    } else if (view == S2MINI_VIEW_SETTINGS) {
        if (menu_edit) {
            setting_change_locked(menu_sel, delta);
        } else {
            menu_sel = (menu_sel + (delta > 0 ? 1 : -1) + S2MINI_SET_COUNT) % S2MINI_SET_COUNT;
        }
    }
    k_spin_unlock(&lock, key);
}

void s2mini_ui_push(void) {
    int view = s2mini_screen_view();
    int64_t now = k_uptime_get();
    bool store = false;
    k_spinlock_key_t key = k_spin_lock(&lock);
    timer_refresh_locked(now);

    if (tmr.state == S2MINI_TIMER_DONE) {
        /* PUSH gasi dzwonek minutnika, niezależnie od widoku. */
        tmr.state = S2MINI_TIMER_IDLE;
    } else if (view == S2MINI_VIEW_TIMER) {
        switch (tmr.state) {
        case S2MINI_TIMER_IDLE:
            tmr.end_at = now + (int64_t)tmr.seconds * 1000;
            tmr.state = S2MINI_TIMER_RUNNING;
            break;
        case S2MINI_TIMER_RUNNING:
            tmr.remaining_ms = (int)(tmr.end_at - now);
            tmr.state = S2MINI_TIMER_PAUSED;
            break;
        case S2MINI_TIMER_PAUSED:
            tmr.end_at = now + tmr.remaining_ms;
            tmr.state = S2MINI_TIMER_RUNNING;
            break;
        default:
            break;
        }
    } else if (view == S2MINI_VIEW_SETTINGS) {
        if (menu_edit) {
            store = true;
        }
        /* Przełączniki (wł./wył.) zmieniają się od razu przy PUSH, jasność wymaga obrotu. */
        if (!menu_edit && menu_sel != S2MINI_SET_BRIGHTNESS) {
            setting_change_locked(menu_sel, 1);
            store = true;
        } else {
            menu_edit = !menu_edit;
        }
    }
    k_spin_unlock(&lock, key);

    if (store) {
        settings_store();
    }
}

#if IS_ENABLED(CONFIG_SETTINGS)
static int ui_settings_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg) {
    if (strcmp(name, "ui") != 0) {
        return -ENOENT;
    }
    struct s2mini_ui_settings loaded;
    if (len != sizeof(loaded) || read_cb(cb_arg, &loaded, sizeof(loaded)) != sizeof(loaded)) {
        return -EINVAL;
    }
    loaded.brightness = clampi(loaded.brightness, 1, S2MINI_BRIGHTNESS_LEVELS);
    k_spinlock_key_t key = k_spin_lock(&lock);
    cfg = loaded;
    k_spin_unlock(&lock, key);
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(s2mini, "s2mini", NULL, ui_settings_set, NULL, NULL);
#endif
