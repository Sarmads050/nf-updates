"""Page ka analysis (sirf parhna): har post ke reactions/comments/shares + page ki maloomat. Nateeja out/."""
import collections, json, os, requests
PID, TOK = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
G = "https://graph.facebook.com/v23.0"
def get(url, params=None):
    return requests.get(url, params=params, timeout=60).json()
url = f"{G}/{PID}/published_posts"
params = {"access_token": TOK, "limit": 50,
          "fields": "id,created_time,message,permalink_url,status_type,full_picture,"
                    "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),shares"}
posts, err = [], None
while url and len(posts) < 3000:
    r = get(url, params)
    if "error" in r:
        err = r["error"].get("message"); break
    posts += r.get("data", [])
    url = (r.get("paging") or {}).get("next"); params = None
rows = []
for p in posts:
    rows.append({"t": p["created_time"], "type": p.get("status_type"), "img": bool(p.get("full_picture")),
                 "msg": (p.get("message") or "")[:160].replace("\n", " "),
                 "react": (p.get("reactions") or {}).get("summary", {}).get("total_count", 0),
                 "com": (p.get("comments") or {}).get("summary", {}).get("total_count", 0),
                 "share": (p.get("shares") or {}).get("count", 0), "url": p.get("permalink_url")})
fields = ("name,username,about,description,category,category_list,phone,website,emails,location,single_line_address,"
          "followers_count,fan_count,link,is_verified,cover,picture,whatsapp_number,general_info,hours,"
          "call_to_actions,rating_count,overall_star_rating")
info = get(f"{G}/{PID}", {"access_token": TOK, "fields": fields})
if "error" in info:
    info = get(f"{G}/{PID}", {"access_token": TOK, "fields": "name,username,about,category,phone,website,followers_count,fan_count,link,location"})
ins = get(f"{G}/{PID}/insights", {"access_token": TOK, "metric": "page_impressions_unique,page_post_engagements,page_follows", "period": "day"})
os.makedirs("out", exist_ok=True)
json.dump({"total": len(posts), "error": err, "page": info, "insights": ins, "posts": rows}, open("out/fb_count.json", "w"),
          ensure_ascii=False, indent=1)
print(len(posts), err)
