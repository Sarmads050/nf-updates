"""Episode voices with Gemini TTS: one call per line, each character has its own voice + acting direction.
usage: python cartoon/tts.py cartoon/episodes/ep001.json   -> cartoon/episodes/out/ep001/NN.mp3"""
import base64, json, os, subprocess, sys, time
import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from art import CHARS  # noqa: E402

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
                d = next(((p.get("inlineData") or p.get("inline_data")) for p in parts if (p.get("inlineData") or p.get("inline_data"))), None)
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
    path = sys.argv[1]
    key = os.environ["GEMINI_API_KEY"]
    ep = json.load(open(path, encoding="utf-8"))
    eid = ep["id"]
    out = os.path.join(HERE, "episodes", "out", eid)
    os.makedirs(out, exist_ok=True)
    only = os.environ.get("ONLY_LINES", "").strip()
    want = {int(x) for x in only.split(",") if x.strip()} if only else None
    ms = models(key)
    lines = [ln for sc in ep["scenes"] for ln in sc["lines"]]
    failed = []
    for i, ln in enumerate(lines, 1):
        if want is not None and i not in want:
            continue
        c = CHARS[ln["who"]]
        extra = " This is a phone call." if ln.get("phone") else ""
        if c.get("toddler"):
            prompt = (f"You are voicing {c['who']} in a 2D cartoon. Speak like a real 2-year-old: tiny cute voice, "
                      f"slow, half words, giggles. Delivery: {ln.get('how', 'cute')}. Say exactly this and nothing else:\n\n{ln['urdu']}")
        else:
            prompt = (f"You are voicing {c['who']} in a 2D family cartoon from Sindh, Pakistan. Speak in natural everyday Urdu "
                      f"with a light Sindhi accent, like a real person at home, not like a news reader.{extra} "
                      f"Emotion and delivery: {ln.get('how', 'natural')}. Say exactly this line and nothing else:\n\n{ln['urdu']}")
        pcm = tts(prompt, c["voice"], ms, key)
        if pcm is None:
            print("FAILED line", i, flush=True)
            failed.append(i)
            continue
        f = os.path.join(out, f"{i:02d}.mp3")
        raw = f + ".raw"
        pcm.tofile(raw)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", raw, "-b:a", "96k", f], check=True)
        os.remove(raw)
        print("ok", i, ln["who"], round(len(pcm) / RATE, 2), "s", flush=True)
        time.sleep(21)
    json.dump({"failed": failed}, open(os.path.join(out, "status.json"), "w"))
    if failed:
        print("SOME LINES FAILED", failed, flush=True)


if __name__ == "__main__":
    main()
