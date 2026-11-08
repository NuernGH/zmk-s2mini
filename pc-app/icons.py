"""
Ikony aplikacji do szybkiego startu na ekranie klawiatury.

- extract_icon(path): kolorowa ikona RGBA (Windows, ikona pliku .exe/.lnk/dowolnego przez powłokę),
- to_keyboard(img, style, invert): ikona 32×32 w 1 bicie, jak ją pokaże OLED,
- pack_bits(img) → 128 B do wysłania (wiersz = 4 bajty, bit 7 = lewy piksel, 1 = świeci).

Style: "silhouette" (kształt ikony, wyraźny), "detail" (jasność z ditheringiem),
"outline" (sam kontur), "auto" (sylwetka z wyciętymi ciemnymi detalami).

SPDX-License-Identifier: MIT
"""

import os

from PIL import Image, ImageFilter, ImageOps

SIZE = 32
STYLES = ("auto", "regions", "levels", "gray", "lines", "silhouette", "detail", "outline")
STYLE_NAMES = {
    "auto": "Auto",
    "regions": "Plamy kolorów",
    "levels": "Jasne/ciemne",
    "gray": "Odcienie",
    "lines": "Rysunek",
    "silhouette": "Sylwetka",
    "detail": "Szczegóły",
    "outline": "Kontur",
}


def _resolve_shortcut(path):
    """Skrót .lnk → (plik z ikoną, indeks). Bez tego Windows dokleja strzałkę skrótu, a skróty
    typu Discord/VS Code (Update.exe z parametrami) dają pustą ikonę pliku."""
    try:
        import comtypes.client
        shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
        sc = shell.CreateShortcut(path)
        icon_loc = str(sc.IconLocation or "")
        target = os.path.expandvars(str(sc.TargetPath or ""))
    except Exception:
        return None, 0
    file, _, idx = icon_loc.rpartition(",")
    file = os.path.expandvars(file.strip().strip('"'))
    try:
        idx = int(idx)
    except ValueError:
        file, idx = icon_loc, 0
    if file and os.path.exists(file):
        return file, idx
    if target and os.path.exists(target):
        return target, 0
    return None, 0


