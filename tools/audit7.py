"""Pichle 7 din ki posts ki jaanch (sirf parhna). DELETE_IDS diye hon to sirf wohi delete.

- Kawish wali posts: kawish-epaper branch ke asal safhe ki tasveer se milao (jagah, number, fot/zakhmi, bigre alfaz).
- Baqi khabrein: editor ki tarah matn ki jaanch (bigre alfaz, bematlab jumle, sarkhi-khabar mel, tazaad).
Nateeja: out/audit.json
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402

PID, TOK = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
G = "https://graph.facebook.com/v23.0"
DAYS = int(os.environ.get("AUDIT_DAYS", "7"))
os.makedirs("out", exist_ok=True)
bot.S.update(json.load(open("state.json", encoding="utf-8")))


def save(obj):
    json.dump(obj, open("out/audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---- delete mode
ids = [x.strip() for x in os.environ.get("DELETE_IDS", "").split(",") if x.strip()]
if ids:
    res = {}
    for i in ids:
        res[i] = requests.delete(f"{G}/{i}", params={"access_token": TOK}, timeout=60).json()
    save({"deleted": res})
    print(json.dumps(res)[:2000])
    sys.exit(0)

# ---- posts
since = int((dt.datetime.utcnow() - dt.timedelta(days=DAYS)).timestamp())
posts, url = [], f"{G}/{PID}/published_posts"
params = {"access_token": TOK, "fields": "id,created_time,message,status_type,permalink_url", "limit": 100,
          "since": since}
while url:
    r = requests.get(url, params=params, timeout=60).json()
    posts += r.get("data", [])
    url, params = (r.get("paging") or {}).get("next"), None
print("posts:", len(posts), flush=True)

PK = dt.timedelta(hours=5)


def pk_date(p):
    return (dt.datetime.strptime(p["created_time"][:19], "%Y-%m-%dT%H:%M:%S") + PK).date()


def page_img(date, page):
    for d in (date, date - dt.timedelta(days=1)):
        r = subprocess.run(["git", "show", f"origin/kawish-epaper:{d.isoformat()}/{page:02d}.jpg"], capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 10000:
            return r.stdout, d.isoformat()
    return None, None


report = []
kaw, other = [], []
for p in posts:
    m = p.get("message") or ""
    if p.get("status_type") == "added_video" or "━━" in m or len(m) < 40:
        continue  # reels / roundup / chhoti posts
    km = re.search(r"ڪاوش\s*\(صفحو\s*(\d+)\)", m)
    (kaw if km else other).append((p, int(km.group(1)) if km else 0))

# Kawish: asal safhe se
for p, page in kaw:
    m = p["message"]
    icon, head, body, tail = bot._split_post(m)
    img, d = page_img(pk_date(p), page)
    if not img:
        report.append({"id": p["id"], "t": p["created_time"], "kind": "kawish", "verdict": "no_page", "head": head})
        continue
    prompt = ("This is page " + str(page) + " of the Daily Kawish (Sindhi newspaper). A Facebook page posted the news "
              "below saying it came from this page.\nPOSTED HEADLINE: " + head + "\nPOSTED STORY: " + body[:1500] +
              "\n\nFind this news on the page and compare STRICTLY with what is printed: is the city/town the same? "
              "are the numbers the same? is the outcome the same (died vs injured etc.)? is anything added that is "
              "not printed? Is the posted Sindhi text garbled (non-existent words, meaningless sentences)?\n"
              "verdict: \"correct\" (matches, small wording differences are fine), \"wrong\" (place, numbers, outcome or "
              "facts differ, or it is not on the page), \"garbled\" (facts fine but text has non-existent/meaningless "
              "words), \"unsure\".\nReturn JSON: {\"verdict\": string, \"printed_headline\": string, \"problem\": string}")
    res = bot.ask_gemini(prompt, image=img, mime="image/jpeg")
    if not isinstance(res, dict):
        res = bot.ask_openrouter(prompt, image=img) or {}
    report.append({"id": p["id"], "t": p["created_time"], "kind": "kawish", "page": page, "paper": d,
                   "verdict": str(res.get("verdict", "unsure")), "head": head,
                   "printed": str(res.get("printed_headline", ""))[:150], "problem": str(res.get("problem", ""))[:300],
                   "url": p.get("permalink_url")})
    save({"done": False, "report": report})
    print("kawish", report[-1]["verdict"], head[:50], flush=True)

# Baqi: matn ki jaanch (10 ek saath)
for k in range(0, len(other), 10):
    chunk = other[k:k + 10]
    listing = "\n\n".join(f"[{i}] HEADLINE: {bot._split_post(p['message'])[1]}\nSTORY: {bot._split_post(p['message'])[2][:900]}"
                          for i, (p, _) in enumerate(chunk))
    prompt = ("You are the senior editor of a professional Sindhi news page. Audit these PUBLISHED posts. For each, "
              "verdict: \"ok\" (clear, correct Sindhi, headline matches story, no contradictions — small spelling "
              "issues are ok), \"garbled\" (has non-existent or meaningless words / sentences that a reader cannot "
              "understand), \"contradiction\" (facts inside the post contradict, e.g. died vs injured, two different "
              "places), \"mismatch\" (headline is about a different event or place than the story), \"mixed\" (two "
              "unrelated news stories mixed in one post). Be strict but fair: only mark a problem a reader would "
              "clearly notice.\n\n" + listing +
              "\n\nReturn JSON: {\"items\": [{\"i\": number, \"verdict\": string, \"problem\": string}]}")
    res = bot.ask_gemini(prompt)
    if not isinstance(res, dict):
        res = bot.ask_openrouter(prompt) or {}
    got = {}
    for it in res.get("items") or []:
        try:
            got[int(it.get("i"))] = it
        except (TypeError, ValueError):
            pass
    for i, (p, _) in enumerate(chunk):
        it = got.get(i, {})
        report.append({"id": p["id"], "t": p["created_time"], "kind": "text", "verdict": str(it.get("verdict", "unsure")),
                       "head": bot._split_post(p["message"])[1], "problem": str(it.get("problem", ""))[:300],
                       "url": p.get("permalink_url")})
    save({"done": False, "report": report})
    print("text chunk", k, flush=True)

save({"done": True, "total_posts": len(posts), "checked": len(report), "report": report})
print("done", len(report))
