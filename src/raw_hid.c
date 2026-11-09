/*
 * Raw HID: a second HID interface (usage page 0xFF60, 32 B reports) that receives data from the PC:
 * CPU/GPU load and temperature, volume, time of day. The screen reads it (status.h).
 *
 * Frame from the PC (output report, 32 B, no report ID):
 *   [0] 0x53 ('S')  [1] 0x01 (version)  [2] flags S2MINI_PC_*
 *   [3] CPU %  [4] CPU °C  [5] GPU %  [6] GPU °C  [7] volume %
 *   [8] hour  [9] minute  [10] second  [11] iGPU % (flag S2MINI_PC_IGPU)
 *   [12..13] network download KB/s  [14..15] upload KB/s (LE, flag S2MINI_PC_NET)   rest = 0
 *
 * COM port list frame (one frame per port, sent in order):
 *   [0] 0x53  [1] 0x02  [2] port number (from 0)  [3] number of ports
 *   [4..31] text, e.g. "COM12 S2 mini 60" (up to 28 characters, rest 0)
 *   With 0 ports, a single frame with [3] = 0.
 *
 * "Now playing" frame (two frames: title, then artist):
 *   [0] 0x53  [1] 0x03  [2] state (0 nothing, 1 playing, 2 paused)  [3] field (0 title, 1 artist)
 *   [4..31] ASCII text (up to 28 characters, rest 0)
 *
 * Notification frame (three frames: app, title, body; shown after the body frame):
 *   [0] 0x53  [1] 0x04  [2] notification number  [3] field (0 app, 1 title, 2 body)
 *   [4..31] ASCII text
 *
 * Quick launch: name [1] 0x05 [2] index [3] number of apps [4..31] ASCII name,
 *   icon [1] 0x06 [2] index [3] chunk 0..4 [4..31] up to 28 B of the 128 B 32×32 1 bpp icon.
 *   Count 0 = empty list.
 * To the PC (input report): [0] 0x53 [1] 0x10 [2] index of the app to launch.
 *
 * Firmware update: [0] 0x53 [1] 0x07 [2..5] "BOOT" → restart into the ROM bootloader (esptool).
 *
 * SPDX-License-Identifier: MIT
 */

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/spinlock.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/usb/class/usbd_hid.h>
#include <zephyr/logging/log.h>

#include <s2mini/status.h>

LOG_MODULE_REGISTER(s2mini_raw_hid, CONFIG_ZMK_LOG_LEVEL);

#define RAW_HID_NODE DT_CHOSEN(s2mini_raw_hid)
#define RAW_HID_REPORT_SIZE 32
#define FRAME_MAGIC 0x53
#define FRAME_VERSION 0x01
#define FRAME_PORTS 0x02
#define FRAME_MEDIA 0x03
#define FRAME_NOTIF 0x04
#define FRAME_APP_NAME 0x05
#define FRAME_APP_ICON 0x06
#define FRAME_BOOTLOADER 0x07
#define FRAME_LAUNCH 0x10

static const uint8_t raw_hid_desc[] = {
    0x06, 0x60, 0xFF,       /* Usage Page (Vendor 0xFF60) */
    0x09, 0x61,             /* Usage (0x61) */
    0xA1, 0x01,             /* Collection (Application) */
    0x09, 0x62,             /*   Usage (0x62): data to the PC */
    0x15, 0x00,             /*   Logical Minimum (0) */
    0x26, 0xFF, 0x00,       /*   Logical Maximum (255) */
    0x95, RAW_HID_REPORT_SIZE, /* Report Count */
    0x75, 0x08,             /*   Report Size (8) */
    0x81, 0x02,             /*   Input (Data, Var, Abs) */
    0x09, 0x63,             /*   Usage (0x63): data from the PC */
    0x15, 0x00,             /*   Logical Minimum (0) */
    0x26, 0xFF, 0x00,       /*   Logical Maximum (255) */
    0x95, RAW_HID_REPORT_SIZE, /* Report Count */
    0x75, 0x08,             /*   Report Size (8) */
    0x91, 0x02,             /*   Output (Data, Var, Abs) */
    0xC0,                   /* End Collection */
};

static struct k_spinlock lock;
static struct s2mini_pc_data pc_data;
static int64_t received_at;
static bool have_data;

