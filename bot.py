"""
Naushahro Feroze Updates - Facebook auto-posting bot
Har 30 minute GitHub Actions par chalta hai. Saari settings config.json mein hain.
"""
import calendar
import datetime as dt
import hashlib
import html
import json
import os
import re
import time
import traceback
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state.json")
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

PKT = dt.timezone(dt.timedelta(hours=5))
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
FB_TOKEN = os.getenv("FB_PAGE_TOKEN", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"
GRAPH = "https://graph.facebook.com/" + CONFIG.get("graph_version", "v23.0")
LBL = CONFIG["labels"]
S = {}  # state


# ---------------------------------------------------------------- helpers
def now():
    return dt.datetime.now(PKT)


def today():
    return now().strftime("%Y-%m-%d")


def log(*a):
    print(now().strftime("%H:%M:%S"), *a, flush=True)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    for k, v in {"seen": {}, "pending": {}, "queue": [], "jobs": [], "tg_offset": 0,
                 "daily": {"date": "", "count": 0}, "last_digest": "", "alert_day": "",
                 "followers": None, "promo": {"announced": False, "last_week": "", "last_check": ""}}.items():
        s.setdefault(k, v)
    return s


def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1)


def item_key(title):
    norm = re.sub(r"\W+", "", title.lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def word_match(text, words):
    """ASCII words word-boundary par match, Sindhi/Urdu words seedha."""
    low = text.lower()
    for w in words:
        w = w.lower().strip()
        if not w:
            continue
        if w.isascii():
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
                return True
        elif w in low:
            return True
    return False


def is_trusted(domain):
    return any(t.lower() in domain for t in CONFIG["trusted_domains"])


# ---------------------------------------------------------------- telegram
def tg(method, **data):
    if not TG_TOKEN:
        return {}
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", json=data, timeout=30)
        res = r.json()
        if not res.get("ok"):
            log(f"TELEGRAM ERROR ({method}):", res.get("error_code"), res.get("description"))
        return res
    except Exception as e:
        log("telegram error:", e)
        return {}


def tg_send(text, buttons=None):
    if not (TG_TOKEN and TG_CHAT):
        return
    d = {"chat_id": TG_CHAT, "text": text[:4000]}
    if buttons:
        d["reply_markup"] = {"inline_keyboard": [buttons]}
    tg("sendMessage", **d)


def alert(text):
    """Error alert din mein sirf ek dafa."""
    if S.get("alert_day") != today():
        S["alert_day"] = today()
        tg_send("⚠️ " + text)


def process_telegram():
    """Review buttons (✅/❌) aur /status command parhna."""
    if not (TG_TOKEN and TG_CHAT):
        return
    res = tg("getUpdates", offset=S["tg_offset"], timeout=0,
             allowed_updates=["callback_query", "message"])
    for u in res.get("result", []):
        S["tg_offset"] = u["update_id"] + 1
        cq = u.get("callback_query")
        if cq:
            msg = cq.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != TG_CHAT:
                continue
            action, _, pid = cq.get("data", "").partition(":")
            p = S["pending"].pop(pid, None)
            if not p:
                answer = "Ye khabar pehle hi handle ho chuki hai"
            elif action == "ok":
                S["queue"].insert(0, {"message": p["message"], "link": p["link"], "added": time.time()})
                answer = "✅ Approved - agle round mein post hogi"
            else:
                answer = "❌ Reject kar di"
            tg("answerCallbackQuery", callback_query_id=cq["id"], text=answer)
            tg("editMessageReplyMarkup", chat_id=TG_CHAT, message_id=msg.get("message_id"),
               reply_markup={"inline_keyboard": []})
            if p:
                tg_send(answer)
            continue
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) == TG_CHAT and m.get("text", "").strip().lower() in ("/status", "/start"):
            tg_send(f"✅ System chal raha hai\nAaj ki posts: {S['daily']['count']}\n"
                    f"Queue: {len(S['queue'])} | Review baqi: {len(S['pending'])}\n"
                    f"Jobs jama: {len(S['jobs'])} | Followers: {S.get('followers')}")


