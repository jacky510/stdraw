

# ═══ 交互层脚本（ref-scrubbed 拖拽重排）═══
# 纯 vanilla JS（零依赖零联网）。挂进 render_auto_html 生成的页面：
#   - 拖动节点（SVG pointer 事件，鼠标/触摸统一；拖动中 clamp 在 viewBox 内）；
#   - 关联边实时重锚（端点贴新框边，中间点保持原形状；弧线初始化时按
#     二次贝塞尔 12 段离散，拖动中按折线跟随）+ 箭头按末段方向重定向；
#   - 顶栏实时指标（预览几何真算：交叉/穿卡1px/卡净距/CV/行对齐）；
#   - 松手全指标刷新 + R/B 极性标记确定性重放（render._polarity_marker 同口径）；
#   - 「导出布局」下载 manual-layout JSON（坐标取整，layout.json 兼容子集）；
#   - 「重置」恢复初始布局。
# 确定性：生成的 HTML 不含时间戳/随机数；不拖时初始几何与静态渲染逐像素一致。
_INTERACTIVE_JS = r"""(function () {
'use strict';
var dataEl = document.getElementById('stdraw-data');
if (!dataEl) return;
var D = JSON.parse(dataEl.textContent);
var svg = document.getElementById('stdraw-svg');
var VB = D.viewBox, cardH = D.cardH;
var nodes = {};
D.nodes.forEach(function (n) { nodes[n.id] = {x: n.x, y: n.y, w: n.w, bx: n.x, by: n.y, g: null}; });
svg.querySelectorAll('[data-node]').forEach(function (g) {
  var id = g.getAttribute('data-node');
  if (nodes[id]) nodes[id].g = g;
});
function quad(p0, c, p1, n) {
  var out = [];
  for (var k = 0; k <= n; k++) {
    var t = k / n, u = 1 - t;
    out.push([u*u*p0[0] + 2*u*t*c[0] + t*t*p1[0], u*u*p0[1] + 2*u*t*c[1] + t*t*p1[1]]);
  }
  return out;
}
var edges = D.edges.map(function (e) {
  var pts = e.pts;
  if (e.arc && e.ctrl && pts.length >= 2) pts = quad(pts[0], e.ctrl, pts[pts.length - 1], 12);
  pts = pts.map(function (p) { return [p[0], p[1]]; });
  return {a: e.a, b: e.b, pol: e.pol, pts: pts, base: pts.map(function (p) { return [p[0], p[1]]; })};
});
var polGroups = {};
svg.querySelectorAll('[data-pol]').forEach(function (g) {
  polGroups[+g.getAttribute('data-pol')] = {g: g, t: g.getAttribute('transform')};
});
var incidentMap = {};
Object.keys(nodes).forEach(function (v) {
  incidentMap[v] = [];
  edges.forEach(function (e, i) { if (e.a === v || e.b === v) incidentMap[v].push(i); });
});
function edgeD(pts) {
  return 'M ' + pts.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L ');
}
function updateEdge(i) {
  var e = edges[i], g = svg.querySelector('[data-edge="' + i + '"]');
  if (!g) return;
  var paths = g.querySelectorAll('path');
  if (paths[0]) paths[0].setAttribute('d', edgeD(e.pts));
  if (paths[1]) {
    var n = e.pts.length, a = e.pts[n - 2], b = e.pts[n - 1];
    var ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
    paths[1].setAttribute('transform', 'translate(' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) + ') rotate(' + ang.toFixed(1) + ')');
  }
}
function borderPoint(c, hw, hh, toward) {
  var dx = toward[0] - c[0], dy = toward[1] - c[1];
  if (!dx && !dy) return [c[0], c[1]];
  var t = Math.min(hw / Math.abs(dx), hh / Math.abs(dy));
  return [c[0] + dx * t, c[1] + dy * t];
}
function reanchor(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pts = e.pts.map(function (p) { return [p[0], p[1]]; });
  var inner = pts.length > 2;
  pts[0] = borderPoint([A.x, A.y], A.w / 2, cardH / 2, inner ? pts[1] : [B.x, B.y]);
  pts[pts.length - 1] = borderPoint([B.x, B.y], B.w / 2, cardH / 2, inner ? pts[pts.length - 2] : [A.x, A.y]);
  e.pts = pts;
}
function segCross(p1, p2, p3, p4) {
  function orient(a, b, c) {
    var v = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
    return Math.abs(v) < 1e-9 ? 0 : (v > 0 ? 1 : -1);
  }
  var d1 = orient(p3,p4,p1), d2 = orient(p3,p4,p2), d3 = orient(p1,p2,p3), d4 = orient(p1,p2,p4);
  return d1 !== d2 && d3 !== d4 && d1 !== 0 && d3 !== 0;
}
function distRect(px, py, cx, cy, hw, hh) {
  var dx = Math.max(Math.abs(px - cx) - hw, 0), dy = Math.max(Math.abs(py - cy) - hh, 0);
  return Math.hypot(dx, dy);
}
function samplePts(pts, step) {
  step = step || 4;
  var out = [];
  for (var i = 0; i < pts.length - 1; i++) {
    var a = pts[i], b = pts[i + 1], d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    var n = Math.max(1, Math.floor(d / step));
    for (var k = 0; k < n; k++) { var t = k / n; out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]); }
  }
  out.push(pts[pts.length - 1].slice());
  return out;
}
function metrics() {
  var ids = Object.keys(nodes), crossings = 0;
  for (var i = 0; i < edges.length; i++) {
    for (var j = i + 1; j < edges.length; j++) {
      var e1 = edges[i], e2 = edges[j];
      if (e1.a === e2.a || e1.a === e2.b || e1.b === e2.a || e1.b === e2.b) continue;
      var hit = false;
      for (var s1 = 0; s1 < e1.pts.length - 1 && !hit; s1++) {
        for (var s2 = 0; s2 < e2.pts.length - 1; s2++) {
          if (segCross(e1.pts[s1], e1.pts[s1 + 1], e2.pts[s2], e2.pts[s2 + 1])) { hit = true; break; }
        }
      }
      if (hit) crossings++;
    }
  }
  var press = 0;
  edges.forEach(function (e) {
    var pts = samplePts(e.pts);
    ids.forEach(function (v) {
      if (v === e.a || v === e.b) return;
      var n = nodes[v];
      for (var k = 0; k < pts.length; k++) {
        if (distRect(pts[k][0], pts[k][1], n.x, n.y, n.w / 2 + 1, cardH / 2 + 1) <= 0) { press++; break; }
      }
    });
  });
  var minGap = Infinity, nn = [];
  for (var a = 0; a < ids.length; a++) {
    var na = nodes[ids[a]], nna = Infinity;
    for (var b = 0; b < ids.length; b++) {
      if (a === b) continue;
      var nb = nodes[ids[b]];
      var dgx = Math.abs(na.x - nb.x) - (na.w + nb.w) / 2;
      var dgy = Math.abs(na.y - nb.y) - cardH;
      var gg = Math.hypot(Math.max(dgx, 0), Math.max(dgy, 0));
      if (gg < minGap) minGap = gg;
      var dc = Math.hypot(na.x - nb.x, na.y - nb.y);
      if (dc < nna) nna = dc;
    }
    nn.push(nna);
  }
  var mean = nn.reduce(function (s, x) { return s + x; }, 0) / nn.length;
  var cv = Math.sqrt(nn.reduce(function (s, x) { return s + (x - mean) * (x - mean); }, 0) / nn.length) / mean;
  var ys = ids.map(function (v) { return nodes[v].y; }).sort(function (p, q) { return p - q; });
  var aligned = 0, i2 = 0;
  while (i2 < ys.length) {
    var j2 = i2;
    while (j2 + 1 < ys.length && ys[j2 + 1] - ys[j2] <= 4) j2++;
    if (j2 > i2) aligned += j2 - i2 + 1;
    i2 = j2 + 1;
  }
  return {crossings: crossings, press: press, minGap: Math.round(minGap * 10) / 10,
          cv: Math.round(cv * 1000) / 1000, row: Math.round(aligned / ids.length * 1000) / 1000};
}
function refreshMetrics() {
  var el = document.getElementById('stdraw-metrics');
  if (!el) return;
  var m = metrics();
  el.textContent = '交叉 ' + m.crossings + ' · 穿卡(1px) ' + m.press +
    ' · 卡净距 ' + m.minGap + 'px · CV ' + m.cv + ' · 行对齐 ' + m.row;
}
function polyPointAt(pts, t) {
  var segs = [], total = 0, i;
  for (i = 0; i < pts.length - 1; i++) {
    var d = Math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]);
    segs.push(d); total += d;
  }
  var target = total * Math.max(0, Math.min(1, t)), acc = 0;
  for (i = 0; i < segs.length; i++) {
    if (acc + segs[i] >= target && segs[i] > 0) {
      var f = (target - acc) / segs[i];
      var p = [pts[i][0] + (pts[i+1][0]-pts[i][0]) * f, pts[i][1] + (pts[i+1][1]-pts[i][1]) * f];
      return {p: p, tan: [(pts[i+1][0]-pts[i][0]) / segs[i], (pts[i+1][1]-pts[i][1]) / segs[i]]};
    }
    acc += segs[i];
  }
  return {p: pts[pts.length - 1].slice(), tan: [0, 1]};
}
function ptPolyDist(px, py, pts) {
  var best = Infinity;
  for (var i = 0; i < pts.length - 1; i++) {
    var a = pts[i], b = pts[i + 1];
    var vx = b[0]-a[0], vy = b[1]-a[1], L2 = vx*vx + vy*vy;
    var t = L2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((px-a[0])*vx + (py-a[1])*vy) / L2));
    best = Math.min(best, Math.hypot(px - a[0] - t*vx, py - a[1] - t*vy));
  }
  return best;
}
function refreshMarkers() {
  var ids = Object.keys(nodes);
  edges.forEach(function (e, i) {
    var rec = polGroups[i];
    if (!rec) return;
    var placed = null;
    var others = [];
    edges.forEach(function (e2, j) { if (j !== i) others.push(e2.pts); });
    var ts = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74];
    for (var ti = 0; ti < ts.length && !placed; ti++) {
      var r = polyPointAt(e.pts, ts[ti]);
      var nx = -r.tan[1], ny = r.tan[0];
      var offs = [10, -10, 14, -14, 18, -18];
      for (var oi = 0; oi < offs.length && !placed; oi++) {
        var cx = r.p[0] + nx * offs[oi], cy = r.p[1] + ny * offs[oi];
        if (cx < 8 || cx > VB[2] - 8 || cy < 8 || cy > VB[3] - 8) continue;
        var bad = false;
        for (var bi = 0; bi < ids.length && !bad; bi++) {
          var n = nodes[ids[bi]];
          var ddx = Math.max(Math.abs(cx - n.x) - n.w / 2, 0);
          var ddy = Math.max(Math.abs(cy - n.y) - cardH / 2, 0);
          if (Math.hypot(ddx, ddy) < 8) bad = true;
        }
        if (bad) continue;
        for (var k = 0; k < others.length; k++) if (ptPolyDist(cx, cy, others[k]) < 11) { bad = true; break; }
        if (bad) continue;
        placed = [cx, cy];
      }
    }
    if (placed) rec.g.setAttribute('transform', 'translate(' + placed[0].toFixed(1) + ' ' + placed[1].toFixed(1) + ')');
  });
}
var drag = null, rafPending = false;
function svgPoint(ev) {
  var m = svg.getScreenCTM();
  if (!m) return null;
  var pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  return pt.matrixTransform(m.inverse());
}
function onDown(ev) {
  var t = ev.target;
  var g = t && t.closest ? t.closest('[data-node]') : null;
  if (!g) return;
  var id = g.getAttribute('data-node');
  var p = svgPoint(ev);
  if (!p || !(id in nodes)) return;
  drag = {id: id, g: g, start: [p.x, p.y], ox: nodes[id].x, oy: nodes[id].y};
  try { g.setPointerCapture(ev.pointerId); } catch (e) {}
  g.classList.add('dragging');
  ev.preventDefault();
}
function onMove(ev) {
  if (!drag) return;
  var p = svgPoint(ev);
  if (!p) return;
  var n = nodes[drag.id];
  var nx = drag.ox + (p.x - drag.start[0]);
  var ny = drag.oy + (p.y - drag.start[1]);
  nx = Math.max(n.w / 2 + 2, Math.min(VB[2] - n.w / 2 - 2, nx));
  ny = Math.max(cardH / 2 + 2, Math.min(VB[3] - cardH / 2 - 2, ny));
  n.x = nx; n.y = ny;
  drag.g.setAttribute('transform', 'translate(' + (nx - n.bx).toFixed(1) + ' ' + (ny - n.by).toFixed(1) + ')');
  incidentMap[drag.id].forEach(function (i) { reanchor(i); updateEdge(i); });
  if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(function () { rafPending = false; refreshMetrics(); });
  }
}
function onUp(ev) {
  if (!drag) return;
  drag.g.classList.remove('dragging');
  var id = drag.id;
  drag = null;
  incidentMap[id].forEach(function (i) { reanchor(i); updateEdge(i); });
  refreshMarkers();
  refreshMetrics();
}
svg.addEventListener('pointerdown', onDown);
window.addEventListener('pointermove', onMove);
window.addEventListener('pointerup', onUp);
window.addEventListener('pointercancel', onUp);
function exportLayout() {
  var out = {tool: 'stdraw', kind: 'manual-layout', graph: D.name,
             viewBox: VB.slice(), nodes: {}};
  Object.keys(nodes).forEach(function (v) {
    out.nodes[v] = {x: Math.round(nodes[v].x), y: Math.round(nodes[v].y)};
  });
  var txt = JSON.stringify(out, null, 1);
  try {
    var blob = new Blob([txt], {type: 'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (D.name || 'graph') + '-manual-layout.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  } catch (e) { /* 沙箱/无下载 API 环境：探针走 __stdrawExportJSON */ }
  return out;
}
function reset() {
  Object.keys(nodes).forEach(function (v) {
    var n = nodes[v];
    n.x = n.bx; n.y = n.by;
    if (n.g) n.g.removeAttribute('transform');
  });
  edges.forEach(function (e, i) {
    e.pts = e.base.map(function (p) { return [p[0], p[1]]; });
    updateEdge(i);
  });
  Object.keys(polGroups).forEach(function (i) {
    polGroups[i].g.setAttribute('transform', polGroups[i].t);
  });
  refreshMetrics();
}
window.__stdrawExportLayout = exportLayout;
window.__stdrawExportJSON = function () { return JSON.stringify(exportLayout(), null, 1); };
window.__stdrawMetrics = metrics;
window.__stdrawNodePos = function (v) {
  return v ? [nodes[v].x, nodes[v].y]
           : Object.keys(nodes).map(function (k) { return [k, nodes[k].x, nodes[k].y]; });
};
var btnE = document.getElementById('stdraw-export');
var btnR = document.getElementById('stdraw-reset');
if (btnE) btnE.addEventListener('click', exportLayout);
if (btnR) btnR.addEventListener('click', reset);
refreshMetrics();
})();
"""
