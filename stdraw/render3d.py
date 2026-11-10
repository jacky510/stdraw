# -*- coding: utf-8 -*-
"""3D rendering layer: layout3d results -> standalone HTML (three.js r128,
zero network dependency).

Dark-3D caliber (UI-A spec D5 / docs/ui-theme-spec-a.md section 3.2, jacky
2026-11-11 ruling): every dark color used below is a FROZEN REGRESSION PIN —
zero changes allowed; the authoritative mirror of those values is
stdraw/themes.py DARK_3D. The UI-A LIGHT_3D group (stage/fog/grid/card/tube
colors) is already defined there; consuming it for a light 3D stage is a
follow-up card, and until then the dark output must stay byte-identical.

three.js is referenced relatively via assets/three.min.js (in the spirit of
zero inline dependencies: shared with the viewer from one in-repo assets
directory, avoiding re-inlining 600KB into every demo).
Visual spec: nodes = double-sided rendered sphere sprites + depth-based
shading falloff, chord edges = two-color polarity tubes ('+' amber / '−' sky,
all solid) bowed outward (single-arc Bezier hugging the spherical shell) with
a cone arrowhead at every edge end (the tube body is trimmed back near the
tip so the cone owns the endpoint), solid wireframe reference, ground grid,
OrbitControls.
"""
import html
import json


def render_3d_html(graph_dict: dict, layouts: dict, graph_name: str = "",
                   cert_note: str = "") -> str:
    """layouts: {solid: layout3d result dict}. One button per solid to switch."""
    data = json.dumps({"name": graph_name,
                       "nodes": graph_dict["nodes"],
                       "edges": graph_dict["edges"],
                       "layouts": {k: v["positions"] for k, v in layouts.items()}},
                      ensure_ascii=False)
    solids = list(layouts.keys())
    buttons = "".join(
        f'<button onclick="setSolid(\'{s}\')" id="btn-{s}">{s}</button>'
        for s in solids)
    return '''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>stdraw 3D · ''' + html.escape(graph_name) + '''</title>
<style>
body{margin:0;font-family:Microsoft YaHei,sans-serif;background:#0b1220;color:#e2e8f0}
#bar{position:fixed;top:10px;left:10px;z-index:10;display:flex;gap:6px;align-items:center}
button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:4px 12px;cursor:pointer}
button.on{background:#2563eb;border-color:#2563eb}
#info{position:fixed;bottom:10px;left:10px;font-size:12px;color:#94a3b8;z-index:10}
#legend{position:fixed;bottom:10px;right:10px;font-size:13px;z-index:10}
#c{position:fixed;inset:0}
</style>
<div id="bar"><b>stdraw 3D · ''' + html.escape(graph_name) + '''</b> ''' + buttons + '''</div>
<div id="legend"><span style="color:#fbbf24">━ +</span>&nbsp;&nbsp;<span style="color:#7dd3fc">━ −</span></div>
<div id="c"></div>
<div id="info">drag to rotate / wheel to zoom / right-drag to pan · deterministic placement (same graph, same layout) · ''' + html.escape(cert_note) + '''</div>
<script src="../assets/three.min.js"></script>
<script src="../assets/OrbitControls.js"></script>
<script>
const DATA = ''' + data + ''';
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1220);
scene.fog = new THREE.Fog(0x0b1220, 900, 2200);
const camera = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 1, 5000);
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setSize(innerWidth, innerHeight);
document.getElementById('c').appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
camera.position.set(0, 240, 1250);
controls.target.set(0, 0, 0);
controls.update();
controls.autoRotate = false;
scene.add(new THREE.GridHelper(1600, 32, 0x1e293b, 0x16233b));
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
      new THREE.LineBasicMaterial({color:0x334155, transparent:true, opacity:0.9}));
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
      new THREE.MeshBasicMaterial({color:0xf59e0b, transparent:true, opacity:0.95}));
    m.position.set(p[0], p[1], p[2]);
    group.add(m);
    const cv = document.createElement('canvas');
    cv.width = 256; cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.font = '28px Microsoft YaHei';
    ctx.fillStyle = '#f1f5f9';
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
    const polCol = e.p === '-' ? 0x7dd3fc : 0xfbbf24;   // '−' sky / '+' amber
    const polHex = e.p === '-' ? '#7dd3fc' : '#fbbf24';
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
</script></html>'''