def expire_old():
    limit = CONFIG["review_expire_hours"] * 3600
    for pid in [k for k, v in S["pending"].items() if time.time() - v["added"] > limit]:
        S["pending"].pop(pid)
    S["queue"] = [q for q in S["queue"] if time.time() - q["added"] < 24 * 3600]
    cutoff = time.time() - 7 * 24 * 3600
    S["seen"] = {k: v for k, v in S["seen"].items() if v > cutoff}


# ---------------------------------------------------------------- news
def gnews_url(query, lang):
    ed = {"ur": "hl=ur&gl=PK&ceid=PK:ur", "en": "hl=en-PK&gl=PK&ceid=PK:en"}[lang]
    return f"https://news.google.com/rss/search?q={quote_plus(query + ' when:2d')}&{ed}"


def fetch(kind):
    queries = CONFIG["news_queries"] if kind == "news" else CONFIG["job_queries"]
    urls = [gnews_url(q, lang) for q in queries for lang in ("ur", "en")]
    urls += [f["url"] for f in CONFIG.get("extra_feeds", []) if f.get("type", "news") == kind]
    max_age = CONFIG["max_age_hours"] * 3600
    items, keys = [], set()
    for u in urls:
        try:
            r = requests.get(u, timeout=25, headers={"User-Agent": "Mozilla/5.0 (NFUpdatesBot)"})
            feed = feedparser.parse(r.content)
        except Exception as e:
            log("feed error:", u, e)
            continue
        for e in feed.entries:
            title = html.unescape(e.get("title", "")).strip()
            link = e.get("link", "")
            if not title or not link:
                continue
            src = e.get("source") or {}
            src_title = src.get("title", "") if hasattr(src, "get") else ""
            src_href = src.get("href", "") if hasattr(src, "get") else ""
            if src_title and title.endswith(" - " + src_title):
                title = title[: -(len(src_title) + 3)].strip()
            pub = e.get("published_parsed") or e.get("updated_parsed")
            ts = calendar.timegm(pub) if pub else time.time()
            if time.time() - ts > max_age:
                continue
            domain = urlparse(src_href or link).netloc.lower().removeprefix("www.")
            k = item_key(title)
            if k in keys:
                continue
            keys.add(k)
            items.append({"key": k, "title": title, "link": link, "domain": domain,
                          "source": src_title or domain, "ts": ts})
    log(f"{kind}: {len(items)} items mile")
    return items


# ---------------------------------------------------------------- AI (layer 1 + 2)
def build_prompt(item):
    return (
        "You write posts for a Facebook news page about Naushahro Feroze district, Sindh, Pakistan.\n"
        f"Headline: {item['title']}\nSource: {item['source']}\n\n"
        "Return JSON only: {\"relevant\": bool, \"sensitive\": bool, \"post\": string, \"lang\": string}\n"
        f"- relevant: true only if the news is about Naushahro Feroze district or its towns: {', '.join(CONFIG['district_towns'])}.\n"
        "- sensitive: true if it involves crime, killing, death, accident, injury, fighting, kidnapping, sexual violence, "
        "suicide, honour killing, violent protest or a dispute between people or groups.\n"
        "- post: rewrite ONLY the information in the headline as a short Facebook post (1-2 sentences). "
        "Write in Sindhi (Arabic script). If you cannot write correct Sindhi, write Urdu; Roman Urdu only as last option. "
        "NEVER add any fact, name, number, place or detail that is not in the headline. No hashtags, no links, no emojis.\n"
        "- lang: sd, ur or roman."
    )


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_discovered = False
_dead_models = set()


def discover_gemini_models():
    """Google ki list se abhi chalne wale Flash models khud dhoondna."""
    try:
        r = requests.get(GEMINI_BASE, headers={"x-goog-api-key": GEMINI_KEY}, params={"pageSize": 200}, timeout=30)
        found = []
        for m in r.json().get("models", []):
            name = m.get("name", "").split("/")[-1]
            if ("generateContent" in m.get("supportedGenerationMethods", []) and "flash" in name
                    and not any(x in name for x in ("image", "tts", "live", "audio", "embed", "native", "thinking"))):
                found.append(name)
        found.sort(key=lambda n: ("preview" in n or "exp" in n, [-int(x) for x in re.findall(r"\d+", n)][:2]))
        log("gemini models mile:", found[:5])
        return found[:4]
    except Exception as e:
        log("gemini model list error:", e)
        return []


