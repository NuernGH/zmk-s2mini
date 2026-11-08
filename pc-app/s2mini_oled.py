"""
Wysyła dane z PC na ekran klawiatury S2 mini 60 (ZMK, Raw HID):
głośność, obciążenie i temperatura CPU/GPU, godzina (raz na sekundę)
oraz listę podłączonych portów COM (co 2 s).

Źródła danych (Windows):
- głośność: pycaw (domyślne wyjście audio),
- CPU/GPU: LibreHardwareMonitor z włączonym „Remote Web Server” (http://localhost:8085),
  a bez niego obciążenie CPU z psutil i GPU NVIDIA z nvidia-smi (bez temperatury CPU),
- godzina: zegar systemu,
- porty COM: pyserial (nazwy znanych płytek po VID:PID).

Uruchomienie:  pythonw s2mini_oled.py          (ikona w zasobniku, gdy jest pystray)
               python  s2mini_oled.py --console (wypisuje wysyłane dane)
               python  s2mini_oled.py --dry-run  (bez klawiatury, tylko odczyt danych)

SPDX-License-Identifier: MIT
"""

import argparse
import json
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
MAGIC, VERSION, PORTS = 0x53, 0x01, 0x02
PORT_TEXT = 28
F_CPU, F_GPU, F_VOLUME, F_TIME, F_MUTED, F_IGPU = 1, 2, 4, 8, 16, 32

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


def collect(volume, warn=print):
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
    data["volume"], data["muted"] = volume.read()
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
    def __init__(self, console=False, dry_run=False):
        super().__init__(daemon=True)
        self.console, self.dry_run = console, dry_run
        self.stop_event = threading.Event()
        self.status = "starting"

    def log(self, *a):
        if self.console:
            print(*a, flush=True)

    def run(self):
        volume = Volume()
        dev = None
        try:
            import psutil
            psutil.cpu_percent(interval=None)  # pierwszy odczyt zawsze 0
        except Exception:
            pass
        tick = 0
        while not self.stop_event.is_set():
            data = collect(volume)
            payloads = [frame(data)]
            if tick % 2 == 0:
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
                        # Windows/hidapi: pierwszy bajt to numer raportu (0 = bez numeru).
                        for payload in payloads:
                            if dev.write(b"\x00" + payload) < 0:
                                raise OSError("write failed")
                        self.log(fmt(data))
                except Exception as e:
                    self.status = f"error: {e}"
                    self.log(self.status)
                    try:
                        dev and dev.close()
                    except Exception:
                        pass
                    dev = None
            self.stop_event.wait(1.0)


def fmt(d):
    f = lambda v, u: "--" if v is None else f"{v:.0f}{u}"
    return (f"{time.strftime('%H:%M:%S', d['time'])}  CPU {f(d['cpu_load'], '%')} {f(d['cpu_temp'], '°C')}"
            f"  GPU {f(d['gpu_load'], '%')} {f(d['gpu_temp'], '°C')}"
            f"  iGPU {f(d.get('igpu_load'), '%')}"
            f"  VOL {'mute' if d['muted'] else f(d['volume'], '%')}"
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
    args = ap.parse_args()

    sender = Sender(console=args.console or args.dry_run, dry_run=args.dry_run)
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
