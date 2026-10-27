"""Episode renderer for "Sindhi Ghar Ki Kahani".
usage: python engine.py episodes/ep001.json <voice_dir> [out.mp4]      (PREVIEW=t1,t2 env for still frames)
Episode JSON -> timed acting (emotions, gestures, eye-lines, blinks, lip-sync, walks), camera, lighting,
sound design, one-line captions, title + end card."""
import os, sys, math, json, random, wave, subprocess, base64
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import art, sets as SETS

K = 1.5
art.setK(K)
SETS.setK(K)
OW, OH, FPS, SR = 1080, 1920, 30, 44100
WW, WH = int(1080 * K), int(1920 * K)
OUT = art.OUT


def sh(c):
    r = subprocess.run(c, shell=True)
    assert r.returncode == 0, c


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, u):
    return a + (b - a) * u


def ease(u):
    u = clamp(u, 0, 1)
    return u * u * (3 - 2 * u)


def back(u):
    u = clamp(u, 0, 1)
    c = 1.6
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


EP_PATH = sys.argv[1]
VO = sys.argv[2]
OUTFILE = sys.argv[3] if len(sys.argv) > 3 else os.path.splitext(EP_PATH)[0] + ".mp4"
WORK = os.path.splitext(OUTFILE)[0] + "_work"
os.makedirs(WORK, exist_ok=True)
EP = json.load(open(EP_PATH, encoding="utf-8"))

# ============================================================== audio per line
LINES = []  # flat list: dict(scene, line...)
for si, sc in enumerate(EP["scenes"]):
    for ln in sc["lines"]:
        LINES.append(dict(ln, scene=si))


def load_line(i, who):
    f = f"{VO}/{i + 1:02d}.mp3"
    pitch = art.CHARS[who].get("toddler")
    af = "asetrate=24000*1.22,aresample=44100,atempo=0.86," if pitch else ""
    if EP.get("tempo", 1.0) != 1.0:  # optional per-episode speed-up (e.g. slower fallback voices)
        af += f"atempo={float(EP['tempo']):.3f},"
    raw = f"{WORK}/l{i}.raw"
    sh(f'ffmpeg -v error -y -i "{f}" -af "{af}aresample={SR}" -ac 1 -f s16le "{raw}"')
    x = np.fromfile(raw, "<i2").astype(np.float32) / 32768
    os.remove(raw)
    k = np.where(np.abs(x) > 0.01)[0]
    x = x[max(k[0] - 800, 0):k[-1] + 2500] if len(k) else x
    act = x[np.abs(x) > 0.02]
    x *= 0.1 / (np.sqrt(np.mean(act ** 2)) + 1e-6) if len(act) else 1
    return np.clip(x, -0.97, 0.97)


VOX = [load_line(i, l["who"]) for i, l in enumerate(LINES)]
for i, l in enumerate(LINES):
    if l.get("offscreen") or l.get("phone"):
        v = np.convolve(VOX[i], np.ones(7) / 7, "same")
        if l.get("phone"):  # telephone band
            v = v - np.convolve(v, np.ones(40) / 40, "same")
        VOX[i] = v * 0.8

# ============================================================== timeline + character tracks
SC = []        # scene objects: dict(t0,t1,set,time,...)
TR = {}        # who -> list of segments (t0, kind, data)
PROP = {}      # who -> list of (t, prop)
times = []
EVT = []       # sound events (t, name)
STEP = 88.0
WALK_V = 430.0


def slot_pos(scene, slot):
    return scene["set"]["slots"][slot]


def seg(who, t, kind, **kw):
    TR.setdefault(who, []).append((t, kind, kw))


t = 0.35
for si, scd in enumerate(EP["scenes"]):
    st = SETS.SETS[scd["set"]](scd.get("time", "day"))
    lm = st["lm"]
    bg = SETS.mult(st["bg"].convert("RGBA"), lm)
    if st.get("glow") is not None:
        bg.alpha_composite(st["glow"])
    scene = dict(t0=t, set=st, bg=bg.convert("RGB"), name=scd["set"], time=scd.get("time", "day"), cast=dict(scd.get("cast", {})),
                 label=scd.get("label"))
    if si > 0:
        EVT.append((t, "whoosh"))
    for who in TR:
        seg(who, t, "off")
    for who, slot in scene["cast"].items():
        s = slot_pos(scene, slot)
        seg(who, t, "at", scene=si, slot=slot)
    for who, pr in scd.get("props", {}).items():
        PROP.setdefault(who, []).append((t, pr))
    pos = dict(scene["cast"])  # current slot of everyone present

    def do_action(a, t):
        kind = a["do"]
        who = a.get("who")
        if kind == "prop":
            PROP.setdefault(who, []).append((t, a.get("prop")))
            return t + 0.1
        if kind == "sfx":
            EVT.append((t, a["name"]))
            return t + a.get("wait", 0.0)
        if kind == "enter":
            dest = slot_pos(scene, a["slot"])
            x0 = scene["set"]["door"]["x"]
            dur = abs(dest["x"] - x0) / WALK_V + 0.25
            EVT.append((t, "door"))
            seg(who, t, "walk", scene=si, x0=x0, x1=dest["x"], foot=dest["foot"] if dest["kind"] == "stand" else dest["foot"] + 80,
                s=dest["s"], fade_in=True, dur=dur)
            t += dur
            if dest["kind"] != "stand":
                seg(who, t, "sit", scene=si, slot=a["slot"], dur=0.5)
                t += 0.5
            seg(who, t, "at", scene=si, slot=a["slot"])
            pos[who] = a["slot"]
            return t + 0.15
        if kind == "exit":
            src = slot_pos(scene, pos[who])
            if src["kind"] != "stand":
                seg(who, t, "rise", scene=si, slot=pos[who], dur=0.5)
                t += 0.5
            x1 = scene["set"]["door"]["x"]
            dur = abs(src["x"] - x1) / WALK_V + 0.25
            seg(who, t, "walk", scene=si, x0=src["x"], x1=x1, foot=src["foot"] if src["kind"] == "stand" else src["foot"] + 80,
                s=src["s"], fade_out=True, dur=dur)
            t += dur
            EVT.append((t - 0.2, "door"))
            seg(who, t, "off")
            pos.pop(who, None)
            return t + 0.1
        if kind == "move":
            src, dest = slot_pos(scene, pos[who]), slot_pos(scene, a["slot"])
            if src["kind"] != "stand":
                seg(who, t, "rise", scene=si, slot=pos[who], dur=0.5)
                t += 0.5
            dur = abs(src["x"] - dest["x"]) / WALK_V + 0.2
            seg(who, t, "walk", scene=si, x0=src["x"], x1=dest["x"], foot=dest["foot"] if dest["kind"] == "stand" else dest["foot"] + 80,
                s=dest["s"], dur=dur)
            t += dur
            if dest["kind"] != "stand":
                seg(who, t, "sit", scene=si, slot=a["slot"], dur=0.5)
                t += 0.5
            seg(who, t, "at", scene=si, slot=a["slot"])
            pos[who] = a["slot"]
            return t + 0.1
        if kind == "approach":  # walk next to another character (e.g. to take something from them)
            tgt = slot_pos(scene, pos[a["to"]])
            src = slot_pos(scene, pos[who])
            side = -1 if src["x"] < tgt["x"] else 1
            name = f"near_{a['to']}_{side}"
            scene["set"]["slots"][name] = dict(x=tgt["x"] + side * 235, kind="stand", foot=tgt.get("foot", 1650) - 6, s=tgt["s"])
            a = dict(a, slot=name)
            kind = "move"
        if kind == "move" and a["slot"].startswith("near_"):
            src, dest = slot_pos(scene, pos[who]), slot_pos(scene, a["slot"])
            if src["kind"] != "stand":
                seg(who, t, "rise", scene=si, slot=pos[who], dur=0.5)
                t += 0.5
            dur = abs(src["x"] - dest["x"]) / WALK_V + 0.2
            seg(who, t, "walk", scene=si, x0=src["x"], x1=dest["x"], foot=dest["foot"], s=dest["s"], dur=dur)
            t += dur
            seg(who, t, "at", scene=si, slot=a["slot"])
            pos[who] = a["slot"]
            return t + 0.1
        if kind == "wait":
            return t + a.get("sec", 0.5)
        return t

    scene["pos_start"] = dict(pos)
    for ln in scd["lines"]:
        for a in ln.get("before", []):
            t = do_action(a, t)
        i = len(times)
        d = len(VOX[i]) / SR
        LINES[i]["present"] = dict(pos)
        times.append((t, t + d))
        for nm in ln.get("sfx", []):
            EVT.append((t, nm))
        if ln.get("joke"):
            EVT.append((t + d + 0.05, "sting"))
        if ln.get("give"):
            g = ln["give"]
            tg = t + d * g.get("at", 0.55)
            PROP.setdefault(ln["who"], []).append((t - 0.01, g.get("prop", "money")))
            PROP.setdefault(ln["who"], []).append((tg, None))
            PROP.setdefault(g["to"], []).append((tg, g.get("prop", "money")))
        gap = ln.get("gap", 0.32)
        if ln.get("joke"):
            gap = max(gap, 1.0)  # let the laugh land
        t += d + gap
        for a in ln.get("after", []):
            t = do_action(a, t)
    t += 0.25
    scene["t1"] = t
    SC.append(scene)
