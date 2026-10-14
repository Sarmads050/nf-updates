# Naushahro Feroze Updates - Auto Posting System

Ye system har 10 minute khud ba khud Naushahro Feroze aur Padidan ki khabrein dhoondta hai, unhein Sindhi mein likhta hai aur aap ke Facebook page par post karta hai. Har subah 9 baje naukriyon ki post lagti hai. Sensitive khabrein (qatl, firing, hadsa waghera) pehle aap ke Telegram par approval ke liye aati hain. Poora system **free** hai.

**Setup sirf ek dafa karna hai, takreeban 45-60 minute lagenge.** Laptop/computer par karna asaan hai, mobile par bhi ho sakta hai.

---

## Step 1: GitHub account aur repository

1. **github.com** kholen → **Sign up** → email, password, username banayen.
2. Login ke baad upar **+** → **New repository**.
3. Repository name: `nf-updates` → **Public** chunein → **Add a README file** par tick lagayen → **Create repository**.
4. Repository mein **Add file → Upload files** dabayen aur ye 5 files upload karein:
   `bot.py`, `config.json`, `requirements.txt`, `PRIVACY.md`, `README.md`
   Neeche **Commit changes** dabayen.
5. Ab **Add file → Create new file** dabayen. Naam ki jagah bilkul ye likhein:
   `.github/workflows/autopost.yml`
   (slash `/` likhte hi folder ban jata hai). Phir `autopost.yml` file ka poora text copy karke yahan paste karein → **Commit changes**.

## Step 2: Telegram bot (review ke liye)

1. Telegram mein **@BotFather** search karein → **Start** → `/newbot` likhen.
2. Bot ka naam likhen (maslan `NF Updates Review`), phir username jo `bot` par khatam ho (maslan `nfupdates_review_bot`).
3. BotFather ek **token** dega (lamba code, maslan `7412...:AAH...`). Isay save kar lein. Ye hai **TELEGRAM_BOT_TOKEN**.
4. Apne naye bot ko open karein aur **Start** dabayen (ye zaroori hai warna bot aap ko message nahi bhej sakega).
5. Ab **@userinfobot** search karein → Start. Woh aap ka **Id** (sirf number) batayega. Ye hai **TELEGRAM_CHAT_ID**.

## Step 3: Gemini API key (AI, free)

1. **aistudio.google.com** kholen aur apne Google account se login karein.
2. **Get API key** → **Create API key** → key copy karein. Ye hai **GEMINI_API_KEY**.

(Optional backup AI: **console.groq.com** par free account bana kar API key lein, ye **GROQ_API_KEY** hogi. Na bhi lein to system chalega.)

## Step 4: Facebook Page token (sab se ahem step)

**4a. App banana**
1. **developers.facebook.com** kholen → apne Facebook account se login → **Get Started** (pehli dafa phone verify karna pare ga).
2. **My Apps → Create App**. Naam: `NF Updates Poster`.
3. Use case mein **"Manage everything on your Page"** chunein (agar ye na dikhe to **Other** → **Business**). Aagay barhte jayen aur **Create app** karein.

**4b. App ko Live karna**
1. App ke andar **App settings → Basic** kholen.
2. **Privacy Policy URL** mein apne GitHub ki PRIVACY.md ka link dalein:
   `https://github.com/APNA-USERNAME/nf-updates/blob/main/PRIVACY.md`
   Yahi link **User data deletion** mein bhi dal dein. **Category**: News. **Save changes**.
3. Upar **App Mode** ko **Development** se **Live** par kar dein (ya **Publish** button). Ye zaroori hai, warna posts sirf aap ko nazar aayengi.

**4c. Token lena**
1. Upar menu se **Tools → Graph API Explorer** kholen.
2. Daayen taraf **Meta App** mein apni app chunein.
3. **Permissions** mein ye teen add karein: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
4. **Generate Access Token** dabayen. Popup mein apna page **Naushahro Feroze Updates** chunein → Continue → Done.
5. Ab jo token bana usay copy karein.

**4d. Token ko hamesha ke liye banana**
1. **Tools → Access Token Debugger** kholen → token paste → **Debug**.
2. Neeche **Extend Access Token** dabayen → naya token aayega, usay copy karein.
3. Wapas **Graph API Explorer** mein jayen, **Access Token** wale box mein ye naya token paste karein.
4. Query box mein `me/accounts` likh kar **Submit** dabayen.
5. Result mein apne page ke saamne:
   - `"access_token"` wala lamba code = **FB_PAGE_TOKEN**
   - `"id"` wala number = **FB_PAGE_ID**
