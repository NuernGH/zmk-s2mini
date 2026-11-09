"""Keymap tab: live keymap editing through ZMK Studio (the keyboard's COM port).

The physical layout, layers and available actions are read from the keyboard. The key to assign
can be picked from a list or by pressing it (with modifiers) on a normal keyboard.
"""

import math
import queue
import threading
import tkinter as tk

import customtkinter as ctk

import zmk_keys as K
from i18n import tr
import zmk_studio as Z

ACCENT = "#5aa9ff"
CARD = "#171a21"
CARD_HI = "#1e232c"
MUTED = "#8a93a3"
WARN = "#f0b35a"
KEY_BG = "#232833"
KEY_SEL = "#2f5f99"
KEY_TRANS = "#1a1d24"

SHORT_BEHAVIOR = {
    "Key Press": "", "Momentary Layer": "MO", "Toggle Layer": "TG", "To Layer": "TO", "Sticky Layer": "SL",
    "Layer-Tap": "LT", "Mod-Tap": "MT", "Transparent": "▽", "None": "", "Sticky Key": "SK",
    "Caps Word": "CapsW", "Key Repeat": "Rep", "Key Toggle": "KT", "Bluetooth": "BT", "Output Selection": "Out",
    "Reset": "Reset", "Bootloader": "Boot", "Studio Unlock": "Unlock", "Grave/Escape": "Esc`",
}


class Worker:
    """All keyboard communication in one thread; results return to the window via after()."""

    def __init__(self, widget):
        self.widget = widget
        self.q = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, fn, done=None, fail=None):
        self.q.put((fn, done, fail))

    def _loop(self):
        while True:
            fn, done, fail = self.q.get()
            try:
                r = fn()
            except Exception as e:  # noqa: BLE001 — the error is shown in the window
                if fail:
                    self.widget.after(0, fail, e)
                continue
            if done:
                self.widget.after(0, done, r)


