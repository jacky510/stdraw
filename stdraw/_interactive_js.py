

# ═══ Interactive layer script (drag rearrange; re-routing + bend handles;
# per-edge style cycle + free fold points + apply API) ═══
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
#         every drag, no more pinned midpoints (fixes the root cause of
#         the user-reported issue 2: the old reanchor only rebuilt endpoints and
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
#   - v0.7.7 per-edge style cycle: double-click a line to cycle
#     auto -> straight -> arc -> free -> auto (>=10px hover hit zone,
#     pointer cursor + highlight; double-click never disturbs node drags);
#     forced states re-route live and the top-bar metrics recompute
#     honestly (red when a hard gate fails — no leniency);
#   - v0.7.7 free fold points: in free mode click the line to insert a
#     handle (exact WYSIWYG polyline, no smoothing; endpoints re-anchored
#     on the box borders facing the first/last fold point); at most 3 user
#     fold points per edge — at the cap a click selects the nearest handle
#     with the tooltip "max 3 points per edge";
#   - v0.7.7 persistence: "Export layout" writes edges[].style (+ fold
#     points as waypoints); window.__stdrawApplyLayout({nodes, edge_styles,
#     waypoints}) restores a layout programmatically; every drag release /
#     fold-point insert / style change / reset dispatches the CustomEvent
#     "stdraw:layoutchanged" on window (detail = the current layout), so
#     product integrations can drop pointerup polling;
#   - live metrics in the top bar (truly computed on preview geometry:
#     crossings / 1px card presses / card gap / CV / row alignment);
#   - full metric refresh on release + deterministic replay of R/B polarity
#     markers (same caliber as render._polarity_marker);
#   - v0.7.9 font-environment robustness: after render, the ACTUAL DOM text
#     geometry is measured (getComputedTextLength/getBBox) per card; when the
#     rendered text overflows the planned card rect the rect is grown (never
#     shrunk) to fit and every edge re-anchors on the new border -- when the
#     browser inflates DOM text (minimum font size / user font scale, which
#     the engine-side text metrics cannot see) lines still hug the rendered
#     frame at 0px. No-op when measured geometry matches the plan (initial
#     render stays pixel-identical to the static rendering); public hook:
#     window.__stdrawSyncDomGeometry();
#   - "Reset" restores the initial layout (incl. original path_d rendering,
#     handle removal, style + fold-point clearing).
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
D.nodes.forEach(function (n) { nodes[n.id] = {x: n.x, y: n.y, w: n.w, h: cardH, bx: n.x, by: n.y, g: null}; });
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
// ── v0.7.7 per-edge hover hit zones (>=10px, pointer cursor, highlight) ──
var SVGNS_EARLY = 'http://www.w3.org/2000/svg';
var hitLayer = document.createElementNS(SVGNS_EARLY, 'g');
hitLayer.id = 'stdraw-hits';
svg.insertBefore(hitLayer, svg.firstChild);
edges.forEach(function (e, i) {
  var h = document.createElementNS(SVGNS_EARLY, 'path');
  h.setAttribute('class', 'stdraw-hit');
  h.setAttribute('data-edge', i);
  h.setAttribute('d', edgeD(e.pts));
  h.addEventListener('mouseenter', function () { hlEdge(i, true); });
  h.addEventListener('mouseleave', function () { hlEdge(i, false); });
  hitLayer.appendChild(h);
});
function hlEdge(i, on) {
  var g = svg.querySelector('[data-edge="' + i + '"]');
  if (g) { if (on) g.classList.add('hl'); else g.classList.remove('hl'); }
}
function updateEdge(i) {
  var e = edges[i], g = svg.querySelector('[data-edge="' + i + '"]');
  var h = hitLayer.querySelector('.stdraw-hit[data-edge="' + i + '"]');
  if (h) h.setAttribute('d', edgeD(e.pts));
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
// v0.7.9 per-card height: every border/obstacle/metrics site below uses the
// node's own h (synced to the rendered DOM geometry by syncDomGeometry)
// instead of the global planned cardH, so anchors always match the frame the
// user actually sees.
function nHH(n) { return (n.h || cardH) / 2; }
function anchor(n, toward) { return borderPoint([n.x, n.y], n.w / 2, nHH(n), toward); }
function reanchor(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pts = e.pts.map(cp);
  var inner = pts.length > 2;
  pts[0] = anchor(A, inner ? pts[1] : [B.x, B.y]);
  pts[pts.length - 1] = anchor(B, inner ? pts[pts.length - 2] : [A.x, A.y]);
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
    out.push([n.x, n.y, n.w / 2, nHH(n)]);
  });
  return out;
}
function previewRoute(i) {
  // Preview-caliber routing: straight line when visible; otherwise
  // visibility-graph detour (same math as the Python router, without fillet
  // smoothing and mutual-pair separation — the certificate remains
  // authoritative via CLI recomputation).
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = anchor(A, [B.x, B.y]);
  var pb = anchor(B, [A.x, A.y]);
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
  var pa = anchor(A, [B.x, B.y]);
  var pb = anchor(B, [A.x, A.y]);
  var ctrl = [e.ctrl0[0] + ((pa[0] - e.pa0[0]) + (pb[0] - e.pb0[0])) / 2,
              e.ctrl0[1] + ((pa[1] - e.pa0[1]) + (pb[1] - e.pb0[1])) / 2];
  e.pts = quad(pa, ctrl, pb, 12);
  e.corners = null;
}
// ── v0.7.7 forced geometries (per-edge style cycle; same math caliber as
// the Python replay in layout_auto._manual_edge_styles/_forced_arc_route) ──
function forcedStraight(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = anchor(A, [B.x, B.y]);
  var pb = anchor(B, [A.x, A.y]);
  e.pts = [pa, pb];
  e.corners = null;
}
function adaptiveArcK(d) {
  // same parameterization as routing.adaptive_arc_k
  var bulge = Math.min(6.0 + 0.06 * d, 40.0);
  var k = 2.0 * bulge / Math.max(d, 1e-6);
  return Math.max(0.12, Math.min(0.50, k));
}
function forcedArc(i) {
  // anchors = box borders facing each other; curvature = chord-adaptive k;
  // side = the sign whose sampled arc keeps more distance from unrelated
  // boxes (deterministic tie -> +1). Same rule as the Python replay.
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = anchor(A, [B.x, B.y]);
  var pb = anchor(B, [A.x, A.y]);
  var vx = pb[0] - pa[0], vy = pb[1] - pa[1], d = Math.hypot(vx, vy);
  var k = adaptiveArcK(d), n = Math.max(d, 1e-6);
  var ux = -vy / n, uy = vx / n;
  var best = null;
  [1, -1].forEach(function (s) {
    var ctrl = [(pa[0] + pb[0]) / 2 + ux * k * d * s,
                (pa[1] + pb[1]) / 2 + uy * k * d * s];
    var pts = quad(pa, ctrl, pb, 12);
    var mclr = null;
    Object.keys(nodes).forEach(function (v) {
      if (v === e.a || v === e.b) return;
      var nn = nodes[v];
      for (var q = 0; q < pts.length; q++) {
        var dd = distRect(pts[q][0], pts[q][1], nn.x, nn.y, nn.w / 2, nHH(nn));
        mclr = (mclr === null) ? dd : Math.min(mclr, dd);
      }
    });
    var key = (-(mclr === null ? 1e9 : mclr));
    if (best === null || key < best[0]) best = [key, pts, ctrl];
  });
  e.pts = best[1];
  e.corners = null;
}
function reanchorFree(i) {
  // free mode: exact polyline over the user fold points; endpoints = box
  // borders facing the first/last fold point (same caliber as waypoints)
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var wps = freeWps[i];
  if (!wps || !wps.length) { forcedStraight(i); return; }
  var pts = [anchor(A, wps[0])];
  pts = pts.concat(wps.map(cp));
  pts.push(anchor(B, wps[wps.length - 1]));
  e.pts = pts;
  e.corners = null;
}
function reroute(i) {
  var st = styles[i] || 'auto';
  if (st === 'free') { reanchorFree(i); return; }   // user fold points: re-anchor endpoints only
  if (pinned[i]) { reanchor(i); return; }           // user-anchored: re-anchor endpoints only, keep waypoints
  if (st === 'straight') { forcedStraight(i); return; }
  if (st === 'arc') { forcedArc(i); return; }
  if (edges[i].arc) { arcFollow(i); return; }
  previewRoute(i);
}

