"""Sindhi news bulletin: Gemini TTS (news anchor andaz) + apna banaya news music. Natija voice/out/ aur Telegram par."""
import base64, json, os, subprocess, traceback
import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
PARAS = [p.strip() for p in open(os.path.join(HERE, "script_sd.txt"), encoding="utf-8").read().split("\n\n") if p.strip()]
LOG = []
RATE = 24000
STYLE = ("You are a professional Pakistani TV news anchor reading the Sindhi news bulletin on a Sindhi news channel "
         "(like KTN News). Read the following text aloud in SINDHI with a formal, confident, authoritative news-anchor "
         "delivery: clear pronunciation of Sindhi letters, steady pace, slight emphasis on headlines, and a short "
         "pause after each headline and between stories. Read exactly the text, nothing else:\n\n")


def log(*a):
    LOG.append(" ".join(str(x) for x in a))
    print(*a, flush=True)


def tts(text, models, key):
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    for m in models:
        body = {"contents": [{"parts": [{"text": STYLE + text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}}}
        for attempt in range(2):
            r = requests.post(f"{base}/{m}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=300)
            if r.status_code == 200:
                cand = (r.json().get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                d = next(((p.get("inlineData") or p.get("inline_data")) for p in parts
                          if (p.get("inlineData") or p.get("inline_data"))), None)
                if d:
                    pcm = np.frombuffer(base64.b64decode(d["data"]), dtype="<i2").astype(np.float32) / 32768
                    log("tts ok", m, round(len(pcm) / RATE, 1), "s")
                    return pcm
                log("tts no audio", m, cand.get("finishReason"))
                break
            log("tts", m, r.status_code, r.text[:120])
            if r.status_code not in (500, 503):
                break
    return None


def env(n, a=0.005, r=0.3):
    t = np.arange(n) / RATE
    return np.minimum(1, t / a) * np.exp(-t / r)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # chhote tukron par hi istemal
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def saw(f, t):
    return 2 * ((t * f) % 1.0) - 1


def note(f, dur, kind="pluck"):
    L = int(dur * RATE)
    t = np.arange(L) / RATE
    if kind == "pluck":
        w = 0.6 * saw(f, t) + 0.4 * np.sin(2 * np.pi * f * t)
        return lowpass(w, 2500) * env(L, 0.002, 0.09)
    if kind == "bass":
        w = saw(f, t) + 0.5 * np.sin(2 * np.pi * f * t)
        return lowpass(w, 500) * env(L, 0.005, 0.25)
    if kind == "pad":
        w = sum(saw(f * d, t) for d in (0.995, 1.0, 1.005)) / 3
        att = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.6)
        return lowpass(w, 1400) * att
    if kind == "brass":
        w = saw(f, t) + saw(f * 1.003, t)
        return lowpass(w, 1800) * env(L, 0.02, 0.35)
    return np.zeros(L)


def reverb(x, secs=0.7, wet=0.25):
    rng = np.random.default_rng(7)
    L = int(secs * RATE)
    ir = rng.standard_normal(L) * np.exp(-np.arange(L) / RATE * 5)
    ir /= np.abs(ir).sum() / 8
    n = len(x) + L
    nf = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:len(x)]
    return (1 - wet) * x + wet * y


def music(seconds):
    """Apna banaya news theme: 120 bpm, D minor — tik-tik, tez arpeggio, bass, strings, dhol. Koi copyright nahi."""
    n = int(seconds * RATE)
    out = np.zeros(n + RATE, np.float32)
    bpm = 120
    beat = 60 / bpm
    six = beat / 4
    prog = [  # (bass root, arpeggio notes) — Dm, Bb, F, C
        (73.42, [293.66, 349.23, 440.0, 587.33]),
        (58.27, [233.08, 293.66, 349.23, 466.16]),
        (87.31, [349.23, 440.0, 523.25, 698.46]),
        (65.41, [261.63, 329.63, 392.0, 523.25]),
    ]
    bar = 4 * beat
    # ek bar ke tukre pehle se bana lo (tez)
    bars = []
    for root, arp in prog:
        L = int(bar * RATE) + RATE
        b = np.zeros(L, np.float32)
        for k in range(16):  # arpeggio 16th
            f = arp[[0, 1, 2, 3, 2, 1, 2, 3][k % 8]]
            s = note(f, six * 1.5, "pluck") * 0.22
            i = int(k * six * RATE)
            b[i:i + len(s)] += s
        for k in range(8):  # bass 8th
            s = note(root * (2 if k % 4 == 3 else 1), beat / 2 * 1.2, "bass") * 0.45
            i = int(k * beat / 2 * RATE)
            b[i:i + len(s)] += s
        pad = sum(note(f / 2, bar, "pad") for f in arp[:3]) * 0.12
        b[:len(pad)] += pad
        bars.append(b)
    kl = int(0.3 * RATE)
    kt = np.arange(kl) / RATE
    kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-kt * 35)) * kt) * env(kl, 0.002, 0.11)
    rng = np.random.default_rng(3)
    sl = int(0.2 * RATE)
    snare = (rng.standard_normal(sl) * 0.6 + np.sin(2 * np.pi * 190 * np.arange(sl) / RATE)) * env(sl, 0.001, 0.06)
    tl = int(0.03 * RATE)
    tick = lowpass(rng.standard_normal(tl), 9000) * env(tl, 0.0005, 0.008)
    i = 0
    bi = 0
    while i < n:
        b = bars[bi % 4]
        out[i:i + len(b)][:max(0, len(out) - i)] += b[:max(0, len(out) - i)]
        for k in range(4):
            j = i + int(k * beat * RATE)
            if k in (0, 2) and j + kl < len(out):
                out[j:j + kl] += 0.7 * kick
            if k in (1, 3) and j + sl < len(out):
                out[j:j + sl] += 0.25 * snare
        for k in range(16):  # ghadi jaisi tik-tik
            j = i + int(k * six * RATE)
            if j + tl < len(out):
                out[j:j + tl] += (0.16 if k % 4 == 0 else 0.08) * tick
        i += int(bar * RATE)
        bi += 1
    out = reverb(out[:n], 0.6, 0.2)
    return out