6. Check: Access Token Debugger mein ye page token paste karein. **Expires: Never** likha ho to sab theek hai.

> ⚠️ Ye token kisi ko na dein, aur kabhi bhi GitHub ki files mein na likhen. Sirf agle step ke "Secrets" mein dalna hai.

## Step 5: Secrets GitHub mein dalna

Repository → **Settings → Secrets and variables → Actions → New repository secret**. Ek ek karke ye bananay hain (naam bilkul aise hi likhen):

| Name | Value |
|---|---|
| `FB_PAGE_ID` | Step 4d ka page id |
| `FB_PAGE_TOKEN` | Step 4d ka page token |
| `GEMINI_API_KEY` | Step 3 ki key |
| `TELEGRAM_BOT_TOKEN` | Step 2 ka token |
| `TELEGRAM_CHAT_ID` | Step 2 ka Id number |
| `GROQ_API_KEY` | (optional) |

## Step 6: Test aur shuru karna

1. Repository mein **Actions** tab kholen. Agar button aaye to **I understand my workflows, go ahead and enable them** dabayen.
2. Baayen taraf **NF Updates Autopost** → **Run workflow** → `dry_run` mein **true** rehne dein → **Run workflow**.
3. 2-3 minute mein aap ke Telegram par **🧪 TEST** wali posts aayengi. Facebook par abhi kuch post nahi hoga.
4. Sab theek lage to dobara **Run workflow** karein aur is dafa `dry_run` mein **false** likhen. Ab asal posting shuru.
5. Iske baad system **har 10 minute khud chalega**. Aap ko kuch nahi karna.

---

## Rozana ka istemal

- **🟠 REVIEW message** Telegram par aaye to **✅ Post karo** ya **❌ Reject** dabayen. Approve ki hui khabar 10 minute ke andar post ho jayegi. 24 ghante tak jawab na diya to khabar khud cancel.
- Telegram bot ko `/status` likhen to woh batayega aaj kitni posts hui aur kitni baqi hain.
- Koi masla ho (maslan token band ho jaye) to bot aap ko **⚠️** wala message bhejega.

## Settings badalna (config.json)

GitHub par `config.json` kholen → pencil ✏️ icon → badlav → **Commit changes**.

- `news_queries`: kin alfaaz se khabrein dhoondni hain.
- `trusted_domains`: sirf in websites ki khabrein post hongi. Koi bharosemand website add karni ho to yahan likhen.
- `sensitive_words`: in alfaaz wali khabrein review mein jayengi.
- `max_posts_per_day`: din ki zyada se zyada posts (abhi 10).
- `jobs_digest_hour`: naukriyon ki post ka waqt (9 = subah 9 baje).
- `promo.text`: 5000 followers ke baad wali promotion post ka text. Ye pehli dafa aur phir har Jumma lagegi.

## Facebook / local khabar khud bhejna (Telegram se)

**Aap khud (sab se aasan):** Facebook par koi local khabar dekhein → post ke neeche **Share** → **Telegram** → apna bot chunein → bhej dein.
- Bot us post ka text aur photo khud parh lega.
- Agar post band/private ho aur bot na parh sake, to woh aap ko batayega. Us waqt post ka **screenshot** bot ko bhej dein (bina caption ke), bot screenshot se khabar parh lega.
- Text copy karke bhejna, ya photo + caption bhejna bhi chalta hai.

Bot agle round (10 minute ke andar) mein:
- khabar ko apne lafzon mein Sindhi mein likhega (koi nayi baat nahi jorega, phone number hata dega),
- khabar ke aakhir mein dot (. ya ۔) ki jagah **!** lagayega,
- pabandiyan check karega (mazhab, gaali, fauj),
- aur **seedha page par post** karke aap ko "✅ Page par post ho gayi" bhejega.

**Videos:**
- **Aap ki apni video:** video file seedha bot ko bhejein (20 MB tak), caption mein chahein to kuch likh dein. Bot usay page par asal video ki tarah upload karega.
- **Aap ke apne TikTok / Instagram ka link:** pehle `config.json` mein `my_accounts` ke andar apne usernames likhen, maslan:
  `"my_accounts": {"tiktok": ["mera_username"], "instagram": ["mera_insta"], "facebook": []}`
  Phir apni video ka link bot ko share karein. Bot video download karke page par upload karega.
- **Doosron ki video (TikTok, Instagram, Facebook):** bot video download nahi karta. Woh video ki tafseel se Sindhi khabar likh kar **asal video ke link** ke saath post karta hai. Is se page copyright strike se bacha rehta hai aur asal banane wale ko credit milta hai.
- Instagram kabhi kabhi bina login video nahi deta. Aisa ho to bot aap ko batayega, us waqt video file seedha bhej dein.

