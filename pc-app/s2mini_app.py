"""
S2 mini 60 – program na PC (okno + ikona w zasobniku).

Wysyła dane na ekran klawiatury (s2mini_oled.Sender) i ma okno ustawień:
- Szybki start: aplikacje do karuzeli na ekranie klawiatury (ikony pobierane z aplikacji,
  podgląd tak, jak pokaże OLED, styl ikony, kolejność),
- Ekran: co wysyłać (CPU, GPU, iGPU, głośność, sieć, co gra, porty, powiadomienia),
  start razem z Windows.

Zamknięcie okna chowa je do zasobnika; „Zakończ” w menu ikony kończy program.
Budowa exe: pc-app/build_exe.bat (PyInstaller).

SPDX-License-Identifier: MIT
"""

import copy
import glob
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw

import icons
import s2mini_oled as core

APP_TITLE = "S2 mini 60"
ACCENT = "#5aa9ff"
BG = "#0f1115"
CARD = "#171a21"
CARD_HI = "#1e232c"
MUTED = "#8a93a3"

DATA_LABELS = [
    ("cpu", "Procesor (obciążenie, temperatura)"),
    ("gpu", "Karta graficzna"),
    ("igpu", "Grafika zintegrowana (Intel)"),
    ("volume", "Głośność"),
    ("net", "Prędkość sieci"),
    ("media", "Co gra (tytuł, wykonawca)"),
    ("ports", "Porty COM"),
    ("notifications", "Powiadomienia Windows (widoczne dla każdego przy klawiaturze)"),
]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "S2mini60"


# ---------- autostart (HKCU\...\Run) ----------

def _exe_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}" --hidden'


def autostart_get():
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def autostart_set(on):
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _exe_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


# ---------- skróty z menu Start ----------

def start_menu_shortcuts():
    roots = [os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    seen, out = set(), []
    skip = ("uninstall", "odinstaluj", "readme", "help", "pomoc", "documentation", "license")
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(path))[0]
            if name.lower() in seen or any(s in name.lower() for s in skip):
                continue
            seen.add(name.lower())
            out.append((name, path))
    return sorted(out, key=lambda x: x[0].lower())


# ---------- obrazki ----------

def tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 12, 60, 52], radius=8, fill=(23, 26, 33, 255), outline=(90, 169, 255, 255), width=4)
    d.rectangle([14, 22, 34, 30], fill=(90, 169, 255, 255))
    d.rectangle([14, 36, 50, 42], fill=(90, 169, 255, 255))
    return img


def ctk_image(pil, size):
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=size)


# ---------- okno ----------

class AppRow(ctk.CTkFrame):
    """Jeden wiersz listy szybkiego startu."""

    def __init__(self, master, window, index, app):
        super().__init__(master, fg_color=CARD, corner_radius=12)
        self.window, self.index, self.app = window, index, app
        self.grid_columnconfigure(2, weight=1)

        src = icons.extract_icon(app.get("icon") or app["path"])
        color = src.resize((40, 40), Image.LANCZOS) if src else Image.new("RGBA", (40, 40))
        oled = icons.preview(icons.to_keyboard(src, app.get("style", "auto"), app.get("invert", False)), 2)

        ctk.CTkLabel(self, text=f"{index + 1}", width=22, text_color=MUTED).grid(row=0, column=0, rowspan=2, padx=(10, 2))
        icon_box = ctk.CTkFrame(self, fg_color="transparent")
        icon_box.grid(row=0, column=1, rowspan=2, padx=6, pady=8)
        ctk.CTkLabel(icon_box, text="", image=ctk_image(color, (40, 40))).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(icon_box, text="", image=ctk_image(oled, (64, 64)), fg_color="#05070a",
                     corner_radius=6).pack(side="left")

        self.name = ctk.CTkEntry(self, placeholder_text="Nazwa na ekranie", border_width=0, fg_color=CARD_HI)
        self.name.insert(0, app.get("name", ""))
        self.name.grid(row=0, column=2, sticky="ew", padx=8, pady=(10, 2))
        self.name.bind("<FocusOut>", self._rename)
        self.name.bind("<Return>", self._rename)
        ctk.CTkLabel(self, text=app["path"], text_color=MUTED, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=1, column=2, sticky="ew", padx=10, pady=(0, 8))

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=3, rowspan=2, padx=6)
        self.style = ctk.CTkSegmentedButton(opts, values=[icons.STYLE_NAMES[s] for s in icons.STYLES],
                                            command=self._style, height=26)
        self.style.set(icons.STYLE_NAMES[app.get("style", "auto")])
        self.style.pack(pady=(0, 4))
        row2 = ctk.CTkFrame(opts, fg_color="transparent")
        row2.pack(fill="x")
        self.inv = ctk.CTkSwitch(row2, text="Odwróć", command=self._invert, width=40)
        if app.get("invert"):
            self.inv.select()
        self.inv.pack(side="left")
        ctk.CTkButton(row2, text="Obrazek…", width=80, height=24, fg_color=CARD_HI,
                      command=self._custom_icon).pack(side="left", padx=6)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=0, column=4, rowspan=2, padx=(4, 10))
        for text, cmd in (("▲", lambda: window.move(index, -1)), ("▼", lambda: window.move(index, 1)),
                          ("✕", lambda: window.remove(index))):
            ctk.CTkButton(btns, text=text, width=30, height=24, fg_color=CARD_HI,
                          hover_color="#7a2c2c" if text == "✕" else None, command=cmd).pack(pady=1)

    def _rename(self, _=None):
        name = self.name.get().strip()
        if name != self.app.get("name", ""):
            self.window.update_app(self.index, name=name)

    def _style(self, label):
        key = next(k for k, v in icons.STYLE_NAMES.items() if v == label)
        self.window.update_app(self.index, style=key, rebuild=True)

    def _invert(self):
        self.window.update_app(self.index, invert=bool(self.inv.get()), rebuild=True)

    def _custom_icon(self):
        path = filedialog.askopenfilename(title="Obrazek ikony", filetypes=[
            ("Obrazki", "*.png *.ico *.jpg *.jpeg *.bmp *.gif"), ("Wszystkie", "*.*")])
        if path:
            self.window.update_app(self.index, icon=path, rebuild=True)