bool s2mini_pc_data_get(struct s2mini_pc_data *out, int64_t *age_ms) {
    bool ok;
    K_SPINLOCK(&lock) {
        ok = have_data;
        *out = pc_data;
        if (age_ms != NULL) {
            *age_ms = ok ? k_uptime_get() - received_at : INT64_MAX;
        }
    }
    return ok;
}

/* COM ports: list collected from consecutive frames, committed after the last one. */
static char ports[S2MINI_PORTS_MAX][S2MINI_PORT_TEXT];
static int ports_count = -1;
static int64_t ports_at;
static int64_t ports_added_at;
static char pending[S2MINI_PORTS_MAX][S2MINI_PORT_TEXT];

int s2mini_ports_get(char out[][S2MINI_PORT_TEXT], int max, int64_t *age_ms, int64_t *added_at) {
    int count;
    K_SPINLOCK(&lock) {
        count = ports_count;
        for (int i = 0; i < MIN(MAX(count, 0), MIN(max, S2MINI_PORTS_MAX)); i++) {
            memcpy(out[i], ports[i], S2MINI_PORT_TEXT);
        }
        if (age_ms != NULL) {
            *age_ms = count >= 0 ? k_uptime_get() - ports_at : INT64_MAX;
        }
        if (added_at != NULL) {
            *added_at = ports_added_at;
        }
    }
    return count;
}

static bool known_port(const char *text) {
    for (int i = 0; i < MIN(MAX(ports_count, 0), S2MINI_PORTS_MAX); i++) {
        if (strncmp(ports[i], text, S2MINI_PORT_TEXT) == 0) {
            return true;
        }
    }
    return false;
}

static void parse_ports(const uint8_t *buf, uint16_t len) {
    int index = buf[2];
    int count = buf[3];

    if (count > 0 && index < S2MINI_PORTS_MAX) {
        size_t n = MIN(len - 4, S2MINI_PORT_TEXT - 1);
        memcpy(pending[index], &buf[4], n);
        pending[index][n] = '\0';
    }
    if (count > 0 && index != count - 1) {
        return;
    }

    K_SPINLOCK(&lock) {
        bool added = false;
        for (int i = 0; i < MIN(count, S2MINI_PORTS_MAX); i++) {
            /* A new port (not in the first list after boot) shows the ports view. */
            if (ports_count >= 0 && !known_port(pending[i])) {
                added = true;
            }
        }
        memcpy(ports, pending, sizeof(ports));
        ports_count = count;
        ports_at = k_uptime_get();
        if (added) {
            ports_added_at = ports_at;
        }
    }
}

/* Now playing: title and artist in separate frames, committed after the artist frame. */
static struct s2mini_media media;
static int64_t media_at;
static bool have_media;
static char pending_title[S2MINI_MEDIA_TEXT];

bool s2mini_media_get(struct s2mini_media *out, int64_t *age_ms) {
    bool ok;
    K_SPINLOCK(&lock) {
        ok = have_media;
        *out = media;
        if (age_ms != NULL) {
            *age_ms = ok ? k_uptime_get() - media_at : INT64_MAX;
        }
    }
    return ok;
}

static void copy_text(char *dst, const uint8_t *src, size_t avail) {
    size_t n = MIN(avail, S2MINI_MEDIA_TEXT - 1);
    for (size_t i = 0; i < n; i++) {
        uint8_t ch = src[i];
        dst[i] = (ch >= 0x20 && ch < 0x7F) || ch == 0 ? (char)ch : '?';
    }
    dst[n] = '\0';
}

static void parse_media(const uint8_t *buf, uint16_t len) {
    if (buf[3] == 0) {
        copy_text(pending_title, &buf[4], len - 4);
        return;
    }
    char artist[S2MINI_MEDIA_TEXT];
    copy_text(artist, &buf[4], len - 4);
    K_SPINLOCK(&lock) {
        int64_t now = k_uptime_get();
        bool new_title = strcmp(media.title, pending_title) != 0 && pending_title[0] != '\0';
        /* The first frame after boot does not show a popup. */
        if (new_title && have_media) {
            media.changed_at = now;
        }
        media.status = MIN(buf[2], S2MINI_MEDIA_PAUSED);
        memcpy(media.title, pending_title, sizeof(media.title));
        memcpy(media.artist, artist, sizeof(media.artist));
        media_at = now;
        have_media = true;
    }
}

static struct s2mini_notif notif;
static struct s2mini_notif notif_pending;

