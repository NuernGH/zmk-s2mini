# zmk-s2mini

ZMK na Wemos/Lolin S2 mini (ESP32-S2) przez USB, dla klawiatury 60% ANSI z [Keyboard maker](https://nuerngh.github.io/Keyboard-maker/).

Stan: **eksperyment**. ZMK oficjalnie nie obsługuje ESP32. Plan i wyniki testów są w dokumencie projektu „Plan: ZMK albo QMK na ESP32-S2 Mini”.

## Co tu jest

| Ścieżka | Co robi |
| --- | --- |
| `zephyr/module.yml`, `CMakeLists.txt` | moduł Zephyra; dokłada `usb_wrap_hal.c` z hal_espressif dla ESP32-S2 (Zephyr robi to tylko dla S3) |
| `boards/shields/s2mini_usb/` | nakładka DTS z kontrolerem USB OTG (DWC2) dla ESP32-S2 pod adresem 0x60080000 |
| `config/west.yml` | ZMK z gałęzi `core/move-to-zephyr-4-4-0` (Zephyr 4.4.1, PR zmkfirmware/zmk#3387) |

Nie trzeba forka Zephyra ani hal_espressif.

## Etapy

- [x] A0: przykład klawiatury Zephyra na S2 mini działa przez USB (Zephyr main, 7.11.2026).
- [x] A1 krok 1: ten moduł zamiast łatek w Zephyrze.
- [ ] A1 krok 2: ten sam test na Zephyrze 4.4.1 z modułem (zbudowany, czeka na wgranie).
- [ ] A1 krok 3: USB w ZMK na nowym stosie USB Zephyra (`usb_next.c`, `usb_hid_next.c`).
- [ ] A1 krok 4: płytka i klawiatura 60% (macierz 5 × 14, EC11, SH1106, PUSH/CON/BAK).
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

## Licencja

Apache-2.0, tak jak Zephyr i ZMK (MIT dla ZMK).
