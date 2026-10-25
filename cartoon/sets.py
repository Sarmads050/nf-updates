"""Locations for "Sindhi Ghar Ki Kahani". World = 1080 x 1920 units. Each set:
build(time) -> dict(bg=RGB image, front=RGBA|None, slots, door, anim(world, t), lm=lightmap, amb=name, glow=RGBA|None)
time: day | evening | night | loadshedding"""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

K = 1.5
OUT = (42, 28, 32)


def setK(k):
    global K
    K = k


def P(*v):
    return [int(round(q * K)) for q in v]


def WW():
    return int(1080 * K)


def WH():
    return int(1920 * K)


def lw(v):
    return max(1, int(v * K))


def grad(w, h, c1, c2):
    a = np.linspace(0, 1, h)[:, None, None]
    return Image.fromarray((np.array(c1) * (1 - a) + np.array(c2) * a).repeat(w, 1).astype("uint8")).convert("RGBA")


SKY = {"day": ((120, 186, 240), (200, 232, 252)), "evening": ((70, 70, 140), (250, 160, 90)),
       "night": ((8, 14, 40), (30, 50, 92)), "loadshedding": ((8, 14, 40), (30, 50, 92))}


def sky_box(im, box, time, seed=3, sun=True):
    x0, y0, x1, y1 = box
    c1, c2 = SKY[time]
    g = grad(lw(x1 - x0), lw(y1 - y0), c1, c2)
    d = ImageDraw.Draw(g)
    r = random.Random(seed)
    if time in ("night", "loadshedding"):
        for _ in range(int((x1 - x0) * (y1 - y0) / 4000)):
            x, y = r.uniform(0, x1 - x0), r.uniform(0, (y1 - y0) * 0.8)
            d.ellipse(P(x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(255, 255, 230, r.randrange(120, 255)))
        if sun:
            mx = (x1 - x0) * 0.7
            d.ellipse(P(mx - 40, 40, mx + 40, 120), fill=(250, 246, 222))
            d.ellipse(P(mx - 18, 32, mx + 58, 112), fill=c1)
    elif time == "day":
        for k in range(3):
            cx, cy = r.uniform(0, x1 - x0), r.uniform(30, (y1 - y0) * 0.5)
            for dx, rr in ((-40, 30), (0, 42), (40, 30)):
                d.ellipse(P(cx + dx - rr, cy - rr * 0.6, cx + dx + rr, cy + rr * 0.6), fill=(255, 255, 255, 220))
        if sun:
            d.ellipse(P(x1 - x0 - 120, 40, x1 - x0 - 40, 120), fill=(255, 236, 140))
    else:
        if sun:
            d.ellipse(P((x1 - x0) * 0.3 - 50, (y1 - y0) * 0.6, (x1 - x0) * 0.3 + 50, (y1 - y0) * 0.6 + 100), fill=(255, 190, 110))
    im.alpha_composite(g, (lw(x0), lw(y0)))


def skyline(d, box, time, seed=5):
    x0, y0, x1, y1 = box
    r = random.Random(seed)
    x = x0 - 20
    lit = time in ("night", "evening")
    while x < x1:
        w = r.randrange(50, 120)
        top = r.randrange(int(y0 + (y1 - y0) * 0.25), int(y0 + (y1 - y0) * 0.7))
        col = (60, 70, 96) if time == "day" else (24, 30, 56) if time != "evening" else (90, 70, 100)
        d.rectangle(P(max(x, x0), top, min(x + w, x1), y1), fill=col)
        for wy in range(top + 12, int(y1) - 10, 26):
            for wx in range(int(x) + 8, int(x + w) - 10, 18):
                if x0 < wx < x1 - 8:
                    on = lit and r.random() < 0.5
                    d.rectangle(P(wx, wy, wx + 8, wy + 12), fill=(255, 214, 128) if on else (90, 100, 130) if time == "day" else (40, 46, 72))
        x += w + r.randrange(2, 10)


def tube_light(d, x, y, on):
    d.rounded_rectangle(P(x - 90, y - 10, x + 90, y + 10), lw(6), fill=(250, 250, 240) if on else (200, 200, 200), outline=(120, 120, 120), width=lw(2))


def glow(im, box, col, blur):
    g = Image.new("RGBA", im.size, 0)
    ImageDraw.Draw(g).ellipse(P(*box), fill=col)
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(lw(blur))))


