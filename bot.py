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
import math
import os
import random
import re
import time
import traceback
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

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
                f"Sahafi: {len(contributors)}\n"
                f"Aaj kul posts: {S.get('all_posts', {}).get('count', 0)}/{CONFIG.get('safety', {}).get('max_total_per_day', 50)}"
                f" | AI: {S.get('ai_usage', {}).get('ok', 0)} theek, {S.get('ai_usage', {}).get('limit', 0)} hadd,"
                f" {S.get('ai_usage', {}).get('fail', 0)} fail\n"
                f"Pichle run ke errors: {', '.join(S.get('last_errors', {}).get('steps', [])) or 'koi nahi'}\n\n"
                "Khabar post karne ke liye uska text (ya photo + text) mujhe bhej dein.\n"
                "Sahafi jorne ke liye: /add ID Naam   hatane ke liye: /remove ID   list: /sahafi\n"
                "Kaunsi khabrein pasand ho rahi hain: /likes")
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
    if owner and cmd == "/likes":
        tg_send(likes_report())
        return
    if owner and cmd == "/token":
        tg_send(token_report(check_token()))
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
    share_only = False
    source_credit = ""  # doosre ki post: asal banane wale ka naam
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
            link = info.get("webpage_url") or sv.group(0)  # doosre ki video: link ke saath share
            source_credit = credit_line(info, "TikTok" if "tiktok" in sv.group(0).lower() else "Instagram")
    elif fb:  # Facebook post share kiya gaya: us link ka preview (text + photo) parhna
        ptext, pimg = fetch_fb_preview(fb.group(0))
        extra = FB_LINK.sub(" ", text).strip()
        is_video = bool(FB_VIDEO_HINT.search(fb.group(0)))
        info = None
        if len(ptext) < 20 or is_video:  # video/reel ya band preview: tafseel aur naam doosre tareeqe se
            info = video_info(fb.group(0))
            if info:
                desc = clean_text(info.get("description") or "")
                title = clean_text(info.get("title") or "")
                cand = desc if len(desc) >= len(title) else title
                if len(ptext) < 20 and len(cand) >= 20 and not re.match(r"^(video|reel|facebook)\b", cand, re.I):
                    ptext = cand
                    is_video = is_video or bool(info.get("duration") or info.get("formats"))
                    if not pimg:
                        pimg = info.get("thumbnail") or ""
        share_only = len(ptext) < 20 and len(extra) < 15
        text = (ptext + "\n" + extra).strip()
        # Facebook post ko share ki tarah lagao: asal post ka pakka link (preview/video ke saath), credit ke saath.
        # Doosre ki photo/video dobara upload nahi hoti.
        link = canonical_fb_link(fb.group(0), info)
        source_credit = credit_line(info, "Facebook") if info else ""
        if share_only:
            # Text na mila: post ko share ki tarah lagao, Facebook khud asal post ka preview dikhayega
            text = ""
            if FB_LINK.search(link) and "/share/" in link:
                reply(chat_id, "Is post ka text ya asal link nahi mil saka. Post ka screenshot bhej dein.")
                return
    elif photo and len(text) < 15:  # sirf photo bina text: screenshot samjho, us se khabar parho
        screenshot = tg_download(photo)
        photo = None
        if not screenshot or not GEMINI_KEY:
            reply(chat_id, "Screenshot parh nahi saka. Khabar ka text bhej dein.")
            return
    if len(text) < 15 and not screenshot and not own_video and not share_only and not (sv and link):
        reply(chat_id, "Khabar ka text, Facebook post ka share link, ya screenshot bhejein.")
        return

    key = item_key((text or link or (video or {}).get("tg") or (video or {}).get("url") or str(len(screenshot or b"")))[:200])
    if key in S["seen"]:
        reply(chat_id, "Ye khabar pehle hi aa chuki hai.")
        return
    S["seen"][key] = time.time()

    reason = blocked_reason(text)
    res = None
    vid_url = link if (link and (sv or (fb and FB_VIDEO_HINT.search(fb.group(0))) or (fb and share_only))) else None
    if vid_url and not is_sindhi(text) and GEMINI_KEY and not reason:
        tr = transcribe_video(vid_url)  # video ki awaz sun kar Sindhi khabar
        if tr and tr.get("has_speech") and isinstance(tr.get("post"), str) and len(tr["post"].strip()) > 15:
            res, share_only = tr, False
    if res is not None:
        if res.get("blocked"):
            reason = "AI"
    elif share_only:
        pass  # sirf share: Facebook asal post ka preview dikhayega
    elif is_sindhi(text) and not screenshot:
        res = {"post": text}  # post pehle se Sindhi mein hai: bilkul wahi text
    elif len(text) >= 15 or screenshot:
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
    raw = res["post"] if res else ("" if share_only else text)
    body = finish(raw) + "\n\n" if raw.strip() else ""
    credit = f"✍️ {LBL.get('reporter', 'رپورٽ')}: {contributors[chat_id]}\n\n" if chat_id in contributors else ""
    if source_credit:
        credit = source_credit + "\n\n" + credit
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
            mark_shareable(raw or message)
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


SINDHI_LETTERS = set("ڪڏٿٽڄڃڳڱٻڀڻڦڙڌڊڍڇڪ")


def is_sindhi(text):
    """Sindhi ke khaas huroof hon to text Sindhi samjha jaye."""
    return sum(ch in SINDHI_LETTERS for ch in (text or "")) >= 3


def transcribe_video(url):
    """Video ki sirf awaz (audio) la kar Gemini se sunwana aur Sindhi khabar banwana. Video upload nahi hoti."""
    import tempfile
    d = tempfile.mkdtemp()
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "outtmpl": d + "/a.%(ext)s",
                "format": "bestaudio[filesize<15M]/bestaudio/worst[filesize<15M]/worst", "max_filesize": 18 * 1024 * 1024}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            path = y.prepare_filename(info)
    except Exception as e:
        log("transcribe download error:", str(e)[:150])
        return None
    if not os.path.exists(path) or os.path.getsize(path) > 19 * 1024 * 1024:
        return None
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"m4a": "audio/mp4", "mp3": "audio/mpeg", "webm": "audio/webm", "ogg": "audio/ogg", "opus": "audio/ogg",
            "wav": "audio/wav", "aac": "audio/aac", "mp4": "video/mp4"}.get(ext, "audio/mp4")
    prompt = (
        "This is the audio of a local news video from Sindh, Pakistan (speech may be Sindhi, Urdu or English).\n"
        "Return JSON only: {\"has_speech\": bool, \"blocked\": bool, \"post\": string}\n"
        "- has_speech: false if there is no clear spoken news (only music, noise, songs).\n"
        "- blocked: true if it insults any religion/sect/religious figure, involves blasphemy or sectarian hatred, "
        "contains abuse/gaali, or mentions the Pakistani military in any way. When in doubt, true.\n"
        "- post: write the news told in the video as a clear Facebook post in Sindhi (Arabic script), 2-5 sentences, "
        "only facts actually said in the video, neutral tone, no phone numbers, no hashtags, no full stop at the end.")
    with open(path, "rb") as f:
        return ask_gemini(prompt, f.read(), mime)


def credit_line(info, platform):
    """Asal banane wale ka credit, maslan: 📹 ذريعو: Ali Reporter (TikTok)"""
    name = ""
    if info:
        name = clean_text(str(info.get("uploader") or info.get("channel") or info.get("creator") or ""))
    return f"📹 {LBL.get('source', 'ذريعو')}: {name} ({platform})" if name else f"📹 {LBL.get('source', 'ذريعو')}: {platform}"


def canonical_fb_link(url, info=None):
    """facebook.com/share/... jaise links ko asal post ke link mein badalna (Facebook share links rad karta hai)."""
    def clean(u):
        p = urlparse(u)
        if not p.netloc.endswith("facebook.com") or "/share/" in p.path or "login" in p.path:
            return None
        keep = p.query if p.path.rstrip("/").split("/")[-1] in ("permalink.php", "story.php", "watch", "photo.php") else ""
        return f"https://www.facebook.com{p.path}" + (f"?{keep}" if keep else "")
    if info:
        for k in ("webpage_url", "original_url"):
            c = clean(str(info.get(k) or ""))
            if c:
                return c
    try:
        r = requests.get(url, headers=BROWSER_UA, timeout=20, allow_redirects=True)
        final = r.url
        if "login" in final:
            nxt = parse_qs(urlparse(final).query).get("next")
            if nxt:
                final = unquote(nxt[0])
        c = clean(final)
        if c:
            return c
    except Exception as e:
        log("fb link resolve error:", e)
    return url


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


def ai_count(kind):
    u = S.setdefault("ai_usage", {"date": "", "ok": 0, "fail": 0, "limit": 0})
    if u["date"] != today():
        u.update(date=today(), ok=0, fail=0, limit=0)
    u[kind] = u.get(kind, 0) + 1


def ask_gemini(prompt, image=None, mime="image/jpeg"):
    global _discovered
    parts = [{"text": prompt}]
    if image:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}})
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
                    ai_count("ok")
                    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                ai_count("fail" if r.status_code != 429 else "limit")
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


