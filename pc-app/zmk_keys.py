"""Kody klawiszy ZMK: nazwa, krótki opis, opis po polsku, strona i numer HID, kod klawisza Windows (VK).

Nazwy i opisy jak w zakładce Keymapa generatora (Keyboard-maker, src/lib/keymap-keys.ts).
Wartość parametru &kp w ZMK: (modyfikatory << 24) | (strona << 16) | numer.
"""

KEYBOARD, CONSUMER = 0x07, 0x0C

# (id, short, opis, grupa, strona, numer, VK Windows lub None)
_K = []


def _k(id_, short, pl, group, usage, vk=None, page=KEYBOARD):
    _K.append((id_, short, pl, group, page, usage, vk))


for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _k(c, c, f"Litera {c}", "Litery", 0x04 + i, ord(c))
for i, d in enumerate("1234567890"):
    _k(f"N{d}", d, f"Cyfra {d}", "Cyfry", 0x1E + i, ord(d))
_k("RET", "Enter", "Enter", "Edycja", 0x28, 0x0D)
_k("ESC", "Esc", "Escape", "Edycja", 0x29, 0x1B)
_k("BSPC", "Bksp", "Backspace", "Edycja", 0x2A, 0x08)
_k("TAB", "Tab", "Tabulator", "Edycja", 0x2B, 0x09)
_k("SPACE", "Spacja", "Spacja", "Edycja", 0x2C, 0x20)
_k("MINUS", "-", "Minus  - _", "Symbole", 0x2D, 0xBD)
_k("EQUAL", "=", "Równa się  = +", "Symbole", 0x2E, 0xBB)
_k("LBKT", "[", "Nawias kwadratowy lewy  [ {", "Symbole", 0x2F, 0xDB)
_k("RBKT", "]", "Nawias kwadratowy prawy  ] }", "Symbole", 0x30, 0xDD)
_k("BSLH", "\\", "Ukośnik wsteczny  \\ |", "Symbole", 0x31, 0xDC)
_k("NON_US_HASH", "ISO #", "Klawisz ISO # ~ (obok Enter)", "Międzynarodowe", 0x32)
_k("SEMI", ";", "Średnik  ; :", "Symbole", 0x33, 0xBA)
_k("SQT", "'", "Apostrof  ' \"", "Symbole", 0x34, 0xDE)
_k("GRAVE", "` ~", "Grawis  ` ~ (tylda)", "Symbole", 0x35, 0xC0)
_k("COMMA", ",", "Przecinek  , <", "Symbole", 0x36, 0xBC)
_k("DOT", ".", "Kropka  . >", "Symbole", 0x37, 0xBE)
_k("FSLH", "/", "Ukośnik  / ?", "Symbole", 0x38, 0xBF)
_k("CAPS", "Caps", "Caps Lock", "Edycja", 0x39, 0x14)
for i in range(12):
    _k(f"F{i + 1}", f"F{i + 1}", f"F{i + 1}", "F1–F24", 0x3A + i, 0x70 + i)
_k("PSCRN", "PrtSc", "Print Screen", "Edycja", 0x46, 0x2C)
_k("SLCK", "ScrLk", "Scroll Lock", "Edycja", 0x47, 0x91)
_k("PAUSE_BREAK", "Pause", "Pause / Break", "Edycja", 0x48, 0x13)
_k("INS", "Ins", "Insert", "Edycja", 0x49, 0x2D)
_k("HOME", "Home", "Home", "Nawigacja", 0x4A, 0x24)
_k("PG_UP", "PgUp", "Page Up", "Nawigacja", 0x4B, 0x21)
_k("DEL", "Del", "Delete", "Edycja", 0x4C, 0x2E)
_k("END", "End", "End", "Nawigacja", 0x4D, 0x23)
_k("PG_DN", "PgDn", "Page Down", "Nawigacja", 0x4E, 0x22)
_k("RIGHT", "→", "Strzałka w prawo", "Nawigacja", 0x4F, 0x27)
_k("LEFT", "←", "Strzałka w lewo", "Nawigacja", 0x50, 0x25)
_k("DOWN", "↓", "Strzałka w dół", "Nawigacja", 0x51, 0x28)
_k("UP", "↑", "Strzałka w górę", "Nawigacja", 0x52, 0x26)
_k("KP_NUMLOCK", "NumLk", "Num Lock", "Numeryczna", 0x53, 0x90)
_k("KP_DIVIDE", "Num /", "Klawiatura numeryczna /", "Numeryczna", 0x54, 0x6F)
_k("KP_MULTIPLY", "Num *", "Klawiatura numeryczna *", "Numeryczna", 0x55, 0x6A)
_k("KP_MINUS", "Num -", "Klawiatura numeryczna -", "Numeryczna", 0x56, 0x6D)
_k("KP_PLUS", "Num +", "Klawiatura numeryczna +", "Numeryczna", 0x57, 0x6B)
_k("KP_ENTER", "Num ⏎", "Klawiatura numeryczna Enter", "Numeryczna", 0x58)
for i in range(9):
    _k(f"KP_N{i + 1}", f"Num {i + 1}", f"Klawiatura numeryczna {i + 1}", "Numeryczna", 0x59 + i, 0x61 + i)
_k("KP_N0", "Num 0", "Klawiatura numeryczna 0", "Numeryczna", 0x62, 0x60)
_k("KP_DOT", "Num .", "Klawiatura numeryczna , (kropka)", "Numeryczna", 0x63, 0x6E)
_k("NON_US_BSLH", "ISO \\", "Klawisz ISO obok lewego Shift  \\ |", "Międzynarodowe", 0x64, 0xE2)
_k("K_APP", "Menu", "Menu kontekstowe", "Edycja", 0x65, 0x5D)
_k("KP_EQUAL", "Num =", "Klawiatura numeryczna =", "Numeryczna", 0x67)
for i in range(12):
    _k(f"F{i + 13}", f"F{i + 13}", f"F{i + 13}", "F1–F24", 0x68 + i, 0x7C + i)
