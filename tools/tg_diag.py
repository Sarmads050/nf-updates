"""Telegram bot diagnose (sirf parhna; token kahin print nahi hota)."""
import json, os, requests
T = os.environ["TELEGRAM_BOT_TOKEN"]
s = json.load(open("state.json"))
B = f"https://api.telegram.org/bot{T}/"
out = {}
for m, p in (("getMe", {}), ("getWebhookInfo", {}),
             ("getUpdates", {"offset": s.get("tg_offset"), "timeout": 0, "allowed_updates": json.dumps(["callback_query", "message"])}),
             ("getUpdates_all", {"timeout": 0}),
             ("getUpdates_long", {"timeout": 50})):  # 409 Conflict here = another program is polling this bot
    try:
        r = requests.get(B + m.split("_")[0], params=p, timeout=70)
        j = r.json()
        if m.startswith("getUpdates") and j.get("ok"):
            j = {"ok": True, "count": len(j["result"]),
                 "items": [{"id": u["update_id"], "kind": [k for k in u if k != "update_id"],
                            "data": (u.get("callback_query") or {}).get("data")} for u in j["result"]]}
        out[m] = {"status": r.status_code, "body": j}
    except Exception as e:
        out[m] = {"error": str(e)}
txt = json.dumps(out, ensure_ascii=False, indent=1).replace(T, "***")
os.makedirs("out", exist_ok=True); open("out/tg_diag.json", "w").write(txt); print(txt[:3000])
