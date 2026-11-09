"""
Sends PC data to the S2 mini 60 keyboard screen (ZMK, Raw HID):
volume, CPU/GPU load and temperature, time of day (once a second),
the list of connected COM ports (every 2 s), what is playing (title/artist) and network speed.

Data sources (Windows):
- volume: pycaw (default audio output),
- CPU/GPU: LibreHardwareMonitor with "Remote Web Server" enabled (http://localhost:8085),
  otherwise CPU load from psutil and NVIDIA GPU from nvidia-smi (no CPU temperature),
- time: system clock,
- COM ports: pyserial (known boards named by VID:PID),
- now playing: Windows Media (winrt-* packages, optional; without them the screen shows "nothing playing"),
- network: psutil (sum of all adapters),
- notifications: Windows UserNotificationListener (same winrt packages + UI.Notifications);
  the screen gets the app, title and start of the body of a new notification (--no-notifications disables).

Usage:  pythonw s2mini_oled.py          (tray icon, if pystray is installed)
        python  s2mini_oled.py --console (prints the data being sent)
        python  s2mini_oled.py --dry-run  (no keyboard, only reads the data)

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


# ---------- data ----------

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
    """Returns a dict cpu_load, cpu_temp, gpu_load, gpu_temp, igpu_load (missing = None) from LibreHardwareMonitor.

    gpu_* = graphics card (NVIDIA/AMD), igpu_load = integrated Intel (LHM only gives its "D3D 3D" load).
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
    """Volume of the default output (pycaw). Refreshes the device every few seconds."""

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
            if ep is None:  # older pycaw
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


# ---------- COM ports ----------

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
    """Frames 0x02: one per port; an empty list is one frame with count 0."""
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


# ---------- network ----------

class NetRate:
    """Network speed in KB/s (download, upload) from the difference of psutil counters."""

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


# ---------- now playing ----------

PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def to_ascii(text):
    import unicodedata
    text = (text or "").translate(PL)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


class Background:
    """Calls fn() every `every` s in its own thread; read() returns the last result without waiting.

    Windows queries (winrt) can hang; then they block only this thread, and sending
    to the keyboard carries on. A result older than `max_age` s counts as no data.
    """

    def __init__(self, fn, every=1.0, max_age=5.0):
        self.fn, self.every, self.max_age = fn, every, max_age
        self.value, self.at = None, 0.0
        self.wanted = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        # winrt needs COM in this thread: MTA (no message loop; STA from pycaw made await hang)
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
            except Exception:
                pass
        while True:
            if self.wanted:
                try:
                    v = self.fn()
                except Exception:
                    v = None
                self.value, self.at = v, time.monotonic()
            time.sleep(self.every)

    def read(self):
        if time.monotonic() - self.at > self.max_age:
            return None
        return self.value


class Media:
    """Title, artist and playback state from Windows (GSMTC). Returns None without the winrt packages."""

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
            return asyncio.run(asyncio.wait_for(get(), 3))
        except Exception:
            return None


def media_child():
    """`--media-child` mode: a separate process with COM set up like the main thread; one JSON line per second.

    winrt (GSMTC) in a worker thread of the app returned nothing or hung, while in a separate process
    it works as in the first version of the script. Exits when the main program closes stdin.
    """
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED, like comtypes
        except Exception:
            pass
    threading.Thread(target=lambda: (sys.stdin.read(), os._exit(0)), daemon=True).start()
    media = Media()
    while True:
        try:
            m = media.read()
        except Exception:
            m = None
        try:
            sys.stdout.write(json.dumps(m) + "\n")
            sys.stdout.flush()
        except Exception:
            os._exit(0)
        if not media.ok:
            os._exit(0)  # no winrt: nothing to do
        time.sleep(1.0)


