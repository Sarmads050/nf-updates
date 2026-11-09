/* Sindhi Ghar Ki Kahani - low-poly 3D renderer v2 (three.js r160, window.THREE + window.PP post-processing).
   LP.init(data) once, then LP.frame(i) -> jpeg dataURL.
   v2: viseme lip-sync, expressive faces, fingers, shaped bodies, spring cloth/hair, planted walk cycle,
       sit/stand acting, anticipation+overshoot, OTS/close-up cameras that find the face,
       GTAO + rim light + bloom + depth of field + per-scene grade, richer Sindhi sets. */
(function () {
  const T = THREE, PP = window.PP;
  const W = 1080, H = 1920, FOV = 38, DT = 1 / 30;
  let renderer, scene, camera, D, composer, gtao, bokeh, bloom, grade, rim;
  const SETS = {}, CHARS = {};
  let camState = null, lastKey = null, lastSi = -1, lastFrame = -9;

  // ------------------------------------------------------------------ helpers
  const C = (v) => Array.isArray(v) ? new T.Color(v[0] / 255, v[1] / 255, v[2] / 255) : new T.Color(v);
  const MC = {};
  function M(c, opts) {
    const key = (Array.isArray(c) ? c.map(Math.round).join(",") : c) + JSON.stringify(opts || {});
    if (!MC[key]) MC[key] = new T.MeshLambertMaterial(Object.assign({ color: C(c), flatShading: true }, opts || {}));
    return MC[key];
  }
  function mesh(g, m, cast = true, recv = true) { const o = new T.Mesh(g, m); o.castShadow = cast; o.receiveShadow = recv; return o; }
  function box(w, h, d, c, x = 0, y = 0, z = 0, p) { const o = mesh(new T.BoxGeometry(w, h, d), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function cyl(rt, rb, h, seg, c, x = 0, y = 0, z = 0, p) { const o = mesh(new T.CylinderGeometry(rt, rb, h, seg), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function ico(r, c, det = 1, x = 0, y = 0, z = 0, p) { const o = mesh(new T.IcosahedronGeometry(r, det), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function lathe(pts, seg, c, p, opts) { const o = mesh(new T.LatheGeometry(pts.map(([r, y]) => new T.Vector2(r, y)), seg), M(c, opts)); if (p) p.add(o); return o; }
  function hash(x, y, z) { const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453; return s - Math.floor(s); }
  function jitter(g, a) {
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      const kx = Math.round(x * 1000) / 1000, ky = Math.round(y * 1000) / 1000, kz = Math.round(z * 1000) / 1000;
      p.setXYZ(i, x + (hash(kx, ky, kz) - 0.5) * a, y + (hash(ky, kz, kx) - 0.5) * a, z + (hash(kz, kx, ky) - 0.5) * a);
    }
    g.computeVertexNormals(); return g;
  }
  const UP = new T.Vector3(0, 1, 0);
  const V = (x, y, z) => new T.Vector3(x, y, z);
  function place(o, a, b) {
    const d = new T.Vector3().subVectors(b, a); const L = d.length();
    o.position.copy(a).addScaledVector(d, 0.5);
    o.scale.set(1, Math.max(L, 1e-4), 1);
    o.quaternion.setFromUnitVectors(UP, d.normalize());
  }
  const lerp = (a, b, u) => a + (b - a) * u;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (u) => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
  const backOut = (u) => { u = clamp(u, 0, 1); const s = 1.4; return 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2); };
  function gesture(u) { // anticipation (small move back) then overshoot settle
    if (u <= 0) return 0; if (u >= 1) return 1;
    if (u < 0.18) return -0.07 * Math.sin(u / 0.18 * Math.PI);
    return backOut((u - 0.18) / 0.82);
  }
  function canvasTex(w, h, draw) {
    const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; t.anisotropy = 4; return t;
  }
  function instBoxes(list, w, h, d, p, cast = false) {
    const g = new T.BoxGeometry(w, h, d);
    const im = new T.InstancedMesh(g, new T.MeshLambertMaterial({ flatShading: true }), list.length);
    const m4 = new T.Matrix4(), q = new T.Quaternion(), s = new T.Vector3();
    list.forEach((e, i) => {
      s.set(e[4] || 1, e[5] || 1, e[6] || 1);
      q.setFromEuler(new T.Euler(0, 0, e[7] || 0));
      m4.compose(new T.Vector3(e[0], e[1], e[2]), q, s); im.setMatrixAt(i, m4); im.setColorAt(i, C(e[3]));
    });
    im.castShadow = cast; im.receiveShadow = true; p.add(im); return im;
  }
  function gradientSky(top, mid, bot, p, w = 70, h = 30, z = -16, y = 8) {
    const g = new T.PlaneGeometry(w, h, 1, 24);
    const cols = []; const ct = C(top), cm = C(mid), cb = C(bot);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const v = (pos.getY(i) / h) + 0.5; const c = new T.Color();
      if (v > 0.4) c.lerpColors(cm, ct, (v - 0.4) / 0.6); else c.lerpColors(cb, cm, v / 0.4);
      cols.push(c.r, c.g, c.b);
    }
    g.setAttribute("color", new T.Float32BufferAttribute(cols, 3));
    const o = new T.Mesh(g, new T.MeshBasicMaterial({ vertexColors: true, fog: false })); o.position.set(0, y, z); p.add(o); return o;
  }
  function framePic(w, h, tex, x, y, z, p, frameCol = [120, 70, 40], ry = 0) {
    const g = new T.Group(); g.position.set(x, y, z); g.rotation.y = ry; p.add(g);
    box(w + 0.08, h + 0.08, 0.04, frameCol, 0, 0, 0, g);
    const pl = new T.Mesh(new T.PlaneGeometry(w, h), new T.MeshLambertMaterial({ map: tex })); pl.position.z = 0.025; g.add(pl);
    return g;
  }
  // Sindhi textures
  function ajrakTex(n = 6, border = true) {
    return canvasTex(256, 256, (x, w, h) => {
      x.fillStyle = "#9e1b26"; x.fillRect(0, 0, w, h);
      const s = w / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const cx = i * s + s / 2, cy = j * s + s / 2;
        x.fillStyle = "#1b2347"; x.beginPath(); for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4, r = k % 2 ? s * 0.22 : s * 0.42; x.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a)); } x.fill();
        x.fillStyle = "#9e1b26"; x.beginPath(); x.arc(cx, cy, s * 0.14, 0, 7); x.fill();
        x.fillStyle = "#f3ead2"; x.beginPath(); x.arc(cx, cy, s * 0.06, 0, 7); x.fill();
        x.fillStyle = "#f3ead2"; [[0, 0], [s, 0], [0, s], [s, s]].forEach(([a, b]) => { x.beginPath(); x.arc(i * s + a, j * s + b, 3, 0, 7); x.fill(); });
      }
      if (border) { x.fillStyle = "#1b2347"; x.fillRect(0, 0, w, 14); x.fillRect(0, h - 14, w, 14); x.fillStyle = "#f3ead2"; for (let k = 0; k < 32; k++) { x.fillRect(k * 8 + 2, 5, 4, 4); x.fillRect(k * 8 + 2, h - 9, 4, 4); } }
    });
  }
  function rilliTex(n = 4) {
    return canvasTex(256, 256, (x, w, h) => {
      const cols = ["#f2e8d0", "#c0392b", "#1f6f8b", "#f2c14e", "#2d6a4f"]; const s = w / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        x.fillStyle = cols[(i + j) % 2 ? 1 : 2]; x.fillRect(i * s, j * s, s, s);
        x.fillStyle = cols[0]; x.beginPath(); x.moveTo(i * s + s / 2, j * s + 6); x.lineTo(i * s + s - 6, j * s + s / 2); x.lineTo(i * s + s / 2, j * s + s - 6); x.lineTo(i * s + 6, j * s + s / 2); x.fill();
        x.fillStyle = cols[3 + ((i * j) % 2)]; x.fillRect(i * s + s / 2 - 7, j * s + s / 2 - 7, 14, 14);
      }
    });
  }
  function sindhiTex(c1, c2, c3, n = 8) {
    return canvasTex(256, 256, (x, w, h) => {
      x.fillStyle = c1; x.fillRect(0, 0, w, h); const s = w / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        x.fillStyle = (i + j) % 2 ? c2 : c3; x.beginPath(); x.moveTo(i * s + s / 2, j * s + 4); x.lineTo(i * s + s - 4, j * s + s / 2); x.lineTo(i * s + s / 2, j * s + s - 4); x.lineTo(i * s + 4, j * s + s / 2); x.fill();
        x.fillStyle = "#fff6"; x.fillRect(i * s + s / 2 - 3, j * s + s / 2 - 3, 6, 6);
      }
    });
  }
  function texBox(w, h, d, tex, side, x, y, z, p) {
    const m = new T.MeshLambertMaterial({ map: tex });
    const o = mesh(new T.BoxGeometry(w, h, d), [M(side), M(side), m, M(side), m, M(side)]); o.position.set(x, y, z); if (p) p.add(o); return o;
  }

  // ------------------------------------------------------------------ lights
  function lightRig(p, o) {
    const hemi = new T.HemisphereLight(C(o.sky), C(o.ground), o.hemi); p.add(hemi);
    const sun = new T.DirectionalLight(C(o.sun), o.sunI);
    sun.position.set(...o.sunPos); sun.target.position.set(0, 0.6, 0);
    sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
    const sc = sun.shadow.camera; sc.left = -5; sc.right = 5; sc.top = 5; sc.bottom = -5; sc.near = 0.5; sc.far = 30;
    sun.shadow.bias = -0.0006; sun.shadow.normalBias = 0.02; sun.shadow.radius = 3;
    p.add(sun); p.add(sun.target);
    const fill = new T.DirectionalLight(C(o.fill || [255, 255, 255]), o.fillI || 0.35); fill.position.set(0, 3, 8); p.add(fill);
    const rimL = new T.DirectionalLight(C(o.rim || [255, 240, 220]), o.rimI || 1.1); rimL.position.set(2.5, 4, -6); p.add(rimL);
    const rimL2 = new T.DirectionalLight(C(o.rim2 || [200, 220, 255]), (o.rimI || 1.1) * 0.6); rimL2.position.set(-3, 3, -5); p.add(rimL2);
    return { hemi, sun, fill };
  }

  // ------------------------------------------------------------------ props
  function makeProp(name) {
    const g = new T.Group();
    if (name === "bat") {
      cyl(0.017, 0.017, 0.26, 6, [40, 40, 46], 0, -0.06, 0, g);
      cyl(0.02, 0.02, 0.03, 6, [60, 40, 30], 0, 0.08, 0, g);
      box(0.1, 0.56, 0.035, [232, 196, 130], 0, -0.46, 0.0, g);
      box(0.06, 0.5, 0.02, [214, 176, 110], 0, -0.46, -0.026, g);
      box(0.1, 0.06, 0.037, [200, 60, 60], 0, -0.66, 0.0, g);
    } else if (name === "cup") {
      cyl(0.042, 0.033, 0.095, 9, [250, 250, 250], 0, 0.05, 0.035, g);
      cyl(0.044, 0.044, 0.012, 9, [70, 130, 200], 0, 0.085, 0.035, g);
      cyl(0.037, 0.037, 0.004, 9, [170, 100, 50], 0, 0.093, 0.035, g);
      const h = mesh(new T.TorusGeometry(0.022, 0.007, 4, 8), M([250, 250, 250])); h.position.set(0.048, 0.05, 0.035); h.rotation.y = Math.PI / 2; g.add(h);
      g.userData.steam = [];
      for (let k = 0; k < 4; k++) {
        const s = mesh(new T.IcosahedronGeometry(0.02, 0), new T.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, flatShading: true }), false, false);
        g.add(s); g.userData.steam.push(s);
      }
    } else if (name === "book") {
      box(0.17, 0.24, 0.036, [50, 100, 180], 0, 0.06, 0.05, g);
      box(0.16, 0.225, 0.03, [245, 240, 225], 0.006, 0.06, 0.05, g);
      box(0.12, 0.03, 0.002, [250, 220, 90], -0.005, 0.12, 0.069, g);
    } else if (name === "phone") {
      box(0.07, 0.14, 0.012, [30, 30, 38], 0, 0.06, 0.03, g);
      box(0.06, 0.12, 0.002, [120, 190, 250], 0, 0.06, 0.037, g);
    } else if (name) {
      box(0.12, 0.12, 0.12, [200, 120, 160], 0, 0, 0.05, g);
    }
    g.traverse(o => { if (o.isMesh && o.material && !o.material.transparent) o.castShadow = true; });
    return g;
  }

  // ------------------------------------------------------------------ acting tables
  const EMO = { // brow tilt, brow raise, eye open, smile(+)/frown(-), min mouth open, asym, cheek raise
    calm: [0, 0, 1, 0.5, 0, 0, 0.1], neutral: [0, 0, 1, 0, 0, 0, 0], happy: [0.08, 0.012, 0.82, 1, 0, 0, 0.7], laugh: [0.12, 0.016, 0.28, 1, 0.75, 0, 1],
    warm: [0.1, 0.006, 0.8, 0.9, 0, 0, 0.5], teasing: [-0.12, 0, 0.7, 0.8, 0, 1, 0.4], sheepish: [0.38, 0.014, 0.82, 0.45, 0, 0, 0.3],
    worried: [0.45, 0.018, 1.08, -0.6, 0, 0, 0], surprised: [0.06, 0.04, 1.35, 0, 0.45, 0, 0], angry: [-0.5, -0.01, 0.8, -0.7, 0, 0, 0],
    tired: [0.25, -0.006, 0.48, -0.25, 0, 0, 0], proud: [-0.05, 0.01, 0.75, 0.9, 0, 0, 0.5], confused: [0.25, 0.012, 1, -0.25, 0, 2, 0],
    sad: [0.5, 0.012, 0.75, -0.9, 0, 0, 0], focused: [-0.22, -0.005, 0.82, 0, 0, 0, 0], chew: [0, 0, 0.9, 0.2, 0, 0, 0.3],
  };
  // hand targets relative to the shoulder-line centre (x + = near/face side), y up, z forward; flags; palm dir; curl
  const P3 = {
    rest_stand: [[0.22, -0.5, 0.05], [-0.22, -0.5, 0.05], "", "in", 0.35], rest_sofa: [[0.12, -0.4, 0.3], [-0.12, -0.4, 0.3], "", "down", 0.35],
    read: [[0.1, -0.22, 0.32], [-0.06, -0.24, 0.32], "prop", "in", 0.75], head_hold: [[0.21, 0.24, 0.04], [-0.21, 0.24, 0.04], "", "in", 0.25],
    beckon: [[0.3, 0.02, 0.26], null, "wave", "up", 0.1], wag: [[0.24, 0.02, 0.3], null, "wag finger", "fwd", 1], plead: [[0.06, -0.14, 0.33], [-0.05, -0.15, 0.33], "", "up", 0.25],
    point_down: [[0.33, -0.42, 0.32], null, "finger", "down", 1], fist: [[0.25, 0.16, 0.18], null, "", "in", 1], point_other: [[0.52, -0.06, 0.2], null, "finger", "down", 1],
    thumb_back: [null, [-0.3, -0.06, -0.04], "farfinger", "in", 1], arms_up: [[0.36, 0.48, 0.06], [-0.36, 0.48, 0.06], "jump", "fwd", 0.05],
    chest: [[0.04, -0.17, 0.2], null, "", "in", 0.2], wave: [[0.33, 0.28, 0.12], null, "wave", "fwd", 0.0], hold: [[0.14, -0.24, 0.32], null, "prop", "in", 0.75],
    newspaper: [[0.16, -0.18, 0.34], [-0.16, -0.18, 0.34], "prop", "in", 0.7], phone_look: [[0.07, 0.0, 0.3], null, "prop", "in", 0.75],
    hands_hips: [[0.25, -0.46, -0.02], [-0.25, -0.46, -0.02], "elbows", "in", 0.8], cross: [[-0.1, -0.22, 0.2], [0.1, -0.2, 0.22], "", "in", 0.6],
    shrug: [[0.38, -0.16, 0.2], [-0.38, -0.16, 0.2], "shrug", "up", 0.05], facepalm: [[0.03, 0.27, 0.21], null, "", "back", 0.15],
    scratch_head: [[0.14, 0.36, -0.02], null, "scratch", "in", 0.6], objection: [[0.28, 0.4, 0.22], null, "finger", "fwd", 1], clap: [[0.03, -0.18, 0.32], [-0.03, -0.18, 0.32], "clap", "in", 0.05],
    think: [[0.04, 0.1, 0.2], [-0.04, -0.24, 0.2], "", "in", 0.7], explain: [[0.33, -0.18, 0.26], [-0.31, -0.22, 0.22], "explain", "up", 0.1],
    point_up: [[0.26, 0.3, 0.2], null, "finger", "fwd", 1], tired: [[0.2, -0.56, 0.07], [-0.2, -0.56, 0.07], "", "in", 0.45],
    walk: [[0.2, -0.5, 0.0], [-0.2, -0.5, 0.0], "walk", "in", 0.4], tray: [[0.15, -0.18, 0.32], [-0.15, -0.18, 0.32], "prop", "up", 0.4],
    give: [[0.2, -0.1, 0.5], null, "prop", "up", 0.4], take: [[0.18, -0.08, 0.46], null, "", "up", 0.3], hold_sofa: [[0.1, -0.27, 0.27], null, "prop", "in", 0.75],
  };
  const NEAR_PROPS = { hold: 1, read: 1, phone_look: 1, give: 1, newspaper: 1, tray: 1, hold_sofa: 1, take: 1 };

  // ------------------------------------------------------------------ characters
  function makeHand(skin, side, sleeveCol) {
    const hand = new T.Group();
    const palm = mesh(jitter(new T.BoxGeometry(0.072, 0.08, 0.03, 1, 1, 1), 0.004), M(skin)); palm.position.y = 0.02; hand.add(palm);
    const fingers = [];
    for (let k = 0; k < 4; k++) {
      const pv = new T.Group(); pv.position.set((k - 1.5) * 0.0175, 0.058, 0); hand.add(pv);
      const len = [0.05, 0.058, 0.055, 0.044][k];
      const f1 = box(0.016, len * 0.55, 0.018, skin, 0, len * 0.27, 0, pv);
      const pv2 = new T.Group(); pv2.position.y = len * 0.55; pv.add(pv2);
      box(0.015, len * 0.5, 0.017, skin, 0, len * 0.24, 0, pv2);
      fingers.push({ pv, pv2 });
    }
    const tp = new T.Group(); tp.position.set(side * 0.034, 0.012, 0.012); tp.rotation.z = -side * 0.7; hand.add(tp);
    box(0.018, 0.045, 0.019, skin, 0, 0.02, 0, tp);
    return { hand, fingers, thumb: tp };
  }

  function makeChar(w, d) {
    const sc = d.scale * (d.toddler ? 1.06 : 1), hs = d.toddler ? 1.38 : 1.0;
    const root = new T.Group(); const body = new T.Group(); root.add(body);
    const skin = d.skin, shirt = d.shirt, pants = d.pants;
    const c = { w, d, root, body, sc, hs, curProp: null, dyn: null };
    const tod = d.toddler, female = d.hair === "dupatta" || d.hair === "plaits";
    const L = tod ? { hip: 0.62, thigh: 0.27, shin: 0.27, torso: 0.4, sh: 0.15, ua: 0.19, fa: 0.18, hr: 0.2 }
      : { hip: 0.86, thigh: 0.41, shin: 0.4, torso: 0.48, sh: 0.18, ua: 0.27, fa: 0.25, hr: 0.165 };
    c.L = L;
    const torsoG = new T.Group(); body.add(torsoG); c.torso = torsoG;
    // shaped torso (lathe): hip -> waist -> chest -> shoulder -> neck base
    const tw = tod ? [[0.15, 0], [0.165, 0.12], [0.16, 0.26], [0.15, 0.36], [0.07, 0.42]]
      : female ? [[0.165, 0], [0.14, 0.15], [0.158, 0.31], [0.16, 0.43], [0.07, 0.5]]
        : [[0.155, 0], [0.145, 0.15], [0.17, 0.32], [0.18, 0.44], [0.07, 0.5]];
    const tor = lathe(tw, 8, shirt, torsoG); tor.scale.set(1.12, L.torso / (tod ? 0.42 : 0.5), 0.72);
    if (!female) [-1, 1].forEach(s => { const dl = ico(0.048, shirt, 1, s * L.sh * 0.96, L.torso - 0.055, 0, torsoG); dl.scale.set(1, 0.8, 0.85); });
    if (d.kameez) {
      const sk = lathe([[0.17, 0.02], [0.18, -0.1], [0.205, -0.3], [0.235, -0.5]], 9, shirt, torsoG, { side: T.DoubleSide }); sk.scale.set(1.08, 1, 0.8); c.skirt = sk;
      // seated: drape over the thighs + front fall from the knees
      const lap = new T.Group(); torsoG.add(lap); c.lap = lap; lap.visible = false;
      const lp = mesh(new T.CylinderGeometry(0.2, 0.21, 0.5, 8, 1, true), M(shirt, { side: T.DoubleSide })); lp.rotation.x = Math.PI / 2; lp.scale.set(0.95, 1, 0.42); lp.position.set(0, 0.06, 0.22); lap.add(lp);
      
      const fall = box(0.4, 0.22, 0.03, shirt, 0, -0.06, 0.46, lap); fall.rotation.x = 0.12; c.fall = fall;
      const nk = mesh(new T.TorusGeometry(0.055, 0.008, 3, 10, Math.PI), M(d.cover2 || shirt.map(v => v * 0.75))); nk.position.set(0, L.torso - 0.03, L.sh * 0.6); nk.rotation.set(-0.35, 0, Math.PI); torsoG.add(nk);
      // buttons / embroidery strip
      for (let k = 0; k < 3; k++) ico(0.009, d.cover2 || shirt.map(v => v * 0.7), 0, 0, L.torso - 0.1 - k * 0.045, L.sh * 0.76, torsoG);
    } else {
      const wb = lathe([[0.165, -0.02], [0.165, 0.05]], 8, pants, torsoG); wb.scale.set(1.1, 1, 0.75);
      if (d.shirt2) {
        const st = mesh(new T.CylinderGeometry(L.sh * 0.95, L.sh * 0.93, 0.05, 8, 1, true), M(d.shirt2)); st.scale.set(1.13, 1, 0.75); st.position.y = L.torso * 0.62; torsoG.add(st);
        const bd = mesh(new T.TorusGeometry(0.032, 0.009, 4, 10), M(d.shirt2)); bd.position.set(0.0, L.torso * 0.42, L.sh * 0.76); torsoG.add(bd);
        const col = mesh(new T.TorusGeometry(0.065, 0.012, 4, 10), M(d.shirt2)); col.position.set(0, L.torso - 0.01, 0.0); col.rotation.x = Math.PI / 2 - 0.25; torsoG.add(col);
      }
    }
    // neck + head
    cyl(0.048 * (tod ? 0.9 : 1), 0.056, 0.12, 6, skin, 0, L.torso + 0.04, 0, torsoG);
    const headG = new T.Group(); headG.position.y = L.torso + (tod ? 0.06 : 0.07); torsoG.add(headG); c.head = headG;
    const hr = L.hr * hs; c.hr = hr;
    const head = mesh(jitter(new T.IcosahedronGeometry(hr, 1), 0.005), M(skin)); head.scale.set(0.95, 1.05, 0.95); head.position.y = hr * 0.98; headG.add(head);
    const jaw = ico(hr * 0.62, skin, 1, 0, hr * 0.48, hr * 0.28, headG); jaw.scale.set(1.15, 0.7, 1); // fuller cheeks/jaw
    const face = new T.Group(); face.position.set(0, hr * 0.95, 0); headG.add(face); c.face = face;
    [-1, 1].forEach(s => { const e = ico(hr * 0.2, skin, 0, s * hr * 0.92, 0, -0.01, face); e.scale.set(0.5, 1, 0.8); });
    // eyes: white, iris, pupil, highlight, upper lid (closes), lower lid (rises when smiling)
    c.eyes = [-1, 1].map(s => {
      const eg = new T.Group(); eg.position.set(s * hr * 0.36, hr * 0.06, hr * 0.84); face.add(eg);
      const wht = ico(hr * 0.2, [252, 252, 250], 1, 0, 0, 0, eg); wht.scale.set(1, 1.15, 0.45); wht.castShadow = false;
      const iris = ico(hr * 0.13, [92, 58, 38], 1, 0, 0, hr * 0.055, eg); iris.scale.set(1, 1.1, 0.45); iris.castShadow = false;
      const pup = ico(hr * 0.075, [20, 12, 10], 1, 0, 0, hr * 0.075, eg); pup.scale.set(1, 1.1, 0.4); pup.castShadow = false;
      const hl = mesh(new T.IcosahedronGeometry(hr * 0.04, 0), new T.MeshBasicMaterial({ color: 0xc8c8c8 }), false, false); hl.position.set(hr * 0.045, hr * 0.06, hr * 0.105); eg.add(hl);
      const lidU = new T.Group(); eg.add(lidU);
      const lu = mesh(new T.SphereGeometry(hr * 0.215, 8, 4, 0, Math.PI * 2, 0, Math.PI / 2), M(skin), false, false); lu.scale.set(1.05, 1.2, 0.55); lidU.add(lu);
      const lash = box(hr * 0.45, hr * (d.lashes ? 0.045 : 0.03), hr * 0.04, [35, 22, 20], 0, 0, hr * 0.1, lidU); lash.castShadow = false;
      const lidD = new T.Group(); eg.add(lidD);
      const ld = mesh(new T.SphereGeometry(hr * 0.215, 8, 4, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), M(skin), false, false); ld.scale.set(1.05, 1.2, 0.55); lidD.add(ld);
      return { eg, iris, pup, hl, lidU, lidD, s };
    });
    c.brows = [-1, 1].map(s => { const b = box(hr * 0.44, hr * 0.075, hr * 0.06, d.hair_col || [30, 20, 20], s * hr * 0.37, hr * 0.33, hr * 0.84, face); b.castShadow = false; return b; });
    const nose = mesh(new T.ConeGeometry(hr * 0.12, hr * 0.26, 4), M(skin.map(v => v * 0.93))); nose.rotation.x = Math.PI / 2 + 0.3; nose.position.set(0, -hr * 0.12, hr * 0.98); face.add(nose); c.nose = nose; c.noseMat = nose.material;
    c.cheeks = [-1, 1].map(s => { const ch = mesh(new T.IcosahedronGeometry(hr * 0.15, 0), new T.MeshLambertMaterial({ color: 0xf08c8c, transparent: true, opacity: 0.5 }), false, false); ch.position.set(s * hr * 0.55, -hr * 0.22, hr * 0.76); ch.scale.set(1, 0.6, 0.3); face.add(ch); return ch; });
    // mouth: lips ring + inner + teeth + tongue + closed smile arc
    const mg = new T.Group(); mg.position.set(0, -hr * 0.42, hr * 0.87); face.add(mg); c.mouth = mg;
    const lipCol = female ? [196, 92, 100] : tod ? [214, 120, 120] : skin.map(v => v * 0.72);
    c.inner = ico(hr * 0.16, [70, 18, 28], 1, 0, 0, -hr * 0.01, mg); c.inner.castShadow = false;
    c.lips = mesh(new T.TorusGeometry(hr * 0.165, hr * 0.038, 4, 12), M(lipCol), false, false); mg.add(c.lips);
    c.teeth = box(hr * 0.24, hr * 0.06, hr * 0.03, [250, 250, 245], 0, hr * 0.07, hr * 0.03, mg); c.teeth.castShadow = false;
    c.teethL = box(hr * 0.2, hr * 0.045, hr * 0.03, [240, 240, 235], 0, -hr * 0.08, hr * 0.02, mg); c.teethL.castShadow = false;
    c.tongue = ico(hr * 0.08, [210, 90, 100], 0, 0, -hr * 0.05, hr * 0.03, mg); c.tongue.scale.z = 0.4; c.tongue.castShadow = false;
    c.smile = mesh(new T.TorusGeometry(hr * 0.2, hr * 0.036, 3, 8, Math.PI), M(female ? [170, 60, 70] : [120, 45, 45]), false, false); mg.add(c.smile);
    c.puffs = [0, 1, 2, 3, 4, 5].map(() => { const p = mesh(new T.IcosahedronGeometry(hr * 0.12, 0), new T.MeshLambertMaterial({ color: 0xf4fbff, transparent: true, opacity: 0.8, flatShading: true }), false, false); p.visible = false; face.add(p); return p; });
    // hair / cover
    const hc = d.hair_col || [30, 20, 20];
    c.swing = []; // spring-driven pieces: {o, ax, k}
    if (d.hair === "spiky") {
      const cap = mesh(new T.SphereGeometry(hr * 1.04, 9, 5, 0, Math.PI * 2, 0, Math.PI * 0.44), M(hc)); cap.position.y = hr * 1.0; cap.rotation.x = -0.22; headG.add(cap);
      for (let k = 0; k < 11; k++) {
        const a = (k / 11) * Math.PI * 2, r = k % 2 ? 0.5 : 0.25;
        const sp = mesh(new T.ConeGeometry(hr * 0.2, hr * 0.6, 4), M(hc));
        sp.position.set(Math.cos(a) * hr * r, hr * 1.8 + (k % 3) * 0.006, Math.sin(a) * hr * r - hr * 0.1);
        sp.rotation.set(Math.sin(a) * 0.55 - 0.25, 0, -Math.cos(a) * 0.55); headG.add(sp);
      }
      [-0.3, 0.05, 0.35].forEach((x, k) => { const fr = mesh(new T.ConeGeometry(hr * 0.2, hr * 0.5, 4), M(hc)); fr.position.set(x * hr, hr * 1.6, hr * 0.62); fr.rotation.set(1.0, 0, x * 0.6); headG.add(fr); });
      [-1, 1].forEach(s => { const sb = box(hr * 0.12, hr * 0.38, hr * 0.3, hc, s * hr * 0.9, hr * 1.12, hr * 0.15, headG); });
    } else if (d.hair === "plaits") {
      const cap = mesh(new T.SphereGeometry(hr * 1.06, 9, 6, 0, Math.PI * 2, 0, Math.PI * 0.55), M(hc)); cap.position.y = hr * 0.98; cap.rotation.x = -0.35; headG.add(cap);
      const bang = mesh(jitter(new T.BoxGeometry(hr * 1.4, hr * 0.3, hr * 0.32, 3, 1, 1), 0.008), M(hc)); bang.position.set(0, hr * 1.62, hr * 0.72); bang.rotation.x = 0.45; headG.add(bang);
      [-1, 1].forEach(s => {
        const pv = new T.Group(); pv.position.set(s * hr * 0.82, hr * 0.85, hr * 0.12); headG.add(pv);
        let prev = pv;
        for (let k = 0; k < 6; k++) {
          const seg = new T.Group(); seg.position.y = k ? -hr * 0.3 : 0; prev.add(seg);
          const b = mesh(new T.OctahedronGeometry(hr * (0.19 - k * 0.012), 0), M(hc)); b.scale.set(1, 1.25, 0.9); b.rotation.y = (k % 2) * 0.6; b.position.y = -hr * 0.15; seg.add(b);
          c.swing.push({ o: seg, k: 0.5 + k * 0.15, kind: "plait", s });
          prev = seg;
        }
        const bow = ico(hr * 0.11, [255, 90, 150], 0, 0, -hr * 0.3, 0, prev);
      });
      ico(hr * 0.12, [255, 120, 170], 0, hr * 0.62, hr * 1.66, hr * 0.5, headG);
    } else if (d.hair === "tuft") {
      const cap = mesh(new T.SphereGeometry(hr * 1.03, 8, 5, 0, Math.PI * 2, 0, Math.PI * 0.36), M(hc)); cap.position.y = hr * 0.98; headG.add(cap);
      const tf = mesh(new T.ConeGeometry(hr * 0.17, hr * 0.42, 4), M(hc)); tf.position.set(0.0, hr * 2.06, 0.02); tf.rotation.z = 0.45; headG.add(tf);
      c.swing.push({ o: tf, k: 0.6, kind: "tuft", base: 0.45 });
    } else if (d.hair === "dupatta") {
      const hl = mesh(new T.SphereGeometry(hr * 1.02, 10, 5, -Math.PI * 0.32, Math.PI * 0.64, Math.PI * 0.12, Math.PI * 0.2), M(hc)); hl.position.y = hr * 0.98; headG.add(hl); // hair visible at the forehead
      const cv = mesh(new T.SphereGeometry(hr * 1.14, 10, 6, 0, Math.PI * 2, 0, Math.PI * 0.58), M(d.cover, { side: T.DoubleSide }));
      cv.position.set(0, hr * 0.96, -hr * 0.16); cv.rotation.x = -0.86; headG.add(cv);
      const border = mesh(new T.TorusGeometry(hr * 0.98, hr * 0.05, 3, 16, Math.PI * 1.1), M(d.cover2)); border.position.set(0, hr * 1.18, hr * 0.32); border.rotation.set(-0.86 - 0.1, 0, -Math.PI * 0.05); headG.add(border);
      // back drape hangs from the head/shoulders (spring)
      const bp = new T.Group(); bp.position.set(0, L.torso + 0.02, -L.sh * 0.72); torsoG.add(bp);
      const back = box(0.4, 0.66, 0.035, d.cover, 0, -0.33, 0, bp); box(0.4, 0.04, 0.04, d.cover2, 0, -0.66, 0, bp);
      c.swing.push({ o: bp, k: 0.6, kind: "back", base: 0.12 });
      [-1, 1].forEach(s => {
        const sp = new T.Group(); sp.position.set(s * L.sh * 1.08, L.torso + 0.0, -0.04); torsoG.add(sp);
        box(0.07, 0.52, 0.1, d.cover, 0, -0.26, 0, sp); box(0.075, 0.04, 0.105, d.cover2, 0, -0.52, 0, sp);
        c.swing.push({ o: sp, k: 0.8, kind: "side", s, base: s * 0.1 });
      });
      [-1, 1].forEach(s => { const v = box(0.085, 0.34, 0.03, d.cover, s * 0.085, L.torso - 0.13, L.sh * 0.75, torsoG); v.rotation.z = -s * 0.5; v.rotation.x = -0.1; const vb = box(0.02, 0.34, 0.035, d.cover2, s * 0.13, L.torso - 0.13, L.sh * 0.755, torsoG); vb.rotation.z = -s * 0.5; vb.rotation.x = -0.1; });
    }
    if (d.earrings) [-1, 1].forEach(s => { ico(hr * 0.06, [240, 200, 60], 0, s * hr * 0.9, -hr * 0.28, 0.0, face); ico(hr * 0.045, [240, 200, 60], 0, s * hr * 0.9, -hr * 0.4, 0.0, face); });
    // arms
    c.arms = [-1, 1].map(s => {
      const longS = d.kameez;
      const ua = mesh(new T.CylinderGeometry(0.05, 0.044, 1, 7), M(shirt)); body.add(ua);
      const fa = mesh(new T.CylinderGeometry(0.043, longS ? 0.05 : 0.034, 1, 7), M(longS ? shirt : skin)); body.add(fa);
      let sleeveEnd = null;
      if (!longS) { sleeveEnd = mesh(new T.CylinderGeometry(0.055, 0.058, 1, 7), M(shirt)); body.add(sleeveEnd); }
      const wrist = mesh(new T.CylinderGeometry(0.028, 0.03, 1, 6), M(skin)); body.add(wrist);
      const H = makeHand(skin, s, shirt); body.add(H.hand);
      const elb = ico(0.045, longS ? shirt : skin, 1, 0, 0, 0, body);
      return Object.assign({ s, ua, fa, sleeveEnd, wrist, elb }, H);
    });
    // legs
    c.legs = [-1, 1].map(s => {
      const lw = d.kameez ? 0.088 : 0.07;
      const th = mesh(new T.CylinderGeometry(lw, lw * 0.92, 1, 7), M(pants)); body.add(th);
      const sh = mesh(new T.CylinderGeometry(lw * 0.92, d.kameez ? lw * 0.6 : lw * 0.8, 1, 7), M(pants)); body.add(sh);
      const kn = ico(lw * 0.86, pants, 1, 0, 0, 0, body);
      const footC = d.toddler ? [245, 245, 245] : (d.kameez ? [120, 70, 45] : [245, 245, 245]);
      const ft = new T.Group(); body.add(ft);
      const sole = mesh(jitter(new T.BoxGeometry(0.09, 0.055, 0.21, 1, 1, 2), 0.004), M(footC)); sole.position.set(0, -0.03, 0.05); ft.add(sole);
      if (!d.kameez) { box(0.095, 0.02, 0.215, [200, 60, 60], 0, -0.06, 0.05, ft); box(0.06, 0.01, 0.08, [200, 60, 60], 0, -0.002, 0.1, ft); }
      if (d.kameez) { ico(0.035, skin, 0, 0, 0.0, 0.02, ft); box(0.07, 0.012, 0.04, [180, 120, 60], 0, -0.005, 0.09, ft); }
      return { s, th, sh, kn, ft };
    });
    c.blob = aoBlob(root, 0, 0.05, 0.75, 0.6, 0.65, 0.014);
    root.scale.setScalar(sc);
    root.traverse(o => { if (o.isMesh && o.castShadow !== false && !(o.material && o.material.transparent)) { o.castShadow = true; o.receiveShadow = true; } });
    c.eyes.forEach(e => e.eg.traverse(o => { o.castShadow = false; }));
    scene.add(root);
    return c;
  }

  function ik(S, Tg, L1, L2, pole) {
    const d = new T.Vector3().subVectors(Tg, S); let len = d.length();
    const maxL = (L1 + L2) * 0.995; if (len > maxL) { d.setLength(maxL); len = maxL; }
    if (len < 0.05) { d.setLength(0.05); len = 0.05; }
    const dir = d.clone().normalize();
    const a = (L1 * L1 - L2 * L2 + len * len) / (2 * len); const h = Math.sqrt(Math.max(L1 * L1 - a * a, 0));
    const pp = pole.clone().sub(dir.clone().multiplyScalar(pole.dot(dir))).normalize();
    return [S.clone().addScaledVector(dir, a).addScaledVector(pp, h), S.clone().add(d)];
  }

  function poseTargets(name, face, seated) {
    const p = P3[name] || P3[seated ? "rest_sofa" : "rest_stand"];
    const rest = P3[seated ? "rest_sofa" : "rest_stand"];
    let n = p[0] || rest[0], f = p[1] || rest[1];
    const fix = (v) => { v = v.slice(); if (seated && v[1] < -0.36) { v[1] = -0.4; v[2] = Math.max(v[2], 0.28); } return v; };
    n = fix(n); f = fix(f);
    return { n: V(n[0] * face, n[1], n[2]), f: V(f[0] * face, f[1], f[2]), flags: p[2], palm: p[3], curl: p[4], fp: p[1] ? p[3] : rest[3], fc: p[1] ? p[4] : rest[4] };
  }

  const PALM = { in: (s) => V(-s, 0, 0.25), down: () => V(0, -1, 0.1), up: () => V(0, 1, 0.2), fwd: () => V(0, 0, 1), back: () => V(0, 0, -1) };
  function orientHand(ar, E, Hh, palmDir, curl, pointIdx) {
    const dir = new T.Vector3().subVectors(Hh, E).normalize();
    const q = new T.Quaternion().setFromUnitVectors(UP, dir);
    const cur = V(0, 0, 1).applyQuaternion(q);
    const want = palmDir.clone().normalize();
    const pc = cur.clone().sub(dir.clone().multiplyScalar(cur.dot(dir))), pw = want.clone().sub(dir.clone().multiplyScalar(want.dot(dir)));
    if (pc.lengthSq() > 1e-4 && pw.lengthSq() > 1e-4) { const q2 = new T.Quaternion().setFromUnitVectors(pc.normalize(), pw.normalize()); q.premultiply(q2); }
    ar.hand.quaternion.copy(q); ar.hand.position.copy(Hh);
    ar.fingers.forEach((f, k) => { const cu = (pointIdx && k === (ar.s > 0 ? 3 : 0)) ? 0 : curl; f.pv.rotation.x = cu * 1.35; f.pv2.rotation.x = cu * 1.5; f.pv.rotation.z = (k - 1.5) * 0.06 * (1 - cu); });
    ar.thumb.rotation.x = curl * 0.8;
  }

  function spring(sp, force, k = 70, damp = 8) { const a = -k * sp.x - damp * sp.v + force; sp.v += a * DT; sp.x = clamp(sp.x + sp.v * DT, -1.2, 1.2); }

  function updateChar(c, s, t, slotInfo, fi, wind) {
    const L = c.L;
    const seat = slotInfo.seatY || 0.46;
    let stand = s.st;
    const sl = s.sl || 0;
    const walking = s.m === "walk";
    const transit = (s.m === "sit" || s.m === "rise") ? Math.sin(Math.PI * clamp(stand, 0, 1)) : 0; // mid sit/stand
    // ---- hips
    let hipY = lerp(seat, L.hip, stand) - (walking ? 0.025 : 0);
    let hop = 0;
    const cur = s.pose, prv = s.prev; const gu = gesture((t - s.tc) / 0.36);
    if (P3[cur] && P3[cur][2] && P3[cur][2].includes("jump") && t - s.tc < 0.9) hop = Math.abs(Math.sin((t - s.tc) * 9)) * 0.05 * (stand > 0.5 ? 1 : 0.4);
    const sway = (!walking && stand > 0.9 && sl === 0) ? Math.sin(t * 0.8 + c.w.length) : 0; // idle weight shift
    c.body.position.set(sway * 0.012, hipY + hop, 0);
    const br = Math.sin(t * 2.1 + c.w.length) * 0.007;
    c.torso.scale.set(1, 1 + br, 1);
    // ---- legs (planted walk cycle via IK)
    const A = 0.17;
    c.legs.forEach((lg, k) => {
      const sx = lg.s * 0.1 * (c.d.toddler ? 0.8 : 1);
      const hip = V(sx, -0.02, 0);
      let an, pole = V(0, 0, 1);
      if (walking) {
        let ph = (s.phase || 0) + (k ? Math.PI : 0); ph = ((ph % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
        let fz, lift;
        if (ph < Math.PI) { fz = A * (1 - 2 * ph / Math.PI); lift = 0; } else { const u = (ph - Math.PI) / Math.PI; fz = -A + 2 * A * ease(u); lift = 0.09 * Math.sin(Math.PI * u); }
        an = V(sx, -(hipY - 0.07) + lift, fz);
      } else an = V(sx * (1 + sway * 0.0), -(hipY - 0.07), 0.0);
      const aSit = V(sx * 1.1, -(hipY - 0.07), L.thigh * 1.08);
      if (!walking) an.lerp(aSit, 1 - stand);
      let kn;
      if (sl > 0) { const lieK = V(sx, -L.thigh, 0), lieA = V(sx, -L.thigh - L.shin, 0); const [k2, a2] = ik(hip, an, L.thigh, L.shin, pole); kn = k2.lerp(lieK, sl); an = a2.lerp(lieA, sl); }
      else { const r = ik(hip, an, L.thigh, L.shin, pole); kn = r[0]; an = r[1]; }
      place(lg.th, hip, kn); place(lg.sh, kn, an); lg.kn.position.copy(kn);
      lg.ft.position.copy(an); lg.ft.rotation.set(walking && an.y > -(hipY - 0.07) + 0.02 ? 0.25 : 0, 0, 0);
      if (sl > 0) lg.ft.rotation.x = -sl * 1.4;
    });
    if (c.skirt) {
      const seated = stand < 0.5 && sl < 0.5;
      c.skirt.visible = !seated; c.lap.visible = seated;
    }
    // ---- emotion
    const e = EMO[s.emo] || EMO.calm;
    const vo = s.vo || 0, vw = s.vw || 0, vf = s.vf || 0;
    const speaking = vo > 0.05 || (s.q || 0) > 0;
    // ---- body facing + lean
    let look = s.lx || 0;
    let total = look * 0.6;
    const tgt = s.lk && CHARS[s.lk] && CHARS[s.lk] !== c && CHARS[s.lk].root.visible ? CHARS[s.lk] : null;
    if (tgt) { const a = tgt.root.position, b = c.root.position; total = clamp(Math.atan2(a.x - b.x, a.z - b.z + 0.6) * 0.92, -1.25, 1.25); look = clamp(total / 0.6, -1, 1); }
    else if (s.lk === "front") total = 0;
    // smooth turning (no snapping between targets)
    if (c.dyn && c.dyn.fi === fi - 1 && c.turn !== undefined) c.turn = lerp(c.turn, total, 0.25); else c.turn = total;
    let yaw = c.turn * 0.5;
    if (walking && s.dir !== undefined) yaw = s.dir;
    if (sl > 0) yaw = lerp(yaw, 0, sl);
    c.root.rotation.y = yaw;
    c.torso.rotation.set((s.emo === "tired" ? 0.08 : 0) + transit * 0.42 + (walking ? 0.05 : 0), 0, -sway * 0.015);
    // ---- head
    const yawHead = walking ? clamp(look * 0.3, -0.4, 0.4) : clamp(c.turn - yaw, -0.75, 0.75), pitch = (s.ly || 0) * 0.15 - (s.emo === "proud" ? 0.1 : 0);
    let hx = pitch + (s.nod || 0) * 0.15 - (s.emo === "laugh" ? 0.05 + Math.abs(Math.sin(t * 15)) * 0.05 : 0) - transit * 0.25;
    if (speaking) hx += Math.sin(t * 4.3 + c.w.length) * 0.025 + vo * 0.04; // talking head motion
    c.head.rotation.set(hx, yawHead + Math.sin(t * 0.7 + c.w.length) * 0.02, -(s.ang || 0) * Math.PI / 180 * 0.9);
    // sneeze
    const sn = (D.fx && D.fx.sneeze || []).find(z => z.who === c.w && t >= z.t - 0.45 && t < z.t + 0.7);
    c.sneezeU = 0; let forceClose = false;
    if (sn) {
      const k = t - sn.t;
      const p = k < 0 ? -0.28 * Math.sin((k + 0.45) / 0.45 * Math.PI / 2) : 0.5 * Math.exp(-k * 5) * (k < 0.08 ? k / 0.08 : 1);
      c.head.rotation.x += p; c.torso.rotation.x += p * 0.4; c.sneezeU = k >= 0 ? Math.max(0, 1 - k / 0.7) : 0;
      if (k < 0.15) forceClose = true;
    }
    const sick = (D.fx && D.fx.sick || []).some(z => z.who === c.w && t >= z.t0 && t < z.t1);
    c.nose.material = sick ? M([226, 92, 92]) : c.noseMat;
    // ---- eyes
    const bl = s.bl || 0;
    let open = e[2] * (bl === 2 ? 0.05 : bl === 1 ? 0.45 : 1);
    if (sl > 0.4 || forceClose) open = 0.04;
    if (sick && open > 0.7) open = 0.7;
    const cheekUp = e[6] * (s.emo === "laugh" ? 1 : 0.7);
    c.eyes.forEach((ey) => {
      ey.eg.scale.set(s.emo === "surprised" ? 1.12 : 1, s.emo === "surprised" ? 1.12 : 1, 1);
      const o = clamp(open, 0, 1.4);
      ey.lidU.rotation.x = lerp(1.25, -1.5, clamp(o, 0, 1)); // upper lid sweeps down over the eye to close
      ey.lidD.rotation.x = lerp(1.55, 0.95, cheekUp); // lower lid rises when smiling
      ey.iris.position.x = look * c.hr * 0.06; ey.iris.position.y = -(s.ly || 0) * c.hr * 0.045;
      ey.pup.position.x = ey.iris.position.x; ey.pup.position.y = ey.iris.position.y; ey.hl.position.x = ey.iris.position.x + c.hr * 0.045;
      const hide = open < 0.15; ey.iris.visible = ey.pup.visible = ey.hl.visible = !hide;
    });
    // brows (emphasis lift on loud syllables)
    c.brows.forEach((b, k) => {
      const sd = k ? 1 : -1;
      let ang = e[0] * sd, raise = e[1];
      if (e[5] === 1 && sd > 0) { raise += 0.016; ang -= 0.25 * sd; }
      if (e[5] === 2) { raise += sd > 0 ? 0.02 : -0.004; }
      if (speaking && s.emo !== "angry") raise += vo * 0.008 + 0.003 * Math.sin(t * 7);
      if (sick) { ang += 0.2 * sd; }
      b.rotation.z = ang; b.position.y = c.hr * 0.33 + raise * (c.hr / 0.165);
    });
    c.cheeks.forEach(ch => { ch.position.y = -c.hr * (0.22 - cheekUp * 0.06); ch.scale.set(s.emo === "chew" ? 1.6 : 1, s.emo === "chew" ? 1.2 : 0.6, s.emo === "chew" ? 0.9 : 0.3); ch.material.opacity = sick ? 0.75 : 0.5; });
    // ---- mouth (visemes)
    let open2 = Math.max(vo, (s.q || 0) / 6);
    if (e[4] && !speaking) open2 = Math.max(open2, s.emo === "laugh" ? 0.55 + 0.25 * Math.sin(t * 14) : e[4]);
    if (s.emo === "laugh" && speaking) open2 = Math.max(open2, 0.35);
    const round = clamp(-vw, 0, 1), wide = clamp(vw, 0, 1);
    const smileW = e[3] > 0.5 ? 0.2 : 0;
    if (open2 > 0.07 || vf > 0.35) {
      c.inner.visible = true; c.lips.visible = true; c.smile.visible = false;
      const sx = (1.0 + wide * 0.4 + smileW - round * 0.42) * (s.emo === "surprised" && !speaking ? 0.7 : 1);
      const sy = Math.max(0.12, open2 * 1.05 + (vf > 0.35 ? 0.12 : 0)) * (1 - round * 0.1);
      c.inner.scale.set(sx, sy, 0.3); c.lips.scale.set(sx, Math.max(sy, 0.25), 0.6);
      c.mouth.position.z = c.hr * (0.87 + round * 0.06);
      c.teeth.visible = open2 > 0.18 || vf > 0.35; c.teeth.position.y = c.hr * (0.03 + sy * 0.09); c.teeth.scale.x = sx * 0.9;
      c.teethL.visible = vf > 0.35 && open2 < 0.4; c.teethL.position.y = c.hr * (-0.02 - sy * 0.05);
      c.tongue.visible = open2 > 0.5; c.tongue.position.y = -c.hr * (0.02 + sy * 0.08);
    } else {
      c.inner.visible = false; c.teeth.visible = false; c.teethL.visible = false; c.tongue.visible = false;
      c.mouth.position.z = c.hr * 0.87;
      if (speaking) { c.lips.visible = true; c.smile.visible = false; c.lips.scale.set(0.9, 0.18, 0.6); } // mm / pressed lips between words
      else {
        c.lips.visible = false; c.smile.visible = true;
        const sm = e[3];
        c.smile.rotation.z = sm >= 0 ? Math.PI : 0;
        c.smile.scale.set(0.6 + Math.abs(sm) * 0.5, 0.35 + Math.abs(sm) * 0.55, 1);
        c.smile.position.y = sm >= 0 ? c.hr * 0.06 : -c.hr * 0.06;
        if (e[5] === 1) c.smile.rotation.z += 0.25;
        if (s.emo === "chew") c.smile.scale.set(0.4, 0.25, 1);
      }
    }
    c.puffs.forEach((p, k) => { p.visible = c.sneezeU > 0.02; if (p.visible) { const u = 1 - c.sneezeU; const a = (k - 2.5) * 0.35; p.position.set(Math.sin(a) * u * c.hr * 1.6, -c.hr * 0.35 + Math.cos(k * 1.7) * u * c.hr * 0.5, c.hr * (1.0 + u * 2.2)); p.scale.setScalar(0.5 + u * 1.4); p.material.opacity = 0.75 * c.sneezeU; } });
    // ---- arms
    const seated = stand < 0.5;
    const Acur = poseTargets(cur, s.face, seated), B = poseTargets(prv, s.face, seated);
    const shY = L.torso + br * 0.5;
    const flags = Acur.flags || "";
    const tn = B.n.clone().lerp(Acur.n, gu), tf = B.f.clone().lerp(Acur.f, gu);
    if (flags.includes("wave")) tn.x += Math.sin(t * 11) * 0.05 * s.face;
    if (flags.includes("wag")) tn.x += Math.sin(t * 13) * 0.035;
    if (flags.includes("scratch")) { tn.x += Math.sin(t * 16) * 0.02; tn.y += Math.cos(t * 16) * 0.012; }
    if (flags.includes("clap")) { const k = Math.abs(Math.sin(t * 9)); tn.x = s.face * (0.02 + 0.07 * k); tf.x = -s.face * (0.02 + 0.07 * k); }
    if (flags.includes("explain")) { tn.y += Math.sin(t * 4) * 0.03; tf.y += Math.sin(t * 4 + 1) * 0.025; }
    if (walking) { const sw = Math.sin(s.phase || 0); tn.z += sw * 0.16 * s.face; tf.z -= sw * 0.16 * s.face; }
    if (speaking && !flags.includes("wave") && !flags.includes("clap") && cur !== "rest_stand" && cur !== "rest_sofa") { tn.y += Math.sin(t * 5.5) * 0.012 + vo * 0.02; }
    if (transit > 0) { const kn = V(0.1, -0.36, 0.34); tn.lerp(V(kn.x * s.face, kn.y, kn.z), transit * 0.8); tf.lerp(V(-kn.x * s.face, kn.y, kn.z), transit * 0.8); }
    c.torso.position.y = flags.includes("shrug") ? 0.025 * clamp(gu, 0, 1) : 0;
    c.arms.forEach(ar => {
      const isNear = ar.s === s.face;
      const T0 = (isNear ? tn : tf).clone().add(V(0, shY, 0));
      // arms live in body space; follow the torso lean
      if (c.torso.rotation.x) T0.applyAxisAngle(V(1, 0, 0), c.torso.rotation.x * 0.8);
      const S = V(ar.s * L.sh * 1.02, shY - 0.04, 0).applyAxisAngle(V(1, 0, 0), c.torso.rotation.x);
      S.y += c.torso.position.y;
      if (Math.abs(T0.x) < 0.15 && T0.z < 0.17 && T0.y < shY && T0.y > 0) T0.z = 0.19;
      const elbowsOut = flags.includes("elbows");
      const pole = elbowsOut ? V(ar.s, 0.0, -0.4) : V(ar.s * 0.45, -1, -0.55);
      const [E, Hh] = ik(S, T0, L.ua, L.fa, pole.normalize());
      place(ar.ua, S, E); ar.elb.position.copy(E);
      const wr = E.clone().lerp(Hh, 0.86);
      if (ar.sleeveEnd) { place(ar.fa, E, Hh); const mid = S.clone().lerp(E, 0.55); place(ar.sleeveEnd, mid, E.clone().lerp(S, -0.02)); }
      else place(ar.fa, E, wr);
      place(ar.wrist, wr, Hh);
      const pd = isNear ? Acur.palm : Acur.fp; const cu = isNear ? Acur.curl : Acur.fc;
      const fingerOn = (isNear && flags.includes("finger")) || (!isNear && flags.includes("farfinger"));
      const holding = c.propObj && c.propArm === ar;
      orientHand(ar, E, Hh, (PALM[pd] || PALM.in)(ar.s), holding ? 0.8 : cu, fingerOn && gu > 0.4);
      ar.isNear = isNear;
    });
    // ---- prop
    const pname = s.prop || null;
    if (pname !== c.curProp) {
      if (c.propObj) { c.propObj.parent.remove(c.propObj); c.propObj = null; }
      if (pname) c.propObj = makeProp(pname);
      c.curProp = pname;
    }
    if (c.propObj) {
      const inNear = !!NEAR_PROPS[cur];
      const arm = c.arms.find(a => a.isNear === inNear) || c.arms[0];
      c.propArm = arm;
      if (c.propObj.parent !== arm.hand) arm.hand.add(c.propObj);
      c.propObj.position.set(0, 0.03, 0.02);
      const q = new T.Quaternion(); arm.hand.updateWorldMatrix(true, false); arm.hand.getWorldQuaternion(q); const inv = q.invert();
      const wq = new T.Quaternion(); c.root.getWorldQuaternion(wq);
      if (pname === "bat") { wq.multiply(new T.Quaternion().setFromEuler(new T.Euler(0.12 + (c.dyn ? c.dyn.sx.x * 0.4 : 0), 0, s.face * -0.1))); c.propObj.position.set(0, 0.0, 0.02); }
      c.propObj.quaternion.copy(inv.multiply(wq));
      if (pname === "cup") c.propObj.userData.steam.forEach((p, k) => { const u = ((t * 0.6 + k / 4) % 1); p.position.set(Math.sin(t * 3 + k) * 0.014, 0.11 + u * 0.18, 0.035); p.material.opacity = 0.5 * (1 - u); p.scale.setScalar(0.6 + u); });
    }
    // ---- secondary motion: springs driven by body acceleration, head turns, wind
    const wp = new T.Vector3(); c.torso.getWorldPosition(wp);
    if (!c.dyn || c.dyn.fi !== fi - 1 || c.dyn.p.distanceTo(wp) > 0.4) c.dyn = { fi, p: wp.clone(), v: V(0, 0, 0), hy: c.head.rotation.y, sx: { x: 0, v: 0 }, sz: { x: 0, v: 0 } };
    const dy = c.dyn;
    const v = wp.clone().sub(dy.p).multiplyScalar(30); const a = v.clone().sub(dy.v).multiplyScalar(30);
    const ry = -c.root.rotation.y; const al = a.clone().applyAxisAngle(UP, ry);
    const hv = (c.head.rotation.y - dy.hy) * 30;
    const gust = wind ? wind * (0.6 + 0.4 * Math.sin(t * 2.3 + c.w.length)) : 0;
    spring(dy.sx, -al.z * 0.9 + gust * 6 + (walking ? 2.5 : 0) + c.torso.rotation.x * 6, 60, 7);
    spring(dy.sz, -al.x * 0.9 - hv * 2.2 + gust * 2 * Math.sin(t * 1.3), 60, 7);
    dy.p.copy(wp); dy.v.copy(v); dy.hy = c.head.rotation.y; dy.fi = fi;
    c.swing.forEach(sw => {
      if (sw.kind === "plait") { sw.o.rotation.x = -dy.sx.x * 0.35 * sw.k - c.torso.rotation.x * 0.3 * sw.k - c.head.rotation.x * 0.2; sw.o.rotation.z = dy.sz.x * 0.3 * sw.k; }
      else if (sw.kind === "back") { sw.o.rotation.x = sw.base + Math.max(-0.05, dy.sx.x) * 0.35 - c.torso.rotation.x * 0.5; sw.o.rotation.z = dy.sz.x * 0.12; }
      else if (sw.kind === "side") { sw.o.rotation.x = -dy.sx.x * 0.15 - c.torso.rotation.x * 0.6; sw.o.rotation.z = sw.base + dy.sz.x * 0.12; }
      else if (sw.kind === "tuft") { sw.o.rotation.z = sw.base + dy.sz.x * 0.4; }
    });
    if (c.skirt && c.skirt.visible) c.skirt.rotation.set(dy.sx.x * 0.06 + (walking ? Math.sin(s.phase || 0) * 0.03 : 0), 0, dy.sz.x * 0.04);
    c.root.visible = (s.al === undefined ? 1 : s.al) > 0.02;
    c.blob.visible = sl < 0.3; c.blob.position.z = lerp(0.3, 0.05, stand); c.blob.material.opacity = lerp(0.45, 0.65, stand);
  }

  // ------------------------------------------------------------------ sets
  function addCeilingFan(p, x, y, z, col = [90, 70, 60]) {
    const g = new T.Group(); g.position.set(x, y, z); p.add(g);
    cyl(0.02, 0.02, 0.8, 5, [70, 70, 70], 0, 0.4, 0, g);
    cyl(0.12, 0.1, 0.12, 8, [200, 200, 205], 0, 0, 0, g);
    const bl = new T.Group(); g.add(bl);
    for (let k = 0; k < 3; k++) { const b = box(0.7, 0.012, 0.13, col, 0.42, -0.02, 0); const h = new T.Group(); h.rotation.y = k * 2.094; h.add(b); bl.add(h); }
    return bl;
  }
  function glow(p, x, y, z, r, col, op = 0.5) {
    const tex = canvasTex(128, 128, (c) => { const g = c.createRadialGradient(64, 64, 4, 64, 64, 64); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.3, "rgba(255,255,255,0.45)"); g.addColorStop(1, "rgba(255,255,255,0)"); c.fillStyle = g; c.fillRect(0, 0, 128, 128); });
    const s = new T.Sprite(new T.SpriteMaterial({ map: tex, color: C(col), transparent: true, opacity: op, depthWrite: false, blending: T.AdditiveBlending })); s.position.set(x, y, z); s.scale.setScalar(r); p.add(s); return s;
  }
  let AO_R = null, AO_L = null;
  function aoTex() {
    if (!AO_R) {
      AO_R = canvasTex(128, 128, (c) => { const g = c.createRadialGradient(64, 64, 2, 64, 64, 64); g.addColorStop(0, "rgba(0,0,0,0.75)"); g.addColorStop(0.45, "rgba(0,0,0,0.42)"); g.addColorStop(1, "rgba(0,0,0,0)"); c.fillStyle = g; c.fillRect(0, 0, 128, 128); });
      AO_L = canvasTex(16, 128, (c) => { const g = c.createLinearGradient(0, 0, 0, 128); g.addColorStop(0, "rgba(0,0,0,0.5)"); g.addColorStop(0.35, "rgba(0,0,0,0.18)"); g.addColorStop(1, "rgba(0,0,0,0)"); c.fillStyle = g; c.fillRect(0, 0, 16, 128); });
    }
  }
  function aoBlob(p, x, z, w, d, op = 0.7, y = 0.016) { aoTex(); const o = new T.Mesh(new T.PlaneGeometry(w, d), new T.MeshBasicMaterial({ map: AO_R, transparent: true, opacity: op, depthWrite: false, fog: false })); o.rotation.x = -Math.PI / 2; o.position.set(x, y, z); o.renderOrder = 1; p.add(o); return o; }
  function aoStrip(p, x, z, w, d, ry = 0, op = 0.8, vertical = false) { // gradient from a wall edge outwards
    aoTex(); const o = new T.Mesh(new T.PlaneGeometry(w, d), new T.MeshBasicMaterial({ map: AO_L, transparent: true, opacity: op, depthWrite: false, fog: false }));
    if (vertical) { o.position.set(x, d / 2, z); o.rotation.set(0, ry, Math.PI); } else { o.rotation.set(-Math.PI / 2, 0, ry); o.position.set(x, 0.015, z); }
    o.renderOrder = 1; p.add(o); return o;
  }
  function chappals(p, x, z, col, ry = 0) { const g = new T.Group(); g.position.set(x, 0, z); g.rotation.y = ry; p.add(g); [-1, 1].forEach(s => { box(0.09, 0.02, 0.24, col, s * 0.06, 0.01, 0, g); box(0.07, 0.025, 0.02, [80, 50, 30], s * 0.06, 0.025, 0.05, g); }); return g; }

  function buildAangan(time) {
    const g = new T.Group();
    const ev = time === "evening";
    gradientSky(ev ? [64, 72, 150] : [90, 160, 230], ev ? [236, 140, 120] : [170, 210, 240], ev ? [255, 200, 120] : [230, 240, 245], g);
    const sun = new T.Mesh(new T.CircleGeometry(1.1, 12), new T.MeshBasicMaterial({ color: ev ? 0xffd27a : 0xfff2b0, fog: false })); sun.position.set(-3.6, 3.2, -15.5); g.add(sun);
    glow(g, -3.6, 3.2, -15.4, 7, ev ? [255, 170, 90] : [255, 255, 220], 0.55);
    // distant rooftops with water tanks, a minaret-free skyline, kites
    const roofCols = ev ? [[180, 128, 140], [160, 118, 140], [196, 144, 140], [150, 110, 135]] : [[230, 215, 190], [210, 195, 175], [240, 225, 200]];
    for (let k = 0; k < 16; k++) {
      const w = 1.3 + hash(k, 1, 2) * 1.6, h = 2.2 + hash(k, 3, 1) * 2.4, x = -10 + k * 1.4, z = -7 - hash(k, 2, 2) * 2.5;
      box(w, h, 1.5, roofCols[k % roofCols.length], x, h / 2, z, g);
      box(w + 0.1, 0.12, 1.6, roofCols[(k + 1) % roofCols.length].map(v => v * 0.9), x, h + 0.06, z, g);
      if (k % 3 === 0) cyl(0.3, 0.3, 0.5, 7, ev ? [70, 70, 90] : [60, 60, 70], x + 0.2, h + 0.37, z, g);
      if (k % 4 === 1) { for (let j = 0; j < 2; j++) { const wn = box(0.22, 0.26, 0.02, ev ? [255, 214, 140] : [120, 160, 190], x - 0.3 + j * 0.6, h * 0.75, z + 0.76, g); if (ev) wn.material = new T.MeshBasicMaterial({ color: 0xb8925a }); } }
    }
    const kites = [];
    [[-1.5, 4.6, -10, [240, 80, 80]], [2.5, 5.2, -11, [80, 160, 240]]].forEach(([x, y, z, col]) => { const k = mesh(new T.OctahedronGeometry(0.28, 0), M(col), false, false); k.scale.set(1, 1.2, 0.08); k.position.set(x, y, z); g.add(k); kites.push(k); });
    const clouds = [];
    for (let k = 0; k < 6; k++) {
      const cg = new T.Group(); cg.position.set(-9 + k * 3.6, 4.2 + hash(k, 4, 4) * 2.2, -13); g.add(cg);
      for (let j = 0; j < 4; j++) { const cl = mesh(jitter(new T.IcosahedronGeometry(0.55 + j % 2 * 0.25, 0), 0.15), new T.MeshBasicMaterial({ color: ev ? 0xffc8b0 : 0xffffff, fog: false }), false, false); cl.position.set(j * 0.55, (j % 2) * 0.2, 0); cg.add(cl); }
      clouds.push(cg);
    }
    // birds
    const birds = [];
    for (let k = 0; k < 4; k++) { const b = new T.Group(); [-1, 1].forEach(s => { const wgs = box(0.16, 0.012, 0.05, [50, 40, 50], s * 0.08, 0, 0, b); wgs.rotation.z = s * 0.3; b.userData[s] = wgs; }); g.add(b); birds.push(b); }
    // ground: packed earth + brick paving
    const gr = mesh(jitter(new T.PlaneGeometry(16, 12, 30, 24), 0.035), M([214, 182, 136])); gr.rotation.x = -Math.PI / 2; gr.position.set(0, 0, -1); g.add(gr);
    const tiles = [];
    for (let i = -7; i <= 7; i++) for (let j = -5; j <= 3; j++) { const h = hash(i, j, 3); tiles.push([i * 0.36 + (j % 2) * 0.18, 0.01, j * 0.36 + 0.1, h > 0.66 ? [196, 120, 90] : h > 0.33 ? [184, 108, 80] : [206, 132, 98]]); }
    instBoxes(tiles, 0.34, 0.02, 0.34, g);
    // low back wall (sky shows above) + plaster coping
    const WZ = -2.6, WH = 2.05;
    box(11, WH, 0.3, [190, 110, 80], 0, WH / 2, WZ - 0.02, g);
    const br = [];
    for (let r = 0; r < 13; r++) for (let k = 0; k < 38; k++) {
      const x = -5.5 + k * 0.3 + (r % 2) * 0.15, y = 0.08 + r * 0.15;
      if (x > 0.75 && x < 2.15) continue;
      const sh = hash(r, k, 1);
      br.push([x, y, WZ + 0.14, sh > 0.7 ? [176, 90, 64] : sh > 0.35 ? [200, 112, 80] : [214, 130, 94]]);
    }
    instBoxes(br, 0.28, 0.13, 0.05, g);
    box(11.2, 0.12, 0.42, [236, 226, 206], 0, WH + 0.06, WZ, g);
    box(0.3, WH, 6.5, [196, 116, 84], -5.0, WH / 2, 0.2, g);
    // gate between two pillars
    const gate = new T.Group(); gate.position.set(1.45, 0, WZ + 0.05); g.add(gate);
    [-1, 1].forEach(s => { box(0.34, 2.55, 0.42, [236, 226, 206], s * 0.9, 1.27, 0, gate); box(0.42, 0.12, 0.5, [210, 190, 160], s * 0.9, 2.6, 0, gate); ico(0.1, [210, 190, 160], 0, s * 0.9, 2.72, 0, gate); });
    const doorL = new T.Group(); doorL.position.set(-0.73, 0, 0.04); gate.add(doorL);
    const doorR = new T.Group(); doorR.position.set(0.73, 0, 0.04); gate.add(doorR);
    [[doorL, 1], [doorR, -1]].forEach(([d, s]) => { box(0.72, 2.15, 0.05, [56, 136, 84], s * 0.36, 1.1, 0, d); for (let k = 0; k < 5; k++) box(0.022, 0.95, 0.07, [36, 96, 58], s * (0.08 + k * 0.13), 1.55, 0.01, d); box(0.68, 0.05, 0.07, [36, 96, 58], s * 0.36, 1.05, 0.01, d); box(0.68, 0.05, 0.07, [36, 96, 58], s * 0.36, 2.05, 0.01, d); });
    // neem tree
    const tree = new T.Group(); tree.position.set(-2.7, 0, -1.8); g.add(tree);
    const trunk = mesh(jitter(new T.CylinderGeometry(0.15, 0.26, 2.4, 7, 3), 0.05), M([110, 80, 55])); trunk.position.y = 1.2; tree.add(trunk);
    const br1 = cyl(0.08, 0.12, 1.3, 6, [110, 80, 55], 0.4, 2.6, 0.1, tree); br1.rotation.z = -0.6;
    const br2 = cyl(0.07, 0.1, 1.1, 6, [110, 80, 55], -0.35, 2.5, -0.1, tree); br2.rotation.z = 0.6;
    const crown = new T.Group(); crown.position.y = 3.0; tree.add(crown);
    const greens = [[86, 150, 70], [70, 132, 60], [104, 166, 80], [60, 120, 56]];
    [[0, 0.3, 0, 1.2], [1.0, 0.0, 0.2, 0.9], [-0.9, -0.1, 0.1, 0.9], [0.4, 0.9, -0.2, 0.85], [-0.4, 0.8, 0.3, 0.8], [1.6, -0.4, 0.5, 0.7], [0.2, -0.3, 0.7, 0.75]].forEach((p, k) => {
      const f = mesh(jitter(new T.IcosahedronGeometry(p[3], 1), 0.25), M(greens[k % 4])); f.position.set(p[0], p[1], p[2]); crown.add(f);
    });
    for (let k = 0; k < 10; k++) { const lf = mesh(new T.TetrahedronGeometry(0.06, 0), M([150, 140, 70]), false, true); lf.position.set(-2.7 + (hash(k, 1, 1) - 0.5) * 2.5, 0.02, -1.8 + (hash(k, 2, 1) - 0.5) * 1.5); lf.rotation.set(1.5, k, 0); lf.scale.y = 0.2; g.add(lf); }
    // charpai with ajrak + hand fan
    const ch = new T.Group(); ch.position.set(0, 0, -0.42); g.add(ch);
    const wood = [150, 96, 56];
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz]) => { lathe([[0.04, 0], [0.05, 0.08], [0.035, 0.15], [0.055, 0.25], [0.04, 0.36], [0.045, 0.42]], 7, [120, 70, 40], ch).position.set(sx * 1.0, 0, sz * 0.42); ico(0.055, [196, 64, 60], 0, sx * 1.0, 0.25, sz * 0.42, ch); });
    box(2.12, 0.07, 0.07, wood, 0, 0.43, -0.44, ch); box(2.12, 0.07, 0.07, wood, 0, 0.43, 0.44, ch);
    box(0.07, 0.07, 0.95, wood, -1.03, 0.43, 0, ch); box(0.07, 0.07, 0.95, wood, 1.03, 0.43, 0, ch);
    const weave = [];
    for (let i = 0; i < 26; i++) weave.push([-0.96 + i * 0.077, 0.445, 0, (i % 6 < 3) ? [235, 225, 200] : [200, 70, 70]]);
    instBoxes(weave, 0.05, 0.02, 0.86, ch);
    const weave2 = [];
    for (let j = 0; j < 11; j++) weave2.push([0, 0.455, -0.4 + j * 0.08, j % 4 < 2 ? [240, 232, 210] : [230, 180, 70]]);
    instBoxes(weave2, 1.98, 0.012, 0.035, ch);
    const aj = texBox(0.42, 0.07, 0.75, ajrakTex(4), [158, 27, 38], 1.25, 0.49, 0.18, g); aj.rotation.y = 0.15; // folded ajrak at the charpai end
    const pankha = new T.Group(); pankha.position.set(-0.95, 0.47, 0.25); pankha.rotation.set(-Math.PI / 2, 0, 0.6); g.add(pankha);
    box(0.24, 0.2, 0.012, [230, 180, 70], 0, 0.1, 0, pankha); box(0.03, 0.18, 0.02, [140, 90, 50], 0, -0.08, 0, pankha); box(0.2, 0.03, 0.014, [200, 60, 60], 0, 0.18, 0, pankha);
    chappals(g, 0.55, 0.32, [120, 70, 45], 0.2);
    // clothesline between a pole and the gate pillar
    const lineY = 1.82, lz = -2.0;
    cyl(0.04, 0.05, 1.9, 6, [90, 80, 70], -3.6, 0.95, lz, g);
    const ln = mesh(new T.CylinderGeometry(0.006, 0.006, 1, 4), M([240, 240, 240])); place(ln, V(-3.6, lineY, lz), V(0.55, lineY + 0.05, WZ + 0.3)); g.add(ln);
    const clothes = [];
    [[-3.1, [220, 70, 70], "shirt"], [-2.45, [245, 245, 240], "shirt"], [-1.8, [80, 130, 200], "shirt"], [-1.15, [250, 170, 60], "dupatta"], [-0.45, [40, 120, 70], "sweater"]].forEach(([x, col, kind], k) => {
      const u = (x + 3.6) / 4.15; const y = lerp(lineY, lineY + 0.05, u) - 0.02, z = lerp(lz, WZ + 0.3, u);
      const piv = new T.Group(); piv.position.set(x, y, z); g.add(piv);
      if (kind === "shirt" || kind === "sweater") { box(0.42, 0.5, 0.02, col, 0, -0.27, 0, piv); box(0.66, 0.14, 0.02, col, 0, -0.08, 0, piv); if (kind === "sweater") for (let j = 0; j < 3; j++) box(0.42, 0.025, 0.025, [240, 240, 240], 0, -0.2 - j * 0.12, 0, piv); }
      else { box(0.32, 0.85, 0.015, col, 0, -0.43, 0, piv); box(0.32, 0.04, 0.02, [200, 60, 90], 0, -0.84, 0, piv); }
      ico(0.02, [240, 200, 60], 0, 0, 0.0, 0.01, piv);
      clothes.push(piv);
    });
    // water matka on stand, tap + bucket, potted plants, wall bulb
    const mk = new T.Group(); mk.position.set(3.0, 0, -2.1); g.add(mk);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => cyl(0.02, 0.02, 0.6, 4, [80, 80, 80], a * 0.18, 0.3, b * 0.18, mk));
    box(0.45, 0.03, 0.45, [80, 80, 80], 0, 0.6, 0, mk);
    lathe([[0.0, 0], [0.2, 0.05], [0.3, 0.25], [0.26, 0.45], [0.13, 0.55], [0.15, 0.62]], 10, [186, 96, 60], mk).position.y = 0.62;
    box(0.24, 0.02, 0.24, [130, 130, 140], 0, 1.25, 0, mk);
    const bucket = lathe([[0.13, 0], [0.16, 0.25]], 9, [60, 120, 200], g, { side: T.DoubleSide }); bucket.position.set(2.3, 0, -2.25);
    cyl(0.02, 0.02, 0.6, 5, [150, 150, 160], 2.3, 0.6, WZ + 0.15, g); box(0.12, 0.03, 0.03, [150, 150, 160], 2.3, 0.6, WZ + 0.22, g);
    [[-4.0, -2.1, [80, 150, 70]], [3.9, -0.6, [100, 160, 80]], [-4.2, 0.6, [70, 140, 70]]].forEach(([x, z, col]) => {
      lathe([[0.15, 0], [0.22, 0.25], [0.2, 0.4], [0.23, 0.42]], 8, [196, 106, 66], g).position.set(x, 0, z);
      for (let j = 0; j < 5; j++) { const lf = mesh(jitter(new T.IcosahedronGeometry(0.22, 0), 0.06), M(col)); lf.position.set(x + Math.sin(j * 1.6) * 0.15, 0.55 + j * 0.09, z + Math.cos(j * 1.6) * 0.12); g.add(lf); }
    });
    const bulb = new T.Mesh(new T.IcosahedronGeometry(0.07, 1), new T.MeshBasicMaterial({ color: 0xfff1b0 })); bulb.position.set(0.3, 1.75, WZ + 0.2); g.add(bulb);
    box(0.02, 0.15, 0.02, [60, 60, 60], 0.3, 1.86, WZ + 0.2, g);
    if (ev) { const pl = new T.PointLight(0xffc880, 1.1, 5, 1.6); pl.position.set(0.3, 1.6, WZ + 0.6); g.add(pl); glow(g, 0.3, 1.75, WZ + 0.25, 0.7, [255, 210, 140], 0.5); }
    const leaves = [];
    for (let k = 0; k < 30; k++) { const lf = mesh(new T.TetrahedronGeometry(0.04, 0), M(k % 3 ? [110, 160, 70] : [190, 170, 80]), false, false); g.add(lf); leaves.push({ o: lf, s: hash(k, 7, 3), y: 0.3 + hash(k, 1, 9) * 2.4, z: -2 + hash(k, 5, 5) * 4 }); }
    aoStrip(g, 0, WZ + 0.45, 11, 0.6, 0, 0.55); aoStrip(g, -4.55, 0.2, 6.5, 0.6, Math.PI / 2, 0.5);
    aoBlob(g, 0, -0.42, 2.6, 1.3, 0.75); aoBlob(g, 3.0, -2.1, 0.8, 0.8, 0.6); aoBlob(g, -2.7, -1.8, 1.6, 1.2, 0.5); aoBlob(g, 2.3, -2.25, 0.5, 0.5, 0.5);
    lightRig(g, ev ? { sky: [170, 160, 230], ground: [200, 150, 110], hemi: 0.85, sun: [255, 186, 125], sunI: 2.1, sunPos: [-6, 5, 4], fill: [255, 220, 200], fillI: 0.3, rim: [255, 170, 110], rimI: 1.4, rim2: [170, 170, 255] }
      : { sky: [200, 225, 255], ground: [220, 190, 150], hemi: 1.0, sun: [255, 245, 220], sunI: 2.2, sunPos: [-4, 8, 5] });
    const anim = (t, wind) => {
      crown.rotation.z = Math.sin(t * 1.3) * 0.02 * (1 + wind) + wind * 0.02; crown.rotation.x = Math.sin(t * 0.9) * 0.012 * (1 + wind);
      clothes.forEach((c, k) => { c.rotation.x = -0.15 * wind - (0.12 + 0.25 * wind) * Math.abs(Math.sin(t * (2.2 + k * 0.3) + k)); c.rotation.z = Math.sin(t * 1.7 + k) * 0.06 * (1 + wind); });
      clouds.forEach((c, k) => { c.position.x = -10 + ((k * 3.6 + t * 0.15) % 22); });
      kites.forEach((k, j) => { k.position.y += Math.sin(t * 1.5 + j) * 0.003; k.rotation.z = Math.sin(t * 2 + j) * 0.25; });
      birds.forEach((b, k) => { const u = ((t * 0.05 + k * 0.07) % 1); b.position.set(-8 + u * 16, 4.5 + k * 0.3 + Math.sin(t + k) * 0.2, -9 - k); const f = Math.sin(t * 10 + k) * 0.5; b.userData[-1].rotation.z = -0.3 - f; b.userData[1].rotation.z = 0.3 + f; });
      leaves.forEach((l, k) => { const sp = 0.6 + l.s * 0.8 + wind * 1.6; const x = -5 + ((l.s * 10 + t * sp) % 10); l.o.position.set(x, l.y + Math.sin(t * 2 + k) * 0.25, l.z); l.o.rotation.set(t * 3 + k, t * 2, t * 4); });
    };
    const slots = { charpai_l: { x: -0.48, z: -0.25, seatY: 0.47 }, charpai_c: { x: 0, z: -0.25, seatY: 0.47 }, charpai_r: { x: 0.48, z: -0.25, seatY: 0.47 },
      stand_l: { x: -1.4, z: 0.75 }, stand_r: { x: 1.25, z: 0.55 }, stand_c: { x: 0.0, z: 0.95 }, floor_l: { x: -0.8, z: 1.1 }, floor_r: { x: 0.8, z: 1.1 } };
    return { g, slots, door: { x: 1.45, z: WZ + 0.3 }, anim, fog: new T.Fog(ev ? 0xe8a888 : 0xdfe9f0, 16, 34), gate: [doorL, doorR], windy: true, bg: ev ? 0xe8a888 : 0xdfe9f0,
      grade: ev ? { gain: [1.06, 0.98, 0.9], lift: [0.025, 0.0, 0.04], sat: 1.12, vig: 0.38 } : { gain: [1, 1, 1], lift: [0, 0, 0], sat: 1.05, vig: 0.3 } };
  }

  function buildBedroom() {
    const g = new T.Group();
    const WZ = -1.75;
    const tl = [];
    for (let i = -6; i <= 6; i++) for (let j = -3; j <= 6; j++) tl.push([i * 0.5, -0.01, WZ + 0.25 + j * 0.5, (i + j) % 2 ? [226, 220, 208] : [212, 206, 194]]);
    instBoxes(tl, 0.49, 0.02, 0.49, g);
    box(7, 5.0, 0.12, [178, 208, 232], 0, 2.5, WZ - 0.06, g);
    box(0.12, 5.0, 5.5, [168, 198, 224], -2.6, 2.5, WZ + 2.7, g);
    box(7, 0.14, 0.04, [150, 180, 210], 0, 0.07, WZ + 0.02, g);
    box(7, 0.08, 0.05, [250, 250, 250], 0, 2.9, WZ + 0.0, g);
    const fan = addCeilingFan(g, 0.3, 3.0, -0.6);
    // window
    const win = new T.Group(); win.position.set(-1.05, 1.75, WZ + 0.02); g.add(win);
    const sky = canvasTex(256, 256, (x, w, h) => { const gr = x.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#6fb6f0"); gr.addColorStop(1, "#d6eefc"); x.fillStyle = gr; x.fillRect(0, 0, w, h); x.fillStyle = "#ffe27a"; x.beginPath(); x.arc(190, 70, 34, 0, 7); x.fill(); x.fillStyle = "#fff"; [[60, 120], [95, 112], [130, 124]].forEach(([a, b]) => { x.beginPath(); x.arc(a, b, 24, 0, 7); x.fill(); }); x.fillStyle = "#c9a27a"; x.fillRect(0, 200, w, 56); x.fillStyle = "#b08a66"; x.fillRect(30, 180, 60, 76); x.fillRect(150, 170, 80, 86); });
    const pane = new T.Mesh(new T.PlaneGeometry(1.0, 1.1), new T.MeshBasicMaterial({ map: sky })); pane.position.z = 0.02; win.add(pane);
    box(1.12, 0.08, 0.1, [250, 250, 250], 0, 0.59, 0.03, win); box(1.12, 0.1, 0.16, [250, 250, 250], 0, -0.59, 0.05, win);
    box(0.08, 1.2, 0.1, [250, 250, 250], -0.56, 0, 0.03, win); box(0.08, 1.2, 0.1, [250, 250, 250], 0.56, 0, 0.03, win); box(0.05, 1.1, 0.06, [250, 250, 250], 0, 0, 0.04, win);
    for (let k = -2; k <= 2; k++) box(0.015, 1.1, 0.02, [90, 90, 100], k * 0.2, 0, 0.06, win);
    [-1, 1].forEach(s => { box(0.28, 1.45, 0.05, [240, 170, 70], s * 0.72, -0.05, 0.12, win); for (let k = 0; k < 3; k++) box(0.04, 1.45, 0.07, [220, 140, 50], s * 0.72 + (k - 1) * 0.08, -0.05, 0.13, win); });
    box(1.8, 0.04, 0.04, [140, 100, 70], 0, 0.78, 0.16, win);
    glow(g, -1.05, 1.75, WZ + 0.2, 2.4, [255, 250, 230], 0.35);
    // sunbeam on the floor
    const beam = new T.Mesh(new T.PlaneGeometry(1.0, 1.4), new T.MeshBasicMaterial({ color: 0xfff6d8, transparent: true, opacity: 0.18, depthWrite: false })); beam.rotation.x = -Math.PI / 2; beam.position.set(-0.6, 0.012, WZ + 1.6); beam.rotation.z = 0.3; g.add(beam);
    const poster = canvasTex(200, 280, (x, w, h) => { x.fillStyle = "#1f7a45"; x.fillRect(0, 0, w, h); x.save(); x.translate(100, 140); x.rotate(-0.6); x.fillStyle = "#e9c98a"; x.fillRect(-14, -100, 28, 150); x.fillStyle = "#6b4a30"; x.fillRect(-5, 50, 10, 50); x.restore(); x.fillStyle = "#d63a3a"; x.beginPath(); x.arc(150, 70, 18, 0, 7); x.fill(); x.fillStyle = "#fff"; x.font = "bold 30px sans-serif"; x.fillText("CRICKET", 30, 255); });
    framePic(0.62, 0.86, poster, 0.15, 1.85, WZ + 0.03, g, [240, 240, 240]);
    const cal = canvasTex(120, 160, (x, w, h) => { x.fillStyle = "#fff"; x.fillRect(0, 0, w, h); x.fillStyle = "#d63a3a"; x.fillRect(0, 0, w, 40); x.fillStyle = "#fff"; x.font = "bold 22px sans-serif"; x.fillText("NOV", 38, 28); x.fillStyle = "#555"; for (let i = 0; i < 5; i++) for (let j = 0; j < 4; j++) x.fillRect(10 + i * 21, 55 + j * 24, 14, 12); x.fillStyle = "#d63a3a"; x.fillRect(31, 79, 14, 12); });
    framePic(0.3, 0.4, cal, 1.6, 1.55, WZ + 0.03, g, [240, 240, 240]);
    // door + hook with school uniform
    const door = new T.Group(); door.position.set(0.95, 0, WZ + 0.03); g.add(door);
    box(1.0, 2.25, 0.06, [235, 230, 220], 0, 1.12, 0, door);
    const dp = new T.Group(); dp.position.set(-0.45, 0, 0.04); door.add(dp);
    box(0.9, 2.12, 0.05, [150, 96, 60], 0.45, 1.07, 0, dp);
    [[0.45, 1.55], [0.45, 0.6]].forEach(([a, b]) => box(0.7, 0.75, 0.02, [170, 112, 70], a, b, 0.03, dp));
    ico(0.035, [230, 200, 80], 0, 0.82, 1.05, 0.06, dp);
    // bed with ajrak-pattern sheet, pillow, razai
    const bed = new T.Group(); bed.position.set(-1.6, 0, WZ + 0.95); g.add(bed);
    box(0.1, 1.15, 1.25, [130, 82, 50], -0.06, 0.58, 0, bed); box(0.14, 0.1, 1.3, [150, 96, 60], -0.06, 1.17, 0, bed);
    for (let k = 0; k < 3; k++) box(0.03, 0.5, 0.18, [150, 96, 60], -0.0, 0.75, -0.4 + k * 0.4, bed);
    box(2.0, 0.28, 1.2, [140, 90, 55], 1.0, 0.22, 0, bed);
    [[0.0, -0.57], [0.0, 0.57], [1.97, -0.57], [1.97, 0.57]].forEach(([a, b]) => box(0.08, 0.12, 0.08, [110, 70, 40], a, 0.06, b, bed));
    const sheetT = ajrakTex(8, false), sideT = ajrakTex(3, true);
    const sheet = new T.Mesh(new T.BoxGeometry(1.95, 0.16, 1.22), [M([230, 225, 215]), M([230, 225, 215]), new T.MeshLambertMaterial({ map: sheetT }), M([230, 225, 215]), new T.MeshLambertMaterial({ map: sideT }), M([230, 225, 215])]);
    sheet.position.set(1.0, 0.43, 0); sheet.castShadow = true; sheet.receiveShadow = true; bed.add(sheet);
    const pil = mesh(jitter(new T.BoxGeometry(0.38, 0.13, 0.7, 2, 1, 2), 0.02), M([250, 248, 240])); pil.position.set(0.25, 0.58, 0); bed.add(pil);
    const rzT = canvasTex(256, 256, (x, w, h) => { x.fillStyle = "#b03048"; x.fillRect(0, 0, w, h); x.strokeStyle = "#e8b446"; x.lineWidth = 18; x.strokeRect(9, 9, w - 18, h - 18); x.fillStyle = "#faecd2"; for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) { const cx = 35 + i * 47, cy = 35 + j * 47; for (let k = 0; k < 5; k++) { x.beginPath(); x.arc(cx + 7 * Math.cos(k * 1.256), cy + 7 * Math.sin(k * 1.256), 5, 0, 7); x.fill(); } } });
    const rz = mesh(jitter(new T.BoxGeometry(1.35, 0.2, 1.05, 4, 1, 3), 0.03), new T.MeshLambertMaterial({ map: rzT, flatShading: true })); bed.add(rz);
    // bedside stool with a glass of water + tissue box (he is "sick")
    const stool = new T.Group(); stool.position.set(-0.05, 0, WZ + 0.35); g.add(stool);
    cyl(0.2, 0.2, 0.04, 8, [150, 96, 60], 0, 0.5, 0, stool); [0, 1, 2].forEach(k => { const l = cyl(0.02, 0.025, 0.5, 5, [120, 76, 46], Math.cos(k * 2.09) * 0.14, 0.25, Math.sin(k * 2.09) * 0.14, stool); });
    const gl = mesh(new T.CylinderGeometry(0.035, 0.03, 0.11, 8), new T.MeshLambertMaterial({ color: 0xcfe9ff, transparent: true, opacity: 0.7 }), false); gl.position.set(-0.06, 0.575, 0); stool.add(gl);
    box(0.14, 0.08, 0.1, [120, 180, 230], 0.08, 0.56, 0.02, stool); box(0.04, 0.03, 0.02, [255, 255, 255], 0.08, 0.61, 0.02, stool);
    // almari (steel cupboard) on the left wall
    const alm = new T.Group(); alm.position.set(-2.3, 0, WZ + 2.25); alm.rotation.y = Math.PI / 2; g.add(alm);
    box(0.9, 1.9, 0.5, [120, 150, 140], 0, 0.95, 0, alm); box(0.02, 1.8, 0.02, [80, 100, 95], 0, 0.95, 0.26, alm); [-1, 1].forEach(s => box(0.03, 0.18, 0.03, [220, 220, 210], s * 0.06, 1.0, 0.27, alm));
    // desk + computer + chair with the sweater he did NOT wear
    const desk = new T.Group(); desk.position.set(1.95, 0, WZ + 0.45); g.add(desk);
    box(1.2, 0.05, 0.6, [170, 120, 80], 0, 0.76, 0, desk);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.05, 0.76, 0.05, [140, 96, 60], a * 0.55, 0.38, b * 0.26, desk));
    box(0.55, 0.36, 0.04, [40, 40, 50], 0, 1.14, -0.12, desk);
    const scr = new T.Mesh(new T.PlaneGeometry(0.5, 0.31), new T.MeshBasicMaterial({ color: 0x58b4f0 })); scr.position.set(0, 1.14, -0.098); desk.add(scr);
    box(0.06, 0.15, 0.06, [40, 40, 50], 0, 0.86, -0.12, desk); box(0.4, 0.02, 0.14, [230, 230, 235], 0, 0.79, 0.1, desk);
    box(0.17, 0.22, 0.03, [200, 60, 60], -0.4, 0.89, -0.05, desk); box(0.17, 0.22, 0.03, [60, 160, 90], -0.37, 0.89, -0.02, desk);
    const chair = new T.Group(); chair.position.set(1.85, 0, WZ + 1.05); g.add(chair);
    box(0.45, 0.05, 0.45, [60, 90, 160], 0, 0.46, 0, chair); box(0.45, 0.5, 0.05, [60, 90, 160], 0, 0.74, 0.22, chair);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.03, 0.46, 0.03, [80, 80, 90], a * 0.2, 0.23, b * 0.2, chair));
    const sw = mesh(jitter(new T.BoxGeometry(0.5, 0.06, 0.4, 3, 1, 2), 0.02), M([40, 120, 70])); sw.position.set(0, 0.5, -0.02); chair.add(sw);
    box(0.5, 0.025, 0.03, [240, 240, 240], 0, 0.53, 0.05, chair); box(0.08, 0.35, 0.05, [40, 120, 70], 0.2, 0.32, -0.2, chair);
    // shelf + books, bat + ball, rug, slippers, school bag
    box(1.0, 0.04, 0.22, [150, 100, 65], 1.95, 2.05, WZ + 0.12, g);
    const books = []; const bc = [[200, 60, 60], [60, 120, 200], [240, 190, 60], [70, 160, 90], [160, 90, 170]];
    for (let k = 0; k < 9; k++) books.push([1.55 + k * 0.09, 2.2 - (k % 3) * 0.02, WZ + 0.12, bc[k % 5], 1, 1 - (k % 3) * 0.12, 1]);
    instBoxes(books, 0.07, 0.28, 0.18, g, true);
    ico(0.08, [230, 190, 60], 0, 2.35, 2.15, WZ + 0.12, g); // cricket trophy
    cyl(0.03, 0.05, 0.12, 6, [230, 190, 60], 2.35, 2.07, WZ + 0.12, g);
    const bat = makeProp("bat"); bat.position.set(2.55, 0.8, WZ + 0.2); bat.rotation.z = 0.25; g.add(bat);
    ico(0.035, [200, 40, 40], 1, 2.3, 0.035, WZ + 0.55, g);
    const bag = new T.Group(); bag.position.set(2.45, 0, WZ + 0.95); g.add(bag); box(0.32, 0.4, 0.16, [150, 80, 120], 0, 0.2, 0, bag); box(0.28, 0.18, 0.04, [130, 66, 104], 0, 0.14, 0.09, bag);
    const rug = new T.Mesh(new T.BoxGeometry(1.8, 0.015, 1.1), new T.MeshLambertMaterial({ map: sindhiTex("#2d5f8a", "#e8c35a", "#c94a4a", 6) })); rug.position.set(0.3, 0.008, 0.55); rug.receiveShadow = true; g.add(rug);
    chappals(g, -0.75, 0.3, [60, 60, 70], 0.1);
    aoStrip(g, 0, WZ + 0.3, 7, 0.55, 0, 0.6); aoStrip(g, -2.3, WZ + 2.7, 5.5, 0.55, Math.PI / 2, 0.55);
    aoStrip(g, 0, WZ + 0.02, 7, 0.5, 0, 0.35, true);
    aoBlob(g, -0.6, WZ + 0.95, 2.5, 1.6, 0.8); aoBlob(g, 1.95, WZ + 0.45, 1.5, 0.9, 0.6); aoBlob(g, 1.85, WZ + 1.05, 0.7, 0.7, 0.55);
    aoBlob(g, -2.25, WZ + 2.25, 0.9, 1.3, 0.6); aoBlob(g, -0.05, WZ + 0.35, 0.6, 0.6, 0.55);
    lightRig(g, { sky: [215, 230, 255], ground: [210, 200, 185], hemi: 1.0, sun: [255, 244, 215], sunI: 2.1, sunPos: [-3, 6, 6], fillI: 0.45, rim: [255, 245, 225], rimI: 1.0 });
    const wl = new T.PointLight(0xfff0d0, 1.3, 5, 1.6); wl.position.set(-1.05, 1.8, WZ + 0.6); g.add(wl);
    const anim = (t) => { fan.rotation.y = t * 5; };
    const slots = { bed: { x: -0.75, z: WZ + 0.95 + 0.45, seatY: 0.53, lieZ: WZ + 0.95 }, desk: { x: 1.85, z: WZ + 1.0, seatY: 0.48 },
      stand_l: { x: 0.35, z: 0.25 }, stand_r: { x: 1.15, z: 0.55 }, stand_c: { x: 0.35, z: 0.45 }, floor_l: { x: -0.6, z: 1.1 }, floor_r: { x: 0.9, z: 1.1 } };
    return { g, slots, door: { x: 0.95, z: WZ + 0.35 }, anim, fog: new T.Fog(0xe8eef4, 12, 30), razai: rz, bed, doorPanel: dp, bg: 0xe8eef4,
      grade: { gain: [0.98, 1.0, 1.04], lift: [0.0, 0.006, 0.02], sat: 1.06, vig: 0.3 } };
  }

  function buildLiving() {
    const g = new T.Group();
    const WZ = -1.6;
    const tl = [];
    for (let i = -6; i <= 6; i++) for (let j = -2; j <= 7; j++) tl.push([i * 0.6, -0.01, WZ + 0.3 + j * 0.6, (i + j) % 2 ? [236, 226, 206] : [224, 212, 190]]);
    instBoxes(tl, 0.59, 0.02, 0.59, g);
    box(7.5, 5.0, 0.12, [246, 228, 196], 0, 2.5, WZ - 0.06, g);
    box(0.12, 5.0, 6, [238, 218, 186], -2.8, 2.5, WZ + 3, g);
    box(0.12, 5.0, 6, [238, 218, 186], 2.8, 2.5, WZ + 3, g);
    box(7.5, 0.16, 0.04, [196, 150, 110], 0, 0.08, WZ + 0.02, g);
    box(7.5, 0.1, 0.05, [196, 150, 110], 0, 2.95, WZ + 0.0, g);
    // decorative wall band (Sindhi tile strip)
    const band = new T.Mesh(new T.PlaneGeometry(7.4, 0.18), new T.MeshLambertMaterial({ map: (() => { const t = sindhiTex("#1f6f8b", "#f2c14e", "#c0392b", 2); t.wrapS = T.RepeatWrapping; t.repeat.set(20, 1); return t; })() })); band.position.set(0, 2.75, WZ + 0.01); g.add(band);
    const fan = addCeilingFan(g, 0, 3.0, -0.4, [150, 110, 80]);
    const cT = canvasTex(512, 320, (x, w, h) => { x.fillStyle = "#a8242e"; x.fillRect(0, 0, w, h); x.strokeStyle = "#e9b949"; x.lineWidth = 16; x.strokeRect(14, 14, w - 28, h - 28); x.strokeStyle = "#1d2d5c"; x.lineWidth = 8; x.strokeRect(36, 36, w - 72, h - 72); x.fillStyle = "#e9b949"; for (let i = 0; i < 6; i++) for (let j = 0; j < 3; j++) { const cx = 90 + i * 66, cy = 90 + j * 70; x.beginPath(); x.moveTo(cx, cy - 22); x.lineTo(cx + 22, cy); x.lineTo(cx, cy + 22); x.lineTo(cx - 22, cy); x.fill(); x.fillStyle = "#1d2d5c"; x.fillRect(cx - 5, cy - 5, 10, 10); x.fillStyle = "#e9b949"; } });
    const carpet = new T.Mesh(new T.BoxGeometry(3.2, 0.015, 2.0), new T.MeshLambertMaterial({ map: cT })); carpet.position.set(0, 0.008, 0.85); carpet.receiveShadow = true; g.add(carpet);
    // sofa
    const sofa = new T.Group(); sofa.position.set(0, 0, WZ + 0.7); g.add(sofa);
    const maroon = [140, 40, 50], mar2 = [118, 30, 42];
    box(2.3, 0.3, 0.75, mar2, 0, 0.22, 0, sofa);
    [-0.7, 0, 0.7].forEach(x => { const cu = mesh(jitter(new T.BoxGeometry(0.68, 0.14, 0.68, 2, 1, 2), 0.015), M(maroon)); cu.position.set(x, 0.42, 0.04); sofa.add(cu); });
    const back = mesh(jitter(new T.BoxGeometry(2.3, 0.62, 0.2, 4, 2, 1), 0.012), M(maroon)); back.position.set(0, 0.68, -0.32); sofa.add(back);
    [-1, 1].forEach(s => { box(0.2, 0.36, 0.78, mar2, s * 1.2, 0.48, 0, sofa); const ar = cyl(0.11, 0.11, 0.78, 7, maroon, s * 1.2, 0.68, 0, sofa); ar.rotation.x = Math.PI / 2; });
    [0, 1, 2, 3].forEach(k => cyl(0.03, 0.02, 0.08, 5, [90, 60, 40], (k % 2 ? 1 : -1) * 1.1, 0.04, (k < 2 ? 1 : -1) * 0.3, sofa));
    const rl = rilliTex(4);
    [-0.75, 0.0, 0.75].forEach((x, k) => { const c = new T.Mesh(new T.BoxGeometry(0.42, 0.38, 0.1), [M([200, 60, 60]), M([200, 60, 60]), M([200, 60, 60]), M([200, 60, 60]), new T.MeshLambertMaterial({ map: rl }), M([200, 60, 60])]); c.position.set(x, 0.78, -0.17); c.rotation.x = -0.2; c.rotation.z = (k - 1) * 0.06; c.castShadow = true; sofa.add(c); });
    const ajb = texBox(0.5, 0.03, 0.7, ajrakTex(4), [158, 27, 38], -1.2, 0.81, 0.0, sofa); ajb.rotation.z = 0.08; // ajrak on the sofa arm
    // topi on the side table
    // coffee table with fruit + chai cups
    const tb = new T.Group(); tb.position.set(0.45, 0, 0.95); g.add(tb);
    box(0.9, 0.05, 0.5, [150, 96, 60], 0, 0.4, 0, tb); box(0.8, 0.03, 0.42, [130, 82, 50], 0, 0.12, 0, tb);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.05, 0.4, 0.05, [120, 76, 46], a * 0.4, 0.2, b * 0.2, tb));
    cyl(0.17, 0.12, 0.05, 9, [245, 245, 245], 0.1, 0.45, 0, tb);
    [[0.05, 0.02, [240, 150, 40]], [0.15, -0.03, [220, 50, 50]], [0.12, 0.07, [240, 150, 40]], [0.2, 0.04, [120, 190, 60]]].forEach(([a, b, col]) => ico(0.045, col, 1, a, 0.5, b, tb));
    [-0.25, -0.12].forEach((x, k) => { cyl(0.035, 0.028, 0.08, 8, [250, 250, 250], x, 0.465, 0.05 * k, tb); cyl(0.03, 0.03, 0.003, 8, [170, 100, 50], x, 0.505, 0.05 * k, tb); });
    // wall decor: clock, family photo, window, door, showcase with crockery, TV cabinet on the left wall
    const clk = canvasTex(128, 128, (x) => { x.fillStyle = "#fff"; x.beginPath(); x.arc(64, 64, 60, 0, 7); x.fill(); x.strokeStyle = "#333"; x.lineWidth = 6; x.stroke(); for (let k = 0; k < 12; k++) { x.fillStyle = "#333"; x.fillRect(64 + 48 * Math.cos(k * 0.5236) - 3, 64 + 48 * Math.sin(k * 0.5236) - 3, 6, 6); } x.lineWidth = 6; x.beginPath(); x.moveTo(64, 64); x.lineTo(64, 28); x.stroke(); x.lineWidth = 4; x.beginPath(); x.moveTo(64, 64); x.lineTo(92, 74); x.stroke(); });
    const ck = new T.Mesh(new T.CircleGeometry(0.22, 12), new T.MeshLambertMaterial({ map: clk })); ck.position.set(0.0, 2.35, WZ + 0.02); g.add(ck);
    cyl(0.24, 0.24, 0.03, 12, [150, 100, 60], 0, 2.35, WZ + 0.005, g).rotation.x = Math.PI / 2;
    const fam = canvasTex(256, 180, (x, w, h) => { x.fillStyle = "#cfe3ef"; x.fillRect(0, 0, w, h); const cols = ["#c0392b", "#2e8b57", "#e67e22", "#8e44ad", "#2c3e50"]; for (let k = 0; k < 5; k++) { const cx = 30 + k * 49; x.fillStyle = cols[k]; x.fillRect(cx - 16, 95, 32, 85); x.fillStyle = "#e0a878"; x.beginPath(); x.arc(cx, 78, 16, 0, 7); x.fill(); } });
    framePic(0.8, 0.56, fam, -0.95, 1.85, WZ + 0.03, g);
    const win = new T.Group(); win.position.set(-2.0, 1.75, WZ + 0.02); g.add(win);
    const sky = canvasTex(256, 256, (x, w, h) => { const gr = x.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#5fb0ee"); gr.addColorStop(1, "#d2ecfb"); x.fillStyle = gr; x.fillRect(0, 0, w, h); x.fillStyle = "#ffe27a"; x.beginPath(); x.arc(80, 70, 30, 0, 7); x.fill(); x.fillStyle = "#fff"; [[150, 140], [185, 130], [215, 145]].forEach(([a, b]) => { x.beginPath(); x.arc(a, b, 22, 0, 7); x.fill(); }); x.fillStyle = "#6aa84f"; x.beginPath(); x.arc(40, 250, 60, 0, 7); x.fill(); });
    const pane = new T.Mesh(new T.PlaneGeometry(0.9, 1.2), new T.MeshBasicMaterial({ map: sky })); pane.position.z = 0.02; win.add(pane);
    for (let k = -2; k <= 2; k++) box(0.025, 1.2, 0.05, [70, 70, 80], k * 0.2, 0, 0.04, win);
    box(1.0, 0.08, 0.12, [250, 250, 250], 0, 0.64, 0.03, win); box(1.0, 0.1, 0.16, [250, 250, 250], 0, -0.64, 0.05, win);
    [-1, 1].forEach(s => { box(0.3, 1.7, 0.05, [170, 40, 50], s * 0.62, -0.1, 0.12, win); for (let k = 0; k < 3; k++) box(0.04, 1.7, 0.07, [140, 30, 40], s * 0.62 + (k - 1) * 0.09, -0.1, 0.13, win); });
    glow(g, -2.0, 1.75, WZ + 0.2, 2.2, [255, 250, 230], 0.32);
    const door = new T.Group(); door.position.set(1.85, 0, WZ + 0.03); g.add(door);
    box(1.05, 2.3, 0.06, [235, 225, 205], 0, 1.15, 0, door);
    const dp = new T.Group(); dp.position.set(-0.46, 0, 0.04); door.add(dp);
    box(0.92, 2.15, 0.05, [140, 88, 52], 0.46, 1.08, 0, dp);
    [[0.46, 1.6], [0.46, 0.6]].forEach(([a, b]) => box(0.72, 0.78, 0.02, [160, 104, 64], a, b, 0.03, dp));
    ico(0.035, [230, 200, 80], 0, 0.84, 1.05, 0.06, dp);
    // shoe rack by the door
    const sr = new T.Group(); sr.position.set(2.45, 0, WZ + 0.6); g.add(sr);
    box(0.5, 0.45, 0.3, [130, 82, 50], 0, 0.225, 0, sr); box(0.46, 0.02, 0.28, [110, 70, 40], 0, 0.22, 0.01, sr);
    [[-0.12, 0.25, [60, 60, 70]], [0.12, 0.25, [200, 60, 60]], [-0.12, 0.03, [120, 70, 45]], [0.12, 0.03, [240, 240, 240]]].forEach(([x, y, c]) => box(0.18, 0.06, 0.24, c, x, y + 0.03, 0.02, sr));
    // showcase with crockery (right of the clock)
    const sc = new T.Group(); sc.position.set(0.95, 0, WZ + 0.2); g.add(sc);
    box(0.8, 1.5, 0.35, [140, 90, 55], 0, 1.35, 0, sc);
    const glass = new T.Mesh(new T.PlaneGeometry(0.7, 1.35), new T.MeshLambertMaterial({ color: 0xd8eef8, transparent: true, opacity: 0.25 })); glass.position.set(0, 1.35, 0.18); sc.add(glass);
    [1.0, 1.45, 1.85].forEach((y, r) => { box(0.72, 0.02, 0.3, [120, 76, 46], 0, y - 0.12, 0.0, sc); for (let k = 0; k < 4; k++) { const pl = cyl(0.07, 0.07, 0.012, 10, r === 1 ? [70, 130, 200] : [250, 250, 250], -0.25 + k * 0.17, y, -0.05, sc); pl.rotation.x = Math.PI / 2 - 0.2; } });
    // TV on a cabinet against the left wall
    const tv = new T.Group(); tv.position.set(-2.55, 0, WZ + 1.9); tv.rotation.y = Math.PI / 2; g.add(tv);
    box(1.1, 0.5, 0.42, [120, 76, 46], 0, 0.25, 0, tv); box(0.5, 0.02, 0.4, [100, 62, 38], 0.25, 0.25, 0.01, tv);
    box(0.95, 0.56, 0.05, [25, 25, 30], 0, 0.88, -0.05, tv);
    const tvs = new T.Mesh(new T.PlaneGeometry(0.88, 0.5), new T.MeshBasicMaterial({ color: 0x1a2030 })); tvs.position.set(0, 0.88, -0.02); tv.add(tvs);
    cyl(0.12, 0.15, 0.03, 8, [30, 30, 35], 0, 0.52, -0.05, tv);
    // side table + lamp + topi, plant
    const st = new T.Group(); st.position.set(-1.65, 0, WZ + 0.55); g.add(st);
    box(0.45, 0.55, 0.45, [150, 96, 60], 0, 0.28, 0, st);
    cyl(0.05, 0.1, 0.3, 6, [220, 200, 160], 0.08, 0.7, -0.05, st);
    cyl(0.12, 0.2, 0.22, 7, [250, 230, 180], 0.08, 0.95, -0.05, st);
    const topi = new T.Group(); topi.position.set(-0.1, 0.56, 0.1); st.add(topi);
    const tp = mesh(new T.CylinderGeometry(0.1, 0.1, 0.09, 10, 1, true), new T.MeshLambertMaterial({ map: sindhiTex("#7a1f2b", "#e9b949", "#2e6d9e", 6), side: T.DoubleSide })); tp.position.y = 0.045; topi.add(tp); cyl(0.1, 0.1, 0.01, 10, [122, 31, 43], 0, 0.09, 0, topi);
    lathe([[0.15, 0], [0.2, 0.3], [0.17, 0.38]], 8, [196, 106, 66], g).position.set(2.35, 0, WZ + 1.3);
    for (let j = 0; j < 6; j++) { const lf = mesh(jitter(new T.IcosahedronGeometry(0.2, 0), 0.06), M(j % 2 ? [70, 150, 70] : [90, 170, 80])); lf.position.set(2.35 + Math.sin(j * 1.2) * 0.14, 0.5 + j * 0.1, WZ + 1.3 + Math.cos(j * 1.2) * 0.1); g.add(lf); }
    aoStrip(g, 0, WZ + 0.3, 7.5, 0.55, 0, 0.6); aoStrip(g, -2.5, WZ + 3, 6, 0.55, Math.PI / 2, 0.55); aoStrip(g, 2.5, WZ + 3, 6, 0.55, -Math.PI / 2, 0.55);
    aoStrip(g, 0, WZ + 0.02, 7.5, 0.5, 0, 0.35, true);
    aoBlob(g, 0, WZ + 0.7, 2.9, 1.3, 0.8, 0.02); aoBlob(g, 0.45, 0.95, 1.2, 0.8, 0.6, 0.02); aoBlob(g, 0.95, WZ + 0.2, 1.1, 0.6, 0.55); aoBlob(g, -2.55, WZ + 1.9, 0.7, 1.4, 0.55);
    aoBlob(g, 2.45, WZ + 0.6, 0.7, 0.5, 0.5); aoBlob(g, -1.65, WZ + 0.55, 0.7, 0.7, 0.55);
    lightRig(g, { sky: [230, 235, 255], ground: [220, 200, 170], hemi: 1.0, sun: [255, 236, 200], sunI: 2.0, sunPos: [-5, 6, 5], fillI: 0.42, rim: [255, 235, 200], rimI: 1.1 });
    const anim = (t) => { fan.rotation.y = t * 5; };
    const slots = { sofa_l: { x: -0.7, z: WZ + 0.95, seatY: 0.5 }, sofa_c: { x: 0, z: WZ + 0.95, seatY: 0.5 }, sofa_r: { x: 0.7, z: WZ + 0.95, seatY: 0.5 },
      stand_l: { x: -1.45, z: 0.55 }, stand_r: { x: 1.35, z: 0.6 }, stand_cl: { x: -0.7, z: 0.75 }, stand_cr: { x: 0.75, z: 0.75 },
      floor_l: { x: -1.15, z: 0.85 }, floor_r: { x: 0.75, z: 1.3 } };
    return { g, slots, door: { x: 1.85, z: WZ + 0.35 }, anim, fog: new T.Fog(0xf3ead8, 12, 30), doorPanel: dp, bg: 0xf3ead8,
      grade: { gain: [1.04, 1.0, 0.95], lift: [0.01, 0.0, 0.0], sat: 1.08, vig: 0.3 } };
  }

  // ------------------------------------------------------------------ camera
  function headWorld(c) { const v = new T.Vector3(); c.head.getWorldPosition(v); v.y += c.hr * c.sc * 1.0; return v; }
  function faceYaw(c) { return c.root.rotation.y + c.head.rotation.y; }
  function computeCam(F) {
    const cam = F.cam; const ws = cam.ws.filter(w => CHARS[w] && CHARS[w].root.visible);
    const pts = ws.map(w => ({ w, h: headWorld(CHARS[w]), c: CHARS[w] }));
    if (!pts.length) return { mode: "orbit", tx: 0, ty: 1.2, tz: 0, Hh: 3.4, yaw: 0, el: 0.3, focus: 0 };
    let minX = Infinity, maxX = -Infinity, top = -Infinity, sz = 0, low = Infinity;
    pts.forEach(p => { minX = Math.min(minX, p.h.x); maxX = Math.max(maxX, p.h.x); top = Math.max(top, p.h.y + p.c.hr * p.c.sc * 1.1); low = Math.min(low, p.h.y); sz += p.h.z; });
    sz /= pts.length;
    const kind = cam.kind; const u = cam.u || 0;
    const fitW = (maxX - minX) + (kind === "wide" ? 1.2 : kind === "group" ? 1.05 : 0.95);
    let Hh, el, yaw = 0, ty, dof = false;
    const li = F.li; const line = li !== null && li !== undefined ? D.lines[li] : null;
    if (kind === "wide") { Hh = Math.max(fitW * 16 / 9, 3.0) * (1 - 0.04 * u); el = 0.42; ty = Math.max(top - Hh * 0.36, 0.55); yaw = 0.05 * (u - 0.5); }
    else if (kind === "group") { Hh = Math.max(fitW * 16 / 9, 2.4) * (1 - 0.05 * u); el = 0.3; ty = Math.max(top - Hh * 0.33, 0.5); }
    else if (kind === "two") { Hh = Math.max(fitW * 16 / 9, 2.0) * (1 - 0.05 * u); el = 0.2; ty = top - Hh * 0.31; }
    else {
      const p = pts[0]; const small = p.c.d.toddler ? 0.7 : 1;
      // over-the-shoulder on alternate close lines when the listener is near
      if (kind === "close" && line && line.to && CHARS[line.to] && CHARS[line.to].root.visible && line.to !== p.w && (li % 2 === 1) && !CHARS[line.to].d.toddler) {
        const lh = headWorld(CHARS[line.to]); const dd = Math.hypot(lh.x - p.h.x, lh.z - p.h.z);
        if (dd > 0.5 && dd < 2.6) return { mode: "ots", sp: p.w, ls: line.to, u, focus: 1 };
      }
      Hh = (kind === "punch" ? lerp(1.7, 1.3, ease((cam.t_in || 0) / 0.35)) : 1.55 * (1 - 0.05 * u)) * small;
      el = 0.1; ty = top - Hh * 0.29; dof = true;
      // find the face: orbit to where the character is looking, then make sure nobody blocks the view
      const want = clamp(faceYaw(p.c) * 0.8, -0.75, 0.75);
      const tyy = top - Hh * 0.29;
      const cands = [want, want * 0.6, want * 0.3, 0, want + 0.3 * Math.sign(want || 1), -want * 0.4, 0.55, -0.55, 0.85, -0.85];
      yaw = cands.find(y => !blocked(p, { tx: p.h.x, ty: tyy, tz: p.h.z, Hh, yaw: y, el })) ?? want;
      yaw += 0.04 * (u - 0.5);
    }
    if ((kind === "two" || kind === "group") && line) {
      const sp = line.who; if (CHARS[sp] && CHARS[sp].root.visible) { const h = headWorld(CHARS[sp]); yaw = clamp((h.x - (minX + maxX) / 2) * 0.15, -0.15, 0.15) + 0.03 * (u - 0.5); }
    }
    return { mode: "orbit", tx: (minX + maxX) / 2, ty, tz: sz, Hh, yaw, el, focus: dof ? 1 : 0 };
  }
  function orbitPos(s) {
    const d = (s.Hh / 2) / Math.tan(FOV / 2 * Math.PI / 180);
    return new T.Vector3(s.tx, s.ty, s.tz).add(new T.Vector3(Math.sin(s.yaw) * Math.cos(s.el), Math.sin(s.el), Math.cos(s.yaw) * Math.cos(s.el)).multiplyScalar(d));
  }
  function blocked(p, st) { // does any other character stand between the camera and this face?
    const cp = orbitPos(st), hp = p.h.clone(); hp.y -= p.c.hr * p.c.sc;
    const seg = hp.clone().sub(cp); const L = seg.length(); seg.normalize();
    return Object.values(CHARS).some(o => {
      if (o === p.c || !o.root.visible) return false;
      const pts = [headWorld(o).add(V(0, -o.hr * o.sc, 0)), o.root.position.clone().add(V(0, 1.1 * o.sc, 0)), o.root.position.clone().add(V(0, 0.75 * o.sc, 0))];
      return pts.some(q => { const k = q.clone().sub(cp).dot(seg); if (k < 0.1 || k > L - 0.25) return false; return cp.clone().addScaledVector(seg, k).distanceTo(q) < 0.3 * o.sc + 0.05; });
    });
  }
  function applyCam(s) {
    if (s.mode === "ots") {
      const sp = headWorld(CHARS[s.sp]), ls = headWorld(CHARS[s.ls]);
      const dir = new T.Vector3(sp.x - ls.x, 0, sp.z - ls.z).normalize();
      const side = new T.Vector3(dir.z, 0, -dir.x); // perpendicular
      const toCam = new T.Vector3(0, 0, 1); const sgn = side.dot(toCam) >= 0 ? 1 : -1; // put the camera on the open (front) side
      const pos = ls.clone().addScaledVector(dir, -0.55).addScaledVector(side, sgn * 0.32); pos.y = ls.y + 0.05;
      pos.z = Math.max(pos.z, ls.z + 0.25);
      const look = sp.clone(); look.y -= 0.22 + s.u * 0.02;
      camera.position.copy(pos); camera.lookAt(look);
      const dist = pos.distanceTo(look); camera.fov = 2 * Math.atan((1.25 / 2) / dist) * 180 / Math.PI; camera.updateProjectionMatrix();
      return dist;
    }
    if (camera.fov !== FOV) { camera.fov = FOV; camera.updateProjectionMatrix(); }
    const d = (s.Hh / 2) / Math.tan(FOV / 2 * Math.PI / 180);
    const dir = new T.Vector3(Math.sin(s.yaw) * Math.cos(s.el), Math.sin(s.el), Math.cos(s.yaw) * Math.cos(s.el));
    camera.position.set(s.tx, s.ty, s.tz).addScaledVector(dir, d);
    camera.lookAt(s.tx, s.ty, s.tz);
    return d;
  }

  // ------------------------------------------------------------------ frame
  function slot3(set, name) { return set.slots[name] || { x: 0, z: 0.5 }; }
  function placeChar(c, s, set, t, fi, wind) {
    let x, z, slotInfo = {};
    if (s.m === "walk") {
      const dst = slot3(set, s.dst || "stand_r");
      const front = (o) => o.seatY ? o.z + 0.42 : o.z;
      let sx, szz, ex, ez;
      if (s.fo) { const sr = s.src ? slot3(set, s.src) : dst; sx = sr.x; szz = front(sr); ex = set.door.x; ez = set.door.z; }
      else if (s.fi) { sx = set.door.x; szz = set.door.z; ex = dst.x; ez = front(dst); }
      else { const sr = s.src ? slot3(set, s.src) : dst; sx = sr.x; szz = front(sr); ex = dst.x; ez = front(dst); }
      const u = ease(s.u); const len = Math.hypot(ex - sx, ez - szz);
      x = lerp(sx, ex, u); z = lerp(szz, ez, u);
      s.phase = (len * u) / 0.34 * Math.PI;
      s.dir = Math.atan2(ex - sx, ez - szz);
      if (s.u > 0.85) s.dir = lerp(s.dir, 0, (s.u - 0.85) / 0.15);
    } else {
      slotInfo = slot3(set, s.slot);
      x = slotInfo.x; z = slotInfo.z;
      if (slotInfo.seatY) z = lerp(slotInfo.z, slotInfo.z + 0.42, s.st);
      if (slotInfo.lieZ !== undefined && s.sl > 0) z = lerp(z, slotInfo.lieZ, s.sl);
    }
    c.root.position.set(x, 0, z);
    if (s.sl > 0 && slotInfo.seatY) { c.body.rotation.z = (Math.PI / 2) * s.sl; c.body.position.x = lerp(0, -0.05, s.sl); }
    else { c.body.rotation.z = 0; c.body.position.x = 0; }
    updateChar(c, s, t, slotInfo, fi, wind);
    if (s.sl > 0 && slotInfo.seatY) c.body.position.y = lerp(c.body.position.y, slotInfo.seatY + 0.13, s.sl);
  }

  const DofShader = {
    uniforms: { tDiffuse: { value: null }, tDepth: { value: null }, focus: { value: 3 }, aperture: { value: 0.9 }, maxBlur: { value: 9 }, cameraNear: { value: 0.05 }, cameraFar: { value: 80 }, res: { value: new T.Vector2(W, H) } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `uniform sampler2D tDiffuse; uniform sampler2D tDepth; uniform float focus; uniform float aperture; uniform float maxBlur; uniform float cameraNear; uniform float cameraFar; uniform vec2 res; varying vec2 vUv;
      float dist(vec2 uv){ float d = texture2D(tDepth, uv).x; float z = d * 2.0 - 1.0; return (2.0 * cameraNear * cameraFar) / (cameraFar + cameraNear - z * (cameraFar - cameraNear)); }
      float coc(float z){ return clamp(abs(z - focus) / max(z, 0.01) * aperture, 0.0, 1.0) * maxBlur; }
      void main(){ float c0 = coc(dist(vUv)); vec4 acc = texture2D(tDiffuse, vUv); float wsum = 1.0;
        if (c0 > 0.6) { for (int i = 0; i < 16; i++) { float fi = float(i); float a = fi * 2.39996; float r = sqrt((fi + 0.5) / 16.0) * c0;
          vec2 uv2 = vUv + vec2(cos(a), sin(a)) * r / res; float cs = coc(dist(uv2)); float w = clamp(cs / max(c0, 0.001) + 0.15, 0.0, 1.0);
          acc += texture2D(tDiffuse, uv2) * w; wsum += w; } }
        gl_FragColor = acc / wsum; }`,
  };
  const GradeShader = {
    uniforms: { tDiffuse: { value: null }, gain: { value: new T.Vector3(1, 1, 1) }, lift: { value: new T.Vector3(0, 0, 0) }, sat: { value: 1 }, vig: { value: 0.3 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec3 gain; uniform vec3 lift; uniform float sat; uniform float vig; varying vec2 vUv;
      void main(){ vec4 c = texture2D(tDiffuse, vUv); vec3 x = c.rgb * gain + lift * (1.0 - c.rgb);
        float l = dot(x, vec3(0.2126, 0.7152, 0.0722)); x = mix(vec3(l), x, sat);
        vec2 d = (vUv - 0.5) * vec2(1.0, 1.25); float v = smoothstep(0.35, 0.85, length(d)); x *= 1.0 - vig * v;
        gl_FragColor = vec4(max(x, 0.0), c.a); }`,
  };

  window.LP = {
    init(data, opts) {
      D = data; opts = opts || {};
      renderer = new T.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer.setPixelRatio(1); renderer.setSize(W, H);
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
      renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.NoToneMapping;
      document.body.appendChild(renderer.domElement);
      scene = new T.Scene();
      camera = new T.PerspectiveCamera(FOV, W / H, 0.05, 80);
      D.scenes.forEach((s, k) => {
        const b = s.set === "aangan" ? buildAangan(s.time) : s.set === "bedroom" ? buildBedroom(s.time) : buildLiving(s.time);
        b.g.visible = false; scene.add(b.g); SETS[k] = b;
      });
      Object.entries(D.chars).forEach(([w, d]) => { CHARS[w] = makeChar(w, d); CHARS[w].root.visible = false; });
      const zt = canvasTex(64, 64, (x) => { x.fillStyle = "#3a4a9a"; x.font = "bold 54px sans-serif"; x.fillText("Z", 14, 52); });
      window._Z = [0, 1, 2].map(() => { const s = new T.Sprite(new T.SpriteMaterial({ map: zt, transparent: true })); s.scale.setScalar(0.16); scene.add(s); s.visible = false; return s; });
      if (PP && !opts.noPost) {
        const rt = new T.WebGLRenderTarget(W, H, { type: T.HalfFloatType, samples: 0, depthTexture: new T.DepthTexture(W, H) });
        composer = new PP.EffectComposer(renderer, rt);
        composer.renderTarget2.depthTexture = new T.DepthTexture(W, H); // own depth buffer (a shared one would be read+written at once)
        composer.addPass(new PP.RenderPass(scene, camera));
        // depth of field from the main render's depth buffer (no second scene render)
        class DofPass extends PP.ShaderPass {
          render(r, wb, rb, dt, m) { this.uniforms.tDepth.value = rb.depthTexture; this.uniforms.cameraNear.value = camera.near; this.uniforms.cameraFar.value = camera.far; super.render(r, wb, rb, dt, m); }
        }
        bokeh = new DofPass(DofShader); bokeh.uniforms = bokeh.material.uniforms; composer.addPass(bokeh);
        bloom = new PP.UnrealBloomPass(new T.Vector2(W / 4, H / 4), 0.32, 0.5, 0.9);
        composer.addPass(bloom);
        grade = new PP.ShaderPass(GradeShader); composer.addPass(grade);
        composer.addPass(new PP.OutputPass());
        const fx = new PP.ShaderPass(PP.FXAAShader); fx.material.uniforms.resolution.value.set(1 / W, 1 / H); composer.addPass(fx);
        if (opts.noBloom) bloom.enabled = false;
        window._noDOF = !!opts.noDOF;
      }
      return true;
    },
    dbg() { const o = { cam: camera.position.toArray().map(v => +v.toFixed(2)), fov: camera.fov, mode: camState && camState.mode };
      Object.entries(CHARS).forEach(([w, c]) => { if (c.root.visible) o[w] = { pos: c.root.position.toArray().map(v => +v.toFixed(2)), ry: +c.root.rotation.y.toFixed(2), hy: +c.head.rotation.y.toFixed(2) }; }); return o; },
    test(w, st, setIdx, camS) {
      const set = SETS[setIdx || 0];
      Object.values(SETS).forEach(s => s.g.visible = false); set.g.visible = true; scene.fog = set.fog; scene.background = new T.Color(set.bg); lastSi = -1;
      Object.values(CHARS).forEach(c => c.root.visible = false);
      const c = CHARS[w]; c.root.visible = true;
      const s = Object.assign({ emo: "calm", q: 0, sh: 0, bl: 0, lx: 0, ly: 0, face: 1, ang: 0, nod: 0, pose: "rest_stand", prev: "rest_stand", tc: -9, prop: null, al: 1, sl: 0, st: 1, m: "at", slot: "stand_c" }, st);
      placeChar(c, s, set, 5, -5, 0); scene.updateMatrixWorld(true);
      const h = headWorld(c);
      const d = applyCam(Object.assign({ mode: "orbit", tx: h.x, ty: h.y - 0.35, tz: h.z, Hh: 1.0, yaw: 0, el: 0.08 }, camS || {}));
      this._post(set, d, true);
      return renderer.domElement.toDataURL("image/jpeg", 0.9);
    },
    _post(set, dist, dof) {
      if (!composer) { renderer.render(scene, camera); return; }
      const gr = set.grade || {};
      grade.uniforms.gain.value.set(...(gr.gain || [1, 1, 1])); grade.uniforms.lift.value.set(...(gr.lift || [0, 0, 0]));
      grade.uniforms.sat.value = gr.sat || 1; grade.uniforms.vig.value = gr.vig || 0.3;
      bokeh.enabled = !!dof && !window._noDOF;
      if (dof) bokeh.uniforms.focus.value = dist;
      composer.render();
    },
    frame(i) {
      const F = D.frames[i]; const t = F.t; const si = F.si; const set = SETS[si];
      if (si !== lastSi) { Object.values(SETS).forEach(s => s.g.visible = false); set.g.visible = true; scene.fog = set.fog; scene.background = new T.Color(set.bg); lastSi = si; camState = null; }
      const wind = set.windy ? 0.6 + 0.4 * Math.sin(t * 0.7) : 0;
      set.anim(t, wind);
      Object.entries(CHARS).forEach(([w, c]) => {
        const s = F.ch[w];
        if (!s) { c.root.visible = false; c.dyn = null; return; }
        c.root.visible = true; placeChar(c, Object.assign({}, s), set, t, i, wind);
      });
      if (set.razai) {
        const sleeper = D.scenes[si].sleepers[0]; const s = sleeper && F.ch[sleeper];
        const sl = s ? s.sl : 0;
        set.razai.position.set(lerp(1.3, 1.45, 1 - sl), lerp(0.62, 0.6, 1 - sl), lerp(0.05, -0.32, 1 - sl));
        set.razai.scale.set(lerp(1.0, 0.75, 1 - sl), lerp(1, 1.5, 1 - sl), lerp(1, 0.5, 1 - sl));
        set.razai.rotation.y = lerp(0, 0.08, 1 - sl);
        window._Z.forEach((z, k) => { z.visible = sl > 0.5; if (sl > 0.5) { const u = ((t * 0.5 + k / 3) % 1); const h = headWorld(CHARS[sleeper]); z.position.set(h.x + 0.15 + u * 0.25, h.y + 0.15 + u * 0.45, h.z); z.material.opacity = Math.sin(u * Math.PI); z.scale.setScalar(0.1 + u * 0.12); } });
      } else window._Z.forEach(z => z.visible = false);
      const walkers = Object.values(F.ch).filter(s => s.m === "walk" && (s.fi || s.fo));
      const op = walkers.length ? Math.max(...walkers.map(s => Math.sin(clamp(s.fi ? s.u * 1.6 : 1 - s.u, 0, 1) * Math.PI / 2))) : 0;
      if (set.doorPanel) set.doorPanel.rotation.y = -op * 1.3;
      if (set.gate) { set.gate[0].rotation.y = op * 1.2; set.gate[1].rotation.y = -op * 1.2; }
      scene.updateMatrixWorld(true);
      const target = computeCam(F);
      const key = F.cam.kind + "|" + F.cam.key + "|" + si + "|" + target.mode;
      const contWide = F.cam.kind === "wide" && lastKey && lastKey.startsWith("wide") && lastKey.endsWith("|" + si + "|orbit");
      if (!camState || i !== lastFrame + 1 || (key !== lastKey && !contWide) || target.mode !== camState.mode) camState = Object.assign({}, target);
      else if (target.mode === "orbit") { for (const k in target) if (typeof target[k] === "number") camState[k] = lerp(camState[k], target[k], 0.16); }
      else camState = Object.assign({}, target);
      lastKey = key; lastFrame = i;
      const dist = applyCam(camState);
      this._post(set, dist, camState.focus > 0.5);
      return renderer.domElement.toDataURL("image/jpeg", 0.93);
    },
  };
})();
