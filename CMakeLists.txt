# SPDX-License-Identifier: Apache-2.0
# USB OTG dla ESP32-S2: hal_espressif w Zephyrze buduje warstwę USB (usb_wrap_hal) tylko dla S3.
# Ten moduł dokłada ją dla S2, więc nie trzeba forka Zephyra ani hal_espressif.
if(CONFIG_SOC_SERIES_ESP32S2 AND (CONFIG_UDC_DWC2 OR CONFIG_UHC_DWC2))
  set(ESP_HAL ${ZEPHYR_HAL_ESPRESSIF_MODULE_DIR})
  zephyr_include_directories(
    ${ESP_HAL}/components/esp_hal_usb/include
    ${ESP_HAL}/components/esp_hal_usb/esp32s2/include
    ${ESP_HAL}/components/usb/include
  )
  zephyr_library_named(zmk_s2mini_usb)
  zephyr_library_sources(${ESP_HAL}/components/esp_hal_usb/usb_wrap_hal.c)
endif()
