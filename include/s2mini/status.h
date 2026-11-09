/*
 * Shared state for the screen: knob mode and data from the PC (Raw HID).
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Knob modes (CONFIG_S2MINI_KNOB_MODES). */
int s2mini_knob_mode_count(void);
int s2mini_knob_mode_index(void);
const char *s2mini_knob_mode_name(int index);
/* Time of the last mode change (k_uptime_get), 0 = never changed. */
int64_t s2mini_knob_mode_changed_at(void);

/* Data from the PC (CONFIG_S2MINI_RAW_HID). */
#define S2MINI_PC_CPU BIT(0)
#define S2MINI_PC_GPU BIT(1)
#define S2MINI_PC_VOLUME BIT(2)
#define S2MINI_PC_TIME BIT(3)
#define S2MINI_PC_MUTED BIT(4)
#define S2MINI_PC_IGPU BIT(5) /* integrated GPU (Intel), load only */
#define S2MINI_PC_NET BIT(6)  /* network speed */

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
    uint16_t net_down; /* KB/s */
    uint16_t net_up;   /* KB/s */
};

/* COM ports from the PC (frame 0x02). */
#define S2MINI_PORTS_MAX 8
#define S2MINI_PORT_TEXT 28

/*
 * Copies the port list to out (up to max entries), returns the number of ports (may exceed max)
 * or -1 if no list has arrived yet. added_at = when a new port appeared (0 = never).
 */
int s2mini_ports_get(char out[][S2MINI_PORT_TEXT], int max, int64_t *age_ms, int64_t *added_at);

/* Now playing on the PC (frame 0x03). ASCII text only (the PC app transliterates). */
#define S2MINI_MEDIA_TEXT 29
enum s2mini_media_status { S2MINI_MEDIA_NONE, S2MINI_MEDIA_PLAYING, S2MINI_MEDIA_PAUSED };
struct s2mini_media {
    uint8_t status;
    char title[S2MINI_MEDIA_TEXT];
    char artist[S2MINI_MEDIA_TEXT];
    int64_t changed_at; /* when the title changed (0 = never) */
};
/* Returns false if nothing has arrived yet. age_ms = age of the data. */
bool s2mini_media_get(struct s2mini_media *out, int64_t *age_ms);

/* Last Windows notification (frame 0x04): app, title, body (ASCII). */
struct s2mini_notif {
    char app[S2MINI_MEDIA_TEXT];
    char title[S2MINI_MEDIA_TEXT];
    char body[S2MINI_MEDIA_TEXT];
    int64_t at; /* when it arrived (0 = never) */
};
void s2mini_notif_get(struct s2mini_notif *out);
/* A new notification arrived: if the screen is blanked (idle), wake it for the popup (status_screen.c). */
void s2mini_screen_notif_wake(void);

/*
 * Quick launch (frames 0x05 name, 0x06 icon): app list from the PC app.
 * Icon 32×32, 1 bit per pixel, row = 4 bytes, bit 7 = left pixel, 1 = lit.
 */
#define S2MINI_APPS_MAX 16
#define S2MINI_ICON_SIZE 32
#define S2MINI_ICON_BYTES (S2MINI_ICON_SIZE * S2MINI_ICON_SIZE / 8)
#define S2MINI_APP_NAME 29
int s2mini_apps_count(void);                 /* -1 = list not received yet */
uint32_t s2mini_apps_version(void);          /* changes whenever the list/icons change */
bool s2mini_app_get(int index, char name[S2MINI_APP_NAME], uint8_t icon[S2MINI_ICON_BYTES]);
int s2mini_app_launch(int index);            /* asks the PC to launch the app */
int s2mini_launcher_selected(void);

/* Screen view selected with &scr_view (CON / BAK). */
enum s2mini_view {
    S2MINI_VIEW_MAIN,
    S2MINI_VIEW_MEDIA,
    S2MINI_VIEW_LAUNCHER,
    S2MINI_VIEW_TIMER,
    S2MINI_VIEW_PORTS,
    S2MINI_VIEW_SETTINGS,
    S2MINI_VIEW_COUNT
};
int s2mini_screen_view(void);
void s2mini_screen_view_step(int delta);

/* Last data from the PC. Returns false if nothing has arrived yet. age_ms = age of the data. */
/* Typing speed (words/min) counted from ordinary keys only, averaged over 10 s. */
int s2mini_wpm_get(void);

bool s2mini_pc_data_get(struct s2mini_pc_data *out, int64_t *age_ms);

/*
 * Timer and screen settings (src/ui_state.c). On the TIMER and SETTINGS views the knob controls
 * the screen instead of its mode (volume etc.), and a short PUSH confirms.
 */
enum s2mini_timer_state { S2MINI_TIMER_IDLE, S2MINI_TIMER_RUNNING, S2MINI_TIMER_PAUSED, S2MINI_TIMER_DONE };

struct s2mini_timer {
    enum s2mini_timer_state state;
    int seconds;      /* set time */
    int remaining_ms; /* time left (RUNNING / PAUSED) */
    int done_ms;      /* ms since the time ran out (DONE) */
};

enum s2mini_setting {
    S2MINI_SET_BRIGHTNESS,
    S2MINI_SET_INVERT,
    S2MINI_SET_CLOCK,
    S2MINI_SET_WPM,
    S2MINI_SET_UPDATE, /* firmware update: PUSH twice within 5 s → ROM bootloader */
    S2MINI_SET_COUNT
};

struct s2mini_ui_settings {
    uint8_t brightness; /* 1..5 */
    uint8_t invert;     /* 0/1 */
    uint8_t clock12;    /* 0 = 24 h, 1 = 12 h */
    uint8_t show_wpm;   /* 0/1 */
};

#define S2MINI_BRIGHTNESS_LEVELS 5

void s2mini_timer_get(struct s2mini_timer *out);
void s2mini_ui_settings_get(struct s2mini_ui_settings *out);
/* Selected settings menu item and whether it is in value-edit mode. */
void s2mini_settings_menu_get(int *selected, bool *editing);

/* Whether the knob / PUSH currently control the screen (TIMER or SETTINGS view, or the timer is ringing). */
bool s2mini_ui_knob_captured(void);
bool s2mini_ui_push_captured(void);
void s2mini_ui_knob(int delta);
void s2mini_ui_push(void);
/* Changes on every knob turn / PUSH on these views; the screen polls it to redraw without waiting. */
uint32_t s2mini_ui_seq(void);
/* SETTINGS → Update FW: the first PUSH arms it for 5 s (the screen asks to push again). */
bool s2mini_update_armed(void);

/*
 * Restart into the ESP32-S2 ROM bootloader (USB 303A:0002) to flash new firmware with esptool,
 * without the 0 + RST buttons (src/bootloader.c). From SETTINGS → Update FW or a Raw HID command.
 */
void s2mini_enter_bootloader(void);
/* True from the bootloader request until the restart: the screen shows BOOT. */
bool s2mini_bootloader_pending(void);
/* Wake a blanked screen so BOOT is visible (status_screen.c). */
void s2mini_screen_boot_wake(void);
