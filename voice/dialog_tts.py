"""Do (ya zyada) kirdaron ka dialog: har line alag Gemini TTS call (alag awaz + andaz).
Input: voice/dialogs/<name>.json   Output: voice/dialogs/out/<name>/NN.mp3"""
import base64, json, os, subprocess, sys, time
import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 24000
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def models(key):
    r = requests.get(BASE, headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60).json()
    ms = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]
    ms.sort(key=lambda m: ("3.1-flash-tts" not in m, "pro" in m))
    print("models", ms, flush=True)
    return ms


def tts(prompt, voice, ms, key):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for m in ms:
        for attempt in range(4):
            r = requests.post(f"{BASE}/{m}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=300)
            if r.status_code == 200:
                parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                d = next(((p.get("inlineData") or p.get("inline_data")) for p in parts
                          if (p.get("inlineData") or p.get("inline_data"))), None)
                if d:
                    return np.frombuffer(base64.b64decode(d["data"]), dtype="<i2")
                print("no audio", m, flush=True)
                break
            print("tts", m, r.status_code, r.text[:150], flush=True)
            if r.status_code == 429:
                time.sleep(65)
            elif r.status_code in (500, 503):
                time.sleep(10)
            else:
                break
    return None


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "behan_bhai"
    key = os.environ["GEMINI_API_KEY"]
    cfg = json.load(open(os.path.join(HERE, "dialogs", f"{name}.json"), encoding="utf-8"))
    out = os.path.join(HERE, "dialogs", "out", name)
    os.makedirs(out, exist_ok=True)
    ms = models(key)
    only = os.environ.get("ONLY_LINES", "").strip()
    want = {int(x) for x in only.split(",") if x.strip()} if only else None
    for i, (who, how, text) in enumerate(cfg["lines"], 1):
        f = os.path.join(out, f"{i:02d}.mp3")
        if want is not None and i not in want:
            continue
        prompt = (f"You are voicing {cfg['who'][who]} in a 2D cartoon. Speak in natural everyday Urdu with a Karachi "
                  f"accent, like a real kid, not like a news reader. Emotion and delivery: {how}. "
                  f"Say exactly this line and nothing else:\n\n{text}")
        pcm = tts(prompt, cfg["voices"][who], ms, key)
        if pcm is None:
            print("FAILED line", i, flush=True)
            continue
        raw = f + ".raw"
        pcm.tofile(raw)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", raw,
                        "-b:a", "96k", f], check=True)
        os.remove(raw)
        print("ok", i, who, round(len(pcm) / RATE, 2), "s", flush=True)
        time.sleep(21)  # free tier: stay under per-minute limit


if __name__ == "__main__":
    main()
