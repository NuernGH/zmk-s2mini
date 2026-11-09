"""ZMK key codes: name, short label, Polish and English description, HID page and usage, Windows key code (VK).

Names and descriptions as in the Keyboard-maker generator's Keymap tab (src/lib/keymap-keys.ts).
ZMK &kp parameter value: (modifiers << 24) | (page << 16) | usage.
"""

KEYBOARD, CONSUMER = 0x07, 0x0C

# (id, short, description, group, page, usage, Windows VK or None)
_K = []


def _k(id_, short, pl, group, usage, vk=None, page=KEYBOARD):
    _K.append((id_, short, pl, group, page, usage, vk))


for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _k(c, c, f"Litera {c}", "Letters", 0x04 + i, ord(c))
for i, d in enumerate("1234567890"):
    _k(f"N{d}", d, f"Cyfra {d}", "Digits", 0x1E + i, ord(d))
_k("RET", "Enter", "Enter", "Editing", 0x28, 0x0D)
_k("ESC", "Esc", "Escape", "Editing", 0x29, 0x1B)
_k("BSPC", "Bksp", "Backspace", "Editing", 0x2A, 0x08)
_k("TAB", "Tab", "Tabulator", "Editing", 0x2B, 0x09)
_k("SPACE", "Spacja", "Spacja", "Editing", 0x2C, 0x20)
_k("MINUS", "-", "Minus  - _", "Symbols", 0x2D, 0xBD)
_k("EQUAL", "=", "Równa się  = +", "Symbols", 0x2E, 0xBB)
_k("LBKT", "[", "Nawias kwadratowy lewy  [ {", "Symbols", 0x2F, 0xDB)
_k("RBKT", "]", "Nawias kwadratowy prawy  ] }", "Symbols", 0x30, 0xDD)
_k("BSLH", "\\", "Ukośnik wsteczny  \\ |", "Symbols", 0x31, 0xDC)
_k("NON_US_HASH", "ISO #", "Klawisz ISO # ~ (obok Enter)", "International", 0x32)
_k("SEMI", ";", "Średnik  ; :", "Symbols", 0x33, 0xBA)
_k("SQT", "'", "Apostrof  ' \"", "Symbols", 0x34, 0xDE)
_k("GRAVE", "` ~", "Grawis  ` ~ (tylda)", "Symbols", 0x35, 0xC0)
_k("COMMA", ",", "Przecinek  , <", "Symbols", 0x36, 0xBC)
_k("DOT", ".", "Kropka  . >", "Symbols", 0x37, 0xBE)
_k("FSLH", "/", "Ukośnik  / ?", "Symbols", 0x38, 0xBF)
_k("CAPS", "Caps", "Caps Lock", "Editing", 0x39, 0x14)
for i in range(12):
    _k(f"F{i + 1}", f"F{i + 1}", f"F{i + 1}", "F1–F24", 0x3A + i, 0x70 + i)
_k("PSCRN", "PrtSc", "Print Screen", "Editing", 0x46, 0x2C)
_k("SLCK", "ScrLk", "Scroll Lock", "Editing", 0x47, 0x91)
_k("PAUSE_BREAK", "Pause", "Pause / Break", "Editing", 0x48, 0x13)
_k("INS", "Ins", "Insert", "Editing", 0x49, 0x2D)
_k("HOME", "Home", "Home", "Navigation", 0x4A, 0x24)
_k("PG_UP", "PgUp", "Page Up", "Navigation", 0x4B, 0x21)
_k("DEL", "Del", "Delete", "Editing", 0x4C, 0x2E)
_k("END", "End", "End", "Navigation", 0x4D, 0x23)
_k("PG_DN", "PgDn", "Page Down", "Navigation", 0x4E, 0x22)
_k("RIGHT", "→", "Strzałka w prawo", "Navigation", 0x4F, 0x27)
_k("LEFT", "←", "Strzałka w lewo", "Navigation", 0x50, 0x25)
_k("DOWN", "↓", "Strzałka w dół", "Navigation", 0x51, 0x28)
_k("UP", "↑", "Strzałka w górę", "Navigation", 0x52, 0x26)
_k("KP_NUMLOCK", "NumLk", "Num Lock", "Keypad", 0x53, 0x90)
_k("KP_DIVIDE", "Num /", "Klawiatura numeryczna /", "Keypad", 0x54, 0x6F)
_k("KP_MULTIPLY", "Num *", "Klawiatura numeryczna *", "Keypad", 0x55, 0x6A)
_k("KP_MINUS", "Num -", "Klawiatura numeryczna -", "Keypad", 0x56, 0x6D)
_k("KP_PLUS", "Num +", "Klawiatura numeryczna +", "Keypad", 0x57, 0x6B)
_k("KP_ENTER", "Num ⏎", "Klawiatura numeryczna Enter", "Keypad", 0x58)
for i in range(9):
    _k(f"KP_N{i + 1}", f"Num {i + 1}", f"Klawiatura numeryczna {i + 1}", "Keypad", 0x59 + i, 0x61 + i)
