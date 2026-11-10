# -*- coding: utf-8 -*-
"""3D rendering layer: layout3d results -> standalone HTML (three.js r128,
zero network dependency).

Theme caliber (UI-A spec sections 3 / 4.4, docs/ui-theme-spec-a.md): every
color on this page comes from stdraw/themes.py THEMES_3D — no color literals
live in this module. Two groups ship:

- theme="dark" (default): the shipped look, a FROZEN REGRESSION PIN
  (spec D5, jacky 2026-11-11 ruling) — output must stay byte-identical to
  the pre-UI-A renderer; DARK_3D mirrors those values verbatim.
- theme="light" (UI-A light stage, spec section 3.1 / D6): structure
  unchanged, parameters only — the drafting-paper stage with ink nodes and
  the two polar inks (vermilion '+' / drafting-blue '−') as the only
  chromatic hues on the canvas.

three.js is referenced relatively via assets/three.min.js (in the spirit of
zero inline dependencies: shared with the viewer from one in-repo assets
directory, avoiding re-inlining 600KB into every demo).
Visual spec: nodes = double-sided rendered sphere sprites + depth-based
shading falloff, chord edges = two-color polarity tubes (all solid) bowed
outward (single-arc Bezier hugging the spherical shell) with a cone arrowhead
at every edge end (the tube body is trimmed back near the tip so the cone
owns the endpoint), solid wireframe reference, ground grid, OrbitControls.
"""
import html
import json

from .themes import THEMES_3D


def _js(hexc: str) -> str:
    """'#1e293b' -> '0x1e293b' (three.js numeric color literal)."""
    return "0x" + hexc[1:]