def ask_gemini(prompt):
    global _discovered
    models = [S.get("gemini_model")] + CONFIG["gemini_models"]
    tried = set()
    while True:
        for model in models:
            if not model or model in tried or model in _dead_models:
                continue
            tried.add(model)
            try:
                r = requests.post(
                    f"{GEMINI_BASE}/{model}:generateContent",
                    headers={"x-goog-api-key": GEMINI_KEY},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}},
                    timeout=60)
                if r.status_code == 200:
                    S["gemini_model"] = model
                    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                log("gemini", model, r.status_code, r.text[:120].replace("\n", " "))
                if r.status_code in (400, 404):
                    _dead_models.add(model)
            except Exception as e:
                log("gemini error", model, e)
        if _discovered:
            return None
        _discovered = True
        models = discover_gemini_models()


def ask_groq(prompt):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": CONFIG["groq_model"], "temperature": 0.3,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60)
        if r.status_code == 200:
            return json.loads(r.json()["choices"][0]["message"]["content"])
        log("groq", r.status_code, r.text[:150])
    except Exception as e:
        log("groq error", e)
    return None


def ask_ai(item):
    prompt = build_prompt(item)
    for fn, key in ((ask_gemini, GEMINI_KEY), (ask_groq, GROQ_KEY)):
        if not key:
            continue
        res = fn(prompt)
        if isinstance(res, dict) and isinstance(res.get("post"), str) and res["post"].strip():
            return res
    return None  # layer 3: bina AI ke


# ---------------------------------------------------------------- facebook
def can_post():
    if S["daily"]["date"] != today():
        S["daily"] = {"date": today(), "count": 0}
    return S["daily"]["count"] < CONFIG["max_posts_per_day"]


def fb_post(message, link=None):
    if DRY_RUN:
        tg_send("🧪 TEST - Facebook par post NAHI hua:\n\n" + message + (f"\n{link}" if link else ""))
        log("DRY RUN post:", message[:60])
        return True
    if not (FB_PAGE_ID and FB_TOKEN):
        log("FB_PAGE_ID / FB_PAGE_TOKEN missing")
        return False
    data = {"message": message, "access_token": FB_TOKEN}
    if link:
        data["link"] = link
    try:
        r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", data=data, timeout=30)
    except Exception as e:
        log("FB error:", e)
        return False
    if r.status_code == 200:
        log("posted:", r.json().get("id"))
        S["daily"]["count"] += 1
        return True
    log("FB error:", r.text[:300])
    alert("Facebook par post nahi hua. Token ya permission check karein:\n" + r.text[:300])
    return False


def compose(item, text):
    return f"{text}\n\n📌 {LBL['source']}: {item['source']}\n\n{CONFIG['hashtags']}"


def publish_queue():
    posted = 0
    while S["queue"] and posted < CONFIG["max_posts_per_run"] and can_post():
        q = S["queue"][0]
        if not fb_post(q["message"], q.get("link")):
            break
        S["queue"].pop(0)
        posted += 1


# ---------------------------------------------------------------- steps
def handle_news():
    items = [i for i in fetch("news") if i["key"] not in S["seen"]]
    items.sort(key=lambda i: i["ts"], reverse=True)
    done = 0
    for it in items:
        if done >= CONFIG["max_new_per_run"]:
            break  # baqi agle round mein
        S["seen"][it["key"]] = time.time()
        if not is_trusted(it["domain"]):
            log("untrusted source, skip:", it["domain"])
            continue
        done += 1
        res = ask_ai(it) if (GEMINI_KEY or GROQ_KEY) else None
        if res is not None:
            time.sleep(4)  # free limit ke liye
            if res.get("relevant") is False:
                log("relevant nahi:", it["title"][:60])
                continue
        text = res["post"].strip() if res else f"{LBL['news_icon']} {it['title']}"
        message = compose(it, text)
        sensitive = word_match(it["title"], CONFIG["sensitive_words"]) or bool(res and res.get("sensitive"))
        if sensitive:
            if not (TG_TOKEN and TG_CHAT):
                log("sensitive aur Telegram nahi, skip:", it["title"][:60])
                continue
            S["pending"][it["key"]] = {"message": message, "link": it["link"], "added": time.time()}
            tg_send("🟠 REVIEW: ye khabar sensitive hai. Post karni hai?\n\n" + message + "\n\n🔗 " + it["link"],
                    [{"text": "✅ Post karo", "callback_data": "ok:" + it["key"]},
                     {"text": "❌ Reject", "callback_data": "no:" + it["key"]}])
        else:
            S["queue"].append({"message": message, "link": it["link"], "added": time.time()})