void s2mini_notif_get(struct s2mini_notif *out) {
    K_SPINLOCK(&lock) { *out = notif; }
}

static void parse_notif(const uint8_t *buf, uint16_t len) {
    switch (buf[3]) {
    case 0:
        copy_text(notif_pending.app, &buf[4], len - 4);
        break;
    case 1:
        copy_text(notif_pending.title, &buf[4], len - 4);
        break;
    default:
        copy_text(notif_pending.body, &buf[4], len - 4);
        K_SPINLOCK(&lock) {
            notif = notif_pending;
            notif.at = k_uptime_get();
        }
#if IS_ENABLED(CONFIG_S2MINI_STATUS_SCREEN)
        s2mini_screen_notif_wake();
#endif
        break;
    }
}

/* Quick launch: app names and icons. */
static char app_names[S2MINI_APPS_MAX][S2MINI_APP_NAME];
static uint8_t app_icons[S2MINI_APPS_MAX][S2MINI_ICON_BYTES];
static int apps_count = -1;
static uint32_t apps_version;

int s2mini_apps_count(void) {
    int n;
    K_SPINLOCK(&lock) { n = apps_count; }
    return n;
}

uint32_t s2mini_apps_version(void) {
    uint32_t v;
    K_SPINLOCK(&lock) { v = apps_version; }
    return v;
}

bool s2mini_app_get(int index, char name[S2MINI_APP_NAME], uint8_t icon[S2MINI_ICON_BYTES]) {
    bool ok = false;
    K_SPINLOCK(&lock) {
        if (index >= 0 && index < MIN(apps_count, S2MINI_APPS_MAX)) {
            memcpy(name, app_names[index], S2MINI_APP_NAME);
            memcpy(icon, app_icons[index], S2MINI_ICON_BYTES);
            ok = true;
        }
    }
    return ok;
}

static void parse_app_name(const uint8_t *buf, uint16_t len) {
    int index = buf[2];
    int count = MIN(buf[3], S2MINI_APPS_MAX);
    char name[S2MINI_APP_NAME];
    copy_text(name, &buf[4], len - 4);
    K_SPINLOCK(&lock) {
        bool changed = count != apps_count;
        if (index < count && strcmp(app_names[index], name) != 0) {
            memcpy(app_names[index], name, sizeof(name));
            changed = true;
        }
        apps_count = count;
        if (changed) {
            apps_version++;
        }
    }
}

static void parse_app_icon(const uint8_t *buf, uint16_t len) {
    int index = buf[2];
    int offset = buf[3] * 28;
    if (index >= S2MINI_APPS_MAX || offset >= S2MINI_ICON_BYTES) {
        return;
    }
    int n = MIN(MIN(len - 4, 28), S2MINI_ICON_BYTES - offset);
    K_SPINLOCK(&lock) {
        if (memcmp(&app_icons[index][offset], &buf[4], n) != 0) {
            memcpy(&app_icons[index][offset], &buf[4], n);
            apps_version++;
        }
    }
}

/* Launch request state for the screen: result of the last send and whether the PC took it. */
static atomic_t launch_in_flight;
static int launch_err;
static int64_t launch_at;
static atomic_t launch_done;

void s2mini_launch_status(int *err, bool *in_flight, bool *done, int64_t *at) {
    *err = launch_err;
    *in_flight = atomic_get(&launch_in_flight) != 0;
    *done = atomic_get(&launch_done) != 0;
    *at = launch_at;
}

int s2mini_app_launch(int index) {
    const struct device *dev = DEVICE_DT_GET(RAW_HID_NODE);
    static uint8_t __aligned(4) report[RAW_HID_REPORT_SIZE];
    launch_at = k_uptime_get();
    atomic_set(&launch_done, 0);
    if (atomic_get(&launch_in_flight)) {
        /* The previous request was never read by the PC; the buffer is still queued. */
        launch_err = -EBUSY;
        LOG_WRN("launch report: previous one still pending");
        return -EBUSY;
    }
    memset(report, 0, sizeof(report));
    report[0] = FRAME_MAGIC;
    report[1] = FRAME_LAUNCH;
    report[2] = index;
    atomic_set(&launch_in_flight, 1);
    int err = hid_device_submit_report(dev, sizeof(report), report);
    launch_err = err;
    if (err) {
        atomic_set(&launch_in_flight, 0);
        LOG_WRN("launch report failed: %d", err);
    }
    return err;
}