# ---------------------------------------------------------------- hifazat aur seekhna
def note_post():
    a = S.setdefault("all_posts", {"date": "", "count": 0, "last": 0})
    if a["date"] != today():
        a.update(date=today(), count=0)
    a["count"] += 1
    a["last"] = time.time()


def is_night():
    n0, n1 = CONFIG.get("safety", {}).get("night_hours", [0, 7])
    return n0 <= now().hour < n1


def pace_ok():
    """Page ki hifazat: din bhar ki kul hadd aur har nai post ke beech kam az kam waqfa (raat ko lamba)."""
    cfg = CONFIG.get("safety", {})
    a = S.setdefault("all_posts", {"date": "", "count": 0, "last": 0})
    if a["date"] != today():
        a.update(date=today(), count=0)
    gap = cfg.get("night_gap_minutes", 45) if is_night() else cfg.get("min_gap_minutes", 15)
    return a["count"] < cfg.get("max_total_per_day", 40) and time.time() - a.get("last", 0) >= gap * 60


def perf_record(section, category=""):
    """Post ka hisaab rakho taake baad mein dekh sakein log kaunsi khabrein pasand karte hain."""
    pid = S.get("last_post_id")
    if not pid or DRY_RUN:
        return
    P = S.setdefault("perf", {"posts": []})
    P["posts"].append({"id": pid, "sec": section, "cat": category or section, "t": int(time.time())})
    P["posts"] = P["posts"][-400:]


def handle_perf():
    """Kam az kam ek din purani posts ke likes/comments/shares parho (har run mein thodi)."""
    P = S.setdefault("perf", {"posts": []})
    if DRY_RUN or not FB_TOKEN:
        return
    wait = CONFIG.get("learning", {}).get("measure_after_hours", 20) * 3600
    todo = [x for x in P["posts"] if "score" not in x and time.time() - x["t"] >= wait][:15]
    for x in todo:
        try:
            r = requests.get(f"{GRAPH}/{x['id']}", timeout=20, params={
                "fields": "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),shares",
                "access_token": FB_TOKEN}).json()
        except Exception as e:
            log("perf error:", e)
            break
        if "error" in r:
            x["score"] = None  # post mit gayi ya parh nahi saka
            continue
        rc = ((r.get("reactions") or {}).get("summary") or {}).get("total_count", 0)
        cc = ((r.get("comments") or {}).get("summary") or {}).get("total_count", 0)
        sc = (r.get("shares") or {}).get("count", 0)
        x.update(likes=rc, comments=cc, shares=sc, score=rc + 2 * cc + 3 * sc)


def _avg(rows):
    return sum(r["score"] for r in rows) / len(rows) if rows else 0


def _window_secs():
    return CONFIG.get("learning", {}).get("window_days", 7) * 86400


def like_weight(key, value):
    """Pichle 7 din ki posts ki pasandeedgi: 1 = aam, 2 = do guna pasand, 0.5 = aadhi. Kam data ho to 1 ke qareeb."""
    cfg = CONFIG.get("learning", {})
    if not cfg.get("enabled", True):
        return 1.0
    cut = time.time() - _window_secs()
    rows = [x for x in S.get("perf", {}).get("posts", []) if isinstance(x.get("score"), (int, float)) and x["t"] >= cut]
    if len(rows) < cfg.get("min_posts", 15):
        return 1.0
    overall = _avg(rows) or 1
    mine = [x for x in rows if x.get(key) == value]
    k = cfg.get("smoothing", 5)  # thode data par zyada bharosa nahi
    return (sum(x["score"] for x in mine) + k * overall) / (len(mine) + k) / overall


# ---- Pakistan ke trends (Google Trends, pichle 7 din)
TREND_CATS = ["fuel", "electricity_gas", "inflation", "water", "budget_tax_imf", "education_jobs", "health",
              "weather_disaster", "transport_trade", "dollar_gold_business", "technology", "agriculture", "cricket"]
CAT_SECTION = {"agriculture": "agri_news", "cricket": "cricket_news"}  # baqi sab public_news


def handle_trends():
    """Har kuch ghante baad Pakistan ke Google trends parho aur AI se un ka mauzoo pehchano."""
    cfg = CONFIG.get("trends", {})
    T = S.setdefault("trends", {"last": 0, "terms": []})
    if not cfg.get("enabled", True) or not (GEMINI_KEY or GROQ_KEY):
        return
    unclassified = any("sindh" not in x for x in T["terms"])
    if time.time() - T.get("last", 0) < cfg.get("refresh_hours", 3) * 3600 and not unclassified:
        return
    T["last"] = time.time()
    try:
        feed = feedparser.parse(requests.get(cfg.get("feed", "https://trends.google.com/trending/rss?geo=PK"),
                                             timeout=25, headers=UA).content)
    except Exception as e:
        log("trends error:", e)
        return
    T["terms"] = [x for x in T["terms"] if "sindh" in x]  # jo pehle pehchane nahi gaye, dobara check hon
    known = {x["term"] for x in T["terms"]}
    new = []
    for e in feed.entries:
        term = clean_text(e.get("title", ""))
        if not term or term.lower() in known:
            continue
        traffic = int(re.sub(r"\D", "", e.get("ht_approx_traffic", "") or "") or 100)
        news = clean_text(e.get("ht_news_item_title", "") or "")
        new.append({"term": term.lower(), "traffic": traffic, "news": news, "t": int(time.time())})
    if new:
        listing = "\n".join(f"[{i}] {x['term']} | {x['news']}" for i, x in enumerate(new[:25]))
        prompt = ("These are trending Google searches in Pakistan with a related headline. For each, give its topic "
                  "category from this list or \"none\": " + json.dumps(TREND_CATS) +
                  ". Use \"cricket\" only for Pakistan national team cricket. Use \"none\" for foreign news, "
                  "celebrities, politics, crime, religion or the military. Also set sindh=true if it is about Sindh."
                  "\nReturn JSON: {\"items\": [{\"i\": number, \"cat\": string, \"sindh\": bool}]}\n\n" + listing)
        def norm(o):  # AI kabhi seedhi list ya doosre naam deta hai
            if isinstance(o, list):
                o = {"items": o}
            if isinstance(o, dict) and not isinstance(o.get("items"), list):
                o = {"items": next((v for v in o.values() if isinstance(v, list)), [])}
            return o if isinstance(o, dict) and o["items"] else None
        out = norm(ask_gemini(prompt)) if GEMINI_KEY else None
        if not out and GROQ_KEY:
            out = norm(ask_groq(prompt))
        T["ai_ok"] = bool(out)
        if not out:
            log("trends: AI ka jawab nahi aaya, agle run mein dobara")
            T["last"] = 0
            return
        for n_, r in enumerate(out["items"]):
            if not isinstance(r, dict):
                continue
            try:
                x = new[int(r.get("i", r.get("index", n_)))]
            except (TypeError, ValueError, IndexError):
                continue
            x["cat"] = r.get("cat") if r.get("cat") in TREND_CATS else "none"
            x["sindh"] = bool(r.get("sindh"))
        for x in new[:25]:
            if "cat" in x:  # sirf pehchane gaye trend rakho; baqi agli baar
                T["terms"].append(x)
    cut = time.time() - _window_secs()
    T["terms"] = [x for x in T["terms"] if x["t"] >= cut][-600:]
    log("trends:", len(new), "naye,", len(T["terms"]), "kul (7 din)")


def trend_scores():
    """Har mauzoo ka 7 din ka trend zor (Sindh wale trend do guna)."""
    cut = time.time() - _window_secs()
    sc = {c: 0.0 for c in TREND_CATS}
    for x in S.get("trends", {}).get("terms", []):
        if x["t"] >= cut and x.get("cat") in sc:
            sc[x["cat"]] += math.log10(max(x.get("traffic", 100), 10)) * (2 if x.get("sindh") else 1)
    return sc


def trend_weight(cat):
    if not CONFIG.get("trends", {}).get("enabled", True):
        return 1.0
    sc = trend_scores()
    total = sum(sc.values())
    if total <= 0:
        return 1.0
    avg = total / len(sc)
    return (sc.get(cat, 0) + avg) / (2 * avg)  # koi trend nahi = 0.5, aam = 1, garam mauzoo = zyada


def section_trend_weight(section):
    cats = [c for c in TREND_CATS if CAT_SECTION.get(c, "public_news") == section]
    if not cats:
        return 1.0
    return max(trend_weight(c) for c in cats) if section == "public_news" else trend_weight(cats[0])


def trend_queries(cat, days=2, n=2):
    """Taaza trend wale lafz (us mauzoo ke) taake bot wohi khabar dhoonde."""
    cut = time.time() - days * 86400
    rows = [x for x in S.get("trends", {}).get("terms", []) if x.get("cat") == cat and x["t"] >= cut]
    rows.sort(key=lambda x: x.get("traffic", 0), reverse=True)
    return [x["term"] for x in rows[:n]]


def _clamp(w):
    cfg = CONFIG.get("learning", {})
    return max(cfg.get("min_weight", 0.5), min(cfg.get("max_weight", 2.5), w))


