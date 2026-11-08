/*
 * Licznik WPM do ekranu. Liczy tylko zwykłe klawisze (litery, cyfry, spacja, interpunkcja,
 * Enter, Backspace, Tab), a nie kroki pokrętła (głośność, przewijanie) ani modyfikatory,
 * które wbudowany licznik ZMK też nabijał.
 * Średnia z ostatnich 10 s; 5 znaków = 1 słowo.
 * SPDX-License-Identifier: MIT
 */

#include <string.h>
#include <zephyr/kernel.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <dt-bindings/zmk/hid_usage_pages.h>

#include <s2mini/status.h>

#define BUCKETS 10 /* sekund */
#define KEY_FIRST 0x04 /* A */
#define KEY_LAST 0x38  /* / */

static struct k_spinlock lock;
static uint16_t counts[BUCKETS];
static int64_t last_sec = -1;

/* Pod blokadą: zeruje kubełki sekund, które minęły od ostatniego wywołania. */
static void advance_locked(int64_t sec) {
    if (last_sec < 0 || sec - last_sec >= BUCKETS) {
        memset(counts, 0, sizeof(counts));
    } else {
        for (int64_t s = last_sec + 1; s <= sec; s++) {
            counts[s % BUCKETS] = 0;
        }
    }
    last_sec = sec;
}

int s2mini_wpm_get(void) {
    int64_t sec = k_uptime_get() / 1000;
    uint32_t sum = 0;
    K_SPINLOCK(&lock) {
        advance_locked(sec);
        for (int i = 0; i < BUCKETS; i++) {
            sum += counts[i];
        }
    }
    /* znaki w 10 s × 6 = znaki/min, / 5 = słowa/min */
    return (int)(sum * 6 / 5);
}

static int wpm_keys_listener(const zmk_event_t *eh) {
    const struct zmk_keycode_state_changed *ev = as_zmk_keycode_state_changed(eh);
    if (ev == NULL || !ev->state || ev->usage_page != HID_USAGE_KEY ||
        ev->keycode < KEY_FIRST || ev->keycode > KEY_LAST) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    int64_t sec = k_uptime_get() / 1000;
    K_SPINLOCK(&lock) {
        advance_locked(sec);
        if (counts[sec % BUCKETS] < UINT16_MAX) {
            counts[sec % BUCKETS]++;
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(s2mini_wpm, wpm_keys_listener);
ZMK_SUBSCRIPTION(s2mini_wpm, zmk_keycode_state_changed);