def lightmap(time, candle=(540, 1300), indoor=True, warm_src=None):
    yy, xx = np.mgrid[0:WH(), 0:WW()] / K
    if time == "day":
        m = np.ones((WH(), WW(), 3), np.float32) * np.array([1.0, 0.99, 0.97], np.float32)
    elif time == "evening":
        m = np.ones((WH(), WW(), 3), np.float32) * np.array([1.0, 0.9, 0.8], np.float32)
    elif time == "night":
        if indoor:
            m = np.ones((WH(), WW(), 3), np.float32) * np.array([0.97, 0.93, 0.86], np.float32)
        else:
            m = np.ones((WH(), WW(), 3), np.float32) * np.array([0.58, 0.64, 0.86], np.float32)
            if warm_src:
                p = np.exp(-(((xx - warm_src[0]) / 520) ** 2 + ((yy - warm_src[1]) / 700) ** 2))[..., None]
                m = m + p * np.array([0.4, 0.3, 0.1], np.float32)
    else:  # load shedding: dark + candle / emergency light pool
        m = np.ones((WH(), WW(), 3), np.float32) * np.array([0.28, 0.32, 0.52], np.float32)
        p = np.exp(-(((xx - candle[0]) / 520) ** 2 + ((yy - candle[1]) / 640) ** 2))[..., None]
        m = m + p * np.array([0.74, 0.62, 0.36], np.float32)
    return np.clip(m, 0, 1.05).astype(np.float32)


