/* Sindhi Ghar Ki Kahani - low-poly 3D renderer (three.js r160, global THREE).
   window.LP.init(data) once, then window.LP.frame(i) -> jpeg dataURL. */
(function () {
  const T = THREE;
  const W = 1080, H = 1920, FOV = 38;
  let renderer, scene, camera, D;
  const SETS = {}, CHARS = {};
  let curSet = null, camState = null, lastKey = null, lastSi = -1;

  // ------------------------------------------------------------------ helpers
  const C = (v) => Array.isArray(v) ? new T.Color(v[0] / 255, v[1] / 255, v[2] / 255) : new T.Color(v);
  const MC = {};
  function M(c, opts) {
    const key = (Array.isArray(c) ? c.join(",") : c) + JSON.stringify(opts || {});
    if (!MC[key]) MC[key] = new T.MeshLambertMaterial(Object.assign({ color: C(c), flatShading: true }, opts || {}));
    return MC[key];
  }
  function mesh(g, m, cast = true, recv = true) { const o = new T.Mesh(g, m); o.castShadow = cast; o.receiveShadow = recv; return o; }
  function box(w, h, d, c, x = 0, y = 0, z = 0, p) { const o = mesh(new T.BoxGeometry(w, h, d), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function cyl(rt, rb, h, seg, c, x = 0, y = 0, z = 0, p) { const o = mesh(new T.CylinderGeometry(rt, rb, h, seg), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function ico(r, c, det = 1, x = 0, y = 0, z = 0, p) { const o = mesh(new T.IcosahedronGeometry(r, det), M(c)); o.position.set(x, y, z); if (p) p.add(o); return o; }
  function hash(x, y, z) { const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453; return s - Math.floor(s); }
  function jitter(g, a) { // same displacement for shared positions -> no cracks
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      const kx = Math.round(x * 1000) / 1000, ky = Math.round(y * 1000) / 1000, kz = Math.round(z * 1000) / 1000;
      p.setXYZ(i, x + (hash(kx, ky, kz) - 0.5) * a, y + (hash(ky, kz, kx) - 0.5) * a, z + (hash(kz, kx, ky) - 0.5) * a);
    }
    g.computeVertexNormals(); return g;
  }
  const UP = new T.Vector3(0, 1, 0);
  function place(o, a, b) { // unit-height Y mesh between points a,b
    const d = new T.Vector3().subVectors(b, a); const L = d.length();
    o.position.copy(a).addScaledVector(d, 0.5);
    o.scale.set(1, Math.max(L, 1e-4), 1);
    o.quaternion.setFromUnitVectors(UP, d.normalize());
  }
  const lerp = (a, b, u) => a + (b - a) * u;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (u) => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
  function canvasTex(w, h, draw) {
    const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; t.anisotropy = 4; return t;
  }
  function instBoxes(list, w, h, d, p, cast = false) { // list of [x,y,z,color,(sx,sy,sz)]
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
  function gradientSky(top, mid, bot, p, w = 60, h = 34, z = -14, y = 10) {
    const g = new T.PlaneGeometry(w, h, 1, 24);
    const cols = []; const ct = C(top), cm = C(mid), cb = C(bot);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const v = (pos.getY(i) / h) + 0.5; const c = new T.Color();
      if (v > 0.45) c.lerpColors(cm, ct, (v - 0.45) / 0.55); else c.lerpColors(cb, cm, v / 0.45);
      cols.push(c.r, c.g, c.b);
    }
    g.setAttribute("color", new T.Float32BufferAttribute(cols, 3));
    const o = new T.Mesh(g, new T.MeshBasicMaterial({ vertexColors: true, fog: false })); o.position.set(0, y, z); p.add(o); return o;
  }
  function frameDeco(w, h, tex, x, y, z, p, frameCol = [120, 70, 40]) {
    const g = new T.Group(); g.position.set(x, y, z); p.add(g);
    box(w + 0.08, h + 0.08, 0.04, frameCol, 0, 0, 0, g);
    const pl = new T.Mesh(new T.PlaneGeometry(w, h), new T.MeshLambertMaterial({ map: tex })); pl.position.z = 0.025; g.add(pl);
    return g;
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
    return { hemi, sun, fill };
  }

  // ------------------------------------------------------------------ props
  function makeProp(name) {
    const g = new T.Group();
    if (name === "bat") {
      cyl(0.018, 0.018, 0.26, 6, [60, 40, 30], 0, -0.1, 0, g);              // handle (grip wrapped)
      cyl(0.021, 0.021, 0.12, 6, [30, 30, 36], 0, -0.06, 0, g);
      const bl = box(0.1, 0.55, 0.035, [232, 196, 130], 0, -0.5, 0.0, g);   // blade
      box(0.07, 0.5, 0.025, [214, 176, 110], 0, -0.5, -0.025, g);
      g.userData.hang = true;
    } else if (name === "cup") {
      cyl(0.04, 0.032, 0.09, 8, [250, 250, 250], 0, 0.05, 0.03, g);
      cyl(0.036, 0.036, 0.005, 8, [170, 100, 50], 0, 0.093, 0.03, g);
      const h = mesh(new T.TorusGeometry(0.022, 0.007, 4, 8), M([250, 250, 250])); h.position.set(0.045, 0.05, 0.03); h.rotation.y = Math.PI / 2; g.add(h);
      g.userData.steam = [];
      for (let k = 0; k < 3; k++) {
        const s = mesh(new T.IcosahedronGeometry(0.018, 0), new T.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, flatShading: true }), false, false);
        g.add(s); g.userData.steam.push(s);
      }
    } else if (name === "book") {
      box(0.17, 0.23, 0.035, [60, 110, 190], 0, 0.05, 0.05, g);
      box(0.16, 0.22, 0.03, [245, 240, 225], 0.006, 0.05, 0.05, g);
      box(0.17, 0.23, 0.006, [60, 110, 190], 0, 0.05, 0.07, g);
    } else if (name === "phone") {
      box(0.07, 0.14, 0.012, [30, 30, 38], 0, 0.06, 0.03, g);
      box(0.06, 0.12, 0.002, [120, 190, 250], 0, 0.06, 0.037, g);
    } else if (name) {
      box(0.12, 0.12, 0.12, [200, 120, 160], 0, 0, 0.05, g);
    }
    g.traverse(o => { if (o.isMesh) o.castShadow = true; });
    return g;
  }

  // ------------------------------------------------------------------ characters
  const EMO = { // brow angle, brow raise, eye open, smile(+)/frown(-), mouth min open, asym
    calm: [0, 0, 1, 0.5, 0, 0], neutral: [0, 0, 1, 0, 0, 0], happy: [0.05, 0.01, 0.85, 1, 0, 0], laugh: [0.1, 0.012, 0.3, 1, 3, 0],
    warm: [0.08, 0.005, 0.82, 0.9, 0, 0], teasing: [-0.1, 0, 0.72, 0.8, 0, 1], sheepish: [0.35, 0.012, 0.85, 0.4, 0, 0],
    worried: [0.4, 0.015, 1.05, -0.6, 0, 0], surprised: [0.05, 0.03, 1.3, 0, 2, 0], angry: [-0.45, -0.008, 0.85, -0.7, 0, 0],
    tired: [0.2, -0.006, 0.5, -0.2, 0, 0], proud: [-0.05, 0.008, 0.78, 0.9, 0, 0], confused: [0.25, 0.01, 1, -0.2, 0, 2],
    sad: [0.45, 0.01, 0.8, -0.9, 0, 0], focused: [-0.2, -0.004, 0.85, 0, 0, 0], chew: [0, 0, 0.9, 0.2, 0, 0],
  };
  // hand targets relative to the shoulder line centre (x: + = near/face side), y up, z forward; flags
  const P3 = {
    rest_stand: [[0.22, -0.52, 0.04], [-0.22, -0.52, 0.04], ""], rest_sofa: [[0.12, -0.42, 0.3], [-0.12, -0.42, 0.3], ""],
    read: [[0.1, -0.22, 0.32], [-0.06, -0.24, 0.32], "prop"], head_hold: [[0.2, 0.25, 0.04], [-0.2, 0.25, 0.04], ""],
    beckon: [[0.3, 0.02, 0.26], null, "wave"], wag: [[0.24, 0.02, 0.3], null, "wag finger"], plead: [[0.06, -0.14, 0.33], [-0.05, -0.15, 0.33], ""],
    point_down: [[0.33, -0.42, 0.32], null, "finger"], fist: [[0.25, 0.16, 0.18], null, ""], point_other: [[0.52, -0.06, 0.2], null, "finger"],
    thumb_back: [null, [-0.3, -0.06, -0.04], "farfinger"], arms_up: [[0.36, 0.48, 0.06], [-0.36, 0.48, 0.06], "jump"],
    chest: [[0.04, -0.17, 0.2], null, ""], wave: [[0.33, 0.28, 0.12], null, "wave"], hold: [[0.14, -0.24, 0.32], null, "prop"],
    newspaper: [[0.16, -0.18, 0.34], [-0.16, -0.18, 0.34], "prop"], phone_look: [[0.07, 0.0, 0.3], null, "prop"],
    hands_hips: [[0.25, -0.46, -0.02], [-0.25, -0.46, -0.02], "elbows"], cross: [[-0.1, -0.22, 0.2], [0.1, -0.2, 0.22], ""],
    shrug: [[0.38, -0.16, 0.2], [-0.38, -0.16, 0.2], "shrug"], facepalm: [[0.03, 0.27, 0.21], null, ""],
    scratch_head: [[0.14, 0.36, -0.02], null, ""], objection: [[0.28, 0.4, 0.22], null, "finger"], clap: [[0.03, -0.18, 0.32], [-0.03, -0.18, 0.32], "clap"],
    think: [[0.04, 0.1, 0.2], [-0.04, -0.24, 0.2], ""], explain: [[0.33, -0.18, 0.26], [-0.31, -0.22, 0.22], "explain"],
    point_up: [[0.26, 0.3, 0.2], null, "finger"], tired: [[0.2, -0.56, 0.07], [-0.2, -0.56, 0.07], ""],
    walk: [[0.2, -0.52, 0.0], [-0.2, -0.52, 0.0], "walk"], tray: [[0.15, -0.18, 0.32], [-0.15, -0.18, 0.32], "prop"],
    give: [[0.2, -0.1, 0.5], null, "prop"], take: [[0.18, -0.08, 0.46], null, ""], hold_sofa: [[0.1, -0.27, 0.27], null, "prop"],
  };
  const NEAR_PROPS = { hold: 1, read: 1, phone_look: 1, give: 1, newspaper: 1, tray: 1, hold_sofa: 1, take: 1 };

  function makeChar(w, d) {
    const sc = d.scale * (d.toddler ? 1.06 : 1), hs = d.toddler ? 1.38 : 1.0;
    const root = new T.Group(); const body = new T.Group(); root.add(body);
    const skin = d.skin, shirt = d.shirt, pants = d.pants;
    const c = { w, d, root, body, sc, hs, props: {}, curProp: null };
    const tod = d.toddler;
    // proportions (adult units, the whole root is scaled by sc)
    const L = tod ? { hip: 0.62, thigh: 0.27, shin: 0.27, torso: 0.4, sh: 0.15, ua: 0.19, fa: 0.18, hr: 0.2 }
      : { hip: 0.86, thigh: 0.4, shin: 0.4, torso: 0.48, sh: 0.18, ua: 0.27, fa: 0.26, hr: 0.165 };
    c.L = L;
    const torsoG = new T.Group(); body.add(torsoG); c.torso = torsoG;
    // torso
    const tor = mesh(new T.CylinderGeometry(L.sh * 0.95, L.sh * 0.88, L.torso, 7), M(shirt)); tor.scale.set(1.12, 1, 0.72); tor.position.y = L.torso / 2; torsoG.add(tor);
    const shoulders = ico(L.sh * 0.98, shirt, 1, 0, L.torso - 0.02, 0, torsoG); shoulders.scale.set(1.22, 0.32, 0.74);
    if (d.kameez) {
      // kameez skirt (standing) + lap panel (seated)
      const sk = mesh(new T.CylinderGeometry(L.sh * 0.92, L.sh * 1.32, 0.5, 8, 1, true), M(shirt, { side: T.DoubleSide })); sk.scale.set(1.12, 1, 0.8); sk.position.y = -0.22; torsoG.add(sk); c.skirt = sk;
      const lap = box(0.37, 0.06, 0.5, shirt, 0, 0.07, 0.22, torsoG); c.lap = lap; lap.visible = false;
      // neckline / embroidery
      const nk = mesh(new T.CylinderGeometry(0.05, 0.07, 0.012, 8), M(d.cover2 || shirt.map(v => v * 0.8))); nk.position.set(0, L.torso - 0.06, L.sh * 0.66); nk.rotation.x = 1.35; torsoG.add(nk);
    } else {
      // tee / jersey + track pants waist
      box(L.sh * 2.05, 0.06, L.sh * 1.45, pants, 0, 0.0, 0, torsoG);
      if (d.shirt2) { // jersey stripe + badge
        const st = mesh(new T.CylinderGeometry(L.sh * 0.96, L.sh * 0.96, 0.05, 7, 1, true), M(d.shirt2)); st.scale.set(1.13, 1, 0.73); st.position.y = L.torso * 0.62; torsoG.add(st);
        const bd = mesh(new T.TorusGeometry(0.035, 0.009, 4, 10), M(d.shirt2)); bd.position.set(0.0, L.torso * 0.4, L.sh * 0.73); torsoG.add(bd);
      }
    }
    // neck + head
    const neck = cyl(0.05 * (tod ? 0.9 : 1), 0.058, 0.12, 6, skin, 0, L.torso + 0.05, 0, torsoG);
    const headG = new T.Group(); headG.position.y = L.torso + (tod ? 0.06 : 0.075); torsoG.add(headG); c.head = headG;
    const hr = L.hr * hs; c.hr = hr;
    const head = mesh(jitter(new T.IcosahedronGeometry(hr, 1), 0.006), M(skin)); head.scale.set(0.95, 1.05, 0.95); head.position.y = hr * 0.98; headG.add(head);
    const face = new T.Group(); face.position.set(0, hr * 0.95, 0); headG.add(face); c.face = face;
    // ears
    [-1, 1].forEach(s => { const e = ico(hr * 0.2, skin, 0, s * hr * 0.92, 0, -0.01, face); e.scale.set(0.5, 1, 0.8); });
    // eyes
    c.eyes = [];
    [-1, 1].forEach(s => {
      const eg = new T.Group(); eg.position.set(s * hr * 0.36, hr * 0.06, hr * 0.84); face.add(eg);
      const wht = ico(hr * 0.2, [252, 252, 250], 1, 0, 0, 0, eg); wht.scale.set(1, 1.15, 0.45); wht.castShadow = false;
      const pup = ico(hr * 0.125, [40, 26, 22], 1, 0, 0, hr * 0.06, eg); pup.scale.set(1, 1.1, 0.5); pup.castShadow = false;
      const hl = ico(hr * 0.04, [255, 255, 255], 0, hr * 0.04, hr * 0.05, hr * 0.11, eg); hl.material = new T.MeshBasicMaterial({ color: 0xffffff }); hl.castShadow = false;
      const lid = ico(hr * 0.215, skin, 1, 0, 0, -0.001, eg); lid.scale.set(1.05, 1.2, 0.5); lid.castShadow = false;
      const clip = new T.Group(); // lid moves down to close
      let lash = null;
      if (d.lashes) { lash = box(hr * 0.42, hr * 0.035, hr * 0.03, [30, 20, 20], s * hr * 0.03, 0, hr * 0.1, eg); lash.rotation.z = s * -0.15; }
      c.eyes.push({ eg, pup, lid, lash, hl, s });
    });
    // brows
    c.brows = [-1, 1].map(s => { const b = box(hr * 0.42, hr * 0.07, hr * 0.06, d.hair_col || [30, 20, 20], s * hr * 0.37, hr * 0.36, hr * 0.84, face); b.castShadow = false; return b; });
    // nose
    const nose = mesh(new T.ConeGeometry(hr * 0.12, hr * 0.26, 4), M(skin.map((v) => v * 0.93))); nose.rotation.x = Math.PI / 2 + 0.3; nose.position.set(0, -hr * 0.12, hr * 0.98); face.add(nose); c.nose = nose; c.noseMat = nose.material;
    c.puffs = [0, 1, 2, 3, 4, 5].map(k => { const p = mesh(new T.IcosahedronGeometry(hr * 0.12, 0), new T.MeshLambertMaterial({ color: 0xf4fbff, transparent: true, opacity: 0.8, flatShading: true }), false, false); p.visible = false; face.add(p); return p; });
    // cheeks
    [-1, 1].forEach(s => { const ch = ico(hr * 0.14, [240, 140, 140], 0, s * hr * 0.55, -hr * 0.22, hr * 0.74, face); ch.scale.set(1, 0.6, 0.3); ch.material = new T.MeshLambertMaterial({ color: 0xf08c8c, transparent: true, opacity: 0.55 }); ch.castShadow = false; c.cheeks = (c.cheeks || []).concat(ch); });
    // mouth
    const mg = new T.Group(); mg.position.set(0, -hr * 0.4, hr * 0.86); face.add(mg); c.mouth = mg;
    c.mOpen = ico(hr * 0.16, [80, 22, 32], 1, 0, 0, 0, mg); c.mOpen.castShadow = false;
    c.teeth = box(hr * 0.22, hr * 0.05, hr * 0.03, [250, 250, 245], 0, hr * 0.06, hr * 0.045, mg); c.teeth.castShadow = false;
    c.tongue = ico(hr * 0.075, [210, 90, 100], 0, 0, -hr * 0.05, hr * 0.035, mg); c.tongue.scale.z = 0.4; c.tongue.castShadow = false;
    c.smile = mesh(new T.TorusGeometry(hr * 0.2, hr * 0.035, 3, 8, Math.PI), M([120, 40, 45])); c.smile.castShadow = false; mg.add(c.smile);
    // hair / cover
    const hc = d.hair_col || [30, 20, 20];
    if (d.hair === "spiky") {
      const cap = mesh(new T.SphereGeometry(hr * 1.04, 8, 5, 0, Math.PI * 2, 0, Math.PI * 0.42), M(hc)); cap.position.y = hr * 1.0; cap.rotation.x = -0.25; headG.add(cap);
      for (let k = 0; k < 9; k++) {
        const a = (k / 9) * Math.PI * 2, r = k % 2 ? 0.45 : 0.25;
        const sp = mesh(new T.ConeGeometry(hr * 0.2, hr * 0.62, 4), M(hc));
        sp.position.set(Math.cos(a) * hr * r, hr * 1.82 + (k % 3) * 0.006, Math.sin(a) * hr * r - hr * 0.08);
        sp.rotation.set(Math.sin(a) * 0.5 - 0.2, 0, -Math.cos(a) * 0.5); headG.add(sp);
      }
      const fr = mesh(new T.ConeGeometry(hr * 0.24, hr * 0.5, 4), M(hc)); fr.position.set(hr * 0.15, hr * 1.62, hr * 0.62); fr.rotation.x = 1.0; headG.add(fr);
    } else if (d.hair === "plaits") {
      const cap = mesh(new T.SphereGeometry(hr * 1.06, 8, 6, 0, Math.PI * 2, 0, Math.PI * 0.55), M(hc)); cap.position.y = hr * 0.98; cap.rotation.x = -0.35; headG.add(cap);
      const bang = box(hr * 1.3, hr * 0.28, hr * 0.3, hc, 0, hr * 1.62, hr * 0.72, headG); bang.rotation.x = 0.45;
      [-1, 1].forEach(s => { for (let k = 0; k < 6; k++) { ico(hr * (0.2 - k * 0.012), hc, 0, s * hr * 0.82, hr * (0.75 - k * 0.32), hr * 0.15 + k * 0.012, headG); } ico(hr * 0.11, [255, 90, 150], 0, s * hr * 0.82, hr * (0.75 - 6 * 0.32), hr * 0.2, headG); });
      ico(hr * 0.12, [255, 120, 170], 0, hr * 0.62, hr * 1.66, hr * 0.5, headG); // hair clip
    } else if (d.hair === "tuft") {
      const cap = mesh(new T.SphereGeometry(hr * 1.03, 8, 5, 0, Math.PI * 2, 0, Math.PI * 0.35), M(hc)); cap.position.y = hr * 0.98; headG.add(cap);
      const tf = mesh(new T.ConeGeometry(hr * 0.18, hr * 0.45, 4), M(hc)); tf.position.set(0.0, hr * 2.08, 0.02); tf.rotation.z = 0.4; headG.add(tf);
    } else if (d.hair === "dupatta") {
      
      const cv = mesh(new T.SphereGeometry(hr * 1.16, 9, 6, 0, Math.PI * 2, 0, Math.PI * 0.62), M(d.cover, { side: T.DoubleSide }));
      cv.position.set(0, hr * 0.94, -hr * 0.14); cv.rotation.x = -0.82; headG.add(cv);
      const border = mesh(new T.TorusGeometry(hr * 1.05, hr * 0.06, 3, 14, Math.PI * 1.25), M(d.cover2)); border.position.set(0, hr * 1.12, hr * 0.36); border.rotation.set(-0.95, 0, Math.PI * -0.125 - Math.PI * 0.0); border.rotation.z = -Math.PI * 0.125 + Math.PI * 0; headG.add(border);
      // drape down the back + over the shoulders
      const back = box(0.42, 0.62, 0.04, d.cover, 0, L.torso - 0.12, -L.sh * 0.78, torsoG); back.rotation.x = 0.12;
      [-1, 1].forEach(s => { const sd = box(0.07, 0.5, 0.1, d.cover, s * L.sh * 1.08, L.torso - 0.2, -0.05, torsoG); sd.rotation.z = s * 0.1; });
      [-1, 1].forEach(s => { const v = box(0.085, 0.34, 0.03, d.cover, s * 0.085, L.torso - 0.13, L.sh * 0.75, torsoG); v.rotation.z = -s * 0.5; v.rotation.x = -0.1; const vb = box(0.02, 0.34, 0.035, d.cover2, s * 0.085 + s * 0.045, L.torso - 0.13, L.sh * 0.755, torsoG); vb.rotation.z = -s * 0.5; vb.rotation.x = -0.1; });
    }
    if (d.earrings) [-1, 1].forEach(s => ico(hr * 0.07, [240, 200, 60], 0, s * hr * 0.9, -hr * 0.3, 0.0, face));
    // arms
    c.arms = [-1, 1].map(s => {
      const sleeveLong = d.kameez;
      const ua = mesh(new T.CylinderGeometry(0.048, 0.044, 1, 6), M(shirt)); body.add(ua);
      const fa = mesh(new T.CylinderGeometry(0.042, 0.036, 1, 6), M(sleeveLong ? shirt : skin)); body.add(fa);
      let cuff = null; if (sleeveLong) { cuff = mesh(new T.CylinderGeometry(0.04, 0.04, 0.035, 6), M(skin)); body.add(cuff); }
      const hand = new T.Group(); body.add(hand);
      const palm = ico(0.048, skin, 1, 0, 0, 0, hand); palm.scale.set(0.85, 1.05, 0.7);
      const thumb = ico(0.02, skin, 0, 0.035, 0.012, 0.02, hand);
      const finger = mesh(new T.CylinderGeometry(0.012, 0.011, 0.07, 5), M(skin)); finger.position.set(0, 0.06, 0); hand.add(finger); finger.visible = false;
      const elb = ico(0.046, shirt, 0, 0, 0, 0, body);
      return { s, ua, fa, cuff, hand, finger, elb };
    });
    // legs
    c.legs = [-1, 1].map(s => {
      const lw = d.kameez ? 0.085 : 0.07;
      const th = mesh(new T.CylinderGeometry(lw, lw * 0.92, 1, 6), M(pants)); body.add(th);
      const sh = mesh(new T.CylinderGeometry(lw * 0.92, d.kameez ? lw * 0.62 : lw * 0.8, 1, 6), M(pants)); body.add(sh);
      const kn = ico(lw * 0.74, pants, 1, 0, 0, 0, body);
      const footC = d.toddler ? [240, 240, 240] : (d.kameez ? [120, 70, 45] : [245, 245, 245]);
      const ft = new T.Group(); body.add(ft);
      box(0.09, 0.06, 0.2, footC, 0, -0.025, 0.05, ft);
      if (!d.kameez) box(0.095, 0.02, 0.21, [200, 60, 60], 0, -0.055, 0.05, ft);
      if (d.kameez) ico(0.035, skin, 0, 0, 0.0, 0.02, ft);
      return { s, th, sh, kn, ft };
    });
    root.scale.setScalar(sc);
    root.traverse(o => { if (o.isMesh && o.castShadow !== false) { o.castShadow = true; o.receiveShadow = true; } });
    c.eyes.forEach(e => [e.pup, e.lid].forEach(o => o.castShadow = false));
    scene.add(root);
    return c;
  }

  const V = (x, y, z) => new T.Vector3(x, y, z);
  function ik(S, Tg, L1, L2, pole) {
    const d = new T.Vector3().subVectors(Tg, S); let len = d.length();
    const maxL = (L1 + L2) * 0.995; if (len > maxL) { d.setLength(maxL); len = maxL; }
    const dir = d.clone().normalize();
    const a = (L1 * L1 - L2 * L2 + len * len) / (2 * len); const h = Math.sqrt(Math.max(L1 * L1 - a * a, 0));
    const pp = pole.clone().sub(dir.clone().multiplyScalar(pole.dot(dir))).normalize();
    const E = S.clone().addScaledVector(dir, a).addScaledVector(pp, h);
    return [E, S.clone().add(d)];
  }

  function poseTargets(name, face, seated) {
    const p = P3[name] || P3[seated ? "rest_sofa" : "rest_stand"];
    const rest = P3[seated ? "rest_sofa" : "rest_stand"];
    let n = p[0] || rest[0], f = p[1] || rest[1];
    const fix = (v) => { v = v.slice(); if (seated && v[1] < -0.36) { v[1] = -0.4; v[2] = Math.max(v[2], 0.28); } return v; };
    n = fix(n); f = fix(f);
    return { n: V(n[0] * face, n[1], n[2]), f: V(f[0] * face, f[1], f[2]), flags: p[2] };
  }

  function updateChar(c, s, t, slotInfo) {
    const L = c.L;
    const seat = slotInfo.seatY || 0.46;
    const stand = s.st;
    // ---- body height / lying
    const sl = s.sl || 0;
    const hipY = lerp(seat, L.hip, stand);
    c.body.position.set(0, hipY, 0);
    let hop = 0;
    const cur = s.pose, prv = s.prev; const blendU = ease((t - s.tc) / 0.28);
    if (P3[cur] && P3[cur][2] && P3[cur][2].includes("jump") && t - s.tc < 0.9) hop = Math.abs(Math.sin((t - s.tc) * 9)) * 0.05 * (stand > 0.5 ? 1 : 0.4);
    c.body.position.y += hop;
    // walking bob
    if (s.m === "walk") c.body.position.y += Math.abs(Math.sin(s.ph || 0)) * 0.02;
    // breathing
    const br = Math.sin(t * 2.1 + c.w.length) * 0.006;
    c.torso.scale.set(1, 1 + br, 1);
    // ---- legs
    const walkA = s.m === "walk" ? Math.sin(s.ph || 0) : 0;
    c.legs.forEach((lg, k) => {
      const sx = lg.s * 0.1 * (c.d.toddler ? 0.8 : 1);
      const hip = V(sx, -0.02, 0);
      let kn, an;
      const swing = walkA * (k ? 1 : -1);
      const kS = V(sx, -L.thigh * Math.cos(swing * 0.5), L.thigh * Math.sin(swing * 0.5));
      const aS = V(sx, kS.y - L.shin, kS.z - Math.max(0, -swing) * 0.12);
      const kSit = V(sx * 1.05, 0.02, L.thigh * 1.02);
      const aSit = V(sx * 1.1, -(hipY - 0.07), L.thigh * 1.08);
      const lie = V(sx, -L.thigh, 0), lieA = V(sx, -L.thigh - L.shin, 0);
      kn = kS.clone().lerp(kSit, 1 - stand); an = aS.clone().lerp(aSit, 1 - stand);
      if (sl > 0) { kn.lerp(lie, sl); an.lerp(lieA, sl); }
      place(lg.th, hip, kn); place(lg.sh, kn, an); lg.kn.position.copy(kn);
      lg.ft.position.copy(an); lg.ft.rotation.set(0, 0, 0);
      if (sl > 0) lg.ft.rotation.x = -sl * 1.4;
    });
    // kameez: skirt standing vs lap seated
    if (c.skirt) { const seated = stand < 0.5 && sl < 0.5; c.skirt.visible = !seated; c.lap.visible = seated; c.lap.scale.z = 1; c.skirt.rotation.x = s.m === "walk" ? walkA * 0.05 : 0; }
    // ---- emotion
    const e = EMO[s.emo] || EMO.calm;
    const speaking = s.q > 0;
    // ---- head / look
    const look = s.lx || 0;
    const yawHead = look * 0.55, pitch = (s.ly || 0) * 0.25 - (s.emo === "proud" ? 0.12 : 0);
    c.head.rotation.set(pitch * 0.6 + (s.nod || 0) * 0.15 - (s.emo === "laugh" ? 0.06 + Math.abs(Math.sin(t * 15)) * 0.06 : 0), yawHead, -(s.ang || 0) * Math.PI / 180 * 0.9);
    // body facing
    let yaw = look * 0.22;
    if (s.m === "walk" && s.dir !== undefined) yaw = s.dir;
    c.root.rotation.y = yaw;
    c.torso.rotation.set(s.emo === "tired" ? 0.08 : 0, 0, 0);
    // sneeze: wind-up (head back) then a sharp forward jerk
    const sn = (D.fx && D.fx.sneeze || []).find(z => z.who === c.w && t >= z.t - 0.45 && t < z.t + 0.7);
    c.sneezeU = 0;
    if (sn) {
      const k = t - sn.t;
      const p = k < 0 ? -0.25 * Math.sin((k + 0.45) / 0.45 * Math.PI / 2) : 0.45 * Math.exp(-k * 5) * (k < 0.08 ? k / 0.08 : 1);
      c.head.rotation.x += p; c.torso.rotation.x += p * 0.35; c.sneezeU = k >= 0 ? Math.max(0, 1 - k / 0.7) : 0;
      if (k < 0) { s = Object.assign({}, s, { bl: 2 }); }
    }
    // sick: red nose + tired eyes
    const sick = (D.fx && D.fx.sick || []).some(z => z.who === c.w && t >= z.t0 && t < z.t1);
    c.nose.material = sick ? M([226, 92, 92]) : c.noseMat;
    // ---- face
    const bl = s.bl || 0;
    let open = e[2] * (bl === 2 ? 0.08 : bl === 1 ? 0.45 : 1);
    if (sl > 0.4) open = 0.06;
    c.eyes.forEach((ey, k) => {
      ey.eg.scale.y = clamp(open, 0.06, 1.35); ey.eg.scale.x = s.emo === "surprised" ? 1.12 : 1;
      ey.pup.position.x = look * c.hr * 0.07; ey.pup.position.y = -(s.ly || 0) * c.hr * 0.05;
      ey.lid.visible = open < 0.95; ey.lid.position.y = c.hr * 0.22 * clamp(open, 0, 1);
      if (open < 0.5 && (s.emo === "laugh" || s.emo === "happy")) ey.eg.position.y = c.hr * 0.03; else ey.eg.position.y = c.hr * 0.06;
    });
    c.brows.forEach((b, k) => {
      const sd = k ? 1 : -1; // k=1 right side of face (+x)
      let ang = e[0] * sd, raise = e[1];
      if (e[5] === 1 && sd > 0) { raise += 0.015; ang -= 0.25 * sd; }
      if (e[5] === 2) { raise += sd > 0 ? 0.018 : -0.004; }
      if (speaking && s.emo !== "angry") raise += 0.004 * Math.sin(t * 9);
      b.rotation.z = ang; b.position.y = c.hr * 0.33 + raise * (c.hr / 0.165);
    });
    // mouth
    let q = s.q || 0; q = Math.max(q, e[4] && (s.emo === "laugh" ? (Math.sin(t * 14) * 0.5 + 0.5) * 2 + 2 : e[4]) || 0);
    if (s.emo === "laugh" && !speaking) q = Math.max(q, 2.5 + Math.sin(t * 14));
    const mo = clamp(q / 5, 0, 1);
    const wide = s.sh ? 0.8 : 1.12;
    if (mo > 0.06) {
      c.mOpen.visible = true; c.smile.visible = false;
      c.mOpen.scale.set(wide * (0.9 + (e[3] > 0.5 ? 0.3 : 0)), 0.18 + mo * 0.9, 0.3);
      if (s.emo === "surprised" && !speaking) c.mOpen.scale.set(0.6, 0.9, 0.5);
      c.teeth.visible = mo > 0.25; c.tongue.visible = mo > 0.45;
      c.teeth.position.y = c.hr * (0.01 + mo * 0.1); c.tongue.position.y = -c.hr * (0.01 + mo * 0.06);
    } else {
      c.mOpen.visible = false; c.teeth.visible = false; c.tongue.visible = false; c.smile.visible = true;
      const sm = e[3];
      c.smile.rotation.z = sm >= 0 ? Math.PI : 0;
      c.smile.scale.set(0.6 + Math.abs(sm) * 0.5, 0.35 + Math.abs(sm) * 0.55, 1);
      c.smile.position.y = sm >= 0 ? c.hr * 0.06 : -c.hr * 0.06;
      if (e[5] === 1) c.smile.rotation.z += 0.25;
      if (s.emo === "chew") { c.smile.scale.set(0.4, 0.25, 1); }
    }
    c.puffs.forEach((p, k) => { p.visible = c.sneezeU > 0.02; if (p.visible) { const u = 1 - c.sneezeU; const a = (k - 2.5) * 0.35; p.position.set(Math.sin(a) * u * c.hr * 1.6, -c.hr * 0.35 + Math.cos(k * 1.7) * u * c.hr * 0.5, c.hr * (1.0 + u * 2.2)); p.scale.setScalar(0.5 + u * 1.4); p.material.opacity = 0.75 * c.sneezeU; } });
    if (c.cheeks) c.cheeks.forEach(ch => ch.scale.set(s.emo === "chew" ? 1.6 : 1, s.emo === "chew" ? 1.2 : 0.6, s.emo === "chew" ? 0.9 : 0.3));
    // ---- arms
    const seated = stand < 0.5;
    const A = poseTargets(cur, s.face, seated), B = poseTargets(prv, s.face, seated);
    const shY = L.torso + br * 0.5;
    const flags = A.flags || "";
    const tn = B.n.clone().lerp(A.n, blendU), tf = B.f.clone().lerp(A.f, blendU);
    // gesture life
    const tt = t - s.tc;
    if (flags.includes("wave")) tn.x += Math.sin(t * 11) * 0.05 * s.face;
    if (flags.includes("wag")) { tn.x += Math.sin(t * 13) * 0.035; }
    if (flags.includes("clap")) { const k = Math.abs(Math.sin(t * 9)); tn.x = s.face * (0.02 + 0.07 * k); tf.x = -s.face * (0.02 + 0.07 * k); }
    if (flags.includes("explain")) { tn.y += Math.sin(t * 4) * 0.03; tf.y += Math.sin(t * 4 + 1) * 0.025; }
    if (flags.includes("walk")) { tn.z += walkA * 0.18; tf.z -= walkA * 0.18; }
    if (speaking && !flags.includes("wave") && !flags.includes("clap") && cur !== "rest_stand" && cur !== "rest_sofa") tn.y += Math.sin(t * 5.5) * 0.012 * (1 + q * 0.2);
    if (flags.includes("shrug")) c.torso.position.y = 0.02 * blendU; else c.torso.position.y = 0;
    const tgt = [tf, tn]; // index by side: near side = sign(face)
    c.arms.forEach(ar => {
      const isNear = ar.s === s.face;
      const T0 = (isNear ? tn : tf).clone().add(V(0, shY, 0));
      const S = V(ar.s * L.sh * 1.05, shY - 0.03, 0);
      // keep hands outside the torso
      if (Math.abs(T0.x) < 0.14 && T0.z < 0.16 && T0.y < shY && T0.y > 0) T0.z = 0.18;
      const elbowsOut = flags.includes("elbows");
      const pole = elbowsOut ? V(ar.s, 0.0, -0.4) : V(ar.s * 0.45, -1, -0.55);
      const [E, Hh] = ik(S, T0, L.ua, L.fa, pole.normalize());
      place(ar.ua, S, E); place(ar.fa, E, Hh); ar.elb.position.copy(E);
      if (ar.cuff) { ar.cuff.position.copy(Hh.clone().lerp(E, 0.12)); ar.cuff.quaternion.copy(ar.fa.quaternion); }
      ar.hand.position.copy(Hh);
      const dirv = new T.Vector3().subVectors(Hh, E).normalize();
      ar.hand.quaternion.setFromUnitVectors(UP, dirv);
      const fingerOn = (isNear && flags.includes("finger")) || (!isNear && flags.includes("farfinger"));
      ar.finger.visible = fingerOn && blendU > 0.5;
      ar.isNear = isNear;
    });
    // ---- prop
    const pname = s.prop || null;
    if (pname !== c.curProp) {
      if (c.propObj) { c.propObj.parent.remove(c.propObj); c.propObj = null; }
      if (pname) { c.propObj = makeProp(pname); }
      c.curProp = pname;
    }
    if (c.propObj) {
      const inNear = NEAR_PROPS[cur] || pname === "cup" && (cur === "hold" || cur === "explain" && false);
      const arm = c.arms.find(a => a.isNear === !!inNear) || c.arms[0];
      if (c.propObj.parent !== arm.hand) arm.hand.add(c.propObj);
      c.propObj.position.set(0, 0, 0);
      // props keep world-up orientation (cup stays upright, bat hangs down)
      const q = new T.Quaternion(); arm.hand.getWorldQuaternion(q); const inv = q.invert();
      const wq = new T.Quaternion();
      if (pname === "bat") { // bat: blade down along the arm when hanging, slight angle
        const rq = new T.Quaternion().setFromEuler(new T.Euler(0.15, 0, s.face * -0.12));
        c.root.getWorldQuaternion(wq); wq.multiply(rq);
      } else { c.root.getWorldQuaternion(wq); }
      c.propObj.quaternion.copy(inv.multiply(wq));
      if (pname === "cup") { c.propObj.position.set(0, 0.0, 0.0); c.propObj.userData.steam.forEach((p, k) => { const u = ((t * 0.6 + k / 3) % 1); p.position.set(0.0 + Math.sin(t * 3 + k) * 0.012, 0.11 + u * 0.16, 0.03); p.material.opacity = 0.55 * (1 - u); p.scale.setScalar(0.6 + u); }); }
      if (pname === "book") c.propObj.position.set(0, -0.02, 0);
    }
    // ---- alpha (fade in at door)
    const al = s.al === undefined ? 1 : s.al;
    c.root.visible = al > 0.02;
  }

  // ------------------------------------------------------------------ sets
  function addCeilingFan(p, x, y, z, col = [90, 70, 60]) {
    const g = new T.Group(); g.position.set(x, y, z); p.add(g);
    cyl(0.02, 0.02, 2.0, 5, [70, 70, 70], 0, 1.0, 0, g);
    cyl(0.12, 0.1, 0.12, 8, [200, 200, 205], 0, 0, 0, g);
    const bl = new T.Group(); g.add(bl);
    for (let k = 0; k < 3; k++) { const b = box(0.7, 0.012, 0.13, col, 0.42, -0.02, 0); const h = new T.Group(); h.rotation.y = k * 2.094; h.add(b); bl.add(h); }
    return bl;
  }

  function buildAangan(time) {
    const g = new T.Group();
    const ev = time === "evening";
    gradientSky(ev ? [70, 80, 150] : [90, 160, 230], ev ? [240, 150, 120] : [170, 210, 240], ev ? [255, 196, 120] : [230, 240, 245], g);
    // sun
    const sun = new T.Mesh(new T.CircleGeometry(1.2, 10), new T.MeshBasicMaterial({ color: ev ? 0xffc070 : 0xfff2b0, fog: false })); sun.position.set(-4.5, 4.2, -13.5); g.add(sun);
    // distant rooftops
    const roofCols = ev ? [[196, 150, 150], [180, 140, 150], [210, 170, 150], [170, 130, 140]] : [[230, 215, 190], [210, 195, 175], [240, 225, 200]];
    for (let k = 0; k < 14; k++) {
      const w = 1.4 + hash(k, 1, 2) * 1.6, h = 1.8 + hash(k, 3, 1) * 2.4, x = -9 + k * 1.45;
      box(w, h, 1.5, roofCols[k % roofCols.length], x, h / 2, -7 - hash(k, 2, 2) * 2, g);
      if (k % 3 === 0) { cyl(0.32, 0.32, 0.5, 7, [60, 60, 70], x + 0.2, h + 0.25, -7, g); }
    }
    // clouds
    const clouds = [];
    for (let k = 0; k < 5; k++) {
      const cg = new T.Group(); cg.position.set(-8 + k * 4, 6.5 + hash(k, 4, 4) * 2, -12); g.add(cg);
      for (let j = 0; j < 4; j++) { const cl = mesh(jitter(new T.IcosahedronGeometry(0.6 + j % 2 * 0.25, 0), 0.15), new T.MeshBasicMaterial({ color: ev ? 0xffd2b0 : 0xffffff, fog: false }), false, false); cl.position.set(j * 0.6, (j % 2) * 0.2, 0); cg.add(cl); }
      clouds.push(cg);
    }
    // ground
    const gr = mesh(jitter(new T.PlaneGeometry(14, 12, 28, 24), 0.04), M([222, 190, 140])); gr.rotation.x = -Math.PI / 2; gr.position.set(0, 0, -1); g.add(gr);
    // brick floor patch around charpai
    const tiles = [];
    for (let i = -6; i <= 6; i++) for (let j = -5; j <= 2; j++) tiles.push([i * 0.4, 0.01, j * 0.4 + 0.1, (i + j) % 2 ? [196, 120, 90] : [184, 108, 80]]);
    instBoxes(tiles, 0.38, 0.02, 0.38, g);
    // back brick wall
    const WZ = -2.6;
    box(10, 2.7, 0.3, [190, 110, 80], 0, 1.35, WZ - 0.02, g);
    const br = [];
    for (let r = 0; r < 18; r++) for (let k = 0; k < 34; k++) {
      const x = -5 + k * 0.3 + (r % 2) * 0.15, y = 0.08 + r * 0.15;
      if (x > 0.7 && x < 2.2 && y < 2.3) continue; // gate opening
      const sh = hash(r, k, 1);
      br.push([x, y, WZ + 0.14, sh > 0.7 ? [178, 92, 66] : sh > 0.35 ? [200, 112, 80] : [214, 128, 92]]);
    }
    instBoxes(br, 0.28, 0.13, 0.05, g);
    box(10.2, 0.12, 0.42, [230, 220, 200], 0, 2.76, WZ, g); // wall top
    // side wall (left)
    box(0.3, 2.7, 6, [196, 116, 84], -4.6, 1.35, -0.1, g);
    // gate (green, right)
    const gate = new T.Group(); gate.position.set(1.45, 0, WZ + 0.05); g.add(gate);
    box(1.6, 0.12, 0.12, [50, 110, 70], 0, 2.32, 0, gate);
    [-1, 1].forEach(s => { box(0.08, 2.4, 0.12, [50, 110, 70], s * 0.78, 1.18, 0, gate); });
    const doorL = new T.Group(); doorL.position.set(-0.74, 0, 0.02); gate.add(doorL);
    const doorR = new T.Group(); doorR.position.set(0.74, 0, 0.02); gate.add(doorR);
    [[doorL, 1], [doorR, -1]].forEach(([d, s]) => { box(0.74, 2.15, 0.05, [60, 140, 85], s * 0.37, 1.1, 0, d); for (let k = 0; k < 5; k++) box(0.02, 1.0, 0.07, [40, 100, 60], s * (0.08 + k * 0.13), 1.5, 0.01, d); box(0.7, 0.05, 0.07, [40, 100, 60], s * 0.37, 1.0, 0.01, d); });
    // neem tree
    const tree = new T.Group(); tree.position.set(-2.6, 0, -1.7); g.add(tree);
    cyl(0.16, 0.24, 2.4, 7, [110, 80, 55], 0, 1.2, 0, tree);
    const br1 = cyl(0.08, 0.12, 1.3, 6, [110, 80, 55], 0.4, 2.6, 0.1, tree); br1.rotation.z = -0.6;
    const br2 = cyl(0.07, 0.1, 1.1, 6, [110, 80, 55], -0.35, 2.5, -0.1, tree); br2.rotation.z = 0.6;
    const crown = new T.Group(); crown.position.y = 3.0; tree.add(crown);
    const greens = [[86, 150, 70], [70, 132, 60], [104, 166, 80], [60, 120, 56]];
    [[0, 0.3, 0, 1.2], [1.0, 0.0, 0.2, 0.9], [-0.9, -0.1, 0.1, 0.9], [0.4, 0.9, -0.2, 0.85], [-0.4, 0.8, 0.3, 0.8], [1.6, -0.4, 0.5, 0.7], [0.2, -0.3, 0.7, 0.75]].forEach((p, k) => {
      const f = mesh(jitter(new T.IcosahedronGeometry(p[3], 1), 0.25), M(greens[k % 4])); f.position.set(p[0], p[1], p[2]); crown.add(f);
    });
    // charpai
    const ch = new T.Group(); ch.position.set(0, 0, -0.42); g.add(ch);
    const wood = [150, 96, 56];
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz]) => { cyl(0.05, 0.04, 0.42, 6, [120, 70, 40], sx * 1.0, 0.21, sz * 0.42, ch); ico(0.06, [190, 60, 60], 0, sx * 1.0, 0.3, sz * 0.42, ch); });
    box(2.12, 0.07, 0.07, wood, 0, 0.43, -0.44, ch); box(2.12, 0.07, 0.07, wood, 0, 0.43, 0.44, ch);
    box(0.07, 0.07, 0.95, wood, -1.03, 0.43, 0, ch); box(0.07, 0.07, 0.95, wood, 1.03, 0.43, 0, ch);
    const weave = [];
    for (let i = 0; i < 26; i++) weave.push([-0.96 + i * 0.077, 0.445, 0, (i % 6 < 3) ? [235, 225, 200] : [200, 70, 70], 1, 1, 1]);
    instBoxes(weave, 0.05, 0.02, 0.86, ch);
    const weave2 = [];
    for (let j = 0; j < 11; j++) weave2.push([0, 0.455, -0.4 + j * 0.08, j % 4 < 2 ? [240, 232, 210] : [230, 180, 70]]);
    instBoxes(weave2, 1.98, 0.012, 0.035, ch);
    // clothesline with clothes
    const lineY = 2.1, lz = -2.0;
    cyl(0.04, 0.05, 2.15, 6, [90, 80, 70], -3.4, 1.07, lz, g);
    const ln = mesh(new T.CylinderGeometry(0.006, 0.006, 1, 4), M([240, 240, 240])); place(ln, V(-3.4, lineY, lz), V(0.55, lineY + 0.05, WZ + 0.18)); g.add(ln);
    const clothes = [];
    [[-2.9, [220, 70, 70], "shirt"], [-2.2, [245, 245, 240], "shirt"], [-1.55, [80, 130, 200], "shirt"], [-0.9, [250, 170, 60], "dupatta"], [-0.25, [150, 90, 170], "shirt"]].forEach(([x, col, kind], k) => {
      const u = (x + 3.4) / 3.95; const y = lerp(lineY, lineY + 0.05, u) - 0.02, z = lerp(lz, WZ + 0.18, u);
      const piv = new T.Group(); piv.position.set(x, y, z); g.add(piv);
      if (kind === "shirt") { box(0.42, 0.5, 0.02, col, 0, -0.27, 0, piv); box(0.66, 0.14, 0.02, col, 0, -0.08, 0, piv); }
      else { box(0.32, 0.9, 0.015, col, 0, -0.45, 0, piv); for (let j = 0; j < 4; j++) box(0.32, 0.03, 0.02, [200, 60, 90], 0, -0.86 + j * 0.0, 0.0, piv); }
      ico(0.02, [240, 200, 60], 0, 0, 0.0, 0.01, piv);
      clothes.push(piv);
    });
    // water matka on stand, plant pots, bulb
    const mk = new T.Group(); mk.position.set(3.0, 0, -2.0); g.add(mk);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => { const l = cyl(0.02, 0.02, 0.6, 4, [80, 80, 80], a * 0.18, 0.3, b * 0.18, mk); });
    box(0.45, 0.03, 0.45, [80, 80, 80], 0, 0.6, 0, mk);
    const pot = mesh(jitter(new T.SphereGeometry(0.3, 8, 6), 0.01), M([186, 96, 60])); pot.scale.y = 0.95; pot.position.y = 0.88; mk.add(pot);
    cyl(0.12, 0.16, 0.12, 8, [170, 86, 54], 0, 1.18, 0, mk);
    box(0.24, 0.02, 0.24, [130, 130, 140], 0, 1.25, 0, mk);
    [[-3.7, -2.1, [80, 150, 70]], [2.3, -2.2, [100, 160, 80]], [3.7, 0.4, [70, 140, 70]]].forEach(([x, z, col]) => {
      cyl(0.22, 0.16, 0.4, 7, [196, 106, 66], x, 0.2, z, g);
      for (let j = 0; j < 4; j++) { const lf = mesh(jitter(new T.IcosahedronGeometry(0.22, 0), 0.06), M(col)); lf.position.set(x + Math.sin(j * 1.6) * 0.15, 0.55 + j * 0.08, z + Math.cos(j * 1.6) * 0.12); g.add(lf); }
    });
    const bulb = new T.Mesh(new T.IcosahedronGeometry(0.07, 1), new T.MeshBasicMaterial({ color: 0xfff1b0 })); bulb.position.set(-0.4, 2.45, WZ + 0.2); g.add(bulb);
    box(0.02, 0.15, 0.02, [60, 60, 60], -0.4, 2.56, WZ + 0.2, g);
    if (ev) { const pl = new T.PointLight(0xffd090, 1.6, 6, 1.5); pl.position.set(-0.4, 2.3, WZ + 0.5); g.add(pl); }
    // wind leaves
    const leaves = [];
    for (let k = 0; k < 26; k++) { const lf = mesh(new T.TetrahedronGeometry(0.04, 0), M(k % 3 ? [110, 160, 70] : [190, 170, 80]), false, false); g.add(lf); leaves.push({ o: lf, s: hash(k, 7, 3), y: 0.4 + hash(k, 1, 9) * 2.4, z: -2 + hash(k, 5, 5) * 4 }); }
    const lights = lightRig(g, ev ? { sky: [170, 160, 230], ground: [200, 150, 110], hemi: 0.85, sun: [255, 190, 130], sunI: 2.0, sunPos: [-6, 6, 5], fill: [255, 220, 200], fillI: 0.35 }
      : { sky: [200, 225, 255], ground: [220, 190, 150], hemi: 1.0, sun: [255, 245, 220], sunI: 2.2, sunPos: [-4, 8, 5] });
    const fog = new T.Fog(ev ? 0xf0b090 : 0xdfe9f0, 14, 30);
    const anim = (t, wind) => {
      crown.rotation.z = Math.sin(t * 1.3) * 0.02 * (1 + wind) + wind * 0.02; crown.rotation.x = Math.sin(t * 0.9) * 0.012 * (1 + wind);
      clothes.forEach((c, k) => { c.rotation.x = -0.15 * wind - (0.12 + 0.25 * wind) * Math.abs(Math.sin(t * (2.2 + k * 0.3) + k)); c.rotation.z = Math.sin(t * 1.7 + k) * 0.06 * (1 + wind); });
      clouds.forEach((c, k) => { c.position.x = -9 + ((k * 4 + t * 0.12) % 20); });
      leaves.forEach((l, k) => { const sp = 0.6 + l.s * 0.8 + wind * 1.6; const x = -5 + ((l.s * 10 + t * sp) % 10); l.o.position.set(x, l.y + Math.sin(t * 2 + k) * 0.25, l.z); l.o.rotation.set(t * 3 + k, t * 2, t * 4); l.o.visible = true; });
      doorL.rotation.y = 0; doorR.rotation.y = 0;
    };
    const slots = { charpai_l: { x: -0.48, z: -0.25, seatY: 0.47 }, charpai_c: { x: 0, z: -0.25, seatY: 0.47 }, charpai_r: { x: 0.48, z: -0.25, seatY: 0.47 },
      stand_l: { x: -1.4, z: 0.75 }, stand_r: { x: 1.25, z: 0.55 }, stand_c: { x: 0.0, z: 0.95 }, floor_l: { x: -0.8, z: 1.1 }, floor_r: { x: 0.8, z: 1.1 } };
    return { g, slots, door: { x: 1.45, z: WZ + 0.3 }, anim, fog, gate: [doorL, doorR], windy: true, bg: ev ? 0xf0b090 : 0xdfe9f0 };
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

  function buildBedroom(time) {
    const g = new T.Group();
    const WZ = -1.75;
    // floor tiles
    const tl = [];
    for (let i = -6; i <= 6; i++) for (let j = -3; j <= 6; j++) tl.push([i * 0.5, -0.01, WZ + 0.25 + j * 0.5, (i + j) % 2 ? [226, 220, 208] : [212, 206, 194]]);
    instBoxes(tl, 0.49, 0.02, 0.49, g);
    // walls
    box(7, 5.0, 0.12, [178, 208, 232], 0, 2.5, WZ - 0.06, g);
    box(0.12, 5.0, 5.5, [168, 198, 224], -2.6, 2.5, WZ + 2.7, g);
    box(7, 0.08, 0.05, [250, 250, 250], 0, 3.0, WZ + 0.0, g);
    box(7, 0.14, 0.04, [150, 180, 210], 0, 0.07, WZ + 0.02, g); // skirting
    const fan = addCeilingFan(g, 0.3, 3.0, -0.6);
    // window with sky
    const win = new T.Group(); win.position.set(-1.05, 1.75, WZ + 0.02); g.add(win);
    const sky = canvasTex(256, 256, (x, w, h) => { const gr = x.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#6fb6f0"); gr.addColorStop(1, "#cfe9fb"); x.fillStyle = gr; x.fillRect(0, 0, w, h); x.fillStyle = "#ffe27a"; x.beginPath(); x.arc(190, 70, 34, 0, 7); x.fill(); x.fillStyle = "#fff"; [[60, 120], [95, 112], [130, 124]].forEach(([a, b]) => { x.beginPath(); x.arc(a, b, 24, 0, 7); x.fill(); }); });
    const pane = new T.Mesh(new T.PlaneGeometry(1.0, 1.1), new T.MeshBasicMaterial({ map: sky })); pane.position.z = 0.02; win.add(pane);
    box(1.12, 0.08, 0.1, [250, 250, 250], 0, 0.59, 0.03, win); box(1.12, 0.1, 0.16, [250, 250, 250], 0, -0.59, 0.05, win);
    box(0.08, 1.2, 0.1, [250, 250, 250], -0.56, 0, 0.03, win); box(0.08, 1.2, 0.1, [250, 250, 250], 0.56, 0, 0.03, win); box(0.05, 1.1, 0.06, [250, 250, 250], 0, 0, 0.04, win);
    [-1, 1].forEach(s => { const cu = box(0.28, 1.45, 0.05, [240, 170, 70], s * 0.72, -0.05, 0.12, win); for (let k = 0; k < 3; k++) box(0.04, 1.45, 0.07, [220, 140, 50], s * 0.72 + (k - 1) * 0.08, -0.05, 0.13, win); });
    box(1.8, 0.04, 0.04, [140, 100, 70], 0, 0.78, 0.16, win);
    // cricket poster
    const poster = canvasTex(200, 280, (x, w, h) => { x.fillStyle = "#1f7a45"; x.fillRect(0, 0, w, h); x.save(); x.translate(100, 140); x.rotate(-0.6); x.fillStyle = "#e9c98a"; x.fillRect(-14, -100, 28, 150); x.fillStyle = "#6b4a30"; x.fillRect(-5, 50, 10, 50); x.restore(); x.fillStyle = "#d63a3a"; x.beginPath(); x.arc(150, 70, 18, 0, 7); x.fill(); x.fillStyle = "#fff"; x.font = "bold 30px sans-serif"; x.fillText("CRICKET", 30, 255); });
    frameDeco(0.62, 0.86, poster, 0.15, 1.85, WZ + 0.03, g, [240, 240, 240]);
    // door
    const door = new T.Group(); door.position.set(0.95, 0, WZ + 0.03); g.add(door);
    box(1.0, 2.25, 0.06, [235, 230, 220], 0, 1.12, 0, door);
    const dp = new T.Group(); dp.position.set(-0.45, 0, 0.04); door.add(dp);
    box(0.9, 2.12, 0.05, [150, 96, 60], 0.45, 1.07, 0, dp);
    [[0.45, 1.55], [0.45, 0.6]].forEach(([a, b]) => box(0.7, 0.75, 0.02, [170, 112, 70], a, b, 0.03, dp));
    ico(0.035, [230, 200, 80], 0, 0.82, 1.05, 0.06, dp);
    // bed (headboard on the left)
    const bed = new T.Group(); bed.position.set(-1.6, 0, WZ + 0.95); g.add(bed);
    box(0.1, 1.15, 1.25, [130, 82, 50], -0.06, 0.58, 0, bed); box(0.14, 0.1, 1.3, [150, 96, 60], -0.06, 1.17, 0, bed);
    box(2.0, 0.28, 1.2, [140, 90, 55], 1.0, 0.22, 0, bed);
    [[0.0, -0.57], [0.0, 0.57], [1.97, -0.57], [1.97, 0.57]].forEach(([a, b]) => box(0.08, 0.12, 0.08, [110, 70, 40], a, 0.06, b, bed));
    const sheet = new T.Mesh(new T.BoxGeometry(1.95, 0.16, 1.22), [M([230, 225, 215]), M([230, 225, 215]), new T.MeshLambertMaterial({ map: sindhiTex("#b8323c", "#1c2c5a", "#f2c14e", 10) }), M([230, 225, 215]), new T.MeshLambertMaterial({ map: sindhiTex("#b8323c", "#1c2c5a", "#f2c14e", 2) }), M([230, 225, 215])]);
    sheet.position.set(1.0, 0.43, 0); sheet.castShadow = true; sheet.receiveShadow = true; bed.add(sheet);
    const pil = mesh(jitter(new T.BoxGeometry(0.38, 0.13, 0.7, 2, 1, 2), 0.02), M([250, 248, 240])); pil.position.set(0.25, 0.58, 0); bed.add(pil);
    // razai (maroon with mustard border + cream flowers)
    const rzT = canvasTex(256, 256, (x, w, h) => { x.fillStyle = "#b03048"; x.fillRect(0, 0, w, h); x.strokeStyle = "#e8b446"; x.lineWidth = 18; x.strokeRect(9, 9, w - 18, h - 18); x.fillStyle = "#faecd2"; for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) { const cx = 35 + i * 47, cy = 35 + j * 47; for (let k = 0; k < 5; k++) { x.beginPath(); x.arc(cx + 7 * Math.cos(k * 1.256), cy + 7 * Math.sin(k * 1.256), 5, 0, 7); x.fill(); } } });
    const rz = mesh(jitter(new T.BoxGeometry(1.35, 0.2, 1.05, 4, 1, 3), 0.03), new T.MeshLambertMaterial({ map: rzT, flatShading: true })); bed.add(rz);
    // desk + computer + chair
    const desk = new T.Group(); desk.position.set(1.95, 0, WZ + 0.45); g.add(desk);
    box(1.2, 0.05, 0.6, [170, 120, 80], 0, 0.76, 0, desk);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.05, 0.76, 0.05, [140, 96, 60], a * 0.55, 0.38, b * 0.26, desk));
    box(0.55, 0.36, 0.04, [40, 40, 50], 0, 1.14, -0.12, desk);
    const scr = new T.Mesh(new T.PlaneGeometry(0.5, 0.31), new T.MeshBasicMaterial({ color: 0x58b4f0 })); scr.position.set(0, 1.14, -0.098); desk.add(scr);
    box(0.06, 0.15, 0.06, [40, 40, 50], 0, 0.86, -0.12, desk); box(0.4, 0.02, 0.14, [230, 230, 235], 0, 0.79, 0.1, desk);
    const chair = new T.Group(); chair.position.set(1.85, 0, WZ + 1.05); g.add(chair);
    box(0.45, 0.05, 0.45, [60, 90, 160], 0, 0.46, 0, chair); box(0.45, 0.5, 0.05, [60, 90, 160], 0, 0.74, 0.22, chair);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.03, 0.46, 0.03, [80, 80, 90], a * 0.2, 0.23, b * 0.2, chair));
    box(0.32, 0.38, 0.14, [150, 80, 120], 0.0, 0.68, 0.0, chair); // school bag on chair
    // shelf with books
    box(1.0, 0.04, 0.22, [150, 100, 65], 1.95, 2.05, WZ + 0.12, g);
    const books = []; const bc = [[200, 60, 60], [60, 120, 200], [240, 190, 60], [70, 160, 90], [160, 90, 170]];
    for (let k = 0; k < 9; k++) books.push([1.55 + k * 0.09, 2.2 - (k % 3) * 0.02, WZ + 0.12, bc[k % 5], 1, 1 - (k % 3) * 0.12, 1]);
    instBoxes(books, 0.07, 0.28, 0.18, g, true);
    // bat leaning + ball on floor
    const bat = makeProp("bat"); bat.position.set(2.55, 0.8, WZ + 0.2); bat.rotation.z = 0.25; g.add(bat);
    ico(0.035, [200, 40, 40], 1, 2.3, 0.035, WZ + 0.55, g);
    // rug
    const rug = new T.Mesh(new T.BoxGeometry(1.8, 0.015, 1.1), new T.MeshLambertMaterial({ map: sindhiTex("#2d5f8a", "#e8c35a", "#c94a4a", 6) })); rug.position.set(0.3, 0.008, 0.55); rug.receiveShadow = true; g.add(rug);
    // slippers by the bed
    box(0.1, 0.03, 0.24, [60, 60, 70], -0.85, 0.015, 0.25, g); box(0.1, 0.03, 0.24, [60, 60, 70], -0.68, 0.015, 0.28, g);
    const lights = lightRig(g, { sky: [215, 230, 255], ground: [210, 200, 185], hemi: 1.05, sun: [255, 244, 215], sunI: 2.1, sunPos: [-3, 6, 6], fillI: 0.45 });
    const wl = new T.PointLight(0xfff0d0, 1.2, 5, 1.6); wl.position.set(-1.05, 1.8, WZ + 0.6); g.add(wl);
    const anim = (t) => { fan.rotation.y = t * 5; };
    const slots = { bed: { x: -0.75, z: WZ + 0.95 + 0.45, seatY: 0.53, lieZ: WZ + 0.95 }, desk: { x: 1.85, z: WZ + 1.0, seatY: 0.48 },
      stand_l: { x: 0.35, z: 0.25 }, stand_r: { x: 1.15, z: 0.55 }, stand_c: { x: 0.35, z: 0.45 }, floor_l: { x: -0.6, z: 1.1 }, floor_r: { x: 0.9, z: 1.1 } };
    return { g, slots, door: { x: 0.95, z: WZ + 0.35 }, anim, fog: new T.Fog(0xe8eef4, 12, 30), razai: rz, bed, doorPanel: dp, bg: 0xe8eef4 };
  }

  function buildLiving(time) {
    const g = new T.Group();
    const WZ = -1.6;
    // floor
    const tl = [];
    for (let i = -6; i <= 6; i++) for (let j = -2; j <= 7; j++) tl.push([i * 0.6, -0.01, WZ + 0.3 + j * 0.6, (i + j) % 2 ? [236, 226, 206] : [224, 212, 190]]);
    instBoxes(tl, 0.59, 0.02, 0.59, g);
    // walls + ceiling
    box(7.5, 5.0, 0.12, [246, 228, 196], 0, 2.5, WZ - 0.06, g);
    box(0.12, 5.0, 6, [238, 218, 186], -2.8, 2.5, WZ + 3, g);
    box(0.12, 5.0, 6, [238, 218, 186], 2.8, 2.5, WZ + 3, g);
    box(7.5, 0.1, 0.05, [196, 150, 110], 0, 3.0, WZ + 0.0, g);
    box(7.5, 0.16, 0.04, [196, 150, 110], 0, 0.08, WZ + 0.02, g);
    const fan = addCeilingFan(g, 0, 3.0, -0.4, [150, 110, 80]);
    // carpet
    const cT = canvasTex(512, 320, (x, w, h) => { x.fillStyle = "#a8242e"; x.fillRect(0, 0, w, h); x.strokeStyle = "#e9b949"; x.lineWidth = 16; x.strokeRect(14, 14, w - 28, h - 28); x.strokeStyle = "#1d2d5c"; x.lineWidth = 8; x.strokeRect(36, 36, w - 72, h - 72); x.fillStyle = "#e9b949"; for (let i = 0; i < 6; i++) for (let j = 0; j < 3; j++) { const cx = 90 + i * 66, cy = 90 + j * 70; x.beginPath(); x.moveTo(cx, cy - 22); x.lineTo(cx + 22, cy); x.lineTo(cx, cy + 22); x.lineTo(cx - 22, cy); x.fill(); x.fillStyle = "#1d2d5c"; x.fillRect(cx - 5, cy - 5, 10, 10); x.fillStyle = "#e9b949"; } });
    const carpet = new T.Mesh(new T.BoxGeometry(3.2, 0.015, 2.0), new T.MeshLambertMaterial({ map: cT })); carpet.position.set(0, 0.008, 0.85); carpet.receiveShadow = true; g.add(carpet);
    // sofa (maroon) with rilli cushions
    const sofa = new T.Group(); sofa.position.set(0, 0, WZ + 0.7); g.add(sofa);
    const maroon = [140, 40, 50], mar2 = [118, 30, 42];
    box(2.3, 0.3, 0.75, mar2, 0, 0.22, 0, sofa);
    [-0.7, 0, 0.7].forEach(x => { const cu = mesh(jitter(new T.BoxGeometry(0.68, 0.14, 0.68, 2, 1, 2), 0.015), M(maroon)); cu.position.set(x, 0.42, 0.04); sofa.add(cu); });
    box(2.3, 0.62, 0.2, maroon, 0, 0.68, -0.32, sofa);
    [-1, 1].forEach(s => { box(0.2, 0.36, 0.78, mar2, s * 1.2, 0.48, 0, sofa); const ar = cyl(0.11, 0.11, 0.78, 7, maroon, s * 1.2, 0.68, 0, sofa); ar.rotation.x = Math.PI / 2; });
    const rilli = sindhiTex("#f2e8d0", "#c0392b", "#1f6f8b", 4);
    [-0.75, 0.0, 0.75].forEach((x, k) => { const c = new T.Mesh(new T.BoxGeometry(0.42, 0.38, 0.1), [M([200, 60, 60]), M([200, 60, 60]), M([200, 60, 60]), M([200, 60, 60]), new T.MeshLambertMaterial({ map: rilli }), M([200, 60, 60])]); c.position.set(x, 0.78, -0.17); c.rotation.x = -0.2; c.rotation.z = (k - 1) * 0.06; c.castShadow = true; sofa.add(c); });
    // coffee table with fruit
    const tb = new T.Group(); tb.position.set(0.45, 0, 0.95); g.add(tb);
    box(0.9, 0.05, 0.5, [150, 96, 60], 0, 0.4, 0, tb);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => box(0.05, 0.4, 0.05, [120, 76, 46], a * 0.4, 0.2, b * 0.2, tb));
    cyl(0.17, 0.12, 0.05, 9, [245, 245, 245], 0.1, 0.45, 0, tb);
    [[0.05, 0.02, [240, 150, 40]], [0.15, -0.03, [220, 50, 50]], [0.12, 0.07, [240, 150, 40]], [0.2, 0.04, [120, 190, 60]]].forEach(([a, b, col]) => ico(0.045, col, 1, a, 0.5, b, tb));
    // wall decor: clock, family photo, window with curtains, door (right)
    const clk = canvasTex(128, 128, (x) => { x.fillStyle = "#fff"; x.beginPath(); x.arc(64, 64, 60, 0, 7); x.fill(); x.strokeStyle = "#333"; x.lineWidth = 6; x.stroke(); for (let k = 0; k < 12; k++) { x.fillStyle = "#333"; x.fillRect(64 + 48 * Math.cos(k * 0.5236) - 3, 64 + 48 * Math.sin(k * 0.5236) - 3, 6, 6); } x.lineWidth = 6; x.beginPath(); x.moveTo(64, 64); x.lineTo(64, 28); x.stroke(); x.lineWidth = 4; x.beginPath(); x.moveTo(64, 64); x.lineTo(92, 74); x.stroke(); });
    const ck = new T.Mesh(new T.CircleGeometry(0.22, 12), new T.MeshLambertMaterial({ map: clk })); ck.position.set(0.0, 2.45, WZ + 0.02); g.add(ck);
    cyl(0.24, 0.24, 0.03, 12, [150, 100, 60], 0, 2.45, WZ + 0.005, g).rotation.x = Math.PI / 2;
    const fam = canvasTex(256, 180, (x, w, h) => { x.fillStyle = "#cfe3ef"; x.fillRect(0, 0, w, h); const cols = ["#c0392b", "#2e8b57", "#e67e22", "#8e44ad", "#2c3e50"]; for (let k = 0; k < 5; k++) { const cx = 30 + k * 49; x.fillStyle = cols[k]; x.fillRect(cx - 16, 95, 32, 85); x.fillStyle = "#e0a878"; x.beginPath(); x.arc(cx, 78, 16, 0, 7); x.fill(); } });
    frameDeco(0.8, 0.56, fam, -0.95, 1.95, WZ + 0.03, g);
    const win = new T.Group(); win.position.set(-2.0, 1.75, WZ + 0.02); g.add(win);
    const sky = canvasTex(256, 256, (x, w, h) => { const gr = x.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#5fb0ee"); gr.addColorStop(1, "#d2ecfb"); x.fillStyle = gr; x.fillRect(0, 0, w, h); x.fillStyle = "#ffe27a"; x.beginPath(); x.arc(80, 70, 30, 0, 7); x.fill(); x.fillStyle = "#fff"; [[150, 140], [185, 130], [215, 145]].forEach(([a, b]) => { x.beginPath(); x.arc(a, b, 22, 0, 7); x.fill(); }); });
    const pane = new T.Mesh(new T.PlaneGeometry(0.9, 1.2), new T.MeshBasicMaterial({ map: sky })); pane.position.z = 0.02; win.add(pane);
    for (let k = -2; k <= 2; k++) box(0.025, 1.2, 0.05, [70, 70, 80], k * 0.2, 0, 0.04, win);
    box(1.0, 0.08, 0.12, [250, 250, 250], 0, 0.64, 0.03, win); box(1.0, 0.1, 0.16, [250, 250, 250], 0, -0.64, 0.05, win);
    [-1, 1].forEach(s => { box(0.3, 1.7, 0.05, [170, 40, 50], s * 0.62, -0.1, 0.12, win); for (let k = 0; k < 3; k++) box(0.04, 1.7, 0.07, [140, 30, 40], s * 0.62 + (k - 1) * 0.09, -0.1, 0.13, win); });
    const door = new T.Group(); door.position.set(1.85, 0, WZ + 0.03); g.add(door);
    box(1.05, 2.3, 0.06, [235, 225, 205], 0, 1.15, 0, door);
    const dp = new T.Group(); dp.position.set(-0.46, 0, 0.04); door.add(dp);
    box(0.92, 2.15, 0.05, [140, 88, 52], 0.46, 1.08, 0, dp);
    [[0.46, 1.6], [0.46, 0.6]].forEach(([a, b]) => box(0.72, 0.78, 0.02, [160, 104, 64], a, b, 0.03, dp));
    ico(0.035, [230, 200, 80], 0, 0.84, 1.05, 0.06, dp);
    // side table + lamp, plant
    box(0.45, 0.55, 0.45, [150, 96, 60], -1.65, 0.28, WZ + 0.55, g);
    cyl(0.05, 0.1, 0.3, 6, [220, 200, 160], -1.65, 0.7, WZ + 0.55, g);
    const shade = cyl(0.12, 0.2, 0.22, 7, [250, 230, 180], -1.65, 0.95, WZ + 0.55, g);
    cyl(0.2, 0.15, 0.38, 7, [196, 106, 66], 2.35, 0.19, WZ + 0.9, g);
    for (let j = 0; j < 6; j++) { const lf = mesh(jitter(new T.IcosahedronGeometry(0.2, 0), 0.06), M(j % 2 ? [70, 150, 70] : [90, 170, 80])); lf.position.set(2.35 + Math.sin(j * 1.2) * 0.14, 0.5 + j * 0.1, WZ + 0.9 + Math.cos(j * 1.2) * 0.1); g.add(lf); }
    const lights = lightRig(g, { sky: [230, 235, 255], ground: [220, 200, 170], hemi: 1.0, sun: [255, 238, 205], sunI: 2.0, sunPos: [-5, 6, 5], fillI: 0.45 });
    const anim = (t) => { fan.rotation.y = t * 5; };
    const slots = { sofa_l: { x: -0.7, z: WZ + 0.95, seatY: 0.5 }, sofa_c: { x: 0, z: WZ + 0.95, seatY: 0.5 }, sofa_r: { x: 0.7, z: WZ + 0.95, seatY: 0.5 },
      stand_l: { x: -1.45, z: 0.55 }, stand_r: { x: 1.35, z: 0.6 }, stand_cl: { x: -0.7, z: 0.75 }, stand_cr: { x: 0.75, z: 0.75 },
      floor_l: { x: -0.6, z: 0.75 }, floor_r: { x: 0.75, z: 1.3 } };
    return { g, slots, door: { x: 1.85, z: WZ + 0.35 }, anim, fog: new T.Fog(0xf3ead8, 12, 30), doorPanel: dp, bg: 0xf3ead8 };
  }

  // ------------------------------------------------------------------ camera
  function headWorld(c) { const v = new T.Vector3(); c.head.getWorldPosition(v); v.y += c.hr * c.sc * 1.0; return v; }
  function computeCam(F, set) {
    const cam = F.cam; const ws = cam.ws.filter(w => CHARS[w] && CHARS[w].root.visible);
    const pts = ws.map(w => ({ w, h: headWorld(CHARS[w]), c: CHARS[w] }));
    if (!pts.length) return { tx: 0, ty: 1.2, tz: 0, Hh: 3.4, yaw: 0, el: 0.16 };
    let minX = Infinity, maxX = -Infinity, top = -Infinity, sz = 0;
    pts.forEach(p => { minX = Math.min(minX, p.h.x); maxX = Math.max(maxX, p.h.x); top = Math.max(top, p.h.y + p.c.hr * p.c.sc * 1.1); sz += p.h.z; });
    sz /= pts.length;
    const kind = cam.kind; const u = cam.u || 0;
    const fitW = (maxX - minX) + (kind === "wide" ? 1.3 : kind === "group" ? 1.1 : 0.95);
    let Hh, el = 0.13, yaw = 0;
    if (kind === "wide") { Hh = Math.max(fitW * 16 / 9, 3.4) * (1 - 0.04 * u); el = 0.26; }
    else if (kind === "group") { Hh = Math.max(fitW * 16 / 9, 2.6) * (1 - 0.05 * u); el = 0.17; }
    else if (kind === "two") { Hh = Math.max(fitW * 16 / 9, 2.1) * (1 - 0.05 * u); el = 0.14; }
    else {
      const p = pts[0]; const small = p.c.d.toddler ? 0.62 : 1;
      Hh = (kind === "punch" ? lerp(1.75, 1.35, ease((cam.t_in || 0) / 0.35)) : 1.6 * (1 - 0.05 * u)) * small;
      el = 0.1; const st = F.ch[p.w]; yaw = clamp((st ? st.lx : 0) * 0.28, -0.3, 0.3);
      // something in front of the subject? swing the camera to the clear side
      Object.values(CHARS).forEach(o => { if (o === p.c || !o.root.visible) return; const hp = headWorld(o); if (hp.z > p.h.z + 0.25 && Math.abs(hp.x - p.h.x) < 0.65) yaw = (p.h.x >= hp.x ? 1 : -1) * 0.38; });
    }
    if (kind === "two" || kind === "group") { // swing slightly towards the speaker's side for depth
      const li = F.li; if (li !== null && li !== undefined) { const sp = D.lines[li].who; if (CHARS[sp] && CHARS[sp].root.visible) { const h = headWorld(CHARS[sp]); yaw = clamp((h.x - (minX + maxX) / 2) * 0.12, -0.12, 0.12); } }
    }
    const cx = (minX + maxX) / 2;
    let ty = top - Hh * 0.3;
    ty = Math.max(ty, Hh * 0.5 - (kind === "wide" ? 1.0 : 0.6));
    return { tx: cx, ty, tz: sz, Hh, yaw, el };
  }
  function applyCam(s) {
    const d = (s.Hh / 2) / Math.tan(FOV / 2 * Math.PI / 180);
    const dir = new T.Vector3(Math.sin(s.yaw) * Math.cos(s.el), Math.sin(s.el), Math.cos(s.yaw) * Math.cos(s.el));
    camera.position.set(s.tx, s.ty, s.tz).addScaledVector(dir, d);
    camera.lookAt(s.tx, s.ty - Math.sin(s.el) * 0.0, s.tz);
  }

  // ------------------------------------------------------------------ frame
  function slot3(set, name) { return set.slots[name] || { x: 0, z: 0.5 }; }
  function placeChar(c, s, set, t, si) {
    let x, z, slotInfo = {};
    if (s.m === "walk") {
      const dst = slot3(set, s.dst || "stand_r"); const src = s.fi ? set.door : s.src ? slot3(set, s.src) : set.door;
      const dd = s.fo ? set.door : dst;
      const u = ease(s.u);
      const sx = s.fo ? (s.src ? slot3(set, s.src).x : dst.x) : src.x, szz = s.fo ? (s.src ? slot3(set, s.src).z : dst.z) : src.z;
      const front = (o) => o.seatY ? o.z + 0.42 : o.z; // walk to the spot in front of a seat
      const ex = dd.x, ez = front(dd);
      x = lerp(sx, ex, u); z = lerp(s.fi ? szz : front({ z: szz, seatY: s.src && slot3(set, s.src).seatY }), ez, u);
      s.dir = Math.atan2(ex - sx, ez - szz);
      if (u > 0.85) s.dir = lerp(s.dir, 0, (u - 0.85) / 0.15);
    } else {
      slotInfo = slot3(set, s.slot);
      x = slotInfo.x; z = slotInfo.z;
      if (slotInfo.seatY) {
        const st = s.st; z = lerp(slotInfo.z, slotInfo.z + 0.42, st); // stand up in front of the seat
      }
      if (slotInfo.lieZ !== undefined && s.sl > 0) z = lerp(z, slotInfo.lieZ, s.sl);
    }
    c.root.position.set(x, 0, z);
    if (s.sl > 0 && slotInfo.seatY) { // lying on the bed, head on the pillow (to the left)
      c.body.rotation.z = (Math.PI / 2) * s.sl; c.body.position.x = lerp(0, -0.05, s.sl);
    } else { c.body.rotation.z = 0; c.body.position.x = 0; }
    updateChar(c, s, t, slotInfo);
    if (s.sl > 0 && slotInfo.seatY) c.body.position.y = lerp(c.body.position.y, slotInfo.seatY + 0.13, s.sl);
  }

  const LIGHTS = {};
  window.LP = {
    init(data) {
      D = data;
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
      // Zzz sprites
      const zt = canvasTex(64, 64, (x) => { x.fillStyle = "#3a4a9a"; x.font = "bold 54px sans-serif"; x.fillText("Z", 14, 52); });
      window._Z = [0, 1, 2].map(k => { const s = new T.Sprite(new T.SpriteMaterial({ map: zt, transparent: true })); s.scale.setScalar(0.16); scene.add(s); s.visible = false; return s; });
      return true;
    },
    test(w, st, setIdx, camS) { // debug: one character, given state, given camera
      const set = SETS[setIdx || 0];
      Object.values(SETS).forEach(s => s.g.visible = false); set.g.visible = true; scene.fog = set.fog; scene.background = new T.Color(set.bg); lastSi = -1;
      Object.values(CHARS).forEach(c => c.root.visible = false);
      const c = CHARS[w]; c.root.visible = true;
      const s = Object.assign({ emo: "calm", q: 0, sh: 0, bl: 0, lx: 0, ly: 0, face: 1, ang: 0, nod: 0, pose: "rest_stand", prev: "rest_stand", tc: -9, prop: null, al: 1, sl: 0, st: 1, m: "at", slot: "stand_c" }, st);
      placeChar(c, s, set, 5, 0); scene.updateMatrixWorld(true);
      const h = headWorld(c);
      applyCam(Object.assign({ tx: h.x, ty: h.y - 0.35, tz: h.z, Hh: 1.0, yaw: 0, el: 0.08 }, camS || {}));
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL("image/jpeg", 0.9);
    },
    frame(i) {
      const F = D.frames[i]; const t = F.t; const si = F.si; const set = SETS[si];
      if (si !== lastSi) { Object.values(SETS).forEach(s => s.g.visible = false); set.g.visible = true; scene.fog = set.fog; scene.background = new T.Color(set.bg); lastSi = si; camState = null; }
      // wind strength (aangan): gusts near whoosh sounds at the start and the sneeze
      let wind = 0.6 + 0.4 * Math.sin(t * 0.7);
      set.anim(t, wind);
      Object.entries(CHARS).forEach(([w, c]) => {
        const s = F.ch[w];
        if (!s) { c.root.visible = false; return; }
        c.root.visible = true; placeChar(c, s, set, t, si);
      });
      // razai: covers the sleeper, slides to the lap when he sits up
      if (set.razai) {
        const sleeper = D.scenes[si].sleepers[0]; const s = sleeper && F.ch[sleeper];
        const sl = s ? s.sl : 0;
        set.razai.position.set(lerp(1.3, 1.45, 1 - sl), lerp(0.62, 0.6, 1 - sl), lerp(0.05, -0.32, 1 - sl));
        set.razai.scale.set(lerp(1.0, 0.75, 1 - sl), lerp(1, 1.5, 1 - sl), lerp(1, 0.5, 1 - sl));
        set.razai.rotation.y = lerp(0, 0.08, 1 - sl);
        const zs = window._Z;
        zs.forEach((z, k) => { z.visible = sl > 0.5; if (sl > 0.5) { const u = ((t * 0.5 + k / 3) % 1); const h = headWorld(CHARS[sleeper]); z.position.set(h.x + 0.15 + u * 0.25, h.y + 0.15 + u * 0.45, h.z); z.material.opacity = Math.sin(u * Math.PI); z.scale.setScalar(0.1 + u * 0.12); } });
      } else window._Z.forEach(z => z.visible = false);
      // doors swing open while someone walks in from them
      const walkers = Object.values(F.ch).filter(s => s.m === "walk" && (s.fi || s.fo));
      const op = walkers.length ? Math.max(...walkers.map(s => Math.sin(clamp(s.fi ? s.u * 1.6 : 1 - s.u, 0, 1) * Math.PI / 2 + 0.0))) : 0;
      if (set.doorPanel) set.doorPanel.rotation.y = -op * 1.3;
      if (set.gate) { set.gate[0].rotation.y = op * 1.2; set.gate[1].rotation.y = -op * 1.2; }
      // fade-in at the door: simple scale-in of opacity is costly, so characters appear in the doorway
      scene.updateMatrixWorld(true);
      const target = computeCam(F, set);
      const key = F.cam.kind + "|" + F.cam.key + "|" + si;
      if (!camState || key !== lastKey && !(F.cam.kind === "wide" && lastKey && lastKey.startsWith("wide") && lastKey.endsWith("|" + si))) camState = Object.assign({}, target);
      else { for (const k in target) camState[k] = lerp(camState[k], target[k], 0.18); }
      lastKey = key;
      applyCam(camState);
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL("image/jpeg", 0.93);
    },
  };
})();