class MediaProcess:
    """Runs `--media-child` and keeps the last result; a hung process is killed and restarted."""

    STALE_S = 10.0

    def __init__(self, max_age=5.0):
        self.max_age = max_age
        self.value, self.at = None, 0.0
        self.proc, self.started = None, 0.0
        self.disabled = False
        threading.Thread(target=self._watch, daemon=True).start()

    def _cmd(self):
        if getattr(sys, "frozen", False):
            return [sys.executable, "--media-child"]
        return [sys.executable, os.path.abspath(__file__), "--media-child"]

    def _start(self):
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen(self._cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, creationflags=flags)
        self.started = time.monotonic()
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            try:
                v = json.loads(line)
            except Exception:
                continue
            self.value = tuple(v) if v else None
            self.at = time.monotonic()

    def _watch(self):
        fails = 0
        backoff, next_try = 0.0, 0.0
        while not self.disabled:
            p = self.proc
            now = time.monotonic()
            if (p is None or p.poll() is not None) and now < next_try:
                pass  # after Windows hangs, wait longer each time (up to 60 s) so processes don't pile up
            elif p is None or p.poll() is not None:
                if p is not None and now - self.started < 5:
                    fails += 1
                    if fails >= 3:  # exits right away (e.g. no winrt): give up
                        self.disabled = True
                        return
                try:
                    self._start()
                except Exception:
                    self.disabled = True
                    return
            elif now - max(self.at, self.started) > self.STALE_S:
                p.kill()
                backoff = min(60.0, backoff * 2 or 5.0)
                next_try = now + backoff
            else:
                fails = 0
                if self.at > self.started:
                    backoff = 0.0
            time.sleep(1.0)

    def read(self):
        if time.monotonic() - self.at > self.max_age:
            return None
        return self.value

    def stop(self):
        self.disabled = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()


def media_frames(state, title, artist):
    """Frames 0x03: title, then artist (ASCII, up to 28 characters)."""
    frames = []
    for field, text in ((0, title), (1, artist)):
        b = bytearray(REPORT_SIZE)
        b[0], b[1], b[2], b[3] = MAGIC, MEDIA, state, field
        raw = to_ascii(text).encode("ascii")[:PORT_TEXT]
        b[4:4 + len(raw)] = raw
        frames.append(bytes(b))
    return frames


# ---------- notifications ----------

class Notifications:
    """New Windows notifications (toasts). The first read only remembers the existing ones."""

    def __init__(self):
        self.ok = True
        self.seen = None
        self.seq = 0

    def read(self):
        """Returns a list of new (app, title, body), oldest first."""
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
            items = asyncio.run(asyncio.wait_for(get(), 3))
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
        return new[-1:]  # only the newest goes to the screen

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


# ---------- settings ----------