T_END = t
TOTAL = T_END + 3.4
N = int(TOTAL * FPS)
print("total", round(TOTAL, 1), "lines", len(LINES), flush=True)


def scene_at(t):
    for s in SC[::-1]:
        if t >= s["t0"]:
            return SC.index(s)
    return 0


def char_state(who, t):
    """-> None or dict(x, foot/T etc)"""
    segs = TR.get(who, [])
    cur = None
    for sg in segs:
        if sg[0] <= t:
            cur = sg
        else:
            break
    if cur is None or cur[1] == "off":
        return None
    t0, kind, kw = cur
    sc = SC[kw["scene"]]
    cs = art.CHARS[who]["scale"]
    if kind == "at":
        s = sc["set"]["slots"][kw["slot"]]
        return dict(x=s["x"], mode=s["kind"], seat=s.get("seat"), foot=s["foot"], s=s["s"] * cs, stand=0 if s["kind"] != "stand" else 1,
                    walking=False, alpha=1, dist=0)
    if kind in ("sit", "rise"):
        s = sc["set"]["slots"][kw["slot"]]
        u = ease((t - t0) / kw["dur"])
        st = 1 - u if kind == "sit" else u
        return dict(x=s["x"], mode="sofa", seat=s["seat"], foot=s["foot"], s=s["s"] * cs, stand=st, walking=False, alpha=1, dist=0)
    if kind == "walk":
        u = clamp((t - t0) / kw["dur"], 0, 1)
        x = lerp(kw["x0"], kw["x1"], ease(u * 0.9 + 0.1 * u * u))
        a = 1
        if kw.get("fade_in"):
            a = clamp((t - t0) / 0.25, 0, 1)
        if kw.get("fade_out"):
            a = clamp((t0 + kw["dur"] - t) / 0.25, 0, 1)
        return dict(x=x, mode="stand", seat=None, foot=kw["foot"], s=kw["s"] * cs, stand=1, walking=True, alpha=a,
                    dist=abs(x - kw["x0"]), dir=1 if kw["x1"] > kw["x0"] else -1)
    return None


def geom(st, who):
    """torso top T and key points for a state"""
    s = st["s"]
    hs = art.CHARS[who].get("hs", 1.0)
    if st["mode"] == "stand" or st["stand"] >= 1:
        T_stand = st["foot"] - (370 + 500) * s
    else:
        T_stand = st["foot"] - (370 + 500) * s
    if st["mode"] != "stand":
        T_sit = st["seat"] - 500 * s
        T = lerp(T_sit, T_stand, st["stand"])
    else:
        T = T_stand
    head_y = T + 90 * s - 205 * s * hs
    return T, head_y


# ============================================================== acting tracks
POSES = {  # near(dx,dy), far(dx,dy), flags ; units relative to torso top, scaled by s
    "rest_sofa": ((70, 470), (-70, 470), ""), "rest_stand": ((165, 440), (-165, 440), "side"),
    "read": ((122, 432), (22, 436), ""), "head_hold": ((112, -150), (-112, -150), ""),
    "beckon": ((178, 95), (-70, 470), "wave"), "wag": ((140, 25), (-70, 470), "wag finger"),
    "plead": ((40, 135), (-18, 140), ""), "point_down": ((230, 400), (-70, 470), "finger"),
    "fist": ((150, -135), (-70, 470), ""), "point_other": ((245, 125), (-70, 470), "finger"),
    "thumb_back": ((70, 470), (-178, 60), "farfinger"), "arms_up": ((185, -285), (-185, -285), "jump"),
    "chest": ((18, 235), (-70, 470), ""), "wave": ((195, -160), (-70, 470), "wave"),
    "hold": ((120, 260), (-70, 470), "prop"), "newspaper": ((60, 260), (-130, 250), "prop"),
    "phone_look": ((70, 60), (-70, 470), "prop"), "hands_hips": ((175, 400), (-175, 400), ""),
    "cross": ((-60, 250), (60, 262), ""), "shrug": ((200, 80), (-200, 80), ""),
    "facepalm": ((20, -110), (-70, 470), ""), "scratch_head": ((95, -240), (-70, 470), ""),
    "objection": ((150, -235), (-70, 470), "finger"), "clap": ((30, 230), (-30, 230), "clap"),
    "think": ((30, -40), (-40, 300), ""), "explain": ((185, 210), (-160, 240), "explain"),
    "point_up": ((150, -200), (-70, 470), "finger"), "tired": ((90, 470), (-90, 470), ""),
    "walk": ((120, 430), (-120, 430), "walk"), "tray": ((80, 175), (-80, 175), "tray"),
    "give": ((175, 150), (-70, 470), "prop"), "take": ((175, 158), (-70, 470), ""),
}
ALIAS = {"rest": None}
EMO_TILT = {"worried": -3, "sheepish": 5, "teasing": -6, "happy": 2.5, "laugh": 0, "warm": 4, "calm": 1.5, "surprised": 0,
            "focused": -1.5, "neutral": 0, "angry": -2, "tired": 6, "proud": -3, "confused": 7, "sad": 5}


def keyed(v, a, d):
    """value can be a string or [[frac, value], ...] -> list of (time, value)"""
    if v is None:
        return []
    if isinstance(v, str):
        return [(a, v)]
    return [(a + f * d, x) for f, x in v]


EMO, POSE, LOOK = {}, {}, {}