def mult(img, lm):
    a = np.asarray(img).astype(np.float32)
    a[..., :3] = np.clip(a[..., :3] * lm, 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def fan(world, t, x, y, spin):
    d = ImageDraw.Draw(world)
    d.line(P(x, 0, x, y), fill=(90, 80, 70), width=lw(8))
    a0 = t * spin
    for k in range(3):
        a = a0 + k * 2 * math.pi / 3
        ex, ey = x + 230 * math.cos(a), y + 34 * math.sin(a)
        d.polygon(P(x + 20 * math.cos(a + 1.4), y + 6 * math.sin(a + 1.4), ex + 30 * math.cos(a + 1.5), ey + 8 * math.sin(a + 1.5),
                    ex - 30 * math.cos(a + 1.5), ey - 8 * math.sin(a + 1.5), x - 20 * math.cos(a + 1.4), y - 6 * math.sin(a + 1.4)),
                  fill=(150, 120, 90), outline=OUT)
    d.ellipse(P(x - 34, y - 20, x + 34, y + 20), fill=(120, 96, 76), outline=OUT, width=lw(3))


def clock(world, t, x, y):
    d = ImageDraw.Draw(world)
    d.ellipse(P(x - 58, y - 58, x + 58, y + 58), fill=(250, 248, 240), outline=(110, 70, 40), width=lw(8))
    for k in range(12):
        a = k * math.pi / 6
        d.line(P(x + 44 * math.cos(a), y + 44 * math.sin(a), x + 52 * math.cos(a), y + 52 * math.sin(a)), fill=(60, 50, 50), width=lw(3))
    am = -math.pi / 2 + t * 0.3
    ah = -math.pi / 2 + 1.3 + t * 0.025
    d.line(P(x, y, x + 40 * math.cos(am), y + 40 * math.sin(am)), fill=(40, 30, 30), width=lw(4))
    d.line(P(x, y, x + 26 * math.cos(ah), y + 26 * math.sin(ah)), fill=(40, 30, 30), width=lw(6))
    d.ellipse(P(x - 5, y - 5, x + 5, y + 5), fill=(180, 40, 40))


def steam(world, t, x, y, n=3, h=120):
    d = ImageDraw.Draw(world)
    for j in range(n):
        pts = [(x - 20 * (n - 1) / 2 + 20 * j + 9 * math.sin(t * 4 + k * 0.5 + j * 2), y - k * h / 10) for k in range(10)]
        d.line([c for p in pts for c in P(*p)], fill=(255, 255, 255, 110), width=lw(5))


def rilli(d, box, seed=1):
    """Sindhi rilli patchwork quilt pattern"""
    x0, y0, x1, y1 = box
    r = random.Random(seed)
    cols = [(190, 40, 50), (240, 200, 60), (40, 110, 70), (30, 40, 100), (240, 240, 230), (230, 120, 50)]
    s = 36
    for yy in range(int(y0), int(y1), s):
        for xx in range(int(x0), int(x1), s):
            c = r.choice(cols)
            d.rectangle(P(xx, yy, min(xx + s, x1), min(yy + s, y1)), fill=c)
            d.polygon(P(xx + s / 2, yy + 4, xx + s - 4, yy + s / 2, xx + s / 2, yy + s - 4, xx + 4, yy + s / 2), fill=r.choice(cols))


def floor_tiles(d, y0, c1, c2):
    d.rectangle(P(0, y0, 1080, 1920), fill=c1)
    for y in range(int(y0), 1920, 110):
        d.line(P(0, y, 1080, y), fill=c2, width=lw(3))
    for x in range(-600, 1700, 150):
        d.line(P(540 + (x - 540) * 0.3, y0, x, 1920), fill=c2, width=lw(3))


def door(d, x0, y0, x1, y1, open_=False):
    d.rectangle(P(x0, y0, x1, y1), fill=(110, 70, 40))
    d.rectangle(P(x0 + 14, y0 + 14, x1 - 14, y1), fill=(150, 98, 58) if not open_ else (40, 30, 30))
    for k in range(2):
        yy = y0 + 40 + k * (y1 - y0 - 80) / 2
        d.rectangle(P(x0 + 30, yy, x1 - 30, yy + (y1 - y0 - 120) / 2), outline=(110, 70, 40), width=lw(5))
    d.ellipse(P(x0 + 22, (y0 + y1) / 2, x0 + 40, (y0 + y1) / 2 + 18), fill=(230, 200, 90))


# ======================================================================= sets
def living_room(time):
    """Nawabshah ghar ka drawing room"""
    on = time != "loadshedding"
    im = Image.new("RGBA", (WW(), WH()), (232, 214, 186, 255))
    d = ImageDraw.Draw(im)
    d.rectangle(P(0, 0, 1080, 110), fill=(214, 196, 168))
    d.rectangle(P(0, 1000, 1080, 1240), fill=(196, 160, 120))
    d.rectangle(P(0, 990, 1080, 1004), fill=(150, 110, 80))
    sky_box(im, (90, 330, 380, 760), "night" if time == "loadshedding" else time)
    d = ImageDraw.Draw(im)
    for x in range(90, 381, 48):
        d.line(P(x, 330, x, 760), fill=(50, 50, 55), width=lw(5))
    for y in (470, 620):
        d.line(P(90, y, 380, y), fill=(50, 50, 55), width=lw(5))
    d.rectangle(P(90, 330, 380, 760), outline=(110, 80, 50), width=lw(12))
    for sd, xx in ((-1, 70), (1, 400)):
        d.polygon(P(xx - 40, 300, xx + 40, 300, xx + 30 * -sd + 20, 820, xx - 30, 820), fill=(140, 40, 50))
    d.rectangle(P(40, 296, 440, 312), fill=(110, 80, 50))
    tube_light(d, 700, 210, on and time in ("night", "evening"))
    for (x0, y0, x1, y1) in ((600, 400, 730, 520), (860, 430, 990, 560)):
        d.rectangle(P(x0, y0, x1, y1), fill=(250, 240, 220), outline=(120, 80, 40), width=lw(10))
        for k, c in enumerate(((190, 60, 60), (60, 90, 170), (60, 140, 90))):
            cx = x0 + 30 + k * 35
            d.ellipse(P(cx - 12, y1 - 70, cx + 12, y1 - 46), fill=(214, 160, 118))
            d.rectangle(P(cx - 14, y1 - 46, cx + 14, y1 - 14), fill=c)
    door(d, 966, 600, 1080, 1240)
    floor_tiles(d, 1240, (176, 150, 128), (150, 126, 106))
    d.rounded_rectangle(P(80, 1380, 1000, 1860), lw(20), fill=(150, 36, 46))
    d.rounded_rectangle(P(110, 1410, 970, 1830), lw(14), outline=(236, 190, 90), width=lw(8))
    for k in range(6):
        cx = 180 + k * 145
        d.polygon(P(cx, 1560, cx + 50, 1620, cx, 1680, cx - 50, 1620), fill=(30, 40, 100), outline=(236, 190, 90))
    # sofa with rilli
    d.rounded_rectangle(P(140, 880, 940, 1190), lw(40), fill=(120, 40, 50), outline=OUT, width=lw(5))
    rilli(d, (190, 920, 890, 1100))
    d.rounded_rectangle(P(110, 1150, 970, 1270), lw(26), fill=(140, 48, 58), outline=OUT, width=lw(5))
    for x in (100, 900):
        d.rounded_rectangle(P(x, 1000, x + 80, 1280), lw(30), fill=(110, 36, 46), outline=OUT, width=lw(5))
    for x in (150, 910):
        d.rectangle(P(x, 1270, x + 22, 1310), fill=(70, 40, 30))
    front = Image.new("RGBA", (WW(), WH()), 0)
    f = ImageDraw.Draw(front)
    f.rounded_rectangle(P(390, 1600, 690, 1640), lw(10), fill=(130, 84, 50), outline=OUT, width=lw(4))
    for x in (410, 650):
        f.rectangle(P(x, 1640, x + 22, 1720), fill=(110, 70, 40), outline=OUT, width=lw(3))
    f.ellipse(P(470, 1560, 610, 1610), fill=(230, 230, 236), outline=OUT, width=lw(3))
    for k, c in enumerate(((250, 180, 40), (200, 50, 50), (250, 160, 40))):
        f.ellipse(P(495 + k * 32, 1550, 535 + k * 32, 1590), fill=c, outline=OUT, width=lw(2))
    glo = None
    if time == "loadshedding":
        f.rounded_rectangle(P(600, 1540, 660, 1606), lw(8), fill=(240, 240, 240), outline=OUT, width=lw(3))
        f.rectangle(P(606, 1548, 654, 1570), fill=(255, 250, 210))
        glo = Image.new("RGBA", (WW(), WH()), 0)
        glow(glo, (420, 1300, 840, 1800), (255, 240, 190, 70), 60)
    elif time in ("night", "evening"):
        glo = Image.new("RGBA", (WW(), WH()), 0)
        glow(glo, (500, 80, 900, 360), (255, 250, 220, 90), 50)
    slots = {
        "sofa_l": dict(x=330, kind="sofa", seat=1185, foot=1360, s=0.66), "sofa_c": dict(x=540, kind="sofa", seat=1185, foot=1360, s=0.66),
        "sofa_r": dict(x=750, kind="sofa", seat=1185, foot=1360, s=0.66),
        "stand_l": dict(x=90, kind="stand", foot=1600, s=0.7), "stand_r": dict(x=990, kind="stand", foot=1600, s=0.7),
        "stand_cl": dict(x=330, kind="stand", foot=1660, s=0.72), "stand_cr": dict(x=760, kind="stand", foot=1660, s=0.72),
        "floor_l": dict(x=240, kind="stand", foot=1800, s=0.8), "floor_r": dict(x=850, kind="stand", foot=1800, s=0.8),
    }

    def anim(world, t):
        fan(world, t, 540, 120, 9 if on else 0.4 * max(0, 1 - t / 4))
        clock(world, t, 840, 260)
    return dict(bg=im.convert("RGB"), front=front, slots=slots, door=dict(x=1020, foot=1600), anim=anim,
                lm=lightmap(time, candle=(630, 1420)), amb="home", glow=glo, mask=None)


def kitchen(time):
    on = time != "loadshedding"
    im = Image.new("RGBA", (WW(), WH()), (236, 238, 240, 255))
    d = ImageDraw.Draw(im)
    for y in range(110, 1240, 60):
        d.line(P(0, y, 1080, y), fill=(206, 214, 222), width=lw(2))
    for x in range(0, 1080, 60):
        d.line(P(x, 110, x, 1240), fill=(206, 214, 222), width=lw(2))
    d.rectangle(P(0, 0, 1080, 110), fill=(214, 206, 196))
    sky_box(im, (640, 430, 940, 740), "night" if time == "loadshedding" else time, seed=9)
    d = ImageDraw.Draw(im)
    d.rectangle(P(640, 430, 940, 740), outline=(90, 110, 130), width=lw(12))
    d.line(P(790, 430, 790, 740), fill=(90, 110, 130), width=lw(8))
    d.rectangle(P(90, 160, 600, 400), fill=(170, 112, 66), outline=OUT, width=lw(4))
    for x in (90, 260, 430):
        d.rectangle(P(x + 8, 170, x + 162, 390), outline=(130, 84, 50), width=lw(5))
        d.ellipse(P(x + 140, 270, x + 152, 290), fill=(230, 200, 90))
    d.rectangle(P(110, 470, 560, 490), fill=(150, 100, 60))
    r = random.Random(4)
    for k in range(7):
        x = 125 + k * 62
        c = r.choice([(230, 160, 40), (200, 50, 40), (120, 70, 40), (240, 220, 120), (90, 140, 60)])
        d.rounded_rectangle(P(x, 400, x + 46, 470), lw(8), fill=(240, 240, 245), outline=OUT, width=lw(3))
        d.rectangle(P(x + 5, 420, x + 41, 466), fill=c)
        d.rectangle(P(x + 8, 392, x + 38, 404), fill=(200, 60, 60))
    tube_light(d, 300, 130, on and time in ("night", "evening"))
    d.rectangle(P(60, 900, 640, 1240), fill=(150, 104, 66), outline=OUT, width=lw(5))
    d.rectangle(P(50, 880, 650, 912), fill=(110, 110, 118), outline=OUT, width=lw(4))
    for x in (90, 280, 470):
        d.rectangle(P(x, 940, x + 150, 1220), outline=(120, 80, 50), width=lw(5))
    d.rectangle(P(120, 852, 520, 884), fill=(40, 40, 46), outline=OUT, width=lw(3))
    d.rounded_rectangle(P(150, 760, 300, 860), lw(10), fill=(170, 170, 180), outline=OUT, width=lw(4))  # pot
    d.rectangle(P(140, 752, 310, 770), fill=(140, 140, 150), outline=OUT, width=lw(3))
    d.polygon(P(360, 860, 380, 790, 470, 790, 490, 860), fill=(60, 60, 66), outline=OUT)  # tawa/kettle
    d.ellipse(P(390, 770, 460, 800), fill=(80, 80, 86), outline=OUT, width=lw(3))
    d.rounded_rectangle(P(690, 990, 800, 1236), lw(30), fill=(200, 40, 40), outline=OUT, width=lw(5))  # gas cylinder
    d.rectangle(P(725, 960, 765, 994), fill=(150, 150, 160), outline=OUT, width=lw(3))
    d.rectangle(P(880, 520, 1080, 1240), fill=(222, 228, 236), outline=OUT, width=lw(5))
    d.line(P(880, 760, 1080, 760), fill=OUT, width=lw(4))
    d.rectangle(P(900, 600, 916, 700), fill=(150, 150, 160))
    d.rectangle(P(0, 560, 40, 1240), fill=(110, 70, 40))
    floor_tiles(d, 1240, (210, 206, 196), (180, 176, 166))
    for y in range(1240, 1920, 110):
        for x in range(0, 1080, 220):
            off = 110 if ((y - 1240) // 110) % 2 else 0
            d.rectangle(P(x + off, y, x + off + 110, y + 110), fill=(196, 190, 180))
    glo = None
    if time == "loadshedding":
        glo = Image.new("RGBA", (WW(), WH()), 0)
        glow(glo, (100, 600, 600, 1000), (255, 200, 120, 80), 50)
    slots = {
        "stove": dict(x=330, kind="stand", foot=1640, s=0.78), "mid": dict(x=560, kind="stand", foot=1690, s=0.8),
        "right": dict(x=820, kind="stand", foot=1650, s=0.78), "left": dict(x=150, kind="stand", foot=1700, s=0.8),
        "floor_l": dict(x=200, kind="stand", foot=1820, s=0.82), "floor_r": dict(x=900, kind="stand", foot=1820, s=0.82),
    }

    def anim(world, t):
        steam(world, t, 225, 740, 3, 140)
        d = ImageDraw.Draw(world)
        for k in range(5):
            fx = 170 + k * 25
            hgt = 10 + 4 * math.sin(t * 20 + k)
            d.polygon(P(fx - 6, 852, fx, 852 - hgt, fx + 6, 852), fill=(80, 140, 255))
    return dict(bg=im.convert("RGB"), front=None, slots=slots, door=dict(x=30, foot=1650), anim=anim,
                lm=lightmap(time, candle=(330, 900)), amb="kitchen", glow=glo, mask=None)


def aangan(time):
    """courtyard with neem tree and charpai"""
    im = Image.new("RGBA", (WW(), WH()), 0)
    sky_box(im, (0, 0, 1080, 900), "night" if time == "loadshedding" else time, seed=11)
    d = ImageDraw.Draw(im)
    d.rectangle(P(0, 620, 1080, 1180), fill=(196, 120, 86))
    r = random.Random(2)
    for y in range(620, 1180, 30):
        for x in range(0 if (y // 30) % 2 else -30, 1080, 60):
            d.rectangle(P(x, y, x + 58, y + 28), outline=(170, 100, 70), width=lw(2))
    for k in range(4):
        x, y = r.randrange(100, 900), r.randrange(660, 1080)
        d.ellipse(P(x, y, x + 140, y + 70), fill=(214, 196, 170))
    d.rectangle(P(0, 600, 1080, 624), fill=(170, 100, 70))
    d.rectangle(P(840, 700, 1060, 1180), fill=(40, 110, 80), outline=OUT, width=lw(5))
    for x in range(860, 1050, 30):
        d.line(P(x, 710, x, 1170), fill=(30, 90, 64), width=lw(4))
    d.rounded_rectangle(P(700, 990, 800, 1180), lw(16), fill=(40, 90, 200), outline=OUT, width=lw(4))
    d.rectangle(P(120, 500, 190, 1200), fill=(110, 80, 56), outline=OUT, width=lw(4))
    d.line(P(190, 760, 830, 720), fill=(220, 220, 220), width=lw(3))
    for cx, c in ((420, (230, 90, 80)), (560, (240, 230, 220)), (690, (90, 150, 210))):
        y = 760 - (cx - 190) * 40 / 640
        d.polygon(P(cx - 40, y, cx + 40, y, cx + 46, y + 28, cx + 30, y + 30, cx + 30, y + 110, cx - 30, y + 110, cx - 30, y + 30, cx - 46, y + 28), fill=c)
    d.rectangle(P(0, 1180, 1080, 1920), fill=(206, 186, 156))
    for k in range(40):
        x, y = r.randrange(0, 1080), r.randrange(1200, 1900)
        d.ellipse(P(x, y, x + 8, y + 5), fill=(180, 160, 130))
    # charpai
    d.polygon(P(230, 1250, 850, 1250, 880, 1340, 200, 1340), fill=(214, 180, 110), outline=OUT)
    for k in range(18):
        x = 240 + k * 35
        d.line(P(x, 1252, x - 12, 1338), fill=(180, 140, 80), width=lw(3))
    for y in (1272, 1296, 1320):
        d.line(P(222, y, 860, y), fill=(180, 140, 80), width=lw(3))
    d.rectangle(P(196, 1336, 884, 1356), fill=(140, 90, 50), outline=OUT, width=lw(3))
    for x in (200, 860):
        d.rectangle(P(x, 1356, x + 24, 1470), fill=(140, 90, 50), outline=OUT, width=lw(3))
    leaves = []
    for k in range(26):
        leaves.append((r.uniform(-60, 420), r.uniform(240, 640), r.uniform(60, 120), r.random() * 6))
    slots = {
        "charpai_l": dict(x=380, kind="sofa", seat=1290, foot=1465, s=0.66), "charpai_r": dict(x=700, kind="sofa", seat=1290, foot=1465, s=0.66),
        "charpai_c": dict(x=540, kind="sofa", seat=1290, foot=1465, s=0.66),
        "stand_l": dict(x=170, kind="stand", foot=1700, s=0.8), "stand_r": dict(x=910, kind="stand", foot=1700, s=0.8),
        "stand_c": dict(x=540, kind="stand", foot=1760, s=0.82), "floor_l": dict(x=260, kind="stand", foot=1840, s=0.84),
        "floor_r": dict(x=820, kind="stand", foot=1840, s=0.84),
    }
    dark = time in ("night", "loadshedding")

    def anim(world, t):
        d = ImageDraw.Draw(world)
        for (x, y, rr, ph) in leaves:
            sw = 6 * math.sin(t * 1.3 + ph)
            col = (50, 120, 60) if not dark else (20, 50, 36)
            d.ellipse(P(x + sw - rr, y - rr * 0.8, x + sw + rr, y + rr * 0.8), fill=col)
        if time == "day":
            for k in range(3):
                bx = (t * 60 + k * 300) % 1300 - 100
                by = 200 + 40 * k + 10 * math.sin(t * 3 + k)
                wv = 10 * math.sin(t * 12 + k)
                d.line(P(bx - 16, by - wv, bx, by, bx + 16, by - wv), fill=(40, 40, 50), width=lw(4))
    return dict(bg=im.convert("RGB"), front=None, slots=slots, door=dict(x=950, foot=1660), anim=anim,
                lm=lightmap(time, candle=(540, 1300), indoor=False, warm_src=(540, 1100)), amb="outdoor", glow=None, mask=None)


def karachi_flat(time):
    on = time != "loadshedding"
    im = Image.new("RGBA", (WW(), WH()), (226, 228, 232, 255))
    d = ImageDraw.Draw(im)
    sky_box(im, (60, 240, 1020, 960), "night" if time == "loadshedding" else time, seed=21)
    d = ImageDraw.Draw(im)
    skyline(d, (60, 380, 1020, 960), "night" if time == "loadshedding" else time)
    if time == "day":
        d.rectangle(P(60, 900, 1020, 960), fill=(70, 140, 190))
    for x in range(60, 1021, 240):
        d.line(P(x, 240, x, 960), fill=(200, 204, 212), width=lw(12))
    d.rectangle(P(60, 240, 1020, 960), outline=(190, 194, 202), width=lw(16))
    d.rectangle(P(0, 960, 1080, 1240), fill=(206, 208, 214))
    d.rounded_rectangle(P(170, 900, 910, 1180), lw(40), fill=(70, 90, 120), outline=OUT, width=lw(5))
    d.rounded_rectangle(P(140, 1150, 940, 1270), lw(26), fill=(84, 104, 136), outline=OUT, width=lw(5))
    for x, c in ((260, (240, 200, 80)), (760, (230, 120, 90))):
        d.rounded_rectangle(P(x - 60, 980, x + 60, 1100), lw(24), fill=c, outline=OUT, width=lw(4))
    d.polygon(P(970, 1150, 1050, 1150, 1036, 1240, 984, 1240), fill=(240, 240, 240), outline=OUT)
    for k in range(7):
        a = -2.5 + k * 0.33
        d.line(P(1010, 1150, 1010 + 110 * math.cos(a), 1150 + 110 * math.sin(a)), fill=(50, 130, 70), width=lw(8))
    floor_tiles(d, 1240, (220, 214, 204), (196, 190, 180))
    d.rectangle(P(0, 560, 50, 1240), fill=(150, 110, 70))
    glo = None
    if time in ("night", "evening") and on:
        glo = Image.new("RGBA", (WW(), WH()), 0)
        glow(glo, (300, 40, 780, 300), (255, 245, 220, 80), 50)
    slots = {
        "sofa_l": dict(x=330, kind="sofa", seat=1190, foot=1365, s=0.66), "sofa_c": dict(x=540, kind="sofa", seat=1190, foot=1365, s=0.66),
        "sofa_r": dict(x=750, kind="sofa", seat=1190, foot=1365, s=0.66),
        "stand_l": dict(x=90, kind="stand", foot=1620, s=0.72), "stand_r": dict(x=990, kind="stand", foot=1620, s=0.72),
        "stand_cl": dict(x=330, kind="stand", foot=1680, s=0.77), "stand_cr": dict(x=760, kind="stand", foot=1680, s=0.77),
        "floor_l": dict(x=240, kind="stand", foot=1800, s=0.8), "floor_r": dict(x=850, kind="stand", foot=1800, s=0.8),
    }

    def anim(world, t):
        d = ImageDraw.Draw(world)
        if time in ("night", "evening"):
            r = random.Random(int(t * 2))
            for _ in range(6):
                x, y = r.randrange(80, 1000), r.randrange(420, 900)
                d.rectangle(P(x, y, x + 8, y + 12), fill=(255, 230, 150))
    return dict(bg=im.convert("RGB"), front=None, slots=slots, door=dict(x=25, foot=1620), anim=anim,
                lm=lightmap(time, candle=(540, 1300)), amb="city", glow=glo, mask=None)


def bedroom(time):
    """boys' room: bed, study desk with computer, cricket poster"""
    on = time != "loadshedding"
    im = Image.new("RGBA", (WW(), WH()), (190, 214, 230, 255))
    d = ImageDraw.Draw(im)
    d.rectangle(P(0, 0, 1080, 100), fill=(170, 196, 214))
    sky_box(im, (400, 300, 640, 600), "night" if time == "loadshedding" else time, seed=31)
    d = ImageDraw.Draw(im)
    d.rectangle(P(400, 300, 640, 600), outline=(240, 240, 240), width=lw(12))
    d.line(P(520, 300, 520, 600), fill=(240, 240, 240), width=lw(8))
    d.rectangle(P(90, 300, 330, 620), fill=(30, 120, 70), outline=(250, 250, 250), width=lw(8))  # cricket poster (generic)
    d.line(P(150, 360, 270, 560), fill=(230, 200, 140), width=lw(26))
    d.ellipse(P(240, 400, 290, 450), fill=(220, 40, 40))
    d.rectangle(P(720, 260, 1000, 300), fill=(150, 100, 60))
    for k in range(8):
        x = 730 + k * 33
        d.rectangle(P(x, 180, x + 26, 260), fill=[(200, 60, 60), (60, 90, 170), (230, 190, 60), (60, 140, 90)][k % 4], outline=OUT)
    tube_light(d, 540, 160, on and time in ("night", "evening"))
    d.rectangle(P(0, 1200, 1080, 1240), fill=(150, 170, 186))
    d.rounded_rectangle(P(40, 980, 560, 1280), lw(20), fill=(120, 80, 50), outline=OUT, width=lw(5))
    d.rounded_rectangle(P(60, 1080, 540, 1240), lw(20), fill=(250, 250, 250), outline=OUT, width=lw(4))
    rilli(d, (60, 1150, 540, 1240), seed=4)
    d.rounded_rectangle(P(80, 1030, 220, 1100), lw(20), fill=(240, 240, 250), outline=OUT, width=lw(3))
    d.rectangle(P(620, 1000, 1040, 1036), fill=(150, 100, 60), outline=OUT, width=lw(4))
    for x in (640, 1010):
        d.rectangle(P(x, 1036, x + 20, 1260), fill=(130, 86, 50), outline=OUT, width=lw(3))
    d.rectangle(P(700, 800, 900, 940), fill=(30, 30, 36), outline=OUT, width=lw(5))
    d.rectangle(P(785, 940, 815, 1000), fill=(60, 60, 66))
    d.rectangle(P(740, 980, 860, 1000), fill=(60, 60, 66))
    floor_tiles(d, 1240, (200, 190, 176), (176, 166, 150))
    d.rectangle(P(1000, 560, 1080, 1240), fill=(110, 70, 40))
    slots = {
        "bed": dict(x=300, kind="sofa", seat=1170, foot=1345, s=0.66), "desk": dict(x=800, kind="sofa", seat=1180, foot=1355, s=0.66),
        "stand_l": dict(x=170, kind="stand", foot=1640, s=0.78), "stand_r": dict(x=910, kind="stand", foot=1640, s=0.78),
        "stand_c": dict(x=540, kind="stand", foot=1700, s=0.8), "floor_l": dict(x=240, kind="stand", foot=1820, s=0.82),
        "floor_r": dict(x=850, kind="stand", foot=1820, s=0.82),
    }

    def anim(world, t):
        d = ImageDraw.Draw(world)
        if on:
            c = int(150 + 40 * math.sin(t * 2))
            d.rectangle(P(712, 812, 888, 928), fill=(60, c, 220))
            for k in range(5):
                d.line(P(724, 830 + k * 18, 724 + 60 + 80 * ((k * 37 + int(t * 3)) % 5) / 5, 830 + k * 18), fill=(230, 240, 255), width=lw(4))
    glo = None
    if on:
        glo = Image.new("RGBA", (WW(), WH()), 0)
        glow(glo, (640, 760, 960, 1000), (120, 180, 255, 50), 40)
    return dict(bg=im.convert("RGB"), front=None, slots=slots, door=dict(x=1040, foot=1640), anim=anim,
                lm=lightmap(time, candle=(800, 1000)), amb="home", glow=glo, mask=None)


def gali(time):
    """street outside the house"""
    im = Image.new("RGBA", (WW(), WH()), 0)
    sky_box(im, (0, 0, 1080, 800), "night" if time == "loadshedding" else time, seed=41)
    d = ImageDraw.Draw(im)
    houses = [(0, 300, 260, (230, 200, 160)), (260, 420, 520, (200, 210, 190)), (520, 360, 800, (240, 220, 200)), (800, 280, 1080, (210, 180, 170))]
    for x0, top, x1, c in houses:
        d.rectangle(P(x0, top, x1, 1250), fill=c, outline=OUT, width=lw(3))
        d.rectangle(P(x0, top - 30, x1, top), fill=tuple(int(v * 0.85) for v in c))
        for wx in range(x0 + 40, x1 - 80, 120):
            d.rectangle(P(wx, top + 80, wx + 70, top + 180), fill=(90, 120, 150) if time == "day" else (255, 214, 128), outline=OUT, width=lw(3))
            for gx in range(wx, wx + 71, 18):
                d.line(P(gx, top + 80, gx, top + 180), fill=(40, 40, 46), width=lw(3))
    d.rectangle(P(560, 860, 780, 1250), fill=(60, 120, 180), outline=OUT, width=lw(4))
    d.rectangle(P(540, 800, 800, 870), fill=(220, 60, 50), outline=OUT, width=lw(4))
    d.text(P(570, 818), "GENERAL STORE", fill=(255, 255, 255))
    for k in range(6):
        d.rectangle(P(580 + k * 32, 900, 604 + k * 32, 960), fill=[(240, 200, 60), (230, 80, 60), (80, 170, 90)][k % 3])
    d.line(P(0, 520, 1080, 480), fill=(30, 30, 30), width=lw(3))
    d.line(P(0, 560, 1080, 540), fill=(30, 30, 30), width=lw(3))
    d.rectangle(P(80, 1000, 180, 1200), fill=(250, 250, 250))
    for x in (100, 128, 156):
        d.line(P(x, 1010, x, 1190), fill=(40, 40, 40), width=lw(5))  # chalk wicket
    d.rectangle(P(0, 1250, 1080, 1920), fill=(150, 150, 154))
    d.rectangle(P(0, 1250, 1080, 1290), fill=(120, 120, 124))
    for x in range(0, 1080, 160):
        d.rectangle(P(x, 1580, x + 90, 1596), fill=(240, 240, 240))
    slots = {
        "left": dict(x=170, kind="stand", foot=1650, s=0.8), "cl": dict(x=420, kind="stand", foot=1700, s=0.82),
        "cr": dict(x=680, kind="stand", foot=1700, s=0.82), "right": dict(x=910, kind="stand", foot=1650, s=0.8),
        "floor_l": dict(x=260, kind="stand", foot=1840, s=0.86), "floor_r": dict(x=820, kind="stand", foot=1840, s=0.86),
    }

    def anim(world, t):
        d = ImageDraw.Draw(world)
        if time == "day":
            for k in range(3):
                bx = (t * 70 + k * 330) % 1300 - 100
                by = 150 + 50 * k + 10 * math.sin(t * 3 + k)
                wv = 10 * math.sin(t * 12 + k)
                d.line(P(bx - 16, by - wv, bx, by, bx + 16, by - wv), fill=(40, 40, 50), width=lw(4))
    return dict(bg=im.convert("RGB"), front=None, slots=slots, door=dict(x=1150, foot=1680), anim=anim,
                lm=lightmap(time, indoor=False, warm_src=(670, 1000)), amb="street", glow=None, mask=None)


SETS = {"living_room": living_room, "kitchen": kitchen, "aangan": aangan, "karachi_flat": karachi_flat,
        "bedroom": bedroom, "gali": gali}
