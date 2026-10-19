"""Sindhi news REEL (1080x1920, ~1 minute): 3 taaza khabrein, Sindhi anchor awaz, apna news music, AI tasveerein
(check ki hui), news channel jaisi screen. Phir Facebook page par Reel upload (REEL_DRY=true ho to sirf Telegram).

Khabrein state.json ke reel_pool se (bot har post hui khabar wahan rakhta hai); istemal hui khabrein voice/reels.json mein.
"""
import datetime as dt
import html
import json
import os
import subprocess
import sys
import time
import traceback

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import bot  # noqa: E402  (AI, tasveer, footer, Sindhi qaide)
import news_video as nv  # noqa: E402  (png, boundaries)
import voice_sample as vs  # noqa: E402  (tts, music, sting, hit)

W, H, FPS, RATE = 1080, 1920, 25, 24000
TZ = dt.timezone(dt.timedelta(hours=5))
DRY = os.getenv("REEL_DRY", "true").lower() == "true"
SLOT = os.getenv("REEL_SLOT", "")
OUTD = os.path.join(HERE, "out")
os.makedirs(OUTD, exist_ok=True)
USED_F = os.path.join(HERE, "reels.json")
NUM_SD = ["پهرين خبر", "ٻي خبر", "ٽين خبر", "چوٿين خبر"]
IMG_Y, IMG_H = 600, 860
E = html.escape


def log(*a):
    print(*a, flush=True)


def tg(method, data=None, files=None):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        return {}
    try:
        return requests.post(f"https://api.telegram.org/bot{tok}/{method}", data=dict(data or {}, chat_id=chat),
                             files=files, timeout=300).json()
    except Exception as e:
        log("telegram error", e)
        return {}


# ------------------------------------------------------------------ khabrein chunna
def pick_stories(n):
    cfg = bot.CONFIG.get("reels", {})
    used = json.load(open(USED_F, encoding="utf-8")) if os.path.exists(USED_F) else {"used": [], "log": []}
    max_age = cfg.get("max_age_hours", 14) * 3600
    pool = [x for x in bot.S.get("reel_pool", []) if x["k"] not in used["used"] and not x.get("s")
            and time.time() - x["t"] < max_age and not bot.blocked_reason(x["h"] + " " + x["x"])]
    # pehle aap ki shehron wali list (1 = Naushahro Feroze ...), phir baqi; har darje mein taaza pehle
    pool.sort(key=lambda x: (x.get("r") or 99, -x["t"]))
    out, seen = [], set()
    for x in pool:
        if x["k"] in seen:
            continue
        seen.add(x["k"])
        out.append(x)
        if len(out) == n:
            break
    return out, used


def write_script(stories):
    """Har khabar ke liye: bolne wala chhota hissa (anchor), screen ki sarkhi aur ek line."""
    listing = "\n\n".join(f"[{i}] {s['h']}\n{s['x'][:900]}" for i, s in enumerate(stories))
    prompt = ("You write a 1-minute Sindhi TV news reel for a Sindhi Facebook page. News items (in Sindhi):\n" + listing +
              "\n\nFor EACH item, in this order, write in Sindhi (Arabic script):\n"
              "- \"say\": what the news anchor will SAY: 2-3 short spoken sentences (25-38 words), clear and formal, "
              "only facts from the item, numbers written as words where natural;\n"
              "- \"head\": on-screen headline, max 7 words;\n"
              "- \"line\": one on-screen sentence (max 18 words) with the key fact.\n"
              "Return JSON: {\"items\": [{\"say\": string, \"head\": string, \"line\": string}]}")
    res = bot.ask_gemini(prompt) if bot.GEMINI_KEY else bot.ask_openrouter(prompt)
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or len(items) < len(stories):
        return None
    out = []
    for s, it in zip(stories, items):
        say = bot.clean_text(str(it.get("say", "")))
        head = bot.cut_words(bot.clean_text(str(it.get("head", ""))), 70) or bot.cut_words(s["h"], 70)
        line = bot.trim_sentences(bot.clean_text(str(it.get("line", ""))), 140)
        if len(say) < 30 or bot.bad_script(say + head + line) or bot.blocked_reason(say + " " + head):
            return None
        out.append({"say": say, "head": head, "line": line})
    return out


