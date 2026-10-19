"""News card tasveer ka test: namoona khabron par tasveer banao, check karo, out/ mein rakho (state save nahi hota)."""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot

bot.S.update(json.load(open("state.json", encoding="utf-8")))
os.makedirs("out", exist_ok=True)
_orig_match = bot.image_matches
_n = [0]
checks = []
def _spy(img, subject, title):
    _n[0] += 1
    open(f"out/try{_n[0]}.jpg", "wb").write(img)
    q = ("News headline: " + title + "\nRequired subject: " + subject + "\nDescribe in one sentence what this picture shows."
         "\nReturn JSON: {\"shows\": string}")
    desc = bot._ask_gemini(q, image=img) or bot.ask_openrouter(q, image=img)
    v = _orig_match(img, subject, title)
    checks.append({"try": _n[0], "subject": subject, "verdict": v, "desc": desc})
    return v
bot.image_matches = _spy
tests = [
    ("ڪڻڪ جو پيداواري خرچ 3761 رپيا في مڻ تي ويو", "ملڪ ۾ ڪڻڪ جو في مڻ پيداواري خرچ وڌي 3 هزار 761 رپين تائين پهچي ويو آهي، جنهن سبب هارين جي خرچن ۽ مارڪيٽ ۾ اٽي جي قيمتن تي سڌو سنئون اثر پوڻ جو امڪان آهي"),
    ("پيٽرول جي قيمت ۾ 5 رپيا واڌ", "حڪومت پيٽرول جي في ليٽر قيمت ۾ 5 رپيا واڌ جو اعلان ڪيو آهي، نئين قيمت سڀاڻي کان لاڳو ٿيندي"),
]
report = []
for i, (t, b) in enumerate(tests, 1):
    p = bot.news_image(t, b)
    if p:
        shutil.copy(p, f"out/test{i}.jpg")
        card = bot.make_card(t, "خبرون", b, theme="news", image=p) if hasattr(bot, "make_card") else None
        if card:
            shutil.copy(card, f"out/card{i}.png")
    report.append({"title": t, "image": bool(p)})
    print(i, t, "->", p, flush=True)
report.append({"checks": checks})
report.append({"img_diag": bot.S.get("img_diag")})
json.dump(report, open("out/report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(bot.S.get("img_diag"), ensure_ascii=False))
