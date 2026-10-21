"""Telegram listener: aap ke clicks/messages ka FORAN jawab (button par "✅ Mil gaya") aur foran posting run.

Updates ko "confirm" nahi karta (sirf dekhta hai) — asal kaam autopost (bot.py) hi karta hai, is liye dono ek
doosre ke kaam mein dakhal nahi dete. ~5 ghante 50 minute chal kar band; bot.py khud dobara chala deta hai.
"""
import os
import re
import time

import requests

TOK = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = str(os.environ["TELEGRAM_CHAT_ID"])
GH = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
B = f"https://api.telegram.org/bot{TOK}/"
END = time.time() + float(os.environ.get("LISTEN_SECONDS", 5 * 3600 + 50 * 60))
seen, need_run, last_dispatch = set(), False, 0.0


def tg(method, **data):
    try:
        return requests.post(B + method, json=data, timeout=70).json()
    except Exception as e:
        print("tg error", method, e, flush=True)
        return {}


def dispatch():
    """Posting run (autopost) foran chalao."""
    global last_dispatch, need_run
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/autopost.yml/dispatches",
                      headers={"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main", "inputs": {"dry_run": "false"}}, timeout=30)
    print("dispatch autopost", r.status_code, flush=True)
    last_dispatch, need_run = time.time(), False


def handle(u):
    global need_run
    cq = u.get("callback_query")
    if cq:
        msg = cq.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != CHAT:
            return
        action = cq.get("data", "").split(":")[0]
        if action not in ("ok", "no"):
            tg("answerCallbackQuery", callback_query_id=cq["id"])
            return
        ok = action == "ok"
        tg("answerCallbackQuery", callback_query_id=cq["id"],
           text="✅ Mil gaya! 1-2 minute mein page par post hogi." if ok else "❌ Reject ho jayegi.")
        tg("editMessageReplyMarkup", chat_id=CHAT, message_id=msg.get("message_id"),
           reply_markup={"inline_keyboard": [[{"text": "⏳ Post ho rahi hai…" if ok else "❌ Reject",
                                               "callback_data": "noop"}]]})
        need_run = True
        return
    m = u.get("message") or {}
    if str(m.get("chat", {}).get("id")) != CHAT:
        return
    text = (m.get("text") or m.get("caption") or "").strip()
    if re.match(r"^\s*(ok|okay|post|haan|han|yes|no|nahi|nhi|reject)\s*#?\s*(\d{1,3}|all|sab)\s*$", text, re.I):
        tg("sendMessage", chat_id=CHAT, text="⏳ Mil gaya, 1-2 minute mein amal hoga.")
    elif text.startswith("/"):
        tg("sendMessage", chat_id=CHAT, text="⏳ Mil gaya, jawab 1-2 minute mein aata hai.")
    else:
        tg("sendMessage", chat_id=CHAT, text="⏳ Khabar mil gayi, 1-2 minute mein amal hoga.")
    need_run = True


while time.time() < END:
    r = tg("getUpdates", timeout=50, allowed_updates=["callback_query", "message"])
    if r.get("error_code") == 409:  # autopost isi waqt parh raha hai: thoda ruko
        time.sleep(5)
        continue
    items = r.get("result") or []
    new = [u for u in items if u["update_id"] not in seen]
    for u in new:
        seen.add(u["update_id"])
        try:
            handle(u)
        except Exception as e:
            print("handle error", e, flush=True)
    if need_run and time.time() - last_dispatch > 40:
        time.sleep(4)  # ek saath kai clicks: thoda jama hone do
        dispatch()
    if items and not new:
        time.sleep(4)  # purane (abhi autopost ne confirm nahi kiye) updates: long-poll foran lautata hai
print("listener band (waqt poora)", flush=True)