DATA_KEYS = ("cpu", "gpu", "igpu", "volume", "net", "media", "ports", "notifications")
DEFAULT_CONFIG = {
    "data": {k: k != "notifications" for k in DATA_KEYS},
    "apps": [],  # {"name", "path", "style", "invert", "icon" (optional image)}
    "default_style": "auto",
    "language": "auto",  # auto = same as Windows, or "pl" / "en"
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
        cfg["default_style"] = saved.get("default_style", "auto")
        cfg["language"] = saved.get("language", "auto")
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


# ---------- quick launch ----------

def app_icon_bits(app):
    """128 B app icon in the style from the settings."""
    import icons
    src = icons.extract_icon(app.get("icon") or app["path"])
    return icons.pack_bits(icons.to_keyboard(src, app.get("style", "auto"), app.get("invert", False)))


def app_frames(apps, icon_cache):
    """Frames 0x05 (name) and 0x06 (5 icon chunks) for each app; an empty list = one frame."""
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
        if os.name == "nt" and path.lower().startswith("shell:appsfolder"):
            subprocess.Popen(["explorer.exe", path])  # Store / MSIX app
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        log(f"launch {path}")
    except Exception as e:
        log(f"launch failed: {path}: {e}")


# ---------- keyboard ----------

def open_keyboard():
    import hid
    for info in hid.enumerate(VID, PID):
        if info.get("usage_page") == USAGE_PAGE:
            dev = hid.device()
            dev.open_path(info["path"])
            return dev
    return None


class HidLink:
    """Raw HID link: a separate writer thread and reader thread, each with its own
    handle. When a hidapi call gets stuck (happens on Windows despite the timeout), the main loop
    does not notice: stuck() reports the stall and Sender opens a new link (the old threads are
    abandoned)."""

    STUCK_S = 4.0

    def __init__(self, on_launch, log):
        import queue
        self.queue = queue.Queue(maxsize=400)
        self.on_launch, self.log = on_launch, log
        self.dead = threading.Event()
        self.busy_since = None  # start time of the current write
        self.wdev = open_keyboard()
        if self.wdev is None:
            raise OSError("keyboard not found")
        self.rdev = open_keyboard()
        threading.Thread(target=self._writer, daemon=True).start()
        if self.rdev is not None:
            threading.Thread(target=self._reader, daemon=True).start()

    def send(self, payloads):
        for p in payloads:
            try:
                self.queue.put_nowait(p)
            except Exception:
                break  # queue full: writing is stuck, stuck() will report it

    def stuck(self):
        b = self.busy_since
        return self.dead.is_set() or (b is not None and time.monotonic() - b > self.STUCK_S)

    def _writer(self):
        while not self.dead.is_set():
            payload = self.queue.get()
            if payload is None:
                return
            self.busy_since = time.monotonic()
            try:
                # Windows/hidapi: the first byte is the report number (0 = no number).
                if self.wdev.write(b"\x00" + payload) < 0:
                    raise OSError("write failed")
            except Exception as e:
                self.log(f"write: {e}")
                self.dead.set()
                return
            self.busy_since = None

    def _reader(self):
        while not self.dead.is_set():
            try:
                data = self.rdev.read(64, 500)
            except Exception as e:
                self.log(f"read: {e}")
                return  # without reading there is no quick launch, but sending carries on
            if data and len(data) >= 3 and data[0] == MAGIC and data[1] == LAUNCH:
                try:
                    self.on_launch(data[2])
                except Exception as e:
                    self.log(f"launch: {e}")

    def close(self):
        """Closes without waiting (the handle is closed in its own thread, because that can hang too)."""
        self.dead.set()
        try:
            self.queue.put_nowait(None)
        except Exception:
            pass

        def _close():
            for d in (self.wdev, self.rdev):
                try:
                    d and d.close()
                except Exception:
                    pass
        threading.Thread(target=_close, daemon=True).start()


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
        """New settings from the window (the app list is sent right away)."""
        self.config = copy.deepcopy(cfg)
        self.config_version += 1

    def _launch(self, index):
        apps = self.config.get("apps", [])
        if index < len(apps):
            self.launches += 1
            launch_app(apps[index], self.log)

    def run(self):
        volume = Volume()
        net = NetRate()
        media = MediaProcess()
        notes = Notifications()
        new_notes = []
        notes_bg = Background(lambda: new_notes.extend(notes.read()) if self.config["data"].get("notifications") else None,
                              every=2.0)
        icon_cache = {}
        sent_version = -1
        link = None
        try:
            import psutil
            psutil.cpu_percent(interval=None)  # the first reading is always 0
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
            if on.get("notifications"):
                while new_notes:
                    app, title, body = new_notes.pop(0)
                    payloads += notes.frames(app, title, body)
                    data["notif"] = to_ascii(app)
            else:
                notes.seen = None  # after enabling, don't send old ones
                new_notes.clear()
            # app list: after a change, after connecting and every 20 s
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
                if link is not None and link.stuck():
                    self.log("hid: link stuck or lost, reconnecting")
                    link.close()
                    link = None
                if link is None:
                    try:
                        link = HidLink(self._launch, self.log)
                        self.status = "connected"
                        payloads += app_frames(self.config.get("apps", []), icon_cache)
                    except Exception:
                        self.status = "keyboard not found"
                    self.log(self.status)
                if link is not None:
                    link.send(payloads)
                    self.last_line = fmt(data)
                    self.log(self.last_line)
            self.stop_event.wait(1.0)
        if link is not None:
            link.close()

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
    if "--media-child" in sys.argv:
        media_child()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--console", action="store_true", help="no tray icon, prints the data")
    ap.add_argument("--dry-run", action="store_true", help="only read the data, no keyboard")
    ap.add_argument("--no-notifications", action="store_true", help="don't send Windows notifications to the screen")
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
        print("pystray is not installed: running in the console (Ctrl+C quits).")
        sender.console = True
        try:
            while sender.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            sender.stop_event.set()


if __name__ == "__main__":
    main()
