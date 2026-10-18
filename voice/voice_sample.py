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
    e = np.minimum(1, t / a) * np.exp(-t / r)
    return e


def music(seconds):
    """Saada 'news bed': pad chords + halki dhamak + tick, aur shuru/aakhir ka sting. Apna banaya, koi copyright nahi."""
    n = int(seconds * RATE)
    out = np.zeros(n, np.float32)
    bpm = 104
    beat = 60 / bpm
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]]
    bar = int(4 * beat * RATE)
    t = np.arange(bar) / RATE
    for i in range(0, n, bar):
        ch = chords[(i // bar) % 4]
        seg = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) for f in ch) / 6
        seg *= np.minimum(1, t / 0.4) * np.minimum(1, (t[-1] - t + 1e-3) / 0.4)
        k = min(bar, n - i)
        out[i:i + k] += 0.35 * seg[:k]
    step = int(beat * RATE)
    kick_len = int(0.35 * RATE)
    kt = np.arange(kick_len) / RATE
    kick = np.sin(2 * np.pi * (55 + 60 * np.exp(-kt * 30)) * kt) * env(kick_len, 0.002, 0.12)
    rng = np.random.default_rng(1)
    tick_len = int(0.04 * RATE)
    tick = rng.standard_normal(tick_len) * env(tick_len, 0.001, 0.01)
    for i in range(0, n - kick_len, step):
        out[i:i + kick_len] += 0.5 * kick
        for q in (0, step // 2):
            j = i + q
            if j + tick_len < n:
                out[j:j + tick_len] += 0.06 * tick
    return out


def sting(up=True):
    notes = [392.0, 523.25, 659.25, 783.99] if up else [783.99, 659.25, 523.25, 392.0]
    parts = []
    for f in notes:
        L = int(0.22 * RATE)
        t = np.arange(L) / RATE
        parts.append((np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)) * env(L, 0.005, 0.25) * 0.5)
    L = int(1.2 * RATE)
    t = np.arange(L) / RATE
    rng = np.random.default_rng(2)
    whoosh = rng.standard_normal(L) * np.sin(np.pi * t / t[-1]) * 0.08
    s = np.concatenate(parts)
    out = np.zeros(max(len(s), L), np.float32)
    out[:len(s)] += s
    out[:L] += whoosh
    return out


def main():
    key = os.getenv("GEMINI_API_KEY", "")
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    r = requests.get(base, headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30).json()
    models = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]
    models.sort(key=lambda m: ("3.1-flash-tts" not in m, "pro" in m))
    log("models", models)
    chunks = [PARAS[0:4], PARAS[4:7], PARAS[7:10], PARAS[10:]]
    pause = np.zeros(int(0.9 * RATE), np.float32)
    voice = []
    for c in chunks:
        if not c:
            continue
        pcm = tts("\n\n".join(c), models, key)
        if pcm is None:
            raise RuntimeError("TTS fail")
        voice += [pcm, pause]
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
    level = np.full(n, 0.55, np.float32)
    level[s0:s0 + len(voice)] = 0.12
    k = np.ones(int(0.6 * RATE)) / int(0.6 * RATE)
    level = np.convolve(level, k, mode="same")
    mix = bed * level + v * 1.0
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
