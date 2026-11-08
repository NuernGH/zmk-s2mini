"""Tylko odczyt: sprawdza połączenie ZMK Studio (info, blokada, warstwy, układ, akcje)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import zmk_studio as z

port = sys.argv[1] if len(sys.argv) > 1 else z.find_port()
print("port", port)
s = z.Studio(port)
print("info", s.device_info())
print("locked", s.locked())
try:
    km = s.keymap()
    print("layers", [(l["id"], l["name"], len(l["bindings"])) for l in km["layers"]], "available", km["available_layers"])
    print("layer0 first 16", km["layers"][0]["bindings"][:16])
    pl = s.physical_layouts()
    print("layouts", [(l["name"], len(l["keys"])) for l in pl["layouts"]], "active", pl["active"])
    print("keys 0..3", pl["layouts"][pl["active"]]["keys"][:4])
    for b in s.behaviors():
        print("behavior", b["id"], b["name"], b["metadata"])
    print("unsaved", s.unsaved())
except z.StudioError as e:
    print("ERR", e)
s.close()
