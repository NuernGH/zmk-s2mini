/*
 * EC11 encoder read by polling instead of GPIO interrupts.
 *
 * Why: ZMK's alps,ec11 driver turns the pin interrupts off on the first edge and back on only
 * after the system work queue has read the pins. A contact that settles while the interrupts are
 * off is never seen; the next read then sees a jump of two states, counts it as 0 and the click
 * loses 2 of its 4 pulses (no key sent). Slow turning bounces longer, so it skipped clicks most.
 *
 * Here a 1 ms timer reads A/B, a new state is accepted only when it is the same in two reads in a
 * row (debounce), and a step is reported only when the encoder comes back to its rest state
 * (the click), after moving at least half a detent in one direction. Bouncing back and forth
 * cancels out and can never lose or add a click.
 *
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT s2mini_ec11_poll

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(s2mini_ec11_poll, CONFIG_SENSOR_LOG_LEVEL);

struct ec11_poll_config {
    struct gpio_dt_spec a;
    struct gpio_dt_spec b;
    int32_t steps;
    int32_t pulses_per_detent;
    uint32_t poll_us;
};

struct ec11_poll_data {
    const struct device *dev;
    struct k_timer timer;
    /* Timer (ISR) side */
    uint8_t stable;   /* last accepted A/B state */
    uint8_t candidate;
    uint8_t rest;     /* A/B state at a click */
    int8_t last_dir;
    int16_t travel;   /* pulses since the last click, signed */
    atomic_t detents; /* clicks not yet fetched */
    /* Sensor API side */
    int32_t pulses;
    sensor_trigger_handler_t handler;
    const struct sensor_trigger *trigger;
};

static uint8_t read_ab(const struct ec11_poll_config *cfg) {
    return (gpio_pin_get_dt(&cfg->a) > 0 ? 2 : 0) | (gpio_pin_get_dt(&cfg->b) > 0 ? 1 : 0);
}

/* Gray code position of an A/B state: 00 → 0, 01 → 1, 11 → 2, 10 → 3. */
static int gray_pos(uint8_t ab) {
    static const int8_t pos[4] = {0, 1, 3, 2};
    return pos[ab & 3];
}

static void poll_tick(struct k_timer *timer) {
    struct ec11_poll_data *data = CONTAINER_OF(timer, struct ec11_poll_data, timer);
    const struct ec11_poll_config *cfg = data->dev->config;
    uint8_t ab = read_ab(cfg);

    if (ab != data->candidate) {
        data->candidate = ab; /* changed: wait for the next read to confirm */
        return;
    }
    if (ab == data->stable) {
        return;
    }

    /* Same direction as alps,ec11: 00 → 01 → 11 → 10 → 00 is +1. */
    int diff = (gray_pos(ab) - gray_pos(data->stable) + 4) % 4;
    int move;
    switch (diff) {
    case 1:
        move = 1;
        break;
    case 3:
        move = -1;
        break;
    default:
        /* Both pins changed between two confirmed reads: the knob is fast; keep the direction. */
        move = 2 * (data->last_dir != 0 ? data->last_dir : 1);
        break;
    }
    data->stable = ab;
    data->last_dir = move > 0 ? 1 : -1;
    data->travel += move;

    if (ab != data->rest) {
        return;
    }

    /* Back at a click: count whole detents, a partial turn (≥ half a detent) counts as one. */
    int ppd = cfg->pulses_per_detent;
    int clicks = (data->travel + (data->travel >= 0 ? ppd / 2 : -(ppd / 2))) / ppd;
    data->travel = 0;
    if (clicks == 0) {
        return;
    }
    atomic_add(&data->detents, clicks);
    if (data->handler != NULL) {
        data->handler(data->dev, data->trigger); /* ZMK sends it on to its work queue */
    }
}

static int ec11_poll_sample_fetch(const struct device *dev, enum sensor_channel chan) {
    struct ec11_poll_data *data = dev->data;
    const struct ec11_poll_config *cfg = dev->config;

    data->pulses += (int32_t)atomic_set(&data->detents, 0) * cfg->pulses_per_detent;
    return 0;
}

static int ec11_poll_channel_get(const struct device *dev, enum sensor_channel chan,
                                 struct sensor_value *val) {
    struct ec11_poll_data *data = dev->data;
    const struct ec11_poll_config *cfg = dev->config;

    if (chan != SENSOR_CHAN_ROTATION) {
        return -ENOTSUP;
    }
    int32_t pulses = data->pulses;
    data->pulses = 0;
    /* Degrees as in alps,ec11 (val1 whole, val2 millionths). */
    val->val1 = (pulses * 360) / cfg->steps;
    val->val2 = (int32_t)(((int64_t)((pulses * 360) % cfg->steps) * 1000000) / cfg->steps);
    return 0;
}

static int ec11_poll_trigger_set(const struct device *dev, const struct sensor_trigger *trig,
                                 sensor_trigger_handler_t handler) {
    struct ec11_poll_data *data = dev->data;
    unsigned int key = irq_lock();
    data->trigger = trig;
    data->handler = handler;
    irq_unlock(key);
    return 0;
}

static const struct sensor_driver_api ec11_poll_api = {
    .trigger_set = ec11_poll_trigger_set,
    .sample_fetch = ec11_poll_sample_fetch,
    .channel_get = ec11_poll_channel_get,
};

static int ec11_poll_init(const struct device *dev) {
    struct ec11_poll_data *data = dev->data;
    const struct ec11_poll_config *cfg = dev->config;

    if (!gpio_is_ready_dt(&cfg->a) || !gpio_is_ready_dt(&cfg->b)) {
        LOG_ERR("encoder GPIO not ready");
        return -ENODEV;
    }
    if (gpio_pin_configure_dt(&cfg->a, GPIO_INPUT) || gpio_pin_configure_dt(&cfg->b, GPIO_INPUT)) {
        LOG_ERR("encoder GPIO configure failed");
        return -EIO;
    }
    if (cfg->steps <= 0 || cfg->pulses_per_detent <= 0) {
        return -EINVAL;
    }

    data->dev = dev;
    k_busy_wait(100); /* let the pull-ups charge the lines */
    data->stable = data->candidate = data->rest = read_ab(cfg);
    k_timer_init(&data->timer, poll_tick, NULL);
    k_timer_start(&data->timer, K_USEC(cfg->poll_us), K_USEC(cfg->poll_us));
    return 0;
}

#define EC11_POLL_INST(n)                                                                          \
    static struct ec11_poll_data ec11_poll_data_##n;                                               \
    static const struct ec11_poll_config ec11_poll_cfg_##n = {                                     \
        .a = GPIO_DT_SPEC_INST_GET(n, a_gpios),                                                    \
        .b = GPIO_DT_SPEC_INST_GET(n, b_gpios),                                                    \
        .steps = DT_INST_PROP(n, steps),                                                           \
        .pulses_per_detent = DT_INST_PROP(n, pulses_per_detent),                                   \
        .poll_us = DT_INST_PROP(n, poll_period_us),                                                \
    };                                                                                             \
    DEVICE_DT_INST_DEFINE(n, ec11_poll_init, NULL, &ec11_poll_data_##n, &ec11_poll_cfg_##n,        \
                          POST_KERNEL, CONFIG_SENSOR_INIT_PRIORITY, &ec11_poll_api);

DT_INST_FOREACH_STATUS_OKAY(EC11_POLL_INST)
