#!/usr/bin/env python3
"""D0 delivery gate: no vertical-orthogonal (ortho-v1) page may ship.

jacky, 2026-11-11 20:46: vertical-orthogonal diagrams are BANNED as
deliverables ("box-over-line everywhere, repeatedly unfixable" -- ruling D0,
WorkBuddy task 2026-11-11).  Isolation, not repair: the ortho-v1 recipe
itself stays frozen for CI byte-regression (AGENTS.md freeze rule,
tests/baselines/ untouched); what this scanner blocks is the DELIVERY EXIT --
any vertical-orthogonal output directory that ships an .html page.

Signals (any hit marks the directory vertical-orthogonal):
  1  certificate.json .caliber     == "v1-legacy"
  2  certificate.json .recipe      == "ortho-v1"
  3  certificate.json .deliverable == false
  4  layout.json .meta.method contains "wires strictly vertical"
  5  layout.json has "bars" AND every edge is a single-x vertical segment
     (edge keys a subset of {a, b, x, y1, y2}; no waypoints)
  6  geometry_report.json contains "all lines strictly vertical"

Verdict per scanned directory tree:
  .html deliverable present + signals  -> VIOLATION, exit 1
  signals, no .html                    -> regression data only
     (layout.json / certificate.json / geometry_report.json stay legal for
     the CI byte-regression baseline): reported, not fatal.
Signals 1-3 are certificate confessions; 4-6 are geometry fallbacks that
always run, so a stripped / hand-made product cannot bypass the gate
(D0 anti-bypass rule).

Usage:
  python scripts/check_no_ortho_delivery.py             # scans demos/
  python scripts/check_no_ortho_delivery.py --dir OUT   # any output dir

Exit codes: 0 = no vertical-orthogonal deliverable, 1 = violation found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

VERTICAL_EDGE_KEYS = {"a", "b", "x", "y1", "y2", "arrow"}


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def certificate_signals(cert):
    """Signals 1-3: the certificate's own delivery confession."""
    hits = []
    if not isinstance(cert, dict):
        return hits
    if cert.get("caliber") == "v1-legacy":
        hits.append('certificate.caliber == "v1-legacy"')
    if cert.get("recipe") == "ortho-v1":
        hits.append('certificate.recipe == "ortho-v1"')
    if cert.get("deliverable") is False:
        hits.append("certificate.deliverable == false")
    return hits


def layout_signals(lay):
    """Signals 4-5: geometry fallbacks (anti-bypass)."""
    hits = []
    if not isinstance(lay, dict):
        return hits
    method = str((lay.get("meta") or {}).get("method") or "")
    if "wires strictly vertical" in method:
        hits.append('layout.meta.method: "wires strictly vertical"')
    bars = lay.get("bars")
    edges = lay.get("edges")
    if bars and isinstance(edges, list) and edges and all(
            set(e) <= VERTICAL_EDGE_KEYS for e in edges
            if isinstance(e, dict)):
        hits.append("layout: leader bars + single-x vertical edges "
                    "(no waypoints)")
    return hits


def geometry_signals(text):
    """Signal 6: geometry self-report fallback (anti-bypass)."""
    if text and "all lines strictly vertical" in text:
        return ['geometry_report: "all lines strictly vertical"']
    return []


def scan_directory(path):
    """Return (violations, notes) for one output directory."""
    cert = _load_json(os.path.join(path, "certificate.json"))
    lay = _load_json(os.path.join(path, "layout.json"))
    try:
        with open(os.path.join(path, "geometry_report.json"),
                  encoding="utf-8") as f:
            geo_text = f.read()
    except OSError:
        geo_text = None
    hits = (certificate_signals(cert) + layout_signals(lay)
            + geometry_signals(geo_text))
    htmls = sorted(fn for fn in os.listdir(path)
                   if fn.lower().endswith(".html"))
    if hits and htmls:
        return ([(path, hits, htmls)], [])
    if hits:
        return ([], [(path, hits)])
    return ([], [])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="D0 gate: reject vertical-orthogonal deliverables")
    ap.add_argument("--dir", default="demos",
                    help="output directory (or repo subtree) to scan")
    args = ap.parse_args()
    root = args.dir
    if not os.path.isdir(root):
        print(f"check_no_ortho_delivery: no such directory: {root}")
        return 1
    violations, notes = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        v, n = scan_directory(dirpath)
        violations += v
        notes += n
    for path, hits in notes:
        print(f"NOTE  {path}: vertical-orthogonal regression data, no .html "
              f"deliverable (legal CI baseline) -- {', '.join(hits)}")
    for path, hits, htmls in violations:
        print(f"VIOLATION  {path}: vertical-orthogonal DELIVERABLE banned "
              f"by D0 -- pages: {', '.join(htmls)}")
        for h in hits:
            print(f"           signal: {h}")
    if violations:
        print(f"\nD0 gate: FAIL ({len(violations)} vertical-orthogonal "
              f"deliverable(s)) -- use the auto-v2 recipe for deliverables; "
              f"ortho-v1 stays a frozen CI-regression baseline only")
        return 1
    print("D0 gate: OK (no vertical-orthogonal deliverable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
