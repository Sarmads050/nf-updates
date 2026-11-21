"""Low-poly 3D renderer for "Sindhi Ghar Ki Kahani" (Blender 4.x, run headless).

Reads the acted timeline that engine.py exports (EXPORT_TL=...), builds low-poly sets + characters
from art.CHARS colours, poses them frame by frame and renders a PNG sequence. engine.py then puts
titles / captions / audio on top (LOWPOLY=<dir>).

usage: xvfb-run -a blender -b --python cartoon/lowpoly/scene3d.py -- <timeline.json> <out_dir> [fps=15] [res=720] [frames=a-b]
"""
import bpy, sys, os, math, json, random
from mathutils import Vector, Euler

argv = sys.argv[sys.argv.index("--") + 1:]
TL = json.load(open(argv[0]))
CHARS = {k: {kk: (tuple(vv) if isinstance(vv, list) and vv and isinstance(vv[0], (int, float)) else vv) for kk, vv in v.items()}
         for k, v in TL["chars"].items()}  # character colours / styles from the 2D series (art.CHARS)
OUTD = argv[1]
LPFPS = float(argv[2]) if len(argv) > 2 else 15.0
RES = int(argv[3]) if len(argv) > 3 else 720
RANGE = argv[4] if len(argv) > 4 else ""
os.makedirs(OUTD, exist_ok=True)
D = math.radians
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
SCN = bpy.context.scene


# ------------------------------------------------------------------ helpers
def lin(c):
    """sRGB 0-255 -> linear 0-1"""
    out = []
    for v in c[:3]:
        v = v / 255
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


MATS = {}


def mat(col, rough=0.75, emit=0.0, metal=0.0):
    key = (tuple(col), rough, emit, metal)
    if key in MATS:
        return MATS[key]
    m = bpy.data.materials.new(f"m{len(MATS)}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = lin(col)
        b.inputs["Emission Strength"].default_value = emit
    MATS[key] = m
    return m


def _finish(o, col, parent=None, name=None, **mk):
    if col is not None:
        o.data.materials.append(mat(col, **mk))
    for p in o.data.polygons:
        p.use_smooth = False  # faceted low-poly look
    if parent is not None:
        o.parent = parent
    if name:
        o.name = name
    return o


def box(size, loc, col, parent=None, rot=(0, 0, 0), **mk):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = size
    return _finish(o, col, parent, **mk)


def cyl(r, h, loc, col, parent=None, verts=8, rot=(0, 0, 0), r2=None, **mk):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=loc, rotation=rot)
    return _finish(bpy.context.object, col, parent, **mk)


def ico(r, loc, col, parent=None, sub=1, scale=(1, 1, 1), **mk):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, col, parent, **mk)


def empty(loc, parent=None, name="e"):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    if parent is not None:
        o.parent = parent
    return o


def coll(name):
    c = bpy.data.collections.new(name)
    SCN.collection.children.link(c)
    lc = bpy.context.view_layer.layer_collection.children[c.name]
    bpy.context.view_layer.active_layer_collection = lc
    return c


# ------------------------------------------------------------------ 2D -> 3D mapping
def depth(foot):
    return (1600 - foot) * 0.006          # sofa back (1360) ~ +1.4 m, front floor (1840) ~ -1.4 m


def X3(x, foot):
    return (x - 540) * 0.0056 * (1 + (1600 - foot) * 0.0006)