# ------------------------------------------------------------------ awaz
def tts_models():
    key = bot.GEMINI_KEY
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key},
                     params={"pageSize": 200}, timeout=30).json()
    ms = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]

    def rank(m):
        import re
        v = re.findall(r"(\d+(?:\.\d+)?)", m)
        return ("lite" in m, "pro" in m, -float(v[0]) if v else 0)
    return sorted(ms, key=rank)


def make_audio(paras):
    """Ek hi TTS call (quota bachao); phir khamoshi se har hisse ka waqt. Music, intro/outro sting, whoosh."""
    pcm = None
    for attempt in range(2):
        pcm = vs.tts("\n\n".join(paras), tts_models(), bot.GEMINI_KEY)
        if pcm is not None:
            break
        time.sleep(20)
    if pcm is None:
        return None
    lead, tail = 3.2, 3.6
    b = nv.boundaries(pcm, paras)  # [0, ..., dur] har paragraph ka shuru
    total = lead + len(pcm) / RATE + tail
    bed = vs.music(total)
    n = len(bed)
    v = np.zeros(n, np.float32)
    s0 = int(lead * RATE)
    v[s0:s0 + len(pcm)] = pcm
    level = np.full(n, 0.95, np.float32)
    level[s0:s0 + len(pcm)] = 0.28
    k = np.ones(int(0.6 * RATE)) / int(0.6 * RATE)
    level = np.convolve(level, k, mode="same")
    mix = bed * level + v
    h = vs.hit()
    for t in b[1:-1]:
        j = s0 + int(t * RATE) - len(h) // 3
        if 0 <= j < n - len(h):
            mix[j:j + len(h)] += 0.7 * h
    intro, outro = vs.sting(True), vs.sting(False)
    mix[:len(intro)] += intro
    mix[n - len(outro):] += outro[:n]
    fade = int(2.0 * RATE)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= max(1e-6, np.abs(mix).max()) / 0.95
    import scipy.io.wavfile as wav
    path = os.path.join(nv.TMP, "reel.wav")
    wav.write(path, RATE, (mix * 32767).astype("int16"))
    spans = [(lead + b[i], lead + b[i + 1]) for i in range(len(paras))]
    return path, total, spans


# ------------------------------------------------------------------ tasveer
def fallback_bg(i):
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(i + 11)
    im = Image.new("RGB", (W, IMG_H), (20, 33, 61))
    d = ImageDraw.Draw(im)
    for _ in range(12):
        x, y, r_ = rng.integers(0, W), rng.integers(0, IMG_H), rng.integers(80, 320)
        c = [(122, 27, 27), (31, 47, 87), (179, 38, 30), (60, 80, 130)][int(rng.integers(0, 4))]
        d.ellipse((x - r_, y - r_, x + r_, y + r_), fill=c)
    p = os.path.join(nv.TMP, f"bg{i}.jpg")
    im.filter(ImageFilter.GaussianBlur(60)).save(p)
    return p


def story_image(s, i):
    try:
        p = bot.news_image(s["h"], s["x"][:600], size=(W, IMG_H))
    except Exception as e:
        log("image error", e)
        p = None
    log("image", i, "ok" if p else "fallback")
    return p or fallback_bg(i)


# ------------------------------------------------------------------ screen
def date_sd(now):
    return f"{nv.SD_DAYS[now.weekday()]}، {now.day} {nv.SD_MONTHS[now.month - 1]} {now.year}"


def slot_name(now):
    h = now.hour
    return ("صبح جون خبرون" if h < 11 else "منجهند جون خبرون" if h < 15 else
            "شام جون خبرون" if h < 19 else "رات جون خبرون")


