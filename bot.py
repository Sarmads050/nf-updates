"""
Naushahro Feroze Updates - Facebook auto-posting bot
Har 30 minute GitHub Actions par chalta hai. Saari settings config.json mein hain.
"""
import base64
import calendar
import datetime as dt
import hashlib
import html
import json
import os
import random
import re
import time
import traceback
from urllib.parse import quote_plus, urljoin, urlparse

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
STATS = {}  # is run ki ginti (report ke liye)


def stat(key, n=1):
    STATS[key] = STATS.get(key, 0) + n


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


def blocked_reason(text):
    """Pakki pabandi: mazhab ki tauheen/firqawariyat, gaali-galoch, aur fauj (military) ka zikr.
    In mein se kuch bhi ho to khabar kabhi post nahi hogi, review mein bhi nahi jayegi."""
    for ok in CONFIG.get("block_exceptions", []):  # maslan "فوجداری" (criminal case) fauj nahi
        text = re.sub(re.escape(ok), " ", text, flags=re.I)
    for reason, words in CONFIG["blocked_words"].items():
        if word_match(text, words):
            return reason
    return None


def keyword_sensitive(title):
    """Jurm wali khabar review mein jaye. Hadsay ki khabar (bina jurm ke) seedha post ho."""
    if not word_match(title, CONFIG["sensitive_words"]):
        return False
    if word_match(title, CONFIG.get("accident_words", [])) and not word_match(title, CONFIG.get("crime_words", [])):
        return False
    return True


def is_trusted(domain):
    for t in CONFIG["trusted_domains"]:
        t = t.lower()
        if domain == t or domain.endswith("." + t) or ("." not in t and t in domain):
            return True
    return False


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
                S["queue"].insert(0, {"message": p["message"], "link": p.get("link"), "photo": p.get("photo"), "video": p.get("video"),
                                      "added": time.time()})
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
        if m:
            try:
                handle_message(m)
            except Exception:
                log("message error:", traceback.format_exc()[-300:])


def finish(text):
    """Khabar ke aakhir mein dot (. ya ۔) ki jagah ! lagana."""
    t = (text or "").strip()
    t = re.sub(r"[\s.۔]+$", "", t)
    if not t.endswith(("!", "؟", "?")):
        t += "!"
    return t


FB_LINK = re.compile(r"https?://(?:[a-z]+\.)?(?:facebook\.com|fb\.watch|fb\.me|fb\.com)/\S+", re.I)
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Mobile Safari/537.36", "Accept-Language": "en-US,en;q=0.9,ur;q=0.8"}


