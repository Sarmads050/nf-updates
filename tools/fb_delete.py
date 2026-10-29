"""Page ki ek ghalat post delete karo: taaza posts mein MATCH wala matn — sirf tab jab bilkul ek post mile."""
import json, os, requests
PID, TOK, MATCH = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"], os.environ["MATCH"].strip()
G = "https://graph.facebook.com/v23.0"
import re
NORM = str.maketrans({"ی": "ي", "ک": "ڪ", "ہ": "ه", "ھ": "ه", "ے": "ي"})
norm = lambda t: re.sub(r"\s+", " ", re.sub(r"[\u064B-\u065F\u0670\u200c\u200d]", "", t or "").translate(NORM))
posts, url, params = [], f"{G}/{PID}/published_posts", {"access_token": TOK, "fields": "id,created_time,message", "limit": 100}
while url and len(posts) < 400:
    r = requests.get(url, params=params, timeout=60).json()
    posts += r.get("data", [])
    url, params = (r.get("paging") or {}).get("next"), None
hits = [p for p in posts if MATCH and norm(MATCH) in norm(p.get("message"))]
print("posts dekhi:", len(posts))
out = {"match": MATCH, "found": [{"id": p["id"], "t": p["created_time"], "msg": (p.get("message") or "")[:120]} for p in hits]}
if len(hits) == 1:
    d = requests.delete(f"{G}/{hits[0]['id']}", params={"access_token": TOK}, timeout=60).json()
    out["deleted"] = d
else:
    out["deleted"] = "NAHI — " + ("koi post nahi mili" if not hits else f"{len(hits)} posts milin, pakka nahi")
os.makedirs("out", exist_ok=True)
json.dump(out, open("out/fb_delete.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:1500])
