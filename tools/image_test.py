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
    ("ڪڻڪ جو پيداواري خرچ 3761 رپيا في مڻ تي ويو", "ملڪ ۾ ڪڻڪ جو في مڻ پيداواري خرچ وڌي 3 هزار 761 رپين تائين پهچي ويو آهي. ڪسان اتحاد جي چيئرمين خالد کوکر چيو ته ڀاڻ، ڊيزل ۽ ٻج جي قيمتن ۾ واڌ سبب هارين جو خرچ ٻيڻو ٿي ويو آهي. هن مطالبو ڪيو ته حڪومت ڪڻڪ جي امدادي قيمت 4 هزار 500 رپيا في مڻ مقرر ڪري. سنڌ حڪومت چيو آهي ته معاملي تي غور ڪيو پيو وڃي ۽ ايندڙ هفتي ڪابينا اجلاس ۾ فيصلو ٿيندو."),
]
report = []
for i, (t, b) in enumerate(tests, 1):
    p = bot.news_image(t, b)
    card = bot.make_card(t, "زراعت", b, theme="news", image=p)
    if card:
        shutil.copy(card, f"out/card{i}.png")
    if p:
        shutil.copy(p, f"out/test{i}.jpg")
        card = bot.make_card(t, "زراعت", b, theme="news", image=p)
        if card:
            shutil.copy(card, f"out/card{i}.png")
    report.append({"title": t, "image": bool(p)})
    print(i, t, "->", p, flush=True)
report.append({"checks": checks})
report.append({"img_diag": bot.S.get("img_diag")})
json.dump(report, open("out/report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(bot.S.get("img_diag"), ensure_ascii=False))
