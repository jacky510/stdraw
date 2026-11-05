# -*- coding: utf-8 -*-
"""3D 渲染层：layout3d 结果 → 独立 HTML（three.js r128，零网络依赖）。

three.js 经 assets/three.min.js 相对引用（零内联依赖精神：
与 viewer 共享仓内 assets 目录一份，避免每份 demo 重复内联 600KB）。
视觉规格：节点=双面渲染球片+深度明暗衰减、
弦线向外弓（单弧贝塞尔贴合球壳）、形体线框参考、地面网格、OrbitControls。
"""
import html
import json


def render_3d_html(graph_dict: dict, layouts: dict, graph_name: str = "",
                   cert_note: str = "") -> str:
    """layouts: {solid: layout3d 结果 dict}。每个形体一个按钮切换。"""
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
#c{position:fixed;inset:0}
</style>
<div id="bar"><b>stdraw 3D · ''' + html.escape(graph_name) + '''</b> ''' + buttons + '''</div>
<div id="c"></div>
<div id="info">拖动旋转 / 滚轮缩放 / 右键平移 · 确定性排布（同图同布局）· ''' + html.escape(cert_note) + '''</div>
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
  // 节点：球片 + 标签 sprite（深度明暗在 render 循环按相机距离调透明度）
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
  // 边：向外弓的单弧弦线（控制点沿位置向量外推）
  DATA.edges.forEach(e=>{
    const a = new THREE.Vector3(...pos[e.a]);
    const b = new THREE.Vector3(...pos[e.b]);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const out = mid.length() < 1 ? a.clone().normalize() : mid.clone().normalize();
    const ctrl = mid.add(out.multiplyScalar(mid.length()*0.18 + 20));
    const curve = new THREE.QuadraticBezierCurve3(a, ctrl, b);
    const neg = e.p === '-';
    const mat = new THREE.LineBasicMaterial({color: neg ? 0x60a5fa : 0x94a3b8, transparent:true, opacity:0.85});
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(24)), mat));
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
  if (group) group.children.forEach(ch=>{ // 深度明暗：远处元素降透明度
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