def _hicon_from_file(file, index, size):
    """HICON w dokładnym rozmiarze z pliku .exe/.dll/.ico (PrivateExtractIconsW)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.UINT),
                                            wintypes.UINT, wintypes.UINT]
    hicon = wintypes.HANDLE()
    icon_id = wintypes.UINT()
    n = user32.PrivateExtractIconsW(file, index, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0)
    return hicon.value if n and n != 0xFFFFFFFF and hicon.value else None


def _draw_icon_windows(path, size):
    """Ikona przez PrivateExtractIcons/SHGetFileInfo + DrawIconEx, rysowana na czarnym i białym
    tle (→ alfa). Skróty .lnk rozwijane do pliku z ikoną (bez strzałki skrótu)."""
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [("hIcon", wintypes.HANDLE), ("iIcon", ctypes.c_int),
                    ("dwAttributes", wintypes.DWORD), ("szDisplayName", wintypes.WCHAR * 260),
                    ("szTypeName", wintypes.WCHAR * 80)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                                       wintypes.UINT, wintypes.UINT]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t
    user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HANDLE,
                                  wintypes.UINT]
    user32.DestroyIcon.argtypes = [wintypes.HANDLE]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    SHGFI_ICON, SHGFI_LARGEICON, DI_NORMAL = 0x100, 0x0, 0x3
    hicon = None
    if path.lower().endswith(".lnk"):
        file, index = _resolve_shortcut(path)
        if file:
            if file.lower().endswith(".ico"):
                return None  # .ico czyta extract_icon przez PIL (patrz niżej)
            hicon = _hicon_from_file(file, index, size)
            if hicon is None:
                path = file  # SHGetFileInfo na pliku docelowym, już bez strzałki
    elif path.lower().endswith((".exe", ".dll")):
        hicon = _hicon_from_file(path, 0, size)
    if hicon is None:
        info = SHFILEINFOW()
        if not shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info),
                                      SHGFI_ICON | SHGFI_LARGEICON) or not info.hIcon:
            return None
        hicon = info.hIcon

    def render(fill):
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth, bmi.biHeight = size, -size  # od góry
        bmi.biPlanes, bmi.biBitCount = 1, 32
        screen = user32.GetDC(None)
        dc = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(dc, bmp)
        ctypes.memset(bits, fill, size * size * 4)
        user32.DrawIconEx(dc, 0, 0, hicon, size, size, 0, None, DI_NORMAL)
        raw = ctypes.string_at(bits, size * size * 4)
        gdi32.SelectObject(dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, screen)
        return Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1).convert("RGB")

    try:
        on_black = render(0x00)
        on_white = render(0xFF)
    finally:
        user32.DestroyIcon(hicon)

    # alfa = 1 - (białe - czarne); kolor = czarne / alfa
    out = Image.new("RGBA", (size, size))
    pb, pw = on_black.load(), on_white.load()
    po = out.load()
    for y in range(size):
        for x in range(size):
            b, w = pb[x, y], pw[x, y]
            a = 255 - max(0, min(255, round(sum(wc - bc for wc, bc in zip(w, b)) / 3)))
            if a == 0:
                po[x, y] = (0, 0, 0, 0)
            else:
                po[x, y] = tuple(min(255, round(c * 255 / a)) for c in b) + (a,)
    return out


def extract_icon(path, size=64):
    """Kolorowa ikona aplikacji (RGBA) albo None. Obrazek (.png/.ico/.jpg) bierze wprost."""
    if not path:
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".ico", ".jpg", ".jpeg", ".bmp", ".gif"):
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size))
            canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
            return canvas
        except Exception:
            return None
    if os.name != "nt":
        return None
    if ext == ".lnk":
        try:
            file, _ = _resolve_shortcut(path)
            if file and file.lower().endswith(".ico"):
                return extract_icon(file, size)
        except Exception:
            pass
    try:
        return _draw_icon_windows(path, size)
    except Exception:
        return None


def _fit(img):
    """Przycina przezroczyste brzegi i skaluje do 30×30 na środku pola 32×32 (większa ikona)."""
    img = img.convert("RGBA")
    box = img.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((SIZE - 2, SIZE - 2), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
    return canvas


def to_keyboard(img, style="auto", invert=False):
    """Ikona tak, jak ją pokaże OLED: obraz 1-bitowy 32×32 (biały = świeci)."""
    if img is None:
        return placeholder()
    img = _fit(img)
    alpha = img.getchannel("A")
    lum = ImageOps.autocontrast(img.convert("L"), cutoff=2)
    shape = alpha.point(lambda a: 255 if a > 110 else 0)

    if style == "silhouette":
        out = shape
    elif style == "outline":
        out = shape.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 0 else 0)
    elif style == "detail":
        mixed = Image.composite(lum, Image.new("L", (SIZE, SIZE), 0), alpha)
        out = mixed.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
    elif style in ("regions", "lines"):
        out = _regions(img, shape, lines_only=(style == "lines"))
    elif style == "levels":
        out = _levels(lum, shape)
    elif style == "gray":
        out = _gray(lum, alpha, shape)
    elif style == "auto":
        # jasne/ciemne, chyba że ikona jest prawie jednolita (wtedy plamy kolorów pokażą podział)
        lev = _levels(lum, shape)
        filled = sum(1 for v in shape.getdata() if v) or 1
        lit = sum(1 for v in lev.getdata() if v)
        out = lev if 0.2 < lit / filled < 0.9 else _regions(img, shape)
    else:  # dawne auto
        dark = lum.point(lambda v: 255 if v < 70 else 0)
        holes = Image.composite(dark, Image.new("L", (SIZE, SIZE), 0), shape)
        inner = shape.filter(ImageFilter.MinFilter(3))
        holes = Image.composite(holes, Image.new("L", (SIZE, SIZE), 0), inner)
        filled = sum(1 for v in shape.getdata() if v)
        cut = sum(1 for v in holes.getdata() if v)
        if filled and 0.06 < cut / filled < 0.6:
            out = Image.composite(Image.new("L", (SIZE, SIZE), 0), shape, holes)
        else:
            out = shape
    out = out.convert("L").point(lambda v: 255 if v > 127 else 0)
    if invert:
        out = ImageOps.invert(out)
    return out.convert("1")


def _ring(shape):
    """Obrys kształtu (1 px po wewnętrznej stronie)."""
    inner = shape.filter(ImageFilter.MinFilter(3))
    return ImageChops_sub(shape, inner)


def ImageChops_sub(a, b):
    from PIL import ImageChops
    return ImageChops.subtract(a, b)


def _otsu(values):
    hist = [0] * 256
    for v in values:
        hist[v] += 1
    total = sum(hist)
    if total == 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w0, s0 = -1, 128, 0, 0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0 or w0 == total:
            continue
        s0 += t * hist[t]
        m0, m1 = s0 / w0, (sum_all - s0) / (total - w0)
        var = w0 * (total - w0) * (m0 - m1) ** 2
        if var > best:
            best, best_t = var, t
    return best_t


def _levels(lum, shape):
    """Jasne części świecą, ciemne nie (próg Otsu liczony tylko w ikonie), plus obrys kształtu."""
    from PIL import ImageChops
    vals = [l for l, a in zip(lum.getdata(), shape.getdata()) if a]
    t = _otsu(vals)
    bright = lum.point(lambda v: 255 if v > t else 0)
    out = ImageChops.multiply(bright, shape)
    return ImageChops.lighter(out, _ring(shape))


def _gray(lum, alpha, shape):
    """Odcienie szarości wzorem (dithering Bayera 4×4), jasność rozciągnięta, plus obrys."""
    from PIL import ImageChops
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    vals = [l for l, a in zip(lum.getdata(), shape.getdata()) if a]
    lo, hi = (min(vals), max(vals)) if vals else (0, 255)
    span = max(hi - lo, 1)
    src, sh = lum.load(), shape.load()
    out = Image.new("L", lum.size, 0)
    po = out.load()
    for y in range(SIZE):
        for x in range(SIZE):
            if not sh[x, y]:
                continue
            v = (src[x, y] - lo) / span  # 0..1
            v = 0.15 + 0.85 * v          # ciemne też lekko świecą, żeby kształt był widoczny
            po[x, y] = 255 if v * 16 > bayer[y % 4][x % 4] + 0.5 else 0
    return ImageChops.lighter(out, _ring(shape))


def _regions(img, shape, lines_only=False):
    """Plamy kolorów: plamy świecą, a tam, gdzie kolor wyraźnie się zmienia, jest ciemna kreska.
    lines_only: odwrotnie, świecą tylko te kreski i obrys (rysunek kreską)."""
    from PIL import ImageChops
    rgb = Image.new("RGB", img.size, (0, 0, 0))
    rgb.paste(img.convert("RGB"), mask=shape)
    rgb = rgb.filter(ImageFilter.MedianFilter(3))
    px, sh = rgb.load(), shape.load()
    out = Image.new("L", img.size, 0)
    po = out.load()

    def dist(a, b):
        return abs(a[0] - b[0]) * 0.3 + abs(a[1] - b[1]) * 0.59 + abs(a[2] - b[2]) * 0.11 + \
            (abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) * 0.25

    for y in range(SIZE):
        for x in range(SIZE):
            if not sh[x, y]:
                continue
            c = px[x, y]
            edge = False
            # kreska tylko po jednej stronie granicy (prawy/dolny sąsiad), żeby była cienka
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx < SIZE and ny < SIZE and sh[nx, ny] and dist(c, px[nx, ny]) > 70:
                    edge = True
            po[x, y] = 255 if edge == lines_only else 0
    if lines_only:
        out = ImageChops.lighter(out, _ring(shape))
    return out


def placeholder():
    """Ikona zastępcza: zaokrąglony kwadrat z kropką."""
    img = Image.new("1", (SIZE, SIZE), 0)
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            edge = x in (3, 28) or y in (3, 28)
            inside = 3 <= x <= 28 and 3 <= y <= 28
            corner = (x in (3, 28)) and (y in (3, 28))
            dot = (x - 15.5) ** 2 + (y - 15.5) ** 2 < 20
            px[x, y] = 1 if (inside and edge and not corner) or dot else 0
    return img


def pack_bits(img1):
    """1-bitowy obraz 32×32 → 128 B (bit 7 = lewy piksel)."""
    img1 = img1.convert("1").resize((SIZE, SIZE))
    px = img1.load()
    out = bytearray(SIZE * SIZE // 8)
    for y in range(SIZE):
        for x in range(SIZE):
            if px[x, y]:
                i = y * SIZE + x
                out[i // 8] |= 0x80 >> (i % 8)
    return bytes(out)


def preview(img1, scale=3, on=(235, 245, 255), off=(8, 10, 14)):
    """Podgląd OLED do okna: piksele ×scale, kolory jak na ekranie."""
    img1 = img1.convert("1")
    rgb = Image.new("RGB", img1.size, off)
    rgb.paste(Image.new("RGB", img1.size, on), mask=img1.convert("L"))
    return rgb.resize((img1.width * scale, img1.height * scale), Image.NEAREST)