def hit():
    """Khabron ke beech: boom + whoosh."""
    L = int(1.6 * RATE)
    t = np.arange(L) / RATE
    rng = np.random.default_rng(5)
    boom = np.sin(2 * np.pi * (40 + 60 * np.exp(-t * 8)) * t) * env(L, 0.003, 0.5)
    sweep = lowpass(rng.standard_normal(L), 3000) * np.sin(np.pi * np.minimum(1, t / 1.0)) * 0.35
    sweep *= np.where(t < 1.0, 1, np.exp(-(t - 1.0) * 6))
    return (0.8 * boom + sweep).astype(np.float32)


def sting(up=True):
    notes = [293.66, 440.0, 587.33, 880.0] if up else [880.0, 587.33, 440.0, 293.66]
    out = np.zeros(int(2.2 * RATE), np.float32)
    for k, f in enumerate(notes):
        s = (note(f, 0.5, "brass") + note(f / 2, 0.5, "brass")) * 0.35
        i = int(k * 0.18 * RATE)
        out[i:i + len(s)] += s
    h = hit()
    out[:len(h)] += 0.8 * h
    return reverb(out, 0.9, 0.3)


def main():
    key = os.getenv("GEMINI_API_KEY", "")
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    r = requests.get(base, headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30).json()
    models = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]
    models.sort(key=lambda m: ("3.1-flash-tts" not in m, "pro" in m))
    log("models", models)
    chunks = [PARAS[0:4], PARAS[4:7], PARAS[7:10], PARAS[10:]]
    pause = np.zeros(int(1.4 * RATE), np.float32)
    cache = os.path.join(OUT, "voice_cache.npz")
    import hashlib
    sig = hashlib.md5(open(os.path.join(HERE, "script_sd.txt"), "rb").read()).hexdigest()
    parts_v = None
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        if str(z["sig"]) == sig:
            parts_v = list(z["parts"])
            log("voice cache se")
    if parts_v is None:
        parts_v = []
        for c in chunks:
            if not c:
                continue
            pcm = tts("\n\n".join(c), models, key)
            if pcm is None:
                raise RuntimeError("TTS fail")
            parts_v.append(pcm)
        np.savez_compressed(cache, sig=sig, parts=np.array(parts_v, dtype=object))
    marks, voice, pos = [], [], 0
    for pcm in parts_v:
        voice += [pcm, pause]
        pos += len(pcm) + len(pause)
        marks.append(pos - len(pause) // 2)
    voice = np.concatenate(voice)
    intro, outro = sting(True), sting(False)
    lead, tail = 4.0, 4.0
    total = lead + len(voice) / RATE + tail
    bed = music(total)
    n = len(bed)
    v = np.zeros(n, np.float32)
    s0 = int(lead * RATE)
    v[s0:s0 + len(voice)] = voice
    # music halka jab anchor bol raha ho (ducking), shuru aakhir mein poora
    level = np.full(n, 0.95, np.float32)
    level[s0:s0 + len(voice)] = 0.30  # anchor ke neeche bhi saaf sunai de
    k = np.ones(int(0.6 * RATE)) / int(0.6 * RATE)
    level = np.convolve(level, k, mode="same")
    mix = bed * level + v * 1.0
    h = hit()
    for mk in marks[:-1]:  # khabron ke hisson ke beech whoosh
        j = s0 + mk - len(h) // 3
        if 0 <= j < n - len(h):
            mix[j:j + len(h)] += 0.9 * h
    mix[:len(intro)] += intro
    mix[n - len(outro):] += outro[:n]
    fade = int(2.5 * RATE)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= max(1e-6, np.abs(mix).max()) / 0.95
    raw = os.path.join(OUT, "bulletin.wav")
    import scipy.io.wavfile as wav
    wav.write(raw, RATE, (mix * 32767).astype("int16"))
    mp3 = os.path.join(OUT, "Sindhi_News_Bulletin.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-ac", "1", "-b:a", "128k", mp3], check=True, capture_output=True)
    os.remove(raw)
    log("bulletin seconds:", round(total, 1))
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat:
        with open(mp3, "rb") as f:
            requests.post(f"https://api.telegram.org/bot{tok}/sendAudio", timeout=180,
                          data={"chat_id": chat, "title": "Sindhi News Bulletin",
                                "caption": "🎙️ Namoona: poori khabrein + news music + anchor andaz (aaj ki 10 khabrein)"},
                          files={"audio": ("Sindhi_News_Bulletin.mp3", f, "audio/mpeg")})


try:
    main()
except Exception:
    log("FAILED:", traceback.format_exc()[-800:])
open(os.path.join(OUT, "log.txt"), "w", encoding="utf-8").write("\n".join(LOG))
