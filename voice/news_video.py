"""Sindhi news bulletin VIDEO: news channel jaisi screen (logo, LIVE, ghadi, tareekh, sarkhi, chalti patti, AI tasveerein)
+ bulletin ki awaz. Natija: voice/out/Sindhi_News_Bulletin.mp4"""
import datetime as dt
import html
import json
import os
import shutil
import subprocess
import tempfile
from urllib.parse import quote

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
W, H, FPS = 1280, 720, 25
RATE = 24000
LEAD, PAUSE = 4.0, 1.4  # voice_sample.py jaisa
TZ = dt.timezone(dt.timedelta(hours=5))
SD_MONTHS = ["جنوري", "فيبروري", "مارچ", "اپريل", "مئي", "جون", "جولاءِ", "آگسٽ", "سيپٽمبر", "آڪٽوبر", "نومبر", "ڊسمبر"]
SD_DAYS = ["سومر", "اڱارو", "اربع", "خميس", "جمعو", "ڇنڇر", "آچر"]
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or os.getenv("CHROME_BIN", "")
FONT_CSS = os.getenv("CARD_FONT_CSS", "") or \
    "@import url('https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@600;700&display=swap');"
CLOCK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TMP = tempfile.mkdtemp()


def log(*a):
    print(*a, flush=True)