/* With this callback the send is asynchronous: before, the caller (system work queue) waited
 * forever for the PC to read the report. */
static void raw_input_done(const struct device *dev, const uint8_t *const report) {
    atomic_set(&launch_in_flight, 0);
    atomic_set(&launch_done, 1);
}

static void parse_frame(const uint8_t *buf, uint16_t len) {
    if (len >= 6 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_BOOTLOADER &&
        memcmp(&buf[2], "BOOT", 4) == 0) {
        s2mini_enter_bootloader();
        return;
    }
    if (len >= 5 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_APP_NAME) {
        parse_app_name(buf, len);
        return;
    }
    if (len >= 5 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_APP_ICON) {
        parse_app_icon(buf, len);
        return;
    }
    if (len >= 5 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_NOTIF) {
        parse_notif(buf, len);
        return;
    }
    if (len >= 5 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_MEDIA) {
        parse_media(buf, len);
        return;
    }
    if (len >= 5 && buf[0] == FRAME_MAGIC && buf[1] == FRAME_PORTS) {
        parse_ports(buf, len);
        return;
    }
    if (len < 11 || buf[0] != FRAME_MAGIC || buf[1] != FRAME_VERSION) {
        LOG_DBG("raw hid: unknown frame (len %u)", len);
        return;
    }

    struct s2mini_pc_data d = {
        .flags = buf[2],
        .cpu_load = MIN(buf[3], 100),
        .cpu_temp = buf[4],
        .gpu_load = MIN(buf[5], 100),
        .gpu_temp = buf[6],
        .volume = MIN(buf[7], 100),
        .hour = buf[8] % 24,
        .minute = buf[9] % 60,
        .second = buf[10] % 60,
        .igpu_load = len >= 12 ? MIN(buf[11], 100) : 0,
        .net_down = len >= 16 ? sys_get_le16(&buf[12]) : 0,
        .net_up = len >= 16 ? sys_get_le16(&buf[14]) : 0,
    };

    K_SPINLOCK(&lock) {
        pc_data = d;
        received_at = k_uptime_get();
        have_data = true;
    }
}

static int raw_get_report(const struct device *dev, const uint8_t type, const uint8_t id,
                          const uint16_t len, uint8_t *const buf) {
    if (type != HID_REPORT_TYPE_INPUT || len < RAW_HID_REPORT_SIZE) {
        return -ENOTSUP;
    }
    memset(buf, 0, RAW_HID_REPORT_SIZE);
    buf[0] = FRAME_MAGIC;
    buf[1] = FRAME_VERSION;
    return RAW_HID_REPORT_SIZE;
}

static int raw_set_report(const struct device *dev, const uint8_t type, const uint8_t id,
                          const uint16_t len, const uint8_t *const buf) {
    if (type != HID_REPORT_TYPE_OUTPUT) {
        return -ENOTSUP;
    }
    parse_frame(buf, len);
    return 0;
}

static void raw_output_report(const struct device *dev, const uint16_t len,
                              const uint8_t *const buf) {
    parse_frame(buf, len);
}

static void raw_iface_ready(const struct device *dev, const bool ready) {
    LOG_DBG("raw hid ready %d", ready);
}

static const struct hid_device_ops raw_hid_ops = {
    .iface_ready = raw_iface_ready,
    .get_report = raw_get_report,
    .set_report = raw_set_report,
    .output_report = raw_output_report,
    .input_report_done = raw_input_done,
};

static int s2mini_raw_hid_init(void) {
    const struct device *dev = DEVICE_DT_GET(RAW_HID_NODE);

    if (!device_is_ready(dev)) {
        LOG_ERR("raw hid device not ready");
        return -ENODEV;
    }

    int err = hid_device_register(dev, raw_hid_desc, sizeof(raw_hid_desc), &raw_hid_ops);
    if (err) {
        LOG_ERR("raw hid register failed: %d", err);
    }
    return err;
}

/* Must register before usbd_init() in ZMK (ZMK_USB_INIT_PRIORITY). */
BUILD_ASSERT(CONFIG_S2MINI_RAW_HID_INIT_PRIORITY < CONFIG_ZMK_USB_INIT_PRIORITY,
             "Raw HID must start before USB");
SYS_INIT(s2mini_raw_hid_init, APPLICATION, CONFIG_S2MINI_RAW_HID_INIT_PRIORITY);
