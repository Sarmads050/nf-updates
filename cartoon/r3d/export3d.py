"""Low-poly 3D pipeline, step 1: run the 2D engine's pre-pass (timing, acting, lip-sync, captions, audio mix)
and export a per-frame timeline for the three.js renderer.
usage: python cartoon/r3d/export3d.py episodes/epNNN.json <voice_dir> <work_dir>"""
import os, sys, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
EPJ, VO, WORK = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(WORK, exist_ok=True)
# engine derives its work dir from the output file name: <out>_work
sys.argv = ["engine.py", EPJ, VO, WORK[:-5] + ".mp4" if WORK.endswith("_work") else WORK + "/x.mp4"]
sys.path.insert(0, os.path.dirname(HERE))
import engine as E  # noqa: E402  (runs the whole pre-pass)

art = E.art


def seg_at(who, t):
    segs = E.TR.get(who, [])
    cur, idx = None, -1
    for k, sg in enumerate(segs):
        if sg[0] <= t:
            cur, idx = sg, k
        else:
            break
    return cur, idx


def slot_of(who, idx, step):
    """nearest slot name before/after a segment index (step -1 / +1)"""
    segs = E.TR.get(who, [])
    k = idx + step
    while 0 <= k < len(segs):
        if segs[k][1] in ("at", "sit", "rise"):
            return segs[k][2]["slot"]
        if segs[k][1] == "off":
            return None
        k += step
    return None


def shot_info(t, states):
    """same decisions as engine.shot_at, but returns the shot kind + who is framed (3D does its own framing)"""
    si = E.scene_at(t)
    present = [w for w, s in states.items() if s is not None and s["alpha"] > 0.2]
    i = E.line_at(t)
    if i is None:
        prev = [k for k, (a, b) in enumerate(E.times) if b <= t]
        if prev and t - E.times[prev[-1]][1] < 0.6 and E.LINES[prev[-1]]["scene"] == si:
            i = prev[-1]
        else:
            return dict(kind="wide", ws=present, u=0, key=f"gap{si}")
    l = E.LINES[i]
    a, b = E.times[i]
    u = max(0.0, min(1.0, (t - a) / max(b - a, 0.1)))
    shot = l.get("shot", "auto")
    sp = l["who"]
    to = l.get("to")
    if l.get("give") and shot == "auto":
        shot = "two:" + l["give"]["to"]
    if states.get(sp) is None and not shot.startswith(("close:", "two:", "punch:")):
        shot = "wide"
    if shot == "auto":
        k = sum(1 for j in range(i) if E.LINES[j]["scene"] == si)
        shot = "wide" if k == 0 else "punch" if l.get("joke") else "two" if (to and to in present and k % 3 == 2) else "close"
    kind = shot.split(":")[0]
    if kind in ("wide", "group"):
        ws = present
    elif kind == "two":
        other = shot.split(":")[1] if ":" in shot else (to if to in present else None)
        ws = [sp] + ([other] if other else [])
    else:
        ws = [shot.split(":")[1] if ":" in shot else sp]
    ws = [w for w in ws if states.get(w) is not None] or present
    return dict(kind=kind, ws=ws, u=round(u, 3), key=f"{i}", t_in=round(t - a, 3))


# ---- visemes from each speaker's voice track: open (jaw), wide (+ee / -oo), fric (s/sh/f: teeth)
import numpy as np  # noqa: E402
VIS = {}
hop = E.SR // E.FPS
win = np.hanning(2048)
fq = np.fft.rfftfreq(2048, 1 / E.SR)
bands = [(fq >= a) & (fq < b) for a, b in ((250, 900), (900, 1700), (1700, 3200), (3500, 8000))]
for w, x in E.trk.items():
    env = E.LIP[w][0]
    vo, vw, vf = np.zeros(E.N), np.zeros(E.N), np.zeros(E.N)
    o_s = w_s = f_s = 0.0
    for i in range(E.N):
        c = i * hop + hop // 2
        seg = x[max(0, c - 1024):c + 1024]
        e = float(env[i])
        if len(seg) == 2048 and e > 0.06:
            sp = np.abs(np.fft.rfft(seg * win)) ** 2
            B = [float(sp[m].sum()) + 1e-9 for m in bands]
            tot = sum(B)
            b1, b2, b3, b4 = (v / tot for v in B)
            o = min(1.0, e * 0.95) * (0.55 + 0.9 * b1)
            wd = max(-1.0, min(1.0, (b3 - b2) * 3.2 + 0.15))
            f = max(0.0, min(1.0, (b4 - 0.18) * 3.0))
        else:
            o, wd, f = 0.0, w_s * 0.6, 0.0
        o_s += (o - o_s) * (0.7 if o > o_s else 0.45)
        w_s += (wd - w_s) * 0.45
        f_s += (f - f_s) * 0.5
        vo[i], vw[i], vf[i] = o_s, w_s, f_s
    VIS[w] = (vo, vw, vf)