def screens(items, now, n):
    logo = "file://" + os.path.join(HERE, "assets", "logo.png")
    card_css = ("position:absolute;inset:0;background:linear-gradient(160deg,#14213D 0%,#1f2f57 55%,#7A1B1B 100%);"
                "display:flex;flex-direction:column;align-items:center;justify-content:center;gap:30px;direction:rtl;"
                "text-align:center")
    pill = ("<div style=\"font-family:Arial;font-weight:700;font-size:44px;direction:ltr;background:#F4EFE6;"
            "color:#14213D;padding:10px 30px;border-radius:60px\">Naushahro Feroze Updates <span style=\"background:"
            "#1877F2;color:#fff;border-radius:40px;padding:4px 22px\">+ Follow</span></div>")
    intro = nv.png(f"""<div style="{card_css}"><img src="{logo}" style="width:330px;height:330px;border-radius:50%;
      border:10px solid #F4EFE6"><div style="font-size:96px;font-weight:700">سنڌي خبرون</div>
      <div style="font-size:60px;background:#B3261E;padding:6px 46px;border-radius:14px">{slot_name(now)}</div>
      <div style="font-size:46px;opacity:.92">{date_sd(now)}</div></div>""", W, H, "r_intro", False)
    outro = nv.png(f"""<div style="{card_css}"><img src="{logo}" style="width:300px;height:300px;border-radius:50%;
      border:10px solid #F4EFE6"><div style="font-size:74px;font-weight:700;line-height:1.5;padding:0 60px">
      وڌيڪ خبرن لاءِ<br>پيج کي فالو ڪريو</div>{pill}
      <div style="font-size:42px;opacity:.9">نوشهروفيروز، پڊعيدن ۽ سڄي سنڌ جون تازيون خبرون</div></div>""",
                   W, H, "r_outro", False)
    frame = nv.png(f"""
      <div style="position:absolute;top:0;left:0;right:0;height:170px;background:#14213D;border-bottom:6px solid #B3261E"></div>
      <img src="{logo}" style="position:absolute;top:22px;right:30px;width:126px;height:126px;border-radius:50%;border:4px solid #F4EFE6">
      <div style="position:absolute;top:26px;right:176px;font-size:54px;font-weight:700;direction:rtl">سنڌي خبرون</div>
      <div style="position:absolute;top:104px;right:178px;font-size:30px;opacity:.9;direction:rtl">{date_sd(now)}</div>
      <div style="position:absolute;top:44px;left:30px;background:#D62828;font-family:Arial;font-weight:700;font-size:34px;
        padding:6px 20px;border-radius:6px">● LIVE</div>
      <div style="position:absolute;top:110px;left:30px;background:#7A1B1B;font-size:28px;padding:0 16px;border-radius:6px;
        direction:rtl">{slot_name(now)}</div>
      <div style="position:absolute;left:0;right:0;top:{IMG_Y + IMG_H}px;height:6px;background:#B3261E"></div>
      <div style="position:absolute;right:0;top:{IMG_Y + IMG_H + 6}px;width:250px;height:80px;background:#B3261E;
        display:flex;align-items:center;justify-content:center;font-size:36px;font-weight:700">تازيون خبرون</div>
      <div style="position:absolute;left:0;right:0;top:{IMG_Y + IMG_H + 86}px;bottom:0;
        background:linear-gradient(to bottom,#14213D,#0b1430)"></div>
      <div style="position:absolute;left:0;right:0;top:{IMG_Y + IMG_H + 120}px;display:flex;justify-content:center">{pill}</div>
    """, W, H, "r_frame")
    ticker_text = "  ◆  ".join(E(it["head"]) for it in items) + "  ◆  "
    tick = nv.png(f"""<div style="height:80px;display:flex;align-items:center;white-space:nowrap;font-size:40px;
      font-weight:600;direction:rtl;padding:0 40px">{ticker_text}</div>""", 7000, 80, "r_ticker")
    from PIL import Image
    with Image.open(tick) as im:
        bb = im.getbbox()
        one = im.crop((max(0, bb[0] - 30), 0, bb[2] + 30, 80))
        tw = one.width
        two = Image.new("RGBA", (tw * 2, 80), (0, 0, 0, 0))
        two.paste(one, (0, 0))
        two.paste(one, (tw, 0))
        two.save(tick)
    texts = []
    for i, it in enumerate(items):
        texts.append(nv.png(f"""
          <div style="position:absolute;left:34px;right:34px;top:196px;height:{IMG_Y - 216}px;direction:rtl;
            display:flex;flex-direction:column;justify-content:center">
            <div><span style="display:inline-block;background:#B3261E;font-size:34px;font-weight:700;padding:2px 24px;
              border-radius:10px 10px 0 0">{NUM_SD[i]}  {i + 1}/{n}</span></div>
            <div style="background:rgba(31,47,87,.96);border-right:12px solid #B3261E;padding:14px 28px 20px;
              border-radius:0 0 14px 14px">
              <div style="font-size:60px;font-weight:700;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;
                -webkit-box-orient:vertical;overflow:hidden">{E(it['head'])}</div>
              <div style="font-size:38px;line-height:1.6;opacity:.95;margin-top:8px;display:-webkit-box;
                -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{E(it['line'])}</div>
            </div></div>""", W, H, f"r_text{i}"))
    return intro, outro, frame, tick, tw, texts


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        log(r.stderr[-1500:])
        raise RuntimeError("ffmpeg fail")


