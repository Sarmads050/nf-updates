"""Open the low-poly renderer in headless Chromium: three.js r160 as ES modules + post-processing addons,
served from disk through a fake http origin (module imports do not work from file://)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
THREE_DIR = os.environ.get("THREE_DIR", "/home/claude/r3d/node_modules/three")
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]

INDEX = """<!doctype html><html><head><style>body{margin:0;background:#000}</style>
<script type="importmap">{"imports":{"three":"/three.module.js","three/addons/":"/addons/"}}</script>
<script type="module">
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FXAAShader } from 'three/addons/shaders/FXAAShader.js';
window.THREE = THREE;
window.PP = { EffectComposer, RenderPass, GTAOPass, BokehPass, UnrealBloomPass, ShaderPass, OutputPass, FXAAShader };
const s = document.createElement('script'); s.src = '/lowpoly.js'; s.onload = () => { window.LP_READY = true; }; document.head.appendChild(s);
</script></head><body></body></html>"""


def open_page(p, w=1080, h=1920, log=True):
    b = p.chromium.launch(args=ARGS)
    pg = b.new_page(viewport={"width": w, "height": h})
    if log:
        pg.on("pageerror", lambda e: print("[js error]", e, flush=True))
        pg.on("console", lambda m: print("[js]", m.text, flush=True) if m.type == "error" else None)

    def route(r):
        path = r.request.url.split("http://lp.local", 1)[1].split("?")[0]
        if path in ("/", "/index.html"):
            return r.fulfill(body=INDEX, content_type="text/html")
        if path == "/three.module.js":
            f = f"{THREE_DIR}/build/three.module.js"
        elif path.startswith("/addons/"):
            f = f"{THREE_DIR}/examples/jsm/" + path[len("/addons/"):]
        else:
            f = f"{HERE}{path}"
        if not os.path.exists(f):
            return r.fulfill(status=404, body="")
        return r.fulfill(path=f, content_type="text/javascript")
    pg.route("http://lp.local/**", route)
    pg.goto("http://lp.local/index.html")
    pg.wait_for_function("window.LP_READY === true", timeout=60000)
    return b, pg
