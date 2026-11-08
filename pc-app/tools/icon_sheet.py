"""Arkusz porównania stylów ikon: python tools/icon_sheet.py wynik.png [--start-menu [filtr ...]]"""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from PIL import Image, ImageDraw, ImageFont
import icons, math
def chrome():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im)
    d.pieslice([2,2,62,62],-150,-30,fill=(219,68,55,255)); d.pieslice([2,2,62,62],-30,90,fill=(244,180,0,255)); d.pieslice([2,2,62,62],90,210,fill=(15,157,88,255))
    d.ellipse([18,18,46,46],fill=(255,255,255,255)); d.ellipse([22,22,42,42],fill=(66,133,244,255)); return im
def spotify():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im); d.ellipse([2,2,62,62],fill=(30,215,96,255))
    for i,(y,w) in enumerate([(20,40),(31,34),(41,28)]): d.arc([32-w//2-6,y,32+w//2+6,y+24],200,340,fill=(0,0,0,255),width=5-i)
    return im
def discord():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im); d.rounded_rectangle([4,12,60,52],18,fill=(88,101,242,255))
    d.ellipse([18,26,28,38],fill=(255,255,255,255)); d.ellipse([36,26,46,38],fill=(255,255,255,255)); return im
def vscode():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im); d.polygon([(44,4),(60,12),(60,52),(44,60),(14,34),(6,40),(2,36),(2,28),(6,24),(14,30)],fill=(0,122,204,255))
    d.polygon([(44,16),(44,48),(24,32)],fill=(31,156,240,255)); return im
def steam():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im); d.ellipse([2,2,62,62],fill=(23,26,33,255))
    d.ellipse([34,12,52,30],outline=(255,255,255,255),width=4); d.line([(14,46),(38,26)],fill=(255,255,255,255),width=6); d.ellipse([10,40,24,54],fill=(255,255,255,255)); return im
def firefox():
    im=Image.new("RGBA",(64,64)); d=ImageDraw.Draw(im); d.ellipse([4,4,60,60],fill=(255,149,0,255)); d.ellipse([14,12,52,50],fill=(120,40,200,255)); d.pieslice([4,4,60,60],120,250,fill=(255,80,40,255)); d.polygon([(8,20),(20,4),(26,18)],fill=(255,200,40,255)); return im
srcs=[("Chrome",chrome()),("Spotify",spotify()),("Discord",discord()),("VS Code",vscode()),("Steam",steam()),("Firefox",firefox())]
if len(sys.argv)>2 and sys.argv[2]=="--start-menu":
    # pierwsze N skrótów z menu Start (ikony prawdziwych aplikacji z tego PC)
    from s2mini_app import start_menu_shortcuts
    want=[w.lower() for w in sys.argv[3:]]
    items=start_menu_shortcuts()
    if want: items=[i for i in items if any(w in i[0].lower() for w in want)]
    srcs=[(n[:12], icons.extract_icon(p)) for n,p in items[:10]]
elif len(sys.argv)>2:
    srcs=[(n, icons.extract_icon(p)) for n,p in zip(sys.argv[2::2], sys.argv[3::2])]
styles=["source"]+list(icons.STYLES)
cell=110; W=cell*len(styles)+90; H=cell*len(srcs)+40
sheet=Image.new("RGB",(W,H),(24,26,32)); d=ImageDraw.Draw(sheet)
try:
    F=ImageFont.truetype("DejaVuSans.ttf",13)
except Exception:
    F=None
for j,s in enumerate(styles): d.text((90+j*cell+4,10),"oryginal" if s=="source" else icons.STYLE_NAMES[s],fill=(220,220,220),font=F)
for i,(n,src) in enumerate(srcs):
    d.text((6,40+i*cell+40),n,fill=(220,220,220),font=F)
    for j,s in enumerate(styles):
        x,y=90+j*cell,32+i*cell
        if s=="source":
            if src: sheet.paste(src.resize((96,96)),(x,y),src.resize((96,96)))
        else: sheet.paste(icons.preview(icons.to_keyboard(src,s),3),(x,y))
sheet.save(sys.argv[1])