def build_video(items, imgs, audio, total, spans, now):
    n = len(items)
    intro, outro, frame, tick, tw, texts = screens(items, now, n)
    # scenes: intro (para 0), har khabar (para 1..n), outro (para n+1 tak aakhir)
    scenes = [(0.0, spans[1][0], "intro")] + [(spans[i + 1][0], spans[i + 2][0], i) for i in range(n)] + \
        [(spans[n + 1][0], total, "outro")]
    segs = []
    for k, (a, b, kind) in enumerate(scenes):
        d = max(0.5, b - a)
        seg = os.path.join(nv.TMP, f"rseg{k}.mp4")
        if kind in ("intro", "outro"):
            run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", intro if kind == "intro" else outro,
                 "-vf", f"scale={W}:{H},format=yuv420p", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", seg])
        else:
            frames = int(d * FPS) + 1
            fc = (f"[1:v]scale={W * 2}:{IMG_H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{IMG_H * 2},"
                  f"zoompan=z='min(zoom+0.0008,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:"
                  f"s={W}x{IMG_H}:fps={FPS},eq=saturation=1.08[z];[0:v][z]overlay=0:{IMG_Y},format=yuv420p")
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x14213D:s={W}x{H}:d={d:.3f}:r={FPS}", "-i", imgs[kind],
                 "-filter_complex", fc, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", seg])
        segs.append(seg)
    lst = os.path.join(nv.TMP, "rlist.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    bg = os.path.join(nv.TMP, "rbg.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])

    a0, a1 = scenes[0][1], scenes[-1][0]
    inputs = ["-i", bg, "-i", audio, "-loop", "1", "-i", frame, "-loop", "1", "-i", tick]
    for p in texts:
        inputs += ["-loop", "1", "-i", p]
    ty = IMG_Y + IMG_H + 6
    fc = [f"[0:v]setpts=PTS-STARTPTS[v0]",
          f"[v0][2:v]overlay=0:0:enable='between(t,{a0:.2f},{a1:.2f})'[f]",
          f"[f]drawbox=x=0:y={ty}:w={W - 250}:h=80:color=0x1f2f57@1:t=fill:enable='between(t,{a0:.2f},{a1:.2f})'[band]",
          f"[band][3:v]overlay=x='-{tw}+mod(t*110\\,{tw})':y={ty}:enable='between(t,{a0:.2f},{a1:.2f})'[tk]",
          # ticker ko "تازيون خبرون" ke daftar ke neeche se guzarne se roko: wo hissa dobara frame se dhak do
          f"[tk][2:v]overlay=0:0:enable='between(t,{a0:.2f},{a1:.2f})'[tk2]"]
    last = "tk2"
    for i in range(len(items)):
        a, b, _ = scenes[i + 1]
        fc.append(f"[{last}][{4 + i}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[t{i}]")
        last = f"t{i}"
    fc.append(f"[{last}]format=yuv420p[vout]")
    out = os.path.join(OUTD, "reel.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "1:a", "-t", f"{total:.2f}",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-profile:v", "high", "-c:a", "aac",
         "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", out])
    # check ke liye kuch frames
    for k, (a, b, kind) in enumerate(scenes):
        t = (a + b) / 2
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", out, "-frames:v", "1", "-vf", "scale=540:-1",
                        os.path.join(OUTD, f"frame{k}.jpg")], capture_output=True)
    return out


