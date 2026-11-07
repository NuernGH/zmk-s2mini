# zmk-s2mini

ZMK na Wemos/Lolin S2 mini (ESP32-S2) przez USB, dla klawiatury 60% ANSI z [Keyboard maker](https://nuerngh.github.io/Keyboard-maker/).

Stan: **eksperyment**. ZMK oficjalnie nie obsługuje ESP32. Plan i wyniki testów są w dokumencie projektu „Plan: ZMK albo QMK na ESP32-S2 Mini”.

## Co tu jest

| Ścieżka | Co robi |
| --- | --- |
| `zephyr/module.yml`, `CMakeLists.txt` | moduł Zephyra; dokłada `usb_wrap_hal.c` z hal_espressif dla ESP32-S2 (Zephyr robi to tylko dla S3) |
| `boards/shields/s2mini_usb/` | nakładka DTS z kontrolerem USB OTG (DWC2) dla ESP32-S2 pod adresem 0x60080000 |
| `patches/zmk-usb-next.patch` | łatka na ZMK: opcja `CONFIG_ZMK_USB_NEXT`, czyli USB HID na nowym stosie USB Zephyra (`usb_next.c`, `usb_hid_next.c`), z tym samym API co stare `usb.c`/`usb_hid.c` |
| `boards/shields/s2mini_zmk_test/` | najprostsza klawiatura ZMK: przycisk 0 wpisuje „zmk ” |
| `boards/shields/s2mini_60/` | klawiatura 60% ANSI: macierz 5 × 14 (COL2ROW), warstwa Fn, gałka EC11 (głośność, z Fn jasność), przyciski modułu PUSH/CON/BAK, ekran SH1106 przez I2C (IO39/IO37), ZMK Studio przez port szeregowy USB (odblokowanie Fn + \\) |
| `scripts/build.sh`, `.github/workflows/build.yml` | budowanie obu shieldów; GitHub Actions publikuje pliki `.bin` jako artefakt `firmware-s2mini` |
| `config/west.yml` | ZMK z gałęzi `core/move-to-zephyr-4-4-0` (Zephyr 4.4.1, PR zmkfirmware/zmk#3387) |

Nie trzeba forka Zephyra ani hal_espressif. ZMK wymaga na razie łatki (stary stos USB w ZMK nie ma sterownika dla ESP32).

## Etapy

- [x] A0: przykład klawiatury Zephyra na S2 mini działa przez USB (Zephyr main, 7.11.2026).
- [x] A1 krok 1: ten moduł zamiast łatek w Zephyrze.
- [x] A1 krok 2: ten sam test na Zephyrze 4.4.1 z modułem (sprawdzony na płytce 7.11.2026).
- [x] A1 krok 3: USB w ZMK na nowym stosie USB Zephyra (`patches/zmk-usb-next.patch`; sprawdzony na płytce 7.11.2026: przycisk 0 wpisuje „zmk”).
- [ ] A1 krok 4: płytka i klawiatura 60% (macierz 5 × 14, EC11, SH1106, PUSH/CON/BAK): shield `s2mini_60` kompiluje się, czeka na test.
- [x] A1 krok 6: budowanie w GitHub Actions (zakładka Actions → ostatni przebieg → artefakt `firmware-s2mini`).
- [ ] A1 krok 8: warstwa ekranu z danymi z PC przez Raw HID (głośność, CPU i GPU: obciążenie i temperatura, godzina).

## Test USB (krok 2)

Wymaga Zephyr SDK 1.0.1 (toolchain `xtensa-espressif_esp32s2_zephyr-elf`) i `west`.

```sh
west init -l config        # w katalogu nadrzędnym workspace
west update
west build -p -b esp32s2_lolin_mini zephyr/samples/subsys/usb/hid-keyboard -- \
  -DZEPHYR_EXTRA_MODULES=$PWD/zmk-s2mini -DSHIELD=s2mini_usb
```

Wgrywanie: przytrzymaj 0, naciśnij RST, puść 0, potem `esptool --chip esp32s2 write-flash 0x1000 build/zephyr/zephyr.bin`. Po wgraniu **odłącz i podłącz kabel** (sam RST zostawia płytkę w bootloaderze). Przycisk 0 przełącza Num Lock, niebieska dioda pokazuje jego stan.

## Test ZMK (krok 3)

```sh
west init -l config && west update
git -C zmk apply ../zmk-s2mini/patches/zmk-usb-next.patch
west build -p -s zmk/app -b esp32s2_lolin_mini -- \
  -DZMK_EXTRA_MODULES=$PWD/zmk-s2mini -DSHIELD="s2mini_usb s2mini_zmk_test"
```

Jeśli CMake nie znajduje Zephyra, dodaj `-DZephyr_DIR=$PWD/zephyr/share/zephyr-package/cmake`. Wgrywanie jak wyżej (`build/zephyr/zmk.bin` pod 0x1000). Windows powinien pokazać klawiaturę „S2 mini ZMK test” (VID 1D50, PID 615E), a przycisk 0 wpisuje „zmk ”.

## Klawiatura 60% (krok 4)

Budowanie jak w kroku 3 (dodatkowo potrzebny `protoc`, np. pakiet `protobuf-compiler`), tylko `-DSHIELD="s2mini_usb s2mini_60"`. UART0 płytki jest wyłączony, bo IO16 i IO17 to klawisze, więc nie ma konsoli szeregowej.

## Licencja

Apache-2.0, tak jak Zephyr i ZMK (MIT dla ZMK).
