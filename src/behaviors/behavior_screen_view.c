/*
 * &scr_view SCR_PREV / SCR_NEXT: przełącza widok ekranu (główny, porty COM).
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT zmk_behavior_screen_view

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <drivers/behavior.h>
#include <zmk/behavior.h>
#include <dt-bindings/zmk/s2mini.h>
#include <s2mini/status.h>

static atomic_t view;

int s2mini_screen_view(void) { return atomic_get(&view); }

void s2mini_screen_view_step(int delta) {
    int v = (atomic_get(&view) + delta) % S2MINI_VIEW_COUNT;
    if (v < 0) {
        v += S2MINI_VIEW_COUNT;
    }
    atomic_set(&view, v);
}

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static int scr_view_pressed(struct zmk_behavior_binding *binding,
                            struct zmk_behavior_binding_event event) {
    s2mini_screen_view_step(binding->param1 == SCR_PREV ? -1 : 1);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int scr_view_released(struct zmk_behavior_binding *binding,
                             struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
static const struct behavior_parameter_value_metadata param_values[] = {
    {.display_name = "Previous view", .type = BEHAVIOR_PARAMETER_VALUE_TYPE_VALUE, .value = SCR_PREV},
    {.display_name = "Next view", .type = BEHAVIOR_PARAMETER_VALUE_TYPE_VALUE, .value = SCR_NEXT},
};
static const struct behavior_parameter_metadata_set param_metadata_set[] = {{
    .param1_values = param_values,
    .param1_values_len = ARRAY_SIZE(param_values),
}};
static const struct behavior_parameter_metadata metadata = {
    .sets_len = ARRAY_SIZE(param_metadata_set),
    .sets = param_metadata_set,
};
#endif

static const struct behavior_driver_api scr_view_api = {
    .binding_pressed = scr_view_pressed,
    .binding_released = scr_view_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .parameter_metadata = &metadata,
#endif
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &scr_view_api);

#endif