def add(tr, who, t, v):
    tr.setdefault(who, []).append((t, v))


for i, l in enumerate(LINES):
    a, b = times[i]
    d = b - a
    sp = l["who"]
    to = l.get("to")
    for tt, v in keyed(l.get("emo", "calm"), a, d):
        add(EMO, sp, tt, v)
    for tt, v in keyed(l.get("pose", "rest"), a, d):
        add(POSE, sp, tt, v)
    add(LOOK, sp, a - 0.1, l.get("look", to or "*"))
    react = dict(l.get("react", {}))
    if l.get("joke") and "*" not in react:
        react["*"] = "laugh"
    for who in l["present"]:
        if who == sp:
            continue
        e = react.get(who, react.get("*"))
        if e:
            if e == "laugh":  # listeners laugh when the punchline lands (end of the line), not before
                add(EMO, who, a + 0.15, "happy")
                add(EMO, who, b - 0.2, "laugh")
                add(EMO, who, b + 1.3, "happy")
            else:
                for tt, v in keyed(e, a + 0.15, d):
                    add(EMO, who, tt, v)
        lk = l.get("looks", {}).get(who, sp)
        add(LOOK, who, a + 0.12, lk)
        for tt, v in keyed(l.get("react_pose", {}).get(who), a + 0.1, d):
            add(POSE, who, tt, v)
    if l.get("give"):  # hand-over: giver reaches out, receiver takes it
        g = l["give"]
        tg = a + d * g.get("at", 0.55)
        add(POSE, sp, max(a, tg - 0.6), "give")
        add(POSE, sp, tg + 0.45, "rest")
        add(POSE, g["to"], tg - 0.35, "take")
        add(POSE, g["to"], tg + 0.5, "hold")
        add(LOOK, sp, a - 0.1, g["to"])
        add(LOOK, g["to"], a + 0.1, sp)
for tr in (EMO, POSE, LOOK):
    for w in tr:
        tr[w].sort(key=lambda e: e[0])


def at(tr, who, t, default):
    lst = tr.get(who, [])
    cur, prev, tc = default, default, -9
    for tt, v in lst:
        if tt <= t:
            if v != cur:
                prev, cur, tc = cur, v, tt
        else:
            break
    return cur, prev, tc


def prop_at(who, t):
    p = None
    for tt, v in PROP.get(who, []):
        if tt <= t:
            p = v
    return p


# lip-sync
trk = {}
for (l, v, (a, b)) in zip(LINES, VOX, times):
    w = l["who"]
    trk.setdefault(w, np.zeros(int(TOTAL * SR) + SR, np.float32))
    i = int(a * SR)
    trk[w][i:i + len(v)] += v


def lip(x):
    hop = SR // FPS
    e = np.zeros(N)
    z = np.zeros(N)
    for i in range(N):
        s = x[i * hop:(i + 1) * hop]
        if len(s) == 0:
            continue
        e[i] = np.sqrt(np.mean(s ** 2))
        z[i] = np.mean(np.abs(np.diff(np.sign(s)))) / 2 if e[i] > 0.01 else 0
    e = e / (np.percentile(e[e > 0.01], 92) + 1e-6) if np.any(e > 0.01) else e
    sm = np.zeros(N)
    c = 0
    for i in range(N):
        c = c + (e[i] - c) * (0.75 if e[i] > c else 0.4)
        sm[i] = c
    hp = np.clip(sm - np.convolve(sm, np.ones(9) / 9, "same"), 0, 1)
    return sm, z, hp


LIP = {w: lip(x) for w, x in trk.items()}
ZERO = (np.zeros(N), np.zeros(N), np.zeros(N))

# ============================================================== per-frame pre-pass
rnd = random.Random(7)
BLINK = {}
for w in art.CHARS:
    BLINK[w] = {}
    f = rnd.randrange(15, 70)
    while f < N:
        for k, v in ((0, 1), (1, 2), (2, 2), (3, 1)):
            BLINK[w][f + k] = v
        f += rnd.randrange(65, 150)


def line_at(t):
    for i, (a, b) in enumerate(times):
        if a - 0.05 <= t <= b + 0.05:
            return i
    return None


def target_pos(name, who, states, t):
    """world point a character looks at"""
    if name in states and states[name] is not None:
        st = states[name]
        T, hy = geom(st, name)
        return st["x"], hy
    st = states.get(who)
    if st is None:
        return None
    T, hy = geom(st, who)
    if name == "front" or name == "*":
        return st["x"], hy + 40
    if name in ("down", "book", "phone"):
        return st["x"] + 60, hy + 600
    if name == "up":
        return st["x"] - 100, hy - 600
    if name == "door":
        sc = SC[scene_at(t)]
        return sc["set"]["door"]["x"], hy
    return None


def shot_at(t, states):
    """camera (cx, cy, z) from shot directive"""
    si = scene_at(t)
    sc = SC[si]
    present = [w for w, s in states.items() if s is not None and s["alpha"] > 0.2]

    def frame(ws, zmax=1.75):
        pts = []
        for w in ws:
            st = states.get(w)
            if st is None:
                continue
            T, hy = geom(st, w)
            pts.append((st["x"], hy, st["s"]))
        if not pts:
            return 540, 960, 1.0
        x0 = min(p[0] - 260 * p[2] for p in pts)
        x1 = max(p[0] + 260 * p[2] for p in pts)
        y0 = min(p[1] - 300 * p[2] for p in pts)
        cx = (x0 + x1) / 2
        z = clamp(1080 / max(x1 - x0, 1), 1.0, zmax)
        h = 1920 / z
        cy = y0 + h * 0.28  # heads in upper third, below the title zone
        return cx, cy, z

    i = line_at(t)
    if i is None:  # between lines: keep previous line's shot during short gaps, wide during actions
        prev = [k for k, (a, b) in enumerate(times) if b <= t]
        if prev and t - times[prev[-1]][1] < 0.6 and LINES[prev[-1]]["scene"] == si:
            i = prev[-1]
        else:
            return (*frame(present, 1.15)[:2], 1.0 if len(present) > 2 else frame(present, 1.15)[2])
    l = LINES[i]
    a, b = times[i]
    shot = l.get("shot", "auto")
    sp = l["who"]
    if l.get("give") and shot == "auto":
        shot = "two:" + l["give"]["to"]
    if states.get(sp) is None and not shot.startswith(("close:", "two:", "punch:")):
        shot = "wide"  # narrator / off-screen voice
    to = l.get("to")
    if shot == "auto":
        k = sum(1 for j in range(i) if LINES[j]["scene"] == si)
        if k == 0:
            shot = "wide"
        elif l.get("joke"):
            shot = "punch"
        elif to and to in present and k % 3 == 2:
            shot = "two"
        else:
            shot = "close"
    if shot == "wide":
        cx, cy, z = frame(present, 1.15)
        z = lerp(z, z * 1.06, (t - a) / max(b - a, 0.1))
        return cx, cy, z
    if shot == "group":
        cx, cy, z = frame(present, 1.4)
        return cx, cy, lerp(z, z * 1.05, (t - a) / max(b - a, 0.1))
    if shot.startswith("two"):
        other = shot.split(":")[1] if ":" in shot else (to if to in present else None)
        ws = [sp] + ([other] if other else [])
        cx, cy, z = frame(ws, 1.6)
        return cx, cy, lerp(z, z * 1.05, (t - a) / max(b - a, 0.1))
    if shot.startswith("close") or shot.startswith("punch"):
        who = shot.split(":")[1] if ":" in shot else sp
        cx, cy, z = frame([who], 2.2)
        z = min(z, 2.0)
        me = states.get(who)
        if me is not None:  # avoid a foreground character blocking the close-up
            for o, so in states.items():
                if o != who and so is not None and so["foot"] > me["foot"] + 20 and abs(so["x"] - me["x"]) < 330:
                    cx += (1 if me["x"] > so["x"] else -1) * 90
        if shot.startswith("punch"):
            z = lerp(z * 0.85, z * 1.05, ease((t - a) / 0.35))
        else:
            z = lerp(z * 0.95, z, (t - a) / max(b - a, 0.1))
        return cx, cy, z
    return frame(present, 1.15)


