# Unified evaluator: any tool's layout (node boxes + edge polylines) -> six metrics (native-coordinate conventions).
#
# Conventions (detailed in REPORT.md §2):
#   All tools take the same input (same labels, same box size w×h px, box width uniformly provided by stdraw textmetrics;
#   Graphviz receives inch=px/72, ELK/stdraw take px directly -- each tool's native coordinates are likewise in "physical px",
#   so the same box has the same px size in every tool).
#   Threshold metrics (clearance violation 16px / box press 1px) are judged in absolute px on native coordinates, comparable across tools;
#   scale-invariant metrics (crossings/CV/row alignment) are unaffected by coordinate scale; bbox is also reported as a canvas-efficiency reference.
#   No forced scaling normalization -- scaling changes the physical semantics of thresholds; whichever tool gets scaled losing out is not a quality difference.
#
# Metric definitions are same-source with stdraw/metrics.py and stdraw/routing.py (their functions are reused directly):
#   crossings        adjacent edges excluded, strict polyline intersection (seg_cross)
#   box_press        edge polyline enters a non-endpoint box (with 1px margin, dist_point_rect)
#   clear_violations number of (edge, box) pairs where the edge-to-non-endpoint-box minimum distance < 16px
#   spacing_cv       nearest-neighbor center distance std/mean
#   row_align_rate   share of nodes on a visual row (y difference <= 4px)
#   runtime_s        passed in from runner timing
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)

from stdraw.metrics import seg_cross                       # noqa: E402
from stdraw.routing import sample_polyline, dist_point_rect  # noqa: E402
from stdraw import textmetrics                             # noqa: E402

CLEARANCE = 16.0        # clearance threshold px (same value as the stdraw hard gate)
PRESS_MARGIN = 1        # box press margin px
ROW_EPS = 4.0           # visual same-row tolerance px
FS_TITLE = 15.0         # font size matching the stdraw auto recipe


def box_size(label: str):
    """Uniform-style box size (layout-engine independent): stdraw textmetrics resolved width + conservative padding."""
    w, h = textmetrics.card_size(label, "", FS_TITLE, FS_TITLE)
    return int(w), int(h)


def evaluate(nodes, routes, edges, runtime_s, tool, graph, extra=None):
    """nodes {id:(x,y,w,h)}, routes {edge_idx:[pts]}, edges [{a,b}] (same order as routes).
    Everything is judged on native coordinates (see the conventions in the file header)."""
    ids = list(nodes)

    # 1. Crossings (adjacent edges sharing an endpoint are not counted)
    crossings = 0
    n_e = len(edges)
    for i in range(n_e):
        for j in range(i + 1, n_e):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            pi, pj = routes.get(i), routes.get(j)
            if not pi or not pj:
                continue
            for s1 in zip(pi[:-1], pi[1:]):
                hit = False
                for s2 in zip(pj[:-1], pj[1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    crossings += 1
                    break

    # 2. Box press / clearance violations (sampled polyline vs non-endpoint boxes)
    press = 0
    clear_violations = 0
    min_clear = None
    for i, e in enumerate(edges):
        pts = sample_polyline(routes.get(i) or [])
        for v in ids:
            if v in (e["a"], e["b"]):
                continue
            p = nodes[v]
            d = min(dist_point_rect(px, py, p[0], p[1], p[2] / 2 + PRESS_MARGIN,
                                    p[3] / 2 + PRESS_MARGIN) for (px, py) in pts)
            if d <= 0:
                press += 1
            dmin = min(dist_point_rect(px, py, p[0], p[1], p[2] / 2, p[3] / 2)
                       for (px, py) in pts)
            if dmin < CLEARANCE:
                clear_violations += 1
            min_clear = dmin if min_clear is None else min(min_clear, dmin)

    # 3. CV (nearest-neighbor center distance std/mean)
    nn = []
    for a in ids:
        (ax, ay, _, _) = nodes[a]
        ds = [math.dist((ax, ay), (nodes[b][0], nodes[b][1])) for b in ids if b != a]
        if ds:
            nn.append(min(ds))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) \
        if nn and mean_nn else 0.0

    # 4. Row alignment rate (grouped when the y difference is <= 4px)
    ys = sorted(p[1] for p in nodes.values())
    aligned, i = 0, 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] - ys[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    W = (max(p[0] + p[2] / 2 for p in nodes.values()) -
         min(p[0] - p[2] / 2 for p in nodes.values()))
    H = (max(p[1] + p[3] / 2 for p in nodes.values()) -
         min(p[1] - p[3] / 2 for p in nodes.values()))

    return {
        "tool": tool, "graph": graph,
        "crossings": crossings,
        "box_press": press,
        "clear_violations": clear_violations,
        "min_edge_box_clear_px": round(min_clear, 1) if min_clear is not None else None,
        "spacing_cv": round(cv, 3),
        "row_align_rate": round(row_rate, 3),
        "runtime_s": round(runtime_s, 3),
        "bbox": [round(W), round(H)],
        "bbox_area": round(W * H),
        "status": "ok",
        **(extra or {}),
    }
