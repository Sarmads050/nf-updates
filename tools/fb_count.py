"""Page ki published posts gino (sirf parhna). Nateeja out/fb_count.json."""
import collections, json, os, requests
PID, TOK = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
V = "v23.0"
url = f"https://graph.facebook.com/{V}/{PID}/published_posts"
params = {"access_token": TOK, "fields": "id,created_time,is_published", "limit": 100}
posts, err = [], None
while url and len(posts) < 5000:
    r = requests.get(url, params=params, timeout=60).json()
    if "error" in r:
        err = r["error"].get("message"); break
    posts += r.get("data", [])
    url = (r.get("paging") or {}).get("next"); params = None
by_day = collections.Counter(p["created_time"][:10] for p in posts)
info = requests.get(f"https://graph.facebook.com/{V}/{PID}", params={"access_token": TOK, "fields": "followers_count,fan_count,name"}, timeout=30).json()
os.makedirs("out", exist_ok=True)
json.dump({"total": len(posts), "error": err, "by_day": dict(sorted(by_day.items())), "first": posts[-1]["created_time"] if posts else None,
           "page": {k: info.get(k) for k in ("name", "followers_count", "fan_count")}}, open("out/fb_count.json", "w"), indent=1)
print(len(posts), err)