look_cur = {}
last_tgt = {}
last_emo = {}
FR = []
cam_prev = None
for fr in range(N):
    t = fr / FPS
    si = scene_at(t)
    states = {w: char_state(w, t) for w in TR}
    li = line_at(t)
    ch = {}
    for w, st in states.items():
        if st is None:
            continue
        T, hy = geom(st, w)
        s = st["s"]
        phase = st["dist"] / (STEP * s / 0.75) * math.pi
        emo, _pe, tce = at(EMO, w, t, "calm")
        if emo in ("surprised", "laugh", "angry") and 0 <= t - tce < 0.3:  # squash & stretch pop on strong reactions
            T -= 16 * s * math.sin(math.pi * (t - tce) / 0.3)
            hy -= 16 * s * math.sin(math.pi * (t - tce) / 0.3)
        lname = at(LOOK, w, t, "*")[0]
        if st["walking"]:
            tp = (st["x"] + 400 * st["dir"], hy)
        else:
            if lname == "*":
                spk = LINES[li]["who"] if li is not None else None
                lname = spk if spk and spk != w else "front"
            tp = target_pos(lname, w, states, t) or (st["x"], hy)
        lx = clamp((tp[0] - st["x"]) / 260.0, -1, 1)
        ly = clamp((tp[1] - hy) / 420.0, -1, 1)
        if abs(lx) < 0.15 and lname not in ("front", "*"):
            lx = 0
        lc = look_cur.setdefault(w, [lx, ly])
        if w in last_tgt and abs(lx - last_tgt[w][0]) + abs(ly - last_tgt[w][1]) > 0.9:
            for k, v in ((0, 1), (1, 2), (2, 1)):
                BLINK[w].setdefault(fr + k, v)
        if w in last_emo and emo != last_emo[w]:
            for k, v in ((0, 1), (1, 1)):
                BLINK[w].setdefault(fr + k, v)
        last_tgt[w] = (lx, ly)
        last_emo[w] = emo
        lc[0] += (lx - lc[0]) * 0.5
        lc[1] += (ly - lc[1]) * 0.5
        env, zcr, hp = LIP.get(w, ZERO)[0][fr], LIP.get(w, ZERO)[1][fr], LIP.get(w, ZERO)[2][fr]
        speaking = li is not None and LINES[li]["who"] == w and env > 0.04
        q = 0 if env < 0.07 else min(5, 1 + int(env * 4.2))
        shape = 1 if zcr > 0.12 else 0
        face = 1 if lc[0] >= 0 else -1
        ang = EMO_TILT.get(emo, 0) * (-face)
        nod = 0
        if speaking:
            ang += 2.2 * math.sin(t * 1.9 + hash(w) % 7) + 9 * hp * face
        elif li is not None and LINES[li]["who"] != w:
            u = t - times[li][0]
            nod = max(0, math.sin(u * 3.2)) * (1 if int(u / 2.0) % 2 == 0 else 0) * 0.8
        if emo == "laugh":
            nod += abs(math.sin(t * 16)) * 0.6
        if st["walking"]:
            ang = 2 * math.sin(phase)
        # pose
        seated = st["mode"] != "stand" and st["stand"] < 0.5
        cur, prev, tc = at(POSE, w, t, "rest")
        if st["walking"]:
            cur, prev, tc = "walk", "walk", -9
        if prop_at(w, t) == "tray" and not seated:
            cur = "tray"
        def res(p):
            if p == "rest":
                return "rest_sofa" if seated else "rest_stand"
            return p if p in POSES else ("rest_sofa" if seated else "rest_stand")
        ch[w] = dict(x=st["x"], T=T, s=s, stand=st["stand"], mode=st["mode"], seat=st.get("seat"), foot=st["foot"],
                     walking=st["walking"], phase=phase, alpha=st["alpha"], emo=emo, q=q, shape=shape,
                     blink=BLINK[w].get(fr, 0), lx=round(lc[0] * 2) / 2, ly=round(lc[1] * 2) / 2, ang=ang, nod=nod,
                     face=face, pose=res(cur), prev=res(prev), tc=tc, prop=prop_at(w, t), t=t)
    cam = shot_at(t, states)
    if cam_prev is not None and cam_prev[3] == (li, si) and abs(cam[0] - cam_prev[0]) < 400:
        cam = (lerp(cam_prev[0], cam[0], 0.25), lerp(cam_prev[1], cam[1], 0.25), lerp(cam_prev[2], cam[2], 0.25))
    cam_prev = (*cam, (li, si))
    cap = None
    if li is not None:
        a, b = times[li]
    FR.append(dict(t=t, si=si, ch=ch, cam=cam[:3], li=li))
print("pre-pass done", flush=True)

# ============================================================== captions (one line at a time)
from playwright.sync_api import sync_playwright


def chunks(text, maxc=27):
    words = text.split()
    out, cur, hi = [], [], False

    def plain(ws):
        return len(" ".join(ws).replace("*", ""))
    for wd in words:
        if cur and (plain(cur + [wd]) > maxc or cur[-1].rstrip("*")[-1:] in ".!?"):
            line = " ".join(cur)
            if line.count("*") % 2:
                line += "*"
                hi = True
            else:
                hi = False
            out.append(line)
            cur = ["*" + wd if hi and not wd.startswith("*") else wd]
        else:
            cur.append(wd)
    out.append(" ".join(cur))
    if len(out) > 1 and len(out[-1].replace("*", "")) < 9 and len((out[-2] + out[-1]).replace("*", "")) <= 33 and out[-2][-1:] not in ".!?":
        out[-2:] = [out[-2] + " " + out[-1]]
    return out


CH = [chunks(l["roman"]) for l in LINES]
CAPT = []
for i, (a, b) in enumerate(times):
    ws = [len(c.replace("*", "")) + 4 for c in CH[i]]
    tot = sum(ws)
    acc = 0
    for j, wj in enumerate(ws):
        CAPT.append((a + (b - a) * acc / tot, i, j))
        acc += wj
FONT_B = "data:font/ttf;base64," + base64.b64encode(open(f"{HERE}/fonts/Poppins-Bold.ttf", "rb").read()).decode()
FONT_M = "data:font/ttf;base64," + base64.b64encode(open(f"{HERE}/fonts/Poppins-Medium.ttf", "rb").read()).decode()
css = f"@font-face{{font-family:P;src:url('{FONT_B}')}}@font-face{{font-family:M;src:url('{FONT_M}')}}body{{margin:0;background:transparent}}"