class StartMenuPicker(ctk.CTkToplevel):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.title("Dodaj z menu Start")
        self.geometry("460x560")
        self.configure(fg_color=BG)
        self.after(50, self.grab_set)
        self.items = start_menu_shortcuts()
        self.search = ctk.CTkEntry(self, placeholder_text="Szukaj…")
        self.search.pack(fill="x", padx=14, pady=(14, 8))
        self.search.bind("<KeyRelease>", lambda _: self.fill())
        self.listbox = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=12)
        self.listbox.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.fill()
        self.search.focus()

    def fill(self):
        for w in self.listbox.winfo_children():
            w.destroy()
        q = self.search.get().lower().strip()
        for name, path in [i for i in self.items if q in i[0].lower()][:120]:
            ctk.CTkButton(self.listbox, text=name, anchor="w", fg_color="transparent", hover_color=CARD_HI,
                          command=lambda n=name, p=path: self.pick(n, p)).pack(fill="x", pady=1)

    def pick(self, name, path):
        self.window.add_app(path, name)
        self.destroy()


class Window(ctk.CTk):
    def __init__(self, sender):
        super().__init__()
        self.sender = sender
        self.cfg = copy.deepcopy(sender.config)
        self.title(APP_TITLE)
        self.geometry("980x640")
        self.minsize(820, 520)
        self.configure(fg_color=BG)
        try:
            self.iconphoto(True, tk.PhotoImage(data=_png_bytes(tray_image())))
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, width=210)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="S2 mini 60", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=20, pady=(22, 0))
        ctk.CTkLabel(side, text="ekran klawiatury", text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 18))
        self.pages, self.nav = {}, {}
        for key, label in (("launcher", "Szybki start"), ("screen", "Ekran"), ("status", "Stan")):
            b = ctk.CTkButton(side, text=label, anchor="w", height=36, corner_radius=8,
                              fg_color="transparent", hover_color=CARD_HI, command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav[key] = b
        self.status_dot = ctk.CTkLabel(side, text="●  …", text_color=MUTED, anchor="w")
        self.status_dot.pack(side="bottom", anchor="w", padx=20, pady=18)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.pages["launcher"] = self._launcher_page(body)
        self.pages["screen"] = self._screen_page(body)
        self.pages["status"] = self._status_page(body)
        self.show("launcher")
        self.after(500, self._tick)

    # --- strony ---
    def _header(self, parent, title, subtitle):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(parent, text=subtitle, text_color=MUTED, justify="left").pack(anchor="w", pady=(2, 14))

    def _launcher_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, "Szybki start",
                     "Na klawiaturze: CON/BAK do widoku LAUNCH, gałka wybiera, wciśnięcie uruchamia.\n"
                     f"Do {core.APPS_MAX} aplikacji. Podgląd po prawej ikonie to dokładnie to, co pokaże OLED.")
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(bar, text="+ Z menu Start", command=lambda: StartMenuPicker(self)).pack(side="left")
        ctk.CTkButton(bar, text="+ Plik / program…", fg_color=CARD_HI, command=self._add_file).pack(side="left", padx=8)
        self.count_label = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.count_label.pack(side="right")
        self.app_list = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.app_list.pack(fill="both", expand=True)
        self._rebuild_apps()
        return page

    def _screen_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, "Ekran", "Co program wysyła na ekran klawiatury. Zmiany działają od razu.")
        card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card.pack(fill="x")
        self.switches = {}
        for key, label in DATA_LABELS:
            sw = ctk.CTkSwitch(card, text=label, command=self._data_changed)
            if self.cfg["data"].get(key):
                sw.select()
            sw.pack(anchor="w", padx=18, pady=8)
            self.switches[key] = sw
        card2 = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card2.pack(fill="x", pady=14)
        self.auto = ctk.CTkSwitch(card2, text="Uruchamiaj razem z Windows", command=self._autostart)
        if autostart_get():
            self.auto.select()
        self.auto.pack(anchor="w", padx=18, pady=12)
        ctk.CTkLabel(page, text="Temperatury CPU/GPU: LibreHardwareMonitor z włączonym „Remote Web Server” (port 8085).",
                     text_color=MUTED).pack(anchor="w")
        return page

    def _status_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, "Stan", "Ostatnie dane wysłane do klawiatury.")
        self.status_box = ctk.CTkTextbox(page, fg_color=CARD, corner_radius=12, height=200,
                                         font=ctk.CTkFont(family="Consolas", size=13))
        self.status_box.pack(fill="both", expand=True)
        return page

    def show(self, key):
        for k, p in self.pages.items():
            p.grid_forget()
            self.nav[k].configure(fg_color=CARD_HI if k == key else "transparent")
        self.pages[key].grid(row=0, column=0, sticky="nsew")

    # --- aplikacje ---
    def _rebuild_apps(self):
        for w in self.app_list.winfo_children():
            w.destroy()
        apps = self.cfg["apps"]
        if not apps:
            ctk.CTkLabel(self.app_list, text="Brak aplikacji. Dodaj z menu Start albo wskaż plik.",
                         text_color=MUTED).pack(pady=40)
        for i, app in enumerate(apps):
            AppRow(self.app_list, self, i, app).pack(fill="x", pady=4)
        self.count_label.configure(text=f"{len(apps)} / {core.APPS_MAX}")

    def _save(self):
        core.save_config(self.cfg)
        self.sender.set_config(self.cfg)

    def add_app(self, path, name=None):
        if len(self.cfg["apps"]) >= core.APPS_MAX:
            return
        name = name or os.path.splitext(os.path.basename(path))[0]
        self.cfg["apps"].append({"name": name, "path": path, "style": "auto", "invert": False})
        self._save()
        self._rebuild_apps()

    def _add_file(self):
        path = filedialog.askopenfilename(title="Wybierz program", filetypes=[
            ("Programy i skróty", "*.exe *.lnk *.url *.bat *.cmd"), ("Wszystkie", "*.*")])
        if path:
            self.add_app(os.path.normpath(path))

    def update_app(self, index, rebuild=False, **changes):
        self.cfg["apps"][index].update(changes)
        self._save()
        if rebuild:
            self._rebuild_apps()

    def move(self, index, delta):
        apps = self.cfg["apps"]
        j = index + delta
        if 0 <= j < len(apps):
            apps[index], apps[j] = apps[j], apps[index]
            self._save()
            self._rebuild_apps()

    def remove(self, index):
        del self.cfg["apps"][index]
        self._save()
        self._rebuild_apps()

    # --- ekran ---
    def _data_changed(self):
        for key, sw in self.switches.items():
            self.cfg["data"][key] = bool(sw.get())
        self._save()

    def _autostart(self):
        try:
            autostart_set(bool(self.auto.get()))
        except Exception as e:
            self.status_dot.configure(text=f"●  autostart: {e}")

    # --- odświeżanie ---
    def _tick(self):
        ok = self.sender.status == "connected"
        self.status_dot.configure(text="●  połączono" if ok else f"●  {self.sender.status}",
                                  text_color="#5fd38d" if ok else "#e0a040")
        line = self.sender.last_line
        if line:
            self.status_box.delete("1.0", "end")
            self.status_box.insert("end", line.replace("  ", "\n"))
        self.after(1000, self._tick)

    def open(self):
        self.deiconify()
        self.lift()
        self.focus_force()


def _png_bytes(img):
    import base64
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue())


def main():
    hidden = "--hidden" in sys.argv
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    sender = core.Sender()
    sender.start()
    win = Window(sender)
    if hidden:
        win.withdraw()

    try:
        import pystray

        def on_open(icon, _):
            win.after(0, win.open)

        def on_quit(icon, _):
            sender.stop_event.set()
            icon.stop()
            win.after(0, win.destroy)

        menu = pystray.Menu(
            pystray.MenuItem(lambda _: f"S2 mini 60: {sender.status}", None, enabled=False),
            pystray.MenuItem("Otwórz", on_open, default=True),
            pystray.MenuItem("Zakończ", on_quit))
        tray = pystray.Icon("s2mini60", tray_image(), APP_TITLE, menu)
        threading.Thread(target=tray.run, daemon=True).start()
    except Exception:
        win.protocol("WM_DELETE_WINDOW", lambda: (sender.stop_event.set(), win.destroy()))
        win.deiconify()

    win.mainloop()
    sender.stop_event.set()


if __name__ == "__main__":
    main()