def fetch_fb_preview(url):
    """Share ki gayi Facebook post ka preview (jaise Telegram/WhatsApp link ka preview dikhate hain).
    Koi login nahi, sirf woh jo Facebook khud public preview mein deta hai."""
    try:
        r = requests.get(url, headers=BROWSER_UA, timeout=25, allow_redirects=True)
        h = r.text
    except Exception as e:
        log("fb link error:", e)
        return "", ""

    def meta(name):
        m = (re.search(r'<meta[^>]+(?:property|name)="og:%s"[^>]+content="([^"]*)"' % name, h) or
             re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="og:%s"' % name, h))
        return html.unescape(m.group(1)).strip() if m else ""

    desc, title, img = meta("description"), meta("title"), meta("image")
    text = desc if len(desc) >= len(title) else title
    low = text.lower()
    if not text or "log in" in low or "log into" in low or low in ("facebook", "facebook.com"):
        text = ""
    if not img.startswith("http") or "/rsrc.php" in img:
        img = ""
    log("fb preview:", len(text), "chars", "| photo" if img else "")
    return text, img


def reply(chat_id, text):
    tg("sendMessage", chat_id=chat_id, text=text[:4000])


def handle_message(m):
    """Aap ya sahafi bot ko khabar bhejein (text ya photo + caption)."""
    chat_id = str(m.get("chat", {}).get("id"))
    user = m.get("from") or {}
    text = (m.get("text") or m.get("caption") or "").strip()
    photo = m["photo"][-1]["file_id"] if m.get("photo") else None
    owner = chat_id == TG_CHAT
    contributors = S.setdefault("contributors", {})
    cmd = text.split()[0].lower() if text.startswith("/") else ""

    if owner and cmd in ("/status", "/start"):
        tg_send(f"✅ System chal raha hai\nAaj ki posts: {S['daily']['count']}\n"
                f"Queue: {len(S['queue'])} | Review baqi: {len(S['pending'])}\n"
                f"Jobs jama: {len(S['jobs'])} | Followers: {S.get('followers')}\n"
                f"Sahafi: {len(contributors)}\n\n"
                "Khabar post karne ke liye uska text (ya photo + text) mujhe bhej dein.\n"
                "Sahafi jorne ke liye: /add ID Naam   hatane ke liye: /remove ID   list: /sahafi")
        return
    if owner and cmd == "/add":
        parts = text.split(maxsplit=2)
        if len(parts) >= 3 and parts[1].lstrip("-").isdigit():
            contributors[parts[1]] = parts[2]
            tg_send(f"✅ {parts[2]} ab khabrein bhej sakte hain. Un ki khabrein aap ke review ke liye aayengi.")
            reply(parts[1], "✅ Aap ko Naushahro Feroze Updates ke liye khabar bhejne ki ijazat mil gayi. "
                            "Khabar ka text ya photo ke saath text bhejein.")
        else:
            tg_send("Aise likhen: /add 123456789 Ali Ahmed")
        return
    if owner and cmd == "/remove":
        parts = text.split()
        name = contributors.pop(parts[1], None) if len(parts) > 1 else None
        tg_send(f"Hata diya: {name}" if name else "Ye ID list mein nahi. /sahafi se list dekhein.")
        return
    if owner and cmd == "/sahafi":
        tg_send("Sahafi:\n" + ("\n".join(f"{k} - {v}" for k, v in contributors.items()) or "abhi koi nahi"))
        return
    if cmd:
        if not owner and chat_id not in contributors:
            name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or "Koi"
            tg_send(f"👤 {name} (@{user.get('username', '-')}) khabrein bhejna chahte hain.\n"
                    f"Ijazat dene ke liye likhen:\n/add {chat_id} {name}")
            reply(chat_id, "Shukriya! Aap ki darkhwast page ke admin ko bhej di gayi hai. Ijazat milte hi bata diya jayega.")
        return

    if not owner and chat_id not in contributors:
        return  # anjaan log

    screenshot, link, video = None, None, None
    own_video = False
    tg_video = m.get("video") or (m.get("document") if str((m.get("document") or {}).get("mime_type", "")).startswith("video") else None)
    sv = SOCIAL_LINK.search(text)
    fb = FB_LINK.search(text)

    if tg_video:  # video file seedha bheji gayi
        if tg_video.get("file_size", 0) > 20 * 1024 * 1024:
            reply(chat_id, "Telegram bot 20 MB se bari video nahi le sakta. Video ka link bhej dein "
                           "(TikTok/Instagram/Facebook), ya choti video bhejein.")
            return
        video = {"tg": tg_video["file_id"]}
        own_video = True  # aap ne khud bheji: aap ki apni video samjhi jayegi
    elif sv:  # TikTok / Instagram link
        info = video_info(sv.group(0))
        if not info:
            reply(chat_id, "Is link se video ki maloomat nahi mil saki. Video file seedha bhej dein (20 MB tak).")
            return
        desc = clean_text(info.get("description") or info.get("title") or "")
        extra = SOCIAL_LINK.sub(" ", text).strip()
        text = (desc + "\n" + extra).strip()
        if is_own_account(info):
            video, own_video = {"url": sv.group(0)}, True
        else:
            link = sv.group(0)  # doosre ki video: link ke saath share (copyright se bachao)
    elif fb:  # Facebook post share kiya gaya: us link ka preview (text + photo) parhna
        ptext, pimg = fetch_fb_preview(fb.group(0))
        extra = FB_LINK.sub(" ", text).strip()
        is_video = bool(FB_VIDEO_HINT.search(fb.group(0)))
        if len(ptext) < 20:  # preview band mila: public video/reel ki tafseel doosre tareeqe se
            info = video_info(fb.group(0))
            if info:
                desc = clean_text(info.get("description") or "")
                title = clean_text(info.get("title") or "")
                cand = desc if len(desc) >= len(title) else title
                if len(cand) >= 20 and not re.match(r"^(video|reel|facebook)\b", cand, re.I):
                    ptext = cand
                    is_video = is_video or bool(info.get("duration") or info.get("formats"))
                    if not pimg:
                        pimg = info.get("thumbnail") or ""
        if len(ptext) < 20 and len(extra) < 15:
            reply(chat_id, "Facebook ne is post ka text nahi diya (shayad post band/private hai). "
                           "Post ka screenshot bhej dein, main us se khabar parh lunga.")
            return
        text = (ptext + "\n" + extra).strip()
        if is_video:
            link = fb.group(0)  # video wali post: asal video ka link lagega
        elif not photo and pimg:
            photo = pimg
    elif photo and len(text) < 15:  # sirf photo bina text: screenshot samjho, us se khabar parho
        screenshot = tg_download(photo)
        photo = None
        if not screenshot or not GEMINI_KEY:
            reply(chat_id, "Screenshot parh nahi saka. Khabar ka text bhej dein.")
            return
    if len(text) < 15 and not screenshot and not own_video:
        reply(chat_id, "Khabar ka text, Facebook post ka share link, ya screenshot bhejein.")
        return

    key = item_key((text or str(video) or str(len(screenshot or b"")))[:200])
    if key in S["seen"]:
        reply(chat_id, "Ye khabar pehle hi aa chuki hai.")
        return
    S["seen"][key] = time.time()

    reason = blocked_reason(text)
    res = None
    if len(text) >= 15 or screenshot:
        res = rewrite_forwarded(text, screenshot, own_video) if (GEMINI_KEY or GROQ_KEY) else None
        if screenshot and not res:
            reply(chat_id, "Screenshot se khabar parh nahi saka. Khabar ka text bhej dein.")
            return
        if res and res.get("not_news") and not own_video:
            reply(chat_id, "Is mein koi khabar nazar nahi aayi, is liye post nahi ki.")
            return
        if not reason and res and res.get("blocked"):
            reason = "AI"
    if reason:
        stat("blocked")
        reply(chat_id, "⛔ Ye post nahi hogi: is mein mazhab, gaali-galoch ya fauj ka zikr hai.")
        return
    raw = res["post"] if res else text
    body = finish(raw) + "\n\n" if raw.strip() else ""
    credit = f"✍️ {LBL.get('reporter', 'رپورٽ')}: {contributors[chat_id]}\n\n" if chat_id in contributors else ""
    message = f"{body}{credit}{footer()}"
    if blocked_reason(message):
        reply(chat_id, "⛔ Ye post nahi hogi: is mein mazhab, gaali-galoch ya fauj ka zikr hai.")
        return

    if owner:  # aap ne khud chuni hai: seedha post
        if video:
            tg_send("⏳ Video upload ho rahi hai…")
        ok = fb_post(message, link=link, photo=photo, video=video, count=False)
        if ok and raw.strip():
            record_title(raw)
        if ok:
            note = ""
            if link and not video:
                note = "\n(Ye doosre ki video thi, is liye asal video ke link ke saath lagayi, copyright se bachne ke liye.)"
            tg_send("✅ Page par post ho gayi." + note)
        else:
            S["seen"].pop(key, None)  # dobara bhejne par phir koshish ho
            tg_send("⚠️ Post nahi ho saki, thori der baad dobara bhejein.")
        return
    S["pending"][key] = {"message": message, "link": link, "photo": photo, "video": video, "added": time.time()}
    stat("review")
    reply(chat_id, "✅ Shukriya! Aap ki khabar mil gayi, admin ki manzoori ke baad page par lagegi.")
    kind = " + video" if video else " + photo" if photo else " + link" if link else ""
    preview = "🟠 SAHAFI KI KHABAR (" + contributors[chat_id] + ")" + kind + "\n\n" + message + (f"\n{link}" if link else "")
    tg_send(preview, [{"text": "✅ Post karo", "callback_data": "ok:" + key},
                      {"text": "❌ Reject", "callback_data": "no:" + key}])


SOCIAL_LINK = re.compile(r"https?://(?:[a-z]+\.)?(?:tiktok\.com|instagram\.com|instagr\.am)/\S+", re.I)
FB_VIDEO_HINT = re.compile(r"fb\.watch|/videos?/|/reel/|/watch|/share/v/|/share/r/", re.I)


def video_info(url):
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as y:
            return y.extract_info(url, download=False)
    except Exception as e:
        log("video info error:", str(e)[:200])
        return None


def is_own_account(info):
    """Sirf config ke `my_accounts` mein likhe aap ke apne accounts ki video asal video ki tarah upload hogi."""
    mine = {str(x).lower().lstrip("@") for v in CONFIG.get("my_accounts", {}).values() for x in v if x}
    if not mine:
        return False
    found = {str(info.get(k) or "").lower().lstrip("@") for k in ("uploader", "uploader_id", "channel", "channel_id", "creator")}
    return bool(mine & found)


def download_video(video):
    """Video ko temp file mein lana: Telegram file ya apne account ka link."""
    import tempfile
    d = tempfile.mkdtemp()
    if video.get("tg"):
        data = tg_download(video["tg"])
        if not data:
            return None
        path = os.path.join(d, "v.mp4")
        with open(path, "wb") as f:
            f.write(data)
        return path
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "outtmpl": d + "/v.%(ext)s",
                "format": "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best",
                "max_filesize": 900 * 1024 * 1024}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(video["url"], download=True)
            path = y.prepare_filename(info)
        return path if os.path.exists(path) else None
    except Exception as e:
        log("video download error:", str(e)[:200])
        return None


