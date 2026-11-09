"""Low-poly 3D pipeline: engine pre-pass -> three.js frames (headless Chromium) -> captions/title/end card -> mp4.
usage: python cartoon/r3d/render3d.py episodes/epNNN.json <voice_dir> <out.mp4>
env: PREVIEW=t1,t2 (still frames only)   THREE_JS=path/to/three.min.js (r160)"""
import os, sys, json, base64, io, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
EPJ, VO, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WORK = os.path.splitext(OUT)[0] + "_work"
sys.argv = [sys.argv[0], EPJ, VO, WORK]
import export3d as X  # noqa: E402  runs the engine pre-pass + writes frames3d.json
E = X.E
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OW, OH, FPS = E.OW, E.OH, E.FPS
data = json.load(open(f"{WORK}/frames3d.json"))


def overlays(out, t, si):
    """same captions / title / scene label / end card as the 2D engine"""
    sc = E.SC[si]
    for s in E.SC[1:]:
        if 0 <= t - s["t0"] < 0.25:
            out.alpha_composite(Image.new("RGBA", (OW, OH), (255, 255, 255, int(255 * (1 - (t - s["t0"]) / 0.25)))))
    lab_t = t - sc["t0"] - (2.8 if si == 0 else 0)
    if si in E.LABEL and 0 <= lab_t < 1.8:
        lab = E.LABEL[si]
        out.alpha_composite(lab, ((OW - lab.width) // 2, 140))
    if t < 2.8:
        u = t / 0.5
        scl = E.back(u) if u < 1 else 1
        al = E.clamp((2.8 - t) / 0.4, 0, 1)
        ti = E.TITLE.resize((max(1, int(E.TITLE.width * scl)), max(1, int(E.TITLE.height * scl))), Image.BICUBIC) if scl != 1 else E.TITLE
        if al < 1:
            ti = ti.copy()
            ti.putalpha(ti.getchannel("A").point(lambda v: int(v * al)))
        out.alpha_composite(ti, ((OW - ti.width) // 2, 200 - (ti.height - E.TITLE.height) // 2))
    if t < E.T_END:
        cur = None
        for (s0, i, j) in E.CAPT:
            a_, b_ = E.times[i]
            if s0 - 0.1 <= t <= b_ + 0.25:
                cur = (s0, i, j)
        if cur:
            s0, i, j = cur
            a = E.clamp((t - s0 + 0.1) / 0.12, 0, 1)
            cp = E.CAP[(i, j)]
            if a < 1:
                cp = cp.copy()
                cp.putalpha(cp.getchannel("A").point(lambda v: int(v * a)))
            out.alpha_composite(cp, ((OW - cp.width) // 2, int(1650 - cp.height + (1 - a) * 30)))
    else:
        a = E.clamp((t - E.T_END) / 0.6, 0, 1)
        out.alpha_composite(Image.new("RGBA", (OW, OH), (0, 0, 0, int(120 * a))))
        ec = E.ENDC
        if a < 1:
            ec = ec.copy()
            ec.putalpha(ec.getchannel("A").point(lambda v: int(v * a)))
        out.alpha_composite(ec, ((OW - ec.width) // 2, int(300 + (1 - a) * 40)))
    return out


with sync_playwright() as p:
    from page import open_page
    b, pg = open_page(p)
    pg.evaluate("d => LP.init(d)", data)

    def grab(fr):
        url = pg.evaluate(f"LP.frame({fr})")
        im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
        return overlays(im, data["frames"][fr]["t"], data["frames"][fr]["si"])

    if os.environ.get("PREVIEW"):
        for ts in map(float, os.environ["PREVIEW"].split(",")):
            fr = min(data["n"] - 1, int(ts * FPS))
            # warm up camera smoothing from a few frames earlier
            for k in range(max(0, fr - 4), fr):
                pg.evaluate(f"LP.frame({k})")
            grab(fr).convert("RGB").save(f"{WORK}/p3_{ts:05.1f}.png")
        print("preview saved in", WORK)
        sys.exit()
    a0 = int(os.environ.get("FROM", 0))
    a1 = int(os.environ.get("TO", data["n"]))
    part = f"{WORK}/video3d_{a0}_{a1}.mp4"
    ff = subprocess.Popen(f'ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s {OW}x{OH} -r {FPS} -i - -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p "{part}"',
                          shell=True, stdin=subprocess.PIPE)
    t0 = time.time()
    for fr in range(a0, a1):
        ff.stdin.write(grab(fr).convert("RGB").tobytes())
        if (fr - a0) % 150 == 0:
            el = time.time() - t0
            print(f"frame {fr}/{a1} {el:.0f}s", flush=True)
    ff.stdin.close()
    ff.wait()
    b.close()
    print("video part", part, flush=True)