def hl(s):
    return "".join(f"<span style='color:#FFD54A'>{p}</span>" if k % 2 else p for k, p in enumerate(s.split("*")))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": OW, "height": 900})

    def png(html, out):
        pg.set_content(f"<html><head><style>{css}</style></head><body>{html}</body></html>")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        pg.locator("#c").screenshot(path=out, omit_background=True)
    seen = set()
    for i, l in enumerate(LINES):
        c = art.CHARS[l["who"]]
        nm = l.get("name", c["name"])
        if l["who"] not in seen and c.get("role") and "name" not in l:
            nm = f"{nm} &bull; {c['role']}"  # introduce each character the first time they speak
        seen.add(l["who"])
        for j, ln in enumerate(CH[i]):
            png(f"<div id=c style='width:{OW}px;text-align:center;padding:16px 0'>"
                f"<div style='font-family:P;font-size:32px;color:{c['color']};-webkit-text-stroke:7px #000;paint-order:stroke fill;text-shadow:0 3px 8px rgba(0,0,0,.8)'>{nm}</div>"
                f"<div style='font-family:P;font-size:60px;line-height:1.2;color:#fff;white-space:nowrap;-webkit-text-stroke:11px #000;paint-order:stroke fill;text-shadow:0 5px 14px rgba(0,0,0,.85)'>{hl(ln)}</div></div>",
                f"{WORK}/cap{i:02d}_{j}.png")
    series = EP.get("series", "Sindhi Ghar Ki Kahani")
    png(f"<div id=c style='width:{OW}px;text-align:center;padding:20px 0'><div style='display:inline-block;font-family:M;font-size:30px;color:#fff;background:#e0484f;border-radius:30px;padding:6px 26px 3px'>{series} &bull; Episode {EP.get('episode', 1)}</div>"
        f"<div style='font-family:P;font-size:74px;line-height:1.12;color:#FFD54A;-webkit-text-stroke:12px #000;paint-order:stroke fill;text-shadow:0 6px 18px #000;padding:14px 40px 10px'>{EP['title']}</div></div>", f"{WORK}/title.png")
    png(f"<div id=c style='width:{OW}px;text-align:center;padding:20px 0'><div style='display:inline-block;max-width:900px;font-family:P;font-size:54px;line-height:1.25;color:#fff;background:linear-gradient(135deg,#ff8a3d,#ff5e7e);border-radius:34px;padding:30px 44px;box-shadow:0 10px 40px rgba(0,0,0,.5)'>{EP.get('lesson', '')}</div>"
        f"<div style='font-family:M;font-size:40px;color:#fff;padding-top:34px;-webkit-text-stroke:6px #000;paint-order:stroke fill'>Roz nayi kahani ke liye <span style='color:#FFD54A'>Follow</span> karein!</div></div>", f"{WORK}/end.png")
    for si, s in enumerate(SC):
        if s.get("label"):
            png(f"<div id=c style='width:{OW}px;text-align:center;padding:10px 0'><div style='display:inline-block;font-family:M;font-size:34px;color:#fff;background:rgba(0,0,0,.55);border-radius:30px;padding:8px 28px 4px'>{s['label']}</div></div>", f"{WORK}/label{si}.png")
    b.close()
CAP = {(i, j): Image.open(f"{WORK}/cap{i:02d}_{j}.png").convert("RGBA") for i in range(len(LINES)) for j in range(len(CH[i]))}
TITLE = Image.open(f"{WORK}/title.png").convert("RGBA")
ENDC = Image.open(f"{WORK}/end.png").convert("RGBA")
LABEL = {si: Image.open(f"{WORK}/label{si}.png").convert("RGBA") for si, s in enumerate(SC) if s.get("label")}
VIG = Image.new("RGBA", (OW, OH), 0)
gy, gx = np.mgrid[0:OH, 0:OW]
va = np.sqrt(((gx - OW / 2) / (OW * 0.75)) ** 2 + ((gy - OH / 2) / (OH * 0.72)) ** 2)
VIG.putalpha(Image.fromarray((np.clip(va - 0.45, 0, 1) * 190).astype(np.uint8)))

# ============================================================== sound design
n = int(TOTAL * SR) + SR
tt = np.arange(n) / SR
rng = np.random.default_rng(5)
voice = np.zeros(n, np.float32)
for w, x in trk.items():
    voice[:len(x)] += x[:n]


def lp(x, k):
    return np.convolve(x, np.ones(k) / k, "same")


def place(buf, t0, s, g=1.0):
    i = int(t0 * SR)
    j = min(n, i + len(s))
    if 0 <= i < n:
        buf[i:j] += s[:j - i] * g


amb = np.zeros(n)
for s in SC:
    a, b = int(s["t0"] * SR), min(n, int((s["t1"] + (3.4 if s is SC[-1] else 0)) * SR))
    L_ = b - a
    if L_ <= 0:
        continue
    x = np.arange(L_) / SR
    room = lp(rng.standard_normal(L_), 300) * 0.25
    kind, time = s["set"]["amb"], s["time"]
    if time != "loadshedding" and kind in ("home", "kitchen", "city"):
        room += lp(rng.standard_normal(L_), 60) * (0.6 + 0.4 * np.sin(2 * np.pi * 4.2 * x)) * 0.06  # fan
    if time in ("night", "loadshedding"):
        room += (np.sin(2 * np.pi * 4300 * x) * (np.sin(2 * np.pi * 9.5 * x) > 0.55) * (np.sin(2 * np.pi * 0.31 * x) > 0.1)) * 0.008
    if time == "loadshedding":
        room += lp((np.sin(2 * np.pi * 98 * x) + 0.5 * np.sin(2 * np.pi * 196 * x)), 6) * 0.008
    if time == "day" and kind in ("outdoor", "street", "home"):
        for k in range(int(L_ / SR / 3)):  # birds
            c0 = rng.uniform(0, max(L_ / SR - 0.4, 0.1))
            d_ = np.arange(int(0.12 * SR)) / SR
            ch_ = np.sin(2 * np.pi * (3200 + 1800 * d_ / 0.12) * d_) * np.sin(np.pi * d_ / 0.12)
            i0 = int(c0 * SR)
            room[i0:i0 + len(ch_)] += ch_[:max(0, min(len(ch_), L_ - i0))] * 0.012
    if kind == "kitchen":
        room += lp(rng.standard_normal(L_), 3) * 0.010  # sizzle
    if kind in ("street", "city"):
        room += lp(rng.standard_normal(L_), 600) * 0.4
    amb[a:a + L_] += room
sfx = np.zeros(n)


def tone(f, d, a, decay=6):
    x = np.arange(int(d * SR)) / SR
    return np.sin(2 * np.pi * f * x) * np.exp(-x * decay) * a


def step():
    x = np.arange(int(0.12 * SR)) / SR
    return np.sin(2 * np.pi * 75 * x) * np.exp(-x * 40) * 0.3 + lp(rng.standard_normal(len(x)), 8) * np.exp(-x * 90) * 0.2


