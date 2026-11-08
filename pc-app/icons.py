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
STYLES = ("auto", "silhouette", "detail", "outline")
STYLE_NAMES = {
    "auto": "Auto",
    "silhouette": "Sylwetka",
    "detail": "Szczegóły",
    "outline": "Kontur",
}


def _draw_icon_windows(path, size):
    """Ikona przez SHGetFileInfo + DrawIconEx, rysowana na czarnym i białym tle (→ alfa)."""
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
    else:  # auto: sylwetka, w środku ciemne detale wycięte, gdy jest ich rozsądnie dużo
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