def handle_jobs():
    for it in fetch("jobs"):
        if it["key"] in S["seen"]:
            continue
        S["seen"][it["key"]] = time.time()
        if not is_trusted(it["domain"]) or word_match(it["title"], CONFIG["job_scam_words"]):
            continue
        it["local"] = word_match(it["title"], CONFIG["district_towns"])
        S["jobs"].append(it)
    S["jobs"] = S["jobs"][-40:]
    if now().hour < CONFIG["jobs_digest_hour"] or S["last_digest"] == today():
        return
    S["last_digest"] = today()
    if not S["jobs"] or not can_post():
        return
    jobs = sorted(S["jobs"], key=lambda j: (j.get("local", False), j["ts"]), reverse=True)[:CONFIG["jobs_per_digest"]]
    lines = [LBL["jobs_header"], ""]
    for n, j in enumerate(jobs, 1):
        lines += [f"{n}. {j['title']} ({j['source']})", f"🔗 {j['link']}", ""]
    lines += [LBL["jobs_warning"], "", CONFIG["hashtags"]]
    if fb_post("\n".join(lines)):
        S["jobs"] = []


def handle_promo():
    p = S["promo"]
    if p.get("last_check") == today() or DRY_RUN or not (FB_PAGE_ID and FB_TOKEN):
        return
    p["last_check"] = today()
    try:
        r = requests.get(f"{GRAPH}/{FB_PAGE_ID}", params={"fields": "followers_count", "access_token": FB_TOKEN}, timeout=30)
        n = r.json().get("followers_count")
    except Exception as e:
        log("followers error:", e)
        return
    if not isinstance(n, int):
        return
    S["followers"] = n
    cfg = CONFIG["promo"]
    if n < cfg["min_followers"]:
        return
    week = now().strftime("%G-W%V")
    first = not p["announced"]
    weekly = now().weekday() == cfg["weekday"] and p["last_week"] != week
    if (first or weekly) and can_post():
        text = cfg["text"].replace("{followers}", f"{(n // 1000) * 1000:,}")
        if fb_post(text):
            if first:
                tg_send(f"🎉 Mubarak! Page ke {n} followers ho gaye. Promotion wali post laga di gayi hai.")
            p["announced"] = True
            p["last_week"] = week


def main():
    global S
    S = load_state()
    log("start", "(TEST MODE)" if DRY_RUN else "")
    for name, val in (("FB_PAGE_ID", FB_PAGE_ID), ("FB_PAGE_TOKEN", FB_TOKEN), ("GEMINI_API_KEY", GEMINI_KEY),
                      ("TELEGRAM_BOT_TOKEN", TG_TOKEN), ("TELEGRAM_CHAT_ID", TG_CHAT)):
        log(f"secret {name}:", "OK" if val else "MISSING (khaali hai)")
    if TG_TOKEN and ":" not in TG_TOKEN:
        log("TELEGRAM_BOT_TOKEN ghalat lagta hai: is mein ':' hona chahiye")
    if TG_CHAT and not TG_CHAT.lstrip("-").isdigit():
        log("TELEGRAM_CHAT_ID ghalat lagta hai: sirf number hona chahiye")
    if DRY_RUN:
        tg_send("🧪 Test run shuru ho gaya. Agar ye message mila to Telegram sahi juda hua hai.")
    try:
        process_telegram()
        expire_old()
        handle_news()
        handle_jobs()
        publish_queue()
        handle_promo()
    except Exception:
        err = traceback.format_exc()
        log(err)
        alert("System mein error aaya:\n" + err[-600:])
    if DRY_RUN:
        log("test mode: state save nahi kiya")
    else:
        save_state()
    log("done. aaj ki posts:", S["daily"]["count"], "| queue:", len(S["queue"]), "| review:", len(S["pending"]))


if __name__ == "__main__":
    main()