# ------------------------------------------------------------------ sets
def set_living(time):
    c = coll("set_living_room")
    wall, floor = (236, 214, 176), (170, 120, 80)
    box((9, 0.2, 5), (0, 2.6, 2.4), wall, rough=0.9)                      # back wall
    box((0.2, 6, 5), (-3.3, 0, 2.4), shade(wall, 0.92))                    # side walls
    box((0.2, 6, 5), (3.3, 0, 2.4), shade(wall, 0.92))
    box((9, 0.22, 0.5), (0, 2.48, 0.25), (150, 110, 80))                   # skirting
    box((9, 8, 0.1), (0, 0, -0.05), floor, rough=0.6)                      # floor
    for i in range(-6, 7):                                                 # floor planks
        box((0.02, 8, 0.01), (i * 0.45, 0, 0.002), shade(floor, 0.8))
    box((3.6, 2.2, 0.03), (0, -0.4, 0.016), (170, 30, 44))                 # sindhi rug
    box((3.2, 1.8, 0.035), (0, -0.4, 0.02), (196, 60, 60))
    for k in range(7):
        box((0.22, 0.22, 0.04), (-1.3 + k * 0.43, -0.4, 0.03), (40, 50, 110), rot=(0, 0, D(45)))
    # window with sky + bars + curtains (left)
    sky = (150, 200, 245) if time == "day" else (250, 170, 120)
    box((1.5, 0.05, 1.7), (-1.9, 2.5, 2.25), sky, emit=1.2)
    box((1.6, 0.12, 0.08), (-1.9, 2.48, 3.1), (120, 80, 50))
    box((1.6, 0.12, 0.08), (-1.9, 2.48, 1.4), (120, 80, 50))
    for k in range(6):
        box((0.03, 0.08, 1.7), (-2.55 + k * 0.26, 2.47, 2.25), (60, 60, 70))
    for sx in (-2.85, -0.95):
        box((0.35, 0.1, 2.6), (sx, 2.4, 2.1), (150, 25, 40))
    # door (right)
    box((1.0, 0.12, 2.3), (2.45, 2.5, 1.15), (130, 80, 45))
    box((0.8, 0.13, 0.9), (2.45, 2.49, 1.65), (150, 95, 55))
    ico(0.05, (2.05, 2.42, 1.1), (230, 190, 80), metal=0.8, rough=0.3)
    # wall clock + family photo
    cyl(0.25, 0.06, (0.4, 2.48, 3.3), (250, 250, 245), rot=(D(90), 0, 0), verts=10)
    box((0.02, 0.02, 0.18), (0.4, 2.44, 3.36), (40, 40, 40))
    box((0.6, 0.06, 0.5), (1.3, 2.48, 2.6), (120, 80, 50))
    box((0.5, 0.07, 0.4), (1.3, 2.47, 2.6), (240, 225, 200))
    # sofa (maroon) behind the sofa slots, with rilli cushions
    sy = depth(1360)
    box((3.4, 0.8, 0.34), (0, sy + 0.18, 0.17), (130, 30, 45))                  # seat base
    box((3.3, 0.7, 0.12), (0, sy + 0.15, 0.4), (160, 40, 55))                  # cushion
    box((3.4, 0.25, 0.75), (0, sy + 0.55, 0.75), (130, 30, 45))                 # back
    for sx in (-1.8, 1.8):
        box((0.25, 0.85, 0.65), (sx, sy + 0.18, 0.4), (120, 25, 40))           # arms
    rilli = [(230, 60, 50), (250, 200, 60), (40, 60, 140), (240, 240, 230), (40, 130, 80)]
    for k in range(3):
        cx = -1.25 + k * 1.25
        box((0.45, 0.14, 0.42), (cx + 0.55, sy + 0.4, 0.78), rilli[k % 5], rot=(D(-12), 0, D(4)))
        for j in range(4):
            box((0.12, 0.15, 0.12), (cx + 0.43 + (j % 2) * 0.24, sy + 0.32, 0.7 + (j // 2) * 0.17), rilli[(k + j + 1) % 5], rot=(D(-12), 0, D(45)))
    # low table with a plant
    box((0.9, 0.5, 0.06), (0.15, -0.9, 0.42), (150, 100, 60))
    for sx in (-0.3, 0.6):
        box((0.06, 0.06, 0.4), (sx, -0.9, 0.2), (130, 85, 50))
    cyl(0.1, 0.18, (-2.7, 1.9, 0.09), (190, 100, 60))
    ico(0.32, (-2.7, 1.9, 0.5), (60, 140, 70), sub=1)
    return c


def set_aangan(time):
    c = coll("set_aangan")
    brick, floor = (190, 100, 70), (200, 170, 130)
    box((10, 0.3, 3.2), (0, 3.0, 1.6), brick, rough=0.95)                 # boundary wall
    for row in range(10):
        for k in range(-8, 9):
            if random.random() < 0.35:
                box((0.5, 0.05, 0.14), (k * 0.6 + (row % 2) * 0.3, 2.84, 0.15 + row * 0.31), shade(brick, random.uniform(0.82, 1.12)))
    box((10, 0.4, 0.12), (0, 3.0, 3.25), (170, 85, 60))
    box((12, 10, 0.1), (0, 0, -0.05), floor, rough=0.9)                    # courtyard floor
    for i in range(-8, 9):
        box((0.02, 10, 0.01), (i * 0.6, 0, 0.002), shade(floor, 0.85))
    # green gate (right)
    box((1.4, 0.15, 2.4), (2.9, 2.85, 1.2), (40, 120, 70))
    for k in range(5):
        box((0.04, 0.17, 2.3), (2.35 + k * 0.28, 2.84, 1.2), (30, 95, 55))
    # neem tree (left)
    cyl(0.16, 3.2, (-2.9, 2.2, 1.6), (110, 75, 50), verts=7, r2=0.1)
    for (dx, dy, dz, r) in ((0, 0, 3.4, 0.9), (-0.6, 0.2, 3.0, 0.7), (0.6, -0.1, 3.1, 0.75), (0.1, 0.3, 3.9, 0.6)):
        ico(r, (-2.9 + dx, 2.2 + dy, dz), (70, 130, 60) if time == "day" else (60, 110, 55), sub=1)
    # clothesline with washing
    for sx in (-2.6, 2.2):
        cyl(0.03, 2.4, (sx, 2.5, 1.2), (90, 90, 95), verts=6)
    box((4.8, 0.02, 0.02), (-0.2, 2.5, 2.38), (220, 220, 220))
    for k, colr in enumerate(((220, 70, 60), (245, 240, 230), (70, 120, 190), (245, 240, 230))):
        box((0.5, 0.03, 0.6), (-1.9 + k * 1.1, 2.5, 2.05), colr, rot=(0, 0, D(random.uniform(-6, 6))))
    # charpai (woven cot) behind the charpai slots
    cy = depth(1465)
    for sx in (-1.45, 1.45):
        for sy_ in (cy - 0.05, cy + 0.85):
            cyl(0.06, 0.42, (sx, sy_, 0.21), (120, 75, 40), verts=6)
    box((3.0, 0.07, 0.08), (0, cy - 0.05, 0.42), (140, 90, 50))
    box((3.0, 0.07, 0.08), (0, cy + 0.85, 0.42), (140, 90, 50))
    box((2.9, 0.86, 0.04), (0, cy + 0.4, 0.42), (220, 190, 130))
    for k in range(14):
        box((0.02, 0.86, 0.045), (-1.4 + k * 0.215, cy + 0.4, 0.425), (190, 150, 95))
    # a matka in the corner
    ico(0.28, (2.0, 2.3, 0.35), (170, 90, 55), sub=1, scale=(1, 1, 1.1))
    cyl(0.12, 0.12, (2.0, 2.3, 0.68), (160, 85, 50), verts=8)
    return c


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


SETFN = {"living_room": set_living, "aangan": set_aangan}

# ------------------------------------------------------------------ characters
POSE = {  # near arm (fwd, out, elbow), far arm (fwd, out, elbow) in degrees
    "rest_stand": ((4, 8, 12), (4, 8, 12)), "rest_sofa": ((30, 6, 55), (30, 6, 55)), "rest": ((4, 8, 12), (4, 8, 12)),
    "hold_sofa": ((40, 4, 95), (30, 6, 55)), "hold": ((40, 6, 90), (4, 8, 12)),
    "phone_look": ((45, 6, 125), (25, 6, 50)), "point_other": ((80, 30, 8), (8, 8, 15)), "point_down": ((40, 20, 10), (6, 8, 12)),
    "wag": ((60, 10, 135), (8, 8, 15)), "explain": ((50, 28, 70), (45, 25, 70)), "facepalm": ((75, 0, 145), (8, 8, 15)),
    "arms_up": ((160, 35, 20), (160, 35, 20)), "beckon": ((70, 18, 100), (8, 8, 15)), "point_up": ((150, 28, 10), (8, 8, 15)),
    "cross": ((50, -25, 115), (48, -25, 115)), "hands_hips": ((8, 50, 120), (8, 50, 120)), "shrug": ((30, 45, 90), (30, 45, 90)),
    "chest": ((55, -10, 130), (8, 8, 15)), "wave": ((140, 30, 40), (8, 8, 15)), "think": ((60, -5, 140), (40, -15, 90)),
    "plead": ((70, 10, 70), (70, 10, 70)), "clap": ((70, -10, 80), (70, -10, 80)), "objection": ((150, 28, 10), (8, 8, 15)),
    "fist": ((80, 10, 120), (8, 8, 15)), "head_hold": ((120, 30, 140), (120, 30, 140)), "scratch_head": ((130, 25, 150), (8, 8, 15)),
    "tired": ((0, 4, 5), (0, 4, 5)), "newspaper": ((55, 10, 80), (55, 10, 80)), "read": ((55, 10, 80), (55, 10, 80)),
    "thumb_back": ((20, 40, 90), (8, 8, 15)), "give": ((70, 10, 20), (8, 8, 15)), "take": ((70, 10, 20), (8, 8, 15)),
    "walk": ((4, 8, 12), (4, 8, 12)),
}
EMO = {  # brow inner tilt (deg), eye open, smile (-1..1)
    "neutral": (0, 1.0, 0.2), "calm": (-3, 0.85, 0.4), "happy": (-8, 0.8, 1.0), "worried": (-22, 1.05, -0.5),
    "surprised": (-18, 1.25, 0.0), "teasing": (10, 0.65, 0.7), "sheepish": (-18, 0.85, 0.4), "laugh": (-10, 0.0, 1.0),
    "warm": (-8, 0.75, 0.8), "focused": (14, 0.85, 0.0), "angry": (24, 0.9, -0.7), "tired": (-6, 0.5, -0.1),
    "proud": (-6, 0.7, 0.7), "confused": (-16, 1.0, -0.2), "sad": (-22, 0.75, -0.7), "chew": (-3, 0.8, 0.2),
}

CH = {}


def build_char(key):
    C = CHARS[key]
    tod = C.get("toddler")
    sc = C.get("scale", 1.0) * (0.55 if tod else 1.0)
    bld = C.get("build", 1.0)
    col = coll("char_" + key)
    root = empty((0, 0, 0), name=key)
    root.scale = (sc, sc, sc)
    sk, sh, pa = C["skin"], C["shirt"], C["pants"]
    if pa == sh:
        pa = shade(pa, 0.88)
    hip_h = 0.86
    hips = empty((0, 0, hip_h), root, key + "_hips")
    cyl(0.17 * bld, 0.2, (0, 0, 0), pa, hips, verts=8)
    legs = []
    for sd in (-1, 1):
        th = empty((sd * 0.09, 0, -0.02), hips, f"{key}_thigh{sd}")
        cyl(0.085, 0.42, (0, 0, -0.21), pa, th, verts=7, r2=0.075 if not C.get("kameez") else 0.09)
        kn = empty((0, 0, -0.42), th, f"{key}_knee{sd}")
        cyl(0.075 if not C.get("kameez") else 0.088, 0.4, (0, 0, -0.2), pa, kn, verts=7, r2=0.062)
        shoe = (150, 95, 45) if C.get("kameez") else ((235, 235, 240) if tod else (60, 50, 48))
        box((0.13, 0.22, 0.07), (0, -0.05, -0.42), shoe, kn)
        legs.append((th, kn))
    torso = empty((0, 0, 0.08), hips, key + "_torso")
    # torso: tapered low-poly trunk; kameez flares down over the hips
    cyl(0.19 * bld, 0.58, (0, 0, 0.3), sh, torso, verts=8, r2=0.21 * bld)
    if C.get("belly"):
        ico(0.2 * bld, (0, -0.06, 0.22), sh, torso, sub=1, scale=(1, 0.9, 1))
    if C.get("kameez"):
        cyl(0.26 * bld, 0.42, (0, 0, -0.18), sh, torso, verts=8, r2=0.2 * bld)
        if C.get("embroidery"):  # sindhi gajj: gold/colour yoke with mirror bits
            th_, th2 = C["embroidery"]
            box((0.14, 0.02, 0.2), (0, -0.2 * bld, 0.46), th_, torso, rot=(D(-6), 0, 0))
            for k in range(4):
                ico(0.018, (-0.04 + (k % 2) * 0.08, -0.215 * bld, 0.52 - (k // 2) * 0.09), (240, 245, 255), torso, sub=1, metal=0.6, rough=0.2)
            box((0.52 * bld, 0.02, 0.05), (0, -0.25 * bld, -0.36), th_, torso, rot=(D(-8), 0, 0))
    col_ = C.get("collar")
    if col_ == "jersey":
        box((0.05, 0.02, 0.5), (0.17, -0.18, 0.3), C.get("shirt2", (240, 240, 240)), torso)
        box((0.05, 0.02, 0.5), (-0.17, -0.18, 0.3), C.get("shirt2", (240, 240, 240)), torso)
        cyl(0.05, 0.02, (0, -0.2, 0.36), C.get("shirt2", (240, 240, 240)), torso, rot=(D(90), 0, 0), verts=10)
    ex = C.get("extra", [])
    if "ajrak" in ex:  # wide ajrak shawl: red with indigo blocks + white dots, on both shoulders
        for sd in (-1, 1):
            sh_ = box((0.13, 0.03, 0.55), (sd * 0.13, -0.205, 0.33), (150, 28, 38), torso, rot=(D(-5), D(sd * 6), 0))
            for k in range(5):
                box((0.045, 0.02, 0.045), (sd * 0.13, -0.225, 0.52 - k * 0.1), (28, 36, 92), torso, rot=(0, D(45), 0))
                ico(0.01, (sd * 0.13, -0.24, 0.52 - k * 0.1), (240, 236, 226), torso, sub=1)
            box((0.14, 0.035, 0.03), (sd * 0.13, -0.21, 0.06), (28, 36, 92), torso)
        box((0.5, 0.25, 0.1), (0, 0.02, 0.6), (150, 28, 38), torso)
    if "waistcoat" in ex:
        for sd in (-1, 1):
            box((0.15 * bld, 0.03, 0.56), (sd * 0.11, -0.2 * bld, 0.3), (30, 30, 40), torso)
    if "lanyard" in ex:
        box((0.012, 0.02, 0.28), (-0.06, -0.205, 0.45), (30, 110, 200), torso, rot=(0, D(-12), 0))
        box((0.012, 0.02, 0.28), (0.06, -0.205, 0.45), (30, 110, 200), torso, rot=(0, D(12), 0))
        box((0.08, 0.02, 0.1), (0, -0.22, 0.28), (250, 250, 250), torso)
    if C.get("cover"):  # dupatta draped over shoulders and down the back
        cyl(0.24 * bld, 0.66, (0, 0.04, 0.28), C["cover"], torso, verts=8, r2=0.22 * bld)
        for sd in (-1, 1):
            box((0.07, 0.03, 0.6), (sd * 0.17 * bld, -0.19 * bld, 0.28), C["cover"], torso)
    # neck + head
    neck = empty((0, 0, 0.58), torso, key + "_neck")
    cyl(0.065, 0.08, (0, 0, 0.03), shade(sk, 0.9), neck, verts=7)
    head = empty((0, 0, 0.02), neck, key + "_head")
    hs = 1.32 * (1.2 if tod else 1.0)
    H = empty((0, 0, 0), head, key + "_hs")
    H.scale = (hs, hs, hs)
    hr = 0.17
    hc = C["hair_col"]
    ico(hr, (0, 0, 0.17), sk, H, sub=2, scale=(1.0, 0.95, 1.12))
    for sd in (-1, 1):  # ears
        ico(0.035, (sd * 0.17, 0.0, 0.16), shade(sk, 0.95), H, sub=1, scale=(0.6, 1, 1))
        if C.get("earrings"):
            ico(0.018, (sd * 0.17, -0.01, 0.1), (245, 200, 60), H, sub=1, metal=0.7, rough=0.3)
    cyl(0.022, 0.06, (0, -0.17, 0.14), shade(sk, 0.93), H, verts=5, rot=(D(80), 0, 0), r2=0.008)  # nose
    if C.get("nosepin"):
        ico(0.008, (0.022, -0.185, 0.125), (250, 215, 90), H, sub=1, metal=0.8)
    eyes = []
    for sd in (-1, 1):
        ew = ico(0.048, (sd * 0.066, -0.13, 0.2), (250, 250, 248), H, sub=2, scale=(1, 0.6, 1.15), rough=0.3)
        pup = empty((sd * 0.065, -0.155, 0.2), H, f"{key}_pup{sd}")
        ico(0.03, (0, -0.006, 0), C.get("iris", (92, 52, 28)), pup, sub=1, scale=(1, 0.5, 1.1), rough=0.2)
        ico(0.016, (0, -0.016, 0), (10, 8, 8), pup, sub=1, scale=(1, 0.5, 1), rough=0.1)
        ico(0.006, (0.009, -0.022, 0.01), (255, 255, 255), pup, sub=1, emit=2)
        lid = empty((sd * 0.065, -0.135, 0.245), H, f"{key}_lid{sd}")
        ico(0.053, (0, 0, -0.03), sk, lid, sub=2, scale=(1.05, 0.72, 0.6))
        brow = empty((sd * 0.065, -0.155, 0.27), H, f"{key}_brow{sd}")
        box((0.07, 0.015, 0.016), (0, 0, 0), C.get("brow_col", (36, 24, 20)), brow)
        eyes.append((ew, pup, lid, brow, sd))
    mouth = empty((0, -0.16, 0.075), H, key + "_mouth")
    ico(0.04, (0, 0, 0), (112, 28, 40), mouth, sub=1, scale=(1, 0.4, 0.4))
    teeth = box((0.05, 0.01, 0.012), (0, -0.012, 0.012), (250, 250, 250), mouth)
    smile = empty((0, -0.163, 0.08), H, key + "_smile")
    for sd in (-1, 1):
        box((0.035, 0.012, 0.01), (sd * 0.022, 0, 0.006), (90, 30, 35), smile, rot=(0, D(sd * 25), 0))
    if C.get("facial") == "mustache":
        box((0.13, 0.03, 0.03), (0, -0.168, 0.105), C["fh_col"], H)
        for sd in (-1, 1):
            box((0.04, 0.03, 0.03), (sd * 0.075, -0.162, 0.09), C["fh_col"], H, rot=(0, D(sd * -40), 0))
    if C.get("facial") == "beard":
        ico(hr * 1.02, (0, -0.01, 0.11), C["fh_col"], H, sub=2, scale=(1.0, 0.95, 0.62))
        ico(0.05, (0, -0.165, 0.075), sk, H, sub=1, scale=(1.2, 0.3, 0.7))
    if C.get("facial") == "light":
        ico(hr * 1.0, (0, -0.005, 0.12), shade(sk, 0.8), H, sub=2, scale=(1.0, 0.95, 0.55))
    if C.get("glasses"):
        for sd in (-1, 1):
            bpy.ops.mesh.primitive_torus_add(major_radius=0.05, minor_radius=0.008, major_segments=10, minor_segments=4,
                                             location=(sd * 0.065, -0.175, 0.2), rotation=(D(90), 0, 0))
            _finish(bpy.context.object, (30, 30, 40), H)
        box((0.04, 0.01, 0.008), (0, -0.178, 0.205), (30, 30, 40), H)
    hair = C["hair"]
    if hair in ("side", "neat"):
        ico(hr * 1.06, (0, 0.02, 0.24), hc, H, sub=1, scale=(1.02, 1.0, 0.75))
        box((0.2, 0.06, 0.06), (0.03, -0.12, 0.31), hc, H, rot=(D(-20), 0, D(-12)))
    elif hair == "curly":
        for k in range(14):
            a = 2 * math.pi * k / 14
            ico(0.055, (0.15 * math.cos(a), 0.05 + 0.1 * math.sin(a), 0.3 + 0.03 * math.sin(3 * a)), hc, H, sub=1)
        ico(hr, (0, 0.03, 0.27), hc, H, sub=1, scale=(1, 1, 0.75))
    elif hair == "spiky":
        ico(hr * 1.04, (0, 0.02, 0.24), hc, H, sub=1, scale=(1, 1, 0.7))
        for k in range(9):
            a = math.pi * (0.1 + 0.8 * k / 8)
            cyl(0.04, 0.12, (0.13 * math.cos(a) - 0.0, -0.02 + 0.04 * (k % 2), 0.33 + 0.04 * math.sin(a)), hc, H, verts=4, r2=0.0,
                rot=(D(-15), D(math.degrees(math.pi / 2 - a) * 0.6), 0))
    elif hair in ("tuft", "tuft2"):
        ico(hr * 1.02, (0, 0.03, 0.24), hc, H, sub=1, scale=(1, 1, 0.6))
        cyl(0.03, 0.09, (0.01, 0, 0.36), hc, H, verts=4, r2=0)
    elif hair == "topi":  # embroidered sindhi topi with front cut-out + white side hair
        cyl(0.18, 0.15, (0, 0.01, 0.33), (178, 30, 40), H, verts=10)
        cyl(0.182, 0.03, (0, 0.01, 0.28), (250, 210, 60), H, verts=10)
        for k in range(10):
            a = 2 * math.pi * k / 10
            ico(0.012, (0.182 * math.sin(a), 0.01 - 0.182 * math.cos(a), 0.36), (235, 240, 250), H, sub=1, metal=0.6, rough=0.2)
        box((0.09, 0.03, 0.08), (0, -0.17, 0.3), sk, H)
        for sd in (-1, 1):
            ico(0.05, (sd * 0.16, 0.03, 0.2), hc, H, sub=1, scale=(0.6, 1, 1))
    elif hair == "dupatta":
        ico(hr * 1.05, (0, 0.03, 0.25), hc, H, sub=1, scale=(1, 1, 0.75))
        ico(hr * 1.28, (0, 0.06, 0.2), C["cover"], H, sub=2, scale=(1.0, 0.92, 1.12))
        box((0.3, 0.06, 0.05), (0, -0.1, 0.38), C.get("cover2", C["cover"]), H, rot=(D(-30), 0, 0))
    elif hair == "plaits":
        ico(hr * 1.05, (0, 0.03, 0.25), hc, H, sub=1, scale=(1, 1, 0.75))
        for sd in (-1, 1):
            for k in range(5):
                ico(0.035, (sd * 0.15, 0.02, 0.08 - k * 0.06), hc, H, sub=1)
        ico(0.025, (0.08, -0.08, 0.36), (250, 120, 170), H, sub=1)
    # arms
    arms = []
    for sd in (-1, 1):
        shp = empty((sd * 0.22 * bld, 0, 0.52), torso, f"{key}_sh{sd}")
        sleeve = sh
        cyl(0.055, 0.3, (0, 0, -0.15), sleeve, shp, verts=7, r2=0.048)
        elb = empty((0, 0, -0.3), shp, f"{key}_elb{sd}")
        fore = sk if C.get("sleeve") == "short" else sleeve
        cyl(0.046, 0.27, (0, 0, -0.135), fore, elb, verts=7, r2=0.04)
        hand = empty((0, 0, -0.3), elb, f"{key}_hand{sd}")
        ico(0.05, (0, 0, 0), sk, hand, sub=1, scale=(0.9, 0.7, 1.1))
        arms.append((shp, elb, hand, sd))
    props = {}
    for (_, _, near_hand, hsd), pn in [(a_, p_) for a_ in arms for p_ in ("phone", "cup", "book", "newspaper", "bat", "plate", "remote", "bag")]:
        pe = empty((0, -0.05, -0.04), near_hand, f"{key}_prop_{pn}{hsd}")
        if pn == "phone":
            box((0.07, 0.015, 0.13), (0, 0, 0.02), (30, 30, 38), pe, rough=0.3)
            box((0.06, 0.005, 0.11), (0, -0.009, 0.02), (120, 190, 250), pe, emit=0.8)
        elif pn == "cup":
            cyl(0.04, 0.08, (0, 0, 0.05), (250, 250, 250), pe, verts=8)
        elif pn == "book":
            box((0.16, 0.03, 0.2), (0, 0, 0.04), (60, 110, 190), pe)
        elif pn == "newspaper":
            box((0.32, 0.01, 0.4), (-0.12, -0.05, 0.1), (236, 234, 222), pe)
        elif pn == "bat":
            box((0.08, 0.03, 0.55), (0, 0, 0.3), (225, 190, 120), pe)
        elif pn == "plate":
            cyl(0.13, 0.02, (0, -0.06, 0.03), (245, 245, 245), pe, verts=10)
        elif pn == "remote":
            box((0.04, 0.02, 0.14), (0, 0, 0.03), (40, 40, 46), pe)
        elif pn == "bag":
            box((0.18, 0.08, 0.16), (0, 0, -0.1), (150, 80, 120), pe)
        props[(pn, hsd)] = pe
    CH[key] = dict(root=root, hips=hips, legs=legs, torso=torso, neck=neck, head=head, eyes=eyes, mouth=mouth, teeth=teeth,
                   smile=smile, arms=arms, props=props, col=col, sc=sc, hip_h=hip_h, tod=tod)


def hide_tree(o, hide):
    o.hide_render = hide
    o.hide_viewport = hide
    for ch in o.children:
        hide_tree(ch, hide)


# ------------------------------------------------------------------ build everything
present = set()
for F in TL["frames"]:
    present |= set(F["ch"].keys())
for k in sorted(present):
    build_char(k)
SETS, _built = {}, {}
for i, s in enumerate(TL["scenes"]):
    kk = (s["set"], s["time"])
    if kk not in _built:
        _built[kk] = SETFN.get(s["set"], set_living)(s["time"])
    SETS[i] = _built[kk]

# lights + camera + world
bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
sun_d = bpy.data.lights.new("sun", "SUN")
sun = bpy.data.objects.new("sun", sun_d)
SCN.collection.objects.link(sun)
fill_d = bpy.data.lights.new("fill", "AREA")
fill_d.size = 6
fill = bpy.data.objects.new("fill", fill_d)
fill.location = (0, -6, 4)
fill.rotation_euler = (D(60), 0, 0)
SCN.collection.objects.link(fill)
cam_d = bpy.data.cameras.new("cam")
cam_d.sensor_fit = "VERTICAL"
cam_d.sensor_height = 36
cam = bpy.data.objects.new("cam", cam_d)
SCN.collection.objects.link(cam)
SCN.camera = cam
world = bpy.data.worlds.new("w")
world.use_nodes = True
SCN.world = world
bg = world.node_tree.nodes["Background"]

SCN.render.engine = "BLENDER_EEVEE"
ee = SCN.eevee
ee.taa_render_samples = 5
ee.use_gtao = True
ee.gtao_distance = 0.6
ee.use_soft_shadows = True
ee.shadow_cube_size = "512"
ee.shadow_cascade_size = "2048"
SCN.view_settings.view_transform = "AgX"
SCN.view_settings.look = "AgX - Base Contrast"
SCN.view_settings.exposure = -0.2
SCN.render.resolution_x = RES * 9 // 16
SCN.render.resolution_y = RES
SCN.render.film_transparent = False


def light_for(time):
    if time == "evening":
        sun_d.color = (1.0, 0.72, 0.5)
        sun_d.energy = 2.2
        sun.rotation_euler = (D(62), D(-28), D(30))
        bg.inputs[0].default_value = (0.55, 0.42, 0.5, 1)
        bg.inputs[1].default_value = 0.6
        fill_d.energy = 250
        fill_d.color = (1.0, 0.85, 0.75)
    else:
        sun_d.color = (1.0, 0.96, 0.88)
        sun_d.energy = 2.4
        sun.rotation_euler = (D(50), D(-20), D(25))
        bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1)
        bg.inputs[1].default_value = 0.7
        fill_d.energy = 220
        fill_d.color = (1.0, 0.97, 0.92)


# ------------------------------------------------------------------ per-frame posing
def lerp(a, b, u):
    return a + (b - a) * u


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def pose_angles(c, t):
    p, pv, tc = c["pose"], c["prev"], c["tc"]
    u = ease((t - tc) / 0.3) if tc is not None else 1
    A, B = POSE.get(pv, POSE["rest_stand"]), POSE.get(p, POSE["rest_stand"])
    return [tuple(lerp(a, b, u) for a, b in zip(A[k], B[k])) for k in range(2)]


def head_z_world(key):
    return CH[key]["head"].matrix_world.translation.z + 0.17 * CH[key]["sc"]


def apply(F):
    t = F["t"]
    for key, R in CH.items():
        c = F["ch"].get(key)
        vis = c is not None and c.get("alpha", 1) > 0.4 and c.get("sleep", 0) < 0.5
        hide_tree(R["root"], not vis)
        if not vis:
            continue
        seat = c["mode"] != "stand" and c["stand"] < 0.5
        x3, y3 = X3(c["x"], c["foot"]), depth(c["foot"])
        if seat:
            y3 = depth(c["foot"]) + 0.12
        R["root"].location = (x3, y3, 0)
        R["root"].rotation_euler = (0, 0, D(c["face"] * 7 + c["lx"] * 4))
        # sitting vs standing (stand in 0..1 blends)
        st = 1.0 if c["mode"] == "stand" else c["stand"]
        seat_h = 0.47
        R["hips"].location.z = lerp(seat_h, R["hip_h"], st)
        for i, (th, kn) in enumerate(R["legs"]):
            sw = math.sin(c["phase"] + i * math.pi) * 28 if c["walking"] else 0
            th.rotation_euler = (D(lerp(-88, 0, st) - sw), 0, D((1 if i else -1) * lerp(6, 0, st)))
            kn.rotation_euler = (D(lerp(88, 0, st) + max(0, sw) * 0.8), 0, 0)
        breath = math.sin(t * 2.2) * 0.012
        R["torso"].scale = (1 + breath, 1 + breath, 1 + breath * 0.5)
        R["torso"].rotation_euler = (D(lerp(4, 0, st) + c["nod"] * 0.5), 0, 0)
        # head acting: look, tilt, nod, talking bob
        bob = math.sin(t * 9) * 2.5 if c["q"] > 0 else 0
        R["head"].rotation_euler = (D(-c["ly"] * 8 + c["nod"] * 4 + bob), D(c["ang"] * 1.2), D(c["lx"] * 13))
        if c["emo"] == "laugh":  # whole-body laugh bounce (squash & stretch)
            sq = abs(math.sin(t * 11)) * 0.04
            R["torso"].scale = (1 + sq * 0.5, 1 + sq * 0.5, 1 - sq)
        # face
        brow, eo, sm = EMO.get(c["emo"], EMO["neutral"])
        bl = (1.0, 0.45, 0.0)[c["blink"]] if c["blink"] in (0, 1, 2) else 1.0
        eo_ = eo * bl
        for ew, pup, lid, br, sd in R["eyes"]:
            lid.location.z = 0.282 - 0.07 * (1 - min(eo_, 1.0))
            lid.scale = (1, 1, 0.7 + 1.4 * (1 - min(eo_, 1.0)))
            pup.location.x = sd * 0.065 + c["lx"] * 0.012
            pup.location.z = 0.2 - c["ly"] * 0.01
            pup.scale = (1, 1, 1) if eo_ > 0.15 else (0.01, 0.01, 0.01)
            br.rotation_euler = (0, D(sd * brow), 0)
            br.location.z = 0.27 + (0.012 if c["emo"] in ("surprised", "worried") else 0) - (0.008 if c["emo"] in ("angry", "focused") else 0)
        q = c["q"]
        if c["emo"] == "laugh":
            q = max(q, 3)
        open_ = q / 5.0
        R["mouth"].scale = (0.8 + 0.5 * max(sm, 0) + 0.3 * c["shape"], 1, 0.15 + 1.6 * open_ if q else 0.0001)
        R["teeth"].hide_render = q < 2
        R["smile"].scale = (1 + 0.4 * max(sm, 0), 1, 1) if q == 0 else (0.0001, 0.0001, 0.0001)
        R["smile"].rotation_euler = (0, 0, 0) if sm >= 0 else (0, D(180), 0)
        # arms
        nearA, farA = pose_angles(c, t)
        face = c["face"] if c["face"] in (-1, 1) else 1
        for shp, elb, hand, sd in R["arms"]:
            near = (sd == face)
            fwd, out, bend = nearA if near else farA
            if c["walking"]:
                fwd = math.sin(c["phase"] + (0 if sd > 0 else math.pi)) * 25
            wob = math.sin(t * 3 + sd) * 2
            shp.rotation_euler = (D(-fwd - wob), D(-sd * out), 0)
            elb.rotation_euler = (D(-bend), 0, 0)
        for (pn, hsd), pe in R["props"].items():
            hide_tree(pe, c.get("prop") != pn or hsd != face)


def place_camera(F, scene):
    cx, cy, z = F["cam"]
    z = max(z, 1.0)
    keys = [k for k in F["ch"] if k in CH and not CH[k]["root"].hide_render]
    w2 = 540 / z
    foc = [k for k in keys if abs(F["ch"][k]["x"] - cx) < w2 * (0.9 if z < 1.4 else 0.5)]
    if not foc and keys:
        foc = [min(keys, key=lambda k: abs(F["ch"][k]["x"] - cx))]
    li = F.get("li")
    if z >= 1.4 and li is not None and TL["lines"][li]["who"] in keys and len(foc) > 1:
        sp = TL["lines"][li]["who"]  # close-ups: the speaker leads the framing
        foc = [sp] + [k for k in foc if k != sp and abs(F["ch"][k]["x"] - F["ch"][sp]["x"]) < 200]
    if foc:
        tx = sum(CH[k]["root"].location.x for k in foc) / len(foc)
        ty = sum(CH[k]["root"].location.y for k in foc) / len(foc)
        hz = sum(head_z_world(k) for k in foc) / len(foc)
    else:
        tx, ty, hz = 0, 0.5, 1.3
    u = ease((z - 1.0) / 1.0)
    tz = lerp(1.05, hz - 0.12, u)
    tx = lerp(tx * 0.6, tx, u)
    dist = lerp(7.2, 3.4, u)
    camz = lerp(1.55, hz + 0.05, u)
    cam.location = (tx * 0.9, ty - dist, camz)
    d = Vector((tx, ty, tz)) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_d.lens = lerp(24, 38, u) * (1 + 0.15 * max(0, z - 2.0))


# ------------------------------------------------------------------ render loop
n_out = int(TL["n"] * LPFPS / TL["fps"])
a, b = 0, n_out
if RANGE:
    a, b = (int(v) for v in RANGE.split("-"))
    b = min(b, n_out)
cur_si = None
for k in range(a, b):
    t = k / LPFPS
    fr = min(int(round(t * TL["fps"])), len(TL["frames"]) - 1)
    F = TL["frames"][fr]
    si = F["si"]
    if si != cur_si:
        for i, c in SETS.items():
            c.hide_render = True
            c.hide_viewport = True
        SETS[si].hide_render = False
        SETS[si].hide_viewport = False
        light_for(TL["scenes"][si]["time"])
        cur_si = si
    apply(F)
    bpy.context.view_layer.update()
    place_camera(F, TL["scenes"][si])
    SCN.render.filepath = os.path.join(OUTD, f"{k + 1:05d}.png")
    bpy.ops.render.render(write_still=True)
    if k % 50 == 0:
        print("frame", k + 1, "/", n_out, flush=True)
print("done", flush=True)