SFX = {
    "whoosh": lambda: lp(rng.standard_normal(int(0.45 * SR)), 10) * np.sin(np.linspace(0, np.pi, int(0.45 * SR))) * 0.12,
    "door": lambda: np.concatenate([lp(rng.standard_normal(int(0.25 * SR)), 30) * np.linspace(0.05, 0.02, int(0.25 * SR)), tone(70, 0.2, 0.3, 20)]),
    "ding": lambda: tone(1320, 0.8, 0.08, 4) + tone(1980, 0.8, 0.04, 5),
    "phone_ring": lambda: np.concatenate([(tone(1400, 0.4, 0.06, 0) + tone(1800, 0.4, 0.04, 0)) * (np.sin(2 * np.pi * 20 * np.arange(int(0.4 * SR)) / SR) > 0), np.zeros(int(0.25 * SR))] * 3),
    "notification": lambda: np.concatenate([tone(1760, 0.12, 0.07, 10), tone(2350, 0.3, 0.07, 8)]),
    "clink": lambda: sum(tone(2600 * m, 0.5, 0.05 / m, 9 + 4 * m) for m in (1, 1.51, 2.24)),
    "pressure_cooker": lambda: lp(rng.standard_normal(int(1.4 * SR)), 2) * np.sin(np.linspace(0, np.pi, int(1.4 * SR))) * 0.12 + tone(2900, 1.4, 0.05, 0.5),
    "bat_hit": lambda: np.pad(lp(rng.standard_normal(int(0.08 * SR)), 2) * np.exp(-np.arange(int(0.08 * SR)) / SR * 60) * 0.6, (0, int(0.15 * SR) - int(0.08 * SR))) + tone(900, 0.15, 0.2, 30),
    "sting": lambda: np.concatenate([tone(180, 0.09, 0.25, 30), tone(220, 0.09, 0.25, 30), lp(rng.standard_normal(int(0.5 * SR)), 1) * np.exp(-np.arange(int(0.5 * SR)) / SR * 7) * 0.12]),
    "boing": lambda: np.sin(2 * np.pi * np.cumsum(220 + 180 * np.sin(np.linspace(0, 18, int(0.5 * SR)))) / SR) * np.exp(-np.linspace(0, 4, int(0.5 * SR))) * 0.15,
    "crash": lambda: lp(rng.standard_normal(int(0.6 * SR)), 2) * np.exp(-np.arange(int(0.6 * SR)) / SR * 6) * 0.3 + sum(tone(f, 0.6, 0.04, 6) for f in (1800, 2500, 3300)),
    "knock": lambda: np.concatenate([tone(120, 0.08, 0.4, 40), np.zeros(int(0.12 * SR)), tone(120, 0.08, 0.4, 40), np.zeros(int(0.12 * SR)), tone(120, 0.08, 0.4, 40)]),
    "baby_giggle": lambda: np.concatenate([tone(700 + 80 * k, 0.09, 0.05, 15) for k in range(4)]),
    "tv": lambda: lp(rng.standard_normal(int(2 * SR)), 4) * 0.02,
    "rain": lambda: lp(rng.standard_normal(int(6 * SR)), 2) * 0.05,
    "bike": lambda: lp(np.sign(np.sin(2 * np.pi * 45 * np.arange(int(2 * SR)) / SR)), 20) * np.sin(np.linspace(0, np.pi, int(2 * SR))) * 0.06,
    "light_on": lambda: lp(rng.standard_normal(500), 2) * np.linspace(0.35, 0, 500),
    "cash": lambda: np.concatenate([tone(2200, 0.1, 0.08, 20), tone(3300, 0.5, 0.07, 6)]),
}
for (t0, name) in EVT:
    if name in SFX:
        place(sfx, t0, SFX[name]())
prev = {}
for fr, F in enumerate(FR):
    for w, c in F["ch"].items():
        if c["walking"]:
            s_ = int(c["phase"] / math.pi)
            if prev.get(w) is not None and s_ != prev[w]:
                place(sfx, F["t"], step(), 0.7 * c["alpha"])
            prev[w] = s_
        else:
            prev[w] = None
place(sfx, 0.0, SFX["whoosh"](), 1.0)
place(sfx, T_END + 0.3, tone(880, 2, 0.05, 2.2) + tone(1318.5, 2, 0.03, 2.2))


def pluck(f, d=0.9):
    m = int(SR / f)
    buf = rng.uniform(-1, 1, m)
    out = np.zeros(int(d * SR))
    for i in range(len(out)):
        out[i] = buf[i % m]
        buf[i % m] = 0.996 * 0.5 * (buf[i % m] + buf[(i + 1) % m])
    return out * np.exp(-np.arange(len(out)) / SR * 2.5)


MOOD = EP.get("music", "happy")
NOTES = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.0, "A": 440.0, "B": 493.88, "c": 523.25, "d": 587.33, "e": 659.25}
MEL = {"happy": ("E G A G E D C D E G E D C D C - E G A c A G E G A G E D C D C -", 96),
       "comic": ("C - E - G - E - F - A - G - E - D - F - E - C - D - G - C - - -", 128),
       "calm": ("E - - G - - A - - G - - E - - D - - C - - D - - E - - - - - - -", 76),
       "tense": ("A - A - c - A - G - G - A - - - A - A - c - d - c - A - - - - -", 110)}
mel, bpm = MEL.get(MOOD, MEL["happy"])
mel = mel.split()
PL = {k: pluck(v) for k, v in NOTES.items()}
mus = np.zeros(n)
beat = 60 / bpm / 2
for k in range(int(TOTAL / beat)):
    nt = mel[k % len(mel)]
    if nt != "-":
        place(mus, k * beat, PL[nt], 0.2 if k % 4 == 0 else 0.14)
chords = [(130.81, 164.81, 196.0), (110.0, 130.81, 164.81), (87.31, 110.0, 130.81), (98.0, 123.47, 146.83)]
for k in range(int(TOTAL / 2.5) + 1):
    a0 = int(k * 2.5 * SR)
    a1 = min(a0 + int(2.5 * SR), n)
    s_ = np.arange(a1 - a0) / SR
    w_ = np.minimum(1, np.minimum(s_ / 0.8, (2.5 - s_) / 0.8))
    mus[a0:a1] += sum(np.sin(2 * np.pi * f * s_) for f in chords[k % 4]) * w_ * 0.03
venv = lp(np.abs(voice), 4410)
venv = np.clip(venv / (venv.max() + 1e-6) * 4, 0, 1)
duck = (0.5 - 0.36 * venv) * np.where(tt > T_END, 1.7, 1)
mix = voice + amb * 0.9 + sfx + mus * duck
mix *= np.clip(tt / 0.3, 0, 1) * np.clip((TOTAL - tt) / 1.2, 0, 1)
mix = mix[:int(TOTAL * SR)]
with wave.open(f"{WORK}/mix.wav", "wb") as w_:
    w_.setnchannels(1)
    w_.setsampwidth(2)
    w_.setframerate(SR)
    w_.writeframes((np.clip(mix / max(1, np.abs(mix).max() / 0.95), -1, 1) * 32767).astype("<i2").tobytes())
print("audio ready", flush=True)

# ============================================================== drawing a character
TOONS = {}


def toon(w):
    if w not in TOONS:
        TOONS[w] = art.Toon(w)
    return TOONS[w]


SCALED = {}


def scaled(img, key, s):
    k = (key, round(s, 3))
    if k not in SCALED:
        SCALED[k] = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)
        if len(SCALED) > 400:
            SCALED.pop(next(iter(SCALED)))
    return SCALED[k]