class KeymapPage(ctk.CTkFrame):
    def __init__(self, master, header):
        super().__init__(master, fg_color="transparent")
        header(self, tr("Keymap"), tr("Changes go to the keyboard right away (like ZMK Studio). "
                                      "“Save to keyboard” keeps them, “Discard” returns to the saved keymap."))
        self.studio = None
        self.worker = Worker(self)
        self.keymap = None
        self.layout = None
        self.behaviors = {}
        self.layer_idx = 0
        self.sel = None
        self.unsaved = False
        self.busy = False

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self.connect_btn = ctk.CTkButton(bar, text=tr("Connect to keyboard"), command=self.connect)
        self.connect_btn.pack(side="left")
        self.state = ctk.CTkLabel(bar, text=tr("Not connected"), text_color=MUTED)
        self.state.pack(side="left", padx=12)
        self.discard_btn = ctk.CTkButton(bar, text=tr("Discard changes"), fg_color=CARD_HI, width=120,
                                         command=self.discard, state="disabled")
        self.discard_btn.pack(side="right")
        self.save_btn = ctk.CTkButton(bar, text=tr("Save to keyboard"), width=170, command=self.save,
                                      state="disabled")
        self.save_btn.pack(side="right", padx=8)

        lbar = ctk.CTkFrame(self, fg_color="transparent")
        lbar.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(lbar, text=tr("Layer"), text_color=MUTED).pack(side="left", padx=(0, 8))
        self.layers = ctk.CTkSegmentedButton(lbar, values=["—"], command=self._pick_layer)
        self.layers.pack(side="left")
        self.rename_btn = ctk.CTkButton(lbar, text=tr("Rename"), width=110, fg_color=CARD_HI,
                                        command=self.rename_layer, state="disabled")
        self.rename_btn.pack(side="left", padx=8)

        self.canvas = tk.Canvas(self, bg=CARD, highlightthickness=0, height=260)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self._click)

        self.editor = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        self.editor.pack(fill="both", expand=True, pady=(10, 0))
        self.hint = ctk.CTkLabel(self.editor, text=tr("Connect to the keyboard, then click a key in the picture."),
                                 text_color=MUTED)
        self.hint.pack(padx=18, pady=18, anchor="w")

    # ---------- connection ----------
    def connect(self):
        if self.studio:
            self._disconnect()
            return
        self._status(tr("Connecting…"))
        self.connect_btn.configure(state="disabled")

        def job():
            port = Z.find_port()
            if not port:
                raise Z.StudioError(tr("keyboard COM port not found (1D50:615E)"))
            s = Z.Studio(port)
            s.on_notification = lambda n: self.after(0, self._note, n)
            info = s.device_info()
            return s, port, info, s.locked()

        self.worker.submit(job, self._connected, self._failed)

    def _connected(self, r):
        self.studio, port, info, locked = r
        self.connect_btn.configure(state="normal", text=tr("Disconnect"))
        self.device = f"{info['name']} ({port})"
        if locked:
            self._status(tr("{dev}: locked. Unlock on the keyboard: Fn + \\", dev=self.device), WARN)
            self.after(1000, self._poll_unlock)
        else:
            self._load()

    def _poll_unlock(self):
        if not self.studio or self.keymap:
            return
        self.worker.submit(lambda: self.studio.locked(),
                           lambda locked: self.after(1000, self._poll_unlock) if locked else self._load(),
                           self._failed)

    def _note(self, n):
        if n.get("lock_state") == 1 and not self.keymap:
            self._load()
        if "unsaved" in n:
            self._set_unsaved(n["unsaved"])

    def _load(self):
        self._status(tr("{dev}: loading keymap…", dev=self.device))

        def job():
            s = self.studio
            return s.keymap(), s.physical_layouts(), s.behaviors(), s.unsaved()

        self.worker.submit(job, self._loaded, self._failed)

    def _loaded(self, r):
        self.keymap, layouts, behaviors, unsaved = r
        self.layout = layouts["layouts"][layouts["active"]]["keys"] if layouts["layouts"] else []
        self.behaviors = {b["id"]: b for b in behaviors}
        self._status(tr("{dev}: connected", dev=self.device), ACCENT)
        self.rename_btn.configure(state="normal")
        self._set_unsaved(unsaved)
        self._refresh_layers()
        self.draw()
        self._show_editor()

    def _failed(self, e):
        self.connect_btn.configure(state="normal")
        self._status(tr("Error: {e}", e=tr(str(e))), WARN)
        if isinstance(e, Z.StudioError) and "closed" in str(e):
            self._disconnect(keep_status=True)

    def _disconnect(self, keep_status=False):
        if self.studio:
            self.studio.close()
        self.studio = self.keymap = None
        self.sel = None
        self.connect_btn.configure(text=tr("Connect to keyboard"), state="normal")
        self.save_btn.configure(state="disabled")
        self.discard_btn.configure(state="disabled")
        self.rename_btn.configure(state="disabled")
        if not keep_status:
            self._status(tr("Not connected"))
        self.draw()
        self._show_editor()

    def _status(self, text, color=MUTED):
        self.state.configure(text=text, text_color=color)

    def _set_unsaved(self, v):
        self.unsaved = v
        st = "normal" if (v and self.studio) else "disabled"
        self.save_btn.configure(state=st)
        self.discard_btn.configure(state=st)
        if self.studio and self.keymap:
            self._status(tr("{dev}: unsaved changes" if v else "{dev}: zapisane", dev=self.device), WARN if v else ACCENT)

    # ---------- layers ----------
    def _layer_names(self):
        return [l["name"] or tr("Layer {i}", i=i) for i, l in enumerate(self.keymap["layers"])]

    def _refresh_layers(self):
        names = self._layer_names()
        self.layers.configure(values=names)
        self.layer_idx = min(self.layer_idx, len(names) - 1)
        self.layers.set(names[self.layer_idx])

    def _pick_layer(self, name):
        self.layer_idx = self._layer_names().index(name)
        self.draw()
        self._show_editor()

    def rename_layer(self):
        layer = self.keymap["layers"][self.layer_idx]
        d = ctk.CTkInputDialog(text=tr("New name (up to {n} characters):", n=self.keymap["max_name"] or 20), title=tr("Layer name"))
        name = (d.get_input() or "").strip()
        if not name:
            return
        name = name[: self.keymap["max_name"] or 20]

        def job():
            self.studio.set_layer_name(layer["id"], name)
            return name

        def done(n):
            layer["name"] = n
            self._refresh_layers()
            self._set_unsaved(True)

        self.worker.submit(job, done, self._failed)

    # ---------- drawing ----------
    def _geometry(self):
        """Key rectangles in canvas pixels (with rotation)."""
        keys = self.layout or []
        if not keys:
            return [], 1
        pts = [self._corners(k, 1.0) for k in keys]
        xs = [x for p in pts for x, _ in p]
        ys = [y for p in pts for _, y in p]
        w = max(self.canvas.winfo_width(), 200) - 20
        scale = min(w / (max(xs) - min(xs) or 1), 240 / (max(ys) - min(ys) or 1))
        ox = (w + 20 - (max(xs) - min(xs)) * scale) / 2 - min(xs) * scale
        oy = 10 - min(ys) * scale
        return [[(ox + x * scale, oy + y * scale) for x, y in p] for p in pts], scale

    @staticmethod
    def _corners(k, s):
        x, y, w, h = k["x"] / 100, k["y"] / 100, k["w"] / 100, k["h"] / 100
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        if k["r"]:
            a = math.radians(k["r"] / 100)
            cx, cy = k["rx"] / 100, k["ry"] / 100
            pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                    cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in pts]
        return [(px * s, py * s) for px, py in pts]

    def draw(self):
        c = self.canvas
        c.delete("all")
        if not self.keymap or not self.layout:
            c.create_text(c.winfo_width() / 2, 120, text=tr("Keyboard not connected"), fill=MUTED,
                          font=("Segoe UI", 12))
            return
        polys, scale = self._geometry()
        self._polys = polys
        bindings = self.keymap["layers"][self.layer_idx]["bindings"]
        c.configure(height=int(max(y for p in polys for _, y in p) + 10))
        for i, p in enumerate(polys):
            b = bindings[i] if i < len(bindings) else (0, 0, 0)
            name = self.behaviors.get(b[0], {}).get("name", "")
            fill = KEY_SEL if i == self.sel else (KEY_TRANS if name in ("Transparent", "None") else KEY_BG)
            inset = 2
            cx = sum(x for x, _ in p) / 4
            cy = sum(y for _, y in p) / 4
            shrunk = [(x + (cx - x) * inset / max(abs(cx - x), 1), y + (cy - y) * inset / max(abs(cy - y), 1))
                      for x, y in p]
            c.create_polygon(*[v for pt in shrunk for v in pt], fill=fill, outline="#2c3340")
            text = self.binding_text(b)
            size = max(7, min(11, int(scale * 0.22)))
            if len(text) > 7:
                size = max(7, size - 2)
            c.create_text(cx, cy, text=text, fill="#e6e9ef" if name != "Transparent" else MUTED,
                          font=("Segoe UI", size), width=max(20, (p[1][0] - p[0][0]) - 4), justify="center")

    def binding_text(self, b):
        bid, p1, p2 = b
        beh = self.behaviors.get(bid)
        if not beh:
            return "?"
        name = beh["name"]
        short = SHORT_BEHAVIOR.get(name, name[:8])
        layers = self.keymap["layers"]

        def layer_name(i):
            return layers[i]["name"] if i < len(layers) and layers[i]["name"] else str(i)

        if name == "Key Press":
            return K.label(p1)
        if name in ("Momentary Layer", "Toggle Layer", "To Layer", "Sticky Layer"):
            return f"{short} {layer_name(p1)}"
        if name == "Layer-Tap":
            return f"{K.label(p2)}\n{short} {layer_name(p1)}"
        if name == "Mod-Tap":
            return f"{K.label(p2)}\n{K.label(p1)}"
        if name in ("Transparent", "None"):
            return short
        desc = self._param_text(beh, p1, p2)
        return f"{short}\n{desc}" if desc else short

    def _param_text(self, beh, p1, p2):
        out = []
        for s in beh["metadata"]:
            for val, descs in ((p1, s["param1"]), (p2, s["param2"])):
                for d in descs:
                    if d["type"] == "constant" and d["value"] == val:
                        out.append(d["name"])
                    elif d["type"] == "hid" and val:
                        out.append(K.label(val))
            if out:
                break
        return " ".join(dict.fromkeys(out))[:14]

    def _click(self, e):
        if not self.keymap:
            return
        for i, p in enumerate(getattr(self, "_polys", [])):
            if _inside(e.x, e.y, p):
                self.sel = i
                self.draw()
                self._show_editor()
                return

    # ---------- key editor ----------
    def _show_editor(self):
        for w in self.editor.winfo_children():
            w.destroy()
        if not self.keymap:
            ctk.CTkLabel(self.editor, text=tr("Connect to the keyboard, then click a key in the picture."),
                         text_color=MUTED).pack(padx=18, pady=18, anchor="w")
            return
        if self.sel is None:
            ctk.CTkLabel(self.editor, text=tr("Click a key in the picture to change what it does on this layer."),
                         text_color=MUTED).pack(padx=18, pady=18, anchor="w")
            return
        b = self.keymap["layers"][self.layer_idx]["bindings"][self.sel]
        BindingEditor(self.editor, self, b).pack(fill="both", expand=True, padx=14, pady=12)

    def apply(self, binding):
        layer = self.keymap["layers"][self.layer_idx]
        pos = self.sel

        def job():
            self.studio.set_binding(layer["id"], pos, *binding)
            return binding

        def done(b):
            layer["bindings"][pos] = tuple(b)
            self._set_unsaved(True)
            self.draw()

        self.worker.submit(job, done, self._failed)

    def save(self):
        self.worker.submit(lambda: self.studio.save(), lambda _: self._set_unsaved(False), self._failed)

    def discard(self):
        def job():
            self.studio.discard()
            return self.studio.keymap()

        def done(km):
            self.keymap = km
            self._set_unsaved(False)
            self._refresh_layers()
            self.draw()
            self._show_editor()

        self.worker.submit(job, done, self._failed)


