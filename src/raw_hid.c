/*
 * Raw HID: drugi interfejs HID (strona 0xFF60, raporty 32 B) do odbioru danych z PC:
 * obciążenie i temperatura CPU/GPU, głośność, godzina. Dane czyta ekran (status.h).
 *
 * Ramka z PC (raport wyjściowy, 32 B, bez ID raportu):
 *   [0] 0x53 ('S')  [1] 0x01 (wersja)  [2] flagi S2MINI_PC_*
 *   [3] CPU %  [4] CPU °C  [5] GPU %  [6] GPU °C  [7] głośność %
 *   [8] godzina  [9] minuta  [10] sekunda   reszta = 0
 *
 * SPDX-License-Identifier: MIT
 */

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/spinlock.h>
#include <zephyr/usb/class/usbd_hid.h>
#include <zephyr/logging/log.h>

#include <s2mini/status.h>

LOG_MODULE_REGISTER(s2mini_raw_hid, CONFIG_ZMK_LOG_LEVEL);

#define RAW_HID_NODE DT_CHOSEN(s2mini_raw_hid)
#define RAW_HID_REPORT_SIZE 32
#define FRAME_MAGIC 0x53
#define FRAME_VERSION 0x01

static const uint8_t raw_hid_desc[] = {
    0x06, 0x60, 0xFF,       /* Usage Page (Vendor 0xFF60) */
    0x09, 0x61,             /* Usage (0x61) */
    0xA1, 0x01,             /* Collection (Application) */
    0x09, 0x62,             /*   Usage (0x62): dane do PC */
    0x15, 0x00,             /*   Logical Minimum (0) */
    0x26, 0xFF, 0x00,       /*   Logical Maximum (255) */
    0x95, RAW_HID_REPORT_SIZE, /* Report Count */
    0x75, 0x08,             /*   Report Size (8) */
    0x81, 0x02,             /*   Input (Data, Var, Abs) */
    0x09, 0x63,             /*   Usage (0x63): dane z PC */
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

static void parse_frame(const uint8_t *buf, uint16_t len) {
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

/* Musi się zarejestrować przed usbd_init() w ZMK (ZMK_USB_INIT_PRIORITY). */
BUILD_ASSERT(CONFIG_S2MINI_RAW_HID_INIT_PRIORITY < CONFIG_ZMK_USB_INIT_PRIORITY,
             "Raw HID musi wystartować przed USB");
SYS_INIT(s2mini_raw_hid_init, APPLICATION, CONFIG_S2MINI_RAW_HID_INIT_PRIORITY);
