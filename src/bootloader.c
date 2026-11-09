/*
 * Restart into the ESP32-S2 ROM bootloader (serial download mode over USB, 303A:0002), so
 * esptool can flash new firmware without holding 0 and pressing RST.
 * The FORCE_DOWNLOAD_BOOT flag lives in the RTC domain, so it survives the restart; the ROM
 * clears it and stays in download mode until the next reset / replug.
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/logging/log.h>
#include <soc/rtc_cntl_reg.h>

#include <s2mini/status.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static void bootloader_work_cb(struct k_work *work) {
    LOG_INF("restarting into the ROM bootloader");
    REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
    sys_reboot(SYS_REBOOT_COLD);
}

static K_WORK_DELAYABLE_DEFINE(bootloader_work, bootloader_work_cb);

void s2mini_enter_bootloader(void) {
    /* Short delay: the HID key release and the Raw HID reply still go out before USB drops. */
    k_work_reschedule(&bootloader_work, K_MSEC(300));
}
