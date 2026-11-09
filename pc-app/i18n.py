"""Program language: Polish or English. Defaults to the Windows UI language (Polish -> PL, else EN).

tr("English text", **params) returns the text for the current language; texts without a
translation stay in English. A language change applies after restarting the program.
"""

import locale
import os

LANG = "en"
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


def tr(text, **kw):
    s = PL.get(text, text) if LANG == "pl" else text
    return s.format(**kw) if kw else s


PL = {
    'keyboard screen': 'ekran klawiatury',
    'Quick launch': 'Szybki start',
    'Keymap': 'Keymapa',
    'Screen': 'Ekran',
    'Status': 'Stan',
    '●  connected': '●  połączono',
    'starting': 'uruchamianie',
    'keyboard not found': 'nie widzę klawiatury',
    'Open': 'Otwórz',
    'Quit': 'Zakończ',
    'On the keyboard: CON/BAK to the LAUNCH view, turn the knob to choose, push to launch.\nUp to {n} apps. The preview right of each icon is exactly what the OLED shows.':
        'Na klawiaturze: CON/BAK do widoku LAUNCH, gałka wybiera, wciśnięcie uruchamia.\nDo {n} aplikacji. Podgląd po prawej ikonie to dokładnie to, co pokaże OLED.',
    '+ From Start menu': '+ Z menu Start',
    '+ File / program…': '+ Plik / program…',
    'No apps yet. Add one from the Start menu or pick a file.':
        'Brak aplikacji. Dodaj z menu Start albo wskaż plik.',
    'Name on screen': 'Nazwa na ekranie',
    'Style: {s}  ▾': 'Styl: {s}  ▾',
    'Invert': 'Odwróć',
    'Image…': 'Obrazek…',
    'Icon image': 'Obrazek ikony',
    'Images': 'Obrazki',
    'All files': 'Wszystkie',
    'Icon style: {name}': 'Styl ikony: {name}',
    'Use for all apps': 'Ustaw dla wszystkich aplikacji',
    'Cancel': 'Anuluj',
    'Add from Start menu': 'Dodaj z menu Start',
    'Search…': 'Szukaj…',
    'Choose a program': 'Wybierz program',
    'Programs and shortcuts': 'Programy i skróty',
    'Colour areas': 'Plamy kolorów',
    'Light/dark': 'Jasne/ciemne',
    'Shades': 'Odcienie',
    'Line art': 'Rysunek',
    'Silhouette': 'Sylwetka',
    'Detail': 'Szczegóły',
    'Outline': 'Kontur',
    'What the program sends to the keyboard screen. Changes apply immediately.':
        'Co program wysyła na ekran klawiatury. Zmiany działają od razu.',
    'CPU (load, temperature)': 'Procesor (obciążenie, temperatura)',
    'Graphics card': 'Karta graficzna',
    'Integrated graphics (Intel)': 'Grafika zintegrowana (Intel)',
    'Volume': 'Głośność',
    'Network speed': 'Prędkość sieci',
    'Now playing (title, artist)': 'Co gra (tytuł, wykonawca)',
    'COM ports': 'Porty COM',
    'Windows notifications (visible to anyone near the keyboard)':
        'Powiadomienia Windows (widoczne dla każdego przy klawiaturze)',
    'Default icon style for new apps': 'Domyślny styl ikon nowych aplikacji',
    'Start with Windows': 'Uruchamiaj razem z Windows',
    'Language': 'Język',
    'The language changes after restarting the program.':
        'Zmiana języka działa po ponownym uruchomieniu programu.',
    'CPU/GPU temperatures: LibreHardwareMonitor with “Remote Web Server” enabled (port 8085).':
        'Temperatury CPU/GPU: LibreHardwareMonitor z włączonym „Remote Web Server” (port 8085).',
    'Last data sent to the keyboard.': 'Ostatnie dane wysłane do klawiatury.',
    'Changes go to the keyboard right away (like ZMK Studio). “Save to keyboard” keeps them, “Discard” returns to the saved keymap.':
        'Zmiany idą od razu do klawiatury (jak w ZMK Studio). „Zapisz w klawiaturze” zostawia je na stałe, „Cofnij” wraca do zapisanych.',
    'Connect to keyboard': 'Połącz z klawiaturą',
    'Disconnect': 'Rozłącz',
    'Not connected': 'Nie połączono',
    'Discard changes': 'Cofnij zmiany',
    'Save to keyboard': 'Zapisz w klawiaturze',
    'Layer': 'Warstwa',
    'Rename': 'Zmień nazwę',
    'Connect to the keyboard, then click a key in the picture.':
        'Połącz się z klawiaturą, potem kliknij klawisz na rysunku.',
    'Click a key in the picture to change what it does on this layer.':
        'Kliknij klawisz na rysunku, żeby zmienić jego działanie na tej warstwie.',
    'Connecting…': 'Łączenie…',
    '{dev}: locked. Unlock on the keyboard: Fn + \\':
        '{dev}: zablokowana. Odblokuj na klawiaturze: Fn + \\',
    '{dev}: loading keymap…': '{dev}: wczytuję układ…',
    '{dev}: connected': '{dev}: połączono',
    '{dev}: unsaved changes': '{dev}: niezapisane zmiany',
    '{dev}: saved': '{dev}: zapisane',
    'Error: {e}': 'Błąd: {e}',
    'Layer {i}': 'Warstwa {i}',
    'New name (up to {n} characters):': 'Nowa nazwa (do {n} znaków):',
    'Layer name': 'Nazwa warstwy',
    'Keyboard not connected': 'Brak połączenia z klawiaturą',
    'Key {n}': 'Klawisz {n}',
    'Action': 'Akcja',
    '⌨  Press a key…': '⌨  Naciśnij klawisz…',
    'Key': 'Klawisz',
    'Value': 'Wartość',
    'Hold': 'Przytrzymanie',
    'Tap': 'Stuknięcie',
    'This action has no settings.': 'Ta akcja nie ma ustawień.',
    'From list…': 'Z listy…',
    'Press…': 'Naciśnij…',
    'Press a key': 'Naciśnij klawisz',
    'Press a key or a shortcut (e.g. Ctrl+C).\nModifier alone: press and release.':
        'Naciśnij klawisz albo skrót (np. Ctrl+C).\nSam modyfikator: naciśnij i puść.',
    'unknown key ({k})': 'nieznany klawisz ({k})',
    'Choose a key': 'Wybierz klawisz',
    'With:': 'Z:',
    'keyboard COM port not found (1D50:615E)': 'nie widzę portu COM klawiatury (1D50:615E)',
    'connection closed': 'połączenie zamknięte',
    'no response from keyboard': 'brak odpowiedzi klawiatury',
    'keyboard is locked': 'klawiatura zablokowana',
    'general error': 'błąd ogólny',
    'unknown request': 'nieznane zapytanie',
    'invalid position': 'zła pozycja',
    'invalid action': 'zła akcja',
    'invalid parameters': 'złe parametry',
    'saving not supported': 'zapis nieobsługiwany',
    'no space left': 'brak miejsca',
    'save error': 'błąd zapisu',
    'could not rename layer': 'nie udało się zmienić nazwy warstwy',
    'Letters': 'Litery',
    'Digits': 'Cyfry',
    'Symbols': 'Symbole',
    'Editing': 'Edycja',
    'Modifiers': 'Modyfikatory',
    'Navigation': 'Nawigacja',
    'Media': 'Multimedia',
    'Keypad': 'Numeryczna',
    'International': 'Międzynarodowe',
    'error {code}': 'błąd {code}',
    'no response': 'brak odpowiedzi',
    'unexpected response': 'nieoczekiwana odpowiedź',
    'no space for another layer': 'brak miejsca na warstwę',
    'could not add layer': 'nie udało się dodać warstwy',
    'could not remove layer': 'nie udało się usunąć warstwy',
    'could not move layer': 'nie udało się przesunąć warstwy',
    'decode error': 'błąd dekodowania',
    'encode error': 'błąd kodowania',
    'connected': 'połączono',
}