def learn_weight(key, value):
    """Aakhri zor = (log kitna pasand kar rahe hain) x (Pakistan mein kitna trend ho raha hai), dono pichle 7 din."""
    if key == "cat":
        tw = trend_weight({"agri_news": "agriculture", "cricket_news": "cricket"}.get(value, value))
    else:
        tw = section_trend_weight(value)
    return _clamp(like_weight(key, value) * tw)


def learned_cap(section, base):
    return max(1, round(base * learn_weight("sec", section)))


def section_order():
    """Jo hissa is hafte zyada pasand/trend ho, wo pehle chance le (posting order)."""
    secs = ["public_news", "agri_news", "cricket_news", "sindh_single"]
    return sorted(secs, key=lambda x: learn_weight("sec", x), reverse=True)


def likes_report():
    cut = time.time() - _window_secs()
    rows = [x for x in S.get("perf", {}).get("posts", []) if isinstance(x.get("score"), (int, float)) and x["t"] >= cut]
    lines = ["📊 Pichle 7 din ka hisaab\n", "Posting order: " + " > ".join(section_order()), ""]
    if rows:
        lines.append(f"👍 Pasand ({len(rows)} posts naapi gayin):")
        for key, name in (("sec", "Hisse"), ("cat", "Mauzoo")):
            groups = {}
            for x in rows:
                groups.setdefault(x.get(key) or "-", []).append(x)
            ranked = sorted(groups.items(), key=lambda g: _avg(g[1]), reverse=True)
            lines.append(f"{name}:")
            lines += [f"  {g}: avg {_avg(v):.1f} ({len(v)} posts) x{learn_weight(key, g):.1f}" for g, v in ranked[:12]]
    else:
        lines.append("👍 Abhi koi post naapi nahi gayi (post ke ~20 ghante baad likes gine jaate hain).")
    sc = sorted(trend_scores().items(), key=lambda kv: kv[1], reverse=True)
    lines.append("\n🔥 Pakistan trends (mauzoo):")
    lines += [f"  {c}: {v:.1f} x{_clamp(trend_weight(c)):.1f}" + (f" ({', '.join(trend_queries(c, 7, 3))})" if v else "")
              for c, v in sc if v][:8] or ["  abhi data nahi"]
    return "\n".join(lines)


def card_title_of(message):
    """Post ki pehli line se card ki sarkhi (emoji/nishan hata kar, pehla jumla, 90 harf tak)."""
    for line in (message or "").splitlines():
        line = re.sub(r"^[^\w\u0600-\u06FF]+", "", line).strip()
        if len(line) >= 4:
            return re.split(r"(?<=[!۔.؟?])\s", line)[0][:90]
    return ""


def fb_post(message, link=None, photo=None, video=None, count=True, card=True, card_label=None, comment=None):
    """Har post: photo/video na ho to design wala card khud lagao; link hamesha pehle comment mein."""
    orig_link = link
    if CONFIG.get("news_cards", True):
        if card and not photo and not video:
            title = card_title_of(message)
            made = make_card(title, card_label or TOPIC_SD.get("district", ""), theme="news") if title else None
            if made:
                photo = made
        if link and (photo or video) and CONFIG.get("link_in_comment", True):
            link = None  # photo/video post mein link preview nahi lagta: comment mein jayega
    auto_card = photo if (card and photo and photo.endswith("card.png")) else None
    ok = _fb_post(message, link, photo, video, count)
    if not ok and auto_card:  # card upload na hua: purane tareeqe se (text + link) koshish
        photo, link = None, orig_link
        ok = _fb_post(message, link, None, video, count)
    if ok and orig_link and link is None:
        web = orig_link.replace("news.google.com/rss/articles/", "news.google.com/articles/")
        if not link_comment(f"{LBL.get('link_comment', '🔗 مڪمل خبر:')} {web}") and not DRY_RUN:
            append_to_post(f"🔗 {web}")  # comment na lage to link post ke andar hi
    if ok and comment:
        link_comment(comment)
    if ok and not DRY_RUN and not blocked_reason(message):
        try:
            crosspost(message, orig_link, photo, video)
        except Exception as e:
            log("telegram channel error:", e)
    return ok


def append_to_post(extra):
    pid = S.get("last_post_id")
    if not pid:
        return
    try:
        g = requests.get(f"{GRAPH}/{pid}", timeout=30, params={"fields": "message", "access_token": FB_TOKEN}).json()
        msg = g.get("message", "")
        if msg:
            parts = msg.rsplit("\n\n📲", 1)
            new = parts[0] + f"\n\n{extra}" + ("\n\n📲" + parts[1] if len(parts) == 2 else "")
            requests.post(f"{GRAPH}/{pid}", timeout=30, data={"message": new, "access_token": FB_TOKEN})
    except Exception as e:
        log("post edit error:", e)


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
                    S["last_post_id"] = r.json().get("id")
                    note_post()
                    stat("posted")
                    if count:
                        S["daily"]["count"] += 1
                    return True
                log("video upload error:", r.text[:200])
            tg_send("⚠️ Video upload nahi ho saki, sirf text post kar raha hoon.")
        img = None
        if photo and os.path.isfile(photo):  # khud bani tasveer (card)
            with open(photo, "rb") as f:
                img = f.read()
        elif photo and not photo.startswith("http"):
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
                              files={"source": ("photo.png" if photo.endswith(".png") else "photo.jpg", img,
                                                "image/png" if photo.endswith(".png") else "image/jpeg")})
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
        S["last_post_id"] = r.json().get("post_id") or r.json().get("id")
        note_post()
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
        ok = fb_post(q["message"], q.get("link"), q.get("photo"), q.get("video"))
        if not ok:
            break
        S["queue"].pop(0)
        perf_record("district")
        record_title(q["message"])
        mark_shareable(q["message"])
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


def job_like(title):
    t = title.lower()
    return any(w in t for w in CONFIG.get("job_words", []))


def handle_jobs():
    for it in fetch("jobs"):
        if it["key"] in S["seen"]:
            continue
        S["seen"][it["key"]] = time.time()
        if not is_trusted(it["domain"]) or word_match(it["title"], CONFIG["job_scam_words"]):
            continue
        if not it.get("local") and not job_like(it["title"]):  # aam khabar, naukri ka ishtihar nahi
            continue
        reason = blocked_reason(it["title"])
        if reason:
            log(f"BLOCKED job ({reason}):", it["title"][:60])
            continue
        it["local"] = it.get("local") or word_match(it["title"], CONFIG["district_towns"])
        S["jobs"].append(it)
    S["jobs"] = [j for j in S["jobs"] if j.get("local") or job_like(j["title"])][-40:]
    if now().hour < CONFIG["jobs_digest_hour"] or S["last_digest"] == today():
        return
    S["last_digest"] = today()
    if not S["jobs"] or not can_post():
        return
    jobs = sorted(S["jobs"], key=lambda j: (j.get("local", False), j["ts"]), reverse=True)[:CONFIG["jobs_per_digest"]]
    lines = [LBL["jobs_header"], ""]
    links = []
    for n, j in enumerate(jobs, 1):
        lines += [f"{n}. {j['title']} ({j['source']})", ""]
        links.append(f"{n}. {j['link'].replace('news.google.com/rss/articles/', 'news.google.com/articles/')}")
    lines += [LBL.get("link_note", "🔗 مڪمل خبر جو لنڪ ڪمينٽ ۾"), "", LBL["jobs_warning"], "", footer()]
    card = make_card(re.sub(r"^[^\w\u0600-\u06FF]+", "", LBL["jobs_header"]), "", theme="jobs") \
        if CONFIG.get("news_cards", True) else None
    if fb_post("\n".join(lines), photo=card, card=False,
               comment=LBL.get("links_comment", "🔗 مڪمل خبرون:") + "\n" + "\n".join(links)):
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
    if photo and not os.path.isfile(photo) and len(message) <= 1000:
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


SD_MONTHS = ["جنوري", "فيبروري", "مارچ", "اپريل", "مئي", "جون", "جولاءِ", "آگسٽ", "سيپٽمبر", "آڪٽوبر", "نومبر", "ڊسمبر"]
SEP = "━━━━━━━━━━━━━━"
NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def sd_date():
    n = now()
    return f"{n.day} {SD_MONTHS[n.month - 1]} {n.year}"