def ik(sx, sy, hx, hy, a, b, side):
    dx, dy = hx - sx, hy - sy
    dd = clamp(math.hypot(dx, dy), abs(a - b) + 1, a + b - 1)
    th = math.atan2(dy, dx)
    al = math.acos(clamp((a * a + dd * dd - b * b) / (2 * a * dd), -1, 1))
    best = None
    for sg in (1, -1):
        ex, ey = sx + a * math.cos(th + sg * al), sy + a * math.sin(th + sg * al)
        sc = side * (ex - sx) + 0.6 * (ey - sy)
        if best is None or sc > best[0]:
            best = (sc, ex, ey)
    return best[1], best[2], sx + dd * math.cos(th), sy + dd * math.sin(th)


def pose_pts(p, c, t):
    nb, fb, fl = POSES[p]
    s, face = c["s"], c["face"]
    (nx, ny), (fx, fy) = nb, fb
    if "walk" in fl:
        sw = math.sin(c["phase"]) * 28
        nx += sw
        fx += sw
    if "wave" in fl:
        nx += 26 * math.sin(t * 10)
        ny += 8 * math.sin(t * 20)
    if "wag" in fl:
        nx += 13 * math.sin(t * 15)
    if "jump" in fl:
        ny += 14 * math.sin(t * 12)
        fy += 14 * math.sin(t * 12 + 0.5)
    if "clap" in fl:
        o = 25 * abs(math.sin(t * 9))
        nx += o
        fx -= o
    if "explain" in fl:
        nx += 18 * math.sin(t * 3)
        fy += 12 * math.sin(t * 3 + 1)
    return (face * nx * s, ny * s), (face * fx * s, fy * s), fl


def hands(c, t):
    pn, pf, _ = pose_pts(c["prev"], c, t)
    cn, cf, fl = pose_pts(c["pose"], c, t)
    u = back((t - c["tc"]) / 0.38) if c["prev"] != c["pose"] else 1
    mix_ = lambda p, q: (lerp(p[0], q[0], u), lerp(p[1], q[1], u))
    return mix_(pn, cn), mix_(pf, cf), (fl if u > 0.5 else POSES[c["prev"]][2])


def draw_char(cv, ox, oy, w, c):
    tn = toon(w)
    C = art.CHARS[w]
    d = ImageDraw.Draw(cv)
    x, T, s = c["x"], c["T"], c["s"]
    hs = C.get("hs", 1.0)
    q = lambda X, Y: ((X - ox) * K, (Y - oy) * K)
    lw = lambda v: max(1, int(v * K * s))
    pants = C["pants"]
    seated = c["mode"] != "stand" and c["stand"] < 0.5
    hip = T + 500 * s
    if not seated:  # contact shadow on the floor
        sha = Image.new("RGBA", cv.size, 0)
        ImageDraw.Draw(sha).ellipse([*q(x - 150 * s, c["foot"] + 4 * s), *q(x + 150 * s, c["foot"] + 44 * s)], fill=(0, 0, 0, 70))
        cv.alpha_composite(sha.filter(ImageFilter.GaussianBlur(max(1, int(10 * s * K)))))
    if not seated:  # standing legs
        st = c["stand"] if c["mode"] != "stand" else 1
        for i, sd in enumerate((-1, 1)):
            lift = max(0, math.sin(c["phase"] + i * math.pi)) if c["walking"] else 0
            hx, hy = x + sd * 52 * s, hip - 10 * s
            Ln = 370 * s * max(st, 0.3)
            fx_, fy_ = hx + sd * 8 * s, hy + Ln - 42 * s * lift
            kx, ky = (hx + fx_) / 2 + sd * (10 + 14 * lift) * s, (hy + fy_) / 2 - 10 * s * lift
            for col, wd in ((OUT, 82), (pants, 72)):
                d.line([q(hx, hy), q(kx, ky), q(fx_, fy_)], fill=col, width=lw(wd), joint="curve")
            d.ellipse([*q(fx_ - 46 * s + sd * 6 * s, fy_ - 12 * s), *q(fx_ + 46 * s + sd * 6 * s, fy_ + 28 * s)],
                      fill=(110, 70, 40) if not C.get("toddler") else (230, 230, 240), outline=OUT, width=lw(4))
    else:  # seated: shins down to the floor (lap drawn after the torso)
        if c["mode"] == "sofa":
            for sd in (-1, 1):
                fx_ = x + sd * 85 * s
                for col, wd in ((OUT, 80), (pants, 70)):
                    d.line([q(x + sd * 85 * s, hip + 40 * s), q(fx_, c["foot"] - 20 * s)], fill=col, width=lw(wd))
                d.ellipse([*q(fx_ - 46 * s, c["foot"] - 34 * s), *q(fx_ + 46 * s, c["foot"] + 6 * s)],
                          fill=(110, 70, 40) if not C.get("toddler") else (230, 230, 240), outline=OUT, width=lw(4))
    body = scaled(tn.body, ("body", w), s)
    p0 = q(x - 260 * s, T - 40 * s)
    cv.alpha_composite(body, (int(p0[0]), int(p0[1])))
    if seated:  # lap / knees towards camera
        d.rounded_rectangle([*q(x - 172 * s, hip - 70 * s), *q(x + 172 * s, hip + 80 * s)], lw(70), fill=pants, outline=OUT, width=lw(5))
        d.line([q(x, hip - 50 * s), q(x, hip + 70 * s)], fill=art.shade(pants, 0.8), width=lw(5))
        if c["mode"] != "sofa":
            for sd in (-1, 1):
                d.ellipse([*q(x + sd * 170 * s - 44 * s, hip + 30 * s), *q(x + sd * 170 * s + 44 * s, hip + 76 * s)], fill=(110, 70, 40), outline=OUT, width=lw(4))
    hi = tn.head(c["emo"], c["q"], c["shape"], c["blink"], c["lx"], c["ly"])
    hi = scaled(hi, ("head", w, c["emo"], c["q"], c["shape"], c["blink"], c["lx"], c["ly"]), s * hs)
    ang = c["ang"]
    if abs(ang) > 0.2:
        hi = hi.rotate(ang, resample=Image.BICUBIC, center=(210 * K * s * hs, 455 * K * s * hs))
    neck = (x + c["lx"] * 4 * s, T + 90 * s + c["nod"] * 7 * s)
    p0 = q(neck[0] - 210 * s * hs, neck[1] - 455 * s * hs)
    cv.alpha_composite(hi, (int(p0[0]), int(p0[1])))
    sleeve = C["shirt"]
    fore = C["skin"] if C["sleeve"] == "short" else sleeve
    nh, fh, fl = hands(c, c["t"])
    face = c["face"]
    for nm, (rx, ry), sd in (("far", fh, -face), ("near", nh, face)):
        sx, sy = x + sd * 136 * s, T + 82 * s
        hx, hy = x + rx, T + ry
        ex, ey, hx, hy = ik(sx, sy, hx, hy, 178 * s, 172 * s, sd)
        for col, wd in ((OUT, 60), (sleeve, 52)):
            d.line([q(sx, sy), q(ex, ey)], fill=col, width=lw(wd))
        d.ellipse([*q(ex - 26 * s, ey - 26 * s), *q(ex + 26 * s, ey + 26 * s)], fill=sleeve)
        for col, wd in ((OUT, 50), (fore, 42)):
            d.line([q(ex, ey), q(hx, hy)], fill=col, width=lw(wd))
        if C["sleeve"] == "short":
            d.line([q(ex, ey), q(ex + (hx - ex) * 0.2, ey + (hy - ey) * 0.2)], fill=sleeve, width=lw(50))
        fing = ("finger" in fl and nm == "near") or ("farfinger" in fl and nm == "far")
        if fing:
            ux, uy = hx - ex, hy - ey
            m = math.hypot(ux, uy) or 1
            ux, uy = ux / m, uy / m
            if "wag" in fl:
                ux, uy = 0, -1
            for col, wd in ((OUT, 22), (C["skin"], 14)):
                d.line([q(hx, hy), q(hx + ux * 46 * s, hy + uy * 46 * s)], fill=col, width=lw(wd))
        if nm == "near" and c.get("prop") and c["prop"] != "tray":
            art.draw_prop(d, c["prop"], q, hx, hy, s, c["t"])
        if nm == "near" and c.get("prop") == "tray":
            ty = hy - 14 * s
            d.rounded_rectangle([*q(x - 120 * s, ty), *q(x + 120 * s, ty + 20 * s)], lw(8), fill=(190, 190, 200), outline=OUT, width=lw(4))
            for cx_ in (x - 55 * s, x + 15 * s):
                d.rounded_rectangle([*q(cx_ - 25 * s, ty - 58 * s), *q(cx_ + 25 * s, ty)], lw(8), fill=(250, 250, 250), outline=OUT, width=lw(4))
                d.ellipse([*q(cx_ - 23 * s, ty - 64 * s), *q(cx_ + 23 * s, ty - 50 * s)], fill=(170, 100, 50))
        r = (29 if not fing else 26) * s
        d.ellipse([*q(hx - r, hy - r), *q(hx + r, hy + r)], fill=C["skin"], outline=OUT, width=lw(4))


