# Low-poly 3D renderer (Sindhi Ghar Ki Kahani)

Same episode JSON + voices as the 2D engine; same timing, acting, lip-sync, captions and sound mix.
Only the picture is rebuilt in low-poly 3D (three.js r160 in headless Chromium).

    npm install three@0.160.0            # once, anywhere; point THREE_JS at build/three.min.js
    PREVIEW=4,30,60 THREE_JS=.../three.min.js python cartoon/r3d/render3d.py cartoon/episodes/epNNN.json cartoon/episodes/out/epNNN <scratch>/epNNN_3d.mp4
    FROM=0 TO=<n/2> ... render3d.py ...  &  FROM=<n/2> TO=<n> ... render3d.py ...   # two halves in parallel (~40 min for 2 min)
    # then concat <scratch>/epNNN_3d_work/video3d_*.mp4 + mix.wav with ffmpeg (loudnorm)

Sets: aangan, bedroom, living_room (others still 2D-only). Optional episode key `fx3d`:
`{"sneeze": [line, [line, offset_s]], "sick": [{"who": C, "from_line": n, "to_line": m}]}`.