def _inside(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class BindingEditor(ctk.CTkFrame):
    """Choosing the action and its parameters for one key."""

    def __init__(self, master, page, binding):
        super().__init__(master, fg_color="transparent")
        self.page = page
        self.bid, self.p1, self.p2 = binding
        beh = page.behaviors
        self.names = sorted((b["name"] for b in beh.values()), key=lambda n: (n != "Key Press", n))
        self.by_name = {b["name"]: b for b in beh.values()}

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=tr("Key {n}", n=page.sel + 1), font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text=tr("Action"), text_color=MUTED).pack(side="left", padx=(18, 6))
        self.beh = ctk.CTkOptionMenu(top, values=self.names, command=self._beh_changed, width=200)
        self.beh.set(beh.get(self.bid, {}).get("name", self.names[0]))
        self.beh.pack(side="left")
        ctk.CTkButton(top, text=tr("⌨  Press a key…"), width=160, command=self._capture).pack(side="right")
        self.params = ctk.CTkFrame(self, fg_color="transparent")
        self.params.pack(fill="both", expand=True, pady=(10, 0))
        self._build_params()

    def _behavior(self):
        return self.by_name[self.beh.get()]

    def _beh_changed(self, _):
        b = self._behavior()
        self.bid = b["id"]
        self.p1 = self.p2 = 0
        d1, _ = self._param_sets(b)
        self.p1 = _default(d1)
        _, d2 = self._param_sets(b)
        self.p2 = _default(d2)
        self._build_params()
        if not self._needs_params(b):
            self._apply()

    @staticmethod
    def _needs_params(b):
        return any(any(d["type"] != "nil" for d in s["param1"] + s["param2"]) for s in b["metadata"])

    def _param_sets(self, b):
        """param1 descriptions, and param2 descriptions matching the chosen param1."""
        p1 = [d for s in b["metadata"] for d in s["param1"]]
        p2 = []
        for s in b["metadata"]:
            if not s["param1"] or any(_matches(d, self.p1) for d in s["param1"]):
                p2 += s["param2"]
        return _dedupe(p1), _dedupe(p2)

    def _build_params(self):
        for w in self.params.winfo_children():
            w.destroy()
        b = self._behavior()
        d1, d2 = self._param_sets(b)
        row = 0
        for idx, descs in ((1, d1), (2, d2)):
            descs = [d for d in descs if d["type"] != "nil"]
            if not descs:
                continue
            label = tr("Key") if any(d["type"] == "hid" for d in descs) else (tr("Layer") if any(
                d["type"] == "layer" for d in descs) else tr("Value"))
            if label == tr("Value") and len(descs) == 1 and descs[0]["name"]:
                label = descs[0]["name"]
            if b["name"] == "Mod-Tap" and idx == 1:
                label = tr("Hold")
            if b["name"] in ("Mod-Tap", "Layer-Tap") and idx == 2:
                label = tr("Tap")
            ctk.CTkLabel(self.params, text=label, text_color=MUTED).grid(row=row, column=0, sticky="w", padx=(0, 10),
                                                                         pady=4)
            self._param_widget(idx, descs).grid(row=row, column=1, sticky="w", pady=4)
            row += 1
        if row == 0:
            ctk.CTkLabel(self.params, text=tr("This action has no settings."), text_color=MUTED).grid(row=0, column=0,
                                                                                            sticky="w")

    def _value(self, idx):
        return self.p1 if idx == 1 else self.p2

    def _set(self, idx, v, apply=True):
        if idx == 1:
            self.p1 = v
        else:
            self.p2 = v
        if idx == 1:
            self._build_params()
        if apply:
            self._apply()

    def _param_widget(self, idx, descs):
        types = {d["type"] for d in descs}
        val = self._value(idx)
        if "hid" in types:
            f = ctk.CTkFrame(self.params, fg_color="transparent")
            ctk.CTkLabel(f, text=K.label(val, long=True) if val else "—", width=220, anchor="w",
                         font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
            ctk.CTkButton(f, text=tr("From list…"), width=90, fg_color=CARD_HI,
                          command=lambda: KeyList(self, lambda v: self._set(idx, v))).pack(side="left", padx=6)
            ctk.CTkButton(f, text=tr("Press…"), width=90, fg_color=CARD_HI,
                          command=lambda: KeyCapture(self, lambda v: self._set(idx, v))).pack(side="left")
            return f
        if "layer" in types:
            names = self.page._layer_names()
            m = ctk.CTkOptionMenu(self.params, values=names,
                                  command=lambda n: self._set(idx, names.index(n)))
            m.set(names[val] if val < len(names) else names[0])
            return m
        consts = [d for d in descs if d["type"] == "constant"]
        if consts:
            labels = [d["name"] or str(d["value"]) for d in consts]
            m = ctk.CTkOptionMenu(self.params, values=labels,
                                  command=lambda n: self._set(idx, consts[labels.index(n)]["value"]))
            cur = next((d for d in consts if d["value"] == val), consts[0])
            m.set(cur["name"] or str(cur["value"]))
            return m
        rng = next((d for d in descs if d["type"] == "range"), None)
        if rng:
            e = ctk.CTkEntry(self.params, width=90)
            e.insert(0, str(val))
            ctk.CTkLabel(self.params, text=f"{rng['min']}–{rng['max']}", text_color=MUTED)

            def commit(_=None):
                try:
                    v = max(rng["min"], min(rng["max"], int(e.get())))
                except ValueError:
                    return
                self._set(idx, v)

            e.bind("<Return>", commit)
            e.bind("<FocusOut>", commit)
            return e
        return ctk.CTkLabel(self.params, text=str(val))

    def _apply(self):
        self.page.apply((self.bid, self.p1, self.p2))

    def _capture(self):
        def got(v):
            kp = self.by_name.get("Key Press")
            if not kp:
                return
            self.beh.set("Key Press")
            self.bid, self.p1, self.p2 = kp["id"], v, 0
            self._build_params()
            self._apply()

        KeyCapture(self, got)


def _default(descs):
    for d in descs:
        if d["type"] == "constant":
            return d["value"]
        if d["type"] == "range":
            return d["min"]
    return 0


def _matches(d, v):
    if d["type"] == "constant":
        return d["value"] == v
    if d["type"] == "range":
        return d["min"] <= v <= d["max"]
    return True


def _dedupe(descs):
    seen, out = set(), []
    for d in descs:
        key = (d["type"], d.get("value"), d["name"])
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


class KeyCapture(ctk.CTkToplevel):
    """Dialog: press a key (with Ctrl/Shift/Alt/AltGr/Win); the result is a &kp value."""

    def __init__(self, master, on_pick):
        super().__init__(master)
        self.on_pick = on_pick
        self.title(tr("Press a key"))
        self.geometry("420x170")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.held = {}
        ctk.CTkLabel(self, text=tr("Press a key or a shortcut (e.g. Ctrl+C).\nModifier alone: press and release."),
                     justify="center").pack(pady=(18, 6))
        self.show = ctk.CTkLabel(self, text="…", font=ctk.CTkFont(size=20, weight="bold"))
        self.show.pack(pady=4)
        ctk.CTkButton(self, text=tr("Cancel"), width=90, fg_color=CARD_HI, command=self.destroy).pack(pady=6)
        self.bind("<KeyPress>", self._down)
        self.bind("<KeyRelease>", self._up)
        self.after(80, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()
        self.grab_set()

    def _mods(self):
        bits = 0
        for _, (bit, _id) in self.held.items():
            bits |= bit
        # AltGr on Windows = left Ctrl + right Alt: the left Ctrl is fake
        if bits & 0x40:
            bits &= ~0x01
        return bits

    def _down(self, e):
        if e.keysym in K.MOD_KEYSYMS:
            self.held[e.keysym] = K.MOD_KEYSYMS[e.keysym]
            self.last_mod = e.keysym
            self.show.configure(text=K.mods_text(self._mods()) + "+…")
            return "break"
        key = K.BY_VK.get(e.keycode)
        if e.keysym in ("KP_Enter",):
            key = K.BY_ID["KP_ENTER"]
        if not key:
            self.show.configure(text=tr("unknown key ({k})", k=e.keysym))
            return "break"
        self._done(K.encode(key, self._mods()))
        return "break"

    def _up(self, e):
        if e.keysym in K.MOD_KEYSYMS and e.keysym in self.held:
            if len(self.held) == 1 or (self._mods() == self.held[e.keysym][0]):
                _bit, kid = self.held[e.keysym]
                self._done(K.encode(K.BY_ID[kid]))
                return "break"
            self.held.pop(e.keysym, None)
        return "break"

    def _done(self, value):
        self.show.configure(text=K.label(value, long=True))
        self.after(250, lambda: (self.destroy(), self.on_pick(value)))
        self.unbind("<KeyPress>")
        self.unbind("<KeyRelease>")


class KeyList(ctk.CTkToplevel):
    """Key list with search and modifiers."""

    def __init__(self, master, on_pick):
        super().__init__(master)
        self.on_pick = on_pick
        self.title(tr("Choose a key"))
        self.geometry("520x560")
        self.attributes("-topmost", True)
        self.after(80, self.grab_set)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.q = ctk.CTkEntry(top, placeholder_text=tr("Search…"))
        self.q.pack(fill="x")
        self.q.bind("<KeyRelease>", lambda e: self.fill())
        mods = ctk.CTkFrame(self, fg_color="transparent")
        mods.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(mods, text=tr("With:"), text_color=MUTED).pack(side="left")
        self.mod_vars = []
        for _, name, bit in K.MODS:
            v = tk.IntVar(value=0)
            ctk.CTkCheckBox(mods, text=name, variable=v, width=60, checkbox_width=16, checkbox_height=16).pack(
                side="left", padx=2)
            self.mod_vars.append((v, bit))
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.fill()

    def fill(self):
        for w in self.list.winfo_children():
            w.destroy()
        q = self.q.get().strip().lower()
        for group in K.GROUPS:
            keys = [k for k in K.KEYS if k["group"] == group and (not q or q in (k["pl"] + " " + k["en"] + " " + k["id"]).lower())]
            if not keys:
                continue
            ctk.CTkLabel(self.list, text=tr(group), text_color=MUTED).pack(anchor="w", pady=(6, 2))
            for k in keys:
                ctk.CTkButton(self.list, text=f"{k['short']:<8}  {K.desc(k)}", anchor="w", fg_color=CARD,
                              hover_color=CARD_HI, height=26, command=lambda k=k: self.pick(k)).pack(fill="x", pady=1)

    def pick(self, key):
        mods = 0
        for v, bit in self.mod_vars:
            if v.get():
                mods |= bit
        self.destroy()
        self.on_pick(K.encode(key, mods))
