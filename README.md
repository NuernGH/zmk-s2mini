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
| `boards/shields/s2mini_60/` | klawiatura 60% ANSI: macierz 5 × 14 (COL2ROW), warstwy BASE / GAME / FN, gałka EC11 z trybami, przyciski modułu PUSH/CON/BAK, ekran SH1106 przez I2C (IO39/IO37), ZMK Studio przez port szeregowy USB (odblokowanie Fn + \\) |
| `src/behaviors/`, `dts/bindings/` | zachowania `&knob` (gałka z trybami), `&knob_next` (następny tryb), `&scr_view SCR_PREV/SCR_NEXT` (widok ekranu) |
| `src/raw_hid.c` | drugi interfejs HID (Raw HID, strona 0xFF60, 32 B) z danymi z PC dla ekranu |
| `src/display/` | własny ekran 128 × 64 (teksty po angielsku) i czcionki z DejaVu Sans Bold |
| `pc-app/` | program na Windows wysyłający dane z PC na ekran |
| `scripts/build.sh`, `.github/workflows/build.yml` | budowanie obu shieldów; GitHub Actions publikuje pliki `.bin` jako artefakt `firmware-s2mini` |
| `config/west.yml` | ZMK z gałęzi `core/move-to-zephyr-4-4-0` (Zephyr 4.4.1, PR zmkfirmware/zmk#3387) |

Nie trzeba forka Zephyra ani hal_espressif. ZMK wymaga na razie łatki (stary stos USB w ZMK nie ma sterownika dla ESP32).

## Etapy

- [x] A0: przykład klawiatury Zephyra na S2 mini działa przez USB (Zephyr main, 7.11.2026).
- [x] A1 krok 1: ten moduł zamiast łatek w Zephyrze.
- [x] A1 krok 2: ten sam test na Zephyrze 4.4.1 z modułem (sprawdzony na płytce 7.11.2026).
- [x] A1 krok 3: USB w ZMK na nowym stosie USB Zephyra (`patches/zmk-usb-next.patch`; sprawdzony na płytce 7.11.2026: przycisk 0 wpisuje „zmk”).
- [ ] A1 krok 4: płytka i klawiatura 60% (macierz 5 × 14, EC11, SH1106, PUSH/CON/BAK): shield `s2mini_60` kompiluje się, czeka na test.
- [x] ZMK Studio przez port szeregowy USB (CDC ACM) na nowym stosie: sprawdzone w zmk.studio na płytce 7.11.2026. Łatka wyłącza przerwanie TX w `uart_rpc_transport.c`, gdy bufor jest pusty (inaczej kolejka systemowa kręci się w kółko i wątek RPC nie kończy odpowiedzi). Uwaga: dziennika (log) nie wolno kierować na ten sam port CDC co Studio, bo zmk.studio odrzuca bajty spoza ramek.
- [x] A1 krok 6: budowanie w GitHub Actions (zakładka Actions → ostatni przebieg → artefakt `firmware-s2mini`).
- [ ] A1 krok 5: tryb GAME (Fn + G) i gałka z trybami: kompiluje się, czeka na test.
- [ ] A1 krok 8: ekran z danymi z PC przez Raw HID (głośność, CPU i GPU: obciążenie i temperatura, godzina) i program `pc-app`: kompiluje się, ekran sprawdzony w symulacji LVGL, czeka na test.

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

### Warstwy, gałka i tryb GAME

| Klawisz | Działanie |
| --- | --- |
| PUSH (wciśnięcie gałki), krótko | następny tryb gałki: VOLUME → SCROLL (kółko myszy) → TRACK (utwory) → BRIGHT (jasność ekranu); ekran pokazuje tryb przez 1,5 s |
| PUSH, długo (ponad 0,3 s) | wyciszenie |
| CON / BAK, krótko | poprzedni / następny widok ekranu (główny, porty COM) |
| CON / BAK, długo | play/pauza / następny utwór |
| Fn + G | tryb GAME (włącz/wyłącz): Win nie działa, Caps Lock wysyła F13 (można go przypisać w grze), ekran pokazuje GAME i temperatury |
| Fn + \\ | odblokowanie ZMK Studio |

Przyciski przy ekranie nie mają skrótów z Fn (Fn jest tylko dla klawiatury). Nazwy warstw na ekranie to `display-name` z keymapy (można je zmienić też w ZMK Studio). Nazwy trybów gałki są w `mode-names` węzła `knob` w keymapie; tam też można dodać, usunąć albo zmienić tryby (każdy tryb to zwykłe `zmk,behavior-sensor-rotate`). Ekran rozpoznaje tryb GAME po etykiecie `game_layer` warstwy.

### Ekran i dane z PC

Ekran ma widoki: główny (godzina, warstwa, CPU i GPU: obciążenie i temperatura, głośność, tryb gałki), GAME, zmianę trybu gałki, „no data from PC”, gdy przez 5 s nic nie przyszło, oraz listę portów COM (do 4 na ekranie; nowo podłączony port pokazuje ten widok sam na 3 s). Podgląd wyrenderowany z kodu ekranu: `ekran-z-firmware.png` w plikach projektu.

Dane wysyła `pc-app/s2mini_oled.py` raz na sekundę jako raport wyjściowy Raw HID (VID 1D50, PID 615E, strona 0xFF60):

| Bajt | Znaczenie |
| --- | --- |
| 0, 1 | 0x53 („S”), 0x01 (wersja) |
| 2 | flagi: 1 CPU, 2 GPU, 4 głośność, 8 godzina, 16 wyciszone |
| 3, 4 | CPU: obciążenie %, temperatura °C |
| 5, 6 | GPU: obciążenie %, temperatura °C |
| 7 | głośność % |
| 8, 9, 10 | godzina, minuta, sekunda |

Lista portów COM idzie co 2 s jako osobne ramki, po jednej na port: bajty 0x53, 0x02, numer portu, liczba portów, potem tekst do 28 znaków (np. „COM12 ZMK S2 mini”). Przy braku portów wysyłana jest jedna ramka z liczbą 0.

Na Windows:

```
pip install -r pc-app/requirements.txt
pythonw pc-app/s2mini_oled.py            (ikona w zasobniku)
python  pc-app/s2mini_oled.py --console  (wypisuje wysyłane dane)
python  pc-app/s2mini_oled.py --dry-run  (tylko odczyt danych, bez klawiatury)
```

Temperatury CPU i GPU czyta z [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor): uruchom go jako administrator i włącz Options → Remote Web Server (port 8085). Bez niego program wysyła obciążenie CPU (psutil) i dane GPU NVIDIA z `nvidia-smi`, a temperatury CPU nie ma. Żeby startował z Windows, połóż skrót do `pythonw s2mini_oled.py` w folderze `shell:startup`.

## Licencja

Apache-2.0, tak jak Zephyr i ZMK (MIT dla ZMK).