_k("INT1", "Ro", "Japoński Ro (INT1)", "Międzynarodowe", 0x87)
_k("INT3", "Yen", "Japoński Yen (INT3)", "Międzynarodowe", 0x89)
_k("LANG1", "Lang1", "Przełącz język 1", "Międzynarodowe", 0x90)
_k("LANG2", "Lang2", "Przełącz język 2", "Międzynarodowe", 0x91)
_k("LCTRL", "Ctrl", "Lewy Ctrl", "Modyfikatory", 0xE0)
_k("LSHFT", "Shift", "Lewy Shift", "Modyfikatory", 0xE1)
_k("LALT", "Alt", "Lewy Alt", "Modyfikatory", 0xE2)
_k("LGUI", "Win", "Lewy Win (GUI)", "Modyfikatory", 0xE3, 0x5B)
_k("RCTRL", "Ctrl", "Prawy Ctrl", "Modyfikatory", 0xE4)
_k("RSHFT", "Shift", "Prawy Shift", "Modyfikatory", 0xE5)
_k("RALT", "AltGr", "Prawy Alt (AltGr)", "Modyfikatory", 0xE6)
_k("RGUI", "Win", "Prawy Win (GUI)", "Modyfikatory", 0xE7, 0x5C)
_k("C_VOL_UP", "Vol+", "Głośniej", "Multimedia", 0xE9, 0xAF, CONSUMER)
_k("C_VOL_DN", "Vol−", "Ciszej", "Multimedia", 0xEA, 0xAE, CONSUMER)
_k("C_MUTE", "Mute", "Wycisz", "Multimedia", 0xE2, 0xAD, CONSUMER)
_k("C_PP", "Play", "Odtwórz / pauza", "Multimedia", 0xCD, 0xB3, CONSUMER)
_k("C_NEXT", "Next", "Następny utwór", "Multimedia", 0xB5, 0xB0, CONSUMER)
_k("C_PREV", "Prev", "Poprzedni utwór", "Multimedia", 0xB6, 0xB1, CONSUMER)
_k("C_STOP", "Stop", "Zatrzymaj", "Multimedia", 0xB7, 0xB2, CONSUMER)
_k("C_BRI_UP", "Jasn+", "Jaśniej (ekran)", "Multimedia", 0x6F, None, CONSUMER)
_k("C_BRI_DN", "Jasn−", "Ciemniej (ekran)", "Multimedia", 0x70, None, CONSUMER)
_k("C_AL_CALC", "Kalk", "Kalkulator", "Multimedia", 0x192, 0xB7, CONSUMER)
_k("C_AL_FILES", "Pliki", "Eksplorator plików", "Multimedia", 0x194, 0xB6, CONSUMER)
_k("C_AL_WWW", "WWW", "Przeglądarka", "Multimedia", 0x196, 0xAC, CONSUMER)
_k("C_AL_MAIL", "Poczta", "Poczta", "Multimedia", 0x18A, 0xB4, CONSUMER)

KEYS = [dict(id=a, short=b, pl=c, group=d, page=e, usage=f, vk=g) for a, b, c, d, e, f, g in _K]
BY_USAGE = {(k["page"], k["usage"]): k for k in KEYS}
BY_ID = {k["id"]: k for k in KEYS}
BY_VK = {}
for _x in KEYS:
    if _x["vk"] is not None and _x["vk"] not in BY_VK:
        BY_VK[_x["vk"]] = _x
GROUPS = ["Litery", "Cyfry", "Symbole", "Edycja", "Modyfikatory", "Nawigacja", "F1–F24", "Multimedia",
          "Numeryczna", "Międzynarodowe"]

# modyfikatory w górnym bajcie (ZMK: LC=0x01 … RG=0x80)
MODS = [("LC", "Ctrl", 0x01), ("LS", "Shift", 0x02), ("LA", "Alt", 0x04), ("LG", "Win", 0x08),
        ("RC", "RCtrl", 0x10), ("RS", "RShift", 0x20), ("RA", "AltGr", 0x40), ("RG", "RWin", 0x80)]
# Tk keysym modyfikatora -> (bit, id klawisza)
MOD_KEYSYMS = {"Control_L": (0x01, "LCTRL"), "Shift_L": (0x02, "LSHFT"), "Alt_L": (0x04, "LALT"),
               "Win_L": (0x08, "LGUI"), "Super_L": (0x08, "LGUI"),
               "Control_R": (0x10, "RCTRL"), "Shift_R": (0x20, "RSHFT"), "Alt_R": (0x40, "RALT"),
               "Win_R": (0x80, "RGUI"), "Super_R": (0x80, "RGUI"), "ISO_Level3_Shift": (0x40, "RALT")}


def encode(key, mods=0):
    return (mods << 24) | (key["page"] << 16) | key["usage"]


def decode(value):
    """param &kp -> (klawisz albo None, maska modyfikatorów, strona, numer)."""
    mods = (value >> 24) & 0xFF
    page = (value >> 16) & 0xFF or KEYBOARD
    usage = value & 0xFFFF
    return BY_USAGE.get((page, usage)), mods, page, usage


def mods_text(mods):
    return "+".join(name for _, name, bit in MODS if mods & bit)


def label(value, long=False):
    key, mods, page, usage = decode(value)
    name = (key["pl"] if long else key["short"]) if key else f"0x{page:02X}:{usage:04X}"
    if mods:
        return f"{mods_text(mods)}+{name}"
    return name
