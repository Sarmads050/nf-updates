# Khamiyan (flaws) — Sarmad ki approval ke saath theek hoti hain
Format: `- [K-NNN] (episode, date) problem — proposed fix`. See RUNBOOK section 6.

## PENDING
- [K-005] (Sarmad, 2026-10-30) Kamar se neeche ka hissa real nahi lagta (patli seedhi taangein, gol joote, baithe huon ki god gaddi jaisi) — fix ready on branch `lower-v3` (kulhe, moti asli taangein, asli joote, shalwar ki silwatein, saaf god). Awaiting "han set kar do".
- [K-006] (ep007, 2026-10-30) Desk par baithe Arsalan ke ghutne kaale gol dabbe lagte hain — desk/charpai par baithne ki pose behtar banana.
- [K-007] (ep007, 2026-10-30) Bedroom close-up mein bolne wale ke saath wala character chhup jata hai — close-up frame thora chaura karna.
- [K-012] (ep009, 2026-11-02) Pichle scene ka pose agle scene mein chala jata hai (Abba ka facepalm kitchen mein entry par bhi tha; abhi `react_pose` se haath se theek kiya) — har naye scene ke shuru mein sab ke pose khud "rest" par reset karna (engine.py).
- [K-013] (ep009, 2026-11-02) Bat pakra hua character "plead/hold" pose mein ho to bat seedha chehre ke aage aa jata hai (Arsalan line 3) — bat ko hamesha side mein neeche pakarna, chehre se door.
- [K-014] (ep009, 2026-11-02) "approach" se khare log baithe logon ke peeche aa jate hain (Ammi raat wale scene mein Mehak ke peeche chhup gayin, paise lete waqt) — approach mein sofa ke saamne khali jagah (stand_cl/cr) chun-na.
- [K-015] (ep009, 2026-11-02) Ammi ki "ration list" ke liye sirf kitaab (book) prop hai jo side mein chhoti si dikhti hai — naya "list" prop (kaghaz ka lamba parcha) banana.

## APPROVED

## DONE
- [K-008] (ep008, 2026-11-01) Plate/thaali mein khana (biryani, aloo) nazar nahi aata — "do aloo" ya "nau aloo" wali line par plate khaali si lagti hai — plate/tray prop mein biryani ka dher aur 2-3 aloo draw karna (aur "food" variant). — DONE 2026-11-01: biryani plate + thaali props (art.draw_food)
- [K-009] (ep008, 2026-11-01) "Moonh bhara hua" (Daniyal line 13) sirf awaaz se pata chalta hai, chehre par chabane ki acting nahi — "chew" emotion add karna (phoole gaal + moonh band hil raha ho). — DONE 2026-11-01: "chew" emotion: puffed cheeks + small chewing mouth
- [K-010] (ep008, 2026-11-01) Aangan mein stand_r par khara character charpai_r wale ke aage aa jata hai aur group/two-shot mein use dhak deta hai — aangan ke stand_r slot ko thora right/peeche karna (x 910→960, foot 1700→1660). — DONE 2026-11-01: aangan stand_r x 910→935, foot 1700→1655, s 0.8→0.76 (sets.py)
- [K-011] (ep008, 2026-11-01) Charpai par saath baithe log plate pakarte hain to ek ka baazu doosre ke kapron par aa jata hai (Imtiaz ka haath Mehak par) — baithe hue "hold" pose mein plate ko seene ke qareeb rakhna. — DONE 2026-11-01: seated "hold" → hold_sofa pose, plate near own chest (engine.py)
- [K-001] (ep007, 2026-10-30) Characters chibi/flat: sar bohot bara, baazu seedhi pipe, haath gol ball, chehra flat — v2 art ready on branch `char-v2` (chhota sar, patle hote baazu, angootha wale haath, shalwar-kameez, naak/bhauein/hont detail). Awaiting "han set kar do". — DONE 2026-10-30: merged char-v2 into main
- [K-002] (ep007, 2026-10-30) Baithe hue logon ki god (lap) ek dabba jaisi lagti hai — ghutno ki shape aur kameez ka gher behtar banana. — DONE 2026-10-30: two thighs + rounded knees instead of one box (engine.py)
- [K-003] (ep007, 2026-10-30) Kamre ke 3 log hon to bedroom close-up mein ek doosre ke aage aa jate hain (ep007 scene 2) — bedroom ke slots thore door karna. — DONE 2026-10-30: bedroom stand_c moved x 540->470 so desk/standing people don't overlap (sets.py)
- [K-004] (ep007, 2026-10-30) Kai lines "edge" fallback voice mein bani (11 of 27) — awaaz ka andaaz badal jata hai; Gemini quota ke hisaab se lines ko 2 din mein baantna ya fallback voices ko characters se behtar match karna. — DONE 2026-10-30: tts.py: one Gemini retry per line + upgrade a character's backup lines to Gemini before forcing all to backup

## REJECTED
