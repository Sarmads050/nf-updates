# Daily episode runbook — "Sindhi Ghar Ki Kahani"

You are making today's 2D cartoon episode for Sarmad (the channel owner). He reads simple Roman Urdu.
He will download the video from the chat and upload it himself. Work fully on your own; do not ask questions.
Total time budget ~60 min. Work in the scratchpad for big files; never commit videos.

## 0. Setup
1. `add_repo` owner `Sarmads050`, repo `nf-updates`, access `push`. Clone: `git clone --depth 1 https://github.com/Sarmads050/nf-updates /home/claude/nf-updates`
2. Read `cartoon/MASTER_PROMPT.md` (the writer rules — STRICT RULES are mandatory), this file, and `cartoon/episodes/index.json`
   (episodes already made — never repeat a topic). Never read or print any secret/key.

## 1a. Trend research (do this BEFORE choosing the topic, ~5 min)
Sarmad wants stories people in Pakistan — especially Sindh — relate to *right now*. Do not rely on one trend; combine several sources:
- WebSearch (standard; use today's date in queries): "Pakistan trending today", "Sindh news today", "Karachi news today",
  "Pakistan Twitter X trends", "Pakistan TikTok trend", "YouTube trending Pakistan", "Google Trends Pakistan",
  plus seasonal/life signals: weather (heat, rain, cold, smog), load shedding / gas / water shortage, petrol & electricity bill prices,
  cricket matches/series, exams/results/admissions, weddings season, Eid/holidays, harvest/mango season, school events.
- Optional (free tools only): vidIQ trending/outlier tools for Pakistan if they don't spend credits.
Write 5–8 short trend notes with source links into `cartoon/episodes/epNNN.md` under `TRENDS:`, then pick the topic that
(1) matches the most trends at once, (2) is an everyday family situation Sindhi middle-class viewers recognise, (3) obeys every
MASTER_PROMPT strict rule. Turn news into a gentle home situation (e.g. petrol price up → family plans to save fuel; big cricket
match → whole family fights over the TV). Never make comedy out of tragedies, accidents, deaths, crime, politics, religion or the army,
never use real people's names, and keep facts in the story true (no invented statistics or news).

## 1. Write the script (as the MASTER_PROMPT head writer)
- Use the topic chosen in 1a (never repeat a topic from index.json). Rotate characters and sets; use 2–5 characters.
- **90–120 seconds = 24–32 lines in 2–3 scenes** (Sarmad wants ~2 minute episodes). Hook in line 1.
- **The story must be easy to follow** (a viewer who has never seen the channel must understand it):
  1. Scene 1 (setup, ~25 s): open with a 1–2 line `NARRATOR` intro that says where we are and what the problem is
     (e.g. "Nawabshah ke is ghar mein aaj subah se ek hi sawal hai... gas cylinder khatam!"), then the characters show the problem.
  2. Scene 2 (complication, ~40 s): a different set or a new character arrives; things get funnier/worse; the main joke builds here.
  3. Scene 3 (resolution, ~30 s): the problem is solved, the punchline lands (`"joke": true`), a warm small lesson, final laugh.
  - One clear problem per episode, cause → effect. Characters say each other's names/relations ("Abba", "Ada Faraz", "Ammi").
  - Each line short (max ~14 words). Let reactions breathe (`gap` 0.5–0.8 after a joke). At least 2 jokes.
  - `NARRATOR` is an off-screen storyteller (not in cast); use it only at the start (and optionally one bridge line between scenes).
  - Every character's name and role is shown automatically the first time they speak.
- **Logic check (mandatory, like a script editor):** read the script once more only for facts and cause → effect.
  Every clue, problem and solution must be physically and logically possible in real life and must not contradict another line
  (e.g. if the router plug is pulled out, its lights are OFF, not red; a gas stove can't light without gas; a phone at 0% can't play a match).
  Also check continuity: who is in the room, who holds what, time of day, and that nobody knows something they could not know. Fix every mistake.
- Run the MASTER_PROMPT safety check (religion, army, real public figures, politics, children safe, respect).
- Run the MASTER_PROMPT safety check (religion, army, real public figures, politics, children safe, respect).
- Save the human script as `cartoon/episodes/epNNN.md` (TITLE, HOOK, CHARACTERS, LOCATION, SCENES, JOKE, ENDING, CAPTION + 5 HASHTAGS).

## 2. Convert to `cartoon/episodes/epNNN.json` (copy the shape of `ep001.json`)
Top: `id`, `series`, `episode` (number), `title`, `topic`, `music` (happy|comic|calm|tense), `lesson` (short, may use `<br>`),
`caption`, `hashtags` (5), `scenes` (2–3 scenes, each with a `label` like "Kitchen • Subah").

Scene: `set`, `time` (day|evening|night|loadshedding), `label` (e.g. "Nawabshah • Subah"), `cast` {CHAR: slot}, `props` {CHAR: prop}, `lines`.

Sets and slots:
- `living_room` (Nawabshah drawing room, sofa with rilli, fan, clock, door right): sofa_l, sofa_c, sofa_r, stand_l, stand_r, stand_cl, stand_cr, floor_l, floor_r
- `kitchen` (stove, masala shelf, gas cylinder, fridge, door left): stove, mid, right, left, floor_l, floor_r
- `aangan` (courtyard, neem tree, charpai, gate right): charpai_l, charpai_c, charpai_r, stand_l, stand_r, stand_c, floor_l, floor_r
- `karachi_flat` (Nimra's flat, big window with Karachi skyline, door left): sofa_l, sofa_c, sofa_r, stand_l, stand_r, stand_cl, stand_cr, floor_l, floor_r
- `bedroom` (boys' room: bed, computer desk, cricket poster, door right): bed, desk, stand_l, stand_r, stand_c, floor_l, floor_r
- `gali` (street outside, general store, chalk wicket): left, cl, cr, right, floor_l, floor_r
Staging tips: speakers who talk to each other should be side by side. stand_cl/stand_cr/stand_c are in FRONT of the sofa —
use them only when nobody sits right behind. Toddlers (HAMZA, HASHIR) go on floor_l/floor_r.

Characters (keys): ABBA, AMMI, IMTIAZ (Ada Imtiaz), SANA (Bhabi), HAMZA, HASHIR (2-yr twins), FARAZ, NIMRA, DANIYAL, ARSALAN, MEHAK,
plus NARRATOR (off-screen storyteller voice, never in `cast`).

Line fields:
- `who`, `to` (character addressed, or front/down/up/door), `roman` (caption, Roman Urdu; wrap 1–3 key words in `*stars*` for yellow highlight),
  `urdu` (same line in proper Urdu script — this is what the voice reads; write English words phonetically in Urdu script),
  `how` (voice acting direction in English), `emo` (string or [[frac, emo], ...]), `pose` (string or [[frac, pose], ...]),
  `react` {CHAR or "*": emo}, optional `react_pose` {CHAR: pose}, `looks` {CHAR: target}, `shot`, `sfx` [names], `joke`, `gap` (sec after line),
  `before`/`after` actions, `offscreen`: true (voice from another room), `phone`: true (voice on phone, speaker may be absent).
- emotions: neutral calm happy worried surprised teasing sheepish laugh warm focused angry tired proud confused sad
- poses: rest read head_hold beckon wag plead point_down fist point_other thumb_back arms_up chest wave hold newspaper phone_look
  hands_hips cross shrug facepalm scratch_head objection clap think explain point_up tired
- props (hand): cup phone newspaper remote bat book ladle plate bag toy tray
- shots: auto | wide | group | close | close:CHAR | punch | two | two:CHAR   (first line usually close on hook speaker; jokes = punch; end = group)
- sfx: whoosh door ding phone_ring notification clink pressure_cooker bat_hit sting boing crash knock baby_giggle tv rain bike light_on cash
- actions: {"do":"enter","who":C,"slot":S} {"do":"exit","who":C} {"do":"move","who":C,"slot":S} {"do":"prop","who":C,"prop":P}
  {"do":"sfx","name":N,"wait":sec} {"do":"wait","sec":s}

Validate: `python cartoon/check.py cartoon/episodes/epNNN.json` must print OK.

## 3. Voices (Gemini TTS in GitHub Actions, uses the repo secret — never touch the key)
```
git add cartoon/episodes && git commit -m "epNNN script" && git fetch origin main && git rebase origin/main && git push origin HEAD:main
gh api -X POST repos/Sarmads050/nf-updates/actions/workflows/cartoon-voices.yml/dispatches -f ref=main -f 'inputs[episode]=epNNN'
```
Poll `gh api "repos/Sarmads050/nf-updates/actions/workflows/cartoon-voices.yml/runs?per_page=1"` until completed (6–12 min),
then `git pull --rebase origin main`. Read `cartoon/episodes/out/epNNN/status.json`; if some lines failed, dispatch again with
`-f 'inputs[only]=3,7'`. If the free quota is finished for today, wait 20 min and retry once; if still failing, tell Sarmad simply.

## 4. Render
Preview first (fast): `PREVIEW=2,8,15,25 python cartoon/engine.py cartoon/episodes/epNNN.json cartoon/episodes/out/epNNN <scratch>/epNNN.mp4`
Look at the PNGs in `<scratch>/epNNN_work/`. Check like a professional animator:
speaker visible and not blocked in close-ups, nobody cut off at frame edge, caption matches speaker, title readable,
gestures make sense, staging/eye-lines feel natural. Fix the JSON (slots, shots, poses) and re-preview.
Then full render (~15–20 min for 2 minutes, 2 processes; run it in the background and wait for it): same command without PREVIEW.
Check duration 85–130 s. Voices for ~28 lines take ~15 min in the workflow (it waits between calls for the free quota).

## 5. Deliver
1. Extract 6 frames across the video and look at them one last time.
2. `SendUserFile` the mp4 (status proactive, display render).
3. Send Sarmad a short Roman Urdu message: episode number + title, 1 line story summary, the posting caption and the 5 hashtags
   (ready to copy), and "YouTube Shorts + Facebook Reels par upload karein".
4. Append the episode to `cartoon/episodes/index.json` (id, date, title, topic, set, cast), commit and push.
