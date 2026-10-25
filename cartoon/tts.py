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


def tts(prompt, voice, ms, key, max_sec=None):
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
                    pcm = np.frombuffer(base64.b64decode(d["data"]), dtype="<i2")
                    if max_sec and len(pcm) / RATE > max_sec:
                        print("rejected: too long", m, round(len(pcm) / RATE, 1), "s (model rambled) - retrying", flush=True)
                        time.sleep(8)
                        continue
                    return pcm
                print("no audio", m, flush=True)
                break
            print("tts", m, r.status_code, r.text[:300], flush=True)
            if r.status_code == 429:
                if "PerDay" in r.text or "per day" in r.text.lower():
                    print("daily quota finished for", m, flush=True)
                    break  # try the next model; don't waste time waiting
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
    failed, source = [], {}
    gem_dead = bool(ep.get("force_backup"))  # testing switch
    for i, ln in enumerate(lines, 1):
        f = os.path.join(out, f"{i:02d}.mp3")
        mx = max_len(ln)
        if want is not None and i not in want:
            continue
        if want is None and os.path.exists(f) and dur(f) <= mx:
            continue  # already made in an earlier run (resume)
        c = CHARS[ln["who"]]
        extra = " This is a phone call." if ln.get("phone") else ""
        if c.get("narrator"):
            prompt = (f"You are the warm, friendly storyteller of a Pakistani family cartoon. Narrate in clear, simple Urdu, "
                      f"engaging like telling a story to the family. Delivery: {ln.get('how', 'warm storytelling')}. "
                      f"Say exactly this and nothing else:\n\n{ln['urdu']}")
        elif c.get("toddler"):
            prompt = (f"You are voicing {c['who']} in a 2D cartoon. Speak like a real 2-year-old: tiny cute voice, "
                      f"slow, half words, giggles. Delivery: {ln.get('how', 'cute')}. Say exactly this and nothing else:\n\n{ln['urdu']}")
        else:
            prompt = (f"You are voicing {c['who']} in a 2D family cartoon from Sindh, Pakistan. Speak in natural everyday Urdu "
                      f"with a light Sindhi accent, like a real person at home, not like a news reader.{extra} "
                      f"Emotion and delivery: {ln.get('how', 'natural')}. Say exactly this line and nothing else:\n\n{ln['urdu']}")
        pcm = None if gem_dead else tts(prompt, c["voice"], ms, key, max_sec=mx)
        if pcm is not None:
            raw = f + ".raw"
            pcm.tofile(raw)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", raw, "-b:a", "96k", f], check=True)
            os.remove(raw)
            source[i] = "gemini"
            print("ok gemini", i, ln["who"], round(len(pcm) / RATE, 2), "s", flush=True)
            time.sleep(21)
            continue
        if not gem_dead:
            g_fail = sum(1 for v in source.values() if v == "edge") + 1
            if g_fail >= 2:
                gem_dead = True  # Gemini quota is finished today: use the free backup voice for the rest
                print("gemini looks finished for today -> backup voices", flush=True)
        if edge_tts_line(ln, f) and dur(f) <= mx:
            source[i] = "edge"
            print("ok backup", i, ln["who"], round(dur(f), 2), "s", flush=True)
        else:
            failed.append(i)
            print("FAILED line", i, flush=True)
    # one character must keep ONE voice inside an episode: if a character got a backup voice on any line,
    # give all of that character's lines the backup voice
    if want is None:
        mixed = {lines[i - 1]["who"] for i, v in source.items() if v == "edge"}
        for i, ln in enumerate(lines, 1):
            if ln["who"] in mixed and source.get(i) == "gemini":
                f = os.path.join(out, f"{i:02d}.mp3")
                if edge_tts_line(ln, f):
                    source[i] = "edge"
                    print("made consistent (backup)", i, ln["who"], flush=True)
    json.dump({"failed": failed, "source": source}, open(os.path.join(out, "status.json"), "w"))
    if failed:
        print("SOME LINES FAILED", failed, flush=True)


def dur(f):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]))
    except Exception:
        return 1e9


def max_len(ln):
    words = len(ln["roman"].replace("*", "").split())
    return max(9.0, words * 0.55 * 2.2 + 2.5)


# Free backup voices (Microsoft Edge neural TTS, Urdu). Same character keeps the same voice every time.
EDGE = {  # voice, rate, pitch
    "ABBA": ("ur-PK-AsadNeural", "-8%", "-14Hz"), "AMMI": ("ur-PK-UzmaNeural", "+0%", "-8Hz"),
    "IMTIAZ": ("ur-IN-SalmanNeural", "-4%", "-6Hz"), "SANA": ("ur-IN-GulNeural", "+0%", "+0Hz"),
    "FARAZ": ("ur-PK-AsadNeural", "+4%", "+2Hz"), "DANIYAL": ("ur-IN-SalmanNeural", "+8%", "+8Hz"),
    "ARSALAN": ("ur-PK-AsadNeural", "+6%", "+16Hz"), "NIMRA": ("ur-PK-UzmaNeural", "+4%", "+6Hz"),
    "MEHAK": ("ur-IN-GulNeural", "+6%", "+24Hz"), "HAMZA": ("ur-IN-GulNeural", "-10%", "+40Hz"),
    "HASHIR": ("ur-PK-UzmaNeural", "-10%", "+40Hz"), "NARRATOR": ("ur-IN-SalmanNeural", "-4%", "+0Hz"),
}


def edge_tts_line(ln, f):
    try:
        import asyncio
        import edge_tts
        v, rate, pitch = EDGE.get(ln["who"], ("ur-PK-AsadNeural", "+0%", "+0Hz"))
        asyncio.run(edge_tts.Communicate(ln["urdu"], v, rate=rate, pitch=pitch).save(f))
        return os.path.exists(f) and os.path.getsize(f) > 1000
    except Exception as e:
        print("backup voice error", repr(e)[:200], flush=True)
        return False

if __name__ == "__main__":
    main()
