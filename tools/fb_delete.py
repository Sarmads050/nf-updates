"""Page ki ek ghalat post delete karo: taaza posts mein MATCH wala matn — sirf tab jab bilkul ek post mile."""
import json, os, requests
PID, TOK, MATCH = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"], os.environ["MATCH"].strip()
G = "https://graph.facebook.com/v23.0"
r = requests.get(f"{G}/{PID}/published_posts", params={"access_token": TOK, "fields": "id,created_time,message,permalink_url",
                                                        "limit": 100}, timeout=60).json()
hits = [p for p in r.get("data", []) if MATCH and MATCH in (p.get("message") or "")]
out = {"match": MATCH, "found": [{"id": p["id"], "t": p["created_time"], "msg": (p.get("message") or "")[:120]} for p in hits]}
if len(hits) == 1:
    d = requests.delete(f"{G}/{hits[0]['id']}", params={"access_token": TOK}, timeout=60).json()
    out["deleted"] = d
else:
    out["deleted"] = "NAHI — " + ("koi post nahi mili" if not hits else f"{len(hits)} posts milin, pakka nahi")
os.makedirs("out", exist_ok=True)
json.dump(out, open("out/fb_delete.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:1500])