// ── Bend handles (vg polylines / user-anchored edges) ──
var pinned = {};          // edgeIdx -> true (user dragged a handle = waypoints anchored)
// v0.7.7 per-edge style cycle: edgeIdx -> 'auto' | 'straight' | 'arc' | 'free'
// (auto = engine default routing; free = exact polyline on user fold points)
var styles = {};
var freeWps = {};         // edgeIdx -> [[x,y], ...] user fold points (free mode, max 3)
var MAX_FREE_PTS = 3;     // per-edge user fold-point cap
var NS = 'http://www.w3.org/2000/svg';
var styleEl = document.createElement('style');
styleEl.textContent = '#stdraw-handles circle.stdraw-wp{fill:#fff;stroke:#475569;' +
  'stroke-width:1.4;cursor:move;pointer-events:all}' +
  '#stdraw-handles circle.stdraw-wp:hover{stroke:#dc2626;fill:#fef2f2}' +
  '#stdraw-handles circle.stdraw-wp.sel{stroke:#dc2626;fill:#fef2f2}' +
  '#stdraw-svg path.stdraw-hit{fill:none;stroke:transparent;stroke-width:12;cursor:pointer;pointer-events:stroke}' +
  '#stdraw-svg [data-edge].hl > path:not(.stdraw-hit){stroke-width:2.4}' +
  '.stdraw-tip{position:absolute;z-index:9;background:#1f2937;color:#fff;' +
  'font:12px/1.4 sans-serif;padding:3px 8px;border-radius:4px;pointer-events:none}';