_k("KP_N0", "Num 0", "Klawiatura numeryczna 0", "Keypad", 0x62, 0x60)
_k("KP_DOT", "Num .", "Klawiatura numeryczna , (kropka)", "Keypad", 0x63, 0x6E)
_k("NON_US_BSLH", "ISO \\", "Klawisz ISO obok lewego Shift  \\ |", "International", 0x64, 0xE2)
_k("K_APP", "Menu", "Menu kontekstowe", "Editing", 0x65, 0x5D)
_k("KP_EQUAL", "Num =", "Klawiatura numeryczna =", "Keypad", 0x67)
for i in range(12):
    _k(f"F{i + 13}", f"F{i + 13}", f"F{i + 13}", "F1–F24", 0x68 + i, 0x7C + i)
_k("INT1", "Ro", "Japoński Ro (INT1)", "International", 0x87)
_k("INT3", "Yen", "Japoński Yen (INT3)", "International", 0x89)
_k("LANG1", "Lang1", "Przełącz język 1", "International", 0x90)
_k("LANG2", "Lang2", "Przełącz język 2", "International", 0x91)
_k("LCTRL", "Ctrl", "Lewy Ctrl", "Modifiers", 0xE0)
_k("LSHFT", "Shift", "Lewy Shift", "Modifiers", 0xE1)
_k("LALT", "Alt", "Lewy Alt", "Modifiers", 0xE2)
_k("LGUI", "Win", "Lewy Win (GUI)", "Modifiers", 0xE3, 0x5B)
_k("RCTRL", "Ctrl", "Prawy Ctrl", "Modifiers", 0xE4)
_k("RSHFT", "Shift", "Prawy Shift", "Modifiers", 0xE5)
_k("RALT", "AltGr", "Prawy Alt (AltGr)", "Modifiers", 0xE6)
_k("RGUI", "Win", "Prawy Win (GUI)", "Modifiers", 0xE7, 0x5C)
_k("C_VOL_UP", "Vol+", "Głośniej", "Media", 0xE9, 0xAF, CONSUMER)
_k("C_VOL_DN", "Vol−", "Ciszej", "Media", 0xEA, 0xAE, CONSUMER)
_k("C_MUTE", "Mute", "Wycisz", "Media", 0xE2, 0xAD, CONSUMER)
_k("C_PP", "Play", "Odtwórz / pauza", "Media", 0xCD, 0xB3, CONSUMER)
_k("C_NEXT", "Next", "Następny utwór", "Media", 0xB5, 0xB0, CONSUMER)
_k("C_PREV", "Prev", "Poprzedni utwór", "Media", 0xB6, 0xB1, CONSUMER)
_k("C_STOP", "Stop", "Zatrzymaj", "Media", 0xB7, 0xB2, CONSUMER)
_k("C_BRI_UP", "Jasn+", "Jaśniej (ekran)", "Media", 0x6F, None, CONSUMER)
_k("C_BRI_DN", "Jasn−", "Ciemniej (ekran)", "Media", 0x70, None, CONSUMER)
_k("C_AL_CALC", "Kalk", "Kalkulator", "Media", 0x192, 0xB7, CONSUMER)
_k("C_AL_FILES", "Pliki", "Eksplorator plików", "Media", 0x194, 0xB6, CONSUMER)
_k("C_AL_WWW", "WWW", "Przeglądarka", "Media", 0x196, 0xAC, CONSUMER)
_k("C_AL_MAIL", "Poczta", "Poczta", "Media", 0x18A, 0xB4, CONSUMER)

