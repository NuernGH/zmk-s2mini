"""Podgląd ekranu LAUNCH (128×64, jak na OLED) z prawdziwymi ikonami w wybranym stylu.

python tools/launcher_preview.py wynik.png [styl] [filtr ...]
styl: auto, levels, regions, gray, lines, silhouette, detail, outline (domyślnie auto)
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import icons  # noqa: E402


def shortcuts():
    roots = [os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    out = {}
    for root in roots:
        for p in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            out.setdefault(os.path.splitext(os.path.basename(p))[0], p)
    return sorted(out.items(), key=lambda x: x[0].lower())


def screen(apps, sel, style):
    img = Image.new("1", (128, 64), 0)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans-Bold.ttf", 9)
    except Exception:
        try:
            f = ImageFont.truetype("arialbd.ttf", 9)
        except Exception:
            f = ImageFont.load_default()
    d.rectangle([0, 0, 127, 11], fill=1)
    d.text((2, 0), "LAUNCH", fill=0, font=f)
    t = f"{sel + 1}/{len(apps)}"
    d.text((126 - d.textlength(t, font=f), 0), t, fill=0, font=f)
    d.rectangle([45, 13, 82, 50], outline=1)
    for slot, x in enumerate((6, 48, 90)):
        name, path = apps[(sel + slot - 1) % len(apps)]
        ic = icons.to_keyboard(icons.extract_icon(path), style)
        img.paste(ic, (x, 16))
    name = apps[sel][0]
    d.text(((128 - d.textlength(name, font=f)) / 2, 52), name, fill=1, font=f)
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "launch.png"
    style = sys.argv[2] if len(sys.argv) > 2 else "auto"
    want = [w.lower() for w in sys.argv[3:]] or ["chrome", "discord", "steam", "code", "spotify"]
    items = [i for i in shortcuts() if any(w in i[0].lower() for w in want)][:8]
    if len(items) < 3:
        sys.exit("za mało pasujących skrótów")
    frames = [icons.preview(screen(items, s, style), 4, on=(235, 245, 255), off=(5, 6, 8)) for s in range(min(3, len(items)))]
    sheet = Image.new("RGB", (frames[0].width, frames[0].height * len(frames) + 8 * (len(frames) - 1)), (40, 40, 40))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (0, i * (fr.height + 8)))
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
