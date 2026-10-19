"""News card tasveer ka test: namoona khabron par tasveer banao, check karo, out/ mein rakho (state save nahi hota)."""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot

bot.S.update(json.load(open("state.json", encoding="utf-8")))
os.makedirs("out", exist_ok=True)
tests = [
    ("ڪڻڪ جو پيداواري خرچ 3761 رپيا في مڻ تي ويو", "ملڪ ۾ ڪڻڪ جو في مڻ پيداواري خرچ وڌي 3 هزار 761 رپين تائين پهچي ويو آهي، جنهن سبب هارين جي خرچن ۽ مارڪيٽ ۾ اٽي جي قيمتن تي سڌو سنئون اثر پوڻ جو امڪان آهي"),
    ("پيٽرول جي قيمت ۾ 5 رپيا واڌ", "حڪومت پيٽرول جي في ليٽر قيمت ۾ 5 رپيا واڌ جو اعلان ڪيو آهي، نئين قيمت سڀاڻي کان لاڳو ٿيندي"),
    ("مورو ۾ نئين اسڪول جو افتتاح", "مورو شهر ۾ ٻارن لاءِ نئين سرڪاري پرائمري اسڪول جو افتتاح ڪيو ويو، جتي 300 ٻار تعليم حاصل ڪندا"),
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
report.append({"img_diag": bot.S.get("img_diag")})
json.dump(report, open("out/report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(bot.S.get("img_diag"), ensure_ascii=False))
