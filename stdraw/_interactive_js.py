

# ═══ Interactive layer script (drag rearrange; re-routing + bend handles) ═══
# Pure vanilla JS (zero dependencies, zero network). Attached to pages generated
# by render_auto_html:
#   - drag nodes (SVG pointer events, mouse/touch unified; clamped to the
#     viewBox while dragging);
#   - live "all line kinds re-routed while dragging" (preview caliber):
#       · straight/vg polylines: a JS port of the visibility-graph
#         shortest-path router (same mathematical caliber as
#         stdraw/routing+visibility: straight-line candidates need 16px
#         clearance, otherwise inflated-corner visibility graph Dijkstra +
#         string-pulling shortcuts, inflation 17.5px) — bends recomputed on
#         every drag, no more pinned midpoints (fixes the root cause of the
#         user-reported issue 2: the old reanchor only rebuilt endpoints and
#         waypoints stayed pinned in place);
#       · arcs: quadratic Bezier endpoint re-anchoring + control point
#         translated by the mean endpoint displacement, all vertices follow;
#       · unrelated edges pressed by the moving node (1px margin) also
#         trigger re-routing;
#   - draggable bend handles: each bend of a vg polyline (route.via non-empty)
#     renders as a small circular handle (move cursor on hover); dragging it
#     marks the edge "user-anchored" — afterwards node drags only re-anchor
#     endpoints and keep user waypoints; the exported layout JSON carries
#     edges[].waypoints, and CLI --from-layout recomputes under the same
#     caliber (anchors = box border facing the first/last waypoint);
#   - live metrics in the top bar (truly computed on preview geometry:
#     crossings / 1px card presses / card gap / CV / row alignment);
#   - full metric refresh on release + deterministic replay of R/B polarity
#     markers (same caliber as render._polarity_marker);
#   - "Export layout" downloads a manual-layout JSON (rounded coordinates, a
#     layout.json-compatible subset);
#   - "Reset" restores the initial layout (incl. original path_d rendering and
#     handle removal).
# Determinism: the generated HTML contains no timestamps/random numbers;
# without dragging the initial geometry is pixel-identical to the static render.
_INTERACTIVE_JS = r"""(function () {
'use strict';
var dataEl = document.getElementById('stdraw-data');
if (!dataEl) return;
var D = JSON.parse(dataEl.textContent);
var svg = document.getElementById('stdraw-svg');
var VB = D.viewBox, cardH = D.cardH;
var CL = 16, VG_C = 17.5, VEPS = 1e-6;   // same caliber as routing.CLEARANCE / +VG_PAD
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
function cp(p) { return [p[0], p[1]]; }
var edges = D.edges.map(function (e) {
  var pts = e.pts, arc = !!e.arc && !!e.ctrl && pts.length >= 2;
  if (arc) pts = quad(pts[0], e.ctrl, pts[pts.length - 1], 12);
  pts = pts.map(cp);
  return {a: e.a, b: e.b, pol: e.pol, arc: arc,
          ctrl0: arc ? cp(e.ctrl) : null,
          pa0: cp(pts[0]), pb0: cp(pts[pts.length - 1]),
          via: (e.via && e.via.length >= 3) ? e.via.map(cp) : null,
          corners: (e.via && e.via.length >= 3) ? e.via.map(cp) : null,
          pts: pts, base: pts.map(cp), d0: null};
});
edges.forEach(function (e, i) {
  var g = svg.querySelector('[data-edge="' + i + '"]');
  if (g) {
    var p0 = g.querySelectorAll('path')[0];
    if (p0) e.d0 = p0.getAttribute('d');
  }
});
var polGroups = {};
// R/B text badges removed (loop polarity is expressed by edge coloring; the
// static stroke attributes are kept while dragging); polGroups/refreshMarkers
// remain as empty implementations for old page-structure compatibility.
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
  // Connector delivery caliber: ray-determined border exit -> the anchor is
  // clamped along that border's tangent into the edge-midpoint +/-1/4 edge
  // length band (orthogonal exits land on the midpoint, diagonal exits are
  // pulled back into the band, corners excluded).
  // Same caliber as Python routing.border_point + Router.midband_reanchor.
  var dx = toward[0] - c[0], dy = toward[1] - c[1];
  if (!dx && !dy) return [c[0], c[1]];
  if (!dx) return [c[0], c[1] + (dy > 0 ? hh : -hh)];
  if (!dy) return [c[0] + (dx > 0 ? hw : -hw), c[1]];
  var t = Math.min(hw / Math.abs(dx), hh / Math.abs(dy));
  var px = c[0] + dx * t, py = c[1] + dy * t;
  var onX = Math.abs(Math.abs(px - c[0]) - hw) <= Math.abs(Math.abs(py - c[1]) - hh);
  if (onX) {
    var limY = hh / 2;
    return [px, c[1] + Math.max(-limY, Math.min(limY, py - c[1]))];
  }
  var limX = hw / 2;
  return [c[0] + Math.max(-limX, Math.min(limX, px - c[0])), py];
}
function reanchor(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pts = e.pts.map(cp);
  var inner = pts.length > 2;
  pts[0] = borderPoint([A.x, A.y], A.w / 2, cardH / 2, inner ? pts[1] : [B.x, B.y]);
  pts[pts.length - 1] = borderPoint([B.x, B.y], B.w / 2, cardH / 2, inner ? pts[pts.length - 2] : [A.x, A.y]);
  e.pts = pts;
}

// ── JS-side preview router (visibility-graph shortest path, same mathematical caliber as visibility.py) ──
function ptSegDist(px, py, a, b) {
  var vx = b[0] - a[0], vy = b[1] - a[1], L2 = vx * vx + vy * vy;
  if (L2 < VEPS) return Math.hypot(px - a[0], py - a[1]);
  var t = Math.max(0, Math.min(1, ((px - a[0]) * vx + (py - a[1]) * vy) / L2));
  return Math.hypot(px - (a[0] + t * vx), py - (a[1] + t * vy));
}
function ornt(a, b, c) {
  var v = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
  return Math.abs(v) < VEPS ? 0 : (v > 0 ? 1 : -1);
}
function segSegDist(p1, p2, p3, p4) {
  var d1 = ornt(p3, p4, p1), d2 = ornt(p3, p4, p2),
      d3 = ornt(p1, p2, p3), d4 = ornt(p1, p2, p4);
  if (d1 !== d2 && d3 !== d4 && d1 !== 0 && d3 !== 0) return 0.0;
  return Math.min(ptSegDist(p1[0], p1[1], p3, p4),
                  ptSegDist(p2[0], p2[1], p3, p4),
                  ptSegDist(p3[0], p3[1], p1, p2),
                  ptSegDist(p4[0], p4[1], p1, p2));
}
function segHitsRect(x1, y1, x2, y2, cx, cy, hw, hh) {
  var dx = x2 - x1, dy = y2 - y1, t0 = 0.0, t1 = 1.0;
  var pq = [[-dx, x1 - (cx - hw)], [dx, (cx + hw) - x1],
            [-dy, y1 - (cy - hh)], [dy, (cy + hh) - y1]];
  for (var k = 0; k < 4; k++) {
    var p = pq[k][0], q = pq[k][1];
    if (Math.abs(p) < VEPS) { if (q < 0) return false; }
    else {
      var r = q / p;
      if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; }
      else { if (r < t0) return false; if (r < t1) t1 = r; }
    }
  }
  return t1 - t0 > VEPS;
}
function segRectDist(p1, p2, r) {
  if (segHitsRect(p1[0], p1[1], p2[0], p2[1], r[0], r[1], r[2], r[3])) return 0.0;
  var cx = r[0], cy = r[1], hw = r[2], hh = r[3];
  var cs = [[cx-hw, cy-hh], [cx+hw, cy-hh], [cx+hw, cy+hh], [cx-hw, cy+hh]];
  var best = Infinity;
  for (var k = 0; k < 4; k++) {
    best = Math.min(best, segSegDist(p1, p2, cs[k], cs[(k + 1) % 4]));
  }
  return best;
}
function visible(p1, p2, rects, c) {
  var t = c - VEPS;
  var x1l = Math.min(p1[0], p2[0]), x1h = Math.max(p1[0], p2[0]);
  var y1l = Math.min(p1[1], p2[1]), y1h = Math.max(p1[1], p2[1]);
  for (var i = 0; i < rects.length; i++) {
    var r = rects[i];
    var gx = Math.max(r[0] - r[2] - x1h, x1l - r[0] - r[2], 0.0);
    var gy = Math.max(r[1] - r[3] - y1h, y1l - r[1] - r[3], 0.0);
    if (gx >= t || gy >= t) continue;              // bbox distance lower bound >= c: cannot block
    if (gx * gx + gy * gy >= t * t) continue;
    if (segRectDist(p1, p2, r) < t) return false;
  }
  return true;
}
function vgShortest(src, dst, rects, c) {
  if (!rects.length) return [cp(src), cp(dst)];
  var nds = [cp(src), cp(dst)];
  rects.forEach(function (r) {
    var gx = r[2] + c, gy = r[3] + c;
    nds.push([r[0]-gx, r[1]-gy], [r[0]+gx, r[1]-gy], [r[0]+gx, r[1]+gy], [r[0]-gx, r[1]+gy]);
  });
  var n = nds.length, adj = [];
  for (var k0 = 0; k0 < n; k0++) adj.push([]);
  for (var i = 0; i < n; i++) {
    for (var j = i + 1; j < n; j++) {
      if (visible(nds[i], nds[j], rects, c)) {
        var w = Math.hypot(nds[i][0]-nds[j][0], nds[i][1]-nds[j][1]);
        adj[i].push([j, w]); adj[j].push([i, w]);
      }
    }
  }
  // Deterministic Dijkstra: array scan for the minimum (ties break to the lower index), same input same output
  var INF = Infinity, dist = [], prev = [], done = [];
  for (var k1 = 0; k1 < n; k1++) { dist.push(INF); prev.push(-1); done.push(false); }
  dist[0] = 0;
  for (var it = 0; it < n; it++) {
    var u = -1, best = INF;
    for (var k2 = 0; k2 < n; k2++) if (!done[k2] && dist[k2] < best - VEPS) { best = dist[k2]; u = k2; }
    if (u < 0) break;
    done[u] = true;
    if (u === 1) break;
    for (var e2 = 0; e2 < adj[u].length; e2++) {
      var v = adj[u][e2][0], nd = dist[u] + adj[u][e2][1];
      if (nd < dist[v] - VEPS) { dist[v] = nd; prev[v] = u; }
    }
  }
  if (dist[1] >= INF) return null;
  var path = [], cur = 1;
  while (cur !== -1) { path.push(cp(nds[cur])); cur = prev[cur]; }
  path.reverse();
  return path;
}
function shortcut(path, rects, c) {
  var pts = path.map(cp);
  for (var round = 0; round < 3; round++) {
    var changed = false, i = 1;
    while (i < pts.length - 1) {
      if (visible(pts[i - 1], pts[i + 1], rects, c)) { pts.splice(i, 1); changed = true; }
      else i++;
    }
    if (!changed) break;
  }
  return pts;
}
function rectsFor(a, b) {
  var out = [];
  Object.keys(nodes).forEach(function (v) {
    if (v === a || v === b) return;
    var n = nodes[v];
    out.push([n.x, n.y, n.w / 2, cardH / 2]);
  });
  return out;
}
function previewRoute(i) {
  // Preview-caliber routing: straight line when visible; otherwise
  // visibility-graph detour (same math as the Python router, without fillet
  // smoothing and mutual-pair separation — the certificate remains
  // authoritative via CLI recomputation).
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = borderPoint([A.x, A.y], A.w / 2, cardH / 2, [B.x, B.y]);
  var pb = borderPoint([B.x, B.y], B.w / 2, cardH / 2, [A.x, A.y]);
  var rects = rectsFor(e.a, e.b);
  if (visible(pa, pb, rects, CL)) { e.pts = [pa, pb]; e.corners = null; return; }
  var path = vgShortest(pa, pb, rects, VG_C);
  if (path && path.length >= 2) {
    e.pts = shortcut(path, rects, VG_C);
    e.corners = (e.pts.length >= 3) ? e.pts.map(cp) : null;
    return;
  }
  reanchor(i);   // fallback (unreachable): shape-preserving re-anchor
}
function arcFollow(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = borderPoint([A.x, A.y], A.w / 2, cardH / 2, [B.x, B.y]);
  var pb = borderPoint([B.x, B.y], B.w / 2, cardH / 2, [A.x, A.y]);
  var ctrl = [e.ctrl0[0] + ((pa[0] - e.pa0[0]) + (pb[0] - e.pb0[0])) / 2,
              e.ctrl0[1] + ((pa[1] - e.pa0[1]) + (pb[1] - e.pb0[1])) / 2];
  e.pts = quad(pa, ctrl, pb, 12);
  e.corners = null;
}
function reroute(i) {
  if (pinned[i]) { reanchor(i); return; }      // user-anchored: re-anchor endpoints only, keep waypoints
  if (edges[i].arc) { arcFollow(i); return; }
  previewRoute(i);
}

// ── Bend handles (vg polylines / user-anchored edges) ──
var pinned = {};          // edgeIdx -> true (user dragged a handle = waypoints anchored)
var NS = 'http://www.w3.org/2000/svg';
var styleEl = document.createElement('style');
styleEl.textContent = '#stdraw-handles circle.stdraw-wp{fill:#fff;stroke:#475569;' +
  'stroke-width:1.4;cursor:move;pointer-events:all}' +
  '#stdraw-handles circle.stdraw-wp:hover{stroke:#dc2626;fill:#fef2f2}';
document.head.appendChild(styleEl);
var handleLayer = document.createElementNS(NS, 'g');
handleLayer.id = 'stdraw-handles';
svg.appendChild(handleLayer);
function edgeHasHandles(i) {
  var e = edges[i];
  if (e.arc) return false;
  if (pinned[i]) return e.pts.length >= 3;
  return !!(e.corners && e.corners.length >= 3);
}
function handlePts(i) {     // handle positions: unanchored = current corners; anchored = midpoints of pts
  return pinned[i] ? edges[i].pts : edges[i].corners;
}
function rebuildHandles() {
  while (handleLayer.firstChild) handleLayer.removeChild(handleLayer.firstChild);
  edges.forEach(function (e, i) {
    if (!edgeHasHandles(i)) return;
    var pts = handlePts(i);
    if (!pts || pts.length < 3) return;
    for (var k = 1; k < pts.length - 1; k++) {
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', pts[k][0].toFixed(1));
      c.setAttribute('cy', pts[k][1].toFixed(1));
      c.setAttribute('r', '4');
      c.setAttribute('class', 'stdraw-wp');
      c.setAttribute('data-edge', i);
      c.setAttribute('data-wp', k);
      handleLayer.appendChild(c);
    }
  });
}
function pinEdge(i) {
  if (pinned[i]) return;
  var e = edges[i];
  // User-anchored waypoints = midpoints of the current corners (endpoint
  // anchors are recomputed on the box border by CLI/re-anchoring, and are not
  // exported as waypoints — avoiding redundant bends coinciding with anchors)
  var cs = (e.corners && e.corners.length >= 3) ? e.corners : e.pts;
  var via = cs.slice(1, -1).map(cp);
  if (via.length < 1) return;
  var A = nodes[e.a], B = nodes[e.b];
  // Same caliber as CLI --from-layout: anchor = box border facing the first/last waypoint
  var pts = [borderPoint([A.x, A.y], A.w / 2, cardH / 2, via[0])];
  pts = pts.concat(via);
  pts.push(borderPoint([B.x, B.y], B.w / 2, cardH / 2, via[via.length - 1]));
  e.pts = pts;
  e.corners = pts.map(cp);
  pinned[i] = true;
}

function segCross(p1, p2, p3, p4) {
  function or(a, b, c) {
    var v = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
    return Math.abs(v) < 1e-9 ? 0 : (v > 0 ? 1 : -1);
  }
  var d1 = or(p3,p4,p1), d2 = or(p3,p4,p2), d3 = or(p1,p2,p3), d4 = or(p1,p2,p4);
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
  el.textContent = 'crossings ' + m.crossings + ' · presses(1px) ' + m.press +
    ' · card gap ' + m.minGap + 'px · CV ' + m.cv + ' · row align ' + m.row;
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
  // Badges removed (edge coloring carries R/B polarity) — empty implementation keeps the interface.
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
  var h = t && t.closest ? t.closest('.stdraw-wp') : null;
  if (h) {
    var ei = +h.getAttribute('data-edge'), wi = +h.getAttribute('data-wp');
    if (!edges[ei]) return;
    pinEdge(ei);
    updateEdge(ei);
    var p0 = svgPoint(ev);
    drag = {wp: true, edge: ei, idx: wi, start: [p0.x, p0.y],
            ox: edges[ei].pts[wi][0], oy: edges[ei].pts[wi][1], g: h};
    try { h.setPointerCapture(ev.pointerId); } catch (e) {}
    ev.preventDefault();
    ev.stopPropagation();
    return;
  }
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
  if (drag.wp) {
    var e = edges[drag.edge];
    var wx = drag.ox + (p.x - drag.start[0]);
    var wy = drag.oy + (p.y - drag.start[1]);
    wx = Math.max(4, Math.min(VB[2] - 4, wx));
    wy = Math.max(4, Math.min(VB[3] - 4, wy));
    e.pts[drag.idx] = [wx, wy];
    updateEdge(drag.edge);
    rebuildHandles();
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(function () { rafPending = false; refreshMetrics(); });
    }
    return;
  }
  var n = nodes[drag.id];
  var nx = drag.ox + (p.x - drag.start[0]);
  var ny = drag.oy + (p.y - drag.start[1]);
  nx = Math.max(n.w / 2 + 2, Math.min(VB[2] - n.w / 2 - 2, nx));
  ny = Math.max(cardH / 2 + 2, Math.min(VB[3] - cardH / 2 - 2, ny));
  n.x = nx; n.y = ny;
  drag.g.setAttribute('transform', 'translate(' + (nx - n.bx).toFixed(1) + ' ' + (ny - n.by).toFixed(1) + ')');
  var touched = {};
  incidentMap[drag.id].forEach(function (i) { touched[i] = 1; reroute(i); updateEdge(i); });
  // Other edges: (1) pressed by the moving node (1px margin) -> re-route;
  // (2) currently polyline-shaped (detour / dense vg geometry) -> obstacles
  // changed so recompute (incl. stale detours invalidated when an obstacle is
  // dragged away). Preview caliber; user-anchored edges excepted (waypoints
  // preserved, endpoints re-anchored only).
  var hw = n.w / 2 + 1, hh = cardH / 2 + 1;
  edges.forEach(function (e2, j) {
    if (touched[j] || pinned[j] || e2.a === drag.id || e2.b === drag.id) return;
    var need = e2.pts.length > 2;
    if (!need) {
      var s = samplePts(e2.pts, 6);
      for (var k = 0; k < s.length; k++) {
        if (distRect(s[k][0], s[k][1], nx, ny, hw, hh) <= 0) { need = true; break; }
      }
    }
    if (need) { reroute(j); updateEdge(j); }
  });
  rebuildHandles();
  if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(function () { rafPending = false; refreshMetrics(); });
  }
}
function onUp(ev) {
  if (!drag) return;
  if (drag.wp) {
    drag = null;
    rebuildHandles();
    refreshMarkers();
    refreshMetrics();
    return;
  }
  drag.g.classList.remove('dragging');
  var id = drag.id;
  drag = null;
  incidentMap[id].forEach(function (i) { reroute(i); updateEdge(i); });
  rebuildHandles();
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
  // Waypoints of user-anchored edges (deterministic: original edge order, rounded coordinates)
  var wps = [];
  edges.forEach(function (e, i) {
    if (!pinned[i]) return;
    wps.push({a: e.a, b: e.b,
              waypoints: e.pts.slice(1, -1).map(function (p) {
                return [Math.round(p[0]), Math.round(p[1])];
              })});
  });
  if (wps.length) out.edges = wps;
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
  } catch (e) { /* sandboxed / no download API: probes go through __stdrawExportJSON */ }
  return out;
}
function reset() {
  pinned = {};
  Object.keys(nodes).forEach(function (v) {
    var n = nodes[v];
    n.x = n.bx; n.y = n.by;
    if (n.g) n.g.removeAttribute('transform');
  });
  edges.forEach(function (e, i) {
    e.pts = e.base.map(cp);
    e.corners = e.via ? e.via.map(cp) : null;
    var g = svg.querySelector('[data-edge="' + i + '"]');
    if (!g) return;
    var paths = g.querySelectorAll('path');
    // Original rendering (vg path_d incl. fillet arcs) restored from the initial d strings
    if (paths[0] && e.d0) paths[0].setAttribute('d', e.d0);
    else if (paths[0]) paths[0].setAttribute('d', edgeD(e.pts));
    if (paths[1]) {
      var n2 = e.pts.length, a = e.pts[n2 - 2], b = e.pts[n2 - 1];
      var ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
      paths[1].setAttribute('transform', 'translate(' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) + ') rotate(' + ang.toFixed(1) + ')');
    }
  });
  Object.keys(polGroups).forEach(function (i) {
    polGroups[i].g.setAttribute('transform', polGroups[i].t);
  });
  rebuildHandles();
  refreshMetrics();
}
window.__stdrawExportLayout = exportLayout;
window.__stdrawExportJSON = function () { return JSON.stringify(exportLayout(), null, 1); };
window.__stdrawMetrics = metrics;
window.__stdrawNodePos = function (v) {
  return v ? [nodes[v].x, nodes[v].y]
           : Object.keys(nodes).map(function (k) { return [k, nodes[k].x, nodes[k].y]; });
};
// Probe hooks: current polyline vertices / anchored state / vg edge list / handle list
window.__stdrawEdgePts = function (i) {
  return (i === undefined || i === null)
    ? edges.map(function (e) { return e.pts; })
    : (edges[i] ? edges[i].pts : null);
};
window.__stdrawPinned = function () {
  return Object.keys(pinned).map(Number);
};
window.__stdrawVgEdges = function () {
  var out = [];
  edges.forEach(function (e, i) { if (e.via) out.push(i); });
  return out;
};
window.__stdrawHandles = function () {
  var out = [];
  handleLayer.querySelectorAll('.stdraw-wp').forEach(function (c) {
    out.push([+c.getAttribute('data-edge'), +c.getAttribute('data-wp'),
              +c.getAttribute('cx'), +c.getAttribute('cy')]);
  });
  return out;
};
var btnE = document.getElementById('stdraw-export');
var btnR = document.getElementById('stdraw-reset');
if (btnE) btnE.addEventListener('click', exportLayout);
if (btnR) btnR.addEventListener('click', reset);
rebuildHandles();
refreshMetrics();
})();
"""
