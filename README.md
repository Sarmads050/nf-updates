# Naushahro Feroze Updates - Auto Posting System

Ye system har 30 minute khud ba khud Naushahro Feroze aur Padidan ki khabrein dhoondta hai, unhein Sindhi mein likhta hai aur aap ke Facebook page par post karta hai. Har subah 9 baje naukriyon ki post lagti hai. Sensitive khabrein (qatl, firing, hadsa waghera) pehle aap ke Telegram par approval ke liye aati hain. Poora system **free** hai.

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
5. Iske baad system **har 30 minute khud chalega**. Aap ko kuch nahi karna.

---

## Rozana ka istemal

- **🟠 REVIEW message** Telegram par aaye to **✅ Post karo** ya **❌ Reject** dabayen. Approve ki hui khabar 30 minute ke andar post ho jayegi. 24 ghante tak jawab na diya to khabar khud cancel.
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
