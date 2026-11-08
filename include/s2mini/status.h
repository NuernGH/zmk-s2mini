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
#define S2MINI_PC_IGPU BIT(5) /* zintegrowane GPU (Intel), tylko obciążenie */

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
    uint8_t igpu_load; /* % */
};

/* Porty COM z PC (ramka 0x02). */
#define S2MINI_PORTS_MAX 8
#define S2MINI_PORT_TEXT 28

/*
 * Kopiuje listę portów do out (max pozycji), zwraca liczbę portów (może być większa niż max)
 * albo -1, gdy lista jeszcze nie przyszła. added_at = czas, gdy pojawił się nowy port (0 = nigdy).
 */
int s2mini_ports_get(char out[][S2MINI_PORT_TEXT], int max, int64_t *age_ms, int64_t *added_at);

/* Widok ekranu wybierany przez &scr_view (CON / BAK). */
enum s2mini_view {
    S2MINI_VIEW_MAIN,
    S2MINI_VIEW_TIMER,
    S2MINI_VIEW_PORTS,
    S2MINI_VIEW_SETTINGS,
    S2MINI_VIEW_COUNT
};
int s2mini_screen_view(void);
void s2mini_screen_view_step(int delta);

/* Ostatnie dane z PC. Zwraca false, gdy jeszcze nic nie przyszło. age_ms = wiek danych. */
bool s2mini_pc_data_get(struct s2mini_pc_data *out, int64_t *age_ms);

/*
 * Minutnik i ustawienia ekranu (src/ui_state.c). Na widokach TIMER i SETTINGS gałka steruje
 * ekranem zamiast trybu (głośność itd.), a krótkie PUSH zatwierdza.
 */
enum s2mini_timer_state { S2MINI_TIMER_IDLE, S2MINI_TIMER_RUNNING, S2MINI_TIMER_PAUSED, S2MINI_TIMER_DONE };

struct s2mini_timer {
    enum s2mini_timer_state state;
    int minutes;      /* ustawiony czas */
    int remaining_ms; /* pozostało (RUNNING / PAUSED) */
    int done_ms;      /* od ilu ms minął czas (DONE) */
};

enum s2mini_setting { S2MINI_SET_BRIGHTNESS, S2MINI_SET_INVERT, S2MINI_SET_CLOCK, S2MINI_SET_WPM, S2MINI_SET_COUNT };

struct s2mini_ui_settings {
    uint8_t brightness; /* 1..5 */
    uint8_t invert;     /* 0/1 */
    uint8_t clock12;    /* 0 = 24 h, 1 = 12 h */
    uint8_t show_wpm;   /* 0/1 */
};

#define S2MINI_BRIGHTNESS_LEVELS 5

void s2mini_timer_get(struct s2mini_timer *out);
void s2mini_ui_settings_get(struct s2mini_ui_settings *out);
/* Zaznaczona pozycja menu ustawień i czy jest w trybie zmiany wartości. */
void s2mini_settings_menu_get(int *selected, bool *editing);

/* Czy gałka / PUSH sterują teraz ekranem (widok TIMER albo SETTINGS, albo dzwoni minutnik). */
bool s2mini_ui_knob_captured(void);
bool s2mini_ui_push_captured(void);
void s2mini_ui_knob(int delta);
void s2mini_ui_push(void);