frames = []
for fr, F in enumerate(E.FR):
    t = F["t"]
    states = {w: E.char_state(w, t) for w in E.TR}
    ch = {}
    for w, c in F["ch"].items():
        sg, idx = seg_at(w, t)
        kind, kw = sg[1], sg[2]
        d = dict(emo=c["emo"], q=c["q"], sh=c["shape"], bl=c["blink"], lx=c["lx"], ly=c["ly"], face=c["face"],
                 ang=round(c["ang"], 2), nod=round(c["nod"], 3), pose=c["pose"], prev=c["prev"], tc=round(c["tc"], 3),
                 prop=c["prop"], al=round(c["alpha"], 3), sl=round(c.get("sleep", 0), 3), st=round(c["stand"], 3))
        lk = E.at(E.LOOK, w, t, "*")[0]
        if lk == "*":
            spk = E.LINES[F["li"]]["who"] if F["li"] is not None else None
            lk = spk if spk and spk != w else "front"
        d["lk"] = lk
        if w in VIS:
            d.update(vo=round(float(VIS[w][0][fr]), 2), vw=round(float(VIS[w][1][fr]), 2), vf=round(float(VIS[w][2][fr]), 2))
        if kind == "walk":
            u = max(0.0, min(1.0, (t - sg[0]) / kw["dur"]))
            d.update(m="walk", u=round(u, 3), fi=bool(kw.get("fade_in")), fo=bool(kw.get("fade_out")),
                     src=slot_of(w, idx, -1), dst=slot_of(w, idx, +1), ph=round(c["phase"], 3))
        else:
            d.update(m=kind, slot=kw.get("slot"))
            if kind in ("sit", "rise"):
                d["u"] = round(max(0.0, min(1.0, (t - sg[0]) / kw["dur"])), 3)
        ch[w] = d
    cam = shot_info(t, states)
    frames.append(dict(t=round(t, 3), si=F["si"], li=F["li"], ch=ch, cam=cam))

talk = {}  # who is speaking per line
out = dict(
    fps=E.FPS, n=E.N, total=E.TOTAL, t_end=E.T_END,
    scenes=[dict(set=s["name"], time=s["time"], t0=s["t0"], t1=s.get("t1"), label=s.get("label"),
                 sleepers=[w for w, ev in E.SLEEP.items() if any(e[3] == k for e in ev)]) for k, s in enumerate(E.SC)],
    lines=[dict(who=l["who"], to=l.get("to"), a=a, b=b, joke=bool(l.get("joke")), scene=l["scene"], shot=l.get("shot", "auto"))
           for l, (a, b) in zip(E.LINES, E.times)],
    chars={w: dict(skin=c["skin"], shirt=c["shirt"], pants=c["pants"], hair=c.get("hair"), hair_col=c.get("hair_col"),
                   cover=c.get("cover"), cover2=c.get("cover2"), shirt2=c.get("shirt2"), scale=c["scale"], hs=c.get("hs", 1.0),
                   age=c.get("age"), kameez=bool(c.get("kameez")), lashes=bool(c.get("lashes")), earrings=bool(c.get("earrings")),
                   grey=bool(c.get("grey_streak")), toddler=bool(c.get("toddler")))
           for w, c in art.CHARS.items() if w in E.TR},
    frames=frames,
)
fx = E.EP.get("fx3d", {})
out["fx"] = dict(
    sneeze=[dict(who=E.LINES[(n if isinstance(n, int) else n[0]) - 1]["who"],
                 t=E.times[(n if isinstance(n, int) else n[0]) - 1][0] + (fx.get("sneeze_at", 0.3) if isinstance(n, int) else n[1]))
            for n in fx.get("sneeze", [])],
    sick=[dict(who=z["who"], t0=E.SC[E.LINES[z["from_line"] - 1]["scene"]]["t0"], t1=E.times[z["to_line"] - 1][0] + 0.4) for z in fx.get("sick", [])],
)
json.dump(out, open(f"{WORK}/frames3d.json", "w"), separators=(",", ":"))
print("exported", len(frames), "frames ->", f"{WORK}/frames3d.json", flush=True)