def rewrite_forwarded(text, image=None, own_video=False):
    where = ("The report is in the attached image (a screenshot of a social media post): read its text. "
             if image else "Below is a local news report someone sent (Sindhi, Urdu, Roman Urdu or English).\n")
    prompt = (
        "You prepare posts for a Facebook news page about Naushahro Feroze district, Sindh, Pakistan.\n" + where +
        "Return JSON only: {\"not_news\": bool, \"blocked\": bool, \"post\": string}\n"
        "- not_news: true if there is no actual news in it (only greetings, ads, jokes, personal posts).\n"
        + ("This text is the caption of the page owner's own video: if it is not news, still write a short, "
           "friendly Sindhi caption from it.\n" if own_video else "") +
        "- blocked: true if ANY of: (a) insult/disrespect of any religion, sect, prophet, religious figure, holy book "
        "or place, blasphemy accusations, sectarian hatred; (b) abuse, cursing, gaali or insulting language, or "
        "someone abusing someone; (c) any mention of the Pakistani military (Army, ISPR, Rangers, FC, Navy, Air Force, "
        "agencies, soldiers). When in doubt, true.\n"
        "- post: rewrite the report as a clear Facebook news post in Sindhi (Arabic script); if you cannot write correct "
        "Sindhi use Urdu, Roman Urdu only as last option. Keep ALL facts (names, places, numbers) exactly; NEVER add any "
        "fact. Remove phone numbers, personal attacks, opinions and emojis. Neutral tone. For deaths and accidents "
        "add one short respectful line of condolence. 2-6 sentences. No hashtags. "
        "Write it in your own words; do not copy sentences. Do not end the post with a full stop; end it with !\n\n"
        "REPORT:\n" + (text or "")[:3000])
    for fn, key in ((ask_gemini, GEMINI_KEY), (ask_groq, GROQ_KEY)):
        if key and not (image and fn is ask_groq):
            out = fn(prompt, image) if fn is ask_gemini else fn(prompt)
            if isinstance(out, dict) and isinstance(out.get("post"), str) and out["post"].strip():
                return out
    return None


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


UA = {"User-Agent": "Mozilla/5.0 (compatible; NFUpdatesBot/1.0)"}


def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def mentions_district(text):
    return word_match(text, CONFIG["district_towns"])


