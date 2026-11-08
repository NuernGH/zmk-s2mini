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

# Dodatki ZMK (tylko gdy moduł jest budowany razem z ZMK, czyli istnieje cel "app").
if(TARGET app AND (CONFIG_S2MINI_KNOB_MODES OR CONFIG_S2MINI_RAW_HID OR CONFIG_S2MINI_STATUS_SCREEN))
  target_include_directories(app PRIVATE include)
  target_sources_ifdef(CONFIG_S2MINI_KNOB_MODES app PRIVATE src/behaviors/behavior_knob_modes.c)
  target_sources(app PRIVATE src/behaviors/behavior_screen_view.c)
  target_sources_ifdef(CONFIG_S2MINI_RAW_HID app PRIVATE src/raw_hid.c)
  if(CONFIG_S2MINI_STATUS_SCREEN)
    target_sources(app PRIVATE
      src/display/status_screen.c
      src/ui_state.c
      src/wpm_keys.c
      src/display/fonts/s2m_font_9.c
      src/display/fonts/s2m_font_11.c
      src/display/fonts/s2m_font_14.c
      src/display/fonts/s2m_font_20.c
    )
    if(NOT CONFIG_S2MINI_KNOB_MODES)
      target_sources(app PRIVATE src/behaviors/behavior_knob_modes.c)
    endif()
  endif()
endif()