def make_card(title, subtitle="", body="", theme="news"):
    """Page ke rang (Ajrak) wali tasveer banana: Chrome headless se HTML ka screenshot. Na bane to None."""
    import html as H
    import shutil
    import subprocess
    import tempfile
    chrome = next((p for p in (shutil.which(x) for x in ("google-chrome", "google-chrome-stable", "chromium",
                                                         "chromium-browser")) if p), None) or os.getenv("CHROME_BIN")
    if not chrome:
        log("card: chrome nahi mila")
        return None
    d = tempfile.mkdtemp()
    accent = "#B3261E" if theme == "news" else "#1F6F5C"
    font_css = os.getenv("CARD_FONT_CSS", "") or \
        "@import url('https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@700&display=swap');"
    big = 92 if len(title) < 22 else 74 if len(title) < 40 else 58
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>{font_css}
    html,body{{margin:0;width:1080px;height:1080px;overflow:hidden}}
    body{{background:#14213D;font-family:'Noto Naskh Arabic','Noto Naskh',serif;color:#F4EFE6;position:relative}}
    .band{{position:absolute;left:0;right:0;height:84px;background-color:#7A1B1B;box-sizing:content-box;
      background-image:radial-gradient(circle at 42px 42px,#F4EFE6 6px,transparent 7px),
      radial-gradient(circle at 42px 42px,#14213D 22px,transparent 23px);background-size:84px 84px}}
    .top{{top:0;border-bottom:8px solid #F4EFE6}} .bot{{top:988px;border-top:8px solid #F4EFE6}}
    .wrap{{position:absolute;top:92px;bottom:92px;left:70px;right:70px;display:flex;flex-direction:column;
      align-items:center;justify-content:center;text-align:center;gap:26px;direction:rtl}}
    .tag{{background:{accent};color:#fff;font-size:34px;padding:8px 30px;border-radius:6px;letter-spacing:1px;
      font-family:Arial,sans-serif;font-weight:700;direction:ltr}}
    h1{{margin:0;font-size:{big}px;line-height:1.45;font-weight:700}}
    .sub{{font-size:44px;opacity:.9;font-family:'Noto Naskh Arabic','Noto Naskh',serif;font-weight:700}} .body{{font-size:40px;line-height:1.6;opacity:.95;max-width:900px}}
    .brand{{font-family:Arial,sans-serif;font-weight:700;font-size:30px;letter-spacing:3px;opacity:.85;direction:ltr}}
    </style></head><body><div class="band top"></div><div class="band bot"></div><div class="wrap">
    <div class="tag">NAUSHAHRO FEROZE UPDATES</div><h1>{H.escape(title)}</h1>
    {f'<div class="sub">{H.escape(subtitle)}</div>' if subtitle else ''}
    {f'<div class="body">{H.escape(body)}</div>' if body else ''}
    <div class="brand">Follow • Share</div></div></body></html>"""
    hp, out = os.path.join(d, "card.html"), os.path.join(d, "card.png")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(page)
    try:
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=1080,1167", "--virtual-time-budget=8000",
                        f"--screenshot={out}", "file://" + hp], capture_output=True, timeout=90)
    except Exception as e:
        log("card error:", e)
        return None
    if not (os.path.isfile(out) and os.path.getsize(out) > 5000):
        return None
    try:  # headless Chrome window viewport se bari hoti hai: sirf upar ka 1080x1080 hissa rakho
        from PIL import Image
        with Image.open(out) as im:
            im.crop((0, 0, 1080, 1080)).save(out)
    except Exception as e:
        log("card crop error:", e)
    return out


def handle_roundup():
    """Din mein do dafa (subah 6, shaam 6) poore Sindh ki ahem khabrein: har khabar alag hissay mein poori, card ke saath."""
    cfg = CONFIG.get("sindh_roundup", {})
    if not cfg.get("enabled", True):
        return
    slot = None
    for name, hour, end in (("am", cfg.get("morning_hour", 6), 12), ("pm", cfg.get("evening_hour", 18), 24)):
        if hour <= now().hour < end and S.get("roundup_" + name) != today():
            slot = name
    if not slot:
        return
    S["roundup_" + slot] = today()
    stories = sindh_stories(cfg)
    if len(stories) < cfg.get("min_items", 3):
        log("sindh roundup: kaafi khabrein nahi mili", len(stories))
        return
    title = cfg.get("title_am" if slot == "am" else "title_pm", "سنڌ جون اهم خبرون")
    lines = [title, f"📅 {sd_date()}", SEP]
    for i, s in enumerate(stories):
        lines += [f"{NUM[i] if i < len(NUM) else '🔹'} {s['title']}", "", finish(s["body"])]
        if s.get("source"):
            lines.append(f"📌 {LBL['source']}: {s['source']}")
        lines.append(SEP)
    lines += ["", footer()]
    card = make_card(re.sub(r"^\W+", "", title), sd_date(), theme="news") if cfg.get("card", True) else None
    if fb_post("\n".join(lines), photo=card):
        links = [f"{NUM[i] if i < len(NUM) else '🔹'} {s['link']}" for i, s in enumerate(stories) if s.get("link")]
        if links:
            link_comment(LBL.get("links_comment", "🔗 مڪمل خبرون:") + "\n" + "\n".join(links))


def sindh_candidates(cfg):
    """Pichle 12 ghante ki Sindh ki bharosemand khabrein (matn ke saath), bina jurm/pabandi wali."""
    max_age = cfg.get("max_age_hours", 12) * 3600
    feeds = cfg.get("story_feeds", []) + cfg.get("feeds", [])
    urls = [(u, True) for u in dict.fromkeys(feeds)]
    urls += [(gnews_url(q, lang), False) for q in cfg.get("queries", ["Sindh"]) for lang in ("ur", "en")]
    keys, raw = set(), []
    for u, from_feed in urls:
        try:
            feed = feedparser.parse(requests.get(u, timeout=25, headers=UA).content)
        except Exception as e:
            log("roundup feed error:", u, e)
            continue
        fname = clean_text(feed.feed.get("title", "")) if from_feed else ""
        for e in feed.entries:
            title = clean_text(e.get("title", ""))
            src = e.get("source") or {}
            st = src.get("title", "") if hasattr(src, "get") else ""
            if st and title.endswith(" - " + st):
                title = title[: -(len(st) + 3)].strip()
            pub = e.get("published_parsed") or e.get("updated_parsed")
            ts = calendar.timegm(pub) if pub else time.time()
            href = (src.get("href") if hasattr(src, "get") else "") or e.get("link", "")
            domain = urlparse(href).netloc.lower().removeprefix("www.")
            body = ""
            for c in (e.get("content") or []):
                body = clean_text(c.get("value", "")) or body
            body = body or clean_text(e.get("summary", ""))
            if body.startswith(title):
                body = body[len(title):].strip()
            k = item_key(title)
            if (len(title) < 15 or k in keys or time.time() - ts > max_age or not is_trusted(domain)
                    or blocked_reason(title + " " + body[:600]) or keyword_sensitive(title)):
                continue
            keys.add(k)
            raw.append({"ts": ts, "title": title, "text": body[:1200], "source": fname or st or domain,
                        "link": e.get("link", ""),
                        "rich": len(body) > 120})
    raw.sort(key=lambda r: (r["rich"], r["ts"]), reverse=True)  # matn wali khabrein pehle
    return raw


def sindh_stories(cfg):
    want = cfg.get("max_items", 5)
    cand = sindh_candidates(cfg)[:20]
    if not cand:
        return []
    if GEMINI_KEY or GROQ_KEY:
        listing = "\n\n".join(f"[{i}] {r['title']}\n{r['text']}" for i, r in enumerate(cand))
        prompt = ("Below are recent news items from Sindh, Pakistan (headline + text). Pick the " + str(want) +
                  " most important for people of Sindh (government decisions, education, health, weather, prices, "
                  "development, jobs, sports). Skip duplicates, crime, violence, political fights, religion "
                  "controversy, abuse and anything about the military. For each write in Sindhi (Arabic script): "
                  "a short headline and a 2-3 sentence summary using ONLY facts in that item, in your own words, "
                  "no full stop at the end.\n"
                  "Return JSON: {\"items\": [{\"i\": number, \"title\": string, \"body\": string}]}\n\n" + listing)
        out = ask_gemini(prompt) if GEMINI_KEY else None
        if not out and GROQ_KEY:
            out = ask_groq(prompt)
        stories = []
        for it in (out or {}).get("items", []):
            try:
                r = cand[int(it.get("i"))]
            except (TypeError, ValueError, IndexError):
                continue
            t, bdy = clean_text(it.get("title", "")), clean_text(it.get("body", ""))
            if len(t) > 5 and len(bdy) > 20 and not blocked_reason(t + " " + bdy):
                stories.append({"title": t, "body": bdy, "source": r["source"], "link": r.get("link", "")})
        if stories:
            return stories[:want]
    return [{"title": r["title"], "body": r["text"][:300] or r["title"], "source": r["source"], "link": r.get("link", "")}
            for r in cand[:want] if r["rich"]]


def handle_sindh_single():
    """Din mein kuch (default 4) Sindh ki khabrein alag post: sirf wohi jo Naushahro Feroze ke logon par asar karein.
    District ki khabron ke baad: jab queue khaali ho, aur do posts ke beech waqfa."""
    cfg = CONFIG.get("sindh_single", {})
    if not cfg.get("enabled", True) or not (GEMINI_KEY or GROQ_KEY):
        return
    h = now().hour
    day = S.setdefault("sindh_single", {"date": "", "count": 0, "last": 0, "used": []})
    if day["date"] != today():
        day.update(date=today(), count=0, used=day.get("used", [])[-200:])
    if (not (cfg.get("from_hour", 9) <= h < cfg.get("to_hour", 22))
            or day["count"] >= learned_cap("sindh_single", cfg.get("max_per_day", 4))
            or (S["queue"] and can_post()) or time.time() - day["last"] < cfg.get("gap_minutes", 150) * 60
            or not pace_ok()):
        return
    cand = [r for r in sindh_candidates(CONFIG.get("sindh_roundup", {})) if item_key(r["title"]) not in day["used"]
            and item_key(r["title"]) not in S["seen"]][:15]
    day["last"] = time.time()  # khabar na mile tab bhi agli koshish waqfe ke baad
    if not cand:
        return
    listing = "\n\n".join(f"[{i}] {r['title']}\n{r['text']}" for i, r in enumerate(cand))
    prompt = ("You choose news for a Facebook page whose audience is the people of Naushahro Feroze district, Sindh. "
              "From the items below pick at most ONE that directly affects them: Sindh government decisions for all "
              "districts, education or health policy, jobs/recruitment, weather or flood warnings, wheat/fertilizer/"
              "fuel prices, canals/barrage water, electricity/gas, exams and results. If none clearly affects them, "
              "return pick -1. Never pick crime, violence, political fights, religion controversy, abuse or anything "
              "about the military. Write in Sindhi (Arabic script) a short headline and a 3-4 sentence post using "
              "ONLY facts in that item, in your own words, no full stop at the end.\n"
              "Return JSON: {\"pick\": number, \"title\": string, \"body\": string}\n\n" + listing)
    out = ask_gemini(prompt) if GEMINI_KEY else None
    if not out and GROQ_KEY:
        out = ask_groq(prompt)
    try:
        r = cand[int((out or {}).get("pick", -1))]
    except (TypeError, ValueError, IndexError):
        return
    if int(out.get("pick", -1)) < 0:
        return
    title, body = clean_text(out.get("title", "")), clean_text(out.get("body", ""))
    day["used"].append(item_key(r["title"]))
    S["seen"][item_key(r["title"])] = time.time()
    if len(title) < 5 or len(body) < 30 or blocked_reason(title + " " + body):
        return
    msg = (f"{cfg.get('label', '📰 سنڌ')} | {title}\n\n{finish(body)}\n\n📌 {LBL['source']}: {r['source']}"
           f"\n\n{footer()}")
    card = make_card(title, cfg.get("card_sub", "سنڌ جون خبرون"), theme="news") if cfg.get("card", True) else None
    if fb_post(msg, photo=card, count=False):
        perf_record("sindh_single", "sindh")
        if r.get("link"):
            link_comment(f"{LBL.get('link_comment', '🔗 مڪمل خبر:')} {r['link']}")
        day["count"] += 1
        mark_shareable(title)


def link_comment(text):
    """Abhi lagi post par page ki taraf se pehla comment (mukammal khabar ka link).
    Comment lag jaye to post mein 'link comment mein' ki line jori jati hai. Facebook API se pin mumkin nahi."""
    pid = S.get("last_post_id")
    if not pid or DRY_RUN or not CONFIG.get("link_in_comment", True):
        return False
    try:
        r = requests.post(f"{GRAPH}/{pid}/comments", timeout=30, data={"message": text, "access_token": FB_TOKEN})
        if r.status_code != 200:
            log("link comment error:", r.text[:150])
            return False
        note = LBL.get("link_note", "🔗 مڪمل خبر جو لنڪ ڪمينٽ ۾")
        g = requests.get(f"{GRAPH}/{pid}", timeout=30, params={"fields": "message", "access_token": FB_TOKEN}).json()
        msg = g.get("message", "")
        if msg and note not in msg:
            parts = msg.rsplit("\n\n📲", 1)  # footer se pehle
            new = parts[0] + f"\n\n{note}" + ("\n\n📲" + parts[1] if len(parts) == 2 else "")
            e = requests.post(f"{GRAPH}/{pid}", timeout=30, data={"message": new, "access_token": FB_TOKEN})
            if e.status_code != 200:
                log("post edit error:", e.text[:150])
        return True
    except Exception as ex:
        log("link comment error:", ex)
        return False


def mark_shareable(text):
    """Abhi lagi post ko 'share karne layak' list mein rakhna (groups mein share ke mashware ke liye)."""
    pid = S.get("last_post_id")
    if not pid or DRY_RUN:
        return
    first = re.sub(r"^\W+", "", (text or "").strip().splitlines()[0] if text else "")[:90]
    sh = S.setdefault("shareable", [])
    if pid not in [x["id"] for x in sh]:
        sh.append({"id": pid, "title": first, "t": time.time()})
    del sh[:-30]


def handle_share_helper():
    """Din mein do dafa Telegram par sab se achhi posts + 'Share' link + kis group mein share karna hai.
    Facebook groups mein software se share ki ijazat nahi deta, is liye share aap 2 tap mein khud karte hain."""
    cfg = CONFIG.get("share_helper", {})
    if not cfg.get("enabled", True) or not (TG_TOKEN and TG_CHAT):
        return
    slots = [str(h) for h in cfg.get("hours", [13, 20]) if now().hour >= h]
    slot = slots[-1] if slots else None
    if not slot or S.get("share_sent", {}).get(slot) == today():
        return
    S.setdefault("share_sent", {})[slot] = today()
    sent_ids = S.setdefault("share_done", [])
    fresh = [x for x in S.get("shareable", []) if x["id"] not in sent_ids and time.time() - x["t"] < 12 * 3600]
    if not fresh:
        return
    picks = fresh[-cfg.get("per_message", 3):]
    groups = cfg.get("groups", [])
    gi = S.get("group_index", 0)
    lines = ["📤 Ye posts groups mein share karein (har post ka link dabayen → Share to a group):", ""]
    for n, p in enumerate(picks, 1):
        url = "https://www.facebook.com/" + p["id"]
        lines += [f"{n}. {p['title']}", "https://www.facebook.com/sharer/sharer.php?u=" + quote_plus(url)]
        if groups:
            g = [groups[(gi + k) % len(groups)] for k in range(min(cfg.get("groups_per_post", 2), len(groups)))]
            gi += len(g)
            lines.append("👥 " + " | ".join(x.get("name", x) if isinstance(x, dict) else str(x) for x in g))
        lines.append("")
        sent_ids.append(p["id"])
    if not groups:
        lines.append("(config.json mein \"share_helper\" → \"groups\" mein apne groups ke naam likhen to bot har post "
                     "ke liye baari baari group bhi batayega.)")
    lines.append("⚠️ Ek group mein din mein 1-2 se zyada share na karein, warna admin spam samjhenge.")
    S["group_index"] = gi
    del sent_ids[:-100]
    tg_send("\n".join(lines))


def handle_engagement():
    """Hafte mein kuch din shaam ko sawal wali post (card ke saath): comments se reach barhti hai."""
    cfg = CONFIG.get("engagement", {})
    qs = cfg.get("questions", [])
    if (not cfg.get("enabled", True) or not qs or now().weekday() not in cfg.get("days", [0, 2, 4])
            or now().hour < cfg.get("hour", 20) or S.get("last_question") == today()):
        return
    i = S.get("q_index", 0) % len(qs)
    card = make_card(qs[i], "ڪمينٽ ۾ جواب ڏيو", theme="question") if cfg.get("card", True) else None
    text = f"💬 {qs[i]}\n\n👇 پنهنجو جواب ڪمينٽ ۾ لکو، ۽ دوستن کي به ٽيگ ڪريو!\n\n{footer()}"
    if fb_post(text, photo=card):
        S["q_index"] = i + 1
        S["last_question"] = today()


PRAISE_WORDS = [
    "zabardast", "zbrdst", "shabash", "shabaash", "mashallah", "masha allah", "mashaallah", "subhanallah",
    "behtareen", "bohat acha", "bohat achi", "bht acha", "acha kaam", "achi khabar", "great", "nice", "good job",
    "excellent", "awesome", "well done", "keep it up", "thanks", "thank you", "shukriya", "jazakallah", "wah",
    "زبردست", "شاباش", "شاباس", "ماشاءالله", "ماشاء الله", "ماشاالله", "سبحان الله", "بہترین", "بهترين", "شاندار",
    "بہت اچھا", "بہت اچھی", "اچھا کام", "سٺو", "تمام سٺو", "ڏاڍو سٺو", "سهڻو", "مهرباني", "شڪريو", "شکریہ", "جزاک الله",
    "👍", "❤", "❤️", "🔥", "👏", "💯", "🌹", "😍", "🥰", "💐", "✅"]


def praise_ids(items):
    """Kaun se comments post/page ki tareef ya shukriya hain. AI se, warna alfaaz se."""
    if not items:
        return set()
    if GEMINI_KEY or GROQ_KEY:
        prompt = ("These are comments on a local news Facebook page from Sindh, Pakistan. For each, decide if it is "
                  "praise or thanks for the post or the page (e.g. 'great work', 'mashallah', 'shabash', only heart/"
                  "thumbs emojis). Questions, complaints, criticism, requests, opinions about the news itself, sad "
                  "condolence comments, or anything else are NOT praise.\n"
                  "Return JSON: {\"praise\": [ids]}\n\n" + "\n".join(f"{cid}: {m[:200]}" for cid, m in items))
        out = ask_gemini(prompt) if GEMINI_KEY else None
        if not out and GROQ_KEY:
            out = ask_groq(prompt)
        if isinstance(out, dict) and isinstance(out.get("praise"), list):
            return {str(x) for x in out["praise"]} & {cid for cid, _ in items}
    found = set()
    for cid, m in items:
        low = (m or "").lower()
        if "?" in low or "؟" in low:
            continue  # sawal: tareef nahi
        if any(w.lower() in low for w in PRAISE_WORDS):
            found.add(cid)
    return found


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
                todo.append((due, cid, c.get("message", "")))
    # Sirf tareef wale comments ka jawab; baqi (sawal, shikayat, waghera) admin khud dekhega
    praise = praise_ids([(cid, msg) for _, cid, msg in todo]) if cfg.get("only_praise", True) else {t[1] for t in todo}
    for _, cid, _m in todo:
        if cid not in praise:
            replied.append(cid)  # chhor diya: manual jawab ke liye
    todo = sorted((d, cid) for d, cid, _m in todo if cid in praise)
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


NEEDED_SCOPES = ["pages_manage_posts", "pages_read_engagement", "pages_read_user_content", "pages_manage_engagement"]


def check_token():
    """FB token mein kaun si ijazatein hain. Nateeja state mein bhi (taake bahar se dekha ja sake)."""
    res = {"time": now().strftime("%Y-%m-%d %H:%M"), "valid": False, "scopes": [], "missing": [], "expires": None}
    if not FB_TOKEN:
        res["error"] = "FB_PAGE_TOKEN khaali"
    else:
        try:
            d = requests.get(f"{GRAPH}/debug_token", timeout=30,
                             params={"input_token": FB_TOKEN, "access_token": FB_TOKEN}).json().get("data", {})
            if d:
                res.update(valid=bool(d.get("is_valid")), scopes=d.get("scopes", []),
                           expires=d.get("expires_at"), data_expires=d.get("data_access_expires_at"))
            else:  # debug na chale to comments parh kar dekh lo
                r = requests.get(f"{GRAPH}/{FB_PAGE_ID}/posts", timeout=30, params={
                    "access_token": FB_TOKEN, "limit": 1, "fields": "id,comments.limit(1){id}"})
                res["valid"] = r.status_code == 200
                res["scopes"] = ["pages_read_user_content"] if r.status_code == 200 else []
                if r.status_code != 200:
                    res["error"] = r.text[:150]
        except Exception as e:
            res["error"] = str(e)[:150]
    res["missing"] = [s for s in NEEDED_SCOPES if s not in res["scopes"]] if res["scopes"] else NEEDED_SCOPES[2:]
    S["token_check"] = res
    return res


def token_report(res):
    if not res["valid"]:
        return "❌ Facebook token kaam nahi kar raha. " + res.get("error", "")
    lines = ["✅ Facebook token theek hai."]
    if res.get("expires") == 0:
        lines.append("⏳ Expires: Never")
    if res["missing"]:
        lines.append("❌ Ye ijazatein nahi hain: " + ", ".join(res["missing"]))
        lines.append("Comments ke jawab aur link wala comment ke liye naya token dalein (README dekhein).")
    else:
        lines.append("✅ Comments wali ijazatein bhi hain (jawab aur link wala comment chalega).")
    return "\n".join(lines)


# ---------------------------------------------------------------- cricket
TEAM_SD = {"pakistan": "پاڪستان", "india": "ڀارت", "australia": "آسٽريليا", "england": "انگلينڊ",
           "south africa": "ڏکڻ آفريڪا", "new zealand": "نيوزيلينڊ", "sri lanka": "سري لنڪا",
           "bangladesh": "بنگلاديش", "afghanistan": "افغانستان", "west indies": "ويسٽ انڊيز",
           "zimbabwe": "زمبابوي", "ireland": "آئرلينڊ", "netherlands": "هالينڊ", "scotland": "اسڪاٽلينڊ",
           "nepal": "نيپال", "oman": "عمان", "uae": "يو اي اي", "united arab emirates": "يو اي اي",
           "usa": "آمريڪا", "united states of america": "آمريڪا", "canada": "ڪئناڊا", "hong kong": "هانگ ڪانگ"}


def team_sd(name):
    n = name.strip()
    low = n.lower()
    for suffix, sd in ((" women", " وومين"), (" a", " اي"), (" u19", " انڊر 19"), (" shaheens", " شاهين")):
        if low.endswith(suffix):
            base = TEAM_SD.get(low[: -len(suffix)])
            return (base + sd) if base else n
    return TEAM_SD.get(low, n)


def parse_side(s):
    """'Pakistan 145/3 *' -> {'name','score','runs','wkts','batting'}"""
    s = html.unescape(s).strip()
    batting = s.endswith("*")
    s = s.rstrip("* ").strip()
    m = re.match(r"^(.*?)\s+((?:\d+(?:/\d+)?d?\s*&\s*)?\d+(?:/\d+)?d?)$", s)
    if not m:
        return {"name": s, "score": "", "runs": None, "wkts": 0, "batting": batting}
    last = m.group(2).split("&")[-1].strip().rstrip("d")
    runs, _, wk = last.partition("/")
    wkts = int(wk) if wk else 10
    innings = m.group(2).count("&") + 1
    return {"name": m.group(1).strip(), "score": m.group(2).strip(), "runs": int(runs), "wkts": wkts,
            "innings": innings, "batting": batting}


def cricket_matches():
    cfg = CONFIG.get("cricket", {})
    team = cfg.get("team", "Pakistan").lower()
    try:
        feed = feedparser.parse(requests.get(cfg.get("feed", "https://static.cricinfo.com/rss/livescores.xml"),
                                             timeout=20, headers=UA).content)
    except Exception as e:
        log("cricket feed error:", e)
        return []
    out = []
    S["cricket_feed"] = {"time": now().strftime("%Y-%m-%d %H:%M"), "items": len(feed.entries),
                         "sample": [clean_text(x.get("title", "")) for x in feed.entries[:3]]}
    for e in feed.entries:
        title = clean_text(e.get("title", ""))
        if " v " not in title or team not in title.lower():
            continue
        a, b = title.split(" v ", 1)
        sa, sb = parse_side(a), parse_side(b)
        # sirf qaumi teamein: "Pakistan" aur "Pakistan Women"; Pakistan A/U19/Shaheens nahi
        names = {sa["name"].strip().lower(), sb["name"].strip().lower()}
        ok = {team, team + " women"} if cfg.get("include_women", True) else {team}
        if not names & ok:
            continue
        women = any(n.endswith(" women") for n in names)
        key = re.sub(r"\W+", "", (e.get("link") or e.get("id") or title).lower())[-60:]
        rival = cfg.get("rival", "India").lower()
        rivals = {rival + " women"} if women else {rival}
        out.append({"key": key, "title": title, "a": sa, "b": sb, "link": e.get("link", ""),
                    "live": sa["batting"] or sb["batting"], "rival": bool(names & rivals)})
    return out


def score_line(m):
    def side(s):
        txt = f"{team_sd(s['name'])}"
        if s["score"]:
            txt += f" {s['score'].replace('/', '/')}"
        return txt + (" 🏏" if s["batting"] else "")
    return f"{side(m['a'])}\n{side(m['b'])}"


def cricket_fb_edit(post_id, message):
    if DRY_RUN or not post_id:
        log("DRY/no id: live edit skipped")
        return False
    try:
        r = requests.post(f"{GRAPH}/{post_id}", timeout=30, data={"message": message, "access_token": FB_TOKEN})
        if r.status_code != 200:
            log("live edit error:", r.text[:150])
        return r.status_code == 200
    except Exception as e:
        log("live edit error:", e)
        return False


def cricket_tick(state, m, cfg):
    """Ek match ki ek jhalak: live post banana/badalna, wicket aur innings ki posts."""
    st = state.setdefault(m["key"], {"post": None, "wkts": {}, "wicket_posts": 0, "break_done": False,
                                     "last_edit": 0, "batting": None, "done": False})
    if st["done"]:
        return
    head = f"🔴 LIVE | {team_sd(m['a']['name'])} بمقابلي {team_sd(m['b']['name'])}"
    live_msg = (f"{head}\n\n{score_line(m)}\n\n⏱️ {LBL.get('updated', 'تازو')}: {now().strftime('%I:%M %p')}\n"
                f"{LBL.get('live_note', 'هي پوسٽ پاڻمرادو اپڊيٽ ٿيندي رهندي')}\n\n{CONFIG.get('cricket_tags', '#PAKvsIND #Cricket')}")
    if m["live"] and not st["post"]:
        if fb_post(live_msg, count=False, card=False):
            st["post"] = S.get("last_post_id")
            st["last_edit"] = time.time()
            tg_send("🏏 Live score post shuru: " + m["title"])
    elif m["live"]:
        gap = (cfg.get("rival_minutes", 1) if m["rival"] else cfg.get("normal_minutes", 5)) * 60
        if time.time() - st["last_edit"] >= gap - 20:
            if cricket_fb_edit(st["post"], live_msg):
                st["last_edit"] = time.time()
    # wickets
    for s in (m["a"], m["b"]):
        if s["runs"] is None:
            continue
        k = f"{s['name']}|{s.get('innings', 1)}"
        prev = st["wkts"].get(k)
        st["wkts"][k] = s["wkts"]
        if (prev is not None and s["wkts"] > prev and s["batting"] and cfg.get("wicket_posts", True)
                and st["wicket_posts"] < cfg.get("max_wicket_posts", 12)):
            n = s["wkts"]
            msg = (f"☝️ وڪيٽ! {team_sd(s['name'])} جو رانديگر آئوٽ، {n} وڪيٽون ڪري پيون\n\n🏏 هاڻوڪو اسڪور:\n{score_line(m)}"
                   f"\n\n{footer()}")
            card = make_card(f"وڪيٽ! {team_sd(s['name'])} {s['score']}", "Live Cricket", theme="news") \
                if cfg.get("card", True) else None
            if fb_post(msg, photo=card, count=False):
                st["wicket_posts"] += 1
    # innings break: batting side badli
    bat = m["a"]["name"] if m["a"]["batting"] else m["b"]["name"] if m["b"]["batting"] else None
    if st["batting"] and bat and bat != st["batting"] and not st["break_done"]:
        fb_post(f"🔄 اننگز جو وقفو\n\n{score_line(m)}\n\n{footer()}", count=False, card_label="پاڪستان ڪرڪيٽ")
        st["break_done"] = True
    if bat:
        st["batting"] = bat
    # match khatam: live tha, ab koi batting nahi
    if st["post"] and not m["live"] and st.get("seen_live"):
        st["done"] = True
        res = cricket_result_line(m)
        final = f"🏆 مئچ ختم | {team_sd(m['a']['name'])} بمقابلي {team_sd(m['b']['name'])}\n\n{score_line(m)}"
        if res:
            final += f"\n\n{res}"
        cricket_fb_edit(st["post"], final + f"\n\n{CONFIG.get('cricket_tags', '#Cricket')}")
        card = make_card(res or "مئچ ختم", f"{team_sd(m['a']['name'])} - {team_sd(m['b']['name'])}",
                         theme="news") if cfg.get("card", True) else None
        fb_post(final + "\n\n" + footer(), photo=card, count=False)
    if m["live"]:
        st["seen_live"] = True


def cricket_result_line(m):
    """Nateeja: Google News ki taaza sarkhi se (AI Sindhi mein), warna khaali."""
    if not (GEMINI_KEY or GROQ_KEY):
        return ""
    try:
        q = f"{m['a']['name']} {m['b']['name']} cricket"
        feed = feedparser.parse(requests.get(gnews_url(q, "en"), timeout=20, headers=UA).content)
        heads = [clean_text(e.get("title", "")) for e in feed.entries[:8]]
    except Exception:
        return ""
    heads = [h for h in heads if re.search(r"\b(beat|beats|won|win|wins|defeat|defeats|lost|lose|draw|tie)\b", h, re.I)]
    if not heads:
        return ""
    prompt = ("Final scores: " + m["title"] + "\nRecent headlines:\n" + "\n".join(heads[:5]) +
              "\nIf the headlines clearly state the result of THIS match, write one short Sindhi line with the "
              "result (who won and by how much). If Pakistan won add 'مبارڪون پاڪستان! 🇵🇰'. If unsure return "
              "empty. Return JSON: {\"line\": string}")
    out = ask_gemini(prompt) if GEMINI_KEY else ask_groq(prompt)
    line = clean_text((out or {}).get("line", ""))
    return "" if blocked_reason(line) else line


def handle_cricket_live():
    cfg = CONFIG.get("cricket", {})
    if not cfg.get("enabled", True):
        return
    state = S.setdefault("cricket", {})
    budget = cfg.get("max_loop_minutes", 8) * 60
    start = time.time()
    while True:
        matches = cricket_matches()
        if not matches:
            return
        for m in matches:
            cricket_tick(state, m, cfg)
        live = [m for m in matches if m["live"]]
        if not live:
            break
        step = (cfg.get("rival_minutes", 1) if any(m["rival"] for m in live) else cfg.get("normal_minutes", 5)) * 60
        if time.time() - start + step > budget:
            break
        if not DRY_RUN:
            save_state()  # beech mein bhi yaaddasht mehfooz
        time.sleep(step)
    for k in list(state)[:-20]:  # purane match hatao
        state.pop(k, None)


def topic_news(state_key, cfg, icon, check_rule, default_queries, max_age_h=12, icons=None):
    """Kisi ek mauzoo (cricket, zarat) ki mulk bhar ki khabrein, din mein hadd ke saath."""
    if not cfg.get("enabled", True):
        return
    day = S.setdefault(state_key, {"date": "", "count": 0, "last": 0})
    if day["date"] != today():
        day.update(date=today(), count=0)
    hour = now().hour
    gap = cfg.get("night_gap_minutes", cfg.get("gap_minutes", 90) * 2) if is_night() else cfg.get("gap_minutes", 90)
    if (day["count"] >= learned_cap(state_key, cfg.get("max_per_day", 4)) or time.time() - day.get("last", 0) < gap * 60
            or not cfg.get("start_hour", 0) <= hour < cfg.get("end_hour", 24) or (S["queue"] and can_post())
            or not pace_ok()):
        return
    items = []
    queries = cfg.get("queries", default_queries)
    per_run = cfg.get("queries_per_run")
    if isinstance(queries, dict):  # mauzoo -> search lafz; jo mauzoo zyada pasand/trend ho wo zyada baar dhoondo
        cats = [c for c in queries if queries[c]]
        picks = []
        while cats and len(picks) < (per_run or len(cats)):
            c = random.choices(cats, weights=[learn_weight("cat", c) for c in cats])[0]
            cats.remove(c)
            picks.append(random.choice(trend_queries(c) + queries[c]))
        queries = picks
    elif per_run and len(queries) > per_run:  # har run mein kuch mauzoo, baari baari
        start = day.get("rot", 0) % len(queries)
        queries = (queries[start:] + queries[:start])[:per_run]
        day["rot"] = start + per_run
    tq = trend_queries({"agri_news": "agriculture", "cricket_news": "cricket"}.get(state_key, ""))
    if tq and not isinstance(cfg.get("queries"), dict):
        queries = tq[:1] + list(queries)  # trend wala lafz bhi dhoondo
    for q in queries:
        for lang in ("ur", "en"):
            try:
                feed = feedparser.parse(requests.get(gnews_url(q, lang), timeout=25, headers=UA).content)
            except Exception:
                continue
            for e in feed.entries:
                title = clean_text(e.get("title", ""))
                src = e.get("source") or {}
                st_ = src.get("title", "") if hasattr(src, "get") else ""
                if st_ and title.endswith(" - " + st_):
                    title = title[: -(len(st_) + 3)].strip()
                pub = e.get("published_parsed")
                ts = calendar.timegm(pub) if pub else time.time()
                href = (src.get("href") if hasattr(src, "get") else "") or e.get("link", "")
                domain = urlparse(href).netloc.lower().removeprefix("www.")
                k = item_key(title)
                if (k in S["seen"] or time.time() - ts > max_age_h * 3600 or not is_trusted(domain)
                        or blocked_reason(title) or keyword_sensitive(title)):
                    continue
                items.append({"key": k, "title": title, "link": e.get("link", ""), "source": st_ or domain, "ts": ts})
    if not items:
        return
    items.sort(key=lambda x: x["ts"], reverse=True)
    uniq, keys = [], set()
    for it in items:
        if it["key"] not in keys:
            keys.add(it["key"])
            uniq.append(it)
    cand = uniq[:10]
    recent = [x["h"] for x in S.get("posted_heads", []) if time.time() - x["t"] < 36 * 3600][-25:]
    cat_field = (", \"category\": one of " + json.dumps(list(icons)) if icons else "")
    listing = "\n".join(f"[{i}] {it['title']}" for i, it in enumerate(cand))
    prompt = ("You pick news for a Sindhi Facebook news page. Candidate headlines:\n" + listing +
              "\n\nAlready posted recently (do NOT pick the same story again, even if worded differently or in "
              "another language):\n" + ("\n".join("- " + h for h in recent) or "- none") +
              "\n\nRule for a suitable item: " + check_rule +
              "\nNever pick anything about religion controversy, abuse, or the Pakistani military."
              "\nPick the ONE most important suitable item that is not a repeat (or -1 if none). List the indexes "
              "of items that are clearly unsuitable or repeats in \"reject\"."
              "\nFor the pick, write \"headline\": a short Sindhi headline (max 8 words, no emoji) and \"post\": its "
              "facts only, as a 1-2 sentence Facebook post in Sindhi (Arabic script), no hashtags, no full stop at the end."
              "\nReturn JSON only: {\"pick\": number, \"reject\": [numbers], \"headline\": string, \"post\": string"
              + cat_field + "}")
    res = ask_gemini(prompt) if GEMINI_KEY else None
    if not isinstance(res, dict) and GROQ_KEY:
        res = ask_groq(prompt)
    if not isinstance(res, dict):
        log(state_key, ": AI ka jawab nahi aaya, khabrein agli baar")  # seen mark nahi, dobara koshish
        return
    for i in res.get("reject") or []:
        try:
            S["seen"][cand[int(i)]["key"]] = time.time()
        except (TypeError, ValueError, IndexError):
            pass
    try:
        pick = int(res.get("pick", -1))
    except (TypeError, ValueError):
        pick = -1
    post = clean_text(str(res.get("post", "")))
    if not 0 <= pick < len(cand) or len(post) < 10 or blocked_reason(post):
        return
    it = cand[pick]
    S["seen"][it["key"]] = time.time()
    cat = str(res.get("category") or "")
    if icons and cat not in icons:
        cat = guess_cat(it["title"] + " " + post)
    ic = (icons or {}).get(cat, icon)
    head = clean_text(str(res.get("headline", "")))[:90]
    if len(head) < 6 or blocked_reason(head):
        head = ""
    label = TOPIC_SD.get(cat if icons else state_key, "")
    msg = (f"{ic} {head}\n\n" if head else f"{ic} ") + \
        f"{finish(post)}\n\n📌 {LBL['source']}: {clean_source(it['source'])}\n\n{footer()}"
    if news_card_post(msg, head or post[:90], label, it["link"]):
        perf_record(state_key, cat if icons else state_key)
        day["count"] += 1
        day["last"] = time.time()
        mark_shareable(post)
        ph = S.setdefault("posted_heads", [])
        ph.append({"h": it["title"][:140], "t": int(time.time())})
        S["posted_heads"] = ph[-80:]


TOPIC_SD = {"fuel": "پيٽرول ۽ ڊيزل", "electricity_gas": "بجلي ۽ گئس", "inflation": "مهانگائي",
            "water": "پاڻي ۽ ڊيم", "budget_tax_imf": "بجيٽ ۽ ٽيڪس", "education_jobs": "تعليم ۽ نوڪريون",
            "health": "صحت", "weather_disaster": "موسم", "transport_trade": "ٽرانسپورٽ ۽ واپار",
            "dollar_gold_business": "ڊالر ۽ سون", "technology": "ٽيڪنالاجي", "other": "پاڪستان جون خبرون",
            "public_news": "پاڪستان جون خبرون", "agri_news": "زراعت", "cricket_news": "پاڪستان ڪرڪيٽ",
            "district": "نوشهروفيروز جون خبرون"}
SOCIAL_DOMAINS = ("facebook.com", "fb.watch", "tiktok.com", "instagram.com", "youtube.com", "youtu.be", "t.me")


def clean_source(src):
    return re.sub(r"[\s|•\-–—:]+$", "", re.sub(r"^[\s|•\-–—:]+", "", src or "")).strip() or src


def news_card_post(msg, card_title, label, link, count=False):
    """Khabar design wale card ke saath; mukammal khabar ka link pehle comment mein (fb_post khud karta hai)."""
    card = make_card(card_title, label, theme="news") if CONFIG.get("news_cards", True) else None
    return fb_post(msg, link=link, photo=card, count=count, card=False)


def handle_cricket_news():
    """Pakistan ki qaumi cricket teamon (mard/khawateen) ki khabrein."""
    topic_news("cricket_news", CONFIG.get("cricket", {}).get("news", {}), "🏏",
               "true ONLY if it is about the Pakistan national cricket team, men's or women's (its matches, "
               "squad, captain, coach, selection) or a player of those national teams. false for other countries' "
               "cricket, domestic/franchise leagues (PSL etc.), Pakistan A/Shaheens/U19, or non-cricket news.",
               ["Pakistan cricket"])


def handle_agri_news():
    """Poore Pakistan ki zarat (kheti-baari) ki khabrein: fasal, qeemat, khaad, paani, kisan."""
    topic_news("agri_news", CONFIG.get("agriculture", {}), "🌾",
               "true ONLY if it is agriculture news useful for Pakistani farmers or the public: crops (wheat, "
               "cotton, rice, sugarcane, mango, vegetables), crop prices or support price, fertilizer/urea/DAP, "
               "seeds, irrigation water and canals, pests and crop diseases, weather affecting crops, livestock and "
               "dairy, farmer packages or government agriculture policy in Pakistan. false for news outside "
               "Pakistan, stock-market-only items, or non-agriculture news.",
               ["Pakistan agriculture"], max_age_h=CONFIG.get("agriculture", {}).get("max_age_hours", 24))


PUBLIC_ICONS = {"fuel": "⛽", "electricity_gas": "💡", "inflation": "🛒", "water": "💧", "budget_tax_imf": "💰",
                "education_jobs": "🎓", "health": "🏥", "weather_disaster": "🌦️", "transport_trade": "🚆",
                "dollar_gold_business": "💵", "technology": "📱", "other": "📰"}


CAT_WORDS = {
    "fuel": ["petrol", "diesel", "fuel", "lpg", "cng", "پیٹرول", "ڈیزل", "پيٽرول", "ڊيزل"],
    "electricity_gas": ["electricity", "power tariff", "load shedding", "loadshedding", "gas price", "sui", "nepra",
                        "بجلی", "لوڈشیڈنگ", "گیس", "بجلي", "گئس"],
    "inflation": ["inflation", "cpi", "flour", "sugar", "ghee", "milk", "mehngai", "مہنگائی", "آٹا", "چینی", "گھی", "مهانگائي"],
    "water": ["water", "dam", "barrage", "canal", "irsa", "پانی", "ڈیم", "بیراج", "نہر", "پاڻي", "بئراج"],
    "budget_tax_imf": ["imf", "budget", "tax", "fbr", "آئی ایم ایف", "بجٹ", "ٹیکس", "ٽيڪس"],
    "education_jobs": ["exam", "admission", "school", "university", "scholarship", "recruitment", "jobs", "result",
                       "امتحان", "داخلے", "اسکول", "نوکری", "بھرتی", "امتحان", "نوڪري"],
    "health": ["health", "hospital", "medicine", "drap", "polio", "dengue", "ہسپتال", "دوا", "صحت", "اسپتال", "دوائون"],
    "weather_disaster": ["weather", "rain", "heatwave", "flood", "earthquake", "pmd", "ndma", "cold wave", "fog",
                         "بارش", "سیلاب", "زلزلہ", "موسم", "گرمی", "مينهن", "ٻوڏ"],
    "transport_trade": ["railway", "train", "motorway", "highway", "port", "export", "import", "trade", "airline", "pia",
                        "ریلوے", "موٹروے", "برآمد", "ٽرين"],
    "dollar_gold_business": ["dollar", "rupee", "gold", "stock", "psx", "sbp", "interest rate", "ڈالر", "سونا", "روپیہ", "ڊالر", "سون"],
    "technology": ["internet", "mobile", "pta", "5g", "app", "technology", "ai ", "انٹرنیٹ", "موبائل", "ٽيڪنالاجي"],
}


def guess_cat(text):
    """AI mauzoo na bataye to lafzon se pehchano."""
    t = " " + text.lower() + " "
    best, hits = "other", 0
    for cat, words in CAT_WORDS.items():
        n = sum(1 for w in words if (re.search(r"\b" + re.escape(w.strip()) + r"\b", t) if w.isascii() else w in t))
        if n > hits:
            best, hits = cat, n
    return best


def handle_public_news():
    """Mulk bhar ki awami dilchaspi ki khabrein: petrol, bijli/gas, mehngai, paani, budget/IMF, taleem,
    sehat, mausam, transport, dollar/sona, technology."""
    topic_news("public_news", CONFIG.get("public_news", {}), "📰",
               "true ONLY if it is a factual Pakistan news item that affects ordinary people in one of these topics: "
               "petrol/diesel/fuel prices; electricity or gas rates and load-shedding; inflation and prices of daily-use "
               "items (flour, sugar, ghee, milk); water, dams and irrigation; government budget, taxes, IMF; education, "
               "exams, admissions, scholarships and government jobs; health, hospitals, medicines and their prices; "
               "weather, rain, heatwave, floods, earthquakes and climate change; transport, railways, roads, trade and "
               "national infrastructure; dollar rate, gold rate and business; technology, internet and mobile. "
               "false for political statements or party fights, crime, court cases about politicians, news outside "
               "Pakistan, rumours, or anything not in these topics.",
               ["petrol price Pakistan"], max_age_h=CONFIG.get("public_news", {}).get("max_age_hours", 12),
               icons=PUBLIC_ICONS)


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
    if S.get("token_check", {}).get("time", "")[:10] != today():  # din mein ek dafa token check
        check_token()
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
    def step(fn):  # har hissa alag: ek mein error aaye to baqi phir bhi chalein
        try:
            fn()
        except Exception:
            err = traceback.format_exc()
            log(err)
            STATS.setdefault("errors", []).append(fn.__name__)
            alert(f"System mein error aaya ({fn.__name__}):\n" + err[-600:])

    for fn in (process_telegram, expire_old, handle_news, handle_jobs, publish_queue, handle_promo, handle_daily,
               handle_engagement, handle_roundup, handle_trends):
        step(fn)
    sections = {"sindh_single": handle_sindh_single, "cricket_news": handle_cricket_news,
                "agri_news": handle_agri_news, "public_news": handle_public_news}
    try:
        order = section_order()
    except Exception:
        order = list(sections)
    for sec in order:  # is hafte jo zyada pasand/trend, wo pehle
        step(sections[sec])
    for fn in (handle_share_helper, handle_perf, handle_cricket_live, handle_auto_reply):
        step(fn)
    S["last_errors"] = {"time": now().strftime("%Y-%m-%d %H:%M"), "steps": STATS.get("errors", [])}
    send_report()
    if DRY_RUN:
        log("test mode: state save nahi kiya")
    else:
        save_state()
    log("done. aaj ki posts:", S["daily"]["count"], "| queue:", len(S["queue"]), "| review:", len(S["pending"]))


if __name__ == "__main__":
    main()
