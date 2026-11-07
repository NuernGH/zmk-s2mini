/*
 * Gałka z trybami: &knob (zachowanie czujnika) przekazuje obrót do zachowania aktywnego
 * trybu, &knob_next przełącza tryb po kolei.
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/logging/log.h>

#include <drivers/behavior.h>
#include <zmk/behavior.h>
#include <s2mini/status.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define KNOB_NODE DT_INST(0, zmk_behavior_knob_modes)

#if DT_NODE_EXISTS(KNOB_NODE)

#define MODE_DEV(idx, node) DEVICE_DT_NAME(DT_PHANDLE_BY_IDX(node, modes, idx))

static const char *const mode_devs[] = {
    LISTIFY(DT_PROP_LEN(KNOB_NODE, modes), MODE_DEV, (, ), KNOB_NODE)};
static const char *const mode_names[] = DT_PROP(KNOB_NODE, mode_names);

BUILD_ASSERT(ARRAY_SIZE(mode_devs) == ARRAY_SIZE(mode_names),
             "knob modes: modes i mode-names muszą mieć tyle samo pozycji");

static atomic_t current_mode;
static atomic_t pending_mode;
static int64_t changed_at;

int s2mini_knob_mode_count(void) { return ARRAY_SIZE(mode_devs); }
int s2mini_knob_mode_index(void) { return atomic_get(&current_mode); }
const char *s2mini_knob_mode_name(int index) {
    if (index < 0 || index >= ARRAY_SIZE(mode_names)) {
        return "";
    }
    return mode_names[index];
}
int64_t s2mini_knob_mode_changed_at(void) { return changed_at; }

static struct zmk_behavior_binding mode_binding(int mode) {
    return (struct zmk_behavior_binding){.behavior_dev = mode_devs[mode]};
}

/* Obrót: dane i wykonanie idą zawsze do tego samego trybu (zapamiętanego w accept_data). */
static int knob_accept_data(struct zmk_behavior_binding *binding,
                            struct zmk_behavior_binding_event event,
                            const struct zmk_sensor_config *sensor_config,
                            size_t channel_data_size,
                            const struct zmk_sensor_channel_data *channel_data) {
    int mode = atomic_get(&current_mode);
    atomic_set(&pending_mode, mode);
    struct zmk_behavior_binding target = mode_binding(mode);
    return behavior_sensor_keymap_binding_accept_data(&target, event, sensor_config,
                                                      channel_data_size, channel_data);
}

static int knob_process(struct zmk_behavior_binding *binding,
                        struct zmk_behavior_binding_event event,
                        enum behavior_sensor_binding_process_mode mode) {
    struct zmk_behavior_binding target = mode_binding(atomic_get(&pending_mode));
    return behavior_sensor_keymap_binding_process(&target, event, mode);
}

static const struct behavior_driver_api knob_modes_api = {
    .sensor_binding_accept_data = knob_accept_data,
    .sensor_binding_process = knob_process,
};

BEHAVIOR_DT_DEFINE(KNOB_NODE, NULL, NULL, NULL, NULL, POST_KERNEL,
                   CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &knob_modes_api);

#define NEXT_NODE DT_INST(0, zmk_behavior_knob_next)

#if DT_NODE_EXISTS(NEXT_NODE)

static int knob_next_pressed(struct zmk_behavior_binding *binding,
                             struct zmk_behavior_binding_event event) {
    int next = (atomic_get(&current_mode) + 1) % ARRAY_SIZE(mode_devs);
    atomic_set(&current_mode, next);
    changed_at = k_uptime_get();
    LOG_DBG("knob mode %d (%s)", next, mode_names[next]);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int knob_next_released(struct zmk_behavior_binding *binding,
                              struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api knob_next_api = {
    .binding_pressed = knob_next_pressed,
    .binding_released = knob_next_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

BEHAVIOR_DT_DEFINE(NEXT_NODE, NULL, NULL, NULL, NULL, POST_KERNEL,
                   CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &knob_next_api);

#endif /* NEXT_NODE */

#else /* brak gałki z trybami */

int s2mini_knob_mode_count(void) { return 0; }
int s2mini_knob_mode_index(void) { return 0; }
const char *s2mini_knob_mode_name(int index) { return ""; }
int64_t s2mini_knob_mode_changed_at(void) { return 0; }

#endif