_EN = {
    "Enter": "Enter", "Escape": "Escape", "Backspace": "Backspace", "Tabulator": "Tab", "Spacja": "Space",
    "Minus  - _": "Minus  - _", "Równa się  = +": "Equal  = +", "Nawias kwadratowy lewy  [ {": "Left bracket  [ {",
    "Nawias kwadratowy prawy  ] }": "Right bracket  ] }", "Ukośnik wsteczny  \\ |": "Backslash  \\ |",
    "Klawisz ISO # ~ (obok Enter)": "ISO # ~ key (next to Enter)", "Średnik  ; :": "Semicolon  ; :",
    "Apostrof  ' \"": "Quote  ' \"", "Grawis  ` ~ (tylda)": "Grave  ` ~", "Przecinek  , <": "Comma  , <",
    "Kropka  . >": "Period  . >", "Ukośnik  / ?": "Slash  / ?", "Caps Lock": "Caps Lock", "Print Screen": "Print Screen",
    "Scroll Lock": "Scroll Lock", "Pause / Break": "Pause / Break", "Insert": "Insert", "Home": "Home",
    "Page Up": "Page Up", "Delete": "Delete", "End": "End", "Page Down": "Page Down",
    "Strzałka w prawo": "Right arrow", "Strzałka w lewo": "Left arrow", "Strzałka w dół": "Down arrow",
    "Strzałka w górę": "Up arrow", "Num Lock": "Num Lock", "Klawisz ISO obok lewego Shift  \\ |": "ISO key next to left Shift",
    "Menu kontekstowe": "Context menu (App)", "Japoński Ro (INT1)": "International 1 (Ro)",
    "Japoński Yen (INT3)": "International 3 (Yen)", "Przełącz język 1": "Language 1", "Przełącz język 2": "Language 2",
    "Lewy Ctrl": "Left Ctrl", "Lewy Shift": "Left Shift", "Lewy Alt": "Left Alt", "Lewy Win (GUI)": "Left GUI (Win)",
    "Prawy Ctrl": "Right Ctrl", "Prawy Shift": "Right Shift", "Prawy Alt (AltGr)": "Right Alt (AltGr)",
    "Prawy Win (GUI)": "Right GUI (Win)", "Głośniej": "Volume up", "Ciszej": "Volume down", "Wycisz": "Mute",
    "Odtwórz / pauza": "Play / pause", "Następny utwór": "Next track", "Poprzedni utwór": "Previous track",
    "Zatrzymaj": "Stop", "Jaśniej (ekran)": "Brightness up", "Ciemniej (ekran)": "Brightness down",
    "Kalkulator": "Calculator", "Eksplorator plików": "File browser", "Przeglądarka": "Web browser", "Poczta": "Mail",
}
_SHORT_EN = {"Spacja": "Space", "Kalk": "Calc", "Pliki": "Files", "Poczta": "Mail", "Jasn+": "Bri+", "Jasn−": "Bri−"}


def _en(pl):
    for a, b in (("Litera ", "Letter "), ("Cyfra ", "Digit "), ("Klawiatura numeryczna , (kropka)", "Keypad ."),
                 ("Klawiatura numeryczna ", "Keypad ")):
        if pl.startswith(a):
            return b + pl[len(a):]
    return _EN.get(pl, pl)


KEYS = [dict(id=a, short=b, pl=c, en=_en(c), short_en=_SHORT_EN.get(b, b), group=d, page=e, usage=f, vk=g)
        for a, b, c, d, e, f, g in _K]
BY_USAGE = {(k["page"], k["usage"]): k for k in KEYS}
BY_ID = {k["id"]: k for k in KEYS}
BY_VK = {}
for _x in KEYS:
    if _x["vk"] is not None and _x["vk"] not in BY_VK:
        BY_VK[_x["vk"]] = _x
GROUPS = ["Letters", "Digits", "Symbols", "Editing", "Modifiers", "Navigation", "F1–F24", "Media",
          "Keypad", "International"]

# modifiers in the top byte (ZMK: LC=0x01 … RG=0x80)
MODS = [("LC", "Ctrl", 0x01), ("LS", "Shift", 0x02), ("LA", "Alt", 0x04), ("LG", "Win", 0x08),
        ("RC", "RCtrl", 0x10), ("RS", "RShift", 0x20), ("RA", "AltGr", 0x40), ("RG", "RWin", 0x80)]
# Tk modifier keysym -> (bit, key id)
MOD_KEYSYMS = {"Control_L": (0x01, "LCTRL"), "Shift_L": (0x02, "LSHFT"), "Alt_L": (0x04, "LALT"),
               "Win_L": (0x08, "LGUI"), "Super_L": (0x08, "LGUI"),
               "Control_R": (0x10, "RCTRL"), "Shift_R": (0x20, "RSHFT"), "Alt_R": (0x40, "RALT"),
               "Win_R": (0x80, "RGUI"), "Super_R": (0x80, "RGUI"), "ISO_Level3_Shift": (0x40, "RALT")}


def encode(key, mods=0):
    return (mods << 24) | (key["page"] << 16) | key["usage"]


def decode(value):
    """&kp param -> (key or None, modifier mask, page, usage)."""
    mods = (value >> 24) & 0xFF
    page = (value >> 16) & 0xFF or KEYBOARD
    usage = value & 0xFFFF
    return BY_USAGE.get((page, usage)), mods, page, usage


def mods_text(mods):
    return "+".join(name for _, name, bit in MODS if mods & bit)


def _lang():
    try:
        import i18n
        return i18n.LANG
    except Exception:
        return "pl"


def desc(key):
    return key["en"] if _lang() == "en" else key["pl"]


def label(value, long=False):
    key, mods, page, usage = decode(value)
    en = _lang() == "en"
    if key:
        name = desc(key) if long else (key["short_en"] if en else key["short"])
    else:
        name = f"0x{page:02X}:{usage:04X}"
    if mods:
        return f"{mods_text(mods)}+{name}"
    return name
