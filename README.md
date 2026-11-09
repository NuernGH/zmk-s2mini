# zmk-s2mini

ZMK firmware for a 60% ANSI keyboard from [Keyboard-maker](https://nuerngh.github.io/Keyboard-maker/) on a Wemos/Lolin **S2 mini** (ESP32-S2), plus a Windows app that feeds the keyboard's OLED.

ZMK does not officially support the ESP32. This module adds USB OTG for the ESP32-S2 and a small ZMK patch for Zephyr's new USB stack.

## Features

- 5 × 14 matrix (COL2ROW), layers BASE / GAME / FN, ZMK Studio over USB serial (unlock: **Fn + \\**).
- EC11 knob with modes (VOLUME, SCROLL, TRACK, BRIGHT) and the OLED module buttons PUSH / CON / BAK.
- 1.3" SH1106 OLED (128 × 64) with views: main (clock, layer, CPU/GPU/iGPU, volume, WPM), now playing, quick launch, timer, COM ports, settings; FN cheat sheet; GAME mode.
- Raw HID channel (usage page 0xFF60) for data from the PC and app-launch requests to the PC.

## Repository

| Path | Contents |
| --- | --- |
| `boards/shields/s2mini_60/` | keyboard: pins, physical layout, keymap, config |
| `boards/shields/s2mini_usb/` | USB OTG (DWC2) node for the ESP32-S2 |
| `CMakeLists.txt`, `zephyr/module.yml` | module; adds `usb_wrap_hal.c` for the S2 |
| `patches/zmk-usb-next.patch` | ZMK on Zephyr's new USB stack (`CONFIG_ZMK_USB_NEXT`) + Studio UART fix |
| `src/`, `include/`, `dts/` | knob modes, screen views, Raw HID, timer/settings, WPM |
| `pc-app/` | Windows app (S2mini60) |
| `firmware/` | current prebuilt firmware |
| `scripts/build.sh`, `.github/workflows/` | firmware and app builds |

## Flashing

Prebuilt image: `firmware/s2mini_60-0x0.bin` (flash at address 0x0; checksum in `SHA256SUMS`). Every push also builds it in GitHub Actions (artifact `firmware-s2mini`).

1. Hold **0**, press **RST**, release **0** (ROM bootloader).
2. `esptool --chip esp32s2 write-flash 0x0 s2mini_60-0x0.bin`
3. Unplug and replug the USB cable (RST alone stays in the bootloader).

## Building

Needs Zephyr SDK 1.0.1 (`xtensa-espressif_esp32s2_zephyr-elf`), `west` and `protoc`.

```sh
mkdir ws && cd ws && git clone https://github.com/NuernGH/zmk-s2mini
west init -l zmk-s2mini/config && west update
../zmk-s2mini/scripts/build.sh .        # output: out/s2mini_60-0x0.bin
```

`config/west.yml` pins ZMK on Zephyr 4.4.1 (zmkfirmware/zmk#3387). See `.github/workflows/build.yml` for the full setup.

## PC app (S2mini60)

Download the `S2mini60` artifact from the latest *Build PC app* run in Actions, unzip, run `S2mini60.exe`. It sits in the tray and has four tabs:

- **Quick launch** – up to 16 apps for the LAUNCH view (Start menu, Store apps or any file); icons are converted to 1-bit with a selectable style and a live OLED preview.
- **Keymap** – live keymap editing through ZMK Studio; pick a key from a list or by pressing it.
- **Screen** – what to send (CPU, GPU, iGPU, volume, network, now playing, COM ports, notifications), language (follows Windows, Polish or English), start with Windows.
- **Status** – the last data sent.

CPU/GPU temperatures come from [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) with *Remote Web Server* enabled (port 8085). From source: `pip install -r pc-app/requirements.txt` and `python pc-app/s2mini_app.py`; `pc-app/build_exe.bat` builds the exe.

## Raw HID protocol

32-byte reports, byte 0 = `0x53`, byte 1 = frame type. Details are in the comment at the top of `src/raw_hid.c`.

| Type | Direction | Contents |
| --- | --- | --- |
| `0x01` | PC → kbd | flags, CPU/GPU load and temp, volume, time, iGPU load, network KB/s |
| `0x02` | PC → kbd | COM port list, one frame per port |
| `0x03` | PC → kbd | now playing: state, title / artist (ASCII) |
| `0x04` | PC → kbd | notification: app / title / body |
| `0x05`, `0x06` | PC → kbd | quick launch: app name, 32×32 1-bpp icon in 5 chunks |
| `0x10` | kbd → PC | launch app by index |

## License

Module code MIT; USB parts derived from Zephyr/hal_espressif are Apache-2.0 (see SPDX headers).
