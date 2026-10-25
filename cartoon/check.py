"""Validate an episode JSON before voices/render. usage: python cartoon/check.py cartoon/episodes/epNNN.json"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from art import CHARS, EM
import sets as S

POSES = ["rest", "read", "head_hold", "beckon", "wag", "plead", "point_down", "fist", "point_other", "thumb_back", "arms_up", "chest",
         "wave", "hold", "newspaper", "phone_look", "hands_hips", "cross", "shrug", "facepalm", "scratch_head", "objection", "clap",
         "think", "explain", "point_up", "tired"]
SFX = ["whoosh", "door", "ding", "phone_ring", "notification", "clink", "pressure_cooker", "bat_hit", "sting", "boing", "crash", "knock",
       "baby_giggle", "tv", "rain", "bike", "light_on", "cash"]
PROPS = ["cup", "phone", "newspaper", "remote", "bat", "book", "ladle", "plate", "bag", "toy", "tray", None]
LOOKS = ["front", "down", "book", "phone", "up", "door", "*"]
S.setK(0.2)
ep = json.load(open(sys.argv[1], encoding="utf-8"))
err = []
for k in ("id", "title", "episode", "scenes", "lesson", "caption", "hashtags", "music"):
    if k not in ep:
        err.append(f"missing top key {k}")
if ep.get("music") not in ("happy", "comic", "calm", "tense"):
    err.append("music must be happy|comic|calm|tense")
n = 0
for si, sc in enumerate(ep.get("scenes", [])):
    if sc.get("set") not in S.SETS:
        err.append(f"scene {si}: unknown set {sc.get('set')} (use {list(S.SETS)})")
        continue
    if sc.get("time", "day") not in ("day", "evening", "night", "loadshedding"):
        err.append(f"scene {si}: bad time")
    slots = S.SETS[sc["set"]](sc.get("time", "day"))["slots"]
    present = {}
    for who, sl in sc.get("cast", {}).items():
        if who not in CHARS:
            err.append(f"scene {si}: unknown character {who}")
        if sl not in slots:
            err.append(f"scene {si}: slot {sl} not in {sc['set']} slots {list(slots)}")
        if sl in present.values():
            err.append(f"scene {si}: two characters on slot {sl}")
        present[who] = sl
    for who, p in sc.get("props", {}).items():
        if p not in PROPS:
            err.append(f"scene {si}: unknown prop {p}")
    for li, ln in enumerate(sc.get("lines", [])):
        n += 1
        tag = f"line {n} ({ln.get('who')})"
        for a in ln.get("before", []) + ln.get("after", []):
            d = a.get("do")
            if d == "enter":
                if a["slot"] not in slots:
                    err.append(f"{tag}: enter slot {a['slot']} not in set")
                if a["slot"] in present.values():
                    err.append(f"{tag}: enter slot {a['slot']} already taken")
                present[a["who"]] = a["slot"]
            elif d == "exit":
                if a["who"] not in present:
                    err.append(f"{tag}: exit of {a['who']} who is not present")
                present.pop(a["who"], None)
            elif d == "move":
                if a["slot"] not in slots or a["slot"] in present.values():
                    err.append(f"{tag}: bad move slot {a['slot']}")
                present[a["who"]] = a["slot"]
            elif d == "prop":
                if a.get("prop") not in PROPS:
                    err.append(f"{tag}: bad prop")
            elif d == "sfx":
                if a.get("name") not in SFX:
                    err.append(f"{tag}: bad sfx {a.get('name')}")
            elif d != "wait":
                err.append(f"{tag}: unknown action {d}")
        if ln.get("who") not in present and not ln.get("offscreen") and not ln.get("phone"):
            err.append(f"{tag}: speaker not present in scene (add to cast or 'enter' first, or set offscreen/phone)")
        for k in ("roman", "urdu", "how"):
            if not ln.get(k):
                err.append(f"{tag}: missing {k}")
        def emos(v):
            return [v] if isinstance(v, str) else [x[1] for x in v] if v else []
        for e in emos(ln.get("emo")):
            if e not in EM:
                err.append(f"{tag}: unknown emo {e} (use {list(EM)})")
        for w, v in ln.get("react", {}).items():
            for e in emos(v):
                if e not in EM:
                    err.append(f"{tag}: unknown react emo {e}")
        for p in ([ln.get("pose")] if isinstance(ln.get("pose"), str) else [x[1] for x in ln.get("pose") or []]):
            if p and p not in POSES:
                err.append(f"{tag}: unknown pose {p} (use {POSES})")
        to = ln.get("to")
        if to and to not in LOOKS and to not in present:
            err.append(f"{tag}: 'to' {to} not present")
        sh = ln.get("shot", "auto")
        if not (sh in ("auto", "wide", "group", "close", "punch") or sh.split(":")[0] in ("two", "close", "punch")):
            err.append(f"{tag}: bad shot {sh}")
        if ":" in sh and sh.split(":")[1] not in present:
            err.append(f"{tag}: shot target not present")
        for s_ in ln.get("sfx", []):
            if s_ not in SFX:
                err.append(f"{tag}: bad sfx {s_}")
        if "*" in ln.get("roman", "") and ln["roman"].count("*") % 2:
            err.append(f"{tag}: unbalanced *highlight*")
print(f"{n} lines")
if err:
    print("ERRORS:\n- " + "\n- ".join(err))
    sys.exit(1)
print("OK")