def render_3d_html(graph_dict: dict, layouts: dict, graph_name: str = "",
                   cert_note: str = "", theme: str = "dark") -> str:
    """layouts: {solid: layout3d result dict}. One button per solid to switch.

    theme: "dark" (default; frozen byte pin — spec D5) or "light" (UI-A
    light stage). An unknown theme raises KeyError (no silent light).
    """
    T = THEMES_3D[theme]
    # Active-solid-button rule. Dark's accent text equals its inherited body
    # text and the frozen dark CSS bytes carry no color property there, so the
    # property is emitted only when the accent text differs (light: paper on
    # ink). This keeps the dark byte pin exact without a second template.
    accent_extra = ("" if T["ui_accent_text"] == T["ui_text"]
                    else ";color:" + T["ui_accent_text"])
    accent_rule = (f"button.on{{background:{T['ui_accent']};"
                   f"border-color:{T['ui_accent']}{accent_extra}}}")
    data = json.dumps({"name": graph_name,
                       "nodes": graph_dict["nodes"],
                       "edges": graph_dict["edges"],
                       "layouts": {k: v["positions"] for k, v in layouts.items()}},
                      ensure_ascii=False)
    solids = list(layouts.keys())
    buttons = "".join(
        f'<button onclick="setSolid(\'{s}\')" id="btn-{s}">{s}</button>'
        for s in solids)
    return ('''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>stdraw 3D · ''' + html.escape(graph_name) + '''</title>
<style>
body{margin:0;font-family:Microsoft YaHei,sans-serif;background:%(scene_bg_css)s;color:%(ui_text_css)s}
#bar{position:fixed;top:10px;left:10px;z-index:10;display:flex;gap:6px;align-items:center}
button{background:%(card_fill_css)s;color:%(ui_text_css)s;border:1px solid %(card_stroke_css)s;border-radius:6px;padding:4px 12px;cursor:pointer}
%(accent_rule)s
#info{position:fixed;bottom:10px;left:10px;font-size:12px;color:%(ui_muted_css)s;z-index:10}
#legend{position:fixed;bottom:10px;right:10px;font-size:13px;z-index:10}
#c{position:fixed;inset:0}
</style>
<div id="bar"><b>stdraw 3D · ''' + html.escape(graph_name) + '''</b> ''' + buttons + '''</div>
<div id="legend"><span style="color:%(tube_r_css)s">━ +</span>&nbsp;&nbsp;<span style="color:%(tube_b_css)s">━ −</span></div>
<div id="c"></div>
<div id="info">drag to rotate / wheel to zoom / right-drag to pan · deterministic placement (same graph, same layout) · ''' + html.escape(cert_note) + '''</div>
<script src="../assets/three.min.js"></script>
<script src="../assets/OrbitControls.js"></script>
<script>
const DATA = ''' + data + ''';
const scene = new THREE.Scene();
scene.background = new THREE.Color(%(scene_bg_js)s);
scene.fog = new THREE.Fog(%(fog_js)s, 900, 2200);
const camera = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 1, 5000);
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setSize(innerWidth, innerHeight);
document.getElementById('c').appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
camera.position.set(0, 240, 1250);
controls.target.set(0, 0, 0);
controls.update();
controls.autoRotate = false;
scene.add(new THREE.GridHelper(1600, 32, %(grid_major_js)s, %(grid_minor_js)s));
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dl = new THREE.DirectionalLight(0xffffff, 0.6); dl.position.set(400, 600, 300); scene.add(dl);

let group = null;
function wireframeBox(solid, size){
  const g = new THREE.Group();
  let geo = null;
  if (solid === 'sphere') geo = new THREE.SphereGeometry(size, 16, 12);
  else if (solid === 'cube') geo = new THREE.BoxGeometry(size*1.15, size*1.15, size*1.15);
  else if (solid === 'tetra'){
    const s = size*1.6;
    const v = [new THREE.Vector3(s,s,s), new THREE.Vector3(s,-s,-s),
               new THREE.Vector3(-s,s,-s), new THREE.Vector3(-s,-s,s)];
    geo = new THREE.BufferGeometry().setFromPoints(
      [v[0],v[1],v[2],v[0],v[2],v[3],v[0],v[3],v[1],v[1],v[2],v[3]].map(p=>p));
  } else if (solid === 'cone'){
    geo = new THREE.ConeGeometry(size*0.9, size*2.4, 24, 6, true);
    geo.translate(0, -size*0.2, 0);
  }
  if (geo){
    const wf = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 12),
      new THREE.LineBasicMaterial({color:%(card_stroke_js)s, transparent:true, opacity:0.9}));
    g.add(wf);
  }
  return g;
}
function draw(solid){
  if (group) scene.remove(group);
  group = new THREE.Group();
  const pos = DATA.layouts[solid];
  const size = Math.max(...Object.values(pos).flat().map(Math.abs));
  group.add(wireframeBox(solid, size));
  const idx = {}; DATA.nodes.forEach((n,i)=>idx[n.id]=i);
  // nodes: sphere sprites + label sprites (depth shading adjusts opacity by camera distance in the render loop)
  const sprites = [];
  DATA.nodes.forEach(n=>{
    const p = pos[n.id];
    const m = new THREE.Mesh(new THREE.SphereGeometry(14, 16, 12),
      new THREE.MeshBasicMaterial({color:%(node_sprite_js)s, transparent:true, opacity:0.95}));
    m.position.set(p[0], p[1], p[2]);
    group.add(m);
    const cv = document.createElement('canvas');
    cv.width = 256; cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.font = '28px Microsoft YaHei';
    ctx.fillStyle = '%(card_text_css)s';
    ctx.textAlign = 'center';
    ctx.fillText(n.label, 128, 40);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv), transparent:true}));
    sp.scale.set(150, 38, 1);
    sp.position.set(p[0], p[1] + 30, p[2]);
    group.add(sp); sprites.push(sp);
  });
  // edges: two-color polarity tubes (jacky 2026-11-09 caliber: color = the
  // edge's own sign, all solid) + a cone arrowhead at every edge end; the tube
  // body is trimmed back near the tip so the cone owns the endpoint and the
  // direction stays legible when zoomed out. Bright shades of the 2D palette
  // (#d97706/#0284c7) for the dark scene background.
  const TUBE_RAD = 3.2, CONE_RAD = 8.0, CONE_LEN = 30;
  window.__stdraw3dEdges = [];
  DATA.edges.forEach(e=>{
    const a = new THREE.Vector3(...pos[e.a]);
    const b = new THREE.Vector3(...pos[e.b]);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const out = mid.length() < 1 ? a.clone().normalize() : mid.clone().normalize();
    const ctrl = mid.add(out.multiplyScalar(mid.length()*0.18 + 20));
    const curve = new THREE.QuadraticBezierCurve3(a, ctrl, b);
    const polCol = e.p === '-' ? %(tube_b_js)s : %(tube_r_js)s;   // '−' sky / '+' amber
    const polHex = e.p === '-' ? '%(tube_b_hex)s' : '%(tube_r_hex)s';
    const bodyPts = curve.getPoints(24).slice(0, 22);   // t=0..0.875: tube stops before the cone zone
    const body = new THREE.CatmullRomCurve3(bodyPts);
    group.add(new THREE.Mesh(new THREE.TubeGeometry(body, 24, TUBE_RAD, 8, false),
      new THREE.MeshBasicMaterial({color: polCol})));
    const tangent = curve.getTangent(1).normalize();
    const cone = new THREE.Mesh(new THREE.ConeGeometry(CONE_RAD, CONE_LEN, 12),
      new THREE.MeshBasicMaterial({color: polCol}));
    cone.position.copy(b.clone().sub(tangent.clone().multiplyScalar(CONE_LEN/2)));
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), tangent);
    group.add(cone);
    window.__stdraw3dEdges.push({a:e.a, b:e.b, pol:e.p, color:polHex,
      tube:true, cone:true, dir:[tangent.x, tangent.y, tangent.z]});
  });
  scene.add(group);
  document.querySelectorAll('#bar button').forEach(b=>b.classList.toggle('on', b.id==='btn-'+solid));
}
function setSolid(s){ draw(s); }
addEventListener('resize', ()=>{
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop(){
  requestAnimationFrame(loop);
  if (group) group.children.forEach(ch=>{ // depth shading: distant elements fade
    if (ch.material && ch.material.opacity !== undefined){
      const d = camera.position.distanceTo(ch.position instanceof THREE.Vector3 ? ch.position : new THREE.Vector3());
      const f = Math.max(0.25, Math.min(1, 1.25 - d/1800));
      if (ch.material.transparent) ch.material.opacity = (ch instanceof THREE.Sprite ? 0.95 : 0.9) * f;
    }
  });
  controls.update(); renderer.render(scene, camera);
})();
draw(''' + repr(solids[0]) + ''');
</script></html>''') % {
        "scene_bg_css": T["scene_bg"],
        "ui_text_css": T["ui_text"],
        "card_fill_css": T["card_fill"],
        "card_stroke_css": T["card_stroke"],
        "accent_rule": accent_rule,
        "ui_muted_css": T["ui_muted"],
        "tube_r_css": T["tube_r"],
        "tube_b_css": T["tube_b"],
        "scene_bg_js": _js(T["scene_bg"]),
        "fog_js": _js(T["fog_color"]),
        "grid_major_js": _js(T["grid_major"]),
        "grid_minor_js": _js(T["grid_minor"]),
        "card_stroke_js": _js(T["card_stroke"]),
        "node_sprite_js": _js(T["node_sprite"]),
        "card_text_css": T["card_text"],
        "tube_r_js": _js(T["tube_r"]),
        "tube_b_js": _js(T["tube_b"]),
        "tube_r_hex": T["tube_r"],
        "tube_b_hex": T["tube_b"],
    }
