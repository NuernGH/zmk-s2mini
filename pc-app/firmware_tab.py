"""
"Firmware" page: update the keyboard firmware with one button, without the 0 + RST buttons.

1. Downloads firmware/s2mini_60-0x0.bin and SHA256SUMS from the repo (or takes a local .bin)
   and checks the checksum.
2. Sends the Raw HID command [0x53, 0x07, "BOOT"]: the keyboard restarts into the ESP32-S2 ROM
   bootloader (USB 303A:0002). The same as SETTINGS -> Update FW (push twice) on the keyboard.
3. Waits for the bootloader COM port and flashes with esptool (write-flash 0x0, without erasing
   the whole flash, so keymap changes saved from Studio stay).
4. Restarts the board (watchdog reset). If the keyboard does not come back, unplug and replug USB.

SPDX-License-Identifier: MIT
"""

import contextlib
import hashlib
import io
import os
import tempfile
import threading
import time
import urllib.request
from tkinter import filedialog

import customtkinter as ctk

from i18n import tr

REPO_FIRMWARE = "https://raw.githubusercontent.com/NuernGH/zmk-s2mini/HEAD/firmware/"
IMAGE = "s2mini_60-0x0.bin"
BOOT_VID, BOOT_PID = 0x303A, 0x0002
BOOT_FRAME = bytes([0x53, 0x07]) + b"BOOT" + bytes(26)

CARD = "#171a21"
CARD_HI = "#1e232c"
MUTED = "#8a93a3"


def download_image(base=REPO_FIRMWARE, log=print):
    """Image from the repo, checked against SHA256SUMS. Returns (path, sha256)."""
    def get(name):
        url = base + name + "?t=%d" % int(time.time())  # no cached copy
        req = urllib.request.Request(url, headers={"User-Agent": "S2mini60-updater"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    sums = get("SHA256SUMS").decode("ascii", "replace")
    want = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == IMAGE:
            want = parts[0].lower()
    if not want:
        raise RuntimeError(tr("SHA256SUMS has no entry for {f}", f=IMAGE))
    data = get(IMAGE)
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise RuntimeError(tr("checksum does not match (download damaged?)"))
    path = os.path.join(tempfile.gettempdir(), "S2mini60-" + IMAGE)
    with open(path, "wb") as f:
        f.write(data)
    log(tr("Downloaded {n} KB, SHA256 {h}… OK", n=len(data) // 1024, h=got[:12]))
    return path, got


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def bootloader_port():
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            if p.vid == BOOT_VID and p.pid == BOOT_PID:
                return p.device
    except Exception:
        pass
    return None


def wait_port(timeout, log):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        port = bootloader_port()
        if port:
            return port
        time.sleep(0.3)
    return None


def run_esptool(args, log):
    import esptool

    class Out(io.TextIOBase):
        def __init__(self):
            self.buf = ""

        def write(self, s):
            self.buf += s
            while "\n" in self.buf or "\r" in self.buf:
                i = min(x for x in (self.buf.find("\n"), self.buf.find("\r")) if x >= 0)
                line, self.buf = self.buf[:i].strip(), self.buf[i + 1:]
                if line:
                    log(line)
            return len(s)

    out = Out()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            esptool.main(args)
        except SystemExit as e:
            if e.code not in (0, None):
                raise RuntimeError(f"esptool: exit {e.code}")


def update(sender, image, log):
    """The whole update (call in a thread). image: local .bin path or None = download from the repo."""
    if image is None:
        log(tr("Downloading firmware from GitHub…"))
        image, sha = download_image(log=log)
    else:
        sha = file_sha(image)
        log(tr("File {f}, SHA256 {h}…", f=os.path.basename(image), h=sha[:12]))

    port = bootloader_port()
    if port:
        log(tr("The keyboard is already in the bootloader ({p}).", p=port))
    else:
        if not sender.send_raw(BOOT_FRAME):
            raise RuntimeError(tr("The keyboard is not connected (Raw HID). Connect it, or enter the "
                                  "bootloader with 0 + RST and press the button again."))
        log(tr("Keyboard restarting into the bootloader…"))
        port = wait_port(15, log)
        if not port:
            raise RuntimeError(tr("No bootloader port (303A:0002) after 15 s. Old firmware without this "
                                  "option? Hold 0, press RST and press the button again."))
    log(tr("Bootloader on {p}. Flashing…", p=port))
    time.sleep(0.5)
    run_esptool(["--chip", "esp32s2", "--port", port, "--before", "no-reset",
                 "--after", "watchdog-reset", "write-flash", "0x0", image], log)
    log(tr("Done. The keyboard is restarting; if it does not come back in a few seconds, "
           "unplug and replug USB."))


class FirmwarePage(ctk.CTkFrame):
    def __init__(self, master, header, sender):
        super().__init__(master, fg_color="transparent")
        self.sender = sender
        header(self, tr("Firmware"),
               tr("Update the keyboard firmware without the 0 + RST buttons. On the keyboard itself:\n"
                  "SETTINGS view → Update FW, push the knob twice (then flash with this page or esptool)."))
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        card.pack(fill="x")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=12)
        self.btn = ctk.CTkButton(row, text=tr("Update firmware (latest from GitHub)"), command=self.start_repo)
        self.btn.pack(side="left")
        self.btn_file = ctk.CTkButton(row, text=tr("From file…"), fg_color=CARD_HI, command=self.start_file)
        self.btn_file.pack(side="left", padx=8)
        ctk.CTkLabel(card, text=tr("Keymap changes saved from Studio stay (the whole flash is not erased)."),
                     text_color=MUTED).pack(anchor="w", padx=18, pady=(0, 12))
        self.out = ctk.CTkTextbox(self, fg_color=CARD, corner_radius=12,
                                  font=ctk.CTkFont(family="Consolas", size=12))
        self.out.pack(fill="both", expand=True, pady=(14, 0))
        self.running = False

    def log(self, text):
        self.after(0, lambda: (self.out.insert("end", text + "\n"), self.out.see("end")))

    def start_repo(self):
        self._start(None)

    def start_file(self):
        path = filedialog.askopenfilename(title=tr("Firmware image (flash at 0x0)"),
                                          filetypes=[("bin", "*.bin"), ("*", "*.*")])
        if path:
            self._start(path)

    def _start(self, image):
        if self.running:
            return
        self.running = True
        self.btn.configure(state="disabled")
        self.btn_file.configure(state="disabled")
        self.out.delete("1.0", "end")

        def work():
            try:
                update(self.sender, image, self.log)
            except Exception as e:
                self.log(tr("ERROR: {e}", e=e))
            finally:
                self.after(0, self._done)
        threading.Thread(target=work, daemon=True).start()

    def _done(self):
        self.running = False
        self.btn.configure(state="normal")
        self.btn_file.configure(state="normal")
