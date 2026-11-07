/*
 * Wspólny stan dla ekranu: tryb gałki i dane z PC (Raw HID).
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Tryby gałki (CONFIG_S2MINI_KNOB_MODES). */
int s2mini_knob_mode_count(void);
int s2mini_knob_mode_index(void);
const char *s2mini_knob_mode_name(int index);
/* Czas ostatniej zmiany trybu (k_uptime_get), 0 = jeszcze nie zmieniany. */
int64_t s2mini_knob_mode_changed_at(void);

/* Dane z PC (CONFIG_S2MINI_RAW_HID). */
#define S2MINI_PC_CPU BIT(0)
#define S2MINI_PC_GPU BIT(1)
#define S2MINI_PC_VOLUME BIT(2)
#define S2MINI_PC_TIME BIT(3)
#define S2MINI_PC_MUTED BIT(4)

struct s2mini_pc_data {
    uint8_t flags;
    uint8_t cpu_load; /* % */
    uint8_t cpu_temp; /* °C */
    uint8_t gpu_load;
    uint8_t gpu_temp;
    uint8_t volume; /* % */
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
};

/* Ostatnie dane z PC. Zwraca false, gdy jeszcze nic nie przyszło. age_ms = wiek danych. */
bool s2mini_pc_data_get(struct s2mini_pc_data *out, int64_t *age_ms);
