"""
S2 mini 60 – PC program (window + tray icon).

Sends data to the keyboard screen (s2mini_oled.Sender) and has a settings window:
- Quick launch: apps for the carousel on the keyboard screen (icons taken from the apps,
  preview exactly as the OLED shows it, icon style, order),
- Keymap: live keymap editing through ZMK Studio,
- Screen: what to send (CPU, GPU, iGPU, volume, network, now playing, ports, notifications), language, start with Windows.

Closing the window hides it to the tray; "Quit" in the icon menu ends the program.
Building the exe: pc-app/build_exe.bat (PyInstaller).

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

import i18n
import icons
from i18n import tr
import keymap_tab
import s2mini_oled as core

APP_TITLE = "S2 mini 60"
ACCENT = "#5aa9ff"
BG = "#0f1115"
CARD = "#171a21"
CARD_HI = "#1e232c"
MUTED = "#8a93a3"

DATA_LABELS = [
    ("cpu", tr("CPU (load, temperature)")),
    ("gpu", tr("Graphics card")),
    ("igpu", tr("Integrated graphics (Intel)")),
    ("volume", tr("Volume")),
    ("net", tr("Network speed")),
    ("media", tr("Now playing (title, artist)")),
    ("ports", tr("COM ports")),
    ("notifications", tr("Windows notifications (visible to anyone near the keyboard)")),
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


# ---------- Start menu shortcuts ----------

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
    # Store / MSIX apps (e.g. Claude) have no .lnk file, so they come from Get-StartApps
    for name, aumid in store_apps():
        if name.lower() not in seen and not any(s in name.lower() for s in skip):
            seen.add(name.lower())
            out.append((name, icons.APPS_FOLDER + aumid))
    return sorted(out, key=lambda x: x[0].lower())


def store_apps():
    """(name, AppUserModelID) of packaged (MSIX/Store) apps from the Start menu (shell:AppsFolder)."""
    if os.name != "nt":
        return []
    try:
        import comtypes.client
        shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
        folder = shell.NameSpace("shell:AppsFolder")
        items = folder.Items()
        out = []
        for i in range(items.Count):
            it = items.Item(i)
            aumid = str(it.Path or "")
            if "!" in aumid:
                out.append((str(it.Name), aumid))
        return out
    except Exception:
        return []


# ---------- images ----------

def tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 12, 60, 52], radius=8, fill=(23, 26, 33, 255), outline=(90, 169, 255, 255), width=4)
    d.rectangle([14, 22, 34, 30], fill=(90, 169, 255, 255))
    d.rectangle([14, 36, 50, 42], fill=(90, 169, 255, 255))
    return img


def ctk_image(pil, size):
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=size)


# ---------- window ----------

class AppRow(ctk.CTkFrame):
    """One row of the quick launch list."""

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

        self.name = ctk.CTkEntry(self, placeholder_text=tr("Name on screen"), border_width=0, fg_color=CARD_HI)
        self.name.insert(0, app.get("name", ""))
        self.name.grid(row=0, column=2, sticky="ew", padx=8, pady=(10, 2))
        self.name.bind("<FocusOut>", self._rename)
        self.name.bind("<Return>", self._rename)
        ctk.CTkLabel(self, text=app["path"], text_color=MUTED, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=1, column=2, sticky="ew", padx=10, pady=(0, 8))

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=3, rowspan=2, padx=6)
        self.style = ctk.CTkButton(opts, text=tr("Style: {s}  ▾", s=icons.style_name(app.get("style", "auto"))),
                                   height=26, width=170, fg_color=CARD_HI,
                                   command=lambda: StylePicker(window, index, src))
        self.style.pack(pady=(0, 4))
        row2 = ctk.CTkFrame(opts, fg_color="transparent")
        row2.pack(fill="x")
        self.inv = ctk.CTkSwitch(row2, text=tr("Invert"), command=self._invert, width=40)
        if app.get("invert"):
            self.inv.select()
        self.inv.pack(side="left")
        ctk.CTkButton(row2, text=tr("Image…"), width=80, height=24, fg_color=CARD_HI,
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

    def _invert(self):
        self.window.update_app(self.index, invert=bool(self.inv.get()), rebuild=True)

    def _custom_icon(self):
        path = filedialog.askopenfilename(title=tr("Icon image"), filetypes=[
            (tr("Images"), "*.png *.ico *.jpg *.jpeg *.bmp *.gif"), (tr("All files"), "*.*")])
        if path:
            self.window.update_app(self.index, icon=path, rebuild=True)


class StylePicker(ctk.CTkToplevel):
    """All icon styles of one app side by side (as on the OLED); click to choose."""

    def __init__(self, window, index, src):
        super().__init__(window)
        self.window, self.index = window, index
        app = window.cfg["apps"][index]
        self.title(tr("Icon style: {name}", name=app.get("name") or app["path"]))
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.after(50, self.grab_set)
        current = app.get("style", "auto")
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=16, pady=(16, 8))
        for i, key in enumerate(icons.STYLES):
            pv = icons.preview(icons.to_keyboard(src, key, app.get("invert", False)), 3)
            cell = ctk.CTkFrame(grid, fg_color=CARD_HI if key == current else CARD, corner_radius=10,
                                border_width=2, border_color=ACCENT if key == current else CARD)
            cell.grid(row=i // 4, column=i % 4, padx=6, pady=6)
            b = ctk.CTkButton(cell, text="", image=ctk_image(pv, (96, 96)), width=104, height=104,
                              fg_color="#05070a", hover_color="#1b2230", command=lambda k=key: self.pick(k))
            b.pack(padx=6, pady=(6, 2))
            ctk.CTkLabel(cell, text=icons.style_name(key)).pack(pady=(0, 6))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        self.all = ctk.CTkCheckBox(row, text=tr("Use for all apps"))
        self.all.pack(side="left")
        ctk.CTkButton(row, text=tr("Cancel"), width=90, fg_color=CARD_HI, command=self.destroy).pack(side="right")

    def pick(self, key):
        if self.all.get():
            for a in self.window.cfg["apps"]:
                a["style"] = key
            self.window.cfg["default_style"] = key
            self.window._save()
            self.window._rebuild_apps()
        else:
            self.window.update_app(self.index, style=key, rebuild=True)
        self.destroy()


class StartMenuPicker(ctk.CTkToplevel):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.title(tr("Add from Start menu"))
        self.geometry("460x560")
        self.configure(fg_color=BG)
        self.after(50, self.grab_set)
        self.items = start_menu_shortcuts()
        self.search = ctk.CTkEntry(self, placeholder_text=tr("Search…"))
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
        ctk.CTkLabel(side, text=tr("keyboard screen"), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 18))
        self.pages, self.nav = {}, {}
        for key, label in (("launcher", tr("Quick launch")), ("keymap", tr("Keymap")), ("screen", tr("Screen")),
                           ("status", tr("Status"))):
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
        self.pages["keymap"] = keymap_tab.KeymapPage(body, self._header)
        self.pages["screen"] = self._screen_page(body)
        self.pages["status"] = self._status_page(body)
        self.show("launcher")
        self.after(500, self._tick)

    # --- pages ---
    def _header(self, parent, title, subtitle):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(parent, text=subtitle, text_color=MUTED, justify="left").pack(anchor="w", pady=(2, 14))

    def _launcher_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, tr("Quick launch"),
                     tr("On the keyboard: CON/BAK to the LAUNCH view, turn the knob to choose, push to launch.\n"
                        "Up to {n} apps. The preview right of each icon is exactly what the OLED shows.", n=core.APPS_MAX))
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(bar, text=tr("+ From Start menu"), command=lambda: StartMenuPicker(self)).pack(side="left")
        ctk.CTkButton(bar, text=tr("+ File / program…"), fg_color=CARD_HI, command=self._add_file).pack(side="left", padx=8)
        self.count_label = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.count_label.pack(side="right")
        self.app_list = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.app_list.pack(fill="both", expand=True)
        self._rebuild_apps()
        return page

    def _screen_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, tr("Screen"), tr("What the program sends to the keyboard screen. Changes apply immediately."))
        card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card.pack(fill="x")
        self.switches = {}
        for key, label in DATA_LABELS:
            sw = ctk.CTkSwitch(card, text=label, command=self._data_changed)
            if self.cfg["data"].get(key):
                sw.select()
            sw.pack(anchor="w", padx=18, pady=8)
            self.switches[key] = sw
        card3 = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card3.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(card3, text=tr("Default icon style for new apps")).pack(side="left", padx=18, pady=12)
        self.default_style = ctk.CTkOptionMenu(card3, values=[icons.style_name(s) for s in icons.STYLES],
                                               command=self._default_style)
        self.default_style.set(icons.style_name(self.cfg.get("default_style", "auto")))
        self.default_style.pack(side="left", padx=8)
        card4 = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card4.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(card4, text="Język / Language").pack(side="left", padx=18, pady=12)
        labels = [l for _, l in i18n.CHOICES]
        self.lang = ctk.CTkOptionMenu(card4, values=labels, command=self._language)
        self.lang.set(dict(i18n.CHOICES).get(self.cfg.get("language", "auto"), labels[0]))
        self.lang.pack(side="left", padx=8)
        self.lang_note = ctk.CTkLabel(card4, text="", text_color=MUTED)
        self.lang_note.pack(side="left", padx=8)
        card2 = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        card2.pack(fill="x", pady=14)
        self.auto = ctk.CTkSwitch(card2, text=tr("Start with Windows"), command=self._autostart)
        if autostart_get():
            self.auto.select()
        self.auto.pack(anchor="w", padx=18, pady=12)
        ctk.CTkLabel(page, text=tr("CPU/GPU temperatures: LibreHardwareMonitor with “Remote Web Server” enabled (port 8085)."),
                     text_color=MUTED).pack(anchor="w")
        return page

    def _status_page(self, body):
        page = ctk.CTkFrame(body, fg_color="transparent")
        self._header(page, tr("Status"), tr("Last data sent to the keyboard."))
        self.status_box = ctk.CTkTextbox(page, fg_color=CARD, corner_radius=12, height=200,
                                         font=ctk.CTkFont(family="Consolas", size=13))
        self.status_box.pack(fill="both", expand=True)
        return page

    def show(self, key):
        for k, p in self.pages.items():
            p.grid_forget()
            self.nav[k].configure(fg_color=CARD_HI if k == key else "transparent")
        self.pages[key].grid(row=0, column=0, sticky="nsew")

    # --- apps ---
    def _rebuild_apps(self):
        for w in self.app_list.winfo_children():
            w.destroy()
        apps = self.cfg["apps"]
        if not apps:
            ctk.CTkLabel(self.app_list, text=tr("No apps yet. Add one from the Start menu or pick a file."),
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
        self.cfg["apps"].append({"name": name, "path": path, "style": self.cfg.get("default_style", "auto"),
                                 "invert": False})
        self._save()
        self._rebuild_apps()

    def _add_file(self):
        path = filedialog.askopenfilename(title=tr("Choose a program"), filetypes=[
            (tr("Programs and shortcuts"), "*.exe *.lnk *.url *.bat *.cmd"), (tr("All files"), "*.*")])
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

    # --- screen ---
    def _data_changed(self):
        for key, sw in self.switches.items():
            self.cfg["data"][key] = bool(sw.get())
        self._save()

    def _default_style(self, label):
        self.cfg["default_style"] = next(k for k in icons.STYLES if icons.style_name(k) == label)
        self._save()

    def _language(self, label):
        self.cfg["language"] = next(k for k, l in i18n.CHOICES if l == label)
        self._save()
        self.lang_note.configure(text=tr("The language changes after restarting the program."))

    def _autostart(self):
        try:
            autostart_set(bool(self.auto.get()))
        except Exception as e:
            self.status_dot.configure(text=f"●  autostart: {e}")

    # --- refresh ---
    def _tick(self):
        ok = self.sender.status == "connected"
        self.status_dot.configure(text=tr("●  connected") if ok else "●  " + tr(self.sender.status),
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
    if "--media-child" in sys.argv:  # "now playing" helper process (same exe)
        core.media_child()
        return
    hidden = "--hidden" in sys.argv
    i18n.init(core.load_config().get("language", "auto"))
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
            pystray.MenuItem(lambda _: "S2 mini 60: " + tr(sender.status), None, enabled=False),
            pystray.MenuItem(tr("Open"), on_open, default=True),
            pystray.MenuItem(tr("Quit"), on_quit))
        tray = pystray.Icon("s2mini60", tray_image(), APP_TITLE, menu)
        threading.Thread(target=tray.run, daemon=True).start()
    except Exception:
        win.protocol("WM_DELETE_WINDOW", lambda: (sender.stop_event.set(), win.destroy()))
        win.deiconify()

    win.mainloop()
    sender.stop_event.set()


if __name__ == "__main__":
    main()