def fetch(kind):
    """kind = news ya jobs. Google News + akhbaaron ke feeds + naukri pages + Telegram channels."""
    queries = CONFIG["news_queries"] if kind == "news" else CONFIG["job_queries"]
    sources = [(gnews_url(q, lang), None, False) for q in queries for lang in ("ur", "en")]
    # akhbaaron ke aam feeds: in mein sab khabrein hoti hain, is liye sirf district wali li jayengi
    sources += [(f["url"], f.get("name"), True) for f in CONFIG.get("extra_feeds", []) if f.get("type", "news") == kind]
    max_age = CONFIG["max_age_hours"] * 3600
    items, keys = [], set()

    def add(title, link, domain, source, ts, local=False):
        k = item_key(title)
        if not title or not link or k in keys:
            return
        keys.add(k)
        items.append({"key": k, "title": title, "link": link, "domain": domain,
                      "source": source or domain, "ts": ts, "local": local})

    for u, name, need_district in sources:
        try:
            r = requests.get(u, timeout=25, headers=UA)
            feed = feedparser.parse(r.content)
        except Exception as e:
            log("feed error:", u, e)
            continue
        for e in feed.entries:
            title = clean_text(e.get("title", ""))
            link = e.get("link", "")
            src = e.get("source") or {}
            src_title = src.get("title", "") if hasattr(src, "get") else ""
            src_href = src.get("href", "") if hasattr(src, "get") else ""
            if src_title and title.endswith(" - " + src_title):
                title = title[: -(len(src_title) + 3)].strip()
            pub = e.get("published_parsed") or e.get("updated_parsed")
            ts = calendar.timegm(pub) if pub else time.time()
            if time.time() - ts > max_age:
                continue
            if need_district and not (mentions_district(title) or
                                      mentions_district(clean_text(e.get("summary", ""))[:250])):
                continue
            domain = urlparse(src_href or link).netloc.lower().removeprefix("www.")
            add(title, link, domain, src_title or name or feed.feed.get("title"), ts, need_district)

    for ch in CONFIG.get("telegram_channels", []):
        if ch.get("type", "news") == kind:
            for it in fetch_telegram_channel(ch["name"], max_age):
                if kind == "news" and not mentions_district(it["title"] + " " + it["text"][:300]):
                    continue
                add(it["title"], it["link"], "t.me", "Telegram: " + ch["name"], it["ts"],
                    mentions_district(it["text"]))

    if kind == "jobs":
        for it in fetch_job_pages():
            add(it["title"], it["link"], it["domain"], it["source"], it["ts"], True)

    log(f"{kind}: {len(items)} items mile")
    return items


def fetch_telegram_channel(name, max_age):
    """Public Telegram channel ka web preview (t.me/s/naam) parhna. Koi login nahi chahiye."""
    out = []
    try:
        r = requests.get(f"https://t.me/s/{name}", timeout=25, headers=UA)
    except Exception as e:
        log("telegram channel error:", name, e)
        return out
    for block in r.text.split('class="tgme_widget_message_wrap')[1:]:
        post = re.search(r'data-post="([^"]+)"', block)
        body = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        when = re.search(r'<time[^>]*datetime="([^"]+)"', block)
        if not (post and body):
            continue
        text = clean_text(body.group(1).replace("<br/>", "\n").replace("<br>", "\n"))
        try:
            ts = dt.datetime.fromisoformat(when.group(1)).timestamp() if when else time.time()
        except ValueError:
            ts = time.time()
        if time.time() - ts > max_age or len(text) < 15:
            continue
        title = text if len(text) <= 160 else text[:160].rsplit(" ", 1)[0] + "…"
        out.append({"title": title, "text": text, "link": "https://t.me/" + post.group(1), "ts": ts})
    return out


def fetch_job_pages():
    """Naukri websites ke shehar wale pages (in ka RSS nahi hota). Naya link = nayi naukri."""
    out = []
    for p in CONFIG.get("job_pages", []):
        try:
            r = requests.get(p["url"], timeout=25, headers=UA)
        except Exception as e:
            log("job page error:", p["url"], e)
            continue
        links = []
        for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S | re.I):
            href = m.group(1)
            if not re.search(p["link_pattern"], href):
                continue
            link = urljoin(p["url"], href)
            if link in (l for l, _ in links):
                continue
            text = clean_text(m.group(2))
            if len(text) < 8:  # link ka text na ho to URL se naam banana
                slug = re.sub(r"-\d+/?$", "", link.rstrip("/").rsplit("/", 1)[-1])
                text = slug.replace("-", " ").title()
            links.append((link, text))
        known = S.setdefault("job_links", [])
        seeded = S.setdefault("job_pages_seeded", [])
        new = [(l, t) for l, t in links if l not in known]
        if p["url"] not in seeded:
            # pehli dafa: purani naukriyan na bheji jayen, sirf sab se upar wali 2 (sab se nayi)
            known.extend(l for l, _ in new[2:])
            new = new[:2]
            seeded.append(p["url"])
        known.extend(l for l, _ in new)
        del known[:-600]
        for link, text in new:
            out.append({"title": text, "link": link, "domain": urlparse(link).netloc.lower().removeprefix("www."),
                        "source": p.get("name", ""), "ts": time.time()})
    return out