**Sahafi:**
1. Sahafi aap ka bot Telegram mein khol kar **Start** dabaye.
2. Agle round mein aap ko message aayega: "👤 Naam khabrein bhejna chahte hain… /add 123456 Naam". Wahi line copy karke bot ko bhej dein.
3. Ab sahafi khabar (text ya photo + caption) bheje. Woh aap ke paas **🟠 SAHAFI KI KHABAR** ke taur par ✅ / ❌ ke saath aayegi. ✅ dabane par post, aur neeche un ka naam: ✍️ رپورٽ: Naam

Bot commands (sirf aap ke liye): `/status`, `/sahafi` (list), `/add ID Naam`, `/remove ID`

## Page barhane wale automatic features

- **Roz subah 7 baje "نوشهروفيروز جو اڄ"**: tareekh (Hijri bhi), namaz ke auqaat aur mausam. `config.json` → `daily_post` mein waqt (`hour`) badal sakte hain, ya `enabled: false` se band.
- **Har post ke neeche Follow/Share ki dawat**: `follow_line` mein text badal sakte hain.
- **Subah 6 aur shaam 6 baje "سنڌ جون اهم خبرون"**: poore Sindh ki ahem khabrein, har ek Sindhi mein ek line, alag post. Jurm aur pabandi wali khabrein shamil nahi hoti. `sindh_roundup` mein waqt aur alfaaz badal sakte hain.
- **Peer, Budh, Jumma shaam 8 baje sawal wali post** (maslan "ڪهڙي شهر مان آهيو؟"). `engagement` → `questions` mein apne sawal jor/badal sakte hain.
- **Comments ka khud jawab** (shuru mein band): Graph API Explorer mein token banate waqt `pages_read_user_content` aur `pages_manage_engagement` bhi add karein, naya page token `FB_PAGE_TOKEN` secret mein dalein, phir `auto_reply` → `enabled: true`. Har comment ka jawab 1 se 10 minute ke beech kisi random waqt par jata hai (`delay_min_minutes`, `delay_max_minutes`).
- **Telegram channel par bhi post**: Telegram mein ek public channel banayen (maslan @nf_updates), apne bot ko us channel ka **admin** banayen, aur `config.json` mein `"telegram_channel": "@nf_updates"` likh dein. Har post wahan bhi jayegi.

## Sindh ki chuni hui khabrein aur groups mein share

- **Sindh ki khabrein alag post (`sindh_single`)**: din mein zyada se zyada 4, sirf wohi jo Naushahro Feroze ke logon par asar karein (sarkari faisle, taleem/sehat, naukriyan, mausam, qeematein, paani, bijli/gas). District ki khabrein hamesha pehle; do posts ke beech kam se kam 2.5 ghante.
- **Groups mein share (`share_helper`)**: Facebook groups mein software se share ki ijazat nahi deta. Is liye dopahar 1 aur raat 8 baje bot Telegram par 2-3 achhi posts ke **Share** link bhejta hai; link dabayen → "Share to a group" → group chunein. `groups` mein apne groups ke naam likhen, maslan `[{"name": "Padidan Group"}, {"name": "Moro Online"}]`, to bot har post ke liye baari baari group batayega.

## Cricket

- **Live score**: Pakistan ka match shuru hote hi ek "🔴 LIVE" post lagti hai jo khud badalti rehti hai: aam match mein har 5 minute, Pakistan vs India mein har 1 minute.
- **Wicket**: har wicket par alag post (current score ke saath), ek match mein zyada se zyada 12 (`max_wicket_posts`).
- **Innings ka waqfa** aur **nateeja** alag posts mein; nateeja khabron ki sarkhi se Sindhi mein.
- **Cricket ki khabrein**: Pakistan cricket aur cricketers ki khabrein, din mein zyada se zyada 4 (`cricket.news`).
- Score ESPNcricinfo ki free live feed se aata hai. Khilari ka naam is free feed mein nahi hota.

## Pakki pabandiyan (ye kabhi post nahi hongi)

Neeche wali khabrein **na post hongi, na review ke liye Telegram par aayengi**, seedha rad:

1. **Mazhab:** kisi bhi mazhab, firqe, nabi, mazhabi shakhsiyat, kitab ya jagah ki tauheen, tauheen ke ilzamat, firqawarana nafrat ya jhagra.
2. **Gaali-galoch:** koi kisi ko gaali de raha ho, badzabani, ya khabar mein khud bure alfaaz hon.
3. **Fauj:** Pakistani fauj ka kisi bhi tarah zikr (Army, ISPR, Army Chief, Rangers, FC, Navy, Air Force), fauj ki naukriyan bhi.