# ============================================================== frame renderer
def render(fr):
    F = FR[fr]
    t = F["t"]
    sc = SC[F["si"]]
    world = sc["bg"].copy().convert("RGBA")
    sc["set"]["anim"](world, t)
    fg = Image.new("RGBA", (WW, WH), 0)
    order = sorted(F["ch"].items(), key=lambda kv: kv[1]["foot"])
    for w, c in order:
        s = c["s"]
        ox, oy = c["x"] - 460 * s, c["T"] - 480 * s
        cw, chh = int(920 * s * K), int(1500 * s * K)
        cv = Image.new("RGBA", (cw, chh), 0)
        draw_char(cv, ox, oy, w, c)
        if c["alpha"] < 1:
            cv.putalpha(cv.getchannel("A").point(lambda v: int(v * c["alpha"])))
        fg.alpha_composite(cv, (int(ox * K), int(oy * K)))
    if sc["set"].get("front") is not None:
        fg.alpha_composite(sc["set"]["front"])
    fg = SETS.mult(fg, sc["set"]["lm"])
    world.alpha_composite(fg)
    if sc["set"].get("glow") is not None and sc["time"] == "loadshedding":
        world.alpha_composite(sc["set"]["glow"])
    cx, cy, z = F["cam"]
    z = max(z, 1.0)  # never zoom out past the set edges
    w_, h_ = 1080 / z, 1920 / z
    x0, y0 = clamp(cx - w_ / 2, 0, 1080 - w_), clamp(cy - h_ / 2, 0, 1920 - h_)
    out = world.crop((int(x0 * K), int(y0 * K), int((x0 + w_) * K), int((y0 + h_) * K))).resize((OW, OH), Image.BICUBIC)
    out.alpha_composite(VIG)
    # scene transition flash
    for s in SC[1:]:
        if 0 <= t - s["t0"] < 0.25:
            a = int(255 * (1 - (t - s["t0"]) / 0.25))
            out.alpha_composite(Image.new("RGBA", (OW, OH), (255, 255, 255, a)))
    lab_t = t - sc["t0"] - (2.8 if F["si"] == 0 else 0)
    if F["si"] in LABEL and 0 <= lab_t < 1.8:
        lab = LABEL[F["si"]]
        out.alpha_composite(lab, ((OW - lab.width) // 2, 140))
    if t < 2.8:
        u = t / 0.5
        scl = back(u) if u < 1 else 1
        al = clamp((2.8 - t) / 0.4, 0, 1)
        ti = TITLE.resize((max(1, int(TITLE.width * scl)), max(1, int(TITLE.height * scl))), Image.BICUBIC) if scl != 1 else TITLE
        if al < 1:
            ti = ti.copy()
            ti.putalpha(ti.getchannel("A").point(lambda v: int(v * al)))
        out.alpha_composite(ti, ((OW - ti.width) // 2, 200 - (ti.height - TITLE.height) // 2))
    if t < T_END:
        cur = None
        for (s0, i, j) in CAPT:
            a_, b_ = times[i]
            if s0 - 0.1 <= t <= b_ + 0.25:
                cur = (s0, i, j)
        if cur:
            s0, i, j = cur
            a = clamp((t - s0 + 0.1) / 0.12, 0, 1)
            cp = CAP[(i, j)]
            if a < 1:
                cp = cp.copy()
                cp.putalpha(cp.getchannel("A").point(lambda v: int(v * a)))
            out.alpha_composite(cp, ((OW - cp.width) // 2, int(1650 - cp.height + (1 - a) * 30)))
    else:
        a = clamp((t - T_END) / 0.6, 0, 1)
        out.alpha_composite(Image.new("RGBA", (OW, OH), (0, 0, 0, int(120 * a))))
        ec = ENDC
        if a < 1:
            ec = ec.copy()
            ec.putalpha(ec.getchannel("A").point(lambda v: int(v * a)))
        out.alpha_composite(ec, ((OW - ec.width) // 2, int(300 + (1 - a) * 40)))
    return out.convert("RGB").tobytes()


def worker(args):
    k, a, b = args
    ff = subprocess.Popen(f'ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s {OW}x{OH} -r {FPS} -i - -c:v libx264 -preset veryfast -crf 19 -pix_fmt yuv420p "{WORK}/part{k}.mp4"',
                          shell=True, stdin=subprocess.PIPE)
    for fr in range(a, b):
        ff.stdin.write(render(fr))
        if (fr - a) % 300 == 0:
            print(f"worker {k}: {fr - a}/{b - a}", flush=True)
    ff.stdin.close()
    ff.wait()
    return k


if __name__ == "__main__":
    if os.environ.get("PREVIEW"):
        for ts in map(float, os.environ["PREVIEW"].split(",")):
            fr = min(N - 1, int(ts * FPS))
            Image.frombytes("RGB", (OW, OH), render(fr)).save(f"{WORK}/pv_{ts:05.1f}.png")
        print("preview saved in", WORK)
        sys.exit()
    NP = int(os.environ.get("PROCS", "2"))
    cuts = [N * k // NP for k in range(NP + 1)]
    with Pool(NP) as pool:
        pool.map(worker, [(k, cuts[k], cuts[k + 1]) for k in range(NP)])
    open(f"{WORK}/parts.txt", "w").write("".join(f"file 'part{k}.mp4'\n" for k in range(NP)))
    sh(f'ffmpeg -v error -y -f concat -safe 0 -i "{WORK}/parts.txt" -i "{WORK}/mix.wav" -map 0:v -map 1:a -c:v copy '
       f'-af loudnorm=I=-14:TP=-1.5:LRA=11 -ar 44100 -c:a aac -b:a 192k -shortest -movflags +faststart "{OUTFILE}"')
    print("done", OUTFILE, round(TOTAL, 1), flush=True)
