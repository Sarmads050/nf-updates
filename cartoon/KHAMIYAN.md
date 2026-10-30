# Khamiyan (flaws) — Sarmad ki approval ke saath theek hoti hain
Format: `- [K-NNN] (episode, date) problem — proposed fix`. See RUNBOOK section 6.

## PENDING
- [K-005] (Sarmad, 2026-10-30) Kamar se neeche ka hissa real nahi lagta (patli seedhi taangein, gol joote, baithe huon ki god gaddi jaisi) — fix ready on branch `lower-v3` (kulhe, moti asli taangein, asli joote, shalwar ki silwatein, saaf god). Awaiting "han set kar do".
- [K-006] (ep007, 2026-10-30) Desk par baithe Arsalan ke ghutne kaale gol dabbe lagte hain — desk/charpai par baithne ki pose behtar banana.
- [K-007] (ep007, 2026-10-30) Bedroom close-up mein bolne wale ke saath wala character chhup jata hai — close-up frame thora chaura karna.

## APPROVED

## DONE
- [K-001] (ep007, 2026-10-30) Characters chibi/flat: sar bohot bara, baazu seedhi pipe, haath gol ball, chehra flat — v2 art ready on branch `char-v2` (chhota sar, patle hote baazu, angootha wale haath, shalwar-kameez, naak/bhauein/hont detail). Awaiting "han set kar do". — DONE 2026-10-30: merged char-v2 into main
- [K-002] (ep007, 2026-10-30) Baithe hue logon ki god (lap) ek dabba jaisi lagti hai — ghutno ki shape aur kameez ka gher behtar banana. — DONE 2026-10-30: two thighs + rounded knees instead of one box (engine.py)
- [K-003] (ep007, 2026-10-30) Kamre ke 3 log hon to bedroom close-up mein ek doosre ke aage aa jate hain (ep007 scene 2) — bedroom ke slots thore door karna. — DONE 2026-10-30: bedroom stand_c moved x 540->470 so desk/standing people don't overlap (sets.py)
- [K-004] (ep007, 2026-10-30) Kai lines "edge" fallback voice mein bani (11 of 27) — awaaz ka andaaz badal jata hai; Gemini quota ke hisaab se lines ko 2 din mein baantna ya fallback voices ko characters se behtar match karna. — DONE 2026-10-30: tts.py: one Gemini retry per line + upgrade a character's backup lines to Gemini before forcing all to backup

## REJECTED
