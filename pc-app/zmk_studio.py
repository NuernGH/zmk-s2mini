"""ZMK Studio client (RPC over the keyboard's COM port), without external protobuf libraries.

Frame: 0xAB, message bytes (0xAB/0xAC/0xAD prefixed with 0xAC), 0xAD.
Messages follow zmk-studio-messages (studio.proto, core/keymap/behaviors.proto).
"""

import threading
import time

SOF, ESC, EOF = 0xAB, 0xAC, 0xAD
ZMK_VID, ZMK_PID = 0x1D50, 0x615E


# ---------- minimal protobuf ----------

def _varint(n):
    n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _zigzag(n):
    return (n << 1) ^ (n >> 31)


def _unzigzag(n):
    return (n >> 1) ^ -(n & 1)


def f_int(field, value):
    return _varint(field << 3) + _varint(value)


def f_sint(field, value):
    return _varint(field << 3) + _varint(_zigzag(value))


def f_bytes(field, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return _varint((field << 3) | 2) + _varint(len(data)) + data


def parse(buf):
    """bytes -> {field: [values]}; varint as int, length-delimited as bytes."""
    out, i = {}, 0
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(buf, i)
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            v, i = bytes(buf[i:i + ln]), i + ln
        elif wt == 5:
            v, i = int.from_bytes(buf[i:i + 4], "little"), i + 4
        elif wt == 1:
            v, i = int.from_bytes(buf[i:i + 8], "little"), i + 8
        else:
            raise ValueError("bad wire type")
        out.setdefault(field, []).append(v)
    return out


def _read_varint(buf, i):
    n = shift = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7


def one(msg, field, default=None):
    v = msg.get(field)
    return v[0] if v else default


def i32(n):
    """uint64 from a varint -> int32 (negative int32 fields are encoded in 10 bytes)."""
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


# ---------- frames ----------

def frame(payload):
    out = bytearray([SOF])
    for b in payload:
        if b in (SOF, ESC, EOF):
            out.append(ESC)
        out.append(b)
    out.append(EOF)
    return bytes(out)


class Deframer:
    def __init__(self):
        self.buf, self.inside, self.esc = bytearray(), False, False

    def feed(self, data):
        msgs = []
        for b in data:
            if self.esc:
                self.buf.append(b)
                self.esc = False
            elif b == SOF:
                self.buf, self.inside = bytearray(), True
            elif not self.inside:
                continue
            elif b == ESC:
                self.esc = True
            elif b == EOF:
                msgs.append(bytes(self.buf))
                self.inside = False
            else:
                self.buf.append(b)
        return msgs


# ---------- data ----------

class StudioError(Exception):
    pass


META_ERRORS = {0: "general error", 1: "keyboard is locked", 2: "unknown request",
               3: "decode error", 4: "encode error"}


def _binding(raw):
    m = parse(raw)
    return (_unzigzag(one(m, 1, 0)), one(m, 2, 0), one(m, 3, 0))


def _layer(raw):
    m = parse(raw)
    return {"id": one(m, 1, 0), "name": one(m, 2, b"").decode("utf-8", "replace"),
            "bindings": [_binding(b) for b in m.get(3, [])]}


def _keymap(raw):
    m = parse(raw)
    return {"layers": [_layer(x) for x in m.get(1, [])], "available_layers": one(m, 2, 0),
            "max_name": one(m, 3, 0)}


def _param_desc(raw):
    m = parse(raw)
    d = {"name": one(m, 1, b"").decode("utf-8", "replace")}
    if 2 in m:
        d["type"] = "nil"
    elif 3 in m:
        d["type"], d["value"] = "constant", i32(one(m, 3))
    elif 4 in m:
        r = parse(one(m, 4))
        d["type"], d["min"], d["max"] = "range", i32(one(r, 1, 0)), i32(one(r, 2, 0))
    elif 5 in m:
        h = parse(one(m, 5))
        d["type"], d["keyboard_max"], d["consumer_max"] = "hid", one(h, 1, 0), one(h, 2, 0)
    elif 6 in m:
        d["type"] = "layer"
    else:
        d["type"] = "nil"
    return d


def _behavior(raw):
    m = parse(raw)
    sets = []
    for s in m.get(3, []):
        p = parse(s)
        sets.append({"param1": [_param_desc(x) for x in p.get(1, [])],
                     "param2": [_param_desc(x) for x in p.get(2, [])]})
    return {"id": one(m, 1, 0), "name": one(m, 2, b"").decode("utf-8", "replace"), "metadata": sets}


def _layouts(raw):
    m = parse(raw)
    layouts = []
    for lr in m.get(2, []):
        lm = parse(lr)
        keys = []
        for kr in lm.get(2, []):
            k = parse(kr)
            g = lambda f: _unzigzag(one(k, f, 0))
            keys.append({"w": g(1), "h": g(2), "x": g(3), "y": g(4), "r": g(5), "rx": g(6), "ry": g(7)})
        layouts.append({"name": one(lm, 1, b"").decode("utf-8", "replace"), "keys": keys})
    return {"active": one(m, 1, 0), "layouts": layouts}


# ---------- connection ----------

def find_port():
    """COM port of the ZMK keyboard (1D50:615E) or None."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    for p in list_ports.comports():
        if p.vid == ZMK_VID and p.pid == ZMK_PID:
            return p.device
    return None


class Studio:
    CORE, BEHAVIORS, KEYMAP = 3, 4, 5

    def __init__(self, port, timeout=3.0):
        import serial
        self.ser = serial.Serial(port, 115200, timeout=0.1)
        self.timeout = timeout
        self.next_id = 1
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.responses = {}
        self.on_notification = None  # fn(dict)
        self.closed = False
        self.deframer = Deframer()
        threading.Thread(target=self._reader, daemon=True).start()

    def close(self):
        self.closed = True
        try:
            self.ser.close()
        except Exception:
            pass

    def _reader(self):
        while not self.closed:
            try:
                data = self.ser.read(256)
            except Exception:
                self.closed = True
                with self.cond:
                    self.cond.notify_all()
                return
            for msg in self.deframer.feed(data):
                self._handle(msg)

    def _handle(self, msg):
        try:
            m = parse(msg)
        except Exception:
            return
        if 1 in m:
            rr = parse(one(m, 1))
            with self.cond:
                self.responses[one(rr, 1, 0)] = rr
                self.cond.notify_all()
        elif 2 in m and self.on_notification:
            n = parse(one(m, 2))
            note = {}
            if 2 in n:
                c = parse(one(n, 2))
                if 1 in c:
                    note["lock_state"] = one(c, 1)
            if 5 in n:
                k = parse(one(n, 5))
                if 1 in k:
                    note["unsaved"] = bool(one(k, 1))
            try:
                self.on_notification(note)
            except Exception:
                pass

    def _call(self, subsystem, request):
        """Sends a Request and returns the subsystem's response bytes (that subsystem's Response)."""
        with self.lock:
            rid = self.next_id
            self.next_id += 1
            self.ser.write(frame(f_int(1, rid) + f_bytes(subsystem, request)))
        end = time.monotonic() + self.timeout
        with self.cond:
            while rid not in self.responses:
                if self.closed:
                    raise StudioError("connection closed")
                left = end - time.monotonic()
                if left <= 0:
                    raise StudioError("no response from keyboard")
                self.cond.wait(left)
            rr = self.responses.pop(rid)
        if 2 in rr:
            meta = parse(one(rr, 2))
            if 2 in meta:
                code = one(meta, 2)
                raise StudioError(META_ERRORS.get(code, f"error {code}"))
            raise StudioError("no response")
        if subsystem not in rr:
            raise StudioError("unexpected response")
        return parse(one(rr, subsystem))

    # core
    def device_info(self):
        r = parse(one(self._call(self.CORE, f_int(1, 1)), 1))
        return {"name": one(r, 1, b"").decode("utf-8", "replace"), "serial": one(r, 2, b"").hex()}

    def locked(self):
        return one(self._call(self.CORE, f_int(2, 1)), 2, 0) == 0

    def lock(self):
        self._call(self.CORE, f_int(3, 1))

    # behaviors
    def behaviors(self):
        ids = []
        lst = parse(one(self._call(self.BEHAVIORS, f_int(1, 1)), 1, b""))
        for v in lst.get(1, []):
            if isinstance(v, bytes):  # packed repeated
                i = 0
                while i < len(v):
                    n, i = _read_varint(v, i)
                    ids.append(n)
            else:
                ids.append(v)
        out = []
        for bid in ids:
            r = self._call(self.BEHAVIORS, f_bytes(2, f_int(1, bid)))
            out.append(_behavior(one(r, 2, b"")))
        return out

    # keymap
    def keymap(self):
        return _keymap(one(self._call(self.KEYMAP, f_int(1, 1)), 1, b""))

    def physical_layouts(self):
        return _layouts(one(self._call(self.KEYMAP, f_int(6, 1)), 6, b""))

    def set_binding(self, layer_id, position, behavior_id, p1=0, p2=0):
        b = f_sint(1, behavior_id) + f_int(2, p1) + f_int(3, p2)
        req = f_int(1, layer_id) + f_int(2, position) + f_bytes(3, b)
        code = one(self._call(self.KEYMAP, f_bytes(2, req)), 2, 0)
        if code:
            raise StudioError({1: "invalid position", 2: "invalid action", 3: "invalid parameters"}.get(code, f"error {code}"))

    def unsaved(self):
        return bool(one(self._call(self.KEYMAP, f_int(3, 1)), 3, 0))

    def save(self):
        r = parse(one(self._call(self.KEYMAP, f_int(4, 1)), 4, b""))
        if 2 in r and one(r, 2):
            raise StudioError({2: "saving not supported", 3: "no space left"}.get(one(r, 2), "save error"))

    def discard(self):
        self._call(self.KEYMAP, f_int(5, 1))

    def set_layer_name(self, layer_id, name):
        code = one(self._call(self.KEYMAP, f_bytes(12, f_int(1, layer_id) + f_bytes(2, name))), 12, 0)
        if code:
            raise StudioError("could not rename layer")

    def add_layer(self):
        r = parse(one(self._call(self.KEYMAP, f_bytes(9, b"")), 9, b""))
        if 2 in r and one(r, 2):
            raise StudioError("no space for another layer" if one(r, 2) == 2 else "could not add layer")
        d = parse(one(r, 1, b""))
        return one(d, 1, 0), _layer(one(d, 2, b""))

    def remove_layer(self, index):
        r = parse(one(self._call(self.KEYMAP, f_bytes(10, f_int(1, index))), 10, b""))
        if 2 in r and one(r, 2):
            raise StudioError("could not remove layer")

    def move_layer(self, start, dest):
        r = parse(one(self._call(self.KEYMAP, f_bytes(8, f_int(1, start) + f_int(2, dest))), 8, b""))
        if 2 in r and one(r, 2):
            raise StudioError("could not move layer")
        return _keymap(one(r, 1, b""))