# ---------------------------------------------------------------- AI (layer 1 + 2)
def build_prompt(item):
    return (
        "You write posts for a Facebook news page about Naushahro Feroze district, Sindh, Pakistan.\n"
        f"Headline: {item['title']}\nSource: {item['source']}\n\n"
        "Return JSON only: {\"relevant\": bool, \"sensitive\": bool, \"blocked\": bool, \"post\": string, \"lang\": string}\n"
        "- blocked: true if ANY of these is true (when in doubt, true):\n"
        "  (a) it involves religion in a negative or controversial way: insult or disrespect of any religion, sect, "
        "prophet, religious figure, holy book or place; blasphemy cases or accusations; sectarian hatred or conflict;\n"
        "  (b) anyone abusing, cursing or insulting someone (gaali, bad language, slurs), or the text itself contains abusive words;\n"
        "  (c) it mentions the Pakistani military in any way: Pakistan Army, ISPR, army chief, Rangers, FC, Navy, "
        "Air Force, intelligence agencies, or any soldier/military matter.\n"
        f"- relevant: true only if the news is about Naushahro Feroze district or its towns: {', '.join(CONFIG['district_towns'])}.\n"
        "- sensitive: true if it involves crime: murder, firing/shooting, robbery, kidnapping, sexual violence, "
        "torture, suicide, honour killing, violent protest, or a fight or dispute between people or groups. "
        "Accidents (road, traffic, train, fire, drowning, building collapse, natural disaster) and the deaths or "
        "injuries caused by them are NOT sensitive: set false for those, unless a crime is also involved.\n"
        "- post: rewrite ONLY the information in the headline as a short Facebook post (1-2 sentences). "
        "Write in Sindhi (Arabic script). If you cannot write correct Sindhi, write Urdu; Roman Urdu only as last option. "
        "NEVER add any fact, name, number, place or detail that is not in the headline. No hashtags, no links, no emojis. "
        "Keep it neutral: no opinion, no blame, no insulting or emotional words. "
        "For accidents and deaths write respectfully and add one short line of condolence/prayer for the victims.\n"
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


def ask_gemini(prompt, image=None):
    global _discovered
    parts = [{"text": prompt}]
    if image:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}})
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
                    json={"contents": [{"parts": parts}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}},
                    timeout=60)
                if r.status_code == 200:
                    S["gemini_model"] = model
                    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                log("gemini", model, r.status_code, r.text[:120].replace("\n", " "))
                if r.status_code == 404 or "no longer available" in r.text or "not found" in r.text.lower():
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


def tg_download(file_id):
    res = tg("getFile", file_id=file_id)
    path = (res.get("result") or {}).get("file_path")
    if not path:
        return None
    r = requests.get(f"https://api.telegram.org/file/bot{TG_TOKEN}/{path}", timeout=60)
    return r.content if r.status_code == 200 else None


def fb_post(message, link=None, photo=None, video=None, count=True):
    ok = _fb_post(message, link, photo, video, count)
    if ok and not DRY_RUN and not blocked_reason(message):
        try:
            crosspost(message, link, photo, video)
        except Exception as e:
            log("telegram channel error:", e)
    return ok


def _fb_post(message, link=None, photo=None, video=None, count=True):
    reason = blocked_reason(message)
    if reason:  # aakhri hifazat: koi bhi post jo pabandi wale alfaaz rakhti ho, kabhi nahi jayegi
        log(f"BLOCKED at posting ({reason}):", message[:60])
        return True  # queue se hata do
    if DRY_RUN:
        tg_send("🧪 TEST - Facebook par post NAHI hua" + (" (video ke saath)" if video else " (photo ke saath)" if photo else "") + ":\n\n"
                + message + (f"\n{link}" if link else ""))
        log("DRY RUN post:", message[:60])
        return True
    if not (FB_PAGE_ID and FB_TOKEN):
        log("FB_PAGE_ID / FB_PAGE_TOKEN missing")
        return False
    try:
        if video:
            path = download_video(video)
            if path:
                with open(path, "rb") as f:
                    r = requests.post(f"https://graph-video.facebook.com/{CONFIG.get('graph_version', 'v23.0')}/{FB_PAGE_ID}/videos",
                                      data={"description": message, "access_token": FB_TOKEN},
                                      files={"source": ("video.mp4", f, "video/mp4")}, timeout=900)
                if r.status_code == 200:
                    log("video posted:", r.json().get("id"))
                    stat("posted")
                    if count:
                        S["daily"]["count"] += 1
                    return True
                log("video upload error:", r.text[:200])
            tg_send("⚠️ Video upload nahi ho saki, sirf text post kar raha hoon.")
        img = None
        if photo and not photo.startswith("http"):
            img = tg_download(photo)
            if not img:
                log("photo download nahi hui, sirf text post")
                photo = None
        if photo and photo.startswith("http"):
            r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/photos", timeout=90,
                              data={"caption": message, "url": photo, "access_token": FB_TOKEN})
            if r.status_code != 200:  # photo na lag saki to sirf text
                log("photo url error, text post:", r.text[:150])
                r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", timeout=30,
                                  data={"message": message, "access_token": FB_TOKEN})
        elif photo:
            r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/photos", timeout=90,
                              data={"caption": message, "access_token": FB_TOKEN},
                              files={"source": ("photo.jpg", img, "image/jpeg")})
        else:
            data = {"message": message, "access_token": FB_TOKEN}
            if link:
                data["link"] = link
            r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", data=data, timeout=30)
            if r.status_code != 200 and link and ("1500" in r.text or "url" in r.text.lower()):
                # Facebook kuch links (maslan apne share links) qubool nahi karta: link text mein likh do
                log("link qubool nahi hua, text mein likh kar post:", r.text[:120])
                r = requests.post(f"{GRAPH}/{FB_PAGE_ID}/feed", timeout=30,
                                  data={"message": f"{message}\n\n🔗 {link}", "access_token": FB_TOKEN})
    except Exception as e:
        log("FB error:", e)
        return False
    if r.status_code == 200:
        log("posted:", r.json().get("id"))
        stat("posted")
        if count:
            S["daily"]["count"] += 1
        return True
    log("FB error:", r.text[:300])
    stat("fb_error")
    STATS["fb_error_text"] = r.text[:200]
    alert("Facebook par post nahi hua. Token ya permission check karein:\n" + r.text[:300])
    return False