Ye teen tareeqon se pakra jata hai: (1) `config.json` mein `blocked_words` ke alfaaz, (2) AI har khabar ko in teen baaton par check karta hai, (3) post hone se bilkul pehle aakhri check. Shaq ki surat mein bhi khabar rok di jati hai.

Agar koi aam khabar ghalti se rukne lage (maslan "فوجداری" yani criminal case mein "فوج" aata hai), to woh lafz `block_exceptions` mein daal dein.

## Khabron aur naukriyon ke sources

- **Google News**: `news_queries` aur `job_queries` ke alfaaz se.
- **Akhbaaron ke feeds** (`extra_feeds`): Awami Awaz (Sindhi), KTN News (Sindhi), Express (Urdu), ARY Urdu. In mein sirf woh khabar li jati hai jis mein district ya shehar ka naam ho.
- **Naukri pages** (`job_pages`): ilmkidunya ka Naushahro Feroze wala page. Naya link aate hi agli subah ki naukri post mein shamil.
- **Telegram channels** (`telegram_channels`): koi bhi *public* Telegram channel jo aap ko bharosemand lage. Channel ka username (bina @) aise likhen:
  `"telegram_channels": [{"name": "channel_username", "type": "jobs"}, {"name": "doosra_channel", "type": "news"}]`
  `type: news` wale channel se sirf district wali khabar li jayegi.

Facebook pages/groups aur WhatsApp se khabrein uthana mumkin nahi: Facebook doosre pages ka data parhne ki free ijazat nahi deta, aur chori chhupe parhne se aap ka account band ho sakta hai.

## SBA region tak barhana

`news_queries` aur `district_towns` mein naye shehar add kar dein, maslan:
`"Nawabshah"`, `"Shaheed Benazirabad"`, `"Sanghar"`, `"Sakrand"`, `"Daur"`, `"Shahdadpur"`, `"نوابشاہ"`, `"سانگھڑ"`.
Aur `hashtags` mein naye tags. Code badalne ki zaroorat nahi.

## Masail aur hal

| Masla | Hal |
|---|---|
| Kuch bhi post nahi ho raha | Actions tab mein aakhri run kholen aur "Run bot" ka log parhen |
| ⚠️ Facebook error | Step 4c-4d dobara karke naya token `FB_PAGE_TOKEN` secret mein update karein |
| Telegram par kuch nahi aata | Bot ko Start kiya tha? `TELEGRAM_CHAT_ID` sahi number hai? |
| Posts Urdu mein aa rahi hain | AI ko Sindhi mein mushkil hui ya AI limit khatam. System khud Urdu/headline par chala jata hai |
| Ghalat area ki khabar | `news_queries` mein us lafz ko zyada wazeh karein |

**Note:** Khabar ka text sirf headline se banta hai, AI ko apni taraf se koi baat jorne ki ijazat nahi. Har post mein asal source ka naam aur link hota hai.

## Mulk bhar ki khabrein, hifazat aur seekhna

- **Zarat (🌾)** aur **awami khabrein**: petrol ⛽, bijli/gas 💡, mehngai 🛒, paani 💧, budget/IMF 💰, taleem/naukri 🎓, sehat 🏥, mausam 🌦️, transport 🚆, dollar/sona 💵, technology 📱. Settings: `config.json` mein `agriculture` aur `public_news`.
- **24 ghante**: ye khabrein din raat lagti hain; raat (1 se 6 baje) ko waqfa lamba hota hai.
- **Page ki hifazat** (`safety`): din mein kul zyada se zyada 50 posts, har nai khabar ke beech kam az kam 10 minute (raat 1 se 6 baje 30 minute).
- **Seekhna** (`learning`): har post ke ~20 ghante baad us ke likes, comments aur shares gine jaate hain. Jo hissa/mauzoo zyada pasand ho, us ki posts aur search khud badh jaati hain (2 guna tak), kam pasand wale kam (aadhe tak). Telegram par `/likes` likh kar dekhein.
- **Pakistan trends** (`trends`): har 3 ghante Google Trends (Pakistan) parhe jaate hain, AI un ka mauzoo pehchanta hai (Sindh wale trend do guna). Har mauzoo ka zor = pichle 7 din ki pasand x pichle 7 din ka trend. Garam mauzoo ki posts 2.5 guna tak, thande ki aadhi tak; trend wale lafz bhi search hote hain. Jo hissa zyada garam ho wo pehle post karta hai (posting order). `/likes` mein order aur trends dikhte hain.
