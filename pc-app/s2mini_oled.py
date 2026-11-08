"""
Wysyła dane z PC na ekran klawiatury S2 mini 60 (ZMK, Raw HID):
głośność, obciążenie i temperatura CPU/GPU, godzina (raz na sekundę)
oraz listę podłączonych portów COM (co 2 s), to, co gra (tytuł/wykonawca), i prędkość sieci.

Źródła danych (Windows):
- głośność: pycaw (domyślne wyjście audio),
- CPU/GPU: LibreHardwareMonitor z włączonym „Remote Web Server” (http://localhost:8085),
  a bez niego obciążenie CPU z psutil i GPU NVIDIA z nvidia-smi (bez temperatury CPU),
- godzina: zegar systemu,
- porty COM: pyserial (nazwy znanych płytek po VID:PID),
- co gra: Windows Media (pakiety winrt-*, opcjonalnie; bez nich ekran pokaże „nothing playing”),
- sieć: psutil (suma wszystkich kart),
- powiadomienia: Windows UserNotificationListener (te same pakiety winrt + UI.Notifications);
  na ekran idzie aplikacja, tytuł i początek treści nowego powiadomienia (--no-notifications wyłącza).

Uruchomienie:  pythonw s2mini_oled.py          (ikona w zasobniku, gdy jest pystray)
               python  s2mini_oled.py --console (wypisuje wysyłane dane)
               python  s2mini_oled.py --dry-run  (bez klawiatury, tylko odczyt danych)

SPDX-License-Identifier: MIT
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

VID = 0x1D50
PID = 0x615E
USAGE_PAGE = 0xFF60
REPORT_SIZE = 32
MAGIC, VERSION, PORTS, MEDIA, NOTIF = 0x53, 0x01, 0x02, 0x03, 0x04
APP_NAME, APP_ICON, LAUNCH = 0x05, 0x06, 0x10
APPS_MAX = 16
PORT_TEXT = 28
F_CPU, F_GPU, F_VOLUME, F_TIME, F_MUTED, F_IGPU, F_NET = 1, 2, 4, 8, 16, 32, 64

LHM_URL = "http://localhost:8085/data.json"


# ---------- dane ----------

def _num(text):
    """'54,3 °C' / '23.0 %' -> 54.3"""
    try:
        return float(str(text).split()[0].replace(",", "."))
    except (ValueError, IndexError):
        return None


def _walk(node, path=()):
    yield node, path
    for child in node.get("Children", []):
        yield from _walk(child, path + (node.get("Text", ""),))


CPU_TEMP_NAMES = ("cpu package", "core (tctl/tdie)", "package", "core (tctl)", "cpu")


def read_lhm(url=LHM_URL):
    """Zwraca dict cpu_load, cpu_temp, gpu_load, gpu_temp, igpu_load (brakujące = None) z LibreHardwareMonitor.

    gpu_* = karta (NVIDIA/AMD), igpu_load = zintegrowany Intel (LHM daje mu tylko obciążenie „D3D 3D”).
    """
    with urllib.request.urlopen(url, timeout=0.8) as r:
        tree = json.load(r)
    out = dict(cpu_load=None, cpu_temp=None, gpu_load=None, gpu_temp=None, igpu_load=None)
    cpu_temp_rank = len(CPU_TEMP_NAMES)
    for node, _ in _walk(tree):
        sid = str(node.get("SensorId", "")).lower()
        text = str(node.get("Text", "")).lower()
        stype = str(node.get("Type", "")).lower()
        value = _num(node.get("Value"))
        if not sid or value is None:
            continue
        is_cpu = sid.startswith(("/intelcpu", "/amdcpu", "/cpu"))
        is_igpu = sid.startswith("/gpu-intel")
        is_gpu = sid.startswith("/gpu") and not is_igpu
        is_temp = stype == "temperature" or "/temperature/" in sid
        is_load = stype == "load" or "/load/" in sid
        if is_cpu and is_load and text == "cpu total":
            out["cpu_load"] = value
        elif is_cpu and is_temp and text in CPU_TEMP_NAMES:
            rank = CPU_TEMP_NAMES.index(text)
            if rank < cpu_temp_rank:
                out["cpu_temp"], cpu_temp_rank = value, rank
        elif is_igpu and is_load and text in ("d3d 3d", "gpu core") and out["igpu_load"] is None:
            out["igpu_load"] = value
        elif is_gpu and is_load and text == "gpu core" and out["gpu_load"] is None:
            out["gpu_load"] = value
        elif is_gpu and is_temp and text in ("gpu core", "gpu temperature") and out["gpu_temp"] is None:
            out["gpu_temp"] = value
    return out


def read_nvidia_smi():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    res = subprocess.run(
        [exe, "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=2, creationflags=flags)
    load, temp = (float(x) for x in res.stdout.strip().splitlines()[0].split(","))
    return load, temp


class Volume:
    """Głośność domyślnego wyjścia (pycaw). Odświeża urządzenie co kilka sekund."""

    def __init__(self):
        self.endpoint = None
        self.got_at = 0.0
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

    def _endpoint(self):
        if self.endpoint is None or time.monotonic() - self.got_at > 5:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            ep = getattr(speakers, "EndpointVolume", None)
            if ep is None:  # starsze pycaw
                from ctypes import POINTER, cast
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume
                iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                ep = cast(iface, POINTER(IAudioEndpointVolume))
            self.endpoint, self.got_at = ep, time.monotonic()
        return self.endpoint

    def read(self):
        try:
            ep = self._endpoint()
            return round(ep.GetMasterVolumeLevelScalar() * 100), bool(ep.GetMute())
        except Exception:
            self.endpoint = None
            return None, False


def collect(volume, on=None):
    on = on or {}
    data = dict(cpu_load=None, cpu_temp=None, gpu_load=None, gpu_temp=None, igpu_load=None)
    try:
        data.update({k: v for k, v in read_lhm().items() if v is not None})
    except Exception:
        pass
    if data["cpu_load"] is None:
        try:
            import psutil
            data["cpu_load"] = psutil.cpu_percent(interval=None)
        except Exception:
            pass
    if data["gpu_load"] is None:
        try:
            nv = read_nvidia_smi()
            if nv:
                data["gpu_load"], data["gpu_temp"] = nv
        except Exception:
            pass
    data["volume"], data["muted"] = volume.read() if on.get("volume", True) else (None, False)
    if not on.get("cpu", True):
        data["cpu_load"] = data["cpu_temp"] = None
    if not on.get("gpu", True):
        data["gpu_load"] = data["gpu_temp"] = None
    if not on.get("igpu", True):
        data["igpu_load"] = None
    data["time"] = time.localtime()
    return data


def frame(data):
    b = bytearray(REPORT_SIZE)
    b[0], b[1] = MAGIC, VERSION
    flags = F_TIME
    clamp = lambda v: max(0, min(255, int(round(v or 0))))
    if data["cpu_load"] is not None:
        flags |= F_CPU
        b[3], b[4] = clamp(data["cpu_load"]), clamp(data["cpu_temp"])
    if data["gpu_load"] is not None or data["gpu_temp"] is not None:
        flags |= F_GPU
        b[5], b[6] = clamp(data["gpu_load"]), clamp(data["gpu_temp"])
    if data["volume"] is not None:
        flags |= F_VOLUME
        b[7] = clamp(data["volume"])
    if data["muted"]:
        flags |= F_MUTED
    if data.get("net") is not None:
        flags |= F_NET
        down, up = (max(0, min(65535, int(v))) for v in data["net"])
        b[12:14] = down.to_bytes(2, "little")
        b[14:16] = up.to_bytes(2, "little")
    if data.get("igpu_load") is not None:
        flags |= F_IGPU
        b[11] = clamp(data["igpu_load"])
    t = data["time"]
    b[8], b[9], b[10] = t.tm_hour, t.tm_min, t.tm_sec
    b[2] = flags
    return bytes(b)


# ---------- porty COM ----------

KNOWN_USB = {
    (0x303A, 0x0002): "ESP32-S2 boot",
    (0x303A, 0x1001): "ESP32-S3/C3 JTAG",
    (0x303A, 0x0009): "ESP32-S3 boot",
    (0x1D50, 0x615E): "ZMK S2 mini",
    (0x2E8A, 0x0005): "RP2040 MicroPython",
    (0x2E8A, 0x000A): "RP2040",
    (0x239A, None): "Adafruit",
    (0x2341, None): "Arduino",
    (0x1A86, None): "CH340",
    (0x10C4, None): "CP210x",
    (0x0403, None): "FTDI",
}


def port_label(p):
    name = KNOWN_USB.get((p.vid, p.pid)) or KNOWN_USB.get((p.vid, None))
    if not name:
        name = (p.product or p.description or "").replace(f"({p.device})", "").strip()
        for junk in ("USB Serial Device", "Standard Serial over Bluetooth link"):
            if name.startswith(junk) and p.manufacturer and "Microsoft" not in p.manufacturer:
                name = p.manufacturer
        name = name.replace("Standard Serial over Bluetooth link", "Bluetooth")
    return f"{p.device} {name}".strip()[:PORT_TEXT - 1]


def list_com_ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        return None

    def key(p):
        digits = "".join(c for c in p.device if c.isdigit())
        return (int(digits) if digits else 0, p.device)

    return [port_label(p) for p in sorted(list_ports.comports(), key=key)]


def port_frames(labels):
    """Ramki 0x02: po jednej na port; przy pustej liście jedna ramka z liczbą 0."""
    frames = []
    count = min(len(labels), 255)
    for i, text in enumerate(labels[:255] or [None]):
        b = bytearray(REPORT_SIZE)
        b[0], b[1], b[2], b[3] = MAGIC, PORTS, i, count
        if text:
            raw = text.encode("ascii", "replace")[:PORT_TEXT - 1]
            b[4:4 + len(raw)] = raw
        frames.append(bytes(b))
    return frames


# ---------- sieć ----------

class NetRate:
    """Prędkość sieci w KB/s (pobieranie, wysyłanie) z różnicy liczników psutil."""

    def __init__(self):
        self.last = None

    def read(self):
        try:
            import psutil
            c = psutil.net_io_counters()
        except Exception:
            return None
        now = time.monotonic()
        prev, self.last = self.last, (now, c.bytes_recv, c.bytes_sent)
        if prev is None or now <= prev[0]:
            return None
        dt = now - prev[0]
        return ((c.bytes_recv - prev[1]) / dt / 1000, (c.bytes_sent - prev[2]) / dt / 1000)


# ---------- co gra ----------

PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def to_ascii(text):
    import unicodedata
    text = (text or "").translate(PL)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


class Media:
    """Tytuł, wykonawca i stan odtwarzania z Windows (GSMTC). Bez pakietów winrt zwraca None."""

    def __init__(self):
        self.ok = True

    def read(self):
        if not self.ok:
            return None
        try:
            import asyncio
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
            )
        except Exception:
            self.ok = False
            return None

        async def get():
            mgr = await Manager.request_async()
            ses = mgr.get_current_session()
            if ses is None:
                return (0, "", "")
            props = await ses.try_get_media_properties_async()
            status = ses.get_playback_info().playback_status
            state = 1 if status == Status.PLAYING else (2 if status == Status.PAUSED else 0)
            return (state, props.title or "", props.artist or "")

        try:
            return asyncio.run(get())
        except Exception:
            return None


def media_frames(state, title, artist):
    """Ramki 0x03: tytuł, potem wykonawca (ASCII, do 28 znaków)."""
    frames = []
    for field, text in ((0, title), (1, artist)):
        b = bytearray(REPORT_SIZE)
        b[0], b[1], b[2], b[3] = MAGIC, MEDIA, state, field
        raw = to_ascii(text).encode("ascii")[:PORT_TEXT]
        b[4:4 + len(raw)] = raw
        frames.append(bytes(b))
    return frames


# ---------- powiadomienia ----------

class Notifications:
    """Nowe powiadomienia Windows (toast). Pierwszy odczyt tylko zapamiętuje istniejące."""

    def __init__(self):
        self.ok = True
        self.seen = None
        self.seq = 0

    def read(self):
        """Zwraca listę nowych (aplikacja, tytuł, treść), najstarsze pierwsze."""
        if not self.ok:
            return []
        try:
            import asyncio
            from winrt.windows.ui.notifications.management import UserNotificationListener
            from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
        except Exception:
            self.ok = False
            return []

        async def get():
            listener = UserNotificationListener.current
            if int(listener.get_access_status()) != 1:  # 1 = Allowed
                if int(await listener.request_access_async()) != 1:
                    return None
            items = await listener.get_notifications_async(NotificationKinds.TOAST)
            out = []
            for n in items:
                try:
                    app = n.app_info.display_info.display_name
                except Exception:
                    app = ""
                texts = []
                try:
                    binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
                    if binding is not None:
                        texts = [t.text for t in binding.get_text_elements()]
                except Exception:
                    pass
                out.append((n.id, app, texts[0] if texts else "", " ".join(texts[1:])))
            return out

        try:
            items = asyncio.run(get())
        except Exception:
            return []
        if items is None:
            self.ok = False
            return []
        ids = {i[0] for i in items}
        if self.seen is None:
            self.seen = ids
            return []
        new = [i[1:] for i in items if i[0] not in self.seen]
        self.seen = ids
        return new[-1:]  # na ekran tylko najnowsze

    def frames(self, app, title, body):
        self.seq = (self.seq + 1) % 256
        frames = []
        for field, text in ((0, app), (1, title), (2, body)):
            b = bytearray(REPORT_SIZE)
            b[0], b[1], b[2], b[3] = MAGIC, NOTIF, self.seq, field
            raw = to_ascii(text).encode("ascii")[:PORT_TEXT]
            b[4:4 + len(raw)] = raw
            frames.append(bytes(b))
        return frames


# ---------- ustawienia ----------

DATA_KEYS = ("cpu", "gpu", "igpu", "volume", "net", "media", "ports", "notifications")
DEFAULT_CONFIG = {
    "data": {k: k != "notifications" for k in DATA_KEYS},
    "apps": [],  # {"name", "path", "style", "invert", "icon"(opcjonalny obrazek)}
}


def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, "S2mini60", "config.json")


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(config_path(), encoding="utf-8") as f:
            saved = json.load(f)
        cfg["data"].update({k: bool(v) for k, v in saved.get("data", {}).items() if k in DATA_KEYS})
        cfg["apps"] = [a for a in saved.get("apps", []) if isinstance(a, dict) and a.get("path")][:APPS_MAX]
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"config: {e}")
    return cfg


def save_config(cfg):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- szybki start ----------

def app_icon_bits(app):
    """128 B ikony aplikacji w stylu z ustawień."""
    import icons
    src = icons.extract_icon(app.get("icon") or app["path"])
    return icons.pack_bits(icons.to_keyboard(src, app.get("style", "auto"), app.get("invert", False)))


def app_frames(apps, icon_cache):
    """Ramki 0x05 (nazwa) i 0x06 (5 kawałków ikony) dla każdej aplikacji; pusta lista = jedna ramka."""
    frames = []
    count = min(len(apps), APPS_MAX)
    if count == 0:
        b = bytearray(REPORT_SIZE)
        b[0], b[1], b[2], b[3] = MAGIC, APP_NAME, 0, 0
        return [bytes(b)]
    for i, app in enumerate(apps[:APPS_MAX]):
        b = bytearray(REPORT_SIZE)
        b[0], b[1], b[2], b[3] = MAGIC, APP_NAME, i, count
        raw = to_ascii(app.get("name") or os.path.splitext(os.path.basename(app["path"]))[0]).encode("ascii")[:PORT_TEXT]
        b[4:4 + len(raw)] = raw
        frames.append(bytes(b))
        key = (app["path"], app.get("icon"), app.get("style", "auto"), bool(app.get("invert")))
        if key not in icon_cache:
            try:
                icon_cache[key] = app_icon_bits(app)
            except Exception:
                icon_cache[key] = bytes(128)
        bits = icon_cache[key]
        for chunk in range(5):
            b = bytearray(REPORT_SIZE)
            b[0], b[1], b[2], b[3] = MAGIC, APP_ICON, i, chunk
            part = bits[chunk * 28:(chunk + 1) * 28]
            b[4:4 + len(part)] = part
            frames.append(bytes(b))
    return frames


def launch_app(app, log=print):
    path = app.get("path")
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        log(f"launch {path}")
    except Exception as e:
        log(f"launch failed: {path}: {e}")


# ---------- klawiatura ----------

def open_keyboard():
    import hid
    for info in hid.enumerate(VID, PID):
        if info.get("usage_page") == USAGE_PAGE:
            dev = hid.device()
            dev.open_path(info["path"])
            return dev
    return None


class Sender(threading.Thread):
    def __init__(self, console=False, dry_run=False, notifications=None, config=None):
        super().__init__(daemon=True)
        self.config = config or load_config()
        if notifications is not None:
            self.config["data"]["notifications"] = notifications
        self.config_version = 0
        self.last_line = ""
        self.launches = 0
        self.console, self.dry_run = console, dry_run
        self.stop_event = threading.Event()
        self.status = "starting"

    def log(self, *a):
        if self.console:
            print(*a, flush=True)

    def set_config(self, cfg):
        """Nowe ustawienia z okna (lista aplikacji wysyłana od razu)."""
        self.config = copy.deepcopy(cfg)
        self.config_version += 1

    def _poll_launch(self, dev, seconds):
        """Czeka do `seconds`, czytając raporty z klawiatury (prośby o uruchomienie)."""
        end = time.monotonic() + seconds
        while not self.stop_event.is_set():
            left = end - time.monotonic()
            if left <= 0:
                return
            if dev is None:
                self.stop_event.wait(left)
                return
            data = dev.read(64, int(min(left, 0.1) * 1000))
            if data and len(data) >= 3 and data[0] == MAGIC and data[1] == LAUNCH:
                apps = self.config.get("apps", [])
                if data[2] < len(apps):
                    self.launches += 1
                    launch_app(apps[data[2]], self.log)

    def run(self):
        volume = Volume()
        net = NetRate()
        media = Media()
        notes = Notifications()
        icon_cache = {}
        sent_version = -1
        dev = None
        try:
            import psutil
            psutil.cpu_percent(interval=None)  # pierwszy odczyt zawsze 0
        except Exception:
            pass
        tick = 0
        while not self.stop_event.is_set():
            on = self.config["data"]
            data = collect(volume, on)
            data["net"] = net.read() if on.get("net", True) else None
            payloads = [frame(data)]
            m = media.read() if on.get("media", True) else None
            if m is not None:
                payloads += media_frames(*m)
                data["media"] = m
            if on.get("notifications") and tick % 2 == 1:
                for app, title, body in notes.read():
                    payloads += notes.frames(app, title, body)
                    data["notif"] = to_ascii(app)
            elif not on.get("notifications"):
                notes.seen = None  # po włączeniu nie wysyłaj starych
            # lista aplikacji: po zmianie, po podłączeniu i co 20 s
            if sent_version != self.config_version or tick % 20 == 0:
                payloads += app_frames(self.config.get("apps", []), icon_cache)
                sent_version = self.config_version
            if tick % 2 == 0 and on.get("ports", True):
                ports = list_com_ports()
                if ports is not None:
                    payloads += port_frames(ports)
                    data["ports"] = ports
            tick += 1
            if self.dry_run:
                self.log(fmt(data))
            else:
                try:
                    if dev is None:
                        dev = open_keyboard()
                        self.status = "connected" if dev else "keyboard not found"
                        self.log(self.status)
                        if dev is not None:
                            payloads += app_frames(self.config.get("apps", []), icon_cache)
                    if dev is not None:
                        # Windows/hidapi: pierwszy bajt to numer raportu (0 = bez numeru).
                        for payload in payloads:
                            if dev.write(b"\x00" + payload) < 0:
                                raise OSError("write failed")
                        self.last_line = fmt(data)
                        self.log(self.last_line)
                except Exception as e:
                    self.status = f"error: {e}"
                    self.log(self.status)
                    try:
                        dev and dev.close()
                    except Exception:
                        pass
                    dev = None
            try:
                self._poll_launch(dev, 1.0)
            except Exception as e:
                self.log(f"read: {e}")
                try:
                    dev and dev.close()
                except Exception:
                    pass
                dev = None


def fmt(d):
    f = lambda v, u: "--" if v is None else f"{v:.0f}{u}"
    return (f"{time.strftime('%H:%M:%S', d['time'])}  CPU {f(d['cpu_load'], '%')} {f(d['cpu_temp'], '°C')}"
            f"  GPU {f(d['gpu_load'], '%')} {f(d['gpu_temp'], '°C')}"
            f"  iGPU {f(d.get('igpu_load'), '%')}"
            f"  VOL {'mute' if d['muted'] else f(d['volume'], '%')}"
            + (f"  NET {d['net'][0]:.0f}/{d['net'][1]:.0f} KB/s" if d.get("net") else "")
            + (f"  MEDIA {['-', 'play', 'pause'][d['media'][0]]} {to_ascii(d['media'][1])!r} {to_ascii(d['media'][2])!r}"
               if d.get("media") else "")
            + (f"  NOTIF {d['notif']!r}" if d.get("notif") is not None else "")
            + (f"  PORTS {', '.join(d['ports']) or '-'}" if "ports" in d else ""))


def run_tray(sender):
    import pystray
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), (10, 12, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([6, 14, 58, 50], outline=(150, 210, 255), width=4)
    d.rectangle([14, 22, 34, 30], fill=(150, 210, 255))
    d.rectangle([14, 36, 48, 42], fill=(150, 210, 255))

    def on_quit(icon, _):
        sender.stop_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: f"S2 mini 60: {sender.status}", None, enabled=False),
        pystray.MenuItem("Quit", on_quit))
    pystray.Icon("s2mini_oled", img, "S2 mini 60 OLED", menu).run()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--console", action="store_true", help="bez ikony w zasobniku, wypisuje dane")
    ap.add_argument("--dry-run", action="store_true", help="tylko odczyt danych, bez klawiatury")
    ap.add_argument("--no-notifications", action="store_true", help="nie wysyłaj powiadomień Windows na ekran")
    args = ap.parse_args()

    sender = Sender(console=args.console or args.dry_run, dry_run=args.dry_run,
                    notifications=False if args.no_notifications else None)
    sender.start()
    if args.console or args.dry_run:
        try:
            while sender.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            sender.stop_event.set()
        return
    try:
        run_tray(sender)
    except ImportError:
        print("pystray nie jest zainstalowany: działam w konsoli (Ctrl+C kończy).")
        sender.console = True
        try:
            while sender.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            sender.stop_event.set()


if __name__ == "__main__":
    main()