def compose(item, text):
    text = finish(text)
    return f"{text}\n\n📌 {LBL['source']}: {item['source']}\n\n{footer()}"


def publish_queue():
    posted = 0
    while S["queue"] and posted < CONFIG["max_posts_per_run"] and can_post():
        q = S["queue"][0]
        if not fb_post(q["message"], q.get("link"), q.get("photo"), q.get("video")):
            break
        S["queue"].pop(0)
        record_title(q["message"])
        posted += 1


# ---------------------------------------------------------------- steps
def handle_news():
    allitems = fetch("news")
    items = [i for i in allitems if i["key"] not in S["seen"]]
    stat("news_found", len(allitems))
    stat("news_old", len(allitems) - len(items))
    items.sort(key=lambda i: i["ts"], reverse=True)
    done = 0
    for it in items:
        if done >= CONFIG["max_new_per_run"]:
            break  # baqi agle round mein
        S["seen"][it["key"]] = time.time()
        if not is_trusted(it["domain"]):
            log("untrusted source, skip:", it["domain"])
            stat("untrusted")
            continue
        reason = blocked_reason(it["title"])
        if reason:
            log(f"BLOCKED ({reason}), kabhi post nahi hogi:", it["title"][:60])
            stat("blocked")
            continue
        done += 1
        res = ask_ai(it) if (GEMINI_KEY or GROQ_KEY) else None
        if res is not None and (res.get("blocked") or blocked_reason(str(res.get("post", "")))):
            log("BLOCKED (AI: mazhab / gaali / fauj), kabhi post nahi hogi:", it["title"][:60])
            stat("blocked")
            time.sleep(4)
            continue
        if res is not None:
            time.sleep(4)  # free limit ke liye
            if res.get("relevant") is False:
                log("relevant nahi:", it["title"][:60])
                stat("irrelevant")
                continue
        elif not word_match(it["title"], CONFIG["district_towns"]):
            # bina AI ke sirf woh khabar jis ki headline mein district/shehar ka naam ho
            log("headline mein district ka naam nahi, skip:", it["title"][:60])
            stat("irrelevant")
            continue
        text = res["post"].strip() if res else f"{LBL['news_icon']} {it['title']}"
        message = compose(it, text)
        sensitive = keyword_sensitive(it["title"]) or bool(res and res.get("sensitive"))
        if sensitive:
            if not (TG_TOKEN and TG_CHAT):
                log("sensitive aur Telegram nahi, skip:", it["title"][:60])
                continue
            S["pending"][it["key"]] = {"message": message, "link": it["link"], "added": time.time()}
            stat("review")
            tg_send("🟠 REVIEW: ye khabar sensitive hai. Post karni hai?\n\n" + message + "\n\n🔗 " + it["link"],
                    [{"text": "✅ Post karo", "callback_data": "ok:" + it["key"]},
                     {"text": "❌ Reject", "callback_data": "no:" + it["key"]}])
        else:
            S["queue"].append({"message": message, "link": it["link"], "added": time.time(), "title": it["title"]})
            stat("queued")


def handle_jobs():
    for it in fetch("jobs"):
        if it["key"] in S["seen"]:
            continue
        S["seen"][it["key"]] = time.time()
        if not is_trusted(it["domain"]) or word_match(it["title"], CONFIG["job_scam_words"]):
            continue
        reason = blocked_reason(it["title"])
        if reason:
            log(f"BLOCKED job ({reason}):", it["title"][:60])
            continue
        it["local"] = it.get("local") or word_match(it["title"], CONFIG["district_towns"])
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
    lines += [LBL["jobs_warning"], "", footer()]
    if fb_post("\n".join(lines)):
        S["jobs"] = []


def footer():
    """Har post ke neeche: follow/share ki dawat + hashtags."""
    line = CONFIG.get("follow_line", "").strip()
    return (line + "\n\n" if line else "") + CONFIG["hashtags"]


WEATHER_SD = [((0,), "☀️ صاف آسمان"), ((1, 2, 3), "⛅ ڪجهه ڪڪر"), ((45, 48), "🌫️ ڪوهيڙو"),
              ((51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82), "🌧️ مينهن جو امڪان"),
              ((95, 96, 99), "⛈️ طوفاني مينهن جو امڪان")]


