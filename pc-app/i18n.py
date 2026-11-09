"""Język programu: polski albo angielski. Domyślnie język Windows (polski → PL, inny → EN).

tr("tekst po polsku", **parametry) zwraca tłumaczenie dla bieżącego języka; teksty bez
tłumaczenia zostają po polsku. Zmiana języka działa po ponownym uruchomieniu programu.
"""

import locale
import os

LANG = "pl"
CHOICES = (("auto", "Jak Windows / As Windows"), ("pl", "Polski"), ("en", "English"))


def system_lang():
    if os.name == "nt":
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "pl" if (lid & 0x3FF) == 0x15 else "en"
        except Exception:
            pass
    try:
        loc = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        loc = os.environ.get("LANG", "")
    return "pl" if (loc or "").lower().startswith(("pl", "polish")) else "en"


def init(setting="auto"):
    global LANG
    LANG = setting if setting in ("pl", "en") else system_lang()
    return LANG


# stany z s2mini_oled.py są po angielsku
PL = {"starting": "uruchamianie", "connected": "połączono", "keyboard not found": "nie widzę klawiatury"}


def tr(text, **kw):
    s = EN.get(text, text) if LANG == "en" else PL.get(text, text)
    return s.format(**kw) if kw else s


EN = {
    # okno
    "ekran klawiatury": "keyboard screen",
    "Szybki start": "Quick launch",
    "Keymapa": "Keymap",
    "Ekran": "Screen",
    "Stan": "Status",
    "●  połączono": "●  connected",
    "starting": "starting",
    "connected": "connected",
    "keyboard not found": "keyboard not found",
    "uruchamianie": "starting",
    "nie widzę klawiatury": "keyboard not found",
    "Otwórz": "Open",
    "Zakończ": "Quit",
    # szybki start
    "Na klawiaturze: CON/BAK do widoku LAUNCH, gałka wybiera, wciśnięcie uruchamia.\n"
    "Do {n} aplikacji. Podgląd po prawej ikonie to dokładnie to, co pokaże OLED.":
        "On the keyboard: CON/BAK to the LAUNCH view, turn the knob to choose, push to launch.\n"
        "Up to {n} apps. The preview right of each icon is exactly what the OLED shows.",
    "+ Z menu Start": "+ From Start menu",
    "+ Plik / program…": "+ File / program…",
    "Brak aplikacji. Dodaj z menu Start albo wskaż plik.": "No apps yet. Add one from the Start menu or pick a file.",
    "Nazwa na ekranie": "Name on screen",
    "Styl: {s}  ▾": "Style: {s}  ▾",
    "Odwróć": "Invert",
    "Obrazek…": "Image…",
    "Obrazek ikony": "Icon image",
    "Obrazki": "Images",
    "Wszystkie": "All files",
    "Styl ikony: {name}": "Icon style: {name}",
    "Ustaw dla wszystkich aplikacji": "Use for all apps",
    "Anuluj": "Cancel",
    "Dodaj z menu Start": "Add from Start menu",
    "Szukaj…": "Search…",
    "Wybierz program": "Choose a program",
    "Programy i skróty": "Programs and shortcuts",
    # style ikon
    "Auto": "Auto",
    "Plamy kolorów": "Colour areas",
    "Jasne/ciemne": "Light/dark",
    "Odcienie": "Shades",
    "Rysunek": "Line art",
    "Sylwetka": "Silhouette",
    "Szczegóły": "Detail",
    "Kontur": "Outline",
    # ekran
    "Co program wysyła na ekran klawiatury. Zmiany działają od razu.":
        "What the program sends to the keyboard screen. Changes apply immediately.",
    "Procesor (obciążenie, temperatura)": "CPU (load, temperature)",
    "Karta graficzna": "Graphics card",
    "Grafika zintegrowana (Intel)": "Integrated graphics (Intel)",
    "Głośność": "Volume",
    "Prędkość sieci": "Network speed",
    "Co gra (tytuł, wykonawca)": "Now playing (title, artist)",
    "Porty COM": "COM ports",
    "Powiadomienia Windows (widoczne dla każdego przy klawiaturze)":
        "Windows notifications (visible to anyone near the keyboard)",
    "Domyślny styl ikon nowych aplikacji": "Default icon style for new apps",
    "Uruchamiaj razem z Windows": "Start with Windows",
    "Język": "Language",
    "Zmiana języka działa po ponownym uruchomieniu programu.": "The language changes after restarting the program.",
    "Temperatury CPU/GPU: LibreHardwareMonitor z włączonym „Remote Web Server” (port 8085).":
        "CPU/GPU temperatures: LibreHardwareMonitor with “Remote Web Server” enabled (port 8085).",
    "Ostatnie dane wysłane do klawiatury.": "Last data sent to the keyboard.",
    # keymapa
    "Zmiany idą od razu do klawiatury (jak w ZMK Studio). "
    "„Zapisz w klawiaturze” zostawia je na stałe, „Cofnij” wraca do zapisanych.":
        "Changes go to the keyboard right away (like ZMK Studio). "
        "“Save to keyboard” keeps them, “Discard” returns to the saved keymap.",
    "Połącz z klawiaturą": "Connect to keyboard",
    "Rozłącz": "Disconnect",
    "Nie połączono": "Not connected",
    "Cofnij zmiany": "Discard changes",
    "Zapisz w klawiaturze": "Save to keyboard",
    "Warstwa": "Layer",
    "Zmień nazwę": "Rename",
    "Połącz się z klawiaturą, potem kliknij klawisz na rysunku.": "Connect to the keyboard, then click a key in the picture.",
    "Kliknij klawisz na rysunku, żeby zmienić jego działanie na tej warstwie.":
        "Click a key in the picture to change what it does on this layer.",
    "Łączenie…": "Connecting…",
    "{dev}: zablokowana. Odblokuj na klawiaturze: Fn + \\": "{dev}: locked. Unlock on the keyboard: Fn + \\",
    "{dev}: wczytuję układ…": "{dev}: loading keymap…",
    "{dev}: połączono": "{dev}: connected",
    "{dev}: niezapisane zmiany": "{dev}: unsaved changes",
    "{dev}: zapisane": "{dev}: saved",
    "Błąd: {e}": "Error: {e}",
    "Warstwa {i}": "Layer {i}",
    "Nowa nazwa (do {n} znaków):": "New name (up to {n} characters):",
    "Nazwa warstwy": "Layer name",
    "Brak połączenia z klawiaturą": "Keyboard not connected",
    "Klawisz {n}": "Key {n}",
    "Akcja": "Action",
    "⌨  Naciśnij klawisz…": "⌨  Press a key…",
    "Klawisz": "Key",
    "Wartość": "Value",
    "Przytrzymanie": "Hold",
    "Stuknięcie": "Tap",
    "Ta akcja nie ma ustawień.": "This action has no settings.",
    "Z listy…": "From list…",
    "Naciśnij…": "Press…",
    "Naciśnij klawisz": "Press a key",
    "Naciśnij klawisz albo skrót (np. Ctrl+C).\nSam modyfikator: naciśnij i puść.":
        "Press a key or a shortcut (e.g. Ctrl+C).\nModifier alone: press and release.",
    "nieznany klawisz ({k})": "unknown key ({k})",
    "Wybierz klawisz": "Choose a key",
    "Z:": "With:",
    # błędy Studio
    "nie widzę portu COM klawiatury (1D50:615E)": "keyboard COM port not found (1D50:615E)",
    "połączenie zamknięte": "connection closed",
    "brak odpowiedzi klawiatury": "no response from keyboard",
    "klawiatura zablokowana": "keyboard is locked",
    "błąd ogólny": "general error",
    "nieznane zapytanie": "unknown request",
    "zła pozycja": "invalid position",
    "zła akcja": "invalid action",
    "złe parametry": "invalid parameters",
    "zapis nieobsługiwany": "saving not supported",
    "brak miejsca": "no space left",
    "błąd zapisu": "save error",
    "nie udało się zmienić nazwy warstwy": "could not rename layer",
    # grupy klawiszy
    "Litery": "Letters", "Cyfry": "Digits", "Symbole": "Symbols", "Edycja": "Editing",
    "Modyfikatory": "Modifiers", "Nawigacja": "Navigation", "F1–F24": "F1–F24", "Multimedia": "Media",
    "Numeryczna": "Keypad", "Międzynarodowe": "International",
}
