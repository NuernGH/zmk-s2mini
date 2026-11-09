/*
 * Timer and screen settings controlled by the knob.
 *
 * TIMER view: turning sets the time (15 s steps up to 5 min, 1 min up to 1 h, 5 min up to 3 h) while stopped; PUSH = start / pause.
 * SETTINGS view: turning picks an item, PUSH enters value editing (turning changes it),
 * the next PUSH confirms and saves it to the board's flash.
 * When the timer runs out, the screen flashes "TIME UP" until PUSH or for 30 s.
 *
 * State is changed by behaviors (system work queue) and read by the display thread, so everything
 * goes through a spinlock.
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
    int seconds; /* set time */
    int64_t end_at;    /* RUNNING: when it ends */
    int remaining_ms;  /* PAUSED */
    int64_t done_at;   /* DONE: when the time ran out */
} tmr = {.state = S2MINI_TIMER_IDLE, .seconds = TIMER_DEFAULT_S};

static int menu_sel;
static int launcher_sel;

int s2mini_launcher_selected(void) {
    int n = s2mini_apps_count();
    return n > 0 ? launcher_sel % n : 0;
}
static bool menu_edit;

/* Called with the lock held: RUNNING → DONE when time is up, DONE → IDLE after DONE_SHOW_MS. */
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
    return v == S2MINI_VIEW_TIMER || v == S2MINI_VIEW_SETTINGS || v == S2MINI_VIEW_LAUNCHER;
}

bool s2mini_ui_push_captured(void) { return s2mini_ui_knob_captured() || timer_done_now(); }

static int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

/*
 * One timer knob step: 15 s up to 5 min, 1 min up to an hour, then 5 min.
 * A step down uses the lower range's step, so turning back passes the same values.
 */
static int timer_step(int sec, int dir) {
    int probe = dir > 0 ? sec : sec - 1;
    int step = probe < 5 * 60 ? 15 : (probe < 3600 ? 60 : 300);
    int next = dir > 0 ? sec + step : sec - step;
    /* align to the step grid */
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
        LOG_WRN("s2mini: saving screen settings failed (%d)", err);
    }
#endif
}

void s2mini_ui_knob(int delta) {
    int view = s2mini_screen_view();
    int64_t now = k_uptime_get();
    k_spinlock_key_t key = k_spin_lock(&lock);
    timer_refresh_locked(now);

    if (view == S2MINI_VIEW_TIMER) {
        /* The time can be changed while the timer is stopped (a change while paused starts over). */
        if (tmr.state != S2MINI_TIMER_RUNNING) {
            /* Acceleration: fast steps in the same direction (< 150 ms apart) multiply the step, up to ×8. */
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
    } else if (view == S2MINI_VIEW_LAUNCHER) {
        int n = s2mini_apps_count();
        if (n > 0) {
            launcher_sel = ((launcher_sel + delta) % n + n) % n;
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

    bool was_done = tmr.state == S2MINI_TIMER_DONE;
    if (was_done) {
        /* PUSH silences the timer alarm, whatever the view. */
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
        /* Toggles (on/off) change immediately on PUSH; brightness needs turning. */
        if (!menu_edit && menu_sel != S2MINI_SET_BRIGHTNESS) {
            setting_change_locked(menu_sel, 1);
            store = true;
        } else {
            menu_edit = !menu_edit;
        }
    }
    bool launch = view == S2MINI_VIEW_LAUNCHER && !was_done;
    k_spin_unlock(&lock, key);

    if (launch && s2mini_apps_count() > 0) {
        s2mini_app_launch(s2mini_launcher_selected());
    }
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