def handle_daily():
    """Roz subah: Naushahro Feroze ka mausam, namaz ke auqaat aur tareekh. Followers ki roz ki aadat."""
    d = CONFIG.get("daily_post", {})
    if not d.get("enabled", True) or now().hour < d.get("hour", 7) or S.get("last_daily") == today():
        return
    lat, lon = d.get("lat", 26.84), d.get("lon", 68.12)
    lines = [f"🌅 {d.get('title', 'نوشهروفيروز جو اڄ')} | {now().strftime('%d-%m-%Y')}"]
    try:
        p = requests.get("https://api.aladhan.com/v1/timings", timeout=25,
                         params={"latitude": lat, "longitude": lon, "method": 1, "school": 1}).json()["data"]
        hj = p["date"]["hijri"]
        lines.append(f"🗓️ {hj['day']} {hj['month']['ar']} {hj['year']}ھ")
        t = p["timings"]
        lines += ["", "🕌 نماز جا وقت:",
                  f"فجر {t['Fajr']} | ظهر {t['Dhuhr']} | عصر {t['Asr']}",
                  f"مغرب {t['Maghrib']} | عشا {t['Isha']}", f"🌄 سج اڀرڻ {t['Sunrise']}"]
    except Exception as e:
        log("namaz times error:", e)
    try:
        w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=25, params={
            "latitude": lat, "longitude": lon, "timezone": "Asia/Karachi", "forecast_days": 1,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"}).json()["daily"]
        code = w["weather_code"][0]
        sky = next((s for codes, s in WEATHER_SD if code in codes), "")
        lines += ["", "🌡️ اڄ جو موسم:", sky,
                  f"وڌ ۾ وڌ گرمي پد {round(w['temperature_2m_max'][0])}° | گهٽ ۾ گهٽ {round(w['temperature_2m_min'][0])}°"]
        rain = w.get("precipitation_probability_max", [None])[0]
        if rain:
            lines.append(f"مينهن جو امڪان {rain}%")
    except Exception as e:
        log("weather error:", e)
    if len(lines) < 4:  # dono API na chalein to post na karo
        return
    lines += ["", d.get("closing", "اوهان سڀني جو ڏينهن سٺو گذري!"), "", footer()]
    if fb_post("\n".join(lines)):
        S["last_daily"] = today()


def crosspost(message, link=None, photo=None, video=None):
    """Telegram public channel par bhi post (agar config mein channel likha ho)."""
    ch = CONFIG.get("telegram_channel", "").strip()
    if not ch or not TG_TOKEN:
        return
    text = message + (f"\n\n{link}" if link else "")
    if photo and len(message) <= 1000:
        tg("sendPhoto", chat_id=ch, photo=photo, caption=text)
    elif video and video.get("tg") and len(message) <= 1000:
        tg("sendVideo", chat_id=ch, video=video["tg"], caption=text)
    else:
        tg("sendMessage", chat_id=ch, text=text[:4000])


def record_title(text):
    """Aaj post hui khabron ki list (raat ki roundup post ke liye)."""
    t = S.setdefault("today_titles", {"date": "", "items": []})
    if t["date"] != today():
        t.update(date=today(), items=[])
    line = re.sub(r"^[^\w\u0600-\u06FF]+", "", (text or "").strip().splitlines()[0] if text else "")
    line = re.sub(r"[\s.۔!]+$", "", line)[:110]
    if len(line) > 10 and line not in t["items"]:
        t["items"].append(line)


def handle_roundup():
    """Din mein do dafa (subah 6, shaam 6) poore Sindh ki ahem khabron ki list, alag post."""
    cfg = CONFIG.get("sindh_roundup", {})
    if not cfg.get("enabled", True):
        return
    slot = None
    for name, hour in (("am", cfg.get("morning_hour", 6)), ("pm", cfg.get("evening_hour", 18))):
        start = hour if name == "am" else hour
        end = 12 if name == "am" else 24
        if start <= now().hour < end and S.get("roundup_" + name) != today():
            slot = name
    if not slot:
        return
    S["roundup_" + slot] = today()
    items = sindh_headlines(cfg)
    if len(items) < cfg.get("min_items", 4):
        log("sindh roundup: kaafi khabrein nahi mili", len(items))
        return
    lines = [cfg.get("title_am" if slot == "am" else "title_pm", "📋 سنڌ جون اهم خبرون"), ""]
    lines += [f"🔹 {finish(x)}" for x in items]
    lines += ["", footer()]
    fb_post("\n".join(lines))


def sindh_headlines(cfg):
    """Pichle 12 ghante ki Sindh ki khabrein: bharosemand, bina pabandi aur bina jurm wali, Sindhi mein ek line."""
    max_age = cfg.get("max_age_hours", 12) * 3600
    urls = [gnews_url(q, lang) for q in cfg.get("queries", ["Sindh"]) for lang in ("ur", "en")]
    urls += cfg.get("feeds", [])
    seen_keys, raw = set(), []
    for u in urls:
        try:
            feed = feedparser.parse(requests.get(u, timeout=25, headers=UA).content)
        except Exception as e:
            log("roundup feed error:", u, e)
            continue
        for e in feed.entries:
            title = clean_text(e.get("title", ""))
            src = e.get("source") or {}
            st = src.get("title", "") if hasattr(src, "get") else ""
            if st and title.endswith(" - " + st):
                title = title[: -(len(st) + 3)].strip()
            pub = e.get("published_parsed") or e.get("updated_parsed")
            ts = calendar.timegm(pub) if pub else time.time()
            domain = urlparse((src.get("href") if hasattr(src, "get") else "") or e.get("link", "")).netloc.lower().removeprefix("www.")
            k = item_key(title)
            if (len(title) < 15 or k in seen_keys or time.time() - ts > max_age or not is_trusted(domain)
                    or blocked_reason(title) or keyword_sensitive(title)):
                continue
            seen_keys.add(k)
            raw.append((ts, title))
    raw.sort(reverse=True)
    titles = [t for _, t in raw[:25]]
    if not titles:
        return []
    want = cfg.get("max_items", 8)
    if GEMINI_KEY or GROQ_KEY:
        prompt = ("Below are recent news headlines from Sindh, Pakistan. Pick the " + str(want) + " most important "
                  "for people of Sindh (public interest: government decisions, education, health, weather, prices, "
                  "development, jobs, sports). Skip duplicates, crime, violence, politics fights, anything about "
                  "religion controversy, abusive content or the military. Write each as ONE short line in Sindhi "
                  "(Arabic script), only facts from the headline, no full stop at the end.\n"
                  "Return JSON: {\"items\": [string]}\n\nHEADLINES:\n" + "\n".join(f"- {t}" for t in titles))
        out = ask_gemini(prompt) if GEMINI_KEY else None
        if not out and GROQ_KEY:
            out = ask_groq(prompt)
        items = [clean_text(x) for x in (out or {}).get("items", []) if isinstance(x, str)]
        items = [x for x in items if len(x) > 8 and not blocked_reason(x)]
        if items:
            return items[:want]
    return titles[:want]


def handle_engagement():
    """Hafte mein kuch din shaam ko sawal wali post: comments se reach barhti hai."""
    cfg = CONFIG.get("engagement", {})
    qs = cfg.get("questions", [])
    if (not cfg.get("enabled", True) or not qs or now().weekday() not in cfg.get("days", [0, 2, 4])
            or now().hour < cfg.get("hour", 20) or S.get("last_question") == today()):
        return
    i = S.get("q_index", 0) % len(qs)
    if fb_post(f"💬 {qs[i]}\n\n{footer()}"):
        S["q_index"] = i + 1
        S["last_question"] = today()


def handle_auto_reply():
    """Page ki posts par aaye comments ka jawab, har comment ke 1-10 minute baad (random), taake insaani lage.
    Is ke liye token mein pages_read_user_content aur pages_manage_engagement chahiye."""
    cfg = CONFIG.get("auto_reply", {})
    if not cfg.get("enabled") or DRY_RUN or not (FB_PAGE_ID and FB_TOKEN) or not cfg.get("replies"):
        return
    replied = S.setdefault("replied", [])
    try:
        r = requests.get(f"{GRAPH}/{FB_PAGE_ID}/posts", timeout=30, params={
            "access_token": FB_TOKEN, "limit": 8,
            "fields": "id,comments.limit(40){id,message,from,created_time,comments.limit(10){from}}"})
        if r.status_code != 200:
            log("auto reply read error:", r.text[:200])
            return
        posts = r.json().get("data", [])
    except Exception as e:
        log("auto reply error:", e)
        return
    lo, hi = cfg.get("delay_min_minutes", 1) * 60, cfg.get("delay_max_minutes", 10) * 60
    window = cfg.get("wait_window_minutes", 9) * 60  # is run mein zyada se zyada itna intezar
    started = time.time()
    todo = []
    for p in posts:
        for c in (p.get("comments") or {}).get("data", []):
            cid, frm = c.get("id"), (c.get("from") or {}).get("id")
            if not cid or cid in replied or frm == FB_PAGE_ID:
                continue
            kids = (c.get("comments") or {}).get("data", [])
            if any((k.get("from") or {}).get("id") == FB_PAGE_ID for k in kids) or blocked_reason(c.get("message", "")):
                replied.append(cid)  # pehle se jawab hai, ya gaali/pabandi wala comment: chhor do
                continue
            try:
                created = dt.datetime.strptime(c.get("created_time", ""), "%Y-%m-%dT%H:%M:%S%z").timestamp()
            except ValueError:
                created = started
            if started - created > 2 * 24 * 3600:
                replied.append(cid)  # bohat purana comment
                continue
            due = created + random.Random(cid).randint(lo, hi)  # har comment ka apna random waqt
            if due <= started + window:
                todo.append((due, cid))
    todo.sort()
    done = 0
    for due, cid in todo[: cfg.get("max_per_run", 10)]:
        wait = due - time.time()
        if wait > 0:
            if time.time() + wait - started > window:
                break  # agle run mein
            time.sleep(wait)
        msg = random.choice(cfg["replies"])
        try:
            rr = requests.post(f"{GRAPH}/{cid}/comments", timeout=30, data={"message": msg, "access_token": FB_TOKEN})
            replied.append(cid)
            if rr.status_code == 200:
                done += 1
                stat("replies")
            else:
                log("reply error:", rr.text[:150])
                if "permission" in rr.text.lower():
                    alert("Comments ka jawab nahi diya ja saka: token mein pages_manage_engagement ijazat chahiye.")
                    return
        except Exception as e:
            log("reply error:", e)
    log("comment replies:", done)
    del replied[:-1500]


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


def send_report():
    """Jab aap khud 'Run workflow' dabayen, Telegram par is run ki report."""
    if os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch":
        return
    g = STATS.get
    lines = ["📋 Run report" + (" (TEST)" if DRY_RUN else ""),
             f"Khabrein mili: {g('news_found', 0)} (pehle dekhi hui: {g('news_old', 0)})",
             f"✅ Post hui: {g('posted', 0)} | Queue mein (agle runs): {len(S['queue'])}",
             f"🟠 Review ke liye bheji: {g('review', 0)}",
             f"⛔ Pabandi (mazhab/gaali/fauj): {g('blocked', 0)}",
             f"➖ District ki nahi: {g('irrelevant', 0)} | Ghair-bharosemand website: {g('untrusted', 0)}",
             f"💼 Naukriyan jama: {len(S['jobs'])} | Aaj ki posts: {S['daily']['count']}"]
    if g("fb_error"):
        lines.append("⚠️ Facebook error: " + g("fb_error_text", ""))
    if not g("news_found"):
        lines.append("Is waqt district ki koi nayi khabar online nahi mili.")
    tg_send("\n".join(lines))


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
        handle_daily()
        handle_engagement()
        handle_roundup()
        handle_auto_reply()
    except Exception:
        err = traceback.format_exc()
        log(err)
        alert("System mein error aaya:\n" + err[-600:])
    send_report()
    if DRY_RUN:
        log("test mode: state save nahi kiya")
    else:
        save_state()
    log("done. aaj ki posts:", S["daily"]["count"], "| queue:", len(S["queue"]), "| review:", len(S["pending"]))


if __name__ == "__main__":
    main()
