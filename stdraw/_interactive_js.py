

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
#     caliber (endpoints = standard anchor nearest to the border point
#     facing the first/last waypoint; JS + Python one shared rule, so the
#     anchors_standard hard gate holds after a manual tweak);
#   - v0.7.7 per-edge style cycle: double-click a line to cycle
#     auto -> straight -> arc -> free -> auto (>=10px hover hit zone,
#     pointer cursor + highlight; double-click never disturbs node drags);
#     forced states re-route live and the top-bar metrics recompute
#     honestly (red when a hard gate fails — no leniency);
#   - v0.7.7 free fold points: in free mode click the line to insert a
#     handle (exact WYSIWYG polyline, no smoothing; endpoints re-anchored
#     on the box borders facing the first/last fold point); at most
#     MAX_FREE_PTS user fold points per edge — at the cap a click selects
#     the nearest handle with a "max N points per edge" tooltip;
#   - segment drag (drawio/bpmn-io .djs-segment-dragger caliber): on edges
#     with explicit user geometry (free mode with fold points / user-
#     anchored pinned polylines) dragging a segment translates the whole
#     segment; jog bendpoints are created automatically at the dragged
#     segment's pre-drag endpoints on first movement (anchor-adjacent
#     segments insert one, interior segments insert two — the anchors
#     themselves re-anchor on the box borders). Cursor reflects the segment
#     orientation (ns-resize on horizontal, ew-resize on vertical).
#     Auto-layout edges and straight lines are NOT affected: they keep live
#     re-routing (deterministic contract untouched);
#   - floating bendpoints (bpmn-io .djs-bendpoint.floating caliber): a
#     semi-transparent handle parks at the MIDDLE of the hovered segment
#     (mid-parking, not cursor-following — a cursor-following handle would
#     intercept every pointerdown and make segment drag unreachable).
#     Preview-only: hovering never writes user state. Dragging it >=4px
#     away adopts the edge's current geometry as user fold points (free
#     mode) and creates exactly one fold point; a plain click is a no-op;
#   - fold-point lifecycle: a fold point released within 6px (svg units)
#     of the polyline through its neighboring points merges back into the
#     line (removed; pinned edges whose interior empties fall back to
#     auto). Deletion semantics finalized = drag-back-to-line merge.
#     Legacy paths (double-click style cycle / free click-insert / handle
#     drag) unchanged. Drag preview: the live re-route + release-persist
#     model is kept — no ghost layer added (documented no-op);
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
#   - ref-scrubbed standard anchors + endpoint drag: hover a box shows its 16
#     standard anchors (stdraw/anchors.py caliber, toggleable); every edge's
#     start/arrow endpoint is individually draggable (topmost #stdraw-eps hit
#     circles beat the segment hit band), releasing snaps to the nearest
#     standard anchor of the endpoint's own box, and clicking a visible
#     anchor explicitly assigns it (nearest incident endpoint). Explicit
#     designations (userAnchored) travel with the export (edges[].anchors)
#     and __stdrawApplyLayout edge_anchors; afterwards node drags only
#     RE-PROJECT the endpoint onto the SAME anchor position (never drift).
#     The static layout / auto-routing path is untouched (no default-path
#     behavior change; the 21-input sweep stays byte-identical).
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
  // ref-scrubbed: hovering a box shows its 16 standard anchors (toggleable).
  // The anchor dots layer is pointer-events:none — the dots never steal the
  // cursor, so hovering stays on the node group and the dots cannot flicker.
  g.addEventListener('mouseenter', function () {
    hoverNode = g.getAttribute('data-node');
    renderAnchors();
  });
  g.addEventListener('mouseleave', function () {
    if (hoverNode === g.getAttribute('data-node')) { hoverNode = null; renderAnchors(); }
  });
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
          ctrl: arc ? cp(e.ctrl) : null,
          pa0: cp(pts[0]), pb0: cp(pts[pts.length - 1]),
          via: (e.via && e.via.length >= 3) ? e.via.map(cp) : null,
          corners: (e.via && e.via.length >= 3) ? e.via.map(cp) : null,
          pts: pts, base: pts.map(cp), d0: null};
});
edges.forEach(function (e, i) {
  var g = visG(i);
  if (g) {
    var p0 = g.querySelectorAll('path')[0];
    if (p0) {
      e.d0 = p0.getAttribute('d');
      bindEdgeHover(i, p0);   // visible stroke sits on top of the hit band
    }
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
function bindEdgeHover(i, el) {
  // Hover wiring shared by the hit path AND the visible line: in the real
  // render the visible stroke sits on top of the 12px hit band, so edge
  // hover events must be bound to both (the ±0.8px sliver on the visible
  // line targets the visible path; the rest of the band targets the hit
  // path). Derived state: highlight + floating bendpoint preview +
  // segment-orientation cursor.
  el.addEventListener('mouseenter', function () { hlEdge(i, true); });
  el.addEventListener('mouseleave', function () {
    hlEdge(i, false);
    // NOTE: the inline segment cursor is deliberately NOT cleared here.
    // Showing the floating handle under a stationary cursor makes the
    // browser fire mouseleave right after mousemove (hover recompute);
    // clearing there would wipe the just-set ns/ew-resize cursor. The
    // cursor self-corrects on the next mousemove over any edge segment.
    // Preview visibility is decided by the elementFromPoint interval
    // below, not by boundary events (measured timing-dependent headless).
  });
  el.addEventListener('mousemove', function (ev) {
    var p = svgPoint(ev);
    if (!p) return;
    lastFloatPos = [ev.clientX, ev.clientY];
    showFloat(i, p);
    if (segDraggable(i)) {
      var sd = segAt(edges[i].pts, p);
      if (sd) el.style.cursor = orientCursor(edges[i].pts, sd.k);
    }
  });
}
var SVGNS_EARLY = 'http://www.w3.org/2000/svg';
var hitLayer = document.createElementNS(SVGNS_EARLY, 'g');
hitLayer.id = 'stdraw-hits';
svg.insertBefore(hitLayer, svg.firstChild);
edges.forEach(function (e, i) {
  var h = document.createElementNS(SVGNS_EARLY, 'path');
  h.setAttribute('class', 'stdraw-hit');
  h.setAttribute('data-edge', i);
  h.setAttribute('d', edgeD(e.pts));
  bindEdgeHover(i, h);
  hitLayer.appendChild(h);
});
// ── v0.7.11 edge-element resolution: visible edges are `g[data-edge]`
// groups (render.py); hit paths are `path.stdraw-hit[data-edge]` inside
// #stdraw-hits, which sits at svg.firstChild — so a bare attribute-selector
// lookup on the data-edge attribute resolves to the HIT path first
// (document order). updateEdge then queried `path` CHILDREN of a path
// element (always empty) and the visible line never redrew: internal state
// re-anchored, DOM stale, zero exceptions (2026-11-08 8777/production regression,
// ref-scrubbed). Always resolve the visible group / hit path explicitly.
function visG(i) { return svg.querySelector('g[data-edge="' + i + '"]'); }
function hitP(i) { return hitLayer.querySelector('.stdraw-hit[data-edge="' + i + '"]'); }
// ── v0.7.11 per-edge failure isolation (fail-visible, never abort the round):
// one edge whose reroute/updateEdge throws (degenerate geometry after card
// growth: coincident anchors, infeasible route) must not kill the remaining
// edges of a re-anchor pass — they would stay on stale anchors (jacky's Edge
// mixed floating-arrow outage, ref-scrubbed). Degrade that edge visibly (red
// dashed stroke) + console WARN, keep going, and self-heal the marker on the
// edge's next successful pass.
function markDegraded(i, what, err) {
  try { console.warn('[stdraw] edge #' + i + ' ' + what + ' failed: ' +
        (err && err.message ? err.message : err)); } catch (e0) {}
  var g = visG(i);
  if (g) g.classList.add('stdraw-degraded');
  var h = hitP(i);
  if (h) h.classList.add('stdraw-degraded');
}
function clearDegraded(i) {
  var g = visG(i);
  if (g) g.classList.remove('stdraw-degraded');
  var h = hitP(i);
  if (h) h.classList.remove('stdraw-degraded');
}
function safeRerouteUpdate(i, what) {
  try { reroute(i); updateEdge(i); clearDegraded(i); return true; }
  catch (err) { markDegraded(i, what || 'reroute/update', err); return false; }
}
function hlEdge(i, on) {
  var g = visG(i);
  if (g) { if (on) g.classList.add('hl'); else g.classList.remove('hl'); }
  setEpVis(i, on);   // ref-scrubbed: endpoint handle dots show only on hover
}
// ref-scrubbed: per-edge endpoint handle visibility. Default hidden (visual
// noise in the rendered graph); visible while the edge is hovered or its
// endpoint is being dragged (drag hover is intercepted by the topmost hit
// circle, so the drag start must show them explicitly).
function setEpVis(i, on) {
  var rec = epEls[i];
  if (!rec) return;
  [0, 1].forEach(function (end) {
    (rec[end] || []).forEach(function (c) {
      if (c.getAttribute('class').indexOf('stdraw-eps-hit') === -1)
        c.classList.toggle('vis', !!on);
    });
  });
}
function updateEdge(i) {
  var e = edges[i], g = visG(i);
  var h = hitP(i);
  if (h) h.setAttribute('d', edgeD(e.pts));
  if (!g) return;
  var paths = g.querySelectorAll('path');
  if (paths[0]) paths[0].setAttribute('d', edgeD(e.pts));
  if (paths[1]) {
    var n = e.pts.length, a = e.pts[n - 2], b = e.pts[n - 1];
    var ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
    paths[1].setAttribute('transform', 'translate(' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) + ') rotate(' + ang.toFixed(1) + ')');
  }
  updateEndpointHandles(i);   // ref-scrubbed: endpoint handles track every redraw
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
// ── ref-scrubbed standard per-box anchor set (16 points) ──
// Mirror of stdraw/anchors.py (authoritative Python caliber; the probe
// cross-checks JS vs Python equality). All 16 points sit on the border
// rectangle inset by ANCHOR_INSET (the routing fan-slot -3 inner-offset
// caliber): 4 edge midpoints + 4 corner points (never the geometric tip /
// the rounded rx=7 frame corner) + 2 golden-section points per edge
// (0.382 / 0.618, clockwise g1/g2 direction — see anchors.py docstring).
var ANCHOR_INSET = 3.0, GOLDEN1 = 0.382, GOLDEN2 = 0.618;
var ANCHOR_IDS = ['n', 'e', 's', 'w',
                  'ne', 'se', 'sw', 'nw',
                  'n-g1', 'n-g2', 'e-g1', 'e-g2',
                  's-g1', 's-g2', 'w-g1', 'w-g2'];
function stdAnchors(n) {
  var a = n.w / 2 - ANCHOR_INSET, b = nHH(n) - ANCHOR_INSET;
  var cx = n.x, cy = n.y;
  function r6(v) { return Math.round(v * 1e6) / 1e6; }
  return [['n', cx, cy - b], ['e', cx + a, cy], ['s', cx, cy + b], ['w', cx - a, cy],
          ['ne', cx + a, cy - b], ['se', cx + a, cy + b],
          ['sw', cx - a, cy + b], ['nw', cx - a, cy - b],
          ['n-g1', cx - a + 2 * a * GOLDEN1, cy - b],
          ['n-g2', cx - a + 2 * a * GOLDEN2, cy - b],
          ['e-g1', cx + a, cy - b + 2 * b * GOLDEN1],
          ['e-g2', cx + a, cy - b + 2 * b * GOLDEN2],
          ['s-g1', cx + a - 2 * a * GOLDEN1, cy + b],
          ['s-g2', cx + a - 2 * a * GOLDEN2, cy + b],
          ['w-g1', cx - a, cy + b - 2 * b * GOLDEN1],
          ['w-g2', cx - a, cy + b - 2 * b * GOLDEN2]
         ].map(function (p) { return [p[0], r6(p[1]), r6(p[2])]; });
}
function nearestAnchorId(v, px, py) {
  var n = nodes[v];
  if (!n) return null;
  var pts = stdAnchors(n), best = null;
  for (var k = 0; k < pts.length; k++) {
    var d = Math.hypot(pts[k][1] - px, pts[k][2] - py);
    if (best === null || d < best[0] - 1e-9) best = [d, pts[k][0]];
  }
  return best ? best[1] : null;
}
function nearestAnchorPt(n, px, py) {
  // Nearest standard anchor COORDINATES of node n to (px,py); tie-break
  // mirrors Python anchors.nearest_anchor (lower ANCHOR_IDS index wins).
  var pts = stdAnchors(n), best = null;
  for (var k = 0; k < pts.length; k++) {
    var d = Math.hypot(pts[k][1] - px, pts[k][2] - py);
    if (best === null || d < best[0] - 1e-9) best = [d, pts[k][1], pts[k][2]];
  }
  return best ? [best[1], best[2]] : null;
}
function anchorOccupied(v, ax, ay, excludeEdge) {
  // Does another edge's endpoint already sit on anchor (ax,ay) of box v?
  // (0.75px = the same membership tolerance as the certificate gate.)
  for (var i = 0; i < edges.length; i++) {
    if (i === excludeEdge) continue;
    var e2 = edges[i], m2 = e2.pts.length;
    if (e2.a === v && Math.abs(e2.pts[0][0] - ax) <= 0.75 &&
        Math.abs(e2.pts[0][1] - ay) <= 0.75) return true;
    if (e2.b === v && Math.abs(e2.pts[m2 - 1][0] - ax) <= 0.75 &&
        Math.abs(e2.pts[m2 - 1][1] - ay) <= 0.75) return true;
  }
  return false;
}
function stdAnchorToward(n, toward, edgeIdx) {
  // Waypoint/free endpoint caliber (T2 plan A): border point aimed at the
  // first/last fold direction, snapped to the nearest standard anchor of
  // the SAME box that is not already held by another edge's endpoint
  // (nearest-feasible; falls back to the plain nearest when all 16 are
  // occupied). Python counterpart: layout_auto waypoints override +
  // anchor_snap give-way (same 16-set ladder). Uncontested drags deliver
  // the literal nearest anchor on BOTH sides -- identical endpoints; a
  // contested anchor may resolve to different (still on-set) slots and is
  // reported honestly by the certificate either way.
  var bp = anchor(n, toward);
  var pts = stdAnchors(n).map(function (p) {
    return [Math.hypot(p[1] - bp[0], p[2] - bp[1]), p[1], p[2]];
  }).sort(function (u, w) { return u[0] - w[0]; });
  var vid = null;
  Object.keys(nodes).forEach(function (k) { if (nodes[k] === n) vid = k; });
  for (var k = 0; k < pts.length; k++) {
    if (!anchorOccupied(vid, pts[k][1], pts[k][2], edgeIdx)) {
      return [pts[k][1], pts[k][2]];
    }
  }
  return [pts[0][1], pts[0][2]];
}
// userAnchored: edgeIdx -> {0: aid | 1: aid} — explicitly designated
// standard anchors (endpoint drag release / anchor click / applyLayout).
// user-anchored semantics: after designation, node drags only RE-PROJECT
// the endpoint onto the SAME anchor position (live geometry), never drift.
var userAnchored = {};
function userAnchorPt(i, end) {
  var ua = userAnchored[i];
  if (!ua || !ua[end]) return null;
  var e = edges[i];
  var n = nodes[end === 0 ? e.a : e.b];
  if (!n) return null;
  var pts = stdAnchors(n);
  for (var k = 0; k < pts.length; k++) {
    if (pts[k][0] === ua[end]) return [pts[k][1], pts[k][2]];
  }
  delete ua[end];              // stale designation: fall back gracefully
  return null;
}
function endPt(i, end, fallback) {
  var p = userAnchorPt(i, end);
  if (p) return p;
  // Caliber: the undesignated sibling end of a user-anchored edge snaps to
  // the standard anchor nearest to the border point aimed at the opposite
  // box (same 16-set nearest-anchor family as the waypoint/free endpoints
  // and the CLI --from-layout unspecified-end snap -- the preview endpoint
  // then matches the CLI rerender instead of a raw border point).
  var ua2 = userAnchored[i];
  if (ua2 && ua2[end === 0 ? 1 : 0]) {
    var e2 = edges[i];
    var nOwn = nodes[end === 0 ? e2.a : e2.b];
    var nOpp = nodes[end === 0 ? e2.b : e2.a];
    // aim at the designated sibling end when present (the CLI snap aims at
    // the same point -- identical nearest-anchor resolution)
    var aim = userAnchorPt(i, end === 0 ? 1 : 0) ||
              (nOpp ? [nOpp.x, nOpp.y] : null);
    if (nOwn && aim) return stdAnchorToward(nOwn, aim, i);
  }
  return fallback;
}
function reanchor(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pts = e.pts.map(cp);
  var inner = pts.length > 2;
  pts[0] = endPt(i, 0, anchor(A, inner ? pts[1] : [B.x, B.y]));
  pts[pts.length - 1] = endPt(i, 1, anchor(B, inner ? pts[pts.length - 2] : [A.x, A.y]));
  e.pts = pts;
  e.ctrl = null;   // re-anchor keeps waypoints / shape, never an arc ctrl
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
  var pa = endPt(i, 0, anchor(A, [B.x, B.y]));
  var pb = endPt(i, 1, anchor(B, [A.x, A.y]));
  var rects = rectsFor(e.a, e.b);
  if (visible(pa, pb, rects, CL)) { e.pts = [pa, pb]; e.ctrl = null; e.corners = null; return; }
  var path = vgShortest(pa, pb, rects, VG_C);
  if (path && path.length >= 2) {
    e.pts = shortcut(path, rects, VG_C);
    e.ctrl = null;   // non-arc kind: no live ctrl
    e.corners = (e.pts.length >= 3) ? e.pts.map(cp) : null;
    return;
  }
  reanchor(i);   // fallback (unreachable): shape-preserving re-anchor
}
function arcFollow(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  // v0.7.11 defensive: an arc edge missing its frozen control state (partial
  // restore paths) must degrade to a straight line, not throw mid-round.
  if (!e.ctrl0 || !e.pa0 || !e.pb0) { forcedStraight(i); return; }
  var pa = endPt(i, 0, anchor(A, [B.x, B.y]));
  var pb = endPt(i, 1, anchor(B, [A.x, A.y]));
  var ctrl = [e.ctrl0[0] + ((pa[0] - e.pa0[0]) + (pb[0] - e.pb0[0])) / 2,
              e.ctrl0[1] + ((pa[1] - e.pa0[1]) + (pb[1] - e.pb0[1])) / 2];
  e.pts = quad(pa, ctrl, pb, 12);
  e.ctrl = ctrl;   // live ctrl: exported for the CLI arc replay (final form)
  e.corners = null;
}
// ── v0.7.7 forced geometries (per-edge style cycle; same math caliber as
// the Python replay in layout_auto._manual_edge_styles/_forced_arc_route) ──
function forcedStraight(i) {
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var pa = endPt(i, 0, anchor(A, [B.x, B.y]));
  var pb = endPt(i, 1, anchor(B, [A.x, A.y]));
  e.pts = [pa, pb];
  e.ctrl = null;   // non-arc kind: no live ctrl
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
  var pa = endPt(i, 0, anchor(A, [B.x, B.y]));
  var pb = endPt(i, 1, anchor(B, [A.x, A.y]));
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
  e.ctrl = best[2];   // live ctrl: exported for the CLI arc replay (final form)
  e.corners = null;
}
function reanchorFree(i) {
  // free mode: exact polyline over the user fold points; endpoints =
  // standard anchor nearest to the border point facing the first/last fold
  // point (same caliber as waypoints + CLI --from-layout, T2 plan A)
  var e = edges[i], A = nodes[e.a], B = nodes[e.b];
  var wps = freeWps[i];
  if (!wps || !wps.length) { forcedStraight(i); return; }
  var pts = [endPt(i, 0, stdAnchorToward(A, wps[0], i))];
  pts = pts.concat(wps.map(cp));
  pts.push(endPt(i, 1, stdAnchorToward(B, wps[wps.length - 1], i)));
  e.pts = pts;
  e.ctrl = null;   // non-arc kind: no live ctrl
  e.corners = null;
}
function reroute(i) {
  // v0.7.11 fault-injection hook (probe-only, never set by UI code): lets the
  // DOM-truth regression probe force a single-edge router failure to prove the
  // per-edge isolation + fail-visible degradation (ref-scrubbed acceptance).
  if (edges[i] && edges[i]._probeThrow) {
    throw new Error('probe-injected router failure (edge #' + i + ')');
  }
  var st = styles[i] || 'auto';
  if (st === 'free') { reanchorFree(i); return; }   // user fold points: re-anchor endpoints only
  if (pinned[i]) { reanchor(i); return; }           // user-anchored: re-anchor endpoints only, keep waypoints
  if (st === 'straight') { forcedStraight(i); return; }
  if (st === 'arc') { forcedArc(i); return; }
  if (edges[i].arc) { arcFollow(i); return; }
  previewRoute(i);
  // v0.7.11 defensive final guard (degenerate geometry after card growth:
  // extreme wide/flat cards, coincident anchors, infeasible route): any
  // non-finite coordinate that slipped through a router path degrades this
  // edge to a straight border-to-border line instead of poisoning e.pts
  // (downstream edgeD/updateEdge/metrics would throw and abort the round).
  var pts = edges[i].pts;
  for (var k = 0; k < pts.length; k++) {
    if (!isFinite(pts[k][0]) || !isFinite(pts[k][1])) { forcedStraight(i); return; }
  }
}

// ── Bend handles (vg polylines / user-anchored edges) ──
var pinned = {};          // edgeIdx -> true (user dragged a handle = waypoints anchored)
// v0.7.7 per-edge style cycle: edgeIdx -> 'auto' | 'straight' | 'arc' | 'free'
// (auto = engine default routing; free = exact polyline on user fold points)
var styles = {};
var freeWps = {};         // edgeIdx -> [[x,y], ...] user fold points (free mode, max MAX_FREE_PTS)
// Segment-drag re-review (2026-11-08): an interior segment drag inserts TWO
// jog bendpoints per gesture and a realistic orthogonal detour (e.g. jogging
// around two cards on 8777 P5) needs 4-6 points; drawio/bpmn-io set no hard
// cap at all. 8 = headroom for two segment-drags on one edge while keeping
// metrics/metrics sampling and export/applyLayout truncation sane.
var MAX_FREE_PTS = 8;     // per-edge user fold-point cap (creation-time only)
var NS = 'http://www.w3.org/2000/svg';
var styleEl = document.createElement('style');
styleEl.textContent = '#stdraw-handles circle.stdraw-wp{fill:#fff;stroke:#475569;' +
  'stroke-width:1.4;cursor:move;pointer-events:all}' +
  '#stdraw-handles circle.stdraw-wp:hover{stroke:#dc2626;fill:#fef2f2}' +
  '#stdraw-handles circle.stdraw-wp.sel{stroke:#dc2626;fill:#fef2f2}' +
  // Floating bendpoints (bpmn-io .djs-bendpoint.floating): preview-only
  // handle; creating it never touches user state, so it is safe to render
  // on hover and discard on leave.
  // NOTE (ref-scrubbed): the floating preview mounts in the #stdraw-float
  // layer (floatLayer below), NOT #stdraw-handles -- rebuildHandles clears
  // #stdraw-handles on every gesture and would kill the preview. Prefixing
  // these rules with a layer id silently detached them (handle rendered as
  // a black opaque dot on 8777). Keep the selector layer-agnostic: the
  // probe pins computed opacity so a re-layering regression turns red.
  'circle.stdraw-wp.floating{fill:#94a3b8;stroke:#475569;' +
  'stroke-width:1.4;cursor:move;pointer-events:all;opacity:0.45}' +
  'circle.stdraw-wp.floating:hover{opacity:0.85}' +
  // Edge hit paths: the stroke MUST be painted (alpha > 0) for Chromium's
  // pointer-events:stroke to hit-test it -- stroke:transparent is treated as
  // unpainted and the hit path never resolves under the cursor (2026-11-08
  // 8777 regression: all edge interactions dead while node drags worked).
  // Same caliber as diagram-js InteractionEvents createHitStyle (painted
  // near-transparent hit stroke, production-proven). Do NOT switch to
  // pointer-events:all: with fill:none the implicit-closed fill polygon of
  // an open polyline would hit-test its interior and steal empty-canvas
  // clicks. rgba(...,0.01) is visually imperceptible (+<=2.5/255 composite).
  '#stdraw-svg path.stdraw-hit{fill:none;stroke:rgba(255,255,255,0.01);stroke-width:12;cursor:pointer;pointer-events:stroke}' +
  '#stdraw-svg [data-edge].hl > path:not(.stdraw-hit){stroke-width:2.4}' +
  // v0.7.11 per-edge degradation marker (fail-visible): a single edge whose
  // re-route threw keeps its last geometry but is drawn red + dashed so the
  // failure is visible instead of silently floating.
  '#stdraw-svg g[data-edge].stdraw-degraded > path:not(.stdraw-hit){stroke:#dc2626;stroke-dasharray:6 4}' +
  '#stdraw-svg path.stdraw-hit.stdraw-degraded{stroke:rgba(220,38,38,0.01)}' +
  // ref-scrubbed: standard-anchor dots (hover preview). pointer-events:none —
  // the dots never intercept the cursor (click-to-assign is resolved by the
  // svg pointerdown handler against the LIVE anchor coordinates instead, so
  // hovering a dot keeps the node hover alive and the dots cannot flicker).
  '#stdraw-anchors{pointer-events:none}' +
  // Chrome polar inks read the THEMES tokens through CSS custom properties
  // (--stdraw-chrome-b = T["edge_neg"], --stdraw-chrome-r = T["edge_pos"],
  // declared on #stdraw-svg by render.py per tier) — the legacy hardcoded
  // palette (#0284c7/#fbbf24/#d97706/#075985) leaked the pre-UI-A polar inks
  // onto the live canvas. No hardcoded polar colors here anymore.
  '#stdraw-anchors circle.stdraw-anchor{fill:#fff;stroke:var(--stdraw-chrome-b);stroke-width:1.1;opacity:0.9}' +
  '#stdraw-anchors circle.stdraw-anchor.pinned{fill:var(--stdraw-chrome-b);stroke:var(--stdraw-chrome-b)}' +
  '#stdraw-anchors circle.stdraw-anchor.near{fill:var(--stdraw-chrome-r);stroke:var(--stdraw-chrome-r)}' +
  // ref-scrubbed: per-edge ENDPOINT drag handles. The 9px invisible hit circle
  // sits in the TOPMOST layer (#stdraw-eps appended last), so an endpoint
  // press always resolves to the endpoint drag BEFORE the 12px segment hit
  // band (drag-line = whole-segment translation) can claim it — endpoint
  // hit priority is structural (DOM order), pinned by the probe.
  // ref-scrubbed: the VISIBLE handle dot is hidden by default (jacky: dots in
  // the rendered graph are visual noise); it fades in only while its edge is
  // hovered or its endpoint is being dragged (.vis class, see setEpVis).
  '#stdraw-eps circle.stdraw-ep{fill:#fff;stroke:var(--stdraw-chrome-b);stroke-width:1.6;cursor:move;pointer-events:all;opacity:0;transition:opacity .12s}' +
  '#stdraw-eps circle.stdraw-ep.vis{opacity:1}' +
  '#stdraw-eps circle.stdraw-eps-hit{fill:rgba(255,255,255,0);stroke:none;cursor:move;pointer-events:all}' +
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
  // Same caliber as CLI --from-layout (T2 plan A): endpoint = standard
  // anchor nearest to the border point facing the first/last waypoint
  var pts = [endPt(i, 0, stdAnchorToward(A, via[0], i))];
  pts = pts.concat(via);
  pts.push(endPt(i, 1, stdAnchorToward(B, via[via.length - 1], i)));
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
    // v0.7.11 per-node isolation: a measurement failure on one card must not
    // abort the growth pass for the remaining cards.
    try {
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
    } catch (errN) {
      try { console.warn('[stdraw] node #' + g.getAttribute('data-node') +
            ' geometry sync failed: ' + (errN && errN.message ? errN.message : errN)); } catch (e4) {}
    }
  });
  if (touched) {
    // v0.7.11 per-edge isolation: a single edge throwing must never abort the
    // re-anchor round (stale anchors on all subsequent edges = the mixed
    // floating-arrow state jacky saw in Edge). Fail-visible per edge instead.
    edges.forEach(function (e, i) { safeRerouteUpdate(i, 'sync re-anchor'); });
    try { rebuildHandles(); } catch (errH) {
      try { console.warn('[stdraw] rebuildHandles failed: ' +
            (errH && errH.message ? errH.message : errH)); } catch (e5) {}
    }
    try { refreshMetrics(); } catch (errM) {
      try { console.warn('[stdraw] refreshMetrics failed: ' +
            (errM && errM.message ? errM.message : errM)); } catch (e6) {}
    }
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
  safeRerouteUpdate(i, 'style change');
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
function insertWaypointAt(i, p) {
  // Shared fold-point creation (free click-insert + floating-bendpoint
  // conversion): projected onto the nearest segment, rounded to 0.5.
  // Returns the inserted freeWps index, or null at the MAX_FREE_PTS cap.
  var wps = freeWps[i] = freeWps[i] || [];
  if (wps.length >= MAX_FREE_PTS) return null;
  var pts = edges[i].pts;
  var best = null;
  for (var s = 0; s < pts.length - 1; s++) {
    var q = projectOnSeg(p, pts[s], pts[s + 1]);
    var d = Math.hypot(q[0] - p[0], q[1] - p[1]);
    if (best === null || d < best[0]) best = [d, s, q];
  }
  var wi = Math.min(best[1], wps.length);
  wps.splice(wi, 0, [Math.round(best[2][0] * 2) / 2, Math.round(best[2][1] * 2) / 2]);
  return wi;
}
function insertFreePoint(i, p, ev) {
  var wi = insertWaypointAt(i, p);
  if (wi === null) {
    selectNearestFreeHandle(i, p);
    showTip('max ' + MAX_FREE_PTS + ' points per edge', ev);
    return;
  }
  reanchorFree(i);
  updateEdge(i);
  rebuildHandles();
  refreshMetrics();
  fireLayoutChanged();
}
// ── segment drag + floating bendpoints (drawio/bpmn-io caliber) ──
var MERGE_TOL = 6;        // svg-unit merge tolerance (fold point dropped back onto the line)
function segDraggable(i) {
  // Segment drag applies only to edges with explicit user geometry: free
  // mode with fold points, or user-anchored pinned polylines. Straight
  // lines and auto-layout edges keep live re-routing; arcs have no
  // polyline segments.
  if (edges[i].arc) return false;
  if ((styles[i] || 'auto') === 'free') return !!(freeWps[i] && freeWps[i].length);
  return !!pinned[i];
}
function segAt(pts, p) {
  // svgPoint() returns an SVGPoint object (.x/.y), array callers pass
  // [x, y] — normalize to [x, y] here so every caller is safe
  if (p && typeof p.x === 'number') p = [p.x, p.y];
  var best = null;
  for (var s = 0; s < pts.length - 1; s++) {
    var q = projectOnSeg(p, pts[s], pts[s + 1]);
    var d = Math.hypot(q[0] - p[0], q[1] - p[1]);
    if (best === null || d < best[0]) best = [d, s, q];
  }
  return best === null ? null : {k: best[1], proj: best[2], dist: best[0]};
}
function orientCursor(pts, k) {
  // diagram-js segment-dragger convention: horizontal segments move
  // vertically (ns-resize), vertical segments move horizontally
  // (ew-resize).
  var a = pts[k], b = pts[k + 1];
  return Math.abs(b[1] - a[1]) <= Math.abs(b[0] - a[0]) ? 'ns-resize' : 'ew-resize';
}
function segDragPlan(i, k) {
  // drawio segment-move semantics: the dragged segment translates; jog
  // bendpoints are created at its pre-drag endpoints. Segments adjacent to
  // an edge anchor insert ONE bendpoint (the anchor side re-anchors on the
  // box border instead — same caliber as CLI --from-layout), interior
  // segments insert TWO. head/tail = user waypoints that stay put;
  // mv = the moving points (copies of the dragged segment's waypoint
  // endpoints); added = bendpoints created (mv.length).
  var e = edges[i], pts = e.pts;
  var isFree = (styles[i] || 'auto') === 'free';
  var W = isFree ? (freeWps[i] || []) : pts.slice(1, -1);
  var head, tail, mv;
  if (k === 0) { head = []; tail = W.map(cp); mv = [cp(pts[1])]; }
  else if (k === pts.length - 2) { head = W.map(cp); tail = []; mv = [cp(pts[k])]; }
  else {
    head = W.slice(0, k).map(cp); tail = W.slice(k).map(cp);
    mv = [cp(pts[k]), cp(pts[k + 1])];
  }
  return {head: head, tail: tail, mv: mv, added: mv.length};
}
function applyUserWps(i, wps) {
  // Write the effective user waypoints back: free mode via freeWps +
  // reanchorFree; pinned via the same anchor-first/last caliber.
  var e = edges[i];
  if ((styles[i] || 'auto') === 'free') { freeWps[i] = wps; reanchorFree(i); return; }
  if (!wps.length) {
    var A = nodes[e.a], B = nodes[e.b];
    e.pts = [endPt(i, 0, anchor(A, [B.x, B.y])), endPt(i, 1, anchor(B, [A.x, A.y]))];
    return;
  }
  e.pts = [endPt(i, 0, stdAnchorToward(nodes[e.a], wps[0], i))].concat(wps.map(cp))
           .concat([endPt(i, 1, stdAnchorToward(nodes[e.b], wps[wps.length - 1], i))]);
}
function effectiveWps(i) {
  if ((styles[i] || 'auto') === 'free') return (freeWps[i] || []).map(cp);
  return pinned[i] ? edges[i].pts.slice(1, -1).map(cp) : [];
}
function adoptFreeAndInsert(i, pos) {
  // Floating-bendpoint drag-away: adopt the edge's current geometry as
  // user fold points (free mode) and insert exactly one fold point at the
  // grab position. Returns the inserted freeWps index, or false at the cap
  // (in which case NOTHING is written — preview stays dirty-free).
  var e = edges[i], st = styles[i] || 'auto';
  var cur = (st === 'free') ? (freeWps[i] || [])
          : (pinned[i] ? e.pts.slice(1, -1)
          : (e.corners && e.corners.length >= 3 ? e.corners.slice(1, -1) : []));
  if (cur.length + 1 > MAX_FREE_PTS) return false;
  if (st !== 'free') {
    styles[i] = 'free';
    delete pinned[i];
    freeWps[i] = cur.map(function (q) {
      return [Math.round(q[0] * 2) / 2, Math.round(q[1] * 2) / 2];
    });
  }
  var wi = insertWaypointAt(i, pos);
  if (wi === null) return false;
  reanchorFree(i);
  return wi;
}
function removeWaypoint(i, idx) {
  // Merge-back deletion: drop the fold point, then rebuild. Pinned edges
  // whose interior empties fall back to auto (no empty-pin residue).
  var e = edges[i];
  if ((styles[i] || 'auto') === 'free') {
    if (freeWps[i]) freeWps[i].splice(idx - 1, 1);
    reanchorFree(i);
  } else {
    e.pts.splice(idx, 1);
    if (e.pts.length <= 2) { delete pinned[i]; reroute(i); }
  }
  updateEdge(i);
  rebuildHandles();
  refreshMetrics();
}
// Floating bendpoint handle: a single preview element in its own layer
// (rebuildHandles clears #stdraw-handles; the floating preview must
// survive every rebuild). Hover-only — never written into user state.
var floatLayer = document.createElementNS(NS, 'g');
floatLayer.id = 'stdraw-float';
svg.appendChild(floatLayer);
var floatC = null;
// Last cursor client position seen over an edge (drives the deterministic
// floating-preview visibility check below)
var lastFloatPos = null, lastCursor = null;
function edgeFloatable(i) { return !edges[i].arc; }
function floatHandle() {
  if (floatC) return floatC;
  floatC = document.createElementNS(NS, 'circle');
  floatC.setAttribute('r', '4');
  floatC.setAttribute('class', 'stdraw-wp floating');
  floatC.setAttribute('data-float', '1');
  floatC.style.display = 'none';
  floatLayer.appendChild(floatC);
  return floatC;
}
// Deterministic floating-preview lifecycle: boundary events (mouseenter/
// mouseleave between the line and the handle) fire in a timing-dependent
// order when the handle appears directly under a stationary cursor, so
// visibility is decided by polling elementFromPoint at the last cursor
// position — over the edge or the handle keeps the preview, anywhere else
// hides it. Pure DOM geometry, no timers-on-events races.
window.addEventListener('mousemove', function (ev) { lastCursor = [ev.clientX, ev.clientY]; });
setInterval(function () {
  if (!floatC || floatC.style.display === 'none' || !lastCursor) return;
  // Probe the CURRENT cursor position (window-tracked; the parked handle
  // position would self-lock). Exclude the handle itself from the probe
  // via pointer-events:none — no visual flicker.
  var pe = floatC.style.pointerEvents;
  floatC.style.pointerEvents = 'none';
  var el = document.elementFromPoint(lastCursor[0], lastCursor[1]);
  floatC.style.pointerEvents = pe;
  if (el && el.closest && el.closest('[data-edge]')) return;
  hideFloat();
}, 120);
function showFloat(i, p) {
  if (drag || !edgeFloatable(i)) { hideFloat(); return; }
  var sd = segAt(edges[i].pts, p);
  if (!sd) { hideFloat(); return; }
  // bpmn-io .djs-bendpoint.floating parks the handle at the MIDDLE of the
  // hovered segment, NOT under the cursor: a cursor-following handle would
  // intercept every pointerdown on the line and make segment drag
  // unreachable. Mid-segment parking splits the intents cleanly — press at
  // mid = create fold point (drag away), press elsewhere = segment drag.
  var a = edges[i].pts[sd.k], b2 = edges[i].pts[sd.k + 1];
  var c = floatHandle();
  c.setAttribute('cx', ((a[0] + b2[0]) / 2).toFixed(1));
  c.setAttribute('cy', ((a[1] + b2[1]) / 2).toFixed(1));
  c.setAttribute('data-edge', i);
  c.style.display = '';
}
function hideFloat() {
  if (floatC) floatC.style.display = 'none';
}
// ══ ref-scrubbed: standard-anchor overlay + per-edge endpoint drag ══
// Anchor dots: hover a box -> its 16 standard anchors appear (toggleable via
// #stdraw-anchors-toggle; dots layer is pointer-events:none, click-to-assign
// is resolved against the LIVE anchor coordinates in onDown). Endpoint drag:
// every edge renders two endpoint handles in the topmost #stdraw-eps layer;
// release snaps to the nearest standard anchor of the endpoint's own box and
// records the explicit designation in userAnchored (re-projection caliber:
// node drags afterwards only re-project the endpoint onto the SAME anchor).
var anchorLayer = document.createElementNS(NS, 'g');
anchorLayer.id = 'stdraw-anchors';
svg.appendChild(anchorLayer);
var anchorToggle = false, hoverNode = null;   // ref-scrubbed: anchor dots OFF by default (jacky: dots are visual noise; hover + toolbar toggle still show them)
var ANCHOR_CLICK_TOL = 10;   // px: a press within this distance of a visible
                             // standard anchor is an explicit assignment
function setAnchorToggle(on) {
  anchorToggle = !!on;
  var b = document.getElementById('stdraw-anchors-toggle');
  if (b) b.textContent = 'Anchors: ' + (anchorToggle ? 'on' : 'off');
  renderAnchors();
}
function renderAnchors() {
  while (anchorLayer.firstChild) anchorLayer.removeChild(anchorLayer.firstChild);
  if (!anchorToggle || !hoverNode || !nodes[hoverNode]) return;
  var pinnedAids = {};
  edges.forEach(function (e, i) {
    var ua = userAnchored[i];
    if (!ua) return;
    if (ua[0] && e.a === hoverNode) pinnedAids[ua[0]] = true;
    if (ua[1] && e.b === hoverNode) pinnedAids[ua[1]] = true;
  });
  stdAnchors(nodes[hoverNode]).forEach(function (p) {
    var c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx', p[1].toFixed(1));
    c.setAttribute('cy', p[2].toFixed(1));
    c.setAttribute('r', pinnedAids[p[0]] ? '4.5' : '3');
    c.setAttribute('class', 'stdraw-anchor' + (pinnedAids[p[0]] ? ' pinned' : ''));
    c.setAttribute('data-node', hoverNode);
    c.setAttribute('data-aid', p[0]);
    anchorLayer.appendChild(c);
  });
}
function markNearAnchor(v, x, y) {
  // live snap feedback while dragging an endpoint (works with the dots
  // hidden too: the ring is drawn unconditionally)
  renderAnchors();
  var aid = nearestAnchorId(v, x, y);
  if (!aid || !nodes[v]) return;
  stdAnchors(nodes[v]).forEach(function (p) {
    if (p[0] !== aid) return;
    var c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx', p[1].toFixed(1));
    c.setAttribute('cy', p[2].toFixed(1));
    c.setAttribute('r', '6');
    c.setAttribute('class', 'stdraw-anchor near');
    c.setAttribute('data-node', v);
    c.setAttribute('data-aid', p[0]);
    anchorLayer.appendChild(c);
  });
}
var epsLayer = document.createElementNS(NS, 'g');
epsLayer.id = 'stdraw-eps';
svg.appendChild(epsLayer);   // appended LAST: endpoint hit priority over the
                             // 12px segment hit band is structural (DOM order)
var epEls = {};              // edgeIdx -> {0: [hit, vis], 1: [hit, vis]}
function ensureEpEls(i) {
  if (epEls[i]) return;
  var rec = {};
  [0, 1].forEach(function (end) {
    [true, false].forEach(function (isHit) {
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('r', isHit ? '9' : '3.5');
      c.setAttribute('class', isHit ? 'stdraw-eps-hit' : 'stdraw-ep');
      c.setAttribute('data-edge', i);
      c.setAttribute('data-end', end);
      epsLayer.appendChild(c);
      rec[end] = rec[end] || [];
      rec[end].push(c);
    });
  });
  epEls[i] = rec;
}
function updateEndpointHandles(i) {
  if (!edges[i]) return;
  ensureEpEls(i);
  var e = edges[i];
  if (e.pts.length < 2) return;
  [[0, e.pts[0]], [1, e.pts[e.pts.length - 1]]].forEach(function (pe) {
    epEls[i][pe[0]].forEach(function (c) {
      c.setAttribute('cx', pe[1][0].toFixed(1));
      c.setAttribute('cy', pe[1][1].toFixed(1));
    });
  });
}
function rebuildAllEndpointHandles() {
  edges.forEach(function (e, i) { updateEndpointHandles(i); });
}
edges.forEach(function (e, i) { ensureEpEls(i); });
function arcEpPts(e, end, pt) {
  // endpoint moved on an arc: re-derive the sampled Bezier from the frozen
  // control state, translating ctrl in lockstep with the endpoint delta
  // (tangent-preserving; same caliber as arcFollow's mean translation)
  if (!(e.arc && e.ctrl0 && e.pa0 && e.pb0)) return null;
  var from = end === 0 ? e.pa0 : e.pb0;
  var other = end === 0 ? e.pb0 : e.pa0;
  var ctrl = [e.ctrl0[0] + (pt[0] - from[0]), e.ctrl0[1] + (pt[1] - from[1])];
  var pa = end === 0 ? pt : other;
  var pb = end === 0 ? other : pt;
  return quad(pa, ctrl, pb, 12);
}
function clampVB(x, y) {
  return [Math.max(4, Math.min(VB[2] - 4, x)), Math.max(4, Math.min(VB[3] - 4, y))];
}
function finishUaDesignation(i, end, coordEnd) {
  // CLI-parity finalization of an endpoint designation: (1) keep the live
  // arc ctrl in sync -- it exports in final form (edges[].ctrl) and the CLI
  // replays it verbatim; (2) snap the undesignated sibling end to the
  // standard anchor nearest the border point aimed at the designated end
  // (the same caliber as the CLI --from-layout unspecified-end snap); (3)
  // rebuild the arc geometry from the resolved endpoints. Later node drags
  // re-run reroute(), whose endPt() resolves the same endpoints.
  var e = edges[i];
  var sib = end === 0 ? 1 : 0;
  if (e.arc && e.ctrl0 && e.pa0 && e.pb0) {
    var fromU = end === 0 ? e.pa0 : e.pb0;
    e.ctrl = [e.ctrl0[0] + (coordEnd[0] - fromU[0]),
              e.ctrl0[1] + (coordEnd[1] - fromU[1])];
  }
  if (userAnchored[i] && userAnchored[i][sib]) return;
  var vSib = sib === 0 ? e.a : e.b;
  var nSib = nodes[vSib];
  if (!nSib || !coordEnd) return;
  var sibCoord = stdAnchorToward(nSib, coordEnd, i);
  if (e.arc && e.ctrl) {
    var pa = (end === 0) ? coordEnd : sibCoord;
    var pb = (end === 0) ? sibCoord : coordEnd;
    e.pts = quad(pa, e.ctrl, pb, 12);
    e.corners = null;
  } else {
    e.pts[sib === 0 ? 0 : e.pts.length - 1] = sibCoord;
  }
}
function assignAnchor(v, aid, ax, ay) {
  // Explicit designation (anchor click): the clicked standard anchor goes to
  // the incident edge endpoint nearest to it (deterministic single winner;
  // only endpoints of box v are candidates).
  var best = null;
  edges.forEach(function (e, i) {
    if (e.a !== v && e.b !== v) return;
    var end = e.a === v ? 0 : 1;
    var p = e.pts[end === 0 ? 0 : e.pts.length - 1];
    var d = Math.hypot(p[0] - ax, p[1] - ay);
    if (best === null || d < best[0] - 1e-9) best = [d, i, end];
  });
  if (!best) { showTip('no edge attached to this box'); return; }
  var i2 = best[1], end2 = best[2];
  userAnchored[i2] = userAnchored[i2] || {};
  userAnchored[i2][end2] = aid;
  edges[i2].pts[end2 === 0 ? 0 : edges[i2].pts.length - 1] = [ax, ay];
  finishUaDesignation(i2, end2, [ax, ay]);
  updateEdge(i2);
  updateEndpointHandles(i2);
  renderAnchors();
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
  // ── ref-scrubbed endpoint drag: the topmost #stdraw-eps hit circles claim
  // the press BEFORE the edge hit band (drag-line = segment translation) and
  // before the floating preview. Hit priority is structural + asserted by
  // the probe (drag state keys contain 'ep').
  var he = t && t.closest ? t.closest('.stdraw-eps-hit, .stdraw-ep') : null;
  if (he) {
    var eiE = +he.getAttribute('data-edge'), endE = +he.getAttribute('data-end');
    if (edges[eiE]) {
      var peE = svgPoint(ev);
      if (peE) {
        drag = {ep: true, edge: eiE, end: endE, start: [peE.x, peE.y], ev: ev};
        setEpVis(eiE, true);   // ref-scrubbed: show the dragged endpoint's handles
        try { he.setPointerCapture(ev.pointerId); } catch (eE0) {}
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
    }
  }
  // ── ref-scrubbed anchor click-to-assign: while a box's anchors are shown, a
  // press within ANCHOR_CLICK_TOL of one of its standard anchors explicitly
  // assigns that anchor (nearest incident endpoint wins, deterministic).
  if (hoverNode && anchorToggle && nodes[hoverNode]) {
    var pa2 = svgPoint(ev);
    if (pa2) {
      var apts = stdAnchors(nodes[hoverNode]), hitA = null;
      for (var ka = 0; ka < apts.length; ka++) {
        var da = Math.hypot(apts[ka][1] - pa2.x, apts[ka][2] - pa2.y);
        if (da <= ANCHOR_CLICK_TOL) { hitA = apts[ka]; break; }
      }
      if (hitA) {
        assignAnchor(hoverNode, hitA[0], hitA[1], hitA[2]);
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
    }
  }
  // Floating bendpoint: preview-only until dragged >=4px (conversion in
  // onMove); a plain click writes nothing.
  var hf = t && t.closest ? t.closest('.stdraw-wp[data-float="1"]') : null;
  if (hf) {
    var fEi = +hf.getAttribute('data-edge');
    if (!edges[fEi]) return;
    // The floating handle sits exactly under the cursor (it follows the
    // hover point), so a double-click whose second press lands on the edge
    // resolves here — it must participate in the manual dblclick detection
    // or the style cycle dies whenever the preview is visible (same
    // caliber as the free-handle branch below).
    if (edgeDblClickCheck(fEi)) {
      ev.preventDefault();
      return;
    }
    var fp = svgPoint(ev);
    if (!fp) return;
    if ((styles[fEi] || 'auto') === 'free') {
      // Legacy free-mode click-insert: the parked preview must NOT swallow
      // it. On free edges the press delegates to the standard insert flow
      // (click = insert, drag = segment move); floating adoption stays
      // exclusive to edges without explicit user geometry.
      drag = {insert: true, edge: fEi, start: [fp.x, fp.y], ev: ev};
      if (freeWps[fEi] && freeWps[fEi].length) {
        var sdF = segAt(edges[fEi].pts, fp);
        if (sdF) drag.segPrep = sdF.k;
      }
      hideFloat();
      ev.preventDefault();
      ev.stopPropagation();
      return;
    }
    var fsd = segAt(edges[fEi].pts, fp);
    drag = {floatDrag: true, edge: fEi, start: [fp.x, fp.y],
            proj: fsd ? fsd.proj : [fp.x, fp.y], ev: ev};
    try { hf.setPointerCapture(ev.pointerId); } catch (e0) {}
    hideFloat();
    ev.preventDefault();
    ev.stopPropagation();
    return;
  }
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
          // explicit geometry: arm the segment-drag conversion (first
          // movement >=4px turns this click-insert into a segment drag)
          if (freeWps[ei2] && freeWps[ei2].length) {
            var sd0 = segAt(edges[ei2].pts, p1);
            if (sd0) drag.segPrep = sd0.k;
          }
          ev.preventDefault();
        }
      } else if (segDraggable(ei2)) {
        // pinned (user-anchored) polyline: pointerdown arms a segment drag;
        // a click without movement writes nothing
        var p2 = svgPoint(ev);
        if (p2) {
          var sd1 = segAt(edges[ei2].pts, p2);
          if (sd1) {
            drag = {seg: true, edge: ei2, plan: segDragPlan(ei2, sd1.k),
                    start: [p2.x, p2.y], ev: ev};
            ev.preventDefault();
          }
        }
      }
    }
  }
}
function onMove(ev) {
  if (!drag) return;
  var p = svgPoint(ev);
  if (!p) return;
  if (drag.ep) {
    // ref-scrubbed endpoint drag: the endpoint follows the pointer (clamped to
    // the viewBox); the nearest standard anchor of the endpoint's own box is
    // highlighted live; the snap itself happens on release.
    var eE = edges[drag.edge];
    var ptE = clampVB(p.x, p.y);
    var arcPts = arcEpPts(eE, drag.end, ptE);
    if (arcPts) {
      eE.pts = arcPts;
    } else {
      eE.pts[drag.end === 0 ? 0 : eE.pts.length - 1] = ptE;
    }
    markNearAnchor(drag.end === 0 ? eE.a : eE.b, ptE[0], ptE[1]);
    updateEdge(drag.edge);
    return;
  }
  if (drag.floatDrag) {
    // floating bendpoint: preview until the pointer moves >=4px, then
    // adopt the edge geometry + create exactly one fold point and hand
    // over to the standard fold-point drag; below the threshold = no-op
    if (!drag.converted) {
      var mf = Math.hypot(p.x - drag.start[0], p.y - drag.start[1]);
      if (mf < 4) return;
      var fi = drag.edge;
      var wi = adoptFreeAndInsert(fi, drag.proj);
      if (wi === false) {
        showTip('max ' + MAX_FREE_PTS + ' points per edge', drag.ev || ev);
        drag = null;
        return;
      }
      drag = {wp: true, free: true, edge: fi, idx: wi + 1, start: drag.start,
              ox: freeWps[fi][wi][0], oy: freeWps[fi][wi][1], g: null};
      rebuildHandles();
      return;
    }
  }
  if (drag.insert && drag.segPrep !== undefined) {
    // click-insert upgrades to a segment drag on first real movement
    var mi = Math.hypot(p.x - drag.start[0], p.y - drag.start[1]);
    if (mi >= 4) {
      var ci = drag.edge;
      var plan = segDragPlan(ci, drag.segPrep);
      if ((freeWps[ci] || []).length + plan.added > MAX_FREE_PTS) {
        showTip('max ' + MAX_FREE_PTS + ' points per edge', drag.ev || ev);
        drag = null;
        return;
      }
      drag = {seg: true, edge: ci, plan: plan, start: drag.start, ev: drag.ev};
    }
  }
  if (drag.seg) {
    // whole-segment translation: static head/tail waypoints stay, the
    // moving copies of the dragged segment's endpoints follow the pointer
    var pl = drag.plan;
    var dx = p.x - drag.start[0], dy = p.y - drag.start[1];
    var mvPts = pl.mv.map(function (q) {
      return [Math.max(4, Math.min(VB[2] - 4, q[0] + dx)),
              Math.max(4, Math.min(VB[3] - 4, q[1] + dy))];
    });
    applyUserWps(drag.edge, pl.head.concat(mvPts, pl.tail));
    updateEdge(drag.edge);
    rebuildHandles();
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(function () { rafPending = false; refreshMetrics(); });
    }
    return;
  }
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
  if (drag.insert) {
    // Armed click-insert (free mode, fold points may be empty): movement is
    // neither an insert (that is decided on release, <4px) nor a drag —
    // fall-through here would hit the node branch with drag.id undefined
    // (latent TypeError, exposed by the segment-drag interaction paths).
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
  incidentMap[drag.id].forEach(function (i) { touched[i] = 1; safeRerouteUpdate(i, 'drag re-anchor'); });
  renderAnchors();   // ref-scrubbed: anchor dots + pinned markers follow the moved box
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
    if (need) { safeRerouteUpdate(j, 'drag reroute'); }
  });
  rebuildHandles();
  if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(function () { rafPending = false; refreshMetrics(); });
  }
}
function onUp(ev) {
  if (!drag) return;
  if (drag.ep) {
    // ref-scrubbed endpoint release: snap to the nearest standard anchor of the
    // endpoint's OWN box (deterministic tie -> lower ANCHOR_IDS index) and
    // record the explicit designation; subsequent node drags only re-project
    // this endpoint onto the SAME anchor position.
    var eiU = drag.edge, endU = drag.end;
    var eU = edges[eiU];
    var peU = svgPoint(ev);
    var vU = endU === 0 ? eU.a : eU.b;
    var xU, yU;
    if (peU) { var cU = clampVB(peU.x, peU.y); xU = cU[0]; yU = cU[1]; }
    else { var qU = eU.pts[endU === 0 ? 0 : eU.pts.length - 1]; xU = qU[0]; yU = qU[1]; }
    var aidU = nearestAnchorId(vU, xU, yU);
    var coordU = null;
    if (aidU) stdAnchors(nodes[vU]).forEach(function (q) {
      if (q[0] === aidU) coordU = [q[1], q[2]];
    });
    if (aidU && coordU) {
      userAnchored[eiU] = userAnchored[eiU] || {};
      userAnchored[eiU][endU] = aidU;
      var arcU = arcEpPts(eU, endU, coordU);
      if (arcU) eU.pts = arcU;
      else eU.pts[endU === 0 ? 0 : eU.pts.length - 1] = coordU;
      finishUaDesignation(eiU, endU, coordU);
    }
    drag = null;
    setEpVis(eiU, false);   // ref-scrubbed: drag over, dots hide again
    updateEdge(eiU);
    renderAnchors();
    refreshMetrics();
    fireLayoutChanged();
    return;
  }
  // floating bendpoint click (no drag): preview only, nothing persisted
  if (drag.floatDrag) { drag = null; hideFloat(); return; }
  if (drag.insert) {
    var pe = svgPoint(ev);
    var moved = pe ? Math.hypot(pe.x - drag.start[0], pe.y - drag.start[1]) : 1e9;
    if (moved < 4 && (styles[drag.edge] || 'auto') === 'free') {
      insertFreePoint(drag.edge, [pe.x, pe.y], ev);
    }
    drag = null;
    return;
  }
  if (drag.seg) {
    // finalize the segment drag: round the waypoints to the same 0.5
    // caliber as fold-point insertion, then persist via layoutchanged
    var se = drag;
    drag = null;
    var fw = effectiveWps(se.edge).map(function (q) {
      return [Math.round(q[0] * 2) / 2, Math.round(q[1] * 2) / 2];
    });
    applyUserWps(se.edge, fw);
    updateEdge(se.edge);
    rebuildHandles();
    refreshMarkers();
    refreshMetrics();
    fireLayoutChanged();
    return;
  }
  if (drag.wp) {
    // merge-back deletion (finalized lifecycle semantics): a fold point
    // released within MERGE_TOL of the polyline through its neighbors is
    // removed instead of persisted (only after a real drag >=4px, so a
    // plain handle click never deletes)
    var eiU = drag.edge;
    var peU = svgPoint(ev);
    var movedU = peU ? Math.hypot(peU.x - drag.start[0], peU.y - drag.start[1]) : 1e9;
    var posU = drag.free ? (freeWps[eiU] || [])[drag.idx - 1]
                         : (edges[eiU] ? edges[eiU].pts[drag.idx] : null);
    var merged = false;
    if (posU && movedU >= 4) {
      var restU = edges[eiU].pts.slice(0, drag.idx)
                    .concat(edges[eiU].pts.slice(drag.idx + 1));
      if (ptPolyDist(posU[0], posU[1], restU) <= MERGE_TOL) {
        removeWaypoint(eiU, drag.idx);
        showTip('fold point merged', ev);
        merged = true;
      }
    }
    drag = null;
    if (merged) { refreshMarkers(); fireLayoutChanged(); return; }
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
  renderAnchors();   // ref-scrubbed: pinned-anchor dot markers refresh on release
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
    var ua = userAnchored[i];
    var hasUa = !!(ua && (ua[0] || ua[1]));
    if (st !== 'auto' || (wps && wps.length) || hasUa) {
      var it = {a: e.a, b: e.b, style: st};
      // Caliber: an endpoint-anchored edge whose live route is an arc must
      // export its arc kind -- style 'auto' loses the kind and the CLI
      // rerender re-resolves the edge into a raw right-angle polyline
      // (preview smooth curve != rerender). The live ctrl travels with it in
      // final form: the CLI replays the exact same quad (pa, ctrl, pb)
      // instead of re-deriving a forced arc, so the preview curve and the
      // rerender are the same geometry family (lens arcs included).
      if (st === 'auto' && hasUa && !(wps && wps.length) && e.arc && e.ctrl) {
        it.style = 'arc';
        it.ctrl = [Math.round(e.ctrl[0] * 10) / 10,
                   Math.round(e.ctrl[1] * 10) / 10];
      }
      if (wps && wps.length) it.waypoints = wps;
      // ref-scrubbed: explicit standard-anchor designations travel with the
      // export (viewer round-trip via __stdrawApplyLayout edge_anchors)
      if (hasUa) {
        it.anchors = {};
        if (ua[0]) it.anchors.src = ua[0];
        if (ua[1]) it.anchors.dst = ua[1];
      }
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
  userAnchored = {};    // ref-scrubbed: reset also clears explicit anchor designations
  Object.keys(nodes).forEach(function (v) {
    var n = nodes[v];
    n.x = n.bx; n.y = n.by;
    if (n.g) n.g.removeAttribute('transform');
  });
  edges.forEach(function (e, i) {
    // v0.7.11 per-edge isolation on the restore path as well
    try {
    e.pts = e.base.map(cp);
    e.ctrl = (e.arc && e.ctrl0) ? cp(e.ctrl0) : null;   // restore live ctrl too
    e.corners = e.via ? e.via.map(cp) : null;
    var g = visG(i);
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
    var h = hitP(i);
    if (h) h.setAttribute('d', edgeD(e.pts));
    clearDegraded(i);
    } catch (errR) { markDegraded(i, 'reset', errR); }
  });
  Object.keys(polGroups).forEach(function (i) {
    polGroups[i].g.setAttribute('transform', polGroups[i].t);
  });
  syncDomGeometry();   // v0.7.9: keep cards/anchors in sync after restore (no-op when in sync)
  rebuildHandles();
  rebuildAllEndpointHandles();   // ref-scrubbed
  renderAnchors();               // ref-scrubbed: clear stale dots / pinned markers
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
  userAnchored = {};
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
  // ref-scrubbed: restore explicit standard-anchor designations (applied before
  // the re-anchor round so the re-projection caliber sees them)
  var uas = spec.edge_anchors || {};
  Object.keys(uas).forEach(function (k) {
    var i = edgeIdxByKey(k);
    if (i === null || !uas[k] || typeof uas[k] !== 'object') return;
    var rec = {};
    if (ANCHOR_IDS.indexOf(uas[k].src) >= 0) rec[0] = uas[k].src;
    if (ANCHOR_IDS.indexOf(uas[k].dst) >= 0) rec[1] = uas[k].dst;
    if (rec[0] !== undefined || rec[1] !== undefined) userAnchored[i] = rec;
  });
  // Final-form arc ctrl replay (export edges[].ctrl mirror): applied before
  // the re-anchor round so arcFollow translates from THIS base (identity on
  // an unchanged layout) instead of re-deriving a forced arc.
  var ecs = spec.edge_ctrl || {};
  Object.keys(ecs).forEach(function (k) {
    var i = edgeIdxByKey(k), c = ecs[k];
    if (i === null || !edges[i] || !Array.isArray(c) || c.length !== 2 ||
        !isFinite(+c[0]) || !isFinite(+c[1])) return;
    edges[i].arc = true;
    edges[i].ctrl0 = [+c[0], +c[1]];
    edges[i].ctrl = [+c[0], +c[1]];
    if (styles[i] !== 'arc') styles[i] = 'arc';
  });
  edges.forEach(function (e, i) { safeRerouteUpdate(i, 'applyLayout re-anchor'); });
  rebuildAllEndpointHandles();
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
// Segment-drag / floating-bendpoint probe hooks: effective user waypoints
// per edge (free or pinned interior) + floating preview handle state.
window.__stdrawUserWps = function () {
  var out = {};
  edges.forEach(function (e, i) {
    var w = effectiveWps(i);
    if (w.length) out[i] = w;
  });
  return out;
};
window.__stdrawFloating = function () {
  if (!floatC || floatC.style.display === 'none') return null;
  return {edge: +floatC.getAttribute('data-edge'),
          cx: +floatC.getAttribute('cx'), cy: +floatC.getAttribute('cy')};
};
window.__stdrawSegDraggable = function (i) { return segDraggable(i); };
// v0.7.11 fault-injection hook for the DOM-truth probe (ref-scrubbed): force a
// single edge's reroute to throw so the probe can assert per-edge isolation +
// the visible degradation marker; pass false to clear (self-heal check).
window.__stdrawProbeBreakEdge = function (i, on) {
  if (edges[i]) edges[i]._probeThrow = !!on;
  return true;
};
window.__stdrawDragState = function () {
  if (!drag) return null;
  var keys = [];
  for (var k in drag) keys.push(k);
  return {keys: keys, edge: drag.edge, free: drag.free};
};
window.__stdrawArcFlag = function (i) { return !!edges[i].arc; };
// ── ref-scrubbed probe/integration hooks ──
window.__stdrawAnchors = function (v) {
  return nodes[v] ? stdAnchors(nodes[v]) : null;
};
window.__stdrawUserAnchors = function () {
  return JSON.parse(JSON.stringify(userAnchored));
};
window.__stdrawSetAnchor = function (i, end, aid) {
  if (!edges[i] || ANCHOR_IDS.indexOf(aid) < 0 || (end !== 0 && end !== 1)) return false;
  userAnchored[i] = userAnchored[i] || {};
  userAnchored[i][end] = aid;
  safeRerouteUpdate(i, 'set anchor');
  updateEdge(i);
  renderAnchors();
  refreshMetrics();
  fireLayoutChanged();
  return true;
};
window.__stdrawAnchorDots = function () {
  var out = [];
  anchorLayer.querySelectorAll('circle.stdraw-anchor').forEach(function (c) {
    out.push([c.getAttribute('data-node'), c.getAttribute('data-aid'),
              +c.getAttribute('cx'), +c.getAttribute('cy')]);
  });
  return out;
};
window.__stdrawAnchorToggleState = function () { return !!anchorToggle; };
window.__stdrawSetAnchorToggle = function (on) { setAnchorToggle(!!on); };   // ref-scrubbed probe hook
window.__stdrawEndpointHandleVis = function () {
  var out = [];
  epsLayer.querySelectorAll('circle.stdraw-ep').forEach(function (c) {
    out.push([+c.getAttribute('data-edge'), +c.getAttribute('data-end'),
              getComputedStyle(c).opacity]);
  });
  return out;
};
window.__stdrawEndpointHandles = function () {
  var out = [];
  epsLayer.querySelectorAll('circle.stdraw-ep').forEach(function (c) {
    out.push([+c.getAttribute('data-edge'), +c.getAttribute('data-end'),
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
var btnA = document.getElementById('stdraw-anchors-toggle');
if (btnA) {
  btnA.textContent = 'Anchors: ' + (anchorToggle ? 'on' : 'off');   // ref-scrubbed: default off
  btnA.addEventListener('click', function () { setAnchorToggle(!anchorToggle); });
}
rebuildHandles();
rebuildAllEndpointHandles();   // ref-scrubbed: initial endpoint handle placement
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