# ------------------------------------------------------------------ Facebook Reel
def fb_reel(path, description):
    pid, tok = os.getenv("FB_PAGE_ID", ""), os.getenv("FB_PAGE_TOKEN", "")
    G = f"https://graph.facebook.com/{bot.CONFIG.get('graph_version', 'v23.0')}"
    r = requests.post(f"{G}/{pid}/video_reels", data={"upload_phase": "start", "access_token": tok}, timeout=60).json()
    vid = r.get("video_id")
    if not vid:
        raise RuntimeError("reel start: " + json.dumps(r)[:300])
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        u = requests.post(f"https://rupload.facebook.com/video-upload/{bot.CONFIG.get('graph_version', 'v23.0')}/{vid}",
                          headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)},
                          data=f, timeout=600).json()
    if not u.get("success"):
        raise RuntimeError("reel upload: " + json.dumps(u)[:300])
    fin = requests.post(f"{G}/{pid}/video_reels", timeout=60,
                        data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                              "description": description, "access_token": tok}).json()
    if not fin.get("success"):
        raise RuntimeError("reel finish: " + json.dumps(fin)[:300])
    st = {}
    for _ in range(30):  # Facebook process kare
        time.sleep(10)
        st = requests.get(f"{G}/{vid}", params={"fields": "status,permalink_url", "access_token": tok}, timeout=30).json()
        vs_ = (st.get("status") or {}).get("video_status")
        if vs_ in ("ready", "error"):
            break
    return vid, st


def main():
    bot.S.update(json.load(open("state.json", encoding="utf-8")))
    cfg = bot.CONFIG.get("reels", {})
    n = cfg.get("stories_per_reel", 3)
    now = dt.datetime.now(TZ)
    stories, used = pick_stories(n)
    log("stories", len(stories), [s["h"][:50] for s in stories])
    if len(stories) < 2:
        log("khabrein kam hain, reel nahi bani")
        if DRY:
            tg("sendMessage", {"text": "🎬 Reel test: abhi reel ke liye kafi nayi khabrein nahi (kam az kam 2 chahiye)."})
        return
    items = write_script(stories)
    if not items:
        raise RuntimeError("script nahi bana")
    intro_say = f"السلام عليڪم! نوشهروفيروز اپڊيٽس ۾ ڀليڪار. هي آهن هن وقت جون اهم خبرون."
    outro_say = "وڌيڪ خبرن لاءِ نوشهروفيروز اپڊيٽس کي فالو ڪريو. الله حافظ."
    paras = [intro_say] + [f"{NUM_SD[i]}. {it['say']}" for i, it in enumerate(items)] + [outro_say]
    aud = make_audio(paras)
    if not aud:
        raise RuntimeError("awaz (TTS) nahi bani")
    audio, total, spans = aud
    log("audio seconds", round(total, 1))
    if total > 89:
        raise RuntimeError(f"reel lambi ho gayi ({total:.0f}s)")
    imgs = [story_image(s, i) for i, s in enumerate(stories)]
    out = build_video(items, imgs, audio, total, spans, now)
    log("video", out, round(os.path.getsize(out) / 1e6, 1), "MB")
    desc = (f"📺 {slot_name(now)} | {date_sd(now)}\n\n" +
            "\n".join(f"{['1️⃣', '2️⃣', '3️⃣', '4️⃣'][i]} {it['head']}" for i, it in enumerate(items)) +
            f"\n\n{bot.footer()}")
    if DRY:
        with open(out, "rb") as f:
            tg("sendVideo", {"caption": "🎬 Namoona Reel (Facebook par post NAHI hui)\n\n" + desc[:900],
                             "supports_streaming": "true"}, {"video": ("reel.mp4", f, "video/mp4")})
        return
    vid, st = fb_reel(out, desc)
    link = st.get("permalink_url") or ""
    if link.startswith("/"):
        link = "https://www.facebook.com" + link
    log("reel posted", vid, st.get("status"))
    used["used"] = (used["used"] + [s["k"] for s in stories])[-400:]
    used["log"] = (used.get("log", []) + [{"t": now.strftime("%Y-%m-%d %H:%M"), "slot": SLOT, "video": vid,
                                           "heads": [it["head"] for it in items]}])[-60:]
    json.dump(used, open(USED_F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tg("sendMessage", {"text": f"🎬 Reel post ho gayi ({slot_name(now)})\n\n" +
                       "\n".join("• " + it["head"] for it in items) + (f"\n\n{link}" if link else ""),
                       "disable_web_page_preview": "true"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        log(err)
        tg("sendMessage", {"text": "⚠️ Reel nahi ban saki: " + err.strip().splitlines()[-1][:300]})
        sys.exit(1)
