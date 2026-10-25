"""Character art for "Sindhi Ghar Ki Kahani".
All drawing is done in 'units' (a seated adult head is ~232 units wide) and super-sampled.
Heads: base (cached per character) + expression features (cached per state)."""
import math
import numpy as np
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFilter

OUT = (42, 28, 32)
K = 1.5          # world px per design unit (set by engine)
SS = 2.0         # super-sampling factor


def setK(k):
    global K
    K = k


def outline(img, px):
    a = img.getchannel("A")
    for _ in range(max(1, px // 2)):
        a = a.filter(ImageFilter.MaxFilter(5))
    o = Image.new("RGBA", img.size, OUT + (0,))
    o.putalpha(a)
    o.alpha_composite(img)
    return o


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


# ----------------------------------------------------------------- characters
SK1, SK2, SK3 = (214, 160, 118), (230, 180, 142), (198, 146, 104)
CHARS = {
    "ABBA": dict(name="Abba", age="old_man", skin=SK3, face="oval", hair="topi", hair_col=(200, 200, 205),
                 facial="mustache", fh_col=(215, 215, 218), wrinkles=2, shirt=(236, 230, 212), pants=(236, 230, 212),
                 collar="band", extra=["ajrak"], sleeve="long", scale=1.0, belly=True, brow_col=(190, 190, 195),
                 color="#ffcf6b", voice="Charon",
                 who="a 57-year-old Sindhi father, government office clerk, serious, slow and wise, deep warm voice"),
    "AMMI": dict(name="Ammi", age="old_woman", skin=SK2, face="round", hair="dupatta", hair_col=(40, 30, 28),
                 grey_streak=True, cover=(128, 32, 52), cover2=(170, 60, 80), wrinkles=1, shirt=(214, 120, 70),
                 pants=(214, 120, 70), collar="women", sleeve="long", scale=0.95, lashes=True, color="#ff9f80",
                 voice="Kore", who="a 50-year-old Sindhi mother and housewife, caring but strict, quick and expressive"),
    "IMTIAZ": dict(name="Ada Imtiaz", age="man", skin=SK1, face="long", hair="side", hair_col=(26, 22, 22),
                   facial="beard", fh_col=(30, 24, 24), shirt=(110, 120, 135), pants=(60, 64, 80), collar="polo",
                   sleeve="short", scale=1.03, eyebags=True, color="#9fd0ff", voice="Orus",
                   who="a 29-year-old man, tired after work at a Chinese company, responsible elder brother, calm"),
    "SANA": dict(name="Bhabi Sana", age="woman", skin=SK2, face="oval", hair="dupatta", hair_col=(30, 20, 18),
                 cover=(46, 140, 100), cover2=(90, 190, 140), shirt=(250, 236, 214), pants=(250, 236, 214),
                 collar="women", sleeve="long", scale=0.94, lashes=True, earrings=True, color="#8ff0c0",
                 voice="Aoede", who="a 25-year-old educated young woman, polite, smart and witty"),
    "HAMZA": dict(name="Hamza", age="toddler", skin=SK2, face="toddler", hair="tuft", hair_col=(40, 28, 24),
                  shirt=(226, 70, 70), pants=(60, 90, 160), collar="tee", sleeve="short", scale=0.5, hs=1.45, color="#ff8080",
                  voice="Zephyr", toddler=True, who="a 2-year-old toddler boy who babbles half words, cute and giggly"),
    "HASHIR": dict(name="Hashir", age="toddler", skin=SK2, face="toddler", hair="tuft2", hair_col=(40, 28, 24),
                   shirt=(240, 200, 60), pants=(60, 90, 160), collar="tee", sleeve="short", scale=0.5, hs=1.45, color="#ffe066",
                   voice="Achird", toddler=True, who="a 2-year-old toddler boy who babbles half words, cheeky"),
    "FARAZ": dict(name="Faraz", age="man", skin=SK1, face="oval", hair="neat", hair_col=(24, 20, 20), glasses=True,
                  facial="light", fh_col=(40, 30, 28), shirt=(90, 140, 200), pants=(50, 55, 75), collar="band",
                  extra=["lanyard"], sleeve="long", scale=1.0, color="#7fc8ff", voice="Iapetus",
                  who="a 27-year-old computer science graduate, the tech guy of the house, clear and a bit nerdy"),
    "NIMRA": dict(name="Nimra Aapi", age="woman", skin=SK2, face="oval", hair="dupatta", hair_col=(34, 22, 20),
                  cover=(120, 60, 170), cover2=(170, 110, 220), shirt=(240, 200, 220), pants=(240, 200, 220),
                  collar="women", sleeve="long", scale=0.93, lashes=True, earrings=True, color="#d6a8ff",
                  voice="Despina", who="a 24-year-old married elder sister living in Karachi, loving but bossy"),
    "DANIYAL": dict(name="Daniyal", age="young", skin=SK1, face="long", hair="curly", hair_col=(30, 24, 22),
                    shirt=(245, 245, 245), pants=(40, 40, 48), collar="band", extra=["waistcoat"], sleeve="long",
                    scale=0.98, color="#c0c0ff", voice="Fenrir",
                    who="a 20-year-old law student, dramatic and theatrical, loves saying Objection"),
    "ARSALAN": dict(name="Arsalan", age="teen", skin=SK1, face="round", hair="spiky", hair_col=(22, 18, 18),
                    shirt=(30, 140, 70), shirt2=(240, 240, 240), pants=(30, 30, 40), collar="jersey", sleeve="short",
                    scale=0.95, color="#80e08a", voice="Puck",
                    who="a 17-year-old boy, cricket and mobile games lover, energetic, a bit lazy"),
    "MEHAK": dict(name="Mehak", age="girl", skin=SK2, face="round", hair="plaits", hair_col=(30, 20, 18),
                  shirt=(250, 150, 190), pants=(250, 150, 190), collar="women_print", sleeve="long", scale=0.84,
                  lashes=True, color="#ff9fc8", voice="Leda",
                  who="a 14-year-old girl in class 8, smart, talkative, loves teasing her brothers"),
}

# ----------------------------------------------------------------- expressions
EM = {  # (brow inner dy, outer dy), right brow override, eye open, smile, flags
    "neutral": ((0, 0), None, 1.0, 0.35, ""), "calm": ((-2, 0), None, 0.92, 0.5, ""),
    "happy": ((-6, -4), None, 0.86, 1.0, ""), "worried": ((-13, 6), None, 1.05, -0.45, ""),
    "surprised": ((-18, -15), None, 1.25, 0.0, "o"), "teasing": ((5, 0), (-15, -17), 0.7, 0.7, "smirk"),
    "sheepish": ((-11, 5), None, 0.92, 0.45, ""), "laugh": ((-9, -7), None, 0.0, 1.0, "laugh"),
    "warm": ((-6, -3), None, 0.8, 0.8, ""), "focused": ((5, 1), None, 0.9, 0.15, ""),
    "angry": ((12, -6), None, 0.95, -0.6, ""), "tired": ((-4, 4), None, 0.55, 0.0, ""),
    "proud": ((-4, -6), None, 0.75, 0.75, ""), "confused": ((-14, 2), (6, -2), 1.0, -0.1, "smirk"),
    "sad": ((-14, 8), None, 0.8, -0.6, ""),
}


class Toon:
    """All cached art for one character."""

    def __init__(self, key):
        self.key = key
        self.c = CHARS[key]
        self.cache = OrderedDict()
        self.base = self._head_base()
        self.blush = self._blush()
        self.body = self._body()

    # ---------------- head
    def _s(self, *v):
        return [int(q * SS * K) for q in v]

    def _canvas(self, w, h):
        return Image.new("RGBA", (int(w * SS * K), int(h * SS * K)), 0)

    def _head_base(self):
        c = self.c
        im = self._canvas(420, 480)
        d = ImageDraw.Draw(im)
        s = self._s
        cx, cy = 210, 250
        sk = c["skin"]
        dk = shade(sk, 0.8)
        hc = c["hair_col"]
        fw, fh = {"oval": (110, 136), "round": (118, 128), "long": (104, 142), "toddler": (124, 122)}[c["face"]]
        if c["hair"] == "dupatta":
            d.ellipse(s(cx - 132, 100, cx + 132, 380), fill=hc)
            d.rectangle(s(cx - 120, 240, cx + 120, 480), fill=hc)
            d.ellipse(s(cx - 154, 78, cx + 154, 400), fill=c["cover"])
            d.rectangle(s(cx - 154, 240, cx + 154, 480), fill=c["cover"])
        if c["hair"] == "plaits":
            for sd in (-1, 1):
                for k in range(5):
                    yy = 300 + k * 34
                    d.ellipse(s(cx + sd * 112 - 20, yy, cx + sd * 112 + 20, yy + 40), fill=hc, outline=shade(hc, 0.6))
        d.rectangle(s(cx - 36 if c["face"] != "toddler" else cx - 40, 330, cx + 36, 480), fill=dk)
        d.ellipse(s(cx - fw - 18, cy - 22, cx - fw + 16, cy + 42), fill=sk)
        d.ellipse(s(cx + fw - 16, cy - 22, cx + fw + 18, cy + 42), fill=sk)
        if c.get("earrings"):
            for sd in (-1, 1):
                d.ellipse(s(cx + sd * (fw + 1) - 7, cy + 40, cx + sd * (fw + 1) + 7, cy + 54), fill=(245, 200, 60))
        d.ellipse(s(cx - fw, cy - fh, cx + fw, cy + fh), fill=sk)
        if c.get("facial") == "beard":
            d.chord(s(cx - fw, cy - fh, cx + fw, cy + fh), 0, 180, fill=c["fh_col"])
            d.ellipse(s(cx - fw + 18, cy - fh, cx + fw - 18, cy + fh - 34), fill=sk)
        if c.get("facial") == "light":
            band = Image.new("RGBA", im.size, 0)
            ImageDraw.Draw(band).chord(s(cx - fw, cy - fh, cx + fw, cy + fh), 10, 170, fill=c["fh_col"] + (70,))
            ImageDraw.Draw(band).ellipse(s(cx - fw + 14, cy - fh, cx + fw - 14, cy + fh - 26), fill=(0, 0, 0, 0))
            im.alpha_composite(band)
            d = ImageDraw.Draw(im)
        h = c["hair"]
        if h == "side":
            d.chord(s(cx - fw - 8, cy - fh - 16, cx + fw + 8, cy + 50), 180, 360, fill=hc)
            d.polygon(s(cx - fw - 6, cy - 40, cx - 40, cy - 96, cx + 50, cy - 112, cx + fw + 6, cy - 50, cx + fw + 8, cy - 30,
                        cx + 30, cy - 70, cx - 60, cy - 66, cx - fw - 2, cy - 20), fill=hc)
        elif h == "neat":
            d.chord(s(cx - fw - 6, cy - fh - 14, cx + fw + 6, cy + 46), 180, 360, fill=hc)
            d.polygon(s(cx - fw - 4, cy - 44, cx - 70, cy - 82, cx + fw + 4, cy - 70, cx + fw + 6, cy - 36, cx - 50, cy - 64), fill=hc)
            d.line(s(cx - 40, cy - fh - 4, cx - 54, cy - 70), fill=shade(hc, 1.8), width=int(3 * SS * K))
        elif h == "curly":
            d.chord(s(cx - fw - 8, cy - fh - 10, cx + fw + 8, cy + 40), 180, 360, fill=hc)
            for k in range(11):
                a = math.pi + k * math.pi / 10
                x0, y0 = cx + (fw + 4) * math.cos(a), cy - 34 + (fh + 6) * math.sin(a) * 0.95
                d.ellipse(s(x0 - 26, y0 - 26, x0 + 26, y0 + 26), fill=hc)
        elif h == "spiky":
            d.chord(s(cx - fw - 6, cy - fh - 12, cx + fw + 6, cy + 50), 180, 360, fill=hc)
            pts = []
            for k in range(9):
                x0 = cx - fw - 4 + k * (2 * fw + 8) / 8
                pts += [(x0, cy - fh + 20 + (0 if k % 2 else 10)), (x0 + (2 * fw + 8) / 16, cy - fh - 34 - 10 * (k % 3))]
            d.polygon([q for p in pts for q in self._s(*p)] + s(cx + fw + 6, cy - 40, cx - fw - 6, cy - 40), fill=hc)
        elif h in ("tuft", "tuft2"):
            d.chord(s(cx - fw + 6, cy - fh - 4, cx + fw - 6, cy - 10), 180, 360, fill=hc)
            if h == "tuft":
                d.polygon(s(cx - 6, cy - fh, cx + 10, cy - fh - 44, cx + 22, cy - fh + 2), fill=hc)
            else:
                for dx in (-20, 0, 20):
                    d.arc(s(cx + dx - 14, cy - fh - 40, cx + dx + 14, cy - fh + 4), 200, 350, fill=hc, width=int(7 * SS * K))
        elif h == "topi":
            for sd in (-1, 1):
                d.ellipse(s(cx + sd * fw - 14, cy - 66, cx + sd * fw + 10, cy - 4), fill=hc)
            top, bot = cy - fh - 26, cy - 72
            d.rounded_rectangle(s(cx - fw - 8, top, cx + fw + 8, bot), int(14 * SS * K), fill=(178, 30, 40))
            for k in range(12):  # embroidery zig-zag + mirrors
                x0 = cx - fw + k * (2 * fw) / 11
                d.line(s(x0, bot - 10, x0 + 10, bot - 26, x0 + 20, bot - 10), fill=(250, 210, 60), width=int(4 * SS * K))
                d.ellipse(s(x0 + 4, top + 12, x0 + 14, top + 22), fill=(235, 240, 250))
            d.line(s(cx - fw - 6, bot - 4, cx + fw + 6, bot - 4), fill=(40, 120, 70), width=int(6 * SS * K))
            d.chord(s(cx - 30, bot - 30, cx + 30, bot + 30), 180, 360, fill=c["skin"])  # front cut-out of sindhi topi
            d.arc(s(cx - 30, bot - 30, cx + 30, bot + 30), 180, 360, fill=(40, 120, 70), width=int(5 * SS * K))
        elif h == "dupatta":
            d.chord(s(cx - fw - 4, cy - fh - 10, cx + fw + 4, cy + 30), 180, 360, fill=hc)
            d.line(s(cx, cy - fh - 6, cx + 6, cy - 98), fill=shade(hc, 1.8), width=int(4 * SS * K))
            if c.get("grey_streak"):
                d.arc(s(cx - fw + 6, cy - fh, cx + 40, cy + 20), 200, 260, fill=(200, 200, 205), width=int(10 * SS * K))
            d.arc(s(cx - fw - 42, cy - fh - 46, cx + fw + 42, cy + 152), 188, 352, fill=c["cover"], width=int(38 * SS * K))
            d.arc(s(cx - fw - 42, cy - fh - 46, cx + fw + 42, cy + 152), 198, 342, fill=c["cover2"], width=int(6 * SS * K))
        elif h == "plaits":
            d.chord(s(cx - fw - 6, cy - fh - 10, cx + fw + 6, cy + 30), 180, 360, fill=hc)
            d.line(s(cx, cy - fh - 6, cx + 4, cy - 96), fill=shade(hc, 1.8), width=int(4 * SS * K))
            d.ellipse(s(cx + 50, cy - fh + 4, cx + 84, cy - fh + 26), fill=(250, 120, 170))  # hair clip
        mask = im.getchannel("A")
        sh_ = Image.new("RGBA", im.size, 0)
        ImageDraw.Draw(sh_).ellipse(s(cx + fw * 0.35, cy - fh, cx + fw * 1.6, cy + fh * 1.2), fill=(30, 10, 30, 34))
        sh_ = sh_.filter(ImageFilter.GaussianBlur(int(18 * SS * K)))
        sh_.putalpha(Image.fromarray((np.asarray(sh_.getchannel("A")).astype(np.uint16) * np.asarray(mask) // 255).astype(np.uint8)))
        im.alpha_composite(sh_)
        return outline(im, int(6 * SS * K))

    def _blush(self):
        im = Image.new("RGBA", self.base.size, 0)
        d = ImageDraw.Draw(im)
        s = self._s
        a = 60 if self.c["age"] in ("man", "old_man", "young") else 85
        d.ellipse(s(110, 284, 160, 312), fill=(240, 120, 120, a))
        d.ellipse(s(260, 284, 310, 312), fill=(240, 120, 120, a))
        return im.filter(ImageFilter.GaussianBlur(int(7 * SS * K)))

    def head(self, emo, q, shape, blink, lx, ly):
        key = (emo, q, shape, blink, lx, ly)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        c = self.c
        im = self.base.copy()
        s = self._s
        W = lambda v: int(v * SS * K)
        (bi, bo), br2, eo, sm, fl = EM[emo]
        cx, cy = 210, 250
        fx, fy = lx * 9, ly * 5
        im.alpha_composite(self.blush, (int(fx * SS * K), 0))
        d = ImageDraw.Draw(im)
        eo = eo * (1, 0.45, 0.0)[blink] if "laugh" not in fl else 0
        tod = c.get("toddler")
        esz = 1.15 if tod else 1.0
        for side, ex in ((-1, cx - 48 + fx), (1, cx + 48 + fx)):
            ey = cy - 6 + fy + (10 if tod else 0)
            if "laugh" in fl:
                d.arc(s(ex - 24, ey - 18, ex + 24, ey + 16), 200, 340, fill=OUT, width=W(6))
            elif eo < 0.12:
                d.arc(s(ex - 24, ey - 14, ex + 24, ey + 10), 20, 160, fill=OUT, width=W(5))
            else:
                ry = 24 * eo * esz
                rx = 26 * esz
                d.ellipse(s(ex - rx, ey - ry, ex + rx, ey + ry * 0.85), fill=(255, 255, 255), outline=OUT, width=W(3))
                px, py = ex + lx * 10, ey + ly * 7 * min(eo, 1)
                ir = min(14 * esz, ry * 0.95)
                d.ellipse(s(px - ir, py - ir, px + ir, py + ir), fill=(70, 40, 24))
                d.ellipse(s(px - ir * 0.5, py - ir * 0.5, px + ir * 0.5, py + ir * 0.5), fill=(12, 8, 8))
                d.ellipse(s(px + 2, py - ir * 0.7, px + 7, py - ir * 0.7 + 5), fill=(255, 255, 255))
                if eo < 0.95:
                    d.chord(s(ex - rx - 1, ey - 25, ex + rx + 1, ey + 25 - 30 * eo), 180, 360, fill=c["skin"])
                d.arc(s(ex - rx - 1, ey - ry - 2, ex + rx + 1, ey + ry), 195, 345, fill=OUT, width=W(5))
                if c.get("lashes"):
                    d.line(s(ex + side * 25, ey - ry * 0.6, ex + side * 33, ey - ry * 0.6 - 8), fill=OUT, width=W(4))
                if c.get("eyebags"):
                    d.arc(s(ex - 20, ey + 6, ex + 20, ey + 26), 20, 160, fill=shade(c["skin"], 0.75), width=W(3))
            if c.get("wrinkles"):
                d.line(s(ex + side * 30, ey + 4, ex + side * 40, ey + 10), fill=shade(c["skin"], 0.72), width=W(3))
            bri, bro = (br2 if (br2 and side == 1) else (bi, bo))
            by = cy - 56 + fy
            bw = 7 if c["age"] in ("woman", "old_woman", "girl", "toddler") else 10
            d.line(s(ex - side * 24, by + bri, ex + side * 26, by + bro - 2), fill=c.get("brow_col", (36, 24, 20)), width=W(bw))
        if c.get("glasses"):
            for ex in (cx - 48 + fx, cx + 48 + fx):
                d.rounded_rectangle(s(ex - 34, cy - 34 + fy, ex + 34, cy + 22 + fy), W(12), outline=(30, 30, 40), width=W(6))
            d.line(s(cx - 14 + fx, cy - 12 + fy, cx + 14 + fx, cy - 12 + fy), fill=(30, 30, 40), width=W(5))
        if c.get("wrinkles", 0) >= 2:
            d.arc(s(cx - 60 + fx, cy - 112, cx + 60 + fx, cy - 84), 200, 340, fill=shade(c["skin"], 0.78), width=W(3))
        nz = shade(c["skin"], 0.78)
        d.line(s(cx + fx * 0.9, cy + 10 + fy, cx - 7 + fx * 0.9, cy + 40 + fy, cx + 5 + fx * 0.9, cy + 43 + fy), fill=nz, width=W(4))
        if c.get("wrinkles"):
            for sd in (-1, 1):
                d.arc(s(cx + sd * 40 - 22 + fx, cy + 34, cx + sd * 40 + 22 + fx, cy + 90), 90 - sd * 60 - 25, 90 - sd * 60 + 25, fill=nz, width=W(3))
        mx, my = cx + fx * 0.8, cy + 80 + fy * 0.6 + (-6 if tod else 0)
        if c.get("facial") == "mustache":
            d.polygon(s(mx - 46, my - 6, mx - 30, my - 22, mx, my - 18, mx + 30, my - 22, mx + 46, my - 6, mx, my - 12), fill=c["fh_col"], outline=OUT)
        RED, TEETH, TONGUE = (112, 28, 40), (252, 252, 252), (222, 96, 106)
        if "laugh" in fl:
            h = 34 + q * 3
            d.chord(s(mx - 46, my - h * 0.6, mx + 46, my + h), 0, 180, fill=RED, outline=OUT, width=W(3))
            d.rectangle(s(mx - 34, my + 2, mx + 34, my + 11), fill=TEETH)
            d.ellipse(s(mx - 18, my + h * 0.45, mx + 18, my + h * 0.95), fill=TONGUE)
        elif q == 0:
            if "o" in fl:
                d.ellipse(s(mx - 11, my - 6, mx + 11, my + 14), fill=RED, outline=OUT, width=W(3))
            elif "smirk" in fl:
                d.line(s(mx - 24, my + 2, mx + 4, my + 5, mx + 26, my - 8), fill=OUT, width=W(5), joint="curve")
            elif sm >= 0:
                wd, dp = 22 + 10 * sm, 4 + 12 * sm
                d.arc(s(mx - wd, my - dp - 4, mx + wd, my + dp), 15, 165, fill=OUT, width=W(5))
            else:
                d.arc(s(mx - 20, my + 2, mx + 20, my + 22), 200, 340, fill=OUT, width=W(5))
        else:
            h = [0, 10, 16, 22, 28, 34][q]
            wd = (34 if shape else 22) + 5 * max(sm, 0)
            if sm > 0.6 and shape:
                d.chord(s(mx - wd, my - h * 0.55, mx + wd, my + h * 0.9), 0, 180, fill=RED, outline=OUT, width=W(3))
                if q >= 2:
                    d.rectangle(s(mx - wd + 8, my - 1, mx + wd - 8, my + 6), fill=TEETH)
            else:
                d.ellipse(s(mx - wd, my - 6, mx + wd, my - 6 + h), fill=RED, outline=OUT, width=W(3))
                if shape and q >= 2:
                    d.rectangle(s(mx - wd + 8, my - 4, mx + wd - 8, my + 2), fill=TEETH)
            if q >= 3:
                d.ellipse(s(mx - 14, my - 6 + h - 13, mx + 14, my - 6 + h - 2), fill=TONGUE)
        out = im.resize((int(420 * K), int(480 * K)), Image.LANCZOS)
        self.cache[key] = out
        if len(self.cache) > 90:
            self.cache.popitem(last=False)
        return out

    # ---------------- body (torso sprite)
    def _body(self):
        c = self.c
        tod = c.get("toddler")
        im = self._canvas(520, 600)
        d = ImageDraw.Draw(im)
        s = self._s
        W = lambda v: int(v * SS * K)
        sh = c["shirt"]
        x0, x1 = (92, 428)
        if c.get("belly"):
            d.ellipse(s(110, 300, 410, 590), fill=sh)
        d.rounded_rectangle(s(x0, 40, x1, 560), W(100), fill=sh)
        col = c["collar"]
        if col == "band":
            d.rectangle(s(222, 40, 298, 62), fill=shade(sh, 0.9))
            d.line(s(260, 62, 260, 300), fill=shade(sh, 0.8), width=W(5))
            for y in (100, 160, 220):
                d.ellipse(s(254, y, 266, y + 12), fill=shade(sh, 0.7))
        elif col == "polo":
            d.polygon(s(260, 40, 200, 40, 232, 100), fill=shade(sh, 1.15))
            d.polygon(s(260, 40, 320, 40, 288, 100), fill=shade(sh, 1.15))
            d.line(s(260, 60, 260, 160), fill=shade(sh, 0.8), width=W(4))
            d.rectangle(s(318, 150, 372, 176), fill=(200, 40, 40))  # company logo
            d.text(s(324, 150), "", fill=(255, 255, 255))
        elif col == "jersey":
            d.polygon(s(220, 40, 300, 40, 260, 110), fill=c.get("shirt2", (255, 255, 255)))
            d.polygon(s(232, 40, 288, 40, 260, 92), fill=sh)
            for x in (92, 400):
                d.rectangle(s(x, 120, x + 28, 560), fill=c.get("shirt2", (255, 255, 255)))
            d.text(s(230, 200), "", fill=(255, 255, 255))
            d.ellipse(s(232, 180, 288, 236), fill=c.get("shirt2", (255, 255, 255)))
            d.ellipse(s(244, 192, 276, 224), fill=sh)
        elif col == "tee":
            d.chord(s(220, 20, 300, 70), 0, 180, fill=shade(c["skin"], 0.8))
            d.ellipse(s(230, 200, 290, 260), fill=(255, 255, 255))
            d.ellipse(s(246, 216, 274, 244), fill=(250, 200, 60))
        elif col in ("women", "women_print"):
            d.chord(s(214, 20, 306, 100), 0, 180, fill=shade(sh, 0.85))
            for k in range(7):
                a = math.pi * (0.1 + 0.8 * k / 6)
                d.ellipse(s(260 + 52 * math.cos(a) - 6, 60 + 52 * math.sin(a) - 6, 260 + 52 * math.cos(a) + 6, 60 + 52 * math.sin(a) + 6),
                          fill=(250, 210, 80))
            if col == "women_print":
                for k in range(18):
                    xx, yy = 120 + (k * 67) % 280, 150 + (k * 113) % 380
                    d.ellipse(s(xx, yy, xx + 16, yy + 16), fill=(255, 255, 255))
            if c.get("cover"):
                cv, cv2 = c["cover"], c["cover2"]
                d.polygon(s(92, 90, 196, 40, 182, 545, 100, 520), fill=cv)
                d.polygon(s(428, 90, 324, 40, 338, 545, 420, 520), fill=cv)
                d.line(s(196, 40, 182, 545), fill=cv2, width=W(5))
                d.line(s(324, 40, 338, 545), fill=cv2, width=W(5))
        ex = c.get("extra", [])
        if "ajrak" in ex:  # Sindhi ajrak shawl on shoulders
            for sd in (-1, 1):
                pts = s(260 + sd * 168, 70, 260 + sd * 90, 40, 260 + sd * 120, 330, 260 + sd * 168, 360)
                d.polygon(pts, fill=(150, 30, 40))
                for k in range(6):
                    yy = 70 + k * 46
                    xx = 260 + sd * (140 - k * 2)
                    d.rectangle(s(xx - 10, yy, xx + 10, yy + 20), fill=(30, 40, 90))
                    d.ellipse(s(xx - 4, yy + 6, xx + 4, yy + 14), fill=(240, 240, 240))
                d.line(s(260 + sd * 90, 40, 260 + sd * 120, 330), fill=(30, 40, 90), width=W(8))
        if "waistcoat" in ex:
            for sd in (-1, 1):
                d.polygon(s(260 + sd * 10, 70, 260 + sd * 70, 40, 260 + sd * 166, 110, 260 + sd * 166, 560, 260 + sd * 12, 560), fill=(30, 30, 40))
            for y in (240, 320, 400):
                d.ellipse(s(250, y, 262, y + 12), fill=(200, 180, 90))
        if "lanyard" in ex:
            d.line(s(220, 44, 250, 250, 270, 250, 300, 44), fill=(30, 110, 200), width=W(6))
            d.rounded_rectangle(s(232, 246, 288, 320), W(6), fill=(250, 250, 250), outline=(80, 80, 90), width=W(3))
            d.rectangle(s(240, 256, 262, 282), fill=(150, 180, 220))
        # cel shading: darker side + soft highlight, clipped to the clothes
        mask = im.getchannel("A")
        sh_ = Image.new("RGBA", im.size, 0)
        ImageDraw.Draw(sh_).polygon(s(330, 0, 560, 0, 560, 600, 360, 600), fill=(20, 10, 30, 46))
        sh_ = sh_.filter(ImageFilter.GaussianBlur(int(14 * SS * K)))
        hl_ = Image.new("RGBA", im.size, 0)
        ImageDraw.Draw(hl_).ellipse(s(120, 60, 230, 260), fill=(255, 255, 255, 30))
        hl_ = hl_.filter(ImageFilter.GaussianBlur(int(20 * SS * K)))
        for lay in (sh_, hl_):
            lay.putalpha(Image.fromarray((np.asarray(lay.getchannel("A")).astype(np.uint16) * np.asarray(mask) // 255).astype(np.uint8)))
            im.alpha_composite(lay)
        return outline(im, int(6 * SS * K)).resize((int(520 * K), int(600 * K)), Image.LANCZOS)


# ----------------------------------------------------------------- props held in hand
def draw_prop(d, name, q, hx, hy, s, t):
    """draw a prop held at (hx,hy) world units; q() maps world->canvas px; s = char scale"""
    lw = lambda v: max(1, int(v * K * s))
    P = lambda *pts: [c for i in range(0, len(pts), 2) for c in q(pts[i], pts[i + 1])]
    if name == "cup":
        d.rounded_rectangle(P(hx - 22 * s, hy - 60 * s, hx + 22 * s, hy - 10 * s), lw(7), fill=(250, 250, 250), outline=OUT, width=lw(4))
        d.ellipse(P(hx - 20 * s, hy - 66 * s, hx + 20 * s, hy - 54 * s), fill=(170, 100, 50))
        for j in range(2):
            d.line(P(*[v for k in range(6) for v in (hx - 8 * s + 14 * s * j + 6 * s * math.sin(t * 6 + k * 0.5 + j), hy - 72 * s - k * 9 * s)]),
                   fill=(255, 255, 255), width=lw(3))
    elif name == "phone":
        d.rounded_rectangle(P(hx - 20 * s, hy - 70 * s, hx + 20 * s, hy + 4 * s), lw(6), fill=(30, 30, 38), outline=OUT, width=lw(3))
        d.rectangle(P(hx - 15 * s, hy - 63 * s, hx + 15 * s, hy - 4 * s), fill=(120, 190, 250))
    elif name == "newspaper":
        d.rectangle(P(hx - 150 * s, hy - 170 * s, hx + 10 * s, hy + 20 * s), fill=(236, 234, 222), outline=OUT, width=lw(4))
        for k in range(8):
            d.line(P(hx - 136 * s, hy - 150 * s + k * 20 * s, hx - 6 * s, hy - 150 * s + k * 20 * s), fill=(120, 120, 130), width=lw(3))
        d.rectangle(P(hx - 136 * s, hy - 160 * s, hx - 70 * s, hy - 120 * s), fill=(90, 90, 100))
    elif name == "remote":
        d.rounded_rectangle(P(hx - 12 * s, hy - 80 * s, hx + 12 * s, hy + 6 * s), lw(5), fill=(40, 40, 46), outline=OUT, width=lw(3))
        d.ellipse(P(hx - 6 * s, hy - 72 * s, hx + 6 * s, hy - 60 * s), fill=(220, 50, 50))
    elif name == "bat":
        d.line(P(hx, hy, hx + 10 * s, hy - 60 * s), fill=(60, 40, 30), width=lw(12))
        d.polygon(P(hx + 4 * s, hy - 60 * s, hx + 30 * s, hy - 62 * s, hx + 60 * s, hy - 300 * s, hx + 26 * s, hy - 300 * s), fill=(225, 190, 120), outline=OUT)
    elif name == "book":
        d.rectangle(P(hx - 70 * s, hy - 100 * s, hx + 10 * s, hy + 10 * s), fill=(60, 110, 190), outline=OUT, width=lw(4))
    elif name == "ladle":
        d.line(P(hx, hy, hx + 10 * s, hy - 170 * s), fill=(170, 170, 180), width=lw(9))
        d.ellipse(P(hx - 14 * s, hy - 200 * s, hx + 34 * s, hy - 160 * s), fill=(170, 170, 180), outline=OUT, width=lw(3))
    elif name == "plate":
        d.ellipse(P(hx - 70 * s, hy - 26 * s, hx + 70 * s, hy + 6 * s), fill=(245, 245, 245), outline=OUT, width=lw(4))
        for k in range(3):
            d.ellipse(P(hx - 40 * s + k * 26 * s, hy - 30 * s, hx - 14 * s + k * 26 * s, hy - 12 * s), fill=(210, 150, 70))
    elif name == "bag":
        d.rounded_rectangle(P(hx - 50 * s, hy, hx + 50 * s, hy + 90 * s), lw(10), fill=(150, 80, 120), outline=OUT, width=lw(4))
    elif name == "toy":
        d.ellipse(P(hx - 26 * s, hy - 52 * s, hx + 26 * s, hy), fill=(60, 160, 230), outline=OUT, width=lw(4))
