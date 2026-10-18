"""Sindhi khabron ki awaz ka namoona: (A) Meta MMS Sindhi, (B) Gemini TTS. Natija voice/out/ aur Telegram par."""
import base64, json, os, subprocess, sys, traceback
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
TEXT = open(os.path.join(HERE, "script_sd.txt"), encoding="utf-8").read().strip()
PARAS = [p.strip() for p in TEXT.split("\n\n") if p.strip()]
LOG = []


def log(*a):
    LOG.append(" ".join(str(x) for x in a))
    print(*a, flush=True)


def to_mp3(src, dst, raw_args=None):
    cmd = ["ffmpeg", "-y"] + (raw_args or []) + ["-i", src, "-ac", "1", "-b:a", "96k", dst]
    subprocess.run(cmd, check=True, capture_output=True)


def mms():
    import numpy as np, torch, scipy.io.wavfile as wav
    from transformers import VitsModel, AutoTokenizer
    found = requests.get("https://huggingface.co/api/models", params={"search": "mms-tts-snd", "limit": 20}, timeout=30).json()
    names = [m.get("id") for m in found if isinstance(m, dict)]
    alt = requests.get("https://huggingface.co/api/models", params={"search": "sindhi tts", "limit": 20}, timeout=30).json()
    log("HF mms-tts-snd search:", names, "| sindhi tts search:", [m.get("id") for m in alt if isinstance(m, dict)])
    name = next((n for n in names if n.startswith("facebook/")), names[0] if names else "")
    if not name:
        raise RuntimeError("Sindhi MMS model nahi mila")
    tok = AutoTokenizer.from_pretrained(name)
    model = VitsModel.from_pretrained(name)
    rate = model.config.sampling_rate
    log("MMS loaded, uroman needed:", getattr(tok, "is_uroman", None), "rate", rate)
    roman = None
    if getattr(tok, "is_uroman", False):
        import uroman as ur
        roman = ur.Uroman()
    chunks = []
    for p in PARAS:
        for sent in [s for s in p.replace("!", "۔").replace(".", "۔").split("۔") if s.strip()]:
            t = roman.romanize_string(sent) if roman else sent
            inputs = tok(t, return_tensors="pt")
            with torch.no_grad():
                w = model(**inputs).waveform[0].numpy()
            chunks += [w, np.zeros(int(rate * 0.35), dtype=np.float32)]
        chunks.append(np.zeros(int(rate * 0.5), dtype=np.float32))
    audio = np.concatenate(chunks)
    p = os.path.join(OUT, "A_mms.wav")
    wav.write(p, rate, (audio * 32767).astype("int16"))
    to_mp3(p, os.path.join(OUT, "A_mms_sindhi.mp3"))
    os.remove(p)
    log("A done, seconds:", round(len(audio) / rate, 1))


def gemini():
    key = os.getenv("GEMINI_API_KEY", "")
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    r = requests.get(base, headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30).json()
    tts = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]
    log("Gemini TTS models:", tts)
    for m in tts:
        body = {"contents": [{"parts": [{"text": "Read this Sindhi news bulletin aloud in Sindhi, in a clear, calm, "
                                                  "professional TV news anchor voice:\n\n" + TEXT}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}}}
        resp = requests.post(f"{base}/{m}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=300)
        if resp.status_code != 200:
            log("Gemini", m, resp.status_code, resp.text[:200])
            continue
        js = resp.json()
        cand = (js.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        data = next(((p.get("inlineData") or p.get("inline_data")) for p in parts
                     if (p.get("inlineData") or p.get("inline_data"))), None)
        if not data:
            log("Gemini", m, "no audio; finish:", cand.get("finishReason"), json.dumps(js)[:300])
            continue
        raw = os.path.join(OUT, "B.pcm")
        with open(raw, "wb") as f:
            f.write(base64.b64decode(data["data"]))
        rate = "24000"
        mime = data.get("mimeType", "")
        if "rate=" in mime:
            rate = mime.split("rate=")[1].split(";")[0]
        to_mp3(raw, os.path.join(OUT, "B_gemini_sindhi.mp3"), ["-f", "s16le", "-ar", rate, "-ac", "1"])
        os.remove(raw)
        log("B done with", m)
        if os.path.getsize(os.path.join(OUT, "B_gemini_sindhi.mp3")) > 20000:
            return


def telegram():
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        return
    for fn, cap in (("A_mms_sindhi.mp3", "🎙️ Namoona A: Meta MMS Sindhi awaz (aaj ki 10 khabrein)"),
                    ("B_gemini_sindhi.mp3", "🎙️ Namoona B: Google Gemini awaz (aaj ki 10 khabrein)")):
        p = os.path.join(OUT, fn)
        if os.path.exists(p):
            with open(p, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{tok}/sendAudio", timeout=120,
                              data={"chat_id": chat, "caption": cap, "title": fn}, files={"audio": (fn, f, "audio/mpeg")})


for fn in (mms, gemini):
    try:
        fn()
    except Exception:
        log(fn.__name__, "FAILED:", traceback.format_exc()[-600:])
telegram()
open(os.path.join(OUT, "log.txt"), "w", encoding="utf-8").write("\n".join(LOG))