document.head.appendChild(styleEl);
var handleLayer = document.createElementNS(NS, 'g');
handleLayer.id = 'stdraw-handles';
svg.appendChild(handleLayer);
function edgeHasHandles(i) {
  var e = edges[i];
  if ((styles[i] || 'auto') === 'free') return !!(freeWps[i] && freeWps[i].length);
  if (e.arc) return false;
  if (pinned[i]) return e.pts.length >= 3;
  return !!(e.corners && e.corners.length >= 3);
}
function handlePts(i) {     // handle positions: free = user fold points; unanchored = current corners; anchored = midpoints of pts
  if ((styles[i] || 'auto') === 'free') return freeWps[i] || [];
  return pinned[i] ? edges[i].pts : edges[i].corners;
}
function rebuildHandles() {
  while (handleLayer.firstChild) handleLayer.removeChild(handleLayer.firstChild);
  edges.forEach(function (e, i) {
    if (!edgeHasHandles(i)) return;
    var pts = handlePts(i);
    if (!pts || pts.length < 1) return;
    if ((styles[i] || 'auto') === 'free') {
      // free-mode handles: one per user fold point (data-wp = fold index;
      // pts index = fold index + 1)
      for (var kf = 0; kf < pts.length; kf++) {
        var cf = document.createElementNS(NS, 'circle');
        cf.setAttribute('cx', pts[kf][0].toFixed(1));
        cf.setAttribute('cy', pts[kf][1].toFixed(1));
        cf.setAttribute('r', '4');
        cf.setAttribute('class', 'stdraw-wp');
        cf.setAttribute('data-edge', i);
        cf.setAttribute('data-wp', kf + 1);
        cf.setAttribute('data-free', '1');
        handleLayer.appendChild(cf);
      }
      return;
    }
    if (pts.length < 3) return;
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
  var pts = [anchor(A, via[0])];
  pts = pts.concat(via);
  pts.push(anchor(B, via[via.length - 1]));
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
        if (distRect(pts[k][0], pts[k][1], n.x, n.y, n.w / 2 + 1, nHH(n) + 1) <= 0) { press++; break; }
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
      var dgy = Math.abs(na.y - nb.y) - nHH(na) - nHH(nb);
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
  // honest hard-gate coloring (no leniency): red when a gate clearly fails
  el.style.color = (m.press > 0 || m.crossings > 2 || m.minGap < 16) ? '#dc2626' : '';
}
// ── v0.7.9 font-environment robustness: post-render DOM geometry re-anchor ──
// The planned card geometry is produced by the engine-side text metrics layer
// (PIL measurement at generation time) and cannot see browser font settings.
// When the browser inflates the DOM text (minimum font size / user font
// scale), the rendered label overflows the planned rect while the edges stay
// anchored to the planned border -> floating arrows (jacky's Edge outage,
// ref-scrubbed). Here the ACTUAL rendered text is measured per card
// (getComputedTextLength + getBBox), the rect is grown (never shrunk) to fit
// with the same conservative padding discipline as textmetrics.py
// (>=12px per side + 6% stretch margin), the node geometry every router /
// metrics path consumes is updated, and all edges re-anchor + re-route on the
// new borders at 0px. Determinism: when the measured geometry fits inside the
// plan the function is a strict no-op (the initial render stays pixel-
// identical to the static rendering; the byte-frozen delivery contract is
// untouched). Deterministic given the rendered geometry: fixed traversal
// order, no RNG, no timestamps.
function syncDomGeometry() {
  var touched = false;
  svg.querySelectorAll('[data-node]').forEach(function (g) {
    var id = g.getAttribute('data-node'), n = nodes[id];
    if (!n || !n.g) return;
    var rect = n.g.querySelector('rect');
    if (!rect) return;
    var mw = 0, top = Infinity, bot = -Infinity, texts = g.querySelectorAll('text');
    texts.forEach(function (t) {
      var w = 0;
      try { w = t.getComputedTextLength(); } catch (e1) {}
      try {
        var bb = t.getBBox();
        if (bb.width > w) w = bb.width;
        if (bb.y < top) top = bb.y;
        if (bb.y + bb.height > bot) bot = bb.y + bb.height;
      } catch (e2) {}
      if (w > mw) mw = w;
    });
    if (!(mw > 0)) return;
    // Grow-only + overflow-driven: the planned geometry (engine-side PIL text
    // metrics + conservative padding) is authoritative when the rendered text
    // already fits inside it (any blanket re-padding here would drift the
    // deterministic initial render -- measured, not assumed).
    var needW = n.w, needH = n.h;
    var wNeed = Math.ceil(mw * 1.06 + 24);   // textmetrics.py: >=12px/side + 6% stretch
    if (wNeed > needW + 0.5) needW = wNeed;
    if (top < bot && (top < n.by - n.h / 2 - 0.5 || bot > n.by + n.h / 2 + 0.5)) {
      // vertical text escape: fit the union with the plan's padding discipline
      var hNeed = Math.ceil((bot - top) * 1.06 + 14);
      if (hNeed > needH) needH = hNeed;
    }
    if (needW <= n.w + 0.5 && needH <= n.h + 0.5) return;   // fits: strict no-op
    var grewH = needH > n.h + 0.5;
    n.w = needW; n.h = needH;
    rect.setAttribute('x', (n.bx - needW / 2).toFixed(1));
    rect.setAttribute('y', (n.by - needH / 2).toFixed(1));
    rect.setAttribute('width', String(needW));
    rect.setAttribute('height', String(needH));
    // keep the secondary (value) line pinned to the new bottom inset when the
    // card grew taller (the label stays centered on the card middle)
    if (grewH && texts.length >= 2) {
      try { texts[texts.length - 1].setAttribute('y', (n.by + needH / 2 - 7).toFixed(1)); } catch (e3) {}
    }
    touched = true;
  });
  if (touched) {
    edges.forEach(function (e, i) { reroute(i); updateEdge(i); });
    rebuildHandles();
    refreshMetrics();
  }
  return touched;
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
// ── v0.7.7 per-edge style cycle: auto -> straight -> arc -> free -> auto ──
var STYLE_ORDER = ['auto', 'straight', 'arc', 'free'];
function setStyle(i, st) {
  if (st === 'auto') {
    delete styles[i];
    delete freeWps[i];
    delete pinned[i];       // back to the engine default state (no pins)
  } else {
    styles[i] = st;
  }
  if (st === 'free' && !freeWps[i]) freeWps[i] = [];
  reroute(i);
  updateEdge(i);
  rebuildHandles();
  refreshMetrics();
  fireLayoutChanged();
}
function cycleStyle(i) {
  var cur = styles[i] || 'auto';
  setStyle(i, STYLE_ORDER[(STYLE_ORDER.indexOf(cur) + 1) % STYLE_ORDER.length]);
}
// manual double-click detection on edge pointerdowns: a fold-point insert
// puts a handle circle exactly under the cursor, so the second click of a
// browser dblclick lands on a different target and the native dblclick
// never fires. Track edge pointerdown timestamps instead (deterministic).
var lastEdgeDown = {edge: -1, t: 0};
function edgeDblClickCheck(i) {
  var now = (window.performance && performance.now) ? performance.now() : Date.now();
  if (lastEdgeDown.edge === i && now - lastEdgeDown.t < 450) {
    lastEdgeDown = {edge: -1, t: 0};
    cycleStyle(i);
    return true;
  }
  lastEdgeDown = {edge: i, t: now};
  return false;
}
// ── v0.7.7 free-mode fold points: click inserts, max 3 per edge ──
function projectOnSeg(p, a, b) {
  var vx = b[0] - a[0], vy = b[1] - a[1], L2 = vx * vx + vy * vy;
  var t = L2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2));
  return [a[0] + t * vx, a[1] + t * vy];
}
var tipEl = null, tipTimer = null;
function showTip(text, ev) {
  if (tipEl) tipEl.remove();
  tipEl = document.createElement('div');
  tipEl.className = 'stdraw-tip';
  tipEl.textContent = text;
  document.body.appendChild(tipEl);
  var x = 40, y = 40;
  if (ev && typeof ev.clientX === 'number') { x = ev.clientX + 12; y = ev.clientY - 24; }
  tipEl.style.left = x + 'px';
  tipEl.style.top = y + 'px';
  if (tipTimer) clearTimeout(tipTimer);
  tipTimer = setTimeout(function () { if (tipEl) tipEl.remove(); tipEl = null; }, 1500);
}
function selectNearestFreeHandle(i, p) {
  var bestH = null, bestD = null;
  handleLayer.querySelectorAll('.stdraw-wp[data-free="1"]').forEach(function (c) {
    if (+c.getAttribute('data-edge') !== i) { c.classList.remove('sel'); return; }
    var d = Math.hypot(+c.getAttribute('cx') - p[0], +c.getAttribute('cy') - p[1]);
    if (bestD === null || d < bestD) { bestD = d; bestH = c; }
  });
  if (bestH) bestH.classList.add('sel');
}
function insertFreePoint(i, p, ev) {
  var wps = freeWps[i] = freeWps[i] || [];
  if (wps.length >= MAX_FREE_PTS) {
    selectNearestFreeHandle(i, p);
    showTip('max ' + MAX_FREE_PTS + ' points per edge', ev);
    return;
  }
  var pts = edges[i].pts;
  var best = null;
  for (var s = 0; s < pts.length - 1; s++) {
    var q = projectOnSeg(p, pts[s], pts[s + 1]);
    var d = Math.hypot(q[0] - p[0], q[1] - p[1]);
    if (best === null || d < best[0]) best = [d, s, q];
  }
  var wi = Math.min(best[1], wps.length);
  wps.splice(wi, 0, [Math.round(best[2][0] * 2) / 2, Math.round(best[2][1] * 2) / 2]);
  reanchorFree(i);
  updateEdge(i);
  rebuildHandles();
  refreshMetrics();
  fireLayoutChanged();
}
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
    var isFree = h.getAttribute('data-free') === '1';
    if (isFree && edgeDblClickCheck(ei)) {
      ev.preventDefault();
      return;
    }
    if (!isFree) {
      pinEdge(ei);
      updateEdge(ei);
    }
    var p0 = svgPoint(ev);
    drag = {wp: true, edge: ei, idx: wi, free: isFree, start: [p0.x, p0.y],
            ox: edges[ei].pts[wi][0], oy: edges[ei].pts[wi][1], g: h};
    try { h.setPointerCapture(ev.pointerId); } catch (e) {}
    ev.preventDefault();
    ev.stopPropagation();
    return;
  }
  var g = t && t.closest ? t.closest('[data-node]') : null;
  if (g) {
    var id = g.getAttribute('data-node');
    var p = svgPoint(ev);
    if (!p || !(id in nodes)) return;
    drag = {id: id, g: g, start: [p.x, p.y], ox: nodes[id].x, oy: nodes[id].y};
    try { g.setPointerCapture(ev.pointerId); } catch (e) {}
    g.classList.add('dragging');
    ev.preventDefault();
    return;
  }
  // free-mode fold-point insertion + double-click style cycle: any
  // pointerdown resolving to an edge (hit path / visible line / free
  // handle) participates in the double-click detection
  var eg = t && t.closest ? t.closest('[data-edge]') : null;
  if (eg) {
    var ei2 = +eg.getAttribute('data-edge');
    if (edges[ei2]) {
      if (edgeDblClickCheck(ei2)) {
        ev.preventDefault();
        return;
      }
      if ((styles[ei2] || 'auto') === 'free') {
        var p1 = svgPoint(ev);
        if (p1) {
          drag = {insert: true, edge: ei2, start: [p1.x, p1.y], ev: ev};
          ev.preventDefault();
        }
      }
    }
  }
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
    if (drag.free && freeWps[drag.edge]) freeWps[drag.edge][drag.idx - 1] = [wx, wy];
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
  ny = Math.max(nHH(n) + 2, Math.min(VB[3] - nHH(n) - 2, ny));
  n.x = nx; n.y = ny;
  drag.g.setAttribute('transform', 'translate(' + (nx - n.bx).toFixed(1) + ' ' + (ny - n.by).toFixed(1) + ')');
  var touched = {};
  incidentMap[drag.id].forEach(function (i) { touched[i] = 1; reroute(i); updateEdge(i); });
  // Other edges: (1) pressed by the moving node (1px margin) -> re-route;
  // (2) currently polyline-shaped (detour / dense vg geometry) -> obstacles
  // changed so recompute (incl. stale detours invalidated when an obstacle is
  // dragged away). Preview caliber; user-anchored edges excepted (waypoints
  // preserved, endpoints re-anchored only).
  var hw = n.w / 2 + 1, hh = nHH(n) + 1;
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
  if (drag.insert) {
    var pe = svgPoint(ev);
    var moved = pe ? Math.hypot(pe.x - drag.start[0], pe.y - drag.start[1]) : 1e9;
    if (moved < 4 && (styles[drag.edge] || 'auto') === 'free') {
      insertFreePoint(drag.edge, [pe.x, pe.y], ev);
    }
    drag = null;
    return;
  }
  if (drag.wp) {
    drag = null;
    rebuildHandles();
    refreshMarkers();
    refreshMetrics();
    fireLayoutChanged();
    return;
  }
  drag.g.classList.remove('dragging');
  var id = drag.id;
  drag = null;
  incidentMap[id].forEach(function (i) { reroute(i); updateEdge(i); });
  rebuildHandles();
  refreshMarkers();
  refreshMetrics();
  fireLayoutChanged();
}
svg.addEventListener('pointerdown', onDown);
window.addEventListener('pointermove', onMove);
window.addEventListener('pointerup', onUp);
window.addEventListener('pointercancel', onUp);
function buildLayout() {
  var out = {tool: 'stdraw', kind: 'manual-layout', graph: D.name,
             viewBox: VB.slice(), nodes: {}};
  Object.keys(nodes).forEach(function (v) {
    out.nodes[v] = {x: Math.round(nodes[v].x), y: Math.round(nodes[v].y)};
  });
  // v0.7.7: edges[] carries the per-edge style + user fold points
  // (deterministic: original edge order, rounded coordinates); legacy
  // user-anchored (pinned) edges keep the waypoints-only form
  var es = [];
  edges.forEach(function (e, i) {
    var st = styles[i] || 'auto';
    var wps = null;
    if (st === 'free' && freeWps[i] && freeWps[i].length) {
      wps = freeWps[i].map(function (p) {
        return [Math.round(p[0]), Math.round(p[1])];
      });
    } else if (pinned[i]) {
      wps = e.pts.slice(1, -1).map(function (p) {
        return [Math.round(p[0]), Math.round(p[1])];
      });
    }
    if (st !== 'auto' || (wps && wps.length)) {
      var it = {a: e.a, b: e.b, style: st};
      if (wps && wps.length) it.waypoints = wps;
      es.push(it);
    }
  });
  if (es.length) out.edges = es;
  return out;
}
function exportLayout() {
  var out = buildLayout();
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
// v0.7.7: layout-changed notification (drag release / fold-point insert /
// style cycle / reset / applyLayout) — product integrations can listen on
// window 'stdraw:layoutchanged' instead of polling pointerup
function fireLayoutChanged() {
  try {
    window.dispatchEvent(new CustomEvent('stdraw:layoutchanged',
                                         {detail: buildLayout()}));
  } catch (e) { /* CustomEvent unavailable: silent */ }
}
function reset() {
  pinned = {};
  styles = {};          // v0.7.7: reset clears pins + forced styles -> auto
  freeWps = {};
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
    var h = hitLayer.querySelector('.stdraw-hit[data-edge="' + i + '"]');
    if (h) h.setAttribute('d', edgeD(e.pts));
  });
  Object.keys(polGroups).forEach(function (i) {
    polGroups[i].g.setAttribute('transform', polGroups[i].t);
  });
  syncDomGeometry();   // v0.7.9: keep cards/anchors in sync after restore (no-op when in sync)
  rebuildHandles();
  refreshMetrics();
  fireLayoutChanged();
}
window.__stdrawExportLayout = exportLayout;
window.__stdrawExportJSON = function () { return JSON.stringify(buildLayout(), null, 1); };
// v0.7.7 public apply API: programmatically restore a layout
// ({nodes: {id: {x,y}}, edge_styles: {"a->b": "straight"|"arc"|"free"|"auto"},
//   waypoints: {"a->b": [[x,y],...]}}) — the inverse of "Export layout"
window.__stdrawApplyLayout = function (spec) {
  if (!spec || typeof spec !== 'object') return false;
  var ns = spec.nodes || {};
  Object.keys(ns).forEach(function (v) {
    if (!nodes[v]) return;
    var q = ns[v];
    nodes[v].x = +q.x;
    nodes[v].y = +q.y;
  });
  Object.keys(nodes).forEach(function (v) {
    var n = nodes[v];
    if (n.g) n.g.setAttribute('transform',
      'translate(' + (n.x - n.bx).toFixed(1) + ' ' + (n.y - n.by).toFixed(1) + ')');
  });
  function edgeIdxByKey(k) {
    var m = String(k).split('->');
    if (m.length !== 2) return null;
    for (var i = 0; i < edges.length; i++) {
      if (edges[i].a === m[0] && edges[i].b === m[1]) return i;
    }
    return null;
  }
  styles = {};
  freeWps = {};
  var ess = spec.edge_styles || {};
  Object.keys(ess).forEach(function (k) {
    var i = edgeIdxByKey(k);
    if (i !== null && ['auto', 'straight', 'arc', 'free'].indexOf(ess[k]) >= 0) {
      if (ess[k] === 'free') freeWps[i] = [];
      if (ess[k] !== 'auto') styles[i] = ess[k];
    }
  });
  var wss = spec.waypoints || {};
  Object.keys(wss).forEach(function (k) {
    var i = edgeIdxByKey(k);
    if (i === null || !Array.isArray(wss[k])) return;
    freeWps[i] = wss[k].map(function (p) { return [+p[0], +p[1]]; })
      .filter(function (p) { return isFinite(p[0]) && isFinite(p[1]); })
      .slice(0, MAX_FREE_PTS);
    if (!styles[i]) styles[i] = 'free';
  });
  edges.forEach(function (e, i) { reroute(i); updateEdge(i); });
  rebuildHandles();
  refreshMetrics();
  fireLayoutChanged();
  return true;
};
// v0.7.7 probe hooks: styled-edge list / per-edge style / free fold points
window.__stdrawStyles = function () {
  return Object.keys(styles).map(Number).sort(function (a, b) { return a - b; });
};
window.__stdrawEdgeStyle = function (i) {
  return (i === undefined || i === null) ? JSON.parse(JSON.stringify(styles))
    : (styles[i] || 'auto');
};
window.__stdrawFreePoints = function (i) {
  return (i === undefined || i === null)
    ? JSON.parse(JSON.stringify(freeWps))
    : (freeWps[i] ? freeWps[i].map(cp) : []);
};
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
// v0.7.9 probe/integration hooks: per-card rendered geometry + manual re-anchor
window.__stdrawNodeGeom = function (v) {
  return v ? {x: nodes[v].x, y: nodes[v].y, w: nodes[v].w, h: nodes[v].h}
           : Object.keys(nodes).map(function (k) {
               return [k, nodes[k].x, nodes[k].y, nodes[k].w, nodes[k].h];
             });
};
window.__stdrawSyncDomGeometry = syncDomGeometry;
var btnE = document.getElementById('stdraw-export');
var btnR = document.getElementById('stdraw-reset');
if (btnE) btnE.addEventListener('click', exportLayout);
if (btnR) btnR.addEventListener('click', reset);
rebuildHandles();
refreshMetrics();
// v0.7.9 initial font-environment sync: run now (the script sits after the
// SVG in the DOM, so layout is available) and again on window load (late
// font/measure settling). Both calls are strict no-ops when the rendered
// text fits the planned cards, so the deterministic initial render is
// untouched in matching environments.
syncDomGeometry();
window.addEventListener('load', function () { syncDomGeometry(); });
})();
"""