def png(html_body, w, h, name, transparent=True):
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONT_CSS}
    html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{'transparent' if transparent else '#14213D'}}}
    *{{box-sizing:border-box}} body{{font-family:'Noto Naskh Arabic',serif;color:#fff}}
    </style></head><body><div style="position:relative;width:{w}px;height:{h}px;overflow:hidden">{html_body}</div></body></html>"""
    hp = os.path.join(TMP, name + ".html")
    out = os.path.join(TMP, name + ".png")
    open(hp, "w", encoding="utf-8").write(page)
    subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", f"--window-size={w},{h + 87}", "--virtual-time-budget=6000",
                    "--default-background-color=00000000", f"--screenshot={out}", "file://" + hp],
                   capture_output=True, timeout=120)
    from PIL import Image
    with Image.open(out) as im:
        im.crop((0, 0, w, h)).save(out)
    return out


def silences(x, min_len=0.25):
    """Awaz mein khamoshi ke tukre: [(beech ka waqt, lambai)]."""
    f = int(0.02 * RATE)
    n = len(x) // f
    rms = np.sqrt((x[:n * f].reshape(n, f) ** 2).mean(1))
    thr = max(0.012, np.percentile(rms, 20) * 1.6)
    quiet = rms < thr
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.02 >= min_len:
                out.append(((i + j) / 2 * 0.02, (j - i) * 0.02, i * 0.02))
            i = j
        else:
            i += 1
    return out


def boundaries(x, paras):
    """Ek hisse (chunk) mein khabron ke shuru ka asal waqt: anchor 'ٻي خبر' se pehle rukta hai, phir 'X خبر' keh kar
    dobara rukta hai — is jodi ki pehli khamoshi hi naya hissa. Na mile to andaze ke qareeb sab se lambi khamoshi."""
    dur = len(x) / RATE
    tot = sum(len(p) for p in paras)
    est, c = [], 0.0
    for p in paras[:-1]:
        c += dur * len(p) / tot
        est.append(c)
    sil = [s for s in silences(x) if s[1] >= 0.4]
    pairs = [(s1[0], s1[1]) for s1, s2 in zip(sil, sil[1:]) if 0.6 <= s2[0] - s1[0] <= 2.6]
    picks, last = [], 0.0
    for e in est:
        win = max(6.0, dur / len(paras) * 0.6)
        cand = [p for p in pairs if p[0] > last + 2 and abs(p[0] - e) <= win]
        if not cand:
            cand = [(s[0], s[1]) for s in sil if s[0] > last + 2 and abs(s[0] - e) <= win]
        t = min(cand, key=lambda p: abs(p[0] - e) - p[1])[0] if cand else e
        picks.append(t)
        last = t
    return [0.0] + picks + [dur]


def timing(paras):
    """Har paragraph (intro, 10 khabrein, aakhir) ka asal shuru/khatam waqt, awaz ki khamoshi se."""
    z = np.load(os.path.join(OUT, "voice_cache.npz"), allow_pickle=True)
    parts = list(z["parts"])
    groups = [paras[0:4], paras[4:7], paras[7:10], paras[10:]]
    spans, t = [], LEAD
    for g, x in zip(groups, parts):
        b = boundaries(x, g)
        for k in range(len(g)):
            spans.append((t + b[k], t + b[k + 1]))
        t += len(x) / RATE + PAUSE
    return spans


def image_for(prompt, i):
    import time
    path = os.path.join(TMP, f"img{i}.jpg")
    url = "https://image.pollinations.ai/prompt/" + quote(prompt + ", digital illustration, Sindh Pakistan, "
                                                                 "no text, no letters, cinematic light")
    for attempt in range(4):  # site busy ho to thoda ruk kar dobara
        try:
            r = requests.get(url, params={"width": 1280, "height": 720, "nologo": "true", "seed": 100 + i + attempt},
                             timeout=150, headers={"User-Agent": "Mozilla/5.0 NFUpdatesBot"})
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") and len(r.content) > 8000:
                open(path, "wb").write(r.content)
                log("image ok", i, "try", attempt + 1)
                time.sleep(3)
                return path
            log("image fail", i, r.status_code, r.headers.get("content-type", ""), len(r.content))
        except Exception as e:
            log("image error", i, str(e)[:120])
        time.sleep(8 * (attempt + 1))
    from PIL import Image, ImageDraw, ImageFilter  # na mile to saada rangeen pas-manzar
    rng = np.random.default_rng(i)
    im = Image.new("RGB", (1280, 720), tuple(int(x) for x in rng.integers(30, 90, 3)))
    d = ImageDraw.Draw(im)
    for _ in range(14):
        x, y, r_ = rng.integers(0, 1280), rng.integers(0, 720), rng.integers(80, 300)
        d.ellipse((x - r_, y - r_, x + r_, y + r_), fill=tuple(int(c) for c in rng.integers(60, 200, 3)))
    im.filter(ImageFilter.GaussianBlur(40)).save(path)
    return path


def main():
    paras = [p.strip() for p in open(os.path.join(HERE, "script_sd.txt"), encoding="utf-8").read().split("\n\n") if p.strip()]
    stories = json.load(open(os.path.join(HERE, "stories.json"), encoding="utf-8"))
    audio = os.path.join(OUT, "Sindhi_News_Bulletin.mp3")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
                               capture_output=True, text=True).stdout.strip())
    spans = timing(paras)
    now = dt.datetime.now(TZ)
    slot = ("صبح جو بليٽن" if now.hour < 11 else "منجهند جو بليٽن" if now.hour < 16 else
            "شام جو بليٽن" if now.hour < 20 else "رات جو بليٽن")
    date_sd = f"{SD_DAYS[now.weekday()]}، {now.day} {SD_MONTHS[now.month - 1]} {now.year}"
    logo = "file://" + os.path.join(HERE, "assets", "logo.png")
    E = html.escape

    # --- scenes: intro card, 10 khabrein, outro card
    scenes = [(0.0, spans[1][0], "intro")]
    for i in range(10):
        a = spans[i + 1][0]
        b = spans[i + 2][0] if i < 9 else spans[11][0]
        scenes.append((a, b, i))
    scenes.append((spans[11][0], dur, "outro"))

    title_css = """position:absolute;inset:0;background:linear-gradient(135deg,#14213D 0%,#1f2f57 60%,#7A1B1B 100%);
      display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;direction:rtl"""
    intro = png(f"""<div style="{title_css}"><img src="{logo}" style="width:230px;height:230px;border-radius:50%;
      border:6px solid #F4EFE6"><div style="font-size:64px;font-weight:700">سنڌي خبرنامو</div>
      <div style="font-size:40px;background:#B3261E;padding:4px 30px;border-radius:8px">{slot}</div>
      <div style="font-size:30px;opacity:.9">{date_sd}</div></div>""", W, H, "intro", False)
    outro = png(f"""<div style="{title_css}"><img src="{logo}" style="width:200px;height:200px;border-radius:50%;
      border:6px solid #F4EFE6"><div style="font-size:50px;font-weight:700">وڌيڪ خبرن لاءِ فالو ڪريو</div>
      <div style="font-family:Arial;font-weight:700;font-size:40px;direction:ltr;background:#F4EFE6;color:#14213D;
      padding:6px 26px;border-radius:40px">Naushahro Feroze Updates <span style="background:#1877F2;color:#fff;
      border-radius:30px;padding:2px 18px">+ Follow</span></div></div>""", W, H, "outro", False)

    # --- background video: har scene ka apna tukra (tasveer par halka zoom)
    segs = []
    for k, (a, b, kind) in enumerate(scenes):
        d = max(0.5, b - a)
        seg = os.path.join(TMP, f"seg{k}.mp4")
        if kind in ("intro", "outro"):
            src, vf = (intro if kind == "intro" else outro), f"scale={W}:{H},format=yuv420p"
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", src, "-vf", vf, "-r", str(FPS),
                            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", seg], check=True, capture_output=True)
        else:
            img = image_for(stories[kind]["img"], kind)
            frames = int(d * FPS) + 1
            vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                  f"zoompan=z='min(zoom+0.0007,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
                  "eq=brightness=-0.06:saturation=1.1,format=yuv420p")
            subprocess.run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264",
                            "-preset", "veryfast", seg], check=True, capture_output=True)
        segs.append(seg)
    lst = os.path.join(TMP, "list.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    bg = os.path.join(TMP, "bg.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg], check=True, capture_output=True)

    # --- screen ke hisse (PNG)
    frame = png(f"""
      <div style="position:absolute;top:0;left:0;right:0;height:120px;background:linear-gradient(to bottom,rgba(0,0,0,.55),transparent)"></div>
      <img src="{logo}" style="position:absolute;top:18px;right:22px;width:92px;height:92px;border-radius:50%;border:3px solid #F4EFE6">
      <div style="position:absolute;top:24px;left:22px;width:108px;height:38px;background:#D62828;font-family:Arial;font-weight:700;
        font-size:24px;display:flex;align-items:center;justify-content:center;border-radius:4px">● LIVE</div>
      <div style="position:absolute;top:24px;left:138px;width:170px;height:38px;background:rgba(20,33,61,.88);border-radius:4px"></div>
      <div style="position:absolute;top:24px;left:316px;height:38px;background:rgba(20,33,61,.88);font-size:22px;padding:0 14px;
        border-radius:4px;direction:rtl;display:flex;align-items:center">{date_sd}</div>
      <div style="position:absolute;top:66px;left:22px;background:rgba(122,27,27,.9);font-size:20px;padding:1px 14px;border-radius:4px;direction:rtl">{slot}</div>
      <div style="position:absolute;left:0;right:0;bottom:56px;height:3px;background:#B3261E"></div>
      <div style="position:absolute;right:0;bottom:0;height:56px;width:210px;background:#B3261E;display:flex;align-items:center;
        justify-content:center;font-size:26px;font-weight:700">تازيون خبرون</div>
      <div style="position:absolute;left:0;bottom:0;height:56px;width:300px;background:#F4EFE6;color:#14213D;display:flex;
        align-items:center;justify-content:center;font-family:Arial;font-weight:700;font-size:18px;white-space:nowrap">NAUSHAHRO FEROZE UPDATES</div>
    """, W, H, "frame")
    ticker_text = "  ◆  ".join(E(s["head"]) for s in stories) + "  ◆  "
    ticker = png(f"""<div style="height:56px;display:flex;align-items:center;white-space:nowrap;font-size:27px;
      font-weight:600;direction:rtl;padding:0 30px">{ticker_text}</div>""", 9000, 56, "ticker")
    from PIL import Image
    with Image.open(ticker) as im:  # khaali hissa kaat do
        bbox = im.getbbox()
        one = im.crop((bbox[0] - 20, 0, bbox[2] + 20, 56))
        tw = one.width
        two = Image.new("RGBA", (tw * 2, 56), (0, 0, 0, 0))  # do dafa jor kar patti kabhi khaali na ho
        two.paste(one, (0, 0))
        two.paste(one, (tw, 0))
        two.save(ticker)
    lowers = []
    for i, s in enumerate(stories):
        lowers.append(png(f"""
          <div style="position:absolute;left:40px;right:40px;bottom:74px;direction:rtl">
            <div style="display:inline-block;background:#B3261E;font-size:24px;font-weight:700;padding:2px 18px;border-radius:6px 6px 0 0">خبر {i + 1} / 10</div>
            <div style="background:rgba(20,33,61,.93);border-right:8px solid #B3261E;padding:10px 22px 14px;border-radius:0 0 8px 8px">
              <div style="font-size:36px;font-weight:700;line-height:1.45">{E(s['head'])}</div>
              <div style="font-size:23px;line-height:1.7;opacity:.95;margin-top:6px;display:-webkit-box;-webkit-line-clamp:3;
                -webkit-box-orient:vertical;overflow:hidden">{E(s['summary'])}</div>
            </div></div>""", W, H, f"lower{i}"))

    # --- sab jor kar final video
    inputs = ["-i", bg, "-i", audio, "-loop", "1", "-i", frame, "-loop", "1", "-i", ticker]
    for p in lowers:
        inputs += ["-loop", "1", "-i", p]
    start_epoch = int(now.timestamp())
    clock = (f"drawtext=fontfile={CLOCK_FONT}:text='%{{pts\\:localtime\\:{start_epoch}\\:%I\\\\\\:%M\\\\\\:%S %p}}':"
             "x=150:y=33:fontsize=21:fontcolor=white")
    fc = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    last = "v0"
    for i in range(10):
        a, b, _ = scenes[i + 1]
        fc.append(f"[{last}][{4 + i}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[l{i}]")
        last = f"l{i}"
    speed = 95
    fc.append(f"[{last}]drawbox=x=0:y={H - 56}:w={W}:h=56:color=0x14213D@1:t=fill:"
              f"enable='between(t,{scenes[0][1]:.2f},{scenes[-1][0]:.2f})'[band]")
    fc.append(f"[band][3:v]overlay=x='-{tw}+mod(t*{speed}\\,{tw})':y={H - 56}:"
              f"enable='between(t,{scenes[0][1]:.2f},{scenes[-1][0]:.2f})'[tk]")
    fc.append(f"[tk][2:v]overlay=0:0:enable='between(t,{scenes[0][1]:.2f},{scenes[-1][0]:.2f})'[fr]")
    fc.append(f"[fr]{clock}:enable='between(t,{scenes[0][1]:.2f},{scenes[-1][0]:.2f})',format=yuv420p[vout]")
    out = os.path.join(OUT, "Sindhi_News_Bulletin.mp4")
    env = dict(os.environ, TZ="Asia/Karachi")
    r = subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "1:a",
                        "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-c:a", "aac",
                        "-b:a", "128k", "-movflags", "+faststart", out], capture_output=True, text=True, env=env)
    if r.returncode:
        log(r.stderr[-1500:])
        raise SystemExit(1)
    log("video ready", out, round(os.path.getsize(out) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
